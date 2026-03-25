"""
Tech Debt Aggregator — Quarantine burn-down tracking for Control Plane.

Reads the quarantine manifest and provides categorized counts,
weekly burn-down targets, and progress tracking.
"""
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("controlplane.tech_debt_aggregator")

QUARANTINE_CATEGORIES = {
    "stale_fixtures": {
        "label": "Eski Fixture",
        "description": "Room type seed verisi eksik olan testler",
        "priority": 1,
        "effort_per_test": 0.5,
        "weekly_target": 5,
    },
    "changed_api": {
        "label": "API Degisikligi",
        "description": "Endpoint davranisi veya response degisen testler",
        "priority": 2,
        "effort_per_test": 1.0,
        "weekly_target": 3,
    },
    "changed_implementation": {
        "label": "Implementasyon Degisikligi",
        "description": "Ic mantik veya wiring degisen testler",
        "priority": 3,
        "effort_per_test": 1.5,
        "weekly_target": 3,
    },
    "external_dependency": {
        "label": "Dis Bagimllik",
        "description": "Canli dis servis gerektiren testler",
        "priority": 4,
        "effort_per_test": 2.0,
        "weekly_target": 1,
    },
    "meta-test": {
        "label": "Meta Test",
        "description": "Karantina referansi kontrol testleri",
        "priority": 5,
        "effort_per_test": 0.25,
        "weekly_target": 1,
    },
}


def compute_tech_debt() -> dict[str, Any]:
    """Compute tech debt dashboard from quarantine manifest."""
    try:
        from tests._quarantine.quarantine_manifest import QUARANTINE_SKIP_MAP
    except ImportError:
        logger.warning("Quarantine manifest not found — returning empty")
        return _empty_response()

    now = datetime.now(UTC)

    category_counts: dict[str, int] = {}
    category_tests: dict[str, list] = {}

    for test_id, meta in QUARANTINE_SKIP_MAP.items():
        cat = meta.get("category", "unknown")
        category_counts[cat] = category_counts.get(cat, 0) + 1
        if cat not in category_tests:
            category_tests[cat] = []
        category_tests[cat].append({
            "test_id": test_id.split("::")[-1] if "::" in test_id else test_id,
            "full_path": test_id,
            "since": meta.get("since", ""),
            "reason": meta.get("block_reason", ""),
        })

    total_quarantined = sum(category_counts.values())

    categories = []
    total_weekly_target = 0
    total_effort_hours = 0

    for cat_key, cat_meta in sorted(QUARANTINE_CATEGORIES.items(), key=lambda x: x[1]["priority"]):
        count = category_counts.get(cat_key, 0)
        effort = count * cat_meta["effort_per_test"]
        weekly_target = min(cat_meta["weekly_target"], count)
        weeks_to_clear = _weeks_to_clear(count, cat_meta["weekly_target"])

        total_weekly_target += weekly_target
        total_effort_hours += effort

        categories.append({
            "key": cat_key,
            "label": cat_meta["label"],
            "description": cat_meta["description"],
            "priority": cat_meta["priority"],
            "count": count,
            "effort_hours": round(effort, 1),
            "weekly_target": weekly_target,
            "weeks_to_clear": weeks_to_clear,
            "tests": category_tests.get(cat_key, []),
        })

    weeks_total = _weeks_to_clear(total_quarantined, total_weekly_target) if total_weekly_target > 0 else 0

    return {
        "total_quarantined": total_quarantined,
        "total_effort_hours": round(total_effort_hours, 1),
        "total_weekly_target": total_weekly_target,
        "estimated_weeks_to_zero": weeks_total,
        "categories": categories,
        "health_score": _debt_health_score(total_quarantined),
        "health_grade": _debt_health_grade(total_quarantined),
        "calculated_at": now.isoformat(),
    }


def _weeks_to_clear(count: int, weekly_rate: int) -> int:
    if weekly_rate <= 0 or count <= 0:
        return 0
    return -(-count // weekly_rate)


def _debt_health_score(total: int) -> int:
    if total == 0:
        return 100
    if total <= 5:
        return 90
    if total <= 15:
        return 70
    if total <= 30:
        return 50
    return 30


def _debt_health_grade(total: int) -> str:
    score = _debt_health_score(total)
    if score >= 90:
        return "A"
    if score >= 70:
        return "B"
    if score >= 50:
        return "C"
    return "D"


def _empty_response() -> dict[str, Any]:
    return {
        "total_quarantined": 0,
        "total_effort_hours": 0,
        "total_weekly_target": 0,
        "estimated_weeks_to_zero": 0,
        "categories": [],
        "health_score": 100,
        "health_grade": "A",
        "calculated_at": datetime.now(UTC).isoformat(),
    }
