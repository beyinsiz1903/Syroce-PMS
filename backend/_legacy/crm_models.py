"""
Guest CRM Models - Phase H
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum

class LoyaltyStatus(str, Enum):
    STANDARD = "standard"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"
    VIP = "vip"

class UpsellType(str, Enum):
    ROOM_UPGRADE = "room_upgrade"
    EARLY_CHECKIN = "early_checkin"
    LATE_CHECKOUT = "late_checkout"
    RESTAURANT = "restaurant"
    SPA = "spa"
    AIRPORT_TRANSFER = "airport_transfer"
    PARKING = "parking"
    CHAMPAGNE = "champagne"
    ROMANTIC_SETUP = "romantic_setup"
    EXTRA_BED = "extra_bed"

class MessageChannel(str, Enum):
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"
    IN_APP = "in_app"

class MessageStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    READ = "read"

class GuestProfile(BaseModel):
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    tenant_id: str
    guest_id: str  # Links to guests table
    first_name: str
    last_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    country: Optional[str] = None
    total_stays: int = 0
    total_nights: int = 0
    lifetime_value: float = 0.0
    average_adr: float = 0.0
    preferred_room_type: Optional[str] = None
    preferred_view: Optional[str] = None
    loyalty_status: LoyaltyStatus = LoyaltyStatus.STANDARD
    last_seen_date: Optional[str] = None
    tags: List[str] = []
    notes: List[str] = []
    created_at: str
    updated_at: str

class GuestPreferences(BaseModel):
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    tenant_id: str
    guest_id: str
    bed_type: Optional[str] = None
    pillow_type: Optional[str] = None
    quiet_room: bool = False
    high_floor: bool = False
    allergies: List[str] = []
    favorite_drinks: List[str] = []
    favorite_foods: List[str] = []
    special_requests: Optional[str] = None

class GuestBehavior(BaseModel):
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    tenant_id: str
    guest_id: str
    upsell_accept_rate: float = 0.0
    no_show_probability: float = 0.0
    cancellation_rate: float = 0.0
    booking_channel_mix: dict = {}
    most_common_stay_days: Optional[int] = None
    special_dates: dict = {}  # birthday, anniversary

class UpsellOffer(BaseModel):
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    tenant_id: str
    guest_id: str
    booking_id: str
    type: UpsellType
    current_item: Optional[str] = None
    target_item: Optional[str] = None
    price: float
    confidence: float
    reason: str
    valid_until: str
    status: str = "pending"  # pending, accepted, declined, expired
    created_at: str

class MessageTemplate(BaseModel):
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    tenant_id: str
    name: str
    channel: MessageChannel
    subject: Optional[str] = None
    body: str
    variables: List[str] = []  # {{guest_name}}, {{room_number}} etc
    active: bool = True

class Message(BaseModel):
    id: str = Field(default_factory=lambda: str(__import__('uuid').uuid4()))
    tenant_id: str
    guest_id: str
    channel: MessageChannel
    template_id: Optional[str] = None
    recipient: str  # email or phone
    subject: Optional[str] = None
    body: str
    status: MessageStatus = MessageStatus.PENDING
    sent_at: Optional[str] = None
    delivered_at: Optional[str] = None
    error_message: Optional[str] = None

print("✅ CRM models imported successfully")
