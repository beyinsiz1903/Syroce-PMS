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
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.security import get_current_user
from models.schemas import User
from core.database import db

from .models import COLL_MONITORING_ALERTS, AlertStatus
from .aggregator import (
    collect_all_metrics,
    collect_provider_health,
    collect_ingest_health,
    collect_ari_health,
    collect_reconciliation_health,
    collect_queue_worker_health,
)
from .monitoring_worker import (
    get_monitoring_worker_state,
    get_last_metrics,
    monitoring_run_once,
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
    current_user: User = Depends(get_current_user),
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
        "provider_statuses": {
            name: p.get("status", "unknown") for name, p in providers.items()
        },
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
    status: Optional[str] = Query(None),
    severity: Optional[str] = None,
    provider: Optional[str] = None,
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    """List monitoring alerts with filters."""
    q: Dict[str, Any] = {}
    if status:
        q["status"] = status
    if severity:
        q["severity"] = severity
    if provider:
        q["provider"] = provider

    alerts = await db[COLL_MONITORING_ALERTS].find(
        q, _NO_ID,
    ).sort("created_at", -1).limit(limit).to_list(limit)

    active_count = await db[COLL_MONITORING_ALERTS].count_documents(
        {"status": {"$in": ["active", "acknowledged"]}},
    )

    return {"alerts": alerts, "count": len(alerts), "active_count": active_count}


# ── Metrics ───────────────────────────────────────────────────────────

@router.get("/metrics")
async def get_detailed_metrics(
    current_user: User = Depends(get_current_user),
):
    """Detailed metrics for all health domains."""
    metrics = await collect_all_metrics()
    return metrics


# ── Provider Health ───────────────────────────────────────────────────

@router.get("/providers")
async def get_provider_health(
    current_user: User = Depends(get_current_user),
):
    """Detailed provider health breakdown."""
    health = await collect_provider_health()

    provider_alerts: Dict[str, list] = {}
    for pname in health.get("providers", {}):
        alerts = await db[COLL_MONITORING_ALERTS].find(
            {"provider": pname, "status": {"$in": ["active", "acknowledged"]}},
            _NO_ID,
        ).to_list(20)
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
    current_user: User = Depends(get_current_user),
):
    """Acknowledge a monitoring alert."""
    alert = await db[COLL_MONITORING_ALERTS].find_one(
        {"id": alert_id}, _NO_ID,
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.get("status") == "resolved":
        raise HTTPException(status_code=400, detail="Alert already resolved")

    await db[COLL_MONITORING_ALERTS].update_one(
        {"id": alert_id},
        {"$set": {
            "status": AlertStatus.ACKNOWLEDGED.value,
            "acknowledged_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"message": "Alert acknowledged", "alert_id": alert_id}


# ── Resolve Alert ─────────────────────────────────────────────────────

@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    req: ResolveAlertRequest,
    current_user: User = Depends(get_current_user),
):
    """Resolve a monitoring alert."""
    alert = await db[COLL_MONITORING_ALERTS].find_one(
        {"id": alert_id}, _NO_ID,
    )
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    if alert.get("status") == "resolved":
        raise HTTPException(status_code=400, detail="Alert already resolved")

    await db[COLL_MONITORING_ALERTS].update_one(
        {"id": alert_id},
        {"$set": {
            "status": AlertStatus.RESOLVED.value,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        }},
    )
    return {"message": "Alert resolved", "alert_id": alert_id}
