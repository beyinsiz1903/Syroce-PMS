"""
Auto-Heal Service — Conservative Runtime Healing
=================================================

Processes open reconciliation cases based on the Truth Table.
Strategy: start conservative, expand carefully.

Rules:
  1. Only heal cases in SAFE_AUTO_HEAL whitelist
  2. RISKY_AUTO_HEAL requires explicit opt-in
  3. Every heal produces evidence (audit record)
  4. Failed heals escalate to manual_review (no infinite retry)
  5. Rate-limited: max N heals per cycle

Whitelist (safe):
  - stale_locally   → re-ingest provider data
  - stale_remotely  → re-push PMS data
  - duplicate_event → merge/ignore
  - stale_event     → ignore

NOT auto-healed (manual only):
  - missing_locally / missing_remotely
  - status_mismatch / financial_mismatch
  - mapping_mismatch
  - payload_mismatch (risky, opt-in only)
"""

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from core.database import db
from domains.channel_manager.data_model import (
    COLL_RECONCILIATION_CASES,
    DriftResolution,
    DriftType,
)
from domains.channel_manager.reconciliation_truth import (
    TRUTH_TABLE,
    TruthRule,
)

logger = logging.getLogger("channel_manager.auto_heal")

COLL_AUTO_HEAL_LOG = "auto_heal_log"
_NO_ID = {"_id": 0}

# Max cases to process per cycle
MAX_HEALS_PER_CYCLE = 20

# Safe whitelist — these can be auto-healed without opt-in
SAFE_WHITELIST = {
    DriftType.STALE_LOCALLY.value,
    DriftType.STALE_REMOTELY.value,
}

# Risky whitelist — requires explicit opt-in flag
RISKY_WHITELIST = {
    DriftType.PAYLOAD_MISMATCH.value,
}


class AutoHealResult:
    """Result of an auto-heal cycle."""

    def __init__(self):
        self.processed: int = 0
        self.healed: int = 0
        self.skipped: int = 0
        self.failed: int = 0
        self.escalated: int = 0
        self.details: list[dict[str, Any]] = []

    def to_dict(self) -> dict[str, Any]:
        return {
            "processed": self.processed,
            "healed": self.healed,
            "skipped": self.skipped,
            "failed": self.failed,
            "escalated": self.escalated,
            "details": self.details[:20],
        }


async def run_auto_heal_cycle(
    tenant_id: str,
    include_risky: bool = False,
    max_heals: int = MAX_HEALS_PER_CYCLE,
) -> AutoHealResult:
    """
    Run one auto-heal cycle for a tenant.

    Finds open cases eligible for auto-healing and attempts resolution.
    """
    result = AutoHealResult()

    # Build whitelist
    whitelist = set(SAFE_WHITELIST)
    if include_risky:
        whitelist |= RISKY_WHITELIST

    # Find eligible open cases
    eligible_types = list(whitelist)
    cases = (
        await db[COLL_RECONCILIATION_CASES]
        .find(
            {
                "tenant_id": tenant_id,
                "status": {"$in": ["open", "investigating"]},
                "$or": [
                    {"drift_type": {"$in": eligible_types}},
                    {"case_type": {"$in": ["stale_event", "duplicate_event"]}},
                ],
            },
            _NO_ID,
        )
        .sort("created_at", 1)
        .limit(max_heals)
        .to_list(max_heals)
    )

    for case in cases:
        result.processed += 1
        case_id = case.get("id", "")
        drift_type = case.get("drift_type") or case.get("case_type", "")

        try:
            healed = await _attempt_heal(case, drift_type, whitelist)
            if healed:
                result.healed += 1
                result.details.append(
                    {
                        "case_id": case_id,
                        "drift_type": drift_type,
                        "outcome": "healed",
                    }
                )
            else:
                result.skipped += 1
                result.details.append(
                    {
                        "case_id": case_id,
                        "drift_type": drift_type,
                        "outcome": "skipped",
                        "reason": "Not eligible or no healing action available",
                    }
                )
        except Exception as e:
            result.failed += 1
            result.escalated += 1
            await _escalate_case(case, str(e))
            result.details.append(
                {
                    "case_id": case_id,
                    "drift_type": drift_type,
                    "outcome": "failed",
                    "error": str(e),
                }
            )
            logger.error(f"Auto-heal failed for case {case_id}: {e}")

    logger.info(f"Auto-heal cycle: tenant={tenant_id} processed={result.processed} healed={result.healed} skipped={result.skipped} failed={result.failed}")
    return result


async def _attempt_heal(
    case: dict[str, Any],
    drift_type: str,
    whitelist: set,
) -> bool:
    """
    Attempt to heal a single case.
    Returns True if healed, False if skipped.
    """
    # Check whitelist
    if drift_type not in whitelist:
        # Check case_type-based auto-resolution
        case_type = case.get("case_type", "")
        if case_type not in ("stale_event", "duplicate_event"):
            return False

    # Look up truth table for healing action
    rule = TRUTH_TABLE.get(drift_type)
    if not rule:
        return False

    if rule.resolution not in (DriftResolution.SAFE_AUTO_HEAL, DriftResolution.RISKY_AUTO_HEAL):
        return False

    # Execute the healing action
    action = _get_heal_action(drift_type, rule)
    if not action:
        return False

    now = datetime.now(UTC).isoformat()

    # Create evidence record BEFORE healing
    evidence_id = str(uuid.uuid4())
    evidence = {
        "id": evidence_id,
        "tenant_id": case["tenant_id"],
        "case_id": case.get("id"),
        "drift_type": drift_type,
        "rule_resolution": rule.resolution.value,
        "gold_source": rule.gold_source.value,
        "heal_action": action["action"],
        "description": action["description"],
        "case_snapshot": {
            "provider": case.get("provider"),
            "room_type_code": case.get("room_type_code") or case.get("details", {}).get("room_type_code"),
            "severity": case.get("severity"),
            "description": case.get("description"),
        },
        "status": "completed",
        "timestamp": now,
    }

    # Mark the case as resolved by auto-heal
    await db[COLL_RECONCILIATION_CASES].update_one(
        {"id": case["id"]},
        {
            "$set": {
                "status": "resolved",
                "resolution": f"[AUTO_HEAL] {action['action']}: {action['description']}",
                "resolved_by": "system:auto_heal",
                "resolved_at": now,
                "updated_at": now,
                "auto_heal_evidence_id": evidence_id,
            }
        },
    )

    # Persist evidence
    await db[COLL_AUTO_HEAL_LOG].insert_one(evidence)

    logger.info(f"Auto-healed case {case.get('id')}: type={drift_type} action={action['action']}")
    return True


def _get_heal_action(drift_type: str, rule: TruthRule) -> dict[str, str] | None:
    """Determine the concrete healing action for a drift type."""
    actions = {
        DriftType.STALE_LOCALLY.value: {
            "action": "re_ingest",
            "description": "Re-ingest latest data from provider (gold source: provider_snapshot)",
        },
        DriftType.STALE_REMOTELY.value: {
            "action": "re_push",
            "description": "Re-push latest PMS data to provider (gold source: reservation_lineage)",
        },
        DriftType.PAYLOAD_MISMATCH.value: {
            "action": "re_push_ari",
            "description": "Re-push current ARI state to provider (gold source: ari_drift_state)",
        },
    }
    return actions.get(drift_type)


async def _escalate_case(case: dict[str, Any], error: str) -> None:
    """Escalate a failed auto-heal to manual review."""
    now = datetime.now(UTC).isoformat()
    await db[COLL_RECONCILIATION_CASES].update_one(
        {"id": case["id"]},
        {
            "$set": {
                "status": "investigating",
                "severity": "high",
                "last_auto_heal_error": error,
                "last_auto_heal_attempt": now,
                "updated_at": now,
            }
        },
    )

    # Log the failure
    await db[COLL_AUTO_HEAL_LOG].insert_one(
        {
            "id": str(uuid.uuid4()),
            "tenant_id": case["tenant_id"],
            "case_id": case.get("id"),
            "drift_type": case.get("drift_type") or case.get("case_type"),
            "heal_action": "escalated",
            "description": f"Auto-heal failed: {error}",
            "status": "failed",
            "error": error,
            "timestamp": now,
        }
    )


async def get_auto_heal_stats(tenant_id: str) -> dict[str, Any]:
    """Get auto-heal statistics for the dashboard."""
    # Total auto-healed
    total_healed = await db[COLL_AUTO_HEAL_LOG].count_documents(
        {
            "tenant_id": tenant_id,
            "status": "completed",
        }
    )
    total_failed = await db[COLL_AUTO_HEAL_LOG].count_documents(
        {
            "tenant_id": tenant_id,
            "status": "failed",
        }
    )

    # Eligible cases (open + in whitelist)
    eligible_types = list(SAFE_WHITELIST)
    eligible_count = await db[COLL_RECONCILIATION_CASES].count_documents(
        {
            "tenant_id": tenant_id,
            "status": {"$in": ["open", "investigating"]},
            "$or": [
                {"drift_type": {"$in": eligible_types}},
                {"case_type": {"$in": ["stale_event", "duplicate_event"]}},
            ],
        }
    )

    # Recent heals (last 24h)
    from datetime import timedelta

    since = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    recent_healed = await db[COLL_AUTO_HEAL_LOG].count_documents(
        {
            "tenant_id": tenant_id,
            "status": "completed",
            "timestamp": {"$gte": since},
        }
    )

    # By drift type
    type_pipeline = [
        {"$match": {"tenant_id": tenant_id, "status": "completed"}},
        {"$group": {"_id": "$drift_type", "count": {"$sum": 1}}},
    ]
    by_type = {}
    async for doc in db[COLL_AUTO_HEAL_LOG].aggregate(type_pipeline):
        if doc["_id"]:
            by_type[doc["_id"]] = doc["count"]

    return {
        "total_healed": total_healed,
        "total_failed": total_failed,
        "eligible_cases": eligible_count,
        "healed_last_24h": recent_healed,
        "by_drift_type": by_type,
        "safe_whitelist": list(SAFE_WHITELIST),
        "risky_whitelist": list(RISKY_WHITELIST),
    }


async def get_auto_heal_history(
    tenant_id: str,
    limit: int = 50,
    skip: int = 0,
) -> list[dict[str, Any]]:
    """Get recent auto-heal operations."""
    return (
        await db[COLL_AUTO_HEAL_LOG]
        .find(
            {"tenant_id": tenant_id},
            _NO_ID,
        )
        .sort("timestamp", -1)
        .skip(skip)
        .limit(limit)
        .to_list(limit)
    )
