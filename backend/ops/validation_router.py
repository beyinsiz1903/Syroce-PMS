"""
Phase 6 — Runtime Validation & Go-Live API Router
===================================================
Unified router for: runtime validation, incident drills,
observability validation, go-live scoring.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from common.context import OperationContext
from common.response import from_service_result
from core.security import get_current_user
from modules.pms_core.role_permission_service import require_op  # v98 DW
from ops.golive_scorer import golive_scorer
from ops.incident_drill import incident_drill_service
from ops.observability_validation import observability_validation_service
from ops.runtime_validation import runtime_validation

router = APIRouter(prefix="/api/validation", tags=["Phase 6 — Runtime Validation"])


# ── Schemas ──────────────────────────────────────────────────────────

class RunScenarioRequest(BaseModel):
    scenario_type: str  # load, stress, soak, chaos
    scenario_id: str

class ExecuteDrillRequest(BaseModel):
    drill_id: str


# ── Runtime Validation ───────────────────────────────────────────────

@router.get("/scenarios")
async def get_scenarios(user=Depends(get_current_user)):
    result = await runtime_validation.get_all_scenarios()
    return from_service_result(result)


@router.post("/run")
async def run_scenario(req: RunScenarioRequest, user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    ctx = OperationContext.from_user(user)
    result = await runtime_validation.run_scenario(ctx, req.scenario_type, req.scenario_id)
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)


@router.get("/report")
async def get_validation_report(
    hours: int = Query(24, ge=1, le=720),
    user=Depends(get_current_user),
):
    ctx = OperationContext.from_user(user)
    result = await runtime_validation.get_validation_report(ctx, hours)
    return from_service_result(result)


# ── Incident Drills ─────────────────────────────────────────────────

@router.get("/drills")
async def list_drills(user=Depends(get_current_user)):
    result = await incident_drill_service.list_drills()
    return from_service_result(result)


@router.post("/drills/execute")
async def execute_drill(req: ExecuteDrillRequest, user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    ctx = OperationContext.from_user(user)
    result = await incident_drill_service.execute_drill(ctx, req.drill_id)
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)


@router.get("/drills/history")
async def drill_history(
    limit: int = Query(20, le=100),
    user=Depends(get_current_user),
):
    ctx = OperationContext.from_user(user)
    result = await incident_drill_service.get_drill_history(ctx, limit)
    return from_service_result(result)


@router.post("/drills/cleanup")
async def cleanup_drill_data(user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    ctx = OperationContext.from_user(user)
    result = await incident_drill_service.cleanup_drill_data(ctx)
    return from_service_result(result)


# ── Observability Validation ─────────────────────────────────────────

@router.get("/observability")
async def validate_observability(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await observability_validation_service.full_observability_validation(ctx)
    return from_service_result(result)


@router.get("/observability/metrics")
async def validate_metrics(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await observability_validation_service.validate_metrics(ctx)
    return from_service_result(result)


@router.get("/observability/logs")
async def validate_logs(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await observability_validation_service.validate_logs(ctx)
    return from_service_result(result)


@router.get("/observability/alerts")
async def validate_alerts(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await observability_validation_service.validate_alerts(ctx)
    return from_service_result(result)


@router.get("/observability/audit-timeline")
async def validate_audit_timeline(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await observability_validation_service.validate_audit_timeline(ctx)
    return from_service_result(result)


# ── Go-Live Readiness Score ──────────────────────────────────────────

@router.get("/golive-score")
async def compute_golive_score(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await golive_scorer.compute_score(ctx)
    return from_service_result(result)


@router.get("/golive-score/history")
async def golive_score_history(
    limit: int = Query(10, le=50),
    user=Depends(get_current_user),
):
    ctx = OperationContext.from_user(user)
    result = await golive_scorer.get_score_history(ctx, limit)
    return from_service_result(result)
