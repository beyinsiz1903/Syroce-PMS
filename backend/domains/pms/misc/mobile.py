"""Auto-split from misc_router.py — backward-compatible sub-router."""
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.helpers import require_module
from core.security import get_current_user
from models.enums import UserRole
from models.schemas import User
from modules.pms_core.role_permission_service import require_module as require_module_v101
from modules.pms_core.role_permission_service import require_op

from ._common import (
    DEFAULT_PUSH_CHANNELS,
)

logger = logging.getLogger(__name__)

sub_router = APIRouter()

# ============= MOBILE APP BACKEND =============



@sub_router.post("/mobile/register-device")
async def register_mobile_device(device_data: dict, current_user: User = Depends(get_current_user)):
    """Mobil cihaz kaydı"""
    device = {
        'id': str(uuid.uuid4()),
        'user_id': current_user.id,
        'device_id': device_data['device_id'],
        'device_type': device_data['device_type'],
        'push_token': device_data.get('push_token'),
        'app_version': device_data.get('app_version', '1.0.0'),
        'os_version': device_data.get('os_version'),
        'registered_at': datetime.now(UTC).isoformat(),
        'last_active': datetime.now(UTC).isoformat()
    }
    await db.mobile_devices.insert_one(device)

    if device_data.get('push_token'):
        await db.push_device_tokens.update_one(
            {
                'tenant_id': current_user.tenant_id,
                'user_id': current_user.id,
                'device_id': device_data['device_id']
            },
            {
                '$set': {
                    'tenant_id': current_user.tenant_id,
                    'user_id': current_user.id,
                    'device_id': device_data['device_id'],
                    'platform': device_data.get('device_type', 'mobile'),
                    'push_token': device_data['push_token'],
                    'app_version': device_data.get('app_version'),
                    'os_version': device_data.get('os_version'),
                    'subscriptions': DEFAULT_PUSH_CHANNELS,
                    'departments': [current_user.role] if current_user.role else [],
                    'updated_at': datetime.now(UTC).isoformat(),
                    'created_at': datetime.now(UTC).isoformat()
                }
            },
            upsert=True
        )
    return {'success': True, 'device_id': device['id']}



@sub_router.post("/mobile/push-notification")
async def send_push_notification(notification_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    """Push notification gönder"""
    notification = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'title': notification_data['title'],
        'body': notification_data['body'],
        'sent_at': datetime.now(UTC).isoformat()
    }
    await db.push_notifications.insert_one(notification)
    return {'success': True, 'message': 'Push notification gönderildi (MOCK)'}

@sub_router.get("/mobile/staff/dashboard")
async def get_staff_mobile_dashboard(
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("pms_mobile")),
):
    """
    Mobile staff dashboard
    - Role-based dashboard
    - Quick actions
    - Today's tasks
    """
    role = current_user.role

    dashboard = {
        'user_name': current_user.name,
        'user_role': role.value,
        'quick_actions': [],
        'today_tasks': [],
        'notifications_count': 0
    }

    if role == UserRole.HOUSEKEEPING:
        # Housekeeping tasks — batch room lookup (was N+1)
        task_docs = await db.housekeeping_tasks.find({
            'tenant_id': current_user.tenant_id,
            'assigned_to': current_user.name,
            'status': {'$in': ['pending', 'in_progress']}
        }).limit(20).to_list(20)

        task_room_ids = list({t.get('room_id') for t in task_docs if t.get('room_id')})
        room_num_map = {}
        if task_room_ids:
            async for r in db.rooms.find(
                {'id': {'$in': task_room_ids}, 'tenant_id': current_user.tenant_id},
                {'_id': 0, 'id': 1, 'room_number': 1}
            ):
                room_num_map[r['id']] = r.get('room_number', 'N/A')

        tasks = [{
            'task_id': t.get('id'),
            'room_number': room_num_map.get(t.get('room_id'), 'N/A'),
            'task_type': t.get('task_type'),
            'priority': t.get('priority'),
            'status': t.get('status')
        } for t in task_docs]

        dashboard['quick_actions'] = ['Start Task', 'Report Issue', 'Take Photo']
        dashboard['today_tasks'] = tasks
        dashboard['notifications_count'] = len(tasks)

    elif role == UserRole.FRONT_DESK:
        # Check-in tasks — batch guest lookup (was N+1)
        today = datetime.now().date().isoformat()
        booking_docs = await db.bookings.find({
            'tenant_id': current_user.tenant_id,
            'check_in': today,
            'status': {'$in': ['confirmed', 'guaranteed']}
        }).limit(10).to_list(10)

        booking_guest_ids = list({b.get('guest_id') for b in booking_docs if b.get('guest_id')})
        guest_name_map = {}
        if booking_guest_ids:
            async for g in db.guests.find(
                {'id': {'$in': booking_guest_ids}, 'tenant_id': current_user.tenant_id},
                {'_id': 0, 'id': 1, 'name': 1}
            ):
                guest_name_map[g['id']] = g.get('name', 'Guest')

        arrivals = [{
            'booking_id': b.get('id'),
            'guest_name': guest_name_map.get(b.get('guest_id'), 'Guest'),
            'room': b.get('room_id'),
            'status': 'Pending Check-in'
        } for b in booking_docs]

        dashboard['quick_actions'] = ['Quick Check-in', 'Walk-in Booking', 'Scan Passport']
        dashboard['today_tasks'] = arrivals
        dashboard['notifications_count'] = len(arrivals)

    elif role == UserRole.SUPERVISOR or role == UserRole.ADMIN:
        # Supervisor checklists
        dashboard['quick_actions'] = ['View Reports', 'Staff Performance', 'Occupancy Status']
        dashboard['today_tasks'] = [
            {'type': 'checklist', 'title': 'Morning Inspection', 'status': 'pending'},
            {'type': 'checklist', 'title': 'Revenue Review', 'status': 'pending'},
            {'type': 'checklist', 'title': 'Staff Briefing', 'status': 'completed'}
        ]

    return dashboard




@sub_router.post("/mobile/staff/quick-checkin")
async def mobile_quick_checkin(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    """Quick check-in from mobile — atomic transaction."""
    from core.atomic_checkin_checkout import CheckInError, check_in_booking_atomic
    try:
        result = await check_in_booking_atomic(
            booking_id=booking_id,
            tenant_id=current_user.tenant_id,
            actor_id=current_user.id,
            actor_name=current_user.name,
        )
        return {
            'success': True,
            'message': 'Guest checked in successfully',
            'booking_id': booking_id,
            'checked_in_at': result.get('checked_in_at'),
        }
    except CheckInError as e:
        raise HTTPException(status_code=400, detail=str(e))


