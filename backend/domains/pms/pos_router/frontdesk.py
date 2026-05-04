"""
frontdesk

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
from modules.pms_core.role_permission_service import (
    require_module,  # v89 DW
    require_op,  # v88 DW
)
from modules.pms_core.role_permission_service import require_module as require_module_v92  # v92 DW

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


# ── GET /frontdesk/rooms-with-filters ──
@router.get("/frontdesk/rooms-with-filters")
@cached(ttl=180, key_prefix="frontdesk_rooms_filtered")  # Cache for 3 min
async def get_rooms_with_filters(
    bed_type: str | None = None,
    floor: int | None = None,
    status: str | None = None,
    current_user=Depends(get_current_user),  # v68 Bug DE: tenant-scoped cache key
):
    """Get rooms with advanced filters for room moves"""

    query = {'tenant_id': current_user.tenant_id}

    if bed_type:
        query['bed_type'] = bed_type
    if floor is not None:
        query['floor'] = floor
    if status:
        query['status'] = status

    rooms = []
    async for room in db.rooms.find(query).sort('room_number', 1):
        rooms.append({
            'id': room.get('id'),
            'room_number': room.get('room_number'),
            'room_type': room.get('room_type'),
            'bed_type': room.get('bed_type', 'unknown'),
            'floor': room.get('floor', 0),
            'status': room.get('status'),
            'max_occupancy': room.get('max_occupancy', 2),
            'features': room.get('features', [])
        })

    return {
        'rooms': rooms,
        'count': len(rooms),
        'filters_applied': {
            'bed_type': bed_type,
            'floor': floor,
            'status': status
        }
    }
# ── GET /frontoffice/mobile/available-rooms ──
@router.get("/frontoffice/mobile/available-rooms")
@cached(ttl=120, key_prefix="mobile_available_rooms")  # Cache for 2 min
async def get_available_rooms_mobile(
    check_in: str | None = None,
    check_out: str | None = None,
    room_type: str | None = None,
    current_user=Depends(get_current_user),  # v68 Bug DE: tenant-scoped cache key
):
    """Get available rooms for check-in"""
    # Tur 3: defaults — today / today+1 when omitted
    from datetime import date as _d
    from datetime import timedelta as _td
    if not check_in:
        check_in = _d.today().isoformat()
    if not check_out:
        check_out = (_d.today() + _td(days=1)).isoformat()

    query = {
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['available', 'clean']}
    }

    if room_type:
        query['room_type'] = room_type

    available_rooms = []
    async for room in db.rooms.find(query).sort('room_number', 1):
        # Check if room is not booked for the dates
        booking_conflict = await db.bookings.find_one({
            'tenant_id': current_user.tenant_id,
            'room_id': room.get('id'),
            'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
            '$or': [
                {
                    'check_in': {'$lte': check_out},
                    'check_out': {'$gte': check_in}
                }
            ]
        })

        if not booking_conflict:
            available_rooms.append({
                'id': room.get('id'),
                'room_number': room.get('room_number'),
                'room_type': room.get('room_type'),
                'bed_type': room.get('bed_type', 'unknown'),
                'floor': room.get('floor', 0),
                'status': room.get('status'),
                'max_occupancy': room.get('max_occupancy', 2),
                'features': room.get('features', []),
                'rate': room.get('rate', 0)
            })

    return {
        'available_rooms': available_rooms,
        'count': len(available_rooms),
        'check_in': check_in,
        'check_out': check_out
    }
# ── POST /frontoffice/mobile/scan-id ──
@router.post("/frontoffice/mobile/scan-id")
async def scan_id_mobile(
    scan_type: str,
    first_name: str,
    last_name: str,
    nationality: str,
    id_number: str,
    date_of_birth: str | None = None,
    issue_date: str | None = None,
    expiry_date: str | None = None,
    scan_image: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_v92("frontdesk")),  # v92 DW
):
    """Scan and save ID/Passport information"""
    current_user = await get_current_user(credentials)

    scan_id = str(uuid.uuid4())
    scan_result = {
        'id': scan_id,
        'tenant_id': current_user.tenant_id,
        'scan_type': scan_type,
        'first_name': first_name,
        'last_name': last_name,
        'nationality': nationality,
        'id_number': id_number,
        'date_of_birth': date_of_birth,
        'issue_date': issue_date,
        'expiry_date': expiry_date,
        'scan_image': scan_image,
        'scanned_at': datetime.now(UTC),
        'scanned_by': current_user.username
    }

    await db.id_scans.insert_one(scan_result)

    return {
        'message': 'ID scan saved successfully',
        'scan_id': scan_id,
        'data': {
            'first_name': first_name,
            'last_name': last_name,
            'nationality': nationality,
            'id_number': id_number,
            'date_of_birth': date_of_birth
        }
    }
# ── POST /frontoffice/mobile/checkin ──
@router.post("/frontoffice/mobile/checkin")
async def mobile_checkin(
    booking_id: str,
    room_id: str,
    id_scan_id: str | None = None,
    signature: str | None = None,
    notes: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module_v92("frontdesk")),  # v92 DW
):
    """Perform mobile check-in"""
    current_user = await get_current_user(credentials)

    # Get booking
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Get room
    room = await db.rooms.find_one({
        'id': room_id,
        'tenant_id': current_user.tenant_id
    })

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    # Check room availability
    if room.get('status') not in ['available', 'clean']:
        raise HTTPException(status_code=400, detail=f"Room {room.get('room_number')} is not available")

    # Create check-in record
    checkin_id = str(uuid.uuid4())
    checkin_record = {
        'id': checkin_id,
        'tenant_id': current_user.tenant_id,
        'booking_id': booking_id,
        'guest_id': booking.get('guest_id'),
        'room_id': room_id,
        'room_number': room.get('room_number'),
        'check_in_status': 'checked_in',
        'id_scan_id': id_scan_id,
        'signature': signature,
        'registration_card_signed': True if signature else False,
        'keys_issued': True,
        'welcome_package_given': True,
        'check_in_time': datetime.now(UTC),
        'checked_in_by': current_user.username,
        'notes': notes,
        'created_at': datetime.now(UTC),
        'updated_at': datetime.now(UTC)
    }

    await db.mobile_checkins.insert_one(checkin_record)

    # Update booking status
    await db.bookings.update_one(
        {'id': booking_id, 'tenant_id': current_user.tenant_id},
        {'$set': {
            'status': 'checked_in',
            'room_id': room_id,
            'room_number': room.get('room_number'),
            'actual_check_in': datetime.now(UTC),
            'updated_at': datetime.now(UTC)
        }}
    )

    # Update room status
    await db.rooms.update_one(
        {'id': room_id, 'tenant_id': current_user.tenant_id},
        {'$set': {
            'status': 'occupied',
            'updated_at': datetime.now(UTC)
        }}
    )

    # Get guest info
    guest = await db.guests.find_one({
        'id': booking.get('guest_id'),
        'tenant_id': current_user.tenant_id
    })

    return {
        'message': 'Check-in completed successfully',
        'checkin_id': checkin_id,
        'booking_id': booking_id,
        'room_number': room.get('room_number'),
        'guest_name': guest.get('name') if guest else 'Unknown',
        'check_in_time': datetime.now(UTC).isoformat()
    }
# ── POST /frontoffice/mobile/room-assignment ──
@router.post("/frontoffice/mobile/room-assignment")
async def assign_room_mobile(
    booking_id: str,
    room_id: str,
    notes: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("frontdesk")),  # v89 DW
):
    """Assign room to booking (pre-checkin)"""
    current_user = await get_current_user(credentials)

    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    room = await db.rooms.find_one({
        'id': room_id,
        'tenant_id': current_user.tenant_id
    })

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    # Update booking with room assignment
    await db.bookings.update_one(
        {'id': booking_id, 'tenant_id': current_user.tenant_id},
        {'$set': {
            'room_id': room_id,
            'room_number': room.get('room_number'),
            'room_assigned': True,
            'room_assigned_at': datetime.now(UTC),
            'room_assigned_by': current_user.username,
            'updated_at': datetime.now(UTC)
        }}
    )

    # Update room status to blocked
    await db.rooms.update_one(
        {'id': room_id, 'tenant_id': current_user.tenant_id},
        {'$set': {
            'status': 'blocked',
            'updated_at': datetime.now(UTC)
        }}
    )

    return {
        'message': 'Room assigned successfully',
        'booking_id': booking_id,
        'room_id': room_id,
        'room_number': room.get('room_number')
    }
# ── GET /frontoffice/mobile/reservation/{booking_id}/detail ──
@router.get("/frontoffice/mobile/reservation/{booking_id}/detail")
async def get_reservation_detail_mobile(
    booking_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get detailed reservation information"""
    current_user = await get_current_user(credentials)

    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Get guest
    guest = await db.guests.find_one({
        'id': booking.get('guest_id'),
        'tenant_id': current_user.tenant_id
    })

    # Get room if assigned
    room = None
    if booking.get('room_id'):
        room = await db.rooms.find_one({
            'id': booking.get('room_id'),
            'tenant_id': current_user.tenant_id
        })

    # Get folio
    folio = await db.folios.find_one({
        'booking_id': booking_id,
        'tenant_id': current_user.tenant_id
    })

    # Get guest preferences
    preferences = await db.guest_preferences.find_one({
        'guest_id': booking.get('guest_id'),
        'tenant_id': current_user.tenant_id
    })

    # Get previous stays
    previous_stays = []
    async for prev_booking in db.bookings.find({
        'guest_id': booking.get('guest_id'),
        'tenant_id': current_user.tenant_id,
        'status': 'checked_out'
    }).sort('check_out', -1).limit(5):
        previous_stays.append({
            'booking_id': prev_booking.get('id'),
            'check_in': prev_booking.get('check_in'),
            'check_out': prev_booking.get('check_out'),
            'room_number': prev_booking.get('room_number'),
            'total_amount': prev_booking.get('total_amount', 0)
        })

    return {
        'booking': {
            'id': booking.get('id'),
            'confirmation_number': booking.get('confirmation_number'),
            'status': booking.get('status'),
            'check_in': booking.get('check_in'),
            'check_out': booking.get('check_out'),
            'nights': booking.get('nights', 0),
            'adults': booking.get('adults', 1),
            'children': booking.get('children', 0),
            'room_type': booking.get('room_type'),
            'rate_plan': booking.get('rate_plan'),
            'total_amount': booking.get('total_amount', 0),
            'channel': booking.get('channel'),
            'special_requests': booking.get('special_requests'),
            'created_at': booking.get('created_at').isoformat() if booking.get('created_at') else None
        },
        'guest': {
            'id': guest.get('id') if guest else None,
            'name': guest.get('name') if guest else 'Unknown',
            'email': guest.get('email') if guest else None,
            'phone': guest.get('phone') if guest else None,
            'nationality': guest.get('nationality') if guest else None,
            'id_number': guest.get('id_number') if guest else None,
            'vip_status': guest.get('vip_status', False) if guest else False,
            'loyalty_tier': guest.get('loyalty_tier') if guest else None
        } if guest else None,
        'room': {
            'id': room.get('id') if room else None,
            'room_number': room.get('room_number') if room else None,
            'room_type': room.get('room_type') if room else None,
            'floor': room.get('floor') if room else None,
            'status': room.get('status') if room else None
        } if room else None,
        'folio': {
            'id': folio.get('id') if folio else None,
            'folio_number': folio.get('folio_number') if folio else None,
            'balance': folio.get('balance', 0) if folio else 0,
            'status': folio.get('status') if folio else None
        } if folio else None,
        'preferences': {
            'room_preferences': preferences.get('room_preferences', {}) if preferences else {},
            'dietary_restrictions': preferences.get('dietary_restrictions', []) if preferences else [],
            'special_occasions': preferences.get('special_occasions', []) if preferences else []
        } if preferences else None,
        'previous_stays': previous_stays
    }
# ── GET /frontoffice/mobile/guest/{guest_id}/history ──
@router.get("/frontoffice/mobile/guest/{guest_id}/history")
async def get_guest_history_mobile(
    guest_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get guest stay history"""
    current_user = await get_current_user(credentials)

    guest = await db.guests.find_one({
        'id': guest_id,
        'tenant_id': current_user.tenant_id
    })

    if not guest:
        raise HTTPException(status_code=404, detail="Guest not found")

    # Get all bookings
    bookings = []
    total_spent = 0.0
    total_nights = 0

    async for booking in db.bookings.find({
        'guest_id': guest_id,
        'tenant_id': current_user.tenant_id
    }).sort('check_in', -1):
        total_spent += booking.get('total_amount', 0)
        total_nights += booking.get('nights', 0)

        bookings.append({
            'booking_id': booking.get('id'),
            'confirmation_number': booking.get('confirmation_number'),
            'check_in': booking.get('check_in'),
            'check_out': booking.get('check_out'),
            'nights': booking.get('nights', 0),
            'room_number': booking.get('room_number'),
            'room_type': booking.get('room_type'),
            'status': booking.get('status'),
            'total_amount': booking.get('total_amount', 0)
        })

    return {
        'guest': {
            'id': guest.get('id'),
            'name': guest.get('name'),
            'email': guest.get('email'),
            'phone': guest.get('phone'),
            'vip_status': guest.get('vip_status', False),
            'loyalty_tier': guest.get('loyalty_tier')
        },
        'statistics': {
            'total_stays': len(bookings),
            'total_nights': total_nights,
            'total_spent': total_spent,
            'average_spend_per_stay': total_spent / len(bookings) if bookings else 0
        },
        'bookings': bookings
    }
# ── POST /frontoffice/mobile/guest-request ──
@router.post("/frontoffice/mobile/guest-request")
async def create_guest_request_mobile(
    booking_id: str | None = None,
    guest_id: str | None = None,
    room_number: str | None = None,
    request_type: str = "other",
    description: str = "",
    priority: str = "normal",
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("frontdesk")),  # v89 DW
):
    """Create guest request"""
    current_user = await get_current_user(credentials)

    request_id = str(uuid.uuid4())
    request = {
        'id': request_id,
        'tenant_id': current_user.tenant_id,
        'booking_id': booking_id,
        'guest_id': guest_id,
        'room_number': room_number,
        'request_type': request_type,
        'status': 'pending',
        'priority': priority,
        'description': description,
        'requested_at': datetime.now(UTC),
        'created_by': current_user.username,
        'updated_at': datetime.now(UTC)
    }

    await db.guest_requests.insert_one(request)

    return {
        'message': 'Guest request created successfully',
        'request_id': request_id,
        'request_type': request_type,
        'status': 'pending'
    }
# ── GET /frontoffice/mobile/guest-requests ──
@router.get("/frontoffice/mobile/guest-requests")
async def get_guest_requests_mobile(
    status: str | None = None,
    room_number: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get guest requests"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}

    if status:
        query['status'] = status
    if room_number:
        query['room_number'] = room_number

    requests = []
    async for request in db.guest_requests.find(query).sort('requested_at', -1).limit(100):
        requests.append({
            'id': request.get('id'),
            'booking_id': request.get('booking_id'),
            'room_number': request.get('room_number'),
            'request_type': request.get('request_type'),
            'status': request.get('status'),
            'priority': request.get('priority'),
            'description': request.get('description'),
            'assigned_to': request.get('assigned_to'),
            'requested_at': request.get('requested_at').isoformat() if request.get('requested_at') else None,
            'completed_at': request.get('completed_at').isoformat() if request.get('completed_at') else None
        })

    # Summary by status
    summary = {
        'pending': len([r for r in requests if r['status'] == 'pending']),
        'in_progress': len([r for r in requests if r['status'] == 'in_progress']),
        'completed': len([r for r in requests if r['status'] == 'completed']),
        'total': len(requests)
    }

    return {
        'requests': requests,
        'summary': summary
    }
# ── PUT /frontoffice/mobile/guest-request/{request_id}/status ──
@router.put("/frontoffice/mobile/guest-request/{request_id}/status")
async def update_guest_request_status_mobile(
    request_id: str,
    new_status: str,
    assigned_to: str | None = None,
    notes: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("frontdesk")),  # v89 DW
):
    """Update guest request status"""
    current_user = await get_current_user(credentials)

    request = await db.guest_requests.find_one({
        'id': request_id,
        'tenant_id': current_user.tenant_id
    })

    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    update_data = {
        'status': new_status,
        'updated_at': datetime.now(UTC)
    }

    if assigned_to:
        update_data['assigned_to'] = assigned_to
        if new_status == 'assigned':
            update_data['assigned_at'] = datetime.now(UTC)

    if new_status == 'completed':
        update_data['completed_at'] = datetime.now(UTC)

    if notes:
        update_data['notes'] = notes

    await db.guest_requests.update_one(
        {'id': request_id, 'tenant_id': current_user.tenant_id},
        {'$set': update_data}
    )

    return {
        'message': f'Request status updated to {new_status}',
        'request_id': request_id,
        'new_status': new_status
    }
# ── POST /frontoffice/mobile/folio/charge ──
@router.post("/frontoffice/mobile/folio/charge")
async def add_folio_charge_mobile(
    folio_id: str,
    category: str,
    description: str,
    quantity: float,
    unit_price: float,
    tax_rate: float = 0.18,
    department: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("post_payment")),  # v88 DW
):
    """Add charge to folio"""
    current_user = await get_current_user(credentials)

    folio = await db.folios.find_one({
        'id': folio_id,
        'tenant_id': current_user.tenant_id
    })

    if not folio:
        raise HTTPException(status_code=404, detail="Folio not found")

    # Calculate amounts
    amount = quantity * unit_price
    tax_amount = amount * tax_rate
    total = amount + tax_amount

    # Create charge
    charge_id = str(uuid.uuid4())
    charge = {
        'id': charge_id,
        'tenant_id': current_user.tenant_id,
        'folio_id': folio_id,
        'category': category,
        'description': description,
        'quantity': quantity,
        'unit_price': unit_price,
        'amount': amount,
        'tax_rate': tax_rate,
        'tax_amount': tax_amount,
        'total': total,
        'posted_by': current_user.username,
        'posted_at': datetime.now(UTC),
        'voided': False,
        'department': department
    }

    await db.folio_charges.insert_one(charge)

    # Update folio balance
    new_balance = folio.get('balance', 0) + total
    await db.folios.update_one(
        {'id': folio_id, 'tenant_id': current_user.tenant_id},
        {'$set': {
            'balance': new_balance,
            'updated_at': datetime.now(UTC)
        }}
    )

    return {
        'message': 'Charge added successfully',
        'charge_id': charge_id,
        'amount': amount,
        'tax_amount': tax_amount,
        'total': total,
        'new_folio_balance': new_balance
    }
# ── POST /frontoffice/mobile/folio/void ──
@router.post("/frontoffice/mobile/folio/void")
async def void_folio_charge_mobile(
    charge_id: str,
    void_reason: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("frontdesk")),  # v89 DW
):
    """Void a folio charge"""
    current_user = await get_current_user(credentials)

    charge = await db.folio_charges.find_one({
        'id': charge_id,
        'tenant_id': current_user.tenant_id
    })

    if not charge:
        raise HTTPException(status_code=404, detail="Charge not found")

    if charge.get('voided'):
        raise HTTPException(status_code=400, detail="Charge already voided")

    # Mark charge as voided
    await db.folio_charges.update_one(
        {'id': charge_id, 'tenant_id': current_user.tenant_id},
        {'$set': {
            'voided': True,
            'voided_by': current_user.username,
            'voided_at': datetime.now(UTC),
            'void_reason': void_reason
        }}
    )

    # Update folio balance
    folio = await db.folios.find_one({
        'id': charge.get('folio_id'),
        'tenant_id': current_user.tenant_id
    })

    if folio:
        new_balance = folio.get('balance', 0) - charge.get('total', 0)
        await db.folios.update_one(
            {'id': charge.get('folio_id'), 'tenant_id': current_user.tenant_id},
            {'$set': {
                'balance': new_balance,
                'updated_at': datetime.now(UTC)
            }}
        )

    return {
        'message': 'Charge voided successfully',
        'charge_id': charge_id,
        'voided_amount': charge.get('total', 0),
        'new_folio_balance': new_balance if folio else 0
    }
# ── GET /frontoffice/mobile/folio/{folio_id}/transactions ──
@router.get("/frontoffice/mobile/folio/{folio_id}/transactions")
async def get_folio_transactions_mobile(
    folio_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get folio transactions (charges and payments)"""
    current_user = await get_current_user(credentials)

    folio = await db.folios.find_one({
        'id': folio_id,
        'tenant_id': current_user.tenant_id
    })

    if not folio:
        raise HTTPException(status_code=404, detail="Folio not found")

    # Get charges
    charges = []
    total_charges = 0.0
    async for charge in db.folio_charges.find({
        'folio_id': folio_id,
        'tenant_id': current_user.tenant_id
    }).sort('posted_at', 1):
        if not charge.get('voided'):
            total_charges += charge.get('total', 0)

        charges.append({
            'id': charge.get('id'),
            'type': 'charge',
            'category': charge.get('category'),
            'description': charge.get('description'),
            'quantity': charge.get('quantity'),
            'unit_price': charge.get('unit_price'),
            'amount': charge.get('amount'),
            'tax_amount': charge.get('tax_amount'),
            'total': charge.get('total'),
            'voided': charge.get('voided', False),
            'void_reason': charge.get('void_reason'),
            'posted_by': charge.get('posted_by'),
            'posted_at': charge.get('posted_at').isoformat() if charge.get('posted_at') else None
        })

    # Get payments
    payments = []
    total_payments = 0.0
    async for payment in db.payments.find({
        'folio_id': folio_id,
        'tenant_id': current_user.tenant_id
    }).sort('created_at', 1):
        total_payments += payment.get('amount', 0)

        payments.append({
            'id': payment.get('id'),
            'type': 'payment',
            'amount': payment.get('amount'),
            'payment_method': payment.get('payment_method'),
            'payment_type': payment.get('payment_type'),
            'notes': payment.get('notes'),
            'posted_by': payment.get('created_by'),
            'posted_at': payment.get('created_at').isoformat() if payment.get('created_at') else None
        })

    # Combine and sort by date
    all_transactions = charges + payments
    all_transactions.sort(key=lambda x: x['posted_at'] if x['posted_at'] else '')

    return {
        'folio': {
            'id': folio.get('id'),
            'folio_number': folio.get('folio_number'),
            'balance': folio.get('balance', 0),
            'status': folio.get('status')
        },
        'transactions': all_transactions,
        'summary': {
            'total_charges': total_charges,
            'total_payments': total_payments,
            'current_balance': total_charges - total_payments,
            'charge_count': len(charges),
            'payment_count': len(payments)
        }
    }
# ── POST /frontdesk/calculate-early-late-fees ──
@router.post("/frontdesk/calculate-early-late-fees")
async def calculate_early_late_fees(
    booking_id: str,
    early_checkin_time: str | None = None,
    late_checkout_time: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("frontdesk")),  # v89 DW
):
    """Calculate early check-in and late checkout fees"""
    current_user = await get_current_user(credentials)

    # Get booking
    booking = await db.bookings.find_one({
        'id': booking_id,
        'tenant_id': current_user.tenant_id
    })

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Calculate fees (simplified implementation)
    early_checkin_fee = 50.0 if early_checkin_time else 0.0
    late_checkout_fee = 75.0 if late_checkout_time else 0.0
    total_fees = early_checkin_fee + late_checkout_fee

    return {
        'booking_id': booking_id,
        'early_checkin_fee': early_checkin_fee,
        'late_checkout_fee': late_checkout_fee,
        'total_fees': total_fees,
        'currency': 'USD'
    }
# ── GET /frontdesk/guest-alerts ──
@router.get("/frontdesk/guest-alerts")
async def get_guest_alerts(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get guest alerts (VIP, birthday, health issues, etc.)"""
    current_user = await get_current_user(credentials)

    import asyncio as _asyncio
    alerts = []
    today = datetime.now(UTC).date()

    # 1) Pull all relevant bookings via cursor (no truncation).
    bookings_list: list[dict] = []
    async for b in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        '$or': [
            {'status': 'checked_in'},
            {
                'check_in': {
                    '$gte': datetime.combine(today, datetime.min.time()).replace(tzinfo=UTC),
                    '$lte': datetime.combine(today, datetime.max.time()).replace(tzinfo=UTC)
                },
                'status': {'$in': ['confirmed', 'guaranteed']}
            }
        ]
    }):
        bookings_list.append(b)

    # 2) Batch-load guests + repeat-stay counts with bounded concurrency.
    unique_ids = list({b.get('guest_id') for b in bookings_list if b.get('guest_id')})

    # Guest fetch — chunk $in to keep BSON payload safe (chunks of 500).
    guest_map: dict[str, dict] = {}
    for i in range(0, len(unique_ids), 500):
        chunk = unique_ids[i:i + 500]
        async for g in db.guests.find({
            'id': {'$in': chunk},
            'tenant_id': current_user.tenant_id,
        }):
            guest_map[g['id']] = g

    # Repeat counts — gather with semaphore to cap concurrent ops at 25.
    sem = _asyncio.Semaphore(25)

    async def _count(gid: str) -> int:
        async with sem:
            return await db.bookings.count_documents({
                'guest_id': gid,
                'tenant_id': current_user.tenant_id,
                'status': 'checked_out',
            })
    repeat_counts = await _asyncio.gather(*[_count(gid) for gid in unique_ids])
    repeat_map = dict(zip(unique_ids, repeat_counts, strict=True))

    for booking in bookings_list:
        guest = guest_map.get(booking.get('guest_id'))
        if not guest:
            continue

        # VIP Status Alert
        if guest.get('vip_status'):
            alerts.append({
                'type': 'vip',
                'priority': 'high',
                'guest_name': booking.get('guest_name'),
                'room_number': booking.get('room_number'),
                'message': f"VIP Misafir - {guest.get('vip_tier', 'Standard')} seviye",
                'icon': '⭐',
                'details': {
                    'tier': guest.get('vip_tier'),
                    'preferences': guest.get('preferences', [])
                }
            })

        # Birthday Alert
        if guest.get('date_of_birth'):
            birthday = guest.get('date_of_birth')
            if isinstance(birthday, str):
                birthday = datetime.fromisoformat(birthday).date()

            if birthday.month == today.month and birthday.day == today.day:
                alerts.append({
                    'type': 'birthday',
                    'priority': 'medium',
                    'guest_name': booking.get('guest_name'),
                    'room_number': booking.get('room_number'),
                    'message': 'Bugün doğum günü! 🎂',
                    'icon': '🎂',
                    'details': {
                        'age': today.year - birthday.year
                    }
                })

        # Health Issues Alert
        if guest.get('health_notes') or guest.get('allergies'):
            alerts.append({
                'type': 'health',
                'priority': 'high',
                'guest_name': booking.get('guest_name'),
                'room_number': booking.get('room_number'),
                'message': 'Sağlık notu/alerji var',
                'icon': '🏥',
                'details': {
                    'health_notes': guest.get('health_notes', ''),
                    'allergies': guest.get('allergies', [])
                }
            })

        # Special Requests Alert
        if booking.get('special_requests'):
            alerts.append({
                'type': 'special_request',
                'priority': 'medium',
                'guest_name': booking.get('guest_name'),
                'room_number': booking.get('room_number'),
                'message': 'Özel istek var',
                'icon': '📝',
                'details': {
                    'requests': booking.get('special_requests')
                }
            })

        # Repeat Guest Alert (precomputed)
        guest_booking_count = repeat_map.get(guest.get('id'), 0)

        if guest_booking_count >= 5:
            alerts.append({
                'type': 'repeat_guest',
                'priority': 'low',
                'guest_name': booking.get('guest_name'),
                'room_number': booking.get('room_number'),
                'message': f"Sadık misafir - {guest_booking_count} konaklama",
                'icon': '💎',
                'details': {
                    'total_stays': guest_booking_count
                }
            })

    return {
        'alerts': alerts,
        'count': len(alerts),
        'by_priority': {
            'high': len([a for a in alerts if a['priority'] == 'high']),
            'medium': len([a for a in alerts if a['priority'] == 'medium']),
            'low': len([a for a in alerts if a['priority'] == 'low'])
        }
    }
