"""
Operational Event Emitter — Unified ops telemetry layer.

Emits structured operational events that feed:
  - NotificationBell (in-app notifications)
  - Ops Dashboard
  - Incident feed
  - Audit/timeline

Event types:
  - webhook.delivery.started
  - webhook.delivery.attempt
  - webhook.delivery.succeeded
  - webhook.delivery.failed
  - webhook.delivery.retrying
  - webhook.delivery.terminal_failure
  - webhook.delivery.dlq
  - push.started
  - push.queued
  - push.throttled
  - push.retried
  - push.succeeded
  - push.failed_terminal
  - rate_limit.active
  - rate_limit.cooldown
  - channel.health_changed
  - import.started
  - import.completed
  - import.failed
"""
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from core.database import db

logger = logging.getLogger("ops_events")

# Severity levels
SEVERITY_INFO = "info"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"
SEVERITY_SUCCESS = "success"

# Events that should generate in-app notifications
NOTIFIABLE_EVENTS = {
    "webhook.delivery.terminal_failure": (SEVERITY_CRITICAL, "Webhook teslimati basarisiz (tum denemeler tukendi)"),
    "webhook.delivery.dlq": (SEVERITY_CRITICAL, "Webhook DLQ'ya tasinidi"),
    "push.failed_terminal": (SEVERITY_CRITICAL, "Kanal push islemi basarisiz"),
    "push.throttled": (SEVERITY_WARNING, "Kanal push islemi throttle edildi"),
    "rate_limit.active": (SEVERITY_WARNING, "Rate limit aktif"),
    "import.failed": (SEVERITY_WARNING, "Kanal import islemi basarisiz"),
    "channel.health_changed": (SEVERITY_WARNING, "Kanal sagligi degisti"),
    # Early Warning / Predictive events (Sprint 4)
    "predictive.warning.degradation_likely": (SEVERITY_WARNING, "Bozulma riski tespit edildi"),
    "predictive.warning.failure_rate_rising": (SEVERITY_WARNING, "Hata orani yukseliyor"),
    "predictive.warning.backlog_growth": (SEVERITY_WARNING, "Retry backlog buyuyor"),
    "predictive.warning.dlq_spike": (SEVERITY_CRITICAL, "DLQ ani artis"),
    "predictive.warning.throttle_risk": (SEVERITY_WARNING, "Throttle riski"),
    "predictive.warning.staleness_risk": (SEVERITY_WARNING, "Connector sessiz kaldi"),
}


async def emit_ops_event(
    event_type: str,
    tenant_id: str,
    *,
    channel: str = "",
    connector_id: str = "",
    severity: str = SEVERITY_INFO,
    title: str = "",
    details: dict[str, Any] | None = None,
    affected_entity_type: str = "",
    affected_entity_id: str = "",
    correlation_id: str = "",
) -> str:
    """Emit an operational event and optionally create in-app notification.

    Returns the event_id.
    """
    event_id = str(uuid.uuid4())
    now = datetime.now(UTC).isoformat()

    event_doc = {
        "id": event_id,
        "event_type": event_type,
        "tenant_id": tenant_id,
        "channel": channel,
        "connector_id": connector_id,
        "severity": severity,
        "title": title or event_type,
        "details": details or {},
        "affected_entity_type": affected_entity_type,
        "affected_entity_id": affected_entity_id,
        "correlation_id": correlation_id,
        "created_at": now,
    }

    try:
        await db.ops_events.insert_one(event_doc)
    except Exception as exc:
        logger.error("Failed to store ops event %s: %s", event_type, exc)

    # Create in-app notification for critical/warning events
    if event_type in NOTIFIABLE_EVENTS:
        notif_severity, default_title = NOTIFIABLE_EVENTS[event_type]
        try:
            notif_doc = {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "type": "ops_event",
                "ops_event_type": event_type,
                "title": title or default_title,
                "message": _build_notification_message(event_type, details or {}, channel),
                "priority": "critical" if notif_severity == SEVERITY_CRITICAL else "high",
                "read": False,
                "correlation_id": correlation_id,
                "created_at": now,
            }
            await db.notifications.insert_one(notif_doc)
        except Exception as exc:
            logger.error("Failed to create notification for ops event %s: %s", event_type, exc)

    logger.info("[OPS-EVENT] %s tenant=%s channel=%s severity=%s",
                event_type, tenant_id, channel, severity)
    return event_id


def _build_notification_message(
    event_type: str, details: dict[str, Any], channel: str
) -> str:
    """Build a human-readable notification message."""
    ch = channel or "bilinmeyen kanal"

    if event_type == "webhook.delivery.terminal_failure":
        url = details.get("url", "bilinmeyen URL")
        attempts = details.get("attempt_count", "?")
        last_error = details.get("last_error", "")
        return f"Webhook ({url}) {attempts} deneme sonrasi basarisiz oldu. Son hata: {last_error[:150]}"

    if event_type == "webhook.delivery.dlq":
        url = details.get("url", "bilinmeyen URL")
        return f"Webhook ({url}) DLQ'ya tasindi. Manuel retry gerekli."

    if event_type == "push.failed_terminal":
        error = details.get("error", "bilinmeyen hata")
        return f"{ch}: Push islemi basarisiz — {error[:150]}"

    if event_type == "push.throttled":
        cooldown = details.get("cooldown_until", "bilinmiyor")
        return f"{ch}: Push throttle edildi. Bekleme suresi: {cooldown}"

    if event_type == "rate_limit.active":
        remaining = details.get("remaining_tokens", "?")
        cooldown = details.get("cooldown_until", "bilinmiyor")
        return f"{ch}: Rate limit aktif. Kalan token: {remaining}. Cooldown: {cooldown}"

    if event_type == "import.failed":
        error = details.get("error", "bilinmeyen hata")
        return f"{ch}: Import basarisiz — {error[:150]}"

    if event_type == "channel.health_changed":
        old_state = details.get("old_status", "?")
        new_state = details.get("new_status", "?")
        return f"{ch}: Kanal sagligi degisti: {old_state} → {new_state}"

    # Early Warning / Predictive messages (Sprint 4)
    if event_type == "predictive.warning.degradation_likely":
        reason = details.get("reason", "Health score dusus egilimnide")
        confidence = details.get("confidence", "?")
        return f"ERKEN UYARI ({confidence}% guven): {ch} — {reason[:150]}"

    if event_type == "predictive.warning.failure_rate_rising":
        reason = details.get("reason", "Hata orani artis trendinde")
        confidence = details.get("confidence", "?")
        return f"ERKEN UYARI ({confidence}% guven): {ch} — {reason[:150]}"

    if event_type == "predictive.warning.backlog_growth":
        reason = details.get("reason", "Retry backlog buyuyor")
        return f"ERKEN UYARI: {reason[:150]}"

    if event_type == "predictive.warning.dlq_spike":
        reason = details.get("reason", "DLQ ani artis")
        return f"ERKEN UYARI (KRITIK): {reason[:150]}"

    if event_type == "predictive.warning.throttle_risk":
        reason = details.get("reason", "Throttle riski yuksek")
        return f"ERKEN UYARI: {ch} — {reason[:150]}"

    if event_type == "predictive.warning.staleness_risk":
        reason = details.get("reason", "Connector sessiz kaldi")
        return f"ERKEN UYARI: {ch} — {reason[:150]}"

    if event_type == "predictive.warning.recovery_expected":
        reason = details.get("reason", "Iyilesme bekleniyor")
        return f"IYILESME SINYALI: {ch} — {reason[:150]}"

    return f"{event_type}: {ch}"
