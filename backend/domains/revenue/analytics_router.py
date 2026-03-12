"""
Domain Router: Analytics

Extracted from legacy_routes.py — GM Dashboard, pickup analysis, anomaly detection, revenue analytics.
"""
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta
import uuid

from core.database import db
from core.security import get_current_user, security, JWT_SECRET, JWT_ALGORITHM
from core.helpers import require_module
from core.cache import cached
from models.schemas import User

router = APIRouter(prefix="/api", tags=["analytics"])


# --------------------------------------------------------------------------
# GM Dashboard - Pickup Analysis & Anomaly Detection
# --------------------------------------------------------------------------

@router.get("/dashboard/gm/pickup-analysis")
async def get_pickup_analysis(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get pickup analysis for revenue management"""
    current_user = await get_current_user(credentials)
    
    if not start_date:
        start_date = datetime.now(timezone.utc).replace(day=1)
    else:
        start_date = datetime.fromisoformat(start_date)
    
    if not end_date:
        # Next 30 days
        end_date = datetime.now(timezone.utc) + timedelta(days=30)
    else:
        end_date = datetime.fromisoformat(end_date)
    
    # Get bookings for date range
    pickup_data = []
    
    # Group by booking date (created_at)
    pipeline = [
        {
            '$match': {
                'tenant_id': current_user.tenant_id,
                'check_in': {
                    '$gte': start_date,
                    '$lte': end_date
                },
                'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
            }
        },
        {
            '$group': {
                '_id': {
                    'stay_date': '$check_in',
                    'booking_date': '$created_at'
                },
                'room_count': {'$sum': 1},
                'total_revenue': {'$sum': '$total_amount'}
            }
        },
        {
            '$sort': {'_id.stay_date': 1}
        }
    ]
    
    async for doc in db.bookings.aggregate(pipeline):
        stay_date = doc['_id']['stay_date']
        booking_date = doc['_id']['booking_date']
        
        # Calculate days before arrival
        days_before = (stay_date - booking_date).days if stay_date and booking_date else 0
        
        pickup_data.append({
            'stay_date': stay_date.date().isoformat() if stay_date else None,
            'booking_date': booking_date.date().isoformat() if booking_date else None,
            'days_before_arrival': days_before,
            'rooms': doc['room_count'],
            'revenue': doc['total_revenue']
        })
    
    # Calculate pickup velocity
    total_rooms = sum(d['rooms'] for d in pickup_data)
    total_revenue = sum(d['revenue'] for d in pickup_data)
    
    # Group by days_before_arrival for trend analysis
    pickup_trends = {}
    for data in pickup_data:
        days_key = data['days_before_arrival']
        if days_key not in pickup_trends:
            pickup_trends[days_key] = {'rooms': 0, 'revenue': 0}
        pickup_trends[days_key]['rooms'] += data['rooms']
        pickup_trends[days_key]['revenue'] += data['revenue']
    
    return {
        'pickup_data': pickup_data,
        'pickup_trends': pickup_trends
    }

@router.get("/revenue/market-segment-breakdown")
async def get_market_segment_breakdown(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get revenue breakdown by market segment (OTA, Direct, Corporate, Group)"""
    current_user = await get_current_user(credentials)
    
    today = datetime.now(timezone.utc)
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

@router.get("/channel-manager/overview")
async def get_channel_manager_overview(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get channel manager overview with all connected channels"""
    current_user = await get_current_user(credentials)
    
    # Mock channel data (in production, get from actual channel manager API)
    channels = {
        'booking_com': {
            'name': 'Booking.com',
            'status': 'connected',
            'last_sync': (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
            'active_listings': 24,
            'bookings_today': 3,
            'revenue_today': 1250.0,
            'avg_rating': 8.7,
            'commission_rate': 15.0
        },
        'expedia': {
            'name': 'Expedia',
            'status': 'connected',
            'last_sync': (datetime.now(timezone.utc) - timedelta(minutes=8)).isoformat(),
            'active_listings': 24,
            'bookings_today': 2,
            'revenue_today': 890.0,
            'avg_rating': 4.3,
            'commission_rate': 18.0
        },
        'airbnb': {
            'name': 'Airbnb',
            'status': 'connected',
            'last_sync': (datetime.now(timezone.utc) - timedelta(minutes=12)).isoformat(),
            'active_listings': 15,
            'bookings_today': 1,
            'revenue_today': 450.0,
            'avg_rating': 4.8,
            'commission_rate': 14.0
        },
        'direct': {
            'name': 'Direct Website',
            'status': 'active',
            'last_sync': datetime.now(timezone.utc).isoformat(),
            'active_listings': 24,
            'bookings_today': 4,
            'revenue_today': 1800.0,
            'avg_rating': 4.9,
            'commission_rate': 0.0
        }
    }
    
    total_bookings = sum(ch['bookings_today'] for ch in channels.values())
    total_revenue = sum(ch['revenue_today'] for ch in channels.values())
    
    return {
        'channels': channels,
        'summary': {
            'total_channels': len(channels),
            'connected_channels': sum(1 for ch in channels.values() if ch['status'] == 'connected'),
            'total_bookings_today': total_bookings,
            'total_revenue_today': round(total_revenue, 2)
        }
    }

@router.get("/channel-manager/rate-comparison")
async def get_channel_rate_comparison(
    date: Optional[str] = None,
    room_type: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Compare rates across all channels"""
    current_user = await get_current_user(credentials)
    
    if not date:
        date = datetime.now(timezone.utc).date().isoformat()
    
    # Mock rate comparison data
    rate_comparison = {
        'date': date,
        'room_type': room_type or 'Standard',
        'channels': {
            'booking_com': {'rate': 150.0, 'available': True, 'rank': 3},
            'expedia': {'rate': 155.0, 'available': True, 'rank': 2},
            'airbnb': {'rate': 145.0, 'available': True, 'rank': 1},
            'direct': {'rate': 140.0, 'available': True, 'rank': 4},
            'agoda': {'rate': 158.0, 'available': True, 'rank': 5}
        },
        'your_rate': 140.0,
        'competitor_avg': 152.0,
        'recommendation': 'increase',
        'suggested_rate': 148.0
    }
    
    return rate_comparison

@router.get("/channel-manager/revenue-by-channel")
async def get_revenue_by_channel(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get revenue breakdown by channel"""
    current_user = await get_current_user(credentials)
    
    today = datetime.now(timezone.utc)
    if not start_date:
        start_date = (today - timedelta(days=30)).date().isoformat()
    if not end_date:
        end_date = today.date().isoformat()
    
    # Aggregate actual bookings by source
    channel_revenue = {}
    
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': start_date, '$lte': end_date}
    }):
        source = booking.get('source', 'Direct')
        amount = booking.get('total_amount', 0)
        
        if source not in channel_revenue:
            channel_revenue[source] = {
                'revenue': 0,
                'bookings': 0,
                'avg_value': 0
            }
        
        channel_revenue[source]['revenue'] += amount
        channel_revenue[source]['bookings'] += 1
    
    # Calculate averages
    for channel in channel_revenue:
        if channel_revenue[channel]['bookings'] > 0:
            channel_revenue[channel]['avg_value'] = round(
                channel_revenue[channel]['revenue'] / channel_revenue[channel]['bookings'], 2
            )
        channel_revenue[channel]['revenue'] = round(channel_revenue[channel]['revenue'], 2)
    
    total_revenue = sum(ch['revenue'] for ch in channel_revenue.values())
    
    return {
        'channels': channel_revenue,
        'total_revenue': round(total_revenue, 2),
        'period': {
            'start': start_date,
            'end': end_date
        }
    }

@router.post("/frontdesk/assign-room")
async def assign_room_to_booking(
    assignment_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Assign a specific room to a booking"""
    current_user = await get_current_user(credentials)
    
    booking_id = assignment_data.get('booking_id')
    room_id = assignment_data.get('room_id')
    
    # Check if room is available
    room = await db.rooms.find_one({'id': room_id, 'tenant_id': current_user.tenant_id})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    
    if room.get('status') not in ['available', 'inspected']:
        raise HTTPException(status_code=400, detail="Room not available")
    
    # Update booking with room
    await db.bookings.update_one(
        {'id': booking_id, 'tenant_id': current_user.tenant_id},
        {'$set': {
            'room_id': room_id,
            'room_number': room['room_number'],
            'room_assigned_at': datetime.now(timezone.utc).isoformat(),
            'room_assigned_by': current_user.name
        }}
    )
    
    # Update room status
    await db.rooms.update_one(
        {'id': room_id},
        {'$set': {
            'current_booking_id': booking_id,
            'status': 'reserved'
        }}
    )
    
    return {
        'message': 'Room assigned successfully',
        'booking_id': booking_id,
        'room_number': room['room_number']
    }

@router.get("/frontdesk/search-bookings")
@cached(ttl=180, key_prefix="frontdesk_search_bookings")  # Cache for 3 min
async def search_bookings(
    query: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    status: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Search bookings by various criteria"""
    current_user = await get_current_user(credentials)
    
    search_query = {'tenant_id': current_user.tenant_id}
    
    # Text search on booking number or guest name
    if query:
        search_query['$or'] = [
            {'booking_number': {'$regex': query, '$options': 'i'}},
            {'guest_name': {'$regex': query, '$options': 'i'}}
        ]
    
    # Date range filter
    if date_from or date_to:
        date_filter = {}
        if date_from:
            date_filter['$gte'] = date_from
        if date_to:
            date_filter['$lte'] = date_to
        if date_filter:
            search_query['check_in'] = date_filter
    
    # Status filter
    if status:
        search_query['status'] = status
    
    bookings = []
    async for booking in db.bookings.find(search_query).sort('created_at', -1).limit(50):
        booking.pop('_id', None)
        bookings.append(booking)
    
    return {
        'bookings': bookings,
        'count': len(bookings)
    }

@router.get("/frontdesk/available-rooms")
@cached(ttl=120, key_prefix="frontdesk_available_rooms")  # Cache for 2 min
async def get_available_rooms_for_assignment(
    check_in: str,
    check_out: str,
    room_type: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get available rooms for a specific date range"""
    current_user = await get_current_user(credentials)
    
    query = {
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['available', 'inspected']},
        'is_active': True
    }
    
    if room_type:
        query['room_type'] = room_type
    
    available_rooms = []
    async for room in db.rooms.find(query).sort('room_number', 1):
        room.pop('_id', None)
        available_rooms.append(room)
    
    return {
        'rooms': available_rooms,
        'count': len(available_rooms),
        'check_in': check_in,
        'check_out': check_out
    }


@router.post("/channel-manager/push-availability")
async def push_channel_availability(
    check_in: str,
    check_out: str,
    room_type: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Simulate pushing availability to Booking.com and other OTAs.

    Uses the existing /pms/rooms/availability logic to get availability
    and then normalizes it to a Booking-like payload via BookingAdapter.
    """
    current_user = await get_current_user(credentials)

    # Fetch availability from PMS
    rooms = await check_room_availability(check_in, check_out, room_type, current_user)

    # Only handle booking.com for now via adapter (simulated)
    connection = await db.channel_connections.find_one({
        'tenant_id': current_user.tenant_id,
        'channel_type': ChannelType.BOOKING_COM,
    })

    adapter_result = None
    if connection:
        adapter = BookingAdapter(connection)
        adapter_result = await adapter.push_availability({
            'rooms': rooms,
            'check_in': check_in,
            'check_out': check_out,
        })

    # Log sync
    sync_log = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'channel': ChannelType.BOOKING_COM,
        'sync_type': 'availability',
        'status': 'success',
        'duration_ms': 0,
        'records_synced': len(rooms),
        'error_message': None,
        'initiator_type': 'hotel_user',
        'initiator_name': current_user.name,
        'initiator_id': current_user.id,
        'ip_address': None,
    }
    await db.channel_sync_logs.insert_one(sync_log)

    return {
        'message': 'Availability push simulated successfully',
        'rooms_count': len(rooms),
        'booking_adapter': adapter_result,
    }


from booking_adapter import BookingAdapter
from booking_availability import normalize_availability_response


@router.post("/channel-manager/update-rates")
async def update_channel_rates(
    rate_update: dict,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Update rates across channels"""
    current_user = await get_current_user(credentials)
    
    # Only admins and revenue managers can update rates
    if current_user.role not in ['admin', 'revenue_manager', 'gm']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Determine initiator info
    ip_address = request.headers.get('x-forwarded-for') or request.client.host
    initiator_type = 'hotel_user'
    if getattr(current_user, 'is_staff', False):
        initiator_type = 'pms_staff'
    
    # Log the rate update (for detailed audit)
    rate_log = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'channels': rate_update.get('channels', []),
        'room_type': rate_update.get('room_type'),
        'new_rate': rate_update.get('new_rate'),
        'date_from': rate_update.get('date_from'),
        'date_to': rate_update.get('date_to'),
        'updated_by': current_user.name,
        'updated_by_id': current_user.id,
        'initiator_type': initiator_type,
        'ip_address': ip_address,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    
    await db.rate_updates.insert_one(rate_log)
    
    # Also push a summary entry to channel_sync_logs for UI sync history
    sync_log = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'channel': ','.join(rate_update.get('channels', [])) or 'multiple',
        'sync_type': 'rates',
        'status': 'success',
        'duration_ms': rate_update.get('duration_ms', 0),
        'records_synced': rate_update.get('records_synced', 0),
        'error_message': None,
        'initiator_type': initiator_type,
        'initiator_name': current_user.name,
        'initiator_id': current_user.id,
        'ip_address': ip_address
    }
    await db.channel_sync_logs.insert_one(sync_log)

    # Call Booking.com adapter in simulated mode if booking_com is selected
    channels = rate_update.get('channels', []) or []
    if 'booking_com' in channels:
        connection = await db.channel_connections.find_one({
            'tenant_id': current_user.tenant_id,
            'channel_type': ChannelType.BOOKING_COM,
        })
        if connection:
            adapter = BookingAdapter(connection)
            # Simulate push (no real HTTP call yet)
            await adapter.push_rates(rate_update)
    
    return {
        'message': 'Rates updated successfully',
        'channels_updated': len(rate_update.get('channels', [])),
        'log_id': rate_log['id']
    }

@router.get("/pos/outlet-sales-breakdown")
async def get_outlet_sales_breakdown(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get F&B sales breakdown by outlet"""
    current_user = await get_current_user(credentials)
    
    today = datetime.now(timezone.utc)
    if not start_date:
        start_date = (today - timedelta(days=7)).date().isoformat()
    if not end_date:
        end_date = today.date().isoformat()
    
    # Mock outlet data (in production, get from db.outlets)
    outlet_sales = {
        'Restaurant': {'sales': 0, 'orders': 0, 'avg_ticket': 0},
        'Bar': {'sales': 0, 'orders': 0, 'avg_ticket': 0},
        'Room Service': {'sales': 0, 'orders': 0, 'avg_ticket': 0},
        'Poolside': {'sales': 0, 'orders': 0, 'avg_ticket': 0}
    }
    
    # Aggregate POS orders (mock logic)
    async for order in db.pos_orders.find({
        'tenant_id': current_user.tenant_id,
        'created_at': {'$gte': start_date, '$lte': end_date}
    }):
        outlet = order.get('outlet_name', 'Restaurant')
        if outlet not in outlet_sales:
            outlet_sales[outlet] = {'sales': 0, 'orders': 0, 'avg_ticket': 0}
        
        outlet_sales[outlet]['sales'] += order.get('total_amount', 0)
        outlet_sales[outlet]['orders'] += 1
    
    # Calculate averages
    for outlet in outlet_sales:
        if outlet_sales[outlet]['orders'] > 0:
            outlet_sales[outlet]['avg_ticket'] = round(
                outlet_sales[outlet]['sales'] / outlet_sales[outlet]['orders'], 2
            )
        outlet_sales[outlet]['sales'] = round(outlet_sales[outlet]['sales'], 2)
    
    total_sales = sum(o['sales'] for o in outlet_sales.values())
    
    return {
        'outlets': outlet_sales,
        'total_sales': round(total_sales, 2),
        'period': {'start': start_date, 'end': end_date}
    }

@router.get("/pos/inventory-movements")
async def get_inventory_movements(
    item_id: Optional[str] = None,
    movement_type: Optional[str] = None,
    date_from: Optional[str] = None,
    limit: int = 50,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get inventory movements (stock in/out)"""
    current_user = await get_current_user(credentials)
    
    query = {'tenant_id': current_user.tenant_id}
    
    if item_id:
        query['item_id'] = item_id
    if movement_type:
        query['movement_type'] = movement_type
    if date_from:
        query['created_at'] = {'$gte': date_from}
    
    movements = []
    async for movement in db.inventory_movements.find(query).sort('created_at', -1).limit(limit):
        movement.pop('_id', None)
        movements.append(movement)
    
    # Mock data if empty
    if len(movements) == 0:
        mock_items = ['Yumurta', 'Süt', 'Ekmek', 'Domates', 'Peynir']
        mock_movements = []
        for i, item in enumerate(mock_items):
            mock_movements.append({
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'item_id': f'item_{i}',
                'item_name': item,
                'movement_type': 'out' if i % 2 == 0 else 'in',
                'quantity': random.randint(5, 50),
                'unit': 'kg' if i < 3 else 'adet',
                'reference': f'Order #{random.randint(1000, 9999)}',
                'notes': 'Günlük kullanım' if i % 2 == 0 else 'Tedarikçi teslimatı',
                'created_by': current_user.name,
                'created_at': (datetime.now(timezone.utc) - timedelta(hours=i*2)).isoformat()
            })
        movements = mock_movements
    
    return {
        'movements': movements,
        'count': len(movements)
    }

@router.post("/pos/inventory-movement")
async def create_inventory_movement(
    movement_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Create a new inventory movement"""
    current_user = await get_current_user(credentials)
    
    movement = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'item_id': movement_data.get('item_id'),
        'item_name': movement_data.get('item_name'),
        'movement_type': movement_data.get('movement_type'),  # 'in' or 'out'
        'quantity': movement_data.get('quantity'),
        'unit': movement_data.get('unit'),
        'reference': movement_data.get('reference'),
        'notes': movement_data.get('notes', ''),
        'created_by': current_user.name,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    
    await db.inventory_movements.insert_one(movement)
    
    # Update item stock
    if movement['movement_type'] == 'in':
        await db.inventory_items.update_one(
            {'id': movement['item_id']},
            {'$inc': {'stock': movement['quantity']}}
        )
    else:
        await db.inventory_items.update_one(
            {'id': movement['item_id']},
            {'$inc': {'stock': -movement['quantity']}}
        )
    
    return {
        'message': 'Movement recorded',
        'movement_id': movement['id']
    }

@router.get("/maintenance/reports/weekly")
async def get_weekly_maintenance_report(
    week_offset: int = 0,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get weekly maintenance report"""
    current_user = await get_current_user(credentials)
    
    today = datetime.now(timezone.utc)
    week_start = today - timedelta(days=today.weekday() + (week_offset * 7))
    week_end = week_start + timedelta(days=6)
    
    # Get all maintenance tasks for the week
    query = {
        'tenant_id': current_user.tenant_id,
        'created_at': {
            '$gte': week_start.isoformat(),
            '$lte': week_end.isoformat()
        }
    }
    
    all_tasks = []
    async for task in db.maintenance_tasks.find(query):
        task.pop('_id', None)
        all_tasks.append(task)
    
    # Calculate statistics
    total_tasks = len(all_tasks)
    completed_tasks = len([t for t in all_tasks if t.get('status') == 'completed'])
    in_progress_tasks = len([t for t in all_tasks if t.get('status') == 'in_progress'])
    pending_tasks = len([t for t in all_tasks if t.get('status') == 'pending'])
    emergency_tasks = len([t for t in all_tasks if t.get('priority') == 'emergency'])
    
    # Calculate SLA compliance
    sla_compliant = 0
    for task in all_tasks:
        if task.get('status') == 'completed' and task.get('sla_met'):
            sla_compliant += 1
    
    sla_compliance_rate = round((sla_compliant / completed_tasks * 100) if completed_tasks > 0 else 0, 1)
    completion_rate = round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0, 1)
    
    # Calculate average response time
    response_times = [t.get('response_time_minutes', 0) for t in all_tasks if t.get('response_time_minutes')]
    avg_response_time = round(sum(response_times) / len(response_times), 1) if response_times else 0
    
    # Group by category
    by_category = {}
    for task in all_tasks:
        category = task.get('category', 'other')
        if category not in by_category:
            by_category[category] = {'count': 0, 'completed': 0}
        by_category[category]['count'] += 1
        if task.get('status') == 'completed':
            by_category[category]['completed'] += 1
    
    # Group by priority
    by_priority = {
        'emergency': len([t for t in all_tasks if t.get('priority') == 'emergency']),
        'high': len([t for t in all_tasks if t.get('priority') == 'high']),
        'normal': len([t for t in all_tasks if t.get('priority') == 'normal']),
        'low': len([t for t in all_tasks if t.get('priority') == 'low'])
    }
    
    # Top issues
    issue_counts = {}
    for task in all_tasks:
        issue = task.get('issue_type', 'Other')
        issue_counts[issue] = issue_counts.get(issue, 0) + 1
    
    top_issues = sorted(issue_counts.items(), key=lambda x: x[1], reverse=True)[:5]
    
    return {
        'period': {
            'start': week_start.date().isoformat(),
            'end': week_end.date().isoformat(),
            'week_number': week_start.isocalendar()[1]
        },
        'summary': {
            'total_tasks': total_tasks,
            'completed': completed_tasks,
            'in_progress': in_progress_tasks,
            'pending': pending_tasks,
            'emergency': emergency_tasks,
            'completion_rate': completion_rate,
            'sla_compliance': sla_compliance_rate,
            'avg_response_time': avg_response_time
        },
        'by_category': by_category,
        'by_priority': by_priority,
        'top_issues': [{'issue': issue, 'count': count} for issue, count in top_issues],
        'tasks': all_tasks[:10]  # Latest 10 tasks
    }

@router.get("/maintenance/reports/monthly")
async def get_monthly_maintenance_report(
    month: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get monthly maintenance report"""
    current_user = await get_current_user(credentials)
    
    if not month:
        month = datetime.now(timezone.utc).strftime('%Y-%m')
    
    year, m = month.split('-')
    month_start = datetime(int(year), int(m), 1, tzinfo=timezone.utc)
    
    # Calculate month end
    if int(m) == 12:
        month_end = datetime(int(year) + 1, 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
    else:
        month_end = datetime(int(year), int(m) + 1, 1, tzinfo=timezone.utc) - timedelta(days=1)
    
    # Get all maintenance tasks for the month
    query = {
        'tenant_id': current_user.tenant_id,
        'created_at': {
            '$gte': month_start.isoformat(),
            '$lte': month_end.isoformat()
        }
    }
    
    all_tasks = []
    async for task in db.maintenance_tasks.find(query):
        task.pop('_id', None)
        all_tasks.append(task)
    
    # Calculate statistics
    total_tasks = len(all_tasks)
    completed_tasks = len([t for t in all_tasks if t.get('status') == 'completed'])
    in_progress_tasks = len([t for t in all_tasks if t.get('status') == 'in_progress'])
    pending_tasks = len([t for t in all_tasks if t.get('status') == 'pending'])
    cancelled_tasks = len([t for t in all_tasks if t.get('status') == 'cancelled'])
    
    # Calculate costs
    total_cost = sum(t.get('cost', 0) for t in all_tasks if t.get('cost'))
    parts_cost = sum(t.get('parts_cost', 0) for t in all_tasks if t.get('parts_cost'))
    labor_cost = sum(t.get('labor_cost', 0) for t in all_tasks if t.get('labor_cost'))
    
    # Calculate times
    response_times = [t.get('response_time_minutes', 0) for t in all_tasks if t.get('response_time_minutes')]
    resolution_times = [t.get('resolution_time_minutes', 0) for t in all_tasks if t.get('resolution_time_minutes')]
    
    avg_response_time = round(sum(response_times) / len(response_times), 1) if response_times else 0
    avg_resolution_time = round(sum(resolution_times) / len(resolution_times), 1) if resolution_times else 0
    
    # SLA compliance
    sla_compliant = len([t for t in all_tasks if t.get('status') == 'completed' and t.get('sla_met')])
    sla_compliance_rate = round((sla_compliant / completed_tasks * 100) if completed_tasks > 0 else 0, 1)
    
    # Group by week
    by_week = {}
    for task in all_tasks:
        created_at = datetime.fromisoformat(task['created_at'])
        week_num = created_at.isocalendar()[1]
        if week_num not in by_week:
            by_week[week_num] = {'total': 0, 'completed': 0}
        by_week[week_num]['total'] += 1
        if task.get('status') == 'completed':
            by_week[week_num]['completed'] += 1
    
    # Group by category
    by_category = {}
    for task in all_tasks:
        category = task.get('category', 'other')
        if category not in by_category:
            by_category[category] = {'count': 0, 'cost': 0}
        by_category[category]['count'] += 1
        by_category[category]['cost'] += task.get('cost', 0)
    
    # Most active rooms
    room_counts = {}
    for task in all_tasks:
        room = task.get('location', 'Unknown')
        room_counts[room] = room_counts.get(room, 0) + 1
    
    most_active_rooms = sorted(room_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    
    # Staff performance
    staff_performance = {}
    for task in all_tasks:
        if task.get('assigned_to'):
            staff = task['assigned_to']
            if staff not in staff_performance:
                staff_performance[staff] = {'tasks': 0, 'completed': 0, 'avg_time': 0}
            staff_performance[staff]['tasks'] += 1
            if task.get('status') == 'completed':
                staff_performance[staff]['completed'] += 1
    
    return {
        'period': {
            'month': month,
            'start': month_start.date().isoformat(),
            'end': month_end.date().isoformat()
        },
        'summary': {
            'total_tasks': total_tasks,
            'completed': completed_tasks,
            'in_progress': in_progress_tasks,
            'pending': pending_tasks,
            'cancelled': cancelled_tasks,
            'completion_rate': round((completed_tasks / total_tasks * 100) if total_tasks > 0 else 0, 1),
            'sla_compliance': sla_compliance_rate,
            'avg_response_time': avg_response_time,
            'avg_resolution_time': avg_resolution_time
        },
        'costs': {
            'total': round(total_cost, 2),
            'parts': round(parts_cost, 2),
            'labor': round(labor_cost, 2)
        },
        'by_week': by_week,
        'by_category': by_category,
        'most_active_rooms': [{'room': room, 'tasks': count} for room, count in most_active_rooms],
        'staff_performance': staff_performance
    }

@router.get("/maintenance/reports/summary")
async def get_maintenance_summary(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get quick maintenance summary for mobile dashboard"""
    current_user = await get_current_user(credentials)
    
    today = datetime.now(timezone.utc)
    
    # Today's stats
    today_tasks = await db.maintenance_tasks.count_documents({
        'tenant_id': current_user.tenant_id,
        'created_at': {'$regex': f'^{today.date().isoformat()}'}
    })
    
    # Active tasks
    active_tasks = await db.maintenance_tasks.count_documents({
        'tenant_id': current_user.tenant_id,
        'status': {'$in': ['pending', 'in_progress']}
    })
    
    # Emergency tasks
    emergency_tasks = await db.maintenance_tasks.count_documents({
        'tenant_id': current_user.tenant_id,
        'priority': 'emergency',
        'status': {'$ne': 'completed'}
    })
    
    # This month's completion rate
    month_start = today.replace(day=1)
    month_tasks = []
    async for task in db.maintenance_tasks.find({
        'tenant_id': current_user.tenant_id,
        'created_at': {'$gte': month_start.isoformat()}
    }):
        month_tasks.append(task)
    
    completed_this_month = len([t for t in month_tasks if t.get('status') == 'completed'])
    completion_rate = round((completed_this_month / len(month_tasks) * 100) if month_tasks else 0, 1)
    
    return {
        'today_tasks': today_tasks,
        'active_tasks': active_tasks,
        'emergency_tasks': emergency_tasks,
        'completion_rate': completion_rate,
        'alerts': [
            {
                'type': 'emergency',
                'message': f'{emergency_tasks} acil görev bekliyor',
                'priority': 'high'
            } if emergency_tasks > 0 else None
        ]
    }

@router.get("/maintenance/calendar")
async def get_maintenance_calendar(
    month: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get routine maintenance calendar"""
    current_user = await get_current_user(credentials)
    
    if not month:
        month = datetime.now(timezone.utc).strftime('%Y-%m')
    
    # Get scheduled maintenance tasks
    start_date = f"{month}-01"
    year, m = month.split('-')
    next_month = int(m) + 1
    next_year = year
    if next_month > 12:
        next_month = 1
        next_year = str(int(year) + 1)
    end_date = f"{next_year}-{next_month:02d}-01"
    
    calendar_items = []
    
    # Mock routine maintenance schedule
    routine_tasks = [
        {'task': 'HVAC Filtre Değişimi', 'frequency': 'monthly', 'day': 5, 'duration': '2h'},
        {'task': 'Elektrik Panosu Kontrolü', 'frequency': 'monthly', 'day': 10, 'duration': '3h'},
        {'task': 'Yangın Alarm Testi', 'frequency': 'monthly', 'day': 15, 'duration': '1h'},
        {'task': 'Asansör Bakımı', 'frequency': 'monthly', 'day': 20, 'duration': '4h'},
        {'task': 'Su Tesisatı Kontrolü', 'frequency': 'monthly', 'day': 25, 'duration': '3h'}
    ]
    
    for task in routine_tasks:
        calendar_items.append({
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'task_name': task['task'],
            'task_type': 'routine',
            'scheduled_date': f"{month}-{task['day']:02d}",
            'frequency': task['frequency'],
            'estimated_duration': task['duration'],
            'status': 'scheduled',
            'assigned_to': 'Maintenance Team'
        })
    
    return {
        'calendar': calendar_items,
        'month': month,
        'total_tasks': len(calendar_items)
    }

@router.post("/maintenance/schedule-routine")
async def schedule_routine_maintenance(
    schedule_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Schedule a routine maintenance task"""
    current_user = await get_current_user(credentials)
    
    schedule = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'task_name': schedule_data.get('task_name'),
        'task_type': 'routine',
        'frequency': schedule_data.get('frequency'),  # daily, weekly, monthly, yearly
        'scheduled_date': schedule_data.get('scheduled_date'),
        'estimated_duration': schedule_data.get('estimated_duration'),
        'assigned_to': schedule_data.get('assigned_to'),
        'status': 'scheduled',
        'created_by': current_user.name,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    
    await db.maintenance_schedule.insert_one(schedule)
    
    return {
        'message': 'Routine maintenance scheduled',
        'schedule_id': schedule['id']
    }

@router.get("/pos/shift-metrics")
async def get_shift_metrics(
    date: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get POS sales metrics by shift (morning/afternoon/evening)"""
    current_user = await get_current_user(credentials)
    
    if not date:
        date = datetime.now(timezone.utc).date().isoformat()
    
    shift_data = {
        'morning': {'sales': 0, 'orders': 0, 'hours': '06:00-14:00'},
        'afternoon': {'sales': 0, 'orders': 0, 'hours': '14:00-18:00'},
        'evening': {'sales': 0, 'orders': 0, 'hours': '18:00-23:00'}
    }
    
    # Mock shift calculation
    async for order in db.pos_orders.find({
        'tenant_id': current_user.tenant_id,
        'order_date': date
    }):
        created_at = order.get('created_at', '')
        if isinstance(created_at, str):
            hour = int(created_at.split('T')[1].split(':')[0]) if 'T' in created_at else 12
        else:
            hour = created_at.hour if hasattr(created_at, 'hour') else 12
        
        if 6 <= hour < 14:
            shift = 'morning'
        elif 14 <= hour < 18:
            shift = 'afternoon'
        else:
            shift = 'evening'
        
        shift_data[shift]['sales'] += order.get('total_amount', 0)
        shift_data[shift]['orders'] += 1
    
    # Round values
    for shift in shift_data:
        shift_data[shift]['sales'] = round(shift_data[shift]['sales'], 2)
    
    return {'shifts': shift_data, 'date': date}

@router.post("/housekeeping/room/{room_id}/photo")
async def upload_room_photo(
    room_id: str,
    photo_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Upload a photo for room inspection"""
    current_user = await get_current_user(credentials)
    
    photo = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'room_id': room_id,
        'photo_url': photo_data.get('photo_url'),  # Base64 or URL
        'photo_type': photo_data.get('photo_type', 'inspection'),  # inspection, damage, before, after
        'notes': photo_data.get('notes', ''),
        'uploaded_by': current_user.name,
        'uploaded_at': datetime.now(timezone.utc).isoformat()
    }
    
    await db.room_photos.insert_one(photo)
    
    return {
        'message': 'Photo uploaded',
        'photo_id': photo['id']
    }

@router.get("/housekeeping/room/{room_id}/photos")
async def get_room_photos(
    room_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get all photos for a room"""
    current_user = await get_current_user(credentials)
    
    photos = []
    async for photo in db.room_photos.find({
        'tenant_id': current_user.tenant_id,
        'room_id': room_id
    }).sort('uploaded_at', -1):
        photo.pop('_id', None)
        photos.append(photo)
    
    return {'photos': photos, 'count': len(photos)}

@router.post("/housekeeping/room/{room_id}/checklist")
async def complete_room_checklist(
    room_id: str,
    checklist_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Complete room cleaning checklist"""
    current_user = await get_current_user(credentials)
    
    checklist = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'room_id': room_id,
        'items': checklist_data.get('items', []),  # List of checklist items with status
        'completed_by': current_user.name,
        'completed_at': datetime.now(timezone.utc).isoformat(),
        'total_items': len(checklist_data.get('items', [])),
        'completed_items': sum(1 for item in checklist_data.get('items', []) if item.get('checked')),
        'notes': checklist_data.get('notes', '')
    }
    
    await db.room_checklists.insert_one(checklist)
    
    return {
        'message': 'Checklist completed',
        'checklist_id': checklist['id'],
        'completion_rate': f"{checklist['completed_items']}/{checklist['total_items']}"
    }

@router.post("/housekeeping/lost-found/update-status")
async def update_lost_found_status(
    item_id: str,
    status_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Update lost & found item status"""
    current_user = await get_current_user(credentials)
    
    new_status = status_data.get('status')  # found, claimed, expired, disposed
    
    update_data = {
        'status': new_status,
        'updated_at': datetime.now(timezone.utc).isoformat(),
        'updated_by': current_user.name
    }
    
    if new_status == 'claimed':
        update_data['claimed_by_name'] = status_data.get('claimed_by_name')
        update_data['claimed_by_id'] = status_data.get('claimed_by_id')
        update_data['claimed_at'] = datetime.now(timezone.utc).isoformat()
    
    await db.lost_found_items.update_one(
        {'id': item_id, 'tenant_id': current_user.tenant_id},
        {'$set': update_data}
    )
    
    return {
        'message': 'Status updated',
        'item_id': item_id,
        'new_status': new_status
    }

@router.post("/housekeeping/lost-found/transfer")
async def transfer_lost_found_item(
    item_id: str,
    transfer_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Transfer lost & found item to another department/location"""
    current_user = await get_current_user(credentials)
    
    transfer_record = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'item_id': item_id,
        'from_location': transfer_data.get('from_location'),
        'to_location': transfer_data.get('to_location'),
        'transferred_by': current_user.name,
        'notes': transfer_data.get('notes', ''),
        'transferred_at': datetime.now(timezone.utc).isoformat()
    }
    
    await db.lost_found_transfers.insert_one(transfer_record)
    
    # Update item location
    await db.lost_found_items.update_one(
        {'id': item_id},
        {'$set': {
            'current_location': transfer_data.get('to_location'),
            'last_transfer_at': datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {
        'message': 'Item transferred',
        'transfer_id': transfer_record['id']
    }

@router.get("/housekeeping/lost-found/item/{item_id}/history")
async def get_lost_found_history(
    item_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get full history of a lost & found item"""
    current_user = await get_current_user(credentials)
    
    # Get item details
    item = await db.lost_found_items.find_one({
        'id': item_id,
        'tenant_id': current_user.tenant_id
    })
    
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    item.pop('_id', None)
    
    # Get transfer history
    transfers = []
    async for transfer in db.lost_found_transfers.find({
        'tenant_id': current_user.tenant_id,
        'item_id': item_id
    }).sort('transferred_at', 1):
        transfer.pop('_id', None)
        transfers.append(transfer)
    
    return {
        'item': item,
        'transfers': transfers,
        'transfer_count': len(transfers)
    }

@router.post("/housekeeping/qr-room-access")
async def qr_room_access(
    access_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Record room access via QR code (start/end cleaning)"""
    current_user = await get_current_user(credentials)
    
    room_id = access_data.get('room_id')
    room_number = access_data.get('room_number')
    action = access_data.get('action')  # 'start' or 'end'
    
    # Check if there's an active session
    active_session = await db.room_access_logs.find_one({
        'tenant_id': current_user.tenant_id,
        'room_id': room_id,
        'staff_id': current_user.id,
        'end_time': None
    })
    
    if action == 'start':
        if active_session:
            raise HTTPException(status_code=400, detail="Active cleaning session already exists")
        
        # Create new session
        session = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'room_id': room_id,
            'room_number': room_number,
            'staff_id': current_user.id,
            'staff_name': current_user.name,
            'start_time': datetime.now(timezone.utc).isoformat(),
            'end_time': None,
            'duration_minutes': None,
            'notes': access_data.get('notes', ''),
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        
        await db.room_access_logs.insert_one(session)
        
        # Update room status to cleaning
        await db.rooms.update_one(
            {'id': room_id},
            {'$set': {'status': 'cleaning'}}
        )
        
        return {
            'message': 'Cleaning started',
            'session_id': session['id'],
            'start_time': session['start_time']
        }
    
    elif action == 'end':
        if not active_session:
            raise HTTPException(status_code=400, detail="No active cleaning session found")
        
        # End session
        end_time = datetime.now(timezone.utc)
        start_time = datetime.fromisoformat(active_session['start_time'])
        duration = (end_time - start_time).total_seconds() / 60  # minutes
        
        await db.room_access_logs.update_one(
            {'id': active_session['id']},
            {'$set': {
                'end_time': end_time.isoformat(),
                'duration_minutes': round(duration, 1)
            }}
        )
        
        # Update room status to inspected
        await db.rooms.update_one(
            {'id': room_id},
            {'$set': {'status': 'inspected'}}
        )
        
        return {
            'message': 'Cleaning completed',
            'session_id': active_session['id'],
            'duration_minutes': round(duration, 1),
            'start_time': active_session['start_time'],
            'end_time': end_time.isoformat()
        }
    
    else:
        raise HTTPException(status_code=400, detail="Invalid action")

@router.get("/housekeeping/my-active-sessions")
async def get_my_active_sessions(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get current user's active cleaning sessions"""
    current_user = await get_current_user(credentials)
    
    sessions = []
    async for session in db.room_access_logs.find({
        'tenant_id': current_user.tenant_id,
        'staff_id': current_user.id,
        'end_time': None
    }):
        session.pop('_id', None)
        
        # Calculate elapsed time
        start_time = datetime.fromisoformat(session['start_time'])
        elapsed = (datetime.now(timezone.utc) - start_time).total_seconds() / 60
        session['elapsed_minutes'] = round(elapsed, 1)
        
        sessions.append(session)
    
    return {
        'active_sessions': sessions,
        'count': len(sessions)
    }

@router.get("/housekeeping/room-access-logs")
async def get_room_access_logs(
    room_id: Optional[str] = None,
    staff_id: Optional[str] = None,
    date: Optional[str] = None,
    limit: int = 50,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get room access logs with filters"""
    current_user = await get_current_user(credentials)
    
    query = {'tenant_id': current_user.tenant_id}
    
    if room_id:
        query['room_id'] = room_id
    if staff_id:
        query['staff_id'] = staff_id
    if date:
        query['created_at'] = {'$regex': f'^{date}'}
    
    logs = []
    async for log in db.room_access_logs.find(query).sort('created_at', -1).limit(limit):
        log.pop('_id', None)
        logs.append(log)
    
    # Calculate stats
    total_duration = sum(log.get('duration_minutes', 0) for log in logs if log.get('duration_minutes'))
    avg_duration = round(total_duration / len([l for l in logs if l.get('duration_minutes')]), 1) if logs else 0
    
    return {
        'logs': logs,
        'count': len(logs),
        'stats': {
            'total_duration_minutes': round(total_duration, 1),
            'avg_duration_minutes': avg_duration,
            'completed_sessions': len([l for l in logs if l.get('end_time')])
        }
    }

@router.get("/housekeeping/checklist-template")
async def get_checklist_template(
    room_type: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get standard cleaning checklist template"""
    current_user = await get_current_user(credentials)
    
    standard_template = [
        {'id': '1', 'category': 'bedroom', 'item': 'Yatak takımları değiştirildi', 'required': True},
        {'id': '2', 'category': 'bedroom', 'item': 'Yastıklar kontrol edildi', 'required': True},
        {'id': '3', 'category': 'bedroom', 'item': 'Mobilyalar silindi', 'required': True},
        {'id': '4', 'category': 'bathroom', 'item': 'Banyo temizlendi', 'required': True},
        {'id': '5', 'category': 'bathroom', 'item': 'Havlular yenilendi', 'required': True},
        {'id': '6', 'category': 'bathroom', 'item': 'Sıhhi tesisat kontrol edildi', 'required': False},
        {'id': '7', 'category': 'general', 'item': 'Zemin süpürüldü/silindi', 'required': True},
        {'id': '8', 'category': 'general', 'item': 'Çöpler toplandı', 'required': True},
        {'id': '9', 'category': 'general', 'item': 'Minibar kontrol edildi', 'required': False},
        {'id': '10', 'category': 'general', 'item': 'Klima çalışıyor', 'required': True},
        {'id': '11', 'category': 'general', 'item': 'TV ve kumanda çalışıyor', 'required': False},
        {'id': '12', 'category': 'general', 'item': 'Pencereler temiz', 'required': False}
    ]
    
    return {
        'template': standard_template,
        'room_type': room_type or 'Standard'
    }

@router.get("/crm/guest/{guest_id}/notes")
async def get_guest_notes(
    guest_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get CRM notes for a guest"""
    current_user = await get_current_user(credentials)
    
    notes = []
    async for note in db.crm_notes.find({
        'tenant_id': current_user.tenant_id,
        'guest_id': guest_id
    }).sort('created_at', -1):
        note.pop('_id', None)
        notes.append(note)
    
    return {'notes': notes, 'guest_id': guest_id}

@router.post("/crm/guest/{guest_id}/note")
async def add_guest_note(
    guest_id: str,
    note_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Add a CRM note for a guest"""
    current_user = await get_current_user(credentials)
    
    note = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'guest_id': guest_id,
        'content': note_data.get('content'),
        'category': note_data.get('category', 'general'),
        'created_by': current_user.name,
        'created_at': datetime.now(timezone.utc).isoformat()
    }
    
    await db.crm_notes.insert_one(note)
    return {'message': 'Note added successfully', 'note_id': note['id']}

@router.post("/approvals/request")
async def create_approval_request(
    request_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Create a new approval request"""
    current_user = await get_current_user(credentials)
    
    approval_types = ['discount', 'rate_override', 'budget', 'refund', 'complimentary']
    
    if request_data.get('type') not in approval_types:
        raise HTTPException(status_code=400, detail="Invalid approval type")
    
    approval = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'type': request_data.get('type'),
        'amount': request_data.get('amount', 0),
        'reason': request_data.get('reason', ''),
        'booking_id': request_data.get('booking_id'),
        'requested_by': current_user.id,
        'requested_by_name': current_user.name,
        'requested_by_email': current_user.email,
        'status': 'pending',
        'priority': request_data.get('priority', 'normal'),
        'metadata': request_data.get('metadata', {}),
        'created_at': datetime.now(timezone.utc).isoformat(),
        'approved_at': None,
        'approved_by': None,
        'approved_by_name': None,
        'rejection_reason': None
    }
    
    await db.approval_requests.insert_one(approval)
    
    return {
        'message': 'Approval request created',
        'approval_id': approval['id'],
        'status': 'pending'
    }

@router.get("/approvals/pending")
async def get_pending_approvals(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get all pending approval requests"""
    current_user = await get_current_user(credentials)
    
    # Only managers and admins can see approvals
    if current_user.role not in ['admin', 'manager', 'gm']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    approvals = []
    urgent_count = 0
    async for approval in db.approval_requests.find({
        'tenant_id': current_user.tenant_id,
        'status': 'pending'
    }).sort('created_at', -1):
        approval.pop('_id', None)
        # Check if urgent (more than 24 hours old or marked as urgent)
        created_at = approval.get('created_at')
        is_urgent = False
        if created_at:
            from datetime import datetime, timezone
            if isinstance(created_at, str):
                created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
            else:
                created_dt = created_at
            hours_waiting = (datetime.now(timezone.utc) - created_dt).total_seconds() / 3600
            is_urgent = hours_waiting > 24 or approval.get('priority') == 'urgent'
        if is_urgent:
            urgent_count += 1
        approvals.append(approval)
    
    return {
        'approvals': approvals,
        'count': len(approvals),
        'urgent_count': urgent_count
    }

@router.get("/approvals/my-requests")
async def get_my_approval_requests(
    status: Optional[str] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get approval requests created by current user"""
    current_user = await get_current_user(credentials)
    
    query = {
        'tenant_id': current_user.tenant_id,
        'requested_by': current_user.id
    }
    
    if status:
        query['status'] = status
    
    requests = []
    async for approval in db.approval_requests.find(query).sort('created_at', -1):
        approval.pop('_id', None)
        requests.append(approval)
    
    return {
        'requests': requests,
        'count': len(requests)
    }

@router.post("/approvals/{approval_id}/approve")
async def approve_request(
    approval_id: str,
    approval_note: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Approve an approval request"""
    current_user = await get_current_user(credentials)
    
    # Only managers and admins can approve
    if current_user.role not in ['admin', 'manager', 'gm']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    approval = await db.approval_requests.find_one({
        'id': approval_id,
        'tenant_id': current_user.tenant_id
    })
    
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    
    if approval['status'] != 'pending':
        raise HTTPException(status_code=400, detail="Request already processed")
    
    await db.approval_requests.update_one(
        {'id': approval_id},
        {
            '$set': {
                'status': 'approved',
                'approved_at': datetime.now(timezone.utc).isoformat(),
                'approved_by': current_user.id,
                'approved_by_name': current_user.name,
                'approval_note': approval_note.get('note', '')
            }
        }
    )
    
    return {
        'message': 'Request approved',
        'approval_id': approval_id,
        'status': 'approved'
    }

@router.post("/approvals/{approval_id}/reject")
async def reject_request(
    approval_id: str,
    rejection_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Reject an approval request"""
    current_user = await get_current_user(credentials)
    
    # Only managers and admins can reject
    if current_user.role not in ['admin', 'manager', 'gm']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    approval = await db.approval_requests.find_one({
        'id': approval_id,
        'tenant_id': current_user.tenant_id
    })
    
    if not approval:
        raise HTTPException(status_code=404, detail="Approval request not found")
    
    if approval['status'] != 'pending':
        raise HTTPException(status_code=400, detail="Request already processed")
    
    await db.approval_requests.update_one(
        {'id': approval_id},
        {
            '$set': {
                'status': 'rejected',
                'approved_at': datetime.now(timezone.utc).isoformat(),
                'approved_by': current_user.id,
                'approved_by_name': current_user.name,
                'rejection_reason': rejection_data.get('reason', 'No reason provided')
            }
        }
    )
    
    return {
        'message': 'Request rejected',
        'approval_id': approval_id,
        'status': 'rejected'
    }

@router.get("/gm/team-performance")
async def get_team_performance(
    department: Optional[str] = None,
    period: str = 'month',
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _: None = Depends(require_module("gm_dashboards")),
):
    """Get team performance metrics"""
    current_user = await get_current_user(credentials)
    
    # Mock team performance data
    team_data = {
        'front_desk': {
            'department': 'Front Desk',
            'staff_count': 8,
            'avg_performance_score': 92.5,
            'tasks_completed': 245,
            'guest_satisfaction': 4.6,
            'top_performer': {'name': 'Ayşe Yılmaz', 'score': 98},
            'metrics': {
                'check_ins': 156,
                'check_outs': 148,
                'avg_time': '4.2 min'
            }
        },
        'housekeeping': {
            'department': 'Housekeeping',
            'staff_count': 12,
            'avg_performance_score': 88.3,
            'tasks_completed': 612,
            'guest_satisfaction': 4.4,
            'top_performer': {'name': 'Fatma Demir', 'score': 95},
            'metrics': {
                'rooms_cleaned': 612,
                'avg_time': '28 min',
                'quality_score': 4.5
            }
        },
        'maintenance': {
            'department': 'Maintenance',
            'staff_count': 6,
            'avg_performance_score': 91.2,
            'tasks_completed': 89,
            'guest_satisfaction': 4.5,
            'top_performer': {'name': 'Mehmet Koç', 'score': 96},
            'metrics': {
                'tasks_completed': 89,
                'avg_response_time': '18 min',
                'sla_compliance': 94
            }
        },
        'fnb': {
            'department': 'F&B',
            'staff_count': 15,
            'avg_performance_score': 87.8,
            'tasks_completed': 1240,
            'guest_satisfaction': 4.3,
            'top_performer': {'name': 'Ali Şahin', 'score': 93},
            'metrics': {
                'orders_served': 1240,
                'avg_time': '12 min',
                'quality_score': 4.3
            }
        }
    }
    
    if department:
        return team_data.get(department, {})
    
    return {
        'departments': team_data,
        'period': period,
        'overall_performance': round(sum(d['avg_performance_score'] for d in team_data.values()) / len(team_data), 1)
    }

@router.get("/gm/complaints")
async def get_complaints(
    status: Optional[str] = None,
    priority: Optional[str] = None,
    limit: int = 50,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get guest complaints"""
    current_user = await get_current_user(credentials)
    
    query = {'tenant_id': current_user.tenant_id}
    
    if status:
        query['status'] = status
    if priority:
        query['priority'] = priority
    
    complaints = []
    async for complaint in db.complaints.find(query).sort('created_at', -1).limit(limit):
        complaint.pop('_id', None)
        complaints.append(complaint)
    
    # If no complaints, create mock data
    if len(complaints) == 0:
        mock_complaints = [
            {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'guest_name': 'Ahmet Yılmaz',
                'room_number': '205',
                'category': 'cleanliness',
                'subject': 'Oda temizliği yetersiz',
                'description': 'Banyoda havlu eksikliği var',
                'priority': 'normal',
                'status': 'open',
                'created_at': (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat(),
                'assigned_to': 'Housekeeping',
                'resolution': None
            },
            {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'guest_name': 'Zeynep Kaya',
                'room_number': '312',
                'category': 'noise',
                'subject': 'Gürültü şikayeti',
                'description': 'Yan odadan yüksek ses geliyor',
                'priority': 'high',
                'status': 'in_progress',
                'created_at': (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat(),
                'assigned_to': 'Front Desk',
                'resolution': None
            }
        ]
        complaints = mock_complaints
    
    return {
        'complaints': complaints,
        'count': len(complaints),
        'by_status': {
            'open': sum(1 for c in complaints if c['status'] == 'open'),
            'in_progress': sum(1 for c in complaints if c['status'] == 'in_progress'),
            'resolved': sum(1 for c in complaints if c['status'] == 'resolved')
        }
    }

@router.post("/gm/complaint")
async def create_complaint(
    complaint_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Create a new complaint"""
    current_user = await get_current_user(credentials)
    
    complaint = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'guest_name': complaint_data.get('guest_name'),
        'room_number': complaint_data.get('room_number'),
        'category': complaint_data.get('category'),
        'subject': complaint_data.get('subject'),
        'description': complaint_data.get('description'),
        'priority': complaint_data.get('priority', 'normal'),
        'status': 'open',
        'created_at': datetime.now(timezone.utc).isoformat(),
        'created_by': current_user.name,
        'assigned_to': complaint_data.get('assigned_to'),
        'resolution': None
    }
    
    await db.complaints.insert_one(complaint)
    
    return {
        'message': 'Complaint created',
        'complaint_id': complaint['id']
    }

@router.post("/gm/complaint/{complaint_id}/resolve")
async def resolve_complaint(
    complaint_id: str,
    resolution_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Resolve a complaint"""
    current_user = await get_current_user(credentials)
    
    await db.complaints.update_one(
        {'id': complaint_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'status': 'resolved',
                'resolution': resolution_data.get('resolution'),
                'resolved_by': current_user.name,
                'resolved_at': datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {
        'message': 'Complaint resolved',
        'complaint_id': complaint_id
    }

@router.post("/notifications/send")
async def send_notification(
    notification_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Send a notification to user(s)"""
    current_user = await get_current_user(credentials)
    
    notification = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'type': notification_data.get('type', 'info'),  # info, warning, alert, success
        'category': notification_data.get('category', 'general'),  # revenue, maintenance, booking, etc
        'title': notification_data.get('title'),
        'message': notification_data.get('message'),
        'priority': notification_data.get('priority', 'normal'),  # low, normal, high, critical
        'user_id': notification_data.get('user_id'),  # specific user or None for broadcast
        'read': False,
        'action_url': notification_data.get('action_url'),
        'metadata': notification_data.get('metadata', {}),
        'created_at': datetime.now(timezone.utc).isoformat(),
        'expires_at': notification_data.get('expires_at')
    }
    
    await db.notifications.insert_one(notification)
    
    return {
        'message': 'Notification sent',
        'notification_id': notification['id']
    }

@router.get("/notifications/my")
async def get_my_notifications(
    unread_only: bool = False,
    limit: int = 50,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get notifications for current user"""
    current_user = await get_current_user(credentials)
    
    query = {
        'tenant_id': current_user.tenant_id,
        '$or': [
            {'user_id': current_user.id},
            {'user_id': None}  # Broadcast notifications
        ]
    }
    
    if unread_only:
        query['read'] = False
    
    notifications = []
    async for notif in db.notifications.find(query).sort('created_at', -1).limit(limit):
        notif.pop('_id', None)
        notifications.append(notif)
    
    unread_count = await db.notifications.count_documents({
        'tenant_id': current_user.tenant_id,
        '$or': [
            {'user_id': current_user.id},
            {'user_id': None}
        ],
        'read': False
    })
    
    return {
        'notifications': notifications,
        'unread_count': unread_count,
        'total': len(notifications)
    }

@router.post("/notifications/{notification_id}/mark-read")
async def mark_notification_read(
    notification_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Mark a notification as read"""
    current_user = await get_current_user(credentials)
    
    await db.notifications.update_one(
        {
            'id': notification_id,
            'tenant_id': current_user.tenant_id
        },
        {
            '$set': {'read': True}
        }
    )
    
    return {'message': 'Notification marked as read'}

@router.post("/notifications/mark-all-read")
async def mark_all_notifications_read(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Mark all notifications as read for current user"""
    current_user = await get_current_user(credentials)
    
    result = await db.notifications.update_many(
        {
            'tenant_id': current_user.tenant_id,
            '$or': [
                {'user_id': current_user.id},
                {'user_id': None}
            ],
            'read': False
        },
        {
            '$set': {'read': True}
        }
    )
    
    return {
        'message': 'All notifications marked as read',
        'count': result.modified_count
    }

@router.post("/alerts/check-and-notify")
async def check_alerts_and_notify(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Check system for alert conditions and send notifications"""
    current_user = await get_current_user(credentials)
    
    alerts_sent = []
    
    # Check revenue drop
    today = datetime.now(timezone.utc)
    yesterday = today - timedelta(days=1)
    
    # Revenue alert
    revenue_today = 0
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': today.date().isoformat(),
        'status': {'$in': ['confirmed', 'checked_in']}
    }):
        revenue_today += booking.get('total_amount', 0)
    
    revenue_yesterday = 0
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': yesterday.date().isoformat(),
        'status': {'$in': ['confirmed', 'checked_in', 'checked_out']}
    }):
        revenue_yesterday += booking.get('total_amount', 0)
    
    if revenue_yesterday > 0 and revenue_today < revenue_yesterday * 0.7:
        # Revenue dropped by 30%+
        alert = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'type': 'alert',
            'category': 'revenue',
            'title': '⚠️ Gelir Düşüşü Tespit Edildi',
            'message': f'Bugünkü gelir dünle karşılaştırıldığında %{int((1 - revenue_today/revenue_yesterday) * 100)} düşük',
            'priority': 'high',
            'user_id': None,
            'read': False,
            'metadata': {
                'today_revenue': revenue_today,
                'yesterday_revenue': revenue_yesterday
            },
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        await db.notifications.insert_one(alert)
        alerts_sent.append('revenue_drop')
    
    # Overbooking check
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    bookings_today = await db.bookings.count_documents({
        'tenant_id': current_user.tenant_id,
        'check_in': today.date().isoformat(),
        'status': {'$in': ['confirmed', 'guaranteed']}
    })
    
    if bookings_today > total_rooms:
        alert = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'type': 'alert',
            'category': 'booking',
            'title': '🚨 Overbooking Riski',
            'message': f'{bookings_today} rezervasyon var, sadece {total_rooms} oda mevcut',
            'priority': 'critical',
            'user_id': None,
            'read': False,
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        await db.notifications.insert_one(alert)
        alerts_sent.append('overbooking')
    
    # Maintenance emergency
    emergency_tasks = await db.maintenance_tasks.count_documents({
        'tenant_id': current_user.tenant_id,
        'priority': 'emergency',
        'status': {'$ne': 'completed'}
    })
    
    if emergency_tasks > 0:
        alert = {
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'type': 'alert',
            'category': 'maintenance',
            'title': '🔧 Acil Bakım Görevi',
            'message': f'{emergency_tasks} acil bakım görevi bekliyor',
            'priority': 'high',
            'user_id': None,
            'read': False,
            'created_at': datetime.now(timezone.utc).isoformat()
        }
        await db.notifications.insert_one(alert)
        alerts_sent.append('maintenance_emergency')
    
    return {
        'message': 'Alert check completed',
        'alerts_sent': alerts_sent,
        'count': len(alerts_sent)
    }

@router.get("/monitoring/api-metrics")
async def get_api_metrics(
    hours: int = 24,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get API performance metrics"""
    current_user = await get_current_user(credentials)
    
    # Only IT staff and admins
    if current_user.role not in ['admin', 'it_manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    # Mock API metrics (in production, collect from actual monitoring)
    now = datetime.now(timezone.utc)
    metrics = []
    
    for i in range(24):
        timestamp = now - timedelta(hours=23-i)
        metrics.append({
            'timestamp': timestamp.isoformat(),
            'avg_response_time': round(50 + (i % 5) * 10 + random.uniform(-10, 10), 2),
            'requests_per_minute': 120 + random.randint(-20, 20),
            'error_rate': round(random.uniform(0.5, 2.5), 2),
            'success_rate': round(100 - random.uniform(0.5, 2.5), 2)
        })
    
    return {
        'metrics': metrics,
        'summary': {
            'avg_response_time': round(sum(m['avg_response_time'] for m in metrics) / len(metrics), 2),
            'total_requests': sum(m['requests_per_minute'] for m in metrics) * 60,
            'avg_error_rate': round(sum(m['error_rate'] for m in metrics) / len(metrics), 2),
            'uptime_percentage': 99.8
        }
    }

@router.get("/monitoring/system-health")
async def get_system_health_detailed(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get detailed system health metrics"""
    current_user = await get_current_user(credentials)
    
    # Only IT staff and admins
    if current_user.role not in ['admin', 'it_manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    import psutil
    import platform
    
    # Get system info
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        system_info = {
            'cpu': {
                'usage_percent': cpu_percent,
                'cores': psutil.cpu_count(),
                'status': 'healthy' if cpu_percent < 80 else 'warning'
            },
            'memory': {
                'total_gb': round(memory.total / (1024**3), 2),
                'used_gb': round(memory.used / (1024**3), 2),
                'percent': memory.percent,
                'status': 'healthy' if memory.percent < 80 else 'warning'
            },
            'disk': {
                'total_gb': round(disk.total / (1024**3), 2),
                'used_gb': round(disk.used / (1024**3), 2),
                'percent': disk.percent,
                'status': 'healthy' if disk.percent < 85 else 'warning'
            },
            'platform': {
                'system': platform.system(),
                'python_version': platform.python_version()
            }
        }
    except Exception as e:
        system_info = {
            'error': str(e),
            'message': 'Unable to collect system metrics'
        }
    
    # Check database connection
    try:
        await db.command('ping')
        db_status = 'operational'
        db_response_time = 5  # Mock
    except:
        db_status = 'error'
        db_response_time = 0
    
    # Service statuses
    services = {
        'pms': {'status': 'operational', 'response_time': 45, 'uptime': 99.9},
        'pos': {'status': 'operational', 'response_time': 38, 'uptime': 99.7},
        'channel_manager': {'status': 'operational', 'response_time': 120, 'uptime': 99.5},
        'database': {'status': db_status, 'response_time': db_response_time, 'uptime': 99.95},
        'api_gateway': {'status': 'operational', 'response_time': 15, 'uptime': 99.99}
    }
    
    # Calculate overall health score
    operational_count = sum(1 for s in services.values() if s['status'] == 'operational')
    health_score = (operational_count / len(services)) * 100
    
    return {
        'system': system_info,
        'services': services,
        'health_score': round(health_score, 1),
        'timestamp': datetime.now(timezone.utc).isoformat()
    }

@router.get("/monitoring/alert-thresholds")
async def get_alert_thresholds(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get configured alert thresholds"""
    current_user = await get_current_user(credentials)
    
    thresholds = {
        'api_response_time': {
            'warning': 200,  # ms
            'critical': 500,
            'current': 65
        },
        'error_rate': {
            'warning': 2.0,  # percent
            'critical': 5.0,
            'current': 1.2
        },
        'cpu_usage': {
            'warning': 80,  # percent
            'critical': 95,
            'current': 45
        },
        'memory_usage': {
            'warning': 80,
            'critical': 95,
            'current': 62
        },
        'disk_usage': {
            'warning': 85,
            'critical': 95,
            'current': 58
        },
        'database_connections': {
            'warning': 80,
            'critical': 95,
            'current': 35
        }
    }
    
    return {
        'thresholds': thresholds,
        'alerts_triggered': 0
    }

@router.post("/monitoring/set-threshold")
async def set_alert_threshold(
    threshold_data: dict,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Set or update an alert threshold"""
    current_user = await get_current_user(credentials)
    
    # Only IT staff and admins
    if current_user.role not in ['admin', 'it_manager']:
        raise HTTPException(status_code=403, detail="Access denied")
    
    threshold = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'metric': threshold_data.get('metric'),
        'warning_value': threshold_data.get('warning_value'),
        'critical_value': threshold_data.get('critical_value'),
        'updated_by': current_user.name,
        'updated_at': datetime.now(timezone.utc).isoformat()
    }
    
    await db.alert_thresholds.insert_one(threshold)
    
    return {
        'message': 'Threshold updated',
        'threshold_id': threshold['id']
    }

@router.get("/security/login-logs")
async def get_security_login_logs(
    limit: int = 50,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get security login logs (successful and failed attempts)"""
    current_user = await get_current_user(credentials)
    
    # Create login logs collection if not exists
    logs = []
    
    async for log in db.login_logs.find({
        'tenant_id': current_user.tenant_id
    }).sort('timestamp', -1).limit(limit):
        log.pop('_id', None)
        logs.append(log)
    
    # If no logs, create some mock data for demo
    if len(logs) == 0:
        mock_logs = [
            {
                'id': str(uuid.uuid4()),
                'tenant_id': current_user.tenant_id,
                'email': 'admin@hotel.com',
                'success': True,
                'ip_address': '192.168.1.100',
                'user_agent': 'Mozilla/5.0',
                'timestamp': (datetime.now(timezone.utc) - timedelta(hours=i)).isoformat()
            }
            for i in range(10)
        ]
        logs = mock_logs
    
    return {'logs': logs, 'total': len(logs)}

@router.get("/revenue/adr-tracking")
async def get_adr_tracking(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get ADR tracking with last year vs forecast vs actual comparison"""
    current_user = await get_current_user(credentials)
    
    today = datetime.now(timezone.utc)
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


