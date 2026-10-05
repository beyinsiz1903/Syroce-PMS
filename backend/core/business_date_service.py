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
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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


def _local_calendar_date(timezone_name: str, *, now: datetime | None = None) -> date:
    """Resolve a wall-clock instant to the hotel's local calendar date."""
    try:
        tenant_timezone = ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError, KeyError, OSError):
        logger.warning("Invalid tenant timezone timezone=%s; using Europe/Istanbul", timezone_name)
        tenant_timezone = ZoneInfo("Europe/Istanbul")
    reference = now or datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    return reference.astimezone(tenant_timezone).date()


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
    unresolved_dates = sorted(parsed for parsed in (_date_only(item.get("check_in")) for item in candidates) if parsed is not None and parsed <= today)
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

    timezone_name = str((current or {}).get("timezone") or "Europe/Istanbul")
    today_value = today or _local_calendar_date(timezone_name)
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
    conditional_fields = {key: {"$cond": [missing_date, value, f"${key}"]} for key, value in fields.items()}
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


async def stamp_open_business_date(db, tenant_id: str, document: dict[str, Any]) -> str:
    """Attach the hotel's open PMS day to a newly-created financial record.

    Wall-clock timestamps remain the immutable event time, while
    ``business_date`` is the accounting day.  They intentionally diverge when
    reception keeps working after midnight before night audit is completed.
    An explicit business date (for example a night-audit room charge) is
    preserved.
    """
    explicit = _date_only(document.get("business_date"))
    if explicit is not None:
        document["business_date"] = explicit.isoformat()
        return document["business_date"]

    state = await ensure_business_date_initialized(db, tenant_id)
    resolved = _date_only(state.get("business_date"))
    if resolved is None:
        raise RuntimeError(f"PMS business date is invalid for tenant {tenant_id}")
    document["business_date"] = resolved.isoformat()
    return document["business_date"]


def accounting_day_match(business_date: str, *legacy_date_clauses: dict[str, Any]) -> dict[str, Any]:
    """Match an accounting day without double-classifying modern records.

    Timestamp/date fallbacks are only allowed for legacy documents that do not
    yet carry ``business_date``.  A modern record posted after midnight must
    therefore stay on its open PMS day and cannot also appear on the following
    calendar day.
    """
    missing_business_date = {
        "$or": [
            {"business_date": {"$exists": False}},
            {"business_date": None},
            {"business_date": ""},
        ]
    }
    clauses: list[dict[str, Any]] = [{"business_date": str(business_date)[:10]}]
    if legacy_date_clauses:
        clauses.append(
            {
                "$and": [
                    missing_business_date,
                    {"$or": list(legacy_date_clauses)},
                ]
            }
        )
    return {"$or": clauses}


def accounting_period_match(
    start_business_date: str,
    end_business_date: str,
    *legacy_date_clauses: dict[str, Any],
) -> dict[str, Any]:
    """Match an inclusive PMS-day range with legacy timestamp fallbacks."""
    missing_business_date = {
        "$or": [
            {"business_date": {"$exists": False}},
            {"business_date": None},
            {"business_date": ""},
        ]
    }
    clauses: list[dict[str, Any]] = [
        {
            "business_date": {
                "$gte": str(start_business_date)[:10],
                "$lte": str(end_business_date)[:10],
            }
        }
    ]
    if legacy_date_clauses:
        clauses.append({"$and": [missing_business_date, {"$or": list(legacy_date_clauses)}]})
    return {"$or": clauses}
