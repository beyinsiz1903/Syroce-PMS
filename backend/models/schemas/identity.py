"""Auto-split from schemas.py — domain: identity."""
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, EmailStr, Field

from models.enums import (
    BookingStatus, CancellationPolicyType, ChannelStatus, ChannelType,
    ChargeCategory, CheckInStatus, CompanyStatus, ContractedRateType,
    DepartmentType, FolioOperationType, FolioStatus, FolioType,
    GuestRequestStatus, GuestRequestType, InspectionStatus, InvoiceStatus,
    LostFoundStatus, LoyaltyTier, MaintenancePriority, MaintenanceTaskStatus,
    MaintenanceType, MappingStatus, MarketSegment, MeasurementUnit,
    OrderStatus, OTAChannel, OTAPaymentModel, OutletType, PaymentMethod,
    PaymentStatus, PaymentType, PricingStrategy, RateType, RiskLevel,
    RoomServiceStatus, RoomStatus, UserRole, WarehouseLocation,
)

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


