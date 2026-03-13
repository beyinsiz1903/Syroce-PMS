# PMS Complete Endpoints - Part 2 to append to server.py

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta, date
from typing import List, Dict, Any, Optional
import uuid

from core.database import db
from core.security import get_current_user
from models.schemas import User, FolioCharge, Payment, HousekeepingTask, ChannelRate

api_router = APIRouter(prefix="/api")

# This continues from the previous server.py
# ============= FRONT DESK ENDPOINTS =============

@api_router.post("/frontdesk/checkin/{booking_id}")
async def check_in_guest(booking_id: str, current_user: User = Depends(get_current_user)):
    """Complete check-in process"""
    booking = await db.bookings.find_one({'id': booking_id, 'tenant_id': current_user.tenant_id}, {'_id': 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    if booking['status'] != 'confirmed':
        raise HTTPException(status_code=400, detail="Booking must be confirmed before check-in")
    
    # Update booking status
    checked_in_time = datetime.now(timezone.utc)
    await db.bookings.update_one(
        {'id': booking_id},
        {'$set': {
            'status': 'checked_in',
            'checked_in_at': checked_in_time.isoformat()
        }}
    )
    
    # Update room status
    await db.rooms.update_one(
        {'id': booking['room_id']},
        {'$set': {
            'status': 'occupied',
            'current_booking_id': booking_id
        }}
    )
    
    # Create folio charge for room
    nights = (datetime.fromisoformat(booking['check_out']) - datetime.fromisoformat(booking['check_in'])).days
    room = await db.rooms.find_one({'id': booking['room_id']}, {'_id': 0})
    
    folio_charge = FolioCharge(
        tenant_id=current_user.tenant_id,
        booking_id=booking_id,
        charge_type='room',
        description=f"Room {room['room_number']} - {nights} nights",
        amount=room['base_price'],
        quantity=nights,
        total=room['base_price'] * nights,
        posted_by=current_user.name
    )
    
    charge_dict = folio_charge.model_dump()
    charge_dict['date'] = charge_dict['date'].isoformat()
    await db.folio_charges.insert_one(charge_dict)
    
    # Update guest stats
    await db.guests.update_one(
        {'id': booking['guest_id']},
        {'$inc': {'total_stays': 1}}
    )
    
    return {'message': 'Check-in completed', 'checked_in_at': checked_in_time.isoformat()}

@api_router.post("/frontdesk/checkout/{booking_id}")
async def check_out_guest(booking_id: str, current_user: User = Depends(get_current_user)):
    """Complete checkout process"""
    booking = await db.bookings.find_one({'id': booking_id, 'tenant_id': current_user.tenant_id}, {'_id': 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    # Get total charges
    charges = await db.folio_charges.find({'booking_id': booking_id}, {'_id': 0}).to_list(1000)
    total_charges = sum(c['total'] for c in charges)
    
    # Get total payments
    payments = await db.payments.find({'booking_id': booking_id}, {'_id': 0}).to_list(1000)
    total_paid = sum(p['amount'] for p in payments if p['status'] == 'paid')
    
    balance = total_charges - total_paid
    
    if balance > 0:
        raise HTTPException(status_code=400, detail=f"Outstanding balance: ${balance:.2f}. Please settle before checkout.")
    
    # Update booking
    checked_out_time = datetime.now(timezone.utc)
    await db.bookings.update_one(
        {'id': booking_id},
        {'$set': {
            'status': 'checked_out',
            'checked_out_at': checked_out_time.isoformat()
        }}
    )
    
    # Update room status to dirty
    await db.rooms.update_one(
        {'id': booking['room_id']},
        {'$set': {
            'status': 'dirty',
            'current_booking_id': None
        }}
    )
    
    # Create housekeeping task
    task = HousekeepingTask(
        tenant_id=current_user.tenant_id,
        room_id=booking['room_id'],
        task_type='cleaning',
        priority='high',
        notes='Guest checked out'
    )
    
    task_dict = task.model_dump()
    task_dict['created_at'] = task_dict['created_at'].isoformat()
    await db.housekeeping_tasks.insert_one(task_dict)
    
    return {'message': 'Check-out completed', 'balance': balance, 'checked_out_at': checked_out_time.isoformat()}

@api_router.post("/frontdesk/folio/{booking_id}/charge")
async def add_folio_charge(
    booking_id: str,
    charge_type: str,
    description: str,
    amount: float,
    quantity: float = 1.0,
    current_user: User = Depends(get_current_user)
):
    """Add charge to guest folio"""
    booking = await db.bookings.find_one({'id': booking_id, 'tenant_id': current_user.tenant_id})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    folio_charge = FolioCharge(
        tenant_id=current_user.tenant_id,
        booking_id=booking_id,
        charge_type=charge_type,
        description=description,
        amount=amount,
        quantity=quantity,
        total=amount * quantity,
        posted_by=current_user.name
    )
    
    charge_dict = folio_charge.model_dump()
    charge_dict['date'] = charge_dict['date'].isoformat()
    await db.folio_charges.insert_one(charge_dict)
    
    return folio_charge

@api_router.get("/frontdesk/folio/{booking_id}")
async def get_folio(booking_id: str, current_user: User = Depends(get_current_user)):
    """Get complete folio for a booking"""
    charges = await db.folio_charges.find({'booking_id': booking_id, 'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    payments = await db.payments.find({'booking_id': booking_id, 'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    
    total_charges = sum(c['total'] for c in charges)
    total_paid = sum(p['amount'] for p in payments if p['status'] == 'paid')
    balance = total_charges - total_paid
    
    return {
        'charges': charges,
        'payments': payments,
        'total_charges': total_charges,
        'total_paid': total_paid,
        'balance': balance
    }

@api_router.post("/frontdesk/payment/{booking_id}")
async def process_payment(
    booking_id: str,
    amount: float,
    method: str,
    reference: Optional[str] = None,
    notes: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Process payment for booking"""
    booking = await db.bookings.find_one({'id': booking_id, 'tenant_id': current_user.tenant_id})
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")
    
    payment = Payment(
        tenant_id=current_user.tenant_id,
        booking_id=booking_id,
        amount=amount,
        method=method,
        status='paid',
        reference=reference,
        notes=notes,
        processed_by=current_user.name
    )
    
    payment_dict = payment.model_dump()
    payment_dict['processed_at'] = payment_dict['processed_at'].isoformat()
    await db.payments.insert_one(payment_dict)
    
    # Update booking paid amount
    await db.bookings.update_one(
        {'id': booking_id},
        {'$inc': {'paid_amount': amount}}
    )
    
    return payment

@api_router.get("/frontdesk/arrivals")
async def get_arrivals(date: Optional[str] = None, current_user: User = Depends(get_current_user)):
    """Get today's arrivals (optimized to avoid N+1 queries)"""
    if not date:
        target_date = datetime.now(timezone.utc).date()
    else:
        target_date = datetime.fromisoformat(date).date()

    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())

    # Fetch bookings for the day
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['confirmed', 'checked_in']},
        'check_in': {
            '$gte': start_of_day.isoformat(),
            '$lte': end_of_day.isoformat()
        }
    }, {'_id': 0}).to_list(1000)

    if not bookings:
        return []

    # Collect unique guest and room IDs for bulk lookup
    guest_ids = {b.get('guest_id') for b in bookings if b.get('guest_id')}
    room_ids = {b.get('room_id') for b in bookings if b.get('room_id')}

    guests = []
    rooms = []
    if guest_ids:
        guests = await db.guests.find({'id': {'$in': list(guest_ids)}}, {'_id': 0}).to_list(len(guest_ids))
    if room_ids:
        rooms = await db.rooms.find({'id': {'$in': list(room_ids)}}, {'_id': 0}).to_list(len(room_ids))

    guest_map = {g['id']: g for g in guests if 'id' in g}
    room_map = {r['id']: r for r in rooms if 'id' in r}

    enriched = []
    for booking in bookings:
        enriched.append({
            **booking,
            'guest': guest_map.get(booking.get('guest_id')),
            'room': room_map.get(booking.get('room_id')),
        })

    return enriched

@api_router.get("/frontdesk/departures")
async def get_departures(date: Optional[str] = None, current_user: User = Depends(get_current_user)):
    """Get today's departures (optimized to avoid N+1 queries)"""
    if not date:
        target_date = datetime.now(timezone.utc).date()
    else:
        target_date = datetime.fromisoformat(date).date()

    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())

    # Fetch bookings for the day
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': 'checked_in',
        'check_out': {
            '$gte': start_of_day.isoformat(),
            '$lte': end_of_day.isoformat()
        }
    }, {'_id': 0}).to_list(1000)

    if not bookings:
        return []

    booking_ids = [b['id'] for b in bookings if 'id' in b]
    guest_ids = {b.get('guest_id') for b in bookings if b.get('guest_id')}
    room_ids = {b.get('room_id') for b in bookings if b.get('room_id')}

    guests = []
    rooms = []
    charges = []
    payments = []

    if guest_ids:
        guests = await db.guests.find({'id': {'$in': list(guest_ids)}}, {'_id': 0}).to_list(len(guest_ids))
    if room_ids:
        rooms = await db.rooms.find({'id': {'$in': list(room_ids)}}, {'_id': 0}).to_list(len(room_ids))
    if booking_ids:
        charges = await db.folio_charges.find({'booking_id': {'$in': booking_ids}}, {'_id': 0}).to_list(1000)
        payments = await db.payments.find({'booking_id': {'$in': booking_ids}}, {'_id': 0}).to_list(1000)

    guest_map = {g['id']: g for g in guests if 'id' in g}
    room_map = {r['id']: r for r in rooms if 'id' in r}

    # Group charges and payments by booking
    charges_by_booking: Dict[str, float] = {}
    payments_by_booking: Dict[str, float] = {}

    for c in charges:
        bid = c.get('booking_id')
        if not bid:
            continue
        charges_by_booking[bid] = charges_by_booking.get(bid, 0.0) + c.get('total', 0.0)

    for p in payments:
        if p.get('status') != 'paid':
            continue
        bid = p.get('booking_id')
        if not bid:
            continue
        payments_by_booking[bid] = payments_by_booking.get(bid, 0.0) + p.get('amount', 0.0)

    enriched = []
    for booking in bookings:
        bid = booking.get('id')
        total_charges = charges_by_booking.get(bid, 0.0)
        total_paid = payments_by_booking.get(bid, 0.0)
        balance = total_charges - total_paid

        enriched.append({
            **booking,
            'guest': guest_map.get(booking.get('guest_id')),
            'room': room_map.get(booking.get('room_id')),
            'balance': balance,
        })

    return enriched

@api_router.get("/frontdesk/inhouse")
async def get_inhouse_guests(current_user: User = Depends(get_current_user)):
    """Get all currently checked-in guests (optimized to avoid N+1 queries)"""
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': 'checked_in'
    }, {'_id': 0}).to_list(1000)

    if not bookings:
        return []

    guest_ids = {b.get('guest_id') for b in bookings if b.get('guest_id')}
    room_ids = {b.get('room_id') for b in bookings if b.get('room_id')}

    guests = []
    rooms = []
    if guest_ids:
        guests = await db.guests.find({'id': {'$in': list(guest_ids)}}, {'_id': 0}).to_list(len(guest_ids))
    if room_ids:
        rooms = await db.rooms.find({'id': {'$in': list(room_ids)}}, {'_id': 0}).to_list(len(room_ids))

    guest_map = {g['id']: g for g in guests if 'id' in g}
    room_map = {r['id']: r for r in rooms if 'id' in r}

    enriched = []
    for booking in bookings:
        enriched.append({
            **booking,
            'guest': guest_map.get(booking.get('guest_id')),
            'room': room_map.get(booking.get('room_id')),
        })

    return enriched

# ============= HOUSEKEEPING ENDPOINTS =============

@api_router.get("/housekeeping/tasks")
async def get_housekeeping_tasks(status: Optional[str] = None, current_user: User = Depends(get_current_user)):
    """Get housekeeping tasks"""
    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status
    
    tasks = await db.housekeeping_tasks.find(query, {'_id': 0}).to_list(1000)
    
    # Enrich with room data
    enriched = []
    for task in tasks:
        room = await db.rooms.find_one({'id': task['room_id']}, {'_id': 0})
        enriched.append({**task, 'room': room})
    
    return enriched

@api_router.post("/housekeeping/tasks")
async def create_housekeeping_task(
    room_id: str,
    task_type: str,
    priority: str = "normal",
    notes: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Create housekeeping task"""
    task = HousekeepingTask(
        tenant_id=current_user.tenant_id,
        room_id=room_id,
        task_type=task_type,
        priority=priority,
        notes=notes
    )
    
    task_dict = task.model_dump()
    task_dict['created_at'] = task_dict['created_at'].isoformat()
    await db.housekeeping_tasks.insert_one(task_dict)
    
    return task

@api_router.put("/housekeeping/tasks/{task_id}")
async def update_housekeeping_task(
    task_id: str,
    status: Optional[str] = None,
    assigned_to: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Update housekeeping task"""
    updates = {}
    if status:
        updates['status'] = status
        if status == 'in_progress' and not updates.get('started_at'):
            updates['started_at'] = datetime.now(timezone.utc).isoformat()
        elif status == 'completed':
            updates['completed_at'] = datetime.now(timezone.utc).isoformat()
            
            # Update room status
            task = await db.housekeeping_tasks.find_one({'id': task_id}, {'_id': 0})
            if task and task['task_type'] == 'cleaning':
                await db.rooms.update_one(
                    {'id': task['room_id']},
                    {'$set': {'status': 'inspected', 'last_cleaned': datetime.now(timezone.utc).isoformat()}}
                )
    
    if assigned_to:
        updates['assigned_to'] = assigned_to
    
    await db.housekeeping_tasks.update_one(
        {'id': task_id, 'tenant_id': current_user.tenant_id},
        {'$set': updates}
    )
    
    task = await db.housekeeping_tasks.find_one({'id': task_id}, {'_id': 0})
    return task

@api_router.get("/housekeeping/room-status")
async def get_room_status_board(current_user: User = Depends(get_current_user)):
    """Get room status board"""
    rooms = await db.rooms.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    
    status_counts = {
        'available': 0,
        'occupied': 0,
        'dirty': 0,
        'cleaning': 0,
        'inspected': 0,
        'maintenance': 0,
        'out_of_order': 0
    }
    
    for room in rooms:
        status_counts[room['status']] += 1
    
    return {
        'rooms': rooms,
        'status_counts': status_counts,
        'total_rooms': len(rooms)
    }

# ============= CHANNEL MANAGER ENDPOINTS =============

@api_router.post("/channel/rates")
async def update_channel_rates(
    room_type: str,
    channel: str,
    start_date: str,
    end_date: str,
    rate: float,
    availability: int,
    current_user: User = Depends(get_current_user)
):
    """Update rates for a channel"""
    start = datetime.fromisoformat(start_date).date()
    end = datetime.fromisoformat(end_date).date()
    
    current_date = start
    while current_date <= end:
        channel_rate = ChannelRate(
            tenant_id=current_user.tenant_id,
            room_type=room_type,
            channel=channel,
            date=current_date,
            rate=rate,
            availability=availability
        )
        
        # Update or insert
        await db.channel_rates.update_one(
            {
                'tenant_id': current_user.tenant_id,
                'room_type': room_type,
                'channel': channel,
                'date': current_date.isoformat()
            },
            {'$set': channel_rate.model_dump()},
            upsert=True
        )
        
        current_date += timedelta(days=1)
    
    return {'message': f'Rates updated for {(end - start).days + 1} days'}

@api_router.get("/channel/rates")
async def get_channel_rates(
    room_type: Optional[str] = None,
    channel: Optional[str] = None,
    start_date: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get channel rates"""
    query = {'tenant_id': current_user.tenant_id}
    if room_type:
        query['room_type'] = room_type
    if channel:
        query['channel'] = channel
    if start_date:
        query['date'] = {'$gte': start_date}
    
    rates = await db.channel_rates.find(query, {'_id': 0}).to_list(1000)
    return rates

@api_router.get("/channel/parity-check")
async def check_rate_parity(room_type: str, date_str: str, current_user: User = Depends(get_current_user)):
    """Check rate parity across channels"""
    rates = await db.channel_rates.find({
        'tenant_id': current_user.tenant_id,
        'room_type': room_type,
        'date': date_str
    }, {'_id': 0}).to_list(1000)
    
    if not rates:
        return {'parity': True, 'rates': [], 'issues': []}
    
    rate_values = [r['rate'] for r in rates]
    min_rate = min(rate_values)
    max_rate = max(rate_values)
    
    parity = (max_rate - min_rate) <= 0.01  # Allow 1 cent difference
    
    issues = []
    if not parity:
        for rate in rates:
            if rate['rate'] != max_rate:
                issues.append({
                    'channel': rate['channel'],
                    'rate': rate['rate'],
                    'difference': max_rate - rate['rate']
                })
    
    return {
        'parity': parity,
        'rates': rates,
        'issues': issues
    }

@api_router.get("/channel/performance")
async def get_channel_performance(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get channel performance analytics"""
    query = {'tenant_id': current_user.tenant_id}
    
    if start_date and end_date:
        query['check_in'] = {
            '$gte': start_date,
            '$lte': end_date
        }
    
    bookings = await db.bookings.find(query, {'_id': 0}).to_list(1000)
    
    channel_stats = {}
    for booking in bookings:
        channel = booking['channel']
        if channel not in channel_stats:
            channel_stats[channel] = {
                'bookings': 0,
                'revenue': 0.0,
                'avg_rate': 0.0
            }
        
        channel_stats[channel]['bookings'] += 1
        channel_stats[channel]['revenue'] += booking['total_amount']
    
    # Calculate averages
    for channel in channel_stats:
        if channel_stats[channel]['bookings'] > 0:
            channel_stats[channel]['avg_rate'] = channel_stats[channel]['revenue'] / channel_stats[channel]['bookings']
    
    return channel_stats

# ============= REPORTING ENDPOINTS =============

@api_router.get("/reports/occupancy")
async def get_occupancy_report(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user)
):
    """Get occupancy report"""
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['confirmed', 'checked_in', 'checked_out']},
        '$or': [
            {'check_in': {'$gte': start.isoformat(), '$lte': end.isoformat()}},
            {'check_out': {'$gte': start.isoformat(), '$lte': end.isoformat()}},
            {'check_in': {'$lte': start.isoformat()}, 'check_out': {'$gte': end.isoformat()}}
        ]
    }, {'_id': 0}).to_list(1000)
    
    days = (end - start).days + 1
    total_room_nights = total_rooms * days
    occupied_room_nights = 0
    
    for booking in bookings:
        check_in = datetime.fromisoformat(booking['check_in'])
        check_out = datetime.fromisoformat(booking['check_out'])
        
        overlap_start = max(start, check_in)
        overlap_end = min(end, check_out)
        
        if overlap_start < overlap_end:
            nights = (overlap_end - overlap_start).days
            occupied_room_nights += nights
    
    occupancy_rate = (occupied_room_nights / total_room_nights * 100) if total_room_nights > 0 else 0
    
    return {
        'start_date': start_date,
        'end_date': end_date,
        'total_rooms': total_rooms,
        'total_room_nights': total_room_nights,
        'occupied_room_nights': occupied_room_nights,
        'occupancy_rate': round(occupancy_rate, 2)
    }

@api_router.get("/reports/revenue")
async def get_revenue_report(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user)
):
    """Get revenue report with ADR and RevPAR"""
    start = datetime.fromisoformat(start_date)
    end = datetime.fromisoformat(end_date)
    
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['checked_in', 'checked_out']},
        'check_in': {'$gte': start.isoformat(), '$lte': end.isoformat()}
    }, {'_id': 0}).to_list(1000)
    
    total_revenue = sum(b['total_amount'] for b in bookings)
    total_room_nights = sum((datetime.fromisoformat(b['check_out']) - datetime.fromisoformat(b['check_in'])).days for b in bookings)
    
    adr = (total_revenue / total_room_nights) if total_room_nights > 0 else 0
    
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    days = (end - start).days + 1
    total_available_room_nights = total_rooms * days
    
    rev_par = (total_revenue / total_available_room_nights) if total_available_room_nights > 0 else 0
    
    # Get folio charges by type
    folio_charges = await db.folio_charges.find({
        'tenant_id': current_user.tenant_id,
        'date': {'$gte': start.isoformat(), '$lte': end.isoformat()}
    }, {'_id': 0}).to_list(1000)
    
    revenue_by_type = {}
    for charge in folio_charges:
        charge_type = charge['charge_type']
        if charge_type not in revenue_by_type:
            revenue_by_type[charge_type] = 0.0
        revenue_by_type[charge_type] += charge['total']
    
    return {
        'start_date': start_date,
        'end_date': end_date,
        'total_revenue': round(total_revenue, 2),
        'room_nights_sold': total_room_nights,
        'adr': round(adr, 2),
        'rev_par': round(rev_par, 2),
        'revenue_by_type': revenue_by_type,
        'bookings_count': len(bookings)
    }

@api_router.get("/reports/daily-summary")
async def get_daily_summary(date_str: Optional[str] = None, current_user: User = Depends(get_current_user)):
    """Get daily summary report"""
    if not date_str:
        target_date = datetime.now(timezone.utc).date()
    else:
        target_date = datetime.fromisoformat(date_str).date()
    
    start_of_day = datetime.combine(target_date, datetime.min.time())
    end_of_day = datetime.combine(target_date, datetime.max.time())
    
    # Arrivals
    arrivals = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': start_of_day.isoformat(), '$lte': end_of_day.isoformat()}
    })
    
    # Departures
    departures = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_out': {'$gte': start_of_day.isoformat(), '$lte': end_of_day.isoformat()}
    })
    
    # In-house
    inhouse = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': 'checked_in'
    })
    
    # Total rooms
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    
    # Revenue
    payments = await db.payments.find({
        'tenant_id': current_user.tenant_id,
        'status': 'paid',
        'processed_at': {'$gte': start_of_day.isoformat(), '$lte': end_of_day.isoformat()}
    }, {'_id': 0}).to_list(1000)
    
    daily_revenue = sum(p['amount'] for p in payments)
    
    return {
        'date': target_date.isoformat(),
        'arrivals': arrivals,
        'departures': departures,
        'inhouse': inhouse,
        'total_rooms': total_rooms,
        'occupancy_rate': round((inhouse / total_rooms * 100) if total_rooms > 0 else 0, 2),
        'daily_revenue': round(daily_revenue, 2)
    }

@api_router.get("/reports/forecast")
async def get_forecast(days: int = 30, current_user: User = Depends(get_current_user)):
    """Get occupancy forecast"""
    today = datetime.now(timezone.utc).date()
    forecast_data = []
    
    for i in range(days):
        forecast_date = today + timedelta(days=i)
        start_of_day = datetime.combine(forecast_date, datetime.min.time())
        end_of_day = datetime.combine(forecast_date, datetime.max.time())
        
        bookings = await db.bookings.count_documents({
            'tenant_id': current_user.tenant_id,
            'status': {'$in': ['confirmed', 'checked_in']},
            'check_in': {'$lte': end_of_day.isoformat()},
            'check_out': {'$gte': start_of_day.isoformat()}
        })
        
        total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
        occupancy = round((bookings / total_rooms * 100) if total_rooms > 0 else 0, 2)
        
        forecast_data.append({
            'date': forecast_date.isoformat(),
            'bookings': bookings,
            'total_rooms': total_rooms,
            'occupancy_rate': occupancy
        })
    
    return forecast_data

