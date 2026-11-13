"""PMSConnect 1.17 DepositPayments: provider snapshots, never local receipts.

ReceivedPayment is money received; ExpectedPayment is only a request. Amount
already includes BasisType/Percent/NmbrOfNights. Each delivery contains the full
installment list, so later versions replace this snapshot instead of appending.
"""

import re
from decimal import Decimal, InvalidOperation

NS = "{http://www.opentravel.org/OTA/2003/05}"
KINDS = {
    "ReceivedPayment": "received_amount",
    "ExpectedPayment": "expected_amount",
    "ReceivedLoyaltyPayment": "loyalty_amount",
}


class PrepaymentPayloadError(ValueError):
    """Do not acknowledge malformed money or include payment data in errors."""


def _amount(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or result > Decimal('1000000000000'):
            raise ValueError
        return result
    except (InvalidOperation, ValueError, TypeError):
        raise PrepaymentPayloadError("EXELY_PREPAYMENT_AMOUNT_INVALID") from None


def parse_prepayments(global_info, booking_total, booking_currency):
    if global_info is None:
        return None
    containers = global_info.findall(f"{NS}DepositPayments")
    if not containers:
        return None  # Preserve legacy raw hashes when no payments were supplied.
    if len(containers) != 1:
        raise PrepaymentPayloadError("EXELY_PREPAYMENT_CONTAINER_INVALID")
    nodes = list(containers[0])
    if len(nodes) > 1000:
        raise PrepaymentPayloadError("EXELY_PREPAYMENT_LIMIT")
    payments, totals, seen = [], {}, set()
    for node in nodes:
        kind = node.get("Type")
        amounts = node.findall(f"{NS}AmountPercent")
        if node.tag != f"{NS}GuaranteePayment" or kind not in KINDS or len(amounts) != 1:
            raise PrepaymentPayloadError("EXELY_PREPAYMENT_TYPE_INVALID")
        amount = _amount(amounts[0].get("Amount"))
        currency = str(amounts[0].get("CurrencyCode") or "").strip().upper()
        if not re.fullmatch(r"[A-Z]{3}", currency):
            raise PrepaymentPayloadError("EXELY_PREPAYMENT_CURRENCY_INVALID")
        index = node.get("PaymentIndex")
        if index is not None:
            if not re.fullmatch(r"[0-9]{1,9}", index):
                raise PrepaymentPayloadError("EXELY_PREPAYMENT_INDEX_INVALID")
            index = str(int(index))
            key = (kind, index)
            if key in seen:
                raise PrepaymentPayloadError("EXELY_PREPAYMENT_INDEX_DUPLICATE")
            seen.add(key)
        payments.append({"type": kind, "payment_index": index, "amount": float(amount), "currency": currency})
        bucket = totals.setdefault(currency, {key: Decimal(0) for key in KINDS.values()})
        bucket[KINDS[kind]] += amount
    # Older single-payment responses sometimes omit PaymentIndex. Several
    # unindexed receipts cannot safely identify installments versus duplicates.
    received = [row for row in payments if row['type'] == 'ReceivedPayment']
    if len(received) > 1 and any(row['payment_index'] is None for row in received):
        raise PrepaymentPayloadError("EXELY_PREPAYMENT_INDEX_MISSING")
    paid_currencies = {code for code, amounts in totals.items()
                       if amounts['received_amount'] or amounts['loyalty_amount']}
    currency = str(booking_currency or '').upper()
    comparable = bool(re.fullmatch(r"[A-Z]{3}", currency)) and paid_currencies.issubset({currency})
    paid = totals.get(currency, {})
    outstanding = (_amount(booking_total) - paid.get('received_amount', Decimal(0))
                   - paid.get('loyalty_amount', Decimal(0))) if comparable else None
    return {
        "schema_version": 1,
        "scope": "reservation",
        "payments": payments,
        "totals": [{"currency": code, **{key: float(value) for key, value in amounts.items()}}
                   for code, amounts in sorted(totals.items())],
        "booking_total": float(_amount(booking_total)),
        "booking_currency": currency,
        "remaining_amount": float(max(outstanding, Decimal(0))) if outstanding is not None else None,
        "overpayment_amount": float(max(-outstanding, Decimal(0))) if outstanding is not None else None,
    }
