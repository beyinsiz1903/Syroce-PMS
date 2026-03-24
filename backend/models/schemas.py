"""
Syroce PMS - Pydantic Schema Definitions
All request/response models used across the application.
Extracted from server.py for modularity.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

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
    property_type: Optional[str] = "hotel"
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    address: Optional[str] = None
    total_rooms: Optional[int] = 50
    subscription_status: str = "active"
    subscription_start_date: Optional[str] = None
    subscription_end_date: Optional[str] = None
    subscription_tier: Optional[str] = "basic"
    plan: str = "core_small_hotel"
    subscription_plan: Optional[str] = None
    location: Optional[str] = None
    amenities: List[str] = []
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    modules: Dict[str, bool] = Field(
        default_factory=lambda: {
            "pms": True,
            "reports": True,
            "invoices": True,
            "ai": True,
        }
    )
    features: Optional[Dict[str, bool]] = None

class User(BaseModel):
    model_config = ConfigDict(extra="allow")  # Changed from "ignore" to "allow" to fix tenant_id loading
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: Optional[str] = None  # Hotel ID
    agency_id: Optional[str] = None  # Agency ID (new for agency users)
    email: EmailStr
    name: str
    role: UserRole
    phone: Optional[str] = None
    is_active: bool = True
    email_verified: bool = False
    email_verified_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    password: Optional[str] = Field(None, exclude=True)  # Exclude password from responses

# Helper function (defined after User class)
def _ensure_hotel_context(user: User):
    """Ensure user has hotel/tenant context"""
    if not getattr(user, "tenant_id", None):
        raise HTTPException(status_code=403, detail="Hotel context required")

class TenantRegister(BaseModel):
    property_name: str
    email: EmailStr
    password: str
    name: str
    phone: str
    address: str
    location: Optional[str] = None
    description: Optional[str] = None
    subscription_days: Optional[int] = None  # Duration in days (30, 60, 90, 180, 365, None=unlimited)
    subscription_plan: Optional[str] = None  # e.g. core_small_hotel, pms_lite
    subscription_tier: Optional[str] = "basic"  # basic, professional, enterprise

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
    tenant: Optional[Tenant] = None

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
    amenities: List[str] = []

    # Extended fields
    view: Optional[str] = None  # e.g. sea, city, garden, mountain
    bed_type: Optional[str] = None

class Room(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_number: str
    room_type: str
    floor: int
    capacity: int
    base_price: Optional[float] = None
    price_per_night: Optional[float] = None
    status: RoomStatus = RoomStatus.AVAILABLE
    amenities: List[str] = []

    # Extended fields
    view: Optional[str] = None
    bed_type: Optional[str] = None
    images: List[str] = []  # stored paths/urls

    # Soft delete
    is_active: bool = True
    deleted_at: Optional[str] = None

    current_booking_id: Optional[str] = None
    last_cleaned: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class HousekeepingTask(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_id: str
    task_type: str  # cleaning, inspection, maintenance
    assigned_to: Optional[str] = None
    status: str = "pending"  # pending, in_progress, completed
    priority: str = "normal"  # low, normal, high, urgent
    notes: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MaintenanceWorkOrder(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: Optional[str] = None
    room_id: Optional[str] = None
    room_number: Optional[str] = None
    issue_type: str  # plumbing, hvac, electrical, furniture, housekeeping_damage, other
    priority: str = "normal"  # low, normal, high, urgent
    status: str = "open"  # open, in_progress, completed, cancelled
    source: str = "housekeeping"  # housekeeping, frontdesk, sensor, gm, other
    description: Optional[str] = None
    reported_by_user_id: Optional[str] = None
    asset_id: Optional[str] = None
    plan_id: Optional[str] = None

    reported_by_role: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class SensorAlert(BaseModel):
    """IoT sensör uyarısı modeli - sensörden gelen ham veriyi ve bağlamı temsil eder"""
    id: Optional[str] = None
    tenant_id: Optional[str] = None
    sensor_id: str
    room_id: Optional[str] = None
    room_number: Optional[str] = None
    metric: str  # e.g. temperature, humidity, water_leak, door_open
    value: float
    threshold: Optional[float] = None
    threshold_breached: Optional[bool] = None
    severity: str = "info"  # info, warning, high, critical


class MaintenanceAsset(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: Optional[str] = None
    name: str
    asset_type: str  # hvac, plumbing, electrical, elevator, room_fixture, other
    room_id: Optional[str] = None
    room_number: Optional[str] = None
    location: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    installed_at: Optional[datetime] = None
    warranty_until: Optional[datetime] = None
    status: str = "active"  # active, retired, out_of_service


class PreventiveMaintenancePlan(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: Optional[str] = None
    asset_id: Optional[str] = None
    asset_type: Optional[str] = None
    frequency_type: str  # days, weeks, months
    frequency_value: int
    next_due_date: datetime
    last_completed_date: Optional[datetime] = None
    description: Optional[str] = None
    default_issue_type: str = "other"
    default_priority: str = "normal"
    is_active: bool = True

    message: Optional[str] = None
    metadata: Optional[dict] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    completed_at: Optional[datetime] = None


# Company Models
class CompanyCreate(BaseModel):
    name: str
    corporate_code: Optional[str] = None
    tax_number: Optional[str] = None
    billing_address: Optional[str] = None
    contact_person: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    contracted_rate: Optional[ContractedRateType] = None
    default_rate_type: Optional[RateType] = None
    default_market_segment: Optional[MarketSegment] = None
    default_cancellation_policy: Optional[CancellationPolicyType] = None
    room_nights_commitment: Optional[int] = None

    payment_terms: Optional[str] = None
    status: CompanyStatus = CompanyStatus.PENDING

class Company(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    corporate_code: Optional[str] = None
    tax_number: Optional[str] = None
    billing_address: Optional[str] = None
    contact_person: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    contracted_rate: Optional[ContractedRateType] = None
    default_rate_type: Optional[RateType] = None
    default_market_segment: Optional[MarketSegment] = None
    default_cancellation_policy: Optional[CancellationPolicyType] = None
    payment_terms: Optional[str] = None
    status: CompanyStatus = CompanyStatus.ACTIVE
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


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
    api_credentials: Optional[Dict[str, Any]] = None  # API keys/tokens
    last_sync: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CreditLimit(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    company_id: str  # Link to Company model
    company_name: Optional[str] = None
    credit_limit: float = 0.0
    monthly_limit: Optional[float] = None
    current_debt: float = 0.0
    available_credit: float = 0.0
    payment_terms_days: int = 30  # Net 30, Net 60, etc.
    risk_level: RiskLevel = RiskLevel.NORMAL
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class Expense(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    expense_number: str
    date: datetime
    amount: float
    category: str  # Personnel, Utilities, Maintenance, etc.
    department: DepartmentType
    vendor: Optional[str] = None
    description: str
    payment_method: PaymentMethod
    paid: bool = False
    approved_by: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CashFlow(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    transaction_type: str  # inflow, outflow
    amount: float
    currency: str = "TRY"
    date: datetime
    category: str
    reference_id: Optional[str] = None  # Link to payment, expense, etc.
    reference_type: Optional[str] = None  # payment, expense, invoice, etc.
    bank_account_id: Optional[str] = None
    description: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CityLedgerTransaction(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    account_id: str
    transaction_type: str  # charge, payment
    amount: float
    description: str
    reference_number: Optional[str] = None
    posted_by: str
    transaction_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Maintenance & Technical Service Models
class SLAConfiguration(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    priority: MaintenancePriority
    response_time_minutes: int  # Yanıt süresi (dakika)
    resolution_time_minutes: int  # Çözüm süresi (dakika)
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class SparePart(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    part_number: str
    part_name: str
    description: Optional[str] = None
    category: str  # Plumbing, Electrical, HVAC, etc.
    warehouse_location: WarehouseLocation
    current_stock: int = 0
    minimum_stock: int = 0
    unit_price: float = 0.0
    supplier: Optional[str] = None
    qr_code: Optional[str] = None
    last_restocked: Optional[datetime] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    used_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None

class TaskPhoto(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    task_id: str
    photo_url: str  # URL or base64 data
    photo_type: str  # before, during, after
    description: Optional[str] = None
    uploaded_by: str
    uploaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    downtime_minutes: Optional[int] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class PlannedMaintenance(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    asset_id: str
    asset_name: str
    maintenance_type: MaintenanceType
    frequency_days: int  # Periyot (gün)
    last_maintenance: Optional[datetime] = None
    next_maintenance: datetime
    estimated_duration_minutes: int
    assigned_to: Optional[str] = None
    is_active: bool = True
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc()))

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
    asset_id: Optional[str] = None
    asset_name: Optional[str] = None
    room_id: Optional[str] = None
    room_number: Optional[str] = None
    reported_by: str
    assigned_to: Optional[str] = None
    estimated_duration_minutes: Optional[int] = None
    actual_duration_minutes: Optional[int] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    on_hold_at: Optional[datetime] = None
    on_hold_reason: Optional[str] = None
    parts_waiting: bool = False
    parts_list: List[str] = []
    photos: List[str] = []  # Photo IDs
    notes: Optional[str] = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))



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
    opening_time: Optional[str] = None
    closing_time: Optional[str] = None
    contact_phone: Optional[str] = None
    manager: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    supplier: Optional[str] = None
    last_restocked: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    storage_location: str = "main_kitchen"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    ingredients: List[RecipeIngredient] = []
    preparation_time_minutes: int
    serving_size: int = 1
    total_cost: float = 0.0
    selling_price: float = 0.0
    profit_margin: float = 0.0
    notes: Optional[str] = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class POSOrder(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    order_number: str
    outlet_id: str
    outlet_name: str
    table_number: Optional[str] = None
    room_number: Optional[str] = None
    order_type: str  # dine_in, room_service, takeaway
    items: List[Dict[str, Any]] = []
    subtotal: float = 0.0
    tax: float = 0.0
    service_charge: float = 0.0
    total: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    waiter: Optional[str] = None
    chef: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    ready_at: Optional[datetime] = None
    served_at: Optional[datetime] = None
    notes: Optional[str] = None

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
    booking_id: Optional[str] = None
    guest_id: Optional[str] = None
    room_number: Optional[str] = None
    request_type: GuestRequestType
    status: GuestRequestStatus = GuestRequestStatus.PENDING
    priority: str = "normal"  # low, normal, high, urgent
    description: str
    assigned_to: Optional[str] = None
    requested_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    assigned_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    notes: Optional[str] = None
    created_by: str
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class IDScanResult(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    scan_type: str  # passport, id_card, driving_license
    first_name: str
    last_name: str
    nationality: str
    id_number: str
    date_of_birth: Optional[str] = None
    issue_date: Optional[str] = None
    expiry_date: Optional[str] = None
    scan_image: Optional[str] = None  # Base64 image
    scanned_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
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
    id_scan_id: Optional[str] = None
    signature: Optional[str] = None  # Base64 signature image
    registration_card_signed: bool = False
    keys_issued: bool = False
    welcome_package_given: bool = False
    check_in_time: Optional[datetime] = None
    checked_in_by: str
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# Housekeeping Enhanced Models
class InspectionChecklistItem(BaseModel):
    area: str  # bathroom, bedroom, minibar, amenities, etc.
    item: str  # towels, soap, remote, etc.
    status: str  # ok, missing, damaged, dirty
    notes: Optional[str] = None

class RoomInspection(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_id: str
    room_number: str
    inspection_type: str  # checkout, maintenance, quality, routine
    inspector: str
    inspection_status: InspectionStatus = InspectionStatus.PENDING
    checklist: List[InspectionChecklistItem] = []
    photos: List[str] = []  # Photo URLs or base64
    notes: Optional[str] = None
    issues_found: List[str] = []
    maintenance_required: bool = False
    maintenance_task_id: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class LostFoundItem(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    item_number: str  # LF-001, LF-002, etc.
    item_description: str
    category: str  # Electronics, Jewelry, Clothing, Documents, etc.
    room_number: str
    found_location: str  # bed, bathroom, closet, etc.
    found_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    found_by: str
    photos: List[str] = []
    storage_location: str  # Storage room, Safe, etc.
    storage_number: Optional[str] = None
    status: LostFoundStatus = LostFoundStatus.FOUND
    guest_id: Optional[str] = None
    guest_name: Optional[str] = None
    claimed_by: Optional[str] = None
    claimed_date: Optional[datetime] = None
    delivered_to: Optional[str] = None
    delivered_date: Optional[datetime] = None
    delivery_notes: Optional[str] = None
    disposal_date: Optional[datetime] = None
    disposal_reason: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class HKTaskAssignment(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    assignment_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    staff_id: str
    staff_name: str
    assigned_rooms: List[str] = []  # Room IDs
    room_count: int = 0
    status: str = "assigned"  # assigned, in_progress, completed
    assigned_by: str
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CleaningTimer(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_id: str
    room_number: str
    staff_id: str
    staff_name: str
    task_type: str  # checkout, stayover, deep_clean, turndown
    started_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None
    duration_minutes: Optional[int] = None
    status: str = "in_progress"  # in_progress, completed, paused
    notes: Optional[str] = None



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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class DemandData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    date: datetime
    demand_level: str  # low, medium, high, very_high
    booking_count: int
    search_count: int = 0
    competitor_rate_avg: float = 0.0
    notes: Optional[str] = None

    unit: MeasurementUnit
    order_id: Optional[str] = None
    recipe_id: Optional[str] = None
    outlet_id: str
    outlet_name: str
    cost: float
    consumed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    recorded_by: str


# Guest & Booking Models
class GuestCreate(BaseModel):
    name: str
    email: str = ""
    phone: str
    id_number: str
    nationality: Optional[str] = None
    address: Optional[str] = None
    vip_status: bool = False

class Guest(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    email: str = ""
    phone: str
    id_number: str
    nationality: Optional[str] = None
    address: Optional[str] = None
    vip_status: bool = False
    loyalty_points: int = 0
    total_stays: int = 0
    total_spend: float = 0.0
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class BookingCreate(BaseModel):
    guest_id: str
    room_id: str
    check_in: str
    check_out: str
    adults: int = 1
    children: int = 0

    # CM / integration semantics (optional; defaults applied in Booking model)
    source_channel: Optional[str] = None
    origin: Optional[str] = None
    hold_status: Optional[str] = None
    allocation_source: Optional[str] = None
    children_ages: List[int] = []
    guests_count: int  # Total: adults + children
    total_amount: float
    base_rate: Optional[float] = None  # For override tracking
    channel: ChannelType = ChannelType.DIRECT
    special_requests: Optional[str] = None
    rate_plan: Optional[str] = None
    # New fields for corporate/contracted bookings
    company_id: Optional[str] = None
    contracted_rate: Optional[ContractedRateType] = None
    rate_type: Optional[RateType] = None
    market_segment: Optional[MarketSegment] = None
    cancellation_policy: Optional[CancellationPolicyType] = None
    billing_address: Optional[str] = None
    billing_tax_number: Optional[str] = None
    billing_contact_person: Optional[str] = None
    # Override tracking
    override_reason: Optional[str] = None
    # OTA Channel fields
    ota_channel: Optional[OTAChannel] = None
    ota_confirmation: Optional[str] = None
    ota_reference_id: Optional[str] = None
    commission_pct: Optional[float] = None
    payment_model: Optional[OTAPaymentModel] = None
    virtual_card_provided: bool = False
    virtual_card_number: Optional[str] = None
    virtual_card_expiry: Optional[str] = None

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
    guest_name: Optional[str] = None
    room_number: Optional[str] = None
    check_in: datetime
    check_out: datetime
    adults: int = 1
    children: int = 0
    children_ages: List[int] = []
    guests_count: Optional[int] = None
    total_amount: float
    base_rate: Optional[float] = None
    paid_amount: float = 0.0
    status: BookingStatus = BookingStatus.PENDING
    group_booking_id: Optional[str] = None
    channel: ChannelType = ChannelType.DIRECT
    rate_plan: Optional[str] = "Standard"
    special_requests: Optional[str] = None
    # Corporate/contracted booking fields
    company_id: Optional[str] = None
    contracted_rate: Optional[ContractedRateType] = None
    rate_type: Optional[RateType] = None
    market_segment: Optional[MarketSegment] = None
    cancellation_policy: Optional[CancellationPolicyType] = None
    billing_address: Optional[str] = None
    billing_tax_number: Optional[str] = None
    billing_contact_person: Optional[str] = None
    # OTA Channel fields
    ota_channel: Optional[OTAChannel] = None
    ota_confirmation: Optional[str] = None
    ota_reference_id: Optional[str] = None
    commission_pct: Optional[float] = None
    payment_model: Optional[OTAPaymentModel] = None
    virtual_card_provided: bool = False
    virtual_card_number: Optional[str] = None
    virtual_card_expiry: Optional[str] = None
    # System fields
    qr_code: Optional[str] = None
    qr_code_data: Optional[str] = None
    checked_in_at: Optional[datetime] = None
    checked_out_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Folio & Payment Models
class FolioCreate(BaseModel):
    booking_id: str
    folio_type: FolioType
    guest_id: Optional[str] = None
    company_id: Optional[str] = None
    notes: Optional[str] = None

class Folio(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    booking_id: str
    folio_number: str  # e.g., "F-2024-0001"
    folio_type: FolioType
    status: FolioStatus = FolioStatus.OPEN
    guest_id: Optional[str] = None
    company_id: Optional[str] = None
    balance: float = 0.0  # Total charges - Total payments
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    closed_at: Optional[datetime] = None

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
    date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    posted_by: Optional[str] = None
    voided: bool = False
    void_reason: Optional[str] = None
    voided_by: Optional[str] = None
    voided_at: Optional[datetime] = None

class PaymentCreate(BaseModel):
    amount: float
    method: PaymentMethod
    payment_type: PaymentType
    reference: Optional[str] = None
    notes: Optional[str] = None

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
    voided_by: Optional[str] = None
    voided_at: Optional[datetime] = None
    void_reason: Optional[str] = None
    reference: Optional[str] = None
    notes: Optional[str] = None
    processed_by: Optional[str] = None
    processed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class FolioOperationCreate(BaseModel):
    operation_type: FolioOperationType
    from_folio_id: str
    to_folio_id: Optional[str] = None
    charge_ids: List[str] = []  # For transfer operations
    amount: Optional[float] = None
    reason: str

class Package(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    code: str
    description: Optional[str] = None
    included_services: List[str] = []
    price_type: str = "per_room"  # per_room, per_person, per_stay
    additional_amount: float = 0.0
    linked_rate_plan_ids: List[str] = []
    is_active: bool = True


class FolioOperation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    operation_type: FolioOperationType
    from_folio_id: str
    to_folio_id: Optional[str] = None
    charge_ids: List[str] = []
    amount: Optional[float] = None
    reason: str
    performed_by: str
    performed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CityTaxRule(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    tax_percentage: float
    flat_amount: Optional[float] = None  # If not percentage-based
    per_night: bool = True
    exempt_market_segments: List[MarketSegment] = []
    min_nights: Optional[int] = None
    max_nights: Optional[int] = None
    active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    changes: Optional[dict] = None  # Old and new values
    ip_address: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Rate Override Log Model
class RateOverrideLog(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    booking_id: str
    user_id: str
    user_name: Optional[str] = None
    base_rate: float
    new_rate: float
    override_reason: str
    ip_address: Optional[str] = None
    terminal: Optional[str] = None
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Channel Manager Models
class ChannelConnection(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    channel_type: ChannelType
    channel_name: str
    status: ChannelStatus = ChannelStatus.INACTIVE
    api_endpoint: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    property_id: Optional[str] = None  # Channel's property ID
    last_sync: Optional[datetime] = None
    sync_rate_availability: bool = True
    sync_reservations: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ChannelConnectionCreate(BaseModel):
    channel_type: ChannelType
    channel_name: str
    property_id: Optional[str] = None
    api_endpoint: Optional[str] = None
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    sync_rate_availability: bool = True
    sync_reservations: bool = True

class RoomMapping(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    channel_id: str
    pms_room_type: str  # PMS room type
    channel_room_type: str  # Channel's room type name
    channel_room_id: Optional[str] = None
    status: MappingStatus = MappingStatus.MAPPED
    notes: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class RoomMappingCreate(BaseModel):
    channel_id: str
    pms_room_type: str
    channel_room_type: str
    channel_room_id: Optional[str] = None
    notes: Optional[str] = None

class RatePlan(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    name: str
    code: str
    description: Optional[str] = None
    room_type: str
    base_rate: float
    base_price: Optional[float] = None  # For compatibility
    pricing_strategy: PricingStrategy = PricingStrategy.STATIC
    min_rate: Optional[float] = None
    max_rate: Optional[float] = None
    active_channels: List[ChannelType] = []
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class RateUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    rate_plan_id: str
    date: str  # YYYY-MM-DD
    rate: float
    availability: int
    min_stay: int = 1
    max_stay: Optional[int] = None
    stop_sell: bool = False
    pushed_to_channels: List[ChannelType] = []
    push_status: dict = {}  # {channel: status}
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OTAReservation(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    channel_type: ChannelType
    channel_booking_id: str  # OTA's booking ID
    pms_booking_id: Optional[str] = None  # Created PMS booking ID
    guest_name: str
    guest_email: Optional[str] = None
    guest_phone: Optional[str] = None
    room_type: str
    check_in: str
    check_out: str
    adults: int
    children: int = 0
    total_amount: float
    commission_amount: Optional[float] = None
    status: str = "pending"  # pending, imported, error
    error_message: Optional[str] = None
    raw_data: Optional[dict] = None
    received_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    processed_at: Optional[datetime] = None

class ExceptionQueue(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    exception_type: str  # "mapping_error", "rate_push_failed", "reservation_import_failed"
    channel_type: ChannelType
    entity_id: Optional[str] = None
    error_message: str
    details: Optional[dict] = None
    status: str = "pending"  # pending, resolved, ignored
    resolved_by: Optional[str] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# Room Service Models
class RoomServiceCreate(BaseModel):
    booking_id: str
    service_type: str
    description: str
    notes: Optional[str] = None

class RoomService(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    booking_id: str
    guest_id: str
    service_type: str
    description: str
    notes: Optional[str] = None
    status: RoomServiceStatus = RoomServiceStatus.PENDING
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

# Invoice Models
class InvoiceItem(BaseModel):
    description: str
    quantity: float
    unit_price: float
    total: float

class InvoiceCreate(BaseModel):
    booking_id: Optional[str] = None
    customer_name: str
    customer_email: str
    items: List[InvoiceItem]
    subtotal: float
    tax: float
    total: float
    due_date: str
    notes: Optional[str] = None

class Invoice(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    invoice_number: str
    booking_id: Optional[str] = None
    customer_name: str
    customer_email: str
    items: List[InvoiceItem]
    subtotal: float
    tax: float
    total: float
    status: InvoiceStatus = InvoiceStatus.DRAFT
    issue_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    due_date: datetime
    notes: Optional[str] = None

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
    last_activity: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    image_url: Optional[str] = None
    in_stock: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class OrderCreate(BaseModel):
    items: List[Dict[str, Any]]
    total_amount: float
    delivery_address: str

class Order(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    items: List[Dict[str, Any]]
    total_amount: float
    status: str = "pending"
    delivery_address: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

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
    competitor_avg: Optional[float] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

# ============= NEW FEATURES PYDANTIC MODELS =============

# Messaging Models
class SendWhatsAppRequest(BaseModel):
    to: str
    message: str
    booking_id: Optional[str] = None

class SendEmailRequest(BaseModel):
    to: str
    subject: str
    message: str
    booking_id: Optional[str] = None

class SendSMSRequest(BaseModel):
    to: str
    message: str
    booking_id: Optional[str] = None

class CreateMessageTemplateRequest(BaseModel):
    name: str
    channel: str
    subject: Optional[str] = None
    content: str = ""
    variables: List[str] = []

# RMS Models
class AddCompetitorRequest(BaseModel):
    name: str
    location: str
    star_rating: float
    url: Optional[str] = None

class ScrapePricesRequest(BaseModel):
    date: str

class AutoPricingRequest(BaseModel):
    start_date: str
    end_date: str
    room_type: Optional[str] = None

class DemandForecastRequest(BaseModel):
    start_date: str
    end_date: str

# Housekeeping Models
class ReportIssueRequest(BaseModel):
    room_id: str
    issue_type: str
    description: str
    priority: str = 'normal'
    photos: List[str] = []

class UploadPhotoRequest(BaseModel):
    task_id: str
    photo_base64: str

# POS Models
class CreatePOSTransactionRequest(BaseModel):
    amount: float
    payment_method: str
    folio_id: Optional[str] = None

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
    special_requests: Optional[str] = None

class AssignGroupRoomsRequest(BaseModel):
    room_assignments: List[Dict[str, Any]]

class CreateBlockReservationRequest(BaseModel):
    block_name: str
    room_type: str
    start_date: str
    end_date: str
    total_rooms: int
    block_type: str = 'tentative'
    release_date: Optional[str] = None

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
    reason: Optional[str] = None

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
    items: List[Dict[str, Any]]
    delivery_location: str
    expected_delivery_date: Optional[str] = None

class ReceivePurchaseOrderRequest(BaseModel):
    received_items: List[Dict[str, Any]]

class CreateDeliveryRequest(BaseModel):
    po_id: str
    tracking_number: Optional[str] = None
    carrier: Optional[str] = None
    estimated_delivery: Optional[str] = None

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
    approval_notes: Optional[str] = None

class RejectPurchaseOrderRequest(BaseModel):
    rejection_reason: str

class UpdateDeliveryStatusRequest(BaseModel):
    status: str  # in_transit, delivered, failed
    location: Optional[str] = None
    notes: Optional[str] = None

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
    items: List[Dict[str, Any]]
    currency: str = "TRY"  # Invoice currency
    exchange_rate: Optional[float] = None  # If different from TRY
    payment_terms: str = "Net 30"
    notes: Optional[str] = None

class GenerateInvoiceFromFolioRequest(BaseModel):
    folio_id: str
    invoice_currency: str = "TRY"
    include_efatura: bool = True

class ConvertCurrencyRequest(BaseModel):
    amount: float
    from_currency: str
    to_currency: str
    date: Optional[str] = None  # Use specific date rate, or latest if None

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
    room_type: Optional[str] = None

# POS & F&B Models
class CreateOutletRequest(BaseModel):
    outlet_name: str
    outlet_type: str  # restaurant, bar, room_service, cafe
    location: str
    capacity: Optional[int] = None
    opening_hours: Optional[str] = None

class CreateMenuItemRequest(BaseModel):
    outlet_id: str
    item_name: str
    category: str  # appetizer, main, dessert, beverage
    price: float
    cost: Optional[float] = None
    description: Optional[str] = None

class CreatePOSTransactionWithMenuRequest(BaseModel):
    outlet_id: str
    items: List[Dict[str, Any]]  # [{menu_item_id, quantity, price}]
    payment_method: str
    folio_id: Optional[str] = None
    table_number: Optional[str] = None
    server_name: Optional[str] = None

class GenerateZReportRequest(BaseModel):
    outlet_id: Optional[str] = None
    date: Optional[str] = None  # Default to today

# Feedback & Reviews Models
class CreateSurveyRequest(BaseModel):
    survey_name: str
    description: str
    target_department: Optional[str] = None  # housekeeping, front_desk, fnb, spa, all
    questions: List[Dict[str, Any]]  # [{question, type, options}]
    trigger: str = "checkout"  # checkout, checkin, stay, manual

class SubmitSurveyResponseRequest(BaseModel):
    survey_id: str
    booking_id: Optional[str] = None
    guest_name: Optional[str] = None
    guest_email: Optional[str] = None
    responses: List[Dict[str, Any]]  # [{question_id, answer, rating}]

class ExternalReviewWebhookRequest(BaseModel):
    platform: str  # booking, google, tripadvisor
    review_id: str
    rating: float
    reviewer_name: str
    review_text: str
    review_date: str
    booking_reference: Optional[str] = None

class CreateDepartmentFeedbackRequest(BaseModel):
    department: str  # housekeeping, front_desk, fnb, spa
    booking_id: Optional[str] = None
    guest_name: str
    rating: int  # 1-5
    comment: Optional[str] = None
    staff_member: Optional[str] = None

# Task Management Models
class CreateTaskRequest(BaseModel):
    department: str  # engineering, housekeeping, fnb, maintenance, front_desk
    task_type: str  # repair, inspection, cleaning, setup, delivery, guest_request
    title: str
    description: str
    priority: str = "normal"  # low, normal, high, urgent
    location: Optional[str] = None  # room number or area
    room_id: Optional[str] = None
    assigned_to: Optional[str] = None
    due_date: Optional[str] = None
    recurring: Optional[bool] = False
    recurrence_pattern: Optional[str] = None  # daily, weekly, monthly

class UpdateTaskStatusRequest(BaseModel):
    status: str  # assigned, in_progress, completed, verified, cancelled
    notes: Optional[str] = None
    completion_photos: Optional[List[str]] = []

class AssignTaskRequest(BaseModel):
    assigned_to: str
    notes: Optional[str] = None

# Enterprise Features Models
class CreateRoleRequest(BaseModel):
    role_name: str
    description: str
    permissions: List[str]  # ['view_bookings', 'edit_rates', 'delete_bookings', etc.]
    department: Optional[str] = None

class AssignRoleRequest(BaseModel):
    user_id: str
    role_id: str


class UpdateUserRoleRequest(BaseModel):
    role: str

class CreateBackupRequest(BaseModel):
    backup_type: str = "full"  # full, incremental
    include_collections: Optional[List[str]] = None

