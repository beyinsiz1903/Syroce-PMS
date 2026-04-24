"""Auto-split from schemas.py — domain: folio."""
import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from models.enums import (
    ChargeCategory,
    FolioOperationType,
    FolioStatus,
    FolioType,
    MarketSegment,
    PaymentMethod,
    PaymentStatus,
    PaymentType,
)


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
    description: str = Field(..., min_length=1, max_length=500)
    amount: float = Field(..., ge=0, le=1e9)
    quantity: float = Field(1.0, gt=0, le=1e6)
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
    amount: float = Field(..., gt=0, le=1e9)
    method: PaymentMethod
    payment_type: PaymentType
    reference: str | None = Field(None, max_length=200)
    notes: str | None = Field(None, max_length=2000)

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


