"""
Online Check-in Models
Pre-arrival guest services and room preference management
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone
from enum import Enum
import uuid

class RoomViewType(str, Enum):
    """Oda manzara tercihleri"""
    SEA_VIEW = "sea_view"
    CITY_VIEW = "city_view"
    GARDEN_VIEW = "garden_view"
    POOL_VIEW = "pool_view"
    NO_PREFERENCE = "no_preference"

class FloorPreference(str, Enum):
    """Kat tercihi"""
    LOW_FLOOR = "low_floor"  # 1-3
    MIDDLE_FLOOR = "middle_floor"  # 4-7
    HIGH_FLOOR = "high_floor"  # 8+
    NO_PREFERENCE = "no_preference"

class BedType(str, Enum):
    """Yatak tipi"""
    KING = "king"
    QUEEN = "queen"
    TWIN = "twin"
    NO_PREFERENCE = "no_preference"

class PillowType(str, Enum):
    """Yastık tipi"""
    SOFT = "soft"
    FIRM = "firm"
    HYPOALLERGENIC = "hypoallergenic"
    FEATHER = "feather"
    NO_PREFERENCE = "no_preference"

class UpsellType(str, Enum):
    """Upsell ürün tipleri"""
    ROOM_UPGRADE = "room_upgrade"
    EARLY_CHECKIN = "early_checkin"
    LATE_CHECKOUT = "late_checkout"
    SPA_PACKAGE = "spa_package"
    ROMANTIC_PACKAGE = "romantic_package"
    AIRPORT_TRANSFER = "airport_transfer"

class OnlineCheckinRequest(BaseModel):
    """Online check-in formu"""
    booking_id: str
    
    # Guest Information
    passport_number: Optional[str] = None
    passport_expiry: Optional[str] = None
    nationality: Optional[str] = None
    
    # Arrival Details
    estimated_arrival_time: Optional[str] = None
    flight_number: Optional[str] = None
    coming_from: Optional[str] = None
    
    # Room Preferences
    room_view: RoomViewType = RoomViewType.NO_PREFERENCE
    floor_preference: FloorPreference = FloorPreference.NO_PREFERENCE
    bed_type: BedType = BedType.NO_PREFERENCE
    pillow_type: PillowType = PillowType.NO_PREFERENCE
    room_temperature: Optional[int] = None  # Celsius
    
    # Special Requests
    special_requests: Optional[str] = None
    dietary_restrictions: Optional[str] = None
    accessibility_needs: Optional[str] = None
    
    # Additional Services
    newspaper_preference: Optional[str] = None
    smoking_preference: bool = False
    connecting_rooms: bool = False
    quiet_room: bool = False
    
    # Communication
    mobile_number: Optional[str] = None
    whatsapp_number: Optional[str] = None

class OnlineCheckinResponse(BaseModel):
    """Online check-in yanıtı"""
    checkin_id: str
    booking_id: str
    status: str  # "pending", "approved", "completed"
    room_number: Optional[str] = None
    estimated_ready_time: Optional[str] = None
    upsell_offers: List[dict] = []
    check_in_instructions: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class UpsellOffer(BaseModel):
    """Upsell teklifi"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    booking_id: str
    tenant_id: str
    guest_id: str
    
    upsell_type: UpsellType
    title: str
    description: str
    original_price: float
    discounted_price: Optional[float] = None
    savings: Optional[float] = None
    
    # Details
    valid_until: Optional[datetime] = None
    terms_conditions: Optional[str] = None
    
    # Status
    status: str = "pending"  # pending, accepted, rejected, expired
    offered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    responded_at: Optional[datetime] = None
    
class UpsellAcceptance(BaseModel):
    """Upsell kabul/red"""
    offer_id: str
    action: str  # "accept" or "reject"
    notes: Optional[str] = None

class PreArrivalCommunication(BaseModel):
    """Pre-arrival iletişim kaydı"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    booking_id: str
    tenant_id: str
    guest_id: str
    
    # Communication details
    communication_type: str  # "welcome_email", "checkin_reminder", "upsell_offer"
    sent_at: datetime
    opened_at: Optional[datetime] = None
    clicked_at: Optional[datetime] = None
    
    # Content
    subject: str
    message: str
    
    # Engagement
    opened: bool = False
    clicked: bool = False
    converted: bool = False

class RoomPreferenceProfile(BaseModel):
    """Misafir oda tercihleri profili"""
    guest_id: str
    tenant_id: str
    
    # Room preferences from history
    preferred_view: Optional[RoomViewType] = None
    preferred_floor: Optional[FloorPreference] = None
    preferred_bed: Optional[BedType] = None
    preferred_pillow: Optional[PillowType] = None
    preferred_temperature: Optional[int] = None
    
    # Frequency data
    preference_confidence: float = 0.0  # 0.0 - 1.0
    based_on_stays: int = 0
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
