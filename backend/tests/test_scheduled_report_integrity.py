"""Real-query report periods and delivery contracts; SMTP is always a stub."""

import asyncio
from datetime import UTC, date, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from core import business_date_service, database, tenant_currency
from modules.messaging.email_service import email_service
from routers import report_scheduler as scheduler
from routers.finance import accounting

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
USER = SimpleNamespace(tenant_id="A", role="admin", email="operator@example.test")
NOW = datetime(2026, 10, 15, tzinfo=UTC)


@pytest.fixture(autouse=True)
def context(ledger_db, monkeypatch):
    monkeypatch.setattr(scheduler, "db", ledger_db)
    monkeypatch.setattr(accounting, "db", ledger_db)
    monkeypatch.setattr(database, "_raw_db", ledger_db)
    monkeypatch.setattr(business_date_service, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": "2026-10-07"}))
    monkeypatch.setattr(tenant_currency, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    monkeypatch.setattr(email_service, "mode", "production")
    monkeypatch.setattr(email_service, "smtp_username", "isolated")
    monkeypatch.setattr(email_service, "smtp_password", "test-only")
    monkeypatch.setattr(email_service, "_send_email_smtp", Mock(return_value=True))
    monkeypatch.setattr(scheduler, "_invalidate_scheduler_cache", lambda _: None)


def schedule(**overrides):
    return {
        "_id": "schedule",
        "tenant_id": "A",
        "name": "Weekly",
        "report_type": "revenue",
        "frequency": "weekly",
        "day_of_week": "wednesday",
        "send_time": "08:00",
        "date_range": "auto",
        "format": "csv",
        "recipients": ["first@example.test", "second@example.test"],
        **overrides,
    }


async def test_weekly_finance_covers_seven_business_days_and_uses_room_night_denominators(ledger_db):
    await ledger_db.rooms.insert_many([{"tenant_id": "A", "id": "r1"}, {"tenant_id": "A", "id": "r2"}])
    await ledger_db.bookings.insert_one(
        {"tenant_id": "A", "id": "b", "room_id": "r1", "status": "checked_out", "check_in": "2026-10-01", "check_out": "2026-10-08", "total_amount": 700, "currency": "TRY"}
    )
    await ledger_db.folio_charges.insert_many(
        [
            {"tenant_id": "A", "business_date": "2026-10-01", "total": 300, "category": "room", "currency": " TL "},
            {"tenant_id": "A", "business_date": datetime(2026, 10, 7, 23, tzinfo=UTC), "total": 400, "category": "room", "currency": "TRY"},
            {"tenant_id": "A", "business_date": "2026-10-07", "total": 20, "category": "food", "currency": "EUR"},
            {"tenant_id": "A", "business_date": "2026-10-08", "total": 9999, "category": "room", "currency": "TRY"},
            {"tenant_id": "B", "business_date": "2026-10-01", "total": 9999, "category": "room", "currency": "TRY"},
        ]
    )
    payload = await scheduler._build_report_payload(schedule(), NOW)
    rows = {row["label"]: row["value"] for row in payload["rows"]}
    assert (payload["start_date"], payload["end_date"]) == ("2026-10-01", "2026-10-07")
    assert rows["Toplam gelir (para birimine göre)"] == "EUR 20.00 · TRY 700.00"
    assert rows["ADR (Ortalama Günlük Fiyat)"] == "TRY 100.00"
    assert rows["RevPAR (Oda Başı Gelir)"] == "TRY 50.00"
    assert "2026-10-01" in scheduler._payload_to_csv("Revenue", payload).decode("utf-8-sig")


@pytest.mark.parametrize("kind", ["channel_performance", "b2b_analytics", "reservations"])
async def test_booking_statistics_respect_period_and_keep_all_channels(ledger_db, kind):
    await ledger_db.bookings.insert_many(
        [{"tenant_id": "A", "id": str(i), "check_in": "2026-10-01T23:59:59Z", "channel": f"OTA-{i}", "agency_id": "agency", "status": "confirmed"} for i in range(12)]
        + [
            {"tenant_id": "A", "check_in": datetime(2026, 10, 7, 23, tzinfo=UTC), "channel": "Direct", "agency_id": "agency", "status": "confirmed"},
            {"tenant_id": "A", "check_in": "2026-09-30", "channel": "Outside", "agency_id": "agency"},
            {"tenant_id": "A", "check_in": "2026-10-08", "channel": "Future", "agency_id": "agency"},
            {"tenant_id": "B", "check_in": "2026-10-01", "channel": "Foreign", "agency_id": "agency"},
        ]
    )
    payload = await scheduler._build_report_payload(schedule(report_type=kind), NOW)
    rows = {row["label"]: row["value"] for row in payload["rows"]}
    if kind == "channel_performance":
        assert len(rows) == 13 and sum(rows.values()) == 13
    else:
        assert rows["Giriş dönemindeki rezervasyon sayısı"] == 13


async def test_invoice_list_includes_end_day_bson_and_more_than_1000_rows(ledger_db):
    await ledger_db.accounting_invoices.insert_many(
        [{"id": str(i), "tenant_id": "A", "issue_date": "2026-10-01", "total_amount": 1} for i in range(1001)]
        + [
            {"id": "iso", "tenant_id": "A", "issue_date": "2026-10-07T23:59:59Z", "total_amount": 2},
            {"id": "bson", "tenant_id": "A", "issue_date": datetime(2026, 10, 7, 23, tzinfo=UTC), "total_amount": 3},
            {"id": "next", "tenant_id": "A", "issue_date": "2026-10-08", "total_amount": 9999},
            {"id": "foreign", "tenant_id": "B", "issue_date": "2026-10-01", "total_amount": 9999},
        ]
    )
    rows = await accounting.get_accounting_invoices.__wrapped__(start_date="2026-10-01", end_date="2026-10-07", current_user=USER)
    assert len(rows) == 1003 and sum(row["total_amount"] for row in rows) == 1006
    assert {row["id"] for row in await accounting.get_accounting_invoices.__wrapped__(start_date="2026-10-08", current_user=USER)} == {"next"}


@pytest.mark.parametrize("overrides", [{"recipients": []}, {"name": "   "}, {"format": ""}, {"send_time": ""}, {"date_range": "all_time"}])
async def test_invalid_schedule_update_is_rejected_without_writes(ledger_db, overrides):
    await ledger_db.report_schedules.insert_one(schedule())
    with pytest.raises(HTTPException) as error:
        await scheduler.update_schedule("schedule", scheduler.ScheduleUpdate(**overrides), USER)
    assert error.value.status_code == 400
    assert (await ledger_db.report_schedules.find_one({"_id": "schedule"}))["recipients"] == schedule()["recipients"]


async def test_partial_update_uses_existing_weekday_and_deduplicates_recipients(ledger_db):
    await ledger_db.report_schedules.insert_one(schedule())
    result = await scheduler.update_schedule("schedule", scheduler.ScheduleUpdate(frequency="weekly", recipients=[" first@example.test ", "first@example.test"]), USER)
    assert result["schedule"]["recipients"] == ["first@example.test"]


@pytest.mark.parametrize("fmt", ["pdf", "link"])
async def test_requested_format_failure_never_sends_a_different_report(ledger_db, monkeypatch, fmt):
    monkeypatch.setattr(scheduler, "_build_report_payload", AsyncMock(return_value={"rows": [], "range": "2026-10-07"}))
    monkeypatch.setattr(scheduler, "_payload_to_pdf", lambda *_: None)
    monkeypatch.delenv("PUBLIC_APP_URL", raising=False)
    result = await scheduler._execute_schedule(schedule(format=fmt))
    assert result["status"] == "failed"
    email_service._send_email_smtp.assert_not_called()


async def test_partial_retry_only_sends_failed_recipient_with_original_snapshot(ledger_db, monkeypatch):
    original = schedule()
    await ledger_db.report_schedules.insert_one(original)
    payload = {"rows": [{"label": "Revenue", "value": "TRY 700.00"}], "range": "2026-10-01 – 2026-10-07", "start_date": "2026-10-01", "end_date": "2026-10-07", "generated_at": NOW.isoformat()}
    builder = AsyncMock(return_value=payload)
    monkeypatch.setattr(scheduler, "_build_report_payload", builder)
    email_service._send_email_smtp.side_effect = [True, False]
    initial = await scheduler._execute_schedule(original)
    assert initial["status"] == "partial"
    original_csv = email_service._send_email_smtp.call_args.args[4][0][2]
    await ledger_db.report_schedules.update_one({"_id": "schedule"}, {"$set": {"format": "pdf", "recipients": ["unrelated@example.test"]}})
    builder.side_effect = AssertionError("Retry must not recalculate a different reporting period")
    email_service._send_email_smtp.reset_mock(side_effect=True)
    email_service._send_email_smtp.return_value = True
    result = await scheduler.retry_send(initial["history_id"], USER)
    assert result["status"] == "sent"
    email_service._send_email_smtp.assert_called_once()
    assert email_service._send_email_smtp.call_args.args[0] == "second@example.test"
    assert email_service._send_email_smtp.call_args.args[4][0][2] == original_csv
    entry = await ledger_db.report_schedule_history.find_one({"_id": initial["history_id"]})
    assert entry["delivery_details"]["sent_count"] == 2
    assert entry["delivery_details"]["failed_count"] == 0


async def test_empty_legacy_recipient_list_is_not_success(ledger_db):
    result = await scheduler._execute_schedule(schedule(recipients=[]))
    assert result["status"] == "failed"
    email_service._send_email_smtp.assert_not_called()


@pytest.mark.parametrize(
    "overrides,day,expected",
    [
        ({"frequency": "daily"}, date(2026, 1, 1), (date(2026, 1, 1), date(2026, 1, 1))),
        ({"frequency": "monthly"}, date(2026, 1, 17), (date(2025, 12, 1), date(2025, 12, 31))),
        ({"frequency": "monthly"}, date(2024, 3, 1), (date(2024, 2, 1), date(2024, 2, 29))),
        ({"date_range": "month_to_date"}, date(2026, 10, 7), (date(2026, 10, 1), date(2026, 10, 7))),
        ({"date_range": "last_7_days", "frequency": "daily"}, date(2026, 1, 1), (date(2025, 12, 26), date(2026, 1, 1))),
    ],
)
def test_periods_are_explicit_and_calendar_safe(overrides, day, expected):
    assert scheduler._report_period(schedule(**overrides), day) == expected


async def test_weekly_occupancy_counts_completed_arrivals_and_actual_room_nights(ledger_db):
    await ledger_db.rooms.insert_many([{"tenant_id": "A", "id": "r1"}, {"tenant_id": "A", "id": "r2"}])
    await ledger_db.bookings.insert_many(
        [
            {"tenant_id": "A", "id": "b", "room_id": "r1", "status": "checked_out", "check_in": "2026-10-01T12:00:00Z", "check_out": datetime(2026, 10, 3, tzinfo=UTC), "total_amount": 200},
            {"tenant_id": "A", "id": "b2", "room_id": "r2", "status": "confirmed", "check_in": "2026-10-01", "check_out": "2026-10-08", "total_amount": 700},
        ]
    )
    payload = await scheduler._build_report_payload(schedule(report_type="daily_summary"), NOW)
    rows = {row["label"]: row["value"] for row in payload["rows"]}
    assert rows["Dönemde gelen (arrivals)"] == 2
    assert rows["Dönemde çıkan (departures)"] == 1
    assert rows["Dolu oda-gece"] == 2
    assert rows["Satılabilir oda-gece"] == 14
    assert rows["Doluluk %"] == 14.29
    assert rows["Toplam gelir (para birimine göre)"] == "0.00"


async def test_uncertain_delivery_and_legacy_partial_history_are_not_blindly_retried(ledger_db):
    await ledger_db.report_schedules.insert_one(schedule())
    for key, extra in [
        ("uncertain", {"schedule_snapshot": schedule(), "delivery_states": [{"recipient": "first@example.test", "status": "sending"}]}),
        ("legacy", {"delivery_details": {"sent_count": 1}}),
    ]:
        await ledger_db.report_schedule_history.insert_one({"_id": key, "tenant_id": "A", "schedule_id": "schedule", "status": "partial", **extra})
        with pytest.raises(HTTPException) as error:
            await scheduler.retry_send(key, USER)
        assert error.value.status_code == 409
    email_service._send_email_smtp.assert_not_called()


async def test_saved_recipient_outcomes_survive_final_history_write_failure(ledger_db, monkeypatch):
    original = schedule(recipients=["first@example.test"])
    await ledger_db.report_schedules.insert_one(original)
    monkeypatch.setattr(scheduler, "_build_report_payload", AsyncMock(return_value={"range": "2026-10-07", "rows": []}))
    history = ledger_db.report_schedule_history
    update = history.update_one
    failed_once = False

    async def fail_final_write(query, operation, *args, **kwargs):
        nonlocal failed_once
        if operation.get("$set", {}).get("status") == "sent" and not failed_once:
            failed_once = True
            raise RuntimeError("isolated injected history failure")
        return await update(query, operation, *args, **kwargs)

    monkeypatch.setattr(
        scheduler,
        "db",
        SimpleNamespace(report_schedule_history=SimpleNamespace(insert_one=history.insert_one, find_one=history.find_one, update_one=fail_final_write), report_schedules=ledger_db.report_schedules),
    )
    result = await scheduler._execute_schedule(original)
    assert result["status"] == "failed"
    assert email_service._send_email_smtp.call_count == 1
    final = await scheduler.retry_send(result["history_id"], USER)
    assert final["status"] == "sent"
    assert email_service._send_email_smtp.call_count == 1


async def test_concurrent_retry_is_claimed_once(ledger_db, monkeypatch):
    original = schedule(recipients=["first@example.test"])
    await ledger_db.report_schedules.insert_one(original)
    monkeypatch.setattr(scheduler, "_build_report_payload", AsyncMock(return_value={"range": "2026-10-07", "rows": []}))
    email_service._send_email_smtp.return_value = False
    initial = await scheduler._execute_schedule(original)
    email_service._send_email_smtp.reset_mock()
    email_service._send_email_smtp.return_value = True
    results = await asyncio.gather(scheduler.retry_send(initial["history_id"], USER), scheduler.retry_send(initial["history_id"], USER), return_exceptions=True)
    assert sum(isinstance(result, HTTPException) for result in results) == 1
    assert sum(isinstance(result, dict) and result["status"] == "sent" for result in results) == 1
    email_service._send_email_smtp.assert_called_once()


async def test_link_references_saved_authorized_history_and_pdf_success_keeps_format(ledger_db, monkeypatch):
    monkeypatch.setenv("PUBLIC_APP_URL", "https://pms.example.test/")
    monkeypatch.setattr(scheduler, "_build_report_payload", AsyncMock(return_value={"range": "2026-10-07", "rows": []}))
    result = await scheduler._execute_schedule(schedule(format="link", recipients=["first@example.test"]))
    assert result["status"] == "sent"
    assert f"/report-scheduler?history_id={result['history_id']}" in email_service._send_email_smtp.call_args.args[2]
    assert email_service._send_email_smtp.call_args.args[4] == []
    monkeypatch.setattr(scheduler, "_payload_to_pdf", lambda *_: b"%PDF-isolated")
    result = await scheduler._execute_schedule(schedule(format="pdf", recipients=["first@example.test"]))
    assert result["status"] == "sent"
    assert email_service._send_email_smtp.call_args.args[4][0][1:] == ("application/pdf", b"%PDF-isolated")


async def test_simulated_send_is_not_a_real_delivery_or_last_sent_timestamp(ledger_db, monkeypatch):
    original = schedule()
    await ledger_db.report_schedules.insert_one(original)
    monkeypatch.setattr(email_service, "mode", "mock")
    result = await scheduler._execute_schedule(original)
    assert result["status"] == "mock" and result["sent_count"] == 0
    saved = await ledger_db.report_schedules.find_one({"_id": "schedule"})
    assert not saved.get("last_sent_at")
    assert saved["total_sent"] == 0
    email_service._send_email_smtp.assert_not_called()


async def test_saved_report_history_requires_manager_in_same_tenant(ledger_db):
    await ledger_db.report_schedule_history.insert_one({"_id": "private", "tenant_id": "B", "report_payload": {"rows": [{"value": 9999}]}})
    with pytest.raises(HTTPException) as error:
        await scheduler.get_history_detail("private", USER)
    assert error.value.status_code == 404
    with pytest.raises(HTTPException) as error:
        await scheduler.get_history_detail("private", SimpleNamespace(tenant_id="B", role="staff"))
    assert error.value.status_code == 403


async def test_all_schedules_are_listed_and_history_total_is_not_page_length(ledger_db):
    await ledger_db.report_schedules.insert_many([schedule(_id=str(i)) for i in range(201)])
    result = await scheduler.list_schedules.__wrapped__(current_user=USER)
    assert result["total"] == len(result["schedules"]) == 201
    await ledger_db.report_schedule_history.insert_many([{"_id": str(i), "tenant_id": "A", "sent_at": "2026-10-07", "report_payload": {"rows": []}, "schedule_snapshot": schedule()} for i in range(3)])
    result = await scheduler.get_history.__wrapped__(schedule_id=None, status=None, limit=2, current_user=USER)
    assert result["total"] == 3 and len(result["history"]) == 2
    assert all("report_payload" not in row and "schedule_snapshot" not in row for row in result["history"])


@pytest.mark.parametrize("first,last", [("invalid", None), (None, "invalid"), ("2026-10-08", "2026-10-01")])
async def test_invalid_invoice_period_is_not_silently_unfiltered(first, last):
    with pytest.raises(HTTPException) as error:
        await accounting.get_accounting_invoices.__wrapped__(start_date=first, end_date=last, current_user=USER)
    assert error.value.status_code == 422


@pytest.mark.parametrize("value", ["", "http://pms.example.test", "https://", "https://[invalid", "https://user:password@pms.example.test", "https://pms.example.test?tab=x"])
def test_report_link_requires_a_valid_https_app_base(monkeypatch, value):
    monkeypatch.setenv("PUBLIC_APP_URL", value)
    assert scheduler._resolve_app_url("saved-report") == ""
