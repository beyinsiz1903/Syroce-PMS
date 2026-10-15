"""Regression: two agency endpoints raised NameError (HTTP 500) at runtime."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers import agency_contracts, agency_portal
from routers import marketplace_b2b as marketplace


@pytest.mark.asyncio
async def test_legacy_net_rate_contract_prices_without_name_error(monkeypatch):
    contract = {
        "contract_type": "net_rate",
        "season_rates": [
            {"room_type_id": "standard", "season_start": "2026-11-01", "season_end": "2026-11-30", "price": 750},
        ],
    }
    monkeypatch.setattr(agency_portal, "_legacy_active_contract", AsyncMock(return_value=contract))

    price, has_contract = await agency_portal._get_b2b_price(
        None, "t1", "a1", "2026-11-10", "standard", 1000.0, "2026-11-12"
    )

    assert (price, has_contract) == (750.0, True)


@pytest.mark.asyncio
async def test_hotel_availability_uses_query_occupancy(monkeypatch):
    contract = {"status": "approved", "commission_pct": 10}
    monkeypatch.setattr(agency_contracts, "has_active_contract", AsyncMock(return_value=contract))
    monkeypatch.setattr(marketplace, "_get_listing_or_404", AsyncMock(return_value={"hotel_name": "Test", "currency": "TRY"}))
    monkeypatch.setattr(marketplace, "tenant_context", lambda _tenant: nullcontext())
    rooms = [{"id": "r1", "room_type": "standard", "capacity": 3, "base_price": 100}]
    monkeypatch.setattr(marketplace, "db", SimpleNamespace(
        rooms=SimpleNamespace(find=lambda *a: SimpleNamespace(to_list=AsyncMock(return_value=rooms))),
        bookings=SimpleNamespace(find=lambda *a: SimpleNamespace(to_list=AsyncMock(return_value=[]))),
    ))
    pricing = {"sellable": True, "rate_plan_code": "BB", "nightly_rates": [{"date": "2026-11-10", "rate": 100}], "total_price": 100}
    monkeypatch.setattr(marketplace, "_marketplace_stay_price", AsyncMock(return_value=pricing))
    occupancy = AsyncMock(return_value={**pricing, "total_price": 130, "occupancy_pricing": {"pricing_type": "per_room"}})
    monkeypatch.setattr(marketplace, "_marketplace_occupancy_price", occupancy)

    result = await marketplace.agency_hotel_availability(
        tenant_id="t1", check_in="2026-11-10", check_out="2026-11-11", adults=2, child_ages=[7],
        rate_plan_code=None, agency={"agency_id": "a1"},
    )

    assert occupancy.await_args.kwargs["adults"] == 2
    assert occupancy.await_args.kwargs["child_ages"] == [7]
    room = result["room_types"][0]
    assert (room["available_rooms"], room["total_price"], room["rate_plan_code"]) == (1, 130, "BB")
