"""
Dashboard Router — Control Plane Dashboard API
================================================
Single pane of glass for system health, metrics, and trends.

Endpoints:
  GET  /api/ops/dashboard              — Full system dashboard
  GET  /api/ops/dashboard/tenant/{id}  — Tenant-scoped dashboard
  GET  /api/ops/dashboard/trends       — Historical trends
  GET  /api/ops/dashboard/connectors   — Connector health
  GET  /api/ops/dashboard/pipeline     — Pipeline depth
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Query

from .dashboard_aggregator import (
    get_dashboard_aggregator,
    COLL_SNAPSHOTS,
)

logger = logging.getLogger("controlplane.dashboard_router")

router = APIRouter(prefix="/api/ops/dashboard", tags=["Control Plane Dashboard"])


@router.get("")
async def get_dashboard(
    tenant_id: Optional[str] = Query(None, description="Filter by tenant"),
):
    """Full system dashboard — single pane of glass.
    Health score, failure counts, pipeline depth, connector status.
    """
    agg = get_dashboard_aggregator()
    return await agg.compute_dashboard(tenant_id=tenant_id)


@router.get("/tenant/{tenant_id}")
async def get_tenant_dashboard(tenant_id: str):
    """Tenant-scoped dashboard."""
    agg = get_dashboard_aggregator()
    return await agg.compute_dashboard(tenant_id=tenant_id)


@router.get("/trends")
async def get_trends(
    hours: int = Query(24, ge=1, le=168),
    tenant_id: Optional[str] = Query(None),
):
    """Historical health score trends from snapshots."""
    from core.database import db

    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    query = {
        "timestamp": {"$gte": cutoff},
        "snapshot_type": "system",
    }
    if tenant_id:
        query["tenant_id"] = tenant_id

    snapshots = await db[COLL_SNAPSHOTS].find(
        query, {"_id": 0, "timestamp": 1, "health_score": 1, "health_grade": 1, "metrics": 1}
    ).sort("timestamp", 1).to_list(1000)

    timestamps = []
    health_scores = []
    failure_counts = []
    outbox_depths = []

    for s in snapshots:
        timestamps.append(s["timestamp"])
        health_scores.append(s.get("health_score", 0))
        m = s.get("metrics", {})
        failure_counts.append(m.get("open_failures", 0))
        outbox_depths.append(m.get("outbox_pending", 0) + m.get("outbox_stuck", 0))

    return {
        "hours": hours,
        "data_points": len(snapshots),
        "timestamps": timestamps,
        "health_scores": health_scores,
        "failure_counts": failure_counts,
        "outbox_depths": outbox_depths,
    }


@router.get("/connectors")
async def get_connectors(
    tenant_id: Optional[str] = Query(None),
):
    """All connector health statuses."""
    agg = get_dashboard_aggregator()
    dashboard = await agg.compute_dashboard(tenant_id=tenant_id)
    return {"connectors": dashboard.get("connector_status", [])}


@router.get("/pipeline")
async def get_pipeline(
    tenant_id: Optional[str] = Query(None),
):
    """End-to-end reservation pipeline depth."""
    agg = get_dashboard_aggregator()
    dashboard = await agg.compute_dashboard(tenant_id=tenant_id)
    return dashboard.get("pipeline", {})
