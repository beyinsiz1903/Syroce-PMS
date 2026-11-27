"""Single property-currency view for the GM collection and receivable cards."""
from copy import deepcopy
from datetime import date

from modules.pms_core.property_financial_summary import folio_carrying_values
from modules.pms_core.property_position_values import property_position_value
from modules.pms_core.property_report_projections import property_income_report
from modules.pms_core.property_reporting_currency import PropertyAccumulator, load_historical_rates, source_day
from modules.pms_core.receivable_reporting import folio_snapshots, report_day
from modules.pms_core.report_money import currency_code, money, rounded
from modules.pms_core.reporting_financials import (
    NON_CASH_PAYMENT_METHODS,
    deduplicate_report_payments,
    effective_collection,
    is_valid_payment,
)


async def property_finance_snapshot(database, tenant_id, payload, positions, folios, today_payments,
        month_payments, month_charges, invoices, first, last, base):
    snapshot_issues = []
    try:
        snapshots = await folio_snapshots(database, tenant_id, folios, fallback_currency=base, include_booking_extras=True)
    except (ValueError, TypeError, ArithmeticError, KeyError):
        snapshots = {}
        snapshot_issues = [{"id": row.get("id"), "reason": "receivable_carrying_sources_invalid"} for row in folios]
    sources = [*today_payments, *month_payments, *month_charges,
        *[row for snap in snapshots.values() for row in snap["charges"] + snap["payments"]]]
    days = [source_day(row) for row in sources]
    days += [source_day({"business_date": row.get("exchange_rate_date")}) for row in sources]
    days += [source_day({"business_date": snap["folio"].get("opening_balance_date")}) for snap in snapshots.values()]
    days += [source_day({"business_date": row.get("business_date") or row.get("invoice_date")}) for row in invoices]
    days += [source_day({**row, "business_date": row.get("business_date") or row.get("transaction_date")}) for position in positions for row in [*[part["source"] for part in position.get("valuation_parts", [])], *position.get("valuation_candidates", [])]]
    dates = [day for day in days if day] + [first.isoformat(), last.isoformat()]
    codes = {currency_code(row.get("currency"), base) for row in sources + invoices + positions}
    rates = await load_historical_rates(database, tenant_id, date.fromisoformat(min(dates)), date.fromisoformat(max(dates)),
        base_currency=base, currencies=codes)
    acc = PropertyAccumulator(rates)
    ar_rates = []
    carrying, issues = folio_carrying_values(snapshots, rates, evidence=ar_rates)
    issues.extend(snapshot_issues)
    result = deepcopy(payload)
    result["currency"] = result["reporting_currency"] = base
    for position in positions:
        code = currency_code(position["currency"])
        value = property_position_value(position, rates, carrying, ar_rates)
        if value is None:
            issues.append({"id": position["folio"].get("id"), "currency": code, "reason": "receivable_carrying_value_unverified"})
        source = {"currency": base}
        acc.add("ar:total", value, source)
        if position.get("account_key"):
            age = position.get("age_days")
        else:
            folio = position["folio"]
            anchor = report_day(folio.get("due_date") or folio.get("invoice_date") or folio.get("created_at"))
            age = max((last-anchor).days, 0) if anchor else 99999
        if age is None:
            acc.add("ar:unaged", value, source)
        elif age > 0:
            bucket = "0-30_days" if age <= 30 else "30-60_days" if age <= 60 else "60_plus_days"
            acc.add("ar:"+bucket, value, source)
    pending = result["pending_ar"]
    complete = pending["complete"] and acc.total("ar:total") is not None
    buckets = {key: acc.total("ar:"+key) for key in ("total", "0-30_days", "30-60_days", "60_plus_days")}
    if not pending["complete"]:
        buckets["total"] = None
    pending.update(total=buckets["total"], complete=complete,
        by_currency={base: {**buckets, "overdue_invoices_count": pending["overdue_invoices_count"]}},
        overdue_breakdown={key: buckets[key] for key in ("0-30_days", "30-60_days", "60_plus_days")},
        unaged_balance_by_currency={base: acc.total("ar:unaged")},
        source_issues=[*pending.get("source_issues", []), *issues],
        balance_basis="property_currency_remaining_company_ledger_carrying_values")

    def collections(rows, prefix):
        counts, reconstructed = {}, 0
        for row in deduplicate_report_payments(rows):
            method = str(row.get("payment_method") or row.get("method") or "other").strip().lower()
            if not is_valid_payment(row) or method in NON_CASH_PAYMENT_METHODS:
                continue
            value = effective_collection(row)
            if not value:
                continue
            acc.add(prefix, value, row)
            acc.add(prefix+":"+method, value, row)
            counts[method] = counts.get(method, 0)+1
            reconstructed += (row.get("demo_reconstruction") or {}).get("basis") == "demo_reconstruction"
        return {"currency": base, "amount": acc.total(prefix), "payment_count": sum(counts.values()),
            "by_method": {method: {"amount": acc.total(prefix+":"+method), "count": count} for method, count in counts.items()},
            "conversion_issue_count": len(acc.issues), "conversion_issues": list(acc.issues),
            **({"demo_reconstructed_count": reconstructed, "historical_source_verified": False} if reconstructed else {})}
    result["todays_collections"] = collections(today_payments, "today")
    month = collections(month_payments, "month")
    income = property_income_report(month_charges, first, last, rates)
    revenue, paid = income["totals"]["total"], month["amount"]
    ratio = rounded(money(paid)/money(revenue)*100) if revenue is not None and revenue > 0 and paid is not None else None
    result["mtd_collections"] = {**result["mtd_collections"], **month,
        "collection_rate_percentage": ratio, "collection_rate_currency": base,
        "collection_rate_complete": ratio is not None, "revenue_by_currency": {base: revenue}}
    for row in invoices:
        remaining = max(money(row.get("total"))-money(row.get("amount_paid") if row.get("amount_paid") is not None else row.get("paid_amount")), 0)
        acc.add("invoices", remaining, {**row, "currency": row.get("currency") or base,
            "business_date": row.get("business_date") or row.get("invoice_date")})
    result["accounting_invoices"].update(pending_total=acc.total("invoices"), by_currency={base: acc.total("invoices")})
    result["currency_policy"] = {**acc.metadata(), "rates": [*acc.metadata()["rates"], *ar_rates], "receivable_issues": issues}
    return result
