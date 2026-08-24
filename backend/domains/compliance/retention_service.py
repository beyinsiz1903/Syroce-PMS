"""Bounded GDPR retention enforcement for guest PII.

Financial booking records are preserved. Only the guest master PII is scrubbed,
and only when no booking newer than the tenant cutoff exists.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any

GUEST_PII_FIELDS = (
    "full_name",
    "name",
    "first_name",
    "last_name",
    "email",
    "phone",
    "address",
    "passport_number",
    "id_number",
    "birth_date",
    "date_of_birth",
    "nationality",
    "gender",
    "contact_email",
    "contact_phone",
)


def anonymization_runtime_enabled() -> bool:
    return os.environ.get("ENABLE_GUEST_ANONYMIZATION", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


async def enforce_guest_retention(
    db: Any,
    *,
    tenant_id: str,
    retention_days: int,
    dry_run: bool = True,
    limit: int = 500,
    actor_id: str = "gdpr-retention-worker",
    now: datetime | None = None,
) -> dict[str, Any]:
    """Preview or anonymize a bounded set of guests past the retention window."""
    if retention_days < 30 or retention_days > 3650:
        raise ValueError("retention_days 30-3650 aralığında olmalıdır")
    if limit < 1 or limit > 2000:
        raise ValueError("limit 1-2000 aralığında olmalıdır")
    if not dry_run and not anonymization_runtime_enabled():
        raise RuntimeError("Guest anonymization runtime flag is disabled")

    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=retention_days)
    cutoff_iso = cutoff.isoformat()
    booking_query = {
        "tenant_id": tenant_id,
        "guest_id": {"$nin": [None, ""]},
        "status": {"$in": ["checked_out", "completed", "closed"]},
        "$or": [
            {"check_out": {"$lte": cutoff_iso}},
            {"check_out_date": {"$lte": cutoff_iso}},
        ],
    }
    old_stays = await db.bookings.find(
        booking_query,
        {"_id": 0, "guest_id": 1},
    ).sort("check_out", 1).limit(limit * 4).to_list(limit * 4)
    candidate_ids = list(dict.fromkeys(row.get("guest_id") for row in old_stays if row.get("guest_id")))[:limit]

    eligible_ids: list[str] = []
    skipped_recent = 0
    for guest_id in candidate_ids:
        recent = await db.bookings.find_one(
            {
                "tenant_id": tenant_id,
                "guest_id": guest_id,
                "status": {"$nin": ["cancelled", "no_show"]},
                "$or": [
                    {"check_out": {"$gt": cutoff_iso}},
                    {"check_out_date": {"$gt": cutoff_iso}},
                ],
            },
            {"_id": 1},
        )
        if recent:
            skipped_recent += 1
            continue
        guest = await db.guests.find_one(
            {
                "tenant_id": tenant_id,
                "id": guest_id,
                "anonymized": {"$ne": True},
                "is_anonymized": {"$ne": True},
            },
            {"_id": 0, "id": 1},
        )
        if guest:
            eligible_ids.append(guest_id)

    anonymized = 0
    if not dry_run:
        scrub = dict.fromkeys(GUEST_PII_FIELDS)
        scrub.update(
            {
                "full_name": "ANONYMIZED",
                "anonymized": True,
                "anonymized_at": now.isoformat(),
                "anonymized_by": actor_id,
            }
        )
        for guest_id in eligible_ids:
            result = await db.guests.update_one(
                {"tenant_id": tenant_id, "id": guest_id, "anonymized": {"$ne": True}},
                {"$set": scrub},
            )
            if result.modified_count:
                anonymized += 1
                await db.gdpr_requests.insert_one(
                    {
                        "tenant_id": tenant_id,
                        "guest_id": guest_id,
                        "type": "retention_anonymization",
                        "status": "completed",
                        "created_at": now.isoformat(),
                        "requested_by": actor_id,
                        "retention_days": retention_days,
                        "cutoff": cutoff_iso,
                    }
                )

    return {
        "tenant_id": tenant_id,
        "dry_run": dry_run,
        "retention_days": retention_days,
        "cutoff": cutoff_iso,
        "candidate_count": len(candidate_ids),
        "eligible_count": len(eligible_ids),
        "skipped_recent": skipped_recent,
        "anonymized_count": anonymized,
        "has_more": len(candidate_ids) >= limit,
    }
