"""Write-time agency allotment guard.

Search and booking check the agency allotment before the insert, but two
concurrent requests can both pass that check and together exceed it. The room
night locks only stop two bookings on the *same room*; they do not cap how many
rooms one agency takes from its allotment.

After the booking is committed atomically we count again, including the new
booking. If an allotment night is now over its cap, the new booking is rolled
back and the agency gets a 409. Concurrent losers may both roll back (a safe
false negative that a retry resolves); the allotment is never exceeded, and
no separate counter has to be kept in sync with cancellations or changes.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta

from core.stay_overlap import stay_overlap_filter

logger = logging.getLogger("core.agency_allotment")

ACTIVE_STATUSES = ["confirmed", "guaranteed", "checked_in", "pending"]


def _nights(check_in: str, check_out: str) -> list[str]:
    start, end = date.fromisoformat(check_in[:10]), date.fromisoformat(check_out[:10])
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days)]


async def marketplace_allotment_overrun(
    database, *, tenant_id: str, agency_id: str, room_type: str, rate_plan_code: str | None,
    check_in: str, check_out: str,
) -> str | None:
    """Return the first night whose shared agency availability is now exceeded."""
    nights = _nights(check_in, check_out)
    plan_filter = (
        {"rate_plan_code": {"$exists": False}} if rate_plan_code in (None, "LEGACY") else {"rate_plan_code": rate_plan_code}
    )
    rows = await database.agency_rate_calendar.find(
        {"tenant_id": tenant_id, "agency_id": agency_id, "room_type_code": room_type, "date": {"$in": nights}, **plan_filter},
        {"_id": 0, "date": 1, "availability": 1},
    ).to_list(len(nights) * 4 or 1)
    for row in sorted(rows, key=lambda r: r.get("date", "")):
        if row.get("availability") is None:
            continue
        night = row["date"]
        following = (date.fromisoformat(night) + timedelta(days=1)).isoformat()
        used = await database.bookings.count_documents({
            "tenant_id": tenant_id, "agency_id": agency_id, "room_type": room_type,
            "$or": [{"rate_plan_code": rate_plan_code}, {"rate_plan_code": {"$exists": False}}],
            "status": {"$in": ACTIVE_STATUSES},
            **stay_overlap_filter(night, following),
        })
        if used > int(row["availability"]):
            return night
    return None


async def legacy_allotment_overrun(
    database, *, tenant_id: str, agency_id: str, room_ids: list[str], allotment_count: int,
    check_in: str, check_out: str,
) -> bool:
    """Legacy portal allotments cap overlapping agency bookings for the stay."""
    used = await database.bookings.count_documents({
        "tenant_id": tenant_id, "agency_id": agency_id, "room_id": {"$in": room_ids},
        "status": {"$in": ACTIVE_STATUSES},
        **stay_overlap_filter(check_in, check_out),
    })
    return used > allotment_count


async def rollback_oversold_booking(database, *, tenant_id: str, booking_id: str) -> None:
    """Cancel the just-created booking and free its room nights."""
    now = datetime.now(UTC).isoformat()
    await database.bookings.update_one(
        {"id": booking_id, "tenant_id": tenant_id},
        {"$set": {
            "status": "cancelled",
            "cancellation_reason": "agency_allotment_exceeded",
            "cancelled_at": now,
            "updated_at": now,
            # The durable completion worker must not publish a booking that
            # never became a sale.
            "agency_completion.status": "aborted",
        }},
    )
    try:
        from core.atomic_booking import release_booking_nights

        await release_booking_nights(tenant_id, booking_id, reason="agency_allotment_exceeded")
    except Exception as exc:  # noqa: BLE001 - booking is already cancelled
        logger.warning("Allotment rollback lock release failed booking=%s error=%s", booking_id, type(exc).__name__)
