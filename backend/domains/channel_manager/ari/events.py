"""
ARI Domain Events — Canonical event contract.
All PMS services publish changes through this contract.
"""
import uuid
from datetime import date, datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field


class ARIChangeEvent(BaseModel):
    """Canonical ARI change event published by any PMS service."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_id: str
    source_service: str  # frontdesk / pricing / housekeeping / night_audit / manual
    event_type: str  # availability | rate | restriction
    room_type_code: str
    rate_plan_code: Optional[str] = None
    date_from: date
    date_to: date
    payload: dict
    actor_id: Optional[str] = None
    correlation_id: Optional[str] = Field(default_factory=lambda: str(uuid.uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ARIDelta(BaseModel):
    """Compiled delta ready for provider push."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    provider: str
    tenant_id: str
    property_id: str
    change_scope: str  # availability | rate | restriction
    room_type_code: str
    rate_plan_code: Optional[str] = None
    date_from: date
    date_to: date
    payload: dict
    provider_delta_hash: str = ""


class ProviderResult(BaseModel):
    """Result from provider push attempt."""
    success: bool
    provider: str
    status_code: Optional[int] = None
    response_payload: Optional[dict] = None
    error: Optional[str] = None
    duration_ms: int = 0
    retryable: bool = False
