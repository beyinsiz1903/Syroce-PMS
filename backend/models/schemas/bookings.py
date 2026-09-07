"""Auto-split from schemas.py — domain: bookings."""

import uuid
from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from models.enums import (
    BookingStatus,
    CancellationPolicyType,
    ChannelType,
    ContractedRateType,
    MarketSegment,
    OTAChannel,
    OTAPaymentModel,
    RateType,
)


class BookingCreate(BaseModel):
    guest_id: str
    room_id: str
    check_in: str
    check_out: str
    adults: int = Field(1, ge=0, le=50)
    children: int = Field(0, ge=0, le=50)

    # CM / integration semantics (optional; defaults applied in Booking model)
    source_channel: str | None = None
    origin: str | None = None
    hold_status: str | None = None
    allocation_source: str | None = None
    children_ages: list[int] = []
    guests_count: int = Field(..., ge=1, le=100)  # Total: adults + children
    total_amount: float = Field(..., ge=0, le=1e12)
    base_rate: float | None = None  # For override tracking
    apply_occupancy_pricing: bool = False
    pricing_rule_version: str | None = None
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
    # Complimentary reservations retain their commercial value for reporting,
    # while the posted accommodation total is zero.
    is_complimentary: bool = False
    complimentary_scope: Literal["accommodation_only", "full"] | None = None
    complimentary_reason: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def validate_complimentary_details(self):
        if not self.is_complimentary:
            self.complimentary_scope = None
            self.complimentary_reason = None
            return self
        if self.complimentary_scope not in {"accommodation_only", "full"}:
            raise ValueError("Komp kapsamı seçilmelidir")
        reason = (self.complimentary_reason or "").strip()
        if len(reason) < 3:
            raise ValueError("Komp gerekçesi en az 3 karakter olmalıdır")
        self.complimentary_reason = reason
        return self


class BookingBase(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    guest_id: str
    room_id: str
    # Folio Routing — kategori bazlı masraf yönlendirme kuralları.
    # Her kural: {category, target, limit?, notes?, active?, split_type?, splits?}
    # add_folio_charge bu listeyi okuyup hedef folyoya yönlendirir.
    routing_rules: list[dict] | None = None
    routing_updated_at: str | None = None


REJECTED_STATUS = "rejected"


class Booking(BookingBase):
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
    apply_occupancy_pricing: bool = False
    pricing_rule_version: str | None = None
    pricing_breakdown: dict | None = None
    pricing_rule_snapshot: dict | None = None
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
    is_complimentary: bool = False
    complimentary_scope: Literal["accommodation_only", "full"] | None = None
    complimentary_reason: str | None = None
    complimentary_original_total: float | None = None
    # System fields
    qr_code: str | None = None
    qr_code_data: str | None = None
    checked_in_at: datetime | None = None
    checked_out_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# Backwards-compatible name retained for older imports.
BookingExtended = Booking
