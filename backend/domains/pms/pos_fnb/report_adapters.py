"""Compatibility response shapes over one canonical, read-only POS snapshot."""

from collections import Counter
from datetime import date, timedelta

from modules.pms_core.revenue_categories import charge_category
from modules.pms_core.revenue_report import revenue_day

from .analytics import menu_statistics, snapshot


async def report(db, tenant_id, kind, first=None, last=None, outlet_id=None, days=30):
    data = await snapshot(db, tenant_id, first, last, outlet_id, days)
    common = {key: data[key] for key in ("period", "currency", "totals_by_currency", "report_warnings", "basis")}
    common["financial_by_currency"] = data["financial_by_currency"]
    if len(set(data["totals_by_currency"]) | set(data["financial_by_currency"])) > 1:
        common.update(requires_currency_selection=True)
        common["report_warnings"] = list(dict.fromkeys([*common["report_warnings"], "Farklı satış para birimleri toplanmadı; para birimi kırılımını kullanın."]))
        summary = dict.fromkeys(
            ("total_sales", "total_revenue", "total_food", "total_beverage", "food_sales", "beverage_sales", "total_cost", "gross_profit", "profit_margin", "food_revenue", "beverage_revenue")
        )
        summary.update(orders_count=data["sale_count"], total_transactions=data["sale_count"])
        return {
            **common,
            "summary": summary,
            "orders": {"total_count": data["sale_count"], "total_revenue": None, "by_outlet": {}, "by_status": {}},
            "stock_consumption": {"total_cost": None, "item_count": None, "cost_verified": False},
            "profitability": {"revenue": None, "cost": None, "gross_profit": None, "profit_margin_percentage": None},
            "total_revenue": None,
            "total_items": 0,
            "menu_items": [],
            "top_performers": [],
            "bottom_performers": [],
            "daily_sales": [],
            "chart_data": [],
            "by_category": [],
            "by_outlet": [],
            "totals": {"items": 0, "units_sold": 0, "revenue": None, "contribution_margin": None},
            "stars": 0,
            "plowhorses": 0,
            "puzzles": 0,
            "dogs": 0,
            "unknown": 0,
            "thresholds": {"popularity_pct": None, "avg_cm_per_unit": None},
        }
    if kind in {"sales", "dashboard", "chart"}:
        daily = {}
        for row in data["revenue_rows"]:
            day = revenue_day(row).isoformat()
            bucket = daily.setdefault(day, {"date": day, "food": 0, "beverage": 0, "other": 0, "total": 0})
            category = charge_category(row)
            key = "beverage" if category in {"beverage", "alcohol"} else "food" if category == "food" else "other"
            value = float(row.get("total") or 0)
            bucket[key] += value
            bucket["total"] += value
        daily = [{key: round(value, 2) if isinstance(value, float) else value for key, value in row.items()} for _, row in sorted(daily.items())]
        food = round(sum(row["food"] for row in daily), 2)
        beverage = round(sum(row["beverage"] for row in daily), 2)
        other = round(sum(row["other"] for row in daily), 2)
        total = data["financial_total"]
        if len(data["financial_by_currency"]) > 1:
            food = beverage = other = None  # Never add incompatible currencies.
        if kind == "sales":
            return {
                **common,
                "summary": {
                    "total_sales": total,
                    "food_sales": food,
                    "beverage_sales": beverage,
                    "other_sales": other,
                    "food_percentage": round(food / total * 100, 2) if total and food is not None else 0,
                    "beverage_percentage": round(beverage / total * 100, 2) if total and beverage is not None else 0,
                },
                "daily_sales": daily,
            }
        if kind == "chart":
            start, end = (date.fromisoformat(data["period"][key]) for key in ("start_date", "end_date"))
            by_day = {row["date"]: row for row in daily}
            chart = [
                by_day.get((start + timedelta(days=i)).isoformat(), {"date": (start + timedelta(days=i)).isoformat(), "food": 0, "beverage": 0, "other": 0, "total": 0})
                for i in range((end - start).days + 1)
            ]
            return {**common, "chart_data": chart, "summary": {"total_food": food, "total_beverage": beverage, "total_revenue": total}}
        previous = (date.fromisoformat(data["period"]["start_date"]) - timedelta(days=1)).isoformat()
        prior = await snapshot(db, tenant_id, previous, previous)
        previous_total = prior["financial_total"]
        return {
            **common,
            "date": data["period"]["end_date"],
            "summary": {
                "total_revenue": total,
                "food_revenue": food,
                "beverage_revenue": beverage,
                "other_revenue": other,
                "orders_count": data["sale_count"],
                "refund_count": data["refund_count"],
                "avg_order_value": round(total / data["sale_count"], 2) if total is not None and data["sale_count"] else 0,
                "tables_used": len({r.get("order_snapshot", {}).get("table_number") or r.get("table_number") for r in data["sales"]} - {None}),
                "revenue_change": round((total - previous_total) / previous_total * 100, 2) if total is not None and previous_total else 0,
            },
        }
    if kind == "mobile":
        ids = [row.get("order_id") or row.get("id") for row in data["sales"]]
        consumed = await db.stock_consumptions.find({"tenant_id": tenant_id, "order_id": {"$in": ids}, "reversed": {"$ne": True}}, {"_id": 0}).to_list(None)
        cost = round(sum(float(row["cost"]) for row in consumed), 2) if all(row.get("cost") is not None for row in consumed) else None
        if (data["sales"] and not consumed) or data["refund_count"]:
            cost = None  # Missing consumption or refund cost attribution is not verified zero cost.
        total = data["financial_total"]
        grouped = {}
        for row in data["sales"]:
            key = row.get("outlet_id") or "unassigned"
            grouped.setdefault(key, {"count": 0, "revenue": 0})["count"] += 1
        for row in data["revenue_rows"]:
            key = row.get("outlet_id") or "unassigned"
            grouped.setdefault(key, {"count": 0, "revenue": 0})["revenue"] += float(row.get("total") or 0)
        for bucket in grouped.values():
            bucket["revenue"] = round(bucket["revenue"], 2)
        from modules.pms_core.revenue_report import charge_breakdown

        values = [charge_breakdown(row) for row in data["revenue_rows"]]
        net = round(sum(float(value["net"]) for value in values), 2) if all(value["net"] is not None and not value["issues"] for value in values) else None
        return {
            **common,
            "date": data["period"]["end_date"],
            "orders": {
                "total_count": data["sale_count"],
                "total_revenue": total,
                "by_outlet": grouped,
                "by_status": dict(Counter(row.get("status") for row in data["rows"])),
                "average_order_value": round(total / data["sale_count"], 2) if total is not None and data["sale_count"] else 0,
            },
            "stock_consumption": {"total_cost": cost, "item_count": len(consumed), "cost_verified": cost is not None},
            "profitability": {
                "revenue": total,
                "cost": cost,
                "net_revenue": net,
                "profit_basis": "Vergi hariç net gelir − doğrulanabilen stok maliyeti; eksik kaynak sıfır maliyet değildir.",
                "gross_profit": round(net - cost, 2) if net is not None and cost is not None else None,
                "profit_margin_percentage": round((net - cost) / net * 100, 2) if net and cost is not None else None,
            },
        }
    items = await menu_statistics(db, tenant_id, data)
    if kind == "performance":
        return {**common, "total_items": len(items), "total_revenue": data["total_revenue"], "top_performers": items[:10], "bottom_performers": items[-5:] if len(items) > 5 else []}
    if kind == "breakdown":
        outlet_rows = await db.pos_outlets.find({"tenant_id": tenant_id}, {"id": 1, "outlet_name": 1}).to_list(None)
        names = {row["id"]: row.get("outlet_name") or row["id"] for row in outlet_rows}
        cats, outlets = {}, {}
        for line in data["lines"]:
            key = line["charge_category"]
            cats[key] = cats.get(key, 0) + line["revenue"]
            key = line.get("outlet_id") or "unassigned"
            outlets[key] = outlets.get(key, 0) + line["revenue"]
        cost = round(sum(row["total_cost"] for row in items), 2) if all(row["total_cost"] is not None for row in items) else None
        net = round(sum(row["net_revenue"] for row in items), 2)
        return {
            **common,
            "date_range": f"{data['period']['start_date']} to {data['period']['end_date']}",
            "menu_items": [{**row, "total_revenue": row["revenue"]} for row in items],
            "by_category": [{"category": key, "revenue": round(value, 2)} for key, value in sorted(cats.items())],
            "by_outlet": [{"outlet_id": key, "outlet_name": names.get(key, key), "revenue": round(value, 2)} for key, value in sorted(outlets.items())],
            "summary": {
                "total_transactions": data["sale_count"],
                "total_revenue": data["total_revenue"],
                "total_cost": cost,
                "gross_profit": round(net - cost, 2) if cost is not None else None,
                "profit_margin": round((net - cost) / net * 100, 1) if cost is not None and net else None,
                "cost_basis": "current_catalog; historical profitability is not asserted",
            },
        }
    # Menu engineering: no invented 35% cost when source cost is unavailable.
    positive = [row for row in items if row["quantity_sold"] > 0]
    units = sum(row["quantity_sold"] for row in positive)
    known = [row for row in positive if row["gross_profit"] is not None]
    margin = sum(row["gross_profit"] for row in known)
    known_units = sum(row["quantity_sold"] for row in known)
    threshold = margin / known_units if known_units else 0
    popularity = 70 / len(positive) if positive else 0
    counts = Counter()
    for row in positive:
        row["menu_category"] = row["category"]
        pop = row["quantity_sold"] / units * 100
        cm = row["gross_profit"] / row["quantity_sold"] if row["gross_profit"] is not None else None
        if cm is None:
            group = "Unknown"
        elif pop >= popularity:
            group = "Stars" if cm >= threshold else "Plowhorses"
        else:
            group = "Puzzles" if cm >= threshold else "Dogs"
        counts[group] += 1
        row.update(
            category=group,
            classification=group,
            popularity_pct=round(pop, 2),
            contribution_margin=row["gross_profit"],
            cm_per_unit=round(cm, 2) if cm is not None else None,
            unit_price=row["avg_price"],
            unit_cost=round(row["total_cost"] / row["quantity_sold"], 2) if row["total_cost"] is not None else None,
            profit_margin=round(row["gross_profit"] / row["net_revenue"] * 100, 1) if row["gross_profit"] is not None and row["net_revenue"] else None,
            recommendation="Maliyet güncel katalogdan; geçmiş kârlılık doğrulaması değildir." if cm is not None else "Ürün maliyetini tanımlayın.",
        )
    return {
        **common,
        "outlet_id": outlet_id,
        "menu_items": positive,
        **{key.lower(): counts[key] for key in ("Stars", "Plowhorses", "Puzzles", "Dogs", "Unknown")},
        "thresholds": {"popularity_pct": round(popularity, 2), "avg_cm_per_unit": round(threshold, 2)},
        "totals": {"items": len(positive), "units_sold": units, "revenue": data["total_revenue"], "contribution_margin": round(margin, 2) if len(known) == len(positive) else None},
        "cost_estimation_used": bool(positive),
        "cost_estimated_items": len(known),
        "cost_basis": "current_catalog",
    }
