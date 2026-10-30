"""Night-audit reports consume the same immutable sources as Revenue/Flash."""
from datetime import date

from modules.pms_core.report_money import resolve_ledger_currencies
from modules.pms_core.reporting_financials import (
    NON_CASH_PAYMENT_METHODS,
    deduplicate_report_payments,
    effective_collection,
    is_valid_payment,
    report_payment_period_match,
)
from modules.pms_core.reporting_ledger import charge_amount, charge_category, posted_revenue_rows
from modules.pms_core.revenue_report import charge_breakdown, revenue_day


async def revenue_rows(database, tenant_id, first, last):
    rows = await posted_revenue_rows(tenant_id, date.fromisoformat(first), date.fromisoformat(last), database=database)
    return [{**row, "charge_category": charge_category(row), "total": charge_amount(row)} for row in rows]


async def payment_rows(database, tenant_id, first, last):
    rows = await database.payments.find({"tenant_id": tenant_id, **report_payment_period_match(first, last)}, {"_id": 0}).to_list(None)
    rows = [row for row in deduplicate_report_payments(rows) if is_valid_payment(row)
            and str(row.get("method") or row.get("payment_method") or "").strip().lower() not in NON_CASH_PAYMENT_METHODS]
    rows = await resolve_ledger_currencies(rows, tenant_id, database=database)
    return [{**row, "amount": effective_collection(row)} for row in rows]


async def revenue_documents(database, tenant_id, first, last, *, by_date=False):
    grouped = {}
    for row in await revenue_rows(database, tenant_id, first, last):
        values = charge_breakdown(row)
        code = row["currency"]
        day = revenue_day(row)
        if day is None:
            raise ValueError("Revenue accounting date could not be resolved")
        key = (day.isoformat() if by_date else None, values["category"], code)
        group_id = {"category": values["category"], "currency": code}
        if by_date:
            group_id["date"] = day.isoformat()
        entry = grouped.setdefault(key, {"_id": group_id, "amount": 0, "tax": 0, "total": 0, "count": 0, "tax_unknown_count": 0,
            "tax_breakdown": {"vat": 0, "accommodation_tax": 0, "other_tax": 0}, "tax_breakdown_incomplete_count": 0})
        tax = sum(float(values.get(field) or 0) for field in ("vat", "city_tax", "other_tax"))
        gross = float(values["total"])
        entry["amount"] += gross - tax
        entry["tax"] += tax
        entry["total"] += gross
        entry["count"] += 1
        entry["tax_unknown_count"] += int(values["tax_unknown"])
        # Carry the same component evidence as the category report. A separate
        # folio-only aggregate loses extras/POS, BSON dates and refund signs.
        components = {"vat": values["vat"], "accommodation_tax": values["city_tax"], "other_tax": values["other_tax"]}
        entry["tax_breakdown_incomplete_count"] += int(any(value is None for value in components.values()))
        for component, value in components.items():
            current = entry["tax_breakdown"][component]
            entry["tax_breakdown"][component] = None if value is None or current is None else round(current + float(value), 2)
    return [{**entry, "total_amount": entry["amount"], "total_tax": entry["tax"], "total_with_tax": entry["total"]} for entry in grouped.values()]


async def payment_documents(database, tenant_id, first, last):
    grouped = {}
    for row in await payment_rows(database, tenant_id, first, last):
        method = row.get("payment_method") or row.get("method") or "other"
        key = (method, row["currency"])
        entry = grouped.setdefault(key, {"_id": {"method": method, "currency": row["currency"]}, "total_amount": 0, "total": 0, "count": 0})
        entry["total_amount"] += row["amount"]
        entry["total"] += row["amount"]
        entry["count"] += 1
    return list(grouped.values())


async def open_balance_documents(database, tenant_id):
    from modules.pms_core.receivable_reporting import folio_snapshots
    folios = await database.folios.find({"tenant_id": tenant_id, "status": "open"}, {"_id": 0}).to_list(None)
    snapshots = await folio_snapshots(database, tenant_id, folios, fallback_currency="TRY", include_booking_extras=True)
    grouped = {}
    for snap in snapshots.values():
        balances = snap["balance_by_currency"] or {snap["currency"]: 0}
        for index, (code, amount) in enumerate(sorted(balances.items())):
            entry = grouped.setdefault(code, {"_id": {"currency": code}, "total_balance": 0, "positive_balance": 0,
                "negative_balance": 0, "count": 0, "receivable_count": 0, "overpayment_count": 0, "folios": []})
            entry["total_balance"] += amount
            entry["positive_balance"] += max(amount, 0)
            entry["negative_balance"] += min(amount, 0)
            entry["count"] += int(index == 0)  # a multi-currency folio is still one account
            entry["receivable_count"] += int(amount > 0)
            entry["overpayment_count"] += int(amount < 0)
            entry["folios"].append({**snap["folio"], "balance": amount, "currency": code})
    return list(grouped.values())
