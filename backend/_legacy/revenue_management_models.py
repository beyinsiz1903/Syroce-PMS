"""
Advanced Revenue Management Models
AI-powered pricing, forecasting, yield management
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone, date
from enum import Enum
import uuid

class PricingStrategy(str, Enum):
    """Fiyatlandırma stratejisi"""
    AGGRESSIVE = "aggressive"  # Yüksek fiyat, yüksek gelir
    BALANCED = "balanced"  # Dengeli
    OCCUPANCY_FOCUSED = "occupancy_focused"  # Doluluk odaklı

class DemandLevel(str, Enum):
    """Talep seviyesi"""
    VERY_LOW = "very_low"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"

class PricingRecommendation(BaseModel):
    """AI fiyat önerisi"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    room_type: str
    target_date: date
    
    # AI Recommendations
    recommended_price: float
    min_price: float
    max_price: float
    confidence_score: float  # 0.0 - 1.0
    
    # Market Analysis
    competitor_avg_price: Optional[float] = None
    demand_level: DemandLevel
    occupancy_forecast: float
    
    # Factors considered
    factors: dict = {}  # {"day_of_week": 0.1, "event_impact": 0.3, etc.}
    
    # Current vs Recommended
    current_price: Optional[float] = None
    price_change_pct: Optional[float] = None
    
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ForecastData(BaseModel):
    """Gelir tahmin verisi"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    
    # Forecast period
    forecast_date: date
    forecast_type: str  # "30_day", "60_day", "90_day", "365_day"
    
    # Occupancy forecast
    forecasted_occupancy: float
    forecasted_rooms_sold: int
    
    # Revenue forecast
    forecasted_room_revenue: float
    forecasted_total_revenue: float
    forecasted_adr: float
    forecasted_revpar: float
    
    # Comparison
    budget_variance: Optional[float] = None
    last_year_variance: Optional[float] = None
    
    # Confidence
    confidence_level: float  # 0.0 - 1.0
    
    # Method used
    forecast_method: str = "ai_ml"  # ai_ml, historical_avg, manual
    
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class PickupReport(BaseModel):
    """Pickup raporu"""
    tenant_id: str
    start_date: date
    end_date: date
    
    # Pickup data by date
    daily_pickup: List[dict] = []  # [{date, rooms_on_books, pickup_today, pace}]
    
    # Comparisons
    vs_last_year: Optional[float] = None
    vs_budget: Optional[float] = None
    
    # Pace analysis
    booking_pace: str  # "ahead", "on_pace", "behind"
    pace_percentage: float
    
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class YieldControl(BaseModel):
    """Yield management kısıtlamaları"""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    
    # Date range
    start_date: date
    end_date: date
    
    # Controls
    min_stay: Optional[int] = None
    max_stay: Optional[int] = None
    closed_to_arrival: bool = False
    closed_to_departure: bool = False
    
    # Room types affected
    room_types: List[str] = []  # Empty = all types
    
    # Reason
    reason: str
    auto_created: bool = False  # AI created vs manual
    
    # Status
    active: bool = True
    
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
