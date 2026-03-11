"""
SyncJob / SyncEvent / PushReceipt - Tracks every synchronization operation.

SyncJob: A logical unit of work (e.g., "push inventory for property X for next 30 days")
SyncEvent: An individual push/pull attempt within a job
PushReceipt: Provider acknowledgment of a successful push

Indexes:
  SyncJob: (tenant_id, connector_id, status, created_at)
  SyncEvent: (job_id, status), (tenant_id, connector_id, created_at)
  PushReceipt: (tenant_id, connector_id, sync_event_id)
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field


class SyncStatus(str, Enum):
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    PARTIAL = "partial"
    FAILED = "failed"
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"


class SyncDirection(str, Enum):
    PUSH = "push"  # PMS → Provider
    PULL = "pull"  # Provider → PMS


class SyncType(str, Enum):
    INVENTORY = "inventory"
    RATES = "rates"
    RESTRICTIONS = "restrictions"
    RESERVATIONS = "reservations"
    FULL_REFRESH = "full_refresh"


class SyncJob(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_id: str
    connector_id: str

    direction: SyncDirection
    sync_type: SyncType
    status: SyncStatus = SyncStatus.QUEUED

    # Scope
    date_range_start: Optional[str] = None
    date_range_end: Optional[str] = None
    room_type_ids: List[str] = Field(default_factory=list)
    rate_plan_ids: List[str] = Field(default_factory=list)

    # Progress
    total_events: int = 0
    completed_events: int = 0
    failed_events: int = 0

    # Trigger
    triggered_by: str = "system"  # system | user | webhook | schedule
    trigger_reason: str = ""
    correlation_id: Optional[str] = None

    # Timing
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None

    # Error
    last_error: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3

    # Audit
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_doc(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "SyncJob":
        doc.pop("_id", None)
        return cls(**doc)


class SyncEvent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str
    tenant_id: str
    connector_id: str

    direction: SyncDirection
    sync_type: SyncType
    status: SyncStatus = SyncStatus.QUEUED

    # Payload reference
    entity_type: str = ""  # room_type, rate_plan, reservation
    entity_id: str = ""
    date_key: Optional[str] = None  # YYYY-MM-DD for inventory/rate events

    # Request/response tracking
    request_payload: Optional[Dict[str, Any]] = None
    response_payload: Optional[Dict[str, Any]] = None
    http_status: Optional[int] = None

    # Coalescing
    coalesced_count: int = 1  # How many raw changes were merged into this event
    original_event_ids: List[str] = Field(default_factory=list)

    # Error
    error_message: Optional[str] = None
    retry_count: int = 0
    next_retry_at: Optional[str] = None

    # Timing
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None

    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_doc(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "SyncEvent":
        doc.pop("_id", None)
        return cls(**doc)


class PushReceipt(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    connector_id: str
    sync_event_id: str
    job_id: str

    provider_message_id: Optional[str] = None
    provider_status: str = ""
    provider_response: Dict[str, Any] = Field(default_factory=dict)

    acknowledged: bool = False
    acknowledged_at: Optional[str] = None

    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_doc(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "PushReceipt":
        doc.pop("_id", None)
        return cls(**doc)
