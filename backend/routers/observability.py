"""
Observability Router — metrics, tracing, errors, and health endpoints.
"""
from fastapi import APIRouter, Depends, Query
from modules.pms_core.role_permission_service import require_op  # v98 DW

from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/observability", tags=["observability"])


# ── Metrics ──

@router.get("/metrics")
async def get_metrics(current_user: User = Depends(get_current_user)):
    from modules.observability.metrics_collector import metrics
    return metrics.get_dashboard_metrics()


@router.get("/metrics/all")
async def get_all_metrics(current_user: User = Depends(get_current_user)):
    from modules.observability.metrics_collector import metrics
    return metrics.get_all_metrics()


@router.post("/metrics/flush")
async def flush_metrics(current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    from modules.observability.metrics_collector import metrics
    count = await metrics.flush_to_db()
    return {"flushed": count}


# ── Traces ──

@router.get("/traces/summary")
async def get_trace_summary(hours: int = Query(1, ge=1, le=24),
                            current_user: User = Depends(get_current_user)):
    from modules.observability.distributed_tracing import tracing
    return await tracing.get_trace_summary(hours)


@router.get("/traces")
async def get_recent_traces(limit: int = Query(20, le=100),
                            slow_only: bool = False,
                            current_user: User = Depends(get_current_user)):
    from modules.observability.distributed_tracing import tracing
    return await tracing.get_recent_traces(limit, slow_only)


@router.get("/traces/slow")
async def get_slow_endpoints(threshold_ms: float = Query(1000),
                             current_user: User = Depends(get_current_user)):
    from modules.observability.distributed_tracing import tracing
    return await tracing.get_slow_endpoints(threshold_ms)


@router.get("/traces/hot-paths")
async def get_hot_paths(top_n: int = Query(10, le=50),
                        current_user: User = Depends(get_current_user)):
    from modules.observability.distributed_tracing import tracing
    return await tracing.get_hot_paths(top_n)


@router.post("/traces/flush")
async def flush_traces(current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    from modules.observability.distributed_tracing import tracing
    count = await tracing.flush_to_db()
    return {"flushed": count}


# ── Errors ──

@router.get("/errors/summary")
async def get_error_summary(hours: int = Query(24, ge=1, le=168),
                            current_user: User = Depends(get_current_user)):
    from modules.observability.error_tracker import error_tracker
    return await error_tracker.get_error_summary(hours)


@router.get("/errors")
async def get_recent_errors(limit: int = Query(50, le=200),
                            severity: str = None,
                            current_user: User = Depends(get_current_user)):
    from modules.observability.error_tracker import error_tracker
    return await error_tracker.get_recent_errors(limit, severity)


@router.post("/errors/{error_id}/resolve")
async def resolve_error(error_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    from modules.observability.error_tracker import error_tracker
    return await error_tracker.resolve_error(error_id)


# ── Health ──

@router.get("/health")
async def check_health(current_user: User = Depends(get_current_user)):
    from modules.observability.service_health import service_health
    return await service_health.check_all_services()


@router.get("/health/history")
async def get_health_history(hours: int = Query(24, ge=1, le=168),
                             limit: int = Query(50, le=200),
                             current_user: User = Depends(get_current_user)):
    from modules.observability.service_health import service_health
    return await service_health.get_health_history(hours, limit)
