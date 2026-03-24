"""
PMS Router -- Core routes (availability, reservations, room services, queue, etc.)
Booking/dashboard routes -> pms_bookings.py / pms_dashboard.py.
Room/guest routes -> pms_rooms.py / pms_guests.py.
"""
import asyncio
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from core.database import db
from core.helpers import create_audit_log
from core.security import get_current_user
from core.utils import get_cancellation_policy_details
from models.enums import CancellationPolicyType
from models.schemas import User
from routers.pms_shared import get_guest_name

try:
    from domains.pms.night_audit_module import QueueRoom
    from domains.pms.room_block_models import RoomBlockCreate
except ImportError:
    RoomBlockCreate = None
    QueueRoom = None

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

router = APIRouter(prefix="/api", tags=["pms"])
security = HTTPBearer()
create_room_block_service = CreateRoomBlockService()
release_room_block_service = ReleaseRoomBlockService()
availability_read_service = AvailabilityReadService()

# -- Extracted: bookings -> pms_bookings.py, dashboard -> pms_dashboard.py --
# -- Extracted: rooms -> pms_rooms.py, guests -> pms_guests.py --

@router.get("/pms/room-services")
@cached(ttl=300, key_prefix="pms_room_services")  # Cache for 5 min
async def get_hotel_room_services(current_user: User = Depends(get_current_user)):
    services = await db.room_services.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    return services


@router.put("/pms/room-services/{service_id}")
async def update_room_service(service_id: str, updates: Dict[str, Any], current_user: User = Depends(get_current_user)):
    if 'status' in updates and updates['status'] == 'completed':
        updates['completed_at'] = datetime.now(timezone.utc).isoformat()
    await db.room_services.update_one({'id': service_id, 'tenant_id': current_user.tenant_id}, {'$set': updates})
    service = await db.room_services.find_one({'id': service_id}, {'_id': 0})
    return service


@router.get("/pms/room-blocks")
async def get_room_blocks(
    room_id: Optional[str] = None,
    status: Optional[str] = None,
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
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
    today = datetime.now(timezone.utc).date().isoformat()
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
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'details': update_data
        })

    updated = await db.room_blocks.find_one({'id': block_id}, {'_id': 0})
    return updated


@router.post("/pms/room-blocks/{block_id}/cancel")
async def cancel_room_block(
    block_id: str,
    request: Request,
    reason: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Release a room block through the semantic inventory service."""
    return await release_room_block_service.release(block_id, current_user, request, reason=reason)


@router.get("/pms/rooms/availability")
@cached(ttl=120, key_prefix="rooms_availability")  # Cache for 2 min
async def check_room_availability(
    check_in: str,
    check_out: str,
    request: Request,
    room_type: Optional[str] = None,
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
    room_type: Optional[str] = None,
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


@router.get("/pms/staff-tasks")
async def get_staff_tasks(
    department: Optional[str] = None,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get staff tasks (engineering, housekeeping, maintenance)"""
    query = {'tenant_id': current_user.tenant_id}
    if department:
        query['department'] = department
    if status:
        query['status'] = status

    tasks = await db.staff_tasks.find(query, {'_id': 0}).sort('created_at', -1).to_list(1000)
    return tasks


@router.post("/pms/staff-tasks")
async def create_staff_task(
    task_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Create a new staff task"""
    task = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'task_type': task_data.get('task_type', 'maintenance'),
        'department': task_data.get('department', 'engineering'),
        'title': task_data.get('title', 'Staff Task'),
        'room_id': task_data.get('room_id'),
        'priority': task_data.get('priority', 'normal'),
        'description': task_data.get('description'),
        'assigned_to': task_data.get('assigned_to'),
        'status': task_data.get('status', 'pending'),
        'created_by': current_user.id,
        'created_at': datetime.now(timezone.utc).isoformat()
    }

    # Get room number if room_id provided
    if task['room_id']:
        room = await db.rooms.find_one({'id': task['room_id']}, {'_id': 0, 'room_number': 1})
        if room:
            task['room_number'] = room['room_number']

    await db.staff_tasks.insert_one(task)

    # Return the task without MongoDB ObjectId
    return {
        'id': task['id'],
        'tenant_id': task['tenant_id'],
        'task_type': task['task_type'],
        'department': task['department'],
        'title': task['title'],
        'room_id': task['room_id'],
        'room_number': task.get('room_number'),
        'priority': task['priority'],
        'description': task['description'],
        'assigned_to': task['assigned_to'],
        'status': task['status'],
        'created_by': task['created_by'],
        'created_at': task['created_at']
    }


@router.put("/pms/staff-tasks/{task_id}")
async def update_staff_task(
    task_id: str,
    update_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Update staff task status"""
    await db.staff_tasks.update_one(
        {'id': task_id, 'tenant_id': current_user.tenant_id},
        {'$set': update_data}
    )

    # Return updated task
    updated_task = await db.staff_tasks.find_one(
        {'id': task_id, 'tenant_id': current_user.tenant_id},
        {'_id': 0}
    )

    if not updated_task:
        raise HTTPException(status_code=404, detail="Task not found")

    return updated_task


@router.get("/pms/allotment-contracts")
async def get_allotment_contracts(
    current_user: User = Depends(get_current_user)
):
    """Get tour operator allotment contracts with dynamic usage count"""
    contracts = await db.allotment_contracts.find({
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).to_list(1000)

    # Dynamically calculate used_rooms from active bookings
    ACTIVE_STATUSES = ["pending", "confirmed", "guaranteed", "checked_in"]
    for contract in contracts:
        room_type = contract.get('room_type')
        start_date = contract.get('start_date')
        end_date = contract.get('end_date')
        if room_type and start_date and end_date:
            # Find rooms of this type
            room_ids = []
            async for room in db.rooms.find(
                {"tenant_id": current_user.tenant_id, "room_type": room_type},
                {"_id": 0, "id": 1}
            ):
                room_ids.append(room["id"])

            if room_ids:
                used = await db.bookings.count_documents({
                    "tenant_id": current_user.tenant_id,
                    "room_id": {"$in": room_ids},
                    "status": {"$in": ACTIVE_STATUSES},
                    "check_in": {"$lt": end_date},
                    "check_out": {"$gt": start_date},
                })
                contract['used_rooms'] = used

    return contracts


@router.post("/pms/allotment-contracts")
async def create_allotment_contract(
    contract_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Create new allotment contract"""
    contract = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'tour_operator': contract_data.get('tour_operator'),
        'room_type': contract_data.get('room_type'),
        'allocated_rooms': contract_data.get('allocated_rooms'),
        'used_rooms': 0,
        'start_date': contract_data.get('start_date'),
        'end_date': contract_data.get('end_date'),
        'rate': contract_data.get('rate'),
        'release_days': contract_data.get('release_days', 7),
        'status': 'active',
        'created_at': datetime.now(timezone.utc).isoformat()
    }

    await db.allotment_contracts.insert_one(contract)
    return contract


@router.post("/pms/allotment-contracts/{contract_id}/release")
async def release_allotment_rooms(
    contract_id: str,
    current_user: User = Depends(get_current_user)
):
    """Release unused allotment rooms back to inventory"""
    contract = await db.allotment_contracts.find_one({
        'id': contract_id,
        'tenant_id': current_user.tenant_id
    })

    if not contract:
        raise HTTPException(status_code=404, detail="Contract not found")

    available_rooms = contract['allocated_rooms'] - contract.get('used_rooms', 0)

    await db.allotment_contracts.update_one(
        {'id': contract_id},
        {'$set': {
            'released_rooms': available_rooms,
            'released_at': datetime.now(timezone.utc).isoformat()
        }}
    )

    return {
        "message": f"Released {available_rooms} rooms",
        "released_rooms": available_rooms
    }


@router.get("/pms/group-reservations")
async def get_group_reservations(current_user: User = Depends(get_current_user)):
    groups = await db.group_reservations.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(100)
    return {'groups': groups}


@router.post("/pms/group-reservations")
async def create_group_reservation(
    group_data: dict,
    current_user: User = Depends(get_current_user)
):
    group = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        **group_data,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    await db.group_reservations.insert_one(group)
    return group


@router.get("/pms/setup-status")
async def pms_setup_status(current_user: User = Depends(get_current_user)):
    """Return minimal setup status for PMS Lite onboarding (rooms/bookings counts)."""
    rooms_count = await db.rooms.count_documents({"tenant_id": current_user.tenant_id})
    bookings_count = await db.bookings.count_documents({"tenant_id": current_user.tenant_id})
    return {"rooms_count": rooms_count, "bookings_count": bookings_count}



class RoomNote(BaseModel):
    """Room-specific notes"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_id: str
    note_type: str  # maintenance, issue, preference, general
    description: str
    priority: str = "normal"
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved: bool = False
    resolved_at: Optional[datetime] = None


class MiniBarUpdate(BaseModel):
    """Mini-bar last update tracking"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_id: str
    updated_by: str
    items_restocked: Dict[str, int] = {}  # {item_name: quantity}
    items_consumed: Dict[str, int] = {}
    total_value: float = 0.0
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


@router.get("/rooms/{room_id}/details-enhanced")
@cached(ttl=180, key_prefix="room_details_enhanced")  # Cache for 3 min
async def get_room_details_enhanced(
    room_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get enhanced room details including:
    - Room notes (TV issues, pillow requests, etc)
    - Mini-bar last update
    - Next maintenance due
    """
    room = await db.rooms.find_one({
        'id': room_id,
        'tenant_id': current_user.tenant_id
    })

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    # Get room notes
    notes = []
    async for note in db.room_notes.find({
        'room_id': room_id,
        'tenant_id': current_user.tenant_id,
        'resolved': False
    }).sort('created_at', -1).limit(10):
        notes.append({
            'id': note.get('id'),
            'note_type': note.get('note_type'),
            'description': note.get('description'),
            'priority': note.get('priority'),
            'created_by': note.get('created_by'),
            'created_at': note.get('created_at')
        })

    # Get mini-bar last update
    minibar_update = await db.minibar_updates.find_one({
        'room_id': room_id,
        'tenant_id': current_user.tenant_id
    }, sort=[('updated_at', -1)])

    minibar_info = None
    if minibar_update:
        updated_at = datetime.fromisoformat(minibar_update.get('updated_at'))
        hours_ago = (datetime.now(timezone.utc) - updated_at).total_seconds() / 3600

        minibar_info = {
            'last_updated': minibar_update.get('updated_at'),
            'hours_ago': round(hours_ago, 1),
            'updated_by': minibar_update.get('updated_by'),
            'items_restocked': minibar_update.get('items_restocked', {}),
            'items_consumed': minibar_update.get('items_consumed', {}),
            'total_value': minibar_update.get('total_value', 0.0),
            'needs_restock': hours_ago > 24
        }

    # Get next maintenance due
    next_maintenance = await db.maintenance_schedule.find_one({
        'room_id': room_id,
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['scheduled', 'pending']},
        'scheduled_date': {'$gte': datetime.now(timezone.utc).isoformat()}
    }, sort=[('scheduled_date', 1)])

    maintenance_info = None
    if next_maintenance:
        scheduled_date = datetime.fromisoformat(next_maintenance.get('scheduled_date'))
        days_until = (scheduled_date - datetime.now(timezone.utc)).days

        maintenance_info = {
            'scheduled_date': next_maintenance.get('scheduled_date'),
            'days_until': days_until,
            'maintenance_type': next_maintenance.get('maintenance_type'),
            'description': next_maintenance.get('description'),
            'priority': next_maintenance.get('priority'),
            'is_overdue': days_until < 0
        }

    return {
        'room_id': room_id,
        'room_number': room.get('room_number'),
        'room_type': room.get('room_type'),
        'status': room.get('status'),
        'notes': notes,
        'notes_count': len(notes),
        'minibar': minibar_info,
        'next_maintenance': maintenance_info,
        'alerts': [
            f"⚠️ {len(notes)} unresolved room notes" if notes else "✅ No outstanding room issues",
            "🍷 Mini-bar needs restock" if minibar_info and minibar_info.get('needs_restock') else None,
            f"🔧 Maintenance due in {maintenance_info['days_until']} days" if maintenance_info and maintenance_info['days_until'] <= 7 else None,
            "🚨 Maintenance OVERDUE!" if maintenance_info and maintenance_info.get('is_overdue') else None
        ]
    }



@router.post("/rooms/{room_id}/notes")
async def add_room_note(
    room_id: str,
    note_type: str,
    description: str,
    priority: str = "normal",
    current_user: User = Depends(get_current_user)
):
    """Add a note to a room"""
    note = RoomNote(
        tenant_id=current_user.tenant_id,
        room_id=room_id,
        note_type=note_type,
        description=description,
        priority=priority,
        created_by=current_user.name
    )

    note_dict = note.model_dump()
    note_dict['created_at'] = note_dict['created_at'].isoformat()
    await db.room_notes.insert_one(note_dict)

    return {'success': True, 'note_id': note.id, 'message': 'Room note added'}



@router.post("/rooms/{room_id}/minibar-update")
async def update_minibar(
    room_id: str,
    items_restocked: Dict[str, int] = {},
    items_consumed: Dict[str, int] = {},
    total_value: float = 0.0,
    current_user: User = Depends(get_current_user)
):
    """Update mini-bar status"""
    update = MiniBarUpdate(
        tenant_id=current_user.tenant_id,
        room_id=room_id,
        updated_by=current_user.name,
        items_restocked=items_restocked,
        items_consumed=items_consumed,
        total_value=total_value
    )

    update_dict = update.model_dump()
    update_dict['updated_at'] = update_dict['updated_at'].isoformat()
    await db.minibar_updates.insert_one(update_dict)

    return {'success': True, 'update_id': update.id, 'message': 'Mini-bar updated'}



@router.get("/reservations/{booking_id}/details-enhanced")
async def get_reservation_details_enhanced(
    booking_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Enhanced reservation details showing:
    - Cancellation policy
    - OTA commission info
    - Rate breakdown
    """
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Reservation not found")

    # Cancellation policy details
    policy = booking.get('cancellation_policy', CancellationPolicyType.H24)
    policy_details = get_cancellation_policy_details(policy)

    # OTA commission
    commission_info = None
    if booking.get('ota_channel'):
        commission_pct = booking.get('commission_pct', 15.0)
        total_amount = booking.get('total_amount', 0)
        commission_amount = total_amount * (commission_pct / 100)
        net_revenue = total_amount - commission_amount

        commission_info = {
            'ota_channel': booking.get('ota_channel'),
            'ota_confirmation': booking.get('ota_confirmation'),
            'commission_pct': commission_pct,
            'commission_amount': round(commission_amount, 2),
            'gross_revenue': round(total_amount, 2),
            'net_revenue': round(net_revenue, 2),
            'payment_model': booking.get('payment_model')
        }

    return {
        'booking_id': booking_id,
        'status': booking.get('status'),
        'cancellation_policy': {
            'type': policy,
            **policy_details
        },
        'commission': commission_info,
        'rate_breakdown': {
            'base_rate': booking.get('base_rate'),
            'total_amount': booking.get('total_amount'),
            'rate_type': booking.get('rate_type'),
            'market_segment': booking.get('market_segment')
        }
    }



@router.get("/reservations/double-booking-check")
async def check_double_booking_conflicts(
    date: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Double-booking conflict detection engine
    - Identify potential conflicts
    - Room assignment overlaps
    """
    target_date = date or datetime.now().date().isoformat()

    # Get all bookings for the date
    bookings = []
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
        'check_in': {'$lte': target_date},
        'check_out': {'$gte': target_date}
    }):
        bookings.append(booking)

    # Group by room
    room_bookings = {}
    for booking in bookings:
        room_id = booking.get('room_id')
        if room_id not in room_bookings:
            room_bookings[room_id] = []
        room_bookings[room_id].append(booking)

    # Find conflicts
    conflicts = []
    for room_id, room_booking_list in room_bookings.items():
        if len(room_booking_list) > 1:
            # Potential conflict
            room = await db.rooms.find_one({'id': room_id})
            conflicts.append({
                'room_id': room_id,
                'room_number': room.get('room_number') if room else 'Unknown',
                'booking_count': len(room_booking_list),
                'bookings': [{
                    'booking_id': b.get('id'),
                    'guest_id': b.get('guest_id'),
                    'check_in': b.get('check_in'),
                    'check_out': b.get('check_out'),
                    'status': b.get('status')
                } for b in room_booking_list]
            })

    return {
        'date': target_date,
        'total_conflicts': len(conflicts),
        'conflicts': conflicts,
        'status': 'conflicts_found' if conflicts else 'no_conflicts'
    }



@router.get("/reservations/adr-visibility")
async def get_adr_and_rate_visibility(
    start_date: str,
    end_date: str,
    room_type: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    ADR (Average Daily Rate) and rate code visibility
    - Daily ADR
    - By rate code
    - By room type
    """
    # Get all bookings in date range
    bookings = []
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': start_date,
            '$lte': end_date
        }
    }):
        bookings.append(booking)

    # Calculate ADR
    total_room_revenue = sum(b.get('total_amount', 0) for b in bookings)
    total_room_nights = sum(
        (datetime.fromisoformat(b.get('check_out')) - datetime.fromisoformat(b.get('check_in'))).days
        for b in bookings
    )

    adr = total_room_revenue / total_room_nights if total_room_nights > 0 else 0

    # By rate type
    rate_breakdown = {}
    for booking in bookings:
        rate_type = booking.get('rate_type', 'bar')
        if rate_type not in rate_breakdown:
            rate_breakdown[rate_type] = {
                'bookings': 0,
                'revenue': 0
            }
        rate_breakdown[rate_type]['bookings'] += 1
        rate_breakdown[rate_type]['revenue'] += booking.get('total_amount', 0)

    # Calculate ADR per rate type
    for rate_type, data in rate_breakdown.items():
        data['adr'] = round(data['revenue'] / data['bookings'], 2) if data['bookings'] > 0 else 0

    return {
        'start_date': start_date,
        'end_date': end_date,
        'overall_adr': round(adr, 2),
        'total_room_revenue': round(total_room_revenue, 2),
        'total_room_nights': total_room_nights,
        'total_bookings': len(bookings),
        'rate_breakdown': rate_breakdown
    }



@router.post("/reservations/rate-override-panel")
async def create_rate_override_with_panel(
    booking_id: str,
    new_rate: float,
    override_reason: str,
    authorized_by: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Rate override panel with authorization tracking
    - Manager approval required
    - Reason tracking
    - Audit trail
    """
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    original_rate = booking.get('total_amount', 0)

    # Create override log
    override_log = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'booking_id': booking_id,
        'user_id': current_user.id,
        'user_name': current_user.name,
        'original_rate': original_rate,
        'new_rate': new_rate,
        'override_reason': override_reason,
        'authorized_by': authorized_by or current_user.name,
        'timestamp': datetime.now(timezone.utc).isoformat()
    }

    await db.rate_override_logs.insert_one(override_log)

    # Update booking
    await db.bookings.update_one(
        {'id': booking_id},
        {'$set': {
            'total_amount': new_rate,
            'base_rate': original_rate,
            'override_reason': override_reason
        }}
    )

    # Create audit log
    await create_audit_log(
        tenant_id=current_user.tenant_id,
        user=current_user,
        action="RATE_OVERRIDE",
        entity_type="booking",
        entity_id=booking_id,
        changes={
            'original_rate': original_rate,
            'new_rate': new_rate,
            'reason': override_reason
        }
    )

    return {
        'success': True,
        'booking_id': booking_id,
        'original_rate': original_rate,
        'new_rate': new_rate,
        'override_id': override_log['id'],
        'message': 'Rate override applied successfully'
    }



class BookingSourceType(str, Enum):
    OTA = "ota"
    WEBSITE = "website"
    CORPORATE = "corporate"
    WALK_IN = "walk_in"
    PHONE = "phone"
    AGENT = "agent"


class ExtraCharge(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    booking_id: str
    tenant_id: str
    charge_name: str
    charge_amount: float
    charge_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None


class MultiRoomBooking(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    group_name: str
    primary_booking_id: str
    related_booking_ids: List[str] = []
    total_rooms: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


@router.get("/reservations/{booking_id}/ota-details")
async def get_ota_reservation_details(
    booking_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get detailed OTA reservation information including special requests, multi-room, source, extra charges"""
    current_user = await get_current_user(credentials)

    # Get booking
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Get extra charges
    extra_charges = []
    async for charge in db.extra_charges.find({
        'booking_id': booking_id,
        'tenant_id': current_user.tenant_id
    }):
        # Remove MongoDB _id field to avoid serialization issues
        if '_id' in charge:
            del charge['_id']
        extra_charges.append(charge)

    # Check if part of multi-room reservation
    multi_room_info = None
    multi_room = await db.multi_room_bookings.find_one({
        'tenant_id': current_user.tenant_id,
        '$or': [
            {'primary_booking_id': booking_id},
            {'related_booking_ids': booking_id}
        ]
    })

    if multi_room:
        # Get all related bookings
        related_bookings = []
        all_booking_ids = [multi_room['primary_booking_id']] + multi_room.get('related_booking_ids', [])
        async for related_booking in db.bookings.find({
            'id': {'$in': all_booking_ids},
            'tenant_id': current_user.tenant_id
        }):
            # Get room info
            room = await db.rooms.find_one({'id': related_booking['room_id'], 'tenant_id': current_user.tenant_id})
            related_bookings.append({
                'booking_id': related_booking['id'],
                'room_number': room.get('room_number') if room else 'N/A',
                'guest_name': await get_guest_name(related_booking['guest_id'], current_user.tenant_id)
            })

        multi_room_info = {
            'group_name': multi_room.get('group_name'),
            'total_rooms': multi_room.get('total_rooms'),
            'related_bookings': related_bookings
        }

    # Determine source of booking
    source_of_booking = BookingSourceType.WEBSITE.value  # Default
    if booking.get('ota_channel'):
        source_of_booking = BookingSourceType.OTA.value
    elif booking.get('company_id'):
        source_of_booking = BookingSourceType.CORPORATE.value
    elif booking.get('channel') == 'walk_in':
        source_of_booking = BookingSourceType.WALK_IN.value
    elif booking.get('channel') == 'phone':
        source_of_booking = BookingSourceType.PHONE.value

    return {
        'booking_id': booking_id,
        'special_requests': booking.get('special_requests', ''),
        'remarks': booking.get('notes', ''),
        'source_of_booking': source_of_booking,
        'ota_channel': booking.get('ota_channel'),
        'ota_confirmation': booking.get('ota_confirmation'),
        'extra_charges': extra_charges,
        'multi_room_info': multi_room_info,
        'commission_pct': booking.get('commission_pct'),
        'payment_model': booking.get('payment_model')
    }


class ExtraChargeCreate(BaseModel):
    charge_name: str
    charge_amount: float
    notes: Optional[str] = None


@router.post("/reservations/{booking_id}/extra-charges")
async def add_extra_charge(
    booking_id: str,
    data: ExtraChargeCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Add an extra charge to a reservation"""
    current_user = await get_current_user(credentials)

    # Verify booking exists
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Create extra charge
    extra_charge = ExtraCharge(
        booking_id=booking_id,
        tenant_id=current_user.tenant_id,
        charge_name=data.charge_name,
        charge_amount=data.charge_amount,
        notes=data.notes
    )

    await db.extra_charges.insert_one(extra_charge.model_dump())

    return {
        'success': True,
        'message': 'Extra charge added successfully',
        'extra_charge': extra_charge.model_dump()
    }


class MultiRoomReservationCreate(BaseModel):
    group_name: str
    primary_booking_id: str
    related_booking_ids: List[str]


@router.post("/reservations/multi-room")
async def create_multi_room_reservation(
    data: MultiRoomReservationCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Link multiple bookings as a multi-room reservation"""
    current_user = await get_current_user(credentials)

    # Create multi-room booking record
    multi_room = MultiRoomBooking(
        tenant_id=current_user.tenant_id,
        group_name=data.group_name,
        primary_booking_id=data.primary_booking_id,
        related_booking_ids=data.related_booking_ids,
        total_rooms=len(data.related_booking_ids) + 1
    )

    await db.multi_room_bookings.insert_one(multi_room.model_dump())

    return {
        'success': True,
        'message': 'Multi-room reservation created',
        'multi_room_id': multi_room.id
    }



@router.get("/reservations/search")
async def search_reservations(
    query: str = None,
    check_in: str = None,
    check_out: str = None,
    status: str = None,
    booking_id: str = None,
    phone: str = None,
    email: str = None,
    current_user: User = Depends(get_current_user)
):
    """
    Comprehensive reservation search with multiple filters
    Search by: guest name, booking ID, phone, email, date range, status
    """
    try:
        filter_dict = {'tenant_id': current_user.tenant_id}

        # Search conditions
        search_conditions = []

        if query:
            # Search in guest name or booking ID
            search_conditions.append({
                '$or': [
                    {'guest_name': {'$regex': query, '$options': 'i'}},
                    {'id': {'$regex': query, '$options': 'i'}},
                    {'booking_number': {'$regex': query, '$options': 'i'}}
                ]
            })

        if booking_id:
            search_conditions.append({'id': booking_id})

        if phone:
            # Find guest by phone first
            guest = await db.guests.find_one({'phone': {'$regex': phone, '$options': 'i'}})
            if guest:
                search_conditions.append({'guest_id': guest['id']})

        if email:
            # Find guest by email first
            guest = await db.guests.find_one({'email': {'$regex': email, '$options': 'i'}})
            if guest:
                search_conditions.append({'guest_id': guest['id']})

        if check_in:
            search_conditions.append({'check_in': {'$gte': check_in}})

        if check_out:
            search_conditions.append({'check_out': {'$lte': check_out}})

        if status:
            search_conditions.append({'status': status})

        # Combine all conditions
        if search_conditions:
            filter_dict['$and'] = search_conditions

        # Find bookings
        bookings = await db.bookings.find(filter_dict, {'_id': 0}).sort('check_in', -1).limit(50).to_list(50)

        # Enrich with guest and room data
        for booking in bookings:
            if booking.get('guest_id'):
                guest = await db.guests.find_one({'id': booking['guest_id']}, {'_id': 0})
                if guest:
                    booking['guest_phone'] = guest.get('phone')
                    booking['guest_email'] = guest.get('email')

            if booking.get('room_id'):
                room = await db.rooms.find_one({'id': booking['room_id']}, {'_id': 0})
                if room:
                    booking['room_number'] = room.get('room_number')
                    booking['room_type'] = room.get('room_type')

        return {
            'bookings': bookings,
            'count': len(bookings),
            'search_query': query,
            'filters_applied': {
                'check_in': check_in,
                'check_out': check_out,
                'status': status,
                'phone': phone,
                'email': email
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")



@router.post("/rooms/queue/add")
async def add_to_room_queue(
    queue_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Add guest to room queue (early arrival waiting list)"""
    current_user = await get_current_user(credentials)

    # Verify booking
    booking = await db.bookings.find_one({
        'id': queue_data['booking_id'],
        'tenant_id': current_user.tenant_id
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Get guest info
    guest = await db.guests.find_one({'id': booking['guest_id']})

    # Determine priority
    priority = 5
    if guest and guest.get('vip_status'):
        priority = 1
    elif guest and guest.get('loyalty_tier') in ['gold', 'platinum']:
        priority = 2
    elif queue_data.get('priority'):
        priority = queue_data['priority']

    queue_entry = QueueRoom(
        tenant_id=current_user.tenant_id,
        booking_id=queue_data['booking_id'],
        guest_name=guest.get('name', 'Unknown') if guest else 'Unknown',
        room_type=booking.get('room_type', 'Standard'),
        priority=priority,
        requested_room=queue_data.get('requested_room'),
        arrival_time=queue_data.get('arrival_time'),
        special_requests=queue_data.get('special_requests'),
        vip_status=guest.get('vip_status', False) if guest else False
    )

    await db.room_queue.insert_one(queue_entry.model_dump())

    return {
        'success': True,
        'queue_id': queue_entry.id,
        'priority': priority,
        'message': f"{queue_entry.guest_name} added to room queue with priority {priority}"
    }


@router.get("/rooms/queue/list")
async def get_room_queue(
    status: str = "waiting",
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get room queue list sorted by priority"""
    current_user = await get_current_user(credentials)

    queue = await db.room_queue.find({
        'tenant_id': current_user.tenant_id,
        'status': status
    }, {'_id': 0}).sort('priority', 1).to_list(1000)

    # Get available rooms for assignment
    available_rooms = await db.rooms.find({
        'tenant_id': current_user.tenant_id,
        'status': 'available',
        'housekeeping_status': 'clean'
    }, {'_id': 0}).to_list(1000)

    return {
        'queue': queue,
        'queue_length': len(queue),
        'available_rooms': len(available_rooms),
        'recommendations': [
            {
                'queue_entry': q,
                'suggested_room': next((r for r in available_rooms if r['room_type'] == q['room_type']), None)
            }
            for q in queue[:10]
        ]
    }


@router.post("/rooms/queue/assign-priority")
async def assign_queue_priority(
    queue_id: str,
    priority: int,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Manually assign priority to queue entry"""
    current_user = await get_current_user(credentials)

    if priority < 1 or priority > 10:
        raise HTTPException(status_code=400, detail="Priority must be between 1 and 10")

    result = await db.room_queue.update_one(
        {
            'id': queue_id,
            'tenant_id': current_user.tenant_id
        },
        {'$set': {'priority': priority}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Queue entry not found")

    return {
        'success': True,
        'queue_id': queue_id,
        'new_priority': priority
    }


@router.post("/rooms/queue/notify-guest")
async def notify_guest_room_ready(
    queue_id: str,
    room_number: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Notify guest that their room is ready"""
    current_user = await get_current_user(credentials)

    # Get queue entry
    queue_entry = await db.room_queue.find_one({
        'id': queue_id,
        'tenant_id': current_user.tenant_id
    })

    if not queue_entry:
        raise HTTPException(status_code=404, detail="Queue entry not found")

    # Get booking
    await db.bookings.find_one({'id': queue_entry['booking_id']})

    # Update queue status
    await db.room_queue.update_one(
        {'id': queue_id},
        {
            '$set': {
                'status': 'assigned',
                'notified': True,
                'assigned_room': room_number,
                'notified_at': datetime.now(timezone.utc).isoformat()
            }
        }
    )

    # Send notification (mock)
    notification_message = f"Dear {queue_entry['guest_name']}, your room {room_number} is now ready! Please proceed to reception."

    print(f"📱 Room Ready Notification: {notification_message}")

    return {
        'success': True,
        'message': 'Guest notified successfully',
        'guest_name': queue_entry['guest_name'],
        'room_number': room_number,
        'notification': notification_message
    }


@router.delete("/rooms/queue/{queue_id}")
async def remove_from_queue(
    queue_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Remove entry from room queue"""
    current_user = await get_current_user(credentials)

    result = await db.room_queue.delete_one({
        'id': queue_id,
        'tenant_id': current_user.tenant_id
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Queue entry not found")

    return {
        'success': True,
        'message': 'Entry removed from queue'
    }


