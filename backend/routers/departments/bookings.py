"""
bookings

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Department-Specific Endpoints Router
Front Office, Housekeeping Manager, Finance, Revenue, F&B, Maintenance,
Sales, HR, IT/Security department dashboards.
Extracted from server.py for modularity.
"""
import logging

from modules.pms_core.role_permission_service import require_module as require_module_v97  # v97 DW

logger = logging.getLogger(__name__)
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer

from core.atomic_booking import BookingConflictError, assign_room_atomic
from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import RolePermissionService
from shared_kernel.idempotency import begin_idempotency, get_idempotency_key

_role_perm = RolePermissionService()


def _enforce(role: str, op: str):
    """Bug CU (v60) — Departments/Reports/Rates/POS RBAC zorunlu."""
    _role_perm.enforce_permission(role, op)

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: F401
except ImportError:
    Workbook = None

try:
    from cache_manager import cache, cached
except ImportError:
    cache = None  # type: ignore
    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator

security = HTTPBearer()


# ==================== DEPARTMENT-SPECIFIC ENDPOINTS ====================

# rbac-allow: cache-rbac — FO dashboard operasyonel, hotel staff geneli görür (FO/HK/manager/admin)

# rbac-allow: cache-rbac — HK dashboard operasyonel, FO/HK/manager/admin görür








# NOTE: /ai/dashboard/briefing duplicate removed (R10b) — canonical implementation
# lives in `domains/ai/endpoints.py::get_daily_briefing` with @cached(ttl=300) and
# parallel `_asyncio.gather` over 4 collections.




# rbac-allow: cache-rbac — booking için müsait odalar operasyonel (FO/HK/manager)



# rbac-allow: cache-rbac — HK aktif temizlik timer'ları operasyonel (HK/FO/manager)











































# rbac-allow: cache-rbac — task kanban operasyonel cross-role (FO/HK/maintenance/manager)

router = APIRouter(prefix="/api", tags=["departments"])


# ── POST /bookings/{booking_id}/assign-room ──
@router.post("/bookings/{booking_id}/assign-room")
async def assign_room_to_booking(
    booking_id: str,
    room_assignment: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v97("frontdesk")),  # v97 DW
):
    """Assign a specific room to a booking"""
    room_id = room_assignment.get('room_id')
    room_number = room_assignment.get('room_number')
    notes = room_assignment.get('notes', '')

    # Get booking
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Get room
    room = await db.rooms.find_one({
        'id': room_id,
        'tenant_id': current_user.tenant_id
    })

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    # Atomic room-night claim (overbooking guard). Replaces the previous
    # non-atomic count-then-update pre-check (TOCTOU race + incomplete overlap
    # query that missed fully-nested bookings + never wrote room_night_locks).
    check_in = booking.get('check_in')
    check_out = booking.get('check_out')
    if not check_in or not check_out:
        raise HTTPException(
            status_code=400,
            detail="Booking has no check-in/check-out dates"
        )

    try:
        await assign_room_atomic(
            tenant_id=current_user.tenant_id,
            booking_id=booking_id,
            room_id=room_id,
            check_in=check_in,
            check_out=check_out,
        )
    except BookingConflictError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Room {room_number} is not available for this period"
        ) from exc

    # Update booking — v109 round-9 IDOR: scope by tenant.
    await db.bookings.update_one(
        {'id': booking_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'room_id': room_id,
                'room_number': room_number,
                'room_type': room.get('room_type'),
                'room_assigned_at': datetime.now(UTC).isoformat(),
                'room_assigned_by': current_user.email,
                'room_assignment_notes': notes
            }
        }
    )

    # Log activity
    await db.activity_log.insert_one({
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'type': 'room_assignment',
        'booking_id': booking_id,
        'room_id': room_id,
        'room_number': room_number,
        'performed_by': current_user.email,
        'notes': notes,
        'timestamp': datetime.now(UTC).isoformat()
    })

    return {
        'success': True,
        'message': f'Room {room_number} assigned successfully',
        'booking_id': booking_id,
        'room_number': room_number,
        'assigned_at': datetime.now(UTC).isoformat()
    }
# ── GET /bookings/{booking_id}/available-rooms ──
@router.get("/bookings/{booking_id}/available-rooms")
@cached(ttl=120, key_prefix="booking_available_rooms")  # Cache for 2 min
async def get_available_rooms_for_booking(
    booking_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get list of available rooms for a specific booking"""
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    check_in = datetime.fromisoformat(booking.get('check_in'))
    check_out = datetime.fromisoformat(booking.get('check_out'))
    requested_type = booking.get('room_type', 'standard')

    # Fetch all real rooms (skip "V-..." virtual no-show placeholder rooms).
    blocked_statuses = {'out_of_service', 'maintenance', 'blocked'}
    # Skip "V-..." virtual no-show placeholder rooms and any room whose
    # number starts with formula-injection characters (= @ + -) — these are
    # not real rooms and would not be valid move targets.
    all_rooms = await db.rooms.find({
        'tenant_id': current_user.tenant_id,
        'room_number': {'$not': {'$regex': r'^(V-|[=@+\-])', '$options': 'i'}},
        'status': {'$nin': list(blocked_statuses)},
    }).to_list(1000)

    # Single query to find every room_id that conflicts in this date range,
    # instead of one count_documents per room (N+1 → 2 queries).
    conflicting_cursor = db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'id': {'$ne': booking_id},
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
        '$or': [
            {'check_in': {'$lte': check_in.isoformat()},
             'check_out': {'$gt': check_in.isoformat()}},
            {'check_in': {'$lt': check_out.isoformat()},
             'check_out': {'$gte': check_out.isoformat()}},
        ],
    }, {'room_id': 1})
    conflicting_ids = {doc['room_id'] async for doc in conflicting_cursor if doc.get('room_id')}

    booking_rate = booking.get('rate') or 0
    requested_type_lower = (requested_type or '').lower()
    available_rooms = []
    for room in all_rooms:
        if room['id'] in conflicting_ids:
            continue
        room_price = room.get('price_per_night') or 0
        available_rooms.append({
            'id': room['id'],
            'room_number': room['room_number'],
            'room_type': room['room_type'],
            'floor': room.get('floor', 1),
            'status': room.get('status'),
            'price_per_night': room_price,
            'is_same_type': (room.get('room_type') or '').lower() == requested_type_lower,
            'is_upgrade': room_price > booking_rate,
            'amenities': room.get('amenities', []),
        })

    # Sort: same type first, then by floor
    available_rooms.sort(key=lambda x: (not x['is_same_type'], x['floor']))

    return {
        'available_rooms': available_rooms,
        'total_available': len(available_rooms),
        'requested_type': requested_type,
        'booking_dates': {
            'check_in': check_in.isoformat(),
            'check_out': check_out.isoformat()
        }
    }
# ── POST /bookings/walk-in-quick ──
@router.post("/bookings/walk-in-quick")
async def create_walk_in_booking(data: dict, http_request: Request, current_user: User = Depends(get_current_user)):
    """Quick walk-in booking creation"""
    _enforce(current_user.role, "walk_in")  # Bug CU

    # Idempotency-Key request-replay (additive: no-op without the header).
    guard, replay = await begin_idempotency(
        db, http_request, tenant_id=current_user.tenant_id,
        scope="departments.walk_in_quick", payload=data,
    )
    if replay is not None:
        return replay

    booking_id = str(uuid.uuid4())
    # Deterministic guest id under an Idempotency-Key so a crash-and-retry reuses
    # the same guest instead of orphaning a new one (mirrors pms quick-booking).
    idem_key = get_idempotency_key(http_request)
    if idem_key:
        guest_id = str(uuid.uuid5(uuid.NAMESPACE_OID, f"{current_user.tenant_id}:walkin-quick:{idem_key}"))
    else:
        guest_id = str(uuid.uuid4())

    # Create guest (find-or-insert so a deterministic retry doesn't duplicate it)
    from security.guest_write import encrypt_guest_insert
    existing_guest = await db.guests.find_one(
        {'id': guest_id, 'tenant_id': current_user.tenant_id}, {'_id': 0, 'id': 1}
    )
    if existing_guest is None:
        await db.guests.insert_one(encrypt_guest_insert({
            'id': guest_id,
            'tenant_id': current_user.tenant_id,
            'name': data['guest_name'],
            'phone': data['guest_phone'],
            'email': data.get('guest_email'),
            'created_at': datetime.now(UTC).isoformat()
        }))

    # Find available room
    available_room = await db.rooms.find_one({
        'tenant_id': current_user.tenant_id,
        'room_type': data['room_type'],
        'current_status': 'available'
    })

    if not available_room:
        # No durable booking yet (guest is deterministic/reused) -> release so
        # the same key can be retried once a room frees up.
        await guard.release()
        raise HTTPException(status_code=400, detail='No rooms available')

    # Create booking (atomic overbooking check)
    from core.atomic_booking import BookingConflictError, create_booking_atomic
    try:
        await create_booking_atomic({
            'id': booking_id,
            'tenant_id': current_user.tenant_id,
            'guest_id': guest_id,
            'room_id': available_room['id'],
            'check_in': data['check_in'],
            'check_out': data['check_out'],
            'adults': data['adults'],
            'status': 'confirmed',
            'source': 'walk-in',
            'created_at': datetime.now(UTC).isoformat()
        })
    except BookingConflictError as e:
        # Atomic insert failed -> no booking persisted -> safe to release.
        await guard.release()
        # Structured 409 detail so frontend conflict dialog can render
        # (mirrors create_reservation_service / multi-room handler).
        raise HTTPException(status_code=409, detail={
            "message": str(e),
            "conflicting_booking_id": getattr(e, "conflicting_booking_id", None),
            "conflict_type": getattr(e, "conflict_type", "booking"),
            "conflict_window": {
                "room_id": available_room['id'],
                "check_in": data['check_in'],
                "check_out": data['check_out'],
            },
        })

    result = {'booking_id': booking_id, 'room_number': available_room['room_number']}
    await guard.complete(result)
    return result
