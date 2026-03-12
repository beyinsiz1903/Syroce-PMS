"""
Guest Domain — Schemas
Request/response models extracted from guest routers.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from enum import Enum
import uuid


class GuestStayHistory(BaseModel):
    booking_id: str
    check_in: str
    check_out: str
    room_number: str
    nights: int
    total_spent: float
    rating: Optional[float] = None


class GuestPreference(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    pillow_type: Optional[str] = None
    room_temperature: Optional[int] = None
    smoking: bool = False
    floor_preference: Optional[str] = None
    room_view: Optional[str] = None
    newspaper: Optional[str] = None
    extra_requests: List[str] = []
    dietary_restrictions: List[str] = []
    allergies: List[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GuestTag(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    tag: str
    color: str = "blue"
    added_by: str
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class GuestTagEnum(str, Enum):
    VIP = "vip"
    BLACKLIST = "blacklist"
    HONEYMOON = "honeymoon"
    ANNIVERSARY = "anniversary"
    BUSINESS_TRAVELER = "business_traveler"
    FREQUENT_GUEST = "frequent_guest"
    COMPLAINER = "complainer"
    HIGH_SPENDER = "high_spender"


class RedeemPointsRequest(BaseModel):
    points_to_redeem: int
    reward_type: str


class MinimumStockAlertRequest(BaseModel):
    item_id: str
    min_stock_level: int
    alert_recipients: List[str] = []


class LinenInventoryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    item_type: str
    size: Optional[str] = None
    quantity_in_stock: int = 0
    quantity_in_use: int = 0
    quantity_in_laundry: int = 0
    quantity_damaged: int = 0
    reorder_level: int = 50
    unit_cost: float = 0.0
    last_restocked: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CleaningRequestCreate(BaseModel):
    booking_id: Optional[str] = None
    room_number: Optional[str] = None
    type: str = "regular"
    notes: Optional[str] = ""


# Guest Messaging schemas

class SendMessageRequest(BaseModel):
    guest_id: str
    channel: str = "sms"
    subject: Optional[str] = None
    message: str
    template_id: Optional[str] = None
    template_vars: Optional[Dict[str, str]] = None
    scheduled_at: Optional[str] = None
    priority: str = "normal"


class SentMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    channel: str
    subject: Optional[str] = None
    message: str
    status: str = "sent"
    sent_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    delivered_at: Optional[str] = None


class MessageTemplate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    channel: str
    subject: Optional[str] = None
    body: str
    variables: List[str] = []
    category: str = "general"
    is_active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class InternalMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    from_user_id: str
    to_user_id: str
    subject: str
    body: str
    priority: str = "normal"
    is_read: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
