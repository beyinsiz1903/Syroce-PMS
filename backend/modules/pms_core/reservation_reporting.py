"""Current booked value, not posted revenue or cash, for arrival-date reports."""

from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from modules.pms_core.report_money import money
from modules.pms_core.stay_night_metrics import booking_nights


def reservation_value(booking: dict) -> Decimal | None:
    """Preserve explicit zero and flag malformed money instead of inventing zero.

    Complimentary reference tariffs never become booked sales. Legacy total or
    nightly rate is used only when the authoritative total is absent, not bad.
    Round the booking once so displayed detail and grouped totals reconcile.
    """
    if booking.get("is_complimentary"):
        return Decimal(0)
    value = next((booking[field] for field in ("total_amount", "total") if booking.get(field) is not None), None)
    factor = 1
    if value is None:
        value = booking.get("rate_per_night", 0)
        factor = booking_nights(booking)
    if isinstance(value, bool):
        return None
    try:
        return (money(value) * factor).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (ValueError, TypeError, InvalidOperation):
        return None
