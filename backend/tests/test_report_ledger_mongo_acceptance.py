"""Isolated Mongo acceptance. Runs in CI and never uses a non-local server."""
import os
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from modules.pms_core.report_money import add_amount, rounded_totals
from routers.reports_pkg.standard_reports import _posted_revenue_rows


@pytest.fixture
async def ledger_db():
    uri = os.environ.get("REPORT_AUDIT_MONGO_URL") or os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017/")
    parsed = urlsplit(uri)
    # 27989 is the dedicated isolated minibar/readiness replica, not a live DB.
    if parsed.scheme != "mongodb" or parsed.hostname not in {"127.0.0.1", "localhost"} or parsed.port not in {27017, 27987, 27989} or "," in parsed.netloc:
        pytest.fail("Report acceptance tests only permit a local Mongo server")
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=2000, directConnection=True)
    name = "report_audit_acceptance_" + uuid4().hex
    database = client[name]
    try:
        yield database
    finally:
        await client.drop_database(name)
        client.close()


def totals(rows):
    result = {}
    for row in rows:
        add_amount(result, row.get("currency"), row.get("total"))
    return rounded_totals(result)


async def test_real_mongo_postings_refunds_date_precedence_and_tenant_scope(ledger_db):
    db = ledger_db
    await db.folio_charges.insert_many([
        {"tenant_id": "A", "business_date": "2026-10-01", "date": "2026-10-02T02:00:00Z", "total": 50, "currency": "EUR"},
        {"tenant_id": "A", "date": "2026-10-01", "created_at": "2026-10-02", "total": 30, "currency": "TRY"},
        {"tenant_id": "A", "business_date": "", "created_at": "2026-10-01", "total": 5, "currency": "EUR"},
        {"tenant_id": "A", "business_date": "2026-10-01", "total": 999, "voided": True},
        {"tenant_id": "A", "business_date": "2026-10-01", "total": 42, "currency": "TRY", "source_pos_order_id": "room"},
        {"tenant_id": "B", "business_date": "2026-10-01", "total": 999999},
    ])
    await db.extra_charges.insert_one({"tenant_id": "A", "date": "2026-10-01", "total": 7, "currency": "TRY"})
    await db.pos_orders.insert_many([
        {"tenant_id": "A", "id": "direct", "business_date": "2026-10-01", "closed_at": "2026-10-02", "status": "closed", "grand_total": 24, "currency": "TRY"},
        {"tenant_id": "A", "id": "open", "business_date": "2026-10-01", "status": "pending", "grand_total": 1000},
        {"tenant_id": "A", "id": "free", "business_date": "2026-10-01", "status": "closed", "grand_total": 0, "total_amount": 20, "currency": "TRY"},
        {"tenant_id": "A", "id": "settled", "business_date": "2026-10-01", "status": "closed", "grand_total": 100, "currency": "EUR"},
        {"tenant_id": "A", "id": "room", "business_date": "2026-10-01", "status": "closed", "grand_total": 42, "currency": "TRY"},
    ])
    sale = {"tenant_id": "A", "id": "sale", "order_id": "settled", "transaction_date": "2026-10-01", "status": "completed", "total_amount": 110, "tip_amount": 10, "currency": "EUR"}
    await db.pos_transactions.insert_many([sale,
        {"tenant_id": "A", "id": "refund", "order_id": "settled", "transaction_date": "2026-10-02", "status": "refunded", "total_amount": -55, "tip_amount": -5},
        {"tenant_id": "A", "id": "room-tx", "order_id": "room", "transaction_date": "2026-10-01", "status": "completed", "total_amount": 42, "currency": "TRY", "payment_method": "room_charge"},
    ])
    await db.pos_menu_transactions.insert_one({**sale, "id": "mirror"})
    await db.transactions.insert_one({"tenant_id": "A", "transaction_date": "2026-10-01", "status": "completed", "category": "other", "total_amount": 999999})
    assert totals(await _posted_revenue_rows("A", date(2026, 10, 1), date(2026, 10, 1), database=db)) == {"EUR": 155, "TRY": 103}
    assert totals(await _posted_revenue_rows("A", date(2026, 10, 2), date(2026, 10, 2), database=db)) == {"EUR": -50}
    assert totals(await _posted_revenue_rows("A", date(2026, 10, 1), date(2026, 10, 2), database=db)) == {"EUR": 105, "TRY": 103}


async def test_real_mongo_legacy_bson_dates_do_not_get_lost_or_moved_to_creation_day(ledger_db):
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "date": datetime(2026, 10, 1, 10, tzinfo=UTC), "created_at": datetime(2026, 10, 2, tzinfo=UTC), "total": 19.99, "currency": "EUR"})
    assert totals(await _posted_revenue_rows("A", date(2026, 10, 1), date(2026, 10, 1), database=ledger_db)) == {"EUR": 19.99}
    assert await _posted_revenue_rows("A", date(2026, 10, 2), date(2026, 10, 2), database=ledger_db) == []


async def test_real_mongo_all_reports_resolve_the_same_legacy_currency_and_posting_date(ledger_db):
    from modules.pms_core.report_money import resolve_ledger_currencies
    await ledger_db.folios.insert_many([{"tenant_id": "A", "id": "f", "booking_id": "b", "currency": "EUR"},
        {"tenant_id": "B", "id": "f", "currency": "TRY"}])
    await ledger_db.bookings.insert_one({"tenant_id": "A", "id": "b", "currency": "USD"})
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "folio_id": "f", "posted_at": "2026-10-01", "created_at": "2026-10-02", "total": 100})
    assert totals(await _posted_revenue_rows("A", date(2026, 10, 1), date(2026, 10, 1), database=ledger_db)) == {"EUR": 100}
    assert await _posted_revenue_rows("A", date(2026, 10, 2), date(2026, 10, 2), database=ledger_db) == []
    payments = await resolve_ledger_currencies([{"folio_id": "f", "amount": 50}, {"booking_id": "b", "amount": 20}], "A", database=ledger_db)
    assert [row["currency"] for row in payments] == ["EUR", "USD"]


async def test_real_mongo_bson_business_day_never_moves_revenue_or_cash_to_wall_clock_day(ledger_db):
    from modules.pms_core.reporting_financials import report_payment_day_match
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "business_date": datetime(2026, 10, 1, tzinfo=UTC), "created_at": "2026-10-02", "total": 100, "currency": "EUR"})
    await ledger_db.payments.insert_one({"tenant_id": "A", "business_date": datetime(2026, 10, 1, tzinfo=UTC), "processed_at": "2026-10-02", "amount": 50, "currency": "EUR"})
    assert totals(await _posted_revenue_rows("A", date(2026, 10, 1), date(2026, 10, 1), database=ledger_db)) == {"EUR": 100}
    assert await _posted_revenue_rows("A", date(2026, 10, 2), date(2026, 10, 2), database=ledger_db) == []
    assert await ledger_db.payments.count_documents(report_payment_day_match("2026-10-01")) == 1
    assert await ledger_db.payments.count_documents(report_payment_day_match("2026-10-02")) == 0


async def test_real_mongo_flash_does_not_turn_unposted_reservations_into_income_and_keeps_cancelled_details(ledger_db, monkeypatch):
    from routers.reports_pkg import flash_email
    await ledger_db.bookings.insert_many([
        {"tenant_id": "A", "check_in": "2026-10-01", "check_out": "2026-10-02", "status": "confirmed", "total_amount": 99999},
        {"tenant_id": "A", "check_in": "2026-10-01", "check_out": "2026-10-02", "status": "no_show"},
        {"tenant_id": "A", "check_in": "2026-10-03", "check_out": "2026-10-04", "status": "cancelled", "updated_at": datetime(2026, 10, 1, 10, tzinfo=UTC)},
        {"tenant_id": "B", "status": "cancelled", "updated_at": datetime(2026, 10, 1, 10, tzinfo=UTC)},
    ])
    monkeypatch.setattr(flash_email, "db", ledger_db)
    monkeypatch.setattr(flash_email, "load_stay_night_metrics", AsyncMock(return_value=[{"occupied_rooms": 0, "sold_rooms": 0, "total_rooms": 10, "occupancy_rate": 0}]))
    report = await flash_email.get_flash_report.__wrapped__("2026-10-01", SimpleNamespace(tenant_id="A"))
    assert report["revenue"]["total"] == 0
    assert report["operations"]["no_shows"] == 1
    assert report["operations"]["cancellations"] == 1
    assert len(report["attention_details"]["cancellations"]) == 1


async def test_real_mongo_custom_folio_report_deduplicates_refunds_and_keeps_ledger_currencies(ledger_db, monkeypatch):
    from routers import report_builder as builder
    db = ledger_db
    await db.folios.insert_one({"id": "f", "tenant_id": "A", "currency": "EUR", "booking_id": "b"})
    await db.bookings.insert_one({"id": "b", "tenant_id": "A", "currency": "TRY"})
    await db.folio_charges.insert_many([
        {"tenant_id": "A", "folio_id": "f", "total": 100},
        {"tenant_id": "A", "folio_id": "f", "total": 0, "amount": 999},
        {"tenant_id": "A", "folio_id": "f", "charge_amount": 20, "currency": "USD"},
        {"tenant_id": "B", "folio_id": "f", "total": 99999},
    ])
    payment = {"tenant_id": "A", "folio_id": "f", "amount": 40, "idempotency_key": "paid", "status": "paid"}
    await db.payments.insert_many([payment, {**payment, "id": "retry"},
        {"tenant_id": "A", "folio_id": "f", "amount": 5, "method": "discount"},
        {"tenant_id": "A", "folio_id": "f", "amount": 10, "payment_type": " REFUND "},
        {"tenant_id": "A", "folio_id": "f", "amount": 999, "status": " CANCELED "},
        {"tenant_id": "B", "folio_id": "f", "amount": 99999},
    ])
    monkeypatch.setattr(builder, "_db", db)
    config = builder.ReportConfig(data_source="folios", columns=["total_charges", "total_payments", "balance", "currency"])
    rows = await builder.fetch_report_data(config, "A", True)
    assert rows == [
        {"total_charges": 100, "total_payments": 35, "balance": 65, "currency": "EUR"},
        {"total_charges": 20, "total_payments": 0, "balance": 20, "currency": "USD"},
    ]


async def test_real_mongo_custom_report_currency_follows_folio_then_booking_then_property(ledger_db, monkeypatch):
    from routers import report_builder as builder
    await ledger_db.folios.insert_one({"id": "f", "tenant_id": "A", "booking_id": "b", "currency": "EUR"})
    await ledger_db.bookings.insert_one({"id": "b", "tenant_id": "A", "room_id": "r", "currency": "USD"})
    await ledger_db.rooms.insert_one({"id": "r", "tenant_id": "A", "room_number": "101"})
    await ledger_db.folio_charges.insert_many([
        {"tenant_id": "A", "folio_id": "f", "total": 100, "business_date": "2026-10-01"},
        {"tenant_id": "A", "booking_id": "b", "total": 20, "business_date": "2026-10-01"},
        {"tenant_id": "A", "total": 30, "business_date": "2026-10-01"},
    ])
    monkeypatch.setattr(builder, "_db", ledger_db)
    config = builder.ReportConfig(data_source="revenue", columns=["total", "room_number", "currency"])
    rows = await builder.fetch_report_data(config, "A", True, default_currency="GBP")
    assert {(row["total"], row["currency"]) for row in rows} == {(100, "EUR"), (20, "USD"), (30, "GBP")}
    assert next(row for row in rows if row["total"] == 100)["room_number"] == "101"


async def test_real_mongo_eod_uses_full_posted_ledger_and_valid_deduplicated_collections(ledger_db, monkeypatch):
    from routers import eod_report
    db = ledger_db
    await db.folio_charges.insert_many([
        {"tenant_id": "A", "business_date": "2026-10-01", "total": 100, "currency": "EUR"},
        {"tenant_id": "A", "date": datetime(2026, 10, 1, tzinfo=UTC), "total": 0, "amount": 999, "currency": "EUR"},
        {"tenant_id": "B", "business_date": "2026-10-01", "total": 99999},
    ])
    await db.extra_charges.insert_one({"tenant_id": "A", "date": "2026-10-01", "total": 20, "amount": 10, "currency": "USD"})
    await db.pos_orders.insert_one({"tenant_id": "A", "id": "pos", "business_date": "2026-10-01", "status": "closed", "grand_total": 30, "currency": "EUR"})
    await db.pos_transactions.insert_one({"tenant_id": "A", "id": "refund", "business_date": "2026-10-01", "status": "refunded", "total_amount": -5, "currency": "USD"})
    await db.folios.insert_one({"tenant_id": "A", "id": "f", "currency": "EUR", "booking_id": "b", "status": "open"})
    await db.bookings.insert_many([
        {"tenant_id": "A", "id": "b", "currency": "TRY", "status": "confirmed", "check_in": datetime(2026, 10, 1, tzinfo=UTC)},
        {"tenant_id": "A", "status": "canceled", "check_in": "2026-12-01", "cancelled_at": datetime(2026, 10, 1, tzinfo=UTC)},
    ])
    payment = {"tenant_id": "A", "folio_id": "f", "amount": 50, "method": "cash", "idempotency_key": "same", "processed_at": datetime(2026, 10, 1, tzinfo=UTC)}
    await db.payments.insert_many([payment, {**payment, "id": "retry"},
        {"tenant_id": "A", "amount": 10, "method": "cash", "payment_type": "refund", "currency": "USD", "date": "2026-10-01"},
        {"tenant_id": "A", "amount": 5, "method": "discount", "currency": "EUR", "payment_date": "2026-10-01"},
        {"tenant_id": "A", "amount": 99999, "method": "cash", "status": " CANCELED ", "payment_date": "2026-10-01"},
        {"tenant_id": "A", "amount": 99999, "business_date": "2026-09-30", "processed_at": "2026-10-01"},
    ])
    monkeypatch.setattr(eod_report, "db", db)
    monkeypatch.setattr(eod_report, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    monkeypatch.setattr(eod_report, "load_stay_night_metrics", AsyncMock(return_value=[{"occupied_rooms": 0, "total_rooms": 10, "occupancy_rate": 0}]))
    await db.night_audit_runs.insert_many([
        {"tenant_id": "A", "id": "live", "business_date": "2026-10-01", "status": "completed", "created_at": "2026-10-02", "dry_run": False},
        {"tenant_id": "A", "id": "simulation", "business_date": "2026-10-01", "status": "failed", "created_at": "2026-10-03", "dry_run": True},
        {"tenant_id": "B", "id": "other-tenant", "business_date": "2026-10-01", "status": "failed", "created_at": "2026-10-04"},
    ])
    result = await eod_report._collect("A", "2026-10-01")
    assert result["audit_status"] == "completed" and result["audit_run_id"] == "live"
    assert result["revenue_by_currency"] == {"EUR": 125, "USD": 15}
    assert result["extras_by_currency"] == {"USD": 20}
    assert result["payments_by_currency"] == {"EUR": 50, "USD": -10}
    assert result["cash_total"] is None and result["payments_total"] is None and result["revenue_total"] is None
    assert result["arrivals"] == 1 and result["cancels"] == 1
    assert result["revenue_basis"] == "posted_ledger"


async def test_real_mongo_forecast_horizon_dates_currency_and_actual_history(ledger_db, monkeypatch):
    from domains.revenue import forecast_router as forecast

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 18, 12, tzinfo=UTC)

    monkeypatch.setattr(forecast, "datetime", Clock)
    monkeypatch.setattr(forecast, "get_system_db", lambda: ledger_db)
    monkeypatch.setattr(forecast, "get_tenant_currency", AsyncMock(return_value=("EUR", "€")))
    await ledger_db.rooms.insert_many([{"tenant_id": "A", "id": "r1"}, {"tenant_id": "A", "id": "r2"}, {"tenant_id": "B", "id": "other"}])
    await ledger_db.bookings.insert_many([
        {"tenant_id": "A", "check_in": "2026-10-18", "check_out": "2026-10-19", "created_at": "2026-10-17", "total_amount": 100, "currency": "EUR", "status": "confirmed"},
        {"tenant_id": "A", "check_in": datetime(2026, 10, 18, tzinfo=UTC), "check_out": datetime(2026, 10, 19, tzinfo=UTC), "created_at": datetime(2026, 10, 17, tzinfo=UTC), "total_amount": 200, "currency": "USD", "status": "checked_in"},
        {"tenant_id": "A", "check_in": "2026-10-11", "check_out": "2026-10-12", "created_at": "2026-10-01", "total_amount": 999999, "status": "confirmed"},
        {"tenant_id": "A", "check_in": "2026-10-18", "check_out": "2026-10-19", "total_amount": 999999, "status": "canceled"},
    ])
    user = SimpleNamespace(tenant_id="A")
    result = await forecast.forecast(days=30, segment=None, user=user)
    assert len(result["daily"]) == 30 and result["daily"][-1]["date"] == "2026-11-16"
    assert result["daily"][0]["revenue_otb"] is None
    assert result["daily"][0]["revenue_otb_by_currency"] == {"EUR": 100, "USD": 200}
    assert result["data_quality"]["historical_room_nights"] == 0  # confirmed is not historical realization
    pickup = await forecast.pickup_report(period_days=7, user=user)
    assert pickup["total_rooms_picked"] == 2
    assert pickup["total_revenue_picked"] is None
    assert pickup["total_revenue_picked_by_currency"] == {"EUR": 100, "USD": 200}
    pace = await forecast.pace(target_date="2026-10-18", compare_year=None, user=user)
    assert pace["current"] == [{"days_out": 1, "rooms_on_books": 2}, {"days_out": 0, "rooms_on_books": 2}]


async def test_real_mongo_deluxe_pickup_handles_dates_and_measures_recent_velocity_from_today(ledger_db, monkeypatch):
    from domains.pms import calendar_router as calendar

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 18, 12, tzinfo=UTC)

    monkeypatch.setattr(calendar, "datetime", Clock)
    monkeypatch.setattr(calendar, "db", ledger_db)
    monkeypatch.setattr(calendar, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    await ledger_db.bookings.insert_many([
        {"tenant_id": "A", "check_in": "2026-11-20", "created_at": "2026-10-17", "total_amount": 100, "currency": "EUR", "status": "confirmed"},
        {"tenant_id": "A", "check_in": datetime(2026, 11, 20, tzinfo=UTC), "created_at": datetime(2026, 10, 16, tzinfo=UTC), "total_amount": 200, "currency": "USD", "status": "checked_in"},
        {"tenant_id": "A", "check_in": "2026-11-20", "total_amount": 99999, "status": "confirmed"},
        {"tenant_id": "A", "check_in": "2026-11-20", "created_at": "2026-10-17", "total_amount": 99999, "status": "canceled"},
        {"tenant_id": "B", "check_in": "2026-11-20", "created_at": "2026-10-17", "total_amount": 99999, "status": "confirmed"},
    ])
    result = await calendar.get_pickup_pace_analytics.__wrapped__("2026-11-20", 90, False, None, SimpleNamespace(tenant_id="A"))
    assert result["summary"]["total_bookings"] == 2
    assert result["summary"]["total_revenue"] is None
    assert result["summary"]["total_revenue_by_currency"] == {"EUR": 100, "USD": 200}
    assert result["summary"]["velocity_7day"] == .29
    assert result["summary"]["velocity_as_of"] == "2026-10-18"
    assert result["chart_data"][-1]["cumulative_revenue_by_currency"] == {"EUR": 100, "USD": 200}


async def test_real_mongo_rms_reports_keep_currencies_and_never_fabricate_market_sales(ledger_db, monkeypatch):
    from domains.revenue.rms_router import revenue_reports as rms
    user = SimpleNamespace(tenant_id="A")
    monkeypatch.setattr(rms, "db", ledger_db)
    monkeypatch.setattr(rms, "get_current_user", AsyncMock(return_value=user))
    monkeypatch.setattr(rms, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    monkeypatch.setattr(rms, "load_stay_night_metrics", AsyncMock(return_value=[{"occupied_rooms": 2, "sold_rooms": 2,
        "total_rooms": 10, "occupancy_rate": 20, "revenue_by_currency": {"EUR": 100, "USD": 200}}]))
    monkeypatch.setattr(rms, "posted_revenue_rows", AsyncMock(return_value=[{"currency": "EUR", "total": 100}, {"currency": "USD", "total": 200}]))
    await ledger_db.bookings.insert_many([
        {"tenant_id": "A", "check_in": "2026-10-01", "check_out": "2026-10-03", "created_at": "2026-09-01", "total_amount": 100, "currency": "EUR", "status": "confirmed"},
        {"tenant_id": "A", "check_in": datetime(2026, 10, 1, tzinfo=UTC), "check_out": "2026-10-03", "created_at": datetime(2026, 9, 2, tzinfo=UTC), "total_amount": 200, "currency": "USD", "status": "checked_out"},
    ])
    await ledger_db.competitors.insert_one({"tenant_id": "A", "id": "comp", "is_active": True})
    report = await rms.get_pickup_report.__wrapped__("2026-10-01", "2026-10-01", "json", user)
    assert report["summary"]["total_rooms"] == 2
    assert report["summary"]["total_revenue"] is None
    assert report["summary"]["total_revenue_by_currency"] == {"EUR": 100, "USD": 200}
    csv = await rms.get_pickup_report.__wrapped__("2026-10-01", "2026-10-01", "csv", user)
    assert {(row["Currency"], row["Total Revenue"]) for row in csv["data"]} == {("EUR", 100), ("USD", 200)}
    assert sum(row["Total Rooms"] for row in csv["data"]) == 2
    market = await rms.get_market_share(None)
    assert not market["available"]
    assert market["market_totals"]["revenue"] is None and market["performance_index"]["revenue_rgi"] is None
    assert market["own_performance"]["revenue_by_currency"] == {"EUR": 100, "USD": 200}
    compset = await rms.get_compset_analysis(None)
    assert compset["own_property"]["adr"] is None
    assert compset["own_property"]["adr_by_currency"] == {"EUR": 50, "USD": 100}
    assert compset["competitors"][0]["current_adr"] is None  # no invented zero competitor price


async def test_real_mongo_lead_time_median_and_oversell_checkout_exclusion(ledger_db, monkeypatch):
    from domains.pms import calendar_router as calendar
    monkeypatch.setattr(calendar, "db", ledger_db)
    user = SimpleNamespace(tenant_id="A")
    await ledger_db.rooms.insert_many([{"tenant_id": "A", "id": "active"}, {"tenant_id": "A", "id": "inactive", "is_active": False}])
    await ledger_db.bookings.insert_many([
        {"tenant_id": "A", "check_in": "2026-10-20", "check_out": "2026-10-21", "created_at": "2026-10-18", "status": "confirmed"},
        {"tenant_id": "A", "check_in": datetime(2026, 10, 20, tzinfo=UTC), "check_out": datetime(2026, 10, 21, tzinfo=UTC), "created_at": datetime(2026, 10, 10, tzinfo=UTC), "status": "confirmed"},
        {"tenant_id": "A", "check_in": "2026-10-19", "check_out": "2026-10-20", "created_at": "2026-10-01", "status": "confirmed"},
        {"tenant_id": "A", "check_in": "2026-10-20", "check_out": "2026-10-21", "status": "canceled"},
    ])
    lead = await calendar.get_lead_time_analysis.__wrapped__("2026-10-20", "2026-10-20", user)
    assert lead["overall"]["median_lead_time"] == 6
    assert lead["by_channel"]["direct"]["median_lead_time"] == 6
    oversell = await calendar.get_oversell_protection_map.__wrapped__("2026-10-20", "2026-10-20", user)
    assert oversell["protection_map"][0]["bookings"] == 2  # yesterday's checkout is not occupied tonight
    assert oversell["summary"]["danger_days"] == 1
