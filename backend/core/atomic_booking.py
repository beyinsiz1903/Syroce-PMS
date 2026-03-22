"""
Atomic Booking Creation — Overbooking Prevention
=================================================
Single entry point for ALL booking inserts.

Strategy: Room-Night Locking
  1. Parse check-in/check-out into a list of "night dates"
  2. Insert one lock document per night into `room_night_locks` (unique index)
  3. If any insert fails (DuplicateKeyError), the room is already booked → 409
  4. Insert the booking document
  5. On cancellation, remove the lock documents

The unique compound index on (tenant_id, room_id, night_date) makes
double-booking physically impossible, even under high concurrency.

Overlap rule:
  A booking for check_in=Jan 10 14:00, check_out=Jan 12 11:00
  claims nights: Jan 10, Jan 11 (NOT Jan 12 — guest departs that morning).

If room_id is None (unassigned OTA import), lock is skipped.
"""
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from pymongo.errors import DuplicateKeyError

from core.database import db

logger = logging.getLogger("core.atomic_booking")

ACTIVE_BOOKING_STATUSES = ["confirmed", "checked_in", "guaranteed"]


class BookingConflictError(Exception):
    """Raised when a booking conflicts with an existing reservation."""

    def __init__(self, message: str, conflicting_booking_id: Optional[str] = None):
        super().__init__(message)
        self.conflicting_booking_id = conflicting_booking_id


def _night_dates(check_in: str, check_out: str) -> List[str]:
    """Return list of night dates (YYYY-MM-DD) that a booking occupies."""
    ci = datetime.fromisoformat(check_in.replace("Z", "+00:00"))
    co = datetime.fromisoformat(check_out.replace("Z", "+00:00"))
    ci_date = ci.date()
    co_date = co.date()
    nights = []
    current = ci_date
    while current < co_date:
        nights.append(current.isoformat())
        current += timedelta(days=1)
    return nights


async def create_booking_atomic(booking_doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Atomically create a booking with room-night locking.

    1. Claim each night via unique-index insert into room_night_locks.
    2. If any night is already claimed → BookingConflictError (409).
    3. Insert the booking document.
    4. If booking insert fails → release all claimed nights.
    """
    tenant_id = booking_doc.get("tenant_id")
    room_id = booking_doc.get("room_id")
    check_in = booking_doc.get("check_in") or booking_doc.get("check_in_date")
    check_out = booking_doc.get("check_out") or booking_doc.get("check_out_date")
    booking_status = booking_doc.get("status", "confirmed")
    booking_id = booking_doc.get("id")

    # Cancelled/no-show bookings don't need conflict check
    if booking_status in ("cancelled", "no_show"):
        await db.bookings.insert_one(booking_doc)
        booking_doc.pop("_id", None)
        return booking_doc

    # Unassigned bookings (no room_id) skip conflict check
    if not room_id or not check_in or not check_out:
        await db.bookings.insert_one(booking_doc)
        booking_doc.pop("_id", None)
        return booking_doc

    nights = _night_dates(check_in, check_out)
    if not nights:
        await db.bookings.insert_one(booking_doc)
        booking_doc.pop("_id", None)
        return booking_doc

    # Phase 1: Claim each night
    claimed_nights: List[str] = []
    try:
        for night in nights:
            lock_doc = {
                "tenant_id": tenant_id,
                "room_id": room_id,
                "night_date": night,
                "booking_id": booking_id,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }
            try:
                await db.room_night_locks.insert_one(lock_doc)
                claimed_nights.append(night)
            except DuplicateKeyError:
                # Find which booking owns this night
                existing = await db.room_night_locks.find_one(
                    {"tenant_id": tenant_id, "room_id": room_id, "night_date": night},
                    {"_id": 0, "booking_id": 1},
                )
                conflicting_id = existing.get("booking_id") if existing else None
                # Release already claimed nights
                if claimed_nights:
                    await db.room_night_locks.delete_many({
                        "tenant_id": tenant_id,
                        "room_id": room_id,
                        "night_date": {"$in": claimed_nights},
                        "booking_id": booking_id,
                    })
                raise BookingConflictError(
                    f"Room not available for {check_in} to {check_out}. "
                    f"Night {night} already booked"
                    + (f" by {conflicting_id}" if conflicting_id else ""),
                    conflicting_booking_id=conflicting_id,
                )

        # Phase 2: Insert the booking
        await db.bookings.insert_one(booking_doc)

    except BookingConflictError:
        raise
    except Exception:
        # Rollback: release claimed nights on any failure
        if claimed_nights:
            await db.room_night_locks.delete_many({
                "tenant_id": tenant_id,
                "room_id": room_id,
                "night_date": {"$in": claimed_nights},
                "booking_id": booking_id,
            })
        raise

    booking_doc.pop("_id", None)
    logger.info(
        "Atomic booking created: %s room=%s %s->%s (%d nights locked)",
        booking_id, room_id, check_in, check_out, len(nights),
    )
    return booking_doc


async def release_booking_nights(tenant_id: str, booking_id: str) -> int:
    """Release room-night locks when a booking is cancelled/no-show."""
    result = await db.room_night_locks.delete_many({
        "tenant_id": tenant_id,
        "booking_id": booking_id,
    })
    deleted = result.deleted_count
    if deleted > 0:
        logger.info("Released %d night locks for booking %s", deleted, booking_id)
    return deleted


async def ensure_booking_indexes() -> None:
    """Create indexes for room-night locking and fast overlap detection."""
    indexes_to_create = [
        {
            "collection": "room_night_locks",
            "keys": [("tenant_id", 1), ("room_id", 1), ("night_date", 1)],
            "name": "ux_room_night",
            "unique": True,
        },
        {
            "collection": "room_night_locks",
            "keys": [("tenant_id", 1), ("booking_id", 1)],
            "name": "idx_lock_booking",
            "unique": False,
        },
        {
            "collection": "bookings",
            "keys": [("tenant_id", 1), ("room_id", 1), ("status", 1), ("check_in", 1), ("check_out", 1)],
            "name": "idx_booking_overlap_check",
            "unique": False,
        },
        {
            "collection": "bookings",
            "keys": [("tenant_id", 1), ("guest_id", 1)],
            "name": "idx_booking_tenant_guest",
            "unique": False,
        },
    ]
    for idx_def in indexes_to_create:
        coll = getattr(db, idx_def["collection"])
        try:
            await coll.create_index(
                idx_def["keys"],
                name=idx_def["name"],
                unique=idx_def.get("unique", False),
                background=True,
            )
        except Exception as e:
            if "IndexOptionsConflict" in str(e) or "already exists" in str(e):
                logger.info("Index %s already exists, skipping", idx_def["name"])
            else:
                logger.warning("Index creation failed for %s: %s", idx_def["name"], e)
    logger.info("Booking indexes ensured (room-night locking enabled)")
