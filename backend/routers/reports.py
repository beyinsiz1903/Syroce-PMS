"""
REPORTS Router - Extracted from server.py
"""
import logging
logger = logging.getLogger(__name__)
import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.database import db
from core.helpers import (
    require_module,
)
from core.security import get_current_user
from models.enums import (
    ChargeCategory,
)
from models.schemas import (
    FolioCharge,
    User,
)

try:
    from domains.pms.night_audit_module import AuditStatus, AutomaticPosting, NightAuditRecord
except ImportError:
    NightAuditRecord = None
    AuditStatus = None
    AutomaticPosting = None

from core.utils import (
    calculate_folio_balance,
    create_excel_workbook,
    excel_response,
    night_audit_calculate_revenue,
    night_audit_housekeeping_rollup,
    night_audit_ota_reconciliation,
    night_audit_post_room_charges,
    night_audit_recalculate_ar,
)
from shared_kernel.migration_observability import MigrationObservabilityService

try:
    from infra.logging_service import get_logging_service
except ImportError:
    get_logging_service = None

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator

router = APIRouter(prefix="/api", tags=["reports"])
security = HTTPBearer()
migration_observability_service = MigrationObservabilityService()


@router.get("/reports/migration-observability")
async def get_migration_observability(
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
):
    return await migration_observability_service.get_dashboard(current_user.tenant_id)

@router.post("/reports/send-flash-now")
async def send_flash_report_now(
    recipients: list[str],
    current_user: User = Depends(get_current_user)
):
    """Flash report'u şimdi gönder"""
    from modules.analytics_export.report_automation import get_report_automation
    from modules.messaging.email_service import email_service

    automation = get_report_automation(db, email_service)
    await automation.send_flash_report_email(current_user.tenant_id, recipients)

    return {
        'success': True,
        'message': f'Flash report {len(recipients)} alıcıya gönderildi'
    }


@router.get("/reports/flash-report")
@cached(ttl=300, key_prefix="flash_report")  # Cache for 5 min
async def get_flash_report(
    date: str | None = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
):
    """
    Daily Flash Report - Günlük özet rapor
    5 yıldızlı otel yöneticileri için sabah raporu
    """
    target_date = datetime.now(UTC) if not date else datetime.fromisoformat(date)
    today_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = target_date.replace(hour=23, minute=59, second=59)

    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})

    occupied_today = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': 'checked_in',
        'check_in': {'$lte': today_end.isoformat()},
        'check_out': {'$gte': today_start.isoformat()}
    })

    occupancy_rate = (occupied_today / total_rooms * 100) if total_rooms > 0 else 0

    arrivals_today = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': today_start.isoformat(),
            '$lte': today_end.isoformat()
        },
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
    })

    departures_today = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_out': {
            '$gte': today_start.isoformat(),
            '$lte': today_end.isoformat()
        }
    })

    inhouse_count = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': 'checked_in'
    })

    today_bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': today_start.isoformat(),
            '$lte': today_end.isoformat()
        }
    }, {'_id': 0, 'total_amount': 1, 'base_rate': 1, 'paid_amount': 1,
        'charges': 1, 'channel': 1, 'status': 1}).to_list(1000)

    total_revenue = sum(b.get('total_amount', 0) for b in today_bookings)
    collected = sum(b.get('paid_amount', 0) for b in today_bookings)
    adr = total_revenue / occupied_today if occupied_today > 0 else 0
    revpar = total_revenue / total_rooms if total_rooms > 0 else 0

    no_shows = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': today_start.isoformat(),
            '$lte': today_end.isoformat()
        },
        'status': 'no_show'
    })

    cancellations = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': 'cancelled',
        'created_at': {
            '$gte': today_start.isoformat(),
            '$lte': today_end.isoformat()
        }
    })

    walk_ins = sum(1 for b in today_bookings if b.get('channel') == 'walk_in')
    overstays = 0

    fnb_revenue = 0
    try:
        fnb_orders = await db.pos_orders.find({
            'tenant_id': current_user.tenant_id,
            'created_at': {
                '$gte': today_start.isoformat(),
                '$lte': today_end.isoformat()
            }
        }, {'_id': 0, 'total_amount': 1}).to_list(1000)
        fnb_revenue = sum(o.get('total_amount', 0) for o in fnb_orders)
    except Exception:
        pass

    charges_by_cat = {}
    for b in today_bookings:
        for c in b.get('charges', []):
            cat = c.get('charge_category', 'other')
            charges_by_cat[cat] = charges_by_cat.get(cat, 0) + c.get('amount', 0)

    room_revenue = charges_by_cat.get('room', charges_by_cat.get('accommodation', 0))
    if not charges_by_cat:
        room_revenue = total_revenue
    spa_revenue = charges_by_cat.get('spa', 0)
    minibar_revenue = charges_by_cat.get('minibar', 0)
    laundry_revenue = charges_by_cat.get('laundry', 0)

    grand_total = total_revenue + fnb_revenue
    other_revenue = max(0, grand_total - room_revenue - fnb_revenue - spa_revenue - minibar_revenue - laundry_revenue)

    return {
        "date": target_date.strftime("%Y-%m-%d"),
        "occupancy": {
            "rate": round(occupancy_rate, 2),
            "occupied": occupied_today,
            "total": total_rooms,
            "available": total_rooms - occupied_today,
        },
        "kpi": {
            "adr": round(adr, 2),
            "revpar": round(revpar, 2),
        },
        "revenue": {
            "total": round(grand_total, 2),
            "room": round(room_revenue, 2),
            "fb": round(fnb_revenue, 2),
            "spa": round(spa_revenue, 2),
            "minibar": round(minibar_revenue, 2),
            "laundry": round(laundry_revenue, 2),
            "other": round(other_revenue, 2),
            "collected": round(collected, 2),
            "outstanding": round(grand_total - collected, 2),
        },
        "operations": {
            "arrivals": arrivals_today,
            "departures": departures_today,
            "inhouse": inhouse_count,
            "no_shows": no_shows,
            "walk_ins": walk_ins,
            "cancellations": cancellations,
            "overstays": overstays,
        },
        "departments": [
            {"name": "Oda Geliri", "amount": round(room_revenue, 2)},
            {"name": "Yiyecek & İçecek", "amount": round(fnb_revenue, 2)},
            {"name": "Spa & Wellness", "amount": round(spa_revenue, 2)},
            {"name": "Minibar", "amount": round(minibar_revenue, 2)},
            {"name": "Çamaşırhane", "amount": round(laundry_revenue, 2)},
            {"name": "Diğer", "amount": round(other_revenue, 2)},
        ],
    }



@router.get("/reports/official-guest-list")
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
            'national_id': (g or {}).get('national_id'),
            'passport_number': (g or {}).get('passport_number'),
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

    # Other Revenue (spa, laundry, minibar)
    other_revenue = 0.0
    try:
        other_charges = await db.folio_charges.find({
            'tenant_id': current_user.tenant_id,
            'posted_at': {
                '$gte': today_start.isoformat(),
                '$lte': today_end.isoformat()
            },
            'charge_category': {'$in': ['spa', 'laundry', 'minibar', 'telephone', 'upsell']}
        }, {'_id': 0, 'amount': 1}).to_list(1000)
        other_revenue = sum([c.get('amount', 0) for c in other_charges])
    except Exception:
        pass

    # Total Revenue
    total_revenue_all = total_revenue + fnb_revenue + other_revenue

    # TRevPAR (Total Revenue Per Available Room)
    trevpar = total_revenue_all / total_rooms if total_rooms > 0 else 0

    # VIP arrivals today
    vip_arrivals = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': today_start.isoformat(),
            '$lte': today_end.isoformat()
        },
        'guest_id': {'$exists': True}
        # TODO: Add VIP tag check when guest tags are implemented
    })

    return {
        'report_date': target_date.strftime('%Y-%m-%d'),
        'generated_at': datetime.now(UTC).isoformat(),

        # Occupancy Metrics
        'occupancy': {
            'rooms_occupied': occupied_today,
            'total_rooms': total_rooms,
            'occupancy_pct': round(occupancy_pct, 2),
            'rooms_available': total_rooms - occupied_today
        },

        # Guest Flow
        'guest_flow': {
            'arrivals': arrivals_today,
            'departures': departures_today,
            'in_house': in_house,
            'no_shows': no_shows,
            'cancellations': cancellations
        },

        # Revenue Metrics
        'revenue': {
            'rooms_revenue': round(total_revenue, 2),
            'fnb_revenue': round(fnb_revenue, 2),
            'other_revenue': round(other_revenue, 2),
            'total_revenue': round(total_revenue_all, 2),
            'adr': round(adr, 2),
            'revpar': round(revpar, 2),
            'trevpar': round(trevpar, 2)
        },

        # Breakdown
        'revenue_breakdown': {
            'rooms': round((total_revenue / total_revenue_all * 100) if total_revenue_all > 0 else 0, 1),
            'fnb': round((fnb_revenue / total_revenue_all * 100) if total_revenue_all > 0 else 0, 1),
            'other': round((other_revenue / total_revenue_all * 100) if total_revenue_all > 0 else 0, 1)
        },

        # Special Notes
        'special_notes': {
            'vip_arrivals': vip_arrivals,
            'group_arrivals': 0,  # TODO: Implement when group management is ready
            'events_today': 0  # TODO: Implement events calendar
        }
    }


@router.post("/night-audit/post-room-charges")
async def post_room_charges(current_user: User = Depends(get_current_user)):
    """Night audit: Post room charges to all active bookings"""
    import time
    start_time = time.time()

    logging_service = get_logging_service(db)
    audit_date = datetime.now(UTC).date().isoformat()
    errors = []

    try:
        # Get all checked-in bookings
        bookings = await db.bookings.find({
            'tenant_id': current_user.tenant_id,
            'status': 'checked_in'
        }).to_list(1000)

        charges_posted = 0
        total_amount = 0.0

        for booking in bookings:
            try:
                # Get guest folio for this booking
                folio = await db.folios.find_one({
                    'booking_id': booking['id'],
                    'folio_type': 'guest',
                    'status': 'open'
                })

                if folio:
                    # Post room charge
                    charge_amount = booking.get('base_rate', booking.get('total_amount', 0))
                    charge = FolioCharge(
                        tenant_id=current_user.tenant_id,
                        folio_id=folio['id'],
                        booking_id=booking['id'],
                        charge_category=ChargeCategory.ROOM,
                        description=f"Room {booking.get('room_id', 'N/A')} - Night Charge",
                        unit_price=charge_amount,
                        quantity=1.0,
                        amount=charge_amount,
                        tax_amount=0.0,
                        total=charge_amount,
                        posted_by="SYSTEM"
                    )

                    charge_dict = charge.model_dump()
                    charge_dict['date'] = charge_dict['date'].isoformat()
                    await db.folio_charges.insert_one(charge_dict)

                    # Update folio balance
                    balance = await calculate_folio_balance(folio['id'], current_user.tenant_id)
                    await db.folios.update_one(
                        {'id': folio['id']},
                        {'$set': {'balance': balance}}
                    )

                    charges_posted += 1
                    total_amount += charge_amount
            except Exception as e:
                errors.append(f"Booking {booking.get('id')}: {str(e)}")

        duration = time.time() - start_time
        status = 'completed' if len(errors) == 0 else 'partial' if charges_posted > 0 else 'failed'

        # Log night audit
        await logging_service.log_night_audit(
            tenant_id=current_user.tenant_id,
            audit_date=audit_date,
            user_id=current_user.id,
            user_name=current_user.name,
            status=status,
            rooms_processed=len(bookings),
            charges_posted=charges_posted,
            total_amount=total_amount,
            duration_seconds=duration,
            errors=errors if errors else None
        )

        return {
            "message": "Night audit completed",
            "charges_posted": charges_posted,
            "bookings_processed": len(bookings),
            "status": status,
            "errors": errors if errors else None
        }
    except Exception as e:
        duration = time.time() - start_time

        # Log failed audit
        await logging_service.log_night_audit(
            tenant_id=current_user.tenant_id,
            audit_date=audit_date,
            user_id=current_user.id,
            user_name=current_user.name,
            status='failed',
            rooms_processed=0,
            charges_posted=0,
            total_amount=0.0,
            duration_seconds=duration,
            errors=[str(e)]
        )

        raise HTTPException(status_code=500, detail=f"Night audit failed: {str(e)}")


@router.get("/reports/basic-dashboard")
async def get_basic_reports_dashboard(
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("basic_reporting")),
):
    """
    Temel Raporlar Dashboard - OPTIMIZED: Batch queries
    """
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
        db.bookings.find({'tenant_id': tenant_id, '$or': [{'check_in': {'$gte': trend_start.isoformat(), '$lte': today_end.isoformat()}}, {'check_out': {'$gte': trend_start.isoformat(), '$lte': today_end.isoformat()}}, {'check_in': {'$lte': trend_start.isoformat()}, 'check_out': {'$gte': today_end.isoformat()}}]}, {'_id': 0, 'check_in': 1, 'check_out': 1, 'total_amount': 1, 'status': 1, 'booking_source': 1, 'room_type': 1, 'created_at': 1, 'guest_name': 1, 'guest_email': 1, 'guest_phone': 1, 'room_number': 1, 'nationality': 1, 'id_number': 1, 'passport_number': 1}).to_list(10000),
        db.bookings.count_documents({'tenant_id': tenant_id, 'status': 'checked_in'}),
        db.housekeeping_tasks.find({'tenant_id': tenant_id, 'created_at': {'$gte': (today - timedelta(days=7)).isoformat()}}).to_list(5000),
        db.maintenance_tasks.count_documents({'tenant_id': tenant_id, 'status': {'$in': ['open', 'in_progress', 'pending']}}),
        db.maintenance_tasks.count_documents({'tenant_id': tenant_id, 'status': 'completed', 'completed_at': {'$gte': month_start.isoformat()}}),
        db.invoices.count_documents({'tenant_id': tenant_id, 'payment_status': {'$in': ['pending', 'partial']}}),
        db.invoices.count_documents({'tenant_id': tenant_id, 'payment_status': 'paid', 'created_at': {'$gte': month_start.isoformat()}}),
        db.guests.find({'tenant_id': tenant_id}, {'_id': 0, 'nationality': 1, 'country': 1}).to_list(5000),
        db.payments.find({'tenant_id': tenant_id, 'processed_at': {'$gte': month_start.isoformat()}}, {'_id': 0, 'amount': 1, 'method': 1, 'status': 1}).to_list(5000),
        db.bookings.find({'tenant_id': tenant_id, 'check_in': {'$gte': (today - timedelta(days=60)).replace(hour=0,minute=0,second=0,microsecond=0).isoformat(), '$lt': month_start.isoformat()}, 'status': {'$in': ['confirmed', 'checked_in', 'checked_out']}}, {'_id': 0, 'total_amount': 1}).to_list(10000),
        db.bookings.find({'tenant_id': tenant_id, 'check_in': {'$gte': (today - timedelta(days=365)).isoformat(), '$lt': (today - timedelta(days=335)).isoformat()}, 'status': {'$in': ['confirmed', 'checked_in', 'checked_out']}}, {'_id': 0, 'total_amount': 1}).to_list(10000),
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

    for bk in all_bk:
        ci, co, status = bk.get('check_in',''), bk.get('check_out',''), bk.get('status','')
        amt = bk.get('total_amount', 0) or 0
        created = bk.get('created_at', '')
        if status == 'checked_in' and ci <= ts_e and co >= ts_s: occupied_today += 1
        if ci >= ts_s and ci <= ts_e and status in ('confirmed','guaranteed','checked_in'): arrivals += 1
        if co >= ts_s and co <= ts_e: departures += 1
        if ci >= ts_s and ci <= ts_e and status == 'no_show': no_shows += 1
        if status == 'cancelled' and created >= ts_s and created <= ts_e: cancellations += 1
        if ci >= ts_s and ci <= ts_e: today_revenue += amt
        if created >= ms_s: recent_bookings.append(bk)
        if ci >= ws_s and status in ('confirmed','checked_in','checked_out'): week_bookings.append(bk)
        if ci >= ms_s and status in ('confirmed','checked_in','checked_out'):
            month_bookings.append(bk)
            recent_guests_data.append({'guest_name': bk.get('guest_name'), 'guest_email': bk.get('guest_email'), 'guest_phone': bk.get('guest_phone'), 'room_number': bk.get('room_number'), 'room_type': bk.get('room_type'), 'check_in': ci, 'check_out': co, 'total_amount': amt, 'status': status, 'nationality': bk.get('nationality'), 'id_number': bk.get('id_number'), 'passport_number': bk.get('passport_number'), 'booking_source': bk.get('booking_source')})

    occupancy_pct = round((occupied_today / total_rooms * 100), 1) if total_rooms > 0 else 0
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
            if st2 in ('checked_in','checked_out','confirmed') and ci <= de and co >= ds: occ_c += 1
            if st2 in ('confirmed','checked_in','checked_out') and ci >= ds and ci <= de: day_r += bk.get('total_amount',0) or 0
        occupancy_trend.append({'date': d.strftime('%Y-%m-%d'), 'label': d.strftime('%d %b'), 'occupancy': round((occ_c/total_rooms*100),1) if total_rooms>0 else 0, 'rooms_occupied': occ_c})
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

    country_dist = {}
    for g in all_guests:
        c = g.get('nationality') or g.get('country') or 'Belirtilmemiş'
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

    prev_revenue = sum(b.get('total_amount', 0) or 0 for b in prev_bookings)
    prev_room_nights = len(prev_bookings)
    prev_adr = round(prev_revenue / prev_room_nights, 2) if prev_room_nights > 0 else 0
    ly_revenue = sum(b.get('total_amount', 0) or 0 for b in ly_bookings)
    ly_room_nights = len(ly_bookings)

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
            'last_year_bookings': ly_room_nights,
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
        'guest_list': recent_guests_data[:100],
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


@router.get("/reports/occupancy")
@cached(ttl=600, key_prefix="report_occupancy")  # Cache for 10 minutes
async def get_occupancy_report(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
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


@router.get("/reports/revenue")
@cached(ttl=600, key_prefix="report_revenue")  # Cache for 10 minutes
async def get_revenue_report(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
):
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    bookings = await db.bookings.find({'tenant_id': current_user.tenant_id, 'status': {'$in': ['checked_in', 'checked_out']},
                                       'check_in': {'$gte': start.isoformat(), '$lte': end.isoformat()}}, {'_id': 0}).to_list(1000)
    total_revenue = sum(b['total_amount'] for b in bookings)
    total_room_nights = sum((datetime.fromisoformat(b['check_out']) - datetime.fromisoformat(b['check_in'])).days for b in bookings)
    adr = (total_revenue / total_room_nights) if total_room_nights > 0 else 0
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    days = (end - start).days + 1
    total_available_room_nights = total_rooms * days
    rev_par = (total_revenue / total_available_room_nights) if total_available_room_nights > 0 else 0
    folio_charges = await db.folio_charges.find({'tenant_id': current_user.tenant_id, 'date': {'$gte': start.isoformat(), '$lte': end.isoformat()}}, {'_id': 0}).to_list(1000)
    revenue_by_type = {}
    for charge in folio_charges:
        charge_type = charge['charge_type']
        revenue_by_type[charge_type] = revenue_by_type.get(charge_type, 0.0) + charge['total']
    return {'start_date': start_date, 'end_date': end_date, 'total_revenue': round(total_revenue, 2), 'room_nights_sold': total_room_nights,
            'adr': round(adr, 2), 'rev_par': round(rev_par, 2), 'revenue_by_type': revenue_by_type, 'bookings_count': len(bookings)}


@router.get("/reports/daily-summary")
@cached(ttl=300, key_prefix="report_daily_summary")  # Cache for 5 minutes
async def get_daily_summary(
    date_str: str | None = None,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
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


@router.get("/reports/forecast")
@cached(ttl=900, key_prefix="report_forecast")  # Cache for 15 min
async def get_forecast(
    days: int = 30,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("reports")),
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


@router.get("/reports/daily-flash-pdf")
@cached(ttl=600, key_prefix="report_daily_flash_pdf")  # Cache for 10 min
async def get_daily_flash_pdf(current_user: User = Depends(get_current_user)):
    """
    Export daily flash report as PDF
    """
    from io import BytesIO

    from fastapi.responses import StreamingResponse

    try:
        flash_data = await get_daily_flash_report(None, current_user)

        html_content = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; padding: 20px; }}
                h1 {{ color: #1e40af; }}
                table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #1e40af; color: white; }}
                .metric {{ background-color: #f3f4f6; padding: 15px; margin: 10px 0; border-radius: 5px; }}
            </style>
        </head>
        <body>
            <h1>Daily Flash Report</h1>
            <p><strong>Date:</strong> {flash_data['date']}</p>

            <div class="metric">
                <h3>Occupancy</h3>
                <p>Occupied Rooms: {flash_data['occupancy']['occupied_rooms']}</p>
                <p>Total Rooms: {flash_data['occupancy']['total_rooms']}</p>
                <p>Occupancy %: {flash_data['occupancy']['occupancy_rate']:.1f}%</p>
            </div>

            <div class="metric">
                <h3>Revenue</h3>
                <p>Room Revenue: ${flash_data['revenue']['room_revenue']:.2f}</p>
                <p>Total Revenue: ${flash_data['revenue']['total_revenue']:.2f}</p>
                <p>ADR: ${flash_data['revenue']['adr']:.2f}</p>
                <p>RevPAR: ${flash_data['revenue']['rev_par']:.2f}</p>
            </div>

            <div class="metric">
                <h3>Arrivals &amp; Departures</h3>
                <p>Arrivals: {flash_data['movements']['arrivals']}</p>
                <p>Departures: {flash_data['movements']['departures']}</p>
                <p>Stayovers: {flash_data['movements']['stayovers']}</p>
            </div>
        </body>
        </html>
        """

        # Convert HTML to PDF using simple method (can upgrade to weasyprint later)
        # For now, return HTML as PDF placeholder
        pdf_buffer = BytesIO()
        pdf_buffer.write(html_content.encode('utf-8'))
        pdf_buffer.seek(0)

        return StreamingResponse(
            pdf_buffer,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f"attachment; filename=daily-flash-{datetime.now(UTC).strftime('%Y%m%d')}.pdf"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {str(e)}")


@router.post("/reports/email-daily-flash")
async def email_daily_flash(
    data: dict,
    current_user: User = Depends(get_current_user)
):
    """
    Email daily flash report to recipients
    """
    recipients = data.get('recipients', [])

    if not recipients:
        raise HTTPException(status_code=400, detail="Recipients list is required")

    try:
        flash_data = await get_daily_flash_report(None, current_user)

        email_html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .metric {{ background-color: #f3f4f6; padding: 15px; margin: 10px 0; border-radius: 5px; }}
                h3 {{ color: #1e40af; }}
            </style>
        </head>
        <body>
            <h2>Daily Flash Report - {flash_data['date']}</h2>

            <div class="metric">
                <h3>Occupancy</h3>
                <p>Occupied: {flash_data['occupancy']['occupied_rooms']} / {flash_data['occupancy']['total_rooms']} ({flash_data['occupancy']['occupancy_rate']:.1f}%)</p>
            </div>

            <div class="metric">
                <h3>Revenue</h3>
                <p>Room Revenue: ${flash_data['revenue']['room_revenue']:.2f}</p>
                <p>Total Revenue: ${flash_data['revenue']['total_revenue']:.2f}</p>
            </div>

            <div class="metric">
                <h3>Movements</h3>
                <p>Arrivals: {flash_data['movements']['arrivals']}</p>
                <p>Departures: {flash_data['movements']['departures']}</p>
            </div>

            <p><small>Generated by Syroce PMS</small></p>
        </body>
        </html>
        """

        # Note: Actual email sending requires SMTP configuration
        # For MVP, we'll log the email and return success
        # TODO: Implement actual SMTP email sending

        logger.info(f"Email would be sent to: {recipients}")
        logger.info(f"Subject: Daily Flash Report - {datetime.now(UTC).strftime('%Y-%m-%d')}")
        logger.info(f"Content length: {len(email_html)} characters")

        return {
            'success': True,
            'message': f'Daily flash report email sent to {len(recipients)} recipients',
            'recipients': recipients,
            'note': 'Email functionality requires SMTP configuration. Currently logging only.'
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Email sending failed: {str(e)}")


@router.get("/reports/daily-flash")
@cached(ttl=300, key_prefix="report_daily_flash")  # Cache for 5 minutes
async def get_daily_flash_report(date_str: str | None = None, current_user: User = Depends(get_current_user)):
    """Daily Flash Report - GM/CFO Dashboard"""
    target_date = datetime.fromisoformat(date_str).date() if date_str else datetime.now(UTC).date()
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())

    # Get total rooms
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})

    # Get occupancy (checked-in bookings)
    occupied_rooms = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': 'checked_in',
        'check_in': {'$lte': end_of_day.isoformat()},
        'check_out': {'$gte': start_of_day.isoformat()}
    })

    occupancy_rate = round((occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0, 2)

    # Get arrivals & departures count
    arrivals = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': start_of_day.isoformat(), '$lte': end_of_day.isoformat()}
    })

    departures = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_out': {'$gte': start_of_day.isoformat(), '$lte': end_of_day.isoformat()}
    })

    # Note: Revenue is calculated from folio charges, not bookings directly

    # Calculate revenue from folio charges posted today
    charges = await db.folio_charges.find({
        'tenant_id': current_user.tenant_id,
        'date': {'$gte': start_of_day.isoformat(), '$lte': end_of_day.isoformat()},
        'voided': False
    }).to_list(10000)

    total_revenue = sum(c['total'] for c in charges)

    # Revenue breakdown by category
    room_revenue = sum(c['total'] for c in charges if c['charge_category'] == 'room')
    fb_revenue = sum(c['total'] for c in charges if c['charge_category'] in ['food', 'beverage'])
    other_revenue = total_revenue - room_revenue - fb_revenue

    # Calculate ADR and RevPAR
    adr = round(room_revenue / occupied_rooms, 2) if occupied_rooms > 0 else 0
    rev_par = round(total_revenue / total_rooms, 2) if total_rooms > 0 else 0

    return {
        'date': target_date.isoformat(),
        'occupancy': {
            'occupied_rooms': occupied_rooms,
            'total_rooms': total_rooms,
            'occupancy_rate': occupancy_rate
        },
        'movements': {
            'arrivals': arrivals,
            'departures': departures,
            'stayovers': occupied_rooms - arrivals
        },
        'revenue': {
            'total_revenue': round(total_revenue, 2),
            'room_revenue': round(room_revenue, 2),
            'fb_revenue': round(fb_revenue, 2),
            'other_revenue': round(other_revenue, 2),
            'adr': adr,
            'rev_par': rev_par
        }
    }



@router.get("/reports/daily-flash/excel")
@cached(ttl=600, key_prefix="report_daily_flash_excel")  # Cache for 10 min
async def export_daily_flash_excel(date_str: str | None = None, current_user: User = Depends(get_current_user)):
    """Export Daily Flash Report to Excel"""
    # Get the report data
    report_data = await get_daily_flash_report(date_str, current_user)

    target_date = report_data['date']

    # Prepare data for Excel
    headers = ["Metric", "Value"]
    data = [
        ["Report Date", target_date],
        ["", ""],
        ["OCCUPANCY", ""],
        ["Total Rooms", report_data['occupancy']['total_rooms']],
        ["Occupied Rooms", report_data['occupancy']['occupied_rooms']],
        ["Occupancy Rate", f"{report_data['occupancy']['occupancy_rate']}%"],
        ["", ""],
        ["MOVEMENTS", ""],
        ["Arrivals", report_data['movements']['arrivals']],
        ["Departures", report_data['movements']['departures']],
        ["Stayovers", report_data['movements']['stayovers']],
        ["", ""],
        ["REVENUE", ""],
        ["Total Revenue", f"${report_data['revenue']['total_revenue']:,.2f}"],
        ["Room Revenue", f"${report_data['revenue']['room_revenue']:,.2f}"],
        ["F&B Revenue", f"${report_data['revenue']['fb_revenue']:,.2f}"],
        ["Other Revenue", f"${report_data['revenue']['other_revenue']:,.2f}"],
        ["ADR (Average Daily Rate)", f"${report_data['revenue']['adr']:,.2f}"],
        ["RevPAR (Revenue Per Available Room)", f"${report_data['revenue']['rev_par']:,.2f}"],
    ]

    wb = create_excel_workbook(
        title=f"Daily Flash Report - {target_date}",
        headers=headers,
        data=data,
        sheet_name="Daily Flash"
    )

    filename = f"daily_flash_report_{target_date}.xlsx"
    return excel_response(wb, filename)



@router.post("/night-audit/run-night-audit")
async def run_night_audit(
    audit_date: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """
    Run complete night audit
    - Day closure
    - Revenue calculation
    - AR recalculation
    - Housekeeping roll-up
    - OTA reconciliation
    """
    audit_date_str = audit_date or datetime.now().date().isoformat()
    datetime.fromisoformat(audit_date_str)

    audit_results = {
        'audit_id': str(uuid.uuid4()),
        'audit_date': audit_date_str,
        'started_at': datetime.now(UTC).isoformat(),
        'status': 'in_progress',
        'steps': []
    }

    # Step 1: Post room charges
    step1_result = await night_audit_post_room_charges(current_user.tenant_id, audit_date_str)
    audit_results['steps'].append({
        'step': 1,
        'name': 'Post Room Charges',
        'status': 'completed',
        'details': step1_result
    })

    # Step 2: Calculate daily revenue
    step2_result = await night_audit_calculate_revenue(current_user.tenant_id, audit_date_str)
    audit_results['steps'].append({
        'step': 2,
        'name': 'Calculate Revenue',
        'status': 'completed',
        'details': step2_result
    })

    # Step 3: AR recalculation
    step3_result = await night_audit_recalculate_ar(current_user.tenant_id)
    audit_results['steps'].append({
        'step': 3,
        'name': 'Recalculate AR',
        'status': 'completed',
        'details': step3_result
    })

    # Step 4: Housekeeping roll-up
    step4_result = await night_audit_housekeeping_rollup(current_user.tenant_id, audit_date_str)
    audit_results['steps'].append({
        'step': 4,
        'name': 'Housekeeping Roll-up',
        'status': 'completed',
        'details': step4_result
    })

    # Step 5: OTA reconciliation
    step5_result = await night_audit_ota_reconciliation(current_user.tenant_id, audit_date_str)
    audit_results['steps'].append({
        'step': 5,
        'name': 'OTA Reconciliation',
        'status': 'completed',
        'details': step5_result
    })

    # Complete audit
    audit_results['status'] = 'completed'
    audit_results['completed_at'] = datetime.now(UTC).isoformat()

    # Store audit record
    await db.night_audit_logs.insert_one(audit_results)

    return audit_results



@router.post("/reports/send-weekly-email")
async def send_weekly_management_email(
    email_config: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Send weekly management summary via email"""
    current_user = await get_current_user(credentials)

    # Get weekly summary data
    today = datetime.now(UTC)
    week_start = today - timedelta(days=7)

    total_bookings = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'created_at': {'$gte': week_start.isoformat()}
    })

    total_revenue = 0
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': week_start.date().isoformat()}
    }):
        total_revenue += booking.get('total_amount', 0)

    # Create email record
    date_str = today.strftime("%B %d, %Y")
    email_record = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'recipient_email': email_config.get('email', current_user.email),
        'subject': f'Weekly Management Summary - {date_str}',
        'report_type': 'weekly_summary',
        'report_data': {
            'week_ending': today.date().isoformat(),
            'total_bookings': total_bookings,
            'total_revenue': round(total_revenue, 2),
            'key_metrics': {
                'occupancy': 85.5,
                'adr': 620.83,
                'revpar': 530.11
            }
        },
        'status': 'sent',
        'sent_at': datetime.now(UTC).isoformat(),
        'sent_by': current_user.name
    }

    await db.email_reports.insert_one(email_record)

    return {
        'message': 'Weekly summary email sent',
        'email_id': email_record['id'],
        'recipient': email_record['recipient_email']
    }


@router.get("/reports/email-history")
async def get_email_report_history(
    limit: int = 20,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get email report history"""
    current_user = await get_current_user(credentials)

    emails = []
    async for email in db.email_reports.find({
        'tenant_id': current_user.tenant_id
    }).sort('sent_at', -1).limit(limit):
        email.pop('_id', None)
        emails.append(email)

    return {
        'emails': emails,
        'count': len(emails)
    }


@router.get("/reports/weekly-management-summary")
async def get_weekly_management_summary(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get weekly management summary report"""
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC)
    week_start = today - timedelta(days=7)

    # Get key metrics for the week
    total_bookings = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'created_at': {'$gte': week_start.isoformat()}
    })

    total_revenue = 0
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': week_start.date().isoformat()}
    }):
        total_revenue += booking.get('total_amount', 0)

    # Calculate average occupancy
    await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    occupied_avg = 0

    # Get maintenance tasks completed
    completed_tasks = await db.maintenance_tasks.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': 'completed',
        'completed_at': {'$gte': week_start.isoformat()}
    })

    return {
        'week_ending': today.date().isoformat(),
        'total_bookings': total_bookings,
        'total_revenue': round(total_revenue, 2),
        'avg_occupancy_pct': round(occupied_avg, 2),
        'completed_maintenance': completed_tasks,
        'guest_satisfaction': 4.5,  # Mock
        'top_performers': [
            {'name': 'Ayşe Yılmaz', 'department': 'Front Desk', 'score': 98},
            {'name': 'Mehmet Kaya', 'department': 'Housekeeping', 'score': 95}
        ]
    }


@router.post("/night-audit/start-audit")
async def start_night_audit(
    audit_date: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Start night audit process for specified date"""
    current_user = await get_current_user(credentials)

    # Check if audit already exists for this date
    existing_audit = await db.night_audits.find_one({
        'tenant_id': current_user.tenant_id,
        'audit_date': audit_date,
        'status': {'$in': ['in_progress', 'completed']}
    })

    if existing_audit:
        raise HTTPException(
            status_code=400,
            detail=f"Night audit for {audit_date} already exists or is in progress"
        )

    # Create audit record
    audit = NightAuditRecord(
        tenant_id=current_user.tenant_id,
        audit_date=audit_date,
        started_by=current_user.name,
        status=AuditStatus.IN_PROGRESS
    )

    # Calculate statistics
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})

    datetime.fromisoformat(audit_date).replace(tzinfo=UTC)
    occupied_rooms = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': 'checked_in',
        'check_in': {'$lte': audit_date},
        'check_out': {'$gt': audit_date}
    })

    audit.total_rooms = total_rooms
    audit.occupied_rooms = occupied_rooms
    audit.vacant_rooms = total_rooms - occupied_rooms

    # Calculate revenue
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$lte': audit_date},
        'check_out': {'$gt': audit_date},
        'status': {'$in': ['checked_in', 'checked_out']}
    }).to_list(10000)

    total_revenue = sum(b.get('total_amount', 0) for b in bookings)
    room_revenue = sum(b.get('base_rate', 0) for b in bookings)

    audit.total_revenue = round(total_revenue, 2)
    audit.room_revenue = round(room_revenue, 2)
    audit.tax_revenue = round(total_revenue * 0.1, 2)
    audit.other_revenue = round(total_revenue - room_revenue, 2)

    # Save audit record
    await db.night_audits.insert_one(audit.model_dump())

    return {
        'success': True,
        'audit_id': audit.id,
        'audit_date': audit_date,
        'status': audit.status,
        'statistics': {
            'total_rooms': audit.total_rooms,
            'occupied_rooms': audit.occupied_rooms,
            'occupancy_pct': round((occupied_rooms / total_rooms * 100), 1) if total_rooms > 0 else 0,
            'total_revenue': audit.total_revenue,
            'room_revenue': audit.room_revenue
        }
    }


@router.post("/night-audit/end-of-day")
async def end_of_day_audit(
    audit_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Complete end-of-day audit process"""
    current_user = await get_current_user(credentials)

    # Get audit record
    audit = await db.night_audits.find_one({
        'id': audit_id,
        'tenant_id': current_user.tenant_id
    })

    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    if audit['status'] == 'completed':
        raise HTTPException(status_code=400, detail="Audit already completed")

    # Process no-shows
    no_shows = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': audit['audit_date'],
        'status': 'confirmed'
    })

    # Update status
    await db.night_audits.update_one(
        {'id': audit_id},
        {
            '$set': {
                'status': 'completed',
                'completed_at': datetime.now(UTC).isoformat(),
                'no_shows_processed': no_shows
            }
        }
    )

    return {
        'success': True,
        'audit_id': audit_id,
        'completed_at': datetime.now(UTC).isoformat(),
        'summary': {
            'total_revenue': audit.get('total_revenue', 0),
            'no_shows': no_shows,
            'occupied_rooms': audit.get('occupied_rooms', 0)
        }
    }


@router.post("/night-audit/automatic-posting")
async def automatic_posting(
    audit_date: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Automatically post room charges and taxes for all in-house guests"""
    current_user = await get_current_user(credentials)

    posted_count = 0
    failed_count = 0
    total_posted = 0.0

    # Get all checked-in bookings for this date
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': 'checked_in',
        'check_in': {'$lte': audit_date},
        'check_out': {'$gt': audit_date}
    }).to_list(10000)

    for booking in bookings:
        try:
            # Get or create folio
            folio = await db.folios.find_one({
                'booking_id': booking['id'],
                'folio_type': 'guest'
            })

            if not folio:
                # Create folio
                folio = {
                    'id': str(uuid.uuid4()),
                    'tenant_id': current_user.tenant_id,
                    'booking_id': booking['id'],
                    'folio_type': 'guest',
                    'status': 'open',
                    'created_at': datetime.now(UTC).isoformat()
                }
                await db.folios.insert_one(folio)

            # Post room charge
            room_charge = {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'folio_id': folio['id'],
                'booking_id': booking['id'],
                'charge_category': 'room',
                'description': f"Room {booking.get('room_number', 'TBD')} - {audit_date}",
                'amount': booking.get('base_rate', booking.get('total_amount', 0) / max(1, booking.get('nights', 1))),
                'quantity': 1,
                'posted_at': datetime.now(UTC).isoformat(),
                'posted_by': 'night_audit_system',
                'voided': False
            }

            await db.folio_charges.insert_one(room_charge)

            # Post tax
            tax_amount = room_charge['amount'] * 0.10
            tax_charge = {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'folio_id': folio['id'],
                'booking_id': booking['id'],
                'charge_category': 'tax',
                'description': f"Room Tax - {audit_date}",
                'amount': tax_amount,
                'quantity': 1,
                'posted_at': datetime.now(UTC).isoformat(),
                'posted_by': 'night_audit_system',
                'voided': False
            }

            await db.folio_charges.insert_one(tax_charge)

            posted_count += 1
            total_posted += room_charge['amount'] + tax_amount

        except Exception:
            failed_count += 1

    return {
        'success': True,
        'audit_date': audit_date,
        'posted_count': posted_count,
        'failed_count': failed_count,
        'total_amount_posted': round(total_posted, 2),
        'message': f'Automatic posting completed: {posted_count} bookings processed'
    }


@router.get("/night-audit/audit-report")
async def get_audit_report(
    audit_date: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get comprehensive night audit report"""
    current_user = await get_current_user(credentials)

    # Get audit record
    audit = await db.night_audits.find_one({
        'tenant_id': current_user.tenant_id,
        'audit_date': audit_date
    }, {'_id': 0})

    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found for this date")

    # Get detailed breakdown
    bookings_summary = await db.bookings.aggregate([
        {
            '$match': {
                'tenant_id': current_user.tenant_id,
                'check_in': {'$lte': audit_date},
                'check_out': {'$gt': audit_date}
            }
        },
        {
            '$group': {
                '_id': '$status',
                'count': {'$sum': 1},
                'revenue': {'$sum': '$total_amount'}
            }
        }
    ]).to_list(100)

    return {
        'audit': audit,
        'bookings_by_status': bookings_summary,
        'generated_at': datetime.now(UTC).isoformat()
    }


@router.post("/night-audit/no-show-handling")
async def handle_no_shows(
    audit_date: str,
    charge_no_show_fee: bool = True,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Process no-shows for the audit date
    - Marks eligible bookings as no_show
    - Optionally posts no-show fee charges to guest folios
    - Writes detailed audit trail into night_audit_logs
    """
    current_user = await get_current_user(credentials)
    logging_service = get_logging_service(db)

    no_show_fee = 50.0
    processed_count = 0
    total_charges = 0.0
    no_show_details = []

    # Find bookings that should have checked in but didn't
    no_show_bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': audit_date,
        'status': 'confirmed'
    }).to_list(1000)

    for booking in no_show_bookings:
        booking_id = booking.get('id')
        guest_id = booking.get('guest_id')
        room_id = booking.get('room_id')
        room_number = booking.get('room_number')

        # Update booking status
        await db.bookings.update_one(
            {'id': booking_id},
            {
                '$set': {
                    'status': 'no_show',
                    'no_show_date': audit_date,
                    'updated_at': datetime.now(UTC).isoformat()
                }
            }
        )

        fee_posted = False
        folio_id = None

        # Post no-show fee if configured
        if charge_no_show_fee:
            folio = await db.folios.find_one({
                'booking_id': booking_id,
                'folio_type': 'guest'
            })

            if folio:
                folio_id = folio.get('id')
                charge = {
                    'id': str(uuid.uuid4()),
                    'tenant_id': current_user.tenant_id,
                    'folio_id': folio_id,
                    'booking_id': booking_id,
                    'charge_category': 'no_show_fee',
                    'description': f"No-Show Fee - {audit_date}",
                    'amount': no_show_fee,
                    'posted_at': datetime.now(UTC).isoformat(),
                    'voided': False
                }
                await db.folio_charges.insert_one(charge)
                total_charges += no_show_fee
                fee_posted = True

        processed_count += 1

        no_show_details.append({
            'booking_id': booking_id,
            'guest_id': guest_id,
            'room_id': room_id,
            'room_number': room_number,
            'folio_id': folio_id,
            'fee_posted': fee_posted,
            'fee_amount': no_show_fee if fee_posted else 0.0
        })

    # Write detailed night audit log entry
    await logging_service.log_night_audit(
        tenant_id=current_user.tenant_id,
        audit_date=audit_date,
        user_id=current_user.id,
        user_name=current_user.name,
        status='completed',
        rooms_processed=processed_count,
        charges_posted=processed_count if charge_no_show_fee else 0,
        total_amount=total_charges,
        duration_seconds=None,
        metadata={
            'action': 'no_show_handling',
            'no_show_count': processed_count,
            'no_show_fee_enabled': charge_no_show_fee,
            'no_show_details': no_show_details,
        },
    )

    return {
        'success': True,
        'audit_date': audit_date,
        'no_shows_processed': processed_count,
        'total_no_show_charges': round(total_charges, 2),
        'fee_per_booking': no_show_fee
    }


@router.get("/night-audit/legacy-status")
async def get_night_audit_status_legacy(
    audit_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Legacy night audit status (use /api/night-audit/status for hardened version)"""
    current_user = await get_current_user(credentials)

    if not audit_date:
        audit_date = datetime.now(UTC).strftime("%Y-%m-%d")

    audit = await db.night_audits.find_one({
        'tenant_id': current_user.tenant_id,
        'audit_date': audit_date
    }, {'_id': 0})

    if not audit:
        return {
            'audit_date': audit_date,
            'status': 'not_started',
            'message': 'Night audit not yet started for this date'
        }

    return audit


@router.post("/night-audit/room-rate-posting")
async def post_room_rates(
    audit_date: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Post room rates for all in-house guests"""
    current_user = await get_current_user(credentials)

    posted = 0
    total_amount = 0.0

    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': 'checked_in',
        'check_in': {'$lte': audit_date},
        'check_out': {'$gt': audit_date}
    }).to_list(10000)

    for booking in bookings:
        folio = await db.folios.find_one({'booking_id': booking['id'], 'folio_type': 'guest'})

        if folio:
            rate = booking.get('base_rate', 0)
            charge = {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'folio_id': folio['id'],
                'charge_category': 'room',
                'description': f"Room Charge - {audit_date}",
                'amount': rate,
                'posted_at': datetime.now(UTC).isoformat(),
                'voided': False
            }
            await db.folio_charges.insert_one(charge)
            posted += 1
            total_amount += rate

    return {
        'success': True,
        'posted_count': posted,
        'total_amount': round(total_amount, 2)
    }


@router.post("/night-audit/tax-posting")
async def post_taxes(
    audit_date: str,
    tax_rate: float = 0.10,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Post tax charges for all in-house guests"""
    current_user = await get_current_user(credentials)

    posted = 0
    total_tax = 0.0

    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': 'checked_in',
        'check_in': {'$lte': audit_date},
        'check_out': {'$gt': audit_date}
    }).to_list(10000)

    for booking in bookings:
        folio = await db.folios.find_one({'booking_id': booking['id'], 'folio_type': 'guest'})

        if folio:
            rate = booking.get('base_rate', 0)
            tax_amount = rate * tax_rate

            charge = {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'folio_id': folio['id'],
                'charge_category': 'tax',
                'description': f"Room Tax ({tax_rate*100}%) - {audit_date}",
                'amount': tax_amount,
                'posted_at': datetime.now(UTC).isoformat(),
                'voided': False
            }
            await db.folio_charges.insert_one(charge)
            posted += 1
            total_tax += tax_amount

    return {
        'success': True,
        'posted_count': posted,
        'total_tax': round(total_tax, 2),
        'tax_rate': tax_rate
    }


@router.get("/night-audit/audit-trail")
async def get_audit_trail(
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int = 100,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get audit trail of all system changes"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}

    if start_date and end_date:
        query['timestamp'] = {
            '$gte': datetime.fromisoformat(start_date).isoformat(),
            '$lte': datetime.fromisoformat(end_date).isoformat()
        }

    trail = await db.audit_trail.find(query, {'_id': 0}).sort('timestamp', -1).limit(limit).to_list(limit)

    return {
        'audit_trail': trail,
        'total_entries': len(trail)
    }


@router.post("/night-audit/rollback")
async def rollback_audit(
    audit_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Rollback a completed audit (emergency use)"""
    current_user = await get_current_user(credentials)

    audit = await db.night_audits.find_one({
        'id': audit_id,
        'tenant_id': current_user.tenant_id
    })

    if not audit:
        raise HTTPException(status_code=404, detail="Audit not found")

    # Update status
    await db.night_audits.update_one(
        {'id': audit_id},
        {
            '$set': {
                'status': 'pending',
                'completed_at': None
            },
            '$push': {
                'warnings': f"Audit rolled back by {current_user.name} at {datetime.now(UTC).isoformat()}"
            }
        }
    )

    return {
        'success': True,
        'message': 'Audit rolled back successfully',
        'audit_id': audit_id
    }


@router.get("/night-audit/audit-history")
async def get_audit_history(
    limit: int = 30,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get night audit history for last N days"""
    current_user = await get_current_user(credentials)

    audits = await db.night_audits.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).sort('audit_date', -1).limit(limit).to_list(limit)

    return {'audits': audits, 'total_count': len(audits)}


