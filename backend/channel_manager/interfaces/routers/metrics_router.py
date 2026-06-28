"""Historical metrics, trends, retention, daily-aggregation endpoints."""

import logging

from fastapi import APIRouter, Body, Depends, Query
from pydantic import BaseModel

from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v98 DW

from ...application.historical_metrics_service import HistoricalMetricsService

logger = logging.getLogger("channel_manager.routers.metrics")

router = APIRouter(tags=["CM Metrics"])


class CreateSnapshotRequest(BaseModel):
    connector_id: str | None = None


@router.post("/metrics/snapshot")
async def create_metrics_snapshot(
    req: CreateSnapshotRequest = Body(CreateSnapshotRequest()),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    svc = HistoricalMetricsService()
    return await svc.create_snapshot(current_user.tenant_id, req.connector_id)


@router.get("/metrics/history")
async def get_metrics_history(
    connector_id: str | None = None,
    period: str = Query("7d"),
    limit: int = Query(500, le=2000),
    current_user: User = Depends(get_current_user),
):
    svc = HistoricalMetricsService()
    return await svc.get_history(current_user.tenant_id, connector_id, period, limit)


@router.get("/metrics/trends")
async def get_metrics_trends(
    connector_id: str | None = None,
    period: str = Query("7d"),
    current_user: User = Depends(get_current_user),
):
    svc = HistoricalMetricsService()
    return await svc.get_trends(current_user.tenant_id, connector_id, period)


@router.get("/metrics/history/{connector_id}")
async def get_connector_metrics_history(
    connector_id: str,
    period: str = Query("7d"),
    current_user: User = Depends(get_current_user),
):
    svc = HistoricalMetricsService()
    return await svc.get_history(current_user.tenant_id, connector_id, period)


@router.get("/metrics/history/property/{property_id}")
async def get_property_metrics_history(
    property_id: str,
    period: str = Query("7d"),
    current_user: User = Depends(get_current_user),
):
    svc = HistoricalMetricsService()
    return await svc.get_history_by_property(current_user.tenant_id, property_id, period)


@router.post("/metrics/retention-cleanup")
async def run_retention_cleanup(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    svc = HistoricalMetricsService()
    return await svc.run_retention_cleanup(current_user.tenant_id)


@router.post("/metrics/daily-aggregation")
async def run_daily_aggregation(
    date: str | None = Body(None, embed=True),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    svc = HistoricalMetricsService()
    return await svc.create_daily_aggregation(current_user.tenant_id, date)
