"""
Workers — Task Status Service
Aggregates task execution metrics, retry summaries, and queue health.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List

from core.database import db
from workers.queue_monitor import queue_monitor
from workers.failure_archive import failure_archive

logger = logging.getLogger(__name__)


class TaskStatusService:
    """Provides aggregated task/queue status for monitoring and alerting."""

    @staticmethod
    async def get_queue_health() -> Dict[str, Any]:
        """Comprehensive queue health summary."""
        return await queue_monitor.get_queue_status()

    @staticmethod
    async def get_stuck_tasks() -> List[Dict[str, Any]]:
        """Get all tasks stuck in processing state."""
        return await queue_monitor.get_stuck_tasks()

    @staticmethod
    async def get_failure_summary(
        tenant_id: str = None, limit: int = 50,
    ) -> Dict[str, Any]:
        """Get recent failures from dead-letter archive."""
        failures = await failure_archive.get_archived(
            tenant_id=tenant_id, limit=limit,
        )
        stats = await failure_archive.get_stats()
        return {
            "failures": failures,
            "stats": stats,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    async def replay_task(archive_id: str) -> Dict[str, Any]:
        """Replay a failed task from the dead-letter archive."""
        return await failure_archive.replay(archive_id)

    @staticmethod
    async def get_retry_summary() -> Dict[str, Any]:
        """Aggregate retry statistics across all task types."""
        now = datetime.now(timezone.utc)
        last_24h = (now - timedelta(hours=24)).isoformat()

        # Count by status in last 24h
        pipeline = [
            {"$match": {"started_at": {"$gte": last_24h}}},
            {"$group": {
                "_id": "$status",
                "count": {"$sum": 1},
            }},
        ]
        status_counts = {}
        async for doc in db.task_queue.aggregate(pipeline):
            status_counts[doc["_id"]] = doc["count"]

        # Count by task_type
        type_pipeline = [
            {"$match": {"started_at": {"$gte": last_24h}}},
            {"$group": {
                "_id": "$task_type",
                "total": {"$sum": 1},
                "failed": {"$sum": {"$cond": [{"$eq": ["$status", "failed"]}, 1, 0]}},
            }},
            {"$sort": {"failed": -1}},
            {"$limit": 20},
        ]
        by_type = []
        async for doc in db.task_queue.aggregate(type_pipeline):
            by_type.append({
                "task_type": doc["_id"],
                "total": doc["total"],
                "failed": doc["failed"],
                "success_rate": round((1 - doc["failed"] / max(doc["total"], 1)) * 100, 1),
            })

        return {
            "period": "24h",
            "status_counts": status_counts,
            "by_type": by_type,
            "retrieved_at": now.isoformat(),
        }


task_status_service = TaskStatusService()
