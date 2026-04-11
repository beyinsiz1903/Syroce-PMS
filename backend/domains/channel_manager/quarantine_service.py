"""
Quarantine Visibility Service
==============================

Enhanced quarantine analytics for the Runtime Cockpit:
  - Classification breakdown (mapping_missing, mapping_ambiguous, provider_error, validation_failed)
  - Age buckets (< 5 min, 5-30 min, 30-120 min, > 2h)
  - Safe release guard (validates mapping is fixed before allowing release)
"""
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db
from domains.channel_manager.ari.models import COLL_ARI_CHANGE_SETS
from domains.channel_manager.data_model import (
    COLL_RATE_PLAN_MAPPINGS,
    COLL_ROOM_MAPPINGS,
)
from domains.channel_manager.mapping_validator import (
    validate_rate_plan_mapping,
    validate_room_mapping,
)

logger = logging.getLogger("ari.quarantine")

_NO_ID = {"_id": 0}


async def get_quarantine_overview(tenant_id: str) -> dict[str, Any]:
    """
    Full quarantine visibility: count, classification, age buckets.
    """
    quarantined = await db[COLL_ARI_CHANGE_SETS].find(
        {"tenant_id": tenant_id, "status": "hard_fail"},
        _NO_ID,
    ).to_list(500)

    total = len(quarantined)
    if total == 0:
        return {
            "total_quarantined": 0,
            "by_classification": {},
            "by_age_bucket": {"lt_5min": 0, "5_30min": 0, "30_120min": 0, "gt_2h": 0},
            "by_provider": {},
            "items": [],
        }

    now = datetime.now(UTC)

    # Classification breakdown
    by_classification: dict[str, int] = {}
    by_provider: dict[str, int] = {}
    by_age = {"lt_5min": 0, "5_30min": 0, "30_120min": 0, "gt_2h": 0}
    items = []

    for cs in quarantined:
        # Classification from failure types
        failures = cs.get("hard_fail_failures", [])
        for f in failures:
            ft = f.get("failure_type", "unknown")
            by_classification[ft] = by_classification.get(ft, 0) + 1

        if not failures:
            by_classification["unknown"] = by_classification.get("unknown", 0) + 1

        # Provider
        prov = cs.get("provider", "unknown")
        by_provider[prov] = by_provider.get(prov, 0) + 1

        # Age bucket
        hf_at = cs.get("hard_fail_at") or cs.get("updated_at") or cs.get("created_at", "")
        age_minutes = _compute_age_minutes(hf_at, now)

        if age_minutes < 5:
            by_age["lt_5min"] += 1
        elif age_minutes < 30:
            by_age["5_30min"] += 1
        elif age_minutes < 120:
            by_age["30_120min"] += 1
        else:
            by_age["gt_2h"] += 1

        items.append({
            "id": cs.get("id"),
            "room_type_code": cs.get("room_type_code"),
            "rate_plan_code": cs.get("rate_plan_code"),
            "provider": prov,
            "hard_fail_reason": cs.get("hard_fail_reason", ""),
            "classification": failures[0].get("failure_type", "unknown") if failures else "unknown",
            "age_minutes": age_minutes,
            "hard_fail_at": hf_at,
            "operator_action": failures[0].get("operator_action", "") if failures else "",
        })

    # Sort by age (oldest first)
    items.sort(key=lambda x: -x["age_minutes"])

    return {
        "total_quarantined": total,
        "by_classification": by_classification,
        "by_age_bucket": by_age,
        "by_provider": by_provider,
        "items": items[:50],  # Limit items returned
    }


def _compute_age_minutes(iso_str: str, now: datetime) -> int:
    """Compute age in minutes from ISO timestamp."""
    if not iso_str:
        return 0
    try:
        ts = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        return int((now - ts).total_seconds() / 60)
    except (ValueError, TypeError):
        return 0


async def check_safe_release(
    tenant_id: str,
    room_type_code: str,
    rate_plan_code: str | None = None,
    provider: str | None = None,
) -> dict[str, Any]:
    """
    Safe release guard: verify mapping is fixed before allowing quarantine release.

    Checks:
      1. Room mapping exists and is valid
      2. Rate plan mapping exists and is valid (if applicable)
      3. Change set is not stale (< 24h old)
    """
    issues = []
    checks = {
        "room_mapping_valid": False,
        "rate_mapping_valid": True,  # default True if not applicable
        "not_stale": True,
    }

    providers = [provider] if provider else ["exely", "hotelrunner"]

    for prov in providers:
        # Check room mapping
        room_mapping = await db[COLL_ROOM_MAPPINGS].find_one(
            {
                "tenant_id": tenant_id,
                "provider": prov,
                "provider_room_code": room_type_code,
            },
            _NO_ID,
        )
        room_error = validate_room_mapping(room_mapping, room_type_code)
        if room_error:
            issues.append(f"Room mapping [{prov}:{room_type_code}]: {room_error.reason}")
        else:
            checks["room_mapping_valid"] = True

        # Check rate plan mapping
        if rate_plan_code:
            checks["rate_mapping_valid"] = False
            rate_mapping = await db[COLL_RATE_PLAN_MAPPINGS].find_one(
                {
                    "tenant_id": tenant_id,
                    "provider": prov,
                    "provider_rate_code": rate_plan_code,
                },
                _NO_ID,
            )
            rate_error = validate_rate_plan_mapping(rate_mapping, rate_plan_code)
            if rate_error:
                issues.append(f"Rate mapping [{prov}:{rate_plan_code}]: {rate_error.reason}")
            else:
                checks["rate_mapping_valid"] = True

    # Check staleness (quarantined items > 24h)
    cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    stale_count = await db[COLL_ARI_CHANGE_SETS].count_documents({
        "tenant_id": tenant_id,
        "status": "hard_fail",
        "room_type_code": room_type_code,
        "hard_fail_at": {"$lt": cutoff},
    })
    if stale_count > 0:
        checks["not_stale"] = False
        issues.append(f"{stale_count} quarantined change set(s) older than 24h — may be stale")

    safe_to_release = checks["room_mapping_valid"] and checks["rate_mapping_valid"]

    return {
        "safe_to_release": safe_to_release,
        "checks": checks,
        "issues": issues,
        "stale_count": stale_count,
        "recommendation": (
            "Release is safe — mappings verified"
            if safe_to_release
            else "DO NOT release — fix issues first: " + "; ".join(issues)
        ),
    }
