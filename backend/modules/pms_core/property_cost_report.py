"""Property-currency management cost view without inventing historical FX."""
from modules.pms_core.property_report_projections import property_revenue_kpis
from modules.pms_core.property_reporting_currency import PropertyAccumulator
from modules.pms_core.report_money import currency_code, money, rounded
from modules.pms_core.reporting_ledger import charge_amount

CATEGORIES = {"cleaning": "Housekeeping", "linens": "Housekeeping", "amenities": "Housekeeping",
    "food": "F&B", "beverage": "F&B", "kitchen": "F&B", "maintenance": "Technical",
    "electrical": "Technical", "plumbing": "Technical", "hvac": "Technical"}
CATEGORY_KEYS = {"housekeeping": "Housekeeping", "fnb": "F&B", "technical": "Technical", "general_expenses": "General Expenses"}


def property_cost_report(orders, charges, metrics, first, last, rates):
    acc = PropertyAccumulator(rates)
    base = rates.currency
    for row in orders:
        category = CATEGORIES.get(str(row.get("category") or "other").strip().lower(), "General Expenses")
        source = {**row, "currency": currency_code(row.get("currency"), base)}
        value = row.get("total_amount")
        acc.add("cost", value, source)
        acc.add("category:"+category, value, source)
    for row in charges:
        acc.add("revenue", charge_amount(row), row)
    cost, revenue = acc.total("cost"), acc.total("revenue")
    nights = sum(day["occupied_rooms"] for day in metrics)
    kpis = property_revenue_kpis(charges, metrics, first, last, rates)
    revpar = kpis["rev_par_by_currency"][base]
    cost_per_room = rounded(money(cost)/nights) if cost is not None and nights else 0 if cost is not None else None
    profit = rounded(money(revenue)-money(cost)) if cost is not None and revenue is not None else None
    margin = round(float(money(profit)/money(revenue)*100), 1) if profit is not None and revenue else 0 if profit is not None else None
    ratio = round(float(money(cost)/money(revenue)*100), 1) if cost is not None and revenue else 0 if cost is not None and revenue is not None else None
    category_amounts = {name: acc.total("category:"+name) for name in CATEGORY_KEYS.values()}
    top = sorted([{"name": name, "amount": value} for name, value in category_amounts.items() if value is not None], key=lambda row: row["amount"], reverse=True)[:3] if cost is not None else []
    financial = {"mtd_costs": cost, "mtd_revenue": revenue, "gross_profit": profit,
        "profit_margin_percentage": margin, "cost_to_revenue_ratio": ratio}
    return {"report_date": last.isoformat(), "period": f"{first.isoformat()} to {last.isoformat()}",
        "currency": base, "reporting_currency": base, "mixed_currency": False,
        "currency_policy": acc.metadata(), "kpi_currency_policy": kpis["currency_policy"],
        "amount_basis": "purchase_order_totals_and_posted_gross_revenue; RevPAR uses tax-exclusive posted room revenue",
        "total_mtd_costs": cost, "total_mtd_costs_by_currency": {base: cost},
        "cost_categories_by_currency": {name: {base: value} for name, value in category_amounts.items()},
        "cost_categories": {key: category_amounts[name] for key, name in CATEGORY_KEYS.items()},
        "top_3_categories": [{**row, "percentage": round(float(money(row["amount"])/money(cost)*100), 1) if cost else 0} for row in top],
        "top_3_categories_by_currency": {base: top},
        "per_room_metrics": {"total_room_nights": nights, "cost_per_room_night": cost_per_room,
            "cost_per_room_night_by_currency": {base: cost_per_room}, "mtd_revpar": revpar,
            "mtd_revpar_by_currency": {base: revpar},
            "cost_to_revpar_ratio": round(cost_per_room/revpar*100, 1) if cost_per_room is not None and revpar else 0 if cost_per_room is not None and revpar is not None else None},
        "financial_metrics": {**financial, "by_currency": {base: financial}}}
