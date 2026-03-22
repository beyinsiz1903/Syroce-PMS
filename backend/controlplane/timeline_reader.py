"""
Timeline Reader — Query and Analyze Event Timelines
=====================================================
Provides read access for debugging, gap detection, and search.
The primary debug entry point: "trace any reservation in seconds."
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger("controlplane.timeline_reader")

COLL_TIMELINE = "event_timeline"

# Expected stage sequences for gap detection
EXPECTED_SEQUENCES = {
    "reservation": [
        "webhook_received", "deduplicated", "normalized", "validated",
        "import_decided", "stored", "queued", "dispatched", "confirmed",
    ],
    "ari_update": ["queued", "dispatched", "pushed", "confirmed"],
    "night_audit": ["started", "validating", "posting", "reconciling", "rolling", "completed"],
}


class TimelineReader:
    """Read and analyze event timelines."""

    def __init__(self):
        self._db = None

    def _get_db(self):
        if self._db is None:
            from core.database import db
            self._db = db
        return self._db

    async def get_by_entity(
        self,
        entity_type: str,
        entity_id: str,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Full timeline for an entity (e.g., a PMS booking ID)."""
        db = self._get_db()
        query: Dict[str, Any] = {
            "entity_type": entity_type,
            "entity_id": entity_id,
        }
        if tenant_id:
            query["tenant_id"] = tenant_id

        events = await db[COLL_TIMELINE].find(
            query, {"_id": 0}
        ).sort("timestamp", 1).to_list(500)

        total_duration = self._compute_total_duration(events)
        current_stage = events[-1]["stage"] if events else None
        gaps = self._detect_gaps(events, entity_type)

        # Find external_id from events
        external_id = ""
        for e in events:
            if e.get("external_id"):
                external_id = e["external_id"]
                break

        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "external_id": external_id,
            "timeline": events,
            "total_events": len(events),
            "total_duration_ms": total_duration,
            "current_stage": current_stage,
            "gap_warnings": gaps,
        }

    async def get_by_correlation(
        self, correlation_id: str, tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """All events sharing a correlation ID."""
        db = self._get_db()
        query: Dict[str, Any] = {"correlation_id": correlation_id}
        if tenant_id:
            query["tenant_id"] = tenant_id

        events = await db[COLL_TIMELINE].find(
            query, {"_id": 0}
        ).sort("timestamp", 1).to_list(500)

        # Build entity map
        entity_map: Dict[str, str] = {}
        for e in events:
            if e.get("entity_id"):
                entity_map[e["entity_type"]] = e["entity_id"]
            if e.get("external_id"):
                entity_map["external_id"] = e["external_id"]

        return {
            "correlation_id": correlation_id,
            "events": events,
            "total_events": len(events),
            "entity_map": entity_map,
            "total_duration_ms": self._compute_total_duration(events),
        }

    async def get_by_external_id(
        self, external_id: str, tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Lookup by OTA reservation ID — the most common debug entry point."""
        db = self._get_db()
        query: Dict[str, Any] = {"external_id": external_id}
        if tenant_id:
            query["tenant_id"] = tenant_id

        events = await db[COLL_TIMELINE].find(
            query, {"_id": 0}
        ).sort("timestamp", 1).to_list(500)

        if not events:
            return {
                "external_id": external_id,
                "timeline": [],
                "total_events": 0,
                "message": "No timeline events found for this external ID",
            }

        entity_type = events[0].get("entity_type", "reservation")
        entity_id = ""
        for e in events:
            if e.get("entity_id"):
                entity_id = e["entity_id"]
                break

        return {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "external_id": external_id,
            "timeline": events,
            "total_events": len(events),
            "total_duration_ms": self._compute_total_duration(events),
            "current_stage": events[-1]["stage"] if events else None,
            "gap_warnings": self._detect_gaps(events, entity_type),
        }

    async def search(
        self,
        *,
        tenant_id: Optional[str] = None,
        provider: Optional[str] = None,
        entity_type: Optional[str] = None,
        stage: Optional[str] = None,
        status: Optional[str] = None,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> Dict[str, Any]:
        """Search timeline events with filters."""
        db = self._get_db()
        query: Dict[str, Any] = {}
        if tenant_id:
            query["tenant_id"] = tenant_id
        if provider:
            query["provider"] = provider
        if entity_type:
            query["entity_type"] = entity_type
        if stage:
            query["stage"] = stage
        if status:
            query["status"] = status
        if from_time or to_time:
            ts_query: Dict[str, str] = {}
            if from_time:
                ts_query["$gte"] = from_time
            if to_time:
                ts_query["$lte"] = to_time
            query["timestamp"] = ts_query

        total = await db[COLL_TIMELINE].count_documents(query)
        events = await db[COLL_TIMELINE].find(
            query, {"_id": 0}
        ).sort("timestamp", -1).skip(skip).limit(limit).to_list(limit)

        return {
            "events": events,
            "total": total,
            "limit": limit,
            "skip": skip,
        }

    async def get_stuck_events(
        self,
        *,
        tenant_id: Optional[str] = None,
        max_age_minutes: int = 30,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Find events stuck in intermediate stages."""
        db = self._get_db()
        cutoff = (
            datetime.now(timezone.utc) - timedelta(minutes=max_age_minutes)
        ).isoformat()

        # Find the latest event per correlation_id
        match: Dict[str, Any] = {"timestamp": {"$lte": cutoff}}
        if tenant_id:
            match["tenant_id"] = tenant_id

        # Terminal stages that indicate completion
        terminal_stages = {"confirmed", "failed", "cancelled", "completed"}

        pipeline = [
            {"$match": match},
            {"$sort": {"timestamp": -1}},
            {"$group": {
                "_id": "$correlation_id",
                "last_stage": {"$first": "$stage"},
                "last_status": {"$first": "$status"},
                "last_timestamp": {"$first": "$timestamp"},
                "entity_type": {"$first": "$entity_type"},
                "entity_id": {"$first": "$entity_id"},
                "external_id": {"$first": "$external_id"},
                "tenant_id": {"$first": "$tenant_id"},
                "provider": {"$first": "$provider"},
            }},
            {"$match": {
                "last_stage": {"$nin": list(terminal_stages)},
                "last_status": {"$ne": "failure"},
            }},
            {"$sort": {"last_timestamp": 1}},
            {"$limit": limit},
        ]

        stuck = []
        async for doc in db[COLL_TIMELINE].aggregate(pipeline):
            stuck.append({
                "correlation_id": doc["_id"],
                "entity_type": doc["entity_type"],
                "entity_id": doc.get("entity_id", ""),
                "external_id": doc.get("external_id", ""),
                "last_stage": doc["last_stage"],
                "stuck_since": doc["last_timestamp"],
                "tenant_id": doc["tenant_id"],
                "provider": doc.get("provider", ""),
            })

        return {
            "stuck_events": stuck,
            "total": len(stuck),
            "threshold_minutes": max_age_minutes,
        }

    def _compute_total_duration(self, events: List[Dict[str, Any]]) -> Optional[int]:
        """Compute total duration from first to last event in ms."""
        if len(events) < 2:
            return None
        try:
            first = datetime.fromisoformat(events[0]["timestamp"])
            last = datetime.fromisoformat(events[-1]["timestamp"])
            return int((last - first).total_seconds() * 1000)
        except Exception:
            return None

    def _detect_gaps(
        self, events: List[Dict[str, Any]], entity_type: str,
    ) -> List[str]:
        """Detect missing stages in a timeline."""
        expected = EXPECTED_SEQUENCES.get(entity_type)
        if not expected:
            return []

        actual_stages = {
            e["stage"] for e in events if e.get("status") == "success"
        }
        gaps = []
        for i, expected_stage in enumerate(expected):
            if expected_stage not in actual_stages:
                gaps.append(
                    f"Missing stage: {expected_stage} (expected at position {i})"
                )
        return gaps


# ── Singleton ──────────────────────────────────────────────────────
_reader: Optional[TimelineReader] = None


def get_timeline_reader() -> TimelineReader:
    global _reader
    if _reader is None:
        _reader = TimelineReader()
    return _reader
