"""
Workers — Runtime Service
Production-grade: aggregates real queue health, stuck task management,
failure archive stats, retry pressure, worker heartbeat, and dead-letter trends.
"""
import logging
from datetime import UTC, datetime, timedelta

from common.context import OperationContext
from common.result import ServiceResult
from core.database import db

logger = logging.getLogger(__name__)


class WorkerRuntimeService:
    """Production worker/queue runtime operations with real DB queries."""

    def __init__(self):
        from workers.failure_archive import failure_archive
        from workers.queue_monitor import queue_monitor
        from workers.task_status_service import task_status_service
        self._task_status = task_status_service
        self._queue_monitor = queue_monitor
        self._failure_archive = failure_archive

    async def get_queue_health(self, ctx: OperationContext) -> ServiceResult:
        """Comprehensive queue health with severity, saturation, and per-queue breakdown.
        Sprint 33: 21 sequential count_documents → parallel asyncio.gather (~7×).
        """
        import asyncio as _asyncio
        try:
            now = datetime.now(UTC)
            last_24h = (now - timedelta(hours=24)).isoformat()
            today_start = now.replace(hour=0, minute=0, second=0).isoformat()
            last_5m = (now - timedelta(minutes=5)).isoformat()

            queue_types = ["sync", "notification", "report", "audit", "import"]

            # Build all coroutines, then gather in one shot
            base_health_q = self._task_status.get_queue_health()
            per_queue_qs = []
            for qt in queue_types:
                per_queue_qs.append(db.task_queue.count_documents(
                    {"task_type": qt, "status": "pending"}))
                per_queue_qs.append(db.task_queue.count_documents(
                    {"task_type": qt, "status": "processing"}))
                per_queue_qs.append(db.task_queue.count_documents({
                    "task_type": qt, "status": "failed",
                    "started_at": {"$gte": last_24h},
                }))
            dl_total_q = db.dead_letter_tasks.count_documents({})
            dl_today_q = db.dead_letter_tasks.count_documents({
                "archived_at": {"$gte": today_start}
            })
            replay_q = db.dead_letter_tasks.count_documents({"status": "archived"})
            recent_q = db.task_queue.count_documents({
                "status": "completed", "started_at": {"$gte": last_5m},
            })
            retry_q = db.task_queue.count_documents({
                "retry_count": {"$gt": 0}, "started_at": {"$gte": last_24h},
            })

            results = await _asyncio.gather(
                base_health_q, *per_queue_qs,
                dl_total_q, dl_today_q, replay_q, recent_q, retry_q,
                return_exceptions=True,
            )
            def _safe(v, default=0):
                return default if isinstance(v, Exception) else v
            base_health = _safe(results[0], {})
            per_q_counts = [_safe(v, 0) for v in results[1:1 + 3 * len(queue_types)]]
            dl_total, dl_today, replay_candidates, recent_completions, retry_count_24h = \
                [_safe(v, 0) for v in results[1 + 3 * len(queue_types):]]

            per_queue = []
            for i, qt in enumerate(queue_types):
                pending = per_q_counts[i * 3]
                processing = per_q_counts[i * 3 + 1]
                failed_24h = per_q_counts[i * 3 + 2]
                q_health = "healthy"
                if pending > 100 or failed_24h > 10:
                    q_health = "critical"
                elif pending > 30 or failed_24h > 3:
                    q_health = "warning"
                per_queue.append({
                    "queue": qt, "health": q_health,
                    "pending": pending, "processing": processing,
                    "failed_24h": failed_24h,
                })
            workers_responding = recent_completions > 0

            # Severity calculation
            stuck = base_health.get("stuck", 0)
            pending = base_health.get("pending", 0)
            saturation = base_health.get("saturation_pct", 0)

            severity = "info"
            health = base_health.get("health", "healthy")
            recommendations = []

            if stuck > 5 or saturation > 90:
                severity = "critical"
                health = "critical"
                recommendations.append("Immediate: Unstick blocked tasks and scale workers")
            elif stuck > 0 or saturation > 70:
                severity = "warning"
                if health == "healthy":
                    health = "degraded"
                recommendations.append("Monitor stuck tasks; consider increasing worker count")
            if dl_today > 5:
                severity = max(severity, "warning", key=lambda s: ["info", "warning", "critical"].index(s))
                recommendations.append("Review dead-letter queue; recurring failures detected")
            if not workers_responding:
                severity = "critical"
                health = "critical"
                recommendations.append("No worker activity in last 5 minutes — check worker process")

            return ServiceResult.success({
                **base_health,
                "severity": severity,
                "health": health,
                "per_queue": per_queue,
                "dead_letter": {
                    "total": dl_total,
                    "today": dl_today,
                    "replay_candidates": replay_candidates,
                },
                "worker_heartbeat": {
                    "responding": workers_responding,
                    "recent_completions_5m": recent_completions,
                },
                "retry_pressure": {
                    "retried_tasks_24h": retry_count_24h,
                },
                "recommendations": recommendations,
            })
        except Exception as e:
            logger.error(f"WorkerRuntimeService.get_queue_health error: {e}")
            return ServiceResult.success({
                "health": "unknown",
                "severity": "warning",
                "error": str(e)[:100],
                "checked_at": datetime.now(UTC).isoformat(),
            })

    async def get_stuck_tasks(self, ctx: OperationContext) -> ServiceResult:
        """Get stuck tasks with grouping by task type."""
        stuck = await self._task_status.get_stuck_tasks()
        # Group by task_type
        groups: dict[str, int] = {}
        for t in stuck:
            tt = t.get("task_type", "unknown")
            groups[tt] = groups.get(tt, 0) + 1

        return ServiceResult.success({
            "stuck_tasks": stuck,
            "count": len(stuck),
            "by_type": groups,
        })

    async def unstick_task(self, ctx: OperationContext, task_id: str) -> ServiceResult:
        success = await self._queue_monitor.unstick_task(task_id)
        if not success:
            return ServiceResult.fail("Task not found or not stuck", "NOT_FOUND")
        try:
            from websocket_server import broadcast_system_health_event
            await broadcast_system_health_event(
                "stuck_task_resolved", {"task_id": task_id}, tenant_id=ctx.tenant_id, severity="info"
            )
        except Exception:
            pass
        return ServiceResult.success({"status": "unstuck", "task_id": task_id})

    async def get_failure_summary(
        self, ctx: OperationContext, tenant_id: str | None = None, limit: int = 50,
    ) -> ServiceResult:
        tid = tenant_id or ctx.tenant_id
        data = await self._task_status.get_failure_summary(tenant_id=tid, limit=limit)
        return ServiceResult.success(data)

    async def replay_task(self, ctx: OperationContext, archive_id: str) -> ServiceResult:
        result = await self._task_status.replay_task(archive_id)
        try:
            from websocket_server import broadcast_system_health_event
            await broadcast_system_health_event(
                "replay_completed", {"archive_id": archive_id, **result}, tenant_id=ctx.tenant_id, severity="info"
            )
        except Exception:
            pass
        return ServiceResult.success(result)

    async def get_retry_summary(self, ctx: OperationContext) -> ServiceResult:
        data = await self._task_status.get_retry_summary()
        return ServiceResult.success(data)


worker_runtime_service = WorkerRuntimeService()
