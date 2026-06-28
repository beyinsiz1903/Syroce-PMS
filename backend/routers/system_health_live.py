"""
System Health — Live Events API
Provides live event replay, audit metrics, and WebSocket status for the dashboard.
"""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query

from core.database import db
from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/system-health", tags=["System Health Live"])


@router.get("/live/events")
async def get_live_events(
    since: str | None = None,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """Get recent system health events for replay/fallback when WebSocket is disconnected."""
    query = {"tenant_id": current_user.tenant_id}
    if since:
        query["timestamp"] = {"$gte": since}
    else:
        query["timestamp"] = {"$gte": (datetime.now(UTC) - timedelta(hours=1)).isoformat()}

    events = await db.system_health_events.find(query, {"_id": 0}).sort("timestamp", -1).limit(limit).to_list(limit)

    return {"events": events, "count": len(events)}


@router.get("/live/status")
async def get_live_status(current_user: User = Depends(get_current_user)):
    """WebSocket live status — connection count and last event timestamp."""
    try:
        from websocket_server import connected_clients

        health_clients = len(connected_clients.get("system-health", set()))
    except Exception:
        health_clients = 0

    last_event = await db.system_health_events.find_one({"tenant_id": current_user.tenant_id}, {"_id": 0, "timestamp": 1, "event_type": 1}, sort=[("timestamp", -1)])

    return {
        "ws_connected_clients": health_clients,
        "last_event": last_event,
        "ws_available": True,
    }


@router.get("/audit/metrics")
async def get_health_audit_metrics(
    hours: int = Query(24, ge=1, le=168),
    current_user: User = Depends(get_current_user),
):
    """Audit and observability metrics for health dashboard interactions."""
    since = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
    tid = current_user.tenant_id

    # Drift scan duration (from scan results)
    drift_scans = await db.drift_scan_results.find({"tenant_id": tid, "timestamp": {"$gte": since}}, {"_id": 0, "scanned_at": 1, "drifts_found": 1, "critical_drifts": 1}).to_list(50)

    # Reconciliation success rate
    recon_results = await db.reconciliation_results.find({"tenant_id": tid, "timestamp": {"$gte": since}}, {"_id": 0, "status": 1}).to_list(100)
    recon_total = len(recon_results)
    recon_success = sum(1 for r in recon_results if r.get("status") in ("resolved", "auto_fixed", "success"))

    # Queue backlog trend
    queue_pending = await db.task_queue.count_documents({"status": "pending"})
    queue_stuck = await db.task_queue.count_documents({"status": "stuck"})

    # Security violations trend
    violations = await db.tenant_guard_violations.count_documents({"expected_tenant_id": tid, "timestamp": {"$gte": since}}) if "tenant_guard_violations" in await db.list_collection_names() else 0

    # Dead letter growth
    dl_total = await db.dead_letter_tasks.count_documents({})
    dl_period = await db.dead_letter_tasks.count_documents({"archived_at": {"$gte": since}})

    return {
        "period_hours": hours,
        "drift": {
            "scans_count": len(drift_scans),
            "total_drifts": sum(s.get("drifts_found", 0) for s in drift_scans),
            "critical_drifts": sum(s.get("critical_drifts", 0) for s in drift_scans),
        },
        "reconciliation": {
            "total_runs": recon_total,
            "success_count": recon_success,
            "success_rate": round(recon_success / max(recon_total, 1) * 100, 1),
        },
        "queue": {
            "current_pending": queue_pending,
            "current_stuck": queue_stuck,
        },
        "security": {
            "violations_period": violations,
        },
        "dead_letter": {
            "total": dl_total,
            "new_in_period": dl_period,
        },
        "retrieved_at": datetime.now(UTC).isoformat(),
    }
