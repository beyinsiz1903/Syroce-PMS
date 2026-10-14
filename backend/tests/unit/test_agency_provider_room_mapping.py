"""Exely/HotelRunner hotels: agency calendars use provider codes and currencies."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.channel_manager import unified_rate_manager_router as urm
from routers import marketplace_b2b as marketplace


class _Coll:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def find(self, query, *_):
        self.queries.append(query)
        return SimpleNamespace(to_list=AsyncMock(return_value=self.rows))


class _DB(SimpleNamespace):
    def __getitem__(self, name):
        return getattr(self, name)


@pytest.mark.asyncio
async def test_stay_price_reads_rows_written_under_exely_code(monkeypatch):
    agency_rows = _Coll([{"date": "2026-11-20", "rate": 120, "room_type_code": "5001575", "rate_plan_code": "BB", "currency": "TRY"}])
    db = _DB(
        agency_rate_calendar=agency_rows, hr_rate_calendar=_Coll([]), rate_calendar=_Coll([]),
        exely_room_mappings=_Coll([{"exely_room_code": "5001575"}]), hotelrunner_room_mappings=_Coll([]),
    )
    monkeypatch.setattr(marketplace, "db", db)
    monkeypatch.setattr(marketplace, "_sale_currency", AsyncMock(return_value="TRY"))

    result = await marketplace._marketplace_stay_price(
        tenant_id="t", agency_id="a", room_type="Deluxe", check_in="2026-11-20", check_out="2026-11-21", fallback_rate=0,
    )

    assert result["sellable"] is True and result["total_price"] == 120
    assert agency_rows.queries[0]["room_type_code"] == {"$in": ["Deluxe", "5001575"]}


@pytest.mark.asyncio
async def test_foreign_currency_rate_is_not_sold(monkeypatch):
    db = _DB(
        agency_rate_calendar=_Coll([{"date": "2026-11-20", "rate": 120, "currency": "USD"}]),
        hr_rate_calendar=_Coll([]), rate_calendar=_Coll([]),
        exely_room_mappings=_Coll([]), hotelrunner_room_mappings=_Coll([]),
    )
    monkeypatch.setattr(marketplace, "db", db)
    monkeypatch.setattr(marketplace, "_sale_currency", AsyncMock(return_value="TRY"))

    result = await marketplace._marketplace_stay_price(
        tenant_id="t", agency_id="a", room_type="Deluxe", check_in="2026-11-20", check_out="2026-11-21", fallback_rate=0,
    )

    assert result == {"sellable": False, "nightly_rates": [], "total_price": 0.0, "reason": "currency_mismatch"}


def test_pms_named_row_wins_over_provider_alias():
    rows = [
        {"date": "d1", "rate_plan_code": "BB", "room_type_code": "5001575", "rate": 1},
        {"date": "d1", "rate_plan_code": "BB", "room_type_code": "Deluxe", "rate": 2},
    ]
    assert [r["rate"] for r in marketplace._prefer_pms_rows(rows, "Deluxe")] == [2]


@pytest.mark.asyncio
async def test_unmapped_pms_room_types_are_agency_only(monkeypatch):
    monkeypatch.setattr(urm, "_active_agency_docs_for_tenant", AsyncMock(return_value=[{"id": "a1"}]))
    monkeypatch.setattr(urm, "_pms_room_type_names", AsyncMock(return_value=["Deluxe", "Superior"]))
    monkeypatch.setattr(urm, "db", _DB(exely_room_mappings=_Coll([{"pms_room_type": "Deluxe", "exely_room_code": "5001575"}])))

    extra = await urm._agency_only_room_types("t", "exely", {"5001575"})

    assert extra == [{"code": "Superior", "name": "Superior (yalnız acente)", "agency_only": True}]


@pytest.mark.asyncio
async def test_rate_currency_follows_provider():
    assert await urm._rate_currency("t", {"provider": "exely", "connection": {"currency": "usd"}}) == "USD"
    hr = {"provider": "hotelrunner", "connection": {"cached_rooms": [{"sales_currency": "EUR"}]}}
    assert await urm._rate_currency("t", hr) == "EUR"
