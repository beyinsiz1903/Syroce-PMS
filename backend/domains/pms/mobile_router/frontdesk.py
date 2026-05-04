"""
frontdesk

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Domain Router: Mobile

Extracted from legacy_routes.py — Mobile dashboard, GM mobile, department mobile endpoints.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user, security
from modules.pms_core.role_permission_service import require_module as require_module_v92  # v92 DW

# ============================================================================
# MOBILE ENDPOINTS - Department-Based Mobile Dashboard APIs
# ============================================================================

# Mobile Endpoint Pydantic Models
class ProcessNoShowRequest(BaseModel):
    booking_id: str

class ChangeRoomRequest(BaseModel):
    booking_id: str
    new_room_id: str
    reason: str | None = None

class QuickTaskRequest(BaseModel):
    room_id: str
    task_type: str
    priority: str = 'normal'
    assigned_to: str | None = None
    notes: str | None = None

class QuickIssueRequest(BaseModel):
    room_id: str
    issue_type: str
    description: str
    priority: str = 'normal'

class QuickOrderItem(BaseModel):
    item_id: str
    quantity: int = 1

class QuickOrderRequest(BaseModel):
    outlet_id: str
    table_number: str | None = None
    items: list[QuickOrderItem] = []
    notes: str | None = None

class MenuPriceUpdateRequest(BaseModel):
    new_price: float
    reason: str | None = None

# --------------------------------------------------------------------------
# GM Mobile Dashboard Endpoints
# --------------------------------------------------------------------------







# --------------------------------------------------------------------------
# Front Desk Mobile Dashboard Endpoints
# --------------------------------------------------------------------------











# --------------------------------------------------------------------------
# Housekeeping Mobile Dashboard Endpoints
# --------------------------------------------------------------------------







# --------------------------------------------------------------------------
# Housekeeping Enhanced - Inspection, Lost & Found, Task Assignment, Timer
# --------------------------------------------------------------------------

























# --------------------------------------------------------------------------
# Maintenance Mobile Dashboard Endpoints
# --------------------------------------------------------------------------





# --------------------------------------------------------------------------
# Technical Service Enhancements - SLA, Spare Parts, Task Management
# --------------------------------------------------------------------------























# --------------------------------------------------------------------------
# F&B Mobile Dashboard Endpoints
# --------------------------------------------------------------------------







# --------------------------------------------------------------------------
# Finance Mobile Dashboard Endpoints (NEW)
# --------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["mobile"])


# ── GET /frontdesk/mobile/early-checkin-requests ──
@router.get("/frontdesk/mobile/early-checkin-requests")
async def get_early_checkin_requests_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get early check-in requests for front desk mobile"""
    current_user = await get_current_user(credentials)
    today = datetime.now(UTC)

    requests = []
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': today.replace(hour=0, minute=0, second=0),
            '$lte': today.replace(hour=23, minute=59, second=59)
        },
        'status': {'$in': ['confirmed', 'guaranteed']},
        'early_checkin_requested': True
    }).sort('check_in', 1):
        requests.append({
            'booking_id': booking.get('id'),
            'guest_name': booking.get('guest_name'),
            'room_number': booking.get('room_number'),
            'requested_time': booking.get('early_checkin_time', '12:00'),
            'check_in': booking.get('check_in'),
            'room_status': 'checking',  # Will be updated with actual room status
            'notes': booking.get('special_requests', '')
        })

    # Check actual room status for each request
    for req in requests:
        if req['room_number']:
            room = await db.rooms.find_one({
                'room_number': req['room_number'],
                'tenant_id': current_user.tenant_id
            })
            if room:
                req['room_status'] = room.get('status', 'unknown')

    return {
        'early_checkin_requests': requests,
        'count': len(requests)
    }
# ── GET /frontdesk/mobile/late-checkout-requests ──
@router.get("/frontdesk/mobile/late-checkout-requests")
async def get_late_checkout_requests_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get late checkout requests for front desk mobile"""
    current_user = await get_current_user(credentials)
    today = datetime.now(UTC)

    requests = []
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_out': {
            '$gte': today.replace(hour=0, minute=0, second=0),
            '$lte': today.replace(hour=23, minute=59, second=59)
        },
        'status': 'checked_in',
        'late_checkout_requested': True
    }).sort('check_out', 1):
        requests.append({
            'booking_id': booking.get('id'),
            'guest_name': booking.get('guest_name'),
            'room_number': booking.get('room_number'),
            'requested_time': booking.get('late_checkout_time', '14:00'),
            'check_out': booking.get('check_out'),
            'has_next_arrival': False,  # Will be updated
            'notes': booking.get('special_requests', '')
        })

    # Check if there's a next arrival for the same room
    for req in requests:
        next_booking = await db.bookings.find_one({
            'tenant_id': current_user.tenant_id,
            'room_number': req['room_number'],
            'check_in': {
                '$gte': today.replace(hour=0, minute=0, second=0),
                '$lte': today.replace(hour=23, minute=59, second=59)
            },
            'status': {'$in': ['confirmed', 'guaranteed']}
        })
        if next_booking:
            req['has_next_arrival'] = True
            req['next_arrival_time'] = next_booking.get('check_in')

    return {
        'late_checkout_requests': requests,
        'count': len(requests)
    }
# ── POST /frontdesk/mobile/process-no-show ──
@router.post("/frontdesk/mobile/process-no-show")
async def process_no_show_mobile(
    request: ProcessNoShowRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_v92("frontdesk")),  # v92 DW
):
    """Process no-show for a booking"""
    current_user = await get_current_user(credentials)
    booking_id = request.booking_id

    # Find booking
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Check if already processed
    if booking.get('status') == 'no_show':
        raise HTTPException(status_code=400, detail="Booking already marked as no-show")

    # Update booking status
    await db.bookings.update_one(
        {'id': booking_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'status': 'no_show',
                'no_show_date': datetime.now(UTC),
                'no_show_processed_by': current_user.username
            }
        }
    )

    # Apply no-show charge if policy exists
    no_show_fee = booking.get('cancellation_policy', {}).get('no_show_fee', 0)
    if no_show_fee > 0:
        # Create charge record
        charge_id = str(uuid.uuid4())
        await db.charges.insert_one({
            'id': charge_id,
            'tenant_id': current_user.tenant_id,
            'booking_id': booking_id,
            'guest_id': booking.get('guest_id'),
            'charge_type': 'no_show_fee',
            'amount': no_show_fee,
            'description': 'No-show cancellation fee',
            'created_at': datetime.now(UTC),
            'created_by': current_user.username
        })

    return {
        'message': 'No-show processed successfully',
        'booking_id': booking_id,
        'no_show_fee': no_show_fee,
        'status': 'no_show'
    }
# ── POST /frontdesk/mobile/change-room ──
@router.post("/frontdesk/mobile/change-room")
async def change_room_mobile(
    request: ChangeRoomRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_v92("frontdesk")),  # v92 DW
):
    """Change room for a booking"""
    current_user = await get_current_user(credentials)
    booking_id = request.booking_id
    new_room_id = request.new_room_id
    reason = request.reason

    # Find booking
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Find new room
    new_room = await db.rooms.find_one({
        'id': new_room_id,
        'tenant_id': current_user.tenant_id
    })

    if not new_room:
        raise HTTPException(status_code=404, detail="New room not found")

    # Check if new room is available
    if new_room.get('status') not in ['available', 'inspected']:
        raise HTTPException(
            status_code=400,
            detail=f"Room {new_room.get('room_number')} is not available (status: {new_room.get('status')})"
        )

    old_room_id = booking.get('room_id')
    old_room_number = booking.get('room_number')

    # Update booking with new room
    await db.bookings.update_one(
        {'id': booking_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'room_id': new_room_id,
                'room_number': new_room.get('room_number'),
                'room_type': new_room.get('room_type'),
                'room_changed_at': datetime.now(UTC),
                'room_changed_by': current_user.username,
                'room_change_reason': reason
            }
        }
    )

    # Update old room status (if checked in)
    if booking.get('status') == 'checked_in' and old_room_id:
        await db.rooms.update_one(
            {'id': old_room_id, 'tenant_id': current_user.tenant_id},
            {
                '$set': {
                    'status': 'dirty',
                    'current_booking_id': None
                }
            }
        )

    # Update new room status (if checked in)
    if booking.get('status') == 'checked_in':
        await db.rooms.update_one(
            {'id': new_room_id, 'tenant_id': current_user.tenant_id},
            {
                '$set': {
                    'status': 'occupied',
                    'current_booking_id': booking_id
                }
            }
        )

    # Log room change
    await db.audit_logs.insert_one({
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'user_id': current_user.user_id,
        'user_name': current_user.username,
        'action': 'ROOM_CHANGE',
        'entity_type': 'booking',
        'entity_id': booking_id,
        'changes': {
            'old_room_id': old_room_id,
            'old_room_number': old_room_number,
            'new_room_id': new_room_id,
            'new_room_number': new_room.get('room_number'),
            'reason': reason
        },
        'timestamp': datetime.now(UTC)
    })

    return {
        'message': 'Room changed successfully',
        'booking_id': booking_id,
        'old_room_number': old_room_number,
        'new_room_number': new_room.get('room_number'),
        'reason': reason
    }
