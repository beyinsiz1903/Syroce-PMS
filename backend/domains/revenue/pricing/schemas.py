"""
Revenue / Pricing Domain — Pydantic Schemas
Extracted from pricing_router.py inline models.
"""
from pydantic import BaseModel
from typing import List, Optional, Dict, Any


class RatePlanFilter(BaseModel):
    status: Optional[str] = None
    room_type: Optional[str] = None
    channel: Optional[str] = None


class RatePlanCreate(BaseModel):
    name: str
    description: Optional[str] = None
    room_type_id: str
    base_rate: float
    currency: str = "TRY"
    meal_plan: str = "room_only"
    cancellation_policy: str = "flexible"
    min_stay: int = 1
    max_stay: int = 365
    channels: List[str] = []
    status: str = "active"
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None
    rate_rules: Optional[Dict[str, Any]] = None


class PackageCreate(BaseModel):
    name: str
    description: Optional[str] = None
    base_price: float
    inclusions: List[str] = []
    room_type_id: Optional[str] = None
    min_stay: int = 1
    valid_from: Optional[str] = None
    valid_to: Optional[str] = None


class DynamicRestrictionsRequest(BaseModel):
    room_type_id: str
    start_date: str
    end_date: str
    min_stay: Optional[int] = None
    max_stay: Optional[int] = None
    closed_to_arrival: bool = False
    closed_to_departure: bool = False
    stop_sell: bool = False


class DemandForecast(BaseModel):
    room_type_id: str
    forecast_date: str
    predicted_demand: float
    confidence: float
    factors: Dict[str, Any] = {}
    recommended_rate: Optional[float] = None
    demand_level: str = "normal"
    events_impact: Optional[str] = None
    historical_comparison: Optional[Dict[str, Any]] = None
    competitor_data: Optional[Dict[str, Any]] = None
    weather_impact: Optional[float] = None


class CompetitorRate(BaseModel):
    competitor_name: str
    room_type: str
    rate: float
    source: str = "manual"
    captured_at: Optional[str] = None
    currency: str = "TRY"
    meal_plan: Optional[str] = None
    cancellation_policy: Optional[str] = None
    our_rate: Optional[float] = None
    rate_difference: Optional[float] = None
    position: str = "unknown"


class RateOverrideRequest(BaseModel):
    room_type_id: str
    start_date: str
    end_date: str
    override_rate: float
    reason: str
    override_type: str = "fixed"
