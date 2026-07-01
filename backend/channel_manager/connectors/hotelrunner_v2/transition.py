"""
HotelRunner v2 — Write Path Transition Plan
==============================================

4-phase transition from Shadow to Full Live:

  Phase 1: SHADOW    (read-only, compare, observe)
  Phase 2: DRY_RUN   (simulate writes, verify, no real commit)
  Phase 3: LIMITED    (single tenant / narrow scope, real writes)
  Phase 4: FULL_LIVE  (all tenants, full write path)

Each phase defines:
  - entry_criteria: conditions to enter the phase
  - exit_criteria: conditions to graduate to next phase
  - rollback_conditions: when to fall back to previous phase
"""

import logging
from datetime import UTC, datetime
from typing import Any

from core.database import db

logger = logging.getLogger("hrv2.transition")

COLL_TRANSITION_STATE = "connector_transition_state"
COLL_TRANSITION_LOG = "connector_transition_log"
_NO_ID = {"_id": 0}

# ── Phase Definitions ──────────────────────────────────────────────────

PHASES = {
    "shadow": {
        "order": 1,
        "label": "Shadow Mode",
        "description": "Salt okunur mod. Veriler cekilir, karsilastirilir ama yazma yapilmaz.",
        "entry_criteria": [
            "Connector enabled ve production credential'lar yuklenmis olmali",
            "Feature flags: shadow_mode=true, write_enabled=false",
        ],
        "exit_criteria": [
            "7 gunluk kesintisiz gozlem tamamlanmis olmali",
            "Write Readiness Score >= 80",
            "Son 7 gunde critical alert sayisi = 0",
            "Auth success rate >= 99%",
            "DLQ bos olmali (count = 0)",
            "Drift count son 24 saatte < 5",
        ],
        "rollback_conditions": [
            "N/A — Bu baslangic fazdir",
        ],
        "actions": [
            "Gunluk snapshot toplama",
            "Alert threshold izleme",
            "Ingest consistency kontrolu",
            "Reconciliation calistirma",
        ],
    },
    "dry_run": {
        "order": 2,
        "label": "Dry-Run",
        "description": "Yazma islemleri simule edilir, transaction verification calisir, gercek yazma yapilmaz.",
        "entry_criteria": [
            "Shadow fazinin tum exit kriterleri karsilanmis olmali",
            "Ops ekibi onayi alinmis olmali",
            "Feature flags: shadow_mode=false, write_enabled=false, dry_run_mode=true",
        ],
        "exit_criteria": [
            "Minimum 3 gun dry-run basarili calisma",
            "Simule edilen write islemlerin %100'u transaction verification'dan gecmis olmali",
            "Hicbir data corruption/integrity hatasi tespit edilmemis olmali",
            "Write Readiness Score >= 85",
        ],
        "rollback_conditions": [
            "Transaction verification basari orani < %95",
            "Simule edilen write'larda data mismatch tespit edilirse",
            "Auth hatasi olusmasi durumunda",
        ],
        "actions": [
            "ARI push simule et (gercek API cagrisi yapma)",
            "Transaction verification calistir",
            "Sonuclari confirm_delivery ile karsilastir",
            "Gunluk dry-run raporu olustur",
        ],
    },
    "limited_live": {
        "order": 3,
        "label": "Limited Live",
        "description": "Tek tenant veya dar scope ile gercek yazma. Sinirli risk.",
        "entry_criteria": [
            "Dry-run fazinin tum exit kriterleri karsilanmis olmali",
            "Rollback mekanizmasi test edilmis ve calisir olmali",
            "Feature flags: shadow_mode=false, write_enabled=true, limited_scope=true",
            "Hedef tenant/property secilmis olmali",
        ],
        "exit_criteria": [
            "Minimum 5 gun basarili limited live calisma",
            "Write basari orani >= %99",
            "Hicbir data corruption tespit edilmemis olmali",
            "Reconciliation drift = 0 (son 48 saat)",
            "Write Readiness Score >= 90",
        ],
        "rollback_conditions": [
            "Write basari orani < %95 (son 24 saat)",
            "Herhangi bir data corruption tespit edilirse → HEMEN shadow'a don",
            "DLQ'ya 3'ten fazla entry duserse",
            "Musteri sikayeti gelirse",
        ],
        "actions": [
            "Gercek ARI push (tek tenant/property)",
            "Her write sonrasi transaction verification",
            "Saatlik reconciliation",
            "Anlik alert izleme",
        ],
    },
    "full_live": {
        "order": 4,
        "label": "Full Live",
        "description": "Tum tenant'lar icin tam yazma yolu aktif.",
        "entry_criteria": [
            "Limited live fazinin tum exit kriterleri karsilanmis olmali",
            "Tum tenant'lar icin credential dogrulama yapilmis olmali",
            "Feature flags: shadow_mode=false, write_enabled=true, limited_scope=false",
            "Disaster recovery plani hazir olmali",
        ],
        "exit_criteria": [
            "Surekli calisma — monitoring devam eder",
        ],
        "rollback_conditions": [
            "Write basari orani < %98 (son 1 saat) → Limited'e don",
            "Critical alert tetiklenirse → Limited'e don",
            "Data corruption → HEMEN shadow'a don",
        ],
        "actions": [
            "Tam ARI push (tum tenant/property)",
            "Gunluk reconciliation",
            "Haftalik performans raporu",
            "Otomatik drift fix (onay ile)",
        ],
    },
}


# ── State Management ──────────────────────────────────────────────────


async def get_current_phase(tenant_id: str) -> dict[str, Any]:
    """Get the current transition phase for a tenant."""
    state = await db[COLL_TRANSITION_STATE].find_one(
        {"tenant_id": tenant_id, "provider": "hotelrunner_v2"},
        _NO_ID,
    )
    if not state:
        return {
            "tenant_id": tenant_id,
            "current_phase": "shadow",
            "phase_started_at": None,
            "phase_day": 0,
            "transition_history": [],
        }
    return state


async def get_transition_plan() -> dict[str, Any]:
    """Return the full transition plan with all phase definitions."""
    return {
        "phases": PHASES,
        "phase_order": ["shadow", "dry_run", "limited_live", "full_live"],
        "total_phases": len(PHASES),
    }


async def get_phase_status(tenant_id: str) -> dict[str, Any]:
    """
    Get current phase + readiness check for transition.
    Combines phase state with readiness score evaluation.
    """
    from .readiness import calculate_readiness_score

    state = await get_current_phase(tenant_id)
    current = state.get("current_phase", "shadow")
    phase_def = PHASES.get(current, PHASES["shadow"])

    readiness = await calculate_readiness_score(tenant_id)

    # Check if exit criteria could be met (simplified check)
    score = readiness.get("overall_score", 0)
    phase_started = state.get("phase_started_at")

    days_in_phase = 0
    if phase_started:
        try:
            started = datetime.fromisoformat(phase_started)
            days_in_phase = (datetime.now(UTC) - started).days
        except (ValueError, TypeError):
            days_in_phase = 0

    # Determine next phase
    phase_order = ["shadow", "dry_run", "limited_live", "full_live"]
    current_idx = phase_order.index(current) if current in phase_order else 0
    next_phase = phase_order[current_idx + 1] if current_idx < len(phase_order) - 1 else None

    return {
        "tenant_id": tenant_id,
        "current_phase": current,
        "phase_label": phase_def["label"],
        "phase_description": phase_def["description"],
        "phase_order": phase_def["order"],
        "phase_started_at": phase_started,
        "days_in_phase": days_in_phase,
        "exit_criteria": phase_def["exit_criteria"],
        "rollback_conditions": phase_def["rollback_conditions"],
        "actions": phase_def["actions"],
        "next_phase": next_phase,
        "next_phase_label": PHASES[next_phase]["label"] if next_phase else None,
        "readiness_score": score,
        "readiness_verdict": readiness.get("verdict", "no_data"),
    }


async def log_transition(
    tenant_id: str,
    from_phase: str,
    to_phase: str,
    reason: str,
    initiated_by: str = "system",
) -> dict[str, Any]:
    """Log a phase transition event."""
    now = datetime.now(UTC).isoformat()
    log_entry = {
        "tenant_id": tenant_id,
        "provider": "hotelrunner_v2",
        "from_phase": from_phase,
        "to_phase": to_phase,
        "reason": reason,
        "initiated_by": initiated_by,
        "timestamp": now,
    }
    await db[COLL_TRANSITION_LOG].insert_one(log_entry)

    # Update current state
    await db[COLL_TRANSITION_STATE].update_one(
        {"tenant_id": tenant_id, "provider": "hotelrunner_v2"},
        {
            "$set": {
                "current_phase": to_phase,
                "phase_started_at": now,
                "updated_at": now,
            },
            "$push": {
                "transition_history": {
                    "from": from_phase,
                    "to": to_phase,
                    "reason": reason,
                    "timestamp": now,
                },
            },
        },
        upsert=True,
    )

    logger.info("[HRv2 transition] %s: %s → %s (%s)", tenant_id, from_phase, to_phase, reason)
    return log_entry


async def get_transition_history(tenant_id: str, limit: int = 20) -> list[dict[str, Any]]:
    """Get transition log entries."""
    return (
        await db[COLL_TRANSITION_LOG]
        .find(
            {"tenant_id": tenant_id, "provider": "hotelrunner_v2"},
            _NO_ID,
        )
        .sort("timestamp", -1)
        .to_list(limit)
    )
