"""Read-only daily operations reconciliation, not a general-ledger trial balance.

Daily activity follows the selected PMS day. Open-folio and deposit positions
are explicitly current snapshots: their mutable status cannot reconstruct a
historical closing balance. No live FX or cross-currency netting is performed.
"""

import asyncio
from datetime import UTC, date, datetime

from modules.pms_core.receivable_reporting import folio_snapshots
from modules.pms_core.report_money import add_amount, currency_code, money, resolve_ledger_currencies, rounded, rounded_totals, single_amount
from modules.pms_core.reporting_financials import NON_CASH_PAYMENT_METHODS, deduplicate_report_payments, effective_collection, effective_revenue_adjustment, is_valid_payment, report_payment_day_match
from modules.pms_core.reporting_ledger import charge_amount, charge_category, posted_revenue_rows
from modules.pms_core.room_revenue_reporting import reconcile_room_revenue
from modules.pms_core.stay_night_metrics import ACTUAL_OCCUPANCY_STATUSES, as_date, booking_occupies_night, load_stay_night_metrics, stay_day_match

ROOM_CATEGORIES = {"room", "rooms", "room_charge", "accommodation", "lodging", "konaklama"}
FNB_CATEGORIES = {"fb", "fnb", "f&b", "food", "beverage", "restaurant", "bar", "minibar", "room_service", "food_beverage", "food_and_beverage"}


def _scalar_currency(totals, fallback):
    codes = [code for code, value in totals.items() if money(value) != 0]
    return codes[0] if len(codes) == 1 else (None if codes else fallback)


def daily_revenue_summary(metric_rows, charges_by_cat, *, fallback_currency="TRY"):
    """Accrue only currencies with no room posting, never resurrect a zero net."""
    categories, posted_rooms, accrued_rooms = {}, {}, {}
    for row in charges_by_cat:
        category = str(row.get("_id") or "other").strip().lower()
        code = currency_code(row.get("currency"), fallback_currency)
        if category in ROOM_CATEGORIES:
            add_amount(posted_rooms, code, row.get("total", 0))
        else:
            add_amount(categories.setdefault(category, {}), code, row.get("total", 0))
    for metric in metric_rows:
        totals = metric.get("revenue_by_currency")
        if totals is None:
            totals = {currency_code(metric.get("currency"), fallback_currency): metric.get("revenue") or 0}
        for code, value in totals.items():
            add_amount(accrued_rooms, code, value)
    occupied = sum(int(row.get("occupied_rooms") or 0) for row in metric_rows)
    sold = sum(int(row.get("sold_rooms") or 0) for row in metric_rows)
    capacity = sum(int(row.get("total_rooms") or 0) for row in metric_rows)
    rooms, sources = reconcile_room_revenue(posted_rooms, accrued_rooms, occupied)
    fnb, other = {}, {}
    for category, totals in categories.items():
        for code, value in totals.items():
            add_amount(fnb if category in FNB_CATEGORIES else other, code, value)
    total = {}
    for bucket in (rooms, fnb, other):
        for code, value in bucket.items():
            add_amount(total, code, value)
    pending = any(source == "accrued" for source in sources.values())
    source = "mixed" if pending and any(source == "posted" for source in sources.values()) else "accrued" if pending else "posted"
    result = {
        "room_revenue_source": source,
        "room_revenue_source_by_currency": sources,
        "posting_pending": pending,
        "by_category_currency": {key: rounded_totals(values) for key, values in categories.items()},
        "by_category": {key: single_amount(values) for key, values in categories.items()},
        "currency": _scalar_currency(total, fallback_currency),
        "basis": "posted_plus_unposted_room_accrual",
    }
    for key, totals in {
        "rooms": rooms,
        "posted_rooms": posted_rooms,
        "accrued_rooms": accrued_rooms,
        "fnb": fnb,
        "other": other,
        "total": total,
        "adr": {code: rounded(money(value) / sold) if sold else 0 for code, value in rooms.items()},
        "revpar": {code: rounded(money(value) / capacity) if capacity else 0 for code, value in rooms.items()},
    }.items():
        result[key] = single_amount(totals)
        result[key + "_by_currency"] = rounded_totals(totals)
    return result


async def build_daily_reconciliation(database, tenant_id: str, day: date):
    from core.tenant_currency import get_tenant_currency

    native = currency_code((await get_tenant_currency(tenant_id))[0])
    key = day.isoformat()
    postings, payments, metrics, bookings, folios, deposits, physical_rooms, audit = await asyncio.gather(
        posted_revenue_rows(tenant_id, day, day, database=database, fallback_currency=native),
        database.payments.find({"tenant_id": tenant_id, **report_payment_day_match(key)}, {"_id": 0}).to_list(None),
        load_stay_night_metrics(database, tenant_id, day, day, actual_only=True),
        database.bookings.find({"tenant_id": tenant_id, **stay_day_match(day)}, {"_id": 0}).to_list(None),
        database.folios.find({"tenant_id": tenant_id, "status": "open"}, {"_id": 0}).to_list(None),
        database.deposits.find({"tenant_id": tenant_id, "voided": {"$ne": True}, "deleted": {"$ne": True}}, {"_id": 0}).to_list(None),
        database.rooms.count_documents({"tenant_id": tenant_id, "is_active": {"$ne": False}}),
        database.night_audit_logs.find_one({"tenant_id": tenant_id}, {"_id": 0}, sort=[("created_at", -1)]),
    )
    charges = [{"_id": charge_category(row), "total": charge_amount(row), "currency": row.get("currency")} for row in postings]
    revenue = daily_revenue_summary(metrics, charges, fallback_currency=native)
    payments = deduplicate_report_payments(await resolve_ledger_currencies(payments, tenant_id, database=database, fallback_currency=native))
    payment_totals, by_method, adjustments = {}, {}, {}
    for payment in payments:
        code = payment["currency"]
        add_amount(adjustments, code, effective_revenue_adjustment(payment))
        method = str(payment.get("payment_method") or payment.get("method") or "other").strip().lower() or "other"
        if not is_valid_payment(payment) or method in NON_CASH_PAYMENT_METHODS:
            continue
        amount = effective_collection(payment)
        if not amount:
            continue
        add_amount(payment_totals, code, amount)
        bucket = by_method.setdefault(method, {"by_currency": {}, "count": 0})
        add_amount(bucket["by_currency"], code, amount)
        bucket["count"] += 1
    for bucket in by_method.values():
        bucket.update(total=single_amount(bucket["by_currency"]), currency=_scalar_currency(bucket["by_currency"], native), by_currency=rounded_totals(bucket["by_currency"]))
    net = {code: money(revenue["total_by_currency"].get(code, 0)) - money(adjustments.get(code, 0)) for code in revenue["total_by_currency"].keys() | adjustments.keys()}
    revenue.update(adjustments=single_amount(adjustments), adjustments_by_currency=rounded_totals(adjustments), net_total=single_amount(net), net_total_by_currency=rounded_totals(net))
    difference = {code: money(net.get(code, 0)) - money(payment_totals.get(code, 0)) for code in net.keys() | payment_totals.keys()}
    # Current positions come from actual folio movements, not booking.ar_balance.
    snapshots = await folio_snapshots(database, tenant_id, folios, fallback_currency=native)
    ar, deposit_totals = {}, {}
    for snap in snapshots.values():
        for code, value in snap["balance_by_currency"].items():
            if value > 0:
                add_amount(ar, code, value)
    deposits = await resolve_ledger_currencies(deposits, tenant_id, database=database, fallback_currency=native)
    for deposit in deposits:
        if str(deposit.get("status") or "received").strip().lower() in {"applied", "refunded", "void", "voided", "cancelled", "canceled", "failed", "pending", "processing"}:
            continue
        remaining = max(money(deposit.get("amount", 0)) - money(deposit.get("refunded_amount") or 0) - money(deposit.get("applied_amount") or 0), 0)
        if remaining:
            add_amount(deposit_totals, deposit["currency"], remaining)
    metric = metrics[0] if metrics else {}
    capacity = int(metric.get("total_rooms") or 0)
    occupied = int(metric.get("occupied_rooms") or 0)
    actual = [row for row in bookings if str(row.get("status") or "").strip().lower() in ACTUAL_OCCUPANCY_STATUSES]
    return {
        "date": key,
        "currency": native,
        "generated_at": datetime.now(UTC).isoformat(),
        "occupancy": {
            "total_rooms": capacity,
            "physical_rooms": physical_rooms,
            "occupied": occupied,
            "out_of_order": max(physical_rooms - capacity, 0),
            "available": max(capacity - occupied, 0),
            "occupancy_pct": metric.get("occupancy_rate", 0),
            "basis": "actual_stay_nights",
        },
        "movements": {
            "arrivals": sum(as_date(row.get("check_in")) == day for row in actual),
            "departures": sum(as_date(row.get("check_out")) == day and str(row.get("status") or "").strip().lower() == "checked_out" for row in actual),
            "no_shows": sum(as_date(row.get("check_in")) == day and str(row.get("status") or "").strip().lower() in {"no_show", "noshow"} for row in bookings),
            "in_house": sum(booking_occupies_night(row, day, actual_only=True) for row in actual),
        },
        "revenue": revenue,
        "payments": {"by_method": by_method, "total": single_amount(payment_totals), "total_by_currency": rounded_totals(payment_totals), "currency": _scalar_currency(payment_totals, native)},
        "ledger": {
            "ar_balance": single_amount(ar),
            "ar_balance_by_currency": rounded_totals(ar),
            "deposit_balance": single_amount(deposit_totals),
            "deposit_balance_by_currency": rounded_totals(deposit_totals),
            "open_folios": len(folios),
            "currency": native,
            "snapshot_scope": "current",
            "balance_basis": "posted_open_folio_ledger",
        },
        "balance_check": {
            "revenue_minus_payments": single_amount(difference),
            "by_currency": rounded_totals(difference),
            "in_balance": all(money(value) == 0 for value in rounded_totals(difference).values()),
            "basis": "net_operating_revenue_minus_collections",
        },
        "last_night_audit": {field: audit.get(field) for field in ("status", "created_at", "audit_date")} if audit else None,
    }
