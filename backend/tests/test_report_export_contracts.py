"""Real Mongo → API → workbook checks for operational/export boundaries."""

from datetime import UTC, date, datetime
from io import BytesIO
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from openpyxl import load_workbook

from core import tenant_currency
from modules.pms_core.stay_night_metrics import calculate_stay_night_metrics, load_stay_night_metrics
from routers.departments import housekeeping, reports
from routers.reports_pkg import standard_reports

pytest_plugins = ("tests.test_report_ledger_mongo_acceptance",)
USER = SimpleNamespace(tenant_id="A", role="admin", id="operator", granted_permissions=[])


@pytest.fixture(autouse=True)
def context(ledger_db, monkeypatch):
    for module in (reports, housekeeping, standard_reports):
        monkeypatch.setattr(module, "db", ledger_db)
    monkeypatch.setattr(reports, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": "2026-10-07"}))
    monkeypatch.setattr(standard_reports, "_default_business_date", AsyncMock(return_value=date(2026, 10, 7)))
    monkeypatch.setattr(tenant_currency, "get_tenant_currency", AsyncMock(return_value=("EUR", "€")))


async def sheet(response):
    content = b"".join([chunk async for chunk in response.body_iterator])
    return load_workbook(BytesIO(content)).active


@pytest.mark.parametrize("arrival_bson,departure_bson", [(False, False), (True, True), (True, False), (False, True)])
async def test_revenue_export_keeps_all_date_storage_combinations_and_native_currency(ledger_db, arrival_bson, departure_bson):
    await ledger_db.bookings.insert_many(
        [
            {
                "tenant_id": "A",
                "status": "confirmed",
                "check_in": datetime(2026, 10, 6, 14, tzinfo=UTC) if arrival_bson else "2026-10-06T14:00:00Z",
                "check_out": datetime(2026, 10, 8, 11, tzinfo=UTC) if departure_bson else "2026-10-08T11:00:00Z",
                "total_amount": 100,
            },
            {"tenant_id": "B", "status": "confirmed", "check_in": "2026-10-07", "check_out": "2026-10-08", "total_amount": 999},
            {"tenant_id": "A", "status": "cancelled", "check_in": "2026-10-07", "check_out": "2026-10-08", "total_amount": 999},
        ]
    )
    rows = list((await sheet(await reports.export_revenue_detail_excel("2026-10-07", "2026-10-07", USER))).values)[2:]
    assert len(rows) == 1
    assert rows[0][3:7] == ("EUR", 1, 50, 50)


async def test_revenue_export_adr_excludes_complimentary_room_nights(ledger_db):
    await ledger_db.bookings.insert_many(
        [
            {"tenant_id": "A", "status": "confirmed", "check_in": "2026-10-07", "check_out": "2026-10-08", "total_amount": 100},
            {"tenant_id": "A", "status": "confirmed", "check_in": "2026-10-07", "check_out": "2026-10-08", "total_amount": 999, "is_complimentary": True},
        ]
    )
    rows = list((await sheet(await reports.export_revenue_detail_excel("2026-10-07", "2026-10-07", USER))).values)
    assert rows[1][-1] == "Sold Room Nights"
    assert rows[2][3:] == ("EUR", 2, 100, 100, 1)


async def test_forecast_api_and_excel_use_property_currency_for_legacy_booking(ledger_db):
    await ledger_db.rooms.insert_one({"tenant_id": "A", "id": "r"})
    await ledger_db.bookings.insert_one({"tenant_id": "A", "status": "confirmed", "room_id": "r", "check_in": "2026-10-07", "check_out": "2026-10-08", "total_amount": 20.01})
    metrics = await load_stay_night_metrics(ledger_db, "A", date(2026, 10, 7), date(2026, 10, 7))
    api = await standard_reports.get_forecast.__wrapped__(1, USER)
    rows = list((await sheet(await reports.export_forecast_detail_excel("2026-10-07", "2026-10-07", USER))).values)[2:]
    assert metrics[0]["revenue_by_currency"] == api[0]["expected_revenue_by_currency"] == {"EUR": 20.01}
    assert rows == [("2026-10-07", 100, "EUR", 20.01)]


async def test_operations_excel_counts_bson_arrivals_and_departures_not_other_tenants_or_cancelled(ledger_db):
    await ledger_db.bookings.insert_many(
        [
            {"tenant_id": tenant, "status": status, "check_in": start, "check_out": end}
            for tenant, status, start, end in [
                ("A", "confirmed", datetime(2026, 10, 7, 14, tzinfo=UTC), datetime(2026, 10, 8, 11, tzinfo=UTC)),
                ("A", "checked_out", "2026-10-06", datetime(2026, 10, 7, 11, tzinfo=UTC)),
                ("A", "cancelled", "2026-10-07", "2026-10-08"),
                ("A", "no_show", "2026-10-07", "2026-10-08"),
                ("B", "confirmed", "2026-10-07", "2026-10-08"),
            ]
        ]
    )
    values = dict(list((await sheet(await reports.export_operations_daily_summary_excel("2026-10-07", USER))).values)[2:])
    assert values["Arrivals"] == 1 and values["Departures"] == 1


async def test_housekeeping_screen_and_excel_do_not_truncate_completed_tasks(ledger_db):
    await ledger_db.housekeeping_tasks.insert_many([{"tenant_id": "A", "status": "completed", "completed_at": "2026-10-07", "assigned_to_name": "Staff", "duration_minutes": 10} for _ in range(10001)])
    api = await housekeeping.get_housekeeping_efficiency_report.__wrapped__("2026-10-07", "2026-10-07", USER)
    assert api["total_tasks_completed"] == 10001
    assert api["staff_performance"]["Staff"]["tasks_completed"] == 10001
    rows = list((await sheet(await housekeeping.export_housekeeping_efficiency_excel("2026-10-07", "2026-10-07", USER))).values)[2:]
    assert rows[0][1:4] == (10001, 10001, 10)


async def test_housekeeping_completion_date_precedence_supports_bson_and_legacy_empty_dates(ledger_db):
    await ledger_db.housekeeping_tasks.insert_many(
        [
            {"tenant_id": "A", "status": "completed", "completed_at": datetime(2026, 10, 7, 12, tzinfo=UTC), "created_at": "2026-10-01"},
            {"tenant_id": "A", "task_status": "completed", "completed_at": "", "created_at": datetime(2026, 10, 7, tzinfo=UTC)},
            {"tenant_id": "A", "status": "completed", "completed_at": "2026-10-08", "created_at": "2026-10-07"},
            {"tenant_id": "A", "status": "pending", "completed_at": "2026-10-07"},
            {"tenant_id": "B", "status": "completed", "completed_at": "2026-10-07"},
        ]
    )
    api = await housekeeping.get_housekeeping_efficiency_report.__wrapped__("2026-10-07", "2026-10-07", USER)
    assert api["total_tasks_completed"] == 2


async def test_housekeeping_unknown_duration_is_not_counted_as_zero_minutes(ledger_db):
    await ledger_db.housekeeping_tasks.insert_many(
        [
            {"tenant_id": "A", "status": "completed", "completed_at": "2026-10-07", "assigned_to_name": "Staff", **fields}
            for fields in [
                {"duration_minutes": 20},
                {},
                {"duration_minutes": "invalid"},
                {"duration_minutes": -5},
                {"duration_minutes": None, "started_at": "2026-10-07T00:00:00Z", "completed_at": datetime(2026, 10, 7, 0, 10, tzinfo=UTC)},
            ]
        ]
    )
    api = await housekeeping.get_housekeeping_efficiency_report.__wrapped__("2026-10-07", "2026-10-07", USER)
    staff = api["staff_performance"]["Staff"]
    assert staff["tasks_completed"] == 5
    assert staff["average_minutes"] == 15
    assert staff["timed_tasks"] == 2 and staff["missing_duration_tasks"] == 3
    values = list((await sheet(await housekeeping.export_housekeeping_efficiency_excel("2026-10-07", "2026-10-07", USER))).values)
    assert values[2][3] == 15 and values[2][-2:] == (2, 3)


@pytest.mark.parametrize("duration", [None, "invalid", -1, float("inf"), float("nan")])
def test_unknown_duration_is_not_a_zero_minute_measurement(duration):
    assert housekeeping._task_duration_minutes({"duration_minutes": duration}) is None


def test_zero_minute_measurement_is_not_replaced_with_unknown():
    assert housekeeping._task_duration_minutes({"duration_minutes": 0}) == 0


def test_room_night_adr_and_revpar_round_half_up_like_the_exports():
    data = calculate_stay_night_metrics(
        [{"status": "confirmed", "room_id": room, "check_in": "2026-10-07", "check_out": "2026-10-08", "total_amount": amount, "currency": "EUR"} for room, amount in [("r1", 1), ("r2", 1.01)]],
        [{"id": "r1"}, {"id": "r2"}],
        date(2026, 10, 7),
        date(2026, 10, 7),
    )
    assert data[0]["adr_by_currency"] == data[0]["revpar_by_currency"] == {"EUR": 1.01}


@pytest.mark.parametrize(
    "module,handler,kwargs,prefix",
    [
        (standard_reports, "get_forecast", {"days": 1}, "report_forecast_v3"),
        (standard_reports, "get_occupancy_report", {"start_date": "2026-10-07", "end_date": "2026-10-07"}, "report_occupancy_v3"),
        (housekeeping, "get_housekeeping_efficiency_report", {"start_date": "2026-10-07", "end_date": "2026-10-07"}, "report_hk_efficiency_v2"),
    ],
)
async def test_corrected_reports_cannot_reuse_the_old_cache(monkeypatch, module, handler, kwargs, prefix):
    import cache_manager

    cache = SimpleNamespace(enabled=True, get=MagicMock(side_effect=lambda key: None if f":{prefix}:" in key else {"stale": True}), set=MagicMock())
    monkeypatch.setattr(cache_manager, "cache", cache)
    assert await getattr(module, handler)(current_user=USER, **kwargs) != {"stale": True}
    assert f":{prefix}:" in cache.get.call_args.args[0]
    cache.set.assert_called_once()


@pytest.mark.parametrize("first,last", [("invalid", "2026-10-07"), ("2026-10-08", "2026-10-07")])
async def test_housekeeping_invalid_period_returns_validation_error(first, last):
    with pytest.raises(HTTPException) as error:
        await housekeeping.get_housekeeping_efficiency_report.__wrapped__(first, last, USER)
    assert error.value.status_code == 422


async def test_operations_invalid_day_returns_validation_error():
    with pytest.raises(HTTPException) as error:
        await reports.export_operations_daily_summary_excel("invalid", USER)
    assert error.value.status_code == 422
