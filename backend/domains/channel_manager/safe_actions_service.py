"""
Safe Actions Service — 1-Click Idempotent Operator Actions
============================================================

Each action follows the triple-guard pattern:
  1. Idempotency: Same action twice = no harm
  2. Pre-check: Validate conditions before executing
  3. Post-verification: Verify outcome after executing

Available Actions:
  - retry_safe: Retry failed (retryable) push change sets
  - release_quarantine: Safe release with mapping + staleness guard
  - revalidate_mapping: Full mapping validation with diff output
  - suppress_noise: Manual cooldown trigger for noisy notifications
"""
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from core.database import db
from domains.channel_manager.ari.hard_fail_gate import release_quarantine
from domains.channel_manager.ari.models import COLL_ARI_CHANGE_SETS
from domains.channel_manager.data_model import (
    COLL_RATE_PLAN_MAPPINGS,
    COLL_ROOM_MAPPINGS,
)
from domains.channel_manager.mapping_validator import (
    validate_rate_plan_mapping,
    validate_room_mapping,
)
from domains.channel_manager.quarantine_service import check_safe_release

logger = logging.getLogger("channel_manager.safe_actions")

_NO_ID = {"_id": 0}
COLL_ACTION_LOG = "operator_action_log"

RETRYABLE_STATUSES = {"failed", "provider_error", "timeout"}


async def retry_safe(tenant_id: str, operator_id: str = "system") -> Dict[str, Any]:
    """
    Retry failed push change sets that have retryable errors.

    Guards:
      - Only retries change sets with retryable status
      - Idempotent: re-running won't re-queue already pending items
      - Post-check: returns count of actually retried items
    """
    action_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    # Pre-check: find retryable change sets
    retryable = await db[COLL_ARI_CHANGE_SETS].find(
        {
            "tenant_id": tenant_id,
            "status": {"$in": list(RETRYABLE_STATUSES)},
        },
        _NO_ID,
    ).to_list(100)

    if not retryable:
        return _result(action_id, "retry_safe", "no_action",
                       "Yeniden denenecek basarisiz change set yok", 0,
                       tenant_id, operator_id)

    # Execute: move to pending for re-processing
    ids = [cs.get("id") for cs in retryable if cs.get("id")]
    result = await db[COLL_ARI_CHANGE_SETS].update_many(
        {"tenant_id": tenant_id, "id": {"$in": ids}, "status": {"$in": list(RETRYABLE_STATUSES)}},
        {"$set": {
            "status": "pending",
            "retry_requested_at": now,
            "retry_requested_by": operator_id,
            "updated_at": now,
        }},
    )
    retried = result.modified_count

    # Post-verify: confirm status change
    still_failed = await db[COLL_ARI_CHANGE_SETS].count_documents({
        "tenant_id": tenant_id,
        "id": {"$in": ids},
        "status": {"$in": list(RETRYABLE_STATUSES)},
    })

    await _log_action(action_id, "retry_safe", tenant_id, operator_id,
                      retried, {"attempted": len(ids), "still_failed": still_failed})

    return _result(action_id, "retry_safe", "completed",
                   f"{retried} change set yeniden deneme icin kuyruga alindi",
                   retried, tenant_id, operator_id,
                   post_verify={"still_failed": still_failed, "retried": retried})


async def safe_release_quarantine(
    tenant_id: str,
    room_type_code: str,
    rate_plan_code: Optional[str] = None,
    provider: Optional[str] = None,
    operator_id: str = "system",
) -> Dict[str, Any]:
    """
    Safe quarantine release with full guard chain.

    Guards:
      1. Pre-check: mapping validity + staleness
      2. Execute: release only if guards pass
      3. Post-verify: confirm items were actually released
    """
    action_id = str(uuid.uuid4())

    # Pre-check
    guard = await check_safe_release(tenant_id, room_type_code, rate_plan_code, provider)
    if not guard["safe_to_release"]:
        await _log_action(action_id, "release_quarantine", tenant_id, operator_id,
                          0, {"guard": guard, "blocked": True})
        return _result(action_id, "release_quarantine", "blocked",
                       f"Release engellendi: {guard['recommendation']}",
                       0, tenant_id, operator_id, pre_check=guard)

    # Execute
    released = await release_quarantine(tenant_id, room_type_code, rate_plan_code, provider)

    # Post-verify: check that items are now pending
    still_quarantined = await db[COLL_ARI_CHANGE_SETS].count_documents({
        "tenant_id": tenant_id,
        "status": "hard_fail",
        "room_type_code": room_type_code,
    })

    await _log_action(action_id, "release_quarantine", tenant_id, operator_id,
                      released, {"guard": guard, "still_quarantined": still_quarantined})

    return _result(action_id, "release_quarantine", "completed",
                   f"{released} item karantinadan serbest birakildi",
                   released, tenant_id, operator_id,
                   pre_check=guard,
                   post_verify={"released": released, "still_quarantined": still_quarantined})


async def revalidate_mapping(
    tenant_id: str,
    provider: Optional[str] = None,
    operator_id: str = "system",
) -> Dict[str, Any]:
    """
    Full mapping revalidation with diff output.

    Guards:
      - Idempotent: revalidation is read-only check
      - Returns detailed diff of valid vs broken mappings
    """
    action_id = str(uuid.uuid4())
    providers = [provider] if provider else ["exely", "hotelrunner"]
    results = {}

    for prov in providers:
        rooms = await db[COLL_ROOM_MAPPINGS].find(
            {"tenant_id": tenant_id, "provider": prov}, _NO_ID,
        ).to_list(500)
        rates = await db[COLL_RATE_PLAN_MAPPINGS].find(
            {"tenant_id": tenant_id, "provider": prov}, _NO_ID,
        ).to_list(500)

        room_issues = []
        for m in rooms:
            code = m.get("provider_room_code", "")
            err = validate_room_mapping(m, code)
            if err:
                room_issues.append({
                    "code": code,
                    "failure_type": err.failure_type.value,
                    "reason": err.reason,
                    "action": err.operator_action,
                })

        rate_issues = []
        for m in rates:
            code = m.get("provider_rate_code", "")
            err = validate_rate_plan_mapping(m, code)
            if err:
                rate_issues.append({
                    "code": code,
                    "failure_type": err.failure_type.value,
                    "reason": err.reason,
                    "action": err.operator_action,
                })

        results[prov] = {
            "room_total": len(rooms),
            "room_valid": len(rooms) - len(room_issues),
            "room_issues": room_issues,
            "rate_total": len(rates),
            "rate_valid": len(rates) - len(rate_issues),
            "rate_issues": rate_issues,
            "is_complete": len(room_issues) == 0 and len(rate_issues) == 0,
        }

    all_complete = all(r["is_complete"] for r in results.values())
    total_issues = sum(len(r["room_issues"]) + len(r["rate_issues"]) for r in results.values())

    await _log_action(action_id, "revalidate_mapping", tenant_id, operator_id,
                      total_issues, {"results": {k: {"issues": len(v["room_issues"]) + len(v["rate_issues"])} for k, v in results.items()}})

    return _result(action_id, "revalidate_mapping",
                   "completed" if all_complete else "issues_found",
                   f"Mapping dogrulama tamamlandi: {'Tum mapping gecerli' if all_complete else f'{total_issues} sorun bulundu'}",
                   total_issues, tenant_id, operator_id,
                   post_verify={"by_provider": results, "all_complete": all_complete})


async def suppress_noise(
    tenant_id: str,
    event_type: Optional[str] = None,
    duration_minutes: int = 30,
    operator_id: str = "system",
) -> Dict[str, Any]:
    """
    Suppress noisy notifications by setting manual cooldown.

    Guards:
      - Idempotent: extending suppression just updates the timer
      - Limited duration: max 120 minutes
    """
    action_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    duration_minutes = min(duration_minutes, 120)
    expires_at = (now + timedelta(minutes=duration_minutes)).isoformat()

    suppression = {
        "tenant_id": tenant_id,
        "event_type": event_type or "*",
        "suppressed_by": operator_id,
        "suppressed_at": now.isoformat(),
        "expires_at": expires_at,
        "duration_minutes": duration_minutes,
    }

    # Upsert: idempotent — re-suppressing just extends
    await db["notification_suppressions"].update_one(
        {"tenant_id": tenant_id, "event_type": event_type or "*"},
        {"$set": suppression},
        upsert=True,
    )

    await _log_action(action_id, "suppress_noise", tenant_id, operator_id,
                      1, {"event_type": event_type, "duration_minutes": duration_minutes})

    return _result(action_id, "suppress_noise", "completed",
                   f"Bildirimler {duration_minutes} dakika susturuldu"
                   + (f" (tip: {event_type})" if event_type else " (tum tipler)"),
                   1, tenant_id, operator_id,
                   post_verify={"expires_at": expires_at})


def _result(
    action_id: str, action_type: str, status: str, message: str,
    affected: int, tenant_id: str, operator_id: str,
    pre_check: Dict = None, post_verify: Dict = None,
) -> Dict[str, Any]:
    return {
        "action_id": action_id,
        "action_type": action_type,
        "status": status,
        "message": message,
        "affected_count": affected,
        "tenant_id": tenant_id,
        "operator_id": operator_id,
        "pre_check": pre_check,
        "post_verify": post_verify,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }


async def _log_action(
    action_id: str, action_type: str, tenant_id: str,
    operator_id: str, affected: int, details: Dict,
) -> None:
    await db[COLL_ACTION_LOG].insert_one({
        "id": action_id,
        "action_type": action_type,
        "tenant_id": tenant_id,
        "operator_id": operator_id,
        "affected_count": affected,
        "details": details,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })
