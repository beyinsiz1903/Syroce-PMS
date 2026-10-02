"""Shared financial classification for operator-facing reports.

`payments` also holds non-cash folio offsets (Comp, manual discounts and
audited rate corrections).  They reduce a folio but must never be presented as
cash/card collection.  Keeping the classification here prevents reports from
silently disagreeing about the same transaction.
"""

INVALID_PAYMENT_STATUSES = frozenset({"void", "voided", "failed", "cancelled", "rejected"})


def is_valid_payment(payment: dict) -> bool:
    return not payment.get("voided") and str(payment.get("status") or "paid").lower() not in INVALID_PAYMENT_STATUSES


def is_non_cash_adjustment(payment: dict) -> bool:
    return str(payment.get("method") or payment.get("payment_method") or "").lower() == "discount"


def effective_collection(payment: dict) -> float:
    """Cash/bank/card collection amount; non-cash adjustments return zero."""
    if not is_valid_payment(payment) or is_non_cash_adjustment(payment):
        return 0.0
    amount = float(payment.get("amount") or 0)
    return -amount if str(payment.get("payment_type") or "").lower() == "refund" and amount > 0 else amount


def effective_revenue_adjustment(payment: dict) -> float:
    """Positive value to deduct from gross posted revenue."""
    if not is_valid_payment(payment) or not is_non_cash_adjustment(payment):
        return 0.0
    return abs(float(payment.get("amount") or 0))


def adjustment_kind(payment: dict) -> str:
    return str(payment.get("payment_type") or "discount").lower()
