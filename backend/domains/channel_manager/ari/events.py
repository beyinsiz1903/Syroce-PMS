"""
ARI Domain Events — Canonical event contract.
All PMS services publish changes through this contract.
"""

import uuid
from datetime import UTC, date, datetime

from pydantic import BaseModel, Field


class ARIChangeEvent(BaseModel):
    """Canonical ARI change event published by any PMS service."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_id: str
    source_service: str  # frontdesk / pricing / housekeeping / night_audit / manual
    event_type: str  # availability | rate | restriction
    room_type_code: str
    rate_plan_code: str | None = None
    date_from: date
    date_to: date
    payload: dict
    actor_id: str | None = None
    correlation_id: str | None = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ARIDelta(BaseModel):
    """Compiled delta ready for provider push."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    provider: str
    tenant_id: str
    property_id: str
    change_scope: str  # availability | rate | restriction
    room_type_code: str
    rate_plan_code: str | None = None
    date_from: date
    date_to: date
    payload: dict
    provider_delta_hash: str = ""


class ProviderResult(BaseModel):
    """Result from provider push attempt."""

    success: bool
    provider: str
    status_code: int | None = None
    response_payload: dict | None = None
    error: str | None = None
    duration_ms: int = 0
    retryable: bool = False
