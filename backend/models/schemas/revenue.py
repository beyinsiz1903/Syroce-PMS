"""Auto-split from schemas.py — domain: revenue."""

import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from models.enums import (
    MeasurementUnit,
)


# Revenue Management Models
class RateOverride(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_type: str
    date: datetime
    original_rate: float
    override_rate: float
    reason: str
    approved_by: str
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RevenueForecast(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    forecast_date: datetime
    forecast_period: str  # daily, weekly, monthly
    projected_occupancy: float
    projected_adr: float
    projected_revpar: float
    projected_revenue: float
    confidence_level: float = 0.0
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class DemandData(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    date: datetime
    demand_level: str  # low, medium, high, very_high
    booking_count: int
    search_count: int = 0
    competitor_rate_avg: float = 0.0
    notes: str | None = None

    unit: MeasurementUnit
    order_id: str | None = None
    recipe_id: str | None = None
    outlet_id: str
    outlet_name: str
    cost: float
    consumed_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    recorded_by: str


class RMSSuggestion(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    date: str  # YYYY-MM-DD
    room_type: str
    current_rate: float
    suggested_rate: float
    reason: str  # e.g., "High demand detected", "Competitor analysis"
    confidence_score: float  # 0-100
    based_on: dict  # {occupancy, pickup_pace, competitor_rates, etc.}
    status: str = "pending"  # pending, applied, rejected
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# RMS Models
class PriceAnalysis(BaseModel):
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_type: str
    date: datetime
    current_price: float
    suggested_price: float
    occupancy_rate: float
    demand_score: float
    competitor_avg: float | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
