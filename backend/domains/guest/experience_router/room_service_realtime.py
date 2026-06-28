"""Real-time room-service order updates (Task #64 + Task #70).

Per-(tenant, booking) WebSocket fan-out for guest mobile order status
updates.

Originally single-pod (in-process pub/sub keyed by ``(tenant_id,
booking_id)``); Task #70 bridges this through ``infra/ws_redis_adapter``
so that under horizontal scaling a status change written on pod B
still reaches a guest WebSocket pinned to pod A in <1s instead of
falling back to the 15s safety-net poll.

The bridge mirrors the pattern used by ``broadcast_booking_update`` /
``broadcast_internal_message`` in ``websocket_server``:

    * ``connect()``  — also issues ``ws_redis_adapter.subscribe(room)``
      so this pod receives cross-pod publishes for the same
      (tenant, booking).
    * ``disconnect()`` — mirrors with ``unsubscribe`` (refcounted on
      the adapter side, so a shared booking with multiple sockets only
      drops the Redis subscription on the very last disconnect).
    * ``emit_order_event()`` — routes through ``adapter.publish``,
      whose registered local handler (``websocket_server.local_broadcast``)
      detects the ``room_service:`` prefix and dispatches back into
      ``order_stream.broadcast`` for the publishing pod's local sockets.
      The same call also publishes to Redis pub/sub so other pods'
      listeners fan out to *their* local subscribers. Falls back to
      direct ``order_stream.broadcast`` when the adapter has not been
      wired up (tests, very early startup) or is otherwise unavailable.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from collections import defaultdict, deque
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)

# Sliding-window cap for the in-memory "events delivered in the last
# hour" counter exposed on the System Health dashboard. Bound the deque
# defensively so a runaway producer cannot grow it without limit; in
# practice room-service is not a high-volume channel and this ceiling is
# orders of magnitude above realistic 1-hour traffic.
_EVENT_WINDOW_SECONDS = 3600
_EVENT_WINDOW_MAX = 10_000


# Room-name format used both as the in-process bucket key suffix and
# as the ``ws_redis_adapter`` channel suffix. ``websocket_server.local_broadcast``
# special-cases this prefix to dispatch back into ``order_stream``
# (see Task #70).
ROOM_KEY_PREFIX = "room_service"


def _room_key(tenant_id: str, booking_id: str) -> str:
    """Return the adapter channel name for a (tenant, booking)."""
    return f"{ROOM_KEY_PREFIX}:{tenant_id}:{booking_id}"


def parse_room_key(room: str) -> tuple[str, str] | None:
    """Inverse of :func:`_room_key`. Returns ``(tenant_id, booking_id)``
    or ``None`` if the room name is not a room-service channel.

    Used by the shared local-broadcast handler in ``websocket_server``
    so the dispatch lives next to the room-name format itself and can
    evolve atomically with it.
    """
    if not room or not room.startswith(f"{ROOM_KEY_PREFIX}:"):
        return None
    parts = room.split(":", 2)
    if len(parts) != 3 or not parts[1] or not parts[2]:
        return None
    return parts[1], parts[2]


class RoomServiceOrderStream:
    """Per-(tenant, booking) WebSocket fan-out. Lock guards mutation;
    broadcast snapshots under the lock and sends outside it so a slow
    client cannot block siblings.

    Task #69 adds a tenant-wide *staff* fan-out keyed by ``tenant_id``
    only — kitchen/front-desk dashboards subscribe to every order in
    their tenant without needing to know which bookings exist.
    """

    def __init__(self) -> None:
        self._connections: dict[tuple[str, str], set[WebSocket]] = defaultdict(set)
        self._staff_connections: dict[str, set[WebSocket]] = defaultdict(set)
        self._lock = asyncio.Lock()
        # Monotonic timestamps (seconds) of order events delivered to
        # *any* subscriber — used by the System Health dashboard to show
        # "events delivered in the last hour". Kept in-memory only; on
        # pod restart the window resets, which is acceptable for a live
        # operations gauge (Task #92).
        self._event_timestamps: deque[float] = deque(maxlen=_EVENT_WINDOW_MAX)

    async def connect(self, ws: WebSocket, tenant_id: str, booking_id: str) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[(tenant_id, booking_id)].add(ws)
        # Best-effort: bridge this booking's channel to Redis pub/sub so
        # cross-pod publishes from staff pods reach this guest socket.
        # No-op when the adapter is in local-only mode (or not yet
        # initialised); per-pod refcounting on the adapter side keeps
        # shared bookings (multiple guests on the same booking) cheap.
        try:
            from infra.ws_redis_adapter import ws_redis_adapter

            await ws_redis_adapter.subscribe(_room_key(tenant_id, booking_id))
        except Exception as e:
            logger.warning(
                "room-service WS adapter subscribe failed tenant=%s booking=%s: %s",
                tenant_id,
                booking_id,
                e,
            )
        logger.info(
            "room-service WS connected tenant=%s booking=%s (total=%d)",
            tenant_id,
            booking_id,
            len(self._connections.get((tenant_id, booking_id), set())),
        )

    async def disconnect(self, ws: WebSocket, tenant_id: str, booking_id: str) -> None:
        async with self._lock:
            key = (tenant_id, booking_id)
            bucket = self._connections.get(key)
            if bucket is None:
                # Already cleaned up; do not also drop a Redis refcount
                # because we never bumped one for this socket.
                return
            had_socket = ws in bucket
            bucket.discard(ws)
            if not bucket:
                self._connections.pop(key, None)
        # Mirror the connect-time subscribe so the adapter refcount
        # balances out. Skip when the socket wasn't actually registered
        # (defensive double-disconnect from the WS finally: block).
        if had_socket:
            try:
                from infra.ws_redis_adapter import ws_redis_adapter

                await ws_redis_adapter.unsubscribe(_room_key(tenant_id, booking_id))
            except Exception as e:
                logger.warning(
                    "room-service WS adapter unsubscribe failed tenant=%s booking=%s: %s",
                    tenant_id,
                    booking_id,
                    e,
                )
        logger.info(
            "room-service WS disconnected tenant=%s booking=%s",
            tenant_id,
            booking_id,
        )

    async def broadcast(self, tenant_id: str, booking_id: str, event: dict[str, Any]) -> int:
        """Send ``event`` to every socket on this (tenant, booking).
        Returns delivery count; prunes dead sockets."""
        async with self._lock:
            conns = list(self._connections.get((tenant_id, booking_id), set()))
        if not conns:
            return 0
        payload = json.dumps(
            {
                **event,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        delivered = 0
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(payload)
                delivered += 1
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                bucket = self._connections.get((tenant_id, booking_id))
                if bucket is not None:
                    for ws in dead:
                        bucket.discard(ws)
                    if not bucket:
                        self._connections.pop((tenant_id, booking_id), None)
        return delivered

    def connection_count(self, tenant_id: str, booking_id: str) -> int:
        return len(self._connections.get((tenant_id, booking_id), set()))

    # ── Aggregate gauges (Task #92) ─────────────────────────────────
    def total_room_count(self) -> int:
        """Number of distinct (tenant, booking) rooms with ≥1 socket.

        Used by the System Health "Room service live connections" card
        to answer "how many bookings are currently watching live order
        updates on this pod?".
        """
        return sum(1 for bucket in self._connections.values() if bucket)

    def total_connection_count(self) -> int:
        """Total guest WebSocket connections across all bookings."""
        return sum(len(bucket) for bucket in self._connections.values())

    def total_staff_room_count(self) -> int:
        """Number of distinct tenants with ≥1 staff dashboard socket."""
        return sum(1 for bucket in self._staff_connections.values() if bucket)

    def total_staff_connection_count(self) -> int:
        """Total staff dashboard WebSocket connections across tenants."""
        return sum(len(bucket) for bucket in self._staff_connections.values())

    def record_event_delivery(self, count: int = 1) -> None:
        """Append ``count`` event-delivery timestamps to the rolling
        window. ``count`` is typically the number of recipients on the
        publishing pod, so a fan-out to 3 sockets registers as 3
        delivered events — matching how operators read the gauge ("how
        many guest screens were updated in the last hour")."""
        if count <= 0:
            return
        now = time.monotonic()
        for _ in range(count):
            self._event_timestamps.append(now)

    def recent_event_count(self, seconds: int = _EVENT_WINDOW_SECONDS) -> int:
        """Number of events delivered in the last ``seconds`` window.

        Prunes expired entries from the left of the deque on each call
        — cheap because the deque is bounded and ordered by insertion
        time (which is monotonic)."""
        cutoff = time.monotonic() - max(0, seconds)
        ts = self._event_timestamps
        while ts and ts[0] < cutoff:
            ts.popleft()
        return len(ts)

    # ── Staff (tenant-wide) fan-out ─────────────────────────────────
    async def connect_staff(self, ws: WebSocket, tenant_id: str) -> None:
        await ws.accept()
        async with self._lock:
            self._staff_connections[tenant_id].add(ws)
        logger.info(
            "room-service staff WS connected tenant=%s (total=%d)",
            tenant_id,
            len(self._staff_connections.get(tenant_id, set())),
        )

    async def disconnect_staff(self, ws: WebSocket, tenant_id: str) -> None:
        async with self._lock:
            bucket = self._staff_connections.get(tenant_id)
            if bucket is None:
                return
            bucket.discard(ws)
            if not bucket:
                self._staff_connections.pop(tenant_id, None)
        logger.info(
            "room-service staff WS disconnected tenant=%s",
            tenant_id,
        )

    async def broadcast_staff(self, tenant_id: str, event: dict[str, Any]) -> int:
        """Send ``event`` to every staff socket subscribed to this
        tenant. Used so kitchen/front-desk dashboards see every order
        change regardless of which booking it belongs to."""
        async with self._lock:
            conns = list(self._staff_connections.get(tenant_id, set()))
        if not conns:
            return 0
        payload = json.dumps(
            {
                **event,
                "timestamp": datetime.now(UTC).isoformat(),
            }
        )
        delivered = 0
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(payload)
                delivered += 1
            except Exception:
                dead.append(ws)
        if dead:
            async with self._lock:
                bucket = self._staff_connections.get(tenant_id)
                if bucket is not None:
                    for ws in dead:
                        bucket.discard(ws)
                    if not bucket:
                        self._staff_connections.pop(tenant_id, None)
        return delivered

    def staff_connection_count(self, tenant_id: str) -> int:
        return len(self._staff_connections.get(tenant_id, set()))


order_stream = RoomServiceOrderStream()


def _strip_mongo_id(doc: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in doc.items() if k != "_id"}


def _adapter_is_wired() -> Any | None:
    """Return the ``ws_redis_adapter`` singleton when its local handler
    has been registered (i.e. bootstrap phase F has run), otherwise
    ``None``.

    The local handler is what dispatches a ``room_service:`` channel back
    into :func:`RoomServiceOrderStream.broadcast`; without it, going
    through ``adapter.publish`` would silently swallow the event for
    origin-pod subscribers. Tests and very-early-startup callers hit
    this fallback and use the in-process broadcast directly.
    """
    try:
        from infra.ws_redis_adapter import ws_redis_adapter
    except Exception as e:
        logger.warning("ws_redis_adapter import failed: %s", e)
        return None
    if getattr(ws_redis_adapter, "_local_handler", None) is None:
        return None
    return ws_redis_adapter


async def emit_order_event(order: dict[str, Any], event_type: str = "updated") -> int:
    """Broadcast a room-service order event to subscribers of the
    order's booking. ``event_type`` is ``"created"`` or ``"status_changed"``.
    Tenant + booking are read from the order doc; missing → silent no-op
    so a broadcast failure can't break the originating HTTP request.

    Routes through ``ws_redis_adapter.publish`` when the adapter has been
    wired up, so a status change written on pod B reaches a guest socket
    on pod A via Redis pub/sub. Falls back to the direct in-process
    broadcast when the adapter is unavailable, preserving the original
    single-pod behaviour for tests / early startup.

    Returns the number of *local* sockets the event was delivered to.
    The cross-pod fan-out is fire-and-forget (no per-pod delivery
    accounting) — same contract as ``broadcast_internal_message``.
    """
    tenant_id = order.get("tenant_id")
    booking_id = order.get("booking_id")
    if not tenant_id or not booking_id:
        logger.warning(
            "emit_order_event called without tenant/booking; event_type=%s order_id=%s",
            event_type,
            order.get("id"),
        )
        return 0
    envelope = {
        "type": "room_service_order",
        "event": event_type,
        "order": _strip_mongo_id(order),
    }

    # Local booking-scoped fan-out happens unconditionally and goes
    # directly through ``order_stream.broadcast`` so we can return the
    # *actual* per-socket delivery count (which also prunes dead sockets
    # in the same pass). Going through ``adapter.publish`` for the local
    # hop would only let us report a connection_count() proxy and would
    # re-enter the adapter's local handler, which dispatches back into
    # this same broadcast — adding an unnecessary indirection on the
    # publishing pod.
    try:
        delivered = await order_stream.broadcast(tenant_id, booking_id, envelope)
    except Exception as e:
        logger.error("Failed to emit room-service order event locally: %s", e)
        delivered = 0

    # Cross-pod booking fan-out is best-effort: we publish to Redis
    # (when the adapter is wired) so peer pods' listeners deliver the
    # event to their own guest subscribers. ``publish_remote_only``
    # skips the local handler call so we don't double-deliver on this
    # pod. When the adapter is unwired (tests, very early startup) or
    # Redis is down, this is a silent no-op and the local broadcast
    # above is the only delivery path — preserving Task #64's single-
    # pod behaviour.
    adapter = _adapter_is_wired()
    if adapter is not None:
        try:
            await adapter.publish_remote_only(
                _room_key(tenant_id, booking_id),
                "room_service_order",
                envelope,
            )
        except Exception as e:
            logger.error(
                "Failed to bridge room-service order event to peer pods: %s",
                e,
            )

    # Tenant-wide staff fan-out (Task #69) so kitchen/front-desk
    # dashboards see every order change regardless of booking. Local
    # only — staff sockets live on whichever pod the dashboard hit; a
    # cross-pod bridge for this channel can be added later via the
    # same adapter pattern when staff dashboards span pods.
    try:
        delivered += await order_stream.broadcast_staff(tenant_id, envelope)
    except Exception as e:
        logger.error("Failed to staff-emit room-service order event: %s", e)

    # Task #92: feed the rolling 1-hour gauge on the System Health
    # dashboard. We record the number of locally delivered recipients
    # rather than a single "event" so the gauge reflects how many guest/
    # staff screens were actually updated. Best-effort — never let an
    # in-memory accounting bug fail the originating HTTP request.
    try:
        order_stream.record_event_delivery(delivered)
    except Exception as e:
        logger.warning("Failed to record room-service event delivery: %s", e)

    return delivered
