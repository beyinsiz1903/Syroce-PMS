"""Forecast, pickup and pace must agree with stay nights, inventory and currency."""

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.revenue import forecast_router as reports

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
USER = SimpleNamespace(tenant_id="A")
TODAY = "2026-10-18"


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 10, 18, 12, tzinfo=UTC)


@pytest.fixture(autouse=True)
def context(ledger_db, monkeypatch):
    monkeypatch.setattr(reports, "datetime", Clock)
    monkeypatch.setattr(reports, "get_system_db", lambda: ledger_db)
    monkeypatch.setattr(reports, "get_tenant_currency", AsyncMock(return_value=("EUR", "€")))


async def booking(db, **extra):
    await db.bookings.insert_one({"tenant_id": "A", "check_in": TODAY, "check_out": "2026-10-19", "status": "confirmed",
        "created_at": "2026-10-17", "total_amount": 100, "currency": "EUR", **extra})


async def forecast():
    return await reports.forecast(days=2, segment=None, user=USER)


@pytest.mark.parametrize("start_bson,end_bson", [(False, False), (False, True), (True, False), (True, True)])
async def test_forecast_uses_per_night_sellable_capacity_and_exclusive_block_end(ledger_db, start_bson, end_bson):
    await ledger_db.rooms.insert_many([{"tenant_id": "A", "id": "r1"}, {"tenant_id": "A", "id": "r2"},
        {"tenant_id": "A", "id": "inactive", "is_active": False}, {"tenant_id": "B", "id": "foreign"}])
    await ledger_db.room_blocks.insert_one({"tenant_id": "A", "room_id": "r2", "status": "active", "start_date": Clock(2026, 10, 18, tzinfo=UTC) if start_bson else TODAY,
        "end_date": Clock(2026, 10, 19, tzinfo=UTC) if end_bson else "2026-10-19"})
    await booking(ledger_db, room_id="r1")
    rows = (await forecast())["daily"]
    assert [row["available_rooms"] for row in rows] == [1, 2]
    assert rows[0]["occupancy_pct"] == 100
    assert rows[0]["revpar_by_currency"] == {"EUR": 100}


async def test_forecast_does_not_remove_committed_rooms_or_inflate_adr_when_oversold(ledger_db):
    await ledger_db.rooms.insert_one({"tenant_id": "A", "id": "r"})
    await booking(ledger_db)
    await booking(ledger_db)
    row = (await forecast())["daily"][0]
    assert row["rooms_otb"] == row["rooms_forecast"] == 2
    assert row["overbooked_rooms"] == 1
    assert row["adr_by_currency"] == {"EUR": 100}
    assert row["occupancy_pct"] == 200


async def test_no_capacity_with_commitments_does_not_claim_zero_occupancy_or_revpar(ledger_db):
    await booking(ledger_db)
    row = (await forecast())["daily"][0]
    assert row["rooms_forecast"] == 1
    assert row["capacity_conflict"] is True
    assert row["occupancy_pct"] is None and row["revpar"] is None
    assert row["adr_by_currency"] == {"EUR": 100}


async def test_comp_room_counts_in_occupancy_but_not_the_paid_adr_denominator(ledger_db):
    await ledger_db.rooms.insert_many([{"tenant_id": "A", "id": "r1"}, {"tenant_id": "A", "id": "r2"}])
    await booking(ledger_db)
    await booking(ledger_db, is_complimentary=True, total_amount=999)
    row = (await forecast())["daily"][0]
    assert row["rooms_otb"] == 2
    assert row["revenue_otb_by_currency"] == {"EUR": 100}
    assert row["adr_by_currency"] == {"EUR": 100}


async def test_empty_forecast_keeps_property_currency_instead_of_fabricating_try(ledger_db):
    result = await forecast()
    assert result["currency"] == "EUR"
    assert all(row["revenue_forecast_by_currency"] == {"EUR": 0} for row in result["daily"])


@pytest.mark.parametrize("extra,expected", [
    ({"status": "in_house", "check_in": "2026-10-11", "check_out": "2026-10-13", "total_amount": 200}, 2),
    ({"status": "checked_out", "check_in": "2026-10-04", "check_out": "2026-10-07", "checked_out_at": "2026-10-05T10:00:00Z", "total_amount": 300}, 1),
])
async def test_history_includes_legacy_inhouse_and_stops_at_actual_early_checkout(ledger_db, extra, expected):
    await ledger_db.rooms.insert_one({"tenant_id": "A", "id": "r"})
    await booking(ledger_db, **extra)
    result = await forecast()
    assert result["data_quality"]["historical_room_nights"] == expected


@pytest.mark.parametrize("status", ["draft", "pending", "tentative", "cancelled", "canceled", "noshow", "no_show"])
async def test_nonconfirmed_booking_is_neither_otb_pace_nor_pickup(ledger_db, status):
    await booking(ledger_db, status=status)
    assert (await forecast())["daily"][0]["rooms_otb"] == 0
    assert (await reports.pace(target_date=TODAY, compare_year=None, user=USER))["current"] == []
    assert (await reports.pickup_report(period_days=7, user=USER))["total_rooms_picked"] == 0


async def test_pickup_does_not_turn_comp_reference_amount_into_booked_income(ledger_db):
    await booking(ledger_db, is_complimentary=True, total_amount=999)
    await booking(ledger_db, total_amount=0, total=999, currency="USD")
    await booking(ledger_db, total_amount=100)
    result = await reports.pickup_report(period_days=7, user=USER)
    assert result["total_rooms_picked"] == 3
    assert result["total_revenue_picked_by_currency"] == {"EUR": 100, "USD": 0}


async def test_pickup_excludes_invalid_or_zero_night_stays_and_other_tenants(ledger_db):
    for extra in [{"check_out": TODAY}, {"check_out": "bad-date"}, {"tenant_id": "B"}]:
        await booking(ledger_db, **extra)
    assert (await reports.pickup_report(period_days=7, user=USER))["total_rooms_picked"] == 0


async def test_pace_target_night_includes_stayovers_but_not_departures(ledger_db):
    await booking(ledger_db, check_in="2026-10-17", check_out="2026-10-19")
    await booking(ledger_db, check_in="2026-10-17", check_out=TODAY)
    result = await reports.pace(target_date=TODAY, compare_year=None, user=USER)
    assert result["current"] == [{"days_out": 1, "rooms_on_books": 1}, {"days_out": 0, "rooms_on_books": 1}]


async def test_pace_does_not_draw_unobserved_future_days_as_actual_flat_data(ledger_db):
    await booking(ledger_db, check_in="2026-10-28", check_out="2026-10-29")
    await booking(ledger_db, check_in="2026-10-28", check_out="2026-10-29", created_at="2026-10-20")
    result = await reports.pace(target_date="2026-10-28", compare_year=None, user=USER)
    assert result["current"] == [{"days_out": 11, "rooms_on_books": 1}, {"days_out": 10, "rooms_on_books": 1}]


@pytest.mark.parametrize("day", ["2026-10-18T12:00:00", "20261018", "2026-02-30", ""])
async def test_pace_rejects_noncanonical_target_days(day):
    with pytest.raises(HTTPException) as invalid:
        await reports.pace(target_date=day, compare_year=None, user=USER)
    assert invalid.value.status_code == 422


@pytest.mark.parametrize("year", [0, -1, 10000, 2025])
async def test_pace_rejects_invalid_comparison_instead_of_returning_empty_success(year):
    with pytest.raises(HTTPException) as invalid:
        await reports.pace(target_date="2024-02-29", compare_year=year, user=USER)
    assert invalid.value.status_code == 422


def test_forecast_adr_uses_decimal_half_up_not_binary_bankers_rounding():
    rows, _ = reports._build_forecast_rows({TODAY: {"rooms": 2, "revenue_by_currency": {"EUR": 2.01}}}, {}, 2, Clock(2026, 10, 18, tzinfo=UTC))
    assert rows[0]["adr_by_currency"] == {"EUR": 1.01}


async def test_forecast_does_not_keep_early_departed_stay_in_future_otb(ledger_db):
    await booking(ledger_db, status="checked_out", check_in="2026-10-16", check_out="2026-10-20", checked_out_at="2026-10-17T10:00:00Z")
    assert all(row["rooms_otb"] == 0 for row in (await forecast())["daily"])


async def test_capacity_does_not_subtract_duplicate_blocks_or_sellable_and_foreign_blocks(ledger_db):
    await ledger_db.rooms.insert_many([{"tenant_id": "A", "id": "r1"}, {"tenant_id": "A", "id": "r2"}])
    await ledger_db.room_blocks.insert_many([
        {"tenant_id": "A", "room_id": "r1", "status": "active", "start_date": TODAY},
        {"tenant_id": "A", "room_id": "r1", "status": "active", "start_date": TODAY},
        {"tenant_id": "A", "room_id": "r2", "status": "active", "start_date": TODAY, "allow_sell": True},
        {"tenant_id": "B", "room_id": "r2", "status": "active", "start_date": TODAY},
    ])
    assert all(row["available_rooms"] == 1 for row in (await forecast())["daily"])


def test_historical_forecast_projects_comp_share_without_diluting_paid_adr():
    day = {TODAY: {"rooms": 1, "sold_rooms": 1, "revenue_by_currency": {"EUR": 100}}}
    history = {"2026-10-11": {"rooms": 4, "sold_rooms": 2, "revenue_by_currency": {"EUR": 200}}}
    rows, _ = reports._build_forecast_rows(day, history, 4, Clock(2026, 10, 18, tzinfo=UTC))
    row = rows[0]
    assert row["rooms_forecast"] == 4
    assert row["sold_rooms_forecast"] == 2.5
    assert row["revenue_forecast_by_currency"] == {"EUR": 250}
    assert row["adr_by_currency"] == {"EUR": 100}


def test_small_positive_forecast_is_not_rounded_to_zero_rooms():
    from datetime import timedelta

    history = {(Clock(2026, 10, 11, tzinfo=UTC) - timedelta(weeks=week)).date().isoformat():
        {"rooms": 1 if week == 0 else 0, "revenue_by_currency": {"EUR": 100 if week == 0 else 0}} for week in range(52)}
    rows, _ = reports._build_forecast_rows({TODAY: {"rooms": 0, "revenue_by_currency": {"EUR": 0}}}, history, 10, Clock(2026, 10, 18, tzinfo=UTC))
    assert rows[0]["rooms_forecast"] == 0.02
    assert rows[0]["revenue_forecast_by_currency"]["EUR"] > 0


async def test_compare_database_failure_is_not_reported_as_an_empty_curve(monkeypatch):
    class Collection:
        def __init__(self):
            self.calls = 0

        def find(self, query):
            self.calls += 1
            if self.calls == 2:
                raise RuntimeError("comparison database unavailable")
            return self

        def __aiter__(self):
            async def rows():
                for row in []:
                    yield row
            return rows()

    monkeypatch.setattr(reports, "get_system_db", lambda: SimpleNamespace(bookings=Collection()))
    with pytest.raises(RuntimeError, match="comparison database unavailable"):
        await reports.pace(target_date=TODAY, compare_year=2025, user=USER)
