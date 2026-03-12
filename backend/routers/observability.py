"""
Observability Router - API endpoints for platform observability.
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional

from core.security import get_current_user
from shared_kernel.tenancy_context import get_current_tenant, TenantContext

from modules.observability.metrics_collector import metrics
from modules.observability.distributed_tracing import tracing
from modules.observability.error_tracker import error_tracker
from modules.observability.service_health import service_health

router = APIRouter(prefix="/api/observability", tags=["observability"])


@router.get("/metrics")
async def get_metrics(tenant: TenantContext = Depends(get_current_tenant)):
    return metrics.get_dashboard_metrics()


@router.get("/metrics/all")
async def get_all_metrics(tenant: TenantContext = Depends(get_current_tenant)):
    return metrics.get_all_metrics()


@router.get("/metrics/history")
async def get_metrics_history(
    hours: int = Query(24, le=168),
    limit: int = Query(50, le=200),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await metrics.get_historical_metrics(hours, limit)


@router.post("/metrics/flush")
async def flush_metrics(tenant: TenantContext = Depends(get_current_tenant)):
    return await metrics.flush_to_db()


@router.get("/traces")
async def get_traces(
    slow_only: bool = False,
    limit: int = Query(50, le=200),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await tracing.get_recent_traces(tenant.tenant_id, limit, slow_only)


@router.get("/traces/summary")
async def get_trace_summary(
    hours: int = Query(1, le=24),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await tracing.get_trace_summary(hours)


@router.post("/traces/flush")
async def flush_traces(tenant: TenantContext = Depends(get_current_tenant)):
    return await tracing.flush_traces()


@router.get("/errors")
async def get_errors(
    severity: Optional[str] = None,
    module: Optional[str] = None,
    limit: int = Query(50, le=200),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await error_tracker.get_recent_errors(tenant.tenant_id, severity, module, limit)


@router.get("/errors/summary")
async def get_error_summary(
    hours: int = Query(24, le=168),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await error_tracker.get_error_summary(hours)


@router.post("/errors/{error_id}/resolve")
async def resolve_error(error_id: str, tenant: TenantContext = Depends(get_current_tenant)):
    return await error_tracker.resolve_error(error_id)


@router.get("/health")
async def check_health(tenant: TenantContext = Depends(get_current_tenant)):
    return await service_health.check_all_services()


@router.get("/health/history")
async def get_health_history(
    hours: int = Query(24, le=168),
    limit: int = Query(50, le=200),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await service_health.get_health_history(hours, limit)
