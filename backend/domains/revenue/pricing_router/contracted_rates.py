"""
Revenue / Pricing Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
from __future__ import annotations
from modules.pms_core.role_permission_service import require_op  # v98 DW

import logging
import uuid
from datetime import UTC, datetime, timedelta
from datetime import date as DateType
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from core.database import db
from core.security import (
    get_current_user,
)
from models.enums import CancellationPolicyType, ChannelType, MarketSegment, RateType
from models.schemas import User

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


# ─── Endpoints (split: contracted_rates) ───


@router.get("/contracted-rates")
async def get_contracted_rates(
    company_id: str | None = None,
    status: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """
    Get contracted rates list
    """
    today = datetime.now().date()

    # Sample contracted rates data
    rates = [
        {
            'id': str(uuid.uuid4()),
            'company_name': 'Tech Solutions Ltd.',
            'contract_type': 'volume_based',
            'start_date': (today - timedelta(days=180)).isoformat(),
            'end_date': (today + timedelta(days=185)).isoformat(),
            'room_nights_committed': 500,
            'room_nights_used': 342,
            'contracted_rate': 1500,
            'discount_percentage': 25,
            'status': 'active'
        },
        {
            'id': str(uuid.uuid4()),
            'company_name': 'Finance Corp',
            'contract_type': 'fixed_rate',
            'start_date': (today - timedelta(days=90)).isoformat(),
            'end_date': (today + timedelta(days=45)).isoformat(),
            'room_nights_committed': 200,
            'room_nights_used': 156,
            'contracted_rate': 1800,
            'discount_percentage': 20,
            'status': 'active'
        }
    ]

    # Filter by status
    if status:
        rates = [r for r in rates if r['status'] == status]

    # Filter by company
    if company_id:
        rates = [r for r in rates if r.get('company_id') == company_id]

    return {
        'contracted_rates': rates,
        'count': len(rates)
    }





@router.get("/contracted-rates/allotment-utilization")
async def get_allotment_utilization(
    company_id: str | None = None,
    date_range_days: int = 30,
    current_user: User = Depends(get_current_user)
):
    """
    Track contracted allotment utilization
    - Rooms allocated vs used
    - Pickup rate
    - Alert when 90% utilized
    """
    end_dt = datetime.now(UTC)
    start_dt = end_dt - timedelta(days=date_range_days)

    match_criteria = {
        'tenant_id': current_user.tenant_id
    }

    if company_id:
        match_criteria['company_id'] = company_id

    # Get all companies with contracted rates
    utilization_data = []

    async for company in db.companies.find(match_criteria):
        if not company.get('contracted_rate'):
            continue

        # Get allotment data (if configured)
        allotment = await db.contracted_allotments.find_one({
            'company_id': company.get('id'),
            'tenant_id': current_user.tenant_id
        })

        if not allotment:
            continue

        allocated_rooms = allotment.get('rooms_allocated', 0)

        # Count bookings from this company in date range
        bookings_count = 0
        async for booking in db.bookings.find({
            'company_id': company.get('id'),
            'tenant_id': current_user.tenant_id,
            'check_in': {
                '$gte': start_dt.date().isoformat(),
                '$lte': end_dt.date().isoformat()
            }
        }):
            bookings_count += 1

        utilization_pct = (bookings_count / allocated_rooms * 100) if allocated_rooms > 0 else 0

        utilization_data.append({
            'company_id': company.get('id'),
            'company_name': company.get('name'),
            'allocated_rooms': allocated_rooms,
            'rooms_used': bookings_count,
            'remaining_rooms': max(0, allocated_rooms - bookings_count),
            'utilization_pct': round(utilization_pct, 1),
            'status': '🚨 Critical' if utilization_pct >= 90 else '⚠️ High' if utilization_pct >= 75 else '✅ Normal',
            'alert': utilization_pct >= 90
        })

    # Sort by utilization
    utilization_data.sort(key=lambda x: x['utilization_pct'], reverse=True)

    # Generate alerts
    alerts = []
    for item in utilization_data:
        if item['utilization_pct'] >= 90:
            alerts.append(f"⚠️ {item['company_name']}: Allotment {item['utilization_pct']}% used - Consider increasing allocation")

    return {
        'period_days': date_range_days,
        'total_companies': len(utilization_data),
        'high_utilization_count': sum(1 for d in utilization_data if d['utilization_pct'] >= 75),
        'utilization_data': utilization_data,
        'alerts': alerts
    }






@router.get("/contracted-rates/pickup-alerts")
async def get_pickup_vs_allocation_alerts(
    current_user: User = Depends(get_current_user)
):
    """
    Pickup vs allocation alerts
    - Monitor booking pace
    - Alert when pickup is slow
    """
    alerts = []

    # Get all contracted allotments
    async for allotment in db.contracted_allotments.find({
        'tenant_id': current_user.tenant_id,
        'status': 'active'
    }):
        company_id = allotment.get('company_id')
        company = await db.companies.find_one({'id': company_id})

        allocated = allotment.get('rooms_allocated', 0)
        start_date = allotment.get('start_date')
        end_date = allotment.get('end_date')

        # Count actual bookings
        bookings_count = await db.bookings.count_documents({
            'company_id': company_id,
            'tenant_id': current_user.tenant_id,
            'check_in': {
                '$gte': start_date,
                '$lte': end_date
            }
        })

        pickup_pct = (bookings_count / allocated * 100) if allocated > 0 else 0

        # Calculate expected pickup (time-based)
        if start_date and end_date:
            total_days = (datetime.fromisoformat(end_date) - datetime.fromisoformat(start_date)).days
            days_passed = (datetime.now(UTC) - datetime.fromisoformat(start_date)).days
            expected_pickup_pct = (days_passed / total_days * 100) if total_days > 0 else 0

            if pickup_pct < expected_pickup_pct - 20:  # 20% behind pace
                alerts.append({
                    'company_name': company.get('name') if company else 'Unknown',
                    'allocated': allocated,
                    'picked_up': bookings_count,
                    'pickup_pct': round(pickup_pct, 1),
                    'expected_pickup_pct': round(expected_pickup_pct, 1),
                    'status': 'behind_pace',
                    'message': f"⚠️ Pickup is {round(expected_pickup_pct - pickup_pct, 1)}% behind expected pace"
                })

    return {
        'total_alerts': len(alerts),
        'alerts': alerts
    }


# ============= RESERVATION FINAL IMPROVEMENTS =============

# ============= AI PRICING ENGINE (RMS ENHANCEMENT) =============





@router.get("/contracting/pickup-graph")
async def get_pickup_graph_data(
    contract_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Tour operator pickup graph
    - Daily/weekly/monthly pickup progress
    - Comparison with allocated rooms
    - Forecast vs actual
    """
    # Get contract/allotment details
    allotment = await db.contracted_allotments.find_one({
        'id': contract_id,
        'tenant_id': current_user.tenant_id
    })

    if not allotment:
        raise HTTPException(status_code=404, detail="Contract not found")

    start_date = datetime.fromisoformat(allotment.get('start_date'))
    end_date = datetime.fromisoformat(allotment.get('end_date'))
    company_id = allotment.get('company_id')
    allocated_total = allotment.get('rooms_allocated', 0)

    # Get daily pickup data
    current_date = start_date
    pickup_data = []
    cumulative_pickup = 0
    cumulative_allocation = 0

    days_total = (end_date - start_date).days
    daily_allocation = allocated_total / days_total if days_total > 0 else 0

    while current_date <= end_date:
        date_str = current_date.date().isoformat()

        # Count bookings for this date
        bookings_count = await db.bookings.count_documents({
            'company_id': company_id,
            'tenant_id': current_user.tenant_id,
            'check_in': date_str
        })

        cumulative_pickup += bookings_count
        cumulative_allocation += daily_allocation

        pickup_data.append({
            'date': date_str,
            'daily_pickup': bookings_count,
            'cumulative_pickup': int(cumulative_pickup),
            'cumulative_allocation': int(cumulative_allocation),
            'pickup_pct': round((cumulative_pickup / cumulative_allocation * 100), 1) if cumulative_allocation > 0 else 0,
            'on_track': cumulative_pickup >= cumulative_allocation * 0.8  # 80% threshold
        })

        current_date += timedelta(days=1)

    return {
        'contract_id': contract_id,
        'company_id': company_id,
        'period': {
            'start_date': start_date.date().isoformat(),
            'end_date': end_date.date().isoformat(),
            'total_days': days_total
        },
        'allocation': {
            'total_allocated': allocated_total,
            'total_picked_up': cumulative_pickup,
            'remaining': allocated_total - cumulative_pickup,
            'utilization_pct': round((cumulative_pickup / allocated_total * 100), 1) if allocated_total > 0 else 0
        },
        'pickup_graph_data': pickup_data,
        'forecast': {
            'projected_final_pickup': int(cumulative_pickup * (days_total / max(1, (datetime.now().date() - start_date.date()).days))),
            'on_track': cumulative_pickup >= allocated_total * 0.5  # At midpoint, should be 50%+
        }
    }






@router.get("/contracting/realization-report")
async def get_realization_report(
    start_date: str,
    end_date: str,
    company_id: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """
    Contract realization report
    - Allocated vs realized rooms
    - Realization percentage
    - Revenue impact
    """
    match_criteria = {
        'tenant_id': current_user.tenant_id
    }

    if company_id:
        match_criteria['company_id'] = company_id

    # Get all active allotments in period
    allotments = []
    async for allot in db.contracted_allotments.find(match_criteria):
        allot_start = allot.get('start_date')
        allot_end = allot.get('end_date')

        # Check if allotment overlaps with requested period
        if allot_start <= end_date and allot_end >= start_date:
            # Count realized bookings
            realized = await db.bookings.count_documents({
                'company_id': allot.get('company_id'),
                'tenant_id': current_user.tenant_id,
                'check_in': {'$gte': start_date, '$lte': end_date}
            })

            allocated = allot.get('rooms_allocated', 0)
            realization_pct = (realized / allocated * 100) if allocated > 0 else 0

            # Calculate revenue
            revenue = 0
            async for booking in db.bookings.find({
                'company_id': allot.get('company_id'),
                'tenant_id': current_user.tenant_id,
                'check_in': {'$gte': start_date, '$lte': end_date}
            }):
                revenue += booking.get('total_amount', 0)

            # Get company details
            company = await db.companies.find_one({'id': allot.get('company_id')})

            allotments.append({
                'company_name': company.get('name') if company else 'Unknown',
                'company_id': allot.get('company_id'),
                'contract_id': allot.get('id'),
                'allocated_rooms': allocated,
                'realized_rooms': realized,
                'unrealized_rooms': max(0, allocated - realized),
                'realization_pct': round(realization_pct, 1),
                'revenue': round(revenue, 2),
                'avg_rate': round(revenue / realized, 2) if realized > 0 else 0,
                'status': 'Excellent' if realization_pct >= 90 else 'Good' if realization_pct >= 70 else 'Poor' if realization_pct >= 50 else 'Critical'
            })

    # Sort by realization percentage
    allotments.sort(key=lambda x: x['realization_pct'], reverse=True)

    # Calculate totals
    total_allocated = sum(a['allocated_rooms'] for a in allotments)
    total_realized = sum(a['realized_rooms'] for a in allotments)
    total_revenue = sum(a['revenue'] for a in allotments)
    overall_realization = (total_realized / total_allocated * 100) if total_allocated > 0 else 0

    return {
        'period': {
            'start_date': start_date,
            'end_date': end_date
        },
        'summary': {
            'total_allocated': total_allocated,
            'total_realized': total_realized,
            'overall_realization_pct': round(overall_realization, 1),
            'total_revenue': round(total_revenue, 2),
            'avg_rate': round(total_revenue / total_realized, 2) if total_realized > 0 else 0
        },
        'allotments': allotments,
        'performance_breakdown': {
            'excellent': sum(1 for a in allotments if a['realization_pct'] >= 90),
            'good': sum(1 for a in allotments if 70 <= a['realization_pct'] < 90),
            'poor': sum(1 for a in allotments if 50 <= a['realization_pct'] < 70),
            'critical': sum(1 for a in allotments if a['realization_pct'] < 50)
        }
    }






@router.post("/contracting/free-sale-control")
async def set_free_sale_control(
    company_id: str,
    enable_free_sale: bool,
    min_lead_time_days: int | None = None,
    release_period_days: int | None = None,
    max_free_sale_rooms: int | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v98 DW
):
    """
    Free-sale control mechanism
    - Enable/disable free sale for tour operator
    - Minimum lead time (e.g., 7 days before arrival)
    - Release period (e.g., release unsold rooms 14 days before)
    - Maximum free sale rooms
    """
    control = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'company_id': company_id,
        'enable_free_sale': enable_free_sale,
        'min_lead_time_days': min_lead_time_days or 7,
        'release_period_days': release_period_days or 14,
        'max_free_sale_rooms': max_free_sale_rooms or 10,
        'created_at': datetime.now(UTC).isoformat(),
        'created_by': current_user.name
    }

    # Store or update
    existing = await db.free_sale_controls.find_one({
        'tenant_id': current_user.tenant_id,
        'company_id': company_id
    })

    if existing:
        await db.free_sale_controls.update_one(
            {'company_id': company_id, 'tenant_id': current_user.tenant_id},
            {'$set': control}
        )
    else:
        await db.free_sale_controls.insert_one(control)

    return {
        'success': True,
        'message': 'Free-sale control configured',
        'control': control
    }






@router.get("/contracting/free-sale-availability")
async def check_free_sale_availability(
    company_id: str,
    check_in_date: str,
    rooms_requested: int,
    current_user: User = Depends(get_current_user)
):
    """
    Check if free-sale booking is allowed
    - Validate against control rules
    - Return availability decision
    """
    # Get free-sale control
    control = await db.free_sale_controls.find_one({
        'tenant_id': current_user.tenant_id,
        'company_id': company_id
    })

    if not control or not control.get('enable_free_sale'):
        return {
            'allowed': False,
            'reason': 'Free-sale not enabled for this tour operator'
        }

    # Check lead time
    check_in = datetime.fromisoformat(check_in_date).date()
    today = datetime.now().date()
    lead_time_days = (check_in - today).days

    if lead_time_days < control.get('min_lead_time_days', 7):
        return {
            'allowed': False,
            'reason': f"Minimum lead time is {control['min_lead_time_days']} days"
        }

    # Check max free-sale rooms
    if rooms_requested > control.get('max_free_sale_rooms', 10):
        return {
            'allowed': False,
            'reason': f"Maximum free-sale rooms is {control['max_free_sale_rooms']}"
        }

    # Check release period (if within release period, check allotment)
    release_period = control.get('release_period_days', 14)
    if lead_time_days <= release_period:
        # Check if rooms were released
        # In production: Check actual inventory release
        return {
            'allowed': True,
            'reason': 'Within release period - check inventory',
            'note': 'Inventory check required'
        }

    return {
        'allowed': True,
        'rooms_requested': rooms_requested,
        'lead_time_days': lead_time_days
    }


# ============= AI GUEST PERSONA PROFILING =============



