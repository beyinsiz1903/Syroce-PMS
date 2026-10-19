"""
PMS / Night Audit Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
+ Opera #8: Trial Balance / Daily Operations Resume — gece auditi sonrası tek özet rapor
"""

import logging
from decimal import InvalidOperation

from fastapi import APIRouter, Depends, HTTPException

from common.context import OperationContext
from core.business_date_service import ensure_business_date_initialized
from core.security import (
    get_current_user,
)
from core.tenant_db import get_system_db
from domains.pms.night_audit_service import night_audit_service
from models.schemas import User
from modules.pms_core.daily_reconciliation import build_daily_reconciliation, daily_revenue_summary
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.stay_night_metrics import as_date

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


router = APIRouter(prefix="/api", tags=["PMS / Night Audit"])


@router.get("/audit-logs")
@cached(ttl=600, key_prefix="audit_logs")
async def get_audit_logs(
    entity_type: str | None = None,
    entity_id: str | None = None,
    user_id: str | None = None,
    action: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v86 DV: audit log admin/exec
):
    """Get audit logs with filters"""
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_service.get_audit_logs(ctx, entity_type, entity_id, user_id, action, start_date, end_date, limit)
    if not result.ok:
        raise HTTPException(status_code=403, detail=result.error)
    return result.data


@router.get("/logs/errors")
async def get_error_logs(
    start_date: str | None = None,
    end_date: str | None = None,
    severity: str | None = None,
    endpoint: str | None = None,
    resolved: bool | None = None,
    limit: int = 100,
    skip: int = 0,
    current_user: User = Depends(get_current_user),
):
    """Get error logs with filtering"""
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_service.get_error_logs(ctx, start_date, end_date, severity, endpoint, resolved, limit, skip)
    return result.data


@router.post("/logs/errors/{error_id}/resolve")
async def resolve_error_log(
    error_id: str,
    resolution_notes: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """Mark error log as resolved"""
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_service.resolve_error_log(ctx, error_id, resolution_notes)
    if not result.ok:
        raise HTTPException(status_code=404, detail=result.error)
    return result.data


@router.get("/logs/night-audit")
async def get_night_audit_logs(start_date: str | None = None, end_date: str | None = None, status: str | None = None, limit: int = 100, skip: int = 0, current_user: User = Depends(get_current_user)):
    """Get night audit logs"""
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_service.get_night_audit_logs(ctx, start_date, end_date, status, limit, skip)
    return result.data


@router.get("/logs/ota-sync")
async def get_ota_sync_logs(
    start_date: str | None = None,
    end_date: str | None = None,
    channel: str | None = None,
    sync_type: str | None = None,
    status: str | None = None,
    limit: int = 100,
    skip: int = 0,
    current_user: User = Depends(get_current_user),
):
    """Get OTA sync logs"""
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_service.get_ota_sync_logs(ctx, start_date, end_date, channel, sync_type, status, limit, skip)
    return result.data


@router.get("/logs/rms-publish")
async def get_rms_publish_logs(
    start_date: str | None = None,
    end_date: str | None = None,
    publish_type: str | None = None,
    auto_published: bool | None = None,
    status: str | None = None,
    limit: int = 100,
    skip: int = 0,
    current_user: User = Depends(get_current_user),
):
    """Get RMS publish logs"""
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_service.get_rms_publish_logs(ctx, start_date, end_date, publish_type, auto_published, status, limit, skip)
    return result.data


@router.get("/logs/maintenance-predictions")
async def get_maintenance_prediction_logs(
    start_date: str | None = None,
    end_date: str | None = None,
    equipment_type: str | None = None,
    prediction_result: str | None = None,
    room_number: str | None = None,
    limit: int = 100,
    skip: int = 0,
    current_user: User = Depends(get_current_user),
):
    """Get maintenance prediction logs"""
    ctx = OperationContext.from_user(current_user)
    result = await night_audit_service.get_maintenance_prediction_logs(ctx, start_date, end_date, equipment_type, prediction_result, room_number, limit, skip)
    return result.data


# ─────────────────────────────────────────────────────────────────────────────
# Opera #8 — Trial Balance / Daily Operations Resume
# Gece auditi sonrası: gelir, ödemeler, doluluk, ADR/RevPAR, AR, depozito,
# açık folio'lar — tek bir özet ekran.
# ─────────────────────────────────────────────────────────────────────────────


def _daily_revenue_summary(metric_rows, charges_by_cat):
    """Compatibility entry point for the shared currency-preserving summary."""
    return daily_revenue_summary(metric_rows, charges_by_cat)


@router.get("/trial-balance")
async def trial_balance(
    date: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),
):
    """Selected PMS-day activity plus explicitly current open-ledger positions."""
    database = get_system_db()
    state = await ensure_business_date_initialized(database, current_user.tenant_id)
    target = as_date(date if date is not None else state["business_date"])
    if target is None or (date is not None and date != target.isoformat()):
        raise HTTPException(status_code=422, detail="Tarih formatı YYYY-MM-DD olmalı")
    try:
        return await build_daily_reconciliation(database, current_user.tenant_id, target)
    except (ValueError, TypeError, InvalidOperation) as exc:
        logger.exception("Invalid financial source for daily reconciliation tenant=%s", current_user.tenant_id)
        raise HTTPException(status_code=503, detail="Kaynak finansal kayıt doğrulanamadı; mutabakat raporu oluşturulamadı") from exc
