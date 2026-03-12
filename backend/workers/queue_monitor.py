"""
Workers — Queue Monitor
Monitors queue backlog, saturation, and stuck tasks. Emits alerts to observability.
"""
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional

from core.database import db

logger = logging.getLogger(__name__)


class QueueMonitor:
    """Monitors Celery/task queue health and backlog."""

    _thresholds = {
        "backlog_warning": 50,
        "backlog_critical": 200,
        "stuck_timeout_seconds": 3600,  # 1 hour
        "saturation_pct": 80,
    }

    @classmethod
    async def get_queue_status(cls) -> Dict[str, Any]:
        """Get current queue backlog and health metrics."""
        # Check pending tasks
        pending = await db.task_queue.count_documents({"status": "pending"})
        processing = await db.task_queue.count_documents({"status": "processing"})
        completed = await db.task_queue.count_documents({"status": "completed"})
        failed = await db.task_queue.count_documents({"status": "failed"})

        total_capacity = cls._thresholds["backlog_critical"]
        saturation_pct = round((pending + processing) / max(total_capacity, 1) * 100, 1)

        # Detect stuck tasks
        threshold = (datetime.now(timezone.utc) - timedelta(seconds=cls._thresholds["stuck_timeout_seconds"])).isoformat()
        stuck = await db.task_queue.count_documents({
            "status": "processing",
            "started_at": {"$lt": threshold},
        })

        health = "healthy"
        if pending > cls._thresholds["backlog_critical"] or stuck > 0:
            health = "critical"
        elif pending > cls._thresholds["backlog_warning"]:
            health = "warning"

        return {
            "health": health,
            "pending": pending,
            "processing": processing,
            "completed": completed,
            "failed": failed,
            "stuck": stuck,
            "saturation_pct": saturation_pct,
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }

    @classmethod
    async def get_stuck_tasks(cls) -> List[Dict[str, Any]]:
        threshold = (datetime.now(timezone.utc) - timedelta(seconds=cls._thresholds["stuck_timeout_seconds"])).isoformat()
        return await db.task_queue.find(
            {"status": "processing", "started_at": {"$lt": threshold}},
            {"_id": 0},
        ).to_list(100)

    @classmethod
    async def unstick_task(cls, task_id: str) -> bool:
        result = await db.task_queue.update_one(
            {"id": task_id, "status": "processing"},
            {"$set": {"status": "failed", "error": "Task stuck — force-failed by monitor", "updated_at": datetime.now(timezone.utc).isoformat()}},
        )
        return result.modified_count > 0


queue_monitor = QueueMonitor()
