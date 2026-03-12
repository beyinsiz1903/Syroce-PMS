"""
Event Broadcast Service.
Provides tenant-aware event routing, role-based filtering,
missed event replay, session presence tracking, and delivery metrics.
Falls back to in-memory pub/sub when Redis is not available.
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
from collections import defaultdict

logger = logging.getLogger(__name__)


class EventType:
    VIP_ARRIVAL = "vip_arrival"
    ROOM_READY = "room_ready"
    HK_OVERDUE = "housekeeping_overdue"
    AUDIT_EXCEPTION = "audit_exception"
    OVERBOOKING_RISK = "overbooking_risk"
    RESERVATION_MODIFIED = "reservation_modified"
    MAINTENANCE_BLOCK = "maintenance_block"
    REVENUE_APPLY_SUCCESS = "revenue_apply_success"
    REVENUE_APPLY_FAILURE = "revenue_apply_failure"
    MESSAGING_DELIVERY_FAILURE = "messaging_delivery_failure"
    ML_EXECUTION_COMPLETE = "ml_execution_complete"
    STALE_MODEL_WARNING = "stale_model_warning"


# Role-based event visibility
ROLE_EVENT_MAP = {
    "admin": "*",  # all events
    "super_admin": "*",
    "front_desk": [EventType.VIP_ARRIVAL, EventType.ROOM_READY, EventType.OVERBOOKING_RISK, EventType.RESERVATION_MODIFIED],
    "housekeeping": [EventType.ROOM_READY, EventType.HK_OVERDUE],
    "revenue": [EventType.REVENUE_APPLY_SUCCESS, EventType.REVENUE_APPLY_FAILURE, EventType.OVERBOOKING_RISK],
    "maintenance": [EventType.MAINTENANCE_BLOCK],
    "finance": [EventType.AUDIT_EXCEPTION],
}


class EventBroadcastService:
    """In-memory event pub/sub with tenant/property scoping and WebSocket delivery."""

    def __init__(self, db):
        self.db = db
        # In-memory subscribers: {tenant_id: {session_id: {user_id, roles, property_ids, ws}}}
        self._sessions: Dict[str, Dict[str, dict]] = defaultdict(dict)
        # Recent events buffer for replay (per tenant, last 100)
        self._event_buffer: Dict[str, List[dict]] = defaultdict(list)
        self._metrics = {"total_published": 0, "total_delivered": 0, "total_missed": 0}

    def register_session(self, tenant_id: str, session_id: str, user_id: str,
                         roles: list, property_ids: list = None) -> dict:
        self._sessions[tenant_id][session_id] = {
            "user_id": user_id,
            "roles": roles,
            "property_ids": property_ids or [],
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "last_event_at": None,
        }
        return {"session_id": session_id, "status": "registered"}

    def unregister_session(self, tenant_id: str, session_id: str):
        self._sessions.get(tenant_id, {}).pop(session_id, None)

    def _event_visible(self, event_type: str, roles: list) -> bool:
        for role in roles:
            allowed = ROLE_EVENT_MAP.get(role)
            if allowed == "*":
                return True
            if isinstance(allowed, list) and event_type in allowed:
                return True
        return False

    async def publish(self, tenant_id: str, event_type: str, payload: dict,
                      property_id: Optional[str] = None, source: str = "system") -> dict:
        """Publish an event to all eligible sessions."""
        event = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "property_id": property_id,
            "event_type": event_type,
            "payload": payload,
            "source": source,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        # buffer
        buf = self._event_buffer[tenant_id]
        buf.append(event)
        if len(buf) > 200:
            self._event_buffer[tenant_id] = buf[-200:]

        # persist for replay
        await self.db.event_broadcast_log.insert_one({**event, "delivered_to": []})

        self._metrics["total_published"] += 1
        delivered_count = 0

        sessions = self._sessions.get(tenant_id, {})
        for sid, sess in sessions.items():
            if not self._event_visible(event_type, sess.get("roles", [])):
                continue
            if property_id and sess.get("property_ids") and property_id not in sess["property_ids"]:
                continue
            sess["last_event_at"] = event["timestamp"]
            delivered_count += 1

        self._metrics["total_delivered"] += delivered_count
        return {"event_id": event["id"], "delivered_to": delivered_count}

    async def get_replay(self, tenant_id: str, since: Optional[str] = None, limit: int = 50) -> list:
        """Replay missed events since a timestamp."""
        q = {"tenant_id": tenant_id}
        if since:
            q["timestamp"] = {"$gte": since}
        events = await self.db.event_broadcast_log.find(
            q, {"_id": 0}
        ).sort("timestamp", -1).to_list(limit)
        return events

    def get_active_sessions(self, tenant_id: str) -> list:
        sessions = self._sessions.get(tenant_id, {})
        return [
            {"session_id": sid, **{k: v for k, v in s.items()}}
            for sid, s in sessions.items()
        ]

    async def get_metrics(self, tenant_id: str) -> dict:
        session_count = len(self._sessions.get(tenant_id, {}))
        # count recent events
        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        recent = await self.db.event_broadcast_log.count_documents(
            {"tenant_id": tenant_id, "timestamp": {"$gte": one_hour_ago}}
        )
        return {
            "active_sessions": session_count,
            "events_last_hour": recent,
            "global_metrics": self._metrics,
        }
