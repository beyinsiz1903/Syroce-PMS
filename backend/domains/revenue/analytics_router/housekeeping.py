"""
housekeeping

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


# ── POST /housekeeping/room/{room_id}/photo ──
@router.post("/housekeeping/room/{room_id}/photo")
async def upload_room_photo(
    room_id: str,
    photo_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_rbac("housekeeping")),  # v89 DW
):
    """Upload a photo for room inspection"""
    current_user = await get_current_user(credentials)

    photo = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'room_id': room_id,
        'photo_url': photo_data.get('photo_url'),  # Base64 or URL
        'photo_type': photo_data.get('photo_type', 'inspection'),  # inspection, damage, before, after
        'notes': photo_data.get('notes', ''),
        'uploaded_by': current_user.name,
        'uploaded_at': datetime.now(UTC).isoformat()
    }

    await db.room_photos.insert_one(photo)

    return {
        'message': 'Photo uploaded',
        'photo_id': photo['id']
    }
# ── GET /housekeeping/room/{room_id}/photos ──
@router.get("/housekeeping/room/{room_id}/photos")
async def get_room_photos(
    room_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get all photos for a room"""
    current_user = await get_current_user(credentials)

    photos = []
    async for photo in db.room_photos.find({
        'tenant_id': current_user.tenant_id,
        'room_id': room_id
    }).sort('uploaded_at', -1):
        photo.pop('_id', None)
        photos.append(photo)

    return {'photos': photos, 'count': len(photos)}
# ── POST /housekeeping/room/{room_id}/checklist ──
@router.post("/housekeeping/room/{room_id}/checklist")
async def complete_room_checklist(
    room_id: str,
    checklist_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_rbac("housekeeping")),  # v89 DW
):
    """Complete room cleaning checklist"""
    current_user = await get_current_user(credentials)

    checklist = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'room_id': room_id,
        'items': checklist_data.get('items', []),  # List of checklist items with status
        'completed_by': current_user.name,
        'completed_at': datetime.now(UTC).isoformat(),
        'total_items': len(checklist_data.get('items', [])),
        'completed_items': sum(1 for item in checklist_data.get('items', []) if item.get('checked')),
        'notes': checklist_data.get('notes', '')
    }

    await db.room_checklists.insert_one(checklist)

    return {
        'message': 'Checklist completed',
        'checklist_id': checklist['id'],
        'completion_rate': f"{checklist['completed_items']}/{checklist['total_items']}"
    }
# ── POST /housekeeping/lost-found/update-status ──
@router.post("/housekeeping/lost-found/update-status")
async def update_lost_found_status(
    item_id: str,
    status_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_rbac("housekeeping")),  # v89 DW
):
    """Update lost & found item status"""
    current_user = await get_current_user(credentials)

    new_status = status_data.get('status')  # found, claimed, expired, disposed

    update_data = {
        'status': new_status,
        'updated_at': datetime.now(UTC).isoformat(),
        'updated_by': current_user.name
    }

    if new_status == 'claimed':
        update_data['claimed_by_name'] = status_data.get('claimed_by_name')
        update_data['claimed_by_id'] = status_data.get('claimed_by_id')
        update_data['claimed_at'] = datetime.now(UTC).isoformat()

    await db.lost_found_items.update_one(
        {'id': item_id, 'tenant_id': current_user.tenant_id},
        {'$set': update_data}
    )

    return {
        'message': 'Status updated',
        'item_id': item_id,
        'new_status': new_status
    }
# ── POST /housekeeping/lost-found/transfer ──
@router.post("/housekeeping/lost-found/transfer")
async def transfer_lost_found_item(
    item_id: str,
    transfer_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_rbac("housekeeping")),  # v89 DW
):
    """Transfer lost & found item to another department/location"""
    current_user = await get_current_user(credentials)

    transfer_record = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'item_id': item_id,
        'from_location': transfer_data.get('from_location'),
        'to_location': transfer_data.get('to_location'),
        'transferred_by': current_user.name,
        'notes': transfer_data.get('notes', ''),
        'transferred_at': datetime.now(UTC).isoformat()
    }

    await db.lost_found_transfers.insert_one(transfer_record)

    # Update item location
    await db.lost_found_items.update_one(
        {'id': item_id},
        {'$set': {
            'current_location': transfer_data.get('to_location'),
            'last_transfer_at': datetime.now(UTC).isoformat()
        }}
    )

    return {
        'message': 'Item transferred',
        'transfer_id': transfer_record['id']
    }
# ── GET /housekeeping/lost-found/item/{item_id}/history ──
@router.get("/housekeeping/lost-found/item/{item_id}/history")
async def get_lost_found_history(
    item_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get full history of a lost & found item"""
    current_user = await get_current_user(credentials)

    # Get item details
    item = await db.lost_found_items.find_one({
        'id': item_id,
        'tenant_id': current_user.tenant_id
    })

    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    item.pop('_id', None)

    # Get transfer history
    transfers = []
    async for transfer in db.lost_found_transfers.find({
        'tenant_id': current_user.tenant_id,
        'item_id': item_id
    }).sort('transferred_at', 1):
        transfer.pop('_id', None)
        transfers.append(transfer)

    return {
        'item': item,
        'transfers': transfers,
        'transfer_count': len(transfers)
    }
# ── POST /housekeeping/qr-room-access ──
@router.post("/housekeeping/qr-room-access")
async def qr_room_access(
    access_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_rbac("housekeeping")),  # v89 DW
):
    """Record room access via QR code (start/end cleaning)"""
    current_user = await get_current_user(credentials)

    room_id = access_data.get('room_id')
    room_number = access_data.get('room_number')
    action = access_data.get('action')  # 'start' or 'end'

    # Check if there's an active session
    active_session = await db.room_access_logs.find_one({
        'tenant_id': current_user.tenant_id,
        'room_id': room_id,
        'staff_id': current_user.id,
        'end_time': None
    })

    if action == 'start':
        if active_session:
            raise HTTPException(status_code=400, detail="Active cleaning session already exists")

        # Create new session
        session = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'room_id': room_id,
            'room_number': room_number,
            'staff_id': current_user.id,
            'staff_name': current_user.name,
            'start_time': datetime.now(UTC).isoformat(),
            'end_time': None,
            'duration_minutes': None,
            'notes': access_data.get('notes', ''),
            'created_at': datetime.now(UTC).isoformat()
        }

        await db.room_access_logs.insert_one(session)

        # Update room status to cleaning
        await db.rooms.update_one(
            {'id': room_id},
            {'$set': {'status': 'cleaning'}}
        )

        return {
            'message': 'Cleaning started',
            'session_id': session['id'],
            'start_time': session['start_time']
        }

    elif action == 'end':
        if not active_session:
            raise HTTPException(status_code=400, detail="No active cleaning session found")

        # End session
        end_time = datetime.now(UTC)
        start_time = datetime.fromisoformat(active_session['start_time'])
        duration = (end_time - start_time).total_seconds() / 60  # minutes

        await db.room_access_logs.update_one(
            {'id': active_session['id']},
            {'$set': {
                'end_time': end_time.isoformat(),
                'duration_minutes': round(duration, 1)
            }}
        )

        # Update room status to inspected
        await db.rooms.update_one(
            {'id': room_id},
            {'$set': {'status': 'inspected'}}
        )

        return {
            'message': 'Cleaning completed',
            'session_id': active_session['id'],
            'duration_minutes': round(duration, 1),
            'start_time': active_session['start_time'],
            'end_time': end_time.isoformat()
        }

    else:
        raise HTTPException(status_code=400, detail="Invalid action")
# ── GET /housekeeping/my-active-sessions ──
@router.get("/housekeeping/my-active-sessions")
async def get_my_active_sessions(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get current user's active cleaning sessions"""
    current_user = await get_current_user(credentials)

    sessions = []
    async for session in db.room_access_logs.find({
        'tenant_id': current_user.tenant_id,
        'staff_id': current_user.id,
        'end_time': None
    }):
        session.pop('_id', None)

        # Calculate elapsed time
        start_time = datetime.fromisoformat(session['start_time'])
        elapsed = (datetime.now(UTC) - start_time).total_seconds() / 60
        session['elapsed_minutes'] = round(elapsed, 1)

        sessions.append(session)

    return {
        'active_sessions': sessions,
        'count': len(sessions)
    }
# ── GET /housekeeping/room-access-logs ──
@router.get("/housekeeping/room-access-logs")
async def get_room_access_logs(
    room_id: str | None = None,
    staff_id: str | None = None,
    date: str | None = None,
    limit: int = 50,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get room access logs with filters"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}

    if room_id:
        query['room_id'] = room_id
    if staff_id:
        query['staff_id'] = staff_id
    if date:
        query['created_at'] = {'$regex': f'^{date}'}

    logs = []
    async for log in db.room_access_logs.find(query).sort('created_at', -1).limit(limit):
        log.pop('_id', None)
        logs.append(log)

    # Calculate stats
    total_duration = sum(log.get('duration_minutes', 0) for log in logs if log.get('duration_minutes'))
    avg_duration = round(total_duration / len([l for l in logs if l.get('duration_minutes')]), 1) if logs else 0

    return {
        'logs': logs,
        'count': len(logs),
        'stats': {
            'total_duration_minutes': round(total_duration, 1),
            'avg_duration_minutes': avg_duration,
            'completed_sessions': len([l for l in logs if l.get('end_time')])
        }
    }
# ── GET /housekeeping/checklist-template ──
@router.get("/housekeeping/checklist-template")
async def get_checklist_template(
    room_type: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get standard cleaning checklist template"""
    await get_current_user(credentials)

    standard_template = [
        {'id': '1', 'category': 'bedroom', 'item': 'Yatak takımları değiştirildi', 'required': True},
        {'id': '2', 'category': 'bedroom', 'item': 'Yastıklar kontrol edildi', 'required': True},
        {'id': '3', 'category': 'bedroom', 'item': 'Mobilyalar silindi', 'required': True},
        {'id': '4', 'category': 'bathroom', 'item': 'Banyo temizlendi', 'required': True},
        {'id': '5', 'category': 'bathroom', 'item': 'Havlular yenilendi', 'required': True},
        {'id': '6', 'category': 'bathroom', 'item': 'Sıhhi tesisat kontrol edildi', 'required': False},
        {'id': '7', 'category': 'general', 'item': 'Zemin süpürüldü/silindi', 'required': True},
        {'id': '8', 'category': 'general', 'item': 'Çöpler toplandı', 'required': True},
        {'id': '9', 'category': 'general', 'item': 'Minibar kontrol edildi', 'required': False},
        {'id': '10', 'category': 'general', 'item': 'Klima çalışıyor', 'required': True},
        {'id': '11', 'category': 'general', 'item': 'TV ve kumanda çalışıyor', 'required': False},
        {'id': '12', 'category': 'general', 'item': 'Pencereler temiz', 'required': False}
    ]

    return {
        'template': standard_template,
        'room_type': room_type or 'Standard'
    }
