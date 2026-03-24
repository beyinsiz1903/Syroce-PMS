"""
Channel Manager / Operations Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.database import db
from core.security import (
    get_current_user,
    security,
)
from models.enums import ChannelStatus, ChannelType, ParityStatus
from models.schemas import RoomMappingCreate, User

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func): return func
        return decorator



class ChannelConnectionCreate(BaseModel):
    channel_name: str
    channel_type: str = "ota"
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    property_id: Optional[str] = None
    enabled: bool = True
    sync_config: Optional[Dict[str, Any]] = None

router = APIRouter(prefix="/api", tags=["Channel Manager / Operations"])


# ── Inline Models ──

class PermissionCheckRequest(BaseModel):
    permission: str


@router.get("/channel-manager/connections")
@cached(ttl=300, key_prefix="cm_connections")  # Cache for 5 min
async def get_channel_connections(current_user: User = Depends(get_current_user)):
    """Get all channel connections"""
    connections = await db.channel_connections.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).to_list(100)
    return {'connections': connections, 'count': len(connections)}



@router.post("/channel-manager/connections")
async def create_channel_connection(
    payload: ChannelConnectionCreate,
    current_user: User = Depends(get_current_user)
):
    """Create a new channel connection"""
    connection = ChannelConnection(
        tenant_id=current_user.tenant_id,
        channel_type=payload.channel_type,
        channel_name=payload.channel_name,
        property_id=payload.property_id,
        api_endpoint=payload.api_endpoint,
        api_key=payload.api_key,
        api_secret=payload.api_secret,
        sync_rate_availability=payload.sync_rate_availability,
        sync_reservations=payload.sync_reservations,
        status=ChannelStatus.ACTIVE
    )
    
    conn_dict = connection.model_dump()
    conn_dict['created_at'] = conn_dict['created_at'].isoformat()
    await db.channel_connections.insert_one(conn_dict)
    
    # Log connection creation in channel_sync_logs
    sync_log = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'channel': payload.channel_type,
        'sync_type': 'connection',
        'status': 'success',
        'duration_ms': 0,
        'records_synced': 0,
        'error_message': None,
        'initiator_type': 'hotel_user',
        'initiator_name': current_user.name,
        'initiator_id': current_user.id,
        'ip_address': None,
    }
    await db.channel_sync_logs.insert_one(sync_log)
    
    return {'message': f'Channel {payload.channel_name} connected successfully', 'connection': connection}



@router.get("/channel-manager/room-mappings")
async def get_room_mappings(
    current_user: User = Depends(get_current_user)
):
    mappings = await db.room_mappings.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).to_list(200)
    return {'mappings': mappings, 'count': len(mappings)}



@router.post("/channel-manager/room-mappings")
async def create_room_mapping(
    mapping: RoomMappingCreate,
    current_user: User = Depends(get_current_user)
):
    room_mapping = RoomMapping(
        tenant_id=current_user.tenant_id,
        channel_id=mapping.channel_id,
        pms_room_type=mapping.pms_room_type,
        channel_room_type=mapping.channel_room_type,
        channel_room_id=mapping.channel_room_id,
        notes=mapping.notes,
    )
    payload = room_mapping.model_dump()
    payload['created_at'] = payload['created_at'].isoformat()
    await db.room_mappings.insert_one(payload)

    # Log mapping creation
    sync_log = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'channel': room_mapping.channel_id,
        'sync_type': 'mapping_create',
        'status': 'success',
        'duration_ms': 0,
        'records_synced': 1,
        'error_message': None,
        'initiator_type': 'hotel_user',
        'initiator_name': current_user.name,
        'initiator_id': current_user.id,
        'ip_address': None,
    }
    await db.channel_sync_logs.insert_one(sync_log)

    return {'message': 'Room mapping created', 'mapping': room_mapping}



@router.delete("/channel-manager/room-mappings/{mapping_id}")
async def delete_room_mapping(
    mapping_id: str,
    current_user: User = Depends(get_current_user)
):
    # Fetch mapping for logging context
    mapping = await db.room_mappings.find_one({'id': mapping_id, 'tenant_id': current_user.tenant_id})

    result = await db.room_mappings.delete_one({
        'id': mapping_id,
        'tenant_id': current_user.tenant_id
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Room mapping not found")

    # Log mapping deletion
    sync_log = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'channel': mapping.get('channel_id') if mapping else None,
        'sync_type': 'mapping_delete',
        'status': 'success',
        'duration_ms': 0,
        'records_synced': 0,
        'error_message': None,
        'initiator_type': 'hotel_user',
        'initiator_name': current_user.name,
        'initiator_id': current_user.id,
        'ip_address': None,
    }
    await db.channel_sync_logs.insert_one(sync_log)

    return {'message': 'Room mapping deleted', 'mapping_id': mapping_id}



@router.get("/channel-manager/ota-reservations")
@cached(ttl=180, key_prefix="cm_ota_reservations")  # Cache for 3 min
async def get_ota_reservations(
    status: Optional[str] = None,
    channel: Optional[ChannelType] = None,
    current_user: User = Depends(get_current_user)
):
    """Get OTA reservations with filters"""
    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status
    if channel:
        query['channel_type'] = channel
    
    reservations = await db.ota_reservations.find(query, {'_id': 0}).sort('received_at', -1).to_list(100)
    return {'reservations': reservations, 'count': len(reservations)}



@router.post("/channel-manager/import-reservation/{ota_reservation_id}")
async def import_ota_reservation(
    ota_reservation_id: str,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    """Import OTA reservation into PMS"""
    ota_res = await db.ota_reservations.find_one({
        'id': ota_reservation_id,
        'tenant_id': current_user.tenant_id
    })
    
    if not ota_res:
        raise HTTPException(status_code=404, detail="OTA reservation not found")
    
    if ota_res['status'] == 'imported':
        raise HTTPException(status_code=400, detail="Reservation already imported")
    
    # Find or create guest
    guest = await db.guests.find_one({
        'tenant_id': current_user.tenant_id,
        'email': ota_res['guest_email']
    })
    
    if not guest:
        # Create new guest
        guest_create = GuestCreate(
            name=ota_res['guest_name'],
            email=ota_res.get('guest_email') or 'noemail@example.com',
            phone=ota_res.get('guest_phone') or 'N/A',
            id_number='OTA-' + ota_res['channel_booking_id']
        )
        guest = Guest(tenant_id=current_user.tenant_id, **guest_create.model_dump())
        guest_dict = guest.model_dump()
        guest_dict['created_at'] = guest_dict['created_at'].isoformat()
        await db.guests.insert_one(guest_dict)
    
    # Find available room of matching type
    rooms = await db.rooms.find({
        'tenant_id': current_user.tenant_id,
        'room_type': ota_res['room_type'],
        'status': 'available'
    }).to_list(10)
    
    if not rooms:
        # Create exception
        exception = ExceptionQueue(
            tenant_id=current_user.tenant_id,
            exception_type="reservation_import_failed",
            channel_type=ota_res['channel_type'],
            entity_id=ota_reservation_id,
            error_message=f"No available rooms of type {ota_res['room_type']}",
            details={'ota_booking_id': ota_res['channel_booking_id']}
        )
        exc_dict = exception.model_dump()
        exc_dict['created_at'] = exc_dict['created_at'].isoformat()
        await db.exception_queue.insert_one(exc_dict)
        
        raise HTTPException(status_code=400, detail=f"No available {ota_res['room_type']} rooms")
    
    room = rooms[0]
    
    # Create booking
    booking_create = BookingCreate(
        guest_id=guest['id'],
        room_id=room['id'],
        check_in=ota_res['check_in'],
        check_out=ota_res['check_out'],
        adults=ota_res['adults'],
        children=ota_res['children'],
        guests_count=ota_res['adults'] + ota_res['children'],
        total_amount=ota_res['total_amount'],
        channel=ota_res['channel_type']
    )
    
    booking = Booking(
        tenant_id=current_user.tenant_id,
        **booking_create.model_dump(exclude={'check_in', 'check_out'}),
        check_in=datetime.fromisoformat(ota_res['check_in']),
        check_out=datetime.fromisoformat(ota_res['check_out'])
    )
    
    booking_dict = booking.model_dump()
    booking_dict['check_in'] = booking_dict['check_in'].isoformat()
    booking_dict['check_out'] = booking_dict['check_out'].isoformat()
    booking_dict['created_at'] = booking_dict['created_at'].isoformat()
    from core.atomic_booking import BookingConflictError, create_booking_atomic
    try:
        await create_booking_atomic(booking_dict)
    except BookingConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    
    # Update OTA reservation status
    await db.ota_reservations.update_one(
        {'id': ota_reservation_id},
        {'$set': {
            'status': 'imported',
            'pms_booking_id': booking.id,
            'processed_at': datetime.now(timezone.utc).isoformat()
        }}
    )

    # Log reservation import in channel_sync_logs
    ip_address = request.headers.get('x-forwarded-for') or request.client.host
    sync_log = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'channel': ota_res['channel_type'],
        'sync_type': 'reservation_import',
        'status': 'success',
        'duration_ms': 0,
        'records_synced': 1,
        'error_message': None,
        'initiator_type': 'hotel_user',
        'initiator_name': current_user.name,
        'initiator_id': current_user.id,
        'ip_address': ip_address,
    }
    await db.channel_sync_logs.insert_one(sync_log)
    
    return {
        'message': 'OTA reservation imported successfully',
        'pms_booking_id': booking.id,
        'guest_id': guest['id'],
        'room_number': room['room_number']
    }



@router.get("/channel-manager/exceptions")
@cached(ttl=180, key_prefix="cm_exceptions")  # Cache for 3 min
async def get_exception_queue(
    status: Optional[str] = None,
    exception_type: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get exception queue with filters"""
    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status
    if exception_type:
        query['exception_type'] = exception_type
    
    exceptions = await db.exception_queue.find(query, {'_id': 0}).sort('created_at', -1).to_list(100)
    return {'exceptions': exceptions, 'count': len(exceptions)}

# ============= OTA OVERLAY & RATE PARITY =============



@router.get("/channel/parity/check")
@cached(ttl=300, key_prefix="channel_parity")  # Cache for 5 min
async def check_rate_parity(
    date: Optional[str] = None,
    room_type: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Check rate parity between OTA and direct rates"""
    target_date = datetime.fromisoformat(date).date() if date else datetime.now(timezone.utc).date()
    
    # Get rooms
    room_query = {'tenant_id': current_user.tenant_id}
    if room_type:
        room_query['room_type'] = room_type
    
    rooms = await db.rooms.find(room_query, {'_id': 0}).to_list(1000)
    room_types = list(set(r['room_type'] for r in rooms))
    
    parity_results = []
    
    for rt in room_types:
        # Get direct rate (base_price from room)
        rt_rooms = [r for r in rooms if r['room_type'] == rt]
        if not rt_rooms:
            continue
        
        direct_rate = rt_rooms[0]['base_price']
        
        # Get OTA rates from recent bookings
        start_of_day = datetime.combine(target_date, datetime.min.time())
        end_of_day = datetime.combine(target_date, datetime.max.time())
        
        # Find bookings on this date by channel
        ota_bookings = await db.bookings.find({
            'tenant_id': current_user.tenant_id,
            'room_id': {'$in': [r['id'] for r in rt_rooms]},
            'check_in': {'$gte': start_of_day.isoformat(), '$lte': end_of_day.isoformat()},
            'ota_channel': {'$ne': None}
        }, {'_id': 0}).to_list(100)
        
        # Group by OTA channel
        ota_rates = {}
        for booking in ota_bookings:
            if booking.get('ota_channel'):
                nights = (datetime.fromisoformat(booking['check_out']) - datetime.fromisoformat(booking['check_in'])).days
                if nights > 0:
                    avg_rate = booking['total_amount'] / nights
                    channel = booking['ota_channel']
                    if channel not in ota_rates:
                        ota_rates[channel] = []
                    ota_rates[channel].append(avg_rate)
        
        # Calculate average OTA rate per channel
        for channel, rates in ota_rates.items():
            avg_ota_rate = sum(rates) / len(rates)
            diff = direct_rate - avg_ota_rate
            
            if abs(diff) < 1:
                parity = ParityStatus.EQUAL
            elif diff > 0:
                parity = ParityStatus.POSITIVE  # Direct more expensive (good)
            else:
                parity = ParityStatus.NEGATIVE  # OTA more expensive (bad)
            
            parity_results.append({
                'date': target_date.isoformat(),
                'room_type': rt,
                'channel': channel,
                'direct_rate': round(direct_rate, 2),
                'ota_rate': round(avg_ota_rate, 2),
                'difference': round(diff, 2),
                'parity_status': parity,
                'sample_size': len(rates)
            })
    
    return {
        'date': target_date.isoformat(),
        'parity_checks': parity_results,
        'total_checks': len(parity_results)
    }



@router.get("/channel/status")
@cached(ttl=180, key_prefix="channel_status")  # Cache for 3 min
async def get_channel_status(current_user: User = Depends(get_current_user)):
    """Get health status of all channel connections"""
    # Get all connections
    connections = await db.channel_connections.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).to_list(100)
    
    # Check exception queue for issues
    recent_exceptions = await db.exception_queue.find({
        'tenant_id': current_user.tenant_id,
        'status': 'pending',
        'created_at': {'$gte': (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()}
    }, {'_id': 0}).to_list(100)
    
    channel_statuses = []
    
    for conn in connections:
        # Check for recent exceptions
        conn_exceptions = [e for e in recent_exceptions if e.get('channel_type') == conn.get('channel_type')]
        
        if len(conn_exceptions) > 10:
            health = ChannelHealth.ERROR
            message = f"{len(conn_exceptions)} pending exceptions"
        elif len(conn_exceptions) > 3:
            health = ChannelHealth.DELAYED
            message = f"{len(conn_exceptions)} pending exceptions"
        elif conn.get('status') != 'active':
            health = ChannelHealth.OFFLINE
            message = "Connection inactive"
        else:
            health = ChannelHealth.HEALTHY
            message = "All systems operational"
        
        # Calculate delay if any
        delay_minutes = 0
        if conn_exceptions:
            oldest = min(conn_exceptions, key=lambda x: x['created_at'])
            delay_minutes = int((datetime.now(timezone.utc) - datetime.fromisoformat(oldest['created_at'])).total_seconds() / 60)
        
        channel_statuses.append({
            'channel_type': conn.get('channel_type'),
            'channel_name': conn.get('channel_name'),
            'health': health,
            'message': message,
            'pending_exceptions': len(conn_exceptions),
            'delay_minutes': delay_minutes,
            'last_sync': conn.get('last_sync_at', 'Never')
        })
    
    return {
        'channels': channel_statuses,
        'total_channels': len(channel_statuses),
        'healthy_count': sum(1 for c in channel_statuses if c['health'] == ChannelHealth.HEALTHY),
        'warning_count': sum(1 for c in channel_statuses if c['health'] == ChannelHealth.DELAYED),
        'error_count': sum(1 for c in channel_statuses if c['health'] == ChannelHealth.ERROR)
    }



@router.post("/channel/insights/analyze")
async def analyze_ota_insights(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """AI-powered OTA channel analysis (Phase E preparation)"""
    # Default to last 30 days
    end = datetime.fromisoformat(end_date).date() if end_date else datetime.now(timezone.utc).date()
    start = datetime.fromisoformat(start_date).date() if start_date else (end - timedelta(days=30))
    
    # Get all bookings in date range
    bookings = await db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {'$gte': start.isoformat(), '$lte': end.isoformat()}
    }, {'_id': 0}).to_list(10000)
    
    # Channel performance analysis
    channel_performance = {}
    total_revenue = 0
    total_commission_cost = 0
    
    for booking in bookings:
        channel = booking.get('ota_channel') or 'direct'
        amount = booking.get('total_amount', 0)
        commission = booking.get('commission_pct', 0)
        
        if channel not in channel_performance:
            channel_performance[channel] = {
                'bookings': 0,
                'revenue': 0,
                'commission_cost': 0,
                'avg_rate': 0
            }
        
        channel_performance[channel]['bookings'] += 1
        channel_performance[channel]['revenue'] += amount
        
        if commission > 0:
            commission_amount = amount * (commission / 100)
            channel_performance[channel]['commission_cost'] += commission_amount
            total_commission_cost += commission_amount
        
        total_revenue += amount
    
    # Calculate averages and net revenue
    for channel, data in channel_performance.items():
        if data['bookings'] > 0:
            data['avg_rate'] = round(data['revenue'] / data['bookings'], 2)
            data['net_revenue'] = round(data['revenue'] - data['commission_cost'], 2)
            data['revenue_share_pct'] = round((data['revenue'] / total_revenue * 100) if total_revenue > 0 else 0, 2)
            data['commission_cost'] = round(data['commission_cost'], 2)
    
    # Sort by revenue
    sorted_channels = sorted(
        channel_performance.items(),
        key=lambda x: x[1]['revenue'],
        reverse=True
    )
    
    # Generate insights
    insights = []
    
    # Best performing channel
    if sorted_channels:
        best_channel = sorted_channels[0]
        insights.append({
            'type': 'top_performer',
            'channel': best_channel[0],
            'message': f"{best_channel[0]} is your top channel with ${best_channel[1]['revenue']:.2f} revenue ({best_channel[1]['bookings']} bookings)",
            'priority': 'high'
        })
    
    # High commission cost warning
    if total_commission_cost > total_revenue * 0.20:
        insights.append({
            'type': 'high_commission',
            'message': f"Commission costs are ${total_commission_cost:.2f} ({(total_commission_cost/total_revenue*100):.1f}% of revenue). Consider direct booking strategies.",
            'priority': 'medium'
        })
    
    # Parity suggestions (placeholder for Phase E AI)
    insights.append({
        'type': 'parity_suggestion',
        'message': "Consider rate parity monitoring to optimize OTA vs Direct pricing",
        'priority': 'low'
    })
    
    return {
        'period': {
            'start_date': start.isoformat(),
            'end_date': end.isoformat(),
            'days': (end - start).days
        },
        'summary': {
            'total_bookings': len(bookings),
            'total_revenue': round(total_revenue, 2),
            'total_commission_cost': round(total_commission_cost, 2),
            'net_revenue': round(total_revenue - total_commission_cost, 2),
            'avg_commission_pct': round((total_commission_cost / total_revenue * 100) if total_revenue > 0 else 0, 2)
        },
        'channel_performance': dict(sorted_channels),
        'insights': insights,
        'recommendations': [
            "Monitor rate parity daily to prevent OTA undercutting",
            "Increase direct booking conversion with better incentives",
            "Negotiate commission rates with high-volume OTAs"
        ]
    }

# ============= ENTERPRISE MODE FEATURES =============



@router.get("/channel-manager/rate-parity-check")
async def check_rate_parity_detailed(
    date: Optional[str] = None,
    room_type: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Check rate parity across channels
    - Direct booking vs OTA rates
    - Identify negative disparity (OTA cheaper - BAD)
    - Alert on rate mismatches
    """
    target_date = date or datetime.now().date().isoformat()
    
    # Get rates from channel manager
    channels = ['direct', 'booking_com', 'expedia', 'airbnb']
    rate_comparison = []
    
    for channel in channels:
        # In production, fetch actual rates from channel APIs
        # For MVP, simulate rate data
        channel_rate = await db.channel_rates.find_one({
            'tenant_id': current_user.tenant_id,
            'channel': channel,
            'date': target_date,
            'room_type': room_type
        })
        
        if channel_rate:
            rate = channel_rate.get('rate', 0)
        else:
            # Simulated rates
            base_rate = 100
            if channel == 'direct':
                rate = base_rate
            elif channel == 'booking_com':
                rate = base_rate * 1.15  # Should be higher (commission included)
            elif channel == 'expedia':
                rate = base_rate * 1.18
            else:
                rate = base_rate * 1.12
        
        rate_comparison.append({
            'channel': channel,
            'rate': round(rate, 2)
        })
    
    # Find direct rate
    direct_rate = next((r['rate'] for r in rate_comparison if r['channel'] == 'direct'), 100)
    
    # Check parity
    parity_issues = []
    for channel_data in rate_comparison:
        if channel_data['channel'] != 'direct':
            diff = channel_data['rate'] - direct_rate
            diff_pct = (diff / direct_rate * 100) if direct_rate > 0 else 0
            
            if diff < 0:
                # Negative disparity - OTA is cheaper (BAD!)
                parity_issues.append({
                    'channel': channel_data['channel'],
                    'status': 'negative_disparity',
                    'severity': 'critical',
                    'direct_rate': direct_rate,
                    'channel_rate': channel_data['rate'],
                    'difference': round(diff, 2),
                    'difference_pct': round(diff_pct, 1),
                    'message': f'⚠️ {channel_data["channel"]} is cheaper by {abs(round(diff_pct, 1))}%'
                })
    
    return {
        'date': target_date,
        'room_type': room_type or 'All',
        'direct_rate': direct_rate,
        'rate_comparison': rate_comparison,
        'parity_status': 'issues_found' if parity_issues else 'good',
        'issues': parity_issues,
        'recommendation': 'Adjust OTA rates to maintain positive disparity' if parity_issues else 'Rate parity is good'
    }




@router.get("/channel-manager/sync-history")
async def get_channel_sync_history(
    days: int = 7,
    channel: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """
    Get channel sync history log
    - Successful syncs
    - Failed syncs
    - Sync duration
    """
    end_dt = datetime.now(timezone.utc)
    start_dt = end_dt - timedelta(days=days)
    
    match_criteria = {
        'tenant_id': current_user.tenant_id,
        'timestamp': {
            '$gte': start_dt.isoformat(),
            '$lte': end_dt.isoformat()
        }
    }
    
    if channel:
        match_criteria['channel'] = channel
    
    sync_logs = []
    async for log in db.channel_sync_logs.find(match_criteria).sort('timestamp', -1):
        sync_logs.append({
            'timestamp': log.get('timestamp'),
            'channel': log.get('channel'),
            'sync_type': log.get('sync_type'),  # rates, inventory, bookings
            'status': log.get('status'),  # success, failed
            'duration_ms': log.get('duration_ms'),
            'records_synced': log.get('records_synced'),
            'error_message': log.get('error_message'),
            'initiator_type': log.get('initiator_type'),
            'initiator_name': log.get('initiator_name'),
            'initiator_id': log.get('initiator_id'),
            'ip_address': log.get('ip_address')
        })
    
    # If no logs, create simulated logs
    if not sync_logs:
        channels = ['booking_com', 'expedia', 'airbnb']
        for ch in channels:
            sync_logs.append({
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'channel': ch,
                'sync_type': 'rates',
                'status': 'success',
                'duration_ms': 1250,
                'records_synced': 45,
                'error_message': None
            })
    
    # Calculate stats
    total_syncs = len(sync_logs)
    successful = sum(1 for log in sync_logs if log['status'] == 'success')
    failed = total_syncs - successful
    
    return {
        'period_days': days,
        'start_date': start_dt.date().isoformat(),
        'end_date': end_dt.date().isoformat(),
        'channel_filter': channel,
        'summary': {
            'total_syncs': total_syncs,
            'successful': successful,
            'failed': failed,
            'success_rate': round((successful / total_syncs * 100), 1) if total_syncs > 0 else 0
        },
        'sync_logs': sync_logs
    }


# ============= REVENUE MANAGEMENT ENHANCEMENTS =============



@router.get("/channels/status")
async def get_channel_status_v2(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get OTA channel connection status
    """
    await get_current_user(credentials)
    
    channels = [
        {
            'channel': 'Booking.com',
            'status': 'connected',
            'last_sync': (datetime.now() - timedelta(minutes=5)).isoformat(),
            'inventory_synced': True,
            'rates_synced': True,
            'bookings_today': 12,
            'connection_health': 'good'
        },
        {
            'channel': 'Expedia',
            'status': 'connected',
            'last_sync': (datetime.now() - timedelta(minutes=15)).isoformat(),
            'inventory_synced': True,
            'rates_synced': True,
            'bookings_today': 8,
            'connection_health': 'good'
        },
        {
            'channel': 'Agoda',
            'status': 'warning',
            'last_sync': (datetime.now() - timedelta(hours=2)).isoformat(),
            'inventory_synced': False,
            'rates_synced': True,
            'bookings_today': 5,
            'connection_health': 'warning'
        },
        {
            'channel': 'Hotels.com',
            'status': 'connected',
            'last_sync': (datetime.now() - timedelta(minutes=8)).isoformat(),
            'inventory_synced': True,
            'rates_synced': True,
            'bookings_today': 6,
            'connection_health': 'good'
        }
    ]
    
    return {
        'channels': channels,
        'total_channels': len(channels),
        'connected_count': len([c for c in channels if c['status'] == 'connected']),
        'warning_count': len([c for c in channels if c['connection_health'] == 'warning']),
        'total_bookings_today': sum(c['bookings_today'] for c in channels)
    }


# 2. GET /api/channels/rate-parity - Rate parity check


@router.get("/channels/rate-parity")
async def get_rate_parity(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Check rate parity across channels
    """
    await get_current_user(credentials)
    
    parity_data = [
        {
            'date': datetime.now().date().isoformat(),
            'room_type': 'Standard Room',
            'our_pms_rate': 1200,
            'booking_com': 1200,
            'expedia': 1200,
            'agoda': 1250,
            'hotels_com': 1200,
            'parity_status': 'violation',
            'violating_channel': 'Agoda'
        },
        {
            'date': datetime.now().date().isoformat(),
            'room_type': 'Deluxe Room',
            'our_pms_rate': 1800,
            'booking_com': 1800,
            'expedia': 1800,
            'agoda': 1800,
            'hotels_com': 1800,
            'parity_status': 'good',
            'violating_channel': None
        }
    ]
    
    return {
        'parity_data': parity_data,
        'violations': len([p for p in parity_data if p['parity_status'] == 'violation']),
        'check_date': datetime.now().date().isoformat()
    }


# 3. GET /api/channels/inventory - Inventory distribution


@router.get("/channels/inventory")
async def get_channel_inventory(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get inventory distribution across channels
    """
    current_user = await get_current_user(credentials)
    
    today = datetime.now().date()
    total_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    if total_rooms == 0:
        total_rooms = 100
    
    inventory = [
        {
            'date': today.isoformat(),
            'room_type': 'Standard Room',
            'total_inventory': 50,
            'available': 12,
            'booking_com_allocation': 20,
            'expedia_allocation': 15,
            'agoda_allocation': 10,
            'direct_allocation': 5
        },
        {
            'date': today.isoformat(),
            'room_type': 'Deluxe Room',
            'total_inventory': 30,
            'available': 8,
            'booking_com_allocation': 12,
            'expedia_allocation': 8,
            'agoda_allocation': 6,
            'direct_allocation': 4
        }
    ]
    
    return {
        'inventory': inventory,
        'total_available': sum(i['available'] for i in inventory)
    }


# 4. GET /api/channels/performance - Channel performance


@router.get("/channels/performance")
async def get_channel_performance(
    days: int = 30,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Get channel performance metrics
    """
    await get_current_user(credentials)
    
    performance = [
        {
            'channel': 'Booking.com',
            'bookings': 145,
            'revenue': 348000,
            'avg_rate': 2400,
            'cancellation_rate': 8.5,
            'market_share': 35
        },
        {
            'channel': 'Expedia',
            'bookings': 98,
            'revenue': 245000,
            'avg_rate': 2500,
            'cancellation_rate': 12.2,
            'market_share': 25
        },
        {
            'channel': 'Agoda',
            'bookings': 67,
            'revenue': 156000,
            'avg_rate': 2328,
            'cancellation_rate': 9.8,
            'market_share': 15
        },
        {
            'channel': 'Direct',
            'bookings': 112,
            'revenue': 312000,
            'avg_rate': 2785,
            'cancellation_rate': 5.3,
            'market_share': 25
        }
    ]
    
    return {
        'performance': performance,
        'period_days': days,
        'total_bookings': sum(p['bookings'] for p in performance),
        'total_revenue': sum(p['revenue'] for p in performance),
        'best_performer': max(performance, key=lambda x: x['revenue'])['channel']
    }


# 5. POST /api/channels/push-rates - Push rates to channels


@router.post("/channels/push-rates")
async def push_rates_to_channels(
    room_type: str,
    date: str,
    rate: float,
    channels: List[str],
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """
    Push rates to selected OTA channels
    """
    await get_current_user(credentials)
    
    results = []
    for channel in channels:
        results.append({
            'channel': channel,
            'status': 'success',
            'pushed_at': datetime.now(timezone.utc).isoformat()
        })
    
    return {
        'message': 'Fiyatlar kanallara gönderildi',
        'room_type': room_type,
        'date': date,
        'rate': rate,
        'results': results
    }


# ============================================================================
# CORPORATE CONTRACTS MOBILE - Kurumsal Anlaşmalar
# ============================================================================

# 1. GET /api/corporate/contracts - Corporate contracts

