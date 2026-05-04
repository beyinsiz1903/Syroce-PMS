"""
maintenance

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Domain Router: POS & F&B

Extracted from legacy_routes.py — Point of Sale, F&B operations, kitchen, transactions.
"""
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user, security

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


# ── GET /maintenance/asset-history/{asset_id} ──
@router.get("/maintenance/asset-history/{asset_id}")
async def get_asset_maintenance_history(
    asset_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get maintenance history for a specific asset/equipment"""
    current_user = await get_current_user(credentials)

    # Get asset info
    asset = await db.equipment.find_one({
        'id': asset_id,
        'tenant_id': current_user.tenant_id
    })

    if not asset:
        # Try finding by room_id
        room = await db.rooms.find_one({
            'id': asset_id,
            'tenant_id': current_user.tenant_id
        })

        if not room:
            raise HTTPException(status_code=404, detail="Asset not found")

        asset = {
            'id': room.get('id'),
            'name': f"Room {room.get('room_number')}",
            'type': 'room',
            'room_number': room.get('room_number')
        }

    # Get all maintenance tasks for this asset
    history = []
    async for task in db.tasks.find({
        '$or': [
            {'room_id': asset_id},
            {'equipment_id': asset_id}
        ],
        'tenant_id': current_user.tenant_id,
        'department': 'maintenance'
    }).sort('created_at', -1):

        history.append({
            'task_id': task.get('id'),
            'title': task.get('title'),
            'description': task.get('description'),
            'issue_type': task.get('issue_type'),
            'priority': task.get('priority'),
            'status': task.get('status'),
            'assigned_to': task.get('assigned_to'),
            'created_at': task.get('created_at').isoformat() if task.get('created_at') else None,
            'completed_at': task.get('completed_at').isoformat() if task.get('completed_at') else None,
            'resolution_notes': task.get('resolution_notes', ''),
            'cost': task.get('cost', 0)
        })

    # Calculate statistics
    total_tasks = len(history)
    completed_tasks = len([h for h in history if h['status'] == 'completed'])
    total_cost = sum(h['cost'] for h in history)

    # Calculate average resolution time
    resolution_times = []
    for h in history:
        if h['completed_at'] and h['created_at']:
            created = datetime.fromisoformat(h['created_at'])
            completed = datetime.fromisoformat(h['completed_at'])
            duration = (completed - created).total_seconds() / 3600  # hours
            resolution_times.append(duration)

    avg_resolution_time = sum(resolution_times) / len(resolution_times) if resolution_times else 0

    return {
        'asset': {
            'id': asset.get('id'),
            'name': asset.get('name'),
            'type': asset.get('type'),
            'room_number': asset.get('room_number')
        },
        'history': history,
        'statistics': {
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'pending_tasks': total_tasks - completed_tasks,
            'total_cost': total_cost,
            'avg_resolution_time_hours': avg_resolution_time
        }
    }
