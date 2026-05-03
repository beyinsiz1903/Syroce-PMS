"""
executive

Auto-split sub-router (shared imports/classes inlined).
"""
"""
PMS / Dashboard Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import asyncio
import logging
import random
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.database import db
from core.security import (
    get_current_user,
    security,
)
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator




# ── Inline Models ──

class BudgetMonth(BaseModel):
    month: int
    occ_target: float = 0
    adr_target: float = 0
    rev_target: float = 0



class BudgetConfig(BaseModel):
    year: int
    currency: str = "TRY"
    months: list[BudgetMonth]

















# ============= CHECK-IN ENHANCEMENTS =============













# ===== F&B MODULE ENHANCEMENTS =====








# 2. GET /api/executive/performance-alerts - Performance alerts




# 3. GET /api/executive/daily-summary - Daily summary




















# ============================================================================
# NOTIFICATION SYSTEM - Push Notifications
# ============================================================================





async def _build_complaint_management(current_user) -> dict:
    """Complaint management ortak helper — 3 feedback find'ı tek gather'da paralel."""
    tid = current_user.tenant_id
    active_docs, all_low_docs, resolved_docs = await asyncio.gather(
        db.feedback.find({
            'tenant_id': tid,
            'rating': {'$lte': 2},
            'resolved': {'$ne': True},
        }).sort('created_at', -1).limit(20).to_list(20),
        db.feedback.find(
            {'tenant_id': tid, 'rating': {'$lte': 2}},
            {'_id': 0, 'category': 1},
        ).to_list(10000),
        db.feedback.find({
            'tenant_id': tid,
            'rating': {'$lte': 2},
            'resolved': True,
            'resolved_at': {'$exists': True},
        }).limit(50).to_list(50),
    )

    now_utc = datetime.now(UTC)
    active_complaints = []
    for feedback in active_docs:
        try:
            ca = feedback.get('created_at') or now_utc.isoformat()
            days_open = (now_utc - datetime.fromisoformat(str(ca).replace('Z', '+00:00'))).days
        except Exception:
            days_open = 0
        active_complaints.append({
            'id': feedback.get('id', str(uuid.uuid4())),
            'guest_name': feedback.get('guest_name', 'Anonim'),
            'rating': feedback.get('rating', 1),
            'category': feedback.get('category', 'general'),
            'comment': feedback.get('comment', ''),
            'created_at': feedback.get('created_at'),
            'days_open': days_open,
        })

    categories: dict[str, int] = {}
    for feedback in all_low_docs:
        category = feedback.get('category', 'general')
        categories[category] = categories.get(category, 0) + 1

    category_breakdown = [
        {
            'category': cat,
            'category_tr': {
                'room': 'Oda', 'service': 'Servis', 'cleanliness': 'Temizlik',
                'fnb': 'Yiyecek & İçecek', 'general': 'Genel',
            }.get(cat, cat),
            'count': count,
        }
        for cat, count in categories.items()
    ]

    resolution_hours_list = []
    for feedback in resolved_docs:
        try:
            created = datetime.fromisoformat(feedback['created_at'].replace('Z', '+00:00'))
            resolved = datetime.fromisoformat(feedback['resolved_at'].replace('Z', '+00:00'))
            resolution_hours_list.append((resolved - created).total_seconds() / 3600)
        except Exception:
            continue
    avg_resolution_time = (
        sum(resolution_hours_list) / len(resolution_hours_list)
        if resolution_hours_list else 24
    )

    return {
        'active_complaints': active_complaints,
        'active_count': len(active_complaints),
        'category_breakdown': category_breakdown,
        'avg_resolution_time_hours': round(avg_resolution_time, 1),
        'urgent_complaints': len([c for c in active_complaints if c['days_open'] > 2]),
    }


# 3. GET /api/gm/snapshot-enhanced - Enhanced snapshot mode




# 3. GET /api/gm/snapshot-enhanced - Enhanced snapshot mode




# ============================================================================
# SALES & CRM MOBILE - Satış & Müşteri Yönetimi
# ============================================================================

# Models

router = APIRouter(prefix="/api", tags=["PMS / Dashboard"])


# ── GET /executive/kpi-snapshot ──
@router.get("/executive/kpi-snapshot")
@cached(ttl=180, key_prefix="executive_kpi")
async def get_executive_kpi_snapshot(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v71 Bug DH
):
    """
    Get critical KPI snapshot - INSTANT RESPONSE VIA PRE-WARMED CACHE
    """

    # Check pre-warmed cache first (instant!)
    from cache_warmer import cache_warmer
    if cache_warmer:
        cached_data = cache_warmer.get_cached(f"kpi:{current_user.tenant_id}")
        if cached_data:
            return cached_data

    today = datetime.now(UTC).date()
    today_str = today.isoformat()
    tid = current_user.tenant_id
    yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    two_days_ago = (datetime.now(UTC) - timedelta(days=2)).isoformat()

    # Tum bagimsiz sorgular paralel: 2 count + 4 aggregate + 1 list
    (
        total_rooms,
        occupied_rooms,
        revenue_doc,
        bookings_count,
        nps_doc,
        bank_accounts,
        yesterday_revenue_doc,
    ) = await asyncio.gather(
        db.rooms.count_documents({'tenant_id': tid}),
        db.rooms.count_documents({'tenant_id': tid, 'status': 'occupied'}),
        db.payments.aggregate([
            {'$match': {'tenant_id': tid, 'payment_date': {'$gte': yesterday}}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount'}}},
        ]).to_list(1),
        db.bookings.count_documents({
            'tenant_id': tid,
            'status': {'$in': ['checked_in', 'checked_out']},
            'check_in': {'$gte': yesterday},
        }),
        db.reviews.aggregate([
            {'$match': {'tenant_id': tid}},
            {'$group': {'_id': None, 'sum_rating': {'$sum': '$rating'}, 'cnt': {'$sum': 1}}},
        ]).to_list(1),
        db.bank_accounts.find({'tenant_id': tid}).to_list(100),
        db.payments.aggregate([
            {'$match': {'tenant_id': tid, 'payment_date': {'$gte': two_days_ago, '$lt': yesterday}}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount'}}},
        ]).to_list(1),
    )

    if total_rooms == 0:
        total_rooms = 50  # Default for empty DB

    occupancy_pct = (occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0
    total_revenue = (revenue_doc[0]['total'] if revenue_doc else 0) or 0

    # Fallback: revenue yoksa booking total_amount'u toplam (tek aggregate)
    if total_revenue == 0:
        fb_doc = await db.bookings.aggregate([
            {'$match': {
                'tenant_id': tid,
                'status': {'$in': ['checked_in', 'checked_out']},
                'check_in': {'$gte': yesterday},
            }},
            {'$group': {'_id': None, 'total': {'$sum': '$total_amount'}}},
        ]).to_list(1)
        total_revenue = (fb_doc[0]['total'] if fb_doc else 0) or 0

    adr = (total_revenue / bookings_count) if bookings_count > 0 else 0
    revpar = (total_revenue / total_rooms) if total_rooms > 0 else 0

    # NPS — aggregate sonucundan
    if nps_doc and nps_doc[0].get('cnt', 0) > 0:
        avg_nps = nps_doc[0]['sum_rating'] / nps_doc[0]['cnt'] * 20
    else:
        avg_nps = 75  # Convert 5-star to 100 scale

    # Cash position
    cash_balance = sum(a.get('balance', 0) for a in bank_accounts)
    if cash_balance == 0:
        cash_balance = total_revenue * 10  # Rough estimate

    yesterday_revenue = (yesterday_revenue_doc[0]['total'] if yesterday_revenue_doc else 0) or 0
    revenue_trend = ((total_revenue - yesterday_revenue) / yesterday_revenue * 100) if yesterday_revenue > 0 else 0

    return {
        'snapshot_date': today_str,
        'snapshot_time': datetime.now(UTC).isoformat(),
        'kpis': {
            'revpar': {
                'value': round(revpar, 2),
                'trend': round(revenue_trend, 1),
                'label': 'RevPAR',
                'currency': '₺'
            },
            'adr': {
                'value': round(adr, 2),
                'trend': round(revenue_trend * 0.8, 1),
                'label': 'ADR',
                'currency': '₺'
            },
            'occupancy': {
                'value': round(occupancy_pct, 1),
                'trend': 2.5,
                'label': 'Doluluk',
                'unit': '%'
            },
            'revenue': {
                'value': round(total_revenue, 2),
                'trend': round(revenue_trend, 1),
                'label': 'Günlük Gelir',
                'currency': '₺'
            },
            'nps': {
                'value': round(avg_nps, 0),
                'trend': 1.2,
                'label': 'NPS Skoru',
                'unit': '/100'
            },
            'cash': {
                'value': round(cash_balance, 2),
                'trend': round(revenue_trend * 0.5, 1),
                'label': 'Nakit Pozisyon',
                'currency': '₺'
            }
        },
        'summary': {
            'total_rooms': total_rooms,
            'occupied_rooms': occupied_rooms,
            'available_rooms': total_rooms - occupied_rooms,
            'bookings_today': bookings_count
        }
    }
# ── GET /executive/performance-alerts ──
@router.get("/executive/performance-alerts")
async def get_executive_performance_alerts(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get critical performance alerts for executives
    Revenue drop, low occupancy, cash flow warnings, overbooking risks
    """
    current_user = await get_current_user(credentials)

    alerts = []

    # Revenue drop alert
    today = datetime.now(UTC)
    yesterday = (today - timedelta(days=1)).isoformat()
    last_week = (today - timedelta(days=7)).isoformat()

    # 9 bagimsiz read paralel — N+1 fix.
    # Sum'lar Mongo $sum aggregate ile (silent truncation onlemek icin) — to_list yok.
    month_start = datetime.now(UTC).replace(day=1).isoformat()
    tomorrow = (today + timedelta(days=1)).isoformat()
    tid = current_user.tenant_id

    def _sum_pipeline(match: dict, field: str = 'amount') -> list:
        return [{'$match': match}, {'$group': {'_id': None, 't': {'$sum': f'${field}'}}}]

    recent_pay_doc, week_pay_doc, total_rooms, occupied_rooms, arrivals_tomorrow, available_rooms, pending_maintenance, bank_accounts, expense_doc = await asyncio.gather(
        db.payments.aggregate(_sum_pipeline({
            'tenant_id': tid, 'payment_date': {'$gte': yesterday},
        })).to_list(1),
        db.payments.aggregate(_sum_pipeline({
            'tenant_id': tid,
            'payment_date': {'$gte': last_week, '$lt': (today - timedelta(days=6)).isoformat()},
        })).to_list(1),
        db.rooms.count_documents({'tenant_id': tid}),
        db.rooms.count_documents({'tenant_id': tid, 'status': 'occupied'}),
        db.bookings.count_documents({
            'tenant_id': tid, 'check_in': tomorrow,
            'status': {'$in': ['confirmed', 'guaranteed']},
        }),
        db.rooms.count_documents({
            'tenant_id': tid, 'status': {'$in': ['available', 'inspected']},
        }),
        db.maintenance_tasks.count_documents({
            'tenant_id': tid, 'status': 'pending',
            'priority': {'$in': ['high', 'urgent']},
        }),
        db.bank_accounts.find({'tenant_id': tid}, {'_id': 0, 'balance': 1}).to_list(1000),
        db.expenses.aggregate(_sum_pipeline({
            'tenant_id': tid, 'expense_date': {'$gte': month_start},
        })).to_list(1),
    )

    recent_revenue = (recent_pay_doc[0]['t'] if recent_pay_doc else 0) or 0
    week_ago_revenue = (week_pay_doc[0]['t'] if week_pay_doc else 0) or 0

    if week_ago_revenue > 0:
        revenue_change = ((recent_revenue - week_ago_revenue) / week_ago_revenue * 100)
        if revenue_change < -10:
            alerts.append({
                'id': str(uuid.uuid4()),
                'type': 'revenue_drop',
                'severity': 'high',
                'title': 'Gelir Düşüşü',
                'message': f'Gelir geçen haftaya göre %{abs(revenue_change):.1f} düştü',
                'value': revenue_change,
                'created_at': datetime.now(UTC).isoformat()
            })

    # Low occupancy alert (above gather'dan geldi)
    if total_rooms > 0:
        occupancy_pct = (occupied_rooms / total_rooms * 100)
        if occupancy_pct < 50:
            alerts.append({
                'id': str(uuid.uuid4()),
                'type': 'low_occupancy',
                'severity': 'medium',
                'title': 'Düşük Doluluk',
                'message': f'Doluluk oranı %{occupancy_pct:.1f} - Hedefin altında',
                'value': occupancy_pct,
                'created_at': datetime.now(UTC).isoformat()
            })

    # Overbooking risk (above gather'dan geldi)
    if arrivals_tomorrow > available_rooms:
        alerts.append({
            'id': str(uuid.uuid4()),
            'type': 'overbooking_risk',
            'severity': 'urgent',
            'title': 'Overbooking Riski',
            'message': f'Yarın {arrivals_tomorrow} giriş var, sadece {available_rooms} oda hazır',
            'value': arrivals_tomorrow - available_rooms,
            'created_at': datetime.now(UTC).isoformat()
        })

    # Maintenance backlog (above gather'dan geldi)
    if pending_maintenance > 5:
        alerts.append({
            'id': str(uuid.uuid4()),
            'type': 'maintenance_backlog',
            'severity': 'medium',
            'title': 'Bakım Birikiyor',
            'message': f'{pending_maintenance} acil bakım görevi bekliyor',
            'value': pending_maintenance,
            'created_at': datetime.now(UTC).isoformat()
        })

    # Cash flow warning (bank_accounts find + expense_doc aggregate'tan)
    total_cash = sum(account.get('balance', 0) for account in bank_accounts)
    monthly_costs = (expense_doc[0]['t'] if expense_doc else 0) or 0

    if monthly_costs > 0 and total_cash < monthly_costs * 0.5:
        alerts.append({
            'id': str(uuid.uuid4()),
            'type': 'cash_flow_warning',
            'severity': 'high',
            'title': 'Nakit Akışı Uyarısı',
            'message': f'Nakit pozisyon aylık giderlerin %{(total_cash/monthly_costs*100):.0f}\'i seviyesinde',
            'value': total_cash,
            'created_at': datetime.now(UTC).isoformat()
        })

    # Sort by severity
    severity_order = {'urgent': 0, 'high': 1, 'medium': 2, 'low': 3}
    alerts.sort(key=lambda x: severity_order.get(x['severity'], 3))

    return {
        'alerts': alerts,
        'count': len(alerts),
        'urgent_count': len([a for a in alerts if a['severity'] == 'urgent']),
        'high_count': len([a for a in alerts if a['severity'] == 'high'])
    }
# ── GET /executive/comp-set-summary ──
@router.get("/executive/comp-set-summary")
async def get_executive_comp_set_summary(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get comp-set vs hotel summary for executives (manual/mock comp-set data)."""
    current_user = await get_current_user(credentials)

    # Fetch hotel-level KPIs using existing snapshot logic for consistency
    today = datetime.now(UTC).date().isoformat()

    # 4 bagimsiz read paralel — N+1 fix. Bookings sum Mongo aggregate ile (truncation yok).
    thirty_days_ago = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    total_rooms, occupied_rooms, booking_agg, comp_stats = await asyncio.gather(
        db.rooms.count_documents({'tenant_id': current_user.tenant_id}),
        db.rooms.count_documents({'tenant_id': current_user.tenant_id, 'status': 'occupied'}),
        db.bookings.aggregate([
            {'$match': {
                'tenant_id': current_user.tenant_id,
                'status': {'$in': ['checked_in', 'checked_out']},
                'check_in': {'$gte': thirty_days_ago},
            }},
            {'$group': {
                '_id': None,
                'rev': {'$sum': {'$ifNull': ['$total_amount', 0]}},
                'nights': {'$sum': {'$max': [1, {'$ifNull': ['$nights', 1]}]}},
            }},
        ]).to_list(1),
        db.comp_set_stats.find(
            {'tenant_id': current_user.tenant_id},
            {'_id': 0},
        ).sort('period_start', -1).limit(1).to_list(1),
    )
    total_rooms = total_rooms or 0
    hotel_occupancy = (occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0

    total_revenue = (booking_agg[0]['rev'] if booking_agg else 0) or 0
    room_nights = (booking_agg[0]['nights'] if booking_agg else 0) or 0

    hotel_adr = (total_revenue / room_nights) if room_nights > 0 else 0
    hotel_revpar = (total_revenue / (total_rooms * 30)) if total_rooms > 0 else 0

    if comp_stats:
        comp = comp_stats[0]
        comp_occ = comp.get('occupancy', 0)
        comp_adr = comp.get('adr', 0)
        comp_revpar = comp.get('revpar', 0)
    else:
        # Fallback: simple heuristic based on hotel performance
        comp_occ = max(0, min(100, hotel_occupancy * 0.95))
        comp_adr = hotel_adr * 0.97 if hotel_adr else 0
        comp_revpar = hotel_revpar * 0.96 if hotel_revpar else 0

    def safe_index(hotel_val: float, comp_val: float) -> float:
        if comp_val <= 0:
            return 100.0
        return round((hotel_val / comp_val) * 100, 1)

    occ_index = safe_index(hotel_occupancy, comp_occ)
    adr_index = safe_index(hotel_adr, comp_adr)
    revpar_index = safe_index(hotel_revpar, comp_revpar)

    return {
        'period': today,
        'hotel': {
            'occupancy': round(hotel_occupancy, 1),
            'adr': round(hotel_adr, 2),
            'revpar': round(hotel_revpar, 2)
        },
        'comp_set': {
            'occupancy': round(comp_occ, 1),
            'adr': round(comp_adr, 2),
            'revpar': round(comp_revpar, 2)
        },
        'indexes': {
            'occ_index': occ_index,
            'adr_index': adr_index,
            'revpar_index': revpar_index
        }
    }
# ── GET /executive/budget-config ──
@router.get("/executive/budget-config")
async def get_executive_budget_config(
    year: int | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get or initialize budget configuration for a given year (manual input ready)."""
    current_user = await get_current_user(credentials)
    target_year = year or datetime.now(UTC).year

    existing = await db.executive_budgets.find_one(
        {'tenant_id': current_user.tenant_id, 'year': target_year},
        {'_id': 0}
    )
    if existing:
        return existing

    # Default empty config with 12 months
    default_months = [
        {
            'month': m,
            'occ_target': 0.0,
            'adr_target': 0.0,
            'rev_target': 0.0,
        }
        for m in range(1, 13)
    ]

    return {
        'tenant_id': current_user.tenant_id,
        'year': target_year,
        'currency': 'TRY',
        'months': default_months,
    }
# ── PUT /executive/budget-config ──
@router.put("/executive/budget-config")
async def upsert_executive_budget_config(
    config: BudgetConfig,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_budget_config")),  # v88 DW
):
    """Create or update annual budget configuration for the current tenant."""
    current_user = await get_current_user(credentials)
    doc = config.dict()
    doc['tenant_id'] = current_user.tenant_id

    await db.executive_budgets.update_one(
        {'tenant_id': current_user.tenant_id, 'year': config.year},
        {'$set': doc},
        upsert=True,
    )
    return {'status': 'ok'}
# ── GET /executive/budget-overview ──
@router.get("/executive/budget-overview")
async def get_executive_budget_overview(
    year: int | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Return budget vs actual overview for the selected year (simple heuristic actuals)."""
    current_user = await get_current_user(credentials)
    target_year = year or datetime.now(UTC).year

    # Load budget config (or defaults)
    config = await db.executive_budgets.find_one(
        {'tenant_id': current_user.tenant_id, 'year': target_year},
        {'_id': 0}
    )

    if not config:
        # Reuse the same default as get_executive_budget_config
        config = await get_executive_budget_config(year=target_year, credentials=credentials)

    # Compute simple monthly actuals based on bookings
    months_actual = {m: {'rev_actual': 0.0, 'occ_actual': 0.0, 'adr_actual': 0.0} for m in range(1, 13)}

    # Pre-calc total rooms
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id}) or 0

    # Fetch bookings for the year
    year_start = datetime(target_year, 1, 1, tzinfo=UTC).isoformat()
    year_end = datetime(target_year + 1, 1, 1, tzinfo=UTC).isoformat()

    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['checked_in', 'checked_out']},
        'check_in': {'$gte': year_start, '$lt': year_end},
    }, {'_id': 0}):
        check_in_str = booking.get('check_in')
        if not check_in_str:
            continue
        try:
            check_in_dt = datetime.fromisoformat(check_in_str)
        except Exception:
            continue
        if check_in_dt.year != target_year:
            continue
        month = check_in_dt.month
        total_amount = float(booking.get('total_amount', 0.0) or 0.0)
        nights = max(1, int(booking.get('nights') or 1))

        ma = months_actual[month]
        ma['rev_actual'] += total_amount
        ma['occ_actual'] += nights

    # Derive ADR and rough occupancy per month
    for m in range(1, 13):
        ma = months_actual[m]
        if ma['occ_actual'] > 0:
            ma['adr_actual'] = ma['rev_actual'] / ma['occ_actual']
        # Rough occupancy: occupied room nights / (total_rooms * days_in_month)
        try:
            days_in_month = (datetime(target_year + (1 if m == 12 else 0), (m % 12) + 1, 1, tzinfo=UTC) - datetime(target_year, m, 1, tzinfo=UTC)).days
        except Exception:
            days_in_month = 30
        if total_rooms > 0 and days_in_month > 0:
            ma['occ_actual'] = (ma['occ_actual'] / (total_rooms * days_in_month)) * 100

    # Merge budget + actuals
    months_output = []
    totals = {
        'rev_target': 0.0,
        'rev_actual': 0.0,
        'occ_target': 0.0,
        'occ_actual': 0.0,
        'adr_target': 0.0,
        'adr_actual': 0.0,
    }

    for month_cfg in config['months']:
        m = month_cfg['month']
        ma = months_actual.get(m, {})
        month_entry = {
            'month': m,
            'occ_target': float(month_cfg.get('occ_target', 0.0)),
            'occ_actual': round(float(ma.get('occ_actual', 0.0)), 1),
            'adr_target': float(month_cfg.get('adr_target', 0.0)),
            'adr_actual': round(float(ma.get('adr_actual', 0.0)), 1),
            'rev_target': float(month_cfg.get('rev_target', 0.0)),
            'rev_actual': round(float(ma.get('rev_actual', 0.0)), 2),
        }
        months_output.append(month_entry)

        totals['rev_target'] += month_entry['rev_target']
        totals['rev_actual'] += month_entry['rev_actual']
        totals['occ_target'] += month_entry['occ_target']
        totals['occ_actual'] += month_entry['occ_actual']
        totals['adr_target'] += month_entry['adr_target']
        totals['adr_actual'] += month_entry['adr_actual']

    def variance_pct(target: float, actual: float) -> float:
        if target == 0:
            return 0.0
        return round(((actual - target) / target) * 100, 1)

    totals_output = {
        'rev_target': round(totals['rev_target'], 2),
        'rev_actual': round(totals['rev_actual'], 2),
        'rev_variance_pct': variance_pct(totals['rev_target'], totals['rev_actual']),
        'occ_target': round(totals['occ_target'] / 12, 1) if totals['occ_target'] else 0.0,
        'occ_actual': round(totals['occ_actual'] / 12, 1) if totals['occ_actual'] else 0.0,
        'adr_target': round(totals['adr_target'] / 12, 1) if totals['adr_target'] else 0.0,
        'adr_actual': round(totals['adr_actual'] / 12, 1) if totals['adr_actual'] else 0.0,
    }

    return {
        'year': target_year,
        'currency': config.get('currency', 'TRY'),
        'months': months_output,
        'totals': totals_output,
    }
# ── GET /executive/daily-summary ──
@router.get("/executive/daily-summary")
@cached(ttl=180, key_prefix="executive_daily_summary", role_aware=True)
async def get_executive_daily_summary(
    date: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """
    Get daily summary for executives
    Bookings, revenue, cancellations, complaints, key metrics

    NOT: cache anahtarinin tenant'a duyarli olabilmesi icin
    `current_user`'i Depends ile dogrudan aliyoruz (credentials'tan
    extract edilen tenant cache anahtarina yansimazdi - cross-tenant
    cache sizintisi riski).
    """
    target_date = date if date else datetime.now(UTC).date().isoformat()
    tid = current_user.tenant_id

    # Tum bagimsiz sorgular paralel: 6 count + 1 revenue aggregate
    (
        new_bookings,
        checkins,
        checkouts,
        cancellations,
        revenue_doc,
        complaints,
        incidents,
    ) = await asyncio.gather(
        db.bookings.count_documents({'tenant_id': tid, 'created_at': {'$gte': target_date}}),
        db.bookings.count_documents({'tenant_id': tid, 'check_in': target_date, 'status': 'checked_in'}),
        db.bookings.count_documents({'tenant_id': tid, 'check_out': target_date, 'status': 'checked_out'}),
        db.bookings.count_documents({'tenant_id': tid, 'status': 'cancelled', 'updated_at': {'$gte': target_date}}),
        db.payments.aggregate([
            {'$match': {'tenant_id': tid, 'payment_date': {'$gte': target_date}}},
            {'$group': {'_id': None, 'total': {'$sum': '$amount'}}},
        ]).to_list(1),
        db.feedback.count_documents({
            'tenant_id': tid,
            'rating': {'$lte': 2},
            'created_at': {'$gte': target_date},
        }),
        db.incidents.count_documents({'tenant_id': tid, 'incident_date': target_date}),
    )

    revenue = (revenue_doc[0]['total'] if revenue_doc else 0) or 0

    return {
        'date': target_date,
        'summary': {
            'new_bookings': new_bookings,
            'check_ins': checkins,
            'check_outs': checkouts,
            'cancellations': cancellations,
            'revenue': round(revenue, 2),
            'complaints': complaints,
            'incidents': incidents
        },
        'highlights': {
            'cancellation_rate': round((cancellations / new_bookings * 100) if new_bookings > 0 else 0, 1),
            'avg_revenue_per_booking': round((revenue / checkins) if checkins > 0 else 0, 2)
        }
    }
