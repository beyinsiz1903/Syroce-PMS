"""Auto-split from schemas.py — domain: audit."""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from models.enums import (
    UserRole,
)


# Audit Log Model
class AuditLog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    user_id: str
    user_name: str
    user_role: UserRole
    action: str  # e.g., "CREATE_BOOKING", "POST_CHARGE", "OVERRIDE_RATE"
    entity_type: str  # e.g., "booking", "folio", "charge", "payment"
    entity_id: str
    changes: dict | None = None  # Old and new values
    ip_address: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Rate Override Log Model
class RateOverrideLog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    booking_id: str
    user_id: str
    user_name: str | None = None
    base_rate: float
    new_rate: float
    override_reason: str
    ip_address: str | None = None
    terminal: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Room Move History Model
class RoomMoveHistory(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    booking_id: str
    old_room: str  # Room number
    new_room: str  # Room number
    old_check_in: str
    new_check_in: str
    reason: str
    moved_by: str  # User name
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
