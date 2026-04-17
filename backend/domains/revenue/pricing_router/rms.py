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

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field

from common.context import OperationContext
from core.database import db
from core.security import (
    get_current_user,
    security,
)
from domains.revenue.pricing.pricing_service import pricing_service
from models.enums import CancellationPolicyType, ChannelType, MarketSegment, RateType
from models.schemas import Package, PriceAnalysis, RatePlan, User

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


# ─── Endpoints (split: rms) ───


@router.post("/rms/update-rate")
async def update_room_rate(rate_data: dict, current_user: User = Depends(get_current_user)):
    """Oda fiyatini guncelle ve tum kanallara gonder"""
    ctx = OperationContext.from_user(current_user)
    result = await pricing_service.update_room_rate(ctx, rate_data)
    return result.data

# ============= PAYMENT & FINANCIAL (ALREADY ADDED ABOVE) =============





@router.post("/rms/analysis", response_model=PriceAnalysis)
async def create_price_analysis(analysis: PriceAnalysis, current_user: User = Depends(get_current_user)):
    analysis.tenant_id = current_user.tenant_id
    analysis_dict = analysis.model_dump()
    analysis_dict['date'] = analysis_dict['date'].isoformat()
    analysis_dict['created_at'] = analysis_dict['created_at'].isoformat()
    await db.price_analysis.insert_one(analysis_dict)
    return analysis





@router.get("/rms/analysis", response_model=list[PriceAnalysis])
@cached(ttl=600, key_prefix="rms_analysis")  # Cache for 10 min
async def get_price_analysis(current_user: User = Depends(get_current_user)):
    analyses = await db.price_analysis.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    return analyses

# ============= LOYALTY =============





@router.post("/rms/restrictions")
async def set_dynamic_restrictions(
    request: DynamicRestrictionsRequest,
    current_user: User = Depends(get_current_user)
):
    """
    Set dynamic restrictions for revenue management
    - Minimum Length of Stay (MinLOS)
    - Closed to Arrival (CTA)
    - Closed to Departure (CTD)
    - Stop Sell
    """
    restriction = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'date': request.date,
        'room_type': request.room_type,
        'min_los': request.min_los,
        'cta': request.cta,
        'ctd': request.ctd,
        'stop_sell': request.stop_sell,
        'created_by': current_user.name,
        'created_at': datetime.now(UTC).isoformat()
    }

    # Check if restriction exists
    existing = await db.rms_restrictions.find_one({
        'tenant_id': current_user.tenant_id,
        'date': request.date,
        'room_type': request.room_type
    })

    if existing:
        await db.rms_restrictions.update_one(
            {'id': existing.get('id')},
            {'$set': restriction}
        )
    else:
        await db.rms_restrictions.insert_one(restriction)

    return {
        'success': True,
        'message': 'Restrictions updated',
        'restriction': restriction
    }






@router.get("/rms/market-compression")
async def get_market_compression(
    date: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """
    Market compression score
    - Overall city occupancy estimate
    - Event impact
    - Pricing opportunity
    """
    target_date = date or datetime.now().date().isoformat()

    # In production, integrate with:
    # - Local DMO (Destination Marketing Organization)
    # - STR (Smith Travel Research)
    # - Competitor data

    # Simulated market compression analysis
    # Check for events
    events = await db.city_events.find({
        'date': target_date
    }).to_list(length=10)

    has_major_event = any(e.get('impact') == 'high' for e in events)

    # Calculate compression score (0-100)
    base_score = 50
    if has_major_event:
        base_score += 30

    # Check competitor pricing (simulated)
    competitor_avg_rate = 120
    our_avg_rate = 100

    if our_avg_rate < competitor_avg_rate:
        pricing_opportunity = ((competitor_avg_rate - our_avg_rate) / our_avg_rate) * 100
    else:
        pricing_opportunity = 0

    compression_score = min(100, base_score)

    return {
        'date': target_date,
        'compression_score': compression_score,
        'compression_level': 'High' if compression_score > 70 else 'Medium' if compression_score > 40 else 'Low',
        'city_occupancy_estimate': f"{compression_score}%",
        'events': [{'name': e.get('name'), 'impact': e.get('impact')} for e in events] if events else [],
        'has_major_event': has_major_event,
        'pricing_opportunity_pct': round(pricing_opportunity, 1),
        'recommendation': 'Increase rates by 15-20%' if compression_score > 70 else 'Monitor market' if compression_score > 40 else 'Consider promotions'
    }


# ============= MAINTENANCE ENHANCEMENTS =============





@router.get("/rms/price-recommendation-slider")
async def get_price_recommendation_with_range(
    room_type: str,
    check_in_date: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get price recommendations with slider range (min, recommended, max)"""
    current_user = await get_current_user(credentials)

    # Get base room price
    room = await db.rooms.find_one({
        'tenant_id': current_user.tenant_id,
        'room_type': room_type
    })

    base_price = room.get('base_price', 100) if room else 100

    # Get historical occupancy - handle date parsing
    try:
        check_in = datetime.fromisoformat(check_in_date.replace('Z', '+00:00'))
    except Exception:
        # Try alternative formats
        try:
            check_in = datetime.strptime(check_in_date, '%Y-%m-%d')
        except Exception:
            check_in = datetime.now(UTC)

    # Calculate occupancy for same date last year
    last_year_date = check_in - timedelta(days=365)
    last_year_bookings = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': last_year_date,
            '$lt': last_year_date + timedelta(days=1)
        },
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in', 'checked_out']}
    })

    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    historical_occupancy_pct = (last_year_bookings / total_rooms * 100) if total_rooms > 0 else 50

    # Calculate current occupancy for the target date
    current_bookings = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': check_in,
            '$lt': check_in + timedelta(days=1)
        },
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
    })

    current_occupancy_pct = (current_bookings / total_rooms * 100) if total_rooms > 0 else 0

    # Pricing logic based on occupancy
    if current_occupancy_pct < 30:
        # Low occupancy - discount to attract bookings
        recommended_price = base_price * 0.85
        min_price = base_price * 0.7
        max_price = base_price
    elif current_occupancy_pct < 60:
        # Medium occupancy - standard pricing
        recommended_price = base_price
        min_price = base_price * 0.85
        max_price = base_price * 1.15
    elif current_occupancy_pct < 80:
        # Good occupancy - increase prices
        recommended_price = base_price * 1.15
        min_price = base_price
        max_price = base_price * 1.3
    else:
        # High occupancy - maximize revenue
        recommended_price = base_price * 1.3
        min_price = base_price * 1.15
        max_price = base_price * 1.5

    return {
        'room_type': room_type,
        'check_in_date': check_in_date,
        'base_price': round(base_price, 2),
        'pricing_recommendation': {
            'min_price': round(min_price, 2),
            'recommended_price': round(recommended_price, 2),
            'max_price': round(max_price, 2)
        },
        'occupancy_analysis': {
            'current_occupancy_pct': round(current_occupancy_pct, 1),
            'historical_occupancy_pct': round(historical_occupancy_pct, 1),
            'current_bookings': current_bookings,
            'total_rooms': total_rooms
        },
        'recommendation_reason': get_pricing_reason(current_occupancy_pct)
    }





@router.get("/rms/demand-heatmap")
async def get_demand_heatmap(
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get historical demand heatmap for visualization"""
    current_user = await get_current_user(credentials)

    # Default to next 90 days
    if start_date and end_date:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
    else:
        start = datetime.now(UTC)
        end = start + timedelta(days=90)

    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})

    # Single fetch of all overlapping bookings in window, then count per-day in memory
    overlapping = await db.bookings.find(
        {
            'tenant_id': current_user.tenant_id,
            'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
            'check_in': {'$lte': end},
            'check_out': {'$gt': start},
        },
        {'_id': 0, 'check_in': 1, 'check_out': 1},
    ).to_list(10000)

    def _to_dt(v):
        if isinstance(v, datetime):
            return v
        if isinstance(v, str):
            try:
                return datetime.fromisoformat(v.replace('Z', '+00:00'))
            except Exception:
                return None
        return None

    parsed = []
    for b in overlapping:
        ci = _to_dt(b.get('check_in'))
        co = _to_dt(b.get('check_out'))
        if ci and co:
            parsed.append((ci, co))

    heatmap_data = []
    current_date = start
    while current_date <= end:
        bookings_count = sum(1 for ci, co in parsed if ci <= current_date < co)
        occupancy_pct = (bookings_count / total_rooms * 100) if total_rooms > 0 else 0
        if occupancy_pct < 30:
            demand_level = 'low'
        elif occupancy_pct < 60:
            demand_level = 'medium'
        elif occupancy_pct < 80:
            demand_level = 'high'
        else:
            demand_level = 'very_high'
        heatmap_data.append({
            'date': current_date.strftime('%Y-%m-%d'),
            'day_of_week': current_date.strftime('%A'),
            'occupancy_pct': round(occupancy_pct, 1),
            'bookings_count': bookings_count,
            'demand_level': demand_level
        })
        current_date += timedelta(days=1)

    return {
        'period': {
            'start_date': start.isoformat(),
            'end_date': end.isoformat(),
            'total_days': len(heatmap_data)
        },
        'heatmap_data': heatmap_data
    }





@router.get("/rms/compset-analysis")
async def get_compset_analysis(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get competitive set analysis - most wanted features"""
    current_user = await get_current_user(credentials)

    # Get competitor data
    competitors = []
    async for comp in db.competitors.find({'tenant_id': current_user.tenant_id}):
        competitors.append(comp)

    # If no competitors, return sample data
    if len(competitors) == 0:
        competitors = [
            {
                'name': 'Competitor Hotel A',
                'avg_rate': 120.0,
                'occupancy_estimate': 75.0,
                'rating': 4.2,
                'features': ['Free WiFi', 'Breakfast', 'Pool', 'Spa', 'Gym']
            },
            {
                'name': 'Competitor Hotel B',
                'avg_rate': 110.0,
                'occupancy_estimate': 82.0,
                'rating': 4.5,
                'features': ['Free WiFi', 'Breakfast', 'Pool', 'Restaurant', 'Parking']
            },
            {
                'name': 'Competitor Hotel C',
                'avg_rate': 135.0,
                'occupancy_estimate': 68.0,
                'rating': 4.0,
                'features': ['Free WiFi', 'Breakfast', 'Spa', 'Gym', 'Business Center']
            }
        ]

    # Analyze features
    feature_count = {}
    for comp in competitors:
        for feature in comp.get('features', []):
            feature_count[feature] = feature_count.get(feature, 0) + 1

    # Sort by popularity
    most_wanted_features = [
        {'feature': feature, 'competitor_count': count, 'popularity_pct': round(count / len(competitors) * 100, 1)}
        for feature, count in sorted(feature_count.items(), key=lambda x: x[1], reverse=True)
    ]

    # Calculate averages
    avg_rate = sum(c.get('avg_rate', 0) for c in competitors) / len(competitors) if competitors else 0
    avg_occupancy = sum(c.get('occupancy_estimate', 0) for c in competitors) / len(competitors) if competitors else 0
    avg_rating = sum(c.get('rating', 0) for c in competitors) / len(competitors) if competitors else 0

    return {
        'compset_summary': {
            'total_competitors': len(competitors),
            'avg_rate': round(avg_rate, 2),
            'avg_occupancy_pct': round(avg_occupancy, 1),
            'avg_rating': round(avg_rating, 2)
        },
        'competitors': competitors,
        'most_wanted_features': most_wanted_features[:10],  # Top 10
        'feature_gap_analysis': 'To be implemented with property amenity comparison'
    }


# ===== REVENUE MOBILE MODULE =====
# Comprehensive revenue management endpoints optimized for mobile apps





@router.get("/rms/compset/real-time-prices")
async def get_compset_real_time_prices(
    check_in_date: str,
    room_type: str = 'Standard',
    current_user: User = Depends(get_current_user)
):
    """Get competitor prices - REAL DATA from compset database

    Note: In production, this would integrate with:
    - Booking.com API
    - Expedia API
    - OTA Insight
    For now, uses manually entered competitor data from database
    """

    # Get competitor data from database
    competitors = await db.competitor_prices.find({
        'tenant_id': current_user.tenant_id,
        'check_in_date': check_in_date,
        'room_type': room_type
    }, {'_id': 0}).to_list(20)

    # If no data, return empty (no mock data)
    if not competitors:
        return {
            'check_in_date': check_in_date,
            'room_type': room_type,
            'competitors': [],
            'market_average': 0,
            'recommendation': {
                'suggested_price': 0,
                'strategy': 'No competitor data available',
                'confidence': 0
            },
            'last_updated': datetime.now(UTC).isoformat()
        }

    avg_price = sum(c['price'] for c in competitors) / len(competitors)

    return {
        'check_in_date': check_in_date,
        'room_type': room_type,
        'competitors': competitors,
        'market_average': round(avg_price, 2),
        'recommendation': {
            'suggested_price': round(avg_price * 0.95, 2),
            'strategy': 'Price competitively to maximize occupancy',
            'confidence': 85
        },
        'last_updated': datetime.now(UTC).isoformat()
    }



