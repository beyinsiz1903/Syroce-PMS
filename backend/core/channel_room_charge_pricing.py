"""Room-charge pricing rules for provider-imported reservations.

Channel-manager ``total_amount`` values are guest-payable (tax-inclusive)
totals.  Legacy night-audit paths treated that gross total as a net room rate
and added VAT/accommodation tax a second time.  This module keeps the pricing
decision pure and shared by posting, diagnosis, and the audited repair flow.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

MONEY = Decimal("0.01")


def _decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value or 0))
    except (ValueError, TypeError, ArithmeticError):
        return Decimal("0")


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).date()
    except (TypeError, ValueError):
        try:
            return date.fromisoformat(str(value)[:10])
        except (TypeError, ValueError):
            return None


def is_channel_total_tax_inclusive(booking: dict[str, Any]) -> bool:
    """Return whether ``booking.total_amount`` is a provider gross total.

    New imports persist the explicit flag.  The legacy markers cover existing
    HotelRunner/Exely bookings without broadening the rule to manually entered
    agency reservations.
    """
    explicit = booking.get("pricing_tax_inclusive")
    if explicit is not None:
        return bool(explicit)

    source = booking.get("source")
    structured_source = source if isinstance(source, dict) else {}
    source_text = str(source or "").strip().lower()
    origin = str(booking.get("origin") or "").strip().lower()
    booking_source = str(booking.get("booking_source") or "").strip().lower()
    created_by = str(booking.get("created_by") or "").strip().lower()

    return bool(
        source_text == "ota"
        or booking_source == "ota_import"
        or created_by == "channel_manager"
        or origin in {"channel", "channel_manager", "import", "ota_import", "webhook"}
        or structured_source.get("provider")
        or structured_source.get("external_reservation_id")
    )


def _nightly_gross(booking: dict[str, Any], business_date: Any) -> Decimal:
    """Allocate a gross stay total by cent while preserving the exact total."""
    total = _decimal(booking.get("provider_total_amount", booking.get("total_amount", 0)))
    total_cents = int((total * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    check_in = _date(booking.get("check_in"))
    check_out = _date(booking.get("check_out"))
    posting_date = _date(business_date)
    nights = max((check_out - check_in).days, 1) if check_in and check_out else 1

    index = 0
    if posting_date and check_in:
        index = min(max((posting_date - check_in).days, 0), nights - 1)

    cents, remainder = divmod(total_cents, nights)
    if index < remainder:
        cents += 1
    return (Decimal(cents) / 100).quantize(MONEY)


def calculate_room_charge(
    booking: dict[str, Any],
    business_date: Any,
    *,
    vat_rate: float = 0.10,
    accommodation_tax_rate: float = 0.02,
) -> dict[str, Any]:
    """Return a normalized nightly room-charge breakdown.

    Direct/manual bookings retain the historical net-rate behavior. Provider
    imports are reverse-calculated from their gross nightly allocation so the
    posted total never exceeds the channel reservation total.
    """
    vat_rate_d = _decimal(vat_rate)
    accommodation_rate_d = _decimal(accommodation_tax_rate)
    combined_rate = vat_rate_d + accommodation_rate_d
    inclusive = is_channel_total_tax_inclusive(booking)

    if inclusive:
        gross = _nightly_gross(booking, business_date)
        divisor = Decimal("1") + combined_rate
        net = (gross / divisor).quantize(MONEY, rounding=ROUND_HALF_UP) if divisor > 0 else gross
        vat = (net * vat_rate_d).quantize(MONEY, rounding=ROUND_HALF_UP)
        # Put the final rounding cent in accommodation tax so net + taxes is
        # always exactly equal to the provider's guest-payable gross amount.
        accommodation_tax = (gross - net - vat).quantize(MONEY)
        tax = (gross - net).quantize(MONEY)
        total = gross
    else:
        rate = _decimal(booking.get("room_rate") or booking.get("rate") or 0)
        if rate <= 0 and booking.get("total_amount"):
            check_in = _date(booking.get("check_in"))
            check_out = _date(booking.get("check_out"))
            nights = max((check_out - check_in).days, 1) if check_in and check_out else 1
            rate = (_decimal(booking.get("total_amount")) / nights).quantize(MONEY, rounding=ROUND_HALF_UP)
        net = rate.quantize(MONEY, rounding=ROUND_HALF_UP)
        vat = (net * vat_rate_d).quantize(MONEY, rounding=ROUND_HALF_UP)
        accommodation_tax = (net * accommodation_rate_d).quantize(MONEY, rounding=ROUND_HALF_UP)
        tax = (vat + accommodation_tax).quantize(MONEY)
        total = (net + tax).quantize(MONEY)

    return {
        "amount": float(net),
        "unit_price": float(net),
        "tax_amount": float(tax),
        "total": float(total),
        "tax_rate": float((combined_rate * 100).quantize(Decimal("0.1"))),
        "tax_breakdown": {
            "vat": float(vat),
            "accommodation_tax": float(accommodation_tax),
        },
        "tax_inclusive": inclusive,
    }


def analyze_legacy_double_tax_charge(
    booking: dict[str, Any],
    charge: dict[str, Any],
    *,
    vat_rate: float = 0.10,
    accommodation_tax_rate: float = 0.02,
    tolerance: float = 0.03,
) -> dict[str, Any] | None:
    """Identify the exact legacy double-tax signature on a room charge."""
    if not is_channel_total_tax_inclusive(booking) or charge.get("voided"):
        return None
    if charge.get("charge_category") != "room":
        return None
    posted_by = str(charge.get("posted_by") or "").lower()
    if "night_audit" not in posted_by and charge.get("charge_type") != "room_charge":
        return None

    posting_date = charge.get("business_date") or charge.get("night_audit_date") or charge.get("date")
    expected = calculate_room_charge(
        booking,
        posting_date,
        vat_rate=vat_rate,
        accommodation_tax_rate=accommodation_tax_rate,
    )
    observed_amount = float(charge.get("amount", charge.get("unit_price", 0)) or 0)
    observed_total = float(charge.get("total", observed_amount) or 0)
    gross = expected["total"]
    double_tax_total = round(gross * (1 + vat_rate + accommodation_tax_rate), 2)

    if abs(observed_amount - gross) > tolerance:
        return None
    if abs(observed_total - double_tax_total) > tolerance:
        return None

    return {
        "charge_id": charge.get("id"),
        "folio_id": charge.get("folio_id"),
        "business_date": str(posting_date or "")[:10],
        "observed_total": round(observed_total, 2),
        "expected_total": round(gross, 2),
        "overcharge": round(observed_total - gross, 2),
        "corrected": expected,
    }
