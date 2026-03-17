"""
Runtime Enforcement Router
==========================

API endpoints for the runtime enforcement layers:
  1. Hard Fail Gate — mapping enforcement status & quarantine management
  2. Auto-Heal — conservative healing workflow
  3. Push Loop — delta push worker control & observability
  4. Readiness Scorer — scored "Why NOT READY?" breakdown
  5. Safe Actions — 1-click idempotent operator actions
  6. Rollout Framework — controlled live deployment
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


# ══════════════════════════════════════════════════════════════
# 6. READINESS SCORER — "Why NOT READY?"
# ══════════════════════════════════════════════════════════════

@router.get("/readiness-score")
async def readiness_score(
    current_user: User = Depends(get_current_user),
):
    """
    Scored readiness assessment with prioritized breakdown.
    Returns: score (0-100), issues sorted by severity, fix order suggestion.
    """
    from domains.channel_manager.readiness_scorer import (
        compute_readiness_score, log_ready_state_transition,
    )
    property_id = getattr(current_user, "property_id", "default")
    result = await compute_readiness_score(current_user.tenant_id, property_id)

    # Log state transition
    state = "READY" if result["is_ready"] else "NOT_READY"
    await log_ready_state_transition(
        current_user.tenant_id, state, result["score"],
        result["scores"], result["issues"],
    )

    return result


# ══════════════════════════════════════════════════════════════
# 7. SAFE ACTIONS — 1-Click Operator Actions
# ══════════════════════════════════════════════════════════════

class RetrySafeRequest(BaseModel):
    pass

class RevalidateMappingRequest(BaseModel):
    provider: Optional[str] = None

class SuppressNoiseRequest(BaseModel):
    event_type: Optional[str] = None
    duration_minutes: int = 30


@router.post("/actions/retry-safe")
async def action_retry_safe(
    current_user: User = Depends(get_current_user),
):
    """1-click: Retry all retryable failed change sets."""
    from domains.channel_manager.safe_actions_service import retry_safe
    return await retry_safe(current_user.tenant_id, operator_id=current_user.email)


@router.post("/actions/release-quarantine")
async def action_release_quarantine(
    request: SafeReleaseRequest,
    current_user: User = Depends(get_current_user),
):
    """1-click: Safe release from quarantine with full guard chain."""
    from domains.channel_manager.safe_actions_service import safe_release_quarantine
    return await safe_release_quarantine(
        current_user.tenant_id,
        request.room_type_code,
        request.rate_plan_code,
        request.provider,
        operator_id=current_user.email,
    )


@router.post("/actions/revalidate-mapping")
async def action_revalidate_mapping(
    request: RevalidateMappingRequest,
    current_user: User = Depends(get_current_user),
):
    """1-click: Full mapping revalidation with diff output."""
    from domains.channel_manager.safe_actions_service import revalidate_mapping
    return await revalidate_mapping(
        current_user.tenant_id,
        provider=request.provider,
        operator_id=current_user.email,
    )


@router.post("/actions/suppress-noise")
async def action_suppress_noise(
    request: SuppressNoiseRequest,
    current_user: User = Depends(get_current_user),
):
    """1-click: Suppress noisy notifications temporarily."""
    from domains.channel_manager.safe_actions_service import suppress_noise
    return await suppress_noise(
        current_user.tenant_id,
        event_type=request.event_type,
        duration_minutes=request.duration_minutes,
        operator_id=current_user.email,
    )


# ══════════════════════════════════════════════════════════════
# 8. NARROW ROLLOUT FRAMEWORK
# ══════════════════════════════════════════════════════════════

@router.get("/rollout/state")
async def rollout_state(
    current_user: User = Depends(get_current_user),
):
    """Get current rollout state."""
    from domains.channel_manager.rollout_framework import get_rollout_state
    return await get_rollout_state(current_user.tenant_id)


@router.post("/rollout/initialize")
async def rollout_initialize(
    current_user: User = Depends(get_current_user),
):
    """Initialize rollout at INTERNAL phase."""
    from domains.channel_manager.rollout_framework import initialize_rollout
    return await initialize_rollout(current_user.tenant_id, operator_id=current_user.email)


@router.get("/rollout/gate-check")
async def rollout_gate_check(
    current_user: User = Depends(get_current_user),
):
    """Evaluate whether current phase gate conditions are met."""
    from domains.channel_manager.rollout_framework import evaluate_phase_gate
    return await evaluate_phase_gate(current_user.tenant_id)


@router.post("/rollout/advance")
async def rollout_advance(
    current_user: User = Depends(get_current_user),
):
    """
    Attempt phase transition. ONLY succeeds if all gate checks pass.
    No manual override available.
    """
    from domains.channel_manager.rollout_framework import attempt_phase_transition
    return await attempt_phase_transition(current_user.tenant_id, operator_id=current_user.email)


@router.get("/rollout/dashboard")
async def rollout_dashboard(
    current_user: User = Depends(get_current_user),
):
    """Full rollout dashboard: phase, duration, gates, history."""
    from domains.channel_manager.rollout_framework import get_rollout_dashboard
    return await get_rollout_dashboard(current_user.tenant_id)
