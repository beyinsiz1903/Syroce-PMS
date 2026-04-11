"""
Guest Domain — Schemas
Request/response models extracted from guest routers.
"""
import uuid
from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class GuestStayHistory(BaseModel):
    booking_id: str
    check_in: str
    check_out: str
    room_number: str
    nights: int
    total_spent: float
    rating: float | None = None


class GuestPreference(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    pillow_type: str | None = None
    room_temperature: int | None = None
    smoking: bool = False
    floor_preference: str | None = None
    room_view: str | None = None
    newspaper: str | None = None
    extra_requests: list[str] = []
    dietary_restrictions: list[str] = []
    allergies: list[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class GuestTag(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    tag: str
    color: str = "blue"
    added_by: str
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


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
    alert_recipients: list[str] = []


class LinenInventoryItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    item_type: str
    size: str | None = None
    quantity_in_stock: int = 0
    quantity_in_use: int = 0
    quantity_in_laundry: int = 0
    quantity_damaged: int = 0
    reorder_level: int = 50
    unit_cost: float = 0.0
    last_restocked: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CleaningRequestCreate(BaseModel):
    booking_id: str | None = None
    room_number: str | None = None
    type: str = "regular"
    notes: str | None = ""


# Guest Messaging schemas

class SendMessageRequest(BaseModel):
    guest_id: str
    channel: str = "sms"
    subject: str | None = None
    message: str
    template_id: str | None = None
    template_vars: dict[str, str] | None = None
    scheduled_at: str | None = None
    priority: str = "normal"


class SentMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    channel: str
    subject: str | None = None
    message: str
    status: str = "sent"
    sent_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
    delivered_at: str | None = None


class MessageTemplate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    channel: str
    subject: str | None = None
    body: str
    variables: list[str] = []
    category: str = "general"
    is_active: bool = True
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())


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
    created_at: str = Field(default_factory=lambda: datetime.now(UTC).isoformat())
