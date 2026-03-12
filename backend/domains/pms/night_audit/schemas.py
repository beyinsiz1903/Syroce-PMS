"""
Night Audit — Domain Schemas
Pydantic models for night audit operations.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class NightAuditStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    COMPLETED_WITH_EXCEPTIONS = "completed_with_exceptions"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class AuditExceptionSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class RunNightAuditRequest(BaseModel):
    business_date: Optional[str] = None
    force_rerun: bool = False
    skip_validations: bool = False
    dry_run: bool = False
    reason: Optional[str] = None


class NightAuditSummary(BaseModel):
    audit_id: str
    tenant_id: str
    business_date: str
    status: NightAuditStatus
    started_at: str
    completed_at: Optional[str] = None
    duration_ms: Optional[int] = None
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
    exception_details: List[Dict[str, Any]] = []
    is_rerun: bool = False
    initiated_by: str = ""


class AuditException(BaseModel):
    id: str
    audit_id: str
    tenant_id: str
    severity: AuditExceptionSeverity
    category: str
    entity_type: str
    entity_id: Optional[str] = None
    message: str
    details: Dict[str, Any] = {}
    auto_resolved: bool = False
    resolution: Optional[str] = None
    created_at: str = ""
