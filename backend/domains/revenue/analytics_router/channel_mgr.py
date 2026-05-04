"""
channel_mgr

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Domain Router: Analytics

Extracted from legacy_routes.py — GM Dashboard, pickup analysis, anomaly detection, revenue analytics.
"""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials

from core.database import db
from core.security import _is_super_admin, get_current_user, security
from models.enums import ChannelType
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.role_permission_service import require_role as _require_role

# v67 Bug DD: frontdesk/* endpoint'lerinde RBAC eksikti — HK kullanıcı guest PII (search-bookings),
# müsaitlik (available-rooms), oda atama (assign-room) erişebiliyordu. Front office personeline kısıtla.
_FD_READ = Depends(_require_role("super_admin", "admin", "supervisor", "front_desk"))
_FD_WRITE = Depends(_require_role("super_admin", "admin", "front_desk"))

try:
    from routers.pms_availability import check_room_availability
except Exception:  # pragma: no cover
    async def check_room_availability(*args, **kwargs):
        return {"available": False, "rooms": []}



# --------------------------------------------------------------------------
# GM Dashboard - Pickup Analysis & Anomaly Detection
# --------------------------------------------------------------------------







# rbac-allow: cache-rbac — FO booking search operasyonel

# rbac-allow: cache-rbac — FO available rooms operasyonel




from integrations.booking_adapter import BookingAdapter

_SYSTEM_HEALTH_CACHE: dict = {"ts": 0.0, "payload": None}
_SYSTEM_HEALTH_TTL = 5.0  # seconds

router = APIRouter(prefix="/api", tags=["analytics"])


# ── GET /channel-manager/overview ──
@router.get("/channel-manager/overview")
async def get_channel_manager_overview(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get channel manager overview with all connected channels"""
    await get_current_user(credentials)

    # Mock channel data (in production, get from actual channel manager API)
    channels = {
        'booking_com': {
            'name': 'Booking.com',
            'status': 'connected',
            'last_sync': (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
            'active_listings': 24,
            'bookings_today': 3,
            'revenue_today': 1250.0,
            'avg_rating': 8.7,
            'commission_rate': 15.0
        },
        'expedia': {
            'name': 'Expedia',
            'status': 'connected',
            'last_sync': (datetime.now(UTC) - timedelta(minutes=8)).isoformat(),
            'active_listings': 24,
            'bookings_today': 2,
            'revenue_today': 890.0,
            'avg_rating': 4.3,
            'commission_rate': 18.0
        },
        'airbnb': {
            'name': 'Airbnb',
            'status': 'connected',
            'last_sync': (datetime.now(UTC) - timedelta(minutes=12)).isoformat(),
            'active_listings': 15,
            'bookings_today': 1,
            'revenue_today': 450.0,
            'avg_rating': 4.8,
            'commission_rate': 14.0
        },
        'direct': {
            'name': 'Direct Website',
            'status': 'active',
            'last_sync': datetime.now(UTC).isoformat(),
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
# ── GET /channel-manager/rate-comparison ──
@router.get("/channel-manager/rate-comparison")
async def get_channel_rate_comparison(
    date: str | None = None,
    room_type: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Compare rates across all channels"""
    await get_current_user(credentials)

    if not date:
        date = datetime.now(UTC).date().isoformat()

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
# ── GET /channel-manager/revenue-by-channel ──
@router.get("/channel-manager/revenue-by-channel")
async def get_revenue_by_channel(
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get revenue breakdown by channel"""
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC)
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
# ── POST /channel-manager/push-availability ──
@router.post("/channel-manager/push-availability")
async def push_channel_availability(
    check_in: str,
    check_out: str,
    room_type: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_channel_connectors")),  # v92 DW
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
        'timestamp': datetime.now(UTC).isoformat(),
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
# ── POST /channel-manager/update-rates ──
@router.post("/channel-manager/update-rates")
async def update_channel_rates(
    rate_update: dict,
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_channel_connectors")),  # v89 DW
):
    """Update rates across channels"""
    current_user = await get_current_user(credentials)

    # Only admins and revenue managers can update rates (super_admin always allowed)
    if not _is_super_admin(current_user) and current_user.role not in ['admin', 'revenue_manager', 'gm']:
        raise HTTPException(status_code=403, detail="Access denied")

    # Determine initiator info
    # v109 Bug DAK round-6 (T09 P2): naive XFF allowed audit-log IP spoofing
    # (attacker could send X-Forwarded-For: <fake-ip> to mask their identity in
    # the audit trail). Use the trusted-proxy aware client_ip() helper which
    # extracts the rightmost (edge-appended) hop only.
    from security.auth_throttle import client_ip as _client_ip
    ip_address = _client_ip(request)
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
        'created_at': datetime.now(UTC).isoformat()
    }

    await db.rate_updates.insert_one(rate_log)

    # Also push a summary entry to channel_sync_logs for UI sync history
    sync_log = {
        'id': str(uuid.uuid4()),
        'tenant_id': current_user.tenant_id,
        'timestamp': datetime.now(UTC).isoformat(),
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
