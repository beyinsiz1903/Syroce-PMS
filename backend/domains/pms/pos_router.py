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

router = APIRouter(prefix="/api", tags=["pos-fnb"])

# ============= POS / F&B ENDPOINTS =============

@router.get("/pos/outlets")
async def get_pos_outlets(current_user: User = Depends(get_current_user)):
    """Get all F&B outlets"""
    try:
        outlets = await db.fnb_outlets.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(100)
        return outlets
    except Exception:
        return []

@router.get("/pos/menu-items")
async def get_menu_items(current_user: User = Depends(get_current_user)):
    """Get all menu items"""
    try:
        items = await db.menu_items.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
        return items
    except Exception:
        return []

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

@router.get("/pos/transactions")
async def get_pos_transactions(limit: int = 10, current_user: User = Depends(get_current_user)):
    """Get recent POS transactions"""
    try:
        transactions = await db.transactions.find({
            'tenant_id': current_user.tenant_id
        }, {'_id': 0}).sort('created_at', -1).to_list(limit)
        return transactions
    except Exception:
        return []

@router.get("/pos/z-report")
async def get_z_report(date: str = None, current_user: User = Depends(get_current_user)):
    """Get Z report for end of day"""
    try:
        transactions = await db.transactions.find({
            'tenant_id': current_user.tenant_id
        }, {'_id': 0}).to_list(1000)

        total_sales = sum(t.get('amount', 0) for t in transactions)

        return {
            'report_date': date or datetime.utcnow().isoformat(),
            'report_number': f'Z-{datetime.utcnow().strftime("%Y%m%d")}',
            'gross_sales': total_sales,
            'transaction_count': len(transactions),
            'net_sales': total_sales,
            'refunds': 0,
            'discounts': 0,
            'payment_methods': {
                'cash': total_sales * 0.4,
                'card': total_sales * 0.6
            },
            'category_sales': {
                'food': total_sales * 0.5,
                'beverage': total_sales * 0.3,
                'other': total_sales * 0.2
            }
        }
    except Exception:
        return {'gross_sales': 0, 'transaction_count': 0}

@router.get("/pos/void-transactions")
async def get_void_transactions(start_date: str = None, end_date: str = None, current_user: User = Depends(get_current_user)):
    """Get voided transactions"""
    try:
        void_transactions = await db.transactions.find({
            'tenant_id': current_user.tenant_id,
            'status': 'void'
        }, {'_id': 0}).to_list(100)

        return {'void_transactions': void_transactions}
    except Exception:
        return {'void_transactions': []}

@router.post("/pos/mobile/quick-order")
async def create_quick_order(order_data: dict[str, Any], current_user: User = Depends(get_current_user)):
    """Create quick order from mobile"""
    try:
        order = {
            'id': str(uuid.uuid4()),
            **order_data,
            'tenant_id': current_user.tenant_id,
            'created_at': datetime.utcnow().isoformat(),
            'status': 'pending'
        }
        await db.orders.insert_one(order)
        return {'success': True, 'order_id': order['id']}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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


@router.get("/dashboard/gm/forecast-weekly")
async def get_weekly_forecast(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get weekly forecast for next 4 weeks"""
    current_user = await get_current_user(credentials)

    import asyncio as _asyncio
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0)

    # Hoist total_rooms out of the loop; build per-week windows.
    weeks = [(week_num,
              today + timedelta(days=week_num * 7),
              today + timedelta(days=week_num * 7 + 6))
             for week_num in range(4)]

    async def _week_revenue(start, end):
        pipeline = [
            {'$match': {
                'tenant_id': current_user.tenant_id,
                'check_in': {'$gte': start, '$lte': end},
                'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
            }},
            {'$group': {'_id': None,
                        'total_revenue': {'$sum': '$total_amount'},
                        'avg_rate': {'$avg': '$room_rate'}}}
        ]
        async for d in db.bookings.aggregate(pipeline):
            return d
        return None

    # Run total_rooms + per-week (count + revenue) concurrently.
    total_rooms_task = db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    booking_tasks = [
        db.bookings.count_documents({
            'tenant_id': current_user.tenant_id,
            'check_in': {'$gte': s, '$lte': e},
            'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
        }) for (_, s, e) in weeks
    ]
    revenue_tasks = [_week_revenue(s, e) for (_, s, e) in weeks]
    results = await _asyncio.gather(total_rooms_task, *booking_tasks, *revenue_tasks)
    total_rooms = results[0]
    booking_counts = results[1:1 + len(weeks)]
    revenue_results = results[1 + len(weeks):]

    forecast_weeks = []
    for (week_num, week_start, week_end), bookings_count, revenue_data in zip(
            weeks, booking_counts, revenue_results, strict=True):
        expected_occupancy = (bookings_count / (total_rooms * 7)) * 100 if total_rooms > 0 else 0
        forecast_weeks.append({
            'week_number': week_num + 1,
            'start_date': week_start.date().isoformat(),
            'end_date': week_end.date().isoformat(),
            'bookings': bookings_count,
            'expected_revenue': revenue_data['total_revenue'] if revenue_data else 0,
            'avg_rate': revenue_data['avg_rate'] if revenue_data else 0,
            'expected_occupancy': expected_occupancy
        })

    return {
        'forecast_period': 'weekly',
        'weeks': forecast_weeks,
        'total_expected_revenue': sum(w['expected_revenue'] for w in forecast_weeks),
        'avg_weekly_occupancy': sum(w['expected_occupancy'] for w in forecast_weeks) / len(forecast_weeks)
    }


@router.get("/dashboard/gm/forecast-monthly")
async def get_monthly_forecast(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get monthly forecast for next 3 months"""
    current_user = await get_current_user(credentials)

    import asyncio as _asyncio
    today = datetime.now(UTC)

    # Build per-month windows up-front.
    months_spec = []
    for month_offset in range(3):
        if month_offset == 0:
            month_start = today.replace(day=1, hour=0, minute=0, second=0)
        else:
            year = today.year
            month = today.month + month_offset
            if month > 12:
                month = month - 12
                year += 1
            month_start = datetime(year, month, 1, tzinfo=UTC)
        if month_start.month == 12:
            month_end = datetime(month_start.year + 1, 1, 1, tzinfo=UTC) - timedelta(days=1)
        else:
            month_end = datetime(month_start.year, month_start.month + 1, 1, tzinfo=UTC) - timedelta(days=1)
        months_spec.append((month_start, month_end))

    async def _month_revenue(start, end):
        pipeline = [
            {'$match': {
                'tenant_id': current_user.tenant_id,
                'check_in': {'$gte': start, '$lte': end},
                'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
            }},
            {'$group': {'_id': None,
                        'total_revenue': {'$sum': '$total_amount'},
                        'avg_rate': {'$avg': '$room_rate'}}}
        ]
        async for d in db.bookings.aggregate(pipeline):
            return d
        return None

    total_rooms_task = db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    booking_tasks = [
        db.bookings.count_documents({
            'tenant_id': current_user.tenant_id,
            'check_in': {'$gte': s, '$lte': e},
            'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
        }) for (s, e) in months_spec
    ]
    revenue_tasks = [_month_revenue(s, e) for (s, e) in months_spec]
    results = await _asyncio.gather(total_rooms_task, *booking_tasks, *revenue_tasks)
    total_rooms = results[0]
    booking_counts = results[1:1 + len(months_spec)]
    revenue_results = results[1 + len(months_spec):]

    forecast_months = []
    for (month_start, month_end), bookings_count, revenue_data in zip(
            months_spec, booking_counts, revenue_results, strict=True):
        days_in_month = (month_end - month_start).days + 1
        expected_occupancy = (bookings_count / (total_rooms * days_in_month)) * 100 if total_rooms > 0 else 0
        expected_revenue = revenue_data['total_revenue'] if revenue_data else 0
        avg_rate = revenue_data['avg_rate'] if revenue_data else 0
        revpar = expected_revenue / (total_rooms * days_in_month) if total_rooms > 0 else 0
        forecast_months.append({
            'month': month_start.strftime('%B %Y'),
            'month_number': month_start.month,
            'year': month_start.year,
            'start_date': month_start.date().isoformat(),
            'end_date': month_end.date().isoformat(),
            'days': days_in_month,
            'bookings': bookings_count,
            'expected_revenue': expected_revenue,
            'avg_rate': avg_rate,
            'expected_occupancy': expected_occupancy,
            'revpar': revpar
        })

    return {
        'forecast_period': 'monthly',
        'months': forecast_months,
        'total_expected_revenue': sum(m['expected_revenue'] for m in forecast_months),
        'avg_monthly_occupancy': sum(m['expected_occupancy'] for m in forecast_months) / len(forecast_months)
    }


# --------------------------------------------------------------------------
# Front Office - Enhanced Features
# --------------------------------------------------------------------------

@router.get("/frontdesk/rooms-with-filters")
@cached(ttl=180, key_prefix="frontdesk_rooms_filtered")  # Cache for 3 min
async def get_rooms_with_filters(
    bed_type: str | None = None,
    floor: int | None = None,
    status: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get rooms with advanced filters for room moves"""
    current_user = await get_current_user(credentials)

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


# --------------------------------------------------------------------------
# Front Office Mobile - Check-in, ID Scan, Guest Requests, Folio Operations
# --------------------------------------------------------------------------

@router.get("/frontoffice/mobile/available-rooms")
@cached(ttl=120, key_prefix="mobile_available_rooms")  # Cache for 2 min
async def get_available_rooms_mobile(
    check_in: str,
    check_out: str,
    room_type: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get available rooms for check-in"""
    current_user = await get_current_user(credentials)

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
    credentials: HTTPAuthorizationCredentials = Depends(security)
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


@router.post("/frontoffice/mobile/checkin")
async def mobile_checkin(
    booking_id: str,
    room_id: str,
    id_scan_id: str | None = None,
    signature: str | None = None,
    notes: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
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


@router.post("/frontoffice/mobile/room-assignment")
async def assign_room_mobile(
    booking_id: str,
    room_id: str,
    notes: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
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


@router.post("/frontoffice/mobile/guest-request")
async def create_guest_request_mobile(
    booking_id: str | None = None,
    guest_id: str | None = None,
    room_number: str | None = None,
    request_type: str = "other",
    description: str = "",
    priority: str = "normal",
    credentials: HTTPAuthorizationCredentials = Depends(security)
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


@router.put("/frontoffice/mobile/guest-request/{request_id}/status")
async def update_guest_request_status_mobile(
    request_id: str,
    new_status: str,
    assigned_to: str | None = None,
    notes: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
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


@router.post("/frontoffice/mobile/folio/charge")
async def add_folio_charge_mobile(
    folio_id: str,
    category: str,
    description: str,
    quantity: float,
    unit_price: float,
    tax_rate: float = 0.18,
    department: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
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


@router.post("/frontoffice/mobile/folio/void")
async def void_folio_charge_mobile(
    charge_id: str,
    void_reason: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
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


@router.post("/frontdesk/calculate-early-late-fees")
async def calculate_early_late_fees(
    booking_id: str,
    early_checkin_time: str | None = None,
    late_checkout_time: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
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

# --------------------------------------------------------------------------
# Revenue Management - ADR, RevPAR, Forecasting, Rate Override, Analytics
# --------------------------------------------------------------------------

@router.get("/revenue/mobile/dashboard")
async def get_revenue_dashboard_mobile(
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get comprehensive revenue dashboard"""
    current_user = await get_current_user(credentials)

    # Default to current month
    if not start_date or not end_date:
        today = datetime.now(UTC).date()
        start_date = today.replace(day=1).isoformat()
        last_day = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        end_date = last_day.isoformat()

    start_dt = datetime.fromisoformat(start_date).replace(tzinfo=UTC)
    end_dt = datetime.fromisoformat(end_date).replace(tzinfo=UTC)

    # Total rooms
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})

    # Bookings in period
    bookings_query = {
        'tenant_id': current_user.tenant_id,
        'check_in': {'$lte': end_date},
        'check_out': {'$gte': start_date},
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in', 'checked_out']}
    }

    total_revenue = 0.0
    total_room_nights = 0
    bookings_list = []

    async for booking in db.bookings.find(bookings_query):
        revenue = booking.get('total_amount', 0)
        nights = booking.get('nights', 1)
        total_revenue += revenue
        total_room_nights += nights
        bookings_list.append(booking)

    # Calculate metrics
    days_in_period = (end_dt - start_dt).days + 1
    total_room_nights_available = total_rooms * days_in_period

    occupancy = (total_room_nights / total_room_nights_available * 100) if total_room_nights_available > 0 else 0
    adr = (total_revenue / total_room_nights) if total_room_nights > 0 else 0
    revpar = (total_revenue / total_room_nights_available) if total_room_nights_available > 0 else 0

    return {
        'period': {
            'start_date': start_date,
            'end_date': end_date,
            'days': days_in_period
        },
        'key_metrics': {
            'total_revenue': total_revenue,
            'adr': adr,  # Average Daily Rate
            'revpar': revpar,  # Revenue Per Available Room
            'occupancy_percentage': occupancy,
            'total_bookings': len(bookings_list),
            'room_nights_sold': total_room_nights,
            'room_nights_available': total_room_nights_available
        }
    }


@router.get("/revenue/mobile/segment-analysis")
async def get_segment_analysis_mobile(
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get revenue by market segment"""
    current_user = await get_current_user(credentials)

    # Default to current month
    if not start_date or not end_date:
        today = datetime.now(UTC).date()
        start_date = today.replace(day=1).isoformat()
        last_day = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        end_date = last_day.isoformat()

    bookings_query = {
        'tenant_id': current_user.tenant_id,
        'check_in': {'$lte': end_date},
        'check_out': {'$gte': start_date},
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in', 'checked_out']}
    }

    segments = {}

    async for booking in db.bookings.find(bookings_query):
        segment = booking.get('market_segment', 'other')
        revenue = booking.get('total_amount', 0)
        nights = booking.get('nights', 1)

        if segment not in segments:
            segments[segment] = {
                'segment': segment,
                'revenue': 0,
                'bookings': 0,
                'room_nights': 0,
                'adr': 0
            }

        segments[segment]['revenue'] += revenue
        segments[segment]['bookings'] += 1
        segments[segment]['room_nights'] += nights

    # Calculate ADR for each segment
    for segment in segments.values():
        if segment['room_nights'] > 0:
            segment['adr'] = segment['revenue'] / segment['room_nights']

    # Sort by revenue
    segments_list = sorted(segments.values(), key=lambda x: x['revenue'], reverse=True)

    total_revenue = sum(s['revenue'] for s in segments_list)

    # Add percentage
    for segment in segments_list:
        segment['percentage'] = (segment['revenue'] / total_revenue * 100) if total_revenue > 0 else 0

    return {
        'period': {
            'start_date': start_date,
            'end_date': end_date
        },
        'segments': segments_list,
        'total_revenue': total_revenue
    }


@router.get("/revenue/mobile/channel-distribution")
async def get_channel_distribution_mobile(
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get revenue by booking channel"""
    current_user = await get_current_user(credentials)

    # Default to current month
    if not start_date or not end_date:
        today = datetime.now(UTC).date()
        start_date = today.replace(day=1).isoformat()
        last_day = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        end_date = last_day.isoformat()

    bookings_query = {
        'tenant_id': current_user.tenant_id,
        'check_in': {'$lte': end_date},
        'check_out': {'$gte': start_date},
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in', 'checked_out']}
    }

    channels = {}

    async for booking in db.bookings.find(bookings_query):
        channel = booking.get('channel', 'direct')
        revenue = booking.get('total_amount', 0)

        if channel not in channels:
            channels[channel] = {
                'channel': channel,
                'revenue': 0,
                'bookings': 0,
                'adr': 0
            }

        channels[channel]['revenue'] += revenue
        channels[channel]['bookings'] += 1

    # Calculate ADR
    for channel in channels.values():
        if channel['bookings'] > 0:
            channel['adr'] = channel['revenue'] / channel['bookings']

    channels_list = sorted(channels.values(), key=lambda x: x['revenue'], reverse=True)
    total_revenue = sum(c['revenue'] for c in channels_list)

    for channel in channels_list:
        channel['percentage'] = (channel['revenue'] / total_revenue * 100) if total_revenue > 0 else 0

    return {
        'period': {
            'start_date': start_date,
            'end_date': end_date
        },
        'channels': channels_list,
        'total_revenue': total_revenue
    }


@router.get("/revenue/mobile/pickup-graph")
async def get_pickup_graph_mobile(
    arrival_date: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get booking pickup graph for specific arrival date"""
    current_user = await get_current_user(credentials)

    arrival_dt = datetime.fromisoformat(arrival_date).date()

    # Get bookings for this arrival date
    bookings = []
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': arrival_date,
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in', 'checked_out']}
    }).sort('created_at', 1):
        bookings.append({
            'created_at': booking.get('created_at'),
            'room_nights': booking.get('nights', 1)
        })

    # Generate pickup data points
    pickup_points = []

    # Group by days before arrival
    today = datetime.now(UTC).date()
    days_until_arrival = (arrival_dt - today).days

    for i in range(365, -1, -7):  # Weekly points going back 1 year
        cutoff_date = arrival_dt - timedelta(days=i)
        cutoff_dt = datetime.combine(cutoff_date, datetime.max.time()).replace(tzinfo=UTC)

        rooms_at_cutoff = sum(
            b['room_nights'] for b in bookings
            if b['created_at'] <= cutoff_dt
        )

        pickup_points.append({
            'days_before_arrival': i,
            'date': cutoff_date.isoformat(),
            'cumulative_rooms': rooms_at_cutoff
        })

    return {
        'arrival_date': arrival_date,
        'days_until_arrival': days_until_arrival,
        'current_bookings': len(bookings),
        'pickup_data': pickup_points
    }


@router.get("/revenue/mobile/forecast")
async def get_revenue_forecast_mobile(
    forecast_days: int = 90,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get revenue forecast"""
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC).date()
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})

    # Get historical data for forecasting
    lookback_days = 30
    start_historical = (today - timedelta(days=lookback_days)).isoformat()
    end_historical = today.isoformat()

    historical_query = {
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': start_historical, '$lte': end_historical},
        'status': {'$in': ['confirmed', 'guaranteed', 'checked_in', 'checked_out']}
    }

    historical_revenue = 0.0
    historical_nights = 0

    async for booking in db.bookings.find(historical_query):
        historical_revenue += booking.get('total_amount', 0)
        historical_nights += booking.get('nights', 1)

    # Calculate historical averages
    avg_daily_revenue = historical_revenue / lookback_days if lookback_days > 0 else 0
    avg_occupancy = (historical_nights / (total_rooms * lookback_days) * 100) if lookback_days > 0 else 0
    avg_adr = (historical_revenue / historical_nights) if historical_nights > 0 else 0

    # Generate forecast
    forecast_data = []

    for i in range(forecast_days):
        forecast_date = today + timedelta(days=i)

        # Get existing bookings
        existing_bookings = await db.bookings.count_documents({
            'tenant_id': current_user.tenant_id,
            'check_in': forecast_date.isoformat(),
            'status': {'$in': ['confirmed', 'guaranteed']}
        })

        # Simple projection (can be enhanced with ML)
        projected_occupancy = min((existing_bookings / total_rooms * 100) + (avg_occupancy * 0.3), 100)
        projected_rooms = total_rooms * (projected_occupancy / 100)
        projected_adr = avg_adr * (1 + (projected_occupancy - 70) * 0.002)  # Price elasticity
        projected_revenue = projected_rooms * projected_adr
        projected_revpar = projected_revenue / total_rooms

        forecast_data.append({
            'date': forecast_date.isoformat(),
            'day_of_week': forecast_date.strftime('%A'),
            'current_bookings': existing_bookings,
            'projected_occupancy': round(projected_occupancy, 1),
            'projected_adr': round(projected_adr, 2),
            'projected_revpar': round(projected_revpar, 2),
            'projected_revenue': round(projected_revenue, 2)
        })

    return {
        'forecast_period': {
            'start_date': today.isoformat(),
            'end_date': (today + timedelta(days=forecast_days - 1)).isoformat(),
            'days': forecast_days
        },
        'historical_reference': {
            'avg_occupancy': round(avg_occupancy, 1),
            'avg_adr': round(avg_adr, 2),
            'avg_daily_revenue': round(avg_daily_revenue, 2)
        },
        'forecast_data': forecast_data
    }


@router.get("/revenue/mobile/demand-heatmap")
async def get_demand_heatmap_mobile(
    months_ahead: int = 3,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get demand heatmap"""
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC).date()
    end_date = today + timedelta(days=months_ahead * 30)
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})

    heatmap_data = []

    # Generate data for each day
    current_date = today
    while current_date <= end_date:
        # Count bookings for this date
        bookings_count = await db.bookings.count_documents({
            'tenant_id': current_user.tenant_id,
            'check_in': current_date.isoformat(),
            'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
        })

        occupancy = (bookings_count / total_rooms * 100) if total_rooms > 0 else 0

        # Determine demand level
        if occupancy >= 90:
            demand_level = 'very_high'
        elif occupancy >= 70:
            demand_level = 'high'
        elif occupancy >= 40:
            demand_level = 'medium'
        else:
            demand_level = 'low'

        heatmap_data.append({
            'date': current_date.isoformat(),
            'day_of_week': current_date.strftime('%A'),
            'bookings': bookings_count,
            'occupancy': round(occupancy, 1),
            'demand_level': demand_level,
            'available_rooms': total_rooms - bookings_count
        })

        current_date += timedelta(days=1)

    return {
        'period': {
            'start_date': today.isoformat(),
            'end_date': end_date.isoformat()
        },
        'total_rooms': total_rooms,
        'heatmap_data': heatmap_data
    }


@router.get("/revenue/mobile/cancellations-noshows")
async def get_cancellations_noshows_mobile(
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get cancellation and no-show analysis"""
    current_user = await get_current_user(credentials)

    # Default to current month
    if not start_date or not end_date:
        today = datetime.now(UTC).date()
        start_date = today.replace(day=1).isoformat()
        last_day = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        end_date = last_day.isoformat()

    # Cancelled bookings
    cancelled_bookings = []
    cancelled_revenue = 0.0

    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': 'cancelled',
        'check_in': {'$gte': start_date, '$lte': end_date}
    }):
        revenue_lost = booking.get('total_amount', 0)
        cancelled_revenue += revenue_lost

        cancelled_bookings.append({
            'booking_id': booking.get('id'),
            'confirmation_number': booking.get('confirmation_number'),
            'check_in': booking.get('check_in'),
            'nights': booking.get('nights', 0),
            'revenue_lost': revenue_lost,
            'cancelled_at': booking.get('cancelled_at').isoformat() if booking.get('cancelled_at') else None,
            'channel': booking.get('channel', 'unknown')
        })

    # No-show bookings
    noshow_bookings = []
    noshow_revenue = 0.0

    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': 'no_show',
        'check_in': {'$gte': start_date, '$lte': end_date}
    }):
        revenue_lost = booking.get('total_amount', 0)
        noshow_revenue += revenue_lost

        noshow_bookings.append({
            'booking_id': booking.get('id'),
            'confirmation_number': booking.get('confirmation_number'),
            'check_in': booking.get('check_in'),
            'nights': booking.get('nights', 0),
            'revenue_lost': revenue_lost,
            'channel': booking.get('channel', 'unknown')
        })

    # Total bookings in period for comparison
    total_bookings = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': start_date, '$lte': end_date}
    })

    cancellation_rate = (len(cancelled_bookings) / total_bookings * 100) if total_bookings > 0 else 0
    noshow_rate = (len(noshow_bookings) / total_bookings * 100) if total_bookings > 0 else 0

    return {
        'period': {
            'start_date': start_date,
            'end_date': end_date
        },
        'cancellations': {
            'count': len(cancelled_bookings),
            'rate_percentage': round(cancellation_rate, 2),
            'revenue_lost': cancelled_revenue,
            'bookings': cancelled_bookings
        },
        'noshows': {
            'count': len(noshow_bookings),
            'rate_percentage': round(noshow_rate, 2),
            'revenue_lost': noshow_revenue,
            'bookings': noshow_bookings
        },
        'total_bookings': total_bookings,
        'combined_loss': cancelled_revenue + noshow_revenue
    }


@router.post("/revenue/mobile/rate-override")
async def create_rate_override_mobile(
    room_type: str,
    date: str,
    override_rate: float,
    reason: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Create rate override for specific date"""
    current_user = await get_current_user(credentials)

    # Get current rate (simplified - should fetch from rate table)
    # For demo, using a default rate
    original_rate = 1000.0  # This should come from rate management system

    override_id = str(uuid.uuid4())
    override = {
        'id': override_id,
        'tenant_id': current_user.tenant_id,
        'room_type': room_type,
        'date': datetime.fromisoformat(date),
        'original_rate': original_rate,
        'override_rate': override_rate,
        'reason': reason,
        'approved_by': current_user.username,
        'created_by': current_user.username,
        'created_at': datetime.now(UTC)
    }

    await db.rate_overrides.insert_one(override)

    return {
        'message': 'Rate override created',
        'override_id': override_id,
        'room_type': room_type,
        'date': date,
        'original_rate': original_rate,
        'override_rate': override_rate,
        'difference': override_rate - original_rate,
        'percentage_change': ((override_rate - original_rate) / original_rate * 100) if original_rate > 0 else 0
    }


@router.get("/revenue/mobile/rate-overrides")
async def get_rate_overrides_mobile(
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get rate overrides"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}

    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter['$gte'] = datetime.fromisoformat(start_date)
        if end_date:
            date_filter['$lte'] = datetime.fromisoformat(end_date)
        query['date'] = date_filter

    overrides = []
    async for override in db.rate_overrides.find(query).sort('date', 1):
        overrides.append({
            'id': override.get('id'),
            'room_type': override.get('room_type'),
            'date': override.get('date').isoformat() if override.get('date') else None,
            'original_rate': override.get('original_rate'),
            'override_rate': override.get('override_rate'),
            'difference': override.get('override_rate', 0) - override.get('original_rate', 0),
            'reason': override.get('reason'),
            'approved_by': override.get('approved_by'),
            'created_at': override.get('created_at').isoformat() if override.get('created_at') else None
        })

    return {
        'overrides': overrides,
        'count': len(overrides)
    }


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


# --------------------------------------------------------------------------
# Housekeeping - Enhanced Features
# --------------------------------------------------------------------------

@router.get("/housekeeping/status-change-logs")
async def get_status_change_logs(
    room_id: str | None = None,
    limit: int = 50,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get room status change logs (audit trail)"""
    current_user = await get_current_user(credentials)

    query = {
        'tenant_id': current_user.tenant_id,
        'action': 'ROOM_STATUS_CHANGE'
    }

    if room_id:
        query['entity_id'] = room_id

    logs = []
    async for log in db.audit_logs.find(query).sort('timestamp', -1).limit(limit):
        room = await db.rooms.find_one({
            'id': log.get('entity_id'),
            'tenant_id': current_user.tenant_id
        })

        logs.append({
            'log_id': log.get('id'),
            'room_id': log.get('entity_id'),
            'room_number': room.get('room_number') if room else 'N/A',
            'old_status': log.get('changes', {}).get('old_status'),
            'new_status': log.get('changes', {}).get('new_status'),
            'changed_by': log.get('user_name'),
            'timestamp': log.get('timestamp').isoformat() if log.get('timestamp') else None,
            'reason': log.get('changes', {}).get('reason', '')
        })

    return {
        'logs': logs,
        'count': len(logs)
    }


class LostFoundItemCreate(BaseModel):
    item_description: str
    location_found: str
    found_by: str
    category: str | None = 'other'
    room_number: str | None = None
    guest_name: str | None = None
    notes: str | None = None

@router.post("/housekeeping/lost-found/item")
async def create_lost_found_item(
    item: LostFoundItemCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Create a new lost and found item"""
    current_user = await get_current_user(credentials)

    item_id = str(uuid.uuid4())
    lost_found_item = {
        'id': item_id,
        'tenant_id': current_user.tenant_id,
        'item_description': item.item_description,
        'location_found': item.location_found,
        'found_by': item.found_by,
        'category': item.category,
        'room_number': item.room_number,
        'guest_name': item.guest_name,
        'notes': item.notes,
        'status': 'unclaimed',
        'found_date': datetime.now(UTC),
        'created_by': current_user.username,
        'created_at': datetime.now(UTC)
    }

    await db.lost_found.insert_one(lost_found_item)

    return {
        'message': 'Lost & found item created',
        'item_id': item_id,
        'item_description': item.item_description
    }


@router.get("/housekeeping/lost-found/items")
async def get_lost_found_items(
    status: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get lost and found items"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status

    items = []
    async for item in db.lost_found.find(query).sort('found_date', -1):
        items.append({
            'id': item.get('id'),
            'item_description': item.get('item_description'),
            'category': item.get('category'),
            'location_found': item.get('location_found'),
            'room_number': item.get('room_number'),
            'guest_name': item.get('guest_name'),
            'found_by': item.get('found_by'),
            'found_date': item.get('found_date').isoformat() if item.get('found_date') else None,
            'status': item.get('status'),
            'notes': item.get('notes')
        })

    return {
        'items': items,
        'count': len(items),
        'by_status': {
            'unclaimed': len([i for i in items if i['status'] == 'unclaimed']),
            'claimed': len([i for i in items if i['status'] == 'claimed']),
            'disposed': len([i for i in items if i['status'] == 'disposed'])
        }
    }


@router.get("/housekeeping/task-assignments")
async def get_task_assignments(
    date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get housekeeping task assignments and routes"""
    current_user = await get_current_user(credentials)

    if date:
        target_date = datetime.fromisoformat(date).replace(tzinfo=UTC)
    else:
        target_date = datetime.now(UTC)

    start_of_day = target_date.replace(hour=0, minute=0, second=0)
    end_of_day = target_date.replace(hour=23, minute=59, second=59)

    # Get all housekeeping staff
    staff_list = []
    async for task in db.housekeeping_tasks.find({
        'tenant_id': current_user.tenant_id,
        'assigned_to': {'$exists': True, '$ne': None}
    }).limit(100):
        staff_name = task.get('assigned_to')
        if staff_name and staff_name not in staff_list:
            staff_list.append(staff_name)

    # Get assignments for each staff
    assignments = []

    for staff_name in staff_list:
        staff_tasks = []
        completed_count = 0

        async for task in db.housekeeping_tasks.find({
            'tenant_id': current_user.tenant_id,
            'assigned_to': staff_name,
            'created_at': {'$gte': start_of_day, '$lte': end_of_day}
        }).sort('room_number', 1):

            room = await db.rooms.find_one({
                'id': task.get('room_id'),
                'tenant_id': current_user.tenant_id
            })

            task_info = {
                'task_id': task.get('id'),
                'room_id': task.get('room_id'),
                'room_number': room.get('room_number') if room else task.get('room_number'),
                'floor': room.get('floor') if room else 0,
                'task_type': task.get('task_type'),
                'status': task.get('status'),
                'priority': task.get('priority', 'normal'),
                'started_at': task.get('started_at').isoformat() if task.get('started_at') else None
            }

            staff_tasks.append(task_info)

            if task.get('status') == 'completed':
                completed_count += 1

        # Sort tasks by floor and room number for optimal route
        staff_tasks.sort(key=lambda x: (x['floor'], x['room_number']))

        assignments.append({
            'staff_name': staff_name,
            'total_tasks': len(staff_tasks),
            'completed': completed_count,
            'in_progress': len([t for t in staff_tasks if t['status'] == 'in_progress']),
            'pending': len([t for t in staff_tasks if t['status'] in ['new', 'assigned']]),
            'tasks': staff_tasks,
            'route': [t['room_number'] for t in staff_tasks]
        })

    return {
        'date': target_date.date().isoformat(),
        'assignments': assignments,
        'total_staff': len(assignments),
        'total_tasks': sum(a['total_tasks'] for a in assignments)
    }


# --------------------------------------------------------------------------
# Maintenance - Asset History
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# F&B - Z Report, Void Report, Menu Management
# --------------------------------------------------------------------------

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


class MenuItemCreate(BaseModel):
    name: str
    category: str
    price: float
    description: str | None = None
    cost: float | None = None
    available: bool = True
    image_url: str | None = None

@router.post("/pos/menu-item")
async def create_menu_item(
    item: MenuItemCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Create a new menu item"""
    current_user = await get_current_user(credentials)

    item_id = str(uuid.uuid4())
    menu_item = {
        'id': item_id,
        'tenant_id': current_user.tenant_id,
        'name': item.name,
        'category': item.category,
        'price': item.price,
        'description': item.description,
        'cost': item.cost,
        'available': item.available,
        'image_url': item.image_url,
        'created_at': datetime.now(UTC),
        'created_by': current_user.username
    }

    await db.pos_menu_items.insert_one(menu_item)

    return {
        'message': 'Menu item created',
        'item_id': item_id,
        'name': item.name
    }


@router.put("/pos/menu-item/{item_id}")
async def update_menu_item(
    item_id: str,
    item: MenuItemCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Update a menu item"""
    current_user = await get_current_user(credentials)

    existing_item = await db.pos_menu_items.find_one({
        'id': item_id,
        'tenant_id': current_user.tenant_id
    })

    if not existing_item:
        raise HTTPException(status_code=404, detail="Menu item not found")

    await db.pos_menu_items.update_one(
        {'id': item_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'name': item.name,
                'category': item.category,
                'price': item.price,
                'description': item.description,
                'cost': item.cost,
                'available': item.available,
                'image_url': item.image_url,
                'updated_at': datetime.now(UTC),
                'updated_by': current_user.username
            }
        }
    )

    return {
        'message': 'Menu item updated',
        'item_id': item_id
    }


@router.delete("/pos/menu-item/{item_id}")
async def delete_menu_item(
    item_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Delete a menu item"""
    current_user = await get_current_user(credentials)

    result = await db.pos_menu_items.delete_one({
        'id': item_id,
        'tenant_id': current_user.tenant_id
    })

    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Menu item not found")

    return {
        'message': 'Menu item deleted',
        'item_id': item_id
    }


# --------------------------------------------------------------------------
# Finance - P&L Report and Cashier Shift Report
# --------------------------------------------------------------------------

