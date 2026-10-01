import uuid
from datetime import UTC, datetime
from typing import Any

from core.database import db


def build_audit_entry(
    actor_id: str | None,
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    metadata: dict[str, Any] | None = None,
    property_id: str | None = None,
    correlation_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "actor_id": actor_id,
        "tenant_id": tenant_id,
        "property_id": property_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "action": action,
        # Canonical timeline fields.  Keep the legacy names above because
        # older consumers still read them, but every new record must also be
        # discoverable by the central audit screen.
        "target_type": entity_type,
        "target_id": entity_id,
        "operation_name": action,
        "result_status": "success",
        "severity": "info",
        "metadata": metadata or {},
        "correlation_id": correlation_id,
        "timestamp": datetime.now(UTC).isoformat(),
    }


async def audit_log(
    actor_id: str | None,
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    metadata: dict[str, Any] | None = None,
    property_id: str | None = None,
    correlation_id: str | None = None,
    session=None,
) -> dict[str, Any]:
    entry = build_audit_entry(
        actor_id=actor_id,
        tenant_id=tenant_id,
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        metadata=metadata,
        property_id=property_id,
        correlation_id=correlation_id,
    )
    if session:
        # Session-aware writes still pass through the append-only collection
        # wrapper, which performs the tamper-evident chain link.
        await db.audit_logs.insert_one(entry, session=session)
    else:
        from core.audit_chain import append_audit_log

        await append_audit_log(db, entry)
    return entry
