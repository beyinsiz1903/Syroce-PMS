"""
Night Audit Module - Enterprise Grade
Comprehensive night audit functionality for hotel operations
"""
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class AuditStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class NightAuditRecord(BaseModel):
    """Night Audit Record"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    audit_date: str  # Business date being audited
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    status: AuditStatus = AuditStatus.PENDING
    started_by: str

    # Audit statistics
    total_rooms: int = 0
    occupied_rooms: int = 0
    vacant_rooms: int = 0
    total_revenue: float = 0.0
    room_revenue: float = 0.0
    tax_revenue: float = 0.0
    other_revenue: float = 0.0

    # No-show handling
    no_shows_processed: int = 0
    no_show_charges: float = 0.0

    # Posting results
    room_postings: int = 0
    tax_postings: int = 0
    failed_postings: int = 0

    # Errors and warnings
    errors: List[str] = []
    warnings: List[str] = []

    notes: Optional[str] = None

class AutomaticPosting(BaseModel):
    """Automatic posting configuration"""
    tenant_id: str
    post_room_charges: bool = True
    post_taxes: bool = True
    post_packages: bool = True
    tax_percentage: float = 10.0

class CityLedgerAccount(BaseModel):
    """City Ledger Account for direct billing"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    account_name: str
    company_name: str
    contact_person: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    address: Optional[str] = None
    credit_limit: float = 0.0
    current_balance: float = 0.0
    payment_terms: int = 30  # days
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CityLedgerTransaction(BaseModel):
    """City Ledger Transaction"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    account_id: str
    booking_id: Optional[str] = None
    transaction_type: str  # charge, payment, adjustment
    amount: float
    description: str
    transaction_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reference_number: Optional[str] = None
    posted_by: str

class SplitPayment(BaseModel):
    """Split payment configuration"""
    payment_method: str  # cash, card, city_ledger, etc
    amount: float
    reference: Optional[str] = None

class QueueRoom(BaseModel):
    """Room queue for early arrivals"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    booking_id: str
    guest_name: str
    room_type: str
    priority: int = 5  # 1 (highest) to 10 (lowest)
    requested_room: Optional[str] = None
    arrival_time: Optional[str] = None
    special_requests: Optional[str] = None
    vip_status: bool = False
    added_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notified: bool = False
    status: str = "waiting"  # waiting, assigned, cancelled

class AuditTrailEntry(BaseModel):
    """Audit trail for all system changes"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    user_id: str
    action: str
    entity_type: str  # booking, folio, rate, etc
    entity_id: str
    old_value: Optional[str] = None
    new_value: Optional[str] = None
    ip_address: Optional[str] = None
