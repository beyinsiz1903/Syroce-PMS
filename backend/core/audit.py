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
    # Capture the real client IP + device for this request (best-effort).
    try:
        from common.request_context import get_client_ip, get_user_agent

        ip_address = get_client_ip()
        user_agent = get_user_agent()
    except Exception:
        ip_address = None
        user_agent = None

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
        "ip_address": ip_address,
        "user_agent": user_agent,
        "timestamp": timestamp,
    }
    audit_copy = audit_log.copy()
    # Callers may omit `db` (e.g. router handlers that just want a guaranteed
    # audit record). Fall back to the shared handle so append_audit_log never
    # dereferences None and silently drops a critical-mutation audit entry.
    if db is None:
        from core.database import db as _default_db

        db = _default_db
    from core.audit_chain import append_audit_log

    await append_audit_log(db, audit_copy)
    return audit_log
