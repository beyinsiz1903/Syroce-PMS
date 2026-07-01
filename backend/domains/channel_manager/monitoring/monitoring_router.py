"""
Operational Monitoring — API Router
======================================

Dashboard and alerting endpoints.

Endpoints:
  GET  /api/channel-manager/monitoring/overview      — System health overview
  GET  /api/channel-manager/monitoring/alerts         — List alerts
  GET  /api/channel-manager/monitoring/metrics        — Detailed metrics
  GET  /api/channel-manager/monitoring/providers      — Provider health breakdown
  POST /api/channel-manager/monitoring/alerts/{id}/ack     — Acknowledge alert
  POST /api/channel-manager/monitoring/alerts/{id}/resolve — Resolve alert
"""

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.database import db
from core.helpers import require_super_admin_guard  # v102 — task #54: lock cross-tenant monitoring to super_admin
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v100 DW

# Cross-tenant monitoring endpoints expose data aggregated across all tenants
# (alerts, metrics, dedup counters, time-series). They must only be reachable
# by system (super) admins. Tenant-scoped endpoints (dispatch-config) keep the
# admin-level `view_system_diagnostics` operation guard so a tenant admin can
# still manage their own tenant's Slack settings.
# `not_found=False` returns HTTP 403 for authenticated-but-not-super-admin
# callers (instead of the default 404), matching the contract in task #54.
_REQUIRE_SUPER_ADMIN = require_super_admin_guard(not_found=False)

from .aggregator import (
    collect_all_metrics,
    collect_provider_health,
)
from .models import COLL_MONITORING_ALERTS, AlertStatus
from .monitoring_worker import (
    get_last_metrics,
    get_monitoring_worker_state,
)

logger = logging.getLogger("monitoring.router")

_NO_ID = {"_id": 0}

router = APIRouter(
    prefix="/api/channel-manager/monitoring",
    tags=["Operational Monitoring"],
)


class AckAlertRequest(BaseModel):
    note: str = ""


class ResolveAlertRequest(BaseModel):
    resolution: str = ""


# ── Overview ──────────────────────────────────────────────────────────


@router.get("/overview")
async def get_monitoring_overview(
    current_user: User = Depends(_REQUIRE_SUPER_ADMIN),  # v102 task #54
):
    """System health overview with key metrics."""
    cached = get_last_metrics()
    if cached and cached.get("system_health"):
        metrics = cached
    else:
        metrics = await collect_all_metrics()

    provider_health = metrics.get("provider_health", {})
    providers = provider_health.get("providers", {})
    recon = metrics.get("reconciliation_health", {})
    queue = metrics.get("queue_health", {})

    active_alerts = await db[COLL_MONITORING_ALERTS].count_documents(
        {"status": {"$in": ["active", "acknowledged"]}},
    )
    critical_alerts = await db[COLL_MONITORING_ALERTS].count_documents(
        {"status": "active", "severity": "critical"},
    )

    return {
        "system_health": metrics.get("system_health", "unknown"),
        "providers": len(providers),
        "active_alerts": active_alerts,
        "critical_alerts": critical_alerts,
        "queue_depth": queue.get("queue_depth", 0),
        "reconciliation_open_cases": recon.get("open_cases", 0),
        "provider_statuses": {name: p.get("status", "unknown") for name, p in providers.items()},
        "ingest_status": metrics.get("ingest_health", {}).get("status", "unknown"),
        "ari_status": metrics.get("ari_health", {}).get("status", "unknown"),
        "recon_status": recon.get("status", "unknown"),
        "queue_status": queue.get("status", "unknown"),
        "worker": get_monitoring_worker_state(),
        "collected_at": metrics.get("collected_at"),
    }


# ── Alerts ────────────────────────────────────────────────────────────


@router.get("/alerts")
async def list_alerts(
    status: str | None = Query(None),
    severity: str | None = None,
    provider: str | None = None,
    limit: int = Query(100, le=500),
    current_user: User = Depends(_REQUIRE_SUPER_ADMIN),  # v102 task #54
):
    """List monitoring alerts with filters."""
    q: dict[str, Any] = {}
    if status:
        q["status"] = status
    if severity:
        q["severity"] = severity
    if provider:
        q["provider"] = provider

    alerts = (
        await db[COLL_MONITORING_ALERTS]
        .find(
            q,
            _NO_ID,
        )
        .sort("created_at", -1)
        .limit(limit)
        .to_list(limit)
    )

    active_count = await db[COLL_MONITORING_ALERTS].count_documents(
        {"status": {"$in": ["active", "acknowledged"]}},
    )

    return {"alerts": alerts, "count": len(alerts), "active_count": active_count}


# ── Metrics ───────────────────────────────────────────────────────────


@router.get("/metrics")
async def get_detailed_metrics(
    current_user: User = Depends(_REQUIRE_SUPER_ADMIN),  # v102 task #54
):
    """Detailed metrics for all health domains."""
    metrics = await collect_all_metrics()
    return metrics


# ── Provider Health ───────────────────────────────────────────────────


@router.get("/providers")
async def get_provider_health(
    current_user: User = Depends(_REQUIRE_SUPER_ADMIN),  # v102 task #54
):
    """Detailed provider health breakdown."""
    health = await collect_provider_health()

    provider_alerts: dict[str, list] = {}
    for pname in health.get("providers", {}):
        alerts = (
            await db[COLL_MONITORING_ALERTS]
            .find(
                {"provider": pname, "status": {"$in": ["active", "acknowledged"]}},
                _NO_ID,
            )
            .to_list(20)
        )
        provider_alerts[pname] = alerts

    return {
        **health,
        "provider_alerts": provider_alerts,
    }


# ── Acknowledge Alert ─────────────────────────────────────────────────


@router.post("/alerts/{alert_id}/ack")
async def acknowledge_alert(
    alert_id: str,
    req: AckAlertRequest,
    current_user: User = Depends(_REQUIRE_SUPER_ADMIN),  # v102 task #54 (cross-tenant action)
):
    """Acknowledge a monitoring alert."""
    alert = await db[COLL_MONITORING_ALERTS].find_one(
        {"id": alert_id},
        _NO_ID,
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.get("status") == "resolved":
        raise HTTPException(status_code=400, detail="Alert already resolved")

    await db[COLL_MONITORING_ALERTS].update_one(
        {"id": alert_id},
        {
            "$set": {
                "status": AlertStatus.ACKNOWLEDGED.value,
                "acknowledged_at": datetime.now(UTC).isoformat(),
            }
        },
    )
    return {"message": "Alert acknowledged", "alert_id": alert_id}


# ── Resolve Alert ─────────────────────────────────────────────────────


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    req: ResolveAlertRequest,
    current_user: User = Depends(_REQUIRE_SUPER_ADMIN),  # v102 task #54 (cross-tenant action)
):
    """Resolve a monitoring alert."""
    alert = await db[COLL_MONITORING_ALERTS].find_one(
        {"id": alert_id},
        _NO_ID,
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.get("status") == "resolved":
        raise HTTPException(status_code=400, detail="Alert already resolved")

    await db[COLL_MONITORING_ALERTS].update_one(
        {"id": alert_id},
        {
            "$set": {
                "status": AlertStatus.RESOLVED.value,
                "resolved_at": datetime.now(UTC).isoformat(),
            }
        },
    )
    return {"message": "Alert resolved", "alert_id": alert_id}


# ── Slack / Dispatch Configuration ────────────────────────────────────


class SlackConfigRequest(BaseModel):
    enabled: bool = False
    webhook_url: str = ""
    severities: list = ["critical", "high"]
    channel_name: str = ""


@router.get("/dispatch-config")
async def get_dispatch_config_endpoint(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v102 task #54 — tenant admin gate
):
    """Get alert dispatch configuration (Slack, Email, etc.)."""
    from .alert_dispatch import get_dispatch_config

    config = await get_dispatch_config(current_user.tenant_id)
    # Mask webhook URL for security
    slack = config.get("slack", {})
    if slack.get("webhook_url"):
        url = slack["webhook_url"]
        slack["webhook_url_masked"] = url[:30] + "..." if len(url) > 30 else url
    return config


@router.post("/dispatch-config/slack")
async def update_slack_config(
    req: SlackConfigRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """Update Slack webhook configuration."""
    from .alert_dispatch import get_dispatch_config, update_dispatch_config

    config = await get_dispatch_config(current_user.tenant_id)
    config["slack"] = {
        "enabled": req.enabled,
        "webhook_url": req.webhook_url,
        "severities": req.severities,
        "channel_name": req.channel_name,
    }
    await update_dispatch_config(current_user.tenant_id, config)
    return {"success": True, "message": "Slack configuration updated"}


@router.post("/dispatch-config/slack/test")
async def test_slack(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """Send a test message to the configured Slack webhook."""
    from .alert_dispatch import get_dispatch_config, test_slack_webhook

    config = await get_dispatch_config(current_user.tenant_id)
    webhook_url = config.get("slack", {}).get("webhook_url", "")
    if not webhook_url:
        raise HTTPException(status_code=400, detail="No Slack webhook URL configured")

    result = await test_slack_webhook(webhook_url)
    return result


# ── Catchup Pre-Insert Dedup Counter ─────────────────────────────────


@router.get("/catchup-dedup")
async def get_catchup_dedup_stats(
    current_user: User = Depends(_REQUIRE_SUPER_ADMIN),  # v102 task #54
):
    """Show how often the catchup pre-insert duplicate guard fired.

    Backed by a Redis sorted set (``cm:catchup_dedup:events``) with a 24h
    sliding window — counts now survive backend restarts and aggregate
    across multiple instances. An in-memory deque acts as a fallback
    when Redis is unreachable so single-instance dev setups still work.
    Helps detect hidden re-ingest storms early — the same root cause
    that previously produced 8000+ failed raw_channel_events rows.
    """
    from .alert_engine import THRESHOLDS
    from .dedup_counter import get_counts

    stats = await get_counts()
    return {
        "last_1h_total": stats["last_1h_total"],
        "last_24h_total": stats["last_24h_total"],
        "last_1h_by_tenant_provider": stats["last_1h_by_tenant_provider"],
        "last_24h_by_tenant_provider": stats["last_24h_by_tenant_provider"],
        "thresholds": {
            "per_tenant_1h": THRESHOLDS.get("catchup_dedup_per_tenant_1h"),
            "per_tenant_24h": THRESHOLDS.get("catchup_dedup_per_tenant_24h"),
        },
        "note": (
            "Counts the number of times the pre-insert duplicate guard "
            "short-circuited a re-insert (`[CATCHUP-DEDUP]` log tag). "
            "Redis-backed (cm:catchup_dedup:events ZSET, 24h sliding "
            "window); survives restarts and aggregates across instances. "
            "Falls back to a per-process in-memory deque when Redis is "
            "unreachable."
        ),
    }


# ── Trend Metrics (24h Time Series) ──────────────────────────────────


@router.get("/trends")
async def get_metrics_trends(
    hours: int = Query(24, ge=1, le=168),
    current_user: User = Depends(_REQUIRE_SUPER_ADMIN),  # v102 task #54
):
    """Get time-series metrics for trend charts (last N hours)."""
    from datetime import timedelta

    from .monitoring_worker import COLL_METRICS_HISTORY

    since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()

    cursor = (
        db[COLL_METRICS_HISTORY]
        .find(
            {"ts": {"$gte": since}},
            {"_id": 0},
        )
        .sort("ts", 1)
    )

    snapshots = await cursor.to_list(2000)

    if not snapshots:
        return {
            "hours": hours,
            "data_points": 0,
            "ingest": [],
            "ari": [],
            "reconciliation": [],
            "queue": [],
        }

    # Aggregate into series
    ingest_series = []
    ari_series = []
    recon_series = []
    queue_series = []

    for s in snapshots:
        ts = s.get("ts", "")
        ingest_series.append(
            {
                "ts": ts,
                "events_1h": s.get("ingest_events_1h", 0),
                "failed": s.get("ingest_failed", 0),
                "duplicates": s.get("ingest_duplicates", 0),
            }
        )
        ari_series.append(
            {
                "ts": ts,
                "success_rate": s.get("ari_success_rate", 0),
                "p95_latency": s.get("ari_p95_latency", 0),
                "retry_count": s.get("ari_retry_count", 0),
            }
        )
        recon_series.append(
            {
                "ts": ts,
                "open_cases": s.get("recon_open", 0),
                "critical": s.get("recon_critical", 0),
            }
        )
        queue_series.append(
            {
                "ts": ts,
                "depth": s.get("queue_depth", 0),
                "retry_backlog": s.get("retry_backlog", 0),
            }
        )

    return {
        "hours": hours,
        "data_points": len(snapshots),
        "ingest": ingest_series,
        "ari": ari_series,
        "reconciliation": recon_series,
        "queue": queue_series,
    }
