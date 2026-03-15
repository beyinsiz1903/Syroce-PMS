"""
HotelRunner Provider — Data Schemas
=====================================

Provider-specific request/response contracts.
Centralizes validation and documentation.
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class HotelRunnerRoom:
    """Parsed room from GET /rooms."""
    inv_code: str = ""
    name: str = ""
    rate_plans: List[Dict[str, Any]] = field(default_factory=list)
    channel_codes: List[str] = field(default_factory=list)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HotelRunnerChannel:
    """Parsed channel from GET /infos/channels."""
    code: str = ""
    name: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HotelRunnerConnectedChannel:
    """Parsed connected channel."""
    code: str = ""
    name: str = ""
    status: str = ""
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HotelRunnerReservation:
    """Parsed reservation from GET /reservations."""
    reservation_id: str = ""
    hr_number: str = ""
    status: str = ""
    guest_firstname: str = ""
    guest_lastname: str = ""
    guest_email: str = ""
    guest_phone: str = ""
    check_in: str = ""
    check_out: str = ""
    room_type_code: str = ""
    rate_plan_code: str = ""
    adults: int = 1
    children: int = 0
    total_amount: float = 0.0
    currency: str = "TRY"
    channel: str = ""
    message_uid: str = ""
    last_modified: str = ""
    requires_response: bool = False
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HotelRunnerReservationPage:
    """Parsed reservation page."""
    reservations: List[HotelRunnerReservation] = field(default_factory=list)
    current_page: int = 1
    total_pages: int = 1
    total_count: int = 0


@dataclass
class ProviderResult:
    """Standardized result from any provider operation."""
    success: bool
    data: Any = None
    error: str = ""
    duration_ms: int = 0
    error_type: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class InventoryDailyPayload:
    """Payload for PUT /rooms/daily."""
    inv_code: str
    date: str
    availability: Optional[int] = None
    price: Optional[float] = None
    stop_sale: Optional[int] = None
    min_stay: Optional[int] = None
    cta: Optional[int] = None
    ctd: Optional[int] = None
    channel_codes: Optional[List[str]] = None


@dataclass
class InventoryDateRangePayload:
    """Payload for PUT /rooms."""
    inv_code: str
    start_date: str
    end_date: str
    availability: Optional[int] = None
    price: Optional[float] = None
    stop_sale: Optional[int] = None
    min_stay: Optional[int] = None
    cta: Optional[int] = None
    ctd: Optional[int] = None
    days: Optional[List[int]] = None
    channel_codes: Optional[List[str]] = None
