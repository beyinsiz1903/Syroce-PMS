"""
Alerting — Threshold-Based Operational Alerts
===============================================
Minimal but real alerting layer for the control plane.

Channels:
  1. Log-based (always active)
  2. Generic HTTP webhook (Slack-compatible payload)

Triggers:
  - Reservation import failure spike
  - Outbox stuck > threshold
  - Sync failure spike
  - Secret access anomaly
  - Provider auth failure

Design: log-based + generic HTTP webhook with Slack-compatible payload.
No Slack-specific code — when you provide a Slack webhook URL, it works.
"""
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("controlplane.alerting")

COLL_ALERTS = "cp_alerts"


class AlertSeverity:
    INFO = "info"
    WARNING = "warning"
    HIGH = "high"
    CRITICAL = "critical"


class AlertTrigger:
    IMPORT_FAILURE_SPIKE = "import_failure_spike"
    OUTBOX_STUCK = "outbox_stuck"
    SYNC_FAILURE_SPIKE = "sync_failure_spike"
    SECRET_ANOMALY = "secret_anomaly"
    PROVIDER_AUTH_FAILURE = "provider_auth_failure"
    HIGH_ERROR_RATE = "high_error_rate"
    CRYPTO_FAILURE = "crypto_failure"


# ── Thresholds ─────────────────────────────────────────────────────
DEFAULT_THRESHOLDS = {
    AlertTrigger.IMPORT_FAILURE_SPIKE: {"count": 5, "window_minutes": 30},
    AlertTrigger.OUTBOX_STUCK: {"max_stuck_minutes": 30, "max_stuck_count": 10},
    AlertTrigger.SYNC_FAILURE_SPIKE: {"count": 3, "window_minutes": 60},
    AlertTrigger.SECRET_ANOMALY: {"count": 3, "window_minutes": 60},
    AlertTrigger.PROVIDER_AUTH_FAILURE: {"count": 2, "window_minutes": 15},
    AlertTrigger.HIGH_ERROR_RATE: {"count": 20, "window_minutes": 60},
    AlertTrigger.CRYPTO_FAILURE: {"count": 1, "window_minutes": 60},
}

# Cooldown: don't re-fire the same alert within this window
ALERT_COOLDOWN_MINUTES = 15


class AlertingEngine:
    """Operational alerting engine with log + webhook channels."""

    def __init__(self):
        self._db = None
        self._webhook_url = os.environ.get("ALERT_WEBHOOK_URL", "")
        self._last_fired: Dict[str, datetime] = {}

    def _get_db(self):
        if self._db is None:
            from core.database import db
            self._db = db
        return self._db

    async def fire(
        self,
        *,
        trigger: str,
        severity: str,
        title: str,
        message: str,
        context: Optional[Dict[str, Any]] = None,
        tenant_id: Optional[str] = None,
        property_id: Optional[str] = None,
        provider: Optional[str] = None,
        runbook_link: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Fire an alert if not in cooldown.

        Returns the alert record if fired, None if suppressed by cooldown.
        """
        # Cooldown check
        last = self._last_fired.get(trigger)
        now = datetime.now(timezone.utc)
        if last and (now - last).total_seconds() < ALERT_COOLDOWN_MINUTES * 60:
            logger.debug("Alert suppressed by cooldown: %s", trigger)
            return None

        self._last_fired[trigger] = now

        # Auto-generate runbook link if not provided
        if not runbook_link:
            runbook_link = f"/api/ops/runbooks/{trigger}"

        # Build alert record
        alert = {
            "trigger": trigger,
            "severity": severity,
            "title": title,
            "message": message,
            "context": context or {},
            "tenant_id": tenant_id,
            "property_id": property_id,
            "provider": provider,
            "runbook_link": runbook_link,
            "fired_at": now.isoformat(),
            "acknowledged": False,
        }

        # Channel 1: Log
        log_fn = logger.critical if severity == AlertSeverity.CRITICAL else (
            logger.warning if severity in (AlertSeverity.HIGH, AlertSeverity.WARNING)
            else logger.info
        )
        log_fn("ALERT [%s] %s: %s", severity.upper(), title, message)

        # Channel 2: Webhook (async, best-effort)
        if self._webhook_url:
            asyncio.create_task(self._send_webhook(alert))

        # Persist to DB (copy to avoid _id mutation on the returned alert)
        db = self._get_db()
        try:
            await db[COLL_ALERTS].insert_one({**alert})
        except Exception:
            logger.exception("Failed to persist alert")

        return alert

    async def _send_webhook(self, alert: Dict[str, Any]) -> None:
        """Send alert via HTTP webhook. Slack-compatible payload."""
        try:
            import aiohttp
            severity_emoji = {
                AlertSeverity.CRITICAL: ":rotating_light:",
                AlertSeverity.HIGH: ":warning:",
                AlertSeverity.WARNING: ":large_yellow_circle:",
                AlertSeverity.INFO: ":information_source:",
            }
            emoji = severity_emoji.get(alert["severity"], ":bell:")

            # Slack-compatible payload
            context_fields = []
            if alert.get("tenant_id"):
                context_fields.append({"type": "mrkdwn", "text": f"*Tenant:* {alert['tenant_id']}"})
            if alert.get("provider"):
                context_fields.append({"type": "mrkdwn", "text": f"*Provider:* {alert['provider']}"})
            if alert.get("property_id"):
                context_fields.append({"type": "mrkdwn", "text": f"*Property:* {alert['property_id']}"})

            payload = {
                "text": f"{emoji} *{alert['title']}*\n{alert['message']}",
                "blocks": [
                    {
                        "type": "header",
                        "text": {"type": "plain_text", "text": f"{alert['title']}"},
                    },
                    {
                        "type": "section",
                        "fields": [
                            {"type": "mrkdwn", "text": f"*Severity:* {alert['severity']}"},
                            {"type": "mrkdwn", "text": f"*Trigger:* {alert['trigger']}"},
                            {"type": "mrkdwn", "text": f"*Time:* {alert['fired_at']}"},
                            {"type": "mrkdwn", "text": f"*Runbook:* {alert.get('runbook_link', 'N/A')}"},
                        ] + context_fields,
                    },
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": alert["message"]},
                    },
                ],
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status >= 400:
                        logger.warning("Webhook delivery failed: status=%d", resp.status)
        except ImportError:
            logger.debug("aiohttp not installed — webhook disabled")
        except Exception:
            logger.exception("Webhook delivery error")

    async def check_and_alert(self) -> List[Dict[str, Any]]:
        """Run all alert checks. Returns list of fired alerts."""
        fired = []
        db = self._get_db()
        now = datetime.now(timezone.utc)

        # 1. Import failure spike
        try:
            threshold = DEFAULT_THRESHOLDS[AlertTrigger.IMPORT_FAILURE_SPIKE]
            cutoff = (now - timedelta(minutes=threshold["window_minutes"])).isoformat()
            count = await db.cp_failures.count_documents({
                "operation_type": "reservation_import",
                "status": "open",
                "created_at": {"$gte": cutoff},
            })
            if count >= threshold["count"]:
                alert = await self.fire(
                    trigger=AlertTrigger.IMPORT_FAILURE_SPIKE,
                    severity=AlertSeverity.HIGH,
                    title="Import Failure Spike",
                    message=f"{count} import failures in the last {threshold['window_minutes']} minutes.",
                    context={"count": count, "threshold": threshold["count"]},
                )
                if alert:
                    fired.append(alert)
        except Exception:
            logger.exception("Alert check failed: import_failure_spike")

        # 2. Outbox stuck
        try:
            threshold = DEFAULT_THRESHOLDS[AlertTrigger.OUTBOX_STUCK]
            cutoff = (now - timedelta(minutes=threshold["max_stuck_minutes"])).isoformat()
            stuck = await db.outbox_events.count_documents({
                "status": {"$in": ["pending", "retry"]},
                "created_at": {"$lte": cutoff},
            })
            if stuck >= threshold["max_stuck_count"]:
                alert = await self.fire(
                    trigger=AlertTrigger.OUTBOX_STUCK,
                    severity=AlertSeverity.HIGH,
                    title="Outbox Events Stuck",
                    message=f"{stuck} outbox events stuck for >{threshold['max_stuck_minutes']} minutes.",
                    context={"stuck_count": stuck},
                )
                if alert:
                    fired.append(alert)
        except Exception:
            logger.exception("Alert check failed: outbox_stuck")

        # 3. Secret access anomaly
        try:
            threshold = DEFAULT_THRESHOLDS[AlertTrigger.SECRET_ANOMALY]
            cutoff = (now - timedelta(minutes=threshold["window_minutes"])).isoformat()
            anomalies = await db.secret_access_audit.count_documents({
                "result": {"$in": ["failure", "denied"]},
                "timestamp": {"$gte": cutoff},
            })
            if anomalies >= threshold["count"]:
                alert = await self.fire(
                    trigger=AlertTrigger.SECRET_ANOMALY,
                    severity=AlertSeverity.CRITICAL,
                    title="Secret Access Anomaly",
                    message=f"{anomalies} secret access failures/denials in the last {threshold['window_minutes']} minutes.",
                    context={"anomaly_count": anomalies},
                )
                if alert:
                    fired.append(alert)
        except Exception:
            logger.exception("Alert check failed: secret_anomaly")

        # 4. Crypto failure
        try:
            threshold = DEFAULT_THRESHOLDS[AlertTrigger.CRYPTO_FAILURE]
            cutoff = (now - timedelta(minutes=threshold["window_minutes"])).isoformat()
            crypto_fails = await db.cp_failures.count_documents({
                "operation_type": {"$in": ["crypto_decrypt", "crypto_encrypt"]},
                "status": "open",
                "created_at": {"$gte": cutoff},
            })
            if crypto_fails >= threshold["count"]:
                alert = await self.fire(
                    trigger=AlertTrigger.CRYPTO_FAILURE,
                    severity=AlertSeverity.CRITICAL,
                    title="Crypto Failure Detected",
                    message=f"{crypto_fails} crypto failures detected. Investigate immediately.",
                    context={"count": crypto_fails},
                )
                if alert:
                    fired.append(alert)
        except Exception:
            logger.exception("Alert check failed: crypto_failure")

        return fired

    async def get_recent_alerts(
        self, *, limit: int = 20, severity: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get recent alerts."""
        db = self._get_db()
        query: Dict[str, Any] = {}
        if severity:
            query["severity"] = severity
        return await db[COLL_ALERTS].find(
            query, {"_id": 0}
        ).sort("fired_at", -1).limit(limit).to_list(limit)


# ── Singleton ──────────────────────────────────────────────────────
_engine: Optional[AlertingEngine] = None


def get_alerting_engine() -> AlertingEngine:
    global _engine
    if _engine is None:
        _engine = AlertingEngine()
    return _engine
