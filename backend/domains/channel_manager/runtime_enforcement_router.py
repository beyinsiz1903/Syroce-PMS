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


# ══════════════════════════════════════════════════════════════
# 4. RUNTIME COCKPIT — Unified Dashboard
# ══════════════════════════════════════════════════════════════

@router.get("/cockpit")
async def runtime_cockpit(
    current_user: User = Depends(get_current_user),
):
    """
    Unified runtime cockpit — all golden metrics in one view.

    Sections:
      a) Health summary (is_production_ready, active_incidents, quarantine, verify%)
      b) Flow metrics (queued, coalesced, emitted, dropped, hard_fail_blocked)
      c) Reliability (verify ratio, ack latency, retry, dead letter)
      d) Drift & heal (drift count, auto_heal success/failure, manual required)
    """
    tenant_id = current_user.tenant_id

    # Gather all data
    hf_stats = await get_hard_fail_stats(tenant_id)
    ah_stats = await get_auto_heal_stats(tenant_id)
    worker = get_push_worker()
    push_metrics = worker.metrics.to_dict()
    push_status = worker.get_status()

    # Quarantine overview
    from domains.channel_manager.quarantine_service import get_quarantine_overview
    quarantine = await get_quarantine_overview(tenant_id)

    # Open incidents
    from core.database import db as _db
    from domains.channel_manager.data_model import COLL_RECONCILIATION_CASES
    open_incidents = await _db[COLL_RECONCILIATION_CASES].count_documents({
        "tenant_id": tenant_id,
        "status": {"$in": ["open", "investigating"]},
    })
    critical_incidents = await _db[COLL_RECONCILIATION_CASES].count_documents({
        "tenant_id": tenant_id,
        "status": "open",
        "severity": "critical",
    })

    # Dead letters (manual_review)
    from domains.channel_manager.ari.models import COLL_ARI_CHANGE_SETS
    dead_letters = await _db[COLL_ARI_CHANGE_SETS].count_documents({
        "tenant_id": tenant_id,
        "status": "manual_review",
    })

    # Drift count
    drift_count = await _db[COLL_RECONCILIATION_CASES].count_documents({
        "tenant_id": tenant_id,
        "status": {"$in": ["open", "investigating"]},
        "drift_type": {"$exists": True, "$ne": None},
    })

    # Production readiness
    is_production_ready = (
        hf_stats["hard_fail_change_sets"] == 0
        and hf_stats["open_hard_fail_incidents"] == 0
        and critical_incidents == 0
        and quarantine["total_quarantined"] == 0
    )

    return {
        # a) Health Summary
        "health": {
            "is_production_ready": is_production_ready,
            "active_incidents": open_incidents,
            "critical_incidents": critical_incidents,
            "quarantine_count": quarantine["total_quarantined"],
            "verify_success_pct": round(push_metrics["verify_success_ratio"] * 100, 1),
            "push_loop_status": push_status["status"],
        },
        # b) Flow Metrics
        "flow": {
            "queued": push_metrics["queued_changes"],
            "coalesced": push_metrics["coalesced_changes"],
            "emitted": push_metrics["emitted_payloads"],
            "dropped": push_metrics["dropped_as_duplicate"],
            "hard_fail_blocked": push_metrics["hard_fail_blocked"],
            "cycle_count": push_metrics["cycle_count"],
            "last_cycle_at": push_metrics["last_cycle_at"],
        },
        # c) Reliability
        "reliability": {
            "verify_success_ratio": push_metrics["verify_success_ratio"],
            "verify_success_count": push_metrics["verify_success_count"],
            "verify_fail_count": push_metrics["verify_fail_count"],
            "provider_ack_latency_avg_ms": push_metrics["provider_ack_latency_avg_ms"],
            "dead_letters": dead_letters,
            "last_cycle_duration_ms": push_metrics["last_cycle_duration_ms"],
        },
        # d) Drift & Heal
        "drift_heal": {
            "drift_count": drift_count,
            "auto_heal_total_healed": ah_stats["total_healed"],
            "auto_heal_total_failed": ah_stats["total_failed"],
            "auto_heal_eligible": ah_stats["eligible_cases"],
            "auto_heal_last_24h": ah_stats["healed_last_24h"],
            "manual_required": open_incidents - ah_stats["eligible_cases"] if open_incidents > ah_stats["eligible_cases"] else 0,
        },
        # e) Hard Fail Gate
        "hard_fail": hf_stats,
        # f) Quarantine
        "quarantine": quarantine,
    }


# ══════════════════════════════════════════════════════════════
# 5. QUARANTINE VISIBILITY
# ══════════════════════════════════════════════════════════════

@router.get("/quarantine/overview")
async def quarantine_overview(
    current_user: User = Depends(get_current_user),
):
    """Quarantine items: classification, age buckets, provider breakdown."""
    from domains.channel_manager.quarantine_service import get_quarantine_overview
    return await get_quarantine_overview(current_user.tenant_id)


class SafeReleaseRequest(BaseModel):
    room_type_code: str
    rate_plan_code: Optional[str] = None
    provider: Optional[str] = None


@router.post("/quarantine/check-release")
async def quarantine_check_release(
    request: SafeReleaseRequest,
    current_user: User = Depends(get_current_user),
):
    """Safe release guard: validates mapping is fixed before allowing release."""
    from domains.channel_manager.quarantine_service import check_safe_release
    return await check_safe_release(
        current_user.tenant_id,
        request.room_type_code,
        request.rate_plan_code,
        request.provider,
    )


@router.post("/quarantine/safe-release")
async def quarantine_safe_release(
    request: SafeReleaseRequest,
    current_user: User = Depends(get_current_user),
):
    """
    Safe release: check mapping validity first, then release.
    Two-step: validate → release.
    """
    from domains.channel_manager.quarantine_service import check_safe_release

    guard = await check_safe_release(
        current_user.tenant_id,
        request.room_type_code,
        request.rate_plan_code,
        request.provider,
    )

    if not guard["safe_to_release"]:
        return {
            "released": False,
            "reason": "Mapping validation failed",
            "guard": guard,
        }

    released = await release_quarantine(
        current_user.tenant_id,
        request.room_type_code,
        request.rate_plan_code,
        request.provider,
    )

    return {
        "released": True,
        "released_count": released,
        "guard": guard,
    }
