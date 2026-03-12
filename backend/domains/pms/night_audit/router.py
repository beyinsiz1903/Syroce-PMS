"""
Night Audit — API Router (Production-Grade)
Exposes night audit execution, history, exceptions, and business date.
"""
from fastapi import APIRouter, Depends, HTTPException
import logging

from core.security import get_current_user
from models.schemas import User
from common.context import OperationContext
from domains.pms.night_audit.schemas import RunNightAuditRequest
from domains.pms.night_audit.service import night_audit_core_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/night-audit", tags=["Night Audit Core"])


@router.post("/run")
async def run_night_audit(
    request: RunNightAuditRequest,
    current_user: User = Depends(get_current_user),
):
    """Execute night audit for given business date."""
    if current_user.role not in ("super_admin", "admin"):
        raise HTTPException(status_code=403, detail="Only admins can run night audit")

    ctx = OperationContext.from_user(current_user)
    result = await night_audit_core_service.run_night_audit(
        ctx,
        business_date=request.business_date,
        force_rerun=request.force_rerun,
        skip_validations=request.skip_validations,
        dry_run=request.dry_run,
        reason=request.reason,
    )
    if not result.ok:
        status_code = 409 if result.code in ("ALREADY_COMPLETED", "CONCURRENT_LOCK") else 400
        raise HTTPException(status_code=status_code, detail=result.to_dict())
    return result.data


@router.get("/history")
async def get_audit_history(
    limit: int = 20,
    skip: int = 0,
    current_user: User = Depends(get_current_user),
):
    """Get night audit run history."""
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_core_service.get_audit_history(ctx, limit, skip)
    return result.data


@router.get("/exceptions/{audit_id}")
async def get_audit_exceptions(
    audit_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get exceptions for a specific night audit run."""
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_core_service.get_audit_exceptions(ctx, audit_id)
    return result.data


@router.get("/business-date")
async def get_business_date(
    current_user: User = Depends(get_current_user),
):
    """Get current business date for tenant."""
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_core_service.get_business_date(ctx)
    return result.data
