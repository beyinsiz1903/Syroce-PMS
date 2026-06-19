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

from core.database import db
from core.security import (
    get_current_user,
    security,
)
from models.enums import CancellationPolicyType, ChannelType, MarketSegment, RateType
from modules.pms_core.role_permission_service import require_op  # v92 DW

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


# ─── Endpoints (split: revenue_mobile) ───


@router.get("/revenue-mobile/adr")
async def get_adr_mobile(
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get ADR (Average Daily Rate) for mobile app"""
    current_user = await get_current_user(credentials)

    # Default to last 30 days
    if start_date and end_date:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
    else:
        end = datetime.now(UTC)
        start = end - timedelta(days=30)

    # Sprint 33: ADR computed via parallel batched queries
    # (replaces 2× O(N) loops over folio_charges that caused 12s timeout).
    import asyncio as _asyncio
    prev_start = start - (end - start)
    prev_end = start

    async def _compute_period(p_start, p_end):
        bks = await db.bookings.find({
            'tenant_id': current_user.tenant_id,
            'status': {'$in': ['checked_out', 'checked_in']},
            'check_in': {
                '$gte': p_start.isoformat(),
                '$lte': p_end.isoformat()
            }
        }, {'_id': 0, 'id': 1, 'check_in': 1, 'check_out': 1}).to_list(10000)
        if not bks:
            return 0.0, 0
        booking_ids = [b['id'] for b in bks]
        # Aggregate room revenue in ONE query via $in
        agg = await db.folio_charges.aggregate([
            {'$match': {
                'tenant_id': current_user.tenant_id,
                'booking_id': {'$in': booking_ids},
                'charge_category': 'room',
                'voided': False,
            }},
            {'$group': {'_id': None, 'total': {'$sum': '$total'}}},
        ]).to_list(1)
        revenue = float(agg[0]['total']) if agg else 0.0
        nights = 0
        for b in bks:
            try:
                ci = datetime.fromisoformat(b['check_in'])
                co = datetime.fromisoformat(b['check_out'])
                nights += max((co - ci).days, 1)
            except Exception:
                nights += 1
        return revenue, nights

    (total_room_revenue, total_room_nights), (prev_room_revenue, prev_room_nights) = \
        await _asyncio.gather(
            _compute_period(start, end),
            _compute_period(prev_start, prev_end),
        )

    adr = round(total_room_revenue / total_room_nights, 2) if total_room_nights > 0 else 0
    prev_adr = round(prev_room_revenue / prev_room_nights, 2) if prev_room_nights > 0 else 0
    change_pct = round(((adr - prev_adr) / prev_adr * 100), 2) if prev_adr > 0 else 0

    return {
        'period': {
            'start_date': start.strftime('%Y-%m-%d'),
            'end_date': end.strftime('%Y-%m-%d')
        },
        'adr': adr,
        'room_nights': total_room_nights,
        'room_revenue': round(total_room_revenue, 2),
        'comparison': {
            'previous_adr': prev_adr,
            'change_pct': change_pct,
            'trend': 'up' if change_pct > 0 else 'down' if change_pct < 0 else 'stable'
        }
    }





@router.get("/revenue-mobile/revpar")
async def get_revpar_mobile(
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get RevPAR (Revenue Per Available Room) for mobile app"""
    current_user = await get_current_user(credentials)

    # Default to last 30 days
    if start_date and end_date:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
    else:
        end = datetime.now(UTC)
        start = end - timedelta(days=30)

    # Get total rooms
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    days = (end - start).days + 1
    available_room_nights = total_rooms * days

    # Get total room revenue from folio charges
    charges = await db.folio_charges.find({
        'tenant_id': current_user.tenant_id,
        'charge_category': 'room',
        'voided': False,
        'date': {
            '$gte': start.isoformat(),
            '$lte': end.isoformat()
        }
    }).to_list(10000)

    total_room_revenue = sum(c.get('total', 0) for c in charges)

    # Calculate RevPAR
    revpar = round(total_room_revenue / available_room_nights, 2) if available_room_nights > 0 else 0

    # Calculate occupancy
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['checked_out', 'checked_in']},
        'check_in': {
            '$gte': start.isoformat(),
            '$lte': end.isoformat()
        }
    }).to_list(10000)

    occupied_room_nights = 0
    for booking in bookings:
        check_in = datetime.fromisoformat(booking['check_in'])
        check_out = datetime.fromisoformat(booking['check_out'])
        nights = (check_out - check_in).days
        occupied_room_nights += max(nights, 1)

    occupancy_pct = round((occupied_room_nights / available_room_nights * 100), 2) if available_room_nights > 0 else 0

    # Previous period comparison
    prev_start = start - (end - start)
    prev_end = start
    prev_days = (prev_end - prev_start).days + 1
    prev_available_room_nights = total_rooms * prev_days

    prev_charges = await db.folio_charges.find({
        'tenant_id': current_user.tenant_id,
        'charge_category': 'room',
        'voided': False,
        'date': {
            '$gte': prev_start.isoformat(),
            '$lte': prev_end.isoformat()
        }
    }).to_list(10000)

    prev_room_revenue = sum(c.get('total', 0) for c in prev_charges)
    prev_revpar = round(prev_room_revenue / prev_available_room_nights, 2) if prev_available_room_nights > 0 else 0
    change_pct = round(((revpar - prev_revpar) / prev_revpar * 100), 2) if prev_revpar > 0 else 0

    return {
        'period': {
            'start_date': start.strftime('%Y-%m-%d'),
            'end_date': end.strftime('%Y-%m-%d')
        },
        'revpar': revpar,
        'room_revenue': round(total_room_revenue, 2),
        'available_room_nights': available_room_nights,
        'occupied_room_nights': occupied_room_nights,
        'occupancy_pct': occupancy_pct,
        'comparison': {
            'previous_revpar': prev_revpar,
            'change_pct': change_pct,
            'trend': 'up' if change_pct > 0 else 'down' if change_pct < 0 else 'stable'
        }
    }





@router.get("/revenue-mobile/total-revenue")
async def get_total_revenue_mobile(
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get total revenue breakdown for mobile app"""
    current_user = await get_current_user(credentials)

    # Default to last 30 days
    if start_date and end_date:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
    else:
        end = datetime.now(UTC)
        start = end - timedelta(days=30)

    # Get all charges in date range
    charges = await db.folio_charges.find({
        'tenant_id': current_user.tenant_id,
        'voided': False,
        'date': {
            '$gte': start.isoformat(),
            '$lte': end.isoformat()
        }
    }).to_list(10000)

    # Calculate revenue by category
    room_revenue = sum(c.get('total', 0) for c in charges if c.get('charge_category') == 'room')
    food_revenue = sum(c.get('total', 0) for c in charges if c.get('charge_category') == 'food')
    beverage_revenue = sum(c.get('total', 0) for c in charges if c.get('charge_category') == 'beverage')
    minibar_revenue = sum(c.get('total', 0) for c in charges if c.get('charge_category') == 'minibar')
    spa_revenue = sum(c.get('total', 0) for c in charges if c.get('charge_category') == 'spa')
    laundry_revenue = sum(c.get('total', 0) for c in charges if c.get('charge_category') == 'laundry')
    parking_revenue = sum(c.get('total', 0) for c in charges if c.get('charge_category') == 'parking')
    other_revenue = sum(c.get('total', 0) for c in charges if c.get('charge_category') not in ['room', 'food', 'beverage', 'minibar', 'spa', 'laundry', 'parking'])

    total_revenue = sum(c.get('total', 0) for c in charges)

    # Daily breakdown
    daily_revenue = {}
    for charge in charges:
        date = charge.get('date', '')[:10]
        daily_revenue[date] = daily_revenue.get(date, 0) + charge.get('total', 0)

    daily_data = [{'date': date, 'revenue': round(revenue, 2)} for date, revenue in sorted(daily_revenue.items())]

    # Previous period comparison
    prev_start = start - (end - start)
    prev_end = start
    prev_charges = await db.folio_charges.find({
        'tenant_id': current_user.tenant_id,
        'voided': False,
        'date': {
            '$gte': prev_start.isoformat(),
            '$lte': prev_end.isoformat()
        }
    }).to_list(10000)

    prev_total_revenue = sum(c.get('total', 0) for c in prev_charges)
    change_pct = round(((total_revenue - prev_total_revenue) / prev_total_revenue * 100), 2) if prev_total_revenue > 0 else 0

    return {
        'period': {
            'start_date': start.strftime('%Y-%m-%d'),
            'end_date': end.strftime('%Y-%m-%d')
        },
        'total_revenue': round(total_revenue, 2),
        'revenue_by_category': {
            'room': round(room_revenue, 2),
            'food': round(food_revenue, 2),
            'beverage': round(beverage_revenue, 2),
            'minibar': round(minibar_revenue, 2),
            'spa': round(spa_revenue, 2),
            'laundry': round(laundry_revenue, 2),
            'parking': round(parking_revenue, 2),
            'other': round(other_revenue, 2)
        },
        'daily_breakdown': daily_data,
        'comparison': {
            'previous_total': round(prev_total_revenue, 2),
            'change_pct': change_pct,
            'trend': 'up' if change_pct > 0 else 'down' if change_pct < 0 else 'stable'
        }
    }





@router.get("/revenue-mobile/segment-distribution")
@cached(ttl=300, key_prefix="rev_mob_segment")  # 5dk (Tur 2 timeout fix)
async def get_segment_distribution_mobile(
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get revenue distribution by market segment for mobile app"""
    current_user = await get_current_user(credentials)

    # Default to last 30 days
    if start_date and end_date:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
    else:
        end = datetime.now(UTC)
        start = end - timedelta(days=30)

    # Get bookings in date range
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['checked_out', 'checked_in', 'confirmed', 'guaranteed']},
        'check_in': {
            '$gte': start.isoformat(),
            '$lte': end.isoformat()
        }
    }).to_list(10000)

    # Calculate revenue by market segment
    segment_data = {}
    for booking in bookings:
        segment = booking.get('market_segment', 'other')

        # Get charges for this booking
        charges = await db.folio_charges.find({
            'tenant_id': current_user.tenant_id,
            'booking_id': booking['id'],
            'voided': False
        }).to_list(1000)

        booking_revenue = sum(c.get('total', 0) for c in charges)

        if segment not in segment_data:
            segment_data[segment] = {
                'revenue': 0,
                'bookings_count': 0,
                'room_nights': 0
            }

        segment_data[segment]['revenue'] += booking_revenue
        segment_data[segment]['bookings_count'] += 1

        # Calculate room nights
        check_in = datetime.fromisoformat(booking['check_in'])
        check_out = datetime.fromisoformat(booking['check_out'])
        nights = (check_out - check_in).days
        segment_data[segment]['room_nights'] += max(nights, 1)

    # Calculate percentages and format
    total_revenue = sum(s['revenue'] for s in segment_data.values())

    segments = []
    for segment, data in segment_data.items():
        percentage = round((data['revenue'] / total_revenue * 100), 2) if total_revenue > 0 else 0
        avg_booking_value = round(data['revenue'] / data['bookings_count'], 2) if data['bookings_count'] > 0 else 0

        segments.append({
            'segment': segment,
            'revenue': round(data['revenue'], 2),
            'percentage': percentage,
            'bookings_count': data['bookings_count'],
            'room_nights': data['room_nights'],
            'avg_booking_value': avg_booking_value
        })

    # Sort by revenue descending
    segments.sort(key=lambda x: x['revenue'], reverse=True)

    return {
        'period': {
            'start_date': start.strftime('%Y-%m-%d'),
            'end_date': end.strftime('%Y-%m-%d')
        },
        'total_revenue': round(total_revenue, 2),
        'segments': segments,
        'top_segment': segments[0]['segment'] if segments else None
    }





@router.get("/revenue-mobile/pickup-graph")
async def get_pickup_graph_mobile(
    target_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get pickup graph showing booking pace for mobile app"""
    current_user = await get_current_user(credentials)

    # Default to 30 days from now
    if target_date:
        target = datetime.fromisoformat(target_date)
    else:
        target = datetime.now(UTC) + timedelta(days=30)

    # Get all bookings for target date
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': target.isoformat()[:10],
            '$lt': (target + timedelta(days=1)).isoformat()[:10]
        },
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
    }).to_list(10000)

    # Get total rooms
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})

    # Organize bookings by booking date
    pickup_data = []
    days_out = [90, 60, 30, 14, 7, 3, 1, 0]  # Days before target date

    for days in days_out:
        cutoff_date = target - timedelta(days=days)

        # Count bookings made before this cutoff
        bookings_by_cutoff = [b for b in bookings if datetime.fromisoformat(b.get('created_at', b.get('check_in'))) <= cutoff_date]
        rooms_booked = len(bookings_by_cutoff)
        occupancy_pct = round((rooms_booked / total_rooms * 100), 2) if total_rooms > 0 else 0

        pickup_data.append({
            'days_out': days,
            'date': cutoff_date.strftime('%Y-%m-%d'),
            'rooms_booked': rooms_booked,
            'occupancy_pct': occupancy_pct
        })

    # Calculate pickup velocity (last 7 days)
    recent_bookings = [b for b in bookings if datetime.fromisoformat(b.get('created_at', b.get('check_in'))) >= (datetime.now(UTC) - timedelta(days=7))]
    pickup_velocity = len(recent_bookings)

    # Compare with same date last year
    last_year_target = target - timedelta(days=365)
    last_year_bookings = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': last_year_target.isoformat()[:10],
            '$lt': (last_year_target + timedelta(days=1)).isoformat()[:10]
        },
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in', 'checked_out']}
    })

    current_bookings = len(bookings)
    comparison_pct = round(((current_bookings - last_year_bookings) / last_year_bookings * 100), 2) if last_year_bookings > 0 else 0

    return {
        'target_date': target.strftime('%Y-%m-%d'),
        'total_rooms': total_rooms,
        'current_bookings': current_bookings,
        'current_occupancy': round((current_bookings / total_rooms * 100), 2) if total_rooms > 0 else 0,
        'pickup_data': pickup_data,
        'pickup_velocity': {
            'last_7_days': pickup_velocity,
            'daily_average': round(pickup_velocity / 7, 2)
        },
        'year_over_year': {
            'last_year_bookings': last_year_bookings,
            'change_pct': comparison_pct,
            'trend': 'up' if comparison_pct > 0 else 'down' if comparison_pct < 0 else 'stable'
        }
    }





@router.get("/revenue-mobile/forecast")
@cached(ttl=300, key_prefix="rev_mob_forecast")  # 5dk (Tur 2 timeout fix)
async def get_revenue_forecast_mobile(
    days_ahead: int = 30,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get revenue forecast for next N days for mobile app"""
    current_user = await get_current_user(credentials)

    # Get confirmed bookings for forecast period
    start = datetime.now(UTC)
    end = start + timedelta(days=days_ahead)

    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
        'check_in': {
            '$gte': start.isoformat(),
            '$lte': end.isoformat()
        }
    }).to_list(10000)

    # Get total rooms
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})

    # Gerçek ADR: rate_per_night taşıyan bookings'lerin ortalaması (fabrikasyon 100 fallback kaldırıldı)
    _rated = [b.get('rate_per_night', 0) for b in bookings if b.get('rate_per_night', 0) > 0]
    real_adr = (sum(_rated) / len(_rated)) if _rated else 0

    # Calculate daily forecast
    daily_forecast = {}
    current_date = start

    while current_date <= end:
        date_str = current_date.strftime('%Y-%m-%d')

        # Count bookings for this date
        bookings_on_date = [b for b in bookings
                           if b['check_in'] <= current_date.isoformat()
                           and b['check_out'] > current_date.isoformat()]

        rooms_occupied = len(bookings_on_date)
        occupancy_pct = round((rooms_occupied / total_rooms * 100), 2) if total_rooms > 0 else 0

        # Oda gelirini gerçek per-night rate'ten hesapla; eksikse gerçek ADR (yoksa 0, fabrikasyon yok)
        estimated_room_revenue = 0
        rate_known = 0
        for booking in bookings_on_date:
            rate = booking.get('rate_per_night', 0)
            if rate and rate > 0:
                estimated_room_revenue += rate
                rate_known += 1
            else:
                estimated_room_revenue += real_adr  # gerçek veriden türemiş ortalama (sabit 100 değil)

        # Ancillary fabrikasyonu (x1.25) kaldırıldı: total = gerçek oda geliri
        daily_forecast[date_str] = {
            'date': date_str,
            'day_of_week': current_date.strftime('%A'),
            'rooms_occupied': rooms_occupied,
            'occupancy_pct': occupancy_pct,
            'estimated_room_revenue': round(estimated_room_revenue, 2),
            'estimated_total_revenue': round(estimated_room_revenue, 2),
            'rate_source': ('actual' if rooms_occupied and rate_known == rooms_occupied else ('partial_adr' if real_adr > 0 else 'unavailable'))
        }

        current_date += timedelta(days=1)

    # Calculate totals
    total_forecast_revenue = sum(d['estimated_total_revenue'] for d in daily_forecast.values())
    total_forecast_room_revenue = sum(d['estimated_room_revenue'] for d in daily_forecast.values())
    avg_occupancy = sum(d['occupancy_pct'] for d in daily_forecast.values()) / len(daily_forecast) if daily_forecast else 0

    # Compare with same period last year
    last_year_start = start - timedelta(days=365)
    last_year_end = last_year_start + timedelta(days=days_ahead)

    last_year_charges = await db.folio_charges.find({
        'tenant_id': current_user.tenant_id,
        'voided': False,
        'date': {
            '$gte': last_year_start.isoformat(),
            '$lte': last_year_end.isoformat()
        }
    }).to_list(10000)

    last_year_revenue = sum(c.get('total', 0) for c in last_year_charges)
    variance_pct = round(((total_forecast_revenue - last_year_revenue) / last_year_revenue * 100), 2) if last_year_revenue > 0 else 0

    return {
        'forecast_period': {
            'start_date': start.strftime('%Y-%m-%d'),
            'end_date': end.strftime('%Y-%m-%d'),
            'days': days_ahead
        },
        'summary': {
            'total_forecast_revenue': round(total_forecast_revenue, 2),
            'total_room_revenue': round(total_forecast_room_revenue, 2),
            'avg_occupancy_pct': round(avg_occupancy, 2),
            'total_bookings': len(bookings)
        },
        'daily_forecast': list(daily_forecast.values()),
        'comparison': {
            'last_year_revenue': round(last_year_revenue, 2),
            'variance_pct': variance_pct,
            'trend': 'up' if variance_pct > 0 else 'down' if variance_pct < 0 else 'stable'
        }
    }





@router.get("/revenue-mobile/channel-distribution")
@cached(ttl=300, key_prefix="rev_mob_channel_dist")  # 5dk (Tur 2 timeout fix)
async def get_channel_distribution_mobile(
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get revenue distribution by booking channel for mobile app"""
    current_user = await get_current_user(credentials)

    # Default to last 30 days
    if start_date and end_date:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
    else:
        end = datetime.now(UTC)
        start = end - timedelta(days=30)

    # Get bookings in date range
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['checked_out', 'checked_in', 'confirmed', 'guaranteed']},
        'check_in': {
            '$gte': start.isoformat(),
            '$lte': end.isoformat()
        }
    }).to_list(10000)

    # Calculate revenue by channel
    channel_data = {}
    for booking in bookings:
        source = booking.get('source', 'direct')

        # Get charges for this booking
        charges = await db.folio_charges.find({
            'tenant_id': current_user.tenant_id,
            'booking_id': booking['id'],
            'voided': False
        }).to_list(1000)

        booking_revenue = sum(c.get('total', 0) for c in charges)

        # Get OTA commission if applicable (None-safe)
        commission_pct = booking.get('commission_pct') or 0
        try:
            commission_pct = float(commission_pct)
        except (TypeError, ValueError):
            commission_pct = 0.0
        commission_amount = booking_revenue * (commission_pct / 100)
        net_revenue = booking_revenue - commission_amount

        if source not in channel_data:
            channel_data[source] = {
                'gross_revenue': 0,
                'commission': 0,
                'net_revenue': 0,
                'bookings_count': 0,
                'room_nights': 0
            }

        channel_data[source]['gross_revenue'] += booking_revenue
        channel_data[source]['commission'] += commission_amount
        channel_data[source]['net_revenue'] += net_revenue
        channel_data[source]['bookings_count'] += 1

        # Calculate room nights
        check_in = datetime.fromisoformat(booking['check_in'])
        check_out = datetime.fromisoformat(booking['check_out'])
        nights = (check_out - check_in).days
        channel_data[source]['room_nights'] += max(nights, 1)

    # Calculate percentages and format
    total_gross_revenue = sum(c['gross_revenue'] for c in channel_data.values())
    total_net_revenue = sum(c['net_revenue'] for c in channel_data.values())
    total_commission = sum(c['commission'] for c in channel_data.values())

    channels = []
    for channel, data in channel_data.items():
        percentage = round((data['gross_revenue'] / total_gross_revenue * 100), 2) if total_gross_revenue > 0 else 0
        avg_booking_value = round(data['net_revenue'] / data['bookings_count'], 2) if data['bookings_count'] > 0 else 0
        commission_pct = round((data['commission'] / data['gross_revenue'] * 100), 2) if data['gross_revenue'] > 0 else 0

        channels.append({
            'channel': channel,
            'gross_revenue': round(data['gross_revenue'], 2),
            'commission': round(data['commission'], 2),
            'net_revenue': round(data['net_revenue'], 2),
            'percentage': percentage,
            'bookings_count': data['bookings_count'],
            'room_nights': data['room_nights'],
            'avg_booking_value': avg_booking_value,
            'commission_pct': commission_pct
        })

    # Sort by net revenue descending
    channels.sort(key=lambda x: x['net_revenue'], reverse=True)

    return {
        'period': {
            'start_date': start.strftime('%Y-%m-%d'),
            'end_date': end.strftime('%Y-%m-%d')
        },
        'summary': {
            'total_gross_revenue': round(total_gross_revenue, 2),
            'total_commission': round(total_commission, 2),
            'total_net_revenue': round(total_net_revenue, 2),
            'effective_commission_pct': round((total_commission / total_gross_revenue * 100), 2) if total_gross_revenue > 0 else 0
        },
        'channels': channels,
        'top_channel': channels[0]['channel'] if channels else None
    }





@router.get("/revenue-mobile/cancellation-report")
async def get_cancellation_report_mobile(
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get cancellation and no-show report for mobile app"""
    current_user = await get_current_user(credentials)

    # Default to last 30 days
    if start_date and end_date:
        start = datetime.fromisoformat(start_date)
        end = datetime.fromisoformat(end_date)
    else:
        end = datetime.now(UTC)
        start = end - timedelta(days=30)

    # Get all bookings in date range
    all_bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': start.isoformat(),
            '$lte': end.isoformat()
        }
    }).to_list(10000)

    # Get cancelled bookings
    cancelled_bookings = [b for b in all_bookings if b.get('status') == 'cancelled']

    # Get no-show bookings
    no_show_bookings = [b for b in all_bookings if b.get('status') == 'no_show']

    # Calculate metrics
    total_bookings = len(all_bookings)
    cancellation_count = len(cancelled_bookings)
    no_show_count = len(no_show_bookings)

    cancellation_rate = round((cancellation_count / total_bookings * 100), 2) if total_bookings > 0 else 0
    no_show_rate = round((no_show_count / total_bookings * 100), 2) if total_bookings > 0 else 0

    # Calculate lost revenue
    def calculate_booking_revenue(booking):
        if 'total_amount' in booking:
            return booking['total_amount']
        # Calculate from rate and nights
        check_in = datetime.fromisoformat(booking.get('check_in', start.isoformat()))
        check_out = datetime.fromisoformat(booking.get('check_out', (start + timedelta(days=1)).isoformat()))
        nights = max((check_out - check_in).days, 1)
        rate = booking.get('rate_per_night', 0)
        return rate * nights

    cancelled_revenue = sum(calculate_booking_revenue(b) for b in cancelled_bookings)
    no_show_revenue = sum(calculate_booking_revenue(b) for b in no_show_bookings)
    total_lost_revenue = cancelled_revenue + no_show_revenue

    # Calculate cancellation fees collected
    cancellation_fees = 0
    for booking in cancelled_bookings:
        fees = await db.folio_charges.find({
            'tenant_id': current_user.tenant_id,
            'booking_id': booking['id'],
            'charge_type': 'cancellation_fee',
            'voided': False
        }).to_list(100)
        cancellation_fees += sum(f.get('total', 0) for f in fees)

    # Analyze by channel
    channel_analysis = {}
    for booking in cancelled_bookings + no_show_bookings:
        source = booking.get('source', 'direct')
        status = booking.get('status')

        if source not in channel_analysis:
            channel_analysis[source] = {
                'cancellations': 0,
                'no_shows': 0,
                'total': 0,
                'lost_revenue': 0
            }

        if status == 'cancelled':
            channel_analysis[source]['cancellations'] += 1
        elif status == 'no_show':
            channel_analysis[source]['no_shows'] += 1

        channel_analysis[source]['total'] += 1
        channel_analysis[source]['lost_revenue'] += calculate_booking_revenue(booking)

    # Format channel data
    channels = []
    for channel, data in channel_analysis.items():
        # Count total bookings from this channel
        channel_bookings = [b for b in all_bookings if b.get('source') == channel]
        channel_total = len(channel_bookings)

        rate = round((data['total'] / channel_total * 100), 2) if channel_total > 0 else 0

        channels.append({
            'channel': channel,
            'cancellations': data['cancellations'],
            'no_shows': data['no_shows'],
            'total_issues': data['total'],
            'rate': rate,
            'lost_revenue': round(data['lost_revenue'], 2)
        })

    # Sort by total issues descending
    channels.sort(key=lambda x: x['total_issues'], reverse=True)

    # Analyze by lead time (how far in advance cancelled)
    lead_time_analysis = {
        'same_day': 0,
        '1_3_days': 0,
        '4_7_days': 0,
        '8_14_days': 0,
        '15_plus_days': 0
    }

    for booking in cancelled_bookings:
        check_in = datetime.fromisoformat(booking['check_in'])
        cancelled_at = datetime.fromisoformat(booking.get('cancelled_at', booking.get('updated_at', booking.get('created_at'))))
        days_before = (check_in - cancelled_at).days

        if days_before == 0:
            lead_time_analysis['same_day'] += 1
        elif days_before <= 3:
            lead_time_analysis['1_3_days'] += 1
        elif days_before <= 7:
            lead_time_analysis['4_7_days'] += 1
        elif days_before <= 14:
            lead_time_analysis['8_14_days'] += 1
        else:
            lead_time_analysis['15_plus_days'] += 1

    return {
        'period': {
            'start_date': start.strftime('%Y-%m-%d'),
            'end_date': end.strftime('%Y-%m-%d')
        },
        'summary': {
            'total_bookings': total_bookings,
            'cancellations': cancellation_count,
            'no_shows': no_show_count,
            'cancellation_rate': cancellation_rate,
            'no_show_rate': no_show_rate,
            'total_lost_revenue': round(total_lost_revenue, 2),
            'cancellation_fees_collected': round(cancellation_fees, 2),
            'net_lost_revenue': round(total_lost_revenue - cancellation_fees, 2)
        },
        'by_channel': channels,
        'cancellation_lead_time': lead_time_analysis,
        'top_issue_channel': channels[0]['channel'] if channels else None
    }





@router.post("/revenue-mobile/rate-override")
async def create_rate_override_mobile(
    data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("override_rate")),  # v92 DW
):
    """Create rate override for mobile app - requires approval for significant changes"""
    current_user = await get_current_user(credentials)

    # Validate required fields
    required_fields = ['room_type', 'date', 'new_rate', 'reason']
    for field in required_fields:
        if field not in data:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")

    room_type = data['room_type']
    date_str = data['date']
    new_rate = float(data['new_rate'])
    reason = data['reason']

    # Get current base rate for this room type
    # This is simplified - in production you'd have a rate table
    base_rate = 100  # Default base rate

    # Calculate percentage change
    change_pct = abs((new_rate - base_rate) / base_rate * 100) if base_rate > 0 else 0

    # Determine if approval is needed (>15% change)
    needs_approval = change_pct > 15

    # Create rate override record
    override_id = str(uuid.uuid4())
    override = {
        'id': override_id,
        'tenant_id': current_user.tenant_id,
        'room_type': room_type,
        'date': date_str,
        'base_rate': base_rate,
        'new_rate': new_rate,
        'change_pct': round(change_pct, 2),
        'reason': reason,
        'created_by': current_user.id,
        'created_by_name': current_user.name,
        'created_at': datetime.now(UTC).isoformat(),
        'status': 'pending' if needs_approval else 'approved',
        'approved_by': None if needs_approval else current_user.id,
        'approved_at': None if needs_approval else datetime.now(UTC).isoformat()
    }

    # Save to database
    await db.rate_overrides.insert_one(override)

    # If needs approval, create approval request
    if needs_approval:
        approval_request = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'approval_type': 'rate_override',
            'requested_by': current_user.id,
            'requested_by_name': current_user.name,
            'status': 'pending',
            'priority': 'high' if change_pct > 30 else 'medium',
            'details': {
                'room_type': room_type,
                'date': date_str,
                'base_rate': base_rate,
                'new_rate': new_rate,
                'change_pct': round(change_pct, 2),
                'reason': reason,
                'override_id': override_id
            },
            'created_at': datetime.now(UTC).isoformat()
        }
        await db.approval_requests.insert_one(approval_request)

        message = f"Rate override request created. Requires approval (change: {round(change_pct, 2)}%)"
    else:
        message = "Rate override applied successfully"

    return {
        'message': message,
        'override_id': override_id,
        'status': override['status'],
        'needs_approval': needs_approval,
        'change_pct': round(change_pct, 2),
        'new_rate': new_rate
    }


# ===== DASHBOARD ENHANCEMENTS (REVENUE-EXPENSE, BUDGET, PROFITABILITY, TRENDS) =====



