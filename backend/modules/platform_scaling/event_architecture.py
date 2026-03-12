"""
Real-Time Event Architecture - Enhanced event bus with WebSocket gateway,
event persistence, and operational notification system.
Extends existing EventBus with enterprise-grade features.
"""
import uuid
import asyncio
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional, Set
from collections import defaultdict
from core.database import db


# ── ENHANCED EVENT TYPES ──
PLATFORM_EVENT_TYPES = [
    # Existing
    "check_in_created", "guest_arrived", "housekeeping_task_overdue",
    "room_ready", "audit_exception", "overbooking_risk",
    "reservation_modified", "maintenance_block", "checkout_completed",
    "vip_arrival", "rate_alert", "night_audit_completed",
    # New platform-level events
    "cross_property_transfer", "global_rate_update", "revenue_alert",
    "demand_spike", "cancellation_wave", "competitor_price_change",
    "ml_prediction_alert", "multi_property_sync",
    "occupancy_threshold_breach", "channel_parity_violation",
    "guest_complaint_escalation", "system_health_alert",
]

# ── NOTIFICATION ROUTING ──
NOTIFICATION_ROUTING = {
    "critical": {"channels": ["websocket", "push", "dashboard", "email"], "escalation_minutes": 5},
    "high": {"channels": ["websocket", "push", "dashboard"], "escalation_minutes": 15},
    "medium": {"channels": ["websocket", "dashboard"], "escalation_minutes": 60},
    "low": {"channels": ["dashboard"], "escalation_minutes": None},
}

ROLE_EVENT_MAPPING = {
    "admin": PLATFORM_EVENT_TYPES,
    "revenue": ["rate_alert", "revenue_alert", "demand_spike", "competitor_price_change",
                 "ml_prediction_alert", "occupancy_threshold_breach", "channel_parity_violation"],
    "front_desk": ["check_in_created", "guest_arrived", "vip_arrival", "reservation_modified",
                    "checkout_completed", "guest_complaint_escalation", "cross_property_transfer"],
    "housekeeping": ["housekeeping_task_overdue", "room_ready", "checkout_completed"],
    "maintenance": ["maintenance_block", "system_health_alert"],
    "night_auditor": ["night_audit_completed", "audit_exception"],
    "concierge": ["vip_arrival", "guest_arrived", "guest_complaint_escalation"],
}


class WebSocketGateway:
    """In-memory WebSocket connection registry for real-time push."""

    def __init__(self):
        self._connections: Dict[str, Set[str]] = defaultdict(set)
        self._event_log: List[Dict] = []

    def register(self, tenant_id: str, session_id: str):
        self._connections[tenant_id].add(session_id)

    def unregister(self, tenant_id: str, session_id: str):
        self._connections[tenant_id].discard(session_id)

    def get_active_connections(self, tenant_id: str) -> int:
        return len(self._connections.get(tenant_id, set()))

    async def broadcast(self, tenant_id: str, event: Dict[str, Any]):
        """Broadcast event to all connected sessions for a tenant."""
        self._event_log.append({
            "tenant_id": tenant_id,
            "event_type": event.get("event_type"),
            "broadcast_at": datetime.now(timezone.utc).isoformat(),
            "target_sessions": self.get_active_connections(tenant_id),
        })
        # In production, this would push via actual WebSocket connections
        # For now, events are persisted in DB and fetched via polling/SSE

    def get_gateway_stats(self) -> Dict[str, Any]:
        total_connections = sum(len(s) for s in self._connections.values())
        return {
            "total_connections": total_connections,
            "tenants_connected": len(self._connections),
            "recent_broadcasts": len(self._event_log[-100:]),
        }


class EnhancedEventBus:
    """Enterprise event bus with persistence, routing, and notification management."""

    def __init__(self):
        self.gateway = WebSocketGateway()

    async def publish_event(self, tenant_id: str, event_type: str, payload: Dict[str, Any],
                            user_id: Optional[str] = None, property_id: Optional[str] = None,
                            priority: Optional[str] = None) -> Dict[str, Any]:
        """Publish event with enhanced routing and persistence."""
        if event_type not in PLATFORM_EVENT_TYPES:
            return {"success": False, "error": f"Unknown event type: {event_type}"}

        # Auto-determine priority if not set
        if not priority:
            if event_type in ("overbooking_risk", "system_health_alert", "cancellation_wave"):
                priority = "critical"
            elif event_type in ("vip_arrival", "demand_spike", "competitor_price_change",
                                "revenue_alert", "guest_complaint_escalation"):
                priority = "high"
            elif event_type in ("rate_alert", "ml_prediction_alert", "occupancy_threshold_breach"):
                priority = "medium"
            else:
                priority = "low"

        routing = NOTIFICATION_ROUTING.get(priority, NOTIFICATION_ROUTING["low"])
        target_roles = [role for role, events in ROLE_EVENT_MAPPING.items() if event_type in events]

        event = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "property_id": property_id or tenant_id,
            "event_type": event_type,
            "payload": payload,
            "priority": priority,
            "channels": routing["channels"],
            "target_roles": target_roles,
            "escalation_minutes": routing.get("escalation_minutes"),
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "read": False,
            "acknowledged": False,
            "escalated": False,
        }

        await db.platform_events.insert_one(event)
        await self.gateway.broadcast(tenant_id, event)

        # Create notification records per target role
        for role in target_roles:
            notif = {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "event_id": event["id"],
                "event_type": event_type,
                "priority": priority,
                "target_role": role,
                "title": self._event_title(event_type, payload),
                "message": self._event_message(event_type, payload),
                "read": False,
                "created_at": event["created_at"],
            }
            await db.platform_notifications.insert_one(notif)

        return {"success": True, "event_id": event["id"], "priority": priority,
                "broadcast_to": self.gateway.get_active_connections(tenant_id)}

    def _event_title(self, event_type: str, payload: Dict) -> str:
        titles = {
            "demand_spike": "Talep Artisi Tespit Edildi",
            "competitor_price_change": "Rakip Fiyat Degisikligi",
            "ml_prediction_alert": "ML Tahmin Uyarisi",
            "revenue_alert": "Gelir Uyarisi",
            "cancellation_wave": "Iptal Dalgasi",
            "cross_property_transfer": "Property Arasi Transfer",
            "occupancy_threshold_breach": "Doluluk Esik Asildi",
            "channel_parity_violation": "Kanal Parite Ihlali",
            "guest_complaint_escalation": "Misafir Sikayeti Eskalasyonu",
            "system_health_alert": "Sistem Saglik Uyarisi",
            "global_rate_update": "Global Fiyat Guncelleme",
            "multi_property_sync": "Multi-Property Senkronizasyon",
        }
        return titles.get(event_type, event_type.replace("_", " ").title())

    def _event_message(self, event_type: str, payload: Dict) -> str:
        desc = payload.get("description") or payload.get("message") or ""
        if desc:
            return desc[:200]
        return f"{event_type} olayi gerceklesti"

    async def get_event_stream(self, tenant_id: str, limit: int = 100,
                                event_type: Optional[str] = None,
                                priority: Optional[str] = None,
                                property_id: Optional[str] = None,
                                since: Optional[str] = None) -> Dict[str, Any]:
        """Get event stream with advanced filtering."""
        query: Dict[str, Any] = {"tenant_id": tenant_id}
        if event_type:
            query["event_type"] = event_type
        if priority:
            query["priority"] = priority
        if property_id:
            query["property_id"] = property_id
        if since:
            query["created_at"] = {"$gte": since}

        events = await db.platform_events.find(
            query, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)

        return {"tenant_id": tenant_id, "count": len(events), "events": events}

    async def get_notifications(self, tenant_id: str, role: Optional[str] = None,
                                 unread_only: bool = False, limit: int = 50) -> Dict[str, Any]:
        """Get notifications for a role."""
        query: Dict[str, Any] = {"tenant_id": tenant_id}
        if role:
            query["target_role"] = role
        if unread_only:
            query["read"] = False

        notifs = await db.platform_notifications.find(
            query, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)

        unread_count = await db.platform_notifications.count_documents(
            {"tenant_id": tenant_id, "read": False, **({"target_role": role} if role else {})}
        )

        return {"count": len(notifs), "unread_count": unread_count, "notifications": notifs}

    async def mark_notifications_read(self, tenant_id: str, notification_ids: List[str]) -> Dict[str, Any]:
        """Mark notifications as read."""
        result = await db.platform_notifications.update_many(
            {"tenant_id": tenant_id, "id": {"$in": notification_ids}},
            {"$set": {"read": True, "read_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"success": True, "modified": result.modified_count}

    async def acknowledge_event(self, tenant_id: str, event_id: str,
                                 user_id: str, note: Optional[str] = None) -> Dict[str, Any]:
        """Acknowledge a platform event."""
        result = await db.platform_events.update_one(
            {"tenant_id": tenant_id, "id": event_id},
            {"$set": {
                "acknowledged": True,
                "acknowledged_by": user_id,
                "acknowledged_at": datetime.now(timezone.utc).isoformat(),
                "acknowledge_note": note,
            }},
        )
        if result.matched_count == 0:
            return {"success": False, "error": "Event not found"}
        return {"success": True, "event_id": event_id}

    async def get_event_analytics(self, tenant_id: str, hours: int = 24) -> Dict[str, Any]:
        """Get event analytics for the platform."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        events = await db.platform_events.find(
            {"tenant_id": tenant_id, "created_at": {"$gte": cutoff}},
            {"_id": 0, "event_type": 1, "priority": 1, "acknowledged": 1, "property_id": 1},
        ).to_list(10000)

        by_type = {}
        by_priority = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        by_property = {}
        unack_critical = 0

        for e in events:
            et = e.get("event_type", "unknown")
            by_type[et] = by_type.get(et, 0) + 1
            p = e.get("priority", "low")
            by_priority[p] = by_priority.get(p, 0) + 1
            prop = e.get("property_id", "default")
            by_property[prop] = by_property.get(prop, 0) + 1
            if p in ("critical", "high") and not e.get("acknowledged"):
                unack_critical += 1

        return {
            "period_hours": hours,
            "total_events": len(events),
            "by_type": by_type,
            "by_priority": by_priority,
            "by_property": by_property,
            "unacknowledged_critical": unack_critical,
            "gateway_stats": self.gateway.get_gateway_stats(),
        }

    async def get_escalation_queue(self, tenant_id: str) -> Dict[str, Any]:
        """Get events that need escalation (unacknowledged past their threshold)."""
        now = datetime.now(timezone.utc)
        events = await db.platform_events.find(
            {"tenant_id": tenant_id, "acknowledged": False,
             "priority": {"$in": ["critical", "high"]},
             "escalation_minutes": {"$ne": None}},
            {"_id": 0},
        ).sort("created_at", 1).to_list(100)

        escalation_needed = []
        for e in events:
            created = datetime.fromisoformat(e["created_at"].replace("Z", "+00:00"))
            threshold = timedelta(minutes=e.get("escalation_minutes", 15))
            if now - created > threshold:
                e["overdue_minutes"] = round((now - created).total_seconds() / 60, 1)
                escalation_needed.append(e)

        return {"count": len(escalation_needed), "events": escalation_needed}
