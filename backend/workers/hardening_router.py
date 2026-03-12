"""
Workers — Hardening Router
Production runtime APIs for queue health, stuck tasks, failure archive,
task replay, and retry summary.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional

from core.security import get_current_user
from core.helpers import require_admin
from models.schemas import User
from workers.task_status_service import task_status_service
from workers.queue_monitor import queue_monitor

router = APIRouter(prefix="/api/workers", tags=["Workers / Hardening"])


@router.get("/queues/health", summary="Queue health summary")
async def get_queue_health(current_user: User = Depends(get_current_user)):
    """Get current queue backlog, saturation, and health metrics."""
    return await task_status_service.get_queue_health()


@router.get("/tasks/stuck", summary="Get stuck tasks")
async def get_stuck_tasks(current_user: User = Depends(get_current_user)):
    """Get tasks stuck in processing state beyond timeout threshold."""
    stuck = await task_status_service.get_stuck_tasks()
    return {"stuck_tasks": stuck, "count": len(stuck)}


@router.post("/tasks/{task_id}/unstick", summary="Force-fail a stuck task")
async def unstick_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    """Force-fail a stuck task so it can be retried or archived."""
    success = await queue_monitor.unstick_task(task_id)
    if not success:
        raise HTTPException(status_code=404, detail="Task not found or not stuck")
    return {"status": "unstuck", "task_id": task_id}


@router.get("/tasks/failures", summary="Get failed tasks")
async def get_task_failures(
    tenant_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    """Get failed tasks from dead-letter archive."""
    tid = tenant_id or current_user.tenant_id
    return await task_status_service.get_failure_summary(tenant_id=tid, limit=limit)


@router.post("/tasks/replay", summary="Replay a failed task")
async def replay_task(
    archive_id: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    """Replay a task from the dead-letter archive."""
    result = await task_status_service.replay_task(archive_id)
    return result


@router.get("/retries/summary", summary="Retry statistics")
async def get_retry_summary(current_user: User = Depends(get_current_user)):
    """Aggregated retry statistics for the last 24 hours."""
    return await task_status_service.get_retry_summary()
