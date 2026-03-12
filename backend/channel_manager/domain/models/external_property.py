"""
External property/room/rate representations from channel manager providers.
These are the provider's view of the hotel's inventory.

Indexes:
  ExternalProperty: (tenant_id, connector_id, external_id): unique
  ExternalRoomType: (tenant_id, connector_id, external_id): unique
  ExternalRatePlan: (tenant_id, connector_id, external_id): unique
"""
import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from pydantic import BaseModel, Field


class ExternalProperty(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    connector_id: str
    external_id: str  # Provider's property ID (e.g., HotelRunner hr_id)
    name: str = ""
    currency: str = "TRY"
    timezone: str = "Europe/Istanbul"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    last_synced_at: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_doc(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "ExternalProperty":
        doc.pop("_id", None)
        return cls(**doc)


class ExternalRoomType(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    connector_id: str
    external_property_id: str
    external_id: str  # Provider's room type code
    name: str = ""
    max_occupancy: int = 2
    base_occupancy: int = 2
    description: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    last_synced_at: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_doc(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "ExternalRoomType":
        doc.pop("_id", None)
        return cls(**doc)


class ExternalRatePlan(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    connector_id: str
    external_property_id: str
    external_room_type_id: str
    external_id: str  # Provider's rate plan code
    name: str = ""
    currency: str = "TRY"
    is_derived: bool = False
    meal_plan: str = "RO"  # RO, BB, HB, FB, AI
    cancellation_policy: str = "flexible"
    metadata: Dict[str, Any] = Field(default_factory=dict)
    is_active: bool = True
    last_synced_at: Optional[str] = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_doc(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "ExternalRatePlan":
        doc.pop("_id", None)
        return cls(**doc)
