"""
Group Sales Management Models
Group bookings, blocks, rooming lists, master folios
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from enum import Enum
import uuid

class GroupBlockStatus(str, Enum):
    """Grup bloğu durumu"""
    TENTATIVE = "tentative"  # Opsiyonel
    DEFINITE = "definite"  # Kesinleşmiş
    RELEASED = "released"  # Serbest bırakılmış
    COMPLETED = "completed"  # Tamamlanmış
    CANCELLED = "cancelled"  # İptal

class BillingType(str, Enum):
    """Fatura tipi"""
    MASTER_ACCOUNT = "master_account"  # Tümü master hesaba
    INDIVIDUAL = "individual"  # Her misafir kendi
    SPLIT = "split"  # Karma (oda master, ekstralar bireysel)

class GroupBlock(BaseModel):
    """Grup rezervasyon bloğu"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    
    # Group details
    group_name: str
    organization: str
    contact_name: str
    contact_email: str
    contact_phone: str
    
    # Booking details
    check_in: datetime
    check_out: datetime
    total_rooms: int
    rooms_picked_up: int = 0
    
    # Room breakdown
    room_breakdown: Optional[dict] = None  # {"Standard": 10, "Deluxe": 5}
    
    # Rates
    group_rate: float
    room_type: str
    rate_code: Optional[str] = None
    
    # Important dates
    cutoff_date: datetime
    release_date: Optional[datetime] = None
    
    # Billing
    billing_type: BillingType
    master_folio_id: Optional[str] = None
    payment_terms: Optional[str] = None
    
    # Status
    status: GroupBlockStatus
    
    # Notes
    special_requirements: Optional[str] = None
    catering_notes: Optional[str] = None
    meeting_room_needs: Optional[str] = None
    
    # Tracking
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class GroupBlockCreate(BaseModel):
    """Grup bloğu oluşturma"""
    group_name: str
    organization: str
    contact_name: str
    contact_email: str
    contact_phone: str
    check_in: str
    check_out: str
    total_rooms: int
    room_breakdown: Optional[dict] = None
    group_rate: float
    room_type: str
    cutoff_date: str
    billing_type: BillingType
    special_requirements: Optional[str] = None

class RoomingListEntry(BaseModel):
    """Rooming list girdisi"""
    guest_name: str
    room_type: str
    check_in: str
    check_out: str
    special_requests: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    passport_number: Optional[str] = None

class GroupMasterFolio(BaseModel):
    """Grup master folio"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    group_block_id: str
    
    # Financial
    total_charges: float = 0.0
    total_payments: float = 0.0
    balance: float = 0.0
    
    # Billing rules
    master_charges: List[str] = []  # Charge categories on master (e.g., ["room", "breakfast"])
    individual_charges: List[str] = []  # Individual charges (e.g., ["minibar", "spa"])
    
    # Status
    status: str = "open"  # open, closed
    closed_at: Optional[datetime] = None
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
