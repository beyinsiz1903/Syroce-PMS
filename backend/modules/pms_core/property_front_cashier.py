"""Selected-day flow summary in property currency, never a receivable balance."""
from modules.pms_core.property_reporting_currency import PropertyAccumulator
from modules.pms_core.report_money import money, rounded
from modules.pms_core.reporting_financials import deduplicate_report_payments, effective_collection, effective_folio_payment
from modules.pms_core.reporting_ledger import charge_amount


def property_front_cashier(charges, payments, rates):
    acc = PropertyAccumulator(rates)
    methods = set()
    for row in charges:
        acc.add("charges", charge_amount(row), row)
    for row in deduplicate_report_payments(payments):
        method = str(row.get("payment_method") or row.get("method") or "other").strip().lower()
        acc.add("offsets", effective_folio_payment(row), row)
        collection = effective_collection(row)
        if not collection:
            continue
        methods.add(method)
        acc.add("collections", collection, row)
        acc.add("method:"+method, collection, row)
        acc.add("cash" if method == "cash" else "noncash", collection, row)
    total, offsets = acc.total("charges"), acc.total("offsets")
    change = rounded(money(total)-money(offsets)) if total is not None and offsets is not None else None
    cash, noncash, collection = acc.total("cash"), acc.total("noncash"), acc.total("collections")
    uncollected = max(change, 0) if change is not None else None
    base = rates.currency
    return {"front_cashier": {
        "charge_total": total, "charge_total_by_currency": {base: total},
        "collection_total": collection, "cash_total": cash, "non_cash_total": noncash,
        "net_cash_movement": cash, "net_cash_movement_by_currency": {base: cash},
        "daily_balance_change": change, "daily_balance_change_by_currency": {base: change},
        "uncollected_charges": uncollected, "uncollected_charges_by_currency": {base: uncollected},
        "reporting_currency": base, "currency_policy": acc.metadata(),
        "balance_basis": "selected_day_charge_less_folio_offsets; not_remaining_receivable"},
        "payments": {"reporting_currency": base, "total_paid": collection,
            "by_method": {method: acc.total("method:"+method) for method in methods},
            "totals_by_currency": {base: collection}, "currency_policy": acc.metadata()}}
