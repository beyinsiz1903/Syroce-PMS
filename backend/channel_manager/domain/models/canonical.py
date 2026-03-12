"""
Canonical Data Models - Provider-agnostic representations of hospitality entities.
All provider data is normalized into these models before entering PMS domain logic.
This ensures HotelRunner (or any future provider) differences are absorbed at the connector layer.
"""
import uuid
from enum import Enum
from typing import Optional, Dict, Any, List

from pydantic import BaseModel, Field


class ReservationStatus(str, Enum):
    CONFIRMED = "confirmed"
    PROVISIONAL = "provisional"
    CANCELLED = "cancelled"
    MODIFIED = "modified"
    NO_SHOW = "no_show"
    CHECKED_IN = "checked_in"
    CHECKED_OUT = "checked_out"


class MealPlan(str, Enum):
    RO = "RO"    # Room Only
    BB = "BB"    # Bed & Breakfast
    HB = "HB"    # Half Board
    FB = "FB"    # Full Board
    AI = "AI"    # All Inclusive


class TaxBreakdown(BaseModel):
    tax_name: str = ""
    tax_rate: float = 0.0
    tax_amount: float = 0.0
    is_inclusive: bool = True
    currency: str = "TRY"


class PriceBreakdown(BaseModel):
    date: str  # YYYY-MM-DD
    base_rate: float = 0.0
    net_rate: float = 0.0
    sell_rate: float = 0.0
    currency: str = "TRY"
    adult_count: int = 2
    child_count: int = 0
    taxes: List[TaxBreakdown] = Field(default_factory=list)
    supplements: List[Dict[str, Any]] = Field(default_factory=list)


class CanonicalRoomType(BaseModel):
    """Provider-agnostic room type representation."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    pms_room_type_id: str = ""  # Link to PMS rooms collection
    name: str = ""
    code: str = ""
    max_occupancy: int = 2
    base_occupancy: int = 2
    max_children: int = 0
    description: str = ""
    amenities: List[str] = Field(default_factory=list)
    bed_type: str = ""
    room_size_sqm: Optional[float] = None


class CanonicalRatePlan(BaseModel):
    """Provider-agnostic rate plan representation."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    pms_rate_plan_id: str = ""
    room_type_id: str = ""
    name: str = ""
    code: str = ""
    currency: str = "TRY"
    meal_plan: MealPlan = MealPlan.RO
    is_refundable: bool = True
    cancellation_deadline_hours: int = 24
    min_stay: int = 1
    max_stay: int = 365
    is_derived: bool = False
    base_rate_plan_id: Optional[str] = None
    derivation_rule: Optional[Dict[str, Any]] = None


class InventorySlice(BaseModel):
    """A single date's inventory for a room type."""
    date: str  # YYYY-MM-DD
    room_type_id: str
    total_inventory: int = 0
    sold: int = 0
    blocked: int = 0
    available: int = 0
    overbooking_allowance: int = 0


class RestrictionSet(BaseModel):
    """Rate/availability restrictions for a room-rate-date combination."""
    date: str  # YYYY-MM-DD
    room_type_id: str
    rate_plan_id: str
    closed: bool = False
    closed_to_arrival: bool = False
    closed_to_departure: bool = False
    min_stay: Optional[int] = None
    max_stay: Optional[int] = None
    min_stay_arrival: Optional[int] = None
    min_advance_booking: Optional[int] = None
    max_advance_booking: Optional[int] = None


class CanonicalGuest(BaseModel):
    """Provider-agnostic guest representation."""
    first_name: str = ""
    last_name: str = ""
    email: str = ""
    phone: str = ""
    nationality: str = ""
    national_id: str = ""
    is_citizen: bool = False
    address: str = ""
    city: str = ""
    state: str = ""
    country: str = ""
    country_code: str = ""
    postal_code: str = ""
    street: str = ""
    street_2: str = ""
    company_name: str = ""
    loyalty_id: str = ""
    notes: str = ""
    billing_address: Dict[str, Any] = Field(default_factory=dict)


class CanonicalReservation(BaseModel):
    """Provider-agnostic reservation representation."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    external_id: str = ""
    hr_number: str = ""
    confirmation_number: str = ""
    channel_name: str = ""
    channel_code: str = ""
    status: ReservationStatus = ReservationStatus.CONFIRMED

    # Provider delivery tracking
    message_uid: str = ""
    requires_ack: bool = False
    modified: bool = False

    # Guest
    guest: CanonicalGuest = Field(default_factory=CanonicalGuest)

    # Stay details
    arrival_date: str = ""  # YYYY-MM-DD
    departure_date: str = ""
    room_type_id: str = ""
    room_type_name: str = ""
    rate_plan_id: str = ""
    rate_plan_name: str = ""

    # Occupancy
    adult_count: int = 1
    child_count: int = 0
    child_ages: List[int] = Field(default_factory=list)
    room_count: int = 1

    # Pricing
    total_amount: float = 0.0
    sub_total: float = 0.0
    tax_total: float = 0.0
    extras_total: float = 0.0
    paid_amount: float = 0.0
    currency: str = "TRY"
    price_breakdown: List[PriceBreakdown] = Field(default_factory=list)
    tax_breakdown: List[TaxBreakdown] = Field(default_factory=list)
    daily_prices: List[Dict[str, Any]] = Field(default_factory=list)
    commission_amount: float = 0.0
    commission_rate: float = 0.0

    # Payment
    payment_type: str = ""  # prepaid, pay_at_hotel, credit_card_guarantee
    card_type: str = ""
    card_last_four: str = ""
    payments: List[Dict[str, Any]] = Field(default_factory=list)

    # Policy
    meal_plan: MealPlan = MealPlan.RO
    cancellation_policy: str = ""
    cancellation_deadline: Optional[str] = None
    non_refundable: bool = False

    # Notes
    special_requests: str = ""
    internal_notes: str = ""

    # Rooms raw data (multi-room support)
    rooms: List[Dict[str, Any]] = Field(default_factory=list)

    # Timestamps
    booked_at: Optional[str] = None
    modified_at: Optional[str] = None
    cancelled_at: Optional[str] = None

    # Raw data reference
    raw_provider_data: Dict[str, Any] = Field(default_factory=dict)
