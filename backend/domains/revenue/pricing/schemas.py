"""
Revenue / Pricing Domain — Pydantic Schemas
Extracted from pricing_router.py inline models.
"""

from typing import Any

from pydantic import BaseModel


class RatePlanFilter(BaseModel):
    status: str | None = None
    room_type: str | None = None
    channel: str | None = None


class RatePlanCreate(BaseModel):
    name: str
    description: str | None = None
    room_type_id: str
    base_rate: float
    currency: str = "TRY"
    meal_plan: str = "room_only"
    cancellation_policy: str = "flexible"
    min_stay: int = 1
    max_stay: int = 365
    channels: list[str] = []
    status: str = "active"
    valid_from: str | None = None
    valid_to: str | None = None
    rate_rules: dict[str, Any] | None = None


class PackageCreate(BaseModel):
    name: str
    description: str | None = None
    base_price: float
    inclusions: list[str] = []
    room_type_id: str | None = None
    min_stay: int = 1
    valid_from: str | None = None
    valid_to: str | None = None


class DynamicRestrictionsRequest(BaseModel):
    room_type_id: str
    start_date: str
    end_date: str
    min_stay: int | None = None
    max_stay: int | None = None
    closed_to_arrival: bool = False
    closed_to_departure: bool = False
    stop_sell: bool = False


class DemandForecast(BaseModel):
    room_type_id: str
    forecast_date: str
    predicted_demand: float
    confidence: float
    factors: dict[str, Any] = {}
    recommended_rate: float | None = None
    demand_level: str = "normal"
    events_impact: str | None = None
    historical_comparison: dict[str, Any] | None = None
    competitor_data: dict[str, Any] | None = None
    weather_impact: float | None = None


class CompetitorRate(BaseModel):
    competitor_name: str
    room_type: str
    rate: float
    source: str = "manual"
    captured_at: str | None = None
    currency: str = "TRY"
    meal_plan: str | None = None
    cancellation_policy: str | None = None
    our_rate: float | None = None
    rate_difference: float | None = None
    position: str = "unknown"


class RateOverrideRequest(BaseModel):
    room_type_id: str
    start_date: str
    end_date: str
    override_rate: float
    reason: str
    override_type: str = "fixed"
