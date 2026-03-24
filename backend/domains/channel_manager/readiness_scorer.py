"""
Readiness Scorer — "Why NOT READY?" Scored & Prioritized Breakdown
===================================================================

Produces a scored readiness assessment for a tenant:
  - Overall readiness score (0-100)
  - Prioritized breakdown of blockers with severity
  - Estimated fix impact per issue
  - Fix order suggestion

Score Components:
  - Mapping completeness (40 pts)
  - Hard fail gate clear (25 pts)
  - Verify ratio (20 pts)
  - Drift backlog (10 pts)
  - Quarantine clear (5 pts)
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from core.database import db
from domains.channel_manager.ari.hard_fail_gate import get_hard_fail_stats
from domains.channel_manager.ari.push_loop_worker import get_push_worker
from domains.channel_manager.data_model import (
    COLL_RATE_PLAN_MAPPINGS,
    COLL_RECONCILIATION_CASES,
    COLL_ROOM_MAPPINGS,
)
from domains.channel_manager.quarantine_service import get_quarantine_overview

logger = logging.getLogger("channel_manager.readiness_scorer")

_NO_ID = {"_id": 0}

# Weight configuration
WEIGHT_MAPPING = 40
WEIGHT_HARD_FAIL = 25
WEIGHT_VERIFY = 20
WEIGHT_DRIFT = 10
WEIGHT_QUARANTINE = 5


async def compute_readiness_score(tenant_id: str, property_id: str = "default") -> Dict[str, Any]:
    """
    Compute a scored readiness assessment.

    Returns:
      - score: 0-100
      - is_ready: bool (score == 100)
      - breakdown: list of issues sorted by priority (BLOCKER > CRITICAL > WARNING > INFO)
      - fix_order: recommended fix sequence
    """
    issues: List[Dict[str, Any]] = []
    scores = {}

    # 1. Mapping Completeness (40 pts)
    mapping_score, mapping_issues = await _score_mapping(tenant_id, property_id)
    scores["mapping"] = {"score": mapping_score, "max": WEIGHT_MAPPING}
    issues.extend(mapping_issues)

    # 2. Hard Fail Gate (25 pts)
    hf_score, hf_issues = await _score_hard_fail(tenant_id)
    scores["hard_fail"] = {"score": hf_score, "max": WEIGHT_HARD_FAIL}
    issues.extend(hf_issues)

    # 3. Verify Ratio (20 pts)
    verify_score, verify_issues = _score_verify()
    scores["verify"] = {"score": verify_score, "max": WEIGHT_VERIFY}
    issues.extend(verify_issues)

    # 4. Drift Backlog (10 pts)
    drift_score, drift_issues = await _score_drift(tenant_id)
    scores["drift"] = {"score": drift_score, "max": WEIGHT_DRIFT}
    issues.extend(drift_issues)

    # 5. Quarantine (5 pts)
    q_score, q_issues = await _score_quarantine(tenant_id)
    scores["quarantine"] = {"score": q_score, "max": WEIGHT_QUARANTINE}
    issues.extend(q_issues)

    total_score = sum(s["score"] for s in scores.values())
    total_max = sum(s["max"] for s in scores.values())
    final_score = round(total_score / total_max * 100) if total_max > 0 else 0

    # Sort issues by severity priority
    severity_order = {"blocker": 0, "critical": 1, "warning": 2, "info": 3}
    issues.sort(key=lambda x: severity_order.get(x["severity"], 99))

    # Generate fix order
    fix_order = [
        {
            "step": i + 1,
            "action": issue["fix_action"],
            "impact": f"+{issue['fix_impact']} puan",
            "severity": issue["severity"],
            "category": issue["category"],
        }
        for i, issue in enumerate(issues) if issue["fix_impact"] > 0
    ]

    return {
        "score": final_score,
        "is_ready": final_score == 100,
        "scores": scores,
        "issues": issues,
        "fix_order": fix_order,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


async def _score_mapping(tenant_id: str, property_id: str):
    """Score mapping completeness across all providers."""
    issues = []
    total_rooms = 0
    total_rates = 0
    broken_rooms = 0
    broken_rates = 0
    inactive_rooms = 0
    inactive_rates = 0

    for provider in ["exely", "hotelrunner"]:
        rooms = await db[COLL_ROOM_MAPPINGS].find(
            {"tenant_id": tenant_id, "provider": provider}, _NO_ID,
        ).to_list(500)
        rates = await db[COLL_RATE_PLAN_MAPPINGS].find(
            {"tenant_id": tenant_id, "provider": provider}, _NO_ID,
        ).to_list(500)

        prov_broken_rooms = sum(1 for m in rooms if not m.get("pms_room_type_id"))
        prov_inactive_rooms = sum(1 for m in rooms if not m.get("is_active", True))
        prov_broken_rates = sum(1 for m in rates if not m.get("pms_rate_plan_id"))
        prov_inactive_rates = sum(1 for m in rates if not m.get("is_active", True))

        total_rooms += len(rooms)
        total_rates += len(rates)
        broken_rooms += prov_broken_rooms
        broken_rates += prov_broken_rates
        inactive_rooms += prov_inactive_rooms
        inactive_rates += prov_inactive_rates

        if prov_broken_rooms > 0:
            issues.append({
                "severity": "blocker",
                "category": "mapping",
                "title": f"Kirik room mapping ({provider})",
                "detail": f"{prov_broken_rooms} room mapping'de PMS baglantisi yok",
                "count": prov_broken_rooms,
                "fix_action": f"{provider} room mapping'lerini Data Model'den duzelt",
                "fix_impact": _calc_mapping_impact(prov_broken_rooms, total_rooms, WEIGHT_MAPPING),
            })

        if prov_broken_rates > 0:
            issues.append({
                "severity": "blocker",
                "category": "mapping",
                "title": f"Kirik rate plan mapping ({provider})",
                "detail": f"{prov_broken_rates} rate plan mapping'de PMS baglantisi yok",
                "count": prov_broken_rates,
                "fix_action": f"{provider} rate plan mapping'lerini Data Model'den duzelt",
                "fix_impact": _calc_mapping_impact(prov_broken_rates, total_rates, WEIGHT_MAPPING),
            })

        if prov_inactive_rooms > 0:
            issues.append({
                "severity": "warning",
                "category": "mapping",
                "title": f"Inaktif room mapping ({provider})",
                "detail": f"{prov_inactive_rooms} room mapping inaktif durumda",
                "count": prov_inactive_rooms,
                "fix_action": f"{provider} inaktif room mapping'leri aktif et",
                "fix_impact": _calc_mapping_impact(prov_inactive_rooms, total_rooms, WEIGHT_MAPPING),
            })

    total_all = total_rooms + total_rates
    broken_all = broken_rooms + broken_rates + inactive_rooms + inactive_rates
    if total_all == 0:
        return WEIGHT_MAPPING, issues

    good_ratio = max(0, (total_all - broken_all)) / total_all
    score = round(good_ratio * WEIGHT_MAPPING, 1)
    return score, issues


def _calc_mapping_impact(broken_count: int, total: int, weight: int) -> int:
    if total == 0:
        return 0
    return round(broken_count / total * weight)


async def _score_hard_fail(tenant_id: str):
    """Score based on active hard fail blocks."""
    issues = []
    hf_stats = await get_hard_fail_stats(tenant_id)
    blocked = hf_stats["hard_fail_change_sets"]
    incidents = hf_stats["open_hard_fail_incidents"]

    if blocked == 0 and incidents == 0:
        return WEIGHT_HARD_FAIL, issues

    score = 0  # Any hard fail = 0 points

    if blocked > 0:
        issues.append({
            "severity": "critical",
            "category": "hard_fail",
            "title": "Hard fail bloklari aktif",
            "detail": f"{blocked} change set hard fail ile bloklandi",
            "count": blocked,
            "fix_action": "Eksik mapping'leri tamamla, sonra quarantine'den serbest birak",
            "fix_impact": WEIGHT_HARD_FAIL,
        })

    if incidents > 0:
        issues.append({
            "severity": "critical",
            "category": "hard_fail",
            "title": "Acik hard fail incident'lari",
            "detail": f"{incidents} acik hard fail incident'i var",
            "count": incidents,
            "fix_action": "Incident'lari incele ve mapping sorunlarini coz",
            "fix_impact": round(WEIGHT_HARD_FAIL * 0.4),
        })

    return score, issues


def _score_verify():
    """Score based on verify success ratio."""
    issues = []
    worker = get_push_worker()
    metrics = worker.metrics.to_dict()
    ratio = metrics["verify_success_ratio"]
    total = metrics["verify_success_count"] + metrics["verify_fail_count"]

    if total == 0:
        # No verifications yet — partial score
        issues.append({
            "severity": "info",
            "category": "verify",
            "title": "Henuz dogrulama yapilmadi",
            "detail": "Push loop hic dogrulama cikisi uretmedi",
            "count": 0,
            "fix_action": "Push loop'u baslat ve ARI gonderimi yap",
            "fix_impact": WEIGHT_VERIFY,
        })
        return 0, issues

    score = round(ratio * WEIGHT_VERIFY, 1)

    if ratio < 0.95:
        severity = "critical" if ratio < 0.8 else "warning"
        issues.append({
            "severity": severity,
            "category": "verify",
            "title": f"Verify orani dusuk (%{round(ratio * 100, 1)})",
            "detail": f"{metrics['verify_fail_count']} basarisiz / {total} toplam dogrulama",
            "count": metrics["verify_fail_count"],
            "fix_action": "Provider baglanti ve mapping konfigurasyonunu kontrol et",
            "fix_impact": round((0.95 - ratio) * WEIGHT_VERIFY) if ratio < 0.95 else 0,
        })

    return score, issues


async def _score_drift(tenant_id: str):
    """Score based on active drift count."""
    issues = []
    drift_count = await db[COLL_RECONCILIATION_CASES].count_documents({
        "tenant_id": tenant_id,
        "status": {"$in": ["open", "investigating"]},
        "drift_type": {"$exists": True, "$ne": None},
    })

    if drift_count == 0:
        return WEIGHT_DRIFT, issues

    # Scale: 0 drifts = full score, 10+ = 0
    score = max(0, round(WEIGHT_DRIFT * (1 - min(drift_count / 10, 1)), 1))

    severity = "warning" if drift_count < 5 else "critical"
    issues.append({
        "severity": severity,
        "category": "drift",
        "title": f"Aktif drift backlog ({drift_count})",
        "detail": f"{drift_count} acik drift/uyumsuzluk vakasi var",
        "count": drift_count,
        "fix_action": "Auto-heal calistir veya manuel inceleme yap",
        "fix_impact": WEIGHT_DRIFT - score,
    })

    return score, issues


async def _score_quarantine(tenant_id: str):
    """Score based on quarantined items."""
    issues = []
    overview = await get_quarantine_overview(tenant_id)
    total = overview["total_quarantined"]

    if total == 0:
        return WEIGHT_QUARANTINE, issues

    score = 0

    issues.append({
        "severity": "warning",
        "category": "quarantine",
        "title": f"Karantina'da {total} item",
        "detail": f"{total} change set karantina'da bekliyor",
        "count": total,
        "fix_action": "Mapping'leri duzelt, sonra safe release uygula",
        "fix_impact": WEIGHT_QUARANTINE,
    })

    return score, issues


async def log_ready_state_transition(
    tenant_id: str,
    new_state: str,
    score: int,
    scores: Dict[str, Any],
    issues: List[Dict[str, Any]],
) -> None:
    """
    Log READY state transitions for delta analysis.
    When tenant becomes READY: log why.
    When tenant falls NOT READY: log what changed.
    """
    now = datetime.now(timezone.utc).isoformat()
    coll = db["readiness_state_log"]

    # Get previous state
    prev = await coll.find_one(
        {"tenant_id": tenant_id},
        {"_id": 0},
        sort=[("timestamp", -1)],
    )

    prev_state = prev.get("state") if prev else None
    is_transition = prev_state != new_state

    doc = {
        "tenant_id": tenant_id,
        "state": new_state,
        "score": score,
        "scores": scores,
        "issue_count": len(issues),
        "issues_snapshot": issues[:10],
        "is_transition": is_transition,
        "previous_state": prev_state,
        "timestamp": now,
    }

    if is_transition and prev:
        doc["delta_from_previous"] = {
            "prev_score": prev.get("score", 0),
            "score_change": score - prev.get("score", 0),
            "prev_issue_count": prev.get("issue_count", 0),
        }

    await coll.insert_one(doc)

    if is_transition:
        logger.info(
            f"READY state transition: tenant={tenant_id} "
            f"{prev_state} -> {new_state} (score={score})"
        )
