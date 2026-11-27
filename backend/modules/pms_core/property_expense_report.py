"""Read-only expense accrual report in the configured property currency."""
from modules.pms_core.property_reporting_currency import PropertyAccumulator, load_historical_rates
from modules.pms_core.report_money import currency_code, money, rounded
from modules.pms_core.reporting_financials import report_payment_period_match


async def property_expense_report(database, tenant_id, first, last, base):
    rows = await database.expenses.find({"tenant_id": tenant_id, "voided": {"$ne": True}, "deleted": {"$ne": True},
        "status": {"$nin": ["cancelled", "void", "voided", "deleted"]},
        **report_payment_period_match(first.isoformat(), last.isoformat(), date_fields=("business_date", "date", "expense_date", "created_at"))}, {"_id": 0}).to_list(None)
    rates = await load_historical_rates(database, tenant_id, first, last, base_currency=base,
        currencies={currency_code(row.get("currency"), base) for row in rows})
    acc, counts = PropertyAccumulator(rates), {}
    for row in rows:
        category = str(row.get("category") or "other")
        source = {**row, "currency": currency_code(row.get("currency"), base),
            "business_date": row.get("business_date") or row.get("date") or row.get("expense_date") or row.get("created_at")}
        value = row.get("total_amount") if row.get("total_amount") is not None else row.get("amount")
        acc.add("total", value, source)
        acc.add("category:"+category, value, source)
        counts[category] = counts.get(category, 0)+1
    total = acc.total("total")
    categories = {key: {"category": key, "count": count, "amount": acc.total("category:"+key),
        "by_currency": {base: acc.total("category:"+key)}, "breakdown": {}} for key, count in counts.items()}
    policy = acc.metadata()
    policy["category_rounding_difference"] = rounded(money(total)-sum((money(row["amount"]) for row in categories.values()), money(0))) if total is not None else None
    return {"reporting_currency": base, "currency": base, "start_date": first.isoformat(), "end_date": last.isoformat(),
        "total_expenses": total, "by_currency": {base: total}, "count": len(rows), "categories": categories,
        "daily_average": rounded(money(total)/((last-first).days+1)) if total is not None else None,
        "top_expense": max(categories, key=lambda key: categories[key]["amount"]) if total is not None and categories else None,
        "currency_policy": policy, "source": "expense_accruals", "amount_basis": "recorded_expense_total"}
