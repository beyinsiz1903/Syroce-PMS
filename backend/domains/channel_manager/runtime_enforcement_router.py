"""
Runtime Enforcement Router
==========================

API endpoints for the three runtime enforcement layers:
  1. Hard Fail Gate — mapping enforcement status & quarantine management
  2. Auto-Heal — conservative healing workflow
  3. Push Loop — delta push worker control & observability
"""
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from core.security import get_current_user
from models.schemas import User

from domains.channel_manager.ari.hard_fail_gate import (
    get_hard_fail_stats, release_quarantine,
)
from domains.channel_manager.auto_heal_service import (
    run_auto_heal_cycle, get_auto_heal_stats, get_auto_heal_history,
)
from domains.channel_manager.ari.push_loop_worker import get_push_worker

logger = logging.getLogger("lockdown.runtime")
router = APIRouter(prefix="/api/lockdown/runtime", tags=["Runtime Enforcement"])


# ── Request Models ────────────────────────────────────────────

class ReleaseQuarantineRequest(BaseModel):
    room_type_code: str
    rate_plan_code: Optional[str] = None
    provider: Optional[str] = None


class AutoHealRequest(BaseModel):
    include_risky: bool = False
    max_heals: int = 20


# ══════════════════════════════════════════════════════════════
# 1. HARD FAIL GATE
# ══════════════════════════════════════════════════════════════

@router.get("/hard-fail/stats")
async def hard_fail_stats(
    current_user: User = Depends(get_current_user),
):
    """Hard fail gate statistics."""
    return await get_hard_fail_stats(current_user.tenant_id)


@router.post("/hard-fail/release")
async def release_hard_fail(
    request: ReleaseQuarantineRequest,
    current_user: User = Depends(get_current_user),
):
    """Release quarantined change sets after mapping fix."""
    released = await release_quarantine(
        current_user.tenant_id,
        request.room_type_code,
        request.rate_plan_code,
        request.provider,
    )
    return {
        "released_count": released,
        "room_type_code": request.room_type_code,
        "rate_plan_code": request.rate_plan_code,
    }


# ══════════════════════════════════════════════════════════════
# 2. AUTO-HEAL
# ══════════════════════════════════════════════════════════════

@router.get("/auto-heal/stats")
async def auto_heal_stats(
    current_user: User = Depends(get_current_user),
):
    """Auto-heal workflow statistics."""
    return await get_auto_heal_stats(current_user.tenant_id)


@router.post("/auto-heal/run")
async def run_auto_heal(
    request: AutoHealRequest,
    current_user: User = Depends(get_current_user),
):
    """Trigger an auto-heal cycle."""
    result = await run_auto_heal_cycle(
        current_user.tenant_id,
        include_risky=request.include_risky,
        max_heals=request.max_heals,
    )
    return result.to_dict()


@router.get("/auto-heal/history")
async def auto_heal_history(
    limit: int = Query(default=50, ge=1, le=200),
    skip: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
):
    """Recent auto-heal operations."""
    history = await get_auto_heal_history(
        current_user.tenant_id, limit=limit, skip=skip,
    )
    return {"history": history, "limit": limit, "skip": skip}


# ══════════════════════════════════════════════════════════════
# 3. PUSH LOOP
# ══════════════════════════════════════════════════════════════

@router.get("/push-loop/status")
async def push_loop_status(
    current_user: User = Depends(get_current_user),
):
    """Push loop worker status and metrics."""
    worker = get_push_worker()
    return worker.get_status()


@router.post("/push-loop/start")
async def push_loop_start(
    current_user: User = Depends(get_current_user),
):
    """Start the push loop worker."""
    worker = get_push_worker()
    await worker.start()
    return {"status": worker.status, "message": "Push loop started"}


@router.post("/push-loop/stop")
async def push_loop_stop(
    current_user: User = Depends(get_current_user),
):
    """Stop the push loop worker."""
    worker = get_push_worker()
    await worker.stop()
    return {"status": worker.status, "message": "Push loop stopped"}


@router.post("/push-loop/pause")
async def push_loop_pause(
    current_user: User = Depends(get_current_user),
):
    """Pause the push loop worker."""
    worker = get_push_worker()
    worker.pause()
    return {"status": worker.status, "message": "Push loop paused"}


@router.post("/push-loop/resume")
async def push_loop_resume(
    current_user: User = Depends(get_current_user),
):
    """Resume the push loop worker."""
    worker = get_push_worker()
    worker.resume()
    return {"status": worker.status, "message": "Push loop resumed"}


@router.get("/push-loop/metrics")
async def push_loop_metrics(
    current_user: User = Depends(get_current_user),
):
    """Detailed push loop metrics for observability."""
    worker = get_push_worker()
    return worker.metrics.to_dict()
