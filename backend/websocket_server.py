"""
WebSocket Server for Real-time Updates
Provides live dashboard metrics, booking updates, and notifications
"""
import logging
from datetime import datetime
from typing import Any, Dict, Set

import socketio

logger = logging.getLogger(__name__)

# Create Socket.IO server
sio = socketio.AsyncServer(
    async_mode='asgi',
    cors_allowed_origins='*',
    logger=True,
    engineio_logger=True
)

# Track connected clients by room
connected_clients: Dict[str, Set[str]] = {
    'dashboard': set(),
    'pms': set(),
    'notifications': set(),
    'kitchen': set(),
    'system-health': set(),
    'cockpit': set(),
}

@sio.event
async def connect(sid, environ, auth):
    """Handle client connection"""
    logger.info(f"Client connected: {sid}")
    await sio.emit('connection_established', {
        'sid': sid,
        'timestamp': datetime.utcnow().isoformat()
    }, to=sid)

@sio.event
async def disconnect(sid):
    """Handle client disconnection"""
    logger.info(f"Client disconnected: {sid}")
    # Remove from all rooms
    for room, clients in connected_clients.items():
        if sid in clients:
            clients.remove(sid)
            logger.info(f"Removed {sid} from room: {room}")

@sio.event
async def join_room(sid, data):
    """Join a specific room for targeted updates"""
    room = data.get('room', 'general')
    await sio.enter_room(sid, room)

    if room in connected_clients:
        connected_clients[room].add(sid)

    logger.info(f"Client {sid} joined room: {room}")
    await sio.emit('room_joined', {
        'room': room,
        'message': f'Successfully joined {room}'
    }, to=sid)

@sio.event
async def leave_room(sid, data):
    """Leave a specific room"""
    room = data.get('room', 'general')
    await sio.leave_room(sid, room)

    if room in connected_clients and sid in connected_clients[room]:
        connected_clients[room].remove(sid)

    logger.info(f"Client {sid} left room: {room}")

# Broadcast functions
async def broadcast_dashboard_update(metrics: Dict[str, Any]):
    """Broadcast dashboard metrics update to all dashboard subscribers"""
    try:
        await sio.emit('dashboard_update', {
            'metrics': metrics,
            'timestamp': datetime.utcnow().isoformat()
        }, room='dashboard')
        logger.debug("Dashboard update broadcasted")
    except Exception as e:
        logger.error(f"Failed to broadcast dashboard update: {e}")

async def broadcast_booking_update(booking_data: Dict[str, Any], event_type: str = 'update'):
    """
    Broadcast booking update

    Args:
        booking_data: Booking information
        event_type: 'create', 'update', 'checkin', 'checkout', 'cancel'
    """
    try:
        await sio.emit('booking_update', {
            'event_type': event_type,
            'booking': booking_data,
            'timestamp': datetime.utcnow().isoformat()
        }, room='pms')
        logger.debug(f"Booking {event_type} broadcasted")
    except Exception as e:
        logger.error(f"Failed to broadcast booking update: {e}")

async def broadcast_notification(user_id: str, notification: Dict[str, Any]):
    """Send notification to specific user"""
    try:
        # In a production setup, you'd maintain a mapping of user_id to sid
        await sio.emit('notification', {
            'notification': notification,
            'timestamp': datetime.utcnow().isoformat()
        }, room='notifications')
        logger.debug(f"Notification sent to user {user_id}")
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")

async def broadcast_room_status_update(room_id: str, status: str):
    """Broadcast room status change"""
    try:
        await sio.emit('room_status_update', {
            'room_id': room_id,
            'status': status,
            'timestamp': datetime.utcnow().isoformat()
        }, room='pms')
        logger.debug(f"Room status update broadcasted: {room_id} -> {status}")
    except Exception as e:
        logger.error(f"Failed to broadcast room status update: {e}")


async def broadcast_kitchen_orders(tenant_id: str, orders: Any):
    """Broadcast kitchen display orders"""
    try:
        await sio.emit('kitchen_orders', {
            'tenant_id': tenant_id,
            'orders': orders,
            'timestamp': datetime.utcnow().isoformat()
        }, room='kitchen')
        logger.debug("Kitchen orders broadcasted")
    except Exception as e:
        logger.error(f"Failed to broadcast kitchen orders: {e}")

async def get_connected_clients_count() -> Dict[str, int]:
    """Get count of connected clients per room"""
    return {
        room: len(clients)
        for room, clients in connected_clients.items()
    }


# ── System Health Live Events ──

async def broadcast_system_health_event(event_type: str, payload: Dict[str, Any], tenant_id: str = None, severity: str = "info"):
    """
    Broadcast system health events to system-health room subscribers.
    Events: drift_detected, reconciliation_completed, queue_saturation,
    stuck_task_detected, security_violation, provider_degraded,
    runtime_alert_triggered, worker_recovered, backlog_reduced.
    """
    try:
        await sio.emit('system_health_event', {
            'event_type': event_type,
            'severity': severity,
            'tenant_id': tenant_id,
            'payload': payload,
            'timestamp': datetime.utcnow().isoformat(),
        }, room='system-health')
        logger.debug(f"System health event broadcasted: {event_type} [{severity}]")
    except Exception as e:
        logger.error(f"Failed to broadcast system health event: {e}")


async def broadcast_health_metric_update(metric_type: str, data: Dict[str, Any], tenant_id: str = None):
    """
    Broadcast incremental metric updates (counters, gauges) without full page reload.
    metric_type: queue_depth, drift_count, alert_count, worker_status, security_score, etc.
    """
    try:
        await sio.emit('health_metric_update', {
            'metric_type': metric_type,
            'data': data,
            'tenant_id': tenant_id,
            'timestamp': datetime.utcnow().isoformat(),
        }, room='system-health')
    except Exception as e:
        logger.error(f"Failed to broadcast health metric update: {e}")

# Health check
@sio.event
async def ping(sid):
    """Ping/pong for connection health check"""
    await sio.emit('pong', {
        'timestamp': datetime.utcnow().isoformat()
    }, to=sid)


# ── Cockpit Snapshot Streaming ──
_cockpit_last_snapshot: Dict[str, Any] = {}


async def broadcast_cockpit_snapshot(snapshot: Dict[str, Any], tenant_id: str = None):
    """
    Broadcast cockpit state snapshot to cockpit room subscribers.
    Uses diff-based approach: only sends if changed from last snapshot.
    """
    global _cockpit_last_snapshot
    try:
        # Diff check: only send if data changed
        key = tenant_id or "default"
        if _cockpit_last_snapshot.get(key) == snapshot:
            return  # No change, skip

        _cockpit_last_snapshot[key] = snapshot.copy()

        await sio.emit('cockpit_snapshot', {
            'tenant_id': tenant_id,
            'snapshot': snapshot,
            'timestamp': datetime.utcnow().isoformat(),
        }, room='cockpit')
        logger.debug(f"Cockpit snapshot broadcasted for tenant={tenant_id}")
    except Exception as e:
        logger.error(f"Failed to broadcast cockpit snapshot: {e}")

# Create ASGI app
socket_app = socketio.ASGIApp(
    sio,
    socketio_path='socket.io'
)
