"""Auto-split from schemas.py — domain: guests."""
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


# Guest & Booking Models
class GuestCreate(BaseModel):
    name: str
    email: str = ""
    phone: str
    id_number: str
    nationality: str | None = None
    address: str | None = None
    vip_status: bool = False

class Guest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    email: str | None = ""
    phone: str | None = ""
    id_number: str | None = ""
    nationality: str | None = None
    address: str | None = None
    vip_status: bool = False
    loyalty_points: int = 0
    total_stays: int = 0
    total_spend: float = 0.0
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


