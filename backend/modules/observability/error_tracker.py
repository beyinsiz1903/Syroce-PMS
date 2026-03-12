"""
Error Tracker - Centralized error tracking and aggregation.
"""
import logging
import traceback as tb
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from collections import defaultdict

from core.database import db

logger = logging.getLogger("observability.errors")


class ErrorSeverity:
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ErrorTracker:
    """Tracks and aggregates application errors."""

    def __init__(self):
        self._recent_errors: List[dict] = []
        self._error_counts: Dict[str, int] = defaultdict(int)

    async def track_error(self, error_type: str, message: str,
                          module: str = "", tenant_id: Optional[str] = None,
                          severity: str = ErrorSeverity.MEDIUM,
                          stack_trace: Optional[str] = None,
                          metadata: Optional[dict] = None) -> dict:
        """Track an application error."""
        error_entry = {
            "id": str(__import__("uuid").uuid4()),
            "error_type": error_type,
            "message": message,
            "module": module,
            "tenant_id": tenant_id,
            "severity": severity,
            "stack_trace": stack_trace,
            "metadata": metadata or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "resolved": False,
        }

        self._recent_errors.append(error_entry)
        if len(self._recent_errors) > 500:
            self._recent_errors = self._recent_errors[-250:]

        self._error_counts[error_type] += 1

        await db.observability_errors.insert_one({**error_entry})

        if severity in (ErrorSeverity.CRITICAL, ErrorSeverity.HIGH):
            logger.error(f"[{severity.upper()}] {module}: {error_type} - {message}")

        return {k: v for k, v in error_entry.items() if k != "_id"}

    async def get_recent_errors(self, tenant_id: Optional[str] = None,
                                severity: Optional[str] = None,
                                module: Optional[str] = None,
                                limit: int = 50) -> List[dict]:
        q: Dict[str, Any] = {}
        if tenant_id:
            q["tenant_id"] = tenant_id
        if severity:
            q["severity"] = severity
        if module:
            q["module"] = module
        return await db.observability_errors.find(
            q, {"_id": 0}
        ).sort("timestamp", -1).to_list(limit)

    async def get_error_summary(self, hours: int = 24) -> Dict[str, Any]:
        """Get error aggregation summary."""
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        pipeline = [
            {"$match": {"timestamp": {"$gte": cutoff}}},
            {"$group": {
                "_id": {"type": "$error_type", "severity": "$severity", "module": "$module"},
                "count": {"$sum": 1},
                "latest": {"$max": "$timestamp"},
            }},
            {"$sort": {"count": -1}},
        ]
        results = await db.observability_errors.aggregate(pipeline).to_list(50)

        by_severity: Dict[str, int] = defaultdict(int)
        by_module: Dict[str, int] = defaultdict(int)
        total = 0
        for r in results:
            total += r["count"]
            by_severity[r["_id"]["severity"]] += r["count"]
            by_module[r["_id"]["module"]] += r["count"]

        return {
            "period_hours": hours,
            "total_errors": total,
            "by_severity": dict(by_severity),
            "by_module": dict(by_module),
            "top_errors": [
                {
                    "error_type": r["_id"]["type"],
                    "severity": r["_id"]["severity"],
                    "module": r["_id"]["module"],
                    "count": r["count"],
                    "latest": r["latest"],
                }
                for r in results[:15]
            ],
        }

    async def resolve_error(self, error_id: str) -> dict:
        await db.observability_errors.update_one(
            {"id": error_id},
            {"$set": {"resolved": True, "resolved_at": datetime.now(timezone.utc).isoformat()}},
        )
        return {"id": error_id, "resolved": True}


error_tracker = ErrorTracker()
