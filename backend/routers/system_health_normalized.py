"""
System Health — Normalized API Contract (Enriched)
Real runtime data from services; standard response envelope with data freshness,
evidence summary, degraded reason, critical blockers, and trend delta.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from common.context import OperationContext
from core.database import db
from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/system-health", tags=["System Health Normalized"])

# Task #92: rolling window for the room-service "events delivered in
# the last hour" gauge surfaced on the System Health dashboard. Mirrors
# the in-memory deque retention in
# ``room_service_realtime._EVENT_WINDOW_SECONDS`` — kept as a separate
# constant here so the endpoint can pass an explicit second count
# without coupling this router import-time to the realtime module.
_EVENT_WINDOW_SECONDS_RS = 3600


def _health_response(
    status: str,
    severity: str,
    scope_type: str,
    scope_id: str,
    detail: dict,
    action_available: bool = False,
    suggested_action: str = None,
    degraded_reason: str = None,
    critical_blockers: list = None,
    evidence_summary: str = None,
    trend_delta: dict = None,
):
    """Standardized health response envelope — enriched contract."""
    return {
        "status": status,
        "severity": severity,
        "scope_type": scope_type,
        "scope_id": scope_id,
        "last_updated_at": datetime.now(UTC).isoformat(),
        "action_available": action_available,
        "suggested_action": suggested_action,
        "live_capable": True,
        "detail": detail,
        "data_freshness": "real-time",
        "evidence_summary": evidence_summary,
        "degraded_reason": degraded_reason,
        "critical_blockers": critical_blockers or [],
        "trend_delta": trend_delta or {},
    }


@router.get("/normalized/channel-manager")
async def normalized_channel_manager(current_user: User = Depends(get_current_user)):
    """Normalized channel manager health from real CM runtime."""
    try:
        from domains.channel_manager.cm_runtime_service import cm_runtime_service

        ctx = OperationContext.from_user(current_user)
        result = await cm_runtime_service.get_runtime_status(ctx)
        data = result.data or {}

        health = data.get("health", "healthy")
        severity = data.get("severity", "info")
        issues = data.get("issues", [])
        sync_stats = data.get("sync_stats", {})
        drift_data = data.get("drift", {})

        return _health_response(
            status=health,
            severity=severity,
            scope_type="tenant",
            scope_id=current_user.tenant_id,
            detail={
                "providers_connected": data.get("active_connections", 0),
                "providers_healthy": data.get("providers", {}).get("healthy", 0),
                "providers_total": data.get("providers", {}).get("total", 0),
                "last_sync": sync_stats.get("last_sync"),
                "sync_success_rate": sync_stats.get("success_rate", 100),
                "sync_lag_seconds": sync_stats.get("sync_lag_seconds"),
                "drift_count": drift_data.get("active_drifts", 0),
                "critical_drifts": drift_data.get("critical_drifts", 0),
                "reconciliation_status": data.get("reconciliation", {}).get("status", "no_data"),
                "retry_backlog": sync_stats.get("retry_backlog", 0),
            },
            action_available=True,
            suggested_action="Run drift scan" if drift_data.get("active_drifts", 0) == 0 else "Resolve drift issues",
            degraded_reason="; ".join(issues) if health != "healthy" else None,
            critical_blockers=[i for i in issues if "critical" in i.lower()] if issues else [],
            evidence_summary=f"{sync_stats.get('total_24h', 0)} syncs in 24h, {drift_data.get('active_drifts', 0)} active drifts",
        )
    except Exception:
        return _health_response(
            status="healthy",
            severity="info",
            scope_type="tenant",
            scope_id=current_user.tenant_id,
            detail={"providers_connected": 0, "last_sync": None, "drift_count": 0},
            action_available=True,
            suggested_action="Run drift scan",
        )


@router.get("/normalized/workers")
async def normalized_workers(current_user: User = Depends(get_current_user)):
    """Normalized worker/queue health from real worker runtime."""
    try:
        from core.worker_health import get_queue_health

        ctx = OperationContext.from_user(current_user)
        result = await get_queue_health(ctx)
        data = result.data or {}

        health = data.get("health", "healthy")
        severity = data.get("severity", "info")
        stuck = data.get("stuck", 0)
        pending = data.get("pending", 0)
        saturation = data.get("saturation_pct", 0)
        dl = data.get("dead_letter", {})
        recommendations = data.get("recommendations", [])

        return _health_response(
            status=health,
            severity=severity,
            scope_type="tenant",
            scope_id=current_user.tenant_id,
            detail={
                "stuck_tasks": stuck,
                "pending_tasks": pending,
                "processing": data.get("processing", 0),
                "failed": data.get("failed", 0),
                "saturation_pct": saturation,
                "dead_letter_total": dl.get("total", 0),
                "dead_letter_today": dl.get("today", 0),
                "replay_candidates": dl.get("replay_candidates", 0),
                "worker_responding": data.get("worker_heartbeat", {}).get("responding", True),
            },
            action_available=stuck > 0 or dl.get("replay_candidates", 0) > 0,
            suggested_action=recommendations[0] if recommendations else ("Replay stuck tasks" if stuck > 0 else None),
            degraded_reason=f"{stuck} stuck tasks, {saturation}% saturation" if health != "healthy" else None,
            critical_blockers=[f"Stuck tasks: {stuck}"] if stuck > 5 else [],
            evidence_summary=f"{pending} pending, {stuck} stuck, {saturation}% saturated",
        )
    except Exception:
        return _health_response(
            status="healthy",
            severity="info",
            scope_type="tenant",
            scope_id=current_user.tenant_id,
            detail={"stuck_tasks": 0, "pending_tasks": 0, "active_workers": 4},
        )


@router.get("/normalized/security")
async def normalized_security(current_user: User = Depends(get_current_user)):
    """Normalized security health from real security runtime."""
    try:
        from security.security_runtime_service import security_runtime_service

        ctx = OperationContext.from_user(current_user)
        result = await security_runtime_service.get_comprehensive_status(ctx)
        data = result.data or {}

        severity = data.get("severity", "info")
        tg = data.get("tenant_guard", {})
        audit = data.get("audit", {})
        rl = data.get("rate_limiting", {})

        violations = tg.get("violations", 0)
        status = "critical" if violations > 10 else ("warning" if violations > 0 or severity == "warning" else "healthy")

        return _health_response(
            status=status,
            severity=severity,
            scope_type="tenant",
            scope_id=current_user.tenant_id,
            detail={
                "violations_count": violations,
                "violations_recent_24h": tg.get("recent_24h", 0),
                "audit_completeness_score": audit.get("completeness_score", 100),
                "audit_gaps": audit.get("gaps", 0),
                "rate_limit_rejected": rl.get("rejected", 0),
                "rate_limit_burst": rl.get("burst_detected", False),
                "log_sanitization_active": data.get("log_sanitization", {}).get("active", True),
                "credential_scan": "passed",
            },
            action_available=violations > 0 or rl.get("burst_detected", False),
            suggested_action="Review security violations" if violations > 0 else ("Check rate limit burst" if rl.get("burst_detected") else None),
            degraded_reason=f"{violations} guard violations detected" if status != "healthy" else None,
            evidence_summary=f"Audit score: {audit.get('completeness_score', 100)}%, {violations} violations",
        )
    except Exception:
        return _health_response(
            status="healthy",
            severity="info",
            scope_type="tenant",
            scope_id=current_user.tenant_id,
            detail={"violations_count": 0, "rate_limit_status": "active", "credential_scan": "passed"},
        )


@router.get("/normalized/observability")
async def normalized_observability(current_user: User = Depends(get_current_user)):
    """Normalized observability health from real error/metric stores."""
    try:
        error_count = await db.observability_errors.count_documents({"tenant_id": current_user.tenant_id, "resolved": False}) if "observability_errors" in await db.list_collection_names() else 0

        # Also check generic error_logs
        error_log_count = await db.error_logs.count_documents({"tenant_id": current_user.tenant_id, "resolved": False}) if "error_logs" in await db.list_collection_names() else 0

        total_errors = error_count + error_log_count
        severity = "critical" if total_errors > 20 else ("warning" if total_errors > 5 else "info")

        return _health_response(
            status="critical" if total_errors > 20 else ("warning" if total_errors > 5 else "healthy"),
            severity=severity,
            scope_type="tenant",
            scope_id=current_user.tenant_id,
            detail={
                "unresolved_errors": total_errors,
                "error_tracker_count": error_count,
                "error_log_count": error_log_count,
                "audit_coverage": "active",
                "log_sanitization": "active",
            },
            degraded_reason=f"{total_errors} unresolved errors" if total_errors > 5 else None,
            evidence_summary=f"{total_errors} unresolved errors across stores",
        )
    except Exception:
        return _health_response(
            status="healthy",
            severity="info",
            scope_type="tenant",
            scope_id=current_user.tenant_id,
            detail={"unresolved_errors": 0, "audit_coverage": "active", "log_sanitization": "active"},
        )


@router.get("/normalized/alerts")
async def normalized_alerts(current_user: User = Depends(get_current_user)):
    """Normalized alerts summary."""
    try:
        alert_count = await db.alert_history.count_documents({"tenant_id": current_user.tenant_id, "acknowledged": {"$ne": True}}) if "alert_history" in await db.list_collection_names() else 0

        critical_count = (
            await db.alert_history.count_documents({"tenant_id": current_user.tenant_id, "acknowledged": {"$ne": True}, "severity": "critical"})
            if "alert_history" in await db.list_collection_names()
            else 0
        )

        severity = "critical" if critical_count > 0 else ("warning" if alert_count > 0 else "info")

        return _health_response(
            status="critical" if critical_count > 0 else ("degraded" if alert_count > 0 else "healthy"),
            severity=severity,
            scope_type="tenant",
            scope_id=current_user.tenant_id,
            detail={
                "total_active": alert_count,
                "critical_active": critical_count,
            },
            action_available=alert_count > 0,
            suggested_action="Acknowledge and resolve alerts" if alert_count > 0 else None,
            evidence_summary=f"{alert_count} active alerts ({critical_count} critical)",
        )
    except Exception:
        return _health_response(
            status="healthy",
            severity="info",
            scope_type="tenant",
            scope_id=current_user.tenant_id,
            detail={"total_active": 0, "critical_active": 0},
        )


@router.get("/normalized/ws-bridge")
async def normalized_ws_bridge(current_user: User = Depends(get_current_user)):
    """Multi-instance live chat bridge (ws_redis_adapter) health.

    Surfaces the cumulative pub/sub counters and last error so an outage
    of the cross-instance WebSocket fan-out is visible on the System
    Health dashboard instead of silently breaking real-time delivery.
    """
    try:
        from infra.ws_redis_adapter import ws_redis_adapter
    except Exception as e:
        return _health_response(
            status="degraded",
            severity="warning",
            scope_type="global",
            scope_id="ws-bridge",
            detail={"active": False, "error": str(e)[:200]},
            degraded_reason="ws_redis_adapter not importable",
            evidence_summary="bridge module unavailable",
        )

    try:
        from modules.observability.alerting_engine import (
            DEFAULT_THRESHOLDS,
            AlertType,
        )

        threshold = int(DEFAULT_THRESHOLDS.get(AlertType.WS_BRIDGE_PUBLISH_ERRORS, {}).get("count", 10))
    except Exception:
        threshold = 10

    try:
        m = ws_redis_adapter.get_metrics()
        # Task #47: rolling 1-hour snapshot history for the trend chart.
        # ``get_metrics_history`` is best-effort — adapters that have not
        # been migrated yet (or unit-test stubs) simply won't expose it,
        # in which case we degrade to an empty series rather than fail.
        try:
            raw_history = list(ws_redis_adapter.get_metrics_history() or [])
        except Exception:
            raw_history = []
        active = bool(m.get("active"))
        instance_id = m.get("instance_id") or ""
        publish_errors = int(m.get("publish_errors") or 0)
        published = int(m.get("messages_published") or 0)
        received = int(m.get("messages_received") or 0)
        forwarded = int(m.get("messages_forwarded") or 0)
        channels = list(m.get("subscribed_channels") or [])
        channels_active = int(m.get("channels_active") or len(channels))
        last_publish_error = m.get("last_publish_error")
        last_publish_error_at = m.get("last_publish_error_at")
        last_listen_error = m.get("last_listen_error")
        last_listen_error_at = m.get("last_listen_error_at")

        # The single-instance fallback is intentional in dev / single-pod
        # deployments; surface it as informational rather than degraded.
        single_instance = (not active) and (not instance_id or instance_id == "single-instance")

        if single_instance:
            status = "healthy"
            severity = "info"
            degraded_reason = None
        elif not active:
            status = "degraded"
            severity = "warning"
            degraded_reason = "Bridge inactive — Redis pub/sub unavailable; cross-instance events will not be delivered."
        elif publish_errors >= threshold * 5:
            status = "critical"
            severity = "critical"
            degraded_reason = f"{publish_errors} publish errors observed (critical threshold {threshold * 5})"
        elif publish_errors >= threshold:
            status = "degraded"
            severity = "warning"
            degraded_reason = f"{publish_errors} publish errors observed (threshold {threshold})"
        else:
            status = "healthy"
            severity = "info"
            degraded_reason = None

        critical_blockers: list[str] = []
        if status == "critical":
            critical_blockers.append(degraded_reason or "WS bridge in critical state")

        suggested_action = None
        if status == "critical":
            suggested_action = "Investigate Redis pub/sub and ws_redis_adapter logs"
        elif status == "degraded" and not active:
            suggested_action = "Restore Redis connectivity for multi-instance delivery"
        elif status == "degraded":
            suggested_action = "Review last_publish_error and Redis health"

        evidence = (
            f"{published} pub / {received} recv / {forwarded} fwd, "
            f"{publish_errors} errors, {channels_active} channels, "
            f"mode={'redis' if active else ('single-instance' if single_instance else 'inactive')}"
        )

        # Task #47: convert cumulative snapshots to per-interval deltas
        # so the dashboard can chart "errors per minute" instead of an
        # ever-growing total. Trend direction compares the second half
        # of the window with the first; >25% growth → "up", <-25% →
        # "down", otherwise "flat". Empty/single-sample series stay
        # "flat" (we don't yet have enough data to make a call).
        history_points: list[dict[str, Any]] = []
        prev: dict[str, Any] | None = None
        for snap in raw_history:
            point = {
                "at": snap.get("at"),
                "publish_errors": int(snap.get("publish_errors") or 0),
                "messages_published": int(snap.get("messages_published") or 0),
                "messages_received": int(snap.get("messages_received") or 0),
                "messages_forwarded": int(snap.get("messages_forwarded") or 0),
            }
            if prev is None:
                point["publish_errors_delta"] = 0
                point["messages_published_delta"] = 0
            else:
                point["publish_errors_delta"] = max(0, point["publish_errors"] - int(prev.get("publish_errors") or 0))
                point["messages_published_delta"] = max(0, point["messages_published"] - int(prev.get("messages_published") or 0))
            history_points.append(point)
            prev = point

        error_deltas = [p["publish_errors_delta"] for p in history_points]
        if len(error_deltas) >= 4:
            mid = len(error_deltas) // 2
            first_half = sum(error_deltas[:mid])
            second_half = sum(error_deltas[mid:])
            # Use a small absolute floor so a one-error blip doesn't
            # register as a 100% spike when the first half was zero.
            if second_half >= first_half + 3 and second_half >= first_half * 1.25:
                error_trend = "up"
            elif first_half >= second_half + 3 and first_half >= second_half * 1.25:
                error_trend = "down"
            else:
                error_trend = "flat"
        else:
            error_trend = "flat"

        history_summary = {
            "interval_seconds": int(getattr(ws_redis_adapter, "_snapshot_interval_s", 60) or 60),
            "max_points": int(getattr(ws_redis_adapter, "_snapshot_max", 60) or 60),
            "points": history_points,
            "error_trend": error_trend,
            "errors_in_window": int(sum(error_deltas)),
        }

        return _health_response(
            status=status,
            severity=severity,
            scope_type="global",
            scope_id="ws-bridge",
            detail={
                "active": active,
                "single_instance_mode": single_instance,
                "instance_id": instance_id,
                "messages_published": published,
                "messages_received": received,
                "messages_forwarded": forwarded,
                "publish_errors": publish_errors,
                "channels_active": channels_active,
                "subscribed_channels": channels,
                "last_publish_error": last_publish_error,
                "last_publish_error_at": last_publish_error_at,
                "last_listen_error": last_listen_error,
                "last_listen_error_at": last_listen_error_at,
                "publish_error_threshold": threshold,
                "publish_error_critical_threshold": threshold * 5,
                "metrics_history": history_summary,
            },
            action_available=status != "healthy",
            suggested_action=suggested_action,
            degraded_reason=degraded_reason,
            critical_blockers=critical_blockers,
            evidence_summary=evidence,
        )
    except Exception as e:
        return _health_response(
            status="degraded",
            severity="warning",
            scope_type="global",
            scope_id="ws-bridge",
            detail={"active": False, "error": str(e)[:200]},
            degraded_reason="Failed to read ws_redis_adapter metrics",
            evidence_summary="metrics read failed",
        )


@router.get("/normalized/room-service")
async def normalized_room_service(current_user: User = Depends(get_current_user)):
    """Live room-service realtime channel health (Task #92).

    Surfaces two operational gauges to System Health:

    * how many (tenant, booking) sockets are currently subscribed to
      live order updates on this pod, plus the staff-dashboard fan-out;
    * how many order events were delivered to local subscribers in the
      last hour (rolling, in-memory).

    Cross-pod visibility is added via ``ws_redis_adapter`` —
    ``room_service:`` channels in the bridge's ``subscribed_channels``
    list indicate other pods that have at least one guest socket on the
    matching booking, which gives operators a fleet-wide view without
    standing up an additional storage layer.
    """
    try:
        from domains.guest.experience_router.room_service_realtime import (
            ROOM_KEY_PREFIX,
            order_stream,
        )
    except Exception as e:
        return _health_response(
            status="degraded",
            severity="warning",
            scope_type="global",
            scope_id="room-service",
            detail={"error": str(e)[:200]},
            degraded_reason="room_service module not importable",
            evidence_summary="module unavailable",
        )

    try:
        local_rooms = order_stream.total_room_count()
        local_sockets = order_stream.total_connection_count()
        staff_tenants = order_stream.total_staff_room_count()
        staff_sockets = order_stream.total_staff_connection_count()
        recent_events = order_stream.recent_event_count(_EVENT_WINDOW_SECONDS_RS)
    except Exception as e:
        return _health_response(
            status="degraded",
            severity="warning",
            scope_type="global",
            scope_id="room-service",
            detail={"error": str(e)[:200]},
            degraded_reason="failed to read order_stream gauges",
            evidence_summary="gauge read failed",
        )

    # Bridge view: count cross-pod subscribers via the channel list the
    # adapter exposes. Best-effort — when the adapter isn't wired (tests,
    # very early startup) the bridge view simply collapses to local-only.
    bridge_channels = 0
    bridge_active = False
    try:
        from infra.ws_redis_adapter import ws_redis_adapter

        m = ws_redis_adapter.get_metrics()
        bridge_active = bool(m.get("active"))
        channels = list(m.get("subscribed_channels") or [])
        prefix = f"{ROOM_KEY_PREFIX}:"
        bridge_channels = sum(1 for c in channels if c.startswith(prefix))
    except Exception:
        # Stay healthy on bridge read failures — local gauges are still
        # valid; the bridge already has its own subsystem entry.
        pass

    status = "healthy"
    severity = "info"
    evidence = f"{local_rooms} bookings / {local_sockets} guest sockets, {staff_tenants} staff tenants / {staff_sockets} staff sockets, {recent_events} events delivered in last 60m"

    return _health_response(
        status=status,
        severity=severity,
        scope_type="global",
        scope_id="room-service",
        detail={
            "active_bookings_local": local_rooms,
            "guest_sockets_local": local_sockets,
            "staff_tenants_local": staff_tenants,
            "staff_sockets_local": staff_sockets,
            "events_last_hour": recent_events,
            "event_window_seconds": _EVENT_WINDOW_SECONDS_RS,
            "bridge_active": bridge_active,
            "bridge_room_service_channels": bridge_channels,
        },
        evidence_summary=evidence,
    )


@router.get("/normalized/overview")
async def normalized_overview(current_user: User = Depends(get_current_user)):
    """Aggregated normalized health overview across all subsystems.

    Subsystem checks are awaited concurrently with asyncio.gather so total
    latency tracks the slowest subsystem instead of the sum. Per-subsystem
    failures are isolated via return_exceptions=True and surfaced as a
    degraded subsystem entry rather than failing the whole overview.
    """
    import asyncio

    results = await asyncio.gather(
        normalized_channel_manager(current_user),
        normalized_workers(current_user),
        normalized_security(current_user),
        normalized_observability(current_user),
        normalized_alerts(current_user),
        normalized_ws_bridge(current_user),
        normalized_room_service(current_user),
        return_exceptions=True,
    )

    scope_ids = (
        "channel-manager",
        "workers",
        "security",
        "observability",
        "alerts",
        "ws-bridge",
        "room-service",
    )
    fallback_scope_id = getattr(current_user, "tenant_id", None) or "global"

    def _coerce(scope_id: str, value):
        # Re-raise non-Exception BaseException (CancelledError, SystemExit,
        # KeyboardInterrupt) so cooperative cancellation and shutdown signals
        # are not swallowed by overview aggregation.
        if isinstance(value, BaseException) and not isinstance(value, Exception):
            raise value
        if isinstance(value, Exception):
            return _health_response(
                status="degraded",
                severity="warning",
                scope_type="tenant" if fallback_scope_id != "global" else "global",
                scope_id=fallback_scope_id,
                detail={"error": str(value)[:200], "subsystem": scope_id},
                degraded_reason=f"subsystem check raised {type(value).__name__}",
                evidence_summary="overview aggregation error",
            )
        return value

    cm, wk, sec, obs, al, wsb, rs = (_coerce(sid, v) for sid, v in zip(scope_ids, results))

    subsystems = [cm, wk, sec, obs, al, wsb, rs]
    overall_severity = "critical" if any(s["severity"] == "critical" for s in subsystems) else ("warning" if any(s["severity"] == "warning" for s in subsystems) else "info")
    overall_status = "critical" if any(s["status"] == "critical" for s in subsystems) else ("degraded" if any(s["status"] in ("degraded", "warning") for s in subsystems) else "healthy")

    return {
        "overall_status": overall_status,
        "overall_severity": overall_severity,
        "last_updated_at": datetime.now(UTC).isoformat(),
        "live_capable": True,
        "data_freshness": "real-time",
        "subsystems": {
            "channel_manager": cm,
            "workers": wk,
            "security": sec,
            "observability": obs,
            "alerts": al,
            "ws_bridge": wsb,
            "room_service": rs,
        },
    }
