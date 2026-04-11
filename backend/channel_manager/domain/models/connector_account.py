"""
ConnectorAccount - Represents a configured connection to an external channel manager provider.
Each tenant+property can have one active connector per provider.

Indexes:
  - (tenant_id, property_id, provider): unique
  - (tenant_id, status)
  - (provider, status)
"""
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

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
    credentials: dict[str, Any] = Field(default_factory=dict)
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
    last_successful_sync: str | None = None
    last_error: str | None = None
    last_error_at: str | None = None
    consecutive_failures: int = 0
    total_syncs: int = 0
    total_errors: int = 0

    # Audit
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    created_by: str | None = None
    updated_at: str | None = None
    updated_by: str | None = None

    def to_doc(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "ConnectorAccount":
        doc.pop("_id", None)
        return cls(**doc)
