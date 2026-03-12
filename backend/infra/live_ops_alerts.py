"""
Live Ops Alert Integration — Production alert management with webhook delivery,
severity mapping, cooldown/dedup, runbook hints, and PagerDuty/Slack abstraction.
"""
import os
import logging
import time
import hashlib
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from collections import defaultdict

logger = logging.getLogger("infra.live_ops_alerts")


class AlertSeverity:
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


ALERT_DEFINITIONS = {
    "readiness_blocker": {
        "severity": AlertSeverity.CRITICAL,
        "description": "Production readiness has blockers",
        "runbook": "Check /production-golive dashboard. Fix all blocker items before launch.",
        "cooldown_sec": 300,
    },
    "provider_connection_failure": {
        "severity": AlertSeverity.HIGH,
        "description": "External provider connection test failed",
        "runbook": "Verify provider credentials in environment. Run provider test from dashboard.",
        "cooldown_sec": 600,
    },
    "redis_disconnected": {
        "severity": AlertSeverity.HIGH,
        "description": "Redis connection lost",
        "runbook": "Check REDIS_URL env var. Verify Redis server is running. Check network connectivity.",
        "cooldown_sec": 120,
    },
    "tracing_export_failure": {
        "severity": AlertSeverity.MEDIUM,
        "description": "OpenTelemetry trace export failing",
        "runbook": "Verify OTEL_EXPORTER_ENDPOINT. Check collector health. Review network rules.",
        "cooldown_sec": 600,
    },
    "backup_readiness_failure": {
        "severity": AlertSeverity.HIGH,
        "description": "Backup system not ready for production",
        "runbook": "Enable BACKUP_ENABLED=true. Verify mongodump availability. Check backup path permissions.",
        "cooldown_sec": 3600,
    },
    "config_blocker": {
        "severity": AlertSeverity.CRITICAL,
        "description": "Critical configuration missing for production boot",
        "runbook": "Set all required env vars: MONGO_URL, JWT_SECRET, DB_NAME.",
        "cooldown_sec": 300,
    },
    "security_score_low": {
        "severity": AlertSeverity.HIGH,
        "description": "Security checklist score below threshold",
        "runbook": "Run security checklist. Fix failed checks: RBAC, tenant isolation, credential masking.",
        "cooldown_sec": 1800,
    },
    "prelaunch_validation_failed": {
        "severity": AlertSeverity.CRITICAL,
        "description": "Pre-launch validation returned NOT_READY",
        "runbook": "Run pre-launch validation. Fix all blocker steps before proceeding.",
        "cooldown_sec": 300,
    },
}

# Webhook destinations
WEBHOOK_TARGETS = {
    "default": os.environ.get("OPS_WEBHOOK_URL", ""),
    "pagerduty": os.environ.get("PAGERDUTY_WEBHOOK_URL", ""),
    "slack": os.environ.get("SLACK_WEBHOOK_URL", ""),
}


class LiveOpsAlertManager:
    """Manages production alerts with dedup, cooldown, and webhook delivery."""

    def __init__(self):
        self._alert_history: List[Dict[str, Any]] = []
        self._max_history = 500
        self._last_fired: Dict[str, float] = {}  # alert_type -> last_fired_timestamp
        self._suppressed_count: Dict[str, int] = defaultdict(int)
        self._delivery_log: List[Dict[str, Any]] = []

    def _dedup_key(self, alert_type: str, context: Dict[str, Any]) -> str:
        """Generate dedup key for an alert."""
        ctx_str = str(sorted(context.items())) if context else ""
        return hashlib.md5(f"{alert_type}:{ctx_str}".encode()).hexdigest()

    def _is_cooled_down(self, alert_type: str) -> bool:
        """Check if alert is in cooldown period."""
        defn = ALERT_DEFINITIONS.get(alert_type, {})
        cooldown = defn.get("cooldown_sec", 60)
        last = self._last_fired.get(alert_type, 0)
        return (time.time() - last) < cooldown

    async def fire_alert(self, alert_type: str, context: Optional[Dict[str, Any]] = None,
                         user_id: str = "system") -> Dict[str, Any]:
        """Fire a production alert with dedup and cooldown."""
        context = context or {}
        defn = ALERT_DEFINITIONS.get(alert_type, {
            "severity": AlertSeverity.MEDIUM,
            "description": alert_type,
            "runbook": "No runbook available",
            "cooldown_sec": 60,
        })

        # Cooldown check
        if self._is_cooled_down(alert_type):
            self._suppressed_count[alert_type] += 1
            return {
                "status": "suppressed",
                "reason": "cooldown",
                "alert_type": alert_type,
                "suppressed_count": self._suppressed_count[alert_type],
            }

        alert = {
            "alert_id": f"alert_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{alert_type}",
            "alert_type": alert_type,
            "severity": defn["severity"],
            "description": defn["description"],
            "runbook": defn.get("runbook", ""),
            "context": context,
            "fired_at": datetime.now(timezone.utc).isoformat(),
            "fired_by": user_id,
            "delivered_to": [],
        }

        self._last_fired[alert_type] = time.time()

        # Webhook delivery
        delivery_results = await self._deliver_webhook(alert)
        alert["delivered_to"] = delivery_results

        self._alert_history.append(alert)
        if len(self._alert_history) > self._max_history:
            self._alert_history = self._alert_history[-self._max_history:]

        return {"status": "fired", "alert": alert}

    async def _deliver_webhook(self, alert: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Deliver alert to configured webhook targets."""
        results = []
        for target_name, url in WEBHOOK_TARGETS.items():
            if not url:
                continue

            payload = {
                "alert_id": alert["alert_id"],
                "severity": alert["severity"],
                "description": alert["description"],
                "context": alert["context"],
                "fired_at": alert["fired_at"],
                "runbook": alert.get("runbook", ""),
                "source": "syroce-pms-golive",
            }

            # Adapt payload for specific targets
            if target_name == "slack":
                payload = {
                    "text": f":rotating_light: *{alert['severity'].upper()}* — {alert['description']}",
                    "blocks": [
                        {"type": "section", "text": {"type": "mrkdwn",
                            "text": f"*Alert:* {alert['description']}\n*Severity:* {alert['severity']}\n*Runbook:* {alert.get('runbook', 'N/A')}"}},
                    ],
                }
            elif target_name == "pagerduty":
                payload = {
                    "routing_key": os.environ.get("PAGERDUTY_ROUTING_KEY", ""),
                    "event_action": "trigger",
                    "payload": {
                        "summary": alert["description"],
                        "severity": alert["severity"],
                        "source": "syroce-pms",
                        "custom_details": alert["context"],
                    },
                }

            delivery = {"target": target_name, "url_prefix": url[:30] + "...", "status": "pending"}
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.post(url, json=payload)
                    delivery["status"] = "delivered" if resp.status_code < 400 else "failed"
                    delivery["http_status"] = resp.status_code
            except ImportError:
                delivery["status"] = "skipped"
                delivery["reason"] = "httpx not installed"
            except Exception as e:
                delivery["status"] = "failed"
                delivery["error"] = str(e)[:100]

            results.append(delivery)
            self._delivery_log.append({**delivery, "alert_id": alert["alert_id"],
                                        "timestamp": datetime.now(timezone.utc).isoformat()})

        return results

    def get_alert_history(self, limit: int = 50, severity: Optional[str] = None) -> List[Dict[str, Any]]:
        alerts = self._alert_history
        if severity:
            alerts = [a for a in alerts if a.get("severity") == severity]
        return alerts[-limit:]

    def get_alert_summary(self) -> Dict[str, Any]:
        by_severity = defaultdict(int)
        by_type = defaultdict(int)
        for a in self._alert_history:
            by_severity[a.get("severity", "unknown")] += 1
            by_type[a.get("alert_type", "unknown")] += 1

        return {
            "total_alerts": len(self._alert_history),
            "by_severity": dict(by_severity),
            "by_type": dict(by_type),
            "suppressed": dict(self._suppressed_count),
            "webhook_targets_configured": sum(1 for u in WEBHOOK_TARGETS.values() if u),
            "last_alert": self._alert_history[-1] if self._alert_history else None,
        }

    def get_delivery_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self._delivery_log[-limit:]

    def get_definitions(self) -> Dict[str, Any]:
        return {k: {**v, "type": k} for k, v in ALERT_DEFINITIONS.items()}


# Singleton
live_ops_alerts = LiveOpsAlertManager()
