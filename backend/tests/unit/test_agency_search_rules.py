"""Agency search: physical-room availability, contract room types and
catalogue visibility (regressions from the 2026-10-15 vision audit)."""
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers import agency_contracts
from routers import marketplace_b2b as m


def expr(value, row):
    if isinstance(value, str) and value.startswith("$"):
        return row.get(value[1:])
    if not isinstance(value, dict):
        return value
    op, args = next(iter(value.items()))
    if op == "$toString":
        return str(expr(args, row))
    if op == "$substrBytes":
        return expr(args[0], row)[args[1]:args[1] + args[2]]
    if op == "$and":
        return all(expr(arg, row) for arg in args)
    left, right = [expr(arg, row) for arg in args]
    return left < right if op == "$lt" else left > right


def matches(row, query):
    for key, val in query.items():
        if key == "$expr":
            if not expr(val, row):
                return False
            continue
        got = row.get(key)
        if isinstance(val, dict):
            for op, want in val.items():
                if op == "$in" and got not in want: return False
                if op == "$ne" and got == want: return False
                if op == "$nin" and got in want: return False
                if op == "$lt" and not got < want: return False
                if op == "$gt" and not got > want: return False
                if op == "$gte" and not got >= want: return False
                if op == "$lte" and not got <= want: return False
        elif got != val:
            return False
    return True


class Cursor:
    def __init__(self, rows): self.rows = copy.deepcopy(rows)
    async def to_list(self, length): return self.rows if length is None else self.rows[:length]
    def __aiter__(self):
        async def iterate():
            for row in self.rows: yield row
        return iterate()


class Store:
    def __init__(self, rows=()): self.rows = copy.deepcopy(list(rows))
    def find(self, query, *_a, **_k): return Cursor([r for r in self.rows if matches(r, query)])
    async def find_one(self, query, *_a, **_k):
        return next((copy.deepcopy(r) for r in self.rows if matches(r, query)), None)
    async def count_documents(self, query): return len([r for r in self.rows if matches(r, query)])
    async def update_one(self, query, update, **_k):
        for row in self.rows:
            if matches(row, query):
                row.update(copy.deepcopy(update.get("$set", {})))
                return SimpleNamespace(matched_count=1)
        return SimpleNamespace(matched_count=0)


@pytest.fixture
def search_world(monkeypatch):
    from core import agency_hotel_directory
    contract = {"status": "approved", "commission_pct": 10, "currency": "TRY"}
    listing = {"tenant_id": "t", "hotel_name": "Audit Hotel", "currency": "TRY", "content_agency_ids": []}
    rooms = [{"id": rid, "tenant_id": "t", "room_type": "Standard", "capacity": 2, "base_price": 100}
             for rid in ("r1", "r2")]
    database = SimpleNamespace(rooms=Store(rooms), bookings=Store(),
        hotel_content=Store([{"tenant_id": "t", "description": "private hotel description", "images": ["private-hotel.jpg"],
            "room_types": [{"room_type": "Standard", "description": "private room description", "images": ["private-room.jpg"]}]}]))
    monkeypatch.setattr(m, "db", database)
    monkeypatch.setattr(m, "get_system_db", lambda: database)
    monkeypatch.setattr(agency_contracts, "list_active_contracts", AsyncMock(return_value={"t": contract}))
    monkeypatch.setattr(agency_contracts, "has_active_contract", AsyncMock(return_value=contract))
    monkeypatch.setattr(agency_hotel_directory, "hotel_profiles", AsyncMock(return_value=[listing]))
    monkeypatch.setattr(m, "_get_listing_or_404", AsyncMock(return_value=listing))
    monkeypatch.setattr(m, "_agency_rate_plans", AsyncMock(return_value=["RO"]))
    monkeypatch.setattr(m, "_marketplace_stay_price", AsyncMock(return_value={
        "sellable": True, "total_price": 200, "nightly_rates": [], "shared_availability": 5}))
    async def occupancy(**kwargs): return kwargs["pricing"]
    monkeypatch.setattr(m, "_marketplace_occupancy_price", occupancy)
    return database, contract


QUERY = m.MarketplaceSearchRequest(check_in="2026-11-20", check_out="2026-11-22")
AGENCY = {"agency_id": "a"}


@pytest.mark.asyncio
async def test_back_to_back_stays_in_one_room_leave_the_other_room_sellable(search_world):
    database, _ = search_world
    database.bookings.rows = [
        {"id": "b1", "tenant_id": "t", "room_id": "r1", "status": "confirmed", "check_in": "2026-11-20T14:00:00", "check_out": "2026-11-21T11:00:00"},
        {"id": "b2", "tenant_id": "t", "room_id": "r1", "status": "confirmed", "check_in": "2026-11-21T14:00:00", "check_out": "2026-11-22T11:00:00"},
    ]
    result = await m.agency_search(QUERY, AGENCY)
    assert result["total_hotels"] == 1
    assert result["results"][0]["available_room_types"][0]["available_rooms"] == 1  # r2 is free
    database.bookings.rows.append({"id": "b3", "tenant_id": "t", "room_id": "r2", "status": "confirmed",
                                   "check_in": "2026-11-20T14:00:00", "check_out": "2026-11-22T11:00:00"})
    assert (await m.agency_search(QUERY, AGENCY))["total_hotels"] == 0  # both rooms truly busy


@pytest.mark.asyncio
async def test_search_never_offers_a_room_type_the_contract_excludes(search_world):
    _, contract = search_world
    contract["allowed_room_types"] = ["Suite"]
    assert (await m.agency_search(QUERY, AGENCY))["total_hotels"] == 0
    detail = await m.agency_get_hotel("t", AGENCY)
    assert detail["room_types"] == []
    contract["allowed_room_types"] = ["Standard"]
    assert (await m.agency_search(QUERY, AGENCY))["results"][0]["available_room_types"][0]["room_type"] == "Standard"


@pytest.mark.asyncio
async def test_hidden_catalogue_hides_room_media_too(search_world):
    room = (await m.agency_search(QUERY, AGENCY))["results"][0]["available_room_types"][0]
    assert room["images"] == [] and room["description"] == ""
    hotel = (await m.agency_search(QUERY, AGENCY))["results"][0]
    assert hotel["photos"] == [] and hotel["description"] == ""
