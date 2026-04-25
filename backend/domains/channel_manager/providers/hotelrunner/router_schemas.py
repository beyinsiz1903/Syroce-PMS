"""
HotelRunner Router — Request/Response DTOs
==========================================

Pydantic models used by hotelrunner_router endpoints.
Kept separate from `schemas.py` (provider-internal dataclasses).
"""
from pydantic import BaseModel


class HRCredentials(BaseModel):
    token: str
    hr_id: str


class HRConnectionSetup(BaseModel):
    token: str
    hr_id: str
    property_name: str | None = None
    environment: str = "production"  # production | sandbox | mock
    auto_sync_reservations: bool = True
    auto_confirm_delivery: bool = False
    sync_interval_minutes: int = 15


class HRARIUpdate(BaseModel):
    inv_code: str
    start_date: str
    end_date: str
    availability: int | None = None
    price: float | None = None
    stop_sale: int | None = None
    min_stay: int | None = None
    cta: int | None = None
    ctd: int | None = None
    days: list[int] | None = None
    channel_codes: list[str] | None = None


class HRReservationFilter(BaseModel):
    undelivered: bool = True
    from_date: str | None = None
    per_page: int = 10
    page: int = 1
    modified: bool = False
    booked: bool = False


class HRRoomMapping(BaseModel):
    pms_room_type: str
    hr_inv_code: str
    hr_rate_code: str
    hr_room_name: str
    sync_availability: bool = True
    sync_price: bool = True
    sync_restrictions: bool = True
