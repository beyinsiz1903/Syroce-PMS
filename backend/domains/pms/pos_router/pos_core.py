"""
pos_core

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Domain Router: POS & F&B

Extracted from legacy_routes.py — Point of Sale, F&B operations, kitchen, transactions.
"""
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.cache import cached
from core.database import db
from core.security import get_current_user, security
from models.schemas import User
from modules.pms_core.role_permission_service import (
    require_module,  # v89 DW
    require_op,  # v88 DW
)
from modules.pms_core.role_permission_service import require_module as require_module_v92  # v92 DW
from modules.pms_core.role_permission_service import require_module as require_module_v99  # v99 DW


# ============= POS / F&B ENDPOINTS =============

# NOTE: GET /pos/outlets and GET /pos/menu-items are served by marketplace_router
# (richer logic with today_transactions enrichment). The duplicates that used to
# live here have been removed to keep a single canonical source of truth.


async def _query_pos_transactions(
    tenant_id: str,
    *,
    limit: int = 50,
    outlet_id: str | None = None,
    booking_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    date: str | None = None,
) -> list[dict]:
    """Canonical POS transaction query.

    Reads from pos_menu_transactions (same source as /pos/z-report and
    /pos/void-transactions). Falls back to legacy collections (transactions,
    pos_orders) so older data still surfaces.
    """
    base_q: dict[str, Any] = {'tenant_id': tenant_id}
    if outlet_id:
        base_q['outlet_id'] = outlet_id
    if booking_id:
        base_q['booking_id'] = booking_id
    if date:
        base_q['transaction_date'] = date
    elif start_date or end_date:
        rng: dict[str, Any] = {}
        if start_date:
            rng['$gte'] = start_date
        if end_date:
            rng['$lte'] = end_date
        if rng:
            base_q['transaction_date'] = rng

    try:
        rows = await db.pos_menu_transactions.find(
            base_q, {'_id': 0}
        ).sort('created_at', -1).to_list(limit)
        if rows:
            return rows
        # Legacy fallback #1: db.transactions
        rows = await db.transactions.find(
            base_q, {'_id': 0}
        ).sort('created_at', -1).to_list(limit)
        if rows:
            return rows
        # Legacy fallback #2: db.pos_orders
        return await db.pos_orders.find(
            base_q, {'_id': 0}
        ).sort('created_at', -1).to_list(limit)
    except Exception:
        return []








async def get_anomaly_detection(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Detect anomalies in room operations"""
    current_user = await get_current_user(credentials)

    anomalies = []

    # 1. Price Anomalies - Rooms priced significantly below average
    avg_rate_pipeline = [
        {
            '$match': {
                'tenant_id': current_user.tenant_id,
                'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
                'created_at': {'$gte': datetime.now(UTC) - timedelta(days=30)}
            }
        },
        {
            '$group': {
                '_id': '$room_type',
                'avg_rate': {'$avg': '$room_rate'},
                'min_rate': {'$min': '$room_rate'},
                'max_rate': {'$max': '$room_rate'}
            }
        }
    ]

    rate_stats = {}
    async for stat in db.bookings.aggregate(avg_rate_pipeline):
        rate_stats[stat['_id']] = stat

    # Check for low-priced bookings
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': datetime.now(UTC)},
        'status': {'$in': ['confirmed', 'guaranteed']}
    }):
        room_type = booking.get('room_type')
        room_rate = booking.get('room_rate', 0)

        if room_type in rate_stats:
            avg_rate = rate_stats[room_type]['avg_rate']
            if room_rate < avg_rate * 0.7:  # 30% below average
                anomalies.append({
                    'type': 'low_price',
                    'severity': 'medium',
                    'booking_id': booking.get('id'),
                    'room_number': booking.get('room_number'),
                    'guest_name': booking.get('guest_name'),
                    'current_rate': room_rate,
                    'average_rate': avg_rate,
                    'difference_pct': ((avg_rate - room_rate) / avg_rate * 100),
                    'message': f"Oda {booking.get('room_number')} ortalamanın %{((avg_rate - room_rate) / avg_rate * 100):.0f} altında fiyatlandırılmış"
                })

    # 2. Cleaning Delay Anomalies (batched room lookup)
    delay_tasks = await db.housekeeping_tasks.find({
        'tenant_id': current_user.tenant_id,
        'task_type': 'cleaning',
        'status': 'in_progress',
        'started_at': {'$lte': datetime.now(UTC) - timedelta(hours=1)}
    }).to_list(length=None)
    dt_room_ids = [t.get('room_id') for t in delay_tasks if t.get('room_id')]
    dt_rooms_by_id: dict = {}
    if dt_room_ids:
        async for r in db.rooms.find(
            {'id': {'$in': dt_room_ids}, 'tenant_id': current_user.tenant_id},
            {'_id': 0, 'id': 1, 'room_number': 1},
        ):
            dt_rooms_by_id[r['id']] = r
    for task in delay_tasks:
        duration = (datetime.now(UTC) - task.get('started_at')).total_seconds() / 60
        room = dt_rooms_by_id.get(task.get('room_id'))
        room_num = room.get('room_number') if room else 'N/A'
        anomalies.append({
            'type': 'cleaning_delay',
            'severity': 'high' if duration > 90 else 'medium',
            'room_id': task.get('room_id'),
            'room_number': room_num,
            'duration_minutes': int(duration),
            'assigned_to': task.get('assigned_to'),
            'message': f"Oda {room_num} {int(duration)} dakikadır temizleniyor"
        })

    # 3. Overstay Risk Detection
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0)
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_out': {'$lte': today},
        'status': 'checked_in'
    }):
        days_over = (today - booking.get('check_out')).days

        anomalies.append({
            'type': 'overstay',
            'severity': 'high',
            'booking_id': booking.get('id'),
            'room_number': booking.get('room_number'),
            'guest_name': booking.get('guest_name'),
            'days_over': days_over,
            'original_checkout': booking.get('check_out').date().isoformat(),
            'message': f"Misafir {booking.get('guest_name')} check-out yapması gerekirken hala odada ({days_over} gün geçti)"
        })

    # 4. High Maintenance Frequency Rooms
    maintenance_pipeline = [
        {
            '$match': {
                'tenant_id': current_user.tenant_id,
                'department': 'maintenance',
                'created_at': {'$gte': datetime.now(UTC) - timedelta(days=30)}
            }
        },
        {
            '$group': {
                '_id': '$room_id',
                'count': {'$sum': 1},
                'room_number': {'$first': '$room_number'}
            }
        },
        {
            '$match': {'count': {'$gte': 3}}
        },
        {
            '$sort': {'count': -1}
        }
    ]

    async for room_stat in db.tasks.aggregate(maintenance_pipeline):
        anomalies.append({
            'type': 'high_maintenance',
            'severity': 'medium',
            'room_id': room_stat['_id'],
            'room_number': room_stat['room_number'],
            'maintenance_count': room_stat['count'],
            'message': f"Oda {room_stat['room_number']} son 30 günde {room_stat['count']} kez bakıma girdi"
        })

    return {
        'anomalies': anomalies,
        'count': len(anomalies),
        'by_severity': {
            'high': len([a for a in anomalies if a['severity'] == 'high']),
            'medium': len([a for a in anomalies if a['severity'] == 'medium']),
            'low': len([a for a in anomalies if a['severity'] == 'low'])
        }
    }






# --------------------------------------------------------------------------
# Front Office - Enhanced Features
# --------------------------------------------------------------------------

# rbac-allow: cache-rbac — FO rooms filter operasyonel


# --------------------------------------------------------------------------
# Front Office Mobile - Check-in, ID Scan, Guest Requests, Folio Operations
# --------------------------------------------------------------------------

# rbac-allow: cache-rbac — FO available rooms operasyonel

























# --------------------------------------------------------------------------
# Revenue Management - ADR, RevPAR, Forecasting, Rate Override, Analytics
# --------------------------------------------------------------------------





















# --------------------------------------------------------------------------
# Housekeeping - Enhanced Features
# --------------------------------------------------------------------------



class LostFoundItemCreate(BaseModel):
    item_description: str
    location_found: str
    found_by: str
    category: str | None = 'other'
    room_number: str | None = None
    guest_name: str | None = None
    notes: str | None = None







# --------------------------------------------------------------------------
# Maintenance - Asset History
# --------------------------------------------------------------------------



# --------------------------------------------------------------------------
# F&B - Z Report, Void Report, Menu Management
# --------------------------------------------------------------------------





class MenuItemCreate(BaseModel):
    name: str
    category: str
    price: float
    description: str | None = None
    cost: float | None = None
    available: bool = True
    image_url: str | None = None
    tax_rate: float = 0.10  # KDV (varsayilan %10)
    outlet_id: str | None = None







# --------------------------------------------------------------------------
# Finance - P&L Report and Cashier Shift Report
# --------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["pos-fnb"])


# ── GET /pos/daily-summary ──
@router.get("/pos/daily-summary")
async def get_pos_daily_summary(date: str = None, current_user: User = Depends(get_current_user)):
    """Get daily POS summary"""
    try:
        transactions = await db.transactions.find({
            'tenant_id': current_user.tenant_id,
            'type': {'$in': ['fnb_charge', 'room_charge']}
        }, {'_id': 0}).to_list(1000)

        total_sales = sum(t.get('amount', 0) for t in transactions)
        return {
            'total_sales': total_sales,
            'transaction_count': len(transactions),
            'average_transaction': total_sales / len(transactions) if transactions else 0
        }
    except Exception:
        return {'total_sales': 0, 'transaction_count': 0, 'average_transaction': 0}
# ── GET /pos/transactions ──
@router.get("/pos/transactions")
async def get_pos_transactions(
    limit: int = 50,
    outlet_id: str | None = None,
    booking_id: str | None = None,
    date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Recent POS transactions — canonical endpoint.

    Returns wrapped response: {transactions, count}.
    """
    rows = await _query_pos_transactions(
        current_user.tenant_id,
        limit=limit, outlet_id=outlet_id, booking_id=booking_id,
        date=date, start_date=start_date, end_date=end_date,
    )
    return {'transactions': rows, 'count': len(rows)}
# ── GET /pos/orders ──
@router.get("/pos/orders")
async def get_pos_orders(
    limit: int = 50,
    outlet_id: str | None = None,
    booking_id: str | None = None,
    date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Alias of /pos/transactions returning {orders, count}.

    Reads same canonical source so the two endpoints can never diverge.
    Replaces the older pos_fnb_router.get_pos_orders that only read pos_orders.
    """
    rows = await _query_pos_transactions(
        current_user.tenant_id,
        limit=limit, outlet_id=outlet_id, booking_id=booking_id,
        date=date, start_date=start_date, end_date=end_date,
    )
    return {'orders': rows, 'count': len(rows)}
# ── GET /pos/z-report ──
@router.get("/pos/z-report")
async def get_z_report(
    date: str = None,
    outlet_id: str = None,
    current_user: User = Depends(get_current_user),
):
    """Z raporu — gun sonu (gercek hesaplama).

    Kaynak: pos_menu_transactions. Gecerli tarih (date) veya bugun.
    Sahte oranlar yerine gercek odeme/kategori dagilimi.
    """
    try:
        report_date = date or datetime.now(UTC).date().isoformat()
        query = {
            'tenant_id': current_user.tenant_id,
            'transaction_date': report_date,
        }
        if outlet_id:
            query['outlet_id'] = outlet_id

        all_tx = await db.pos_menu_transactions.find(query, {'_id': 0}).to_list(5000)

        valid_tx = [t for t in all_tx if t.get('status') != 'void']
        void_tx = [t for t in all_tx if t.get('status') == 'void']

        gross_sales = sum(float(t.get('total_amount', 0) or 0) for t in valid_tx)
        discounts = sum(float(t.get('discount_amount', 0) or 0) for t in valid_tx)
        tax_total = sum(float(t.get('tax_amount', 0) or 0) for t in valid_tx)
        refunds = sum(float(t.get('total_amount', 0) or 0) for t in void_tx)
        net_sales = max(gross_sales - discounts, 0)

        # Odeme yontemi dagilimi (gercek)
        payment_methods: dict[str, float] = {}
        for t in valid_tx:
            pm = t.get('payment_method') or 'unknown'
            payment_methods[pm] = payment_methods.get(pm, 0) + float(t.get('total_amount', 0) or 0)

        # Kategori dagilimi (gercek — items[].category)
        category_sales: dict[str, float] = {}
        for t in valid_tx:
            for item in (t.get('items') or []):
                cat = item.get('category') or 'other'
                line_total = float(item.get('price', 0) or 0) * float(item.get('quantity', 1) or 1)
                category_sales[cat] = category_sales.get(cat, 0) + line_total

        # Outlet dagilimi
        outlet_breakdown: dict[str, float] = {}
        for t in valid_tx:
            oid = t.get('outlet_id') or 'unassigned'
            outlet_breakdown[oid] = outlet_breakdown.get(oid, 0) + float(t.get('total_amount', 0) or 0)

        return {
            'report_date': report_date,
            'report_number': f'Z-{report_date.replace("-", "")}',
            'gross_sales': round(gross_sales, 2),
            'net_sales': round(net_sales, 2),
            'tax_total': round(tax_total, 2),
            'discounts': round(discounts, 2),
            'refunds': round(refunds, 2),
            'transaction_count': len(valid_tx),
            'void_count': len(void_tx),
            'payment_methods': {k: round(v, 2) for k, v in payment_methods.items()},
            'category_sales': {k: round(v, 2) for k, v in category_sales.items()},
            'outlet_breakdown': {k: round(v, 2) for k, v in outlet_breakdown.items()},
        }
    except Exception as e:
        return {
            'report_date': date,
            'gross_sales': 0,
            'net_sales': 0,
            'transaction_count': 0,
            'error': str(e),
        }
# ── GET /pos/void-transactions ──
@router.get("/pos/void-transactions")
async def get_void_transactions(
    date: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    outlet_id: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Voided POS transactions, filtered by date/outlet — sourced from
    pos_menu_transactions so it stays consistent with /pos/z-report."""
    try:
        query: dict[str, Any] = {
            'tenant_id': current_user.tenant_id,
            'status': 'void',
        }
        if outlet_id:
            query['outlet_id'] = outlet_id
        if date:
            query['transaction_date'] = date
        elif start_date or end_date:
            range_q: dict[str, Any] = {}
            if start_date:
                range_q['$gte'] = start_date
            if end_date:
                range_q['$lte'] = end_date
            if range_q:
                query['transaction_date'] = range_q

        voids = await db.pos_menu_transactions.find(query, {'_id': 0}).to_list(500)
        if not voids:
            # Legacy fallback for older data in db.transactions
            legacy_q = dict(query)
            voids = await db.transactions.find(legacy_q, {'_id': 0}).to_list(500)
        return {'void_transactions': voids, 'count': len(voids)}
    except Exception:
        return {'void_transactions': [], 'count': 0}
# ── GET /pos/z-report ──
@router.get("/pos/z-report")
async def get_z_report_detailed(
    date: str | None = None,
    outlet_id: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get Z report (end of day report) for POS"""
    current_user = await get_current_user(credentials)

    if date:
        target_date = datetime.fromisoformat(date)
    else:
        target_date = datetime.now(UTC)

    start_of_day = target_date.replace(hour=0, minute=0, second=0)
    end_of_day = target_date.replace(hour=23, minute=59, second=59)

    query = {
        'tenant_id': current_user.tenant_id,
        'created_at': {'$gte': start_of_day, '$lte': end_of_day}
    }

    if outlet_id:
        query['outlet_id'] = outlet_id

    # Get all transactions
    total_sales = 0
    total_tax = 0
    transaction_count = 0
    payment_methods = {}
    voided_amount = 0

    async for transaction in db.pos_transactions.find(query):
        if transaction.get('status') == 'voided':
            voided_amount += transaction.get('total_amount', 0)
            continue

        total_sales += transaction.get('total_amount', 0)
        total_tax += transaction.get('tax_amount', 0)
        transaction_count += 1

        payment_method = transaction.get('payment_method', 'cash')
        payment_methods[payment_method] = payment_methods.get(payment_method, 0) + transaction.get('total_amount', 0)

    # Get category breakdown
    category_sales = {}
    async for order in db.pos_orders.find(query):
        for item in order.get('items', []):
            category = item.get('category', 'other')
            category_sales[category] = category_sales.get(category, 0) + item.get('total', 0)

    # Calculate net sales
    net_sales = total_sales - voided_amount

    return {
        'date': target_date.date().isoformat(),
        'outlet_id': outlet_id,
        'report_type': 'z_report',
        'summary': {
            'gross_sales': total_sales,
            'voided_amount': voided_amount,
            'net_sales': net_sales,
            'total_tax': total_tax,
            'transaction_count': transaction_count,
            'average_transaction': net_sales / transaction_count if transaction_count > 0 else 0
        },
        'payment_methods': payment_methods,
        'category_sales': category_sales,
        'generated_at': datetime.now(UTC).isoformat()
    }
# ── GET /pos/void-report ──
@router.get("/pos/void-report")
async def get_void_report(
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get voided transactions report"""
    current_user = await get_current_user(credentials)

    if not start_date:
        start_date = datetime.now(UTC).replace(hour=0, minute=0, second=0)
    else:
        start_date = datetime.fromisoformat(start_date)

    if not end_date:
        end_date = datetime.now(UTC).replace(hour=23, minute=59, second=59)
    else:
        end_date = datetime.fromisoformat(end_date)

    voided_transactions = []
    total_voided_amount = 0

    async for transaction in db.pos_transactions.find({
        'tenant_id': current_user.tenant_id,
        'status': 'voided',
        'voided_at': {'$gte': start_date, '$lte': end_date}
    }).sort('voided_at', -1):

        voided_transactions.append({
            'transaction_id': transaction.get('id'),
            'outlet_name': transaction.get('outlet_name'),
            'table_number': transaction.get('table_number'),
            'original_amount': transaction.get('total_amount', 0),
            'voided_by': transaction.get('voided_by'),
            'voided_at': transaction.get('voided_at').isoformat() if transaction.get('voided_at') else None,
            'void_reason': transaction.get('void_reason', ''),
            'items': transaction.get('items', [])
        })

        total_voided_amount += transaction.get('total_amount', 0)

    return {
        'date_range': {
            'start': start_date.date().isoformat(),
            'end': end_date.date().isoformat()
        },
        'voided_transactions': voided_transactions,
        'total_voided_count': len(voided_transactions),
        'total_voided_amount': total_voided_amount
    }
