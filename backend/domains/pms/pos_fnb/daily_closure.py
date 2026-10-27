"""Source-bound POS settlement snapshots; never a fiscal Z or bank capture.

Net revenue includes VAT, excludes tips and subtracts refunds. Payment totals
include tips; room charges are transfers, not cash collected. No FX conversion.
"""
import hashlib
import json
import re
from decimal import Decimal, InvalidOperation

from domains.pms.pos_fnb.reporting import enrich_refunds
from domains.pms.pos_router.pos_core import _query_pos_transactions

VERSION = "canonical_pos_ledger_v2"
FINAL = {"closed", "completed", "paid", "settled", "refunded", "refund"}
CARDS = {"card", "credit_card", "debit_card"}
COLLECTIONS = {"cash", "card", "credit_card", "debit_card", "bank", "bank_transfer", "online", "eft", "wire", "havale"}


def money(value):
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError("INVALID_POS_MONETARY_VALUE") from exc
    if not amount.is_finite():
        raise ValueError("INVALID_POS_MONETARY_VALUE")
    return amount


def summarize(transactions, default_currency=None):
    buckets, methods, seen, manifest = {}, {}, {}, []
    count = refunds = 0
    for row in transactions:
        status = str(row.get("status") or "").lower().strip()
        if status not in FINAL:
            continue
        identity = row.get("id") or row.get("transaction_id")
        if not identity:
            raise ValueError("MISSING_POS_TRANSACTION_ID")
        code = str(row.get("currency") or default_currency or "").upper().strip()
        if not re.fullmatch(r"[A-Z]{3}", code):
            raise ValueError("MISSING_POS_CURRENCY")
        refund = status in {"refunded", "refund"} or row.get("payment_type") == "refund"
        amount = money(row.get("total_amount", row.get("amount")))
        tip = money(row.get("tip_amount", 0))
        if (refund and (amount > 0 or tip > 0)) or (not refund and (amount < 0 or tip < 0)) or abs(tip) > abs(amount):
            raise ValueError("INVALID_POS_MONETARY_VALUE")
        parts = row.get("payment_breakdown")
        tender = {}
        if parts:
            for part in parts:
                # Breakdown amounts are in the sale's base currency. A foreign
                # received_amount is evidence, never another base tender.
                method = str(part.get("method") or "").strip().lower()
                value = money(part.get("amount"))
                if not method or method == "mixed" or (value > 0 if refund else value < 0):
                    raise ValueError("INVALID_POS_PAYMENT_BREAKDOWN")
                tender[method] = tender.get(method, Decimal(0)) + value
        else:
            method = str(row.get("payment_method") or "other").strip().lower()
            if method == "mixed":
                raise ValueError("MISSING_POS_PAYMENT_BREAKDOWN")
            tender[method] = amount
        if sum(tender.values(), Decimal(0)) != amount:
            raise ValueError("UNBALANCED_POS_PAYMENT_BREAKDOWN")
        source = {"id": str(identity), "order_id": row.get("order_id"), "status": status,
                  "transaction_date": str(row.get("transaction_date") or row.get("business_date") or ""),
                  "currency": code, "amount": str(amount), "tip": str(tip),
                  "refund": refund, "original_transaction_id": row.get("original_transaction_id"),
                  "tenders": {key: str(value) for key, value in sorted(tender.items())}}
        if str(identity) in seen:
            if seen[str(identity)] != source:
                raise ValueError("CONFLICTING_POS_TRANSACTION")
            continue
        seen[str(identity)] = source
        manifest.append(source)
        totals = buckets.setdefault(code, {key: Decimal(0) for key in (
            "total_sales", "net_sales", "tips", "refund_total", "cash_sales", "card_sales", "other_sales", "room_charge_sales", "collected_total")})
        totals["total_sales"] += amount
        totals["net_sales"] += amount - tip
        totals["tips"] += tip
        totals["refund_total"] += abs(amount) if refund else 0
        for method, value in tender.items():
            methods.setdefault(code, {})[method] = methods.get(code, {}).get(method, Decimal(0)) + value
            totals["cash_sales" if method == "cash" else "card_sales" if method in CARDS else "other_sales"] += value
            if method == "room_charge":
                totals["room_charge_sales"] += value
            if method in COLLECTIONS:
                totals["collected_total"] += value
        count += 1
        refunds += int(refund)
    native = {code: {key: float(value) for key, value in totals.items()} for code, totals in sorted(buckets.items())}
    scalar = next(iter(native.values())) if len(native) == 1 else dict.fromkeys(("total_sales", "net_sales", "tips", "refund_total", "cash_sales", "card_sales", "other_sales", "room_charge_sales", "collected_total"))
    return {**scalar, "currency": next(iter(native)) if len(native) == 1 else None,
            "totals_by_currency": native,
            "payment_methods_by_currency": {code: {key: float(value) for key, value in sorted(values.items())} for code, values in sorted(methods.items())},
            "transaction_count": count, "sale_count": count - refunds, "refund_count": refunds,
            "source_manifest": sorted(manifest, key=lambda item: item["id"])}


async def preview(database, tenant_id, business_date, session=None):
    settings = await database.hotel_settings.find_one({"tenant_id": tenant_id}, {"_id": 0, "currency": 1}, **({"session": session} if session is not None else {}))
    fallback = (settings or {}).get("currency")
    # Check duplicate financial copies before canonical source precedence can
    # hide a conflicting amount/currency/tender. Legacy refunds are enriched
    # below, so compare their stored facts rather than inventing tax/tips.
    def check_duplicates(rows):
        seen = {}
        for row in rows:
            if str(row.get("status") or "").lower().strip() not in FINAL:
                continue
            identity = row.get("id") or row.get("transaction_id")
            if not identity:
                continue  # summarize rejects finalized rows lacking identity.
            facts = {key: row.get(key) for key in ("status", "currency", "payment_method", "payment_type", "original_transaction_id", "payment_breakdown")}
            facts["total_amount"] = str(money(row.get("total_amount", row.get("amount"))))
            facts["tip_amount"] = str(money(row.get("tip_amount", 0)))
            if str(identity) in seen and facts != seen[str(identity)]:
                raise ValueError("CONFLICTING_POS_TRANSACTION")
            seen[str(identity)] = facts
    rows = await _query_pos_transactions(tenant_id, limit=None, date=business_date, database=database, session=session,
                                         validate_duplicates=check_duplicates)
    rows, warnings = await enrich_refunds(database, tenant_id, rows, session=session)
    if warnings:
        raise ValueError("UNVERIFIED_POS_REFUND_SOURCE")
    result = summarize(rows, fallback)
    result.update(closure_date=business_date, calculation_version=VERSION)
    payload = {"tenant_id": tenant_id, **result}
    result["preview_hash"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return result
