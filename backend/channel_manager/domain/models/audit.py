"""
IntegrationAuditLog - Immutable log of all channel manager operations.

Indexes:
  - (tenant_id, connector_id, action, created_at)
  - (tenant_id, entity_type, entity_id)
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any

from pydantic import BaseModel, Field


class AuditAction(str, Enum):
    CONNECTOR_CREATED = "connector_created"
    CONNECTOR_ACTIVATED = "connector_activated"
    CONNECTOR_PAUSED = "connector_paused"
    CONNECTOR_DISABLED = "connector_disabled"
    CREDENTIALS_UPDATED = "credentials_updated"
    MAPPING_CREATED = "mapping_created"
    MAPPING_UPDATED = "mapping_updated"
    MAPPING_DELETED = "mapping_deleted"
    MAPPING_VALIDATED = "mapping_validated"
    INVENTORY_PUSHED = "inventory_pushed"
    RATES_PUSHED = "rates_pushed"
    RESTRICTIONS_PUSHED = "restrictions_pushed"
    RESERVATIONS_PULLED = "reservations_pulled"
    RESERVATION_IMPORTED = "reservation_imported"
    RESERVATION_ACKNOWLEDGED = "reservation_acknowledged"
    RECONCILIATION_RUN = "reconciliation_run"
    RECONCILIATION_RESOLVED = "reconciliation_resolved"
    SYNC_JOB_STARTED = "sync_job_started"
    SYNC_JOB_BATCHED = "sync_job_batched"
    SYNC_JOB_DISPATCHED = "sync_job_dispatched"
    SYNC_JOB_COMPLETED = "sync_job_completed"
    SYNC_JOB_FAILED = "sync_job_failed"
    SYNC_JOB_RETRYING = "sync_job_retrying"
    SYNC_JOB_MANUAL_REVIEW = "sync_job_manual_review"
    SYNC_EVENT_DISPATCHED = "sync_event_dispatched"
    SYNC_EVENT_SUCCEEDED = "sync_event_succeeded"
    SYNC_EVENT_FAILED = "sync_event_failed"
    MANUAL_RETRY = "manual_retry"
    MANUAL_REVIEW_DISMISSED = "manual_review_dismissed"
    ERROR_OCCURRED = "error_occurred"
    CONNECTION_TESTED = "connection_tested"
    # Reservation import lifecycle
    RESERVATION_IMPORT_STARTED = "reservation_import_started"
    RESERVATION_IMPORT_COMPLETED = "reservation_import_completed"
    RESERVATION_IMPORT_FAILED = "reservation_import_failed"
    RESERVATION_CREATED = "reservation_created"
    RESERVATION_MODIFIED = "reservation_modified"
    RESERVATION_CANCELLED = "reservation_cancelled"
    RESERVATION_DUPLICATE = "reservation_duplicate"
    RESERVATION_DUPLICATE_CANCEL = "reservation_duplicate_cancel"
    RESERVATION_CONFLICT = "reservation_conflict"
    RESERVATION_OUT_OF_ORDER = "reservation_out_of_order"
    RESERVATION_REVIEW_QUEUED = "reservation_review_queued"
    RESERVATION_REVIEW_REPROCESSED = "reservation_review_reprocessed"
    RESERVATION_REVIEW_DISMISSED = "reservation_review_dismissed"
    RESERVATION_REVIEW_RESOLVED = "reservation_review_resolved"
    RESERVATION_ACK_SENT = "reservation_ack_sent"
    RESERVATION_ACK_FAILED = "reservation_ack_failed"


class IntegrationAuditLog(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_id: Optional[str] = None
    connector_id: Optional[str] = None

    action: AuditAction
    entity_type: str = ""
    entity_id: str = ""

    actor_id: Optional[str] = None
    actor_type: str = "system"  # system, user, webhook

    metadata: Dict[str, Any] = Field(default_factory=dict)
    correlation_id: Optional[str] = None

    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_doc(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "IntegrationAuditLog":
        doc.pop("_id", None)
        return cls(**doc)
