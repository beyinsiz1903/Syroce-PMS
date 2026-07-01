"""
SyncJob / SyncEvent / PushReceipt / ChangeRecord - Tracks every synchronization operation.

SyncJob Lifecycle: pending → batched → dispatched → succeeded | retrying → failed → manual_review
ChangeRecord: Individual PMS change before coalescing (availability, rate, restriction)

Indexes:
  SyncJob: (tenant_id, connector_id, status, created_at)
  SyncEvent: (job_id, status), (tenant_id, connector_id, created_at)
  PushReceipt: (tenant_id, connector_id, sync_event_id)
"""

import uuid
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SyncJobStatus(str, Enum):
    PENDING = "pending"
    BATCHED = "batched"
    DISPATCHED = "dispatched"
    SUCCEEDED = "succeeded"
    RETRYING = "retrying"
    FAILED = "failed"
    MANUAL_REVIEW = "manual_review"


# Keep legacy alias for backward compatibility in existing code paths
class SyncStatus(str, Enum):
    QUEUED = "pending"
    IN_PROGRESS = "dispatched"
    COMPLETED = "succeeded"
    PARTIAL = "retrying"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTER = "manual_review"


class SyncDirection(str, Enum):
    PUSH = "push"
    PULL = "pull"


class SyncType(str, Enum):
    INVENTORY = "inventory"
    RATES = "rates"
    RESTRICTIONS = "restrictions"
    RESERVATIONS = "reservations"
    FULL_REFRESH = "full_refresh"


class ChangeType(str, Enum):
    AVAILABILITY_CHANGED = "availability_changed"
    STOP_SELL_CHANGED = "stop_sell_changed"
    CLOSED_TO_ARRIVAL_CHANGED = "closed_to_arrival_changed"
    CLOSED_TO_DEPARTURE_CHANGED = "closed_to_departure_changed"
    MINIMUM_STAY_CHANGED = "minimum_stay_changed"
    RATE_CHANGED = "rate_changed"


class ChangeRecord(BaseModel):
    """Individual PMS change event before coalescing."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_id: str
    connector_id: str

    change_type: ChangeType
    room_type_id: str
    rate_plan_id: str = ""
    date_start: str  # YYYY-MM-DD
    date_end: str  # YYYY-MM-DD

    # Old & new values for delta detection
    old_value: Any | None = None
    new_value: Any | None = None

    # Coalescing tracking
    coalesced_into: str | None = None  # event_id if merged
    is_coalesced: bool = False

    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_doc(self) -> dict[str, Any]:
        return self.model_dump()


class SyncJob(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_id: str
    connector_id: str

    direction: SyncDirection
    sync_type: SyncType
    status: SyncJobStatus = SyncJobStatus.PENDING

    # Scope
    date_range_start: str | None = None
    date_range_end: str | None = None
    room_type_ids: list[str] = Field(default_factory=list)
    rate_plan_ids: list[str] = Field(default_factory=list)

    # Change tracking
    change_types: list[str] = Field(default_factory=list)
    total_changes_detected: int = 0
    total_changes_after_coalescing: int = 0

    # Progress
    total_events: int = 0
    completed_events: int = 0
    failed_events: int = 0
    retried_events: int = 0

    # Trigger
    triggered_by: str = "system"  # system | user | webhook | schedule
    trigger_reason: str = ""
    correlation_id: str | None = None

    # Timing
    started_at: str | None = None
    batched_at: str | None = None
    dispatched_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None

    # Error
    last_error: str | None = None
    retry_count: int = 0
    max_retries: int = 3

    # Audit
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_doc(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "SyncJob":
        doc.pop("_id", None)
        return cls(**doc)


class SyncEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str
    tenant_id: str
    connector_id: str

    direction: SyncDirection
    sync_type: SyncType
    status: SyncJobStatus = SyncJobStatus.PENDING

    # What changed
    change_type: str = ""  # ChangeType value
    entity_type: str = ""  # room_type, rate_plan
    entity_id: str = ""
    date_key: str | None = None  # YYYY-MM-DD

    # Batch payload
    batch_index: int = 0
    batch_size: int = 0
    request_payload: dict[str, Any] | None = None
    response_payload: dict[str, Any] | None = None
    http_status: int | None = None

    # Coalescing
    coalesced_count: int = 1
    original_change_ids: list[str] = Field(default_factory=list)

    # Error handling
    error_message: str | None = None
    error_code: str | None = None
    is_retryable: bool = True
    retry_count: int = 0
    max_retries: int = 3
    next_retry_at: str | None = None

    # Timing
    started_at: str | None = None
    completed_at: str | None = None
    duration_ms: int | None = None
    latency_ms: int | None = None

    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_doc(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "SyncEvent":
        doc.pop("_id", None)
        return cls(**doc)


class PushReceipt(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    connector_id: str
    sync_event_id: str
    job_id: str

    provider_message_id: str | None = None
    provider_status: str = ""
    provider_response: dict[str, Any] = Field(default_factory=dict)

    acknowledged: bool = False
    acknowledged_at: str | None = None

    latency_ms: int = 0

    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_doc(self) -> dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_doc(cls, doc: dict[str, Any]) -> "PushReceipt":
        doc.pop("_id", None)
        return cls(**doc)
