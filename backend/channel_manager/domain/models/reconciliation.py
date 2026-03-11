"""
ReconciliationIssue - Tracks mismatches between PMS and provider state.

Indexes:
  - (tenant_id, connector_id, issue_type, status)
  - (tenant_id, severity, created_at)
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, Dict, Any

from pydantic import BaseModel, Field


class ReconciliationSeverity(str, Enum):
    CRITICAL = "critical"  # Overbooking risk
    HIGH = "high"          # Rate mismatch > threshold
    MEDIUM = "medium"      # Inventory drift
    LOW = "low"            # Minor metadata diff
    INFO = "info"


class IssueType(str, Enum):
    INVENTORY_MISMATCH = "inventory_mismatch"
    RATE_MISMATCH = "rate_mismatch"
    RESTRICTION_MISMATCH = "restriction_mismatch"
    MISSING_RESERVATION = "missing_reservation"
    DUPLICATE_RESERVATION = "duplicate_reservation"
    MAPPING_INVALID = "mapping_invalid"
    SYNC_STALE = "sync_stale"
    AVAILABILITY_DRIFT = "availability_drift"


class ReconciliationIssue(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    property_id: str
    connector_id: str

    issue_type: IssueType
    severity: ReconciliationSeverity
    status: str = "open"  # open, investigating, resolved, dismissed, auto_resolved

    # Entity context
    entity_type: str = ""  # room_type, rate_plan, reservation
    entity_id: str = ""
    date_key: Optional[str] = None

    # Mismatch details
    pms_value: Optional[Dict[str, Any]] = None
    external_value: Optional[Dict[str, Any]] = None
    expected_value: Optional[Dict[str, Any]] = None
    description: str = ""

    # Resolution
    resolution: Optional[str] = None
    resolved_by: Optional[str] = None
    resolved_at: Optional[str] = None
    auto_fix_attempted: bool = False
    auto_fix_result: Optional[str] = None

    # Audit
    detected_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_doc(self) -> Dict[str, Any]:
        return self.model_dump()

    @classmethod
    def from_doc(cls, doc: Dict[str, Any]) -> "ReconciliationIssue":
        doc.pop("_id", None)
        return cls(**doc)
