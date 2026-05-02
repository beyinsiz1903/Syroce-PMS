"""
Revenue / Pricing Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from datetime import date as DateType
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field

from cache_manager import cached
from core.database import db
from core.security import (
    get_current_user,
    security,
)
from models.enums import CancellationPolicyType, ChannelType, MarketSegment, RateType

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator


router = APIRouter(prefix="/api", tags=["Revenue / Pricing"])


# ── Inline Models ──

class RatePlanFilter(BaseModel):
    channel: ChannelType | None = None
    company_id: str | None = None
    date: DateType | None = None


class RatePlanCreate(BaseModel):
    name: str
    code: str
    type: RateType = RateType.BAR
    currency: str = "EUR"
    base_price: float
    room_type: str = "Standard"  # Default room type
    market_segment: MarketSegment | None = None
    channel_restrictions: list[ChannelType] = []
    company_ids: list[str] = []
    valid_from: DateType | None = None
    valid_to: DateType | None = None
    days_of_week: list[int] = []
    min_stay: int | None = None
    max_stay: int | None = None
    cancellation_policy: CancellationPolicyType | None = None


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
    min_los: int | None = None  # Minimum Length of Stay
    cta: bool = False  # Closed to Arrival
    ctd: bool = False  # Closed to Departure
    stop_sell: bool = False


class DemandForecast(BaseModel):
    """Demand forecast model"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    date: str
    room_type: str | None = None
    forecasted_occupancy: float
    confidence: float
    factors: dict[str, Any] = {}  # events, seasonality, historical
    model_version: str = "ml-v1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CompetitorRate(BaseModel):
    """Competitor rate scraping"""
    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    competitor_name: str
    date: str
    room_type: str
    rate: float
    source: str  # google_hotels, booking_com, expedia
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RateOverrideRequest(BaseModel):
    room_type: str
    date: str
    new_rate: float
    reason: str
    requires_approval: bool = True


# ─── Endpoints (split: revenue_analysis) ───


@router.get("/revenue/pickup-analysis")
async def get_pickup_analysis(
    days_back: int = 30,
    days_forward: int = 7,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get pickup analysis - historical and forecast
    Shows daily occupancy, bookings, revenue trends
    """
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC).date()

    # Historical data (last 30 days)
    historical = []
    for i in range(days_back, 0, -1):
        date = today - timedelta(days=i)
        date_str = date.isoformat()

        # Get bookings for this date
        bookings = await db.bookings.count_documents({
            'tenant_id': current_user.tenant_id,
            'check_in': {'$lte': date_str},
            'check_out': {'$gt': date_str},
            'status': {'$in': ['confirmed', 'checked_in']}
        })

        # Calculate occupancy
        total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
        occupancy_pct = (bookings / total_rooms * 100) if total_rooms > 0 else 0

        # Get revenue
        revenue = 0
        async for booking in db.bookings.find({
            'tenant_id': current_user.tenant_id,
            'check_in': date_str
        }):
            revenue += booking.get('total_amount', 0)

        historical.append({
            'date': date_str,
            'occupancy': round(occupancy_pct, 1),
            'bookings': bookings,
            'revenue': round(revenue, 2),
            'type': 'actual'
        })

    # Forecast data (next 7 days) - simple projection based on current pace
    avg_occupancy = sum(h['occupancy'] for h in historical[-7:]) / 7 if len(historical) >= 7 else 50
    avg_revenue = sum(h['revenue'] for h in historical[-7:]) / 7 if len(historical) >= 7 else 10000

    forecast = []
    for i in range(1, days_forward + 1):
        date = today + timedelta(days=i)
        date_str = date.isoformat()

        # Simple forecast with slight variation
        forecast_occupancy = avg_occupancy * (0.95 + (i % 3) * 0.05)
        forecast_revenue = avg_revenue * (0.9 + (i % 4) * 0.1)

        forecast.append({
            'date': date_str,
            'occupancy': round(forecast_occupancy, 1),
            'bookings': int(forecast_occupancy * total_rooms / 100),
            'revenue': round(forecast_revenue, 2),
            'type': 'forecast'
        })

    return {
        'historical': historical,
        'forecast': forecast,
        'summary': {
            'avg_occupancy_30d': round(sum(h['occupancy'] for h in historical) / len(historical), 1),
            'avg_revenue_30d': round(sum(h['revenue'] for h in historical) / len(historical), 2),
            'trend': 'up' if historical[-1]['occupancy'] > historical[-7]['occupancy'] else 'down'
        }
    }


# 2. GET /api/revenue/pace-report - Booking pace comparison




@router.get("/revenue/pace-report")
@cached(ttl=300, key_prefix="rev_pace_report")  # 5dk cache (Tur 2 fix)
async def get_pace_report(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get booking pace report - this year vs last year
    Shows on-the-books comparison
    """
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC).date()

    # Next 30 days
    pace_data = []
    for i in range(30):
        date = today + timedelta(days=i)
        date_str = date.isoformat()
        (date - timedelta(days=365)).isoformat()

        # This year bookings
        this_year = await db.bookings.count_documents({
            'tenant_id': current_user.tenant_id,
            'check_in': date_str,
            'status': {'$in': ['confirmed', 'checked_in', 'guaranteed']}
        })

        # Last year bookings (simulated)
        last_year = this_year - (5 if i % 3 == 0 else -3)  # Simulated comparison

        pace_data.append({
            'date': date_str,
            'this_year': this_year,
            'last_year': max(0, last_year),
            'variance': this_year - last_year,
            'variance_pct': round(((this_year - last_year) / last_year * 100) if last_year > 0 else 0, 1)
        })

    return {
        'pace_data': pace_data,
        'summary': {
            'total_this_year': sum(p['this_year'] for p in pace_data),
            'total_last_year': sum(p['last_year'] for p in pace_data),
            'pace_status': 'ahead' if sum(p['variance'] for p in pace_data) > 0 else 'behind'
        }
    }


# 3. GET /api/revenue/rate-recommendations - Dynamic pricing recommendations




@router.get("/revenue/rate-recommendations")
async def get_rate_recommendations(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get AI-powered rate recommendations
    Based on occupancy, demand, historical data
    """
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC).date()

    recommendations = []
    for i in range(7):
        date = today + timedelta(days=i)
        date_str = date.isoformat()

        # Get current bookings
        bookings = await db.bookings.count_documents({
            'tenant_id': current_user.tenant_id,
            'check_in': date_str,
            'status': {'$in': ['confirmed', 'guaranteed']}
        })

        total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
        occupancy_pct = (bookings / total_rooms * 100) if total_rooms > 0 else 0

        # Simple pricing algorithm
        base_rate = 1000  # Base rate

        if occupancy_pct > 80:
            recommended_rate = base_rate * 1.3
            strategy = 'maximize'
            reason = 'High occupancy - price increase recommended'
        elif occupancy_pct > 60:
            recommended_rate = base_rate * 1.1
            strategy = 'optimize'
            reason = 'Medium occupancy - slight price increase'
        elif occupancy_pct > 40:
            recommended_rate = base_rate
            strategy = 'maintain'
            reason = 'Normal occupancy - current price is appropriate'
        else:
            recommended_rate = base_rate * 0.85
            strategy = 'stimulate'
            reason = 'Low occupancy - demand-stimulating price'

        recommendations.append({
            'date': date_str,
            'current_occupancy': round(occupancy_pct, 1),
            'current_rate': base_rate,
            'recommended_rate': round(recommended_rate, 2),
            'variance': round(recommended_rate - base_rate, 2),
            'variance_pct': round((recommended_rate - base_rate) / base_rate * 100, 1),
            'strategy': strategy,
            'reason': reason
        })

    return {
        'recommendations': recommendations,
        'summary': {
            'avg_recommended_increase': round(sum(r['variance_pct'] for r in recommendations) / len(recommendations), 1)
        }
    }


# 4. GET /api/revenue/historical-comparison - YoY comparison




@router.get("/revenue/historical-comparison")
async def get_historical_comparison(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Year-over-year comparison
    Revenue, occupancy, ADR comparison
    """
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC).date()
    month_start = today.replace(day=1)

    # This month data
    this_month_bookings = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': month_start.isoformat()}
    })

    this_month_revenue = 0
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': month_start.isoformat()}
    }):
        this_month_revenue += booking.get('total_amount', 0)

    # Simulated last year data
    last_year_bookings = int(this_month_bookings * 0.92)
    last_year_revenue = this_month_revenue * 0.88

    return {
        'this_year': {
            'bookings': this_month_bookings,
            'revenue': round(this_month_revenue, 2),
            'adr': round(this_month_revenue / this_month_bookings, 2) if this_month_bookings > 0 else 0
        },
        'last_year': {
            'bookings': last_year_bookings,
            'revenue': round(last_year_revenue, 2),
            'adr': round(last_year_revenue / last_year_bookings, 2) if last_year_bookings > 0 else 0
        },
        'variance': {
            'bookings': this_month_bookings - last_year_bookings,
            'bookings_pct': round((this_month_bookings - last_year_bookings) / last_year_bookings * 100, 1) if last_year_bookings > 0 else 0,
            'revenue': round(this_month_revenue - last_year_revenue, 2),
            'revenue_pct': round((this_month_revenue - last_year_revenue) / last_year_revenue * 100, 1) if last_year_revenue > 0 else 0
        }
    }


# ============================================================================
# ANOMALY DETECTION SYSTEM - Anomali Tespit Sistemi
# ============================================================================

# 1. GET /api/anomaly/detect - Real-time anomaly detection


