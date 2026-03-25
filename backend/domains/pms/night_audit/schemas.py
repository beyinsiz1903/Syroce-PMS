"""
Night Audit — Domain Schemas
Pydantic models for night audit operations.
"""
from enum import Enum
from typing import Any

from pydantic import BaseModel


class NightAuditStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    COMPLETED_WITH_EXCEPTIONS = "completed_with_exceptions"
    FAILED = "failed"
    PARTIAL_RECOVERY_REQUIRED = "partial_recovery_required"
    ROLLED_BACK = "rolled_back"


class NightAuditStage(str, Enum):
    VALIDATING = "validating"
    CANDIDATE_BUILD = "candidate_build"
    POSTING_CHARGES = "posting_charges"
    RECONCILING = "reconciling"
    ROLLING_DATE = "rolling_date"
    COMPLETED = "completed"


class AuditExceptionSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RunNightAuditRequest(BaseModel):
    business_date: str | None = None
    property_id: str | None = None
    trigger_source: str = "manual"
    force_rerun: bool = False
    skip_validations: bool = False
    dry_run: bool = False
    reason: str | None = None


class NightAuditSummary(BaseModel):
    audit_id: str
    tenant_id: str
    business_date: str
    status: NightAuditStatus
    started_at: str
    completed_at: str | None = None
    duration_ms: int | None = None
    rooms_processed: int = 0
    charges_posted: int = 0
    total_room_revenue: float = 0.0
    total_tax_amount: float = 0.0
    no_shows_processed: int = 0
    arrivals_pending: int = 0
    departures_pending: int = 0
    folios_balanced: int = 0
    folios_unbalanced: int = 0
    exceptions_count: int = 0
    exception_details: list[dict[str, Any]] = []
    is_rerun: bool = False
    initiated_by: str = ""


class AuditException(BaseModel):
    id: str
    audit_id: str
    tenant_id: str
    severity: AuditExceptionSeverity
    category: str
    entity_type: str
    entity_id: str | None = None
    message: str
    details: dict[str, Any] = {}
    auto_resolved: bool = False
    resolution: str | None = None
    created_at: str = ""


class NightAuditScheduleRequest(BaseModel):
    enabled: bool = False
    scheduled_hour: int = 0       # 0-23
    scheduled_minute: int = 0     # 0-59
    timezone: str = "Europe/Istanbul"
    skip_validations: bool = False
    auto_retry: bool = True
    max_retries: int = 2
    notify_on_complete: bool = True
    notify_on_failure: bool = True
