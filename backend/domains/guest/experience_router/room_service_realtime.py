"""Real-time room-service order updates (Task #64).

In-process pub/sub keyed by ``(tenant_id, booking_id)``. Mobile guest app
opens a WebSocket per active booking; ``emit_order_event`` pushes order
updates so we don't need 15s polling. Single-pod scope today; can be
fronted by ``infra/ws_redis_adapter`` for horizontal scaling without
changing the API surface.
"""
from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket

logger = logging.getLogger(__name__)


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

    async def connect(self, ws: WebSocket, tenant_id: str, booking_id: str) -> None:
        await ws.accept()
        async with self._lock:
            self._connections[(tenant_id, booking_id)].add(ws)
        logger.info(
            "room-service WS connected tenant=%s booking=%s (total=%d)",
            tenant_id, booking_id,
            len(self._connections.get((tenant_id, booking_id), set())),
        )

    async def disconnect(
        self, ws: WebSocket, tenant_id: str, booking_id: str
    ) -> None:
        async with self._lock:
            key = (tenant_id, booking_id)
            bucket = self._connections.get(key)
            if bucket is None:
                return
            bucket.discard(ws)
            if not bucket:
                self._connections.pop(key, None)
        logger.info(
            "room-service WS disconnected tenant=%s booking=%s",
            tenant_id, booking_id,
        )

    async def broadcast(
        self, tenant_id: str, booking_id: str, event: dict[str, Any]
    ) -> int:
        """Send ``event`` to every socket on this (tenant, booking).
        Returns delivery count; prunes dead sockets."""
        async with self._lock:
            conns = list(self._connections.get((tenant_id, booking_id), set()))
        if not conns:
            return 0
        payload = json.dumps({
            **event,
            "timestamp": datetime.now(UTC).isoformat(),
        })
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
            "room-service staff WS disconnected tenant=%s", tenant_id,
        )

    async def broadcast_staff(
        self, tenant_id: str, event: dict[str, Any]
    ) -> int:
        """Send ``event`` to every staff socket subscribed to this
        tenant. Used so kitchen/front-desk dashboards see every order
        change regardless of which booking it belongs to."""
        async with self._lock:
            conns = list(self._staff_connections.get(tenant_id, set()))
        if not conns:
            return 0
        payload = json.dumps({
            **event,
            "timestamp": datetime.now(UTC).isoformat(),
        })
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


async def emit_order_event(
    order: dict[str, Any], event_type: str = "updated"
) -> int:
    """Broadcast a room-service order event to subscribers of the
    order's booking. ``event_type`` is ``"created"`` or ``"status_changed"``.
    Tenant + booking are read from the order doc; missing → silent no-op
    so a broadcast failure can't break the originating HTTP request."""
    tenant_id = order.get("tenant_id")
    booking_id = order.get("booking_id")
    if not tenant_id or not booking_id:
        logger.warning(
            "emit_order_event called without tenant/booking; "
            "event_type=%s order_id=%s",
            event_type, order.get("id"),
        )
        return 0
    event = {
        "type": "room_service_order",
        "event": event_type,
        "order": _strip_mongo_id(order),
    }
    delivered = 0
    try:
        delivered += await order_stream.broadcast(tenant_id, booking_id, event)
    except Exception as e:
        logger.error("Failed to emit room-service order event: %s", e)
    # Tenant-wide staff fan-out (Task #69) so kitchen/front-desk
    # dashboards see every order change, regardless of booking.
    try:
        delivered += await order_stream.broadcast_staff(tenant_id, event)
    except Exception as e:
        logger.error("Failed to staff-emit room-service order event: %s", e)
    return delivered
