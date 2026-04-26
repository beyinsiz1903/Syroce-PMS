"""
WebSocket Server for Real-time Updates
Provides live dashboard metrics, booking updates, and notifications
"""
import logging
from datetime import datetime
from typing import Any

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
connected_clients: dict[str, set[str]] = {
    'dashboard': set(),
    'pms': set(),
    'notifications': set(),
    'kitchen': set(),
    'system-health': set(),
    'cockpit': set(),
    'internal-chat': set(),
}

# Map sid → authenticated identity (used for tenant-scoped internal-chat rooms)
sid_identity: dict[str, dict[str, Any]] = {}

# Department canonical names — keep in sync with messaging/router.py
_DEPARTMENT_BY_ROLE = {
    'front_desk': 'Reception',
    'housekeeping': 'Housekeeping',
    'maintenance': 'Maintenance',
    'finance': 'Finance',
    'supervisor': 'Management',
    'admin': 'Management',
    'super_admin': 'Management',
    'owner': 'Management',
    'sales': 'Reception',
}


async def _resolve_user_identity(auth: Any) -> dict[str, Any] | None:
    """Async variant of _decode_socket_auth that fetches the user document
    for department resolution.
    """
    if not isinstance(auth, dict):
        return None
    token = auth.get('token') or auth.get('Authorization')
    if not token:
        return None
    if isinstance(token, str) and token.lower().startswith('bearer '):
        token = token[7:]

    try:
        from jose import jwt

        from core.security import JWT_ALGORITHM, JWT_SECRET
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception as e:
        logger.debug(f"Socket auth decode failed: {e}")
        return None

    user_id = payload.get('user_id')
    tenant_id = payload.get('tenant_id')
    if not user_id:
        return None

    department = None
    role = None
    try:
        from core.database import db
        user_doc = await db.users.find_one(
            {'$or': [{'id': user_id}, {'user_id': user_id}]},
            {'_id': 0, 'role': 1, 'tenant_id': 1, 'id': 1},
        )
        if user_doc:
            role = user_doc.get('role')
            department = _DEPARTMENT_BY_ROLE.get(role, 'General')
            # Reject token whose tenant_id doesn't match the user record
            doc_tenant = user_doc.get('tenant_id')
            if tenant_id and doc_tenant and tenant_id != doc_tenant:
                logger.warning(
                    f"Socket auth tenant mismatch: user={user_id} jwt={tenant_id} doc={doc_tenant}"
                )
                return None
            tenant_id = tenant_id or doc_tenant
    except Exception as e:
        logger.debug(f"Socket identity user lookup failed: {e}")

    return {
        'user_id': user_id,
        'tenant_id': tenant_id,
        'role': role,
        'department': department,
    }


def _internal_chat_rooms(tenant_id: str, user_id: str, department: str | None) -> list[str]:
    """Compute the tenant-scoped internal chat rooms a user belongs to."""
    rooms = [
        f"internal_chat:{tenant_id}:user:{user_id}",
        f"internal_chat:{tenant_id}:broadcast",
    ]
    if department:
        rooms.append(f"internal_chat:{tenant_id}:dept:{department}")
    return rooms


def _is_internal_chat_room(room: str) -> bool:
    """Whether a room name belongs to the protected internal chat namespace."""
    return isinstance(room, str) and room.startswith('internal_chat:')


@sio.event
async def connect(sid, environ, auth):
    """Handle client connection.

    If the client provided a valid JWT in the auth payload, we enrol them
    in their tenant-scoped internal_chat rooms (DM, department, broadcast)
    so messages pushed by /messaging/internal/send arrive in real time.

    When a Redis pub/sub bridge is configured, we also subscribe the
    adapter to those tenant-scoped channels so a `broadcast_internal_message`
    published on a different backend instance still reaches this client.
    Subscriptions are reference-counted on the adapter side so shared rooms
    (department / tenant broadcast) only translate to a single Redis
    SUBSCRIBE per channel.
    """
    logger.info(f"Client connected: {sid}")
    identity = await _resolve_user_identity(auth)
    if identity and identity.get('tenant_id'):
        sid_identity[sid] = identity
        rooms = _internal_chat_rooms(
            identity['tenant_id'], identity['user_id'], identity.get('department')
        )
        for room in rooms:
            await sio.enter_room(sid, room)
        # Bridge each tenant-scoped room to Redis pub/sub. No-op when the
        # adapter is in local-only mode, so single-instance behaviour is
        # preserved. Per-room try/except so one failed subscription does
        # not skip the remaining rooms (e.g. DM works even if the
        # department channel temporarily fails).
        try:
            from infra.ws_redis_adapter import ws_redis_adapter
        except Exception as e:
            logger.warning(f"WS adapter import failed at connect for {sid}: {e}")
        else:
            for room in rooms:
                try:
                    await ws_redis_adapter.subscribe(room)
                except Exception as e:
                    logger.warning(
                        f"WS adapter subscribe-on-connect failed "
                        f"({sid} → {room}): {e}"
                    )
        connected_clients['internal-chat'].add(sid)
        logger.info(
            f"Socket {sid} authenticated user={identity['user_id']} "
            f"tenant={identity['tenant_id']} dept={identity.get('department')} "
            f"→ joined {len(rooms)} internal_chat rooms"
        )
    await sio.emit('connection_established', {
        'sid': sid,
        'authenticated': bool(identity),
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
    # Drop this connection's contribution to the tenant-scoped Redis
    # subscriptions (refcounted, so shared rooms stay subscribed while
    # any other client on this instance is still using them).
    identity = sid_identity.pop(sid, None)
    if identity and identity.get('tenant_id'):
        rooms = _internal_chat_rooms(
            identity['tenant_id'], identity['user_id'], identity.get('department')
        )
        try:
            from infra.ws_redis_adapter import ws_redis_adapter
        except Exception as e:
            logger.warning(
                f"WS adapter import failed at disconnect for {sid}: {e}"
            )
        else:
            # Per-room error isolation so one failed unsubscribe doesn't
            # leak the remaining refcounts.
            for room in rooms:
                try:
                    await ws_redis_adapter.unsubscribe(room)
                except Exception as e:
                    logger.warning(
                        f"WS adapter unsubscribe-on-disconnect failed "
                        f"({sid} → {room}): {e}"
                    )

def _is_internal_chat_room(room: str) -> bool:
    return isinstance(room, str) and room.startswith('internal_chat:')


@sio.event
async def join_room(sid, data):
    """Join a specific room for targeted updates.

    Membership for `internal_chat:*` rooms is granted exclusively at
    `connect` time based on the authenticated identity (tenant + user +
    department). Manual join requests for those rooms are rejected here so
    a logged-in user cannot eavesdrop on another user's, department's, or
    tenant's chat events by guessing a room name.

    Other shared rooms (dashboard, pms, notifications, kitchen,
    system-health, cockpit) remain freely joinable for backward
    compatibility — those streams are not user-private.
    """
    room = (data or {}).get('room', 'general') if isinstance(data, dict) else 'general'

    if _is_internal_chat_room(room):
        identity = sid_identity.get(sid)
        allowed = False
        if identity:
            allowed_rooms = set(_internal_chat_rooms(
                identity.get('tenant_id'),
                identity.get('user_id'),
                identity.get('department'),
            ))
            allowed = room in allowed_rooms
        if not allowed:
            logger.warning(
                f"Client {sid} denied join to internal_chat room {room!r} "
                f"(authenticated={bool(identity)})"
            )
            await sio.emit('room_join_denied', {
                'room': room,
                'reason': 'not_authorized',
            }, to=sid)
            return

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
    """Leave a specific room.

    `internal_chat:*` rooms cannot be left manually — they are tied to the
    authenticated identity and are torn down on disconnect. Allowing a
    client to leave them would silently disable their own read receipts
    and typing indicators while leaving the rest of the app in an
    inconsistent state.
    """
    room = (data or {}).get('room', 'general') if isinstance(data, dict) else 'general'

    if _is_internal_chat_room(room):
        logger.debug(f"Client {sid} attempted to leave protected room {room!r}; ignored")
        return

    await sio.leave_room(sid, room)

    if room in connected_clients and sid in connected_clients[room]:
        connected_clients[room].remove(sid)

    logger.info(f"Client {sid} left room: {room}")

# Broadcast functions
async def broadcast_dashboard_update(metrics: dict[str, Any]):
    """Broadcast dashboard metrics update to all dashboard subscribers"""
    try:
        await sio.emit('dashboard_update', {
            'metrics': metrics,
            'timestamp': datetime.utcnow().isoformat()
        }, room='dashboard')
        logger.debug("Dashboard update broadcasted")
    except Exception as e:
        logger.error(f"Failed to broadcast dashboard update: {e}")

async def broadcast_booking_update(booking_data: dict[str, Any], event_type: str = 'update'):
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

async def broadcast_notification(user_id: str, notification: dict[str, Any]):
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

async def get_connected_clients_count() -> dict[str, int]:
    """Get count of connected clients per room"""
    return {
        room: len(clients)
        for room, clients in connected_clients.items()
    }


# ── System Health Live Events ──

async def broadcast_system_health_event(event_type: str, payload: dict[str, Any], tenant_id: str = None, severity: str = "info"):
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


async def broadcast_health_metric_update(metric_type: str, data: dict[str, Any], tenant_id: str = None):
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


# ── Internal chat: live read receipts & typing indicators ──

async def local_broadcast(room: str, event: str, data: dict[str, Any]) -> None:
    """Fan-out helper used as the local handler for `ws_redis_adapter`.

    Called both for events originated on this instance and for events
    received from other instances via Redis pub/sub. Wrapping `sio.emit`
    keeps the adapter agnostic of socket.io and lets startup wire the
    bridge with a single function reference.
    """
    try:
        await sio.emit(event, data, room=room)
    except Exception as e:
        logger.error(f"Failed local socket emit ({event} → {room}): {e}")


async def broadcast_internal_message_read(
    reader_id: str,
    sender_id: str | None,
    tenant_id: str | None,
    message_ids: list[str] | None = None,
    partner_id: str | None = None,
):
    """Notify the original sender that `reader_id` has read their messages.

    Routed only to the sender's tenant-scoped DM room
    (`internal_chat:{tenant_id}:user:{sender_id}`) so unrelated staff in the
    same tenant don't receive each other's read receipts. The 15-sec polling
    fallback in the frontend covers the case where WS is unavailable.

    Delivery goes through `ws_redis_adapter.publish(...)` so that under
    horizontal scaling the event also reaches the sender if their socket is
    pinned to another backend instance; if Redis is unavailable the adapter
    falls back to local-only fan-out via the same `local_broadcast` handler.

    No-op if either `tenant_id` or `sender_id` is missing — without those we
    cannot address the right recipient and broadcasting to everyone would
    leak who is chatting with whom (the very issue this routing fixes).
    """
    if not tenant_id or not sender_id:
        return
    target_room = f"internal_chat:{tenant_id}:user:{sender_id}"
    try:
        from infra.ws_redis_adapter import ws_redis_adapter
        await ws_redis_adapter.publish(target_room, 'internal_message_read', {
            'reader_id': reader_id,
            'sender_id': sender_id,
            'tenant_id': tenant_id,
            'message_ids': list(message_ids or []),
            'partner_id': partner_id,
            'timestamp': datetime.utcnow().isoformat(),
        })
    except Exception as e:
        logger.error(f"Failed to broadcast internal_message_read: {e}")


@sio.event
async def internal_typing(sid, data):
    """Relay a typing indicator from the sender to a single recipient.

    Payload: {from_user_id, from_user_name, to_user_id, tenant_id, is_typing}

    The event is delivered only to the recipient's tenant-scoped DM room
    (`internal_chat:{tenant_id}:user:{to_user_id}`) instead of the global
    `pms` room, so other staff don't see who is chatting with whom.

    The authoritative `tenant_id` and `from_user_id` come from the socket's
    authenticated identity (set during `connect`) — client-supplied values
    for those fields are ignored to prevent a logged-in user from spoofing
    typing indicators on behalf of someone else or in another tenant.
    Unauthenticated sockets are silently dropped.

    Delivery goes through `ws_redis_adapter.publish(...)` so the indicator
    reaches the recipient even when their socket is pinned to a different
    backend instance under horizontal scaling. The adapter falls back to
    local-only fan-out when Redis is unavailable.
    """
    try:
        if not isinstance(data, dict):
            return
        identity = sid_identity.get(sid)
        if not identity:
            return  # only authenticated sockets may relay typing events
        tenant_id = identity.get('tenant_id')
        from_user_id = identity.get('user_id')
        to_user_id = data.get('to_user_id')
        if not tenant_id or not from_user_id or not to_user_id:
            return
        target_room = f"internal_chat:{tenant_id}:user:{to_user_id}"
        from infra.ws_redis_adapter import ws_redis_adapter
        await ws_redis_adapter.publish(target_room, 'internal_user_typing', {
            'from_user_id': from_user_id,
            'from_user_name': data.get('from_user_name'),
            'to_user_id': to_user_id,
            'tenant_id': tenant_id,
            'is_typing': bool(data.get('is_typing', True)),
            'timestamp': datetime.utcnow().isoformat(),
        })
    except Exception as e:
        logger.error(f"Failed to relay internal_typing event: {e}")


# ── Cockpit Snapshot Streaming ──
_cockpit_last_snapshot: dict[str, Any] = {}


async def broadcast_cockpit_snapshot(snapshot: dict[str, Any], tenant_id: str = None):
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

# ── Internal Chat Live Events ──

def _internal_message_targets(
    tenant_id: str,
    *,
    to_user_id: str | None,
    to_department: str | None,
) -> list[str]:
    """Resolve the tenant-scoped room set for an internal chat event.

    Routing rules mirror the inbox query in messaging/router.py:
      - to_user_id provided → DM, deliver only to that user's room
      - to_department provided → deliver to that department's room
      - neither → broadcast to all users in the tenant
    """
    if to_user_id:
        return [f"internal_chat:{tenant_id}:user:{to_user_id}"]
    if to_department:
        return [f"internal_chat:{tenant_id}:dept:{to_department}"]
    return [f"internal_chat:{tenant_id}:broadcast"]


async def broadcast_internal_message(
    tenant_id: str,
    message_payload: dict[str, Any],
    *,
    to_user_id: str | None = None,
    to_department: str | None = None,
) -> None:
    """Broadcast a brand new internal chat message to the appropriate
    tenant-scoped rooms.

    Routed through ``ws_redis_adapter`` so that under horizontal scaling
    a message sent on instance A reaches recipients connected to instance
    B without waiting for the safety-net poll. The adapter delivers
    locally first (so the publishing instance never depends on Redis
    loopback) and then bridges via pub/sub; if Redis is unavailable the
    publish call still fans out to local clients via the wired
    ``local_handler``.
    """
    if not tenant_id:
        return

    envelope = {
        'message': message_payload,
        'tenant_id': tenant_id,
        'to_user_id': to_user_id,
        'to_department': to_department,
        'timestamp': datetime.utcnow().isoformat(),
    }

    try:
        from infra.ws_redis_adapter import ws_redis_adapter
    except Exception as e:
        logger.error(f"WS adapter import failed (internal_message): {e}")
        ws_redis_adapter = None  # type: ignore[assignment]

    for room in _internal_message_targets(
        tenant_id, to_user_id=to_user_id, to_department=to_department
    ):
        try:
            if ws_redis_adapter is not None:
                await ws_redis_adapter.publish(room, 'internal_message', envelope)
            else:
                await sio.emit('internal_message', envelope, room=room)
            logger.debug(f"Internal message broadcasted to room={room}")
        except Exception as e:
            logger.error(f"Failed to broadcast internal_message to {room}: {e}")


async def broadcast_internal_message_update(
    tenant_id: str,
    message_payload: dict[str, Any],
    *,
    to_user_id: str | None = None,
    to_department: str | None = None,
) -> None:
    """Broadcast an in-place update for an existing internal chat message.

    Used by the edit (PATCH) endpoint so the recipient's open thread / inbox
    can replace the previous bubble text and surface the "düzenlendi" badge
    without waiting for the safety-net poll. Routing rules mirror the
    original send so the message reaches exactly the same room set.

    Routed through ``ws_redis_adapter`` so the update reaches recipients
    connected to a different backend instance under horizontal scaling.
    """
    if not tenant_id:
        return

    envelope = {
        'message': message_payload,
        'tenant_id': tenant_id,
        'to_user_id': to_user_id,
        'to_department': to_department,
        'timestamp': datetime.utcnow().isoformat(),
    }

    try:
        from infra.ws_redis_adapter import ws_redis_adapter
    except Exception as e:
        logger.error(f"WS adapter import failed (internal_message_updated): {e}")
        ws_redis_adapter = None  # type: ignore[assignment]

    for room in _internal_message_targets(
        tenant_id, to_user_id=to_user_id, to_department=to_department
    ):
        try:
            if ws_redis_adapter is not None:
                await ws_redis_adapter.publish(
                    room, 'internal_message_updated', envelope
                )
            else:
                await sio.emit('internal_message_updated', envelope, room=room)
            logger.debug(f"Internal message update broadcasted to room={room}")
        except Exception as e:
            logger.error(
                f"Failed to broadcast internal_message_updated to {room}: {e}"
            )


# Create ASGI app.
#
# NOTE on the path:
#   The app is mounted at `/ws` in server.py via `app.mount("/ws", socket_app)`.
#   Starlette's `Mount` only sets `scope['root_path']` and does NOT strip the
#   prefix from `scope['path']`, so the inner ASGI app still sees the full
#   request path (e.g. `/ws/socket.io/...`). For engineio's path comparison
#   to succeed, `socketio_path` must therefore include the mount prefix.
#   The frontend sets `path: '/ws/socket.io'` accordingly.
socket_app = socketio.ASGIApp(
    sio,
    socketio_path='ws/socket.io'
)
