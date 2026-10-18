"""Cross-report acceptance using real queries and isolated local Mongo records."""

from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core import tenant_currency
from routers.reports_pkg import dashboard_lists, flash_email, reservation_performance, standard_reports

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
USER = SimpleNamespace(tenant_id="A", role="admin", id="operator", name="Operator", email="operator@example.test", granted_permissions=[])


@pytest.fixture(autouse=True)
def context(ledger_db, monkeypatch):
    for module in (dashboard_lists, flash_email, reservation_performance, standard_reports):
        monkeypatch.setattr(module, "db", ledger_db)
        monkeypatch.setattr(module, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": "2026-10-02"}))
    monkeypatch.setattr(tenant_currency, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    monkeypatch.setattr(flash_email, "get_current_user", AsyncMock(return_value=USER))
    monkeypatch.setattr(flash_email, "send_email", AsyncMock(return_value={"sent": True, "provider": "isolated-test"}))
    monkeypatch.setattr("security.encrypted_lookup.decrypt_guest_doc", lambda row: row)


async def test_official_list_keeps_status_projection_and_all_actual_occupants(ledger_db):
    await ledger_db.rooms.insert_one({"tenant_id": "A", "id": "r", "room_number": "101"})
    await ledger_db.guests.insert_many(
        [
            {"tenant_id": "A", "id": "g", "name": "Primary"},
            {"tenant_id": "A", "id": "extra", "name": "Additional"},
        ]
    )
    await ledger_db.bookings.insert_many(
        [
            {
                "tenant_id": "A",
                "id": "b",
                "room_id": "r",
                "guest_id": "g",
                "status": "checked_in",
                "check_in": datetime(2026, 10, 1, tzinfo=UTC),
                "check_out": "2026-10-03",
                "total_amount": 100,
                "currency": "EUR",
            },
            {"tenant_id": "A", "id": "future", "room_id": "r", "status": "confirmed", "check_in": "2026-10-02", "check_out": "2026-10-03"},
            {"tenant_id": "A", "id": "left", "room_id": "r", "status": "checked_out", "check_in": "2026-10-01", "check_out": "2026-10-02"},
            {"tenant_id": "B", "id": "foreign", "room_id": "r", "status": "checked_in", "check_in": "2026-10-01", "check_out": "2026-10-03"},
        ]
    )
    await ledger_db.booking_guests.insert_many(
        [
            {"tenant_id": "A", "booking_id": "b", "guest_id": "extra"},
            {"tenant_id": "B", "booking_id": "b", "guest_id": "foreign-guest"},
        ]
    )
    result = await dashboard_lists.get_official_guest_list(date="2026-10-02", current_user=USER)
    assert result["count"] == 2
    assert {row["guest_name"] for row in result["rows"]} == {"Primary", "Additional"}
    assert {row["room_number"] for row in result["rows"]} == {"101"}
    assert sum(row["total_amount"] for row in result["rows"]) == 100


async def test_weekly_screen_and_email_share_full_currency_preserving_ledger(ledger_db):
    await ledger_db.rooms.insert_many([{"tenant_id": "A", "id": "r1"}, {"tenant_id": "A", "id": "r2"}])
    await ledger_db.bookings.insert_many(
        [
            {
                "tenant_id": "A",
                "id": "b",
                "room_id": "r1",
                "status": "checked_out",
                "check_in": "2026-10-01",
                "check_out": "2026-10-02",
                "total_amount": 100,
                "currency": "TRY",
                "created_at": datetime(2026, 10, 1, tzinfo=UTC),
            },
            {
                "tenant_id": "A",
                "id": "comp",
                "room_id": "r2",
                "status": "checked_out",
                "check_in": "2026-10-01",
                "check_out": "2026-10-02",
                "is_complimentary": True,
                "total_amount": 0,
                "reservation_date": "2026-10-01",
            },
            {"tenant_id": "A", "id": "outside", "status": "confirmed", "created_at": "2026-10-03"},
            {"tenant_id": "B", "id": "other", "status": "confirmed", "created_at": "2026-10-01"},
        ]
    )
    await ledger_db.folio_charges.insert_many(
        [
            {"tenant_id": "A", "business_date": datetime(2026, 10, 1, tzinfo=UTC), "total": 100, "category": "room", "currency": " TL "},
            {"tenant_id": "A", "date": "2026-10-02", "total": 20, "currency": "EUR"},
            {"tenant_id": "A", "date": "2026-10-01", "total": 0, "amount": 999, "currency": "TRY"},
            {"tenant_id": "B", "business_date": "2026-10-01", "total": 9999, "currency": "TRY"},
        ]
    )
    await ledger_db.extra_charges.insert_one({"tenant_id": "A", "date": "2026-10-02", "total": 10, "currency": "TRY"})
    await ledger_db.pos_orders.insert_one({"tenant_id": "A", "id": "pos", "status": "closed", "business_date": "2026-10-02", "grand_total": 40, "currency": "TRY"})
    await ledger_db.pos_transactions.insert_one({"tenant_id": "A", "id": "refund", "status": "refunded", "business_date": "2026-10-02", "total_amount": -5, "currency": "EUR"})
    result = await flash_email.get_weekly_management_summary(current_user=USER)
    assert result["total_revenue_by_currency"] == {"EUR": 15, "TRY": 150}
    assert result["total_revenue"] is None
    assert result["total_bookings"] == 2
    assert result["key_metrics"]["adr_by_currency"] == {"TRY": 100}
    assert result["key_metrics"]["occupancy"] == round(2 / 14 * 100, 2)
    await flash_email.send_weekly_management_email({"email": "recipient@example.test"}, credentials=None)
    email = await ledger_db.email_reports.find_one({"report_type": "weekly_summary"})
    assert email["report_data"]["total_revenue_by_currency"] == result["total_revenue_by_currency"]
    assert email["report_data"]["total_bookings"] == result["total_bookings"]
    html = flash_email.send_email.await_args.kwargs["html"]
    assert "EUR 15.00" in html and "TRY 150.00" in html
    assert "999" not in html


async def test_reservation_performance_includes_bson_dates_and_all_rows_and_normalizes_currency(ledger_db):
    await ledger_db.bookings.insert_many(
        [{"tenant_id": "A", "id": str(i), "check_in": "2026-10-01", "check_out": "2026-10-02", "status": "confirmed", "total_amount": 1, "currency": "TRY"} for i in range(20001)]
        + [
            {
                "tenant_id": "A",
                "id": "bson",
                "check_in": datetime(2026, 10, 2, 23, tzinfo=UTC),
                "check_out": datetime(2026, 10, 3, tzinfo=UTC),
                "status": "confirmed",
                "total_amount": 2,
                "currency": " TL ",
            },
            {"tenant_id": "A", "id": "outside", "check_in": "2026-10-03", "total_amount": 9999},
            {"tenant_id": "B", "id": "foreign", "check_in": "2026-10-01", "total_amount": 9999},
        ]
    )
    result = await reservation_performance._reservation_performance_payload(tenant_id="A", start_date=date(2026, 10, 1), end_date=date(2026, 10, 2))
    assert len(result["rows"]) == 20002
    assert result["summary"]["booked_revenue_by_currency"] == {"TRY": 20003}


async def test_revenue_reservation_count_does_not_drop_bson_arrivals(ledger_db):
    await ledger_db.bookings.insert_many(
        [
            {"tenant_id": "A", "check_in": datetime(2026, 10, 2, tzinfo=UTC), "status": "guaranteed"},
            {"tenant_id": "A", "check_in": "2026-10-02T23:00:00", "status": "checked_in"},
            {"tenant_id": "A", "check_in": "2026-10-02", "status": "cancelled"},
            {"tenant_id": "A", "check_in": "2026-10-03", "status": "confirmed"},
        ]
    )
    result = await standard_reports.get_revenue_report.__wrapped__("2026-10-02", "2026-10-02", current_user=USER)
    assert result["bookings_count"] == 2


async def test_basic_revenue_matches_standard_ledger_zero_totals_pos_refunds_and_folio_currency(ledger_db):
    await ledger_db.folios.insert_one({"id": "f", "tenant_id": "A", "currency": "EUR"})
    await ledger_db.folio_charges.insert_many(
        [
            {"tenant_id": "A", "business_date": "2026-10-02", "total": 0, "amount": 900, "currency": "TRY"},
            {"tenant_id": "A", "date": "2026-10-02", "folio_id": "f", "charge_amount": 20},
        ]
    )
    await ledger_db.extra_charges.insert_one({"tenant_id": "A", "date": "2026-10-02", "total": 7, "currency": "TRY"})
    await ledger_db.pos_orders.insert_many(
        [
            {"tenant_id": "A", "id": "p", "status": "closed", "business_date": "2026-10-02", "total_amount": 40, "grand_total": 30, "currency": "TRY"},
            {"tenant_id": "A", "id": "zero", "status": "closed", "business_date": "2026-10-02", "total_amount": 999, "grand_total": 0, "currency": "TRY"},
            {"tenant_id": "A", "id": "not-paid", "status": "served", "business_date": "2026-10-02", "total_amount": 999, "currency": "TRY"},
        ]
    )
    await ledger_db.pos_transactions.insert_many(
        [
            {"tenant_id": "A", "id": "sale", "order_id": "p", "status": "completed", "business_date": "2026-10-02", "total_amount": 30, "currency": "TRY"},
            {"tenant_id": "A", "id": "refund", "order_id": "p", "status": "refunded", "business_date": "2026-10-02", "total_amount": -10, "currency": "TRY"},
        ]
    )
    result = await dashboard_lists._basic_dashboard_impl.__wrapped__(USER, True, "2026-10-02", "daily")
    standard = await standard_reports.get_revenue_report.__wrapped__("2026-10-02", "2026-10-02", current_user=USER)
    assert result["summary"]["today_revenue_by_currency"] == standard["total_revenue_by_currency"] == {"EUR": 20, "TRY": 27}


async def test_cash_movements_have_one_processed_day_and_unknown_fx_is_not_try(ledger_db):
    await ledger_db.folios.insert_one({"tenant_id": "A", "id": "f", "currency": "EUR"})
    await ledger_db.payments.insert_one(
        {
            "tenant_id": "A",
            "id": "p",
            "folio_id": "f",
            "business_date": "2026-10-01",
            "payment_date": "2026-10-01",
            "processed_at": datetime(2026, 10, 2, 12, tzinfo=UTC),
            "amount": 20,
            "method": "cash",
        }
    )
    first = await dashboard_lists._basic_dashboard_impl.__wrapped__(USER, True, "2026-10-01", "daily")
    second = await dashboard_lists._basic_dashboard_impl.__wrapped__(USER, True, "2026-10-02", "daily")
    assert first["cash_movements"]["rows"] == []
    assert first["payments"]["received_totals_by_currency"] == {"EUR": 20}
    assert first["payments"]["conversion_issue_count"] == 1
    assert second["cash_movements"]["total_paid"] == 0
    assert second["cash_movements"]["rows"][0]["currency"] == "EUR"
    assert second["cash_movements"]["rows"][0]["conversion_missing"] is True


async def test_daily_balance_effect_counts_non_cash_offsets_without_calling_them_collections(ledger_db):
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "business_date": "2026-10-02", "total": 100, "currency": "TRY"})
    await ledger_db.payments.insert_many(
        [
            {"tenant_id": "A", "id": "discount", "business_date": "2026-10-02", "amount": 20, "method": "discount", "currency": "TRY"},
            {"tenant_id": "A", "id": "cash", "business_date": "2026-10-02", "amount": 30, "method": "cash", "currency": "TRY"},
            {"tenant_id": "A", "id": "void", "business_date": "2026-10-02", "amount": 9999, "method": "discount", "currency": "TRY", "voided": True},
        ]
    )
    result = await dashboard_lists._basic_dashboard_impl.__wrapped__(USER, True, "2026-10-02", "daily")
    assert result["payments"]["total_paid"] == 30
    assert result["front_cashier"]["daily_balance_change_by_currency"] == {"TRY": 50}


async def test_room_rate_control_does_not_label_posted_usd_as_agreed_eur(ledger_db):
    await ledger_db.rooms.insert_one({"tenant_id": "A", "id": "r", "room_number": "101"})
    await ledger_db.bookings.insert_one(
        {"tenant_id": "A", "id": "b", "room_id": "r", "status": "checked_in", "check_in": "2026-10-02", "check_out": "2026-10-03", "total_amount": 100, "currency": "EUR"}
    )
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "booking_id": "b", "business_date": "2026-10-02", "total": 90, "currency": "USD", "charge_category": "room"})
    result = await dashboard_lists._basic_dashboard_impl.__wrapped__(USER, True, "2026-10-02", "daily")
    row = result["room_rate_control"][0]
    assert row["posted_rate"] is None and row["variance"] is None
    assert row["posted_rate_by_currency"] == {"USD": 90}
    assert row["currency_mismatch"] is True
    assert row["posting_status"] == "posted"
    assert result["daily_analysis"]["expected_room_revenue_by_currency"] == {"EUR": 100}


async def test_basic_report_does_not_truncate_capacity_or_cash_totals(ledger_db):
    await ledger_db.rooms.insert_many([{"tenant_id": "A", "id": f"r{i}", "is_active": True} for i in range(1001)])
    await ledger_db.payments.insert_many(
        [{"tenant_id": "A", "id": f"p{i}", "business_date": "2026-10-02", "processed_at": "2026-10-02", "amount": 1, "currency": "TRY", "method": "cash"} for i in range(10001)]
    )
    result = await dashboard_lists._basic_dashboard_impl.__wrapped__(USER, True, "2026-10-02", "daily")
    assert result["summary"]["total_rooms"] == 1001
    assert result["payments"]["total_paid"] == 10001
    assert result["cash_movements"]["total_paid"] == 10001
    assert len(result["payments"]["rows"]) == len(result["cash_movements"]["rows"]) == 10001


async def test_basic_accrued_revenue_preserves_the_exact_stay_total(ledger_db):
    await ledger_db.rooms.insert_one({"tenant_id": "A", "id": "r"})
    await ledger_db.bookings.insert_one(
        {"tenant_id": "A", "id": "b", "room_id": "r", "status": "checked_in", "check_in": "2026-09-30", "check_out": "2026-10-03", "total_amount": 100.01, "currency": "EUR"}
    )
    result = await dashboard_lists._basic_dashboard_impl.__wrapped__(USER, True, "2026-10-02", "monthly")
    assert result["period_metrics"]["room_revenue_by_currency"] == {"EUR": 100.01}


async def test_basic_cash_rows_omit_unsettled_and_canceled_payment_attempts(ledger_db):
    await ledger_db.payments.insert_many(
        [
            {"tenant_id": "A", "id": status, "business_date": "2026-10-02", "processed_at": "2026-10-02", "amount": 999, "currency": "TRY", "method": "cash", "status": status}
            for status in ("pending", "processing", "authorized", "canceled")
        ]
    )
    result = await dashboard_lists._basic_dashboard_impl.__wrapped__(USER, True, "2026-10-02", "daily")
    assert result["payments"]["rows"] == result["cash_movements"]["rows"] == []
    assert result["payments"]["received_totals_by_currency"] == {}


def test_physical_currency_of_negative_refunds_and_explicit_zero_is_preserved():
    assert dashboard_lists._received_payment_amount({"amount": -10, "currency": "EUR", "received_amount": -400, "received_currency": " TL ", "payment_type": "refund"}) == {
        "amount": -400,
        "currency": "TRY",
    }
    assert dashboard_lists._received_payment_amount({"amount": 10, "currency": "EUR", "received_amount": 0, "received_currency": "USD"}) == {"amount": 0, "currency": "USD"}
