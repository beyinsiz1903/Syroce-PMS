"""
Revenue / RMS Domain — Pydantic Schemas
Extracted from rms_router.py inline models.
"""

from pydantic import BaseModel


class GroupBookingCreate(BaseModel):
    group_name: str
    group_type: str
    event_date: str
    start_date: str
    end_date: str
    total_rooms: int
    total_guests: int
    contact_person: str
    contact_email: str
    contact_phone: str
    special_requirements: str | None = None
    notes: str | None = None


class CorporateContractCreate(BaseModel):
    company_name: str
    contract_type: str
    rate_code: str
    negotiated_rate: float | None = None
    discount_percentage: float | None = 0
    start_date: str
    end_date: str
    allotment: int | None = 0
    blackout_dates: list[str] | None = []
    contact_person: str
    contact_email: str
    contact_phone: str
    notes: str | None = None


class OTAPromotionCreate(BaseModel):
    channel: str
    promotion_name: str
    discount_type: str
    discount_value: float
    start_date: str
    end_date: str
    applicable_room_types: list[str] = []
    min_stay: int | None = None
    booking_window_start: str | None = None
    booking_window_end: str | None = None


class InventoryItemCreate(BaseModel):
    name: str
    sku: str
    category: str
    quantity: int = 0
    minimum_quantity: int = 10
    unit_price: float = 0.0
    unit_of_measure: str = "pcs"
    supplier: str | None = None
    location: str | None = None


class InventoryUsage(BaseModel):
    item_id: str
    quantity: int
    usage_type: str
    department: str | None = None
    notes: str | None = None
