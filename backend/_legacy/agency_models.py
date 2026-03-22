"""
Agency Booking Request Models
===============================
MVP için minimal ama production-ready acenta talep sistemi.

Özellikler:
- Idempotent request creation
- Status machine (submitted → hotel_review → approved/rejected/expired/cancelled)
- Audit trail
- Commission tracking
- Restrictions snapshot
"""

from pydantic import BaseModel, Field, constr, EmailStr
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime, timezone
import uuid

# ============= TYPES =============

RequestStatus = Literal["submitted", "hotel_review", "approved", "rejected", "expired", "cancelled"]

FINAL_STATUSES = {"approved", "rejected", "expired", "cancelled"}
PENDING_STATUSES = {"submitted", "hotel_review"}

# ============= HELPER MODELS =============

class RestrictionsSnapshot(BaseModel):
    """Talep anındaki kısıtlamaların snapshot'u"""
    stop_sell: bool = False
    min_stay: int = 1
    max_stay: Optional[int] = None
    cta: bool = False  # Closed to arrival
    ctd: bool = False  # Closed to departure

class AvailabilitySnapshot(BaseModel):
    """Talep anındaki müsaitlik durumu"""
    available_rooms: int
    checked_at: str  # ISO datetime

class AuditEvent(BaseModel):
    """Audit trail için event"""
    event: str  # created, hotel_viewed, approved, rejected, expired, cancelled
    actor_id: str
    actor_type: Literal["agency", "hotel", "system"]
    timestamp: str  # ISO datetime
    metadata: Dict[str, Any] = Field(default_factory=dict)

# ============= REQUEST MODELS =============

class CreateAgencyBookingRequestIn(BaseModel):
    """Acenta tarafından talep oluşturma"""
    hotel_id: str
    room_type_id: str
    rate_plan_id: str
    
    check_in: constr(min_length=10, max_length=10)  # YYYY-MM-DD
    check_out: constr(min_length=10, max_length=10)
    
    adults: int = 2
    children: int = 0
    
    customer_name: str
    customer_phone: str
    customer_email: Optional[EmailStr] = None
    
    source: Literal["web", "mobile", "api"] = "web"

class RejectBookingRequestIn(BaseModel):
    """Otel tarafından red nedeni"""
    reason: str = Field(..., min_length=5, max_length=500)

# ============= RESPONSE MODEL =============

class AgencyBookingRequest(BaseModel):
    """Complete booking request document"""
    # IDs
    request_id: str
    idempotency_key: str
    
    # Relations
    agency_id: str
    hotel_id: str
    room_type_id: str
    rate_plan_id: str
    
    # Booking details
    check_in: str  # YYYY-MM-DD
    check_out: str
    nights: int
    adults: int
    children: int
    
    # Customer info
    customer_name: str
    customer_phone: str
    customer_email: Optional[str] = None
    
    # Pricing snapshot
    price_per_night: float
    total_price: float
    currency: str
    commission_pct: float
    commission_amount: float
    net_to_hotel: float
    
    # Status
    status: RequestStatus
    status_updated_at: str
    
    # Snapshots
    restrictions_snapshot: RestrictionsSnapshot
    availability_at_request: AvailabilitySnapshot
    
    # Lifecycle
    created_at: str
    created_by_user_id: str
    expires_at: str
    
    # Resolution (filled when final)
    resolved_at: Optional[str] = None
    resolved_by_user_id: Optional[str] = None
    resolution_notes: Optional[str] = None
    booking_id: Optional[str] = None
    
    # Audit
    audit_events: List[AuditEvent] = Field(default_factory=list)
    
    # Metadata
    source: str = "web"

# ============= HELPER FUNCTIONS =============

def now_utc() -> datetime:
    """UTC timezone-aware datetime"""
    return datetime.now(timezone.utc)

def iso(dt: datetime) -> str:
    """Convert datetime to ISO string (Z format)"""
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")

def new_uuid() -> str:
    """Generate new UUID v4"""
    return str(uuid.uuid4())

def is_final_status(status: str) -> bool:
    """Check if status is final (cannot be changed)"""
    return status in FINAL_STATUSES

def is_pending_status(status: str) -> bool:
    """Check if status is pending (can be approved/rejected)"""
    return status in PENDING_STATUSES
