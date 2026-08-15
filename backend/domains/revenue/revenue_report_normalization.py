"""Pure normalization helpers for legacy revenue-report booking rows."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from common.legacy_data_normalization import (
    normalize_dimension_label,
)
from common.legacy_data_normalization import (
    parse_utc_datetime as parse_booking_datetime,
)
from common.legacy_data_normalization import (
    safe_decimal as safe_amount,
)

__all__ = [
    "normalize_dimension_label",
    "parse_booking_datetime",
    "safe_amount",
]


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
