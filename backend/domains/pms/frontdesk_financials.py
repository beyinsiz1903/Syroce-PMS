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
) -> float:
    """Return the durable open balance used by the departure queue."""
    charge_total = sum(
        (_amount(charge.get("total", charge.get("amount"))) for charge in charges if not charge.get("voided")),
        start=Decimal("0"),
    )
    extra_total = sum(
        (_amount(charge.get("charge_amount", charge.get("amount"))) for charge in extra_charges if not charge.get("voided")),
        start=Decimal("0"),
    )
    payment_total = sum(
        (_amount(payment.get("amount")) for payment in payments if not payment.get("voided") and payment.get("status") == "paid"),
        start=Decimal("0"),
    )
    return float(charge_total + extra_total - payment_total)
