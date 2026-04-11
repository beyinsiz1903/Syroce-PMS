"""
Cross-Provider Reconciliation — Auto-Resolution Rules
=======================================================

Safe auto-resolution:
  - missing_reservation  → import reservation (auto-resolve)
  - duplicate_event      → merge (auto-resolve)
  - stale_event          → ignore (auto-resolve)

Manual review required (DO NOT auto-resolve):
  - amount_mismatch
  - date_conflict
  - status_conflict
"""
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("reconciliation.auto_resolver")

# Case types that can be safely auto-resolved
SAFE_AUTO_RESOLVE = {
    "missing_reservation": ("auto_import", "Reservation imported from provider"),
    "duplicate_event": ("auto_merge", "Duplicate event merged"),
    "stale_event": ("auto_ignore", "Stale event ignored"),
    "duplicate_reservation": ("auto_merge", "Duplicate reservation flagged for merge"),
}

# Case types that MUST go to manual review
MANUAL_REVIEW_REQUIRED = {
    "amount_mismatch",
    "date_conflict",
    "status_conflict",
}


def can_auto_resolve(case_type: str) -> bool:
    """Check if a case type is eligible for auto-resolution."""
    return case_type in SAFE_AUTO_RESOLVE


def get_auto_resolution(case_type: str) -> tuple[str, str] | None:
    """
    Returns (resolution_action, resolution_note) for auto-resolvable cases.
    Returns None if manual review is required.
    """
    return SAFE_AUTO_RESOLVE.get(case_type)


def attempt_auto_resolve(case: dict[str, Any]) -> dict[str, Any] | None:
    """
    Attempt auto-resolution for a case.
    Returns update dict if resolvable, None otherwise.
    """
    case_type = case.get("case_type", "")

    if case_type in MANUAL_REVIEW_REQUIRED:
        return None

    resolution = get_auto_resolution(case_type)
    if not resolution:
        return None

    action, note = resolution
    now = datetime.now(UTC).isoformat()

    logger.info(
        f"Auto-resolving case {case.get('id','?')}: "
        f"type={case_type}, action={action}"
    )

    return {
        "status": "resolved",
        "resolution": f"[AUTO] {action}: {note}",
        "resolved_by": "system:reconciliation_engine",
        "resolved_at": now,
    }
