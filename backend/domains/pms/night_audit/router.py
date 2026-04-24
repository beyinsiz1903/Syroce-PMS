"""
Night Audit — API Router (NA-001 / NA-002 Hardened)
Exposes hardened night audit execution, status, items, resume, abort,
plus legacy schedule management and financial reporting.
"""
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query

from common.context import OperationContext
from core.security import get_current_user
from domains.pms.night_audit.schemas import NightAuditScheduleRequest, RunNightAuditRequest
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v101 DW

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/night-audit", tags=["Night Audit Core"])


def _admin_guard(user: User):
    if user.role not in ("super_admin", "admin"):
        raise HTTPException(status_code=403, detail="Only admins can manage night audit")


# ═══════════════════════════════════════════════════════════════
#  NA-001/NA-002: HARDENED ENDPOINTS
# ═══════════════════════════════════════════════════════════════

@router.post("/run")
async def run_night_audit(request: RunNightAuditRequest, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("run_night_audit")),  # v101 DW
):
    """Start a hardened night audit run."""
    _admin_guard(current_user)
    from core.night_audit_hardened import start_night_audit

    result = await start_night_audit(
        tenant_id=current_user.tenant_id,
        property_id=request.property_id,
        business_date=request.business_date,
        trigger_source=request.trigger_source,
        actor={"id": current_user.id, "email": getattr(current_user, "email", "")},
    )
    if not result.get("success"):
        code = result.get("code", "UNKNOWN")
        status_code = {
            "ALREADY_COMPLETED": 409, "ALREADY_RUNNING": 409,
            "BLOCKED": 409, "NEEDS_RESUME": 409,
            "STALE_RECOVERED": 409, "VALIDATION_BLOCKED": 422,
        }.get(code, 400)
        raise HTTPException(status_code=status_code, detail=result)
    return result


@router.get("/status")
async def get_audit_status(current_user: User = Depends(get_current_user),
_perm=Depends(require_op("view_finance_reports"))  # v102 DW finance leak fix
):
    """Get current night audit status for this tenant."""
    from core.night_audit_hardened import get_run_status
    return await get_run_status(current_user.tenant_id)


@router.get("/runs")
async def list_runs(
    limit: int = Query(20, ge=1, le=100),
    skip: int = Query(0, ge=0),
    status: str = Query(None),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports"))  # v102 DW finance leak fix
):
    """List night audit runs."""
    from core.night_audit_hardened import get_runs
    return await get_runs(current_user.tenant_id, limit, skip, status)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, current_user: User = Depends(get_current_user),
_perm=Depends(require_op("view_finance_reports"))  # v102 DW finance leak fix
):
    """Get a specific run by ID."""
    from core.night_audit_hardened import get_run_detail
    run = await get_run_detail(current_user.tenant_id, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/runs/{run_id}/items")
async def get_items(
    run_id: str,
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0),
    status: str = Query(None),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports"))  # v102 DW finance leak fix
):
    """List items for a specific run."""
    from core.night_audit_hardened import get_run_items
    return await get_run_items(current_user.tenant_id, run_id, status, limit, skip)


@router.post("/runs/{run_id}/resume")
async def resume_run(run_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("run_night_audit")),  # v101 DW
):
    """Resume a failed/blocked/partial run."""
    _admin_guard(current_user)
    from core.night_audit_hardened import resume_night_audit
    result = await resume_night_audit(
        current_user.tenant_id, run_id,
        actor={"id": current_user.id, "email": getattr(current_user, "email", "")},
    )
    if not result.get("success"):
        code = result.get("code", "UNKNOWN")
        status_code = {"NOT_FOUND": 404, "INVALID_STATE": 409, "STILL_BLOCKED": 422}.get(code, 400)
        raise HTTPException(status_code=status_code, detail=result)
    return result


@router.post("/runs/{run_id}/abort")
async def abort_run(run_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("run_night_audit")),  # v101 DW
):
    """Abort a running/blocked/partial run."""
    _admin_guard(current_user)
    from core.night_audit_hardened import abort_night_audit
    result = await abort_night_audit(
        current_user.tenant_id, run_id,
        actor={"id": current_user.id, "email": getattr(current_user, "email", "")},
    )
    if not result.get("success"):
        code = result.get("code", "UNKNOWN")
        status_code = {"NOT_FOUND": 404, "ALREADY_COMPLETED": 409}.get(code, 400)
        raise HTTPException(status_code=status_code, detail=result)
    return result


# ═══════════════════════════════════════════════════════════════
#  LEGACY: Schedule & Financial Reporting
# ═══════════════════════════════════════════════════════════════

@router.get("/history")
async def get_audit_history(limit: int = 20, skip: int = 0, current_user: User = Depends(get_current_user),
_perm=Depends(require_op("view_finance_reports"))  # v102 DW finance leak fix
):
    """Get night audit run history."""
    from domains.pms.night_audit.service import night_audit_core_service
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_core_service.get_audit_history(ctx, limit, skip)
    return result.data


@router.get("/exceptions/{audit_id}")
async def get_audit_exceptions(audit_id: str, current_user: User = Depends(get_current_user),
_perm=Depends(require_op("view_finance_reports"))  # v102 DW finance leak fix
):
    from domains.pms.night_audit.service import night_audit_core_service
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_core_service.get_audit_exceptions(ctx, audit_id)
    return result.data


@router.get("/business-date")
async def get_business_date(current_user: User = Depends(get_current_user),
_perm=Depends(require_op("view_finance_reports"))  # v102 DW finance leak fix
):
    from domains.pms.night_audit.service import night_audit_core_service
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_core_service.get_business_date(ctx)
    return result.data


@router.get("/schedule")
async def get_schedule(current_user: User = Depends(get_current_user),
_perm=Depends(require_op("view_finance_reports"))  # v102 DW finance leak fix
):
    from domains.pms.night_audit.service import night_audit_core_service
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_core_service.get_schedule(ctx)
    return result.data


@router.put("/schedule")
async def update_schedule(request: NightAuditScheduleRequest, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    _admin_guard(current_user)
    from domains.pms.night_audit.service import night_audit_core_service
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_core_service.update_schedule(ctx, request.model_dump())
    return result.data


@router.get("/schedule/status")
async def get_schedule_status(current_user: User = Depends(get_current_user),
_perm=Depends(require_op("view_finance_reports"))  # v102 DW finance leak fix
):
    from domains.pms.night_audit.service import night_audit_core_service
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_core_service.get_schedule_status(ctx)
    return result.data


@router.get("/financial-summary")
async def get_financial_summary(date: str = Query(None), current_user: User = Depends(get_current_user),
_perm=Depends(require_op("view_finance_reports"))  # v102 DW finance leak fix
):
    from domains.pms.night_audit.financial_service import financial_service
    from domains.pms.night_audit.service import night_audit_core_service
    ctx = OperationContext.from_user(current_user)
    if not date:
        bd_result = await night_audit_core_service.get_business_date(ctx)
        date = bd_result.data.get("business_date", datetime.now(UTC).date().isoformat())
    result = await financial_service.get_daily_financial_summary(ctx, date)
    return result.data


@router.get("/payment-reconciliation")
async def get_payment_reconciliation(date: str = Query(None), current_user: User = Depends(get_current_user),
_perm=Depends(require_op("view_finance_reports"))  # v102 DW finance leak fix
):
    from domains.pms.night_audit.financial_service import financial_service
    from domains.pms.night_audit.service import night_audit_core_service
    ctx = OperationContext.from_user(current_user)
    if not date:
        bd_result = await night_audit_core_service.get_business_date(ctx)
        date = bd_result.data.get("business_date", datetime.now(UTC).date().isoformat())
    result = await financial_service.get_payment_reconciliation(ctx, date)
    return result.data


@router.get("/financial-report")
async def get_financial_report(
    start_date: str = Query(...), end_date: str = Query(...),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports"))  # v102 DW finance leak fix
):
    from domains.pms.night_audit.financial_service import financial_service
    ctx = OperationContext.from_user(current_user)
    result = await financial_service.get_financial_report(ctx, start_date, end_date)
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.to_dict())
    return result.data


@router.get("/integrity-check")
async def get_integrity_check(date: str = Query(None), current_user: User = Depends(get_current_user),
_perm=Depends(require_op("view_finance_reports"))  # v102 DW finance leak fix
):
    from domains.pms.night_audit.financial_service import financial_service
    from domains.pms.night_audit.service import night_audit_core_service
    ctx = OperationContext.from_user(current_user)
    if not date:
        bd_result = await night_audit_core_service.get_business_date(ctx)
        date = bd_result.data.get("business_date", datetime.now(UTC).date().isoformat())
    result = await financial_service.get_integrity_check(ctx, date)
    return result.data
