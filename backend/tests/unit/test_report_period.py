"""Report periods in the hotel's calendar (modules.pms_core.report_period)."""

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi import HTTPException

from modules.pms_core.report_period import day_bounds, instant_between, instant_value, local_today, parse_day, parse_month

IST = ZoneInfo("Europe/Istanbul")


def test_month_bounds_include_the_whole_last_day_and_cross_the_year():
    assert parse_month("2026-12") == (date(2026, 12, 1), date(2026, 12, 31))
    assert parse_month("2028-02") == (date(2028, 2, 1), date(2028, 2, 29))      # leap year
    lower, upper = day_bounds(*parse_month("2026-12"), IST)
    assert lower == datetime(2026, 11, 30, 21, tzinfo=UTC)                    # 1 Dec 00:00 local
    assert upper == datetime(2026, 12, 31, 21, tzinfo=UTC)                    # 1 Jan 00:00 local, exclusive


def test_midnight_belongs_to_the_day_it_starts():
    lower, upper = day_bounds(date(2026, 10, 19), date(2026, 10, 19), IST)
    assert lower == datetime(2026, 10, 18, 21, tzinfo=UTC) and upper == datetime(2026, 10, 19, 21, tzinfo=UTC)
    prefilter, exact = instant_between("t", lower, upper)["$and"]
    assert {"t": {"$gte": lower, "$lt": upper}} in prefilter["$or"]             # BSON dates (index)
    # Text window wide enough for any offset (-12..+14); the exact test is on instants.
    assert {"t": {"$gte": "2026-10-18T07:00:00", "$lt": "2026-10-20T11:00:00"}} in prefilter["$or"]
    assert "$expr" in exact
    last_second = datetime(2026, 10, 19, 20, 59, 59, tzinfo=UTC)               # 23:59:59 local
    assert lower <= last_second < upper
    assert not (lower <= datetime(2026, 10, 19, 21, tzinfo=UTC) < upper)      # next local midnight


def test_local_today_uses_the_hotel_zone():
    assert local_today(IST, datetime(2026, 10, 18, 22, 30, tzinfo=UTC)) == date(2026, 10, 19)
    assert local_today(ZoneInfo("UTC"), datetime(2026, 10, 18, 22, 30, tzinfo=UTC)) == date(2026, 10, 18)


@pytest.mark.parametrize("value", ["bad", "2026-13", "2026", "", None])
def test_malformed_month_is_a_client_error(value):
    with pytest.raises(HTTPException) as exc:
        parse_month(value)
    assert exc.value.status_code == 422


@pytest.mark.parametrize("value", ["bad", "2026-02-30", "19.10.2026"])
def test_malformed_day_is_a_client_error(value):
    with pytest.raises(HTTPException) as exc:
        parse_day(value)
    assert exc.value.status_code == 422


def test_backwards_period_is_a_client_error():
    with pytest.raises(HTTPException) as exc:
        day_bounds(date(2026, 10, 2), date(2026, 10, 1), IST)
    assert exc.value.status_code == 422


def test_stored_instants_read_from_text_or_datetime():
    assert instant_value("2026-10-19T00:01:00Z") == datetime(2026, 10, 19, 0, 1, tzinfo=UTC)
    assert instant_value(datetime(2026, 10, 19, 0, 1)) == datetime(2026, 10, 19, 0, 1, tzinfo=UTC)
    assert instant_value("not a date") is None
