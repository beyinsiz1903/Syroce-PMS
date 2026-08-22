"""Safe room auto-assignment for inbound OTA reservations.

The provider sells room-type inventory, while the PMS calendar needs a
physical room.  This module finds eligible physical rooms and lets the atomic
booking core make the final (race-safe) claim.  It never writes back to a
provider.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from core.atomic_booking import (
    BookingConflictError,
    assert_pending_assignment,
)

UNSELLABLE_ROOM_STATUSES = {
    "maintenance",
    "out_of_order",
    "out_of_service",
    "blocked",
    "inactive",
}
TERMINAL_BOOKING_STATUSES = ("cancelled", "no_show", "checked_out")


def normalize_room_type(value: Any) -> str:
    """Normalize provider/PMS labels without changing the stored display name."""
    text = str(value or "").strip().replace("ı", "i").replace("İ", "I")
    decomposed = unicodedata.normalize("NFKD", text)
    ascii_like = "".join(char for char in decomposed if not unicodedata.combining(char))
    return " ".join(ascii_like.casefold().split())


def _natural_room_key(room: dict[str, Any]) -> tuple[Any, ...]:
    number = str(room.get("room_number") or room.get("name") or room.get("id") or "")
    return tuple(int(part) if part.isdigit() else part.casefold() for part in re.split(r"(\d+)", number))


def _room_matches_property(room: dict[str, Any], property_id: str | None) -> bool:
    """Keep legacy rooms (without property_id) while isolating explicit properties."""
    room_property = room.get("property_id")
    return not property_id or not room_property or str(room_property) == str(property_id)


async def find_auto_assignment_candidates(
    *,
    database: Any,
    tenant_id: str,
    property_id: str | None,
    room_type: str,
    check_in: str,
    check_out: str,
) -> list[dict[str, Any]]:
    """Return naturally ordered rooms that are sellable for the full stay.

    Bookings, explicit room blocks, and room-night locks are all consulted.
    The atomic creator still performs the final claim to close concurrency
    races between this read and the booking insert.
    """
    normalized_type = normalize_room_type(room_type)
    if not normalized_type or not check_in or not check_out:
        return []

    rooms = await database.rooms.find(
        {"tenant_id": tenant_id, "is_active": {"$ne": False}},
        {
            "_id": 0,
            "id": 1,
            "room_number": 1,
            "name": 1,
            "room_type": 1,
            "property_id": 1,
            "status": 1,
            "is_active": 1,
        },
    ).to_list(2000)

    eligible = [
        room
        for room in rooms
        if room.get("id")
        and _room_matches_property(room, property_id)
        and normalize_room_type(room.get("room_type")) == normalized_type
        and str(room.get("status") or "available").strip().casefold() not in UNSELLABLE_ROOM_STATUSES
    ]
    if not eligible:
        return []

    room_ids = [room["id"] for room in eligible]
    bookings = await database.bookings.find(
        {
            "tenant_id": tenant_id,
            "room_id": {"$in": room_ids},
            "status": {"$nin": list(TERMINAL_BOOKING_STATUSES)},
            "check_in": {"$lt": check_out},
            "check_out": {"$gt": check_in},
        },
        {"_id": 0, "room_id": 1},
    ).to_list(5000)
    unavailable_ids = {booking.get("room_id") for booking in bookings}

    blocks = await database.room_blocks.find(
        {
            "tenant_id": tenant_id,
            "room_id": {"$in": room_ids},
            "status": "active",
            "start_date": {"$lt": check_out},
            "$or": [{"end_date": {"$gt": check_in}}, {"end_date": None}],
        },
        {"_id": 0, "room_id": 1, "allow_sell": 1},
    ).to_list(5000)
    unavailable_ids.update(block.get("room_id") for block in blocks if not block.get("allow_sell", False))

    # The lock table is the authoritative oversell barrier and also contains
    # OOO/OOS/maintenance locks. Date-only comparison matches its schema.
    lock_start = str(check_in)[:10]
    lock_end = str(check_out)[:10]
    locks = await database.room_night_locks.find(
        {
            "tenant_id": tenant_id,
            "room_id": {"$in": room_ids},
            "night_date": {"$gte": lock_start, "$lt": lock_end},
        },
        {"_id": 0, "room_id": 1},
    ).to_list(10000)
    unavailable_ids.update(lock.get("room_id") for lock in locks)

    return sorted(
        [room for room in eligible if room["id"] not in unavailable_ids],
        key=_natural_room_key,
    )


async def create_booking_with_auto_assignment(
    *,
    database: Any,
    tenant_id: str,
    booking_doc: dict[str, Any],
    create_booking: Callable[..., Awaitable[dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Atomically create an OTA booking in the first available physical room.

    Concurrent conflicts try the next candidate. If no physical room remains,
    the reservation is retained as pending assignment so front desk can place
    or move it manually without losing the provider reservation.
    """
    candidates = await find_auto_assignment_candidates(
        database=database,
        tenant_id=tenant_id,
        property_id=booking_doc.get("property_id"),
        room_type=booking_doc.get("room_type") or booking_doc.get("room_type_id") or "",
        check_in=booking_doc.get("check_in") or booking_doc.get("check_in_date") or "",
        check_out=booking_doc.get("check_out") or booking_doc.get("check_out_date") or "",
    )

    conflict_count = 0
    for room in candidates:
        assigned = dict(booking_doc)
        assigned["room_id"] = room["id"]
        assigned["room_number"] = room.get("room_number") or room.get("name") or ""
        assigned["allocation_source"] = "ota_auto_assignment"
        assigned["auto_assigned_at"] = datetime.now(UTC).isoformat()
        try:
            created = await create_booking(tenant_id=tenant_id, booking_doc=assigned)
            return created, room
        except BookingConflictError:
            # A second import may have claimed this room after the availability
            # read. The atomic creator compensated its partial locks; continue.
            conflict_count += 1

    pending = dict(booking_doc)
    pending["room_id"] = None
    pending.pop("room_number", None)
    pending["allocation_source"] = "pending_assignment"
    pending["auto_assignment_reason"] = "concurrent_room_conflict" if conflict_count else "no_available_room"
    assert_pending_assignment(pending)
    created = await create_booking(tenant_id=tenant_id, booking_doc=pending)
    return created, None
