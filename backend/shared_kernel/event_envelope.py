import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field


class EventEnvelope(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    timestamp: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    tenant_id: str
    correlation_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


def build_event_envelope(
    event_type: str,
    tenant_id: str,
    payload: dict[str, Any] | None = None,
    correlation_id: str | None = None,
) -> EventEnvelope:
    return EventEnvelope(
        event_type=event_type,
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        payload=payload or {},
    )
