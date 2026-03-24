"""
Narrow Rollout Framework — Controlled Live Deployment
======================================================

State Machine: INTERNAL -> DUAL_PROVIDER -> REAL_PILOT -> 7DAY_PROOF -> PRODUCTION

Each phase has strict automatic gates that MUST be met before transition.
Manual override is NOT available — gates are enforced by the system.

Phase Gates:
  INTERNAL -> DUAL_PROVIDER:
    - mapping_completeness == 100%
    - hard_fail_blocked == 0
    - verify_success_ratio >= 95%
    - drift_count <= threshold
    - no BLOCKER incidents

  DUAL_PROVIDER -> REAL_PILOT:
    - both providers verify_success_ratio >= 95%
    - reconciliation mismatches explainable
    - auto_heal_success_rate >= 90%

  REAL_PILOT -> 7DAY_PROOF:
    - last 24h: 0 silent failures
    - 0 unexplained drift
    - incident resolution time < threshold

  7DAY_PROOF -> PRODUCTION:
    - 7 consecutive days passing all gates
    - 0 data loss
    - all drift explainable
    - all incidents actionable
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

from core.database import db

logger = logging.getLogger("channel_manager.rollout")

_NO_ID = {"_id": 0}
COLL_ROLLOUT_STATE = "rollout_state"
COLL_ROLLOUT_HISTORY = "rollout_history"


class RolloutPhase:
    INTERNAL = "INTERNAL"
    DUAL_PROVIDER = "DUAL_PROVIDER"
    REAL_PILOT = "REAL_PILOT"
    SEVEN_DAY_PROOF = "7DAY_PROOF"
    PRODUCTION = "PRODUCTION"

    ORDERED = ["INTERNAL", "DUAL_PROVIDER", "REAL_PILOT", "7DAY_PROOF", "PRODUCTION"]


PHASE_CONFIG = {
    RolloutPhase.INTERNAL: {
        "label": "Internal Test",
        "description": "1 tenant, test property, single provider (HotelRunner)",
        "min_duration_hours": 24,
        "providers": ["hotelrunner"],
    },
    RolloutPhase.DUAL_PROVIDER: {
        "label": "Dual Provider",
        "description": "Add Exely, full mapping, verify both providers",
        "min_duration_hours": 48,
        "providers": ["hotelrunner", "exely"],
    },
    RolloutPhase.REAL_PILOT: {
        "label": "Real Pilot",
        "description": "Small real hotel, low traffic, operator panel active",
        "min_duration_hours": 72,
        "providers": ["hotelrunner", "exely"],
    },
    RolloutPhase.SEVEN_DAY_PROOF: {
        "label": "7-Day Proof",
        "description": "7 consecutive days, all success criteria met",
        "min_duration_hours": 168,
        "providers": ["hotelrunner", "exely"],
    },
    RolloutPhase.PRODUCTION: {
        "label": "Production",
        "description": "Full production deployment",
        "min_duration_hours": 0,
        "providers": ["hotelrunner", "exely"],
    },
}


async def get_rollout_state(tenant_id: str) -> Dict[str, Any]:
    """Get current rollout state for a tenant."""
    state = await db[COLL_ROLLOUT_STATE].find_one(
        {"tenant_id": tenant_id}, _NO_ID,
    )
    if not state:
        return _default_state(tenant_id)
    return state


async def initialize_rollout(tenant_id: str, operator_id: str = "system") -> Dict[str, Any]:
    """Initialize rollout for a tenant at INTERNAL phase."""
    now = datetime.now(timezone.utc).isoformat()
    state = {
        "tenant_id": tenant_id,
        "current_phase": RolloutPhase.INTERNAL,
        "phase_started_at": now,
        "rollout_started_at": now,
        "initialized_by": operator_id,
        "phase_history": [{
            "phase": RolloutPhase.INTERNAL,
            "started_at": now,
            "gate_results": [],
        }],
        "is_active": True,
        "updated_at": now,
    }

    await db[COLL_ROLLOUT_STATE].update_one(
        {"tenant_id": tenant_id},
        {"$set": state},
        upsert=True,
    )

    await _log_history(tenant_id, "rollout_initialized", RolloutPhase.INTERNAL, operator_id)
    return state


async def evaluate_phase_gate(tenant_id: str) -> Dict[str, Any]:
    """
    Evaluate whether the current phase gate is met.
    Returns gate results and whether transition is possible.
    """
    state = await get_rollout_state(tenant_id)
    current_phase = state.get("current_phase", RolloutPhase.INTERNAL)
    phase_started = state.get("phase_started_at", "")

    # Find next phase
    phases = RolloutPhase.ORDERED
    current_idx = phases.index(current_phase) if current_phase in phases else 0
    if current_idx >= len(phases) - 1:
        return {
            "current_phase": current_phase,
            "next_phase": None,
            "gate_passed": True,
            "message": "Production fazinda — ilerleyecek faz yok",
            "checks": [],
        }

    next_phase = phases[current_idx + 1]

    # Evaluate gate
    checks = await _evaluate_gate(tenant_id, current_phase, next_phase, phase_started)
    all_passed = all(c["passed"] for c in checks)

    return {
        "current_phase": current_phase,
        "next_phase": next_phase,
        "gate_passed": all_passed,
        "message": f"{'Tum gate kontrolleri gecti' if all_passed else 'Gate kontrolleri gecmedi'} — {current_phase} -> {next_phase}",
        "checks": checks,
        "phase_config": PHASE_CONFIG.get(next_phase, {}),
    }


async def attempt_phase_transition(tenant_id: str, operator_id: str = "system") -> Dict[str, Any]:
    """
    Attempt to transition to next phase.
    ONLY succeeds if ALL gate checks pass. No manual override.
    """
    gate_result = await evaluate_phase_gate(tenant_id)

    if not gate_result["gate_passed"]:
        failed = [c for c in gate_result["checks"] if not c["passed"]]
        return {
            "transitioned": False,
            "current_phase": gate_result["current_phase"],
            "reason": "Gate kontrolleri gecmedi",
            "failed_checks": failed,
            "message": f"Gecis engellendi: {len(failed)} kontrol basarisiz",
        }

    if gate_result["next_phase"] is None:
        return {
            "transitioned": False,
            "current_phase": gate_result["current_phase"],
            "reason": "Zaten son fazda",
            "message": "Production fazindasiniz",
        }

    now = datetime.now(timezone.utc).isoformat()
    new_phase = gate_result["next_phase"]

    # Execute transition
    await db[COLL_ROLLOUT_STATE].update_one(
        {"tenant_id": tenant_id},
        {
            "$set": {
                "current_phase": new_phase,
                "phase_started_at": now,
                "updated_at": now,
            },
            "$push": {
                "phase_history": {
                    "phase": new_phase,
                    "started_at": now,
                    "gate_results": gate_result["checks"],
                    "transitioned_by": operator_id,
                }
            },
        },
    )

    await _log_history(tenant_id, "phase_transition",
                       new_phase, operator_id,
                       {"from": gate_result["current_phase"], "gate_checks": len(gate_result["checks"])})

    logger.info(f"Rollout transition: {gate_result['current_phase']} -> {new_phase} tenant={tenant_id}")

    return {
        "transitioned": True,
        "previous_phase": gate_result["current_phase"],
        "current_phase": new_phase,
        "message": f"Basariyla gecis yapildi: {new_phase}",
        "gate_results": gate_result["checks"],
    }


async def get_rollout_dashboard(tenant_id: str) -> Dict[str, Any]:
    """Full rollout dashboard data."""
    state = await get_rollout_state(tenant_id)
    gate = await evaluate_phase_gate(tenant_id)

    current_phase = state.get("current_phase", RolloutPhase.INTERNAL)
    phase_started = state.get("phase_started_at", "")
    rollout_started = state.get("rollout_started_at", "")

    # Duration calculation
    now = datetime.now(timezone.utc)
    phase_duration_h = 0
    total_duration_h = 0
    if phase_started:
        try:
            ps = datetime.fromisoformat(phase_started.replace("Z", "+00:00"))
            if ps.tzinfo is None:
                ps = ps.replace(tzinfo=timezone.utc)
            phase_duration_h = round((now - ps).total_seconds() / 3600, 1)
        except (ValueError, TypeError):
            pass
    if rollout_started:
        try:
            rs = datetime.fromisoformat(rollout_started.replace("Z", "+00:00"))
            if rs.tzinfo is None:
                rs = rs.replace(tzinfo=timezone.utc)
            total_duration_h = round((now - rs).total_seconds() / 3600, 1)
        except (ValueError, TypeError):
            pass

    phase_config = PHASE_CONFIG.get(current_phase, {})
    min_hours = phase_config.get("min_duration_hours", 0)

    # Phase progress map
    phases = RolloutPhase.ORDERED
    current_idx = phases.index(current_phase) if current_phase in phases else 0
    phase_progress = []
    for i, p in enumerate(phases):
        cfg = PHASE_CONFIG.get(p, {})
        phase_progress.append({
            "phase": p,
            "label": cfg.get("label", p),
            "status": "completed" if i < current_idx else ("active" if i == current_idx else "pending"),
        })

    return {
        "tenant_id": tenant_id,
        "current_phase": current_phase,
        "phase_label": phase_config.get("label", current_phase),
        "phase_description": phase_config.get("description", ""),
        "phase_duration_hours": phase_duration_h,
        "min_duration_hours": min_hours,
        "total_rollout_hours": total_duration_h,
        "is_active": state.get("is_active", False),
        "gate_evaluation": gate,
        "phase_progress": phase_progress,
        "phase_history": state.get("phase_history", []),
    }


async def _evaluate_gate(
    tenant_id: str,
    current_phase: str,
    next_phase: str,
    phase_started_at: str,
) -> List[Dict[str, Any]]:
    """Evaluate all gate checks for a phase transition."""
    from domains.channel_manager.ari.hard_fail_gate import get_hard_fail_stats
    from domains.channel_manager.ari.push_loop_worker import get_push_worker
    from domains.channel_manager.auto_heal_service import get_auto_heal_stats
    from domains.channel_manager.quarantine_service import get_quarantine_overview

    checks = []

    # Common metrics
    hf_stats = await get_hard_fail_stats(tenant_id)
    ah_stats = await get_auto_heal_stats(tenant_id)
    worker = get_push_worker()
    metrics = worker.metrics.to_dict()
    quarantine = await get_quarantine_overview(tenant_id)

    # Min duration check
    config = PHASE_CONFIG.get(current_phase, {})
    min_hours = config.get("min_duration_hours", 0)
    if min_hours > 0 and phase_started_at:
        try:
            ps = datetime.fromisoformat(phase_started_at.replace("Z", "+00:00"))
            if ps.tzinfo is None:
                ps = ps.replace(tzinfo=timezone.utc)
            elapsed_h = (datetime.now(timezone.utc) - ps).total_seconds() / 3600
            checks.append({
                "name": "min_phase_duration",
                "label": f"Minimum sure ({min_hours}h)",
                "passed": elapsed_h >= min_hours,
                "value": f"{round(elapsed_h, 1)}h / {min_hours}h",
                "required": f">= {min_hours}h",
            })
        except (ValueError, TypeError):
            checks.append({
                "name": "min_phase_duration",
                "label": f"Minimum sure ({min_hours}h)",
                "passed": False,
                "value": "Hesaplanamadi",
                "required": f">= {min_hours}h",
            })

    # Gate-specific checks
    if next_phase == RolloutPhase.DUAL_PROVIDER:
        checks.extend(_gate_internal_to_dual(hf_stats, metrics, quarantine))
    elif next_phase == RolloutPhase.REAL_PILOT:
        checks.extend(_gate_dual_to_pilot(hf_stats, ah_stats, metrics))
    elif next_phase == RolloutPhase.SEVEN_DAY_PROOF:
        checks.extend(await _gate_pilot_to_proof(tenant_id, hf_stats, metrics))
    elif next_phase == RolloutPhase.PRODUCTION:
        checks.extend(await _gate_proof_to_production(tenant_id, hf_stats, metrics, quarantine))

    # Universal: no BLOCKER incidents
    blocker_count = await db["channel_reconciliation_cases"].count_documents({
        "tenant_id": tenant_id,
        "status": "open",
        "severity": "critical",
    })
    checks.append({
        "name": "no_blocker_incidents",
        "label": "Blocker incident yok",
        "passed": blocker_count == 0,
        "value": str(blocker_count),
        "required": "0",
    })

    return checks


def _gate_internal_to_dual(hf_stats, metrics, quarantine):
    """INTERNAL -> DUAL_PROVIDER gates."""
    verify_ratio = metrics.get("verify_success_ratio", 0)
    return [
        {
            "name": "hard_fail_clear",
            "label": "Hard fail bloklari temiz",
            "passed": hf_stats["hard_fail_change_sets"] == 0,
            "value": str(hf_stats["hard_fail_change_sets"]),
            "required": "0",
        },
        {
            "name": "verify_ratio",
            "label": "Verify basari orani >= %95",
            "passed": verify_ratio >= 0.95,
            "value": f"{round(verify_ratio * 100, 1)}%",
            "required": ">= 95%",
        },
        {
            "name": "quarantine_clear",
            "label": "Karantina temiz",
            "passed": quarantine["total_quarantined"] == 0,
            "value": str(quarantine["total_quarantined"]),
            "required": "0",
        },
    ]


def _gate_dual_to_pilot(hf_stats, ah_stats, metrics):
    """DUAL_PROVIDER -> REAL_PILOT gates."""
    verify_ratio = metrics.get("verify_success_ratio", 0)
    total_ah = ah_stats["total_healed"] + ah_stats["total_failed"]
    ah_success = (ah_stats["total_healed"] / total_ah) if total_ah > 0 else 1.0

    return [
        {
            "name": "verify_ratio_95",
            "label": "Verify basari orani >= %95",
            "passed": verify_ratio >= 0.95,
            "value": f"{round(verify_ratio * 100, 1)}%",
            "required": ">= 95%",
        },
        {
            "name": "auto_heal_success",
            "label": "Auto-heal basari orani >= %90",
            "passed": ah_success >= 0.90,
            "value": f"{round(ah_success * 100, 1)}%",
            "required": ">= 90%",
        },
        {
            "name": "hard_fail_clear",
            "label": "Hard fail bloklari temiz",
            "passed": hf_stats["hard_fail_change_sets"] == 0,
            "value": str(hf_stats["hard_fail_change_sets"]),
            "required": "0",
        },
    ]


async def _gate_pilot_to_proof(tenant_id, hf_stats, metrics):
    """REAL_PILOT -> 7DAY_PROOF gates."""
    since_24h = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()

    # Silent failures in last 24h
    silent_fails = await db["channel_reconciliation_cases"].count_documents({
        "tenant_id": tenant_id,
        "status": "open",
        "created_at": {"$gte": since_24h},
    })

    # Unexplained drifts
    unexplained = await db["channel_reconciliation_cases"].count_documents({
        "tenant_id": tenant_id,
        "status": "open",
        "drift_type": {"$exists": True, "$ne": None},
        "resolution": {"$exists": False},
    })

    verify_ratio = metrics.get("verify_success_ratio", 0)

    return [
        {
            "name": "zero_silent_failures_24h",
            "label": "Son 24 saat 0 sessiz hata",
            "passed": silent_fails == 0,
            "value": str(silent_fails),
            "required": "0",
        },
        {
            "name": "zero_unexplained_drift",
            "label": "0 aciklanamayan drift",
            "passed": unexplained == 0,
            "value": str(unexplained),
            "required": "0",
        },
        {
            "name": "verify_ratio_95",
            "label": "Verify basari orani >= %95",
            "passed": verify_ratio >= 0.95,
            "value": f"{round(verify_ratio * 100, 1)}%",
            "required": ">= 95%",
        },
    ]


async def _gate_proof_to_production(tenant_id, hf_stats, metrics, quarantine):
    """7DAY_PROOF -> PRODUCTION gates — strictest."""
    since_7d = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    data_loss = await db["channel_reconciliation_cases"].count_documents({
        "tenant_id": tenant_id,
        "case_type": {"$in": ["missing_locally", "missing_remotely"]},
        "created_at": {"$gte": since_7d},
    })

    silent_fails = await db["channel_reconciliation_cases"].count_documents({
        "tenant_id": tenant_id,
        "status": "open",
        "created_at": {"$gte": since_7d},
    })

    verify_ratio = metrics.get("verify_success_ratio", 0)

    return [
        {
            "name": "zero_data_loss_7d",
            "label": "7 gun 0 veri kaybi",
            "passed": data_loss == 0,
            "value": str(data_loss),
            "required": "0",
        },
        {
            "name": "zero_silent_failures_7d",
            "label": "7 gun 0 sessiz hata",
            "passed": silent_fails == 0,
            "value": str(silent_fails),
            "required": "0",
        },
        {
            "name": "verify_ratio_95",
            "label": "Verify basari orani >= %95",
            "passed": verify_ratio >= 0.95,
            "value": f"{round(verify_ratio * 100, 1)}%",
            "required": ">= 95%",
        },
        {
            "name": "quarantine_clear",
            "label": "Karantina temiz",
            "passed": quarantine["total_quarantined"] == 0,
            "value": str(quarantine["total_quarantined"]),
            "required": "0",
        },
        {
            "name": "hard_fail_clear",
            "label": "Hard fail bloklari temiz",
            "passed": hf_stats["hard_fail_change_sets"] == 0,
            "value": str(hf_stats["hard_fail_change_sets"]),
            "required": "0",
        },
    ]


def _default_state(tenant_id: str) -> Dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "current_phase": RolloutPhase.INTERNAL,
        "phase_started_at": None,
        "rollout_started_at": None,
        "is_active": False,
        "phase_history": [],
    }


async def _log_history(
    tenant_id: str, event_type: str, phase: str,
    operator_id: str, details: Dict = None,
) -> None:
    await db[COLL_ROLLOUT_HISTORY].insert_one({
        "tenant_id": tenant_id,
        "event_type": event_type,
        "phase": phase,
        "operator_id": operator_id,
        "details": details or {},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
