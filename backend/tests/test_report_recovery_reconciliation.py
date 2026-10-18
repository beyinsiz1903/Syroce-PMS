"""Cross-output, failure-recovery and high-volume report acceptance."""

import sys
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from core import business_date_service, database, tenant_currency
from modules.messaging.email_service import email_service
from modules.pms_core.reporting_financials import reporting_collection_summary
from routers import report_scheduler as scheduler
from routers.finance import accounting
from routers.reports_pkg import dashboard_lists, flash_email, standard_reports

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
USER = SimpleNamespace(tenant_id="A", role="admin", id="operator", email="operator@example.test")
SCHEDULE = {
    "_id": "s",
    "tenant_id": "A",
    "name": "Test report",
    "report_type": "revenue",
    "frequency": "daily",
    "send_time": "08:00",
    "date_range": "auto",
    "format": "csv",
    "recipients": ["recipient@example.test"],
    "total_sent": 0,
    "total_failed": 0,
}


@pytest.fixture(autouse=True)
def context(ledger_db, monkeypatch):
    for module in (scheduler, accounting, dashboard_lists, flash_email, standard_reports):
        monkeypatch.setattr(module, "db", ledger_db)
    monkeypatch.setattr(database, "_raw_db", ledger_db)
    provider = AsyncMock(return_value={"business_date": "2026-10-07"})
    for module in (business_date_service, dashboard_lists, flash_email, standard_reports):
        monkeypatch.setattr(module, "ensure_business_date_initialized", provider)
    monkeypatch.setattr(tenant_currency, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    monkeypatch.setattr(accounting, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    monkeypatch.setattr(scheduler, "_invalidate_scheduler_cache", lambda _: None)
    monkeypatch.setattr(email_service, "mode", "production")
    monkeypatch.setattr(email_service, "smtp_username", "isolated")
    monkeypatch.setattr(email_service, "smtp_password", "test-only")
    monkeypatch.setattr(email_service, "_send_email_smtp", Mock(return_value=True))
    monkeypatch.setattr(flash_email, "send_email", AsyncMock(return_value={"sent": False, "provider": "isolated"}))


@pytest.mark.parametrize("failure_point", ["history", "schedule"])
async def test_delivered_count_and_timestamp_reconcile_after_failed_final_write(ledger_db, monkeypatch, failure_point):
    await ledger_db.report_schedules.insert_one(dict(SCHEDULE))
    monkeypatch.setattr(scheduler, "_build_report_payload", AsyncMock(return_value={"range": "2026-10-07", "rows": []}))
    history, schedules = ledger_db.report_schedule_history, ledger_db.report_schedules
    failed_once = False

    async def update(collection, query, operation):
        nonlocal failed_once
        marker = "status" if failure_point == "history" else "last_status"
        if operation.get("$set", {}).get(marker) == "sent" and not failed_once:
            failed_once = True
            raise RuntimeError("isolated injected final write failure")
        return await collection.update_one(query, operation)

    monkeypatch.setattr(
        scheduler,
        "db",
        SimpleNamespace(
            report_schedule_history=SimpleNamespace(find_one=history.find_one, insert_one=history.insert_one, aggregate=history.aggregate, update_one=lambda q, op: update(history, q, op)),
            report_schedules=SimpleNamespace(find_one=schedules.find_one, update_one=lambda q, op: update(schedules, q, op)),
        ),
    )
    initial = await scheduler._execute_schedule(dict(SCHEDULE))
    assert initial["status"] == "failed"
    recovered = await scheduler.retry_send(initial["history_id"], USER)
    assert recovered["status"] == "sent"
    saved = await schedules.find_one({"_id": "s"})
    assert saved["total_sent"] == 1 and saved["last_sent_at"]
    assert saved["total_failed"] == 0  # DB preparation/recovery errors are not rejected emails.
    email_service._send_email_smtp.assert_called_once()


async def test_delivery_stats_read_all_history_states_and_legacy_proof_not_stale_cache(ledger_db):
    await ledger_db.report_schedules.insert_one({**SCHEDULE, "total_sent": 999, "total_failed": 999})
    await ledger_db.report_schedule_history.insert_many(
        [
            {"tenant_id": "A", "schedule_id": "s", "sent_at": "2026-10-01T08:00:00+00:00", "delivery_details": {"sent_count": 2, "failed_count": 1}},
            {
                "tenant_id": "A",
                "schedule_id": "s",
                "sent_at": "2026-10-02T08:00:00+00:00",
                "delivery_states": [
                    {"recipient": "r", "status": "sent", "sent_at": "2026-10-03T08:00:00+00:00", "failed_attempts": 2},
                    {"recipient": "f", "status": "failed", "failed_attempts": 1},
                    {"recipient": "m", "status": "mock"},
                ],
            },
            {"tenant_id": "B", "schedule_id": "s", "delivery_details": {"sent_count": 999}},
        ]
    )
    result = await scheduler.get_schedule("s", USER)
    assert result["schedule"]["total_sent"] == 3
    assert result["schedule"]["total_failed"] == 4
    assert result["schedule"]["last_sent_at"] == "2026-10-03T08:00:00+00:00"


async def test_legacy_flash_send_never_claims_success_without_provider_delivery():
    result = await flash_email.send_flash_report_now(["recipient@example.test"], USER)
    assert result["success"] is False
    assert result["recipients_failed"] == ["recipient@example.test"]
    flash_email.send_email.assert_awaited_once()


async def test_legacy_automation_adapter_does_not_simulate_delivery(ledger_db):
    from modules.analytics_export.report_automation import ReportAutomation

    automation = ReportAutomation(ledger_db, email_service)
    assert await automation.send_flash_report_email("A", ["recipient@example.test"]) is False
    flash_email.send_email.assert_awaited_once()


@pytest.mark.parametrize("recipients", [[], "recipient@example.test", ["bad"], ["ok@example.test", "bad"]])
async def test_flash_rejects_bad_recipient_list_before_any_delivery(recipients):
    with pytest.raises(HTTPException) as error:
        await flash_email.email_daily_flash({"recipients": recipients}, USER)
    assert error.value.status_code == 400
    flash_email.send_email.assert_not_awaited()


async def test_flash_pdf_email_and_screen_keep_the_selected_business_date_and_native_amounts(ledger_db, monkeypatch):
    await ledger_db.folio_charges.insert_many(
        [
            {"tenant_id": "A", "business_date": "2026-10-01", "category": "room", "total": 10, "currency": "EUR"},
            {"tenant_id": "A", "business_date": "2026-10-07", "category": "room", "total": 9999, "currency": "TRY"},
        ]
    )
    rendered = []

    class Renderer:
        def __init__(self, string):
            rendered.append(string)

        def write_pdf(self):
            return b"%PDF-isolated"

    monkeypatch.setitem(sys.modules, "weasyprint", SimpleNamespace(HTML=Renderer))
    screen = await flash_email.get_daily_flash_report.__wrapped__("2026-10-01", USER)
    pdf = await flash_email.get_daily_flash_pdf(current_user=USER, date_str="2026-10-01")
    result = await flash_email.email_daily_flash({"recipients": [" recipient@example.test ", "recipient@example.test"], "date_str": "2026-10-01"}, USER)
    assert screen["revenue"]["total_revenue_by_currency"] == {"EUR": 10}
    assert pdf.body.startswith(b"%PDF") and "EUR 10.00" in rendered[0] and "9,999" not in rendered[0]
    assert flash_email.send_email.await_count == 1
    assert "2026-10-01" in flash_email.send_email.await_args.kwargs["subject"]
    assert "EUR 10.00" in flash_email.send_email.await_args.kwargs["html"]
    assert not result["success"]


@pytest.mark.parametrize("amount,expected", [(2.675, 2.68), (2.665, 2.67)])
async def test_cent_rounding_is_shared_by_daily_standard_flash_scheduler_and_basic(ledger_db, amount, expected):
    await ledger_db.rooms.insert_one({"tenant_id": "A", "id": "r", "room_type": "standard"})
    await ledger_db.bookings.insert_one(
        {
            "tenant_id": "A",
            "id": "b",
            "room_id": "r",
            "room_type": "standard",
            "booking_source": "direct",
            "check_in": "2026-10-07",
            "check_out": "2026-10-08",
            "status": "checked_out",
            "currency": "TRY",
            "total_amount": amount,
        }
    )
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "booking_id": "b", "business_date": "2026-10-07", "total": amount, "currency": "TRY", "category": "room"})
    standard = await standard_reports.get_revenue_report.__wrapped__("2026-10-07", "2026-10-07", USER)
    daily = await standard_reports.get_daily_summary.__wrapped__("2026-10-07", USER)
    flash = await flash_email.get_daily_flash_report.__wrapped__("2026-10-07", USER)
    basic = await dashboard_lists._basic_dashboard_impl.__wrapped__(USER, True, "2026-10-07", "daily")
    scheduled = await scheduler._build_report_payload(SCHEDULE, datetime(2026, 10, 15, tzinfo=UTC))
    assert (
        standard["total_revenue_by_currency"]
        == daily["gross_posted_revenue_by_currency"]
        == flash["revenue"]["total_revenue_by_currency"]
        == basic["summary"]["today_revenue_by_currency"]
        == {"TRY": expected}
    )
    assert next(row["value"] for row in scheduled["rows"] if row["label"] == "Toplam gelir (para birimine göre)") == f"TRY {expected:.2f}"
    assert basic["booking_sources"]["revenue_by_currency"]["direct"] == {"TRY": expected}
    assert basic["room_type_occupancy"]["Standart"]["revenue_by_currency"] == {"TRY": expected}
    assert basic["revenue_trend"][0]["revenue_by_currency"] == {"TRY": expected}
    assert basic["revenue_trend"][0]["revenue"] == expected


async def test_transfer_report_never_cuts_a_document_in_the_middle(ledger_db):
    await ledger_db.stock_movements.insert_many(
        [
            {
                "tenant_id": "A",
                "transfer_id": "bulk",
                "movement_type": kind,
                "item_id": f"src-{i}" if kind == "transfer_out" else f"dst-{i}",
                "counterpart_item_id": f"dst-{i}" if kind == "transfer_out" else f"src-{i}",
                "created_at": "2026-10-07T23:00:00+00:00",
                "quantity": 1,
                "unit_cost": 0.1,
            }
            for i in range(150)
            for kind in ("transfer_out", "transfer_in")
        ]
    )
    result = await accounting.get_transfer_history(limit=1, current_user=USER)
    assert result["transfers"][0]["line_count"] == 150
    assert result["transfers"][0]["total_value"] == 15


async def test_transfer_date_filter_keeps_final_day_iso_and_bson_rows(ledger_db):
    await ledger_db.stock_movements.insert_many(
        [
            {
                "tenant_id": "A",
                "transfer_id": "mixed",
                "movement_type": kind,
                "item_id": "a" if kind == "transfer_out" else "b",
                "counterpart_item_id": "b" if kind == "transfer_out" else "a",
                "created_at": when,
                "quantity": 1,
                "unit_cost": 10,
            }
            for kind, when in [("transfer_out", "2026-10-07T23:00:00Z"), ("transfer_in", datetime(2026, 10, 7, 23, tzinfo=UTC))]
        ]
    )
    result = await accounting.get_transfer_history(start_date="2026-10-07", end_date="2026-10-07", current_user=USER)
    assert result["count"] == 1
    assert result["transfers"][0]["total_value"] == 10


async def test_native_adr_uses_same_denominator_on_all_reports_and_previous_period(ledger_db):
    await ledger_db.rooms.insert_many([{"tenant_id": "A", "id": "r1"}, {"tenant_id": "A", "id": "r2"}])
    for day, departure in [("2026-10-06", "2026-10-07"), ("2026-10-07", "2026-10-08")]:
        for room, currency, amount in [("r1", "TRY", 100), ("r2", "EUR", 40)]:
            await ledger_db.bookings.insert_one(
                {"tenant_id": "A", "id": day + room, "room_id": room, "status": "checked_out", "check_in": day, "check_out": departure, "currency": currency, "total_amount": amount}
            )
            await ledger_db.folio_charges.insert_one({"tenant_id": "A", "business_date": day, "category": "room", "total": amount, "currency": currency})
    standard = await standard_reports.get_revenue_report.__wrapped__("2026-10-07", "2026-10-07", USER)
    basic = await dashboard_lists._basic_dashboard_impl.__wrapped__(USER, True, "2026-10-07", "daily")
    flash = await flash_email.get_daily_flash_report.__wrapped__("2026-10-07", USER)
    expected = {"TRY": 50, "EUR": 20}
    assert standard["adr_by_currency"] == flash["revenue"]["adr_by_currency"] == basic["summary"]["adr_by_currency"] == expected
    assert basic["period_comparison"]["prev_month_adr_by_currency"] == expected
    assert basic["period_comparison"]["prev_month_adr"] == 0  # Legacy scalar is never a sum of currencies.


async def test_transfer_values_keep_item_currencies_separate_and_show_unpaired_legs(ledger_db):
    await ledger_db.inventory_items.insert_many([{"tenant_id": "A", "id": "a", "currency": "EUR"}, {"tenant_id": "A", "id": "c", "currency": "TRY"}])
    await ledger_db.stock_movements.insert_many(
        [
            {"tenant_id": "A", "transfer_id": "mixed", "movement_type": "transfer_out", "item_id": "a", "counterpart_item_id": "b", "created_at": "2026-10-07", "quantity": 2, "unit_cost": 10},
            {"tenant_id": "A", "transfer_id": "mixed", "movement_type": "transfer_out", "item_id": "c", "counterpart_item_id": "d", "created_at": "2026-10-07", "quantity": 3, "unit_cost": 10},
        ]
    )
    result = await accounting.get_transfer_history(current_user=USER)
    record = result["transfers"][0]
    assert record["total_value_by_currency"] == {"EUR": 20, "TRY": 30}
    assert record["total_value"] is None
    assert record["balanced"] is False
    assert record["lines"][0]["in_quantity"] == 0


async def test_transfer_repeated_pair_uses_each_outgoing_cost_not_the_first_cost(ledger_db):
    await ledger_db.stock_movements.insert_many(
        [
            {
                "tenant_id": "A",
                "transfer_id": "repeat",
                "movement_type": kind,
                "item_id": "a" if kind == "transfer_out" else "b",
                "counterpart_item_id": "b" if kind == "transfer_out" else "a",
                "created_at": "2026-10-07",
                "quantity": quantity,
                "unit_cost": cost,
            }
            for quantity, cost in [(2, 10), (3, 20)]
            for kind in ("transfer_out", "transfer_in")
        ]
    )
    record = (await accounting.get_transfer_history(current_user=USER))["transfers"][0]
    assert record["total_value_by_currency"] == {"TRY": 80}
    assert record["balanced"] is True


async def test_legacy_transfer_with_different_units_is_unverified_not_a_false_mismatch(ledger_db):
    await ledger_db.inventory_items.insert_many(
        [
            {"tenant_id": "A", "id": "a", "unit": "kg"},
            {"tenant_id": "A", "id": "b", "unit": "adet"},
        ]
    )
    await ledger_db.stock_movements.insert_many(
        [
            {
                "tenant_id": "A",
                "transfer_id": "converted",
                "movement_type": kind,
                "item_id": "a" if kind == "transfer_out" else "b",
                "counterpart_item_id": "b" if kind == "transfer_out" else "a",
                "created_at": "2026-10-07",
                "quantity": quantity,
                "unit_cost": 10,
            }
            for kind, quantity in [("transfer_out", 5), ("transfer_in", 20)]
        ]
    )
    record = (await accounting.get_transfer_history(current_user=USER))["transfers"][0]
    assert record["balanced"] is None
    assert record["lines"][0]["quantity_difference"] is None
    assert record["lines"][0]["source_unit"] == "kg"
    assert record["lines"][0]["destination_unit"] == "adet"
    assert record["total_value"] == 50


async def test_unfiltered_transfer_history_does_not_crash_on_a_legacy_invalid_date(ledger_db):
    await ledger_db.stock_movements.insert_one(
        {
            "tenant_id": "A",
            "transfer_id": "legacy",
            "movement_type": "transfer_out",
            "item_id": "a",
            "counterpart_item_id": "b",
            "created_at": "invalid-legacy-date",
            "quantity": 1,
            "unit_cost": 10,
        }
    )
    record = (await accounting.get_transfer_history(current_user=USER))["transfers"][0]
    assert record["created_at"] == "invalid-legacy-date"
    assert record["balanced"] is False


async def test_adr_half_cent_rounding_is_consistent(ledger_db):
    await ledger_db.rooms.insert_many([{"tenant_id": "A", "id": "r1"}, {"tenant_id": "A", "id": "r2"}])
    await ledger_db.bookings.insert_many(
        [{"tenant_id": "A", "id": r, "room_id": r, "status": "checked_out", "check_in": "2026-10-07", "check_out": "2026-10-08", "total_amount": 2.675, "currency": "TRY"} for r in ("r1", "r2")]
    )
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "business_date": "2026-10-07", "total": 5.35, "currency": "TRY", "category": "room"})
    standard = await standard_reports.get_revenue_report.__wrapped__("2026-10-07", "2026-10-07", USER)
    basic = await dashboard_lists._basic_dashboard_impl.__wrapped__(USER, True, "2026-10-07", "daily")
    flash = await flash_email.get_daily_flash_report.__wrapped__("2026-10-07", USER)
    assert standard["adr_by_currency"] == basic["summary"]["adr_by_currency"] == flash["revenue"]["adr_by_currency"] == {"TRY": 2.68}


@pytest.mark.parametrize("amount,expected", [(2.675, 2.68), (2.665, 2.67)])
async def test_collection_rounding_and_refunds_match_report_totals(ledger_db, amount, expected):
    payment = {"tenant_id": "A", "id": "p", "business_date": "2026-10-07", "processed_at": "2026-10-07", "amount": amount, "currency": "TRY", "method": "cash"}
    await ledger_db.payments.insert_one(dict(payment))
    core = reporting_collection_summary([payment])
    daily = await standard_reports.get_daily_summary.__wrapped__("2026-10-07", USER)
    basic = await dashboard_lists._basic_dashboard_impl.__wrapped__(USER, True, "2026-10-07", "daily")
    assert core["amount"] == core["by_method"]["cash"]["amount"] == daily["collections"] == basic["payments"]["total_paid"] == basic["cash_movements"]["total_paid"] == expected
    assert basic["payments"]["totals_by_method_currency"]["cash"]["TRY"] == expected


@pytest.mark.parametrize("payment_type,amount,expected", [("rate_correction", -20, 120), ("refund", 20, 120), ("discount", 20, 80)])
async def test_signed_non_cash_adjustments_follow_the_folio_balance_direction(ledger_db, payment_type, amount, expected):
    await ledger_db.folio_charges.insert_one({"tenant_id": "A", "business_date": "2026-10-07", "total": 100, "currency": "TRY"})
    await ledger_db.payments.insert_one({"tenant_id": "A", "business_date": "2026-10-07", "amount": amount, "currency": "TRY", "method": "discount", "payment_type": payment_type})
    report = await standard_reports.get_daily_summary.__wrapped__("2026-10-07", USER)
    assert report["daily_revenue"] == expected
    assert report["collections"] == 0


async def test_retry_preserves_legacy_failed_attempt_count(ledger_db):
    await ledger_db.report_schedules.insert_one(dict(SCHEDULE))
    await ledger_db.report_schedule_history.insert_one(
        {
            "_id": "legacy-state",
            "tenant_id": "A",
            "schedule_id": "s",
            "status": "failed",
            "retry_count": 0,
            "schedule_snapshot": dict(SCHEDULE),
            "report_payload": {"range": "2026-10-07", "rows": []},
            "delivery_states": [{"recipient": "recipient@example.test", "status": "failed"}],
        }
    )
    result = await scheduler.retry_send("legacy-state", USER)
    assert result["status"] == "sent"
    record = await ledger_db.report_schedules.find_one({"_id": "s"})
    assert record["total_sent"] == record["total_failed"] == 1
