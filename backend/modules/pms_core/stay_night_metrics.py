"""Canonical room-night metrics used by PMS dashboards and reports."""

from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

OCCUPYING_STATUSES = frozenset({"confirmed", "guaranteed", "checked_in", "checked_out"})


def _as_date(value) -> date | None:
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
    bookings: list[dict], rooms: list[dict], start_date: date, end_date: date
) -> list[dict]:
    """Return inclusive daily metrics using ``check_in <= day < check_out``.

    Occupancy is the number of unique assigned rooms. Gross reservation totals
    are allocated evenly over their stay nights, so they are never repeated on
    every day. Inactive rooms are excluded from capacity.
    """
    active_rooms = [room for room in rooms if room.get("is_active") is not False]
    total_rooms = len(active_rooms)
    days = (end_date - start_date).days + 1
    result = []

    parsed = []
    for booking in bookings:
        if booking.get("status") not in OCCUPYING_STATUSES:
            continue
        check_in = _as_date(booking.get("check_in"))
        check_out = _as_date(booking.get("check_out"))
        room_key = _room_key(booking)
        if not check_in or not check_out or check_out <= check_in or not room_key:
            continue
        nights = (check_out - check_in).days
        parsed.append((check_in, check_out, room_key, _money(booking.get("total_amount")) / nights))

    for offset in range(max(days, 0)):
        day = start_date + timedelta(days=offset)
        occupied_rooms: set[str] = set()
        revenue = Decimal("0")
        for check_in, check_out, room_key, nightly_revenue in parsed:
            if check_in <= day < check_out:
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


async def load_stay_night_metrics(db, tenant_id: str, start_date: date, end_date: date) -> list[dict]:
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
        },
    ).to_list(10000)
    return calculate_stay_night_metrics(bookings, rooms, start_date, end_date)
