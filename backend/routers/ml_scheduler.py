"""
ML Scheduler Router - Schedule policies, execution triggers, status monitoring.
"""
from typing import Optional
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/data-intelligence/schedules", tags=["ml-scheduler"])

_service = None


def _get_service():
    global _service
    if _service is None:
        from server import db
        from modules.ml_scheduler.service import MLSchedulerService
        _service = MLSchedulerService(db)
    return _service


@router.get("/dashboard")
async def get_scheduler_dashboard(current_user: User = Depends(get_current_user)):
    svc = _get_service()
    return await svc.get_dashboard(current_user.tenant_id)


@router.get("/policies")
async def get_schedule_policies(current_user: User = Depends(get_current_user)):
    svc = _get_service()
    policies = await svc.get_schedule_policies(current_user.tenant_id)
    return {"policies": policies}


class UpdateScheduleReq(BaseModel):
    interval_hours: Optional[int] = None
    enabled: Optional[bool] = None


@router.put("/policies/{model_type}")
async def update_schedule(model_type: str, req: UpdateScheduleReq,
                           current_user: User = Depends(get_current_user)):
    svc = _get_service()
    return await svc.update_schedule(current_user.tenant_id, model_type, req.interval_hours, req.enabled)


class TriggerReq(BaseModel):
    model_type: str
    property_id: Optional[str] = None


@router.post("/trigger")
async def trigger_execution(req: TriggerReq, current_user: User = Depends(get_current_user)):
    svc = _get_service()
    return await svc.trigger_execution(
        current_user.tenant_id, req.model_type, req.property_id, triggered_by=current_user.id
    )


@router.get("/history")
async def get_execution_history(
    model_type: Optional[str] = None,
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    svc = _get_service()
    jobs = await svc.get_execution_history(current_user.tenant_id, model_type, limit)
    return {"jobs": jobs}


@router.get("/stale")
async def get_stale_models(current_user: User = Depends(get_current_user)):
    svc = _get_service()
    stale = await svc.get_stale_models(current_user.tenant_id)
    return {"stale_models": stale}
