"""
Syroce PMS - Pydantic Schema Definitions
All request/response models used across the application.
Extracted from server.py for modularity.
"""
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from models.enums import (
    BookingStatus,
    CancellationPolicyType,
    ChannelStatus,
    ChannelType,
    ChargeCategory,
    CheckInStatus,
    CompanyStatus,
    ContractedRateType,
    DepartmentType,
    FolioOperationType,
    FolioStatus,
    FolioType,
    GuestRequestStatus,
    GuestRequestType,
    InspectionStatus,
    InvoiceStatus,
    LostFoundStatus,
    LoyaltyTier,
    MaintenancePriority,
    MaintenanceTaskStatus,
    MaintenanceType,
    MappingStatus,
    MarketSegment,
    MeasurementUnit,
    OrderStatus,
    OTAChannel,
    OTAPaymentModel,
    OutletType,
    PaymentMethod,
    PaymentStatus,
    PaymentType,
    PricingStrategy,
    RateType,
    RiskLevel,
    RoomServiceStatus,
    RoomStatus,
    UserRole,
    WarehouseLocation,
)

# ============= MODELS =============

class Tenant(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    property_name: str
    property_type: str | None = "hotel"
    contact_email: str | None = None
    contact_phone: str | None = None
    address: str | None = None
    total_rooms: int | None = 50
    subscription_status: str = "active"
    subscription_start_date: str | None = None
    subscription_end_date: str | None = None
    subscription_tier: str | None = "basic"
    plan: str = "core_small_hotel"
    subscription_plan: str | None = None
    location: str | None = None
    amenities: list[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    modules: dict[str, bool] = Field(
        default_factory=lambda: {
            "pms": True,
            "reports": True,
            "invoices": True,
            "ai": True,
        }
    )
    features: dict[str, bool] | None = None

class User(BaseModel):
    model_config = ConfigDict(extra="allow")  # Changed from "ignore" to "allow" to fix tenant_id loading
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str | None = None  # Hotel ID
    agency_id: str | None = None  # Agency ID (new for agency users)
    email: EmailStr
    name: str
    role: UserRole
    phone: str | None = None
    is_active: bool = True
    email_verified: bool = False
    email_verified_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    password: str | None = Field(None, exclude=True)  # Exclude password from responses

# Helper function (defined after User class)
def _ensure_hotel_context(user: User):
    """Ensure user has hotel/tenant context"""
    if not getattr(user, "tenant_id", None):
        raise HTTPException(status_code=403, detail="Hotel context required")

class TenantRegister(BaseModel):
    property_name: str
    property_type: str | None = "city_hotel"
    email: EmailStr
    password: str
    name: str
    phone: str
    address: str
    location: str | None = None
    total_rooms: int | None = None
    description: str | None = None
    subscription_days: int | None = None
    subscription_plan: str | None = None
    subscription_tier: str | None = "basic"

class GuestRegister(BaseModel):
    email: EmailStr
    password: str
    name: str
    phone: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: User
    tenant: Tenant | None = None

class NotificationPreferences(BaseModel):
    model_config = ConfigDict(extra="ignore")
    user_id: str
    email_notifications: bool = True
    whatsapp_notifications: bool = False
    in_app_notifications: bool = True
    booking_updates: bool = True
    promotional: bool = True
    room_service_updates: bool = True

# Room Models
class RoomCreate(BaseModel):
    room_number: str
    room_type: str
    floor: int
    capacity: int
    base_price: float
    amenities: list[str] = []

    # Extended fields
    view: str | None = None  # e.g. sea, city, garden, mountain
    bed_type: str | None = None

class Room(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_number: str
    room_type: str
    floor: int
    capacity: int
    base_price: float | None = None
    price_per_night: float | None = None
    status: RoomStatus = RoomStatus.AVAILABLE
    amenities: list[str] = []

    # Extended fields
    view: str | None = None
    bed_type: str | None = None
    images: list[str] = []  # stored paths/urls

    # Virtual room (for no-show bookings)
    is_virtual: bool = False

    # Soft delete
    is_active: bool = True
    deleted_at: str | None = None

    current_booking_id: str | None = None
    last_cleaned: datetime | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class HousekeepingTask(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_id: str
    task_type: str  # cleaning, inspection, maintenance
    assigned_to: str | None = None
    status: str = "pending"  # pending, in_progress, completed
    priority: str = "normal"  # low, normal, high, urgent
    notes: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MaintenanceWorkOrder(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str | None = None
    room_id: str | None = None
    room_number: str | None = None
    issue_type: str  # plumbing, hvac, electrical, furniture, housekeeping_damage, other
    priority: str = "normal"  # low, normal, high, urgent
    status: str = "open"  # open, in_progress, completed, cancelled
    source: str = "housekeeping"  # housekeeping, frontdesk, sensor, gm, other
    description: str | None = None
    reported_by_user_id: str | None = None
    asset_id: str | None = None
    plan_id: str | None = None

    reported_by_role: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class SensorAlert(BaseModel):
    """IoT sensör uyarısı modeli - sensörden gelen ham veriyi ve bağlamı temsil eder"""
    id: str | None = None
    tenant_id: str | None = None
    sensor_id: str
    room_id: str | None = None
    room_number: str | None = None
    metric: str  # e.g. temperature, humidity, water_leak, door_open
    value: float
    threshold: float | None = None
    threshold_breached: bool | None = None
    severity: str = "info"  # info, warning, high, critical


class MaintenanceAsset(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str | None = None
    name: str
    asset_type: str  # hvac, plumbing, electrical, elevator, room_fixture, other
    room_id: str | None = None
    room_number: str | None = None
    location: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    installed_at: datetime | None = None
    warranty_until: datetime | None = None
    status: str = "active"  # active, retired, out_of_service


class PreventiveMaintenancePlan(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str | None = None
    asset_id: str | None = None
    asset_type: str | None = None
    frequency_type: str  # days, weeks, months
    frequency_value: int
    next_due_date: datetime
    last_completed_date: datetime | None = None
    description: str | None = None
    default_issue_type: str = "other"
    default_priority: str = "normal"
    is_active: bool = True

    message: str | None = None
    metadata: dict | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    completed_at: datetime | None = None


# Company Models
class CompanyCreate(BaseModel):
    name: str
    corporate_code: str | None = None
    tax_number: str | None = None
    billing_address: str | None = None
    contact_person: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    contracted_rate: ContractedRateType | None = None
    default_rate_type: RateType | None = None
    default_market_segment: MarketSegment | None = None
    default_cancellation_policy: CancellationPolicyType | None = None
    room_nights_commitment: int | None = None

    payment_terms: str | None = None
    status: CompanyStatus = CompanyStatus.PENDING

class Company(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    corporate_code: str | None = None
    tax_number: str | None = None
    billing_address: str | None = None
    contact_person: str | None = None
    contact_email: EmailStr | None = None
    contact_phone: str | None = None
    contracted_rate: ContractedRateType | None = None
    default_rate_type: RateType | None = None
    default_market_segment: MarketSegment | None = None
    default_cancellation_policy: CancellationPolicyType | None = None
    payment_terms: str | None = None
    status: CompanyStatus = CompanyStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Finance Mobile Models - Bank Accounts & Credit Limits
class BankAccount(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    bank_name: str  # Garanti BBVA, İş Bankası, etc.
    account_number: str
    iban: str
    currency: str = "TRY"
    current_balance: float = 0.0
    available_balance: float = 0.0
    account_type: str = "checking"  # checking, savings, etc.
    is_active: bool = True
    api_enabled: bool = False  # Future: Open Banking API integration
    api_credentials: dict[str, Any] | None = None  # API keys/tokens
    last_sync: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class CreditLimit(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    company_id: str  # Link to Company model
    company_name: str | None = None
    credit_limit: float = 0.0
    monthly_limit: float | None = None
    current_debt: float = 0.0
    available_credit: float = 0.0
    payment_terms_days: int = 30  # Net 30, Net 60, etc.
    risk_level: RiskLevel = RiskLevel.NORMAL
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class Expense(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    expense_number: str
    date: datetime
    amount: float
    category: str  # Personnel, Utilities, Maintenance, etc.
    department: DepartmentType
    vendor: str | None = None
    description: str
    payment_method: PaymentMethod
    paid: bool = False
    approved_by: str | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class CashFlow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    transaction_type: str  # inflow, outflow
    amount: float
    currency: str = "TRY"
    date: datetime
    category: str
    reference_id: str | None = None  # Link to payment, expense, etc.
    reference_type: str | None = None  # payment, expense, invoice, etc.
    bank_account_id: str | None = None
    description: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class CityLedgerTransaction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    account_id: str
    transaction_type: str  # charge, payment
    amount: float
    description: str
    reference_number: str | None = None
    posted_by: str
    transaction_date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Maintenance & Technical Service Models
class SLAConfiguration(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    priority: MaintenancePriority
    response_time_minutes: int  # Yanıt süresi (dakika)
    resolution_time_minutes: int  # Çözüm süresi (dakika)
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class SparePart(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    part_number: str
    part_name: str
    description: str | None = None
    category: str  # Plumbing, Electrical, HVAC, etc.
    warehouse_location: WarehouseLocation
    current_stock: int = 0
    minimum_stock: int = 0
    unit_price: float = 0.0
    supplier: str | None = None
    qr_code: str | None = None
    last_restocked: datetime | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class SparePartUsage(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    task_id: str
    spare_part_id: str
    part_name: str
    quantity: int
    unit_price: float
    total_cost: float
    used_by: str  # User who used the part
    used_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    notes: str | None = None

class TaskPhoto(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    task_id: str
    photo_url: str  # URL or base64 data
    photo_type: str  # before, during, after
    description: str | None = None
    uploaded_by: str
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class AssetMaintenanceHistory(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    asset_id: str  # Equipment/Asset ID
    asset_name: str
    task_id: str
    maintenance_type: MaintenanceType
    description: str
    parts_cost: float = 0.0
    labor_cost: float = 0.0
    total_cost: float = 0.0
    technician: str
    completed_at: datetime
    downtime_minutes: int | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class PlannedMaintenance(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    asset_id: str
    asset_name: str
    maintenance_type: MaintenanceType
    frequency_days: int  # Periyot (gün)
    last_maintenance: datetime | None = None
    next_maintenance: datetime
    estimated_duration_minutes: int
    assigned_to: str | None = None
    is_active: bool = True
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC()))

class MaintenanceTaskExtended(BaseModel):
    """Extended maintenance task with all new fields"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    task_number: str
    title: str
    description: str
    priority: MaintenancePriority
    status: MaintenanceTaskStatus
    maintenance_type: MaintenanceType
    asset_id: str | None = None
    asset_name: str | None = None
    room_id: str | None = None
    room_number: str | None = None
    reported_by: str
    assigned_to: str | None = None
    estimated_duration_minutes: int | None = None
    actual_duration_minutes: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None
    on_hold_at: datetime | None = None
    on_hold_reason: str | None = None
    parts_waiting: bool = False
    parts_list: list[str] = []
    photos: list[str] = []  # Photo IDs
    notes: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))



# F&B Management Models
class Outlet(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    outlet_type: OutletType
    department: str  # F&B department
    location: str
    capacity: int
    is_active: bool = True
    opening_time: str | None = None
    closing_time: str | None = None
    contact_phone: str | None = None
    manager: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class Ingredient(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    category: str  # Meat, Vegetables, Dairy, Beverages, etc.
    unit: MeasurementUnit
    current_stock: float = 0.0
    minimum_stock: float = 0.0
    unit_cost: float = 0.0
    supplier: str | None = None
    last_restocked: datetime | None = None
    expiry_date: datetime | None = None
    storage_location: str = "main_kitchen"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class RecipeIngredient(BaseModel):
    ingredient_id: str
    ingredient_name: str
    quantity: float
    unit: MeasurementUnit
    cost: float

class Recipe(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    menu_item_id: str
    menu_item_name: str
    ingredients: list[RecipeIngredient] = []
    preparation_time_minutes: int
    serving_size: int = 1
    total_cost: float = 0.0
    selling_price: float = 0.0
    profit_margin: float = 0.0
    notes: str | None = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class POSOrder(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    order_number: str
    outlet_id: str
    outlet_name: str
    table_number: str | None = None
    room_number: str | None = None
    order_type: str  # dine_in, room_service, takeaway
    items: list[dict[str, Any]] = []
    subtotal: float = 0.0
    tax: float = 0.0
    service_charge: float = 0.0
    total: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    waiter: str | None = None
    chef: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    ready_at: datetime | None = None
    served_at: datetime | None = None
    notes: str | None = None

class StockConsumption(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    ingredient_id: str
    ingredient_name: str
    consumed_quantity: float


# Front Office Mobile Models
class GuestRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    booking_id: str | None = None
    guest_id: str | None = None
    room_number: str | None = None
    request_type: GuestRequestType
    status: GuestRequestStatus = GuestRequestStatus.PENDING
    priority: str = "normal"  # low, normal, high, urgent
    description: str
    assigned_to: str | None = None
    requested_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    assigned_at: datetime | None = None
    completed_at: datetime | None = None
    notes: str | None = None
    created_by: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class IDScanResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    scan_type: str  # passport, id_card, driving_license
    first_name: str
    last_name: str
    nationality: str
    id_number: str
    date_of_birth: str | None = None
    issue_date: str | None = None
    expiry_date: str | None = None
    scan_image: str | None = None  # Base64 image
    scanned_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    scanned_by: str

class MobileCheckIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    booking_id: str
    guest_id: str
    room_id: str
    room_number: str
    check_in_status: CheckInStatus
    id_scan_id: str | None = None
    signature: str | None = None  # Base64 signature image
    registration_card_signed: bool = False
    keys_issued: bool = False
    welcome_package_given: bool = False
    check_in_time: datetime | None = None
    checked_in_by: str
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Housekeeping Enhanced Models
class InspectionChecklistItem(BaseModel):
    area: str  # bathroom, bedroom, minibar, amenities, etc.
    item: str  # towels, soap, remote, etc.
    status: str  # ok, missing, damaged, dirty
    notes: str | None = None

class RoomInspection(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_id: str
    room_number: str
    inspection_type: str  # checkout, maintenance, quality, routine
    inspector: str
    inspection_status: InspectionStatus = InspectionStatus.PENDING
    checklist: list[InspectionChecklistItem] = []
    photos: list[str] = []  # Photo URLs or base64
    notes: str | None = None
    issues_found: list[str] = []
    maintenance_required: bool = False
    maintenance_task_id: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    duration_minutes: int | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class LostFoundItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    item_number: str  # LF-001, LF-002, etc.
    item_description: str
    category: str  # Electronics, Jewelry, Clothing, Documents, etc.
    room_number: str
    found_location: str  # bed, bathroom, closet, etc.
    found_date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    found_by: str
    photos: list[str] = []
    storage_location: str  # Storage room, Safe, etc.
    storage_number: str | None = None
    status: LostFoundStatus = LostFoundStatus.FOUND
    guest_id: str | None = None
    guest_name: str | None = None
    claimed_by: str | None = None
    claimed_date: datetime | None = None
    delivered_to: str | None = None
    delivered_date: datetime | None = None
    delivery_notes: str | None = None
    disposal_date: datetime | None = None
    disposal_reason: str | None = None
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class HKTaskAssignment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    assignment_date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    staff_id: str
    staff_name: str
    assigned_rooms: list[str] = []  # Room IDs
    room_count: int = 0
    status: str = "assigned"  # assigned, in_progress, completed
    assigned_by: str
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class CleaningTimer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_id: str
    room_number: str
    staff_id: str
    staff_name: str
    task_type: str  # checkout, stayover, deep_clean, turndown
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    duration_minutes: int | None = None
    status: str = "in_progress"  # in_progress, completed, paused
    notes: str | None = None



# Revenue Management Models
class RateOverride(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_type: str
    date: datetime
    original_rate: float
    override_rate: float
    reason: str
    approved_by: str
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class RevenueForecast(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    forecast_date: datetime
    forecast_period: str  # daily, weekly, monthly
    projected_occupancy: float
    projected_adr: float
    projected_revpar: float
    projected_revenue: float
    confidence_level: float = 0.0
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class DemandData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    date: datetime
    demand_level: str  # low, medium, high, very_high
    booking_count: int
    search_count: int = 0
    competitor_rate_avg: float = 0.0
    notes: str | None = None

    unit: MeasurementUnit
    order_id: str | None = None
    recipe_id: str | None = None
    outlet_id: str
    outlet_name: str
    cost: float
    consumed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    recorded_by: str


# Guest & Booking Models
class GuestCreate(BaseModel):
    name: str
    email: str = ""
    phone: str
    id_number: str
    nationality: str | None = None
    address: str | None = None
    vip_status: bool = False

class Guest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    email: str = ""
    phone: str
    id_number: str
    nationality: str | None = None
    address: str | None = None
    vip_status: bool = False
    loyalty_points: int = 0
    total_stays: int = 0
    total_spend: float = 0.0
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class BookingCreate(BaseModel):
    guest_id: str
    room_id: str
    check_in: str
    check_out: str
    adults: int = 1
    children: int = 0

    # CM / integration semantics (optional; defaults applied in Booking model)
    source_channel: str | None = None
    origin: str | None = None
    hold_status: str | None = None
    allocation_source: str | None = None
    children_ages: list[int] = []
    guests_count: int  # Total: adults + children
    total_amount: float
    base_rate: float | None = None  # For override tracking
    channel: ChannelType = ChannelType.DIRECT
    special_requests: str | None = None
    rate_plan: str | None = None
    # New fields for corporate/contracted bookings
    company_id: str | None = None
    contracted_rate: ContractedRateType | None = None
    rate_type: RateType | None = None
    market_segment: MarketSegment | None = None
    cancellation_policy: CancellationPolicyType | None = None
    billing_address: str | None = None
    billing_tax_number: str | None = None
    billing_contact_person: str | None = None
    # Override tracking
    override_reason: str | None = None
    # OTA Channel fields
    ota_channel: OTAChannel | None = None
    ota_confirmation: str | None = None
    ota_reference_id: str | None = None
    commission_pct: float | None = None
    payment_model: OTAPaymentModel | None = None
    virtual_card_provided: bool = False
    virtual_card_number: str | None = None
    virtual_card_expiry: str | None = None

class Booking(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    room_id: str

REJECTED_STATUS = "rejected"

class BookingExtended(BaseModel):
    """Extended booking model with CM/integration fields"""
    # CM / integration semantics (defaults chosen by user)
    source_channel: str = "direct"  # direct|agency|airbnb|booking|expedia|manual
    origin: str = "ui"  # ui|api|webhook|import
    hold_status: str = "none"  # none|tentative|hold|released|expired
    allocation_source: str = "manual"  # manual|channel|allotment
    # Enriched fields for calendar display
    guest_name: str | None = None
    room_number: str | None = None
    check_in: datetime
    check_out: datetime
    adults: int = 1
    children: int = 0
    children_ages: list[int] = []
    guests_count: int | None = None
    total_amount: float
    base_rate: float | None = None
    paid_amount: float = 0.0
    status: BookingStatus = BookingStatus.PENDING
    group_booking_id: str | None = None
    channel: ChannelType = ChannelType.DIRECT
    rate_plan: str | None = "Standard"
    special_requests: str | None = None
    # Corporate/contracted booking fields
    company_id: str | None = None
    contracted_rate: ContractedRateType | None = None
    rate_type: RateType | None = None
    market_segment: MarketSegment | None = None
    cancellation_policy: CancellationPolicyType | None = None
    billing_address: str | None = None
    billing_tax_number: str | None = None
    billing_contact_person: str | None = None
    # OTA Channel fields
    ota_channel: OTAChannel | None = None
    ota_confirmation: str | None = None
    ota_reference_id: str | None = None
    commission_pct: float | None = None
    payment_model: OTAPaymentModel | None = None
    virtual_card_provided: bool = False
    virtual_card_number: str | None = None
    virtual_card_expiry: str | None = None
    # System fields
    qr_code: str | None = None
    qr_code_data: str | None = None
    checked_in_at: datetime | None = None
    checked_out_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

# Folio & Payment Models
class FolioCreate(BaseModel):
    booking_id: str
    folio_type: FolioType
    guest_id: str | None = None
    company_id: str | None = None
    notes: str | None = None

class Folio(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    booking_id: str
    folio_number: str  # e.g., "F-2024-0001"
    folio_type: FolioType
    status: FolioStatus = FolioStatus.OPEN
    guest_id: str | None = None
    company_id: str | None = None
    balance: float = 0.0  # Total charges - Total payments
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    closed_at: datetime | None = None

class ChargeCreate(BaseModel):
    charge_category: ChargeCategory
    description: str
    amount: float
    quantity: float = 1.0
    auto_calculate_tax: bool = False

class FolioCharge(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    folio_id: str
    booking_id: str
    charge_category: ChargeCategory
    description: str
    unit_price: float
    quantity: float = 1.0
    amount: float  # unit_price * quantity
    tax_amount: float = 0.0
    total: float  # amount + tax_amount
    date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    posted_by: str | None = None
    voided: bool = False
    void_reason: str | None = None
    voided_by: str | None = None
    voided_at: datetime | None = None

class PaymentCreate(BaseModel):
    amount: float
    method: PaymentMethod
    payment_type: PaymentType
    reference: str | None = None
    notes: str | None = None

class Payment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    folio_id: str
    booking_id: str
    amount: float
    method: PaymentMethod
    payment_type: PaymentType
    status: PaymentStatus = PaymentStatus.PAID
    voided: bool = False
    voided_by: str | None = None
    voided_at: datetime | None = None
    void_reason: str | None = None
    reference: str | None = None
    notes: str | None = None
    processed_by: str | None = None
    processed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class FolioOperationCreate(BaseModel):
    operation_type: FolioOperationType
    from_folio_id: str
    to_folio_id: str | None = None
    charge_ids: list[str] = []  # For transfer operations
    amount: float | None = None
    reason: str

class Package(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    code: str
    description: str | None = None
    included_services: list[str] = []
    price_type: str = "per_room"  # per_room, per_person, per_stay
    additional_amount: float = 0.0
    linked_rate_plan_ids: list[str] = []
    is_active: bool = True


class FolioOperation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    operation_type: FolioOperationType
    from_folio_id: str
    to_folio_id: str | None = None
    charge_ids: list[str] = []
    amount: float | None = None
    reason: str
    performed_by: str
    performed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class CityTaxRule(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    tax_percentage: float
    flat_amount: float | None = None  # If not percentage-based
    per_night: bool = True
    exempt_market_segments: list[MarketSegment] = []
    min_nights: int | None = None
    max_nights: int | None = None
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

# Audit Log Model
class AuditLog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    user_id: str
    user_name: str
    user_role: UserRole
    action: str  # e.g., "CREATE_BOOKING", "POST_CHARGE", "OVERRIDE_RATE"
    entity_type: str  # e.g., "booking", "folio", "charge", "payment"
    entity_id: str
    changes: dict | None = None  # Old and new values
    ip_address: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

# Rate Override Log Model
class RateOverrideLog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    booking_id: str
    user_id: str
    user_name: str | None = None
    base_rate: float
    new_rate: float
    override_reason: str
    ip_address: str | None = None
    terminal: str | None = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

# Room Move History Model
class RoomMoveHistory(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    booking_id: str
    old_room: str  # Room number
    new_room: str  # Room number
    old_check_in: str
    new_check_in: str
    reason: str
    moved_by: str  # User name
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))

# Channel Manager Models
class ChannelConnection(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    channel_type: ChannelType
    channel_name: str
    status: ChannelStatus = ChannelStatus.INACTIVE
    api_endpoint: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    property_id: str | None = None  # Channel's property ID
    last_sync: datetime | None = None
    sync_rate_availability: bool = True
    sync_reservations: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class ChannelConnectionCreate(BaseModel):
    channel_type: ChannelType
    channel_name: str
    property_id: str | None = None
    api_endpoint: str | None = None
    api_key: str | None = None
    api_secret: str | None = None
    sync_rate_availability: bool = True
    sync_reservations: bool = True

class RoomMapping(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    channel_id: str
    pms_room_type: str  # PMS room type
    channel_room_type: str  # Channel's room type name
    channel_room_id: str | None = None
    status: MappingStatus = MappingStatus.MAPPED
    notes: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class RoomMappingCreate(BaseModel):
    channel_id: str
    pms_room_type: str
    channel_room_type: str
    channel_room_id: str | None = None
    notes: str | None = None

class RatePlan(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    code: str
    description: str | None = None
    room_type: str
    base_rate: float
    base_price: float | None = None  # For compatibility
    pricing_strategy: PricingStrategy = PricingStrategy.STATIC
    min_rate: float | None = None
    max_rate: float | None = None
    active_channels: list[ChannelType] = []
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class RateUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    rate_plan_id: str
    date: str  # YYYY-MM-DD
    rate: float
    availability: int
    min_stay: int = 1
    max_stay: int | None = None
    stop_sell: bool = False
    pushed_to_channels: list[ChannelType] = []
    push_status: dict = {}  # {channel: status}
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class OTAReservation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    channel_type: ChannelType
    channel_booking_id: str  # OTA's booking ID
    pms_booking_id: str | None = None  # Created PMS booking ID
    guest_name: str
    guest_email: str | None = None
    guest_phone: str | None = None
    room_type: str
    check_in: str
    check_out: str
    adults: int
    children: int = 0
    total_amount: float
    commission_amount: float | None = None
    status: str = "pending"  # pending, imported, error
    error_message: str | None = None
    raw_data: dict | None = None
    received_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    processed_at: datetime | None = None

class ExceptionQueue(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    exception_type: str  # "mapping_error", "rate_push_failed", "reservation_import_failed"
    channel_type: ChannelType
    entity_id: str | None = None
    error_message: str
    details: dict | None = None
    status: str = "pending"  # pending, resolved, ignored
    resolved_by: str | None = None
    resolved_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class RMSSuggestion(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    date: str  # YYYY-MM-DD
    room_type: str
    current_rate: float
    suggested_rate: float
    reason: str  # e.g., "High demand detected", "Competitor analysis"
    confidence_score: float  # 0-100
    based_on: dict  # {occupancy, pickup_pace, competitor_rates, etc.}
    status: str = "pending"  # pending, applied, rejected
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

# Room Service Models
class RoomServiceCreate(BaseModel):
    booking_id: str
    service_type: str
    description: str
    notes: str | None = None

class RoomService(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    booking_id: str
    guest_id: str
    service_type: str
    description: str
    notes: str | None = None
    status: RoomServiceStatus = RoomServiceStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None

# Invoice Models
class InvoiceItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    total: float

class InvoiceCreate(BaseModel):
    booking_id: str | None = None
    customer_name: str
    customer_email: str
    items: list[InvoiceItem]
    subtotal: float
    tax: float
    total: float
    due_date: str
    notes: str | None = None

class Invoice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    invoice_number: str
    booking_id: str | None = None
    customer_name: str
    customer_email: str
    items: list[InvoiceItem]
    subtotal: float
    tax: float
    total: float
    status: InvoiceStatus = InvoiceStatus.DRAFT
    issue_date: datetime = Field(default_factory=lambda: datetime.now(UTC))
    due_date: datetime
    notes: str | None = None

# Loyalty Models
class LoyaltyProgramCreate(BaseModel):
    guest_id: str
    tier: LoyaltyTier = LoyaltyTier.BRONZE
    points: int = 0
    lifetime_points: int = 0

class LoyaltyProgram(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    tier: LoyaltyTier = LoyaltyTier.BRONZE
    points: int = 0
    lifetime_points: int = 0
    last_activity: datetime = Field(default_factory=lambda: datetime.now(UTC))

class LoyaltyTransactionCreate(BaseModel):
    guest_id: str
    points: int
    transaction_type: str
    description: str

class LoyaltyTransaction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    points: int
    transaction_type: str
    description: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

# Marketplace Models
class Product(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    category: str
    description: str
    price: float
    unit: str
    supplier: str
    image_url: str | None = None
    in_stock: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

class OrderCreate(BaseModel):
    items: list[dict[str, Any]]
    total_amount: float
    delivery_address: str

class Order(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    items: list[dict[str, Any]]
    total_amount: float
    status: str = "pending"
    delivery_address: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

# RMS Models
class PriceAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_type: str
    date: datetime
    current_price: float
    suggested_price: float
    occupancy_rate: float
    demand_score: float
    competitor_avg: float | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

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

