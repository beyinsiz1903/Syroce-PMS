"""
notifications

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Domain Router: Analytics

Extracted from legacy_routes.py — GM Dashboard, pickup analysis, anomaly detection, revenue analytics.
"""
import random
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from core.cache import cached
from core.database import db
from core.helpers import require_module
from core.security import _is_super_admin, get_current_user, security
from models.enums import ChannelType
from modules.pms_core.role_permission_service import require_module as require_module_rbac  # v89 DW
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.role_permission_service import require_role as _require_role

# v67 Bug DD: frontdesk/* endpoint'lerinde RBAC eksikti — HK kullanıcı guest PII (search-bookings),
# müsaitlik (available-rooms), oda atama (assign-room) erişebiliyordu. Front office personeline kısıtla.
_FD_READ = Depends(_require_role("super_admin", "admin", "supervisor", "front_desk"))
_FD_WRITE = Depends(_require_role("super_admin", "admin", "front_desk"))

try:
    from routers.pms_availability import check_room_availability
except Exception:  # pragma: no cover
    async def check_room_availability(*args, **kwargs):
        return {"available": False, "rooms": []}



# --------------------------------------------------------------------------
# GM Dashboard - Pickup Analysis & Anomaly Detection
# --------------------------------------------------------------------------







# rbac-allow: cache-rbac — FO booking search operasyonel

# rbac-allow: cache-rbac — FO available rooms operasyonel




from integrations.booking_adapter import BookingAdapter







































_SYSTEM_HEALTH_CACHE: dict = {"ts": 0.0, "payload": None}
_SYSTEM_HEALTH_TTL = 5.0  # seconds

router = APIRouter(prefix="/api", tags=["analytics"])


# ── POST /notifications/send ──
@router.post("/notifications/send")
async def send_notification(
    notification_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(get_current_user),  # v89 DW: auth-only
):
    """Send a notification to user(s)"""
    current_user = await get_current_user(credentials)

    notification = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'type': notification_data.get('type', 'info'),  # info, warning, alert, success
        'category': notification_data.get('category', 'general'),  # revenue, maintenance, booking, etc
        'title': notification_data.get('title'),
        'message': notification_data.get('message'),
        'priority': notification_data.get('priority', 'normal'),  # low, normal, high, critical
        'user_id': notification_data.get('user_id'),  # specific user or None for broadcast
        'read': False,
        'action_url': notification_data.get('action_url'),
        'metadata': notification_data.get('metadata', {}),
        'created_at': datetime.now(UTC).isoformat(),
        'expires_at': notification_data.get('expires_at')
    }

    await db.notifications.insert_one(notification)

    return {
        'message': 'Notification sent',
        'notification_id': notification['id']
    }
# ── GET /notifications/my ──
@router.get("/notifications/my")
async def get_my_notifications(
    unread_only: bool = False,
    limit: int = 50,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get notifications for current user"""
    current_user = await get_current_user(credentials)

    query = {
        'tenant_id': current_user.tenant_id,
        '$or': [
            {'user_id': current_user.id},
            {'user_id': None}  # Broadcast notifications
        ]
    }

    if unread_only:
        query['read'] = False

    notifications = []
    async for notif in db.notifications.find(query).sort('created_at', -1).limit(limit):
        notif.pop('_id', None)
        notifications.append(notif)

    unread_count = await db.notifications.count_documents({
        'tenant_id': current_user.tenant_id,
        '$or': [
            {'user_id': current_user.id},
            {'user_id': None}
        ],
        'read': False
    })

    return {
        'notifications': notifications,
        'unread_count': unread_count,
        'total': len(notifications)
    }
# ── POST /notifications/{notification_id}/mark-read ──
@router.post("/notifications/{notification_id}/mark-read")
async def mark_notification_read(
    notification_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(get_current_user),  # v89 DW: auth-only
):
    """Mark a notification as read"""
    current_user = await get_current_user(credentials)

    await db.notifications.update_one(
        {
            'id': notification_id,
            'tenant_id': current_user.tenant_id
        },
        {
            '$set': {'read': True}
        }
    )

    return {'message': 'Notification marked as read'}
# ── POST /notifications/mark-all-read ──
@router.post("/notifications/mark-all-read")
async def mark_all_notifications_read(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(get_current_user),  # v89 DW: auth-only
):
    """Mark all notifications as read for current user"""
    current_user = await get_current_user(credentials)

    result = await db.notifications.update_many(
        {
            'tenant_id': current_user.tenant_id,
            '$or': [
                {'user_id': current_user.id},
                {'user_id': None}
            ],
            'read': False
        },
        {
            '$set': {'read': True}
        }
    )

    return {
        'message': 'All notifications marked as read',
        'count': result.modified_count
    }
# ── POST /alerts/check-and-notify ──
@router.post("/alerts/check-and-notify")
async def check_alerts_and_notify(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_system_diagnostics")),  # v89 DW
):
    """Check system for alert conditions and send notifications"""
    current_user = await get_current_user(credentials)

    alerts_sent = []

    # Check revenue drop
    today = datetime.now(UTC)
    yesterday = today - timedelta(days=1)

    # Revenue alert
    revenue_today = 0
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': today.date().isoformat(),
        'status': {'$in': ['confirmed', 'checked_in']}
    }):
        revenue_today += booking.get('total_amount', 0)

    revenue_yesterday = 0
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': yesterday.date().isoformat(),
        'status': {'$in': ['confirmed', 'checked_in', 'checked_out']}
    }):
        revenue_yesterday += booking.get('total_amount', 0)

    if revenue_yesterday > 0 and revenue_today < revenue_yesterday * 0.7:
        # Revenue dropped by 30%+
        alert = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'type': 'alert',
            'category': 'revenue',
            'title': '⚠️ Gelir Düşüşü Tespit Edildi',
            'message': f'Bugünkü gelir dünle karşılaştırıldığında %{int((1 - revenue_today/revenue_yesterday) * 100)} düşük',
            'priority': 'high',
            'user_id': None,
            'read': False,
            'metadata': {
                'today_revenue': revenue_today,
                'yesterday_revenue': revenue_yesterday
            },
            'created_at': datetime.now(UTC).isoformat()
        }
        await db.notifications.insert_one(alert)
        alerts_sent.append('revenue_drop')

    # Overbooking check
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    bookings_today = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': today.date().isoformat(),
        'status': {'$in': ['confirmed', 'guaranteed']}
    })

    if bookings_today > total_rooms:
        alert = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'type': 'alert',
            'category': 'booking',
            'title': '🚨 Overbooking Riski',
            'message': f'{bookings_today} rezervasyon var, sadece {total_rooms} oda mevcut',
            'priority': 'critical',
            'user_id': None,
            'read': False,
            'created_at': datetime.now(UTC).isoformat()
        }
        await db.notifications.insert_one(alert)
        alerts_sent.append('overbooking')

    # Maintenance emergency
    emergency_tasks = await db.maintenance_tasks.count_documents({
        'tenant_id': current_user.tenant_id,
        'priority': 'emergency',
        'status': {'$ne': 'completed'}
    })

    if emergency_tasks > 0:
        alert = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'type': 'alert',
            'category': 'maintenance',
            'title': '🔧 Acil Bakım Görevi',
            'message': f'{emergency_tasks} acil bakım görevi bekliyor',
            'priority': 'high',
            'user_id': None,
            'read': False,
            'created_at': datetime.now(UTC).isoformat()
        }
        await db.notifications.insert_one(alert)
        alerts_sent.append('maintenance_emergency')

    return {
        'message': 'Alert check completed',
        'alerts_sent': alerts_sent,
        'count': len(alerts_sent)
    }
