"""
Online Check-in Models
Pre-arrival guest services and room preference management
"""
import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


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
    passport_number: str | None = None
    passport_expiry: str | None = None
    nationality: str | None = None

    # Arrival Details
    estimated_arrival_time: str | None = None
    flight_number: str | None = None
    coming_from: str | None = None

    # Room Preferences
    room_view: RoomViewType = RoomViewType.NO_PREFERENCE
    floor_preference: FloorPreference = FloorPreference.NO_PREFERENCE
    bed_type: BedType = BedType.NO_PREFERENCE
    pillow_type: PillowType = PillowType.NO_PREFERENCE
    room_temperature: int | None = None  # Celsius

    # Special Requests
    special_requests: str | None = None
    dietary_restrictions: str | None = None
    accessibility_needs: str | None = None

    # Additional Services
    newspaper_preference: str | None = None
    smoking_preference: bool = False
    connecting_rooms: bool = False
    quiet_room: bool = False

    # Communication
    mobile_number: str | None = None
    whatsapp_number: str | None = None

class OnlineCheckinResponse(BaseModel):
    """Online check-in yanıtı"""
    checkin_id: str
    booking_id: str
    status: str  # "pending", "approved", "completed"
    room_number: str | None = None
    estimated_ready_time: str | None = None
    upsell_offers: list[dict] = []
    check_in_instructions: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

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
    discounted_price: float | None = None
    savings: float | None = None

    # Details
    valid_until: datetime | None = None
    terms_conditions: str | None = None

    # Status
    status: str = "pending"  # pending, accepted, rejected, expired
    offered_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    responded_at: datetime | None = None

class UpsellAcceptance(BaseModel):
    """Upsell kabul/red"""
    offer_id: str
    action: str  # "accept" or "reject"
    notes: str | None = None

class PreArrivalCommunication(BaseModel):
    """Pre-arrival iletişim kaydı"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    booking_id: str
    tenant_id: str
    guest_id: str

    # Communication details
    communication_type: str  # "welcome_email", "checkin_reminder", "upsell_offer"
    sent_at: datetime
    opened_at: datetime | None = None
    clicked_at: datetime | None = None

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
    preferred_view: RoomViewType | None = None
    preferred_floor: FloorPreference | None = None
    preferred_bed: BedType | None = None
    preferred_pillow: PillowType | None = None
    preferred_temperature: int | None = None

    # Frequency data
    preference_confidence: float = 0.0  # 0.0 - 1.0
    based_on_stays: int = 0
    last_updated: datetime = Field(default_factory=lambda: datetime.now(UTC))
