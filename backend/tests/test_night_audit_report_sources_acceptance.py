"""Night-audit, Revenue and Flash must report the same real posted sources."""
from datetime import UTC, date, datetime

import pytest

from common.context import OperationContext
from domains.pms.night_audit.financial_service import FinancialService

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
pytestmark = pytest.mark.asyncio


async def test_daily_range_and_reconciliation_share_extras_refunds_dates_and_currencies(ledger_db):
    db = ledger_db
    tid, day = "qa", "2026-10-30"
    await db.hotel_settings.insert_one({"tenant_id": tid, "currency": "TRY"})
    await db.bookings.insert_one({"tenant_id": tid, "id": "b", "currency": "TRY", "total_amount": 250, "status": "checked_in"})
    await db.folio_charges.insert_many([
        {"tenant_id": tid, "id": "laundry", "booking_id": "b", "charge_category": "laundry", "total": 15, "amount": 15, "currency": "TRY", "business_date": day, "posted_at": "2026-10-31T02:00:00Z"},
        {"tenant_id": tid, "id": "euro", "charge_category": "room", "amount": 8, "tax_amount": 2, "total": 10, "currency": "EUR", "business_date": datetime(2026, 10, 30, tzinfo=UTC)},
        {"tenant_id": "other", "total": 999, "business_date": day},
    ])
    await db.extra_charges.insert_many([
        {"tenant_id": tid, "id": "spa", "booking_id": "b", "category": "spa", "total": 40, "currency": "TRY", "business_date": day},
        {"tenant_id": tid, "id": "food", "booking_id": "b", "category": "food", "total": 20, "currency": "TRY", "business_date": day},
        {"tenant_id": tid, "total": 999, "voided": True, "business_date": day},
    ])
    await db.payments.insert_many([
        {"tenant_id": tid, "id": "dep", "booking_id": "b", "amount": 70, "currency": "TRY", "method": "cash", "status": "paid", "business_date": day, "idempotency_key": "deposit"},
        {"tenant_id": tid, "id": "retry", "booking_id": "b", "amount": 70, "currency": "TRY", "method": "cash", "status": "paid", "business_date": day, "idempotency_key": "deposit"},
        {"tenant_id": tid, "id": "refund", "amount": 20, "currency": "TRY", "method": "cash", "status": "refunded", "business_date": day},
        {"tenant_id": tid, "id": "failed", "amount": 999, "currency": "TRY", "method": "cash", "status": "failed", "business_date": day},
        {"tenant_id": tid, "id": "discount", "amount": 99, "currency": "TRY", "method": "discount", "business_date": day},
    ])
    service = FinancialService(); service._db = db
    ctx = OperationContext(tenant_id=tid, actor_id="qa", actor_role="admin")
    summary = (await service.get_daily_financial_summary(ctx, day)).data
    reconciliation = (await service.get_payment_reconciliation(ctx, day)).data
    period = (await service.get_financial_report(ctx, day, day)).data
    assert summary["revenue"]["total_with_tax_by_currency"] == {"TRY": 75, "EUR": 10}
    assert summary["payments"]["total_by_currency"] == {"TRY": 50}
    assert summary["tax_unknown_count"] == 3
    assert reconciliation["charges_by_currency"] == {"TRY": 75, "EUR": 10}
    assert reconciliation["payments_by_currency"] == {"TRY": 50}
    assert period["summary"]["total_payments_by_currency"] == {"TRY": 50}
    assert period["summary"]["total_with_tax"] is None  # no fictitious TRY + EUR total
    assert summary["revenue"]["total_with_tax"] is None
    assert reconciliation["charges_total"] is None
    assert {row["date"] for row in period["revenue_by_date"]} == {day}
    assert not summary["degraded"] and not period["degraded"] and not reconciliation["degraded"]


async def test_untransferred_pos_is_included_but_room_transfer_is_not_double_counted(ledger_db):
    db = ledger_db; tid = "qa"; day = "2026-10-30"
    await db.hotel_settings.insert_one({"tenant_id": tid, "currency": "TRY"})
    await db.pos_orders.insert_many([
        {"tenant_id": tid, "id": "direct", "business_date": day, "status": "closed", "grand_total": 30, "currency": "TRY"},
        {"tenant_id": tid, "id": "room", "business_date": day, "status": "closed", "grand_total": 20, "currency": "TRY"},
    ])
    await db.folio_charges.insert_one({"tenant_id": tid, "business_date": day, "id": "room-fee", "source_pos_order_id": "room", "charge_category": "food", "total": 20, "currency": "TRY"})
    service = FinancialService(); service._db = db
    ctx = OperationContext(tenant_id=tid, actor_id="qa", actor_role="admin")
    assert (await service.get_daily_financial_summary(ctx, day)).data["revenue"]["total_with_tax_by_currency"] == {"TRY": 50}


async def test_nightly_plan_and_currency_specific_adr_survive_real_loader(ledger_db):
    from modules.pms_core.room_revenue_reporting import room_period_performance
    from modules.pms_core.stay_night_metrics import load_stay_night_metrics
    db = ledger_db
    await db.rooms.insert_many([{"tenant_id": "qa", "id": rid} for rid in ("r1", "r2", "r3")])
    await db.bookings.insert_many([{"tenant_id": "qa", "id": bid, "room_id": rid, "check_in": "2026-10-30",
        "check_out": "2026-11-01", "status": "checked_in", "currency": code, "total_amount": total}
        for bid, rid, code, total in [("a", "r1", "TRY", 250), ("b", "r2", "TRY", 200), ("c", "r3", "USD", 200)]])
    await db.daily_rates.insert_many([
        {"tenant_id": "qa", "booking_id": "a", "date": datetime(2026, 10, 30, tzinfo=UTC), "rate": 120, "currency": "TRY"},
        {"tenant_id": "qa", "booking_id": "a", "date": "2026-10-31", "rate": 130, "currency": "TRY"},
        {"tenant_id": "other", "booking_id": "a", "date": "2026-10-30", "rate": 999},
    ])
    metrics = await load_stay_night_metrics(db, "qa", date(2026, 10, 30), date(2026, 10, 31), actual_only=True)
    assert [row["revenue_by_currency"] for row in metrics] == [{"TRY": 220, "USD": 100}, {"TRY": 230, "USD": 100}]
    assert metrics[0]["adr_by_currency"] == {"TRY": 110, "USD": 100}
    assert room_period_performance(metrics[:1], {})["adr_by_currency"] == {"TRY": 110, "USD": 100}
    # Plans are operational accrual, never posted financial income.
    service = FinancialService(); service._db = db
    ctx = OperationContext(tenant_id="qa", actor_id="qa", actor_role="admin")
    assert (await service.get_daily_financial_summary(ctx, "2026-10-30")).data["revenue"]["total_with_tax"] == 0
    await db.daily_rates.insert_one({"tenant_id": "qa", "booking_id": "a", "date": "2026-10-30", "rate": 120})
    with pytest.raises(ValueError, match="Ambiguous"):
        await load_stay_night_metrics(db, "qa", date(2026, 10, 30), date(2026, 10, 30))


async def test_single_window_and_receivable_report_include_legacy_booking_extras_without_binding_or_duplication(ledger_db, monkeypatch):
    from types import SimpleNamespace

    from domains.pms import folio_window_router
    from modules.pms_core.receivable_reporting import receivable_rows
    db = ledger_db
    await db.bookings.insert_one({"tenant_id": "qa", "id": "b", "currency": "TRY"})
    await db.folios.insert_one({"tenant_id": "qa", "id": "f", "booking_id": "b", "status": "open", "currency": "TRY"})
    await db.folio_charges.insert_one({"tenant_id": "qa", "id": "laundry", "folio_id": "f", "total": 15, "currency": "TRY"})
    await db.extra_charges.insert_many([
        {"tenant_id": "qa", "id": "food", "booking_id": "b", "total": 60, "currency": "TRY"},
        {"tenant_id": "qa", "id": "void", "booking_id": "b", "total": 999, "voided": True},
        {"tenant_id": "other", "id": "foreign", "booking_id": "b", "total": 999},
    ])
    await db.payments.insert_many([{"tenant_id": "qa", "folio_id": "f", "amount": amount, "currency": "TRY", "status": status}
        for amount, status in [(80, "paid"), (20, "refunded")]])
    monkeypatch.setattr(folio_window_router, "db", db)
    windows = await folio_window_router.list_windows("b", SimpleNamespace(tenant_id="qa"), None)
    assert (windows[0].balance, windows[0].charges_count, windows[0].payments_count) == (15, 2, 2)
    report = await receivable_rows(db, "qa", date(2026, 10, 30), fallback_currency="TRY")
    assert report[0]["balance"] == 15
    service = FinancialService(); service._db = db
    summary = (await service.get_daily_financial_summary(OperationContext(tenant_id="qa", actor_id="qa", actor_role="admin"), "2026-10-30")).data
    assert summary["open_folios"]["balance"]["total"] == 15
    assert summary["open_folios"]["items"][0]["balance"] == 15
    assert not (await db.extra_charges.find_one({"id": "food"})).get("folio_id")  # read-only
    await db.folios.insert_one({"tenant_id": "qa", "id": "second", "booking_id": "b", "status": "open", "currency": "TRY"})
    windows = await folio_window_router.list_windows("b", SimpleNamespace(tenant_id="qa"), None)
    assert {w.folio_id: w.balance for w in windows} == {"f": -45, "second": 0}  # no guessed payer
