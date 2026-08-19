"""Business-date guards for PMS state transitions.

The hotel business date, not the wall-clock date, controls whether a booking
is eligible for normal check-in/check-out.  These helpers are intentionally
pure so every state-transition entry point can share the same fail-closed
semantics and regression tests can exercise the boundary without database I/O.
"""

from __future__ import annotations

from datetime import date, datetime


def _as_date(value: object, *, field_name: str, error_type: type[Exception]) -> date:
    """Normalize a stored PMS date value to ``date`` or fail closed."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value

    text = str(value or "").strip()
    if not text:
        raise error_type(f"{field_name} is missing; refusing date-sensitive transition")

    # PMS booking/business-date fields are canonical YYYY-MM-DD strings, but
    # accepting an ISO datetime here makes the guard robust to legacy rows.
    try:
        return date.fromisoformat(text[:10])
    except (TypeError, ValueError) as exc:
        raise error_type(
            f"{field_name} has invalid date value {text!r}; refusing date-sensitive transition"
        ) from exc


def enforce_business_date_not_before(
    *,
    business_date: object,
    boundary_date: object,
    operation: str,
    boundary_field: str,
    error_type: type[Exception],
) -> None:
    """Reject a transition when hotel business date is before its boundary.

    Equality is allowed: a 17-Aug arrival may be checked in on business date
    17-Aug, and an 18-Aug departure may be checked out on business date 18-Aug.
    Earlier business dates are rejected even when the server wall clock is later.
    """
    business = _as_date(
        business_date,
        field_name="business_date",
        error_type=error_type,
    )
    boundary = _as_date(
        boundary_date,
        field_name=boundary_field,
        error_type=error_type,
    )

    if business < boundary:
        raise error_type(
            f"Cannot {operation}: business_date {business.isoformat()} is before "
            f"{boundary_field} {boundary.isoformat()}"
        )
