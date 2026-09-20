"""
Night Audit — API Router (NA-001 / NA-002 Hardened)
Exposes hardened night audit execution, status, items, resume, abort,
plus legacy schedule management and financial reporting.
"""

import logging
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query

from cache_manager import cache as _cache
from cache_manager import cached
from common.context import OperationContext
from core.database import db
from core.security import get_current_user
from domains.pms.night_audit.schemas import NightAuditScheduleRequest, RunNightAuditRequest
from models.schemas import User
from modules.pms_core.role_permission_service import RolePermissionService, require_op  # v101 DW

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/night-audit", tags=["Night Audit Core"])

# Short-TTL cache for read-only finance dashboards. Mutations
# (run / resume / checkout / folio charge / payment / refund) call
# `invalidate_finance_cache` to bound staleness to <1s instead of 30s.
_FIN_CACHE_TTL = 30
_FIN_CACHE_PREFIXES = (
    "na_preview",
    "na_financial_summary",
    "na_payment_reconciliation",
    "na_integrity_check",
)


def _fin_cache_key(name: str, tenant_id: str, business_date: str) -> str:
    # Mirrors `cache:{tenant_id}:{entity_prefix}:{date}` so safe_invalidate
    # with the same entity_prefix can sweep all dates in one pattern.
    return f"cache:{tenant_id}:na_{name}:{business_date}"


def invalidate_finance_cache(tenant_id: str) -> None:
    """Drop all cached night-audit finance dashboards for a tenant.

    Uses `cache.safe_invalidate` (regex-validated tenant_id, glob-safe
    prefix) so we get observability metrics + defense-in-depth instead
    of raw `delete_pattern`. Best-effort: failures are logged by the
    cache layer; never raised to the request path.

    Exposed at module level so other routers (front-desk, folio) can
    call it after their own mutations without depending on the night
    audit router internals.
    """
    for prefix in _FIN_CACHE_PREFIXES:
        try:
            _cache.safe_invalidate(tenant_id, prefix)
        except Exception as e:  # pragma: no cover — best-effort
            logger.debug("finance cache invalidation skipped (%s): %s", prefix, e)


# Backwards-compat alias for in-file callers added before the rename.
_invalidate_finance_cache = invalidate_finance_cache


def _night_audit_operator_guard(user: User):
    """Enforce the narrowly scoped day-end operator permission.

    This guard remains inside handlers so direct service calls cannot bypass
    the route dependency.  It deliberately does not grant system settings or
    financial-report access to a night-shift receptionist.
    """
    if RolePermissionService().check_permission(
        user.role,
        "run_night_audit",
        granted_permissions=getattr(user, "granted_permissions", None),
    ):
        return
    raise HTTPException(status_code=403, detail="Night audit operator permission required")


def _admin_guard(user: User):
    """Keep schedule configuration restricted to administrators."""
    from core.security import _is_super_admin

    if _is_super_admin(user):
        return
    if user.role not in ("super_admin", "admin"):
        raise HTTPException(status_code=403, detail="Only admins can manage night audit schedule")


# ═══════════════════════════════════════════════════════════════
#  NA-001/NA-002: HARDENED ENDPOINTS
# ═══════════════════════════════════════════════════════════════


@router.post("/run")
async def run_night_audit(
    request: RunNightAuditRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("run_night_audit")),  # v101 DW
):
    """Start a hardened night audit run."""
    _night_audit_operator_guard(current_user)
    from core.business_date_service import ensure_business_date_initialized
    from core.night_audit_hardened import start_night_audit

    authoritative_bd = (await ensure_business_date_initialized(db, current_user.tenant_id))["business_date"]
    requested_bd = request.business_date or authoritative_bd
    if requested_bd != authoritative_bd:
        raise HTTPException(
            status_code=409,
            detail={
                "success": False,
                "code": "BUSINESS_DATE_MISMATCH",
                "error": (f"İstenen iş günü {request.business_date}, otelin açık iş günü {authoritative_bd} ile eşleşmiyor. Yenileyip tekrar deneyin."),
                "requested_business_date": request.business_date,
                "current_business_date": authoritative_bd,
            },
        )

    # A bypass must never turn an incomplete or same-day close into a financial
    # posting/date-roll operation.  Preview is the safe operational tool; a
    # blocked final close must be resolved or resumed through its run record.
    if request.skip_validations and not request.dry_run:
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "code": "UNSAFE_VALIDATION_BYPASS",
                "error": "Doğrulamalar yalnızca simülasyonda atlanabilir. Canlı gün sonu için engeller çözülmelidir.",
            },
        )
    if request.force_rerun and not request.dry_run:
        raise HTTPException(
            status_code=422,
            detail={
                "success": False,
                "code": "UNSAFE_RERUN",
                "error": "Tamamlanmış gün sonu tekrar çalıştırılamaz. Gerekliyse ilgili denetim kaydından kontrollü kurtarma işlemi başlatın.",
            },
        )

    # A final close is only valid after the property's local calendar has
    # moved past the open business date.  Closing today's date would advance
    # the PMS date prematurely, even when all validations were skipped.
    local_today = datetime.now(ZoneInfo("Europe/Istanbul")).date().isoformat()
    if not request.dry_run and authoritative_bd >= local_today:
        raise HTTPException(
            status_code=409,
            detail={
                "success": False,
                "code": "BUSINESS_DATE_NOT_READY",
                "error": (
                    f"Açık iş günü {authoritative_bd}. Bugünün günü kapanmadan canlı denetim çalıştırılamaz; "
                    "önce simülasyon kullanın veya yerel tarih bir sonraki güne geçtiğinde tekrar deneyin."
                ),
                "current_business_date": authoritative_bd,
                "local_calendar_date": local_today,
            },
        )

    result = await start_night_audit(
        tenant_id=current_user.tenant_id,
        property_id=request.property_id,
        business_date=request.business_date,
        trigger_source=request.trigger_source,
        actor={"id": current_user.id, "email": getattr(current_user, "email", "")},
        skip_validations=request.skip_validations,
        dry_run=request.dry_run,
        force_rerun=request.force_rerun,
        reason=request.reason,
    )
    if not result.get("success"):
        code = result.get("code", "UNKNOWN")
        status_code = {
            "ALREADY_COMPLETED": 409,
            "ALREADY_RUNNING": 409,
            "BLOCKED": 409,
            "NEEDS_RESUME": 409,
            "STALE_RECOVERED": 409,
            "VALIDATION_BLOCKED": 422,
        }.get(code, 400)
        raise HTTPException(status_code=status_code, detail=result)
    # Successful run mutates folio charges, payments, balances → drop dashboards.
    _invalidate_finance_cache(current_user.tenant_id)
    # History/business-date also change after a successful audit run.
    for prefix in ("na_history", "na_business_date"):
        try:
            _cache.safe_invalidate(current_user.tenant_id, prefix)
        except Exception as e:  # pragma: no cover
            logger.debug("na cache invalidation skipped (%s): %s", prefix, e)
    return result


@router.get("/status")
async def get_audit_status(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v102 DW finance leak fix
):
    """Get current night audit status for this tenant."""
    from core.night_audit_hardened import get_run_status

    return await get_run_status(current_user.tenant_id)


@router.get("/preview")
async def preview_night_audit(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
):
    """Gece denetimi Hazirlik ozeti — engelleyiciler, uyarilar, oda/misafir durumu."""
    from core.night_audit_hardened import build_audit_preview

    return await build_audit_preview(current_user.tenant_id)


@router.get("/runs")
async def list_runs(
    limit: int = Query(20, ge=1, le=100),
    skip: int = Query(0, ge=0),
    status: str = Query(None),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v102 DW finance leak fix
):
    """List night audit runs."""
    from core.night_audit_hardened import get_runs

    return await get_runs(current_user.tenant_id, limit, skip, status)


@router.get("/runs/{run_id}")
async def get_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v102 DW finance leak fix
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
    _perm=Depends(require_op("view_finance_reports")),  # v102 DW finance leak fix
):
    """List items for a specific run."""
    from core.night_audit_hardened import get_run_items

    return await get_run_items(current_user.tenant_id, run_id, status, limit, skip)


@router.post("/runs/{run_id}/resume")
async def resume_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("run_night_audit")),  # v101 DW
):
    """Resume a failed/blocked/partial run."""
    _night_audit_operator_guard(current_user)
    from core.night_audit_hardened import resume_night_audit

    result = await resume_night_audit(
        current_user.tenant_id,
        run_id,
        actor={"id": current_user.id, "email": getattr(current_user, "email", "")},
    )
    if not result.get("success"):
        code = result.get("code", "UNKNOWN")
        status_code = {
            "NOT_FOUND": 404,
            "INVALID_STATE": 409,
            "DRY_RUN_NOT_RESUMABLE": 409,
            "STILL_BLOCKED": 422,
        }.get(code, 400)
        raise HTTPException(status_code=status_code, detail=result)
    # Resume can finalize remaining steps → mutates folio/payment state.
    _invalidate_finance_cache(current_user.tenant_id)
    for prefix in ("na_history", "na_business_date"):
        try:
            _cache.safe_invalidate(current_user.tenant_id, prefix)
        except Exception as e:  # pragma: no cover
            logger.debug("na cache invalidation skipped (%s): %s", prefix, e)
    return result


@router.post("/runs/{run_id}/abort")
async def abort_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("run_night_audit")),  # v101 DW
):
    """Abort a running/blocked/partial run."""
    _night_audit_operator_guard(current_user)
    from core.night_audit_hardened import abort_night_audit

    result = await abort_night_audit(
        current_user.tenant_id,
        run_id,
        actor={"id": current_user.id, "email": getattr(current_user, "email", "")},
    )
    if not result.get("success"):
        code = result.get("code", "UNKNOWN")
        status_code = {"NOT_FOUND": 404, "ALREADY_COMPLETED": 409}.get(code, 400)
        raise HTTPException(status_code=status_code, detail=result)
    # Abort changes run status → invalidate history cache.
    try:
        _cache.safe_invalidate(current_user.tenant_id, "na_history")
    except Exception as e:  # pragma: no cover
        logger.debug("na_history cache invalidation skipped: %s", e)
    return result


# ═══════════════════════════════════════════════════════════════
#  LEGACY: Schedule & Financial Reporting
# ═══════════════════════════════════════════════════════════════


@router.get("/history")
@cached(ttl=60, key_prefix="na_history")
async def get_audit_history(
    limit: int = 20,
    skip: int = 0,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v102 DW finance leak fix
    _nocache: bool = Query(False, alias="nocache"),
):
    """Get night audit run history."""
    from domains.pms.night_audit.service import night_audit_core_service

    ctx = OperationContext.from_user(current_user)
    result = await night_audit_core_service.get_audit_history(ctx, limit, skip)
    return result.data


@router.get("/exceptions/{audit_id}")
async def get_audit_exceptions(
    audit_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v102 DW finance leak fix
):
    from domains.pms.night_audit.service import night_audit_core_service

    ctx = OperationContext.from_user(current_user)
    result = await night_audit_core_service.get_audit_exceptions(ctx, audit_id)
    return result.data


@router.get("/business-date")
@cached(ttl=60, key_prefix="na_business_date")
async def get_business_date(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v102 DW finance leak fix
    _nocache: bool = Query(False, alias="nocache"),
):
    from domains.pms.night_audit.service import night_audit_core_service

    ctx = OperationContext.from_user(current_user)
    result = await night_audit_core_service.get_business_date(ctx)
    return result.data


@router.get("/schedule")
@cached(ttl=300, key_prefix="na_schedule")
async def get_schedule(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v102 DW finance leak fix
    _nocache: bool = Query(False, alias="nocache"),
):
    from domains.pms.night_audit.service import night_audit_core_service

    ctx = OperationContext.from_user(current_user)
    result = await night_audit_core_service.get_schedule(ctx)
    return result.data


@router.put("/schedule")
async def update_schedule(
    request: NightAuditScheduleRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    _admin_guard(current_user)
    if request.skip_validations:
        raise HTTPException(
            status_code=422,
            detail="Zamanlanmış gün sonu doğrulamaları atlayamaz; bu ayarı kapatın.",
        )
    from domains.pms.night_audit.service import night_audit_core_service

    ctx = OperationContext.from_user(current_user)
    result = await night_audit_core_service.update_schedule(ctx, request.model_dump())
    # Invalidate schedule + status caches so next GET shows the new schedule.
    for prefix in ("na_schedule", "na_schedule_status"):
        try:
            _cache.safe_invalidate(current_user.tenant_id, prefix)
        except Exception as e:  # pragma: no cover
            logger.debug("schedule cache invalidation skipped (%s): %s", prefix, e)
    return result.data


@router.get("/schedule/status")
@cached(ttl=30, key_prefix="na_schedule_status")
async def get_schedule_status(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v102 DW finance leak fix
    _nocache: bool = Query(False, alias="nocache"),
):
    from domains.pms.night_audit.service import night_audit_core_service

    ctx = OperationContext.from_user(current_user)
    result = await night_audit_core_service.get_schedule_status(ctx)
    return result.data


@router.get("/financial-summary")
async def get_financial_summary(
    date: str = Query(None),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v102 DW finance leak fix
    _nocache: bool = Query(False, alias="nocache"),
):
    from domains.pms.night_audit.financial_service import financial_service
    from domains.pms.night_audit.service import night_audit_core_service

    ctx = OperationContext.from_user(current_user)
    if not date:
        bd_result = await night_audit_core_service.get_business_date(ctx)
        date = bd_result.data.get("business_date", datetime.now(UTC).date().isoformat())
    cache_key = _fin_cache_key("financial_summary", ctx.tenant_id, date)
    if not _nocache:
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached
    result = await financial_service.get_daily_financial_summary(ctx, date)
    payload = result.data
    _cache.set(cache_key, payload, ttl=_FIN_CACHE_TTL)
    return payload


@router.get("/payment-reconciliation")
async def get_payment_reconciliation(
    date: str = Query(None),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v102 DW finance leak fix
    _nocache: bool = Query(False, alias="nocache"),
):
    from domains.pms.night_audit.financial_service import financial_service
    from domains.pms.night_audit.service import night_audit_core_service

    ctx = OperationContext.from_user(current_user)
    if not date:
        bd_result = await night_audit_core_service.get_business_date(ctx)
        date = bd_result.data.get("business_date", datetime.now(UTC).date().isoformat())
    cache_key = _fin_cache_key("payment_reconciliation", ctx.tenant_id, date)
    if not _nocache:
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached
    result = await financial_service.get_payment_reconciliation(ctx, date)
    payload = result.data
    _cache.set(cache_key, payload, ttl=_FIN_CACHE_TTL)
    return payload


@router.get("/financial-report")
async def get_financial_report(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v102 DW finance leak fix
):
    # Tur 3: defaults — last 30 days when omitted
    from datetime import date as _d
    from datetime import timedelta as _td

    if not start_date:
        start_date = (_d.today() - _td(days=30)).isoformat()
    if not end_date:
        end_date = _d.today().isoformat()
    from domains.pms.night_audit.financial_service import financial_service

    ctx = OperationContext.from_user(current_user)
    result = await financial_service.get_financial_report(ctx, start_date, end_date)
    if not result.ok:
        raise HTTPException(status_code=400, detail=result.to_dict())
    return result.data


@router.get("/integrity-check")
async def get_integrity_check(
    date: str = Query(None),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v102 DW finance leak fix
    _nocache: bool = Query(False, alias="nocache"),
):
    from domains.pms.night_audit.financial_service import financial_service
    from domains.pms.night_audit.service import night_audit_core_service

    ctx = OperationContext.from_user(current_user)
    if not date:
        bd_result = await night_audit_core_service.get_business_date(ctx)
        date = bd_result.data.get("business_date", datetime.now(UTC).date().isoformat())
    cache_key = _fin_cache_key("integrity_check", ctx.tenant_id, date)
    if not _nocache:
        cached = _cache.get(cache_key)
        if cached is not None:
            return cached
    result = await financial_service.get_integrity_check(ctx, date)
    payload = result.data
    _cache.set(cache_key, payload, ttl=_FIN_CACHE_TTL)
    return payload
