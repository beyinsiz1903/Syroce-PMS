"""
Workers — Runtime Service
Orchestrates queue health monitoring, stuck task management,
failure archive, and retry statistics. No FastAPI dependencies.
"""
from typing import Dict, Any, Optional

from common.context import OperationContext
from common.result import ServiceResult


class WorkerRuntimeService:
    """Business logic for worker/queue runtime operations."""

    def __init__(self):
        from workers.task_status_service import task_status_service
        from workers.queue_monitor import queue_monitor
        self._task_status = task_status_service
        self._queue_monitor = queue_monitor

    async def get_queue_health(self, ctx: OperationContext) -> ServiceResult:
        data = await self._task_status.get_queue_health()
        return ServiceResult.success(data)

    async def get_stuck_tasks(self, ctx: OperationContext) -> ServiceResult:
        stuck = await self._task_status.get_stuck_tasks()
        return ServiceResult.success({"stuck_tasks": stuck, "count": len(stuck)})

    async def unstick_task(self, ctx: OperationContext, task_id: str) -> ServiceResult:
        success = await self._queue_monitor.unstick_task(task_id)
        if not success:
            return ServiceResult.fail("Task not found or not stuck", "NOT_FOUND")
        return ServiceResult.success({"status": "unstuck", "task_id": task_id})

    async def get_failure_summary(
        self, ctx: OperationContext, tenant_id: Optional[str] = None, limit: int = 50,
    ) -> ServiceResult:
        tid = tenant_id or ctx.tenant_id
        data = await self._task_status.get_failure_summary(tenant_id=tid, limit=limit)
        return ServiceResult.success(data)

    async def replay_task(self, ctx: OperationContext, archive_id: str) -> ServiceResult:
        result = await self._task_status.replay_task(archive_id)
        return ServiceResult.success(result)

    async def get_retry_summary(self, ctx: OperationContext) -> ServiceResult:
        data = await self._task_status.get_retry_summary()
        return ServiceResult.success(data)


worker_runtime_service = WorkerRuntimeService()
