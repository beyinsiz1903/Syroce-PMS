"""Virtual holder rooms (is_virtual, capacity 99) are not agency inventory."""

from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from core.sellable_rooms import PHYSICAL_ROOM_FILTER
from routers import agency_contracts
from routers import marketplace_b2b as marketplace

ROOMS = [
    {"id": "r1", "room_type": "Superior", "capacity": 3, "base_price": 9200},
    {"id": "v1", "room_type": "Superior", "capacity": 99, "base_price": 9200, "is_virtual": True, "room_number": "V-SUP"},
]


def _find(query, *_args):
    rows = [room for room in ROOMS if not (query.get("is_virtual") == {"$ne": True} and room.get("is_virtual"))]
    return SimpleNamespace(to_list=AsyncMock(return_value=rows))


@pytest.mark.asyncio
async def test_hotel_availability_counts_only_physical_rooms(monkeypatch):
    monkeypatch.setattr(agency_contracts, "has_active_contract", AsyncMock(return_value={"status": "approved", "commission_pct": 15}))
    monkeypatch.setattr(marketplace, "_get_listing_or_404", AsyncMock(return_value={"hotel_name": "Test"}))
    monkeypatch.setattr(marketplace, "tenant_context", lambda _tenant: nullcontext())
    monkeypatch.setattr(marketplace, "db", SimpleNamespace(
        rooms=SimpleNamespace(find=_find),
        bookings=SimpleNamespace(find=lambda *a: SimpleNamespace(to_list=AsyncMock(return_value=[]))),
    ))
    pricing = {"sellable": True, "rate_plan_code": "BASE", "nightly_rates": [], "total_price": 9200}
    monkeypatch.setattr(marketplace, "_marketplace_stay_price", AsyncMock(return_value=pricing))
    monkeypatch.setattr(marketplace, "_marketplace_occupancy_price", AsyncMock(return_value=pricing))

    result = await marketplace.agency_hotel_availability(
        tenant_id="t1", check_in="2026-11-20", check_out="2026-11-21", adults=2, child_ages=[],
        rate_plan_code=None, agency={"agency_id": "a1"},
    )

    room = result["room_types"][0]
    assert (room["total_rooms"], room["available_rooms"], room["capacity"]) == (1, 1, 3)


def test_filter_shape():
    assert PHYSICAL_ROOM_FILTER == {"is_virtual": {"$ne": True}}
