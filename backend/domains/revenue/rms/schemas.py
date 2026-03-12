"""
Revenue / RMS Domain — Pydantic Schemas
Extracted from rms_router.py inline models.
"""
from pydantic import BaseModel
from typing import List, Optional


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
    special_requirements: Optional[str] = None
    notes: Optional[str] = None


class CorporateContractCreate(BaseModel):
    company_name: str
    contract_type: str
    rate_code: str
    negotiated_rate: Optional[float] = None
    discount_percentage: Optional[float] = 0
    start_date: str
    end_date: str
    allotment: Optional[int] = 0
    blackout_dates: Optional[List[str]] = []
    contact_person: str
    contact_email: str
    contact_phone: str
    notes: Optional[str] = None


class OTAPromotionCreate(BaseModel):
    channel: str
    promotion_name: str
    discount_type: str
    discount_value: float
    start_date: str
    end_date: str
    applicable_room_types: List[str] = []
    min_stay: Optional[int] = None
    booking_window_start: Optional[str] = None
    booking_window_end: Optional[str] = None


class InventoryItemCreate(BaseModel):
    name: str
    sku: str
    category: str
    quantity: int = 0
    minimum_quantity: int = 10
    unit_price: float = 0.0
    unit_of_measure: str = "pcs"
    supplier: Optional[str] = None
    location: Optional[str] = None


class InventoryUsage(BaseModel):
    item_id: str
    quantity: int
    usage_type: str
    department: Optional[str] = None
    notes: Optional[str] = None
