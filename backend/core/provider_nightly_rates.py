"""Read a complete Exely room-stay price plan without changing any source."""

from datetime import date, datetime, timedelta
from decimal import Decimal


def _day(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _cents(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        cents = Decimal(str(value)) * 100
        if not cents.is_finite() or cents < 0 or cents != cents.to_integral_value():
            return None
        return int(cents)
    except (ArithmeticError, ValueError):
        return None


def exely_daily_rate_plan(booking: dict) -> dict[date, int] | None:
    """Return cents by stay night only when the entire plan reconciles.

    Missing, conflicting, duplicate, out-of-stay or non-finite prices are not
    authoritative source evidence. Explicit PMS overrides are checked by the
    caller and always take precedence. No database or provider access.
    """
    if str(booking.get("booking_source") or "").lower() != "exely":
        return None
    start, end = _day(booking.get("check_in")), _day(booking.get("check_out"))
    plan = booking.get("daily_rates")
    if start is None or end is None or not isinstance(plan, list) or not plan:
        return None
    nights = (end - start).days
    if nights <= 0 or len(plan) != nights:
        return None
    amounts = {}
    for row in plan:
        if not isinstance(row, dict):
            return None
        day, amount = _day(row.get("date")), _cents(row.get("amount"))
        if day is None or not start <= day < end or day in amounts or amount is None:
            return None
        amounts[day] = amount
    if sum(amounts.values()) != _cents(booking.get("total_amount")):
        return None
    return {start + timedelta(days=i): amounts[start + timedelta(days=i)] for i in range(nights)}
