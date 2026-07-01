"""Auto-split from schemas.py — domain: folio."""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

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
    # Opera #11 — Multi-window Folio:
    # Bir booking için 1-8 arası window numarası. Geriye uyumlu (eski folio'lar None).
    # payor_type: "guest" | "company" | "agency" | "master"
    window_number: int | None = Field(default=None, ge=1, le=8)
    payor_type: str | None = None
    payor_id: str | None = None


class ChargeCreate(BaseModel):
    charge_category: ChargeCategory
    description: str = Field(..., min_length=1, max_length=500)
    amount: float = Field(..., ge=0, le=1e9)
    quantity: float = Field(1.0, gt=0, le=1e6)
    auto_calculate_tax: bool = False
    vat_rate: float = Field(0.0, ge=0, le=100)  # KDV oranı %
    discount_amount: float = Field(0.0, ge=0, le=1e9)  # mutlak tutar (TL)
    discount_reason: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def _require_reason_when_discount(self):
        if (self.discount_amount or 0) > 0 and not (self.discount_reason and self.discount_reason.strip()):
            raise ValueError("İndirim için neden zorunludur")
        return self


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
    amount: float  # net (subtotal - discount), KDV/şehir vergisi hariç (geriye uyumluluk için bu isim korundu)
    subtotal: float = 0.0  # unit_price * quantity (indirim öncesi)
    discount_amount: float = 0.0
    discount_reason: str | None = None
    vat_rate: float = 0.0
    vat_amount: float = 0.0  # net * vat_rate / 100
    tax_amount: float = 0.0  # şehir vergisi (mevcut)
    total: float  # net + vat + city_tax
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
