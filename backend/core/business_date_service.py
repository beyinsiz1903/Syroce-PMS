"""Authoritative PMS business-date initialization and metadata helpers.

The calendar date is not a safe substitute for an uninitialized hotel business
date.  Older tenants may predate ``tenant_settings.business_date``; for those
tenants we establish the first open day from persisted operational evidence and
store the decision exactly once.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)

ACTIVE_ARRIVAL_STATUSES = ["confirmed", "guaranteed", "checked_in"]
COMPLETED_AUDIT_STATUSES = ["completed", "completed_with_exceptions"]


def _date_only(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or len(value.strip()) < 10:
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


async def _derive_initial_business_date(db, tenant_id: str, today: date) -> tuple[str, str]:
    """Return the safest first open date and a machine-readable reason."""
    latest_run = await db.night_audit_runs.find_one(
        {
            "tenant_id": tenant_id,
            "status": {"$in": COMPLETED_AUDIT_STATUSES},
        },
        {"_id": 0, "business_date": 1},
        sort=[("business_date", -1), ("completed_at", -1)],
    )
    last_closed = _date_only((latest_run or {}).get("business_date"))
    if last_closed is not None:
        # A stored successful close is authoritative. Never initialize beyond
        # today's calendar day if bad legacy data contains a future audit.
        next_open = min(last_closed + timedelta(days=1), today)
        return next_open.isoformat(), "night_audit_history"

    candidates = await db.bookings.find(
        {
            "tenant_id": tenant_id,
            "status": {"$in": ACTIVE_ARRIVAL_STATUSES},
        },
        {"_id": 0, "check_in": 1},
    ).to_list(5000)
    unresolved_dates = sorted(
        parsed
        for parsed in (_date_only(item.get("check_in")) for item in candidates)
        if parsed is not None and parsed <= today
    )
    if unresolved_dates:
        return unresolved_dates[0].isoformat(), "earliest_unresolved_arrival"

    return today.isoformat(), "first_operational_use"


def business_date_payload(settings: dict[str, Any]) -> dict[str, Any]:
    """Return the public business-date fields without leaking other settings."""
    update_source = settings.get("business_date_update_source")
    if settings.get("business_date") and not update_source:
        update_source = "legacy_record"
    return {
        "business_date": settings.get("business_date"),
        "previous_business_date": settings.get("previous_business_date"),
        "updated_at": settings.get("business_date_updated_at"),
        "initialized_at": settings.get("business_date_initialized_at"),
        "initialization_reason": settings.get("business_date_initialization_reason"),
        "update_source": update_source,
        "updated_by": settings.get("business_date_updated_by"),
        "audit_run_id": settings.get("business_date_audit_run_id"),
        "trigger_source": settings.get("business_date_trigger_source"),
        "is_initialized": bool(settings.get("business_date")),
    }


async def ensure_business_date_initialized(
    db,
    tenant_id: str,
    *,
    today: date | None = None,
    actor_id: str = "system_business_date_bootstrap",
) -> dict[str, Any]:
    """Load or safely initialize one tenant's authoritative business date.

    The compare-and-set filter prevents two simultaneous first requests from
    replacing an already established date.  A tenant-settings document may or
    may not already exist because several older modules created it lazily.
    """
    current = await db.tenant_settings.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if current and current.get("business_date"):
        return business_date_payload(current)

    today_value = today or datetime.now(UTC).date()
    initial_date, reason = await _derive_initial_business_date(db, tenant_id, today_value)
    now = datetime.now(UTC).isoformat()
    fields = {
        "business_date": initial_date,
        "previous_business_date": None,
        "business_date_initialized_at": now,
        "business_date_initialization_reason": reason,
        "business_date_updated_at": now,
        "business_date_update_source": "initialization",
        "business_date_updated_by": actor_id,
        "business_date_audit_run_id": None,
        "business_date_trigger_source": "bootstrap",
    }

    missing_date = {
        "$or": [
            {"$eq": [{"$type": "$business_date"}, "missing"]},
            {"$eq": ["$business_date", None]},
            {"$eq": ["$business_date", ""]},
        ]
    }
    # An aggregation-pipeline update makes initialization an atomic compare and
    # set. If a concurrent night audit establishes the date first, every field
    # below keeps the authoritative value already stored by that audit.
    conditional_fields = {
        key: {"$cond": [missing_date, value, f"${key}"]}
        for key, value in fields.items()
    }
    await db.tenant_settings.update_one(
        {"tenant_id": tenant_id},
        [
            {
                "$set": {
                    "tenant_id": {"$ifNull": ["$tenant_id", tenant_id]},
                    **conditional_fields,
                }
            }
        ],
        upsert=True,
    )

    stored = await db.tenant_settings.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if not stored or not stored.get("business_date"):
        raise RuntimeError(f"PMS business date could not be initialized for tenant {tenant_id}")

    logger.info(
        "Business date initialized tenant=%s date=%s reason=%s",
        tenant_id,
        stored["business_date"],
        stored.get("business_date_initialization_reason"),
    )
    return business_date_payload(stored)
