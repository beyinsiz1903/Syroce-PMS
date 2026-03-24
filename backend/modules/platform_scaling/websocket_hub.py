"""
Enterprise WebSocket Hub - Production-grade real-time push system.
Authenticated sessions, tenant-aware channels, role-based filtering,
heartbeat/keepalive, event replay, reconnect tokens.
"""
import asyncio
import json
import logging
import os
import time
import uuid
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

import jwt

from core.database import db

logger = logging.getLogger(__name__)

JWT_SECRET = os.environ.get("JWT_SECRET", "")
JWT_ALGORITHM = "HS256"

# Role-based event filter mapping
ROLE_EVENT_FILTER = {
    "admin": None,  # None = all events
    "super_admin": None,
    "revenue": {
        "rate_alert", "revenue_alert", "demand_spike", "competitor_price_change",
        "ml_prediction_alert", "occupancy_threshold_breach", "channel_parity_violation",
        "auto_pricing_applied", "auto_pricing_rollback", "pricing_approval_needed",
    },
    "front_desk": {
        "check_in_created", "guest_arrived", "vip_arrival", "reservation_modified",
        "checkout_completed", "guest_complaint_escalation", "cross_property_transfer",
        "overbooking_risk", "reservation_risk_warning", "walk_in_alert",
    },
    "housekeeping": {
        "housekeeping_task_overdue", "room_ready", "checkout_completed",
        "vip_room_priority", "guest_request_housekeeping", "room_inspection_needed",
    },
    "maintenance": {"maintenance_block", "system_health_alert", "equipment_alert"},
    "night_auditor": {"night_audit_completed", "audit_exception", "audit_escalation"},
    "concierge": {"vip_arrival", "guest_arrived", "guest_complaint_escalation", "guest_request_new"},
    "finance": {"revenue_alert", "folio_exception", "payment_failure", "night_audit_completed"},
}

HEARTBEAT_INTERVAL = 30  # seconds
EVENT_REPLAY_BUFFER_SIZE = 500  # per tenant


class WebSocketSession:
    """Represents a single authenticated WebSocket connection."""
    __slots__ = (
        "session_id", "websocket", "tenant_id", "user_id", "role",
        "channels", "connected_at", "last_heartbeat", "reconnect_token",
    )

    def __init__(self, websocket, tenant_id: str, user_id: str, role: str):
        self.session_id = str(uuid.uuid4())
        self.websocket = websocket
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.role = role
        self.channels: Set[str] = {"general"}
        self.connected_at = time.time()
        self.last_heartbeat = time.time()
        self.reconnect_token = str(uuid.uuid4())


class EventReplayBuffer:
    """Per-tenant circular buffer for event replay on reconnect."""

    def __init__(self, max_size: int = EVENT_REPLAY_BUFFER_SIZE):
        self._buffers: Dict[str, deque] = defaultdict(lambda: deque(maxlen=max_size))

    def append(self, tenant_id: str, event: Dict[str, Any]):
        event["_ts"] = time.time()
        self._buffers[tenant_id].append(event)

    def get_since(self, tenant_id: str, since_ts: float) -> List[Dict[str, Any]]:
        return [e for e in self._buffers.get(tenant_id, []) if e.get("_ts", 0) > since_ts]


class WebSocketHub:
    """
    Central WebSocket connection manager.
    Handles auth, tenant isolation, role filtering, heartbeat, replay.
    """

    def __init__(self):
        self._sessions: Dict[str, WebSocketSession] = {}  # session_id -> session
        self._tenant_sessions: Dict[str, Set[str]] = defaultdict(set)  # tenant_id -> set(session_id)
        self._user_sessions: Dict[str, Set[str]] = defaultdict(set)  # user_id -> set(session_id)
        self._reconnect_tokens: Dict[str, str] = {}  # token -> session_id (for replay)
        self._replay_buffer = EventReplayBuffer()
        self._heartbeat_task: Optional[asyncio.Task] = None

    async def authenticate_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Validate JWT and return user context."""
        try:
            payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            user_id = payload.get("user_id")
            tenant_id = payload.get("tenant_id")
            if not user_id:
                return None
            user_doc = await db.users.find_one(
                {"$or": [{"id": user_id}, {"user_id": user_id}]},
                {"_id": 0, "id": 1, "user_id": 1, "tenant_id": 1, "role": 1, "name": 1},
            )
            if not user_doc:
                return None
            return {
                "user_id": user_doc.get("id") or user_doc.get("user_id"),
                "tenant_id": user_doc.get("tenant_id") or tenant_id,
                "role": user_doc.get("role", "staff"),
                "name": user_doc.get("name", ""),
            }
        except Exception as e:
            logger.warning(f"WS auth failed: {e}")
            return None

    async def connect(self, websocket, token: str, last_event_ts: Optional[float] = None) -> Optional[WebSocketSession]:
        """Authenticate and register a WebSocket connection."""
        user_ctx = await self.authenticate_token(token)
        if not user_ctx:
            return None

        session = WebSocketSession(
            websocket=websocket,
            tenant_id=user_ctx["tenant_id"],
            user_id=user_ctx["user_id"],
            role=user_ctx["role"],
        )
        self._sessions[session.session_id] = session
        self._tenant_sessions[session.tenant_id].add(session.session_id)
        self._user_sessions[session.user_id].add(session.session_id)
        self._reconnect_tokens[session.reconnect_token] = session.session_id

        # Send connection ack
        await self._send(session, {
            "type": "connection_established",
            "session_id": session.session_id,
            "reconnect_token": session.reconnect_token,
            "role": session.role,
            "tenant_id": session.tenant_id,
            "heartbeat_interval": HEARTBEAT_INTERVAL,
        })

        # Replay missed events if reconnecting
        if last_event_ts:
            missed = self._replay_buffer.get_since(session.tenant_id, last_event_ts)
            filtered = self._filter_events_for_role(missed, session.role)
            if filtered:
                await self._send(session, {
                    "type": "event_replay",
                    "count": len(filtered),
                    "events": filtered,
                })

        # Log connection
        await db.ws_connection_log.insert_one({
            "session_id": session.session_id,
            "tenant_id": session.tenant_id,
            "user_id": session.user_id,
            "role": session.role,
            "action": "connect",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        logger.info(f"WS connected: user={session.user_id} tenant={session.tenant_id} role={session.role}")
        return session

    async def disconnect(self, session_id: str):
        """Clean up a disconnected session."""
        session = self._sessions.pop(session_id, None)
        if not session:
            return
        self._tenant_sessions[session.tenant_id].discard(session_id)
        self._user_sessions[session.user_id].discard(session_id)
        self._reconnect_tokens.pop(session.reconnect_token, None)

        await db.ws_connection_log.insert_one({
            "session_id": session_id,
            "tenant_id": session.tenant_id,
            "user_id": session.user_id,
            "action": "disconnect",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"WS disconnected: session={session_id}")

    async def handle_message(self, session_id: str, raw: str):
        """Process incoming WebSocket message."""
        session = self._sessions.get(session_id)
        if not session:
            return

        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = msg.get("type", "")

        if msg_type == "heartbeat":
            session.last_heartbeat = time.time()
            await self._send(session, {"type": "heartbeat_ack", "ts": time.time()})

        elif msg_type == "subscribe":
            channel = msg.get("channel", "")
            if channel:
                session.channels.add(channel)
                await self._send(session, {"type": "subscribed", "channel": channel})

        elif msg_type == "unsubscribe":
            channel = msg.get("channel", "")
            session.channels.discard(channel)
            await self._send(session, {"type": "unsubscribed", "channel": channel})

    # ── Broadcasting ──

    async def broadcast_to_tenant(self, tenant_id: str, event: Dict[str, Any], channel: str = "general"):
        """Broadcast event to all sessions of a tenant, filtered by role."""
        event["channel"] = channel
        event["broadcast_at"] = datetime.now(timezone.utc).isoformat()
        self._replay_buffer.append(tenant_id, event)

        session_ids = list(self._tenant_sessions.get(tenant_id, set()))
        for sid in session_ids:
            session = self._sessions.get(sid)
            if not session:
                continue
            if channel not in session.channels and channel != "general":
                continue
            if not self._event_passes_role_filter(event, session.role):
                continue
            await self._send(session, event)

    async def broadcast_to_user(self, user_id: str, event: Dict[str, Any]):
        """Send event to a specific user's sessions."""
        session_ids = list(self._user_sessions.get(user_id, set()))
        for sid in session_ids:
            session = self._sessions.get(sid)
            if session:
                await self._send(session, event)

    async def broadcast_to_role(self, tenant_id: str, role: str, event: Dict[str, Any]):
        """Broadcast to all sessions with a specific role in a tenant."""
        event["broadcast_at"] = datetime.now(timezone.utc).isoformat()
        session_ids = list(self._tenant_sessions.get(tenant_id, set()))
        for sid in session_ids:
            session = self._sessions.get(sid)
            if session and session.role == role:
                await self._send(session, event)

    # ── Helpers ──

    def _event_passes_role_filter(self, event: Dict, role: str) -> bool:
        allowed = ROLE_EVENT_FILTER.get(role)
        if allowed is None:
            return True  # admin sees everything
        event_type = event.get("event_type", event.get("type", ""))
        return event_type in allowed

    def _filter_events_for_role(self, events: List[Dict], role: str) -> List[Dict]:
        allowed = ROLE_EVENT_FILTER.get(role)
        if allowed is None:
            return events
        return [e for e in events if e.get("event_type", e.get("type", "")) in allowed]

    async def _send(self, session: WebSocketSession, data: Dict[str, Any]):
        try:
            await session.websocket.send_json(data)
        except Exception:
            await self.disconnect(session.session_id)

    # ── Stats ──

    def get_stats(self) -> Dict[str, Any]:
        tenant_counts = {t: len(sids) for t, sids in self._tenant_sessions.items() if sids}
        return {
            "total_connections": len(self._sessions),
            "tenants_connected": len(tenant_counts),
            "connections_by_tenant": tenant_counts,
            "replay_buffer_tenants": len(self._replay_buffer._buffers),
        }

    async def get_tenant_live_data(self, tenant_id: str) -> Dict[str, Any]:
        """Get current live operational data for tenant's dashboard."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # Front desk queue
        front_desk_queue = await db.bookings.find(
            {"tenant_id": tenant_id, "check_in": today,
             "status": {"$in": ["confirmed", "guaranteed"]}},
            {"_id": 0, "id": 1, "guest_name": 1, "room_id": 1, "check_in": 1,
             "room_type": 1, "vip_status": 1, "estimated_arrival_time": 1},
        ).sort("estimated_arrival_time", 1).limit(50).to_list(50)

        # Housekeeping board
        hk_tasks = await db.housekeeping_tasks.find(
            {"tenant_id": tenant_id, "status": {"$in": ["pending", "assigned", "in_progress"]}},
            {"_id": 0, "id": 1, "room_id": 1, "task_type": 1, "status": 1,
             "priority": 1, "assigned_to": 1, "created_at": 1},
        ).sort("priority", -1).limit(50).to_list(50)

        # Audit exceptions (last 24h)
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        audit_exceptions = await db.platform_events.find(
            {"tenant_id": tenant_id, "event_type": "audit_exception",
             "created_at": {"$gte": cutoff}},
            {"_id": 0},
        ).sort("created_at", -1).limit(20).to_list(20)

        # VIP arrivals
        vip_arrivals = await db.bookings.find(
            {"tenant_id": tenant_id, "check_in": today,
             "status": {"$in": ["confirmed", "guaranteed"]},
             "$or": [{"vip_status": True}, {"tags": "vip"}]},
            {"_id": 0, "id": 1, "guest_name": 1, "room_id": 1, "room_type": 1},
        ).to_list(20)

        # Overbooking risk
        total_rooms = await db.rooms.count_documents({
            "tenant_id": tenant_id,
            "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
        })
        booked = await db.bookings.count_documents({
            "tenant_id": tenant_id,
            "check_in": {"$lte": today}, "check_out": {"$gt": today},
            "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
        })
        overbooking_risk = booked >= total_rooms if total_rooms > 0 else False

        return {
            "tenant_id": tenant_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "front_desk_queue": {"count": len(front_desk_queue), "items": front_desk_queue},
            "housekeeping_board": {"count": len(hk_tasks), "items": hk_tasks},
            "audit_exceptions": {"count": len(audit_exceptions), "items": audit_exceptions},
            "vip_arrivals": {"count": len(vip_arrivals), "items": vip_arrivals},
            "overbooking_risk": overbooking_risk,
            "occupancy": {
                "total_rooms": total_rooms,
                "booked": booked,
                "available": max(total_rooms - booked, 0),
                "pct": round((booked / max(total_rooms, 1)) * 100, 1),
            },
        }


# Singleton instance
ws_hub = WebSocketHub()
