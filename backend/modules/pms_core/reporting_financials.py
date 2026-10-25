"""Shared financial classification for operator-facing reports.

`payments` also holds non-cash folio offsets (Comp, manual discounts and
audited rate corrections).  They reduce a folio but must never be presented as
cash/card collection.  Keeping the classification here prevents reports from
silently disagreeing about the same transaction.
"""

from modules.pms_core.report_money import currency_code, money, rounded

INVALID_PAYMENT_STATUSES = frozenset({"void", "voided", "failed", "cancelled", "canceled", "rejected", "pending", "processing", "initiated", "authorized", "expired", "declined", "requires_action"})
REPORTING_CURRENCY = "TRY"
INSTRUMENT_SETTLEMENT_METHODS = frozenset({"gift_card_redemption", "wallet", "loyalty_redemption", "barter", "write_off"})
NON_CASH_PAYMENT_METHODS = frozenset({"discount", "city_ledger", "direct_bill", "complimentary", "correction", "ar", "security_deposit_application"}) | INSTRUMENT_SETTLEMENT_METHODS


def report_payment_day_match(day: str) -> dict:
    return report_payment_period_match(day, day)


def report_payment_period_match(first: str, last: str, *, date_fields=("payment_date", "date", "processed_at", "created_at"), use_business_date: bool = True) -> dict:
    """Use one authoritative ISO/BSON date, with ordered legacy fallbacks.

    Cash-movement audit trails explicitly opt out of accounting-day selection
    and put processed_at first, so a payment cannot appear on two event days.
    """
    from datetime import UTC, datetime, timedelta

    from core.business_date_service import accounting_period_match

    start = datetime.fromisoformat(first).replace(tzinfo=UTC)
    end = datetime.fromisoformat(last).replace(tzinfo=UTC) + timedelta(days=1)
    clauses, previous = [], []
    for field in date_fields:
        clauses.append({**{key: {"$in": [None, ""]} for key in previous},
            "$or": [{field: {"$gte": first, "$lt": end.date().isoformat()}}, {field: {"$gte": start, "$lt": end}}]})
        previous.append(field)
    if not use_business_date:
        return {"$or": clauses}
    query = accounting_period_match(first, last, *clauses)
    query["$or"][0] = {"business_date": {"$gte": first, "$lt": end.date().isoformat()}}
    query["$or"].append({"business_date": {"$gte": start, "$lt": end}})
    return query


def report_payment_identity(payment: dict) -> tuple:
    """Return the real-world transaction identity used by report totals."""
    payment_type = str(payment.get("payment_type") or "payment").strip().lower()
    scope = (payment.get("tenant_id"), payment.get("folio_id") or payment.get("booking_id"), payment.get("provider"))
    # A refund may carry the ORIGINAL payment's provider_ref. Distinct partial
    # refunds need their own transaction/idempotency identity, not the parent.
    fields = ("idempotency_key", "provider_txn_ref", "provider_transaction_id", "transaction_id")
    if payment_type != "refund":
        fields += ("provider_ref",)
    for field in fields:
        value = str(payment.get(field) or "").strip()
        if value:
            return (scope, field, value, payment_type)
    value = str(payment.get("id") or payment.get("_id") or "").strip()
    return (scope, "id", value, payment_type) if value else ("object", id(payment))


def deduplicate_report_payments(payments: list[dict]) -> list[dict]:
    """Omit retry-created duplicate ledger rows without collapsing refunds."""
    seen: dict[tuple, int] = {}
    unique: list[dict] = []
    for payment in payments:
        identity = report_payment_identity(payment)
        if identity in seen:
            index = seen[identity]
            if not is_valid_payment(unique[index]) and is_valid_payment(payment):
                unique[index] = payment
            continue
        seen[identity] = len(unique)
        unique.append(payment)
    return unique


def stamp_reporting_values(payment: dict, reporting_currency: str = REPORTING_CURRENCY) -> dict:
    """Persist the transaction-time reporting value on a new payment document."""
    reporting_currency = currency_code(reporting_currency, REPORTING_CURRENCY)
    if payment.get("reporting_amount") is None:
        ledger_currency = currency_code(payment.get("currency"), reporting_currency)
        received_currency = currency_code(payment.get("received_currency"), ledger_currency)
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
    return not payment.get("voided") and str(payment.get("status") or "paid").strip().lower() not in INVALID_PAYMENT_STATUSES


def _payment_method(payment: dict) -> str:
    return str(payment.get("payment_method") or payment.get("method") or "").strip().lower()


def is_non_cash_adjustment(payment: dict) -> bool:
    return _payment_method(payment) == "discount"


def effective_collection(payment: dict) -> float:
    """Cash/bank/card collection amount; non-cash adjustments return zero."""
    if not is_valid_payment(payment) or _payment_method(payment) in NON_CASH_PAYMENT_METHODS:
        return 0.0
    return effective_folio_payment(payment)


def effective_folio_payment(payment: dict) -> float:
    """Signed ledger offset, including non-cash folio adjustments.

    A discount reduces the folio balance but is not cash collection. Keep that
    distinction while sharing validation and refund sign handling.
    """
    if not is_valid_payment(payment):
        return 0.0
    amount = float(money(payment.get("amount") or 0))
    return -amount if str(payment.get("payment_type") or "").strip().lower() == "refund" and amount > 0 else amount


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
    if not is_valid_payment(payment) or _payment_method(payment) in NON_CASH_PAYMENT_METHODS:
        return 0.0

    reporting_currency = currency_code(reporting_currency, REPORTING_CURRENCY)
    sign = -1 if str(payment.get("payment_type") or "").strip().lower() == "refund" else 1

    explicit_currency = currency_code(payment.get("reporting_currency") or payment.get("base_currency"), "")
    for field in ("reporting_amount", "base_amount", "amount_try"):
        value = payment.get(field)
        if value is not None and (not explicit_currency or explicit_currency == reporting_currency):
            try:
                return -abs(float(money(value))) if sign < 0 else float(money(value))
            except (TypeError, ValueError):
                pass

    ledger_currency = currency_code(payment.get("currency"), reporting_currency)
    if ledger_currency == reporting_currency:
        return effective_collection(payment)

    received_currency = currency_code(payment.get("received_currency"), "")
    if received_currency == reporting_currency and payment.get("received_amount") is not None:
        try:
            return -abs(float(money(payment["received_amount"]))) if sign < 0 else float(money(payment["received_amount"]))
        except (TypeError, ValueError):
            return None

    return None


def reporting_collection_summary(payments: list[dict], reporting_currency: str = REPORTING_CURRENCY) -> dict:
    """Build a single-currency collection summary without FX revaluation."""
    total = money(0)
    count = 0
    by_method: dict[str, dict[str, float | int]] = {}
    conversion_issues: list[dict] = []
    reconstructed_count = 0
    for payment in deduplicate_report_payments(payments):
        if not is_valid_payment(payment) or _payment_method(payment) in NON_CASH_PAYMENT_METHODS:
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
        reconstructed_count += (payment.get("demo_reconstruction") or {}).get("basis") == "demo_reconstruction"
        total += money(amount)
        count += 1
        method = str(payment.get("payment_method") or payment.get("method") or "other").strip().lower() or "other"
        entry = by_method.setdefault(method, {"amount": 0.0, "count": 0})
        entry["amount"] = money(entry["amount"]) + money(amount)
        entry["count"] = int(entry["count"]) + 1
    return {
        "currency": str(reporting_currency or REPORTING_CURRENCY).upper(),
        "amount": rounded(total),
        "payment_count": count,
        "by_method": {method: {**entry, "amount": rounded(entry["amount"])} for method, entry in by_method.items()},
        "conversion_issue_count": len(conversion_issues),
        "conversion_issues": conversion_issues,
        **({"demo_reconstructed_count": reconstructed_count, "historical_source_verified": False} if reconstructed_count else {}),
    }


def effective_revenue_adjustment(payment: dict) -> float:
    """Signed non-cash offset to deduct; a reversal restores revenue."""
    if not is_valid_payment(payment) or not is_non_cash_adjustment(payment):
        return 0.0
    return effective_folio_payment(payment)


def adjustment_kind(payment: dict) -> str:
    return str(payment.get("payment_type") or "discount").lower()
