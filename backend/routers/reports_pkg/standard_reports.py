"""Auto-split from reports.py — backward-compatible sub-router."""
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

security = HTTPBearer()

from core.database import db
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

try:
    from domains.pms.night_audit_module import AuditStatus, AutomaticPosting, NightAuditRecord
except ImportError:
    NightAuditRecord = None
    AuditStatus = None
    AutomaticPosting = None


try:
    from infra.logging_service import get_logging_service
except ImportError:
    get_logging_service = None

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator

logger = logging.getLogger(__name__)
sub_router = APIRouter()

@sub_router.get("/reports/occupancy")
@cached(ttl=600, key_prefix="report_occupancy")  # Cache for 10 minutes
async def get_occupancy_report(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
    _perm=Depends(require_op("view_reports")),  # v71 Bug DH
):
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)

    # Normalize to timezone-aware UTC datetimes to avoid naive/aware comparison issues
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)

    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    bookings = await db.bookings.find({'tenant_id': current_user.tenant_id, 'status': {'$in': ['confirmed', 'checked_in', 'checked_out']},
                                       '$or': [{'check_in': {'$gte': start.isoformat(), '$lte': end.isoformat()}},
                                              {'check_out': {'$gte': start.isoformat(), '$lte': end.isoformat()}},
                                              {'check_in': {'$lte': start.isoformat()}, 'check_out': {'$gte': end.isoformat()}}]}, {'_id': 0}).to_list(1000)
    days = (end - start).days + 1
    total_room_nights = total_rooms * days
    occupied_room_nights = 0
    for booking in bookings:
        ci_raw = booking['check_in']
        co_raw = booking['check_out']
        check_in = datetime.fromisoformat(ci_raw) if isinstance(ci_raw, str) else ci_raw
        check_out = datetime.fromisoformat(co_raw) if isinstance(co_raw, str) else co_raw
        if check_in.tzinfo is None:
            check_in = check_in.replace(tzinfo=UTC)
        if check_out.tzinfo is None:
            check_out = check_out.replace(tzinfo=UTC)
        overlap_start = max(start, check_in)
        overlap_end = min(end, check_out)
        if overlap_start < overlap_end:
            occupied_room_nights += (overlap_end - overlap_start).days
    occupancy_rate = (occupied_room_nights / total_room_nights * 100) if total_room_nights > 0 else 0
    return {'start_date': start_date, 'end_date': end_date, 'total_rooms': total_rooms, 'total_room_nights': total_room_nights,
            'occupied_room_nights': occupied_room_nights, 'occupancy_rate': round(occupancy_rate, 2)}


@sub_router.get("/reports/revenue")
@cached(ttl=600, key_prefix="report_revenue")  # Cache for 10 minutes
async def get_revenue_report(
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
    _perm=Depends(require_op("view_reports")),  # v71 Bug DH
):
    # Default: son 30 gün (Tur 2 fix)
    if not end_date:
        end = datetime.now(UTC)
        end_date = end.date().isoformat()
    else:
        end = datetime.fromisoformat(end_date)
    if not start_date:
        start = end - timedelta(days=30)
        start_date = start.date().isoformat()
    else:
        start = datetime.fromisoformat(start_date)
    bookings = await db.bookings.find({'tenant_id': current_user.tenant_id, 'status': {'$in': ['checked_in', 'checked_out']},
                                       'check_in': {'$gte': start.isoformat(), '$lte': end.isoformat()}}, {'_id': 0}).to_list(1000)
    total_revenue = sum(float(b.get('total_amount') or 0) for b in bookings)
    total_room_nights = 0
    for b in bookings:
        ci, co = b.get('check_in'), b.get('check_out')
        if not ci or not co:
            continue
        try:
            total_room_nights += (datetime.fromisoformat(co) - datetime.fromisoformat(ci)).days
        except (ValueError, TypeError):
            continue
    adr = (total_revenue / total_room_nights) if total_room_nights > 0 else 0
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    days = (end - start).days + 1
    total_available_room_nights = total_rooms * days
    rev_par = (total_revenue / total_available_room_nights) if total_available_room_nights > 0 else 0
    folio_charges = await db.folio_charges.find({'tenant_id': current_user.tenant_id, 'date': {'$gte': start.isoformat(), '$lte': end.isoformat()}}, {'_id': 0}).to_list(1000)
    revenue_by_type = {}
    for charge in folio_charges:
        charge_type = charge.get('charge_type') or 'unknown'
        revenue_by_type[charge_type] = revenue_by_type.get(charge_type, 0.0) + float(charge.get('total') or 0)
    return {'start_date': start_date, 'end_date': end_date, 'total_revenue': round(total_revenue, 2), 'room_nights_sold': total_room_nights,
            'adr': round(adr, 2), 'rev_par': round(rev_par, 2), 'revenue_by_type': revenue_by_type, 'bookings_count': len(bookings)}


@sub_router.get("/reports/daily-summary")
@cached(ttl=300, key_prefix="report_daily_summary")  # Cache for 5 minutes
async def get_daily_summary(
    date_str: str | None = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
    _perm=Depends(require_op("view_reports")),  # v71 Bug DH
):
    target_date = datetime.fromisoformat(date_str).date() if date_str else datetime.now(UTC).date()
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())
    arrivals = await db.bookings.count_documents({'tenant_id': current_user.tenant_id, 'check_in': {'$gte': start_of_day.isoformat(), '$lte': end_of_day.isoformat()}})
    departures = await db.bookings.count_documents({'tenant_id': current_user.tenant_id, 'check_out': {'$gte': start_of_day.isoformat(), '$lte': end_of_day.isoformat()}})
    inhouse = await db.bookings.count_documents({'tenant_id': current_user.tenant_id, 'status': 'checked_in'})
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    payments = await db.payments.find({'tenant_id': current_user.tenant_id, 'status': 'paid',
                                       'processed_at': {'$gte': start_of_day.isoformat(), '$lte': end_of_day.isoformat()}}, {'_id': 0}).to_list(1000)
    daily_revenue = sum(p['amount'] for p in payments)
    return {'date': target_date.isoformat(), 'arrivals': arrivals, 'departures': departures, 'inhouse': inhouse, 'total_rooms': total_rooms,
            'occupancy_rate': round((inhouse / total_rooms * 100) if total_rooms > 0 else 0, 2), 'daily_revenue': round(daily_revenue, 2)}


@sub_router.get("/reports/forecast")
@cached(ttl=900, key_prefix="report_forecast")  # Cache for 15 min
async def get_forecast(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
    _perm=Depends(require_op("view_reports")),  # v71 Bug DH
):
    today = datetime.now(UTC).date()
    window_start = datetime.combine(today, datetime.min.time())
    window_end = datetime.combine(today + timedelta(days=days - 1), datetime.max.time())

    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['confirmed', 'checked_in']},
        'check_in': {'$lte': window_end.isoformat()},
        'check_out': {'$gte': window_start.isoformat()},
    }, {'_id': 0, 'check_in': 1, 'check_out': 1}).to_list(10000)

    parsed = []
    for b in bookings:
        try:
            ci = datetime.fromisoformat(b['check_in'].replace('Z', '+00:00')).date()
            co = datetime.fromisoformat(b['check_out'].replace('Z', '+00:00')).date()
            parsed.append((ci, co))
        except (KeyError, ValueError, TypeError, AttributeError):
            continue

    forecast_data = []
    for i in range(days):
        forecast_date = today + timedelta(days=i)
        count = sum(1 for ci, co in parsed if ci <= forecast_date <= co)
        occupancy = round((count / total_rooms * 100) if total_rooms > 0 else 0, 2)
        forecast_data.append({'date': forecast_date.isoformat(), 'bookings': count, 'total_rooms': total_rooms, 'occupancy_rate': occupancy})
    return forecast_data



