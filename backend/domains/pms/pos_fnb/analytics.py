"""One read-only business-day snapshot for POS and F&B analytics."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from fastapi import HTTPException

from .folio_lines import checkout_lines
from .reporting import enrich_refunds, is_refund

PAID = {"completed", "closed", "paid", "refunded", "refund"}
VOID = {"void", "voided", "cancelled", "canceled"}


async def period(db, tenant_id, first=None, last=None, days=30):
    if not last:
        settings = await db.tenant_settings.find_one({"tenant_id": tenant_id}, {"business_date": 1}) or {}
        last = settings.get("business_date") or datetime.now(UTC).date().isoformat()
    try:
        end = date.fromisoformat(str(last)[:10])
        start = date.fromisoformat(str(first)[:10]) if first else end - timedelta(days=days - 1)
        if start > end or (end - start).days > 1095:
            raise ValueError
    except (TypeError, ValueError):
        raise HTTPException(422, "Geçerli bir rapor tarih aralığı seçin (en fazla 1096 gün).") from None
    return start.isoformat(), end.isoformat()


def item_rows(rows):
    """Refund quantities/revenue use the sale snapshot, not today's menu."""
    result = []
    for row in rows:
        if row.get("status") not in PAID:
            continue
        source = row.get("source_sale") if is_refund(row) else row
        if not source:
            continue  # unknown legacy refund is a visible report warning
        paid = Decimal(str(source.get("total_amount") or source.get("amount") or 0))
        ratio = -abs(Decimal(str(row.get("total_amount") or row.get("amount") or 0))) / paid if is_refund(row) and paid else Decimal(1)
        for line in checkout_lines(source):
            result.append(
                {
                    **line,
                    "order_id": row.get("order_id") or row.get("id"),
                    "outlet_id": row.get("outlet_id") or source.get("outlet_id"),
                    "currency": source.get("currency"),
                    "date": str(row.get("transaction_date") or row.get("business_date") or row.get("created_at") or "")[:10],
                    "quantity": float(Decimal(str(line["quantity"])) * ratio),
                    "revenue": float(Decimal(str(line["total"])) * ratio),
                    "net_revenue": float(Decimal(str(line["amount"])) * ratio),
                }
            )
    return result


async def snapshot(db, tenant_id, first=None, last=None, outlet_id=None, days=30):
    from domains.pms.pos_router.pos_core import _query_pos_transactions

    start, end = await period(db, tenant_id, first, last, days)
    rows = await _query_pos_transactions(tenant_id, limit=None, start_date=start, end_date=end, outlet_id=outlet_id, database=db)
    rows, warnings = await enrich_refunds(db, tenant_id, rows)
    paid = [r for r in rows if r.get("status") in PAID]
    sales = [r for r in paid if not is_refund(r)]
    settings = await db.hotel_settings.find_one({"tenant_id": tenant_id}, {"currency": 1}) or {}
    base = str(settings.get("currency") or "TRY").upper()
    # Canonical POS currency is the sales/base currency, not tender currency.
    by_currency = {}
    for row in paid:
        code = row.get("currency") or (row.get("source_sale") or {}).get("currency") or base
        bucket = by_currency.setdefault(code, {"revenue": 0, "tips": 0, "payable": 0})
        value = Decimal(str(row.get("total_amount", row.get("grand_total", row.get("amount", 0))) or 0))
        tip = Decimal(str(row.get("tip_amount") or 0))
        bucket["payable"] += value
        bucket["tips"] += tip
        bucket["revenue"] += value - tip
    by_currency = {code: {key: round(float(value), 2) for key, value in bucket.items()} for code, bucket in by_currency.items()}
    if len(by_currency) > 1:
        warnings.append("Farklı satış para birimleri toplanmadı; para birimi kırılımını kullanın.")
    total = sum(v["revenue"] for v in by_currency.values()) if len(by_currency) <= 1 else None
    lines = item_rows(paid)
    from modules.pms_core.reporting_ledger import posted_revenue_rows
    from modules.pms_core.revenue_categories import FNB_CATEGORIES, charge_category

    revenue_rows = [
        row
        for row in await posted_revenue_rows(tenant_id, date.fromisoformat(start), date.fromisoformat(end), database=db)
        if charge_category(row) in FNB_CATEGORIES or (row.get("source_pos_order_id") and charge_category(row) == "service_charge")
    ]
    if outlet_id:
        scoped_ids = {row.get("order_id") or row.get("id") for row in rows}
        revenue_rows = [row for row in revenue_rows if row.get("outlet_id") == outlet_id or row.get("source_pos_order_id") in scoped_ids]
    # A terminal POS room transfer and its folio line are the same revenue.
    # Include manual F&B ledger charges as well, never accommodation/minibar.
    revenue_totals = {}
    for row in revenue_rows:
        code = row.get("currency") or base
        revenue_totals[code] = revenue_totals.get(code, Decimal(0)) + Decimal(str(row.get("total") or 0))
    financial_total = round(float(sum(revenue_totals.values())), 2) if len(revenue_totals) <= 1 else None
    return {
        "period": {"start_date": start, "end_date": end},
        "currency": next(iter(by_currency), next(iter(revenue_totals), base)),
        "totals_by_currency": by_currency,
        "total_revenue": round(total, 2) if total is not None else None,
        "sale_count": len(sales),
        "refund_count": len(paid) - len(sales),
        "rows": rows,
        "paid": paid,
        "sales": sales,
        "lines": lines,
        "report_warnings": warnings,
        "revenue_rows": revenue_rows,
        "financial_total": financial_total,
        "financial_by_currency": {code: round(float(value), 2) for code, value in revenue_totals.items()},
        "basis": "PMS iş günü; kesinleşmiş POS satışı − iade; vergiler dahil, bahşiş hariç. Oda aktarımı tahsilat değildir.",
    }


async def menu_statistics(db, tenant_id, data):
    catalog = await db.pos_menu_items.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(None)
    costs = {row.get("id"): row for row in catalog}
    stats = {}
    for line in data["lines"]:
        key = line.get("item_id") or line["description"]
        row = stats.setdefault(
            key,
            {
                "item_id": line.get("item_id"),
                "item_name": line["description"],
                "category": line["charge_category"],
                "quantity_sold": 0,
                "revenue": 0,
                "net_revenue": 0,
                "total_cost": 0,
                "cost_known": True,
                "orders": set(),
            },
        )
        row["quantity_sold"] += line["quantity"]
        row["revenue"] += line["revenue"]
        row["net_revenue"] += line["net_revenue"]
        row["orders"].add(line["order_id"])
        menu = costs.get(line.get("item_id")) or {}
        if menu.get("cost") is None or (menu.get("currency") and line.get("currency") and menu["currency"] != line["currency"]):
            row["cost_known"] = False
        else:
            row["total_cost"] += float(menu["cost"]) * line["quantity"]
    result = []
    for row in stats.values():
        row["orders_count"] = len(row.pop("orders"))
        for key in ("quantity_sold", "revenue", "net_revenue", "total_cost"):
            row[key] = round(row[key], 4 if key == "quantity_sold" else 2)
        row["total_cost"] = row["total_cost"] if row["cost_known"] else None
        row["gross_profit"] = round(row["net_revenue"] - row["total_cost"], 2) if row["cost_known"] else None
        row["cost_basis"] = "current_catalog" if row["cost_known"] else "unknown"
        row["avg_price"] = round(row["revenue"] / row["quantity_sold"], 2) if row["quantity_sold"] else 0
        result.append(row)
    return sorted(result, key=lambda row: (-row["revenue"], row["item_name"]))
