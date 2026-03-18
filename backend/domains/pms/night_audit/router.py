"""
Night Audit — API Router (Production-Grade)
Exposes night audit execution, history, exceptions, business date, and financial reporting.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
import logging
from datetime import datetime, timezone

from core.security import get_current_user
from models.schemas import User
from common.context import OperationContext
from domains.pms.night_audit.schemas import RunNightAuditRequest, NightAuditScheduleRequest
from domains.pms.night_audit.service import night_audit_core_service
from domains.pms.night_audit.financial_service import financial_service

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


@router.get("/schedule")
async def get_schedule(
    current_user: User = Depends(get_current_user),
):
    """Get night audit schedule configuration."""
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_core_service.get_schedule(ctx)
    return result.data


@router.put("/schedule")
async def update_schedule(
    request: NightAuditScheduleRequest,
    current_user: User = Depends(get_current_user),
):
    """Update night audit schedule configuration."""
    if current_user.role not in ("super_admin", "admin"):
        raise HTTPException(status_code=403, detail="Only admins can update schedule")
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_core_service.update_schedule(ctx, request.model_dump())
    return result.data


@router.get("/schedule/status")
async def get_schedule_status(
    current_user: User = Depends(get_current_user),
):
    """Get scheduler status and recent auto-run logs."""
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_core_service.get_schedule_status(ctx)
    return result.data


# ── Financial Reporting Endpoints ──────────────────────────────────────

@router.get("/financial-summary")
async def get_financial_summary(
    date: str = Query(None, description="Business date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
):
    """Get daily financial summary for a business date."""
    ctx = OperationContext.from_user(current_user)
    if not date:
        bd_result = await night_audit_core_service.get_business_date(ctx)
        date = bd_result.data.get("business_date", datetime.now(timezone.utc).date().isoformat())
    result = await financial_service.get_daily_financial_summary(ctx, date)
    return result.data


@router.get("/payment-reconciliation")
async def get_payment_reconciliation(
    date: str = Query(None, description="Business date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
):
    """Reconcile charges vs payments for a business date."""
    ctx = OperationContext.from_user(current_user)
    if not date:
        bd_result = await night_audit_core_service.get_business_date(ctx)
        date = bd_result.data.get("business_date", datetime.now(timezone.utc).date().isoformat())
    result = await financial_service.get_payment_reconciliation(ctx, date)
    return result.data


@router.get("/financial-report")
async def get_financial_report(
    start_date: str = Query(..., description="Start date (YYYY-MM-DD)"),
    end_date: str = Query(..., description="End date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
):
    """Generate financial report for a date range."""
    ctx = OperationContext.from_user(current_user)
    result = await financial_service.get_financial_report(ctx, start_date, end_date)
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.to_dict())
    return result.data


@router.get("/integrity-check")
async def get_integrity_check(
    date: str = Query(None, description="Business date (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
):
    """Run financial integrity checks for a business date."""
    ctx = OperationContext.from_user(current_user)
    if not date:
        bd_result = await night_audit_core_service.get_business_date(ctx)
        date = bd_result.data.get("business_date", datetime.now(timezone.utc).date().isoformat())
    result = await financial_service.get_integrity_check(ctx, date)
    return result.data
