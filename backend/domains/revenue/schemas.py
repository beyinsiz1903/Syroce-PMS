"""
Revenue Domain — Schemas
Request/response models extracted from revenue/pricing routers.
"""

import datetime as _datetime
import uuid
from datetime import UTC, date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RatePlanFilter(BaseModel):
    channel: str | None = None
    company_id: str | None = None
    date: _datetime.date | None = None


class RatePlanCreate(BaseModel):
    name: str
    code: str
    type: str = "BAR"
    currency: str = "EUR"
    base_price: float
    room_type: str = "Standard"
    market_segment: str | None = None
    channel_restrictions: list[str] = []
    company_ids: list[str] = []
    valid_from: date | None = None
    valid_to: date | None = None
    days_of_week: list[int] = []
    min_stay: int | None = None
    max_stay: int | None = None
    cancellation_policy: str | None = None


class PackageCreate(BaseModel):
    name: str
    code: str
    description: str | None = None
    included_services: list[str] = []
    price_type: str = "per_room"
    additional_amount: float = 0.0
    linked_rate_plan_ids: list[str] = []


class DynamicRestrictionsRequest(BaseModel):
    date: str
    room_type: str
    min_los: int | None = None
    cta: bool = False
    ctd: bool = False
    stop_sell: bool = False


class DemandForecast(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    date: str
    room_type: str | None = None
    forecasted_occupancy: float
    confidence: float
    factors: dict[str, Any] = {}
    model_version: str = "ml-v1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CompetitorRate(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    competitor_name: str
    date: str
    room_type: str
    rate: float
    source: str
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RateOverrideRequest(BaseModel):
    room_type: str
    date: str
    new_rate: float
    reason: str
    requires_approval: bool = True


class GroupBookingCreate(BaseModel):
    group_name: str
    company_id: str | None = None
    contact_person: str
    contact_email: str | None = None
    contact_phone: str | None = None
    check_in: str
    check_out: str
    room_count: int
    room_type: str | None = None
    rate_per_room: float | None = None
    notes: str | None = None


class CorporateContractCreate(BaseModel):
    company_name: str
    company_id: str | None = None
    contact_person: str
    contact_email: str | None = None
    valid_from: str
    valid_to: str
    discount_percentage: float = 0
    fixed_rate: float | None = None
    room_types: list[str] = []
    min_nights_per_year: int = 0
    payment_terms: str = "net30"


class OTAPromotionCreate(BaseModel):
    name: str
    channel: str
    discount_type: str = "percentage"
    discount_value: float
    valid_from: str
    valid_to: str
    room_types: list[str] = []
    min_stay: int = 1
    max_stay: int | None = None


class InventoryItemCreate(BaseModel):
    name: str
    category: str
    unit: str = "piece"
    current_stock: int = 0
    min_stock_level: int = 10
    unit_cost: float = 0
    supplier: str | None = None
    location: str | None = None


class InventoryUsage(BaseModel):
    item_id: str
    quantity: int
    department: str
    used_by: str | None = None
    notes: str | None = None
