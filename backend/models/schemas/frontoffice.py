"""Auto-split from schemas.py — domain: frontoffice."""
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


