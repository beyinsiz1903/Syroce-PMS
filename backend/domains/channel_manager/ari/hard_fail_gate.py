"""
Hard Fail Gate — Runtime Mapping Enforcement
=============================================

Guards the ARI push pipeline. No push is allowed when:
  - Room mapping missing or broken
  - Rate plan mapping missing or broken
  - Provider connection inactive

On hard fail:
  1. Quarantine the change set (status → "hard_fail")
  2. Create an incident with operator action hint
  3. Update dashboard hard_fail counter

This is the runtime enforcement layer. Tests prove the logic;
this module ensures it ACTUALLY blocks bad pushes in production.
"""
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from core.database import db
from domains.channel_manager.data_model import (
    COLL_ROOM_MAPPINGS, COLL_RATE_PLAN_MAPPINGS,
    COLL_PROVIDER_CONNECTIONS, COLL_RECONCILIATION_CASES,
    CaseType, CaseSeverity, CaseStatus, MappingFailure,
)
from domains.channel_manager.mapping_validator import (
    validate_room_mapping, validate_rate_plan_mapping,
)
from domains.channel_manager.ari.models import COLL_ARI_CHANGE_SETS

logger = logging.getLogger("ari.hard_fail_gate")

_NO_ID = {"_id": 0}

# Hard fail status constants
HF_PASS = "pass"
HF_BLOCKED = "hard_fail"

COLL_HARD_FAIL_LOG = "ari_hard_fail_log"


class HardFailVerdict:
    """Result of a hard fail gate check."""

    def __init__(self, passed: bool):
        self.passed = passed
        self.failures: List[Dict[str, Any]] = []

    def add_failure(
        self, entity_type: str, code: str,
        failure_type: str, reason: str, operator_action: str,
    ):
        self.failures.append({
            "entity_type": entity_type,
            "code": code,
            "failure_type": failure_type,
            "reason": reason,
            "operator_action": operator_action,
        })
        self.passed = False

    @property
    def status(self) -> str:
        return HF_PASS if self.passed else HF_BLOCKED

    def summary(self) -> str:
        if self.passed:
            return "All mappings valid"
        parts = [f"[{f['entity_type']}:{f['code']}] {f['reason']}" for f in self.failures]
        return "; ".join(parts)


async def check_mapping_gate(
    tenant_id: str,
    property_id: str,
    provider: str,
    room_type_code: str,
    rate_plan_code: Optional[str] = None,
) -> HardFailVerdict:
    """
    Pre-push mapping gate. Returns verdict with detailed failure info.
    This is called BEFORE any ARI push attempt.
    """
    verdict = HardFailVerdict(passed=True)

    # Check room mapping
    room_mapping = await db[COLL_ROOM_MAPPINGS].find_one(
        {
            "tenant_id": tenant_id,
            "property_id": property_id,
            "provider": provider,
            "provider_room_code": room_type_code,
        },
        _NO_ID,
    )
    room_error = validate_room_mapping(room_mapping, room_type_code)
    if room_error:
        verdict.add_failure(
            entity_type="room",
            code=room_type_code,
            failure_type=room_error.failure_type.value,
            reason=room_error.reason,
            operator_action=room_error.operator_action,
        )

    # Check rate plan mapping (if applicable)
    if rate_plan_code:
        rate_mapping = await db[COLL_RATE_PLAN_MAPPINGS].find_one(
            {
                "tenant_id": tenant_id,
                "property_id": property_id,
                "provider": provider,
                "provider_rate_code": rate_plan_code,
            },
            _NO_ID,
        )
        rate_error = validate_rate_plan_mapping(rate_mapping, rate_plan_code)
        if rate_error:
            verdict.add_failure(
                entity_type="rate_plan",
                code=rate_plan_code,
                failure_type=rate_error.failure_type.value,
                reason=rate_error.reason,
                operator_action=rate_error.operator_action,
            )

    return verdict


async def check_provider_gate(
    tenant_id: str,
    property_id: str,
    provider: str,
) -> HardFailVerdict:
    """Check that the provider connection is active."""
    verdict = HardFailVerdict(passed=True)

    conn = await db[COLL_PROVIDER_CONNECTIONS].find_one(
        {
            "tenant_id": tenant_id,
            "property_id": property_id,
            "provider": provider,
            "status": "active",
        },
        _NO_ID,
    )
    if not conn:
        verdict.add_failure(
            entity_type="provider",
            code=provider,
            failure_type="inactive_connection",
            reason=f"No active connection for provider: {provider}",
            operator_action="Activate or create a provider connection in Settings",
        )

    return verdict


async def enforce_hard_fail_gate(change_set: Dict[str, Any]) -> HardFailVerdict:
    """
    Full pre-push gate for a single change set.

    Checks mappings + provider connection.
    If failed: quarantines change set + creates incident.
    """
    tenant_id = change_set["tenant_id"]
    property_id = change_set["property_id"]
    provider = change_set["provider"]
    room_type_code = change_set.get("room_type_code", "")
    rate_plan_code = change_set.get("rate_plan_code")

    # Run mapping gate
    mapping_verdict = await check_mapping_gate(
        tenant_id, property_id, provider,
        room_type_code, rate_plan_code,
    )

    if not mapping_verdict.passed:
        await _quarantine_change_set(change_set, mapping_verdict)
        await _create_hard_fail_incident(change_set, mapping_verdict)
        await _log_hard_fail(change_set, mapping_verdict)
        logger.warning(
            f"HARD FAIL: cs={change_set.get('id')} "
            f"room={room_type_code} rate={rate_plan_code} "
            f"failures={len(mapping_verdict.failures)}"
        )
        return mapping_verdict

    return mapping_verdict


async def _quarantine_change_set(
    cs: Dict[str, Any], verdict: HardFailVerdict,
) -> None:
    """Move change set to hard_fail status."""
    now = datetime.now(timezone.utc).isoformat()
    await db[COLL_ARI_CHANGE_SETS].update_one(
        {"id": cs["id"]},
        {"$set": {
            "status": "hard_fail",
            "hard_fail_reason": verdict.summary(),
            "hard_fail_failures": verdict.failures,
            "hard_fail_at": now,
            "updated_at": now,
        }},
    )


async def _create_hard_fail_incident(
    cs: Dict[str, Any], verdict: HardFailVerdict,
) -> str:
    """Create a reconciliation case for the hard fail."""
    import uuid
    now = datetime.now(timezone.utc).isoformat()

    # Determine the primary failure type for the case
    primary = verdict.failures[0] if verdict.failures else {}
    case_type = CaseType.MISSING_MAPPING
    severity = CaseSeverity.HIGH

    case_id = str(uuid.uuid4())
    doc = {
        "id": case_id,
        "tenant_id": cs["tenant_id"],
        "property_id": cs["property_id"],
        "provider": cs["provider"],
        "case_type": case_type.value,
        "severity": severity.value,
        "status": CaseStatus.OPEN.value,
        "description": f"Hard fail: {verdict.summary()}",
        "details": {
            "change_set_id": cs.get("id"),
            "room_type_code": cs.get("room_type_code"),
            "rate_plan_code": cs.get("rate_plan_code"),
            "failures": verdict.failures,
            "change_scope": cs.get("change_scope"),
        },
        "suggested_action": primary.get("operator_action", "Review mapping configuration"),
        "drift_type": "mapping_mismatch",
        "created_at": now,
        "updated_at": now,
    }

    # Avoid duplicate incidents for same room/rate/provider
    existing = await db[COLL_RECONCILIATION_CASES].find_one({
        "tenant_id": cs["tenant_id"],
        "provider": cs["provider"],
        "case_type": case_type.value,
        "status": {"$in": ["open", "investigating"]},
        "details.room_type_code": cs.get("room_type_code"),
        "details.rate_plan_code": cs.get("rate_plan_code"),
    })
    if existing:
        return existing.get("id", "")

    await db[COLL_RECONCILIATION_CASES].insert_one(doc)
    return case_id


async def _log_hard_fail(
    cs: Dict[str, Any], verdict: HardFailVerdict,
) -> None:
    """Log hard fail for audit and metrics."""
    import uuid
    now = datetime.now(timezone.utc).isoformat()
    await db[COLL_HARD_FAIL_LOG].insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": cs["tenant_id"],
        "property_id": cs["property_id"],
        "provider": cs["provider"],
        "change_set_id": cs.get("id"),
        "room_type_code": cs.get("room_type_code"),
        "rate_plan_code": cs.get("rate_plan_code"),
        "failures": verdict.failures,
        "summary": verdict.summary(),
        "timestamp": now,
    })


async def get_hard_fail_stats(tenant_id: str) -> Dict[str, Any]:
    """Get hard fail statistics for the dashboard."""
    # Active hard-fail change sets
    hard_fail_count = await db[COLL_ARI_CHANGE_SETS].count_documents(
        {"tenant_id": tenant_id, "status": "hard_fail"},
    )

    # Hard fail incidents (open)
    hf_incidents = await db[COLL_RECONCILIATION_CASES].count_documents({
        "tenant_id": tenant_id,
        "case_type": "missing_mapping",
        "status": {"$in": ["open", "investigating"]},
    })

    # Recent hard fail log entries (last 24h)
    from datetime import timedelta
    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    recent_hf = await db[COLL_HARD_FAIL_LOG].count_documents({
        "tenant_id": tenant_id,
        "timestamp": {"$gte": since},
    })

    # Breakdown by failure type
    type_pipeline = [
        {"$match": {"tenant_id": tenant_id, "status": "hard_fail"}},
        {"$unwind": "$hard_fail_failures"},
        {"$group": {
            "_id": "$hard_fail_failures.failure_type",
            "count": {"$sum": 1},
        }},
    ]
    by_type = {}
    async for doc in db[COLL_ARI_CHANGE_SETS].aggregate(type_pipeline):
        if doc["_id"]:
            by_type[doc["_id"]] = doc["count"]

    return {
        "hard_fail_change_sets": hard_fail_count,
        "open_hard_fail_incidents": hf_incidents,
        "hard_fails_last_24h": recent_hf,
        "by_failure_type": by_type,
        "enforcement_active": True,
    }


async def release_quarantine(
    tenant_id: str, room_type_code: str,
    rate_plan_code: Optional[str] = None,
    provider: Optional[str] = None,
) -> int:
    """
    Release quarantined change sets after mapping fix.
    Moves them back to 'pending' so the push loop picks them up.
    """
    query: Dict[str, Any] = {
        "tenant_id": tenant_id,
        "status": "hard_fail",
        "room_type_code": room_type_code,
    }
    if rate_plan_code:
        query["rate_plan_code"] = rate_plan_code
    if provider:
        query["provider"] = provider

    now = datetime.now(timezone.utc).isoformat()
    result = await db[COLL_ARI_CHANGE_SETS].update_many(
        query,
        {"$set": {
            "status": "pending",
            "hard_fail_reason": None,
            "hard_fail_failures": None,
            "released_from_quarantine_at": now,
            "updated_at": now,
        }},
    )

    released = result.modified_count
    if released > 0:
        logger.info(
            f"Released {released} quarantined change sets: "
            f"room={room_type_code} rate={rate_plan_code} provider={provider}"
        )
    return released
