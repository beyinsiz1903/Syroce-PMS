"""Pure normalization helpers for legacy revenue-report booking rows."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any


def parse_booking_datetime(value: Any) -> datetime | None:
    """Return a UTC-aware datetime for supported values, otherwise ``None``."""
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, datetime.min.time())
    elif isinstance(value, str):
        candidate = value.strip()
        if not candidate:
            return None
        if candidate.endswith("Z"):
            candidate = f"{candidate[:-1]}+00:00"
        try:
            parsed = datetime.fromisoformat(candidate)
        except ValueError:
            return None
    else:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def safe_amount(value: Any) -> Decimal:
    """Coerce stored numeric values without allowing malformed data to crash reports."""
    if isinstance(value, bool) or value is None:
        return Decimal("0")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return Decimal("0")
    return amount if amount.is_finite() else Decimal("0")


def calculate_booking_revenue(booking: dict[str, Any]) -> Decimal:
    """Calculate report revenue while tolerating incomplete legacy rows."""
    if booking.get("total_amount") is not None:
        return safe_amount(booking.get("total_amount"))

    check_in = parse_booking_datetime(booking.get("check_in"))
    check_out = parse_booking_datetime(booking.get("check_out"))
    if check_in is None or check_out is None:
        return Decimal("0")

    nights = max((check_out.date() - check_in.date()).days, 1)
    return safe_amount(booking.get("rate_per_night")) * nights


def cancellation_lead_bucket(booking: dict[str, Any]) -> str | None:
    """Classify lead time, returning ``None`` when required dates are unavailable."""
    check_in = parse_booking_datetime(booking.get("check_in"))
    cancelled_at = parse_booking_datetime(booking.get("cancelled_at") or booking.get("updated_at") or booking.get("created_at"))
    if check_in is None or cancelled_at is None:
        return None

    days_before = (check_in.date() - cancelled_at.date()).days
    if days_before <= 0:
        return "same_day"
    if days_before <= 3:
        return "1_3_days"
    if days_before <= 7:
        return "4_7_days"
    if days_before <= 14:
        return "8_14_days"
    return "15_plus_days"
