"""Mounted HTTP + real Mongo: wall-clock delay must not hide business-day cash."""
from datetime import UTC, datetime

import pytest

from domains.pms import cashier_router
from tests.test_frontdesk_acceptance_replica import frontdesk_acceptance as frontdesk_acceptance

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def wire_cashier(acceptance, monkeypatch):
    monkeypatch.setattr(cashier_router, "db", acceptance.db)
    acceptance.api._transport.app.include_router(cashier_router.router)


def shift(sid="delayed", tenant="qa", **extra):
    return {"_id": sid, "tenant_id": tenant, "business_date": "2026-10-26", "closed_business_date": "2026-10-26",
        "opened_at": "2026-10-31T16:00:00", "closed_at": "2026-10-31T17:00:00", "status": "closed",
        "opening_amount": 0, "closing_amount": 60, "difference": 0, "cash_in": 100, "cash_out": 40,
        "transactions": [{"id": "in", "business_date": "2026-10-26", "created_at": "2026-10-31T16:01:00", "amount": 100, "direction": "in", "method": "cash", "currency": "TRY"},
                         {"id": "out", "business_date": "2026-10-26", "created_at": "2026-10-31T16:02:00", "amount": 40, "direction": "out", "method": "cash", "currency": "TRY"}], **extra}


async def period(a, day):
    response = await a.api.get(f"/api/cashier/period-report?start_date={day}&end_date={day}")
    assert response.status_code == 200, response.text
    return response.json()


async def test_delayed_shift_and_transactions_belong_to_the_accounting_day_not_creation_day(acceptance):
    a = acceptance
    await a.db.cashier_shifts.insert_many([shift(), shift("foreign", "other")])
    actual = await period(a, "2026-10-26")
    assert [row["shift_id"] for row in actual["shifts"]] == ["delayed"]
    assert actual["totals"]["cash_in_total"] == 100
    assert actual["totals"]["cash_out_total"] == 40
    assert actual["totals"]["closing_total"] == actual["totals"]["expected_total"] == 60
    assert actual["totals"]["transaction_count"] == 2
    assert (await period(a, "2026-10-31"))["shifts"] == []


async def test_close_only_day_and_later_postings_are_not_lost_by_shift_open_date_filter(acceptance):
    a = acceptance
    await a.db.cashier_shifts.insert_one(shift(opened_at="2026-10-20T15:00:00", closed_at="2026-10-27T15:00:00", business_date="2026-10-20", closed_business_date="2026-10-27"))
    actual = await period(a, "2026-10-26")
    assert actual["totals"]["cash_in_total"] == 100 and actual["totals"]["opening_total"] == 0
    closed = await period(a, "2026-10-27")
    assert closed["totals"]["closing_total"] == 60
    assert closed["totals"]["transaction_count"] == 0


async def test_legacy_unstamped_shift_keeps_wall_clock_fallback_and_read_only_role_cannot_read(acceptance):
    a = acceptance
    row = shift("legacy")
    row.pop("business_date"); row.pop("closed_business_date")
    for txn in row["transactions"]:
        txn.pop("business_date")
    await a.db.cashier_shifts.insert_one(row)
    assert (await period(a, "2026-10-31"))["totals"]["cash_in_total"] == 100
    assert (await period(a, "2026-10-26"))["shifts"] == []
    a.user.role = "guest"
    assert (await a.api.get("/api/cashier/period-report")).status_code == 403


async def test_bson_accounting_days_survive_late_wall_clock_and_invalid_dates_are_controlled(acceptance):
    a = acceptance
    row = shift()
    for field in ("business_date", "closed_business_date"):
        row[field] = datetime(2026, 10, 26, tzinfo=UTC)
    for txn in row["transactions"]:
        txn["business_date"] = datetime(2026, 10, 26, tzinfo=UTC)
    await a.db.cashier_shifts.insert_one(row)
    assert (await period(a, "2026-10-26"))["totals"]["cash_in_total"] == 100
    for start, end in (("2026-10-26T00:00:00", "2026-10-26"), ("2026-10-27", "2026-10-26"), ("2026-02-30", "2026-10-26")):
        response = await a.api.get(f"/api/cashier/period-report?start_date={start}&end_date={end}")
        assert response.status_code == 400


@pytest.mark.parametrize("end", ["not-a-date", "2026-02-30", "2026-10-26T00:00:00", "9999-12-31"])
async def test_invalid_end_only_query_is_controlled_before_default_start_is_computed(acceptance, end):
    response = await acceptance.api.get("/api/cashier/period-report", params={"end_date": end})
    assert response.status_code == 400
