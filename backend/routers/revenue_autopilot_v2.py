"""
Revenue Autopilot Router - Policy, approval queue, apply, rollback, dashboard.
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from cache_manager import cached
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

router = APIRouter(prefix="/api/revenue-autopilot", tags=["revenue-autopilot"])

_service = None


def _get_service():
    global _service
    if _service is None:
        from modules.revenue_autopilot.service import RevenueAutopilotService
        from server import db
        _service = RevenueAutopilotService(db)
    return _service


@router.get("/dashboard")
@cached(ttl=180, key_prefix="revenue_autopilot_dashboard")
async def get_autopilot_dashboard(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v73 Bug DI: autopilot policy = stratejik
):
    svc = _get_service()
    return await svc.get_dashboard(current_user.tenant_id)


@router.get("/policy")
async def get_policy(current_user: User = Depends(get_current_user)):
    svc = _get_service()
    return await svc.get_policy(current_user.tenant_id)


@router.put("/policy")
async def update_policy(req: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
):
    svc = _get_service()
    return await svc.update_policy(current_user.tenant_id, req)


@router.get("/queue")
async def get_approval_queue(
    status: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    svc = _get_service()
    items = await svc.get_approval_queue(current_user.tenant_id, status, limit)
    return {"items": items, "total": len(items)}


class ProcessRecommendationReq(BaseModel):
    room_type: str = "Standard"
    target_date: str = ""
    current_price: float = 100.0
    recommended_price: float = 110.0
    confidence: float = 0.8
    source_job_id: str | None = None


@router.post("/process")
async def process_recommendation(req: ProcessRecommendationReq,
                                  current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
):
    svc = _get_service()
    return await svc.process_recommendation(current_user.tenant_id, req.model_dump())


@router.post("/queue/{item_id}/approve")
async def approve_item(item_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),  # v95 DW
):
    svc = _get_service()
    return await svc.approve_item(current_user.tenant_id, item_id, current_user.id)


class RejectReq(BaseModel):
    reason: str = ""


@router.post("/queue/{item_id}/reject")
async def reject_item(item_id: str, req: RejectReq,
                       current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_approvals")),  # v95 DW
):
    svc = _get_service()
    return await svc.reject_item(current_user.tenant_id, item_id, current_user.id, req.reason)


@router.post("/queue/{item_id}/rollback")
async def rollback_item(item_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
):
    svc = _get_service()
    return await svc.rollback_item(current_user.tenant_id, item_id, current_user.id)


@router.get("/summary")
async def get_daily_summary(current_user: User = Depends(get_current_user)):
    svc = _get_service()
    return await svc.get_daily_summary(current_user.tenant_id)
