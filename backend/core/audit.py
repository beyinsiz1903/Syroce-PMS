"""
Core: Audit Event Logger

Shared audit logging utility used across all domain routers.
"""
import uuid
from datetime import UTC, datetime


async def log_audit_event(
    tenant_id: str,
    user_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    details: str,
    before_value: dict = None,
    after_value: dict = None,
    db=None,
):
    """Helper function to log audit events."""
    audit_log = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "user_id": user_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "details": details,
        "before_value": before_value,
        "after_value": after_value,
        "ip_address": None,
        "user_agent": None,
        "timestamp": datetime.now(UTC).isoformat(),
    }
    audit_copy = audit_log.copy()
    await db.audit_logs.insert_one(audit_copy)
    return audit_log
