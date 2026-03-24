"""
PMS Domain — Schemas
Request/response models extracted from PMS routers.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

# ── Front Desk ──

class PassportScanData(BaseModel):
    passport_number: Optional[str] = None
    name: Optional[str] = None
    surname: Optional[str] = None
    nationality: Optional[str] = None
    date_of_birth: Optional[str] = None
    expiry_date: Optional[str] = None
    sex: Optional[str] = None
    mrz_line1: Optional[str] = None
    mrz_line2: Optional[str] = None


class PassportScanRequest(BaseModel):
    image_base64: str
    booking_id: Optional[str] = None


class WalkInBookingRequest(BaseModel):
    guest_name: str
    guest_email: Optional[str] = None
    guest_phone: str
    guest_id_number: Optional[str] = None
    nationality: Optional[str] = None
    room_id: str
    nights: int = 1
    adults: int = 1
    children: int = 0
    rate_per_night: Optional[float] = None
    special_requests: Optional[str] = None


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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None


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
    reason: Optional[str] = None


class QuickTaskRequest(BaseModel):
    title: str
    department: str
    priority: str = "normal"
    assigned_to: Optional[str] = None
    notes: Optional[str] = None


class QuickIssueRequest(BaseModel):
    title: str
    category: str
    priority: str = "normal"
    room_number: Optional[str] = None
    description: Optional[str] = None


class QuickOrderItem(BaseModel):
    name: str
    quantity: int = 1


class QuickOrderRequest(BaseModel):
    room_number: str
    items: List[QuickOrderItem]
    notes: Optional[str] = None


class MenuPriceUpdateRequest(BaseModel):
    item_id: str
    new_price: float


# ── Notifications ──

class NotificationPreferenceRequest(BaseModel):
    channel: str
    enabled: bool
    settings: Optional[Dict[str, Any]] = None


class SystemAlertRequest(BaseModel):
    title: str
    message: str
    severity: str = "info"
    target_roles: List[str] = []


# ── Approvals ──

class CreateApprovalRequest(BaseModel):
    type: str
    title: str
    description: Optional[str] = None
    amount: Optional[float] = None
    department: Optional[str] = None
    priority: str = "normal"
    data: Optional[Dict[str, Any]] = None
    approvers: List[str] = []


class ApprovalActionRequest(BaseModel):
    action: str
    comment: Optional[str] = None


class BudgetMonth(BaseModel):
    month: int
    year: int
    amount: float
    category: str
    department: Optional[str] = None


class BudgetConfig(BaseModel):
    fiscal_year: int
    months: List[BudgetMonth]
    auto_approval_limit: Optional[float] = None


# ── Calendar ──

class ChannelMixRequest(BaseModel):
    date_from: str
    date_to: str


# ── POS / F&B ──

class POSMenuItem(BaseModel):
    name: str
    category: str
    price: float
    description: Optional[str] = None
    is_available: bool = True
    allergens: List[str] = []
    prep_time_minutes: Optional[int] = None
    image_url: Optional[str] = None


class POSOrderItem(BaseModel):
    menu_item_id: str
    quantity: int = 1
    notes: Optional[str] = None
    modifiers: List[str] = []


class LostFoundItemCreate(BaseModel):
    description: str
    location: str
    found_by: Optional[str] = None
    category: str = "other"
    image_url: Optional[str] = None


class MenuItemCreate(BaseModel):
    name: str
    category: str
    price: float
    description: Optional[str] = None
    is_available: bool = True


# ── Misc ──

class PingTestRequest(BaseModel):
    target: str
    port: int = 443
    timeout: int = 5
