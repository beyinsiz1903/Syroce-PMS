"""Shared financial classification for operator-facing reports.

`payments` also holds non-cash folio offsets (Comp, manual discounts and
audited rate corrections).  They reduce a folio but must never be presented as
cash/card collection.  Keeping the classification here prevents reports from
silently disagreeing about the same transaction.
"""

INVALID_PAYMENT_STATUSES = frozenset({"void", "voided", "failed", "cancelled", "rejected"})
REPORTING_CURRENCY = "TRY"


def report_payment_identity(payment: dict) -> tuple:
    """Return the real-world transaction identity used by report totals."""
    payment_type = str(payment.get("payment_type") or "payment").strip().lower()
    for field in ("idempotency_key", "provider_ref", "provider_transaction_id", "transaction_id"):
        value = str(payment.get(field) or "").strip()
        if value:
            return (field, value, payment_type)
    value = str(payment.get("id") or payment.get("_id") or "").strip()
    return ("id", value, payment_type) if value else ("object", id(payment))


def deduplicate_report_payments(payments: list[dict]) -> list[dict]:
    """Omit retry-created duplicate ledger rows without collapsing refunds."""
    seen: set[tuple] = set()
    unique: list[dict] = []
    for payment in payments:
        identity = report_payment_identity(payment)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(payment)
    return unique


def stamp_reporting_values(payment: dict, reporting_currency: str = REPORTING_CURRENCY) -> dict:
    """Persist the transaction-time reporting value on a new payment document."""
    reporting_currency = str(reporting_currency or REPORTING_CURRENCY).upper()
    if payment.get("reporting_amount") is None:
        ledger_currency = str(payment.get("currency") or reporting_currency).upper()
        received_currency = str(payment.get("received_currency") or ledger_currency).upper()
        if ledger_currency == reporting_currency:
            payment["reporting_amount"] = float(payment.get("amount") or 0)
        elif received_currency == reporting_currency and payment.get("received_amount") is not None:
            payment["reporting_amount"] = float(payment["received_amount"])
    if payment.get("reporting_amount") is not None:
        payment["reporting_currency"] = reporting_currency
    payment.setdefault(
        "exchange_rate_date",
        str(payment.get("business_date") or payment.get("payment_date") or payment.get("processed_at") or "")[:10] or None,
    )
    return payment


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


def reporting_collection_amount(payment: dict, reporting_currency: str = REPORTING_CURRENCY) -> float | None:
    """Return a collection in the property's reporting currency.

    ``amount``/``currency`` are the folio-ledger values while
    ``received_amount``/``received_currency`` preserve what the guest actually
    handed over.  Reports must use the former when it is already in TRY and
    must never add a raw USD/EUR amount to a TRY total.  Older records whose
    ledger is foreign can still be reported when the physically received
    amount was TRY or when an explicit immutable reporting amount was stored.

    ``None`` deliberately means "cannot convert safely".  Callers surface that
    as a conversion issue instead of silently applying today's rate to a
    historical transaction.
    """
    if not is_valid_payment(payment) or is_non_cash_adjustment(payment):
        return 0.0

    reporting_currency = str(reporting_currency or REPORTING_CURRENCY).upper()
    sign = -1 if str(payment.get("payment_type") or "").lower() == "refund" else 1

    explicit_currency = str(payment.get("reporting_currency") or payment.get("base_currency") or "").upper()
    for field in ("reporting_amount", "base_amount", "amount_try"):
        value = payment.get(field)
        if value is not None and (not explicit_currency or explicit_currency == reporting_currency):
            try:
                return sign * abs(float(value))
            except (TypeError, ValueError):
                pass

    ledger_currency = str(payment.get("currency") or reporting_currency).upper()
    if ledger_currency == reporting_currency:
        return effective_collection(payment)

    received_currency = str(payment.get("received_currency") or "").upper()
    if received_currency == reporting_currency and payment.get("received_amount") is not None:
        try:
            return sign * abs(float(payment["received_amount"]))
        except (TypeError, ValueError):
            return None

    return None


def reporting_collection_summary(payments: list[dict], reporting_currency: str = REPORTING_CURRENCY) -> dict:
    """Build a single-currency collection summary without FX revaluation."""
    total = 0.0
    count = 0
    by_method: dict[str, dict[str, float | int]] = {}
    conversion_issues: list[dict] = []
    for payment in payments:
        if not is_valid_payment(payment) or is_non_cash_adjustment(payment):
            continue
        amount = reporting_collection_amount(payment, reporting_currency)
        if amount is None:
            conversion_issues.append(
                {
                    "id": payment.get("id"),
                    "currency": str(payment.get("currency") or "").upper() or None,
                    "received_currency": str(payment.get("received_currency") or "").upper() or None,
                    "reason": "historical_exchange_rate_missing",
                }
            )
            continue
        if amount == 0:
            continue
        total += amount
        count += 1
        method = str(payment.get("payment_method") or payment.get("method") or "other").strip().lower() or "other"
        entry = by_method.setdefault(method, {"amount": 0.0, "count": 0})
        entry["amount"] = round(float(entry["amount"]) + amount, 2)
        entry["count"] = int(entry["count"]) + 1
    return {
        "currency": str(reporting_currency or REPORTING_CURRENCY).upper(),
        "amount": round(total, 2),
        "payment_count": count,
        "by_method": by_method,
        "conversion_issue_count": len(conversion_issues),
        "conversion_issues": conversion_issues,
    }


def effective_revenue_adjustment(payment: dict) -> float:
    """Positive value to deduct from gross posted revenue."""
    if not is_valid_payment(payment) or not is_non_cash_adjustment(payment):
        return 0.0
    return abs(float(payment.get("amount") or 0))


def adjustment_kind(payment: dict) -> str:
    return str(payment.get("payment_type") or "discount").lower()
