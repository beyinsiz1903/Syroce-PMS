"""
approvals

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


# ── POST /approvals/request ──
@router.post("/approvals/request")
async def create_approval_request(
    request_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_approvals")),  # v89 DW
):
    """Create a new approval request"""
    current_user = await get_current_user(credentials)

    approval_types = ['discount', 'rate_override', 'budget', 'refund', 'complimentary']

    if request_data.get('type') not in approval_types:
        raise HTTPException(status_code=400, detail="Invalid approval type")

    approval = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'type': request_data.get('type'),
        'amount': request_data.get('amount', 0),
        'reason': request_data.get('reason', ''),
        'booking_id': request_data.get('booking_id'),
        'requested_by': current_user.id,
        'requested_by_name': current_user.name,
        'requested_by_email': current_user.email,
        'status': 'pending',
        'priority': request_data.get('priority', 'normal'),
        'metadata': request_data.get('metadata', {}),
        'created_at': datetime.now(UTC).isoformat(),
        'approved_at': None,
        'approved_by': None,
        'approved_by_name': None,
        'rejection_reason': None
    }

    await db.approval_requests.insert_one(approval)

    return {
        'message': 'Approval request created',
        'approval_id': approval['id'],
        'status': 'pending'
    }
# ── GET /approvals/pending ──
@router.get("/approvals/pending")
async def get_pending_approvals(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get all pending approval requests"""
    current_user = await get_current_user(credentials)

    # Only managers and admins can see approvals (Sprint 33: super_admin included)
    if not _is_super_admin(current_user) and current_user.role not in ['admin', 'manager', 'gm', 'super_admin']:
        raise HTTPException(status_code=403, detail="Access denied")

    approvals = []
    urgent_count = 0
    async for approval in db.approval_requests.find({
        'tenant_id': current_user.tenant_id,
        'status': 'pending'
    }).sort('created_at', -1):
        approval.pop('_id', None)
        # Check if urgent (more than 24 hours old or marked as urgent)
        created_at = approval.get('created_at')
        is_urgent = False
        if created_at:
            from datetime import datetime
            if isinstance(created_at, str):
                created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            else:
                created_dt = created_at
            hours_waiting = (datetime.now(UTC) - created_dt).total_seconds() / 3600
            is_urgent = hours_waiting > 24 or approval.get('priority') == 'urgent'
        if is_urgent:
            urgent_count += 1
        approvals.append(approval)

    return {
        'approvals': approvals,
        'count': len(approvals),
        'urgent_count': urgent_count
    }
# ── GET /approvals/my-requests ──
@router.get("/approvals/my-requests")
async def get_my_approval_requests(
    status: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get approval requests created by current user"""
    current_user = await get_current_user(credentials)

    query = {
        'tenant_id': current_user.tenant_id,
        'requested_by': current_user.id
    }

    if status:
        query['status'] = status

    requests = []
    async for approval in db.approval_requests.find(query).sort('created_at', -1):
        approval.pop('_id', None)
        requests.append(approval)

    return {
        'requests': requests,
        'count': len(requests)
    }
# ── POST /approvals/{approval_id}/approve ──
@router.post("/approvals/{approval_id}/approve")
async def approve_request(
    approval_id: str,
    approval_note: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_approvals")),  # v89 DW
):
    """Approve an approval request"""
    current_user = await get_current_user(credentials)

    # Only managers and admins can approve (super_admin always allowed)
    if not _is_super_admin(current_user) and current_user.role not in ['admin', 'manager', 'gm']:
        raise HTTPException(status_code=403, detail="Access denied")

    approval = await db.approval_requests.find_one({
        'id': approval_id,
        'tenant_id': current_user.tenant_id
    })

    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if approval['status'] != 'pending':
        raise HTTPException(status_code=400, detail="Request already processed")

    await db.approval_requests.update_one(
        {'id': approval_id},
        {
            '$set': {
                'status': 'approved',
                'approved_at': datetime.now(UTC).isoformat(),
                'approved_by': current_user.id,
                'approved_by_name': current_user.name,
                'approval_note': approval_note.get('note', '')
            }
        }
    )

    return {
        'message': 'Request approved',
        'approval_id': approval_id,
        'status': 'approved'
    }
# ── POST /approvals/{approval_id}/reject ──
@router.post("/approvals/{approval_id}/reject")
async def reject_request(
    approval_id: str,
    rejection_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_approvals")),  # v89 DW
):
    """Reject an approval request"""
    current_user = await get_current_user(credentials)

    # Only managers and admins can reject (super_admin always allowed)
    if not _is_super_admin(current_user) and current_user.role not in ['admin', 'manager', 'gm']:
        raise HTTPException(status_code=403, detail="Access denied")

    approval = await db.approval_requests.find_one({
        'id': approval_id,
        'tenant_id': current_user.tenant_id
    })

    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if approval['status'] != 'pending':
        raise HTTPException(status_code=400, detail="Request already processed")

    await db.approval_requests.update_one(
        {'id': approval_id},
        {
            '$set': {
                'status': 'rejected',
                'approved_at': datetime.now(UTC).isoformat(),
                'approved_by': current_user.id,
                'approved_by_name': current_user.name,
                'rejection_reason': rejection_data.get('reason', 'No reason provided')
            }
        }
    )

    return {
        'message': 'Request rejected',
        'approval_id': approval_id,
        'status': 'rejected'
    }
