"""Auto-split from schemas.py — domain: loyalty."""
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


