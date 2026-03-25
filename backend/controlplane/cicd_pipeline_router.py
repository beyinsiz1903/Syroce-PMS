"""
CI/CD Pipeline Router — API endpoints for 3-tier deploy validation.

Endpoints:
  POST /api/ops/cicd/run                — Trigger a pipeline run (pr_gate, staging_gate, nightly)
  GET  /api/ops/cicd/runs               — List recent pipeline runs
  GET  /api/ops/cicd/runs/{run_id}      — Get specific run details
  GET  /api/ops/cicd/deploy-gate/{run_id} — Get deploy gate verdict
  GET  /api/ops/cicd/baseline           — Get current passing baselines per tier
  GET  /api/ops/cicd/health-badges      — Separate badges: sandbox / staging / prod
  GET  /api/ops/cicd/trends             — Trend analysis across runs
  GET  /api/ops/cicd/tiers              — Available tier configurations
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.security import get_current_user
from models.schemas import User
from security.ops_guard import require_ops_access

from .cicd_pipeline_runner import TIER_CONFIGS, CICDPipelineRunner

logger = logging.getLogger("controlplane.cicd_pipeline_router")

router = APIRouter(
    prefix="/api/ops/cicd",
    tags=["CI/CD Pipeline"],
    dependencies=[Depends(require_ops_access)],
)


class PipelineRunRequest(BaseModel):
    tier: str = Field(..., description="Pipeline tier: pr_gate, staging_gate, nightly")
    build_id: str | None = Field(default=None, description="CI/CD build ID")
    commit_sha: str | None = Field(default=None, description="Git commit SHA")
    deploy_id: str | None = Field(default=None, description="Deploy event ID")
    triggered_by: str = Field(default="operator", description="Who triggered this run")


@router.get("/tiers")
async def get_tiers():
    """Get available pipeline tier configurations."""
    tiers = {}
    for tier_key, config in TIER_CONFIGS.items():
        tiers[tier_key] = {
            "display_name": config["display_name"],
            "description": config["description"],
            "scenarios": config["scenarios"],
            "providers": config["providers"],
            "blocks_deploy": config["blocks_deploy"],
            "duplicate_count": config["duplicate_count"],
            "storm_size": config["storm_size"],
        }
    return {"tiers": tiers}


@router.post("/run")
async def run_pipeline(
    body: PipelineRunRequest,
    current_user: User = Depends(get_current_user),
):
    """Trigger a CI/CD pipeline run for the specified tier."""
    if body.tier not in TIER_CONFIGS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid tier '{body.tier}'. Valid: {list(TIER_CONFIGS.keys())}",
        )

    tenant_id = current_user.tenant_id
    property_id = getattr(current_user, "property_id", "PROP-001")

    runner = CICDPipelineRunner()
    result = await runner.run_pipeline(
        tier=body.tier,
        tenant_id=tenant_id,
        property_id=property_id,
        build_id=body.build_id,
        commit_sha=body.commit_sha,
        deploy_id=body.deploy_id,
        triggered_by=body.triggered_by,
    )
    return result


@router.get("/runs")
async def list_runs(
    tier: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """List recent CI/CD pipeline runs."""
    runner = CICDPipelineRunner()
    runs = await runner.get_runs(tenant_id=current_user.tenant_id, tier=tier, limit=limit)
    return {"runs": runs, "total": len(runs)}


@router.get("/runs/{run_id}")
async def get_run(run_id: str):
    """Get a specific CI/CD pipeline run."""
    runner = CICDPipelineRunner()
    run = await runner.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return run


@router.get("/deploy-gate/{run_id}")
async def get_deploy_gate(run_id: str):
    """Get the deploy gate verdict for a specific run."""
    runner = CICDPipelineRunner()
    run = await runner.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Pipeline run not found")
    return {
        "run_id": run_id,
        "tier": run.get("tier"),
        "deploy_gate": run.get("deploy_gate"),
        "acceptance_criteria": run.get("acceptance_criteria"),
        "build_context": run.get("build_context"),
    }


@router.get("/baseline")
async def get_baseline(current_user: User = Depends(get_current_user)):
    """Get the last passing baseline for each tier."""
    runner = CICDPipelineRunner()
    return await runner.get_baseline(tenant_id=current_user.tenant_id)


@router.get("/health-badges")
async def get_health_badges(current_user: User = Depends(get_current_user)):
    """Get separate health badges: sandbox_validation / staging_deploy_validation / prod_health."""
    runner = CICDPipelineRunner()
    badges = await runner.get_health_badges(tenant_id=current_user.tenant_id)
    return {"badges": badges}


@router.get("/trends")
async def get_trends(
    tier: str | None = Query(None),
    limit: int = Query(30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """Get trend data across CI/CD pipeline runs."""
    runner = CICDPipelineRunner()
    return await runner.get_trends(tenant_id=current_user.tenant_id, tier=tier, limit=limit)
