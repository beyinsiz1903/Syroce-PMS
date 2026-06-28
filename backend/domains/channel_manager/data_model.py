"""
Channel Manager — Production-Grade Data Model
==============================================

Core Lockdown: Reservation Lifecycle + Mapping + Provider + Reconciliation

Collections:
  1. provider_connections       — Provider credentials & config
  2. room_mappings              — PMS room → provider room mapping
  3. rate_plan_mappings         — PMS rate plan → provider rate mapping
  4. raw_channel_events         — Immutable event store (webhook, pull, replay)
  5. reservation_lineage        — Gold table: reservation tracking & reconciliation
  6. ari_change_sets            — ARI push pipeline state
  7. ari_outbound_logs          — Provider communication audit log
  8. ari_drift_state            — ARI parity / consistency tracking
  9. channel_reconciliation_cases — Discrepancy tracking
"""

import hashlib
import json
import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

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
# CANONICAL RESERVATION STATE MODEL
# ══════════════════════════════════════════════════════════════════════


class ReservationState(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    MODIFIED = "modified"
    CANCELLED = "cancelled"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"
    NO_SHOW = "no_show"


class MutationType(str, Enum):
    NEW_BOOKING = "new_booking"
    PARTIAL_MODIFICATION = "partial_modification"
    DATE_CHANGE = "date_change"
    ROOM_TYPE_CHANGE = "room_type_change"
    RATE_CHANGE = "rate_change"
    GUEST_DETAIL_CHANGE = "guest_detail_change"
    CANCELLATION = "cancellation"
    REINSTATEMENT = "reinstatement"


# Valid state transitions: {from_state: [allowed_to_states]}
STATE_TRANSITIONS: dict[str, list[str]] = {
    ReservationState.PENDING: [
        ReservationState.CONFIRMED,
        ReservationState.CANCELLED,
    ],
    ReservationState.CONFIRMED: [
        ReservationState.MODIFIED,
        ReservationState.CANCELLED,
        ReservationState.CHECKED_IN,
        ReservationState.NO_SHOW,
    ],
    ReservationState.MODIFIED: [
        ReservationState.CONFIRMED,
        ReservationState.MODIFIED,
        ReservationState.CANCELLED,
        ReservationState.CHECKED_IN,
        ReservationState.NO_SHOW,
    ],
    ReservationState.CHECKED_IN: [
        ReservationState.CHECKED_OUT,
    ],
    ReservationState.CANCELLED: [
        ReservationState.CONFIRMED,  # reinstatement goes back to confirmed
    ],
    ReservationState.CHECKED_OUT: [],
    ReservationState.NO_SHOW: [],
}


def is_valid_transition(from_state: str, to_state: str) -> bool:
    if from_state == to_state:
        return True  # same-state update is always valid
    allowed = STATE_TRANSITIONS.get(from_state, [])
    return to_state in allowed


# ══════════════════════════════════════════════════════════════════════
# DELIVERY CONFIRMATION MODEL
# ══════════════════════════════════════════════════════════════════════


class DeliveryState(str, Enum):
    QUEUED = "queued"
    SENT = "sent"
    ACKNOWLEDGED = "acknowledged"
    ACCEPTED = "accepted"
    APPLIED = "applied"
    VERIFIED = "verified"
    FAILED = "failed"


# ══════════════════════════════════════════════════════════════════════
# ERROR CLASSIFICATION
# ══════════════════════════════════════════════════════════════════════


class ErrorClass(str, Enum):
    RETRYABLE = "retryable"
    CONFIGURATION = "configuration"
    BUSINESS_REJECTION = "business_rejection"


# ══════════════════════════════════════════════════════════════════════
# DRIFT TAXONOMY
# ══════════════════════════════════════════════════════════════════════


class DriftType(str, Enum):
    MISSING_LOCALLY = "missing_locally"
    MISSING_REMOTELY = "missing_remotely"
    STALE_LOCALLY = "stale_locally"
    STALE_REMOTELY = "stale_remotely"
    MAPPING_MISMATCH = "mapping_mismatch"
    PAYLOAD_MISMATCH = "payload_mismatch"
    FINANCIAL_MISMATCH = "financial_mismatch"
    STATUS_MISMATCH = "status_mismatch"


class DriftResolution(str, Enum):
    SAFE_AUTO_HEAL = "safe_auto_heal"
    RISKY_AUTO_HEAL = "risky_auto_heal"
    MANUAL_REVIEW = "manual_review"


# ══════════════════════════════════════════════════════════════════════
# MAPPING VALIDATION STATUS
# ══════════════════════════════════════════════════════════════════════


class MappingFailure(str, Enum):
    UNMAPPED = "unmapped"
    INACTIVE = "inactive"
    AMBIGUOUS = "ambiguous"
    DELETED = "deleted"


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
    credentials: dict[str, Any] = Field(default_factory=dict)

    # Sync configuration
    sync_inventory: bool = True
    sync_rates: bool = True
    sync_reservations: bool = True
    sync_restrictions: bool = True

    # Rate limit config
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
        d = self.model_dump()
        d["provider"] = self.provider.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "ProviderConnection":
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
    last_validated_at: str | None = None

    # Audit
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str | None = None

    def to_doc(self) -> dict[str, Any]:
        d = self.model_dump()
        d["provider"] = self.provider.value
        return d

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "RoomMapping":
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
    rate_modifier: float | None = None  # multiply rate by this before push
    rate_offset: float | None = None  # add this to rate before push

    # Status
    is_active: bool = True
    validation_status: str = "pending"  # pending | valid | invalid
    last_validated_at: str | None = None

    # Audit
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str | None = None

    def to_doc(self) -> dict[str, Any]:
        d = self.model_dump()
        d["provider"] = self.provider.value
        return d

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "RatePlanMapping":
        doc.pop("_id", None)
        return cls(**doc)


# ══════════════════════════════════════════════════════════════════════
# 4. RAW CHANNEL EVENTS
# ══════════════════════════════════════════════════════════════════════

COLL_RAW_CHANNEL_EVENTS = "raw_channel_events"
COLL_CHANNEL_EVENT_DEDUP = "channel_event_dedup"


class RawEventSource(str, Enum):
    WEBHOOK = "webhook"
    PULL = "pull"
    REPLAY = "replay"
    MANUAL = "manual"


class ProcessingStatus(str, Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"
    DUPLICATE = "duplicate"
    STALE = "stale"


class RawChannelEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_id: str
    provider: ConnectorProvider
    connection_id: str = ""

    event_type: str = ""  # reservation_create, reservation_modify, reservation_cancel

    # Provider identity
    provider_event_id: str = ""
    external_reservation_id: str = ""
    provider_version: str = ""
    provider_last_modified_at: str | None = None

    # Raw data from provider
    raw_payload: dict[str, Any] = Field(default_factory=dict)
    payload_hash: str = ""
    raw_payload_hash: str = ""  # hash of raw payload before normalization
    canonical_hash: str = ""  # hash of canonicalized payload (same meaning despite format diffs)

    # Processing state
    processing_status: ProcessingStatus = ProcessingStatus.PENDING
    processing_error: str | None = None
    processed_at: str | None = None

    # Decision tracking (stored on raw event for traceability)
    decision_result: str | None = None  # create/update/cancel/skip etc
    decision_reason: str | None = None
    decision_version: int = 0  # aggregate version at decision time
    normalization_result: dict[str, Any] | None = None  # canonical form after normalization

    # Ingest tracking
    received_via: RawEventSource = RawEventSource.WEBHOOK
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    # Timestamps: provider_timestamp vs received_timestamp vs processed_at
    provider_timestamp: str | None = None  # when provider generated the event
    received_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    # processed_at already above

    def to_doc(self) -> dict[str, Any]:
        d = self.model_dump()
        d["provider"] = self.provider.value
        d["received_via"] = self.received_via.value
        d["processing_status"] = self.processing_status.value
        return d

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "RawChannelEvent":
        doc.pop("_id", None)
        return cls(**doc)

    @staticmethod
    def compute_payload_hash(payload: dict[str, Any]) -> str:
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
    reservation_id: str | None = None  # PMS reservation ID (linked after import)
    external_reservation_id: str
    provider_event_id: str = ""
    provider_version: str = ""
    provider_last_modified: str | None = None

    # Idempotency & versioning
    payload_hash: str = ""
    version: int = 1
    decision_version: int = 1  # increments on each decision applied
    confidence_score: float = 1.0

    # Source tracking
    source_system: str = ""  # e.g. "booking.com", "expedia", "direct"
    ingested_via: str = ""  # "webhook" | "pull" | "replay"

    # Loop prevention
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

    # State (canonical)
    status: str = "pending"  # uses ReservationState values
    previous_status: str | None = None  # for transition tracking
    cancellation_reason: str | None = None

    # Mutation tracking
    mutation_type: str | None = None  # uses MutationType values
    last_decision: str = ""  # create | update | cancel | skip | pending_mapping | manual_review
    decision_reason: str = ""

    # Reconciliation
    reconciled: bool = False
    reconciled_at: str | None = None

    # Concurrency control
    lock_holder: str | None = None  # worker ID holding lock
    lock_acquired_at: str | None = None
    lock_expires_at: str | None = None

    # Timestamps
    first_seen_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_seen_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    last_synced_at: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str | None = None

    def to_doc(self) -> dict[str, Any]:
        d = self.model_dump()
        d["provider"] = self.provider.value
        return d

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "ReservationLineage":
        doc.pop("_id", None)
        return cls(**doc)

    @staticmethod
    def compute_payload_hash(canonical_data: dict[str, Any]) -> str:
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
    GHOST_RESERVATION = "ghost_reservation"
    DUPLICATE_RESERVATION = "duplicate_reservation"
    STALE_SYNC = "stale_sync"
    ACK_FAILURE = "ack_failure"
    MISSING_MAPPING = "missing_mapping"
    AMOUNT_MISMATCH = "amount_mismatch"
    DATE_CONFLICT = "date_conflict"
    STATUS_CONFLICT = "status_conflict"
    RESERVATION_CONFLICT = "reservation_conflict"
    CANCELLATION_WITHOUT_RESERVATION = "cancellation_without_reservation"
    DUPLICATE_EVENT = "duplicate_event"
    STALE_EVENT = "stale_event"


class CaseStatus(str, Enum):
    OPEN = "open"
    ACKNOWLEDGED = "acknowledged"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    IGNORED = "ignored"
    DISMISSED = "dismissed"


class ReconciliationCase(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_id: str
    provider: ConnectorProvider

    # Case identity
    external_reservation_id: str | None = None
    reservation_id: str | None = None

    case_type: CaseType
    severity: CaseSeverity
    status: CaseStatus = CaseStatus.OPEN

    # Evidence
    description: str = ""
    details: dict[str, Any] | None = None
    suggested_action: str = ""
    pms_value: dict[str, Any] | None = None
    provider_value: dict[str, Any] | None = None

    # Resolution
    resolution: str | None = None
    resolved_by: str | None = None
    resolved_at: str | None = None
    dismiss_reason: str | None = None

    # Timestamps
    detected_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str | None = None

    def to_doc(self) -> dict[str, Any]:
        d = self.model_dump()
        d["provider"] = self.provider.value
        d["case_type"] = self.case_type.value
        d["severity"] = self.severity.value
        d["status"] = self.status.value
        return d

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "ReconciliationCase":
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
