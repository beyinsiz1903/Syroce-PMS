"""
Real-Time Operational Event System - Event Bus, Persistence, WebSocket Gateway.
Handles hotel operational events: check-in, guest arrival, HK overdue, room ready, etc.
"""
import uuid
from datetime import UTC, datetime
from typing import Any

from core.database import db

# ── EVENT TYPES ──
EVENT_TYPES = [
    "check_in_created",
    "guest_arrived",
    "housekeeping_task_overdue",
    "room_ready",
    "audit_exception",
    "overbooking_risk",
    "reservation_modified",
    "maintenance_block",
    "checkout_completed",
    "vip_arrival",
    "rate_alert",
    "night_audit_completed",
]

# ── NOTIFICATION RULES ──
NOTIFICATION_RULES = {
    "vip_arrival": {"priority": "high", "channels": ["dashboard", "toast", "push"], "roles": ["admin", "front_desk", "concierge"]},
    "housekeeping_task_overdue": {"priority": "high", "channels": ["dashboard", "toast"], "roles": ["admin", "housekeeping"]},
    "audit_exception": {"priority": "high", "channels": ["dashboard", "toast"], "roles": ["admin", "night_auditor", "finance"]},
    "overbooking_risk": {"priority": "critical", "channels": ["dashboard", "toast", "push"], "roles": ["admin", "front_desk", "revenue"]},
    "room_ready": {"priority": "medium", "channels": ["dashboard"], "roles": ["front_desk", "housekeeping"]},
    "check_in_created": {"priority": "medium", "channels": ["dashboard"], "roles": ["front_desk"]},
    "guest_arrived": {"priority": "medium", "channels": ["dashboard"], "roles": ["front_desk", "concierge"]},
    "reservation_modified": {"priority": "low", "channels": ["dashboard"], "roles": ["front_desk"]},
    "maintenance_block": {"priority": "medium", "channels": ["dashboard"], "roles": ["admin", "maintenance", "housekeeping"]},
    "checkout_completed": {"priority": "low", "channels": ["dashboard"], "roles": ["front_desk", "housekeeping"]},
    "rate_alert": {"priority": "medium", "channels": ["dashboard"], "roles": ["admin", "revenue"]},
    "night_audit_completed": {"priority": "low", "channels": ["dashboard"], "roles": ["admin", "night_auditor"]},
}


class EventBus:
    """Central event bus for publishing and persisting operational events."""

    async def publish(self, tenant_id: str, event_type: str, payload: dict[str, Any],
                      user_id: str | None = None, property_id: str | None = None) -> dict[str, Any]:
        """Publish an operational event to the event bus."""
        if event_type not in EVENT_TYPES:
            return {"success": False, "error": f"Unknown event type: {event_type}"}

        rule = NOTIFICATION_RULES.get(event_type, {})
        event = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "property_id": property_id or tenant_id,
            "event_type": event_type,
            "payload": payload,
            "priority": rule.get("priority", "low"),
            "channels": rule.get("channels", ["dashboard"]),
            "target_roles": rule.get("roles", []),
            "user_id": user_id,
            "created_at": datetime.now(UTC).isoformat(),
            "read": False,
            "acknowledged": False,
        }

        await db.operational_events.insert_one(event)
        return {"success": True, "event_id": event["id"], "event_type": event_type, "priority": event["priority"]}

    async def get_live_feed(self, tenant_id: str, limit: int = 50,
                            event_type: str | None = None,
                            priority: str | None = None) -> dict[str, Any]:
        """Get live activity feed for the operational dashboard."""
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if event_type:
            query["event_type"] = event_type
        if priority:
            query["priority"] = priority

        events = await db.operational_events.find(
            query, {"_id": 0}
        ).sort("created_at", -1).limit(limit).to_list(limit)

        return {
            "tenant_id": tenant_id,
            "count": len(events),
            "events": events,
        }

    async def get_unread_count(self, tenant_id: str, role: str | None = None) -> dict[str, Any]:
        """Get count of unread events, optionally filtered by target role."""
        query: dict[str, Any] = {"tenant_id": tenant_id, "read": False}
        if role:
            query["target_roles"] = role

        count = await db.operational_events.count_documents(query)

        # Count by priority
        critical = await db.operational_events.count_documents({**query, "priority": "critical"})
        high = await db.operational_events.count_documents({**query, "priority": "high"})

        return {
            "total_unread": count,
            "critical": critical,
            "high": high,
            "normal": count - critical - high,
        }

    async def mark_read(self, tenant_id: str, event_ids: list[str]) -> dict[str, Any]:
        """Mark events as read."""
        result = await db.operational_events.update_many(
            {"tenant_id": tenant_id, "id": {"$in": event_ids}},
            {"$set": {"read": True, "read_at": datetime.now(UTC).isoformat()}},
        )
        return {"success": True, "modified": result.modified_count}

    async def acknowledge_event(self, tenant_id: str, event_id: str, user_id: str, note: str | None = None) -> dict[str, Any]:
        """Acknowledge a critical/high priority event."""
        result = await db.operational_events.update_one(
            {"tenant_id": tenant_id, "id": event_id},
            {"$set": {
                "acknowledged": True,
                "acknowledged_by": user_id,
                "acknowledged_at": datetime.now(UTC).isoformat(),
                "acknowledge_note": note,
            }},
        )
        if result.matched_count == 0:
            return {"success": False, "error": "Event not found"}
        return {"success": True, "event_id": event_id}

    async def get_event_stats(self, tenant_id: str, hours: int = 24) -> dict[str, Any]:
        """Get event statistics for the last N hours."""
        cutoff = (datetime.now(UTC) - timedelta(hours=hours)).isoformat()
        events = await db.operational_events.find(
            {"tenant_id": tenant_id, "created_at": {"$gte": cutoff}},
            {"_id": 0, "event_type": 1, "priority": 1, "acknowledged": 1},
        ).to_list(5000)

        by_type = {}
        by_priority = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        unack_critical = 0

        for e in events:
            et = e.get("event_type", "unknown")
            by_type[et] = by_type.get(et, 0) + 1
            p = e.get("priority", "low")
            by_priority[p] = by_priority.get(p, 0) + 1
            if p in ("critical", "high") and not e.get("acknowledged"):
                unack_critical += 1

        return {
            "period_hours": hours,
            "total_events": len(events),
            "by_type": by_type,
            "by_priority": by_priority,
            "unacknowledged_critical": unack_critical,
        }

    async def get_front_desk_queue(self, tenant_id: str) -> dict[str, Any]:
        """Get front desk live queue - pending arrivals, departures, requests."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")

        arrivals = await db.bookings.find(
            {"tenant_id": tenant_id, "check_in": today, "status": {"$in": ["confirmed", "guaranteed"]}},
            {"_id": 0, "id": 1, "guest_name": 1, "room_id": 1, "check_in": 1, "vip": 1, "source": 1},
        ).to_list(200)

        departures = await db.bookings.find(
            {"tenant_id": tenant_id, "check_out": today, "status": "checked_in"},
            {"_id": 0, "id": 1, "guest_name": 1, "room_id": 1, "check_out": 1},
        ).to_list(200)

        # Recent events for front desk
        recent = await db.operational_events.find(
            {"tenant_id": tenant_id, "target_roles": "front_desk", "read": False},
            {"_id": 0},
        ).sort("created_at", -1).limit(20).to_list(20)

        return {
            "pending_arrivals": len(arrivals),
            "arrivals": arrivals,
            "pending_departures": len(departures),
            "departures": departures,
            "alerts": recent,
        }

    async def get_housekeeping_board(self, tenant_id: str) -> dict[str, Any]:
        """Get housekeeping live board with pending tasks and alerts."""
        rooms = await db.rooms.find(
            {"tenant_id": tenant_id},
            {"_id": 0, "id": 1, "room_number": 1, "room_type": 1, "status": 1, "floor": 1},
        ).to_list(1000)

        dirty = [r for r in rooms if r.get("status") == "dirty"]
        cleaning = [r for r in rooms if r.get("status") == "cleaning"]
        inspected = [r for r in rooms if r.get("status") == "inspected"]
        clean = [r for r in rooms if r.get("status") in ("clean", "available")]

        # Overdue HK events
        overdue_events = await db.operational_events.find(
            {"tenant_id": tenant_id, "event_type": "housekeeping_task_overdue", "acknowledged": False},
            {"_id": 0},
        ).sort("created_at", -1).limit(20).to_list(20)

        return {
            "summary": {
                "dirty": len(dirty),
                "cleaning": len(cleaning),
                "inspected": len(inspected),
                "clean": len(clean),
                "total": len(rooms),
            },
            "dirty_rooms": dirty[:20],
            "overdue_alerts": overdue_events,
        }


# Singleton for import convenience
from datetime import timedelta  # noqa: E402
