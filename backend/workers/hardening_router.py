"""
Workers — Hardening Router
Production runtime APIs for queue health, stuck tasks, failure archive,
task replay, and retry summary.
Thin router: delegates all business logic to WorkerRuntimeService.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional

from core.security import get_current_user
from models.schemas import User
from common.context import OperationContext
from workers.worker_runtime_service import worker_runtime_service

router = APIRouter(prefix="/api/workers", tags=["Workers / Hardening"])


def _ctx(user: User) -> OperationContext:
    return OperationContext.from_user(user)


@router.get("/queues/health", summary="Queue health summary")
async def get_queue_health(current_user: User = Depends(get_current_user)):
    result = await worker_runtime_service.get_queue_health(_ctx(current_user))
    return result.data


@router.get("/tasks/stuck", summary="Get stuck tasks")
async def get_stuck_tasks(current_user: User = Depends(get_current_user)):
    result = await worker_runtime_service.get_stuck_tasks(_ctx(current_user))
    return result.data


@router.post("/tasks/{task_id}/unstick", summary="Force-fail a stuck task")
async def unstick_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
):
    result = await worker_runtime_service.unstick_task(_ctx(current_user), task_id)
    if not result.ok:
        raise HTTPException(status_code=404, detail=result.error)
    return result.data


@router.get("/tasks/failures", summary="Get failed tasks")
async def get_task_failures(
    tenant_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    result = await worker_runtime_service.get_failure_summary(
        _ctx(current_user), tenant_id=tenant_id, limit=limit
    )
    return result.data


@router.post("/tasks/replay", summary="Replay a failed task")
async def replay_task(
    archive_id: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    result = await worker_runtime_service.replay_task(_ctx(current_user), archive_id)
    return result.data


@router.get("/retries/summary", summary="Retry statistics")
async def get_retry_summary(current_user: User = Depends(get_current_user)):
    result = await worker_runtime_service.get_retry_summary(_ctx(current_user))
    return result.data
