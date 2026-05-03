"""
crm

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


# ── GET /crm/guest/{guest_id}/notes ──
@router.get("/crm/guest/{guest_id}/notes")
async def get_guest_notes(
    guest_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get CRM notes for a guest"""
    current_user = await get_current_user(credentials)

    notes = []
    async for note in db.crm_notes.find({
        'tenant_id': current_user.tenant_id,
        'guest_id': guest_id
    }).sort('created_at', -1):
        note.pop('_id', None)
        notes.append(note)

    return {'notes': notes, 'guest_id': guest_id}
# ── POST /crm/guest/{guest_id}/note ──
@router.post("/crm/guest/{guest_id}/note")
async def add_guest_note(
    guest_id: str,
    note_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_guests")),  # v89 DW
):
    """Add a CRM note for a guest"""
    current_user = await get_current_user(credentials)

    note = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'guest_id': guest_id,
        'content': note_data.get('content'),
        'category': note_data.get('category', 'general'),
        'created_by': current_user.name,
        'created_at': datetime.now(UTC).isoformat()
    }

    await db.crm_notes.insert_one(note)
    return {'message': 'Note added successfully', 'note_id': note['id']}
