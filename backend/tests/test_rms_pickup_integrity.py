"""The secondary RMS booking-window report must use the shared sales contract."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.revenue.rms_router import revenue_reports as reports

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
USER = SimpleNamespace(tenant_id="A")


@pytest.fixture(autouse=True)
def context(ledger_db, monkeypatch):
    monkeypatch.setattr(reports, "db", ledger_db)
    monkeypatch.setattr(reports, "get_current_user", AsyncMock(return_value=USER))
    monkeypatch.setattr(reports, "get_tenant_currency", AsyncMock(return_value=("EUR", "€")), raising=False)


async def booking(database, **extra):
    await database.bookings.insert_one({"tenant_id": "A", "id": "b", "status": "confirmed", "check_in": "2026-10-01",
        "check_out": "2026-10-03", "created_at": "2026-09-01", "total_amount": 100, "currency": "EUR", **extra})


async def report(format="json"):
    return await reports.get_pickup_report.__wrapped__("2026-10-01", "2026-10-02", format, USER)


@pytest.mark.parametrize("status", ["draft", "pending", "tentative", "cancelled", "noshow", "unknown"])
async def test_rms_does_not_turn_non_sales_into_booked_revenue(ledger_db, status):
    await booking(ledger_db, status=status)
    assert (await report())["summary"]["total_rooms"] == 0


@pytest.mark.parametrize("extra,amount", [({"is_complimentary": True, "total_amount": 999}, 0),
    ({"total_amount": None, "total": 1.005}, 1.01), ({"total_amount": 0, "total": 999}, 0)])
async def test_rms_shares_comp_zero_legacy_and_cent_rules(ledger_db, extra, amount):
    await booking(ledger_db, nights=99, **extra)
    result = await report()
    assert result["summary"]["total_revenue_by_currency"] == {"EUR": amount}
    assert result["summary"]["total_room_nights"] == 2


@pytest.mark.parametrize("extra", [{"check_out": "bad"}, {"check_out": "2026-10-01"}, {"tenant_id": "B"}])
async def test_rms_does_not_count_invalid_stays_or_other_tenants(ledger_db, extra):
    await booking(ledger_db, **extra)
    assert (await report())["summary"]["total_rooms"] == 0


async def test_rms_csv_does_not_fabricate_try_or_hide_unknown_amount_currencies(ledger_db):
    empty = await report("csv")
    assert {row["Currency"] for row in empty["data"]} == {"EUR"}
    await booking(ledger_db, currency="USD", total_amount="NaN")
    result = await report("csv")
    usd = next(row for row in result["data"] if row["Currency"] == "USD")
    assert usd["Total Rooms"] == 1 and usd["Total Revenue"] is None
    assert usd["Invalid Amounts"] == 1


@pytest.mark.parametrize("first,last", [("20261001", "2026-10-02"), ("2026-10-01T12:00:00", "2026-10-02"),
    ("2026-10-01", "9999-12-31"), ("2026-10-03", "2026-10-01")])
async def test_rms_validates_canonical_bounded_dates(first, last):
    with pytest.raises(HTTPException) as invalid:
        await reports.get_pickup_report.__wrapped__(first, last, "json", USER)
    assert invalid.value.status_code == 422


async def test_rms_uses_one_uncapped_query_for_the_entire_window_and_honors_bson(ledger_db, monkeypatch):
    collection = ledger_db.bookings
    calls = []
    def find(*args):
        calls.append(args)
        return collection.find(*args)
    monkeypatch.setattr(reports, "db", SimpleNamespace(bookings=SimpleNamespace(find=find)))
    await booking(ledger_db, check_in=datetime(2026, 10, 2, 23, tzinfo=UTC), check_out="2026-10-04")
    result = await report()
    assert result["summary"]["total_rooms"] == 1
    assert len(calls) == 1


async def test_rms_cache_is_scoped_to_resolved_tenant_and_new_calculation_version(ledger_db, monkeypatch):
    import cache_manager

    memory = object.__new__(cache_manager.CacheManager)
    memory.enabled = True
    memory.backend = "memory"
    memory.client = cache_manager._InMemoryTTLStore()
    monkeypatch.setattr(cache_manager, "cache", memory)
    await booking(ledger_db)
    await booking(ledger_db, tenant_id="B", total_amount=999)
    results = []
    for tenant in ["A", "B", "A"]:
        results.append(await reports.get_pickup_report("2026-10-01", "2026-10-02", "json", current_user=SimpleNamespace(tenant_id=tenant), _nocache=False))
    assert [row["summary"]["total_revenue"] for row in results] == [100, 999, 100]
    keys = memory.client.keys("*")
    assert any(key.startswith("cache:A:rev_pickup_report_v3:") for key in keys)
    assert any(key.startswith("cache:B:rev_pickup_report_v3:") for key in keys)
