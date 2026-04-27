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
    severity: str = "info",
):
    """Helper function to log audit events.

    `severity` opsiyoneldir, varsayılan "info". Audit zaman çizelgesi UI'sı
    severity'ye göre filtreleme yaptığı için, "warning"/"error"/"critical"
    seviyelerini geçmek bu kayıtların ön plana çıkmasını sağlar (örn. acil
    mesaj kötüye kullanımının izlenmesi). Mevcut çağıranlar için davranış
    değişmez.
    """
    timestamp = datetime.now(UTC).isoformat()
    audit_log = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        # Legacy field names (kept for older consumers)
        "user_id": user_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "details": details,
        "before_value": before_value,
        "after_value": after_value,
        # New AuditTimeline-compatible field names
        # (consumed by routers/audit_timeline.py)
        "actor_id": user_id,
        "actor_role": None,
        "operation_name": action,
        "target_type": entity_type,
        "target_id": entity_id,
        "before_snapshot": before_value,
        "after_snapshot": after_value,
        "result_status": "success",
        "severity": severity,
        "duration_ms": None,
        "override_reason": None,
        "ip_address": None,
        "user_agent": None,
        "timestamp": timestamp,
    }
    audit_copy = audit_log.copy()
    await db.audit_logs.insert_one(audit_copy)
    return audit_log
