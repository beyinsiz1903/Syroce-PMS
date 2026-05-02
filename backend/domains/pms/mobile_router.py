"""
Domain Router: Mobile

Extracted from legacy_routes.py — Mobile dashboard, GM mobile, department mobile endpoints.
"""
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from cache_manager import cached
from core.database import db
from core.security import get_current_user, security
from models.schemas import User
from modules.pms_core.role_permission_service import (
    require_module,  # v89 DW
    require_op,
)
from modules.pms_core.role_permission_service import require_module as require_module_v92  # v92 DW

router = APIRouter(prefix="/api", tags=["mobile"])


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

@router.get("/dashboard/mobile/critical-issues")
async def get_critical_issues_mobile(
    limit: int = 5,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get recent critical issues for GM mobile dashboard"""
    current_user = await get_current_user(credentials)

    # Get critical maintenance tasks
    critical_tasks = []
    async for task in db.tasks.find({
        'tenant_id': current_user.tenant_id,
        'department': 'maintenance',
        'priority': 'urgent',
        'status': {'$ne': 'completed'}
    }).sort('created_at', -1).limit(limit):
        critical_tasks.append({
            'id': task.get('id'),
            'title': task.get('title'),
            'description': task.get('description'),
            'room_number': task.get('room_number'),
            'priority': task.get('priority'),
            'status': task.get('status'),
            'created_at': task.get('created_at'),
            'type': 'maintenance'
        })

    # Get overbooking situations
    today = datetime.now(UTC)
    overbookings = []
    candidate_bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$lte': today + timedelta(days=1)},
        'status': 'confirmed'
    }, {'_id': 0, 'id': 1, 'room_id': 1, 'room_number': 1, 'guest_name': 1, 'created_at': 1}).to_list(length=None)
    occupied_room_ids: set = set()
    cb_room_ids = [b.get('room_id') for b in candidate_bookings if b.get('room_id')]
    if cb_room_ids:
        async for r in db.rooms.find(
            {'id': {'$in': cb_room_ids}, 'tenant_id': current_user.tenant_id, 'status': 'occupied'},
            {'_id': 0, 'id': 1},
        ):
            occupied_room_ids.add(r['id'])
    for booking in candidate_bookings:
        if booking.get('room_id') in occupied_room_ids:
            overbookings.append({
                'id': booking.get('id'),
                'title': f"Overbooking - Room {booking.get('room_number')}",
                'description': f"Guest: {booking.get('guest_name')}",
                'room_number': booking.get('room_number'),
                'priority': 'urgent',
                'created_at': booking.get('created_at'),
                'type': 'overbooking'
            })

    # Combine and sort by date
    all_issues = critical_tasks + overbookings[:limit]
    all_issues.sort(key=lambda x: x['created_at'], reverse=True)

    return {
        'critical_issues': all_issues[:limit],
        'total_count': len(all_issues)
    }


@router.get("/dashboard/mobile/recent-complaints")
async def get_recent_complaints_mobile(
    limit: int = 5,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get recent guest complaints for GM mobile dashboard"""
    current_user = await get_current_user(credentials)

    # Get recent negative feedback/reviews
    complaints = []
    async for feedback in db.feedback.find({
        'tenant_id': current_user.tenant_id,
        '$or': [
            {'rating': {'$lte': 3}},
            {'sentiment': 'negative'}
        ]
    }).sort('created_at', -1).limit(limit):
        complaints.append({
            'id': feedback.get('id'),
            'guest_name': feedback.get('guest_name'),
            'rating': feedback.get('rating'),
            'comment': feedback.get('comment', ''),
            'category': feedback.get('category', 'general'),
            'sentiment': feedback.get('sentiment', 'negative'),
            'source': feedback.get('source', 'internal'),
            'created_at': feedback.get('created_at'),
            'status': feedback.get('status', 'new')
        })

    return {
        'complaints': complaints,
        'total_count': len(complaints)
    }


@router.get("/notifications/mobile/gm")
@cached(ttl=60, key_prefix="notif_mobile_gm")
async def get_gm_notifications_mobile(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v86 DV: GM mobile notif
):
    """Get notifications for GM mobile dashboard"""
    today = datetime.now(UTC)

    notifications = []

    # VIP Check-ins today
    vip_checkins = 0
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': today.replace(hour=0, minute=0, second=0),
            '$lte': today.replace(hour=23, minute=59, second=59)
        },
        'status': {'$in': ['confirmed', 'guaranteed']}
    }):
        guest = await db.guests.find_one({
            'id': booking.get('guest_id'),
            'tenant_id': current_user.tenant_id
        })
        if guest and guest.get('vip_status'):
            vip_checkins += 1
            notifications.append({
                'id': str(uuid.uuid4()),
                'type': 'vip_checkin',
                'title': 'VIP Check-in Today',
                'message': f"{booking.get('guest_name')} - Room {booking.get('room_number')}",
                'priority': 'high',
                'created_at': today.isoformat()
            })

    # Low inventory warning (occupancy > 90%)
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    occupied_rooms = await db.rooms.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': 'occupied'
    })

    if total_rooms > 0:
        occupancy_pct = (occupied_rooms / total_rooms) * 100
        if occupancy_pct > 90:
            notifications.append({
                'id': str(uuid.uuid4()),
                'type': 'low_inventory',
                'title': 'Low Inventory Warning',
                'message': f"Occupancy {occupancy_pct:.1f}% - Only {total_rooms - occupied_rooms} room(s) left",
                'priority': 'high',
                'created_at': today.isoformat()
            })

    # High-risk reviews (rating <= 2 in last 24 hours)
    risk_reviews = 0
    yesterday = today - timedelta(days=1)
    async for feedback in db.feedback.find({
        'tenant_id': current_user.tenant_id,
        'rating': {'$lte': 2},
        'created_at': {'$gte': yesterday}
    }):
        risk_reviews += 1

    if risk_reviews > 0:
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'high_risk_review',
            'title': 'High Risk Reviews',
            'message': f"{risk_reviews} low-rated review(s) received in the last 24 hours",
            'priority': 'medium',
            'created_at': today.isoformat()
        })

    return {
        'notifications': notifications,
        'unread_count': len(notifications)
    }


# --------------------------------------------------------------------------
# Front Desk Mobile Dashboard Endpoints
# --------------------------------------------------------------------------

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


@router.get("/notifications/mobile/frontdesk")
async def get_frontdesk_notifications_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get notifications for front desk mobile dashboard"""
    current_user = await get_current_user(credentials)
    today = datetime.now(UTC)

    notifications = []

    # VIP arrivals today
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': today.replace(hour=0, minute=0, second=0),
            '$lte': today.replace(hour=23, minute=59, second=59)
        },
        'status': {'$in': ['confirmed', 'guaranteed']}
    }):
        guest = await db.guests.find_one({
            'id': booking.get('guest_id'),
            'tenant_id': current_user.tenant_id
        })
        if guest and guest.get('vip_status'):
            notifications.append({
                'id': str(uuid.uuid4()),
                'type': 'vip_arrival',
                'title': 'VIP Arrival',
                'message': f"{booking.get('guest_name')} - Room {booking.get('room_number')}",
                'priority': 'high',
                'created_at': today.isoformat()
            })

    # Overbooking risk
    available_rooms = await db.rooms.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['available', 'inspected']}
    })

    arrivals_today = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': today.replace(hour=0, minute=0, second=0),
            '$lte': today.replace(hour=23, minute=59, second=59)
        },
        'status': {'$in': ['confirmed', 'guaranteed']}
    })

    if arrivals_today > available_rooms:
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'overbooking_risk',
            'title': 'Overbooking Risk',
            'message': f"{arrivals_today} arrivals, only {available_rooms} room(s) available",
            'priority': 'urgent',
            'created_at': today.isoformat()
        })

    # Room cleaning completed
    recently_cleaned = 0
    last_hour = today - timedelta(hours=1)
    async for task in db.housekeeping_tasks.find({
        'tenant_id': current_user.tenant_id,
        'task_type': 'cleaning',
        'status': 'completed',
        'completed_at': {'$gte': last_hour}
    }):
        recently_cleaned += 1

    if recently_cleaned > 0:
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'room_ready',
            'title': 'Rooms Ready',
            'message': f"{recently_cleaned} room(s) cleaned in the last hour",
            'priority': 'info',
            'created_at': today.isoformat()
        })

    return {
        'notifications': notifications,
        'unread_count': len(notifications)
    }


# --------------------------------------------------------------------------
# Housekeeping Mobile Dashboard Endpoints
# --------------------------------------------------------------------------

@router.get("/housekeeping/mobile/sla-delayed-rooms")
async def get_sla_delayed_rooms_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get rooms with SLA delays for housekeeping mobile"""
    current_user = await get_current_user(credentials)

    # SLA standard: cleaning should complete within 30 minutes
    sla_threshold = timedelta(minutes=30)
    delayed_rooms = []

    now_utc = datetime.now(UTC)
    async for task in db.housekeeping_tasks.find({
        'tenant_id': current_user.tenant_id,
        'task_type': 'cleaning',
        'status': 'in_progress'
    }):
        started_at = task.get('started_at')
        if started_at:
            if isinstance(started_at, str):
                try:
                    started_at = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                except (ValueError, TypeError):
                    continue
            if started_at.tzinfo is None:
                started_at = started_at.replace(tzinfo=UTC)
            duration = now_utc - started_at
            if duration > sla_threshold:
                room = await db.rooms.find_one({
                    'id': task.get('room_id'),
                    'tenant_id': current_user.tenant_id
                })

                delayed_rooms.append({
                    'task_id': task.get('id'),
                    'room_id': task.get('room_id'),
                    'room_number': room.get('room_number') if room else 'N/A',
                    'assigned_to': task.get('assigned_to'),
                    'started_at': started_at.isoformat(),
                    'duration_minutes': int(duration.total_seconds() / 60),
                    'sla_breach_minutes': int((duration - sla_threshold).total_seconds() / 60),
                    'priority': task.get('priority', 'normal')
                })

    # Sort by breach time (most delayed first)
    delayed_rooms.sort(key=lambda x: x['sla_breach_minutes'], reverse=True)

    return {
        'sla_delayed_rooms': delayed_rooms,
        'count': len(delayed_rooms),
        'sla_threshold_minutes': 30
    }


@router.get("/housekeeping/mobile/team-assignments")
async def get_team_assignments_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get team assignment overview for housekeeping mobile"""
    current_user = await get_current_user(credentials)

    # Get all active housekeeping staff
    staff_assignments = {}

    async for task in db.housekeeping_tasks.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['assigned', 'in_progress']},
        'assigned_to': {'$exists': True, '$ne': None}
    }):
        staff_name = task.get('assigned_to')

        if staff_name not in staff_assignments:
            staff_assignments[staff_name] = {
                'staff_name': staff_name,
                'assigned_rooms': [],
                'total_tasks': 0,
                'completed_today': 0,
                'in_progress': 0
            }

        room = await db.rooms.find_one({
            'id': task.get('room_id'),
            'tenant_id': current_user.tenant_id
        })

        staff_assignments[staff_name]['assigned_rooms'].append({
            'room_number': room.get('room_number') if room else 'N/A',
            'task_type': task.get('task_type'),
            'status': task.get('status'),
            'priority': task.get('priority')
        })

        staff_assignments[staff_name]['total_tasks'] += 1

        if task.get('status') == 'in_progress':
            staff_assignments[staff_name]['in_progress'] += 1

    # Get completed tasks today for each staff
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0)

    for staff_name in staff_assignments:
        completed_count = await db.housekeeping_tasks.count_documents({
            'tenant_id': current_user.tenant_id,
            'assigned_to': staff_name,
            'status': 'completed',
            'completed_at': {'$gte': today}
        })
        staff_assignments[staff_name]['completed_today'] = completed_count

    return {
        'team_assignments': list(staff_assignments.values()),
        'total_staff': len(staff_assignments)
    }


@router.post("/housekeeping/mobile/quick-task")
async def create_quick_task_mobile(
    request: QuickTaskRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("housekeeping")),  # v89 DW
):
    """Create a quick housekeeping task from mobile"""
    current_user = await get_current_user(credentials)
    room_id = request.room_id
    task_type = request.task_type
    priority = request.priority
    assigned_to = request.assigned_to
    notes = request.notes

    # Validate room
    room = await db.rooms.find_one({
        'id': room_id,
        'tenant_id': current_user.tenant_id
    })

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    # Create task
    task_id = str(uuid.uuid4())
    task = {
        'id': task_id,
        'tenant_id': current_user.tenant_id,
        'room_id': room_id,
        'room_number': room.get('room_number'),
        'task_type': task_type,
        'priority': priority,
        'status': 'assigned' if assigned_to else 'new',
        'assigned_to': assigned_to,
        'notes': notes,
        'created_at': datetime.now(UTC),
        'created_by': current_user.username
    }

    await db.housekeeping_tasks.insert_one(task)

    # Update room status if needed
    if task_type == 'cleaning':
        await db.rooms.update_one(
            {'id': room_id, 'tenant_id': current_user.tenant_id},
            {'$set': {'status': 'cleaning'}}
        )

    return {
        'message': 'Task created successfully',
        'task_id': task_id,
        'room_number': room.get('room_number'),
        'task_type': task_type,
        'priority': priority,
        'assigned_to': assigned_to
    }


# --------------------------------------------------------------------------
# Housekeeping Enhanced - Inspection, Lost & Found, Task Assignment, Timer
# --------------------------------------------------------------------------

@router.get("/housekeeping/mobile/inspection-checklist")
async def get_inspection_checklist_template(
    room_type: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get inspection checklist template"""
    await get_current_user(credentials)

    # Default checklist template
    checklist = [
        # Bathroom
        {'area': 'bathroom', 'item': 'Towels (bath, hand, face)', 'status': 'pending'},
        {'area': 'bathroom', 'item': 'Toilet paper', 'status': 'pending'},
        {'area': 'bathroom', 'item': 'Soap/Shampoo', 'status': 'pending'},
        {'area': 'bathroom', 'item': 'Hair dryer', 'status': 'pending'},
        {'area': 'bathroom', 'item': 'Cleanliness (sink, shower, toilet)', 'status': 'pending'},

        # Bedroom
        {'area': 'bedroom', 'item': 'Bed linens fresh', 'status': 'pending'},
        {'area': 'bedroom', 'item': 'Pillows (quantity)', 'status': 'pending'},
        {'area': 'bedroom', 'item': 'Duvet/blanket', 'status': 'pending'},
        {'area': 'bedroom', 'item': 'Curtains functional', 'status': 'pending'},
        {'area': 'bedroom', 'item': 'Carpet/floor clean', 'status': 'pending'},

        # Minibar
        {'area': 'minibar', 'item': 'Minibar stocked', 'status': 'pending'},
        {'area': 'minibar', 'item': 'Minibar clean', 'status': 'pending'},
        {'area': 'minibar', 'item': 'Glasses/cups clean', 'status': 'pending'},

        # Amenities
        {'area': 'amenities', 'item': 'TV remote working', 'status': 'pending'},
        {'area': 'amenities', 'item': 'AC working', 'status': 'pending'},
        {'area': 'amenities', 'item': 'Safe working', 'status': 'pending'},
        {'area': 'amenities', 'item': 'Phone working', 'status': 'pending'},
        {'area': 'amenities', 'item': 'Light bulbs OK', 'status': 'pending'},

        # General
        {'area': 'general', 'item': 'No damage visible', 'status': 'pending'},
        {'area': 'general', 'item': 'No stains', 'status': 'pending'},
        {'area': 'general', 'item': 'No odors', 'status': 'pending'},
    ]

    return {
        'checklist': checklist,
        'template_name': 'Standard Room Inspection',
        'total_items': len(checklist)
    }


@router.post("/housekeeping/mobile/inspection")
async def create_room_inspection(
    room_id: str,
    room_number: str,
    inspection_type: str,
    checklist: list[dict[str, Any]],
    photos: list[str] | None = None,
    notes: str | None = None,
    maintenance_required: bool = False,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("housekeeping")),  # v89 DW
):
    """Create room inspection record"""
    current_user = await get_current_user(credentials)

    inspection_id = str(uuid.uuid4())

    # Check for issues
    issues_found = []
    for item in checklist:
        if item.get('status') in ['missing', 'damaged', 'dirty']:
            issues_found.append(f"{item.get('area')}: {item.get('item')} - {item.get('status')}")

    # Create maintenance task if needed
    maintenance_task_id = None
    if maintenance_required and issues_found:
        task_id = str(uuid.uuid4())
        await db.tasks.insert_one({
            'id': task_id,
            'tenant_id': current_user.tenant_id,
            'title': f'Maintenance Required - Room {room_number}',
            'description': '\n'.join(issues_found),
            'priority': 'high',
            'status': 'new',
            'room_id': room_id,
            'room_number': room_number,
            'department': 'maintenance',
            'created_by': current_user.username,
            'created_at': datetime.now(UTC)
        })
        maintenance_task_id = task_id

    # Create inspection record
    inspection = {
        'id': inspection_id,
        'tenant_id': current_user.tenant_id,
        'room_id': room_id,
        'room_number': room_number,
        'inspection_type': inspection_type,
        'inspector': current_user.username,
        'inspection_status': 'completed' if not maintenance_required else 'failed',
        'checklist': checklist,
        'photos': photos or [],
        'notes': notes,
        'issues_found': issues_found,
        'maintenance_required': maintenance_required,
        'maintenance_task_id': maintenance_task_id,
        'completed_at': datetime.now(UTC),
        'created_at': datetime.now(UTC),
        'updated_at': datetime.now(UTC)
    }

    await db.room_inspections.insert_one(inspection)

    return {
        'message': 'Inspection completed',
        'inspection_id': inspection_id,
        'issues_count': len(issues_found),
        'maintenance_required': maintenance_required,
        'maintenance_task_id': maintenance_task_id,
        'status': 'passed' if not issues_found else 'failed'
    }


@router.post("/housekeeping/mobile/lost-found")
async def create_lost_found_item(
    item_description: str,
    category: str,
    room_number: str,
    found_location: str,
    photos: list[str] | None = None,
    storage_location: str = "Lost & Found Office",
    storage_number: str | None = None,
    notes: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("housekeeping")),  # v89 DW
):
    """Register lost & found item"""
    current_user = await get_current_user(credentials)

    # Generate item number
    count = await db.lost_found_items.count_documents({'tenant_id': current_user.tenant_id})
    item_number = f"LF-{count + 1:05d}"

    item_id = str(uuid.uuid4())
    item = {
        'id': item_id,
        'tenant_id': current_user.tenant_id,
        'item_number': item_number,
        'item_description': item_description,
        'category': category,
        'room_number': room_number,
        'found_location': found_location,
        'found_date': datetime.now(UTC),
        'found_by': current_user.username,
        'photos': photos or [],
        'storage_location': storage_location,
        'storage_number': storage_number or item_number,
        'status': 'in_storage',
        'notes': notes,
        'created_at': datetime.now(UTC),
        'updated_at': datetime.now(UTC)
    }

    await db.lost_found_items.insert_one(item)

    return {
        'message': 'Lost & Found item registered',
        'item_id': item_id,
        'item_number': item_number,
        'storage_number': storage_number or item_number
    }


@router.get("/housekeeping/mobile/lost-found/items")
async def get_lost_found_items(
    status: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get lost & found items"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status

    items = []
    async for item in db.lost_found_items.find(query).sort('found_date', -1).limit(100):
        items.append({
            'id': item.get('id'),
            'item_number': item.get('item_number'),
            'item_description': item.get('item_description'),
            'category': item.get('category'),
            'room_number': item.get('room_number'),
            'found_location': item.get('found_location'),
            'found_date': item.get('found_date').isoformat() if item.get('found_date') else None,
            'found_by': item.get('found_by'),
            'storage_location': item.get('storage_location'),
            'storage_number': item.get('storage_number'),
            'status': item.get('status'),
            'photos_count': len(item.get('photos', [])),
            'claimed_by': item.get('claimed_by'),
            'claimed_date': item.get('claimed_date').isoformat() if item.get('claimed_date') else None
        })

    # Summary
    summary = {
        'total': len(items),
        'in_storage': len([i for i in items if i['status'] == 'in_storage']),
        'claimed': len([i for i in items if i['status'] == 'claimed']),
        'delivered': len([i for i in items if i['status'] == 'delivered'])
    }

    return {
        'items': items,
        'summary': summary
    }


@router.put("/housekeeping/mobile/lost-found/{item_id}/claim")
async def claim_lost_found_item(
    item_id: str,
    claimed_by: str,
    guest_id: str | None = None,
    notes: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("housekeeping")),  # v89 DW
):
    """Mark item as claimed"""
    current_user = await get_current_user(credentials)

    item = await db.lost_found_items.find_one({
        'id': item_id,
        'tenant_id': current_user.tenant_id
    })

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    await db.lost_found_items.update_one(
        {'id': item_id, 'tenant_id': current_user.tenant_id},
        {'$set': {
            'status': 'claimed',
            'claimed_by': claimed_by,
            'guest_id': guest_id,
            'claimed_date': datetime.now(UTC),
            'delivery_notes': notes,
            'updated_at': datetime.now(UTC)
        }}
    )

    return {
        'message': 'Item marked as claimed',
        'item_id': item_id,
        'item_number': item.get('item_number'),
        'claimed_by': claimed_by
    }


@router.post("/housekeeping/mobile/assign-tasks")
async def assign_hk_tasks(
    staff_id: str,
    staff_name: str,
    room_ids: list[str],
    notes: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("housekeeping")),  # v89 DW
):
    """Assign rooms to housekeeping staff"""
    current_user = await get_current_user(credentials)

    assignment_id = str(uuid.uuid4())
    assignment = {
        'id': assignment_id,
        'tenant_id': current_user.tenant_id,
        'assignment_date': datetime.now(UTC),
        'staff_id': staff_id,
        'staff_name': staff_name,
        'assigned_rooms': room_ids,
        'room_count': len(room_ids),
        'status': 'assigned',
        'assigned_by': current_user.username,
        'notes': notes,
        'created_at': datetime.now(UTC),
        'updated_at': datetime.now(UTC)
    }

    await db.hk_task_assignments.insert_one(assignment)

    # Update rooms status
    await db.rooms.update_many(
        {
            'id': {'$in': room_ids},
            'tenant_id': current_user.tenant_id
        },
        {'$set': {
            'assigned_to': staff_name,
            'assigned_at': datetime.now(UTC)
        }}
    )

    return {
        'message': 'Tasks assigned successfully',
        'assignment_id': assignment_id,
        'staff_name': staff_name,
        'room_count': len(room_ids)
    }


@router.get("/housekeeping/mobile/staff-assignments")
async def get_staff_assignments(
    assignment_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get staff task assignments"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}

    if assignment_date:
        date_obj = datetime.fromisoformat(assignment_date).date()
        start_of_day = datetime.combine(date_obj, datetime.min.time()).replace(tzinfo=UTC)
        end_of_day = datetime.combine(date_obj, datetime.max.time()).replace(tzinfo=UTC)
        query['assignment_date'] = {'$gte': start_of_day, '$lte': end_of_day}
    else:
        # Today
        today = datetime.now(UTC).date()
        start_of_day = datetime.combine(today, datetime.min.time()).replace(tzinfo=UTC)
        end_of_day = datetime.combine(today, datetime.max.time()).replace(tzinfo=UTC)
        query['assignment_date'] = {'$gte': start_of_day, '$lte': end_of_day}

    assignments = []
    async for assignment in db.hk_task_assignments.find(query).sort('assignment_date', -1):
        # Get room details
        rooms = []
        async for room in db.rooms.find({
            'id': {'$in': assignment.get('assigned_rooms', [])},
            'tenant_id': current_user.tenant_id
        }):
            rooms.append({
                'room_id': room.get('id'),
                'room_number': room.get('room_number'),
                'status': room.get('status')
            })

        assignments.append({
            'assignment_id': assignment.get('id'),
            'staff_id': assignment.get('staff_id'),
            'staff_name': assignment.get('staff_name'),
            'room_count': assignment.get('room_count'),
            'rooms': rooms,
            'status': assignment.get('status'),
            'assigned_by': assignment.get('assigned_by'),
            'assignment_date': assignment.get('assignment_date').isoformat() if assignment.get('assignment_date') else None
        })

    return {
        'assignments': assignments,
        'total_staff': len(assignments),
        'total_rooms': sum(a['room_count'] for a in assignments)
    }


@router.post("/housekeeping/mobile/cleaning/start")
async def start_cleaning_timer(
    room_id: str,
    room_number: str,
    task_type: str = "checkout",
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("housekeeping")),  # v89 DW
):
    """Start cleaning timer"""
    current_user = await get_current_user(credentials)

    # Check if already started
    existing = await db.cleaning_timers.find_one({
        'tenant_id': current_user.tenant_id,
        'room_id': room_id,
        'status': 'in_progress'
    })

    if existing:
        return {
            'message': 'Timer already running',
            'timer_id': existing.get('id'),
            'started_at': existing.get('started_at').isoformat()
        }

    timer_id = str(uuid.uuid4())
    timer = {
        'id': timer_id,
        'tenant_id': current_user.tenant_id,
        'room_id': room_id,
        'room_number': room_number,
        'staff_id': current_user.id,
        'staff_name': current_user.username,
        'task_type': task_type,
        'started_at': datetime.now(UTC),
        'status': 'in_progress'
    }

    await db.cleaning_timers.insert_one(timer)

    # Update room status
    await db.rooms.update_one(
        {'id': room_id, 'tenant_id': current_user.tenant_id},
        {'$set': {'status': 'cleaning'}}
    )

    return {
        'message': 'Cleaning started',
        'timer_id': timer_id,
        'room_number': room_number,
        'started_at': timer['started_at'].isoformat()
    }


@router.post("/housekeeping/mobile/cleaning/stop")
async def stop_cleaning_timer(
    room_id: str,
    notes: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("housekeeping")),  # v89 DW
):
    """Stop cleaning timer"""
    current_user = await get_current_user(credentials)

    timer = await db.cleaning_timers.find_one({
        'tenant_id': current_user.tenant_id,
        'room_id': room_id,
        'status': 'in_progress'
    })

    if not timer:
        raise HTTPException(status_code=404, detail="No active timer found")

    completed_at = datetime.now(UTC)
    duration = (completed_at - timer['started_at']).total_seconds() / 60

    await db.cleaning_timers.update_one(
        {'id': timer['id'], 'tenant_id': current_user.tenant_id},
        {'$set': {
            'completed_at': completed_at,
            'duration_minutes': int(duration),
            'status': 'completed',
            'notes': notes
        }}
    )

    # Update room status
    await db.rooms.update_one(
        {'id': room_id, 'tenant_id': current_user.tenant_id},
        {'$set': {'status': 'clean'}}
    )

    return {
        'message': 'Cleaning completed',
        'room_number': timer.get('room_number'),
        'duration_minutes': int(duration),
        'started_at': timer['started_at'].isoformat(),
        'completed_at': completed_at.isoformat()
    }


@router.post("/housekeeping/mobile/report-maintenance")
async def report_maintenance_from_hk(
    room_id: str,
    room_number: str,
    issue_type: str,
    description: str,
    priority: str = "normal",
    photos: list[str] | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("housekeeping")),  # v89 DW
):
    """Report maintenance issue from housekeeping"""
    current_user = await get_current_user(credentials)

    task_id = str(uuid.uuid4())
    task = {
        'id': task_id,
        'tenant_id': current_user.tenant_id,
        'task_number': f'MAINT-HK-{task_id[:8]}',
        'title': f'{issue_type} - Room {room_number}',
        'description': description,
        'priority': priority,
        'status': 'new',
        'room_id': room_id,
        'room_number': room_number,
        'department': 'maintenance',
        'reported_by': current_user.username,
        'source': 'housekeeping',
        'photos': photos or [],
        'created_at': datetime.now(UTC)
    }

    await db.tasks.insert_one(task)

    return {
        'message': 'Maintenance task created',
        'task_id': task_id,
        'task_number': task['task_number'],
        'priority': priority
    }


@router.get("/housekeeping/mobile/reports/daily")
async def get_hk_daily_report(
    report_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get housekeeping daily report"""
    current_user = await get_current_user(credentials)

    if report_date:
        target_date = datetime.fromisoformat(report_date).date()
    else:
        target_date = datetime.now(UTC).date()

    start_of_day = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=UTC)
    end_of_day = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=UTC)

    # Room statistics
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    clean_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id, 'status': 'clean'})
    dirty_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id, 'status': 'dirty'})
    occupied_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id, 'status': 'occupied'})

    # Cleaning timers today
    timers = []
    total_duration = 0
    async for timer in db.cleaning_timers.find({
        'tenant_id': current_user.tenant_id,
        'started_at': {'$gte': start_of_day, '$lte': end_of_day},
        'status': 'completed'
    }):
        duration = timer.get('duration_minutes', 0)
        total_duration += duration
        timers.append({
            'room_number': timer.get('room_number'),
            'staff_name': timer.get('staff_name'),
            'task_type': timer.get('task_type'),
            'duration_minutes': duration
        })

    avg_cleaning_time = total_duration / len(timers) if timers else 0

    # Lost & Found today
    lf_count = await db.lost_found_items.count_documents({
        'tenant_id': current_user.tenant_id,
        'found_date': {'$gte': start_of_day, '$lte': end_of_day}
    })

    # Inspections today
    inspection_count = await db.room_inspections.count_documents({
        'tenant_id': current_user.tenant_id,
        'created_at': {'$gte': start_of_day, '$lte': end_of_day}
    })

    # Maintenance reports from HK
    maintenance_count = await db.tasks.count_documents({
        'tenant_id': current_user.tenant_id,
        'source': 'housekeeping',
        'created_at': {'$gte': start_of_day, '$lte': end_of_day}
    })

    return {
        'report_date': target_date.isoformat(),
        'room_statistics': {
            'total_rooms': total_rooms,
            'clean_rooms': clean_rooms,
            'dirty_rooms': dirty_rooms,
            'occupied_rooms': occupied_rooms,
            'cleaning_percentage': (clean_rooms / total_rooms * 100) if total_rooms > 0 else 0
        },
        'cleaning_performance': {
            'rooms_cleaned_today': len(timers),
            'total_cleaning_time_minutes': total_duration,
            'average_cleaning_time_minutes': round(avg_cleaning_time, 1),
            'details': timers
        },
        'lost_and_found': {
            'items_found_today': lf_count
        },
        'quality_control': {
            'inspections_completed': inspection_count
        },
        'maintenance_reports': {
            'issues_reported_today': maintenance_count
        }
    }


@router.get("/notifications/mobile/housekeeping")
async def get_housekeeping_notifications_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get notifications for housekeeping mobile dashboard"""
    current_user = await get_current_user(credentials)

    notifications = []

    # Damage reports
    async for report in db.damage_reports.find({
        'tenant_id': current_user.tenant_id,
        'status': 'new',
        'created_at': {'$gte': datetime.now(UTC) - timedelta(days=1)}
    }):
        room = await db.rooms.find_one({
            'id': report.get('room_id'),
            'tenant_id': current_user.tenant_id
        })
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'damage_report',
            'title': 'Damage Report',
            'message': f"Room {room.get('room_number') if room else 'N/A'}: {report.get('description', 'Damage reported')}",
            'priority': 'high',
            'created_at': report.get('created_at').isoformat()
        })

    # Rush room requests (early check-in)
    today = datetime.now(UTC)
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': today.replace(hour=0, minute=0, second=0),
            '$lte': today.replace(hour=23, minute=59, second=59)
        },
        'early_checkin_requested': True,
        'status': {'$in': ['confirmed', 'guaranteed']}
    }):
        room = await db.rooms.find_one({
            'room_number': booking.get('room_number'),
            'tenant_id': current_user.tenant_id,
            'status': {'$nin': ['available', 'inspected']}
        })
        if room:
            notifications.append({
                'id': str(uuid.uuid4()),
                'type': 'rush_room',
                'title': 'Rush Cleaning',
                'message': f"Room {booking.get('room_number')} - Early check-in {booking.get('early_checkin_time', 'request')}",
                'priority': 'urgent',
                'created_at': datetime.now(UTC).isoformat()
            })

    # Guest "clean now" requests
    async for request in db.room_service_requests.find({
        'tenant_id': current_user.tenant_id,
        'request_type': 'cleaning',
        'status': 'pending',
        'created_at': {'$gte': datetime.now(UTC) - timedelta(hours=2)}
    }):
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'clean_now_request',
            'title': 'Guest Cleaning Request',
            'message': f"Room {request.get('room_number')} - Immediate cleaning requested",
            'priority': 'medium',
            'created_at': request.get('created_at').isoformat()
        })

    return {
        'notifications': notifications,
        'unread_count': len(notifications)
    }


# --------------------------------------------------------------------------
# Maintenance Mobile Dashboard Endpoints
# --------------------------------------------------------------------------

@router.get("/maintenance/mobile/preventive-maintenance-schedule")
async def get_pm_schedule_mobile(
    days: int = 7,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get preventive maintenance schedule for mobile"""
    current_user = await get_current_user(credentials)
    today = datetime.now(UTC)
    end_date = today + timedelta(days=days)

    # Get scheduled PM tasks
    pm_schedule = []

    # Check equipment maintenance schedules
    async for equipment in db.equipment.find({
        'tenant_id': current_user.tenant_id,
        'next_maintenance_date': {
            '$gte': today,
            '$lte': end_date
        }
    }):
        pm_schedule.append({
            'id': equipment.get('id'),
            'equipment_name': equipment.get('name'),
            'equipment_type': equipment.get('type'),
            'location': equipment.get('location'),
            'next_maintenance_date': equipment.get('next_maintenance_date').isoformat(),
            'maintenance_type': equipment.get('maintenance_type', 'preventive'),
            'frequency': equipment.get('maintenance_frequency', 'monthly'),
            'last_maintenance_date': equipment.get('last_maintenance_date').isoformat() if equipment.get('last_maintenance_date') else None,
            'assigned_technician': equipment.get('assigned_technician'),
            'status': 'scheduled'
        })

    # Sort by date
    pm_schedule.sort(key=lambda x: x['next_maintenance_date'])

    return {
        'pm_schedule': pm_schedule,
        'count': len(pm_schedule),
        'date_range': {
            'from': today.isoformat(),
            'to': end_date.isoformat()
        }
    }


@router.post("/maintenance/mobile/quick-issue")
async def create_quick_issue_mobile(
    request: QuickIssueRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("maintenance")),  # v89 DW
):
    """Create a quick maintenance issue from mobile"""
    current_user = await get_current_user(credentials)
    room_id = request.room_id
    issue_type = request.issue_type
    description = request.description
    priority = request.priority

    # Validate room
    room = await db.rooms.find_one({
        'id': room_id,
        'tenant_id': current_user.tenant_id
    })

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    # Create maintenance task
    task_id = str(uuid.uuid4())
    task = {
        'id': task_id,
        'tenant_id': current_user.tenant_id,
        'room_id': room_id,
        'room_number': room.get('room_number'),
        'department': 'maintenance',
        'title': f"{issue_type} - Room {room.get('room_number')}",
        'description': description,
        'issue_type': issue_type,
        'priority': priority,
        'status': 'new',
        'created_at': datetime.now(UTC),
        'created_by': current_user.username,
        'reported_by': current_user.username
    }

    await db.tasks.insert_one(task)

    # If priority is urgent or high, update room status
    if priority in ['urgent', 'high']:
        await db.rooms.update_one(
            {'id': room_id, 'tenant_id': current_user.tenant_id},
            {'$set': {'status': 'maintenance'}}
        )

    return {
        'message': 'Maintenance issue created successfully',
        'task_id': task_id,
        'room_number': room.get('room_number'),
        'issue_type': issue_type,
        'priority': priority
    }


# --------------------------------------------------------------------------
# Technical Service Enhancements - SLA, Spare Parts, Task Management
# --------------------------------------------------------------------------

@router.get("/maintenance/mobile/sla-configurations")
async def get_sla_configurations(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get SLA configurations for different priorities"""
    current_user = await get_current_user(credentials)

    configurations = []
    async for config in db.sla_configurations.find({
        'tenant_id': current_user.tenant_id,
        'is_active': True
    }).sort('priority', 1):
        configurations.append({
            'id': config.get('id'),
            'priority': config.get('priority'),
            'response_time_minutes': config.get('response_time_minutes'),
            'resolution_time_minutes': config.get('resolution_time_minutes'),
            'is_active': config.get('is_active', True)
        })

    # If no configurations exist, return defaults
    if not configurations:
        default_slas = [
            {'priority': 'emergency', 'response_time_minutes': 15, 'resolution_time_minutes': 120},
            {'priority': 'urgent', 'response_time_minutes': 30, 'resolution_time_minutes': 240},
            {'priority': 'high', 'response_time_minutes': 60, 'resolution_time_minutes': 480},
            {'priority': 'normal', 'response_time_minutes': 120, 'resolution_time_minutes': 1440},
            {'priority': 'low', 'response_time_minutes': 240, 'resolution_time_minutes': 2880}
        ]
        configurations = default_slas

    return {
        'sla_configurations': configurations,
        'count': len(configurations)
    }


@router.post("/maintenance/mobile/sla-configurations")
async def update_sla_configuration(
    priority: str,
    response_time_minutes: int,
    resolution_time_minutes: int,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("maintenance")),  # v89 DW
):
    """Update or create SLA configuration"""
    current_user = await get_current_user(credentials)

    # Check if configuration exists
    existing = await db.sla_configurations.find_one({
        'tenant_id': current_user.tenant_id,
        'priority': priority
    })

    if existing:
        # Update
        await db.sla_configurations.update_one(
            {'id': existing['id'], 'tenant_id': current_user.tenant_id},
            {'$set': {
                'response_time_minutes': response_time_minutes,
                'resolution_time_minutes': resolution_time_minutes,
                'updated_at': datetime.now(UTC)
            }}
        )
        config_id = existing['id']
    else:
        # Create new
        config_id = str(uuid.uuid4())
        await db.sla_configurations.insert_one({
            'id': config_id,
            'tenant_id': current_user.tenant_id,
            'priority': priority,
            'response_time_minutes': response_time_minutes,
            'resolution_time_minutes': resolution_time_minutes,
            'is_active': True,
            'created_at': datetime.now(UTC),
            'updated_at': datetime.now(UTC)
        })

    return {
        'message': 'SLA configuration updated',
        'config_id': config_id,
        'priority': priority,
        'response_time_minutes': response_time_minutes,
        'resolution_time_minutes': resolution_time_minutes
    }


@router.post("/maintenance/mobile/task/{task_id}/status")
async def update_task_status_mobile(
    task_id: str,
    new_status: str,
    reason: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("maintenance")),  # v89 DW
):
    """Update task status (complete, on_hold, waiting_parts, in_progress)"""
    current_user = await get_current_user(credentials)

    task = await db.tasks.find_one({
        'id': task_id,
        'tenant_id': current_user.tenant_id
    })

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    update_data = {
        'status': new_status,
        'updated_at': datetime.now(UTC)
    }

    if new_status == 'in_progress':
        if not task.get('started_at'):
            update_data['started_at'] = datetime.now(UTC)

    elif new_status == 'completed':
        update_data['completed_at'] = datetime.now(UTC)

        # Calculate actual duration
        if task.get('started_at'):
            started = task['started_at']
            completed = datetime.now(UTC)
            duration_minutes = int((completed - started).total_seconds() / 60)
            update_data['actual_duration_minutes'] = duration_minutes

    elif new_status == 'on_hold':
        update_data['on_hold_at'] = datetime.now(UTC)
        if reason:
            update_data['on_hold_reason'] = reason

    elif new_status == 'waiting_parts':
        update_data['parts_waiting'] = True
        if reason:
            update_data['on_hold_reason'] = reason

    await db.tasks.update_one(
        {'id': task_id, 'tenant_id': current_user.tenant_id},
        {'$set': update_data}
    )

    return {
        'message': f'Task status updated to {new_status}',
        'task_id': task_id,
        'new_status': new_status,
        'updated_at': update_data['updated_at'].isoformat()
    }


@router.post("/maintenance/mobile/task/{task_id}/photo")
async def upload_task_photo_mobile(
    task_id: str,
    photo_data: str,  # Base64 encoded
    photo_type: str,  # before, during, after
    description: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("maintenance")),  # v89 DW
):
    """Upload photo for maintenance task"""
    current_user = await get_current_user(credentials)

    task = await db.tasks.find_one({
        'id': task_id,
        'tenant_id': current_user.tenant_id
    })

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Create photo record
    photo_id = str(uuid.uuid4())
    photo = {
        'id': photo_id,
        'tenant_id': current_user.tenant_id,
        'task_id': task_id,
        'photo_url': photo_data,  # In production, upload to S3/storage
        'photo_type': photo_type,
        'description': description,
        'uploaded_by': current_user.username,
        'uploaded_at': datetime.now(UTC)
    }

    await db.task_photos.insert_one(photo)

    # Update task with photo reference
    await db.tasks.update_one(
        {'id': task_id, 'tenant_id': current_user.tenant_id},
        {'$push': {'photos': photo_id}}
    )

    return {
        'message': 'Photo uploaded successfully',
        'photo_id': photo_id,
        'task_id': task_id,
        'photo_type': photo_type
    }


@router.get("/maintenance/mobile/task/{task_id}/photos")
async def get_task_photos_mobile(
    task_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get all photos for a task"""
    current_user = await get_current_user(credentials)

    photos = []
    async for photo in db.task_photos.find({
        'tenant_id': current_user.tenant_id,
        'task_id': task_id
    }).sort('uploaded_at', -1):
        photos.append({
            'id': photo.get('id'),
            'photo_url': photo.get('photo_url'),
            'photo_type': photo.get('photo_type'),
            'description': photo.get('description'),
            'uploaded_by': photo.get('uploaded_by'),
            'uploaded_at': photo.get('uploaded_at').isoformat() if photo.get('uploaded_at') else None
        })

    return {
        'photos': photos,
        'count': len(photos)
    }


@router.get("/maintenance/mobile/spare-parts")
async def get_spare_parts_mobile(
    low_stock_only: bool = False,
    warehouse_location: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get spare parts inventory"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}

    if warehouse_location:
        query['warehouse_location'] = warehouse_location

    parts = []
    low_stock_count = 0
    total_value = 0.0

    async for part in db.spare_parts.find(query).sort('part_name', 1):
        current_stock = part.get('current_stock', 0)
        minimum_stock = part.get('minimum_stock', 0)
        is_low_stock = current_stock <= minimum_stock

        if low_stock_only and not is_low_stock:
            continue

        if is_low_stock:
            low_stock_count += 1

        stock_value = current_stock * part.get('unit_price', 0)
        total_value += stock_value

        parts.append({
            'id': part.get('id'),
            'part_number': part.get('part_number'),
            'part_name': part.get('part_name'),
            'description': part.get('description'),
            'category': part.get('category'),
            'warehouse_location': part.get('warehouse_location'),
            'current_stock': current_stock,
            'minimum_stock': minimum_stock,
            'is_low_stock': is_low_stock,
            'unit_price': part.get('unit_price', 0),
            'stock_value': stock_value,
            'supplier': part.get('supplier'),
            'qr_code': part.get('qr_code'),
            'last_restocked': part.get('last_restocked').isoformat() if part.get('last_restocked') else None
        })

    return {
        'spare_parts': parts,
        'summary': {
            'total_count': len(parts),
            'low_stock_count': low_stock_count,
            'total_inventory_value': total_value
        }
    }


@router.post("/maintenance/mobile/spare-parts/use")
async def use_spare_part_mobile(
    task_id: str,
    spare_part_id: str,
    quantity: int,
    notes: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("maintenance")),  # v89 DW
):
    """Record spare part usage for a task"""
    current_user = await get_current_user(credentials)

    # Validate task
    task = await db.tasks.find_one({
        'id': task_id,
        'tenant_id': current_user.tenant_id
    })

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Validate spare part
    part = await db.spare_parts.find_one({
        'id': spare_part_id,
        'tenant_id': current_user.tenant_id
    })

    if not part:
        raise HTTPException(status_code=404, detail="Spare part not found")

    # Check stock
    current_stock = part.get('current_stock', 0)
    if current_stock < quantity:
        raise HTTPException(status_code=400, detail=f"Insufficient stock. Available: {current_stock}, Requested: {quantity}")

    # Calculate cost
    unit_price = part.get('unit_price', 0)
    total_cost = unit_price * quantity

    # Record usage
    usage_id = str(uuid.uuid4())
    usage = {
        'id': usage_id,
        'tenant_id': current_user.tenant_id,
        'task_id': task_id,
        'spare_part_id': spare_part_id,
        'part_name': part.get('part_name'),
        'quantity': quantity,
        'unit_price': unit_price,
        'total_cost': total_cost,
        'used_by': current_user.username,
        'used_at': datetime.now(UTC),
        'notes': notes
    }

    await db.spare_part_usage.insert_one(usage)

    # Update stock
    new_stock = current_stock - quantity
    await db.spare_parts.update_one(
        {'id': spare_part_id, 'tenant_id': current_user.tenant_id},
        {'$set': {
            'current_stock': new_stock,
            'updated_at': datetime.now(UTC)
        }}
    )

    # Add part to task
    await db.tasks.update_one(
        {'id': task_id, 'tenant_id': current_user.tenant_id},
        {'$push': {'parts_list': f"{part.get('part_name')} x{quantity}"}}
    )

    return {
        'message': 'Spare part usage recorded',
        'usage_id': usage_id,
        'part_name': part.get('part_name'),
        'quantity': quantity,
        'total_cost': total_cost,
        'remaining_stock': new_stock,
        'is_low_stock': new_stock <= part.get('minimum_stock', 0)
    }


@router.get("/maintenance/mobile/asset/{asset_id}/history")
async def get_asset_history_mobile(
    asset_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get maintenance history for an asset with MTBF calculation"""
    current_user = await get_current_user(credentials)

    # Get maintenance history
    history = []
    total_cost = 0.0
    total_downtime = 0
    corrective_count = 0

    async for record in db.asset_maintenance_history.find({
        'tenant_id': current_user.tenant_id,
        'asset_id': asset_id
    }).sort('completed_at', -1):
        total_cost += record.get('total_cost', 0)
        total_downtime += record.get('downtime_minutes', 0)

        if record.get('maintenance_type') == 'corrective':
            corrective_count += 1

        history.append({
            'id': record.get('id'),
            'task_id': record.get('task_id'),
            'maintenance_type': record.get('maintenance_type'),
            'description': record.get('description'),
            'parts_cost': record.get('parts_cost', 0),
            'labor_cost': record.get('labor_cost', 0),
            'total_cost': record.get('total_cost', 0),
            'technician': record.get('technician'),
            'completed_at': record.get('completed_at').isoformat() if record.get('completed_at') else None,
            'downtime_minutes': record.get('downtime_minutes'),
            'notes': record.get('notes')
        })

    # Calculate MTBF (Mean Time Between Failures)
    mtbf_hours = 0.0
    if corrective_count > 1 and history:
        first_failure = history[-1].get('completed_at') if history else None
        last_failure = history[0].get('completed_at') if history else None

        if first_failure and last_failure:
            from dateutil import parser
            first_dt = parser.isoparse(first_failure)
            last_dt = parser.isoparse(last_failure)
            total_hours = (last_dt - first_dt).total_seconds() / 3600
            mtbf_hours = total_hours / (corrective_count - 1) if corrective_count > 1 else 0

    return {
        'asset_id': asset_id,
        'maintenance_history': history,
        'summary': {
            'total_maintenance_count': len(history),
            'corrective_maintenance_count': corrective_count,
            'preventive_maintenance_count': len(history) - corrective_count,
            'total_cost': total_cost,
            'total_downtime_minutes': total_downtime,
            'total_downtime_hours': round(total_downtime / 60, 2),
            'mtbf_hours': round(mtbf_hours, 2),
            'mtbf_days': round(mtbf_hours / 24, 2)
        }
    }


@router.get("/maintenance/mobile/planned-maintenance")
async def get_planned_maintenance_mobile(
    upcoming_days: int = 30,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get planned maintenance calendar"""
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC).date()
    end_date = today + timedelta(days=upcoming_days)

    planned_items = []
    overdue_count = 0

    async for item in db.planned_maintenance.find({
        'tenant_id': current_user.tenant_id,
        'is_active': True
    }).sort('next_maintenance', 1):
        next_maintenance_date = item.get('next_maintenance')

        if isinstance(next_maintenance_date, str):
            next_maintenance_date = datetime.fromisoformat(next_maintenance_date).date()
        elif isinstance(next_maintenance_date, datetime):
            next_maintenance_date = next_maintenance_date.date()

        if next_maintenance_date <= end_date:
            is_overdue = next_maintenance_date < today
            days_until = (next_maintenance_date - today).days

            if is_overdue:
                overdue_count += 1

            planned_items.append({
                'id': item.get('id'),
                'asset_id': item.get('asset_id'),
                'asset_name': item.get('asset_name'),
                'maintenance_type': item.get('maintenance_type'),
                'frequency_days': item.get('frequency_days'),
                'last_maintenance': item.get('last_maintenance').isoformat() if item.get('last_maintenance') else None,
                'next_maintenance': next_maintenance_date.isoformat(),
                'estimated_duration_minutes': item.get('estimated_duration_minutes'),
                'assigned_to': item.get('assigned_to'),
                'is_overdue': is_overdue,
                'days_until': days_until,
                'notes': item.get('notes')
            })

    return {
        'planned_maintenance': planned_items,
        'summary': {
            'total_count': len(planned_items),
            'overdue_count': overdue_count,
            'upcoming_7days': len([p for p in planned_items if 0 <= p['days_until'] <= 7]),
            'upcoming_30days': len([p for p in planned_items if 0 <= p['days_until'] <= 30])
        }
    }


@router.get("/maintenance/mobile/tasks/filtered")
async def get_filtered_tasks_mobile(
    status: str | None = None,
    priority: str | None = None,
    assigned_to: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get filtered maintenance tasks"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}

    if status:
        query['status'] = status
    if priority:
        query['priority'] = priority
    if assigned_to:
        query['assigned_to'] = assigned_to

    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter['$gte'] = datetime.fromisoformat(start_date)
        if end_date:
            date_filter['$lte'] = datetime.fromisoformat(end_date)
        query['created_at'] = date_filter

    tasks = []
    async for task in db.tasks.find(query).sort('created_at', -1).limit(100):
        tasks.append({
            'id': task.get('id'),
            'task_number': task.get('task_number'),
            'title': task.get('title'),
            'description': task.get('description'),
            'priority': task.get('priority'),
            'status': task.get('status'),
            'room_number': task.get('room_number'),
            'assigned_to': task.get('assigned_to'),
            'created_at': task.get('created_at').isoformat() if task.get('created_at') else None,
            'started_at': task.get('started_at').isoformat() if task.get('started_at') else None,
            'completed_at': task.get('completed_at').isoformat() if task.get('completed_at') else None
        })

    return {
        'tasks': tasks,
        'count': len(tasks),
        'filters_applied': {
            'status': status,
            'priority': priority,
            'assigned_to': assigned_to,
            'start_date': start_date,
            'end_date': end_date
        }
    }


@router.get("/notifications/mobile/maintenance")
async def get_maintenance_notifications_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get notifications for maintenance mobile dashboard"""
    current_user = await get_current_user(credentials)

    notifications = []

    # Water leak / electrical issues (critical)
    critical_issues = ['water_leak', 'electrical', 'gas_leak', 'fire_alarm']

    async for task in db.tasks.find({
        'tenant_id': current_user.tenant_id,
        'department': 'maintenance',
        'issue_type': {'$in': critical_issues},
        'status': {'$in': ['new', 'assigned', 'in_progress']},
        'created_at': {'$gte': datetime.now(UTC) - timedelta(hours=24)}
    }):
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'critical_issue',
            'title': 'Critical Issue',
            'message': f"Room {task.get('room_number', 'N/A')}: {task.get('issue_type', 'Unknown')} - {task.get('description', '')}",
            'priority': 'urgent',
            'created_at': task.get('created_at').isoformat()
        })

    # SLA breach alerts
    async for task in db.tasks.find({
        'tenant_id': current_user.tenant_id,
        'department': 'maintenance',
        'priority': 'urgent',
        'status': {'$in': ['new', 'assigned']},
        'created_at': {'$lte': datetime.now(UTC) - timedelta(hours=2)}
    }):
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'sla_breach',
            'title': 'SLA İhlali',
            'message': f"Görev #{task.get('id')[:8]} - 2 saatten fazla bekliyor",
            'priority': 'high',
            'created_at': task.get('created_at').isoformat()
        })

    # Critical room maintenance (room is out of order)
    async for room in db.rooms.find({
        'tenant_id': current_user.tenant_id,
        'status': 'out_of_order',
        'updated_at': {'$gte': datetime.now(UTC) - timedelta(days=1)}
    }):
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'critical_room',
            'title': 'Room Out of Service',
            'message': f"Room {room.get('room_number')} out of service - Urgent attention required",
            'priority': 'high',
            'created_at': room.get('updated_at').isoformat()
        })

    return {
        'notifications': notifications,
        'unread_count': len(notifications)
    }


# --------------------------------------------------------------------------
# F&B Mobile Dashboard Endpoints
# --------------------------------------------------------------------------

@router.post("/pos/mobile/quick-order")
async def create_quick_order_mobile(
    request: QuickOrderRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("pos")),  # v89 DW
):
    """Create a quick POS order from mobile"""
    current_user = await get_current_user(credentials)
    outlet_id = request.outlet_id
    table_number = request.table_number
    items = [item.dict() for item in request.items]
    notes = request.notes

    # Validate outlet
    outlet = await db.pos_outlets.find_one({
        'id': outlet_id,
        'tenant_id': current_user.tenant_id
    })

    if not outlet:
        raise HTTPException(status_code=404, detail="Outlet not found")

    # Calculate total
    subtotal = 0.0
    order_items = []

    for item in items:
        menu_item = await db.pos_menu_items.find_one({
            'id': item.get('item_id'),
            'tenant_id': current_user.tenant_id
        })

        if not menu_item:
            continue

        quantity = item.get('quantity', 1)
        item_price = menu_item.get('price', 0)
        item_total = item_price * quantity
        subtotal += item_total

        order_items.append({
            'item_id': item.get('item_id'),
            'item_name': menu_item.get('name'),
            'quantity': quantity,
            'unit_price': item_price,
            'total': item_total
        })

    # Calculate tax (18% VAT)
    tax = subtotal * 0.18
    total = subtotal + tax

    # Create order
    order_id = str(uuid.uuid4())
    order = {
        'id': order_id,
        'tenant_id': current_user.tenant_id,
        'outlet_id': outlet_id,
        'outlet_name': outlet.get('name'),
        'table_number': table_number,
        'items': order_items,
        'subtotal': subtotal,
        'tax': tax,
        'total': total,
        'status': 'pending',
        'notes': notes,
        'created_at': datetime.now(UTC),
        'created_by': current_user.username
    }

    await db.pos_orders.insert_one(order)

    return {
        'message': 'Order created successfully',
        'order_id': order_id,
        'outlet_name': outlet.get('name'),
        'table_number': table_number,
        'total': total,
        'items_count': len(order_items)
    }


@router.put("/pos/mobile/menu-items/{item_id}/price")
async def update_menu_item_price_mobile(
    item_id: str,
    request: MenuPriceUpdateRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("pos")),  # v89 DW
):
    """Update menu item price from mobile"""
    current_user = await get_current_user(credentials)
    new_price = request.new_price
    reason = request.reason

    # Find menu item
    menu_item = await db.pos_menu_items.find_one({
        'id': item_id,
        'tenant_id': current_user.tenant_id
    })

    if not menu_item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    old_price = menu_item.get('price')

    # Update price
    await db.pos_menu_items.update_one(
        {'id': item_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'price': new_price,
                'price_updated_at': datetime.now(UTC),
                'price_updated_by': current_user.username
            }
        }
    )

    # Log price change
    await db.audit_logs.insert_one({
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'user_id': current_user.user_id,
        'user_name': current_user.username,
        'action': 'MENU_PRICE_UPDATE',
        'entity_type': 'menu_item',
        'entity_id': item_id,
        'changes': {
            'item_name': menu_item.get('name'),
            'old_price': old_price,
            'new_price': new_price,
            'reason': reason
        },
        'timestamp': datetime.now(UTC)
    })

    return {
        'message': 'Menu item price updated',
        'item_id': item_id,
        'item_name': menu_item.get('name'),
        'old_price': old_price,
        'new_price': new_price
    }


@router.get("/notifications/mobile/fnb")
async def get_fnb_notifications_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get notifications for F&B mobile dashboard"""
    current_user = await get_current_user(credentials)

    notifications = []

    # Void transactions in last 24 hours
    void_transactions = 0
    async for transaction in db.pos_transactions.find({
        'tenant_id': current_user.tenant_id,
        'status': 'voided',
        'voided_at': {'$gte': datetime.now(UTC) - timedelta(hours=24)}
    }):
        void_transactions += 1

    if void_transactions > 0:
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'void_transaction',
            'title': 'İptal Edilen İşlemler',
            'message': f"Son 24 saatte {void_transactions} işlem iptal edildi",
            'priority': 'medium',
            'created_at': datetime.now(UTC).isoformat()
        })

    # POS connection errors
    async for error in db.system_logs.find({
        'tenant_id': current_user.tenant_id,
        'log_type': 'pos_error',
        'created_at': {'$gte': datetime.now(UTC) - timedelta(hours=1)}
    }).limit(1):
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'pos_error',
            'title': 'POS Connection Error',
            'message': error.get('message', 'POS system connection issue'),
            'priority': 'high',
            'created_at': error.get('created_at').isoformat()
        })

    # End of day report ready notification
    today = datetime.now(UTC).date().isoformat()
    eod_report = await db.pos_eod_reports.find_one({
        'tenant_id': current_user.tenant_id,
        'report_date': today
    })

    if eod_report and eod_report.get('status') == 'ready':
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'eod_report_ready',
            'title': 'Gün Sonu Raporu Hazır',
            'message': f"Toplam satış: ₺{eod_report.get('total_sales', 0):.2f}",
            'priority': 'info',
            'created_at': eod_report.get('created_at').isoformat()
        })

    return {
        'notifications': notifications,
        'unread_count': len(notifications)
    }


# --------------------------------------------------------------------------
# Finance Mobile Dashboard Endpoints (NEW)
# --------------------------------------------------------------------------

