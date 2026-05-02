"""
PMS Room Queue Router — Early arrival waiting list management.
Extracted from pms.py (Stage 3b).

Routes:
  POST   /rooms/queue/add
  GET    /rooms/queue/list
  POST   /rooms/queue/assign-priority
  POST   /rooms/queue/notify-guest
  DELETE /rooms/queue/{queue_id}
"""
import logging

from modules.pms_core.role_permission_service import require_module as require_module_v92  # v92 DW

logger = logging.getLogger(__name__)
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from cache_manager import cache, cached  # v95 — cache for invalidation on writes
from core.database import db
from core.security import get_current_user
from modules.pms_core.role_permission_service import require_op  # v89 DW

try:
    from domains.pms.night_audit_module import QueueRoom
except ImportError:
    QueueRoom = None

router = APIRouter(prefix="/api", tags=["pms-room-queue"])
security = HTTPBearer()


@router.post("/rooms/queue/add")
async def add_to_room_queue(
    queue_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_v92("frontdesk")),  # v92 DW
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

    # Get guest info (defense-in-depth: explicit tenant_id filter even though booking is already tenant-scoped)
    guest = await db.guests.find_one({'id': booking['guest_id'], 'tenant_id': current_user.tenant_id})

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
    cache.invalidate_tenant_cache(current_user.tenant_id, "rooms_queue_list")  # v95

    return {
        'success': True,
        'queue_id': queue_entry.id,
        'priority': priority,
        'message': f"{queue_entry.guest_name} added to room queue with priority {priority}"
    }


@router.get("/rooms/queue/list")
@cached(ttl=60, key_prefix="rooms_queue_list")  # v95 — 60s cache (front-desk, kısa TTL)
async def get_room_queue(
    status: str = "waiting",
    current_user=Depends(get_current_user),  # v95 — explicit dep so @cached extracts tenant_id (was 'global' namespace bug)
):
    """Get room queue list sorted by priority"""
    # v95 — Parallel queries + projection on rooms (only fields used downstream)
    import asyncio as _asyncio
    queue_q = db.room_queue.find({
        'tenant_id': current_user.tenant_id,
        'status': status
    }, {'_id': 0}).sort('priority', 1).to_list(1000)
    available_rooms_q = db.rooms.find({
        'tenant_id': current_user.tenant_id,
        'status': 'available',
        'housekeeping_status': 'clean'
    }, {'_id': 0, 'id': 1, 'room_number': 1, 'room_type': 1, 'floor': 1}).to_list(1000)
    queue, available_rooms = await _asyncio.gather(queue_q, available_rooms_q)

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
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_v92("frontdesk")),  # v92 DW
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

    cache.invalidate_tenant_cache(current_user.tenant_id, "rooms_queue_list")  # v95
    return {
        'success': True,
        'queue_id': queue_id,
        'new_priority': priority
    }


@router.post("/rooms/queue/notify-guest")
async def notify_guest_room_ready(
    queue_id: str,
    room_number: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_reports")),  # v89 DW
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

    # (no booking re-fetch needed — queue_entry already tenant-scoped above)

    # v95 — tenant_id filter eklendi (önceden filter yok → cross-tenant update riski)
    await db.room_queue.update_one(
        {'id': queue_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'status': 'assigned',
                'notified': True,
                'assigned_room': room_number,
                'notified_at': datetime.now(UTC).isoformat()
            }
        }
    )

    cache.invalidate_tenant_cache(current_user.tenant_id, "rooms_queue_list")  # v95

    # Send notification (mock)
    notification_message = f"Dear {queue_entry['guest_name']}, your room {room_number} is now ready! Please proceed to reception."

    logger.info(f"Room Ready Notification: {notification_message}")

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
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_reports")),  # v89 DW
):
    """Remove entry from room queue"""
    current_user = await get_current_user(credentials)

    result = await db.room_queue.delete_one({
        'id': queue_id,
        'tenant_id': current_user.tenant_id
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Queue entry not found")

    cache.invalidate_tenant_cache(current_user.tenant_id, "rooms_queue_list")  # v95
    return {
        'success': True,
        'message': 'Entry removed from queue'
    }
