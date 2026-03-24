"""
PMS / Approvals Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timezone
import uuid
import logging

from core.database import db
from core.security import (
    get_current_user, security,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["PMS / Approvals"])


# ── Inline Models ──

from enum import Enum

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
    reference_id: Optional[str] = None  # booking_id, folio_id, etc.
    amount: float
    original_value: Optional[float] = None
    new_value: Optional[float] = None
    reason: str
    notes: Optional[str] = None
    priority: str = "normal"  # low, normal, high, urgent


class ApprovalActionRequest(BaseModel):
    notes: Optional[str] = None
    rejection_reason: Optional[str] = None


class BudgetMonth(BaseModel):
    month: int
    occ_target: float = 0
    adr_target: float = 0
    rev_target: float = 0


class BudgetConfig(BaseModel):
    year: int
    currency: str = "TRY"
    months: List[BudgetMonth]


@router.post("/approvals/create")
async def create_approval_request(
    request: CreateApprovalRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
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
        'request_date': datetime.now(timezone.utc).isoformat(),
        'approved_by': None,
        'approval_date': None,
        'rejection_reason': None,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    
    await db.approvals.insert_one(approval)
    
    return {
        'message': 'Onay isteği oluşturuldu',
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
    credentials: HTTPAuthorizationCredentials = Depends(security)
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
                'approval_date': datetime.now(timezone.utc).isoformat(),
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
        'title': 'Onay İsteği Onaylandı',
        'message': f"{approval['approval_type']} türünde onay isteğiniz onaylandı",
        'priority': 'normal',
        'read': False,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    await db.notifications.insert_one(notification)
    
    return {
        'message': 'Onay isteği onaylandı',
        'approval_id': approval_id,
        'approved_by': current_user.name,
        'approval_date': datetime.now(timezone.utc).isoformat()
    }


# 5. PUT /api/approvals/{approval_id}/reject - Reject request


@router.get("/approvals/my-requests")
@router.put("/approvals/{approval_id}/approve")
async def approve_request_v2(
    approval_id: str,
    request: ApprovalActionRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
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
                'approval_date': datetime.now(timezone.utc).isoformat(),
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
        'title': 'Onay İsteği Onaylandı',
        'message': f"{approval['approval_type']} türünde onay isteğiniz onaylandı",
        'priority': 'normal',
        'read': False,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    await db.notifications.insert_one(notification)
    
    return {
        'message': 'Onay isteği onaylandı',
        'approval_id': approval_id,
        'approved_by': current_user.name,
        'approval_date': datetime.now(timezone.utc).isoformat()
    }


# 5. PUT /api/approvals/{approval_id}/reject - Reject request


@router.put("/approvals/{approval_id}/approve")
async def approve_request_v3(
    approval_id: str,
    request: ApprovalActionRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
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
                'approval_date': datetime.now(timezone.utc).isoformat(),
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
        'title': 'Onay İsteği Onaylandı',
        'message': f"{approval['approval_type']} türünde onay isteğiniz onaylandı",
        'priority': 'normal',
        'read': False,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    await db.notifications.insert_one(notification)
    
    return {
        'message': 'Onay isteği onaylandı',
        'approval_id': approval_id,
        'approved_by': current_user.name,
        'approval_date': datetime.now(timezone.utc).isoformat()
    }


# 5. PUT /api/approvals/{approval_id}/reject - Reject request


@router.put("/approvals/{approval_id}/reject")
async def reject_request(
    approval_id: str,
    request: ApprovalActionRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
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
                'approval_date': datetime.now(timezone.utc).isoformat(),
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
        'title': 'Onay İsteği Reddedildi',
        'message': f"{approval['approval_type']} türünde onay isteğiniz reddedildi: {request.rejection_reason}",
        'priority': 'high',
        'read': False,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    await db.notifications.insert_one(notification)
    
    return {
        'message': 'Onay isteği reddedildi',
        'approval_id': approval_id,
        'rejected_by': current_user.name,
        'rejection_reason': request.rejection_reason
    }


# 6. GET /api/approvals/history - Get approval history


@router.get("/approvals/history")
async def get_approval_history(
    status: Optional[str] = None,
    approval_type: Optional[str] = None,
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

