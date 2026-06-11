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
import asyncio
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Body, Query

from .dashboard_aggregator import (
    COLL_SNAPSHOTS,
    get_dashboard_aggregator,
)

logger = logging.getLogger("controlplane.dashboard_router")

router = APIRouter(prefix="/api/ops/dashboard", tags=["Control Plane Dashboard"])

# Per-endpoint time budget for the Control Plane polling surface.
# On Atlas shared tiers a stuck aggregation (or a privileged Mongo command) can
# hang for tens of seconds; the edge proxy then drops the idle connection, which
# the browser surfaces as `net::ERR_CONNECTION_CLOSED`. Bound every dashboard
# endpoint so it always answers within a few seconds — returning a partial /
# degraded payload on timeout — instead of holding the connection open.
DASHBOARD_TIMEOUT_S = 8.0


async def _bounded(coro, *, fallback, label, timeout: float = DASHBOARD_TIMEOUT_S):
    """Await ``coro`` under a time budget.

    On timeout (or unexpected error) log it and return a copy of ``fallback``
    flagged ``degraded`` so the front-end can render an empty/error card instead
    of the request hanging until the proxy kills the connection. We do NOT
    swallow errors silently — each failure is logged at the endpoint level.
    """
    from fastapi import HTTPException
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except (TimeoutError, asyncio.TimeoutError):
        logger.warning(
            "ops dashboard endpoint '%s' exceeded %.1fs budget; returning degraded payload",
            label, timeout,
        )
    except HTTPException:
        # Auth / validation errors must surface as-is, never masked as degraded 200.
        raise
    except Exception:
        logger.warning(
            "ops dashboard endpoint '%s' failed; returning degraded payload",
            label, exc_info=True,
        )
    fb = dict(fallback)
    fb["degraded"] = True
    return fb


def _degraded_dashboard() -> dict:
    return {
        "health_score": 0,
        "health_grade": "F",
        "metrics": {},
        "connector_status": [],
        "pipeline": {"stages": [], "total_in_flight": 0},
        "recent_failures": [],
        "timestamp": datetime.now(UTC).isoformat(),
    }


@router.get("")
async def get_dashboard(
    tenant_id: str | None = Query(None, description="Filter by tenant"),
):
    """Full system dashboard — single pane of glass.
    Health score, failure counts, pipeline depth, connector status.
    """
    agg = get_dashboard_aggregator()
    return await _bounded(
        agg.compute_dashboard(tenant_id=tenant_id),
        fallback=_degraded_dashboard(),
        label="dashboard",
    )


@router.get("/tenant/{tenant_id}")
async def get_tenant_dashboard(tenant_id: str):
    """Tenant-scoped dashboard."""
    agg = get_dashboard_aggregator()
    return await agg.compute_dashboard(tenant_id=tenant_id)


@router.get("/trends")
async def get_trends(
    hours: int = Query(24, ge=1, le=168),
    tenant_id: str | None = Query(None),
):
    """Historical health score trends from snapshots."""
    from core.database import db

    async def _work():
        cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
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

    return await _bounded(
        _work(),
        fallback={
            "hours": hours,
            "data_points": 0,
            "timestamps": [],
            "health_scores": [],
            "failure_counts": [],
            "outbox_depths": [],
        },
        label="trends",
    )


@router.get("/connectors")
async def get_connectors(
    tenant_id: str | None = Query(None),
):
    """All connector health statuses."""
    agg = get_dashboard_aggregator()
    dashboard = await agg.compute_dashboard(tenant_id=tenant_id)
    return {"connectors": dashboard.get("connector_status", [])}


@router.get("/pipeline")
async def get_pipeline(
    tenant_id: str | None = Query(None),
):
    """End-to-end reservation pipeline depth."""
    agg = get_dashboard_aggregator()
    dashboard = await agg.compute_dashboard(tenant_id=tenant_id)
    return dashboard.get("pipeline", {})


@router.get("/channel-health")
async def get_channel_health(
    tenant_id: str | None = Query(None),
    hours: int = Query(24, ge=1, le=168),
):
    """Channel Health Dashboard — push latency percentiles, sync rates,
    failure breakdown, reconciliation drift, retry metrics, provider SLA."""
    from .channel_health_aggregator import compute_channel_health
    return await _bounded(
        compute_channel_health(tenant_id=tenant_id, hours=hours),
        fallback={
            "push_latency": {},
            "sync_metrics": {},
            "failure_breakdown": {},
            "reconciliation_drift": {},
            "retry_metrics": {},
            "provider_summary": {},
            "provider_sla": {},
            "period_hours": hours,
        },
        label="channel-health",
    )


@router.get("/channel-health/trends")
async def get_channel_health_trends(
    tenant_id: str | None = Query(None),
    hours: int = Query(168, ge=1, le=720),
    bucket_hours: int = Query(0, ge=0, le=24, description="0 = auto"),
):
    """Historical trends for channel health — time-bucketed latency, sync, drift, retry."""
    from .channel_health_aggregator import compute_channel_health_trends
    return await _bounded(
        compute_channel_health_trends(
            tenant_id=tenant_id, hours=hours, bucket_hours=bucket_hours,
        ),
        fallback={
            "buckets": [],
            "bucket_size_hours": bucket_hours,
            "period_hours": hours,
            "total_buckets": 0,
        },
        label="channel-health/trends",
    )


@router.get("/channel-health/field-kpis")
async def get_channel_health_field_kpis(
    tenant_id: str | None = Query(None),
    period_hours: int = Query(24, ge=1, le=720),
):
    """Operational field KPIs — sync success, drift reduction, MTTR,
    operator interventions, push SLA compliance with period-over-period comparison."""
    from .channel_health_aggregator import compute_field_kpis
    _empty_kpi = {"current": 0, "previous": 0, "delta": 0, "trend": "flat"}
    return await _bounded(
        compute_field_kpis(tenant_id=tenant_id, period_hours=period_hours),
        fallback={
            "sync_success": dict(_empty_kpi),
            "drift_reduction": dict(_empty_kpi),
            "mttr_hours": dict(_empty_kpi),
            "operator_interventions": dict(_empty_kpi),
            "push_sla_compliance": dict(_empty_kpi),
            "period_hours": period_hours,
        },
        label="channel-health/field-kpis",
    )


@router.get("/channel-health/weekly-proof")
async def get_channel_health_weekly_proof(
    tenant_id: str | None = Query(None),
    weeks: int = Query(8, ge=2, le=52),
):
    """Week-over-week improvement proof — drift reduction, MTTR improvement,
    SLA compliance trend, sync success trend over N weeks."""
    from .channel_health_aggregator import compute_weekly_proof
    return await _bounded(
        compute_weekly_proof(tenant_id=tenant_id, weeks=weeks),
        fallback={"weeks": [], "improvements": {}, "total_weeks": 0},
        label="channel-health/weekly-proof",
    )


@router.get("/tech-debt")
async def get_tech_debt():
    """Quarantine burn-down dashboard — categorized test counts,
    weekly targets, effort estimates, and health score."""
    from .tech_debt_aggregator import compute_tech_debt
    return compute_tech_debt()


@router.get("/deploys")
async def get_deploys(
    environment: str | None = Query(None, description="Filter by environment"),
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
    return await _bounded(
        get_deploy_stats(),
        fallback={"by_environment": [], "overall": {}},
        label="deploy-stats",
    )


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
    tenant_id: str | None = Query(None),
    days_ahead: int = Query(14, ge=1, le=60),
):
    """Inventory ledger alignment status.

    Compares room_type_inventory (authoritative, from room_night_locks)
    against channel manager sync snapshots.

    Returns: alignment_status, drift_count, drift_nights, provider breakdown.
    """
    from .inventory_alignment import compute_inventory_alignment
    return await _bounded(
        compute_inventory_alignment(tenant_id=tenant_id, days_ahead=days_ahead),
        fallback={
            "alignment_status": "no_data",
            "freshness": "empty",
            "drift_count": 0,
            "drift_nights": 0,
            "provider_breakdown": [],
            "inventory_room_type_nights": 0,
            "connectors_checked": 0,
            "date_range": {"start": "", "end": ""},
        },
        label="inventory-alignment",
    )


@router.get("/dora-metrics")
async def get_dora_metrics(
    days: int = Query(30, ge=7, le=90),
    environment: str | None = Query(None),
):
    """DORA release metrics — deployment frequency, change failure rate, MTTR, lead time."""
    from .dora_metrics import compute_dora_metrics
    return await _bounded(
        compute_dora_metrics(days=days, environment=environment),
        fallback={
            "period_days": days,
            "environment": environment or "all",
            "total_deploys": 0,
            "metrics": {},
        },
        label="dora-metrics",
    )


@router.get("/dora-correlation")
async def get_dora_correlation(
    days: int = Query(30, ge=14, le=90),
    tenant_id: str | None = Query(None),
):
    """DORA x Channel Health correlation analysis.

    Cross-references deployment behavior with channel health outcomes:
    deploy frequency vs drift, failure rate vs sync success, MTTR vs import failures.
    """
    from .dora_metrics import compute_dora_channel_correlation
    return await _bounded(
        compute_dora_channel_correlation(days=days, tenant_id=tenant_id),
        fallback={"period_days": days, "correlations": []},
        label="dora-correlation",
    )


# ── Drift Alerts ─────────────────────────────────────────────────

@router.get("/drift-alerts")
async def get_drift_alerts_endpoint(
    tenant_id: str | None = Query(None),
    severity: str | None = Query(None, description="Filter: warning, critical, severe"),
    acknowledged: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Active drift alerts — threshold-based inventory drift warnings."""
    from .drift_alerting import get_drift_alerts
    result = await _bounded(
        get_drift_alerts(
            tenant_id=tenant_id, severity=severity,
            acknowledged=acknowledged, limit=limit,
        ),
        fallback={"__alerts__": []},
        label="drift-alerts",
    )
    if isinstance(result, dict) and result.get("degraded"):
        return {"alerts": [], "count": 0, "degraded": True}
    return {"alerts": result, "count": len(result)}


@router.get("/drift-alerts/summary")
async def get_drift_alert_summary_endpoint(
    tenant_id: str | None = Query(None),
):
    """Drift alert summary for the ops dashboard — quick severity overview."""
    from .drift_alerting import get_drift_alert_summary
    return await _bounded(
        get_drift_alert_summary(tenant_id=tenant_id),
        fallback={
            "active_count": 0,
            "by_severity": {"warning": 0, "critical": 0, "severe": 0},
            "highest_severity": "none",
            "recent_alerts": [],
        },
        label="drift-alerts-summary",
    )


@router.post("/drift-alerts/evaluate")
async def evaluate_drift_alerts_endpoint(
    tenant_id: str | None = Query(None),
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
    acknowledged_by: str | None = Query("operator"),
):
    """Acknowledge a drift alert."""
    from .drift_alerting import acknowledge_drift_alert
    success = await acknowledge_drift_alert(alert_id, acknowledged_by=acknowledged_by)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Alert not found or already acknowledged")
    return {"success": True, "alert_id": alert_id, "status": "acknowledged"}


# ── Auto-Actions ────────────────────────────────────────────────

@router.get("/auto-actions")
async def get_auto_actions_endpoint(
    tenant_id: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """Auto-action history — automated responses to severe alerts."""
    from .auto_actions import get_auto_action_history
    actions = await get_auto_action_history(tenant_id=tenant_id, limit=limit)
    return {"actions": actions, "count": len(actions)}


@router.get("/ops-kpis")
async def get_ops_kpis_endpoint(
    tenant_id: str | None = Query(None),
    hours: int = Query(24, ge=1, le=168),
):
    """Unified KPI panel data — MTTR, drift trend, sync success, auto-heal stats."""
    from datetime import datetime, timedelta

    from core.database import db as _db

    from .auto_actions import COLL_AUTO_ACTIONS
    from .drift_alerting import COLL_DRIFT_EVAL_LOG, get_drift_alert_summary

    now = datetime.now(UTC)
    cutoff = (now - timedelta(hours=hours)).isoformat()

    async def _work():
        # Drift alert stats
        drift_summary = await get_drift_alert_summary(tenant_id=tenant_id)

        # Auto-action stats
        total_actions = await _db[COLL_AUTO_ACTIONS].count_documents(
            {"executed_at": {"$gte": cutoff}}
        )
        success_actions = await _db[COLL_AUTO_ACTIONS].count_documents(
            {"executed_at": {"$gte": cutoff}, "status": {"$in": ["success", "partial"]}}
        )
        failed_actions = await _db[COLL_AUTO_ACTIONS].count_documents(
            {"executed_at": {"$gte": cutoff}, "status": "failed"}
        )

        # Evaluation history for drift trend
        eval_logs = await _db[COLL_DRIFT_EVAL_LOG].find(
            {"evaluated_at": {"$gte": cutoff}},
            {"_id": 0, "evaluated_at": 1, "drift_records": 1, "drift_nights": 1, "alignment_status": 1},
        ).sort("evaluated_at", 1).to_list(500)

        drift_trend = []
        for ev in eval_logs:
            drift_trend.append({
                "time": ev.get("evaluated_at", ""),
                "drift_records": ev.get("drift_records", 0),
                "drift_nights": ev.get("drift_nights", 0),
                "status": ev.get("alignment_status", "unknown"),
            })

        # Channel health KPIs (sync success, MTTR)
        try:
            from .channel_health_aggregator import compute_field_kpis
            field_kpis = await compute_field_kpis(tenant_id=tenant_id, period_hours=hours)
        except Exception:
            field_kpis = {}

        return {
            "period_hours": hours,
            "calculated_at": now.isoformat(),
            "drift_alerts": drift_summary,
            "auto_actions": {
                "total": total_actions,
                "success": success_actions,
                "failed": failed_actions,
                "success_rate": round(success_actions / total_actions * 100, 1) if total_actions > 0 else 100.0,
            },
            "drift_trend": drift_trend[-50:],
            "field_kpis": {
                "sync_success": field_kpis.get("sync_success", {}),
                "mttr_hours": field_kpis.get("mttr_hours", {}),
                "drift_reduction": field_kpis.get("drift_reduction", {}),
                "push_sla_compliance": field_kpis.get("push_sla_compliance", {}),
            },
        }

    return await _bounded(
        _work(),
        fallback={
            "period_hours": hours,
            "calculated_at": now.isoformat(),
            "drift_alerts": {
                "active_count": 0,
                "by_severity": {"warning": 0, "critical": 0, "severe": 0},
                "highest_severity": "none",
                "recent_alerts": [],
            },
            "auto_actions": {"total": 0, "success": 0, "failed": 0, "success_rate": 100.0},
            "drift_trend": [],
            "field_kpis": {
                "sync_success": {},
                "mttr_hours": {},
                "drift_reduction": {},
                "push_sla_compliance": {},
            },
        },
        label="ops-kpis",
    )


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
