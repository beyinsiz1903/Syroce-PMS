"""
Production Alerting Engine.
Threshold-based operational alerts with dedup, cooldown, severity mapping,
and integration with observability metrics.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from collections import defaultdict

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
}


class ProductionAlertEngine:
    """Production alerting engine with dedup, cooldown, and threshold evaluation."""

    def __init__(self):
        self._cooldowns: Dict[str, datetime] = {}
        self._cooldown_minutes = 15  # Minimum time between same alert type
        self._alert_counts: Dict[str, int] = defaultdict(int)
        self._suppressed_count = 0
        self._active_alerts: List[dict] = []

    async def evaluate_all(self) -> List[dict]:
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
            pass

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
            pass

        # 3. Messaging failure spike
        try:
            one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
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
            pass

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
            pass

        # 5. High error rate
        try:
            one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
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
            pass

        # 6. Abnormal retry burst
        try:
            retry_burst = await db.messaging_delivery_logs.count_documents({
                "status": "failed",
                "retry_count": {"$gte": 2},
                "created_at": {"$gte": (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()},
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
            pass

        # 7. DB connection check
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
                          context: dict = None) -> Optional[dict]:
        """Fire an alert with dedup and cooldown."""
        # Cooldown check
        last_fired = self._cooldowns.get(alert_type)
        if last_fired:
            cooldown_until = last_fired + timedelta(minutes=self._cooldown_minutes)
            if datetime.now(timezone.utc) < cooldown_until:
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
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        # Persist to MongoDB
        try:
            await db.alert_history.insert_one({**alert_doc})
        except Exception as e:
            logger.error(f"Failed to persist alert: {e}")

        # Update cooldown
        self._cooldowns[alert_type] = datetime.now(timezone.utc)
        self._alert_counts[alert_type] += 1

        logger.warning(f"ALERT [{severity.upper()}] {title}: {message}")

        return {k: v for k, v in alert_doc.items() if k != "_id"}

    async def get_alert_candidates(self) -> List[dict]:
        """Get recent unacknowledged alerts."""
        return await db.alert_history.find(
            {"acknowledged": False},
            {"_id": 0},
        ).sort("created_at", -1).to_list(50)

    async def get_alert_history(self, hours: int = 24, limit: int = 100) -> List[dict]:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
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
                "acknowledged_at": datetime.now(timezone.utc).isoformat(),
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
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# Singleton
alert_engine = ProductionAlertEngine()
