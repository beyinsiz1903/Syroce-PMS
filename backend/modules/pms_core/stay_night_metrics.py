"""Canonical room-night metrics used by PMS dashboards and reports."""

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

OCCUPYING_STATUSES = frozenset({"confirmed", "guaranteed", "checked_in", "in_house", "checked_out"})
ACTUAL_OCCUPANCY_STATUSES = frozenset({"checked_in", "in_house", "checked_out"})
NON_COMMERCIAL_STATUSES = frozenset({"cancelled", "canceled", "no_show", "noshow"})


def as_date(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


# Backward-compatible private alias for existing callers.
_as_date = as_date


def booking_occupies_night(booking: dict, day: date, *, actual_only: bool = False) -> bool:
    """Return whether one booking occupies ``day`` as a hotel room-night.

    Hotel stays are half-open intervals: arrival is included and departure is
    excluded.  ``actual_only`` additionally requires an actual in-house status
    and respects early check-out / late check-in timestamps.  This prevents a
    historical confirmed/no-show reservation from becoming realised occupancy.
    """
    status = str(booking.get("status") or "").strip().lower()
    allowed = ACTUAL_OCCUPANCY_STATUSES if actual_only else OCCUPYING_STATUSES
    if status not in allowed:
        return False
    check_in = as_date(booking.get("check_in"))
    check_out = as_date(booking.get("check_out"))
    if not check_in or not check_out or not (check_in <= day < check_out):
        return False
    if actual_only:
        actual_in = as_date(booking.get("checked_in_at"))
        actual_out = as_date(booking.get("checked_out_at"))
        if actual_in and day < actual_in:
            return False
        if actual_out and day >= actual_out:
            return False
    return True


def booking_nights(booking: dict) -> int:
    check_in = as_date(booking.get("check_in"))
    check_out = as_date(booking.get("check_out"))
    if not check_in or not check_out or check_out <= check_in:
        return 0
    return (check_out - check_in).days


def allocated_revenue_for_night(booking: dict, day: date) -> Decimal:
    """Evenly allocate a reservation total over its booked nights."""
    nights = booking_nights(booking)
    if not nights or not booking_occupies_night(booking, day):
        return Decimal("0")
    return _money(booking.get("total_amount")) / nights


def _money(value) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _room_key(booking: dict) -> str | None:
    room_id = booking.get("room_id")
    if room_id:
        return f"id:{room_id}"
    room_number = booking.get("room_number")
    if room_number:
        return f"number:{room_number}"
    return None


def calculate_stay_night_metrics(
    bookings: list[dict],
    rooms: list[dict],
    start_date: date,
    end_date: date,
    *,
    actual_only: bool = False,
    room_blocks: list[dict] | None = None,
) -> list[dict]:
    """Return inclusive daily metrics using ``check_in <= day < check_out``.

    Occupancy is the number of unique assigned rooms. Gross reservation totals
    are allocated evenly over their stay nights, so they are never repeated on
    every day. Inactive rooms are excluded from capacity.
    """
    active_rooms = [room for room in rooms if room.get("is_active") is not False]
    active_room_keys = {
        f"id:{room.get('id')}" if room.get("id") else f"number:{room.get('room_number')}"
        for room in active_rooms
        if room.get("id") or room.get("room_number")
    }
    days = (end_date - start_date).days + 1
    result = []

    parsed = []
    for booking in bookings:
        status = str(booking.get("status") or "").strip().lower()
        allowed = ACTUAL_OCCUPANCY_STATUSES if actual_only else OCCUPYING_STATUSES
        if status not in allowed:
            continue
        check_in = as_date(booking.get("check_in"))
        check_out = as_date(booking.get("check_out"))
        room_key = _room_key(booking)
        if not check_in or not check_out or check_out <= check_in or not room_key:
            continue
        nights = (check_out - check_in).days
        parsed.append(
            (
                check_in,
                check_out,
                as_date(booking.get("checked_in_at")),
                as_date(booking.get("checked_out_at")),
                room_key,
                _money(booking.get("total_amount")) / nights,
            )
        )

    for offset in range(max(days, 0)):
        day = start_date + timedelta(days=offset)
        blocked_room_keys = set()
        for block in room_blocks or []:
            if block.get("allow_sell", False) or str(block.get("status") or "active").lower() != "active":
                continue
            block_start = as_date(block.get("start_date"))
            block_end = as_date(block.get("end_date"))
            if block_start and block_start <= day and (not block_end or day < block_end):
                room_id = block.get("room_id")
                if room_id:
                    blocked_room_keys.add(f"id:{room_id}")
        total_rooms = len(active_room_keys - blocked_room_keys)
        occupied_rooms: set[str] = set()
        revenue = Decimal("0")
        for check_in, check_out, actual_in, actual_out, room_key, nightly_revenue in parsed:
            actual_window_ok = not actual_only or ((not actual_in or actual_in <= day) and (not actual_out or day < actual_out))
            if check_in <= day < check_out and actual_window_ok:
                occupied_rooms.add(room_key)
                revenue += nightly_revenue
        occupied = len(occupied_rooms)
        revenue_value = round(float(revenue), 2)
        occupancy_rate = round(min((occupied / total_rooms * 100), 100.0), 2) if total_rooms else 0
        adr = round(revenue_value / occupied, 2) if occupied else 0
        revpar = round(revenue_value / total_rooms, 2) if total_rooms else 0
        result.append(
            {
                "date": day.isoformat(),
                "occupied_rooms": occupied,
                "total_rooms": total_rooms,
                "occupancy_rate": occupancy_rate,
                "revenue": revenue_value,
                "adr": adr,
                "revpar": revpar,
            }
        )
    return result


async def load_stay_night_metrics(db, tenant_id: str, start_date: date, end_date: date, *, actual_only: bool = False) -> list[dict]:
    """Load the minimum shared dataset and calculate canonical metrics."""
    rooms = await db.rooms.find(
        {"tenant_id": tenant_id, "is_active": {"$ne": False}},
        {"_id": 0, "id": 1, "room_number": 1, "is_active": 1},
    ).to_list(5000)
    bookings = await db.bookings.find(
        {
            "tenant_id": tenant_id,
            "status": {"$in": list(OCCUPYING_STATUSES)},
            "check_out": {"$gt": start_date.isoformat()},
            "check_in": {"$lt": (end_date + timedelta(days=1)).isoformat()},
        },
        {
            "_id": 0,
            "room_id": 1,
            "room_number": 1,
            "check_in": 1,
            "check_out": 1,
            "status": 1,
            "total_amount": 1,
            "checked_in_at": 1,
            "checked_out_at": 1,
        },
    ).to_list(10000)
    room_blocks = await db.room_blocks.find(
        {
            "tenant_id": tenant_id,
            "status": "active",
            "allow_sell": {"$ne": True},
            "start_date": {"$lt": (end_date + timedelta(days=1)).isoformat()},
            "$or": [{"end_date": {"$gt": start_date.isoformat()}}, {"end_date": None}],
        },
        {"_id": 0, "room_id": 1, "start_date": 1, "end_date": 1, "status": 1, "allow_sell": 1},
    ).to_list(10000)
    return calculate_stay_night_metrics(bookings, rooms, start_date, end_date, actual_only=actual_only, room_blocks=room_blocks)
