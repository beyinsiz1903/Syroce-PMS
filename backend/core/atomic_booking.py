"""
Atomic Booking Creation — Overbooking Prevention
=================================================
Single entry point for ALL booking inserts.

Uses MongoDB transactions with snapshot isolation to guarantee:
  1. Check for overlapping bookings (same room, same dates)
  2. Insert only if no conflict
  3. All-or-nothing: commit or abort

Overlap rule:
  Two bookings conflict when:
    new.check_in < existing.check_out  AND  new.check_out > existing.check_in

If room_id is None (unassigned OTA import), conflict check is skipped.
"""
import logging
from typing import Any, Dict, Optional

from pymongo import ReadPreference
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from core.database import client, db

logger = logging.getLogger("core.atomic_booking")

ACTIVE_BOOKING_STATUSES = ["confirmed", "checked_in", "guaranteed"]


class BookingConflictError(Exception):
    """Raised when a booking conflicts with an existing reservation."""

    def __init__(self, message: str, conflicting_booking_id: Optional[str] = None):
        super().__init__(message)
        self.conflicting_booking_id = conflicting_booking_id


async def create_booking_atomic(booking_doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Atomically create a booking with overlap prevention using MongoDB transaction.

    Args:
        booking_doc: Complete booking document to insert.

    Returns:
        The inserted booking document (without _id).

    Raises:
        BookingConflictError: If an overlapping booking exists for the same room.
    """
    tenant_id = booking_doc.get("tenant_id")
    room_id = booking_doc.get("room_id")
    check_in = booking_doc.get("check_in") or booking_doc.get("check_in_date")
    check_out = booking_doc.get("check_out") or booking_doc.get("check_out_date")
    booking_status = booking_doc.get("status", "confirmed")

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

    # Exclude current booking id from conflict check (for upsert-like operations)
    booking_id = booking_doc.get("id")

    async with await client.start_session() as session:
        async with session.start_transaction(
            read_concern=ReadConcern("snapshot"),
            write_concern=WriteConcern("majority"),
            read_preference=ReadPreference.PRIMARY,
        ):
            # Build conflict query
            conflict_query = {
                "tenant_id": tenant_id,
                "room_id": room_id,
                "status": {"$in": ACTIVE_BOOKING_STATUSES},
                "check_in": {"$lt": check_out},
                "check_out": {"$gt": check_in},
            }
            if booking_id:
                conflict_query["id"] = {"$ne": booking_id}

            conflict = await db.bookings.find_one(
                conflict_query,
                {"_id": 0, "id": 1, "check_in": 1, "check_out": 1, "status": 1},
                session=session,
            )

            if conflict:
                raise BookingConflictError(
                    f"Room not available for {check_in} to {check_out}. "
                    f"Conflicting booking: {conflict.get('id')} "
                    f"({conflict.get('check_in')} - {conflict.get('check_out')})",
                    conflicting_booking_id=conflict.get("id"),
                )

            await db.bookings.insert_one(booking_doc, session=session)

    booking_doc.pop("_id", None)
    logger.info(
        "Atomic booking created: %s room=%s %s→%s",
        booking_doc.get("id"), room_id, check_in, check_out,
    )
    return booking_doc


async def ensure_booking_indexes() -> None:
    """Create compound indexes for fast overlap detection. Handles pre-existing indexes."""
    indexes_to_create = [
        {
            "keys": [("tenant_id", 1), ("room_id", 1), ("status", 1), ("check_in", 1), ("check_out", 1)],
            "name": "idx_booking_overlap_check",
        },
        {
            "keys": [("tenant_id", 1), ("guest_id", 1)],
            "name": "idx_booking_tenant_guest",
        },
    ]
    for idx_def in indexes_to_create:
        try:
            await db.bookings.create_index(
                idx_def["keys"], name=idx_def["name"], background=True,
            )
        except Exception as e:
            if "IndexOptionsConflict" in str(e) or "already exists" in str(e):
                logger.info("Index %s already exists (possibly under different name), skipping", idx_def["name"])
            else:
                logger.warning("Index creation failed for %s: %s", idx_def["name"], e)
    logger.info("Booking indexes ensured")
