"""HotelRunner reservation amount selection.

HotelRunner exposes ``rooms[].price`` as the before-tax amount and
``total``/``rooms[].total`` as the guest-payable after-tax amount.  PMS totals
must therefore prefer the latter and use ``price`` only as a compatibility
fallback when HotelRunner did not send an after-tax total.
"""

from typing import Any


def _amount(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def hotelrunner_room_guest_total(room: dict[str, Any]) -> float | None:
    """Return a room's guest-payable total, falling back to legacy price."""
    after_tax = _amount(room.get("total"))
    if after_tax is not None:
        return after_tax
    return _amount(room.get("price"))


def hotelrunner_guest_total(payload: dict[str, Any]) -> float | None:
    """Return the authoritative guest-payable total for an HR payload.

    A non-exploded reservation keeps HotelRunner's reservation-level grand
    total.  An exploded multi-room sub-reservation uses that room's after-tax
    total.  This distinction preserves reservation-level adjustments while
    still assigning the correct amount to each PMS booking after explosion.
    """
    rooms = payload.get("rooms") or []
    valid_rooms = [room for room in rooms if isinstance(room, dict)] if isinstance(rooms, list) else []

    if payload.get("_exploded_from") and valid_rooms:
        return hotelrunner_room_guest_total(valid_rooms[0])

    reservation_total = _amount(payload.get("total"))
    if reservation_total is not None:
        return reservation_total

    if len(valid_rooms) == 1:
        return hotelrunner_room_guest_total(valid_rooms[0])

    room_totals = [hotelrunner_room_guest_total(room) for room in valid_rooms]
    if room_totals and all(total is not None for total in room_totals):
        return sum(total for total in room_totals if total is not None)
    return None


def matches_legacy_before_tax_total(
    current_total: Any,
    payload: dict[str, Any],
    *,
    tolerance: float = 0.01,
) -> bool:
    """Detect the old Syroce import signature without guessing a tax rate."""
    rooms = payload.get("rooms") or []
    if not isinstance(rooms, list) or len(rooms) != 1 or not isinstance(rooms[0], dict):
        return False

    before_tax = _amount(rooms[0].get("price"))
    guest_total = hotelrunner_guest_total(payload)
    current = _amount(current_total)
    if before_tax is None or guest_total is None or current is None:
        return False
    return abs(current - before_tax) <= tolerance and abs(guest_total - before_tax) > tolerance
