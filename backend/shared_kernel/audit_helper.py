import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.database import db


def build_audit_entry(
    actor_id: Optional[str],
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    metadata: Optional[Dict[str, Any]] = None,
    property_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "actor_id": actor_id,
        "tenant_id": tenant_id,
        "property_id": property_id,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "action": action,
        "metadata": metadata or {},
        "correlation_id": correlation_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def audit_log(
    actor_id: Optional[str],
    tenant_id: str,
    entity_type: str,
    entity_id: str,
    action: str,
    metadata: Optional[Dict[str, Any]] = None,
    property_id: Optional[str] = None,
    correlation_id: Optional[str] = None,
) -> Dict[str, Any]:
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
    await db.audit_logs.insert_one(entry)
    return entry
