"""Marketplace net-rate contracts: hotel-set season prices, no commission."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from routers import agency_contracts
from routers import marketplace_b2b as marketplace

NET = {"status": "approved", "contract_type": "net_rate", "commission_pct": 0,
       "season_rates": [{"room_type_id": "Superior", "season_start": "2026-11-01", "season_end": "2026-11-30", "price": 700}]}


class _DB(SimpleNamespace):
    def __getitem__(self, name):
        return getattr(self, name)


def _patch(monkeypatch, rows):
    coll = lambda r: SimpleNamespace(find=lambda *a: SimpleNamespace(to_list=AsyncMock(return_value=r)))
    monkeypatch.setattr(marketplace, "db", _DB(agency_rate_calendar=coll(rows), hr_rate_calendar=coll([]), rate_calendar=coll([]),
                                               exely_room_mappings=coll([]), hotelrunner_room_mappings=coll([])))


@pytest.mark.asyncio
async def test_net_contract_sells_without_calendar_as_net_product(monkeypatch):
    _patch(monkeypatch, [])
    result = await marketplace._marketplace_stay_price(
        tenant_id="t", agency_id="a", room_type="Superior", check_in="2026-11-20", check_out="2026-11-22",
        fallback_rate=0, contract=NET,
    )
    assert result["sellable"] and result["rate_plan_code"] == "NET" and result["total_price"] == 1400
    assert await marketplace._agency_rate_plans("t", "a", "Superior", "2026-11-20", "2026-11-22", contract=NET) == ["NET"]


@pytest.mark.asyncio
async def test_net_price_overrides_calendar_but_restrictions_still_apply(monkeypatch):
    _patch(monkeypatch, [{"date": "2026-11-20", "rate": 1000, "rate_plan_code": "BB"},
                         {"date": "2026-11-21", "rate": 1000, "rate_plan_code": "BB", "stop_sell": True}])
    closed = await marketplace._marketplace_stay_price(
        tenant_id="t", agency_id="a", room_type="Superior", check_in="2026-11-20", check_out="2026-11-22",
        fallback_rate=0, contract=NET,
    )
    assert closed["sellable"] is False
    _patch(monkeypatch, [{"date": "2026-11-20", "rate": 1000, "rate_plan_code": "BB"}])
    priced = await marketplace._marketplace_stay_price(
        tenant_id="t", agency_id="a", room_type="Superior", check_in="2026-11-20", check_out="2026-11-21",
        fallback_rate=0, contract=NET,
    )
    assert priced["total_price"] == 700


@pytest.mark.asyncio
async def test_partial_season_coverage_is_not_a_net_product(monkeypatch):
    _patch(monkeypatch, [])
    result = await marketplace._marketplace_stay_price(
        tenant_id="t", agency_id="a", room_type="Superior", check_in="2026-11-30", check_out="2026-12-02",
        fallback_rate=0, contract=NET,
    )
    assert result == {"sellable": False, "nightly_rates": [], "total_price": 0.0, "reason": "agency_rate_not_shared"}


def test_net_contract_has_no_commission():
    assert marketplace._contract_commission(NET) == 0.0
    assert marketplace._contract_commission({"status": "approved", "commission_pct": 12}) == 12.0


def test_approval_requires_seasons_for_net_rate():
    with pytest.raises(ValidationError):
        agency_contracts.ApproveRequest(contract_type="net_rate")
    with pytest.raises(ValidationError):
        agency_contracts.ApproveRequest(contract_type="net_rate", season_rates=[
            {"room_type_id": "Superior", "season_start": "2026-11-30", "season_end": "2026-11-01", "price": 1}])
    ok = agency_contracts.ApproveRequest(contract_type="net_rate", season_rates=[
        {"room_type_id": "Superior", "season_start": "2026-11-01", "season_end": "2026-11-30", "price": 700}])
    assert ok.season_rates[0].price == 700


@pytest.mark.asyncio
async def test_engine_never_sells_a_free_night_or_an_ambiguous_price(monkeypatch):
    async def sale_try(_tenant):
        return "TRY"

    monkeypatch.setattr(marketplace, "_sale_currency", sale_try)
    row = {"room_type_code": "Superior", "rate_plan_code": "BB", "date": "2026-11-20", "rate": 1000}
    stay = {"tenant_id": "t", "agency_id": "a", "room_type": "Superior", "check_in": "2026-11-20", "check_out": "2026-11-21",
                "fallback_rate": 0, "rate_plan_code": "BB"}

    _patch(monkeypatch, [{**row, "rate": 0}])
    assert (await marketplace._marketplace_stay_price(**stay))["reason"] == "zero_rate_night"
    _patch(monkeypatch, [row, {**row, "rate": 1200}])
    assert (await marketplace._marketplace_stay_price(**stay))["reason"] == "duplicate_rate_plan_night"
    _patch(monkeypatch, [row, dict(row)])  # identical copy: not ambiguous
    assert (await marketplace._marketplace_stay_price(**stay))["total_price"] == 1000
