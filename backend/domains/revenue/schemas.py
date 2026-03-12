"""
Revenue Domain — Schemas
Request/response models extracted from revenue/pricing routers.
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, date
from enum import Enum
import uuid


class RatePlanFilter(BaseModel):
    channel: Optional[str] = None
    company_id: Optional[str] = None
    date: Optional[date] = None


class RatePlanCreate(BaseModel):
    name: str
    code: str
    type: str = "BAR"
    currency: str = "EUR"
    base_price: float
    room_type: str = "Standard"
    market_segment: Optional[str] = None
    channel_restrictions: List[str] = []
    company_ids: List[str] = []
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    days_of_week: List[int] = []
    min_stay: Optional[int] = None
    max_stay: Optional[int] = None
    cancellation_policy: Optional[str] = None


class PackageCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    included_services: List[str] = []
    price_type: str = "per_room"
    additional_amount: float = 0.0
    linked_rate_plan_ids: List[str] = []


class DynamicRestrictionsRequest(BaseModel):
    date: str
    room_type: str
    min_los: Optional[int] = None
    cta: bool = False
    ctd: bool = False
    stop_sell: bool = False


class DemandForecast(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    date: str
    room_type: Optional[str] = None
    forecasted_occupancy: float
    confidence: float
    factors: Dict[str, Any] = {}
    model_version: str = "ml-v1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CompetitorRate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    competitor_name: str
    date: str
    room_type: str
    rate: float
    source: str
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RateOverrideRequest(BaseModel):
    room_type: str
    date: str
    new_rate: float
    reason: str
    requires_approval: bool = True


class GroupBookingCreate(BaseModel):
    group_name: str
    company_id: Optional[str] = None
    contact_person: str
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    check_in: str
    check_out: str
    room_count: int
    room_type: Optional[str] = None
    rate_per_room: Optional[float] = None
    notes: Optional[str] = None


class CorporateContractCreate(BaseModel):
    company_name: str
    company_id: Optional[str] = None
    contact_person: str
    contact_email: Optional[str] = None
    valid_from: str
    valid_to: str
    discount_percentage: float = 0
    fixed_rate: Optional[float] = None
    room_types: List[str] = []
    min_nights_per_year: int = 0
    payment_terms: str = "net30"


class OTAPromotionCreate(BaseModel):
    name: str
    channel: str
    discount_type: str = "percentage"
    discount_value: float
    valid_from: str
    valid_to: str
    room_types: List[str] = []
    min_stay: int = 1
    max_stay: Optional[int] = None


class InventoryItemCreate(BaseModel):
    name: str
    category: str
    unit: str = "piece"
    current_stock: int = 0
    min_stock_level: int = 10
    unit_cost: float = 0
    supplier: Optional[str] = None
    location: Optional[str] = None


class InventoryUsage(BaseModel):
    item_id: str
    quantity: int
    department: str
    used_by: Optional[str] = None
    notes: Optional[str] = None
