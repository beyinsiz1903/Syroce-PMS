"""
PMS Availability & Room Blocks Router — Core inventory management.
Extracted from pms.py (Stage 3d-availability — FINAL extraction).

CRITICAL: This is the most sensitive module in the PMS.
Room blocks directly affect availability calculations.
Any bug here can cause overbooking or inventory drift.

Routes:
  GET   /pms/room-blocks
  POST  /pms/room-blocks
  PATCH /pms/room-blocks/{block_id}
  POST  /pms/room-blocks/{block_id}/cancel
  GET   /pms/rooms/availability

Dependencies:
  - AvailabilityReadService (semantic inventory)
  - CreateRoomBlockService (idempotent block creation)
  - ReleaseRoomBlockService (block cancellation)
  - Shadow compare (legacy parity validation)
"""
import asyncio
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request

from core.database import db
from core.security import get_current_user
from models.schemas import User

try:
    from domains.pms.room_block_models import RoomBlockCreate
except ImportError:
    RoomBlockCreate = None

from modules.inventory.services.availability_read_service import AvailabilityReadService
from modules.inventory.services.create_room_block_service import CreateRoomBlockService
from modules.inventory.services.release_room_block_service import ReleaseRoomBlockService
from shared_kernel.shadow_metrics import compare_availability_payloads, run_shadow_compare

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator

router = APIRouter(prefix="/api", tags=["pms-availability"])

create_room_block_service = CreateRoomBlockService()
release_room_block_service = ReleaseRoomBlockService()
availability_read_service = AvailabilityReadService()


# ═══════════════════════════════════════════════════════════════════
# Room Blocks (mutation paths that affect availability)
# ═══════════════════════════════════════════════════════════════════

@router.get("/pms/room-blocks")
async def get_room_blocks(
    room_id: str | None = None,
    status: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Get room blocks with optional filters"""
    query = {'tenant_id': current_user.tenant_id}

    if room_id:
        query['room_id'] = room_id

    if status:
        query['status'] = status

    if from_date or to_date:
        date_query = {}
        if from_date:
            date_query['$gte'] = from_date
        if to_date:
            date_query['$lte'] = to_date
        query['start_date'] = date_query

    blocks = await db.room_blocks.find(query, {'_id': 0}).to_list(1000)

    # Filter expired blocks
    today = datetime.now(UTC).date().isoformat()
    for block in blocks:
        if block.get('end_date') and block['end_date'] < today and block['status'] == 'active':
            # Auto-expire
            await db.room_blocks.update_one(
                {'id': block['id']},
                {'$set': {'status': 'expired'}}
            )
            block['status'] = 'expired'

    return blocks


@router.post("/pms/room-blocks")
async def create_room_block(
    block_data: dict,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    payload = RoomBlockCreate(**block_data)
    return await create_room_block_service.create(payload, current_user, request)


@router.patch("/pms/room-blocks/{block_id}")
async def update_room_block(
    block_id: str,
    updates: dict,
    current_user: User = Depends(get_current_user)
):
    """Update a room block"""
    existing = await db.room_blocks.find_one({
        'tenant_id': current_user.tenant_id,
        'id': block_id
    })

    if not existing:
        raise HTTPException(404, "Block not found")

    # Only allow updates to active blocks
    if existing['status'] != 'active':
        raise HTTPException(400, "Cannot update cancelled or expired blocks")

    update_data = {}
    allowed_fields = ['reason', 'details', 'start_date', 'end_date', 'allow_sell']

    for field in allowed_fields:
        if field in updates:
            update_data[field] = updates[field]

    if update_data:
        await db.room_blocks.update_one(
            {'id': block_id},
            {'$set': update_data}
        )

        # Audit log
        await db.audit_logs.insert_one({
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'action': 'room_block_updated',
            'entity_type': 'room_block',
            'entity_id': block_id,
            'user': current_user.name,
            'timestamp': datetime.now(UTC).isoformat(),
            'details': update_data
        })

    updated = await db.room_blocks.find_one({'id': block_id}, {'_id': 0})
    return updated


@router.post("/pms/room-blocks/{block_id}/cancel")
async def cancel_room_block(
    block_id: str,
    request: Request,
    reason: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Release a room block through the semantic inventory service."""
    return await release_room_block_service.release(block_id, current_user, request, reason=reason)


# ═══════════════════════════════════════════════════════════════════
# Availability (read path — queries blocks + bookings)
# ═══════════════════════════════════════════════════════════════════

@router.get("/pms/rooms/availability")
@cached(ttl=120, key_prefix="rooms_availability")  # Cache for 2 min
async def check_room_availability(
    check_in: str,
    check_out: str,
    request: Request,
    room_type: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Check room availability including blocks"""
    semantic_response = await availability_read_service.get_availability(
        tenant_id=current_user.tenant_id,
        check_in=check_in,
        check_out=check_out,
        room_type=room_type,
    )
    asyncio.create_task(
        run_shadow_compare(
            endpoint="availability",
            tenant_id=current_user.tenant_id,
            property_id=request.headers.get("x-property-id"),
            correlation_id=request.headers.get("x-correlation-id"),
            semantic_payload=semantic_response,
            legacy_loader=lambda: _legacy_check_room_availability(
                tenant_id=current_user.tenant_id,
                check_in=check_in,
                check_out=check_out,
                room_type=room_type,
            ),
            comparator=compare_availability_payloads,
            entity_id=f"{check_in}:{check_out}:{room_type or '*'}",
        )
    )
    return semantic_response


async def _legacy_check_room_availability(
    tenant_id: str,
    check_in: str,
    check_out: str,
    room_type: str | None = None,
):
    query = {'tenant_id': tenant_id}

    if room_type:
        query['room_type'] = room_type

    rooms = await db.rooms.find(query, {'_id': 0}).to_list(1000)
    bookings = await db.bookings.find({
        'tenant_id': tenant_id,
        'status': {'$in': ['confirmed', 'checked_in', 'guaranteed']},
        'check_in': {'$lt': check_out},
        'check_out': {'$gt': check_in}
    }, {'_id': 0}).to_list(1000)
    blocks = await db.room_blocks.find({
        'tenant_id': tenant_id,
        'status': 'active',
        'start_date': {'$lt': check_out},
        '$or': [
            {'end_date': {'$gt': check_in}},
            {'end_date': None}
        ]
    }, {'_id': 0}).to_list(1000)

    available = []
    for room in rooms:
        is_booked = any(b['room_id'] == room['id'] for b in bookings)
        room_blocks = [b for b in blocks if b['room_id'] == room['id']]
        is_blocked = any(not b.get('allow_sell', False) for b in room_blocks)

        if not is_booked and not is_blocked:
            available.append({
                **room,
                'available': True
            })
        else:
            unavailable_reason = []
            if is_booked:
                unavailable_reason.append('booked')
            if is_blocked:
                block_info = [b for b in room_blocks if not b.get('allow_sell')]
                if block_info:
                    unavailable_reason.append(f"{block_info[0]['type']}")

            available.append({
                **room,
                'available': False,
                'reason': ', '.join(unavailable_reason),
                'blocks': room_blocks
            })

    return available
