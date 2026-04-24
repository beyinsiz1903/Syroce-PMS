"""
PMS / Approvals Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.database import db
from core.security import (
    get_current_user,
    security,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["PMS / Approvals"])


# ── Inline Models ──

from enum import Enum
from modules.pms_core.role_permission_service import require_op  # v89 DW


class ApprovalType(str, Enum):
    DISCOUNT = "discount"
    PRICE_OVERRIDE = "price_override"
    BUDGET_EXPENSE = "budget_expense"
    RATE_CHANGE = "rate_change"
    REFUND = "refund"
    COMP_ROOM = "comp_room"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class CreateApprovalRequest(BaseModel):
    approval_type: ApprovalType
    reference_id: str | None = None  # booking_id, folio_id, etc.
    amount: float
    original_value: float | None = None
    new_value: float | None = None
    reason: str
    notes: str | None = None
    priority: str = "normal"  # low, normal, high, urgent


class ApprovalActionRequest(BaseModel):
    notes: str | None = None
    rejection_reason: str | None = None


class BudgetMonth(BaseModel):
    month: int
    occ_target: float = 0
    adr_target: float = 0
    rev_target: float = 0


class BudgetConfig(BaseModel):
    year: int
    currency: str = "TRY"
    months: list[BudgetMonth]


@router.post("/approvals/create")
async def create_approval_request(
    request: CreateApprovalRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_approvals")),  # v92 DW
):
    """
    Create a new approval request
    Types: discount, price_override, budget_expense, rate_change, refund, comp_room
    """
    current_user = await get_current_user(credentials)

    approval = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'approval_type': request.approval_type.value,
        'reference_id': request.reference_id,
        'amount': request.amount,
        'original_value': request.original_value,
        'new_value': request.new_value,
        'reason': request.reason,
        'notes': request.notes,
        'priority': request.priority,
        'status': ApprovalStatus.PENDING.value,
        'requested_by': current_user.name,
        'requested_by_id': current_user.id,
        'requested_by_role': current_user.role,
        'request_date': datetime.now(UTC).isoformat(),
        'approved_by': None,
        'approval_date': None,
        'rejection_reason': None,
        'created_at': datetime.now(UTC).isoformat()
    }

    await db.approvals.insert_one(approval)

    return {
        'message': 'Approval request created',
        'approval_id': approval['id'],
        'status': approval['status'],
        'approval_type': approval['approval_type']
    }


# 2. GET /api/approvals/pending - Get pending approvals


@router.get("/approvals/pending")
@router.get("/approvals/my-requests")
@router.put("/approvals/{approval_id}/approve")
async def approve_request(
    approval_id: str,
    request: ApprovalActionRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_approvals")),  # v92 DW
):
    """
    Approve an approval request
    Only managers and supervisors can approve
    """
    current_user = await get_current_user(credentials)

    # Check permissions - only certain roles can approve
    allowed_roles = ['admin', 'supervisor', 'fnb_manager', 'gm', 'finance_manager']
    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions. Only managers can approve requests."
        )

    # Get approval
    approval = await db.approvals.find_one({
        'id': approval_id,
        'tenant_id': current_user.tenant_id
    })

    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if approval['status'] != ApprovalStatus.PENDING.value:
        raise HTTPException(status_code=400, detail=f"Cannot approve. Request is already {approval['status']}")

    # Update approval
    await db.approvals.update_one(
        {'id': approval_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'status': ApprovalStatus.APPROVED.value,
                'approved_by': current_user.name,
                'approved_by_id': current_user.id,
                'approved_by_role': current_user.role,
                'approval_date': datetime.now(UTC).isoformat(),
                'approval_notes': request.notes
            }
        }
    )

    # Create notification for requester
    notification = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'user_id': approval['requested_by_id'],
        'type': 'approval_approved',
        'title': 'Approval Request Approved',
        'message': f"{approval['approval_type']} approval request has been approved",
        'priority': 'normal',
        'read': False,
        'created_at': datetime.now(UTC).isoformat()
    }
    await db.notifications.insert_one(notification)

    return {
        'message': 'Approval request approved',
        'approval_id': approval_id,
        'approved_by': current_user.name,
        'approval_date': datetime.now(UTC).isoformat()
    }


# 5. PUT /api/approvals/{approval_id}/reject - Reject request


@router.get("/approvals/my-requests")
@router.put("/approvals/{approval_id}/approve")
async def approve_request_v2(
    approval_id: str,
    request: ApprovalActionRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_approvals")),  # v89 DW
):
    """
    Approve an approval request
    Only managers and supervisors can approve
    """
    current_user = await get_current_user(credentials)

    # Check permissions - only certain roles can approve
    allowed_roles = ['admin', 'supervisor', 'fnb_manager', 'gm', 'finance_manager']
    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions. Only managers can approve requests."
        )

    # Get approval
    approval = await db.approvals.find_one({
        'id': approval_id,
        'tenant_id': current_user.tenant_id
    })

    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if approval['status'] != ApprovalStatus.PENDING.value:
        raise HTTPException(status_code=400, detail=f"Cannot approve. Request is already {approval['status']}")

    # Update approval
    await db.approvals.update_one(
        {'id': approval_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'status': ApprovalStatus.APPROVED.value,
                'approved_by': current_user.name,
                'approved_by_id': current_user.id,
                'approved_by_role': current_user.role,
                'approval_date': datetime.now(UTC).isoformat(),
                'approval_notes': request.notes
            }
        }
    )

    # Create notification for requester
    notification = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'user_id': approval['requested_by_id'],
        'type': 'approval_approved',
        'title': 'Approval Request Approved',
        'message': f"{approval['approval_type']} approval request has been approved",
        'priority': 'normal',
        'read': False,
        'created_at': datetime.now(UTC).isoformat()
    }
    await db.notifications.insert_one(notification)

    return {
        'message': 'Approval request approved',
        'approval_id': approval_id,
        'approved_by': current_user.name,
        'approval_date': datetime.now(UTC).isoformat()
    }


# 5. PUT /api/approvals/{approval_id}/reject - Reject request


@router.put("/approvals/{approval_id}/approve")
async def approve_request_v3(
    approval_id: str,
    request: ApprovalActionRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_approvals")),  # v89 DW
):
    """
    Approve an approval request
    Only managers and supervisors can approve
    """
    current_user = await get_current_user(credentials)

    # Check permissions - only certain roles can approve
    allowed_roles = ['admin', 'supervisor', 'fnb_manager', 'gm', 'finance_manager']
    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions. Only managers can approve requests."
        )

    # Get approval
    approval = await db.approvals.find_one({
        'id': approval_id,
        'tenant_id': current_user.tenant_id
    })

    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if approval['status'] != ApprovalStatus.PENDING.value:
        raise HTTPException(status_code=400, detail=f"Cannot approve. Request is already {approval['status']}")

    # Update approval
    await db.approvals.update_one(
        {'id': approval_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'status': ApprovalStatus.APPROVED.value,
                'approved_by': current_user.name,
                'approved_by_id': current_user.id,
                'approved_by_role': current_user.role,
                'approval_date': datetime.now(UTC).isoformat(),
                'approval_notes': request.notes
            }
        }
    )

    # Create notification for requester
    notification = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'user_id': approval['requested_by_id'],
        'type': 'approval_approved',
        'title': 'Approval Request Approved',
        'message': f"{approval['approval_type']} approval request has been approved",
        'priority': 'normal',
        'read': False,
        'created_at': datetime.now(UTC).isoformat()
    }
    await db.notifications.insert_one(notification)

    return {
        'message': 'Approval request approved',
        'approval_id': approval_id,
        'approved_by': current_user.name,
        'approval_date': datetime.now(UTC).isoformat()
    }


# 5. PUT /api/approvals/{approval_id}/reject - Reject request


@router.put("/approvals/{approval_id}/reject")
async def reject_request(
    approval_id: str,
    request: ApprovalActionRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_approvals")),  # v89 DW
):
    """
    Reject an approval request
    Only managers and supervisors can reject
    """
    current_user = await get_current_user(credentials)

    # Check permissions
    allowed_roles = ['admin', 'supervisor', 'fnb_manager', 'gm', 'finance_manager']
    if current_user.role not in allowed_roles:
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions. Only managers can reject requests."
        )

    if not request.rejection_reason:
        raise HTTPException(status_code=400, detail="Rejection reason is required")

    # Get approval
    approval = await db.approvals.find_one({
        'id': approval_id,
        'tenant_id': current_user.tenant_id
    })

    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")

    if approval['status'] != ApprovalStatus.PENDING.value:
        raise HTTPException(status_code=400, detail=f"Cannot reject. Request is already {approval['status']}")

    # Update approval
    await db.approvals.update_one(
        {'id': approval_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'status': ApprovalStatus.REJECTED.value,
                'approved_by': current_user.name,
                'approved_by_id': current_user.id,
                'approved_by_role': current_user.role,
                'approval_date': datetime.now(UTC).isoformat(),
                'rejection_reason': request.rejection_reason,
                'approval_notes': request.notes
            }
        }
    )

    # Create notification for requester
    notification = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'user_id': approval['requested_by_id'],
        'type': 'approval_rejected',
        'title': 'Approval Request Rejected',
        'message': f"{approval['approval_type']} approval request has been rejected: {request.rejection_reason}",
        'priority': 'high',
        'read': False,
        'created_at': datetime.now(UTC).isoformat()
    }
    await db.notifications.insert_one(notification)

    return {
        'message': 'Approval request rejected',
        'approval_id': approval_id,
        'rejected_by': current_user.name,
        'rejection_reason': request.rejection_reason
    }


# 6. GET /api/approvals/history - Get approval history


@router.get("/approvals/history")
async def get_approval_history(
    status: str | None = None,
    approval_type: str | None = None,
    limit: int = 50,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get approval history
    Filter by status and approval_type
    """
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}

    if status:
        query['status'] = status

    if approval_type:
        query['approval_type'] = approval_type

    approvals = []
    async for approval in db.approvals.find(query).sort('request_date', -1).limit(limit):
        approvals.append({
            'id': approval['id'],
            'approval_type': approval['approval_type'],
            'amount': approval['amount'],
            'reason': approval['reason'],
            'status': approval['status'],
            'requested_by': approval['requested_by'],
            'request_date': approval['request_date'],
            'approved_by': approval.get('approved_by'),
            'approval_date': approval.get('approval_date'),
            'rejection_reason': approval.get('rejection_reason')
        })

    return {
        'history': approvals,
        'count': len(approvals)
    }

