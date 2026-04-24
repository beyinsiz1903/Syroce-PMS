"""
Deploy Router — Production Deploy Pipeline API
================================================
Hard-gate CI/CD, progressive deploy, auto-rollback, migration verification,
smoke tests, and canary analysis — all wired through a single router.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from common.context import OperationContext
from common.response import from_service_result
from core.security import get_current_user
from modules.pms_core.role_permission_service import require_op  # v98 DW

router = APIRouter(prefix="/api/deploy", tags=["Deploy Pipeline"])


# ── Schemas ──────────────────────────────────────────────────────────

class StartPipelineRequest(BaseModel):
    version_tag: str = "latest"

class ExecuteGateRequest(BaseModel):
    pipeline_id: str
    gate_id: str

class AdvanceStageRequest(BaseModel):
    target_stage_id: str

class RollbackRequest(BaseModel):
    reason: str

class ExecuteRollbackRequest(BaseModel):
    reason: str


# ═══════════════════════════════════════════════════════════════════════
# 1. PIPELINE — Hard Gate CI/CD
# ═══════════════════════════════════════════════════════════════════════

@router.get("/pipeline/gates")
async def get_gate_definitions(user=Depends(get_current_user)):
    """Get all pipeline gate definitions."""
    from ops.deploy_pipeline import deploy_pipeline
    result = await deploy_pipeline.get_gate_definitions()
    return from_service_result(result)


@router.post("/pipeline/start")
async def start_pipeline(req: StartPipelineRequest, user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """Start a new deploy pipeline run."""
    from ops.deploy_pipeline import deploy_pipeline
    ctx = OperationContext.from_user(user)
    result = await deploy_pipeline.start_pipeline(ctx.actor_email, req.version_tag)
    return from_service_result(result)


@router.post("/pipeline/gate")
async def execute_gate(req: ExecuteGateRequest, user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """Execute a single pipeline gate."""
    from ops.deploy_pipeline import deploy_pipeline
    result = await deploy_pipeline.execute_gate(req.pipeline_id, req.gate_id)
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)


@router.post("/pipeline/run-all")
async def run_full_pipeline(req: StartPipelineRequest, user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """Run the complete pipeline (all gates sequentially)."""
    from ops.deploy_pipeline import deploy_pipeline
    ctx = OperationContext.from_user(user)
    result = await deploy_pipeline.run_full_pipeline(ctx.actor_email, req.version_tag)
    return from_service_result(result)


@router.get("/pipeline/{pipeline_id}")
async def get_pipeline(pipeline_id: str, user=Depends(get_current_user)):
    """Get pipeline run details."""
    from ops.deploy_pipeline import deploy_pipeline
    result = await deploy_pipeline.get_pipeline(pipeline_id)
    if not result.ok:
        raise HTTPException(status_code=404, detail=from_service_result(result))
    return from_service_result(result)


@router.get("/pipelines")
async def list_pipelines(limit: int = Query(20, le=50), user=Depends(get_current_user)):
    """List recent pipeline runs."""
    from ops.deploy_pipeline import deploy_pipeline
    result = await deploy_pipeline.list_pipelines(limit)
    return from_service_result(result)


# ═══════════════════════════════════════════════════════════════════════
# 2. MIGRATION VERIFICATION
# ═══════════════════════════════════════════════════════════════════════

@router.get("/migration/verify")
async def verify_migrations(user=Depends(get_current_user)):
    """Run migration verification (schema drift, index check)."""
    from ops.migration_verification import migration_verifier
    result = await migration_verifier.verify_all()
    return from_service_result(result)


@router.get("/migration/stats")
async def collection_stats(user=Depends(get_current_user)):
    """Get collection statistics."""
    from ops.migration_verification import migration_verifier
    result = await migration_verifier.get_collection_stats()
    return from_service_result(result)


# ═══════════════════════════════════════════════════════════════════════
# 3. PROGRESSIVE DEPLOY (CANARY)
# ═══════════════════════════════════════════════════════════════════════

@router.get("/canary/plan")
async def get_canary_plan(user=Depends(get_current_user)):
    """Get canary deployment stage plan."""
    from ops.canary_deployment_service import canary_deployment_service
    result = await canary_deployment_service.get_deployment_plan()
    return from_service_result(result)


@router.get("/canary/status")
async def get_canary_status(user=Depends(get_current_user)):
    """Get current canary deployment status."""
    from ops.canary_deployment_service import canary_deployment_service
    ctx = OperationContext.from_user(user)
    result = await canary_deployment_service.get_current_stage(ctx)
    return from_service_result(result)


@router.post("/canary/advance")
async def advance_canary(req: AdvanceStageRequest, user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """Advance to the next canary stage."""
    from ops.canary_deployment_service import canary_deployment_service
    ctx = OperationContext.from_user(user)
    result = await canary_deployment_service.advance_stage(ctx, req.target_stage_id)
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)


@router.post("/canary/rollback")
async def rollback_canary(req: RollbackRequest, user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """Rollback current canary deployment."""
    from ops.canary_deployment_service import canary_deployment_service
    ctx = OperationContext.from_user(user)
    result = await canary_deployment_service.rollback(ctx, req.reason)
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)


# ═══════════════════════════════════════════════════════════════════════
# 4. AUTO-ROLLBACK
# ═══════════════════════════════════════════════════════════════════════

@router.get("/rollback/triggers")
async def get_rollback_triggers(user=Depends(get_current_user)):
    """Get rollback trigger definitions."""
    from ops.auto_rollback_engine import auto_rollback_engine
    result = await auto_rollback_engine.get_trigger_definitions()
    return from_service_result(result)


@router.get("/rollback/evaluate")
async def evaluate_rollback_triggers(user=Depends(get_current_user)):
    """Evaluate current system state against rollback triggers."""
    from ops.auto_rollback_engine import auto_rollback_engine
    result = await auto_rollback_engine.evaluate_triggers()
    return from_service_result(result)


@router.post("/rollback/execute")
async def execute_rollback(req: ExecuteRollbackRequest, user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """Execute a manual or automated rollback."""
    from ops.auto_rollback_engine import auto_rollback_engine
    ctx = OperationContext.from_user(user)
    result = await auto_rollback_engine.execute_rollback(req.reason, ctx.actor_email)
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)


@router.get("/rollback/history")
async def rollback_history(limit: int = Query(20, le=50), user=Depends(get_current_user)):
    """Get rollback execution history."""
    from ops.auto_rollback_engine import auto_rollback_engine
    result = await auto_rollback_engine.get_rollback_history(limit)
    return from_service_result(result)


# ═══════════════════════════════════════════════════════════════════════
# 5. SMOKE TESTS
# ═══════════════════════════════════════════════════════════════════════

@router.post("/smoke-tests/run")
async def run_smoke_tests(user=Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """Run the full smoke test suite."""
    from ops.smoke_test_runner import smoke_test_runner
    result = await smoke_test_runner.run_all()
    return from_service_result(result)


# ═══════════════════════════════════════════════════════════════════════
# 6. CANARY ANALYSIS (combined view)
# ═══════════════════════════════════════════════════════════════════════

@router.get("/analysis/overview")
async def deploy_analysis_overview(user=Depends(get_current_user)):
    """Combined view: canary status + trigger evaluation + last pipeline."""
    from ops.auto_rollback_engine import auto_rollback_engine
    from ops.canary_deployment_service import canary_deployment_service
    from ops.deploy_pipeline import deploy_pipeline

    ctx = OperationContext.from_user(user)

    # Run all in parallel
    import asyncio
    canary_result, trigger_result, pipeline_result = await asyncio.gather(
        canary_deployment_service.get_current_stage(ctx),
        auto_rollback_engine.evaluate_triggers(),
        deploy_pipeline.list_pipelines(1),
    )

    return {
        "canary": canary_result.data if canary_result.ok else None,
        "triggers": trigger_result.data if trigger_result.ok else None,
        "last_pipeline": (pipeline_result.data["pipelines"][0] if pipeline_result.ok and pipeline_result.data.get("pipelines") else None),
    }
