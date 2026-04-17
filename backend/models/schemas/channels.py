"""Auto-split from schemas.py — domain: channels."""
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


