"""Syroce Xchange (SXI) — canonical message schemas.

These are the platform-neutral, OPERA/PMSXchange-equivalent message
types. Adapters translate to/from HTNG 2024B XML, OTA, JSON, etc.

Naming follows OTA / HTNG verbs so existing integration teams can
map them 1:1 to their certified message catalogs.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageType(str, Enum):
    # Reservation lifecycle
    RESERVATION_CREATE = "OTA_HotelResNotifRQ.Commit"
    RESERVATION_MODIFY = "OTA_HotelResNotifRQ.Modify"
    RESERVATION_CANCEL = "OTA_HotelResNotifRQ.Cancel"
    # Profile
    PROFILE_UPSERT = "OTA_ProfileCreateRQ"
    # Stay events
    STAY_CHECK_IN = "OTA_HotelStatsRQ.CheckIn"
    STAY_CHECK_OUT = "OTA_HotelStatsRQ.CheckOut"
    # Folio / financial
    POSTING_CHARGE = "OTA_HotelPostingRQ.Charge"
    POSTING_PAYMENT = "OTA_HotelPostingRQ.Payment"
    # Inventory & rates
    INVENTORY_UPDATE = "OTA_HotelInvCountNotifRQ"
    RATE_UPDATE = "OTA_HotelRateAmountNotifRQ"
    # Room status
    ROOM_STATUS_CHANGE = "OTA_HotelRoomStatusRQ"
    # Night audit close (SAP, ERP)
    NIGHT_AUDIT_CLOSE = "Syroce.NightAuditClose"
    # Folio close — e-Fatura readiness (reference-based; PII pulled via signed URL)
    FOLIO_CLOSE = "Syroce.FolioClose"


class Direction(str, Enum):
    OUTBOUND = "outbound"  # Syroce → partner
    INBOUND = "inbound"  # partner → Syroce


class DeliveryStatus(str, Enum):
    PENDING = "pending"
    IN_FLIGHT = "in_flight"
    DELIVERED = "delivered"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"
    SKIPPED = "skipped"


# ── Canonical payload sub-schemas ─────────────────────────────────
class GuestProfile(BaseModel):
    profile_id: str | None = None
    given_name: str | None = None
    surname: str
    email: str | None = None
    phone: str | None = None
    nationality: str | None = None  # ISO 3166-1 alpha-2
    document_type: str | None = None  # PASSPORT / NATIONAL_ID
    document_number_masked: str | None = None  # last4 only at this layer
    loyalty_program: str | None = None
    loyalty_number: str | None = None


class ReservationRoomStay(BaseModel):
    room_type_code: str
    rate_plan_code: str
    arrival: date
    departure: date
    adults: int = 1
    children: int = 0
    total_amount: float
    currency: str = "TRY"
    room_number: str | None = None


class ReservationPayload(BaseModel):
    reservation_id: str
    confirmation_number: str | None = None
    status: str  # Reserved / InHouse / CheckedOut / Cancelled
    primary_guest: GuestProfile
    room_stays: list[ReservationRoomStay]
    source: str | None = None  # direct / booking / sabre / etc.
    booking_channel: str | None = None
    notes: str | None = None
    created_at: datetime | None = None


class PostingPayload(BaseModel):
    """Folio posting — a charge or payment line."""

    posting_id: str
    reservation_id: str | None = None
    folio_id: str
    posting_type: str  # CHARGE / PAYMENT
    transaction_code: str  # ROOM, FNB, TAX, CASH, CARD, ...
    description: str
    amount: float
    currency: str = "TRY"
    posted_at: datetime
    reference: str | None = None


class InventoryPayload(BaseModel):
    room_type_code: str
    business_date: date
    available_count: int
    on_hold_count: int = 0


class RatePayload(BaseModel):
    room_type_code: str
    rate_plan_code: str
    business_date: date
    amount: float
    currency: str = "TRY"
    min_los: int | None = None
    max_los: int | None = None
    closed: bool = False


class RoomStatusPayload(BaseModel):
    room_number: str
    front_office_status: str  # Vacant / Occupied
    housekeeping_status: str  # Clean / Dirty / Inspected / OO
    business_date: date


class NightAuditPayload(BaseModel):
    business_date: date
    closed_at: datetime
    revenue_total: float
    tax_total: float
    payment_total: float
    currency: str = "TRY"
    journal_lines: list[dict[str, Any]] = Field(default_factory=list)


# ── Envelope ─────────────────────────────────────────────────────
class XchangeEnvelope(BaseModel):
    """Universal envelope for every message on the bus."""

    message_id: str  # idempotency key (uuid4)
    message_type: MessageType
    tenant_id: str
    correlation_id: str | None = None
    occurred_at: datetime
    payload: dict[str, Any]
    direction: Direction = Direction.OUTBOUND


# ── Capability matrix ────────────────────────────────────────────
class PartnerCapability(BaseModel):
    message_type: MessageType
    direction: Direction
    certified: bool = False  # has the partner signed off in a UAT cycle?
