"""Business-date guard for PMS check-in/check-out transitions.

The PMS business date is authoritative for operational state transitions. A
wall-clock timestamp must never allow a future-stay booking to be checked in or
checked out while the hotel's business date is still behind the scheduled
arrival/departure date.

This module is deliberately DB-light and side-effect free: it only reads the
current tenant business date and raises the caller-supplied domain error when a
transition is unsafe or cannot be validated.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

_VALID_OPERATIONS = {
    "check_in": ("check_in", "check in", "check-in"),
    "check_out": ("check_out", "check out", "check-out"),
}


def _parse_date(value: Any, *, label: str, error_cls: type[Exception]) -> date:
    """Parse a PMS date/datetime value into a calendar date, fail-closed."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value.strip():
        raise error_cls(f"{label} is missing; refusing date-sensitive transition")

    raw = value.strip()
    try:
        # Accept both YYYY-MM-DD and ISO datetimes, including a trailing Z.
        return datetime.fromisoformat(raw.replace("Z", "+00:00")).date()
    except ValueError as exc:
        raise error_cls(
            f"{label} is invalid ({raw!r}); refusing date-sensitive transition"
        ) from exc


async def enforce_business_date_transition(
    db,
    *,
    tenant_id: str,
    booking: dict[str, Any],
    operation: str,
    error_cls: type[Exception],
    session=None,
) -> tuple[date, date]:
    """Ensure business date has reached the booking's transition date.

    ``operation`` is ``check_in`` or ``check_out``. Equality is allowed; a
    later business date is also allowed (late arrival/departure handling stays
    unchanged). Missing/malformed business-date or booking-date state is denied
    so that the atomic transition cannot silently fall back to wall-clock time.
    """
    if operation not in _VALID_OPERATIONS:
        raise ValueError(f"Unsupported PMS transition operation: {operation}")

    booking_field, verb, display_field = _VALID_OPERATIONS[operation]

    session_kwargs = {"session": session} if session is not None else {}
    settings = await db.tenant_settings.find_one(
        {"tenant_id": tenant_id},
        {"_id": 0, "business_date": 1},
        **session_kwargs,
    )
    business_date = _parse_date(
        (settings or {}).get("business_date"),
        label="PMS business_date",
        error_cls=error_cls,
    )
    scheduled_date = _parse_date(
        booking.get(booking_field),
        label=f"Booking {display_field}",
        error_cls=error_cls,
    )

    if business_date < scheduled_date:
        raise error_cls(
            f"Cannot {verb} before scheduled {display_field} date: "
            f"business_date={business_date.isoformat()}, "
            f"{booking_field}={scheduled_date.isoformat()}"
        )

    return business_date, scheduled_date
