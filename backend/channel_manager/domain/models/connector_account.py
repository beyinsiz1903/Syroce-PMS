"""
ConnectorAccount - Represents a configured connection to an external channel manager provider.
Each tenant+property can have one active connector per provider.

Indexes:
  - (tenant_id, property_id, provider): unique
  - (tenant_id, status)
  - (provider, status)
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field


class ConnectorProvider(str, Enum):
    HOTELRUNNER = "hotelrunner"
    SITEMINDER = "siteminder"
    CHANNEX = "channex"


class ConnectorStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    DISABLED = "disabled"


class ConnectorAccount(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_id: str
    provider: ConnectorProvider
    status: ConnectorStatus = ConnectorStatus.DRAFT
    display_name: str = ""

    # Provider-specific credentials (encrypted at rest)
    credentials: Dict[str, Any] = Field(default_factory=dict)
    # HotelRunner: { "token": "...", "hr_id": "..." }

    # Sync configuration
    sync_inventory: bool = True
    sync_rates: bool = True
    sync_reservations: bool = True
    sync_restrictions: bool = True

    # Rate limit config per provider
    max_requests_per_minute: int = 60
    max_requests_per_hour: int = 1000

    # Health tracking
    last_successful_sync: Optional[str] = None
    last_error: Optional[str] = None
    last_error_at: Optional[str] = None
    consecutive_failures: int = 0
    total_syncs: int = 0
    total_errors: int = 0

    # Audit
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_by: Optional[str] = None
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None

    def to_doc(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "ConnectorAccount":
        doc.pop("_id", None)
        return cls(**doc)
