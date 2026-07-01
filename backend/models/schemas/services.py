"""Auto-split from schemas.py — domain: services."""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from models.enums import (
    RoomServiceStatus,
)


# Room Service Models
class RoomServiceCreate(BaseModel):
    booking_id: str
    service_type: str
    description: str
    notes: str | None = None


class RoomService(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    booking_id: str
    guest_id: str
    service_type: str
    description: str
    notes: str | None = None
    status: RoomServiceStatus = RoomServiceStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
