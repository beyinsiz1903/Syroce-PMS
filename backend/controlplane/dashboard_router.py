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
  GET  /api/ops/dashboard/channel-health — Channel Health Dashboard
  GET  /api/ops/dashboard/channel-health/weekly-proof — Weekly improvement proof
  GET  /api/ops/dashboard/tech-debt    — Quarantine burn-down tracking
  POST /api/ops/deploys                — Record deploy event (CI/CD → Control Plane)
  GET  /api/ops/dashboard/deploys      — Deploy history
  GET  /api/ops/dashboard/deploy-stats — Deploy statistics
  GET  /api/ops/dashboard/deploy-trend — Daily deploy trend chart data
  GET  /api/ops/dashboard/inventory-alignment — Inventory ledger alignment status
  GET  /api/ops/dashboard/dora-metrics — DORA release metrics
  GET  /api/ops/dashboard/dora-correlation — DORA × Channel Health correlation
  GET  /api/ops/dashboard/drift-alerts — Active drift alerts
  GET  /api/ops/dashboard/drift-alerts/summary — Drift alert summary for dashboard
  POST /api/ops/dashboard/drift-alerts/evaluate — Evaluate and fire drift alerts
  POST /api/ops/dashboard/drift-alerts/{alert_id}/acknowledge — Acknowledge a drift alert
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Query, Body

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


@router.get("/channel-health")
async def get_channel_health(
    tenant_id: Optional[str] = Query(None),
    hours: int = Query(24, ge=1, le=168),
):
    """Channel Health Dashboard — push latency percentiles, sync rates,
    failure breakdown, reconciliation drift, retry metrics, provider SLA."""
    from .channel_health_aggregator import compute_channel_health
    return await compute_channel_health(tenant_id=tenant_id, hours=hours)


@router.get("/channel-health/trends")
async def get_channel_health_trends(
    tenant_id: Optional[str] = Query(None),
    hours: int = Query(168, ge=1, le=720),
    bucket_hours: int = Query(0, ge=0, le=24, description="0 = auto"),
):
    """Historical trends for channel health — time-bucketed latency, sync, drift, retry."""
    from .channel_health_aggregator import compute_channel_health_trends
    return await compute_channel_health_trends(
        tenant_id=tenant_id, hours=hours, bucket_hours=bucket_hours,
    )


@router.get("/channel-health/field-kpis")
async def get_channel_health_field_kpis(
    tenant_id: Optional[str] = Query(None),
    period_hours: int = Query(24, ge=1, le=720),
):
    """Operational field KPIs — sync success, drift reduction, MTTR,
    operator interventions, push SLA compliance with period-over-period comparison."""
    from .channel_health_aggregator import compute_field_kpis
    return await compute_field_kpis(tenant_id=tenant_id, period_hours=period_hours)


@router.get("/channel-health/weekly-proof")
async def get_channel_health_weekly_proof(
    tenant_id: Optional[str] = Query(None),
    weeks: int = Query(8, ge=2, le=52),
):
    """Week-over-week improvement proof — drift reduction, MTTR improvement,
    SLA compliance trend, sync success trend over N weeks."""
    from .channel_health_aggregator import compute_weekly_proof
    return await compute_weekly_proof(tenant_id=tenant_id, weeks=weeks)


@router.get("/tech-debt")
async def get_tech_debt():
    """Quarantine burn-down dashboard — categorized test counts,
    weekly targets, effort estimates, and health score."""
    from .tech_debt_aggregator import compute_tech_debt
    return compute_tech_debt()


@router.get("/deploys")
async def get_deploys(
    environment: Optional[str] = Query(None, description="Filter by environment"),
    limit: int = Query(20, ge=1, le=100),
):
    """Recent deployment events — CI/CD history in Control Plane."""
    from .deploy_tracker import get_deploy_history
    deploys = await get_deploy_history(environment=environment, limit=limit)
    return {"deploys": deploys, "count": len(deploys)}


@router.get("/deploy-stats")
async def get_deploy_stats_endpoint():
    """Deploy statistics — success rates, rollback counts per environment."""
    from .deploy_tracker import get_deploy_stats
    return await get_deploy_stats()


@router.get("/deploy-trend")
async def get_deploy_trend_endpoint(
    days: int = Query(14, ge=1, le=90),
):
    """Daily deploy activity trend for Control Plane chart."""
    from .deploy_tracker import get_deploy_trend
    trend = await get_deploy_trend(days=days)
    return {"trend": trend, "days": days}


@router.get("/inventory-alignment")
async def get_inventory_alignment(
    tenant_id: Optional[str] = Query(None),
    days_ahead: int = Query(14, ge=1, le=60),
):
    """Inventory ledger alignment status.

    Compares room_type_inventory (authoritative, from room_night_locks)
    against channel manager sync snapshots.

    Returns: alignment_status, drift_count, drift_nights, provider breakdown.
    """
    from .inventory_alignment import compute_inventory_alignment
    return await compute_inventory_alignment(tenant_id=tenant_id, days_ahead=days_ahead)


@router.get("/dora-metrics")
async def get_dora_metrics(
    days: int = Query(30, ge=7, le=90),
    environment: Optional[str] = Query(None),
):
    """DORA release metrics — deployment frequency, change failure rate, MTTR, lead time."""
    from .dora_metrics import compute_dora_metrics
    return await compute_dora_metrics(days=days, environment=environment)


@router.get("/dora-correlation")
async def get_dora_correlation(
    days: int = Query(30, ge=14, le=90),
    tenant_id: Optional[str] = Query(None),
):
    """DORA x Channel Health correlation analysis.

    Cross-references deployment behavior with channel health outcomes:
    deploy frequency vs drift, failure rate vs sync success, MTTR vs import failures.
    """
    from .dora_metrics import compute_dora_channel_correlation
    return await compute_dora_channel_correlation(days=days, tenant_id=tenant_id)


# ── Drift Alerts ─────────────────────────────────────────────────

@router.get("/drift-alerts")
async def get_drift_alerts_endpoint(
    tenant_id: Optional[str] = Query(None),
    severity: Optional[str] = Query(None, description="Filter: warning, critical, severe"),
    acknowledged: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Active drift alerts — threshold-based inventory drift warnings."""
    from .drift_alerting import get_drift_alerts
    alerts = await get_drift_alerts(
        tenant_id=tenant_id, severity=severity,
        acknowledged=acknowledged, limit=limit,
    )
    return {"alerts": alerts, "count": len(alerts)}


@router.get("/drift-alerts/summary")
async def get_drift_alert_summary_endpoint(
    tenant_id: Optional[str] = Query(None),
):
    """Drift alert summary for the ops dashboard — quick severity overview."""
    from .drift_alerting import get_drift_alert_summary
    return await get_drift_alert_summary(tenant_id=tenant_id)


@router.post("/drift-alerts/evaluate")
async def evaluate_drift_alerts_endpoint(
    tenant_id: Optional[str] = Query(None),
):
    """Evaluate current inventory state and fire drift alerts if thresholds are breached.

    Thresholds:
      - warning: 1+ drift record in 15 min
      - critical: 3+ room-night drift in 15 min
      - severe: drift persists after reconciliation
    """
    from .drift_alerting import evaluate_drift_alerts
    return await evaluate_drift_alerts(tenant_id=tenant_id)


@router.post("/drift-alerts/{alert_id}/acknowledge")
async def acknowledge_drift_alert_endpoint(
    alert_id: str,
    acknowledged_by: Optional[str] = Query("operator"),
):
    """Acknowledge a drift alert."""
    from .drift_alerting import acknowledge_drift_alert
    success = await acknowledge_drift_alert(alert_id, acknowledged_by=acknowledged_by)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Alert not found or already acknowledged")
    return {"success": True, "alert_id": alert_id, "status": "acknowledged"}


# ── Deploy event ingestion (separate prefix for CI/CD webhook) ───
deploy_router = APIRouter(prefix="/api/ops", tags=["Deploy Events"])


@deploy_router.post("/deploys")
async def record_deploy(event: dict = Body(...)):
    """Record a deployment event from CI/CD pipeline.

    Called by GitHub Actions after each deploy attempt.
    Captures: sha, environment, status, actor, smoke_test results, rollback info.
    """
    from .deploy_tracker import record_deploy_event
    result = await record_deploy_event(event)
    return result
