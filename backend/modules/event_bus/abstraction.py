"""
Event Bus Abstraction Layer.
Provides a unified interface for event publishing/subscribing.
Environment-based mode selection: REDIS_URL → redis, else in_memory.
Production mode + fallback mode coexist.
"""
import logging
import asyncio
import uuid
import os
import json
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List, Callable, Any
from collections import defaultdict

from core.database import db

logger = logging.getLogger("event_bus.abstraction")


class EventPriority:
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


ROLE_EVENT_VISIBILITY = {
    "admin": "*",
    "super_admin": "*",
    "front_desk": [
        "vip_arrival", "room_ready", "overbooking_risk",
        "reservation_modified", "check_in", "check_out",
    ],
    "housekeeping": ["room_ready", "housekeeping_overdue", "room_status_change"],
    "revenue": [
        "revenue_apply_success", "revenue_apply_failure",
        "overbooking_risk", "rate_change", "autopilot_action",
    ],
    "maintenance": ["maintenance_block", "maintenance_request", "equipment_alert"],
    "finance": ["audit_exception", "payment_received", "folio_closed"],
    "guest_services": ["guest_request", "complaint", "vip_arrival"],
}


class EventEnvelope:
    """Standard event envelope with ordering and tenant scoping."""

    def __init__(self, tenant_id: str, event_type: str, payload: dict,
                 property_id: Optional[str] = None, source: str = "system",
                 priority: str = EventPriority.NORMAL,
                 correlation_id: Optional[str] = None):
        self.id = str(uuid.uuid4())
        self.tenant_id = tenant_id
        self.property_id = property_id
        self.event_type = event_type
        self.payload = payload
        self.source = source
        self.priority = priority
        self.correlation_id = correlation_id or str(uuid.uuid4())
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.sequence = 0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "tenant_id": self.tenant_id,
            "property_id": self.property_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "source": self.source,
            "priority": self.priority,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp,
            "sequence": self.sequence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EventEnvelope":
        env = cls(
            tenant_id=data["tenant_id"],
            event_type=data["event_type"],
            payload=data.get("payload", {}),
            property_id=data.get("property_id"),
            source=data.get("source", "system"),
            priority=data.get("priority", EventPriority.NORMAL),
            correlation_id=data.get("correlation_id"),
        )
        env.id = data.get("id", env.id)
        env.timestamp = data.get("timestamp", env.timestamp)
        env.sequence = data.get("sequence", 0)
        return env


class EventBusBackend:
    """Abstract backend interface."""

    async def publish(self, channel: str, event: EventEnvelope) -> bool:
        raise NotImplementedError

    async def subscribe(self, channel: str, callback: Callable) -> str:
        raise NotImplementedError

    async def unsubscribe(self, subscription_id: str) -> bool:
        raise NotImplementedError

    async def health_check(self) -> dict:
        raise NotImplementedError


class InMemoryBackend(EventBusBackend):
    """In-memory fallback when Redis is unavailable."""

    def __init__(self):
        self._subscribers: Dict[str, Dict[str, Callable]] = defaultdict(dict)
        self._published = 0
        self._delivered = 0
        self._dropped = 0

    async def publish(self, channel: str, event: EventEnvelope) -> bool:
        self._published += 1
        subs = self._subscribers.get(channel, {})
        for sub_id, callback in subs.items():
            try:
                await callback(event)
                self._delivered += 1
            except Exception as e:
                self._dropped += 1
                logger.warning(f"InMemory delivery failed sub={sub_id}: {e}")
        return True

    async def subscribe(self, channel: str, callback: Callable) -> str:
        sub_id = str(uuid.uuid4())
        self._subscribers[channel][sub_id] = callback
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> bool:
        for channel_subs in self._subscribers.values():
            if subscription_id in channel_subs:
                del channel_subs[subscription_id]
                return True
        return False

    async def health_check(self) -> dict:
        total_subs = sum(len(s) for s in self._subscribers.values())
        return {
            "backend": "in_memory",
            "status": "healthy",
            "channels": len(self._subscribers),
            "subscribers": total_subs,
            "published": self._published,
            "delivered": self._delivered,
            "dropped": self._dropped,
        }


class EventBus:
    """
    Main Event Bus orchestrator.
    - Environment-based mode selection (REDIS_URL → redis, else in_memory)
    - Tenant-aware channel routing
    - Property-scoped event routing
    - Role-based filtering
    - Event ordering (monotonic sequence per tenant)
    - Persistence for replay
    - Graceful fallback to in-memory when Redis unavailable
    - Observability hooks
    """

    def __init__(self):
        self._backend: EventBusBackend = InMemoryBackend()
        self._fallback_backend: InMemoryBackend = self._backend
        self._sequence_counters: Dict[str, int] = defaultdict(int)
        self._sessions: Dict[str, Dict[str, dict]] = defaultdict(dict)
        self._metrics = {
            "total_published": 0,
            "total_delivered": 0,
            "total_errors": 0,
            "total_dropped": 0,
            "total_fallback_used": 0,
            "by_type": defaultdict(int),
            "by_tenant": defaultdict(int),
        }
        self._mode = "in_memory"
        self._redis_backend = None
        self._initialized = False

    async def initialize(self):
        """Initialize event bus with environment-based mode selection."""
        if self._initialized:
            return

        redis_url = os.environ.get("REDIS_URL")
        if redis_url:
            from modules.event_bus.redis_pubsub import RedisPubSubBackend
            redis_backend = RedisPubSubBackend(redis_url)
            if await redis_backend.connect():
                self._redis_backend = redis_backend
                self._backend = redis_backend
                self._mode = "redis"
                logger.info("Event bus initialized in REDIS mode")
            else:
                logger.warning("Redis unavailable at startup, using in-memory fallback")
                self._mode = "in_memory"
        else:
            logger.info("Event bus initialized in IN_MEMORY mode (no REDIS_URL)")
            self._mode = "in_memory"

        self._initialized = True

    def set_backend(self, backend: EventBusBackend, mode: str = "redis"):
        self._backend = backend
        self._mode = mode
        if mode == "redis":
            self._redis_backend = backend
        logger.info(f"Event bus backend switched to: {mode}")

    @property
    def mode(self) -> str:
        return self._mode

    def _tenant_channel(self, tenant_id: str, property_id: Optional[str] = None) -> str:
        if property_id:
            return f"events:{tenant_id}:{property_id}"
        return f"events:{tenant_id}"

    def register_session(self, tenant_id: str, session_id: str, user_id: str,
                         roles: list, property_ids: list = None) -> dict:
        self._sessions[tenant_id][session_id] = {
            "user_id": user_id,
            "roles": roles,
            "property_ids": property_ids or [],
            "connected_at": datetime.now(timezone.utc).isoformat(),
            "last_event_at": None,
            "events_received": 0,
        }
        return {"session_id": session_id, "status": "registered", "mode": self._mode}

    def unregister_session(self, tenant_id: str, session_id: str):
        self._sessions.get(tenant_id, {}).pop(session_id, None)

    def _is_event_visible(self, event_type: str, roles: list) -> bool:
        for role in roles:
            allowed = ROLE_EVENT_VISIBILITY.get(role)
            if allowed == "*":
                return True
            if isinstance(allowed, list) and event_type in allowed:
                return True
        return False

    async def publish(self, tenant_id: str, event_type: str, payload: dict,
                      property_id: Optional[str] = None, source: str = "system",
                      priority: str = EventPriority.NORMAL,
                      correlation_id: Optional[str] = None) -> dict:
        """Publish an event through the bus with automatic fallback."""
        if not self._initialized:
            await self.initialize()

        self._sequence_counters[tenant_id] += 1

        envelope = EventEnvelope(
            tenant_id=tenant_id,
            event_type=event_type,
            payload=payload,
            property_id=property_id,
            source=source,
            priority=priority,
            correlation_id=correlation_id,
        )
        envelope.sequence = self._sequence_counters[tenant_id]

        # Persist for replay
        event_doc = envelope.to_dict()
        await db.event_bus_log.insert_one({**event_doc})

        # Publish to backend with fallback
        channel = self._tenant_channel(tenant_id, property_id)
        used_fallback = False
        try:
            success = await self._backend.publish(channel, envelope)
            if not success and self._mode == "redis":
                # Redis publish failed, use in-memory fallback
                await self._fallback_backend.publish(channel, envelope)
                used_fallback = True
                self._metrics["total_fallback_used"] += 1
        except Exception as e:
            logger.error(f"Backend publish failed: {e}")
            self._metrics["total_errors"] += 1
            if self._mode == "redis":
                try:
                    await self._fallback_backend.publish(channel, envelope)
                    used_fallback = True
                    self._metrics["total_fallback_used"] += 1
                except Exception:
                    self._metrics["total_dropped"] += 1

        # Deliver to registered sessions
        delivered_count = 0
        sessions = self._sessions.get(tenant_id, {})
        for sid, sess in sessions.items():
            if not self._is_event_visible(event_type, sess.get("roles", [])):
                continue
            if property_id and sess.get("property_ids") and property_id not in sess["property_ids"]:
                continue
            sess["last_event_at"] = envelope.timestamp
            sess["events_received"] = sess.get("events_received", 0) + 1
            delivered_count += 1

        self._metrics["total_published"] += 1
        self._metrics["total_delivered"] += delivered_count
        self._metrics["by_type"][event_type] += 1
        self._metrics["by_tenant"][tenant_id] += 1

        # Observability hook
        try:
            from modules.observability.metrics_collector import metrics as obs_metrics
            obs_metrics.record_event_throughput(1)
        except Exception:
            pass

        return {
            "event_id": envelope.id,
            "sequence": envelope.sequence,
            "delivered_to": delivered_count,
            "mode": self._mode,
            "used_fallback": used_fallback,
        }

    async def replay(self, tenant_id: str, since: Optional[str] = None,
                     event_types: Optional[List[str]] = None,
                     limit: int = 100) -> List[dict]:
        q: Dict[str, Any] = {"tenant_id": tenant_id}
        if since:
            q["timestamp"] = {"$gte": since}
        if event_types:
            q["event_type"] = {"$in": event_types}

        events = await db.event_bus_log.find(
            q, {"_id": 0}
        ).sort("sequence", 1).to_list(limit)
        return events

    def get_active_sessions(self, tenant_id: str) -> list:
        sessions = self._sessions.get(tenant_id, {})
        return [
            {"session_id": sid, **{k: v for k, v in s.items()}}
            for sid, s in sessions.items()
        ]

    def get_channels(self, tenant_id: Optional[str] = None) -> list:
        channels = []
        tenants = [tenant_id] if tenant_id else list(self._sessions.keys())
        for tid in tenants:
            session_count = len(self._sessions.get(tid, {}))
            channels.append({
                "tenant_id": tid,
                "channel": self._tenant_channel(tid),
                "active_sessions": session_count,
                "events_published": self._metrics["by_tenant"].get(tid, 0),
            })
        return channels

    async def get_metrics(self) -> dict:
        backend_health = await self._backend.health_check()
        one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        recent_count = await db.event_bus_log.count_documents(
            {"timestamp": {"$gte": one_hour_ago}}
        )
        total_sessions = sum(len(s) for s in self._sessions.values())

        redis_delivery_metrics = None
        if self._redis_backend:
            redis_delivery_metrics = self._redis_backend.get_delivery_metrics()

        return {
            "mode": self._mode,
            "backend": backend_health,
            "total_published": self._metrics["total_published"],
            "total_delivered": self._metrics["total_delivered"],
            "total_errors": self._metrics["total_errors"],
            "total_dropped": self._metrics["total_dropped"],
            "total_fallback_used": self._metrics["total_fallback_used"],
            "events_last_hour": recent_count,
            "active_sessions": total_sessions,
            "active_tenants": len(self._sessions),
            "top_event_types": dict(
                sorted(self._metrics["by_type"].items(), key=lambda x: -x[1])[:10]
            ),
            "redis_delivery_metrics": redis_delivery_metrics,
        }

    async def get_status(self) -> dict:
        backend_health = await self._backend.health_check()
        return {
            "mode": self._mode,
            "backend_status": backend_health.get("status", "unknown"),
            "backend_details": backend_health,
            "active_tenants": len(self._sessions),
            "total_sessions": sum(len(s) for s in self._sessions.values()),
            "redis_configured": bool(os.environ.get("REDIS_URL")),
            "fallback_available": True,
        }


# Singleton
event_bus = EventBus()
