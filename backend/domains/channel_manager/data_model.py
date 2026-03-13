"""
Channel Manager — Optimized 9-Collection Data Model
====================================================

Designed for 2-provider architecture (HotelRunner + Exely).
No over-abstraction. Clean, debuggable, performant.

Collections:
  1. provider_connections    — Provider credentials & config
  2. room_mappings           — PMS room → provider room mapping
  3. rate_plan_mappings      — PMS rate plan → provider rate mapping
  4. raw_channel_events      — Immutable event store (webhook, pull, replay)
  5. reservation_lineage     — Gold table: reservation tracking & reconciliation
  6. ari_change_sets         — ARI push pipeline state
  7. ari_outbound_logs       — Provider communication audit log
  8. ari_drift_state         — ARI parity / consistency tracking
  9. channel_reconciliation_cases — Discrepancy tracking
"""
import uuid
import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field


# ── Provider Enum (HotelRunner + Exely only) ──────────────────────────

class ConnectorProvider(str, Enum):
    HOTELRUNNER = "hotelrunner"
    EXELY = "exely"


# ── Connection Status ─────────────────────────────────────────────────

class ConnectionStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    ERROR = "error"
    DISABLED = "disabled"


# ══════════════════════════════════════════════════════════════════════
# 1. PROVIDER CONNECTIONS
# ══════════════════════════════════════════════════════════════════════

COLL_PROVIDER_CONNECTIONS = "provider_connections"

class ProviderConnection(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_id: str
    provider: ConnectorProvider

    status: ConnectionStatus = ConnectionStatus.DRAFT
    display_name: str = ""

    # Provider-specific credentials (encrypted at rest)
    credentials: Dict[str, Any] = Field(default_factory=dict)

    # Sync configuration
    sync_inventory: bool = True
    sync_rates: bool = True
    sync_reservations: bool = True
    sync_restrictions: bool = True

    # Rate limit config
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
        d = self.model_dump()
        d["provider"] = self.provider.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "ProviderConnection":
        doc.pop("_id", None)
        return cls(**doc)


# ══════════════════════════════════════════════════════════════════════
# 2. ROOM MAPPINGS
# ══════════════════════════════════════════════════════════════════════

COLL_ROOM_MAPPINGS = "room_mappings"

class RoomMapping(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_id: str
    provider: ConnectorProvider

    # PMS side
    pms_room_type_id: str
    pms_room_type_name: str = ""

    # Provider side
    provider_room_code: str
    provider_room_id: str = ""

    # Optional transform
    occupancy_offset: int = 0

    # Status
    is_active: bool = True
    validation_status: str = "pending"  # pending | valid | invalid
    last_validated_at: Optional[str] = None

    # Audit
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Optional[str] = None

    def to_doc(self) -> Dict[str, Any]:
        d = self.model_dump()
        d["provider"] = self.provider.value
        return d

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "RoomMapping":
        doc.pop("_id", None)
        return cls(**doc)


# ══════════════════════════════════════════════════════════════════════
# 3. RATE PLAN MAPPINGS
# ══════════════════════════════════════════════════════════════════════

COLL_RATE_PLAN_MAPPINGS = "rate_plan_mappings"

class RatePlanMapping(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_id: str
    provider: ConnectorProvider

    # PMS side
    pms_rate_plan_id: str
    pms_rate_plan_name: str = ""

    # Provider side
    provider_rate_code: str
    provider_rate_id: str = ""

    # Optional transform
    rate_modifier: Optional[float] = None  # multiply rate by this before push
    rate_offset: Optional[float] = None  # add this to rate before push

    # Status
    is_active: bool = True
    validation_status: str = "pending"  # pending | valid | invalid
    last_validated_at: Optional[str] = None

    # Audit
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Optional[str] = None

    def to_doc(self) -> Dict[str, Any]:
        d = self.model_dump()
        d["provider"] = self.provider.value
        return d

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "RatePlanMapping":
        doc.pop("_id", None)
        return cls(**doc)


# ══════════════════════════════════════════════════════════════════════
# 4. RAW CHANNEL EVENTS
# ══════════════════════════════════════════════════════════════════════

COLL_RAW_CHANNEL_EVENTS = "raw_channel_events"

class RawEventSource(str, Enum):
    WEBHOOK = "webhook"
    PULL = "pull"
    REPLAY = "replay"
    MANUAL = "manual"


class RawChannelEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_id: str
    provider: ConnectorProvider

    source: RawEventSource = RawEventSource.WEBHOOK
    event_type: str = ""  # reservation_create, reservation_modify, etc.

    # Raw data from provider
    raw_payload: Dict[str, Any] = Field(default_factory=dict)
    payload_hash: str = ""

    # Processing state
    processed: bool = False
    processed_at: Optional[str] = None
    processing_result: Optional[str] = None  # success | error | skipped
    error_message: Optional[str] = None

    # Idempotency
    external_event_id: str = ""
    deduplicated: bool = False

    # Timestamps
    received_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    provider_timestamp: Optional[str] = None

    def to_doc(self) -> Dict[str, Any]:
        d = self.model_dump()
        d["provider"] = self.provider.value
        d["source"] = self.source.value
        return d

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "RawChannelEvent":
        doc.pop("_id", None)
        return cls(**doc)

    @staticmethod
    def compute_payload_hash(payload: Dict[str, Any]) -> str:
        raw = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ══════════════════════════════════════════════════════════════════════
# 5. RESERVATION LINEAGE (Gold Table)
# ══════════════════════════════════════════════════════════════════════

COLL_RESERVATION_LINEAGE = "reservation_lineage"

class ReservationLineage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_id: str
    provider: ConnectorProvider

    # Core identity
    reservation_id: Optional[str] = None  # PMS reservation ID (linked after import)
    external_reservation_id: str
    provider_event_id: str = ""  # Event that created/updated this record
    provider_last_modified: Optional[str] = None

    # Idempotency & versioning
    payload_hash: str = ""
    version: int = 1
    confidence_score: float = 1.0

    # Source tracking
    source_system: str = ""  # e.g. "booking.com", "expedia", "direct"
    ingested_via: str = ""  # "webhook" | "pull" | "replay"

    # Protection flag
    external_write_protected: bool = False

    # Guest summary
    guest_name: str = ""
    guest_email: str = ""
    guest_phone: str = ""

    # Stay summary
    arrival_date: str = ""
    departure_date: str = ""
    room_type_code: str = ""
    rate_plan_code: str = ""
    adults: int = 1
    children: int = 0
    total_amount: float = 0.0
    currency: str = "TRY"

    # Status
    status: str = "pending"  # pending | confirmed | modified | cancelled | imported
    cancellation_reason: Optional[str] = None

    # Reconciliation
    reconciled: bool = False
    reconciled_at: Optional[str] = None

    # Timestamps
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Optional[str] = None

    def to_doc(self) -> Dict[str, Any]:
        d = self.model_dump()
        d["provider"] = self.provider.value
        return d

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "ReservationLineage":
        doc.pop("_id", None)
        return cls(**doc)

    @staticmethod
    def compute_payload_hash(canonical_data: Dict[str, Any]) -> str:
        key_fields = {
            "arrival_date": canonical_data.get("arrival_date", ""),
            "departure_date": canonical_data.get("departure_date", ""),
            "room_type_code": canonical_data.get("room_type_code", ""),
            "rate_plan_code": canonical_data.get("rate_plan_code", ""),
            "adults": canonical_data.get("adults", 1),
            "children": canonical_data.get("children", 0),
            "total_amount": canonical_data.get("total_amount", 0.0),
            "status": canonical_data.get("status", ""),
            "guest_email": canonical_data.get("guest_email", ""),
        }
        raw = json.dumps(key_fields, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ══════════════════════════════════════════════════════════════════════
# 6-8. ARI COLLECTIONS (already exist, constants only)
# ══════════════════════════════════════════════════════════════════════

COLL_ARI_CHANGE_SETS = "ari_change_sets"
COLL_ARI_OUTBOUND_LOGS = "ari_outbound_logs"
COLL_ARI_DRIFT_STATE = "ari_drift_state"


# ══════════════════════════════════════════════════════════════════════
# 9. CHANNEL RECONCILIATION CASES
# ══════════════════════════════════════════════════════════════════════

COLL_RECONCILIATION_CASES = "channel_reconciliation_cases"

class CaseSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CaseType(str, Enum):
    INVENTORY_MISMATCH = "inventory_mismatch"
    RATE_MISMATCH = "rate_mismatch"
    MISSING_RESERVATION = "missing_reservation"
    DUPLICATE_RESERVATION = "duplicate_reservation"
    STALE_SYNC = "stale_sync"
    ACK_FAILURE = "ack_failure"


class CaseStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class ReconciliationCase(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_id: str
    provider: ConnectorProvider

    # Case identity
    external_reservation_id: Optional[str] = None
    reservation_id: Optional[str] = None

    case_type: CaseType
    severity: CaseSeverity
    status: CaseStatus = CaseStatus.OPEN

    # Evidence
    description: str = ""
    pms_value: Optional[Dict[str, Any]] = None
    provider_value: Optional[Dict[str, Any]] = None

    # Resolution
    resolution: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None
    dismiss_reason: Optional[str] = None

    # Timestamps
    detected_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Optional[str] = None

    def to_doc(self) -> Dict[str, Any]:
        d = self.model_dump()
        d["provider"] = self.provider.value
        d["case_type"] = self.case_type.value
        d["severity"] = self.severity.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "ReconciliationCase":
        doc.pop("_id", None)
        return cls(**doc)


# ══════════════════════════════════════════════════════════════════════
# Collection names registry (for migration, indexing, etc.)
# ══════════════════════════════════════════════════════════════════════

ALL_COLLECTIONS = [
    COLL_PROVIDER_CONNECTIONS,
    COLL_ROOM_MAPPINGS,
    COLL_RATE_PLAN_MAPPINGS,
    COLL_RAW_CHANNEL_EVENTS,
    COLL_RESERVATION_LINEAGE,
    COLL_ARI_CHANGE_SETS,
    COLL_ARI_OUTBOUND_LOGS,
    COLL_ARI_DRIFT_STATE,
    COLL_RECONCILIATION_CASES,
]
