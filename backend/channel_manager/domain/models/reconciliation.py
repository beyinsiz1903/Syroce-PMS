"""
ReconciliationIssue - Tracks mismatches between PMS and provider state.

Issue Types:
  - inventory_mismatch, rate_mismatch, missing_reservation, stale_sync
  - invalid_mapping, ack_failed, ack_pending_too_long, unprocessed_import

Severity: low, medium, high, critical

Issue Lifecycle: open -> investigating -> retrying -> resolved | dismissed

Indexes:
  - (tenant_id, connector_id, issue_type, status)
  - (tenant_id, severity, created_at)
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ReconciliationSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IssueType(str, Enum):
    INVENTORY_MISMATCH = "inventory_mismatch"
    RATE_MISMATCH = "rate_mismatch"
    MISSING_RESERVATION = "missing_reservation"
    STALE_SYNC = "stale_sync"
    INVALID_MAPPING = "invalid_mapping"
    ACK_FAILED = "ack_failed"
    ACK_PENDING_TOO_LONG = "ack_pending_too_long"
    UNPROCESSED_IMPORT = "unprocessed_import"


class IssueStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RETRYING = "retrying"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class SuggestedAction(str, Enum):
    RETRY_SYNC = "retry_sync"
    REVALIDATE_MAPPING = "revalidate_mapping"
    RETRY_ACK = "retry_ack"
    SEND_TO_REVIEW = "send_to_review"
    DISMISS_WITH_REASON = "dismiss_with_reason"


class ReconciliationIssue(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_id: str
    connector_id: str

    issue_type: IssueType
    severity: ReconciliationSeverity
    status: IssueStatus = IssueStatus.OPEN

    # Entity context
    entity_type: str = ""
    entity_id: str = ""
    date_key: Optional[str] = None

    # Related entity references
    related_sync_job_ids: List[str] = Field(default_factory=list)
    related_mapping_ids: List[str] = Field(default_factory=list)
    related_reservation_ids: List[str] = Field(default_factory=list)

    # Evidence
    pms_value: Optional[Dict[str, Any]] = None
    external_value: Optional[Dict[str, Any]] = None
    evidence_payload: Optional[Dict[str, Any]] = None
    description: str = ""

    # Suggested actions
    suggested_actions: List[str] = Field(default_factory=list)

    # Resolution
    resolution: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None
    auto_fix_attempted: bool = False
    auto_fix_result: Optional[str] = None
    dismiss_reason: Optional[str] = None

    # Audit
    detected_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: Optional[str] = None

    def to_doc(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "ReconciliationIssue":
        doc.pop("_id", None)
        return cls(**doc)
