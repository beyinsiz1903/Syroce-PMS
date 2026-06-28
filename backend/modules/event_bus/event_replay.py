"""
Event Replay Service.
Supports reconnection recovery and missed event delivery.
"""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db

logger = logging.getLogger("event_bus.replay")


class EventReplayService:
    """Manages event replay for reconnected clients."""

    async def get_missed_events(self, tenant_id: str, last_sequence: int, property_id: str | None = None, limit: int = 200) -> list[dict]:
        """Get events missed by a client since their last known sequence."""
        q: dict[str, Any] = {
            "tenant_id": tenant_id,
            "sequence": {"$gt": last_sequence},
        }
        if property_id:
            q["property_id"] = property_id

        events = await db.event_bus_log.find(q, {"_id": 0}).sort("sequence", 1).to_list(limit)
        return events

    async def get_events_since(self, tenant_id: str, since_iso: str, event_types: list[str] | None = None, limit: int = 100) -> list[dict]:
        """Get events since a specific timestamp."""
        q: dict[str, Any] = {
            "tenant_id": tenant_id,
            "timestamp": {"$gte": since_iso},
        }
        if event_types:
            q["event_type"] = {"$in": event_types}

        events = await db.event_bus_log.find(q, {"_id": 0}).sort("sequence", 1).to_list(limit)
        return events

    async def get_replay_summary(self, tenant_id: str) -> dict:
        """Get summary of replayable events."""
        one_day_ago = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        pipeline = [
            {"$match": {"tenant_id": tenant_id, "timestamp": {"$gte": one_day_ago}}},
            {
                "$group": {
                    "_id": "$event_type",
                    "count": {"$sum": 1},
                    "last_sequence": {"$max": "$sequence"},
                    "latest": {"$max": "$timestamp"},
                }
            },
            {"$sort": {"count": -1}},
        ]
        results = await db.event_bus_log.aggregate(pipeline).to_list(50)
        total = sum(r["count"] for r in results)
        return {
            "tenant_id": tenant_id,
            "replayable_events_24h": total,
            "by_type": [
                {
                    "event_type": r["_id"],
                    "count": r["count"],
                    "last_sequence": r["last_sequence"],
                    "latest": r["latest"],
                }
                for r in results
            ],
        }

    async def cleanup_old_events(self, days: int = 7) -> int:
        """Remove events older than specified days."""
        cutoff = (datetime.now(UTC) - timedelta(days=days)).isoformat()
        result = await db.event_bus_log.delete_many({"timestamp": {"$lt": cutoff}})
        logger.info(f"Cleaned up {result.deleted_count} old events (>{days} days)")
        return result.deleted_count


replay_service = EventReplayService()
