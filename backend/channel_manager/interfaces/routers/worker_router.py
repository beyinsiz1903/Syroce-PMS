"""Background Worker Router — Job execution, history, and stats."""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query

from core.security import get_current_user
from models.schemas import User

from ...application.background_worker_service import BackgroundWorkerService

logger = logging.getLogger("channel_manager.routers.worker")

router = APIRouter(tags=["CM Background Worker"])


@router.post("/worker/jobs/run")
async def run_worker_job(
    job_type: str = Query(..., description="Job type: reservation_import, inventory_safety_sync, connector_health_check, metrics_aggregation"),
    connector_id: str = Query("", description="Optional connector ID"),
    current_user: User = Depends(get_current_user),
):
    """Manually trigger a background worker job."""
    svc = BackgroundWorkerService()
    result = await svc.run_job(job_type, current_user.tenant_id, connector_id)
    return result


@router.post("/worker/jobs/run-all")
async def run_all_worker_jobs(
    current_user: User = Depends(get_current_user),
):
    """Run all scheduled job types for the tenant."""
    svc = BackgroundWorkerService()
    return await svc.run_all_scheduled(current_user.tenant_id)


@router.get("/worker/jobs")
async def list_worker_jobs(
    job_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
):
    """List recent background worker jobs."""
    svc = BackgroundWorkerService()
    jobs = await svc.get_jobs(current_user.tenant_id, job_type, status, limit)
    return {"jobs": jobs, "count": len(jobs)}


@router.get("/worker/stats")
async def get_worker_stats(
    current_user: User = Depends(get_current_user),
):
    """Get worker job statistics and default intervals."""
    svc = BackgroundWorkerService()
    return await svc.get_job_stats(current_user.tenant_id)
