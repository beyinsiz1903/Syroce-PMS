"""Auto-split from reports.py — backward-compatible sub-router."""
import asyncio
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

security = HTTPBearer()

from core.database import db
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import User

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

@sub_router.get("/reports/official-guest-list")
async def get_official_guest_list(
    date: str | None = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
):
    """Resmi misafir listesi (Maliye / resmi denetimler için).

    Verilen tarihte (veya bugün) otelde konaklayan tüm misafirleri ve konaklama
    bilgilerini döner. Check-in <= tarih <= Check-out koşulunu kullanır.
    """
    target_date = datetime.now(UTC).date() if not date else datetime.fromisoformat(date).date()
    has_pii = _user_has_pii_access(current_user)

    # Tarihi gün başlangıç/bitiş aralığına çevir
    day_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=UTC)
    day_end = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=UTC)

    # İlgili tarihte otelde konaklayan rezervasyonlar
    bookings_cursor = db.bookings.find(
        {
            'tenant_id': current_user.tenant_id,
            'check_in': {'$lte': day_end.isoformat()},
            'check_out': {'$gte': day_start.isoformat()},
            'status': {'$nin': ['cancelled', 'no_show']},
        },
        {
            '_id': 0,
            'id': 1,
            'guest_id': 1,
            'guest_name': 1,
            'room_number': 1,
            'room_id': 1,
            'check_in': 1,
            'check_out': 1,
            'adults': 1,
            'children': 1,
            'total_amount': 1,
            'billing_tax_number': 1,
            'billing_address': 1,
            'company_id': 1,
            'market_segment': 1,
        },
    )

    bookings = await bookings_cursor.to_list(5000)

    # Misafir bilgilerini toplamak için guest_id set'i
    guest_ids = {b['guest_id'] for b in bookings if b.get('guest_id')}

    guests_by_id = {}
    if guest_ids:
        guests_cursor = db.guests.find(
            {'tenant_id': current_user.tenant_id, 'id': {'$in': list(guest_ids)}},
            {
                '_id': 0,
                'id': 1,
                'first_name': 1,
                'last_name': 1,
                'national_id': 1,
                'passport_number': 1,
                'country': 1,
                'city': 1,
                'date_of_birth': 1,
            },
        )
        guest_docs = await guests_cursor.to_list(5000)
        guests_by_id = {g['id']: g for g in guest_docs}

    rows = []
    for b in bookings:
        g = guests_by_id.get(b.get('guest_id'))

        full_name = b.get('guest_name')
        if not full_name and g:
            full_name = f"{g.get('first_name', '')} {g.get('last_name', '')}".strip()

        row = {
            'booking_id': b.get('id'),
            'guest_name': full_name,
            'national_id': _mask_pii((g or {}).get('national_id')) if not has_pii else (g or {}).get('national_id'),
            'passport_number': _mask_pii((g or {}).get('passport_number')) if not has_pii else (g or {}).get('passport_number'),
            'country': (g or {}).get('country'),
            'city': (g or {}).get('city'),
            'date_of_birth': (g or {}).get('date_of_birth'),
            'room_number': b.get('room_number'),
            'check_in': b.get('check_in'),
            'check_out': b.get('check_out'),
            'adults': b.get('adults', 1),
            'children': b.get('children', 0),
            'total_amount': b.get('total_amount', 0.0),
            'billing_tax_number': b.get('billing_tax_number'),
            'billing_address': b.get('billing_address'),
            'company_id': b.get('company_id'),
            'market_segment': b.get('market_segment'),
        }

        rows.append(row)

    return {
        'date': target_date.isoformat(),
        'count': len(rows),
        'rows': rows,
    }



def _user_has_pii_access(user) -> bool:
    """KVKK PII gate: TCKN / pasaport sadece yöneticilere açıktır.

    - Admin / Super-Admin / Manager / General Manager rolleri: tam erişim.
    - Diğer roller: yalnızca `granted_permissions` içinde "view_guest_pii"
      anahtarı bulunan kullanıcılar PII alanlarını görebilir.
    """
    role = getattr(user, 'role', None)
    role_str = getattr(role, 'value', None) or str(role or '')
    if role_str in ('admin', 'super_admin', 'manager', 'general_manager'):
        return True
    granted = getattr(user, 'granted_permissions', None) or []
    return 'view_guest_pii' in granted


def _mask_pii(value):
    if not value:
        return value
    s = str(value)
    if len(s) <= 4:
        return '*' * len(s)
    return s[:2] + '*' * (len(s) - 4) + s[-2:]


@sub_router.get("/reports/basic-dashboard")
async def get_basic_reports_dashboard(
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("basic_reporting")),
):
    """
    Temel Raporlar Dashboard - OPTIMIZED: Batch queries + cache (Tur 28).
    """
    has_pii = _user_has_pii_access(current_user)
    return await _basic_dashboard_impl(current_user, has_pii)


@cached(ttl=120, key_prefix="reports:basic_dashboard", role_aware=True)
async def _basic_dashboard_impl(current_user: User, has_pii: bool):
    today = datetime.now(UTC)
    today_start = today.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today.replace(hour=23, minute=59, second=59)
    tenant_id = current_user.tenant_id
    month_start = (today - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = (today - timedelta(days=7)).replace(hour=0, minute=0, second=0, microsecond=0)
    trend_start = (today - timedelta(days=29)).replace(hour=0, minute=0, second=0, microsecond=0)

    # ALL queries in parallel
    async def get_fnb():
        try:
            orders = await db.pos_orders.find({'tenant_id': tenant_id, 'created_at': {'$gte': today_start.isoformat(), '$lte': today_end.isoformat()}}, {'_id': 0, 'total_amount': 1}).to_list(1000)
            return sum(o.get('total_amount', 0) for o in orders)
        except Exception:
            return 0.0

    results = await asyncio.gather(
        db.rooms.find({'tenant_id': tenant_id}).to_list(1000),
        db.bookings.find({'tenant_id': tenant_id, '$or': [{'check_in': {'$gte': trend_start.isoformat(), '$lte': today_end.isoformat()}}, {'check_out': {'$gte': trend_start.isoformat(), '$lte': today_end.isoformat()}}, {'check_in': {'$lte': trend_start.isoformat()}, 'check_out': {'$gte': today_end.isoformat()}}]}, {'_id': 0, 'check_in': 1, 'check_out': 1, 'total_amount': 1, 'status': 1, 'booking_source': 1, 'room_type': 1, 'created_at': 1, 'guest_id': 1, 'guest_name': 1, 'guest_email': 1, 'guest_phone': 1, 'room_number': 1, 'nationality': 1, 'id_number': 1, 'passport_number': 1}).to_list(10000),
        db.bookings.count_documents({'tenant_id': tenant_id, 'status': 'checked_in'}),
        db.housekeeping_tasks.find({'tenant_id': tenant_id, 'created_at': {'$gte': (today - timedelta(days=7)).isoformat()}}).to_list(5000),
        db.maintenance_tasks.count_documents({'tenant_id': tenant_id, 'status': {'$in': ['open', 'in_progress', 'pending']}}),
        db.maintenance_tasks.count_documents({'tenant_id': tenant_id, 'status': 'completed', 'completed_at': {'$gte': month_start.isoformat()}}),
        db.invoices.count_documents({'tenant_id': tenant_id, 'payment_status': {'$in': ['pending', 'partial']}}),
        db.invoices.count_documents({'tenant_id': tenant_id, 'payment_status': 'paid', 'created_at': {'$gte': month_start.isoformat()}}),
        db.guests.find({'tenant_id': tenant_id}, {'_id': 0, 'id': 1, 'nationality': 1, 'country': 1}).to_list(5000),
        db.payments.find({'tenant_id': tenant_id, 'processed_at': {'$gte': month_start.isoformat()}}, {'_id': 0, 'amount': 1, 'method': 1, 'status': 1}).to_list(5000),
        db.bookings.find({'tenant_id': tenant_id, 'check_in': {'$gte': (today - timedelta(days=60)).replace(hour=0,minute=0,second=0,microsecond=0).isoformat(), '$lt': month_start.isoformat()}, 'status': {'$in': ['confirmed', 'checked_in', 'checked_out']}}, {'_id': 0, 'total_amount': 1, 'check_in': 1, 'check_out': 1}).to_list(10000),
        db.bookings.find({'tenant_id': tenant_id, 'check_in': {'$gte': (today - timedelta(days=365)).isoformat(), '$lt': (today - timedelta(days=335)).isoformat()}, 'status': {'$in': ['confirmed', 'checked_in', 'checked_out']}}, {'_id': 0, 'total_amount': 1, 'check_in': 1, 'check_out': 1}).to_list(10000),
        get_fnb(),
    )
    rooms, all_bk, in_house, hk_tasks, maint_open, maint_completed, pending_invoices, paid_invoices, all_guests, all_payments, prev_bookings, ly_bookings, fnb_revenue = results

    total_rooms = len(rooms)
    room_types = {}
    for r in rooms:
        rt = r.get('room_type', 'Standard')
        room_types[rt] = room_types.get(rt, 0) + 1

    room_status_counts = {'available': 0, 'occupied': 0, 'dirty': 0, 'maintenance': 0, 'out_of_order': 0}
    for r in rooms:
        st = r.get('current_status', r.get('status', 'available'))
        room_status_counts[st] = room_status_counts.get(st, room_status_counts.get('available', 0)) + 1

    ts_s, ts_e = today_start.isoformat(), today_end.isoformat()
    ms_s, ws_s = month_start.isoformat(), week_start.isoformat()
    occupied_today = arrivals = departures = no_shows = cancellations = today_revenue = 0
    recent_bookings = []; week_bookings = []; month_bookings = []; recent_guests_data = []
    ALL_REVENUE_STATUSES = ('confirmed', 'guaranteed', 'checked_in', 'checked_out')

    for bk in all_bk:
        ci, co, status = bk.get('check_in',''), bk.get('check_out',''), bk.get('status','')
        amt = bk.get('total_amount', 0) or 0
        created = bk.get('created_at', '')
        # P0 fix: Tür 28 — occupied_today STAY-DATE bazlı (overlap),
        # status'u checked_in'e kısıtlamak günün gerçek doluluğunu sıfırlıyordu.
        if status in ALL_REVENUE_STATUSES and ci <= ts_e and co >= ts_s: occupied_today += 1
        if ci >= ts_s and ci <= ts_e and status in ('confirmed','guaranteed','checked_in'): arrivals += 1
        if co >= ts_s and co <= ts_e: departures += 1
        if ci >= ts_s and ci <= ts_e and status == 'no_show': no_shows += 1
        if status == 'cancelled' and created >= ts_s and created <= ts_e: cancellations += 1
        if ci >= ts_s and ci <= ts_e: today_revenue += amt
        if created >= ms_s: recent_bookings.append(bk)
        if ci >= ws_s and status in ALL_REVENUE_STATUSES: week_bookings.append(bk)
        # P1 fix: ay listesi — cancelled / no_show da dahil edilmeli; aksi
        # halde "No-Show & İptaller" sekmesi recent_guests_data filtresinden
        # geçemediği için boş görünür.
        if ci >= ms_s and status in (*ALL_REVENUE_STATUSES, 'cancelled', 'no_show'):
            if status in ALL_REVENUE_STATUSES:
                month_bookings.append(bk)
            recent_guests_data.append({
                'guest_name': bk.get('guest_name'),
                'guest_email': bk.get('guest_email'),
                'guest_phone': bk.get('guest_phone'),
                'room_number': bk.get('room_number'),
                'room_type': bk.get('room_type'),
                'check_in': ci,
                'check_out': co,
                'total_amount': amt,
                'status': status,
                'nationality': bk.get('nationality'),
                'id_number': bk.get('id_number') if has_pii else _mask_pii(bk.get('id_number')),
                'passport_number': bk.get('passport_number') if has_pii else _mask_pii(bk.get('passport_number')),
                'booking_source': bk.get('booking_source'),
            })

    occupancy_pct = round(min((occupied_today / total_rooms * 100), 100.0), 1) if total_rooms > 0 else 0
    adr = round(today_revenue / occupied_today, 2) if occupied_today > 0 else 0
    revpar = round(today_revenue / total_rooms, 2) if total_rooms > 0 else 0

    # Compute 30-day trends from batch data (NO extra queries)
    occupancy_trend = []; revenue_trend = []
    for i in range(29, -1, -1):
        d = today - timedelta(days=i)
        ds = d.replace(hour=0,minute=0,second=0,microsecond=0).isoformat()
        de = d.replace(hour=23,minute=59,second=59).isoformat()
        occ_c = 0; day_r = 0
        for bk in all_bk:
            ci, co, st2 = bk.get('check_in',''), bk.get('check_out',''), bk.get('status','')
            if st2 in ('checked_in','checked_out','confirmed','guaranteed') and ci <= de and co >= ds: occ_c += 1
            if st2 in ('confirmed','guaranteed','checked_in','checked_out') and ci >= ds and ci <= de: day_r += bk.get('total_amount',0) or 0
        # Cap %100 (overbooking veya cakisma durumlarinda)
        _occ_pct = round((occ_c/total_rooms*100),1) if total_rooms>0 else 0
        occupancy_trend.append({'date': d.strftime('%Y-%m-%d'), 'label': d.strftime('%d %b'), 'occupancy': min(_occ_pct, 100.0), 'rooms_occupied': occ_c})
        revenue_trend.append({'date': d.strftime('%Y-%m-%d'), 'label': d.strftime('%d %b'), 'revenue': round(day_r, 2)})

    hk_completed = len([t for t in hk_tasks if t.get('status') == 'completed'])
    hk_pending = len([t for t in hk_tasks if t.get('status') in ['pending', 'assigned']])
    hk_in_progress = len([t for t in hk_tasks if t.get('status') == 'in_progress'])

    source_distribution = {}; source_revenue = {}
    for bk in recent_bookings:
        src = bk.get('booking_source', 'direct')
        source_distribution[src] = source_distribution.get(src, 0) + 1
        source_revenue[src] = source_revenue.get(src, 0) + (bk.get('total_amount', 0) or 0)

    week_revenue = sum(b.get('total_amount', 0) or 0 for b in week_bookings)
    month_revenue = sum(b.get('total_amount', 0) or 0 for b in month_bookings)

    # P1 fix: Milliyet dağılımı tüm zamanlar yerine SADECE bu ayın
    # rezervasyonlarından (month_bookings) türetilir. Booking üstünde
    # nationality yoksa guest dokümanından lookup yapılır.
    guests_by_id = {g.get('id'): g for g in all_guests if g.get('id')}
    country_dist = {}
    for bk in month_bookings:
        c = bk.get('nationality')
        if not c:
            g = guests_by_id.get(bk.get('guest_id'))
            if g:
                c = g.get('nationality') or g.get('country')
        c = c or 'Belirtilmemiş'
        country_dist[c] = country_dist.get(c, 0) + 1

    room_type_occ = {}
    for rt_name, rt_count in room_types.items():
        rt_rooms = [r for r in rooms if r.get('room_type') == rt_name]
        rt_occ = len([r for r in rt_rooms if r.get('current_status') == 'occupied'])
        room_type_occ[rt_name] = {'total': rt_count, 'occupied': rt_occ, 'occupancy': round((rt_occ/rt_count*100),1) if rt_count>0 else 0, 'revenue': 0}
    for bk in recent_bookings:
        rt = bk.get('room_type', 'Standard')
        if rt in room_type_occ: room_type_occ[rt]['revenue'] += bk.get('total_amount', 0) or 0
    for rt in room_type_occ: room_type_occ[rt]['revenue'] = round(room_type_occ[rt]['revenue'], 2)

    payment_methods = {}; total_paid = 0
    for p in all_payments:
        method = p.get('method', 'other'); amt = p.get('amount', 0) or 0
        payment_methods[method] = payment_methods.get(method, 0) + amt
        if p.get('status') == 'paid': total_paid += amt
    payment_methods = {k: round(v, 2) for k, v in payment_methods.items()}

    # P1 fix: ADR — room_nights HER REZERVASYONUN GECE SAYISI toplamı
    # olmalı (rezervasyon adedi değil). (check_out - check_in).days; min 1.
    def _nights(b):
        try:
            ci_s, co_s = b.get('check_in', ''), b.get('check_out', '')
            if not ci_s or not co_s:
                return 1
            ci_d = datetime.fromisoformat(ci_s.replace('Z', '+00:00'))
            co_d = datetime.fromisoformat(co_s.replace('Z', '+00:00'))
            return max(1, (co_d.date() - ci_d.date()).days)
        except Exception:
            return 1

    prev_revenue = sum(b.get('total_amount', 0) or 0 for b in prev_bookings)
    prev_room_nights = sum(_nights(b) for b in prev_bookings)
    prev_adr = round(prev_revenue / prev_room_nights, 2) if prev_room_nights > 0 else 0
    ly_revenue = sum(b.get('total_amount', 0) or 0 for b in ly_bookings)

    return {
        'date': today.strftime('%Y-%m-%d'),
        'summary': {
            'total_rooms': total_rooms,
            'occupied_rooms': occupied_today,
            'occupancy_percentage': occupancy_pct,
            'arrivals': arrivals,
            'departures': departures,
            'in_house': in_house,
            'no_shows': no_shows,
            'cancellations': cancellations,
            'today_revenue': round(today_revenue, 2),
            'adr': adr,
            'revpar': revpar,
            'fnb_revenue': round(fnb_revenue, 2),
        },
        'period_comparison': {
            'week_revenue': round(week_revenue, 2),
            'week_bookings': len(week_bookings),
            'month_revenue': round(month_revenue, 2),
            'month_bookings': len(month_bookings),
            'prev_month_revenue': round(prev_revenue, 2),
            'prev_month_bookings': len(prev_bookings),
            'prev_month_adr': prev_adr,
            'last_year_revenue': round(ly_revenue, 2),
            'last_year_bookings': len(ly_bookings),
        },
        'occupancy_trend': occupancy_trend,
        'revenue_trend': revenue_trend,
        'room_status': room_status_counts,
        'room_types': room_types,
        'room_type_occupancy': room_type_occ,
        'booking_sources': {
            'distribution': source_distribution,
            'revenue': {k: round(v, 2) for k, v in source_revenue.items()}
        },
        'country_distribution': country_dist,
        'payments': {
            'by_method': payment_methods,
            'total_paid': round(total_paid, 2),
            'total_pending': pending_invoices,
        },
        # P1 fix: Polis bildirimi ve maliye listesinde 100 kayıt yetersiz —
        # tüm aylık misafir listesi (cap 5000) döndürülür; frontend tarafı
        # sayfalar / arama ile sınırlı gösterim yapar.
        'guest_list': recent_guests_data[:5000],
        'housekeeping': {
            'completed': hk_completed,
            'pending': hk_pending,
            'in_progress': hk_in_progress,
            'total_week': len(hk_tasks)
        },
        'maintenance': {
            'open': maint_open,
            'completed_month': maint_completed
        },
        'finance': {
            'pending_invoices': pending_invoices,
            'paid_invoices_month': paid_invoices
        }
    }



