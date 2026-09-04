"""Pure financial helpers shared by front-desk read models."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def _amount(value: Any) -> Decimal:
    if value is None or isinstance(value, bool):
        return Decimal("0")
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")
    return amount if amount.is_finite() else Decimal("0")


def calculate_departure_balance(
    charges: list[dict[str, Any]],
    payments: list[dict[str, Any]],
    extra_charges: list[dict[str, Any]],
    *,
    booking_total: Any = 0,
) -> float:
    """Return the durable open balance used by departure and checkout."""
    active_charges = [charge for charge in charges if not charge.get("voided")]
    charge_total = sum(
        (_amount(charge.get("total", charge.get("amount"))) for charge in active_charges),
        start=Decimal("0"),
    )
    extra_total = sum(
        (_amount(charge.get("total", charge.get("charge_amount", charge.get("amount")))) for charge in extra_charges if not charge.get("voided")),
        start=Decimal("0"),
    )
    payment_total = sum(
        (_amount(payment.get("amount")) for payment in payments if not payment.get("voided") and payment.get("status") == "paid"),
        start=Decimal("0"),
    )
    room_charge_total = sum(
        (
            _amount(charge.get("total", charge.get("amount")))
            for charge in active_charges
            if charge.get("charge_type") == "room_charge" or charge.get("charge_category") == "room"
        ),
        start=Decimal("0"),
    )
    # A partly posted stay still owes the portion of its confirmed total that
    # has not reached the folio.  Treating *any* room charge as the full stay
    # allowed a checkout to close with a hidden final-night credit.
    unposted_room_total = max(Decimal("0"), _amount(booking_total) - room_charge_total)
    return float(unposted_room_total + charge_total + extra_total - payment_total)
