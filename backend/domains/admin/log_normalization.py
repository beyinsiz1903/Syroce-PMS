import re
import uuid
from datetime import UTC, datetime


def safe_log_label(value: object, fallback: str) -> str:
    """Keep log labels useful without reflecting arbitrary audit payload data."""
    if not isinstance(value, str):
        return fallback
    normalized = re.sub(r"[^A-Za-z0-9_.:-]+", "_", value.strip())[:64]
    return normalized or fallback


def safe_log_timestamp(log: dict) -> str:
    raw = log.get("timestamp") or log.get("created_at") or log.get("occurred_at")
    if isinstance(raw, datetime):
        value = raw if raw.tzinfo else raw.replace(tzinfo=UTC)
        return value.astimezone(UTC).isoformat()
    if isinstance(raw, str):
        try:
            value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            return value.astimezone(UTC).isoformat()
        except ValueError:
            pass
    return datetime.now(UTC).isoformat()


def normalize_audit_log(log: dict) -> dict:
    action = safe_log_label(log.get("action") or log.get("event_type"), "AUDIT_EVENT")
    entity_type = safe_log_label(log.get("entity_type") or log.get("resource_type"), "system")
    upper_action = action.upper()
    level = "INFO"
    if "DELETE" in upper_action or "VOID" in upper_action:
        level = "WARN"
    elif "ERROR" in upper_action or "FAIL" in upper_action:
        level = "ERROR"

    has_actor = any(log.get(key) for key in ("user_name", "user_email", "user_id", "actor_id"))
    return {
        "id": str(log.get("id") or uuid.uuid4()),
        "level": level,
        "timestamp": safe_log_timestamp(log),
        "message": f"{action} on {entity_type}",
        "user": "User" if has_actor else "System",
        "action": action,
        "entity_type": entity_type,
        "details": {
            "source": "audit",
            "has_changes": bool(log.get("changes")),
        },
    }
