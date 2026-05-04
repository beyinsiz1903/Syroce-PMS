"""
rms_rates

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Department-Specific Endpoints Router
Front Office, Housekeeping Manager, Finance, Revenue, F&B, Maintenance,
Sales, HR, IT/Security department dashboards.
Extracted from server.py for modularity.
"""
import logging

logger = logging.getLogger(__name__)
import random
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import RolePermissionService, require_op

_role_perm = RolePermissionService()


def _enforce(role: str, op: str):
    """Bug CU (v60) — Departments/Reports/Rates/POS RBAC zorunlu."""
    _role_perm.enforce_permission(role, op)

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: F401
except ImportError:
    Workbook = None

try:
    from cache_manager import cache, cached
except ImportError:
    cache = None  # type: ignore
    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator

security = HTTPBearer()


# ==================== DEPARTMENT-SPECIFIC ENDPOINTS ====================

# rbac-allow: cache-rbac — FO dashboard operasyonel, hotel staff geneli görür (FO/HK/manager/admin)

# rbac-allow: cache-rbac — HK dashboard operasyonel, FO/HK/manager/admin görür








# NOTE: /ai/dashboard/briefing duplicate removed (R10b) — canonical implementation
# lives in `domains/ai/endpoints.py::get_daily_briefing` with @cached(ttl=300) and
# parallel `_asyncio.gather` over 4 collections.




# rbac-allow: cache-rbac — booking için müsait odalar operasyonel (FO/HK/manager)



# rbac-allow: cache-rbac — HK aktif temizlik timer'ları operasyonel (HK/FO/manager)











































# rbac-allow: cache-rbac — task kanban operasyonel cross-role (FO/HK/maintenance/manager)

router = APIRouter(prefix="/api", tags=["departments"])


# ── GET /rms/rate-recommendations ──
@router.get("/rms/rate-recommendations")
@cached(ttl=600, key_prefix="rms_recommendations")  # Cache for 10 min
async def get_rate_recommendations(
    days_ahead: int = 14,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v84 DT: AI rate önerileri (revenue)
):
    """AI-powered rate recommendations based on demand forecast"""
    today = datetime.now(UTC).date()

    # Get current base rates
    room_types = await db.rooms.aggregate([
        {'$match': {'tenant_id': current_user.tenant_id}},
        {'$group': {
            '_id': '$room_type',
            'avg_price': {'$avg': '$price_per_night'},
            'count': {'$sum': 1}
        }}
    ]).to_list(100)

    base_rates = {rt['_id']: rt['avg_price'] for rt in room_types}
    if not base_rates:
        base_rates = {'standard': 100, 'deluxe': 150, 'suite': 250}

    # Hoist tenant-wide constants out of the per-day loop, then run all
    # historical lookups concurrently to cut Atlas round-trips from 14 → 1.
    import asyncio as _asyncio
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    target_dates = [today + timedelta(days=d) for d in range(days_ahead)]
    same_dates_ly = [td.replace(year=td.year - 1) for td in target_dates]
    historical_counts = await _asyncio.gather(*[
        db.bookings.count_documents({
            'tenant_id': current_user.tenant_id,
            'check_in': {
                '$gte': sd.isoformat(),
                '$lte': (sd + timedelta(days=1)).isoformat()
            }
        }) for sd in same_dates_ly
    ])

    recommendations = []

    for days in range(days_ahead):
        target_date = target_dates[days]

        # Forecast occupancy
        base_occ = 65
        weekend_boost = 15 if target_date.weekday() in [4, 5] else 0
        seasonal = 10 if target_date.month in [6, 7, 8, 12] else 0
        variation = random.randint(-5, 8)
        forecasted_occ = min(98, base_occ + weekend_boost + seasonal + variation)

        # Historical bookings (precomputed in parallel above).
        historical = historical_counts[days]

        # Rate recommendation logic
        rate_adjustments = {}
        strategy = {}

        if forecasted_occ >= 90:
            # Very high demand
            for room_type, base_rate in base_rates.items():
                adjustment = 25
                rate_adjustments[room_type] = {
                    'current_rate': base_rate,
                    'recommended_rate': round(base_rate * (1 + adjustment/100), 2),
                    'adjustment_pct': adjustment,
                    'adjustment_amount': round(base_rate * adjustment/100, 2)
                }
            strategy = {
                'action': 'maximize',
                'min_stay': 2,
                'close_to_arrival': True,
                'stop_sell': forecasted_occ > 95,
                'reason': 'Peak demand - maximize revenue'
            }
        elif forecasted_occ >= 75:
            # Good demand
            for room_type, base_rate in base_rates.items():
                adjustment = 10
                rate_adjustments[room_type] = {
                    'current_rate': base_rate,
                    'recommended_rate': round(base_rate * (1 + adjustment/100), 2),
                    'adjustment_pct': adjustment,
                    'adjustment_amount': round(base_rate * adjustment/100, 2)
                }
            strategy = {
                'action': 'optimize',
                'min_stay': 1,
                'close_to_arrival': False,
                'stop_sell': False,
                'reason': 'Strong demand - optimize rates'
            }
        elif forecasted_occ >= 50:
            # Moderate demand
            for room_type, base_rate in base_rates.items():
                adjustment = 0
                rate_adjustments[room_type] = {
                    'current_rate': base_rate,
                    'recommended_rate': base_rate,
                    'adjustment_pct': adjustment,
                    'adjustment_amount': 0
                }
            strategy = {
                'action': 'maintain',
                'min_stay': 1,
                'close_to_arrival': False,
                'stop_sell': False,
                'reason': 'Balanced demand - maintain rates'
            }
        else:
            # Low demand
            for room_type, base_rate in base_rates.items():
                adjustment = -15
                rate_adjustments[room_type] = {
                    'current_rate': base_rate,
                    'recommended_rate': round(base_rate * (1 + adjustment/100), 2),
                    'adjustment_pct': adjustment,
                    'adjustment_amount': round(base_rate * adjustment/100, 2)
                }
            strategy = {
                'action': 'stimulate',
                'min_stay': 1,
                'close_to_arrival': False,
                'stop_sell': False,
                'reason': 'Low demand - stimulate bookings',
                'suggested_promotions': ['Weekend getaway', 'Extended stay discount']
            }

        # Calculate potential revenue impact (total_rooms hoisted above).
        potential_revenue_impact = sum(
            adj['adjustment_amount'] * total_rooms * (forecasted_occ / 100)
            for adj in rate_adjustments.values()
        ) / len(rate_adjustments) if rate_adjustments else 0

        recommendations.append({
            'date': target_date.isoformat(),
            'day_of_week': target_date.strftime('%A'),
            'forecasted_occupancy': forecasted_occ,
            'historical_bookings': historical,
            'rate_adjustments': rate_adjustments,
            'strategy': strategy,
            'potential_revenue_impact': round(potential_revenue_impact, 2),
            'confidence': 0.85 if days < 7 else 0.75,
            'priority': 'high' if abs(strategy.get('action') in ['maximize', 'stimulate']) else 'medium'
        })

    return {
        'recommendations': recommendations,
        'total_days': len(recommendations),
        'summary': {
            'high_demand_days': sum(1 for r in recommendations if r['forecasted_occupancy'] >= 85),
            'low_demand_days': sum(1 for r in recommendations if r['forecasted_occupancy'] < 50),
            'total_potential_impact': round(sum(r['potential_revenue_impact'] for r in recommendations), 2)
        }
    }
# ── POST /rms/apply-recommendation ──
@router.post("/rms/apply-recommendation")
async def apply_rate_recommendation(
    recommendation_data: dict,
    current_user: User = Depends(get_current_user)
):
    """Apply recommended rates to room inventory"""
    _enforce(current_user.role, "manage_rates")  # Bug CU
    target_date = recommendation_data.get('date')
    rate_adjustments = recommendation_data.get('rate_adjustments', {})

    updated_rooms = 0
    for room_type, adjustment in rate_adjustments.items():
        result = await db.rooms.update_many(
            {
                'tenant_id': current_user.tenant_id,
                'room_type': room_type
            },
            {
                '$set': {
                    'price_per_night': adjustment['recommended_rate'],
                    'last_rate_update': datetime.now(UTC).isoformat(),
                    'rate_update_reason': f"RMS recommendation for {target_date}"
                }
            }
        )
        updated_rooms += result.modified_count

    # Log the rate change
    await db.rate_change_log.insert_one({
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'date': target_date,
        'rate_adjustments': rate_adjustments,
        'applied_by': current_user.email,
        'applied_at': datetime.now(UTC).isoformat(),
        'source': 'rms_recommendation'
    })

    return {
        'success': True,
        'rooms_updated': updated_rooms,
        'date': target_date,
        'message': f'Rates updated for {updated_rooms} rooms'
    }
# ── GET /rates/periods ──
@router.get("/rates/periods")
@cached(ttl=600, key_prefix="rates_periods")  # Cache for 10 min
async def get_rate_periods(
    operator_id: str,
    room_type_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v84 DT: rate config (revenue)
):
    """
    Get multi-period rates for operator and room type
    """
    periods = await db.rate_periods.find({
        'tenant_id': current_user.tenant_id,
        'operator_id': operator_id,
        'room_type_id': room_type_id
    }).sort('start_date', 1).to_list(100)

    return {'periods': periods}
# ── POST /rates/periods/bulk-update ──
@router.post("/rates/periods/bulk-update")
async def bulk_update_rate_periods(
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """
    Bulk update/insert rate periods for operator
    """
    _enforce(current_user.role, "manage_rates")  # Bug CU
    operator_id = data.get('operator_id')
    room_type_id = data.get('room_type_id')
    periods = data.get('periods', [])

    # Delete existing periods
    await db.rate_periods.delete_many({
        'tenant_id': current_user.tenant_id,
        'operator_id': operator_id,
        'room_type_id': room_type_id
    })

    # Insert new periods
    if periods:
        for period in periods:
            period_doc = {
                'id': period.get('id') if not period.get('isNew') else str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'operator_id': operator_id,
                'room_type_id': room_type_id,
                'start_date': period['start_date'],
                'end_date': period['end_date'],
                'rate': period['rate'],
                'currency': period.get('currency', 'USD'),
                'created_at': datetime.now(UTC).isoformat(),
                'created_by': current_user.id
            }
            await db.rate_periods.insert_one(period_doc)

    return {'message': f'{len(periods)} rate periods saved successfully'}
# ── GET /rates/stop-sale/status ──
@router.get("/rates/stop-sale/status")
@cached(ttl=300, key_prefix="rates_stop_sale")  # Cache for 5 min
async def get_stop_sale_status(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v84 DT: stop sale durumu (revenue)
):
    """
    Get stop-sale status for all operators
    """
    stop_sales = await db.stop_sales.find({
        'tenant_id': current_user.tenant_id,
        'active': True
    }).to_list(100)

    operators = {}
    for ss in stop_sales:
        operators[ss['operator_id']] = ss.get('stop_sale', False)
        operators[f"{ss['operator_id']}_timestamp"] = ss.get('updated_at')

    return {'operators': operators}
# ── POST /rates/stop-sale/toggle ──
@router.post("/rates/stop-sale/toggle")
async def toggle_stop_sale(
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """
    Toggle stop-sale for specific operator
    """
    _enforce(current_user.role, "manage_rates")  # Bug CU
    operator_id = data.get('operator_id')
    stop_sale = data.get('stop_sale', False)

    await db.stop_sales.update_one(
        {
            'tenant_id': current_user.tenant_id,
            'operator_id': operator_id
        },
        {
            '$set': {
                'stop_sale': stop_sale,
                'active': True,
                'updated_at': datetime.now(UTC).isoformat(),
                'updated_by': current_user.id
            }
        },
        upsert=True
    )

    return {
        'operator_id': operator_id,
        'stop_sale': stop_sale,
        'message': f'Stop-sale {"activated" if stop_sale else "deactivated"} for {operator_id}'
    }
# ── GET /allotment/consumption ──
@router.get("/allotment/consumption")
@cached(ttl=300, key_prefix="allotment_consumption")  # Cache for 5 min
async def get_allotment_consumption(
    start_date: str = None,
    end_date: str = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v85 DU: operatör allotment (revenue)
):
    """
    Get allotment consumption chart data: Allocated vs Sold vs Remaining
    """
    # Get all allotments for tenant
    allotments = await db.allotments.find({
        'tenant_id': current_user.tenant_id,
        'status': 'active'
    }).to_list(100)

    consumption_data = []

    for allotment in allotments:
        operator_name = allotment.get('operator_name', 'Unknown')
        allocated = allotment.get('allocated_rooms', 0)

        # Count sold bookings for this allotment
        bookings = await db.bookings.find({
            'tenant_id': current_user.tenant_id,
            'allotment_id': allotment.get('id'),
            'status': {'$in': ['confirmed', 'checked_in', 'checked_out']}
        }).to_list(1000)

        sold = len(bookings)
        remaining = max(allocated - sold, 0)
        utilization = int(sold / allocated * 100) if allocated > 0 else 0

        # Determine status
        if remaining == 0:
            status = 'critical'
        elif utilization >= 80:
            status = 'warning'
        else:
            status = 'good'

        consumption_data.append({
            'operator': operator_name,
            'allocated': allocated,
            'sold': sold,
            'remaining': remaining,
            'utilization': utilization,
            'status': status
        })

    return {'allotments': consumption_data}
# ── POST /loyalty/tier-benefits/update ──
@router.post("/loyalty/tier-benefits/update")
async def update_loyalty_tier_benefits(
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """
    Update loyalty tier benefits configuration
    """
    _enforce(current_user.role, "manage_loyalty_tiers")  # Bug CU
    tiers = data.get('tiers', [])

    for tier in tiers:
        await db.loyalty_tier_benefits.update_one(
            {
                'tenant_id': current_user.tenant_id,
                'tier_name': tier['name']
            },
            {
                '$set': {
                    'benefits': tier['benefits'],
                    'updated_at': datetime.now(UTC).isoformat(),
                    'updated_by': current_user.id
                }
            },
            upsert=True
        )

    return {'message': f'{len(tiers)} tier benefits updated successfully'}
