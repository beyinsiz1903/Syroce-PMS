"""
PMS Domain — Schemas
Request/response models extracted from PMS routers.
"""
import uuid
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ── Front Desk ──

class PassportScanData(BaseModel):
    passport_number: str | None = None
    name: str | None = None
    surname: str | None = None
    nationality: str | None = None
    date_of_birth: str | None = None
    expiry_date: str | None = None
    sex: str | None = None
    mrz_line1: str | None = None
    mrz_line2: str | None = None


class PassportScanRequest(BaseModel):
    image_base64: str
    booking_id: str | None = None


class WalkInBookingRequest(BaseModel):
    guest_name: str
    guest_email: str | None = None
    guest_phone: str
    guest_id_number: str | None = None
    nationality: str | None = None
    room_id: str
    nights: int = 1
    adults: int = 1
    children: int = 0
    rate_per_night: float | None = None
    special_requests: str | None = None


class GuestAlert(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    alert_type: str
    priority: str = "normal"
    title: str
    description: str
    is_active: bool = True
    show_on_checkin: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    expires_at: datetime | None = None


class KeycardIssueRequest(BaseModel):
    booking_id: str
    card_type: str = "physical"
    validity_hours: int = 48


# ── Housekeeping ──

class CleaningRequestStatusUpdate(BaseModel):
    status: str


# ── Mobile ──

class ProcessNoShowRequest(BaseModel):
    booking_id: str


class ChangeRoomRequest(BaseModel):
    booking_id: str
    new_room_id: str
    reason: str | None = None


class QuickTaskRequest(BaseModel):
    title: str
    department: str
    priority: str = "normal"
    assigned_to: str | None = None
    notes: str | None = None


class QuickIssueRequest(BaseModel):
    title: str
    category: str
    priority: str = "normal"
    room_number: str | None = None
    description: str | None = None


class QuickOrderItem(BaseModel):
    name: str
    quantity: int = 1


class QuickOrderRequest(BaseModel):
    room_number: str
    items: list[QuickOrderItem]
    notes: str | None = None


class MenuPriceUpdateRequest(BaseModel):
    item_id: str
    new_price: float


# ── Notifications ──

class NotificationPreferenceRequest(BaseModel):
    channel: str
    enabled: bool
    settings: dict[str, Any] | None = None


class SystemAlertRequest(BaseModel):
    title: str
    message: str
    severity: str = "info"
    target_roles: list[str] = []


# ── Approvals ──

class CreateApprovalRequest(BaseModel):
    type: str
    title: str
    description: str | None = None
    amount: float | None = None
    department: str | None = None
    priority: str = "normal"
    data: dict[str, Any] | None = None
    approvers: list[str] = []


class ApprovalActionRequest(BaseModel):
    action: str
    comment: str | None = None


class BudgetMonth(BaseModel):
    month: int
    year: int
    amount: float
    category: str
    department: str | None = None


class BudgetConfig(BaseModel):
    fiscal_year: int
    months: list[BudgetMonth]
    auto_approval_limit: float | None = None


# ── Calendar ──

class ChannelMixRequest(BaseModel):
    date_from: str
    date_to: str


# ── POS / F&B ──

class POSMenuItem(BaseModel):
    name: str
    category: str
    price: float
    description: str | None = None
    is_available: bool = True
    allergens: list[str] = []
    prep_time_minutes: int | None = None
    image_url: str | None = None


class POSOrderItem(BaseModel):
    menu_item_id: str
    quantity: int = 1
    notes: str | None = None
    modifiers: list[str] = []


class LostFoundItemCreate(BaseModel):
    description: str
    location: str
    found_by: str | None = None
    category: str = "other"
    image_url: str | None = None


class MenuItemCreate(BaseModel):
    name: str
    category: str
    price: float
    description: str | None = None
    is_available: bool = True


# ── Misc ──

class PingTestRequest(BaseModel):
    target: str
    port: int = 443
    timeout: int = 5
