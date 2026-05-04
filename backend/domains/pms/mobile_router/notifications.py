"""
notifications

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Domain Router: Mobile

Extracted from legacy_routes.py — Mobile dashboard, GM mobile, department mobile endpoints.
"""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from cache_manager import cached
from core.database import db
from core.security import get_current_user, security
from models.schemas import User
from modules.pms_core.role_permission_service import (
    require_op,
)

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


# ── GET /notifications/mobile/gm ──
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
# ── GET /notifications/mobile/frontdesk ──
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
# ── GET /notifications/mobile/housekeeping ──
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
# ── GET /notifications/mobile/maintenance ──
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
# ── GET /notifications/mobile/fnb ──
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
