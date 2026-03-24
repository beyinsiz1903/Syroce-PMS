import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    tenant_id: str
    correlation_id: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)


def build_event_envelope(
    event_type: str,
    tenant_id: str,
    payload: Optional[Dict[str, Any]] = None,
    correlation_id: Optional[str] = None,
) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        payload=payload or {},
    )
