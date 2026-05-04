"""
revenue

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Domain Router: Analytics

Extracted from legacy_routes.py — GM Dashboard, pickup analysis, anomaly detection, revenue analytics.
"""
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials

from core.database import db
from core.security import get_current_user, security
from modules.pms_core.role_permission_service import require_role as _require_role

# v67 Bug DD: frontdesk/* endpoint'lerinde RBAC eksikti — HK kullanıcı guest PII (search-bookings),
# müsaitlik (available-rooms), oda atama (assign-room) erişebiliyordu. Front office personeline kısıtla.
_FD_READ = Depends(_require_role("super_admin", "admin", "supervisor", "front_desk"))
_FD_WRITE = Depends(_require_role("super_admin", "admin", "front_desk"))

try:
    from routers.pms_availability import check_room_availability
except Exception:  # pragma: no cover
    async def check_room_availability(*args, **kwargs):
        return {"available": False, "rooms": []}



# --------------------------------------------------------------------------
# GM Dashboard - Pickup Analysis & Anomaly Detection
# --------------------------------------------------------------------------







# rbac-allow: cache-rbac — FO booking search operasyonel

# rbac-allow: cache-rbac — FO available rooms operasyonel











































_SYSTEM_HEALTH_CACHE: dict = {"ts": 0.0, "payload": None}
_SYSTEM_HEALTH_TTL = 5.0  # seconds

router = APIRouter(prefix="/api", tags=["analytics"])


# ── GET /revenue/market-segment-breakdown ──
@router.get("/revenue/market-segment-breakdown")
async def get_market_segment_breakdown(
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get revenue breakdown by market segment (OTA, Direct, Corporate, Group)"""
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC)
    if not start_date:
        start_date = today.replace(day=1)
    else:
        start_date = datetime.fromisoformat(start_date)

    if not end_date:
        end_date = today
    else:
        end_date = datetime.fromisoformat(end_date)

    # Aggregate bookings by source (mapping to market segments)
    segment_data = {
        'OTA': {'bookings': 0, 'revenue': 0, 'rooms': 0},
        'Direct': {'bookings': 0, 'revenue': 0, 'rooms': 0},
        'Corporate': {'bookings': 0, 'revenue': 0, 'rooms': 0},
        'Group': {'bookings': 0, 'revenue': 0, 'rooms': 0}
    }

    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': start_date.date().isoformat(), '$lte': end_date.date().isoformat()}
    }):
        source = booking.get('source', 'Direct')

        # Map source to segment
        if source in ['Booking.com', 'Expedia', 'Airbnb']:
            segment = 'OTA'
        elif source in ['Corporate', 'Company']:
            segment = 'Corporate'
        elif source in ['Group', 'Wedding', 'Conference']:
            segment = 'Group'
        else:
            segment = 'Direct'

        segment_data[segment]['bookings'] += 1
        segment_data[segment]['revenue'] += booking.get('total_amount', 0)
        segment_data[segment]['rooms'] += 1

    # Calculate percentages
    total_revenue = sum(s['revenue'] for s in segment_data.values())
    total_bookings = sum(s['bookings'] for s in segment_data.values())

    for segment in segment_data:
        segment_data[segment]['revenue_pct'] = round((segment_data[segment]['revenue'] / total_revenue * 100) if total_revenue > 0 else 0, 2)
        segment_data[segment]['bookings_pct'] = round((segment_data[segment]['bookings'] / total_bookings * 100) if total_bookings > 0 else 0, 2)
        segment_data[segment]['revenue'] = round(segment_data[segment]['revenue'], 2)

    return {
        'segments': segment_data,
        'total_revenue': round(total_revenue, 2),
        'total_bookings': total_bookings,
        'period': {
            'start': start_date.date().isoformat(),
            'end': end_date.date().isoformat()
        }
    }
# ── GET /revenue/adr-tracking ──
@router.get("/revenue/adr-tracking")
async def get_adr_tracking(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get ADR tracking with last year vs forecast vs actual comparison"""
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC)
    current_year = today.year
    last_year = current_year - 1

    # Get current month ADR
    month_start = today.replace(day=1)
    next_month = month_start + timedelta(days=32)
    month_end = next_month.replace(day=1) - timedelta(days=1)

    async def calculate_adr(start, end):
        total_revenue = 0
        total_rooms = 0
        async for booking in db.bookings.find({
            'tenant_id': current_user.tenant_id,
            'check_in': {'$gte': start.date().isoformat(), '$lte': end.date().isoformat()},
            'status': {'$in': ['confirmed', 'checked_in', 'checked_out']}
        }):
            total_revenue += booking.get('total_amount', 0)
            total_rooms += 1
        return round(total_revenue / total_rooms, 2) if total_rooms > 0 else 0

    # Current year ADR
    actual_adr = await calculate_adr(month_start, month_end)

    # Last year ADR (same month)
    last_year_start = month_start.replace(year=last_year)
    last_year_end = month_end.replace(year=last_year)
    last_year_adr = await calculate_adr(last_year_start, last_year_end)

    # Forecast (simple: last year + 10%)
    forecast_adr = round(last_year_adr * 1.1, 2)

    # Calculate variance
    vs_last_year = round(((actual_adr - last_year_adr) / last_year_adr * 100) if last_year_adr > 0 else 0, 2)
    vs_forecast = round(((actual_adr - forecast_adr) / forecast_adr * 100) if forecast_adr > 0 else 0, 2)

    return {
        'actual_adr': actual_adr,
        'last_year_adr': last_year_adr,
        'forecast_adr': forecast_adr,
        'vs_last_year_pct': vs_last_year,
        'vs_forecast_pct': vs_forecast,
        'month': today.month,
        'year': current_year
    }
