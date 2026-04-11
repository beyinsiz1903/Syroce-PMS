"""
VIP & Guest Profile Management Models
Enhanced guest preferences, VIP tiers, celebrations tracking
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone, date
from enum import Enum
import uuid

class VIPTier(str, Enum):
    """VIP seviyeleri"""
    PLATINUM = "platinum"  # En üst seviye
    GOLD = "gold"
    SILVER = "silver"
    REGULAR = "regular"

class GuestTag(str, Enum):
    """Misafir etiketleri"""
    VIP = "vip"
    BLACKLIST = "blacklist"
    DO_NOT_RENT = "do_not_rent"
    HONEYMOON = "honeymoon"
    ANNIVERSARY = "anniversary"
    BIRTHDAY = "birthday"
    BUSINESS_TRAVELER = "business_traveler"
    FREQUENT_GUEST = "frequent_guest"
    COMPLAINER = "complainer"
    HIGH_SPENDER = "high_spender"
    SPECIAL_NEEDS = "special_needs"

class CelebrationTracking(BaseModel):
    """Kutlama ve özel günler takibi"""
    guest_id: str
    tenant_id: str
    
    # Important dates
    birthday: Optional[date] = None
    anniversary: Optional[date] = None
    wedding_date: Optional[date] = None
    
    # Preferences for celebrations
    preferred_celebration_type: Optional[str] = None  # cake, champagne, flowers
    notes: Optional[str] = None
    
    # Tracking
    last_birthday_celebrated: Optional[date] = None
    last_anniversary_celebrated: Optional[date] = None
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class EnhancedGuestPreferences(BaseModel):
    """Gelişmiş misafir tercihleri"""
    guest_id: str
    tenant_id: str
    
    # Room Preferences
    pillow_type: Optional[str] = None  # soft, firm, hypoallergenic, feather
    bed_type: Optional[str] = None  # king, queen, twin
    room_temperature: Optional[int] = None  # Celsius
    floor_preference: Optional[str] = None  # low, middle, high
    room_view: Optional[str] = None  # sea, city, garden, pool
    quiet_room: bool = False
    connecting_rooms: bool = False
    
    # Amenities
    extra_towels: bool = False
    extra_pillows: bool = False
    bathrobes: bool = False
    slippers: bool = False
    
    # Services
    newspaper_preference: Optional[str] = None
    turndown_service: bool = True
    do_not_disturb_preference: Optional[str] = None
    
    # F&B Preferences
    dietary_restrictions: Optional[str] = None
    favorite_cuisine: Optional[str] = None
    allergies: Optional[str] = None
    breakfast_preference: Optional[str] = None  # continental, american, turkish
    
    # Special Needs
    accessibility_needs: Optional[str] = None
    medical_conditions: Optional[str] = None
    language_preference: Optional[str] = None
    
    # Learned from history
    preference_confidence: float = 0.0  # 0.0 - 1.0
    based_on_stays: int = 0
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class VIPProtocol(BaseModel):
    """VIP misafir için özel protokol"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    guest_id: str
    tenant_id: str
    
    # VIP Level
    vip_tier: VIPTier
    
    # Special Instructions
    special_handling_notes: Optional[str] = None
    preferred_room_numbers: List[str] = []
    preferred_staff_members: List[str] = []
    
    # Amenities
    welcome_amenities: List[str] = []  # champagne, flowers, fruit basket
    turndown_amenities: List[str] = []
    
    # Services
    airport_transfer_required: bool = False
    personal_concierge: bool = False
    early_checkin_guaranteed: bool = False
    late_checkout_guaranteed: bool = False
    
    # Communication
    preferred_communication: Optional[str] = None  # email, whatsapp, phone
    do_not_contact: bool = False
    
    # Approval
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class BlacklistEntry(BaseModel):
    """Blacklist/Do Not Rent kaydı"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    guest_id: str
    tenant_id: str
    
    # Reason
    reason: str
    severity: str  # low, medium, high, critical
    incident_date: datetime
    
    # Details
    detailed_notes: str
    reported_by: str
    approved_by: Optional[str] = None
    
    # Action
    action_taken: Optional[str] = None  # warning, blacklist, do_not_rent, legal_action
    
    # Status
    active: bool = True
    permanent: bool = False
    review_date: Optional[datetime] = None
    
    # Attachments
    evidence_files: List[str] = []
    
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class GuestSpendingProfile(BaseModel):
    """Misafir harcama profili"""
    guest_id: str
    tenant_id: str
    
    # Lifetime metrics
    total_stays: int = 0
    total_nights: int = 0
    total_spent: float = 0.0
    
    # Average metrics
    avg_room_rate: float = 0.0
    avg_fnb_spend: float = 0.0
    avg_total_spend: float = 0.0
    
    # Breakdown
    room_revenue: float = 0.0
    fnb_revenue: float = 0.0
    spa_revenue: float = 0.0
    other_revenue: float = 0.0
    
    # Value classification
    lifetime_value_tier: str = "regular"  # regular, valuable, high_value, vip
    predicted_ltv: Optional[float] = None
    
    # Last activity
    last_stay_date: Optional[datetime] = None
    last_booking_date: Optional[datetime] = None
    
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
