"""
Ops Router — Control Plane API Endpoints
==========================================
All /api/ops/* endpoints for operational visibility and control.

Endpoints:
  GET  /api/ops/overview               — System health overview
  GET  /api/ops/failures               — List failures with filters
  GET  /api/ops/failures/{failure_id}  — Get single failure
  POST /api/ops/failures/{failure_id}/retry    — Retry a failure
  POST /api/ops/failures/{failure_id}/resolve  — Mark resolved
  POST /api/ops/failures/{failure_id}/ignore   — Mark ignored
  GET  /api/ops/outbox                 — Outbox monitor
  GET  /api/ops/imports                — Import pipeline monitor
  GET  /api/ops/sync                   — Sync jobs monitor
  GET  /api/ops/secrets/audit          — Secret access audit trail
  GET  /api/ops/runbooks               — Operational runbooks
  GET  /api/ops/runbooks/{runbook_id}  — Single runbook
"""
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.database import db
from security.ops_guard import require_ops_access

from .alerting import COLL_ALERTS, get_alerting_engine
from .failure_tracker import get_failure_tracker
from .retry_engine import get_retry_engine
from .runbooks import get_runbook, list_runbooks
from .secret_audit import get_secret_access_control

logger = logging.getLogger("controlplane.ops_router")

router = APIRouter(prefix="/api/ops", tags=["Control Plane"],
                   dependencies=[Depends(require_ops_access)])


# ── Response Models ────────────────────────────────────────────────

class OverviewResponse(BaseModel):
    open_failures: int = 0
    failures_by_severity: dict = Field(default_factory=dict)
    failures_by_type: dict = Field(default_factory=dict)
    failures_by_operation: dict = Field(default_factory=dict)
    stuck_outbox_count: int = 0
    failed_imports_24h: int = 0
    pending_imports: int = 0
    sync_success_rate: float = 0.0
    recent_sync_jobs: int = 0
    secret_access_anomalies: int = 0
    active_connectors: int = 0
    recent_error_rate: float = 0.0
    timestamp: str = ""


class RetryRequest(BaseModel):
    dry_run: bool = False
    initiated_by: str = "operator"


# ── 1. System Health Overview ──────────────────────────────────────

@router.get("/overview", response_model=OverviewResponse)
async def ops_overview(
    tenant_id: str | None = Query(None, description="Filter by tenant"),
):
    """System health overview — the single pane of glass for operations."""
    tracker = get_failure_tracker()
    now = datetime.now(UTC)
    cutoff_24h = (now - timedelta(hours=24)).isoformat()
    cutoff_30m = (now - timedelta(minutes=30)).isoformat()

    # Failure counts
    open_count = await tracker.count_open(tenant_id=tenant_id)
    by_severity = await tracker.count_by_severity(tenant_id=tenant_id)
    by_type = await tracker.count_by_type(tenant_id=tenant_id)
    by_operation = await tracker.count_by_operation(tenant_id=tenant_id)

    # Outbox: stuck events (pending > 30 min)
    outbox_query = {"status": {"$in": ["pending", "retry"]}, "created_at": {"$lte": cutoff_30m}}
    stuck_outbox = await db.outbox_events.count_documents(outbox_query)

    # Imports: failed last 24h + pending
    import_fail_query = {"import_status": "failed", "updated_at": {"$gte": cutoff_24h}}
    failed_imports = await db.imported_reservations.count_documents(import_fail_query)
    pending_imports = await db.imported_reservations.count_documents(
        {"import_status": {"$in": ["pending_auto_import", "retry"]}}
    )

    # Sync jobs: success rate
    sync_total = await db.cp_sync_jobs.count_documents({"started_at": {"$gte": cutoff_24h}})
    sync_success = await db.cp_sync_jobs.count_documents(
        {"started_at": {"$gte": cutoff_24h}, "status": "completed"}
    )
    sync_rate = (sync_success / sync_total * 100) if sync_total > 0 else 100.0

    # Secret access anomalies (failures in last 24h)
    secret_anomalies = await db.secret_access_audit.count_documents(
        {"result": {"$in": ["failure", "denied", "not_found"]}, "timestamp": {"$gte": cutoff_24h}}
    )

    # Active connectors
    active_connectors = await db.exely_connections.count_documents({"is_active": True})
    try:
        active_connectors += await db.hotelrunner_connections.count_documents({"is_active": True})
    except Exception:
        pass

    # Recent error rate (failures last 1h / total operations)
    cutoff_1h = (now - timedelta(hours=1)).isoformat()
    recent_failures = await db.cp_failures.count_documents({"created_at": {"$gte": cutoff_1h}})

    return OverviewResponse(
        open_failures=open_count,
        failures_by_severity=by_severity,
        failures_by_type=by_type,
        failures_by_operation=by_operation,
        stuck_outbox_count=stuck_outbox,
        failed_imports_24h=failed_imports,
        pending_imports=pending_imports,
        sync_success_rate=round(sync_rate, 2),
        recent_sync_jobs=sync_total,
        secret_access_anomalies=secret_anomalies,
        active_connectors=active_connectors,
        recent_error_rate=round(recent_failures, 2),
        timestamp=now.isoformat(),
    )


# ── 2. Failures API ───────────────────────────────────────────────

@router.get("/failures")
async def list_failures(
    tenant_id: str | None = Query(None),
    provider: str | None = Query(None),
    failure_type: str | None = Query(None),
    severity: str | None = Query(None),
    status: str | None = Query(None),
    operation_type: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    """List failures with filters and pagination."""
    tracker = get_failure_tracker()
    return await tracker.list_failures(
        tenant_id=tenant_id, provider=provider,
        failure_type=failure_type, severity=severity,
        status=status, operation_type=operation_type,
        limit=limit, skip=skip,
    )


@router.get("/failures/{failure_id}")
async def get_failure(failure_id: str):
    """Get a single failure event."""
    tracker = get_failure_tracker()
    failure = await tracker.get_failure(failure_id)
    if not failure:
        raise HTTPException(status_code=404, detail="Failure not found")
    return failure


# ── 3. Retry / Resolve / Ignore ───────────────────────────────────

@router.post("/failures/{failure_id}/retry")
async def retry_failure(failure_id: str, body: RetryRequest | None = None):
    """Retry a failed operation. Idempotent and duplicate-safe."""
    engine = get_retry_engine()
    dry_run = body.dry_run if body else False
    initiated_by = body.initiated_by if body else "operator"
    result = await engine.retry(failure_id, dry_run=dry_run, initiated_by=initiated_by)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result)
    return result


@router.post("/failures/{failure_id}/resolve")
async def resolve_failure(failure_id: str):
    """Mark a failure as resolved."""
    tracker = get_failure_tracker()
    success = await tracker.resolve(failure_id)
    if not success:
        raise HTTPException(status_code=404, detail="Failure not found or already resolved")
    return {"success": True, "failure_id": failure_id, "status": "resolved"}


@router.post("/failures/{failure_id}/ignore")
async def ignore_failure(failure_id: str):
    """Mark a failure as ignored (acknowledged, won't fix)."""
    tracker = get_failure_tracker()
    success = await tracker.ignore(failure_id)
    if not success:
        raise HTTPException(status_code=404, detail="Failure not found or already ignored")
    return {"success": True, "failure_id": failure_id, "status": "ignored"}


# ── 4. Outbox Monitor ─────────────────────────────────────────────

@router.get("/outbox")
async def outbox_monitor(
    tenant_id: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """Outbox event monitor — pending, stuck, and failed events."""
    now = datetime.now(UTC)
    cutoff_30m = (now - timedelta(minutes=30)).isoformat()

    base_query = {}
    if tenant_id:
        base_query["tenant_id"] = tenant_id

    pending = await db.outbox_events.count_documents({**base_query, "status": "pending"})
    processing = await db.outbox_events.count_documents({**base_query, "status": "processing"})
    failed = await db.outbox_events.count_documents({**base_query, "status": {"$in": ["failed", "parked"]}})

    # Stuck = pending/retry older than 30 min
    stuck_query = {**base_query, "status": {"$in": ["pending", "retry"]}, "created_at": {"$lte": cutoff_30m}}
    stuck = await db.outbox_events.count_documents(stuck_query)

    # Recent failed events
    failed_events = await db.outbox_events.find(
        {**base_query, "status": {"$in": ["failed", "parked"]}},
        {"_id": 0, "event_id": 1, "event_type": 1, "tenant_id": 1,
         "status": 1, "retry_count": 1, "last_error": 1, "created_at": 1, "updated_at": 1},
    ).sort("updated_at", -1).limit(limit).to_list(limit)

    return {
        "pending": pending,
        "processing": processing,
        "failed": failed,
        "stuck": stuck,
        "stuck_threshold_minutes": 30,
        "recent_failed_events": failed_events,
        "timestamp": now.isoformat(),
    }


# ── 5. Import Pipeline Monitor ────────────────────────────────────

@router.get("/imports")
async def imports_monitor(
    tenant_id: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """Import pipeline monitor — pending, failed, and delayed imports."""
    now = datetime.now(UTC)
    cutoff_24h = (now - timedelta(hours=24)).isoformat()
    coll = db.imported_reservations

    base_query = {}
    if tenant_id:
        base_query["tenant_id"] = tenant_id

    pending = await coll.count_documents({**base_query, "import_status": "pending_auto_import"})
    processing = await coll.count_documents({**base_query, "import_status": "processing"})
    imported = await coll.count_documents({**base_query, "import_status": "imported", "updated_at": {"$gte": cutoff_24h}})
    review = await coll.count_documents({**base_query, "import_status": "review_required"})
    retry = await coll.count_documents({**base_query, "import_status": "retry"})
    failed = await coll.count_documents({**base_query, "import_status": "failed"})

    # Recent failed imports
    failed_items = await coll.find(
        {**base_query, "import_status": "failed"},
        {"_id": 0, "id": 1, "tenant_id": 1, "provider": 1, "import_status": 1,
         "error_message": 1, "retry_count": 1, "created_at": 1, "updated_at": 1},
    ).sort("updated_at", -1).limit(limit).to_list(limit)

    return {
        "pending": pending,
        "processing": processing,
        "imported_24h": imported,
        "review_required": review,
        "retry": retry,
        "failed": failed,
        "recent_failed": failed_items,
        "timestamp": now.isoformat(),
    }


# ── 6. Sync Jobs Monitor ──────────────────────────────────────────

@router.get("/sync")
async def sync_monitor(
    tenant_id: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """Sync jobs monitor — recent jobs, success/failure rate, latency."""
    now = datetime.now(UTC)
    cutoff_24h = (now - timedelta(hours=24)).isoformat()

    base_query = {"started_at": {"$gte": cutoff_24h}}
    if tenant_id:
        base_query["tenant_id"] = tenant_id

    coll = db.cp_sync_jobs
    total = await coll.count_documents(base_query)
    completed = await coll.count_documents({**base_query, "status": "completed"})
    failed = await coll.count_documents({**base_query, "status": "failed"})
    running = await coll.count_documents({**base_query, "status": "running"})
    stalled = await coll.count_documents({**base_query, "status": "stalled"})

    success_rate = (completed / total * 100) if total > 0 else 100.0

    # Recent jobs
    recent = await coll.find(
        base_query,
        {"_id": 0, "id": 1, "tenant_id": 1, "provider": 1, "job_type": 1,
         "status": 1, "started_at": 1, "completed_at": 1, "duration_ms": 1, "error": 1},
    ).sort("started_at", -1).limit(limit).to_list(limit)

    return {
        "total_24h": total,
        "completed": completed,
        "failed": failed,
        "running": running,
        "stalled": stalled,
        "success_rate": round(success_rate, 2),
        "recent_jobs": recent,
        "timestamp": now.isoformat(),
    }


# ── 7. Secret Access Audit ────────────────────────────────────────

@router.get("/secrets/audit")
async def secret_audit(
    tenant_id: str | None = Query(None),
    provider: str | None = Query(None),
    result_filter: str | None = Query(None, alias="result"),
    limit: int = Query(50, ge=1, le=200),
    skip: int = Query(0, ge=0),
):
    """Secret access audit trail. No secret values returned."""
    query = {}
    if tenant_id:
        query["tenant_id"] = tenant_id
    if provider:
        query["provider"] = provider
    if result_filter:
        query["result"] = result_filter

    coll = db.secret_access_audit
    total = await coll.count_documents(query)
    items = await coll.find(
        query, {"_id": 0}
    ).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)

    # Anomaly count (failures in last 24h)
    cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    anomaly_count = await coll.count_documents(
        {"result": {"$in": ["failure", "denied", "not_found"]}, "timestamp": {"$gte": cutoff}}
    )

    return {
        "items": items,
        "total": total,
        "limit": limit,
        "skip": skip,
        "anomalies_24h": anomaly_count,
    }


# ── 8. Runbooks ───────────────────────────────────────────────────

@router.get("/runbooks")
async def get_runbooks(
    category: str | None = Query(None, description="Filter by category: import, outbox, ari, provider, security, operations, sync"),
):
    """List all operational runbooks."""
    return {"runbooks": list_runbooks(category=category)}


@router.get("/runbooks/{runbook_id}")
async def get_single_runbook(runbook_id: str):
    """Get a specific runbook by ID."""
    rb = get_runbook(runbook_id)
    if not rb:
        raise HTTPException(status_code=404, detail=f"Runbook '{runbook_id}' not found")
    return rb.to_dict()


# ── 9. Alerts ─────────────────────────────────────────────────────

@router.get("/alerts")
async def list_alerts(
    severity: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """Get recent operational alerts."""
    engine = get_alerting_engine()
    alerts = await engine.get_recent_alerts(limit=limit, severity=severity)
    return {"alerts": alerts, "total": len(alerts)}


@router.post("/alerts/check")
async def run_alert_checks():
    """Manually trigger all alert checks. Returns any fired alerts."""
    engine = get_alerting_engine()
    fired = await engine.check_and_alert()
    return {"fired": len(fired), "alerts": fired}


# ── 10. Secret Access Anomalies ───────────────────────────────────

@router.get("/secrets/anomalies")
async def secret_anomalies(
    tenant_id: str | None = Query(None),
    hours: int = Query(24, ge=1, le=168),
):
    """Get secret access anomalies (failures, denials)."""
    control = get_secret_access_control()
    return await control.get_anomalies(hours=hours, tenant_id=tenant_id)


# ── 11. Alert → Business KPI Correlation ──────────────────────────

@router.get("/alerts/kpi-correlation")
async def alert_kpi_correlation(
    hours: int = Query(24, ge=1, le=168),
    tenant_id: str | None = Query(None),
):
    """Correlate alerts with business KPIs.

    Maps alerts to business impact:
    - Import failures → missed bookings → revenue impact
    - Outbox stuck → delayed rate pushes → rate parity risk
    - Secret anomalies → security exposure → compliance risk
    - Crypto failures → data protection risk
    """
    now = datetime.now(UTC)
    cutoff = (now - timedelta(hours=hours)).isoformat()

    query = {"fired_at": {"$gte": cutoff}}
    if tenant_id:
        query["tenant_id"] = tenant_id

    alerts = await db[COLL_ALERTS].find(
        query, {"_id": 0},
    ).sort("fired_at", -1).to_list(500)

    # Compute KPI impact
    kpi_impact = {
        "revenue_risk": {"level": "low", "alert_count": 0, "drivers": []},
        "rate_parity_risk": {"level": "low", "alert_count": 0, "drivers": []},
        "security_risk": {"level": "low", "alert_count": 0, "drivers": []},
        "data_protection_risk": {"level": "low", "alert_count": 0, "drivers": []},
    }

    TRIGGER_KPI_MAP = {
        "import_failure_spike": "revenue_risk",
        "high_error_rate": "revenue_risk",
        "outbox_stuck": "rate_parity_risk",
        "sync_failure_spike": "rate_parity_risk",
        "secret_anomaly": "security_risk",
        "provider_auth_failure": "security_risk",
        "crypto_failure": "data_protection_risk",
    }

    for alert in alerts:
        trigger = alert.get("trigger", "")
        kpi = TRIGGER_KPI_MAP.get(trigger)
        if kpi and kpi in kpi_impact:
            kpi_impact[kpi]["alert_count"] += 1
            kpi_impact[kpi]["drivers"].append({
                "trigger": trigger,
                "severity": alert.get("severity", ""),
                "title": alert.get("title", ""),
                "fired_at": alert.get("fired_at", ""),
                "tenant_id": alert.get("tenant_id"),
                "provider": alert.get("provider"),
                "runbook_link": alert.get("runbook_link"),
            })

    # Compute risk levels
    for kpi_key, kpi_data in kpi_impact.items():
        count = kpi_data["alert_count"]
        has_critical = any(d.get("severity") == "critical" for d in kpi_data["drivers"])
        if has_critical or count >= 5:
            kpi_data["level"] = "critical"
        elif count >= 3:
            kpi_data["level"] = "high"
        elif count >= 1:
            kpi_data["level"] = "medium"
        else:
            kpi_data["level"] = "low"
        # Limit drivers to top 5
        kpi_data["drivers"] = kpi_data["drivers"][:5]

    # Alert summary by severity and provider
    by_severity = {}
    by_provider = {}
    for alert in alerts:
        sev = alert.get("severity", "unknown")
        by_severity[sev] = by_severity.get(sev, 0) + 1
        prov = alert.get("provider")
        if prov:
            by_provider[prov] = by_provider.get(prov, 0) + 1

    return {
        "kpi_impact": kpi_impact,
        "alert_summary": {
            "total_alerts": len(alerts),
            "by_severity": by_severity,
            "by_provider": by_provider,
            "time_window_hours": hours,
        },
        "timestamp": now.isoformat(),
    }
