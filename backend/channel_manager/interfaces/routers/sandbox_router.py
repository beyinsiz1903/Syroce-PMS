"""
Sandbox Simulation Router — API endpoints for running and viewing simulation results.
"""
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, Query

from core.security import get_current_user
from models.schemas import User
from ...application.sandbox_simulation.engine import SandboxSimulationEngine

logger = logging.getLogger("channel_manager.routers.sandbox")

router = APIRouter(tags=["CM Sandbox Simulation"])


@router.post("/sandbox/simulate")
async def run_simulation(
    providers: Optional[List[str]] = Query(default=None, description="Providers to simulate: hotelrunner, exely"),
    current_user: User = Depends(get_current_user),
):
    """Run full sandbox simulation for specified providers (default: all)."""
    engine = SandboxSimulationEngine()
    property_id = getattr(current_user, "property_id", "PROP-001")
    result = await engine.run_full_simulation(
        tenant_id=current_user.tenant_id,
        property_id=property_id,
        providers=providers,
        actor_id=current_user.id,
    )
    return result


@router.get("/sandbox/results")
async def get_results(
    limit: int = Query(default=10, ge=1, le=50),
    current_user: User = Depends(get_current_user),
):
    """Get recent simulation results."""
    engine = SandboxSimulationEngine()
    return await engine.get_simulation_results(current_user.tenant_id, limit)


@router.get("/sandbox/results/{run_id}")
async def get_result(
    run_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get a specific simulation result."""
    engine = SandboxSimulationEngine()
    result = await engine.get_simulation_result(current_user.tenant_id, run_id)
    if not result:
        return {"error": "Simulation run not found"}
    return result


@router.get("/sandbox/timeline/{run_id}")
async def get_timeline(
    run_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get the event timeline for a simulation run."""
    engine = SandboxSimulationEngine()
    return await engine.get_simulation_timeline(current_user.tenant_id, run_id)


@router.delete("/sandbox/cleanup/{run_id}")
async def cleanup_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
):
    """Clean up sandbox data for a simulation run."""
    engine = SandboxSimulationEngine()
    await engine.cleanup_sandbox_data(current_user.tenant_id, run_id)
    return {"status": "cleaned", "run_id": run_id}
