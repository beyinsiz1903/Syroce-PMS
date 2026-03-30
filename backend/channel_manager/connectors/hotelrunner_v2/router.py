"""
HotelRunner v2 — API Router
==============================

Exposes v2 connector operations via REST API.
All endpoints are under /api/channel/hotelrunner-v2/

Ops endpoints:
  GET  /status           → connector health + metrics
  GET  /trace/{res_id}   → reservation timeline trace
  POST /test-connection   → connection test
  POST /pull-reservations → manual pull
  POST /ingest            → manual ingest single reservation
  POST /push-ari          → manual ARI push
  POST /reconcile         → trigger reconciliation
  GET  /reconciliation/history → past runs
  GET  /reconciliation/drifts  → recent drifts
  GET  /flags             → get feature flags
  PUT  /flags             → update feature flags
  GET  /metrics           → metrics summary
  GET  /dlq               → dead letter queue entries
  GET  /readiness-score   → write readiness score (0-100)
  POST /observation/snapshot → collect daily observation snapshot
  GET  /observation/history  → observation snapshots (7 days)
  GET  /observation/report   → daily observation report
  GET  /observation/thresholds → alert threshold definitions
  GET  /transition/plan      → full write path transition plan
  GET  /transition/status    → current phase + readiness
  GET  /transition/history   → transition log
"""
import logging
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query

logger = logging.getLogger("hrv2.router")

router = APIRouter(prefix="/api/channel/hotelrunner-v2", tags=["HotelRunner v2 Connector"])


# ── Status & Health ───────────────────────────────────────────────────

@router.get("/status")
async def get_connector_status(
    tenant_id: str = Query(..., description="Tenant ID"),
    property_id: str = Query("default", description="Property ID"),
):
    """Get connector health status, flags, and metrics."""
    try:
        from channel_manager.connectors.hotelrunner_v2.service import HotelRunnerV2Service
        svc = await HotelRunnerV2Service.create(tenant_id, property_id)
        return await svc.get_status()
    except Exception as e:
        # Even if credentials fail, return flags + metrics
        from channel_manager.connectors.hotelrunner_v2.feature_flags import get_flags
        from channel_manager.connectors.hotelrunner_v2.metrics import get_summary
        flags = await get_flags(tenant_id)
        summary = await get_summary(tenant_id)
        return {
            "tenant_id": tenant_id,
            "property_id": property_id,
            "provider": "hotelrunner_v2",
            "connected": False,
            "connection_error": str(e),
            "feature_flags": flags,
            "metrics_24h": summary,
        }


@router.get("/trace/{reservation_id}")
async def get_reservation_trace(
    reservation_id: str,
    tenant_id: str = Query(...),
):
    """Get full timeline trace for a reservation."""
    from core.database import db
    _NO_ID = {"_id": 0}

    # Raw events
    raw_events = await db["raw_channel_events"].find(
        {"tenant_id": tenant_id, "external_reservation_id": reservation_id},
        _NO_ID,
    ).sort("received_at", 1).to_list(100)

    # Lineage
    lineage = await db["reservation_lineage"].find_one(
        {"tenant_id": tenant_id, "external_reservation_id": reservation_id},
        _NO_ID,
    )

    # Outbox entries
    outbox = await db["connector_outbox"].find(
        {"tenant_id": tenant_id, "correlation_id": {"$regex": reservation_id}},
        _NO_ID,
    ).sort("created_at", 1).to_list(50)

    # DLQ entries
    dlq = await db["connector_dlq"].find(
        {"tenant_id": tenant_id, "correlation_id": {"$regex": reservation_id}},
        _NO_ID,
    ).to_list(10)

    return {
        "reservation_id": reservation_id,
        "raw_events": raw_events,
        "lineage": lineage,
        "outbox_entries": outbox,
        "dlq_entries": dlq,
    }


# ── Connection Test ───────────────────────────────────────────────────

@router.post("/test-connection")
async def test_connection(
    tenant_id: str = Query(...),
    property_id: str = Query("default"),
):
    """Test HotelRunner connection."""
    from core.tenant_db import set_tenant_context
    set_tenant_context(tenant_id)
    from channel_manager.connectors.hotelrunner_v2.service import HotelRunnerV2Service
    try:
        svc = await HotelRunnerV2Service.create(tenant_id, property_id)
        return await svc.test_connection()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Reservation Operations ────────────────────────────────────────────

@router.post("/pull-reservations")
async def pull_reservations(
    tenant_id: str = Query(...),
    property_id: str = Query("default"),
    undelivered: bool = Query(True),
    from_date: str | None = Query(None, description="YYYY-MM-DD (max 30 days before)"),
    from_last_update_date: str | None = Query(None, description="YYYY-MM-DD"),
    modified: bool | None = Query(None, description="Only modified reservations"),
    booked: bool | None = Query(None, description="Only new reservations"),
    reservation_number: str | None = Query(None, description="Specific HR or channel code"),
):
    """Pull reservations from HotelRunner."""
    from channel_manager.connectors.hotelrunner_v2.feature_flags import is_enabled
    if not await is_enabled(tenant_id):
        raise HTTPException(status_code=403, detail="Connector not enabled for this tenant")

    from channel_manager.connectors.hotelrunner_v2.service import HotelRunnerV2Service
    svc = await HotelRunnerV2Service.create(tenant_id, property_id)
    return await svc.pull_reservations(
        undelivered=undelivered, from_date=from_date,
        from_last_update_date=from_last_update_date,
        modified=modified, booked=booked,
        reservation_number=reservation_number,
    )


@router.post("/confirm-delivery")
async def confirm_delivery(
    tenant_id: str = Query(...),
    property_id: str = Query("default"),
    message_uid: str = Query(..., description="message_uid from reservation"),
    pms_number: str | None = Query(None),
):
    """Confirm reservation delivery to HotelRunner."""
    from channel_manager.connectors.hotelrunner_v2.service import HotelRunnerV2Service
    svc = await HotelRunnerV2Service.create(tenant_id, property_id)
    return await svc.confirm_delivery(message_uid, pms_number=pms_number)


@router.get("/verify-transaction/{transaction_id}")
async def verify_transaction(
    transaction_id: str,
    tenant_id: str = Query(...),
    property_id: str = Query("default"),
):
    """Check ARI push transaction status via HotelRunner."""
    from channel_manager.connectors.hotelrunner_v2.service import HotelRunnerV2Service
    svc = await HotelRunnerV2Service.create(tenant_id, property_id)
    return await svc.verify_transaction(transaction_id)


@router.post("/ingest")
async def ingest_reservation(
    tenant_id: str = Query(...),
    property_id: str = Query("default"),
    payload: dict[str, Any] = Body(...),
):
    """Ingest a single reservation (webhook or manual)."""
    from channel_manager.connectors.hotelrunner_v2.feature_flags import is_enabled
    if not await is_enabled(tenant_id):
        raise HTTPException(status_code=403, detail="Connector not enabled for this tenant")

    from channel_manager.connectors.hotelrunner_v2.service import HotelRunnerV2Service
    svc = await HotelRunnerV2Service.create(tenant_id, property_id)
    return await svc.ingest_reservation(payload, received_via="api")


# ── ARI Push ──────────────────────────────────────────────────────────

@router.post("/push-ari")
async def push_ari(
    tenant_id: str = Query(...),
    property_id: str = Query("default"),
    body: dict[str, Any] = Body(...),
):
    """Push ARI update (availability/rate/restriction)."""
    from channel_manager.connectors.hotelrunner_v2.feature_flags import is_enabled
    if not await is_enabled(tenant_id):
        raise HTTPException(status_code=403, detail="Connector not enabled for this tenant")

    from channel_manager.connectors.hotelrunner_v2.service import HotelRunnerV2Service
    svc = await HotelRunnerV2Service.create(tenant_id, property_id)
    return await svc.push_ari(
        inv_code=body.get("inv_code") or body.get("room_code", ""),
        start_date=body.get("start_date", ""),
        end_date=body.get("end_date", ""),
        availability=body.get("availability"),
        price=body.get("price"),
        stop_sale=body.get("stop_sale"),
        min_stay=body.get("min_stay"),
        cta=body.get("cta"),
        ctd=body.get("ctd"),
        days=body.get("days"),
        channel_codes=body.get("channel_codes"),
        verify=body.get("verify", True),
    )


# ── Reconciliation ────────────────────────────────────────────────────

@router.post("/reconcile")
async def trigger_reconciliation(
    tenant_id: str = Query(...),
    property_id: str = Query("default"),
    since_hours: int = Query(24),
    auto_fix: bool = Query(False),
):
    """Trigger reconciliation run."""
    from core.tenant_db import set_tenant_context
    set_tenant_context(tenant_id)
    from channel_manager.connectors.hotelrunner_v2.reconciliation import run_reconciliation
    return await run_reconciliation(tenant_id, property_id, since_hours=since_hours, auto_fix=auto_fix)


@router.get("/reconciliation/history")
async def reconciliation_history(
    tenant_id: str = Query(...),
    limit: int = Query(20),
):
    from channel_manager.connectors.hotelrunner_v2.reconciliation import get_reconciliation_history
    return await get_reconciliation_history(tenant_id, limit=limit)


@router.get("/reconciliation/drifts")
async def reconciliation_drifts(
    tenant_id: str = Query(...),
    limit: int = Query(50),
):
    from channel_manager.connectors.hotelrunner_v2.reconciliation import get_recent_drifts
    return await get_recent_drifts(tenant_id, limit=limit)


# ── Feature Flags ─────────────────────────────────────────────────────

@router.get("/flags")
async def get_flags_endpoint(tenant_id: str = Query(...)):
    from channel_manager.connectors.hotelrunner_v2.feature_flags import get_flags
    return await get_flags(tenant_id)


@router.put("/flags")
async def update_flags(
    tenant_id: str = Query(...),
    body: dict[str, Any] = Body(...),
):
    from channel_manager.connectors.hotelrunner_v2.feature_flags import set_flags
    return await set_flags(tenant_id, body)


# ── Metrics ───────────────────────────────────────────────────────────

@router.get("/metrics")
async def get_metrics(
    tenant_id: str = Query(...),
    hours: int = Query(24),
):
    from channel_manager.connectors.hotelrunner_v2.metrics import get_summary
    return await get_summary(tenant_id, hours=hours)


# ── Dead Letter Queue ─────────────────────────────────────────────────

@router.get("/dlq")
async def get_dlq(
    tenant_id: str = Query(...),
    limit: int = Query(50),
):
    from core.database import db
    entries = await db["connector_dlq"].find(
        {"tenant_id": tenant_id, "provider": "hotelrunner"},
        {"_id": 0},
    ).sort("created_at", -1).to_list(limit)
    return {"entries": entries, "count": len(entries)}


@router.post("/dlq/{dlq_id}/retry")
async def retry_dlq_entry(
    dlq_id: str,
    tenant_id: str = Query(...),
    property_id: str = Query("default"),
):
    """Retry a dead letter queue entry."""
    from core.database import db
    entry = await db["connector_dlq"].find_one({"id": dlq_id, "tenant_id": tenant_id}, {"_id": 0})
    if not entry:
        raise HTTPException(status_code=404, detail="DLQ entry not found")

    from channel_manager.connectors.hotelrunner_v2.service import HotelRunnerV2Service
    svc = await HotelRunnerV2Service.create(tenant_id, property_id)

    operation = entry.get("operation", "")
    payload = entry.get("payload", {})

    if operation == "ari_push":
        result = await svc.push_ari(
            room_code=payload.get("inv_code", ""),
            start_date=payload.get("start_date", ""),
            end_date=payload.get("end_date", ""),
            availability=int(payload["availability"]) if "availability" in payload else None,
            price=float(payload["price"]) if "price" in payload else None,
            stop_sale=payload.get("stop_sale") == "1" if "stop_sale" in payload else None,
        )
        if result.get("success"):
            await db["connector_dlq"].update_one(
                {"id": dlq_id}, {"$set": {"status": "retried_success"}},
            )
        return result

    raise HTTPException(status_code=400, detail=f"Unknown operation: {operation}")


# ── Ops Dashboard (Aggregated) ────────────────────────────────────────

@router.get("/ops-dashboard")
async def get_ops_dashboard(
    tenant_id: str = Query(...),
    property_id: str = Query("default"),
):
    """
    Aggregated endpoint for the Ops Dashboard Frontend.
    Returns provider health, sync overview, failure visibility,
    recent events, readiness score — all in one call.
    """
    from channel_manager.connectors.hotelrunner_v2.feature_flags import get_flags
    from channel_manager.connectors.hotelrunner_v2.metrics import get_last_sync, get_summary
    from channel_manager.connectors.hotelrunner_v2.readiness import calculate_readiness_score
    from channel_manager.connectors.hotelrunner_v2.reconciliation import (
        get_recent_drifts,
        get_reconciliation_history,
    )
    from channel_manager.connectors.hotelrunner_v2.transition import get_current_phase
    from core.database import db as _db
    from core.tenant_db import set_tenant_context

    # Override tenant context to match the requested tenant_id
    # (middleware may have set a different tenant from JWT)
    set_tenant_context(tenant_id)

    now_iso = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()

    # 1. Feature flags
    flags = await get_flags(tenant_id)

    # 2. Metrics summary (24h)
    metrics = await get_summary(tenant_id, hours=24)

    # 3. Last sync timestamp
    last_sync = await get_last_sync(tenant_id)

    # 4. DLQ count + recent entries
    dlq_entries = await _db["connector_dlq"].find(
        {"tenant_id": tenant_id, "provider": "hotelrunner"},
        {"_id": 0},
    ).sort("created_at", -1).to_list(10)
    dlq_count = await _db["connector_dlq"].count_documents(
        {"tenant_id": tenant_id, "provider": "hotelrunner"},
    )

    # 5. Recent drifts + count
    drifts = await get_recent_drifts(tenant_id, limit=10)
    drift_count = await _db["connector_reconciliation_drifts"].count_documents(
        {"tenant_id": tenant_id, "provider": "hotelrunner_v2"},
    )

    # 6. Last reconciliation
    recon_history = await get_reconciliation_history(tenant_id, limit=1)
    last_recon = recon_history[0] if recon_history else None

    # 7. Recent connector events (last 10 metrics)
    recent_events = await _db["connector_metrics"].find(
        {"tenant_id": tenant_id, "provider": "hotelrunner_v2"},
        {"_id": 0},
    ).sort("recorded_at", -1).to_list(10)

    # 8. Retry count (failed operations in last 24h)
    retry_count = metrics.get("operations", {}).get("pull_reservations", {}).get("failed", 0)
    for op_data in metrics.get("operations", {}).values():
        retry_count = max(retry_count, op_data.get("failed", 0))
    total_retry = sum(
        op_data.get("failed", 0) for op_data in metrics.get("operations", {}).values()
    )

    # 9. Latency (average across all ops)
    latencies = [
        op_data.get("avg_latency_ms", 0)
        for op_data in metrics.get("operations", {}).values()
        if op_data.get("avg_latency_ms", 0) > 0
    ]
    avg_latency = round(sum(latencies) / len(latencies), 1) if latencies else 0

    # 10. Per-endpoint health from metrics
    ops = metrics.get("operations", {})

    def _endpoint_health(op_name):
        op = ops.get(op_name, {})
        if not op:
            return "unknown"
        if op.get("failed", 0) > 0 and op.get("success", 0) == 0:
            return "error"
        if op.get("total", 0) > 0 and op.get("success", 0) > 0:
            sr = op.get("success_rate", 0)
            if sr >= 90:
                return "healthy"
            if sr >= 50:
                return "degraded"
            return "error"
        return "unknown"

    # 11. Write Readiness Score
    readiness = await calculate_readiness_score(tenant_id)

    # 12. Transition phase
    phase_state = await get_current_phase(tenant_id)

    return {
        "generated_at": now_iso,
        "tenant_id": tenant_id,
        "property_id": property_id,

        # Provider Health
        "provider_health": {
            "provider": "HotelRunner",
            "connector_version": "v2",
            "auth_status": _endpoint_health("test_connection"),
            "reservations_api": _endpoint_health("pull_reservations"),
            "rooms_api": _endpoint_health("test_connection"),
            "channels_api": _endpoint_health("test_connection"),
            "shadow_mode": flags.get("shadow_mode", True),
            "write_path": "enabled" if flags.get("write_enabled", False) and not flags.get("shadow_mode", True) else "disabled",
            "connector_enabled": flags.get("connector_enabled", False),
        },

        # Feature Flags
        "feature_flags": flags,

        # Sync Overview
        "sync_overview": {
            "last_pull_timestamp": last_sync.get("recorded_at") if last_sync else None,
            "last_pull_operation": last_sync.get("operation") if last_sync else None,
            "last_pull_success": last_sync.get("success") if last_sync else None,
            "drift_count": drift_count,
            "last_reconciliation": {
                "run_id": last_recon.get("id") if last_recon else None,
                "timestamp": last_recon.get("created_at") if last_recon else None,
                "mismatch_count": last_recon.get("mismatch_count", 0) if last_recon else 0,
                "duration_ms": last_recon.get("duration_ms", 0) if last_recon else 0,
            },
        },

        # Metrics
        "metrics_24h": metrics,
        "avg_latency_ms": avg_latency,
        "total_retry_count": total_retry,

        # DLQ
        "dlq": {
            "count": dlq_count,
            "recent_entries": dlq_entries,
        },

        # Failure Visibility
        "error_taxonomy": metrics.get("error_taxonomy", {}),

        # Recent Events
        "recent_events": recent_events,

        # Recent Drifts
        "recent_drifts": drifts,

        # Write Readiness Score
        "readiness": readiness,

        # Transition Phase
        "transition": {
            "current_phase": phase_state.get("current_phase", "shadow"),
            "phase_started_at": phase_state.get("phase_started_at"),
            "phase_day": phase_state.get("phase_day", 0),
        },
    }


# ── Write Readiness Score ─────────────────────────────────────────────

@router.get("/readiness-score")
async def get_readiness_score(
    tenant_id: str = Query(...),
    hours: int = Query(24),
):
    """Calculate the Write Readiness Score (0-100)."""
    from core.tenant_db import set_tenant_context
    set_tenant_context(tenant_id)
    from channel_manager.connectors.hotelrunner_v2.readiness import calculate_readiness_score
    return await calculate_readiness_score(tenant_id, hours=hours)


# ── Shadow Observation ─────────────────────────────────────────────────

@router.post("/observation/snapshot")
async def collect_observation_snapshot(
    tenant_id: str = Query(...),
):
    """Collect a daily observation snapshot (metrics, alerts, consistency)."""
    from core.tenant_db import set_tenant_context
    set_tenant_context(tenant_id)
    from channel_manager.connectors.hotelrunner_v2.observation import collect_daily_snapshot
    return await collect_daily_snapshot(tenant_id)


@router.get("/observation/history")
async def get_observation_history_endpoint(
    tenant_id: str = Query(...),
    days: int = Query(7),
):
    """Get observation snapshot history (last N days)."""
    from core.tenant_db import set_tenant_context
    set_tenant_context(tenant_id)
    from channel_manager.connectors.hotelrunner_v2.observation import get_observation_history
    return await get_observation_history(tenant_id, days=days)


@router.get("/observation/report")
async def get_observation_report(
    tenant_id: str = Query(...),
):
    """Generate a daily observation report with trends."""
    from core.tenant_db import set_tenant_context
    set_tenant_context(tenant_id)
    from channel_manager.connectors.hotelrunner_v2.observation import generate_daily_report
    return await generate_daily_report(tenant_id)


@router.get("/observation/thresholds")
async def get_alert_thresholds_endpoint():
    """Return alert threshold definitions."""
    from channel_manager.connectors.hotelrunner_v2.observation import get_alert_thresholds
    return await get_alert_thresholds()


# ── Transition Plan ─────────────────────────────────────────────────

@router.get("/transition/plan")
async def get_transition_plan_endpoint():
    """Get the full write path transition plan."""
    from channel_manager.connectors.hotelrunner_v2.transition import get_transition_plan
    return await get_transition_plan()


@router.get("/transition/status")
async def get_transition_status(
    tenant_id: str = Query(...),
):
    """Get current transition phase + readiness for next phase."""
    from core.tenant_db import set_tenant_context
    set_tenant_context(tenant_id)
    from channel_manager.connectors.hotelrunner_v2.transition import get_phase_status
    return await get_phase_status(tenant_id)


@router.get("/transition/history")
async def get_transition_history_endpoint(
    tenant_id: str = Query(...),
    limit: int = Query(20),
):
    """Get transition history log."""
    from core.tenant_db import set_tenant_context
    set_tenant_context(tenant_id)
    from channel_manager.connectors.hotelrunner_v2.transition import get_transition_history
    return await get_transition_history(tenant_id, limit=limit)
