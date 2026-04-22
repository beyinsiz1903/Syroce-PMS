"""Auto-split from schemas.py — domain: requests."""
import math
from typing import Any

from pydantic import BaseModel, field_validator


def _finite_positive(v: float, field: str = "value", *, allow_zero: bool = False) -> float:
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        raise ValueError(f"{field} sonlu bir sayı olmalı (NaN/Infinity kabul edilmiyor)")
    if not allow_zero and v <= 0:
        raise ValueError(f"{field} sıfırdan büyük olmalı")
    return float(v)


def _finite(v: float, field: str = "value") -> float:
    if v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v))):
        raise ValueError(f"{field} sonlu bir sayı olmalı")
    return float(v)


def _iso_currency(v: str, field: str = "currency") -> str:
    if not isinstance(v, str) or len(v) != 3 or not v.isalpha():
        raise ValueError(f"{field} 3 harfli ISO 4217 kodu olmalı (örn: USD, EUR, TRY)")
    return v.upper()

# ============= NEW FEATURES PYDANTIC MODELS =============

# Messaging Models
class SendWhatsAppRequest(BaseModel):
    to: str
    message: str
    booking_id: str | None = None

class SendEmailRequest(BaseModel):
    to: str
    subject: str
    message: str
    booking_id: str | None = None

class SendSMSRequest(BaseModel):
    to: str
    message: str
    booking_id: str | None = None

class CreateMessageTemplateRequest(BaseModel):
    name: str
    channel: str
    subject: str | None = None
    content: str = ""
    variables: list[str] = []

# RMS Models
class AddCompetitorRequest(BaseModel):
    name: str
    location: str
    star_rating: float
    url: str | None = None

class ScrapePricesRequest(BaseModel):
    date: str

class AutoPricingRequest(BaseModel):
    start_date: str
    end_date: str
    room_type: str | None = None

class DemandForecastRequest(BaseModel):
    start_date: str
    end_date: str

# Housekeeping Models
class ReportIssueRequest(BaseModel):
    room_id: str
    issue_type: str
    description: str
    priority: str = 'normal'
    photos: list[str] = []

class UploadPhotoRequest(BaseModel):
    task_id: str
    photo_base64: str

# POS Models
class CreatePOSTransactionRequest(BaseModel):
    amount: float
    payment_method: str
    folio_id: str | None = None

# Group Reservations Models
class CreateGroupReservationRequest(BaseModel):
    group_name: str
    group_type: str
    contact_person: str
    contact_email: str
    contact_phone: str
    check_in_date: str
    check_out_date: str
    total_rooms: int
    adults_per_room: int = 2
    special_requests: str | None = None

class AssignGroupRoomsRequest(BaseModel):
    room_assignments: list[dict[str, Any]]

class CreateBlockReservationRequest(BaseModel):
    block_name: str
    room_type: str
    start_date: str
    end_date: str
    total_rooms: int
    block_type: str = 'tentative'
    release_date: str | None = None

class UseBlockRoomRequest(BaseModel):
    guest_name: str
    guest_email: str

# Multi-Property Models
class CreatePropertyRequest(BaseModel):
    property_name: str
    property_code: str
    location: str
    total_rooms: int
    property_type: str = 'hotel'
    status: str = 'active'

class TransferReservationRequest(BaseModel):
    target_property_id: str
    reason: str | None = None

# Marketplace Models
class CreateMarketplaceProductRequest(BaseModel):
    product_name: str
    category: str
    unit_price: float
    unit_of_measure: str
    supplier: str
    min_order_qty: int = 1

class AdjustInventoryRequest(BaseModel):
    product_id: str
    location: str
    quantity_change: int
    reason: str

class CreatePurchaseOrderRequest(BaseModel):
    supplier: str
    items: list[dict[str, Any]]
    delivery_location: str
    expected_delivery_date: str | None = None

class ReceivePurchaseOrderRequest(BaseModel):
    received_items: list[dict[str, Any]]

class CreateDeliveryRequest(BaseModel):
    po_id: str
    tracking_number: str | None = None
    carrier: str | None = None
    estimated_delivery: str | None = None

# Marketplace Extended Models
class CreateSupplierRequest(BaseModel):
    supplier_name: str
    contact_person: str
    contact_email: str
    contact_phone: str
    credit_limit: float = 0.0
    payment_terms: str = "Net 30"  # Net 15, Net 30, Net 60, COD
    status: str = "active"

class UpdateSupplierCreditRequest(BaseModel):
    credit_limit: float
    payment_terms: str

class ApprovePurchaseOrderRequest(BaseModel):
    approval_notes: str | None = None

class RejectPurchaseOrderRequest(BaseModel):
    rejection_reason: str

class UpdateDeliveryStatusRequest(BaseModel):
    status: str  # in_transit, delivered, failed
    location: str | None = None
    notes: str | None = None

class CreateWarehouseRequest(BaseModel):
    warehouse_name: str
    location: str
    capacity: int
    warehouse_type: str = "central"  # central, regional, local

# Accounting & Multi-Currency Models
class CreateCurrencyRateRequest(BaseModel):
    from_currency: str  # USD, EUR, GBP, TRY
    to_currency: str
    rate: float
    effective_date: str

    @field_validator("from_currency", "to_currency")
    @classmethod
    def _v_curr(cls, v):
        return _iso_currency(v, "currency")

    @field_validator("rate")
    @classmethod
    def _v_rate(cls, v):
        return _finite_positive(v, "rate")

class CreateMultiCurrencyInvoiceRequest(BaseModel):
    customer_name: str
    customer_email: str
    customer_address: str
    items: list[dict[str, Any]]
    currency: str = "TRY"  # Invoice currency
    exchange_rate: float | None = None  # If different from TRY
    payment_terms: str = "Net 30"
    notes: str | None = None

class GenerateInvoiceFromFolioRequest(BaseModel):
    folio_id: str
    invoice_currency: str = "TRY"
    include_efatura: bool = True

class ConvertCurrencyRequest(BaseModel):
    amount: float
    from_currency: str
    to_currency: str
    date: str | None = None  # Use specific date rate, or latest if None

    @field_validator("from_currency", "to_currency")
    @classmethod
    def _v_curr(cls, v):
        return _iso_currency(v, "currency")

    @field_validator("amount")
    @classmethod
    def _v_amt(cls, v):
        return _finite(v, "amount")

# Rate Code & Calendar Models
class CreateRateCodeRequest(BaseModel):
    code: str  # BB, HB, FB, AI, RO
    name: str  # Bed & Breakfast, Half Board, etc.
    description: str
    includes_breakfast: bool = False
    includes_lunch: bool = False
    includes_dinner: bool = False
    is_refundable: bool = True
    cancellation_policy: str = "Free cancellation"
    price_modifier: float = 1.0  # Multiplier on base rate

class GetCalendarTooltipRequest(BaseModel):
    date: str
    room_type: str | None = None

# POS & F&B Models
class CreateOutletRequest(BaseModel):
    outlet_name: str
    outlet_type: str  # restaurant, bar, room_service, cafe
    location: str
    capacity: int | None = None
    opening_hours: str | None = None

class CreateMenuItemRequest(BaseModel):
    outlet_id: str
    item_name: str
    category: str  # appetizer, main, dessert, beverage
    price: float
    cost: float | None = None
    description: str | None = None

class CreatePOSTransactionWithMenuRequest(BaseModel):
    outlet_id: str
    items: list[dict[str, Any]]  # [{menu_item_id, quantity, price}]
    payment_method: str
    folio_id: str | None = None
    table_number: str | None = None
    server_name: str | None = None

class GenerateZReportRequest(BaseModel):
    outlet_id: str | None = None
    date: str | None = None  # Default to today

# Feedback & Reviews Models
class CreateSurveyRequest(BaseModel):
    survey_name: str
    description: str
    target_department: str | None = None  # housekeeping, front_desk, fnb, spa, all
    questions: list[dict[str, Any]]  # [{question, type, options}]
    trigger: str = "checkout"  # checkout, checkin, stay, manual

class SubmitSurveyResponseRequest(BaseModel):
    survey_id: str
    booking_id: str | None = None
    guest_name: str | None = None
    guest_email: str | None = None
    responses: list[dict[str, Any]]  # [{question_id, answer, rating}]

class ExternalReviewWebhookRequest(BaseModel):
    platform: str  # booking, google, tripadvisor
    review_id: str
    rating: float
    reviewer_name: str
    review_text: str
    review_date: str
    booking_reference: str | None = None

class CreateDepartmentFeedbackRequest(BaseModel):
    department: str  # housekeeping, front_desk, fnb, spa
    booking_id: str | None = None
    guest_name: str
    rating: int  # 1-5
    comment: str | None = None
    staff_member: str | None = None

# Task Management Models
class CreateTaskRequest(BaseModel):
    department: str  # engineering, housekeeping, fnb, maintenance, front_desk
    task_type: str  # repair, inspection, cleaning, setup, delivery, guest_request
    title: str
    description: str
    priority: str = "normal"  # low, normal, high, urgent
    location: str | None = None  # room number or area
    room_id: str | None = None
    assigned_to: str | None = None
    due_date: str | None = None
    recurring: bool | None = False
    recurrence_pattern: str | None = None  # daily, weekly, monthly

class UpdateTaskStatusRequest(BaseModel):
    status: str  # assigned, in_progress, completed, verified, cancelled
    notes: str | None = None
    completion_photos: list[str] | None = []

class AssignTaskRequest(BaseModel):
    assigned_to: str
    notes: str | None = None

# Enterprise Features Models
class CreateRoleRequest(BaseModel):
    role_name: str
    description: str
    permissions: list[str]  # ['view_bookings', 'edit_rates', 'delete_bookings', etc.]
    department: str | None = None

class AssignRoleRequest(BaseModel):
    user_id: str
    role_id: str


class UpdateUserRoleRequest(BaseModel):
    role: str

class CreateBackupRequest(BaseModel):
    backup_type: str = "full"  # full, incremental
    include_collections: list[str] | None = None


