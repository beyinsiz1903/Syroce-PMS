"""
Error Tracker — production error classification, tracking, and persistence.
"""
import logging
import uuid
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

logger = logging.getLogger("observability.error_tracker")


class ErrorTracker:
    """Tracks and classifies application errors with MongoDB persistence."""

    def __init__(self):
        self._errors: List[dict] = []
        self._error_counts: Dict[str, int] = defaultdict(int)
        self._max_buffer = 500

    async def track_error(self, error_type: str, message: str,
                          module: str = "unknown", tenant_id: Optional[str] = None,
                          severity: str = "medium", stack_trace: Optional[str] = None,
                          correlation_id: Optional[str] = None):
        error_doc = {
            "id": str(uuid.uuid4()),
            "error_type": error_type,
            "message": message[:1000],
            "module": module,
            "tenant_id": tenant_id,
            "severity": severity,
            "stack_trace": stack_trace[:2000] if stack_trace else None,
            "correlation_id": correlation_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "resolved": False,
        }

        # Buffer in memory
        self._errors.append(error_doc)
        if len(self._errors) > self._max_buffer:
            self._errors = self._errors[-250:]
        self._error_counts[error_type] += 1

        # Persist to MongoDB
        try:
            from core.database import db
            await db.observability_errors.insert_one({**error_doc})
        except Exception as e:
            logger.warning(f"Error persistence failed: {e}")

    async def get_error_summary(self, hours: int = 24) -> dict:
        try:
            from core.database import db
            cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
            pipeline = [
                {"$match": {"timestamp": {"$gte": cutoff}}},
                {"$group": {
                    "_id": {"error_type": "$error_type", "severity": "$severity"},
                    "count": {"$sum": 1},
                    "last_seen": {"$max": "$timestamp"},
                }},
                {"$sort": {"count": -1}},
            ]
            cursor = db.observability_errors.aggregate(pipeline)
            results = await cursor.to_list(100)

            by_severity = defaultdict(int)
            top_errors = []
            total = 0
            for r in results:
                severity = r["_id"]["severity"]
                by_severity[severity] += r["count"]
                total += r["count"]
                top_errors.append({
                    "error_type": r["_id"]["error_type"],
                    "severity": severity,
                    "count": r["count"],
                    "last_seen": r["last_seen"],
                })

            return {
                "total_errors": total,
                "by_severity": dict(by_severity),
                "top_errors": top_errors[:20],
                "period_hours": hours,
            }
        except Exception:
            # Fallback to in-memory
            return {
                "total_errors": len(self._errors),
                "by_severity": {},
                "top_errors": [],
                "period_hours": hours,
            }

    async def get_recent_errors(self, limit: int = 50, severity: Optional[str] = None) -> List[dict]:
        try:
            from core.database import db
            q = {}
            if severity:
                q["severity"] = severity
            return await db.observability_errors.find(q, {"_id": 0}).sort("timestamp", -1).to_list(limit)
        except Exception:
            return self._errors[-limit:]

    async def resolve_error(self, error_id: str) -> dict:
        try:
            from core.database import db
            await db.observability_errors.update_one(
                {"id": error_id},
                {"$set": {"resolved": True, "resolved_at": datetime.now(timezone.utc).isoformat()}},
            )
        except Exception:
            pass
        return {"id": error_id, "resolved": True}


error_tracker = ErrorTracker()
