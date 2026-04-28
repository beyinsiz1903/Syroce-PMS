"""
Production Alerting Engine.
Threshold-based operational alerts with dedup, cooldown, severity mapping,
and integration with observability metrics.
"""
import logging
from collections import defaultdict
from datetime import UTC, datetime, timedelta

from core.database import db

logger = logging.getLogger("alerting.engine")


class AlertSeverity:
    CRITICAL = "critical"
    HIGH = "high"
    WARNING = "warning"
    INFO = "info"


class AlertType:
    REDIS_DISCONNECTED = "redis_disconnected"
    EVENT_DROP_SPIKE = "event_drop_spike"
    WEBSOCKET_FAILURE_SPIKE = "websocket_failure_spike"
    MESSAGING_FAILURE_SPIKE = "messaging_failure_spike"
    PROVIDER_CREDENTIAL_INVALID = "provider_credential_invalid"
    SLOW_ENDPOINT_BREACH = "slow_endpoint_breach"
    MODEL_RUN_TIMEOUT = "model_run_timeout"
    STALE_DATASET = "stale_dataset"
    EXPORT_QUEUE_BACKLOG = "export_queue_backlog"
    ABNORMAL_RETRY_BURST = "abnormal_retry_burst"
    HIGH_ERROR_RATE = "high_error_rate"
    DB_CONNECTION_ISSUE = "db_connection_issue"
    WS_BRIDGE_PUBLISH_ERRORS = "ws_bridge_publish_errors"
    WS_BRIDGE_INACTIVE = "ws_bridge_inactive"


# Alert thresholds
DEFAULT_THRESHOLDS = {
    AlertType.EVENT_DROP_SPIKE: {"count": 50, "window_minutes": 5},
    AlertType.WEBSOCKET_FAILURE_SPIKE: {"count": 20, "window_minutes": 5},
    AlertType.MESSAGING_FAILURE_SPIKE: {"count": 10, "window_minutes": 15},
    AlertType.SLOW_ENDPOINT_BREACH: {"threshold_ms": 2000, "count": 5, "window_minutes": 5},
    AlertType.MODEL_RUN_TIMEOUT: {"timeout_minutes": 30},
    AlertType.STALE_DATASET: {"stale_hours": 48},
    AlertType.EXPORT_QUEUE_BACKLOG: {"max_pending": 20},
    AlertType.ABNORMAL_RETRY_BURST: {"count": 50, "window_minutes": 10},
    AlertType.HIGH_ERROR_RATE: {"rate": 0.05, "min_requests": 100},
    AlertType.WS_BRIDGE_PUBLISH_ERRORS: {"count": 10, "delta_count": 5, "window_minutes": 15},
    AlertType.WS_BRIDGE_INACTIVE: {},
}

# Severity mapping per alert type
SEVERITY_MAP = {
    AlertType.REDIS_DISCONNECTED: AlertSeverity.HIGH,
    AlertType.EVENT_DROP_SPIKE: AlertSeverity.HIGH,
    AlertType.WEBSOCKET_FAILURE_SPIKE: AlertSeverity.WARNING,
    AlertType.MESSAGING_FAILURE_SPIKE: AlertSeverity.HIGH,
    AlertType.PROVIDER_CREDENTIAL_INVALID: AlertSeverity.CRITICAL,
    AlertType.SLOW_ENDPOINT_BREACH: AlertSeverity.WARNING,
    AlertType.MODEL_RUN_TIMEOUT: AlertSeverity.WARNING,
    AlertType.STALE_DATASET: AlertSeverity.INFO,
    AlertType.EXPORT_QUEUE_BACKLOG: AlertSeverity.WARNING,
    AlertType.ABNORMAL_RETRY_BURST: AlertSeverity.HIGH,
    AlertType.HIGH_ERROR_RATE: AlertSeverity.CRITICAL,
    AlertType.DB_CONNECTION_ISSUE: AlertSeverity.CRITICAL,
    AlertType.WS_BRIDGE_PUBLISH_ERRORS: AlertSeverity.HIGH,
    AlertType.WS_BRIDGE_INACTIVE: AlertSeverity.WARNING,
}

# Runbook hints
RUNBOOK_HINTS = {
    AlertType.REDIS_DISCONNECTED: "Check REDIS_URL env var. Verify Redis server is running. Check network connectivity.",
    AlertType.EVENT_DROP_SPIKE: "Check event bus backend health. Review backpressure settings. Scale Redis if needed.",
    AlertType.WEBSOCKET_FAILURE_SPIKE: "Check WebSocket server health. Review connection limits. Check client-side errors.",
    AlertType.MESSAGING_FAILURE_SPIKE: "Check provider credentials. Review rate limits. Check provider status page.",
    AlertType.PROVIDER_CREDENTIAL_INVALID: "Rotate provider credentials via credential vault. Verify API keys are active.",
    AlertType.SLOW_ENDPOINT_BREACH: "Review endpoint performance. Check DB query efficiency. Consider caching.",
    AlertType.MODEL_RUN_TIMEOUT: "Check ML pipeline status. Review model complexity. Increase timeout if needed.",
    AlertType.STALE_DATASET: "Trigger data pipeline refresh. Check pipeline scheduler. Verify data sources.",
    AlertType.EXPORT_QUEUE_BACKLOG: "Check export worker status. Scale export processing. Review queue consumers.",
    AlertType.ABNORMAL_RETRY_BURST: "Check messaging providers. Review retry policies. Investigate root cause.",
    AlertType.HIGH_ERROR_RATE: "Check application logs. Review recent deployments. Investigate error patterns.",
    AlertType.DB_CONNECTION_ISSUE: "Check MongoDB connection. Review connection pool settings. Check disk space.",
    AlertType.WS_BRIDGE_PUBLISH_ERRORS: (
        "Multi-instance live chat bridge is failing to publish to Redis. "
        "Check REDIS_URL connectivity, Redis pub/sub health, and "
        "ws_redis_adapter.get_metrics() for last_publish_error details."
    ),
    AlertType.WS_BRIDGE_INACTIVE: (
        "Multi-instance live chat bridge is running in local-only mode. "
        "Cross-instance WebSocket events will not be delivered. "
        "Verify Redis is reachable on startup."
    ),
}


class ProductionAlertEngine:
    """Production alerting engine with dedup, cooldown, and threshold evaluation."""

    def __init__(self):
        self._cooldowns: dict[str, datetime] = {}
        self._cooldown_minutes = 15  # Minimum time between same alert type
        self._alert_counts: dict[str, int] = defaultdict(int)
        self._suppressed_count = 0
        self._active_alerts: list[dict] = []
        # Baselines used to compute deltas between evaluations (e.g., for the
        # WS Redis bridge, where only the cumulative `publish_errors` counter
        # is exposed). Allows the alert to re-fire when new failures occur
        # after the cooldown without spamming on a stale total.
        self._baselines: dict[str, int] = {}

    async def evaluate_all(self) -> list[dict]:
        """Run all threshold checks and generate alerts."""
        alerts = []

        # 1. Redis disconnected
        try:
            from modules.event_bus.abstraction import event_bus
            status = await event_bus.get_status()
            if status.get("mode") == "redis" and status.get("backend_status") != "healthy":
                alert = await self._fire_alert(
                    AlertType.REDIS_DISCONNECTED,
                    "Redis Event Bus Disconnected",
                    f"Redis backend status: {status.get('backend_status')}",
                    context={"backend_details": status.get("backend_details", {})},
                )
                if alert:
                    alerts.append(alert)
        except Exception:
            logger.warning("alerting: redis_disconnected check failed", exc_info=True)

        # 2. Event drop spike
        try:
            from modules.event_bus.abstraction import event_bus
            metrics = await event_bus.get_metrics()
            dropped = metrics.get("total_dropped", 0)
            if dropped > DEFAULT_THRESHOLDS[AlertType.EVENT_DROP_SPIKE]["count"]:
                alert = await self._fire_alert(
                    AlertType.EVENT_DROP_SPIKE,
                    "Event Drop Spike Detected",
                    f"Total dropped events: {dropped}",
                    context={"dropped": dropped, "total_errors": metrics.get("total_errors", 0)},
                )
                if alert:
                    alerts.append(alert)
        except Exception:
            logger.warning("alerting: event_drop_spike check failed", exc_info=True)

        # 3. Messaging failure spike
        try:
            one_hour_ago = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
            msg_failures = await db.messaging_delivery_logs.count_documents({
                "status": "failed",
                "created_at": {"$gte": one_hour_ago},
            })
            threshold = DEFAULT_THRESHOLDS[AlertType.MESSAGING_FAILURE_SPIKE]["count"]
            if msg_failures > threshold:
                alert = await self._fire_alert(
                    AlertType.MESSAGING_FAILURE_SPIKE,
                    "Messaging Failure Spike",
                    f"{msg_failures} failed deliveries in the last hour",
                    context={"failure_count": msg_failures},
                )
                if alert:
                    alerts.append(alert)
        except Exception:
            logger.warning("alerting: messaging_failure_spike check failed", exc_info=True)

        # 4. Slow endpoint breach
        try:
            from modules.observability.metrics_collector import metrics as obs_metrics
            all_metrics = obs_metrics.get_all_metrics()
            for key, summary in all_metrics.get("histograms", {}).items():
                if "http_request_duration_ms" in key and summary.get("p95", 0) > 2000:
                    alert = await self._fire_alert(
                        AlertType.SLOW_ENDPOINT_BREACH,
                        "Slow Endpoint Detected",
                        f"Endpoint {key} p95 latency: {summary.get('p95')}ms",
                        context={"endpoint": key, "p95_ms": summary.get("p95")},
                    )
                    if alert:
                        alerts.append(alert)
                    break  # Only one slow endpoint alert per evaluation
        except Exception:
            logger.warning("alerting: slow_endpoint_breach check failed", exc_info=True)

        # 5. High error rate
        try:
            one_hour_ago = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
            error_count = await db.observability_errors.count_documents({
                "timestamp": {"$gte": one_hour_ago},
                "severity": {"$in": ["critical", "high"]},
            })
            if error_count > 10:
                alert = await self._fire_alert(
                    AlertType.HIGH_ERROR_RATE,
                    "High Error Rate",
                    f"{error_count} critical/high errors in the last hour",
                    context={"error_count": error_count},
                )
                if alert:
                    alerts.append(alert)
        except Exception:
            logger.warning("alerting: high_error_rate check failed", exc_info=True)

        # 6. Abnormal retry burst
        try:
            retry_burst = await db.messaging_delivery_logs.count_documents({
                "status": "failed",
                "retry_count": {"$gte": 2},
                "created_at": {"$gte": (datetime.now(UTC) - timedelta(minutes=10)).isoformat()},
            })
            if retry_burst > DEFAULT_THRESHOLDS[AlertType.ABNORMAL_RETRY_BURST]["count"]:
                alert = await self._fire_alert(
                    AlertType.ABNORMAL_RETRY_BURST,
                    "Abnormal Retry Burst",
                    f"{retry_burst} messages with 2+ retries in 10 minutes",
                    context={"retry_burst_count": retry_burst},
                )
                if alert:
                    alerts.append(alert)
        except Exception:
            logger.warning("alerting: abnormal_retry_burst check failed", exc_info=True)

        # 7. Multi-instance live chat (WS Redis bridge) health
        try:
            from infra.ws_redis_adapter import ws_redis_adapter

            ws_metrics = ws_redis_adapter.get_metrics()
            instance_id = ws_metrics.get("instance_id") or ""
            active = bool(ws_metrics.get("active"))
            publish_errors = int(ws_metrics.get("publish_errors") or 0)

            # Only treat "inactive" as alert-worthy when a multi-instance
            # deployment was actually intended (instance_id is set and is
            # not the single-instance fallback marker).
            if not active and instance_id and instance_id != "single-instance":
                alert = await self._fire_alert(
                    AlertType.WS_BRIDGE_INACTIVE,
                    "Multi-Instance Chat Bridge Inactive",
                    "ws_redis_adapter is not active — cross-instance "
                    "WebSocket events will not be delivered.",
                    context={
                        "instance_id": instance_id,
                        "subscribed_channels": ws_metrics.get("subscribed_channels", []),
                    },
                )
                if alert:
                    alerts.append(alert)

            cfg = DEFAULT_THRESHOLDS[AlertType.WS_BRIDGE_PUBLISH_ERRORS]
            threshold = int(cfg["count"])
            delta_threshold = int(cfg.get("delta_count", threshold))
            baseline = int(self._baselines.get("ws_bridge_publish_errors", 0))

            # Counter is in-memory in ws_redis_adapter, so a process restart
            # (or reinitialise) drops it back toward zero. If the live counter
            # is below our stored baseline, the adapter clearly reset — drop
            # the baseline so we can detect the next threshold crossing
            # immediately instead of waiting for it to climb past the old
            # high-water mark.
            if publish_errors < baseline:
                baseline = 0
                self._baselines["ws_bridge_publish_errors"] = 0

            delta = publish_errors - baseline

            # Fire when either the absolute counter crosses the threshold
            # for the first time, or when new failures (delta) accumulate
            # past the per-window threshold AFTER an earlier fire.
            should_fire = (
                publish_errors >= threshold and baseline == 0
            ) or (
                baseline > 0
                and delta_threshold > 0
                and delta >= delta_threshold
            )

            if should_fire:
                alert = await self._fire_alert(
                    AlertType.WS_BRIDGE_PUBLISH_ERRORS,
                    "Multi-Instance Chat Bridge Publish Errors",
                    f"WS Redis bridge has {publish_errors} publish errors "
                    f"(+{delta} since last alert).",
                    context={
                        "publish_errors": publish_errors,
                        "delta": delta,
                        "messages_published": ws_metrics.get("messages_published", 0),
                        "messages_received": ws_metrics.get("messages_received", 0),
                        "messages_forwarded": ws_metrics.get("messages_forwarded", 0),
                        "channels_active": ws_metrics.get("channels_active", 0),
                        "active": active,
                        "instance_id": instance_id,
                        "last_publish_error": ws_metrics.get("last_publish_error"),
                        "last_publish_error_at": ws_metrics.get("last_publish_error_at"),
                        "threshold": threshold,
                        "delta_threshold": delta_threshold,
                    },
                )
                if alert:
                    alerts.append(alert)
                    self._baselines["ws_bridge_publish_errors"] = publish_errors
        except Exception:
            logger.warning("alerting: ws_bridge check failed", exc_info=True)

        # 8. DB connection check
        try:
            await db.command("ping")
        except Exception as e:
            alert = await self._fire_alert(
                AlertType.DB_CONNECTION_ISSUE,
                "Database Connection Issue",
                f"MongoDB ping failed: {str(e)[:200]}",
                context={"error": str(e)[:200]},
            )
            if alert:
                alerts.append(alert)

        self._active_alerts = alerts
        return alerts

    async def _fire_alert(self, alert_type: str, title: str, message: str,
                          context: dict = None) -> dict | None:
        """Fire an alert with dedup and cooldown."""
        # Cooldown check
        last_fired = self._cooldowns.get(alert_type)
        if last_fired:
            cooldown_until = last_fired + timedelta(minutes=self._cooldown_minutes)
            if datetime.now(UTC) < cooldown_until:
                self._suppressed_count += 1
                return None

        severity = SEVERITY_MAP.get(alert_type, AlertSeverity.WARNING)
        runbook = RUNBOOK_HINTS.get(alert_type, "")

        alert_doc = {
            "id": str(__import__("uuid").uuid4()),
            "alert_type": alert_type,
            "severity": severity,
            "title": title,
            "message": message,
            "context": context or {},
            "runbook_hint": runbook,
            "acknowledged": False,
            "created_at": datetime.now(UTC).isoformat(),
        }

        # Persist to MongoDB
        try:
            await db.alert_history.insert_one({**alert_doc})
        except Exception as e:
            logger.error(f"Failed to persist alert: {e}")

        # Update cooldown
        self._cooldowns[alert_type] = datetime.now(UTC)
        self._alert_counts[alert_type] += 1

        logger.warning(f"ALERT [{severity.upper()}] {title}: {message}")

        # Best-effort fan-out to configured notification channels
        # (Slack/email). Failures here must never break alert evaluation —
        # the dashboard record is already persisted above and remains the
        # source of truth.
        try:
            from domains.channel_manager.monitoring.alert_dispatch import (
                dispatch_alert,
            )
            await dispatch_alert(alert_doc)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "alerting: notification dispatch failed for %s: %s",
                alert_type, exc,
            )

        return {k: v for k, v in alert_doc.items() if k != "_id"}

    async def get_alert_candidates(self) -> list[dict]:
        """Get recent unacknowledged alerts."""
        return await db.alert_history.find(
            {"acknowledged": False},
            {"_id": 0},
        ).sort("created_at", -1).to_list(50)

    async def get_alert_history(self, hours: int = 24, limit: int = 100) -> list[dict]:
        cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
        return await db.alert_history.find(
            {"created_at": {"$gte": cutoff}},
            {"_id": 0},
        ).sort("created_at", -1).to_list(limit)

    async def acknowledge_alert(self, alert_id: str, user_id: str) -> dict:
        await db.alert_history.update_one(
            {"id": alert_id},
            {"$set": {
                "acknowledged": True,
                "acknowledged_by": user_id,
                "acknowledged_at": datetime.now(UTC).isoformat(),
            }},
        )
        return {"id": alert_id, "acknowledged": True}

    def get_engine_status(self) -> dict:
        return {
            "active_alerts": len(self._active_alerts),
            "alert_counts": dict(self._alert_counts),
            "suppressed_by_cooldown": self._suppressed_count,
            "cooldown_minutes": self._cooldown_minutes,
            "thresholds": DEFAULT_THRESHOLDS,
            "timestamp": datetime.now(UTC).isoformat(),
        }


# Singleton
alert_engine = ProductionAlertEngine()
