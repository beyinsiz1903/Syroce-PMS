"""
Security — Audit Validator
Validates audit trail completeness and detects gaps.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from core.database import db

logger = logging.getLogger(__name__)

# Operations that MUST generate audit entries
_REQUIRED_AUDITS = {
    "booking.create", "booking.update", "booking.cancel", "booking.check_in", "booking.check_out",
    "room.create", "room.update", "room.delete", "room.status_change",
    "folio.create", "folio.charge", "folio.payment", "folio.close",
    "user.create", "user.update", "user.role_change", "user.delete",
    "rate.override", "rate.update",
    "channel.connect", "channel.disconnect", "channel.sync",
}


class AuditValidator:
    """Validates that critical operations have matching audit trail entries."""

    @staticmethod
    async def validate_completeness(
        tenant_id: str, *, hours: int = 24,
    ) -> Dict[str, Any]:
        """Check audit trail completeness for the last N hours."""
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()

        # Get audit entries
        audit_entries = await db.audit_logs.find(
            {"tenant_id": tenant_id, "timestamp": {"$gte": since}},
            {"_id": 0, "action": 1, "entity_type": 1, "timestamp": 1},
        ).to_list(10000)

        # Get critical operations from collections
        bookings_modified = await db.bookings.count_documents({
            "tenant_id": tenant_id,
            "updated_at": {"$gte": since},
        })
        rooms_modified = await db.rooms.count_documents({
            "tenant_id": tenant_id,
            "updated_at": {"$gte": since},
        })

        # Count audit entries by action
        audit_actions = {}
        for entry in audit_entries:
            action = entry.get("action", "unknown")
            audit_actions[action] = audit_actions.get(action, 0) + 1

        gaps = []
        if bookings_modified > 0 and not any(a.startswith("booking") for a in audit_actions):
            gaps.append({"type": "booking_operations", "expected": bookings_modified, "audited": 0})
        if rooms_modified > 0 and not any(a.startswith("room") for a in audit_actions):
            gaps.append({"type": "room_operations", "expected": rooms_modified, "audited": 0})

        return {
            "tenant_id": tenant_id,
            "period_hours": hours,
            "total_audit_entries": len(audit_entries),
            "audit_actions": audit_actions,
            "bookings_modified": bookings_modified,
            "rooms_modified": rooms_modified,
            "gaps_found": len(gaps),
            "gaps": gaps,
            "status": "complete" if not gaps else "gaps_detected",
            "validated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    async def get_audit_summary(tenant_id: str, *, hours: int = 24) -> Dict[str, Any]:
        since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        pipeline = [
            {"$match": {"tenant_id": tenant_id, "timestamp": {"$gte": since}}},
            {"$group": {"_id": "$action", "count": {"$sum": 1}, "last": {"$max": "$timestamp"}}},
            {"$sort": {"count": -1}},
        ]
        summary = {}
        async for doc in db.audit_logs.aggregate(pipeline):
            summary[doc["_id"]] = {"count": doc["count"], "last": doc.get("last")}
        return {
            "tenant_id": tenant_id,
            "period_hours": hours,
            "actions": summary,
            "total_entries": sum(v["count"] for v in summary.values()),
        }


audit_validator = AuditValidator()
