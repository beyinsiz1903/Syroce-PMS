"""Why an agency is not selling: search outcomes and the hotel's checklist."""

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from routers import agency_contracts
from routers import agency_readiness as ar
from routers import marketplace_b2b as m
from tests.unit.test_agency_statements_symmetric import _Coll

TODAY = date(2026, 10, 17)


# ── search records why each hotel returned nothing ──────────────────


@pytest.fixture
def search_world(monkeypatch):
    from core import agency_hotel_directory

    contract = {"status": "approved", "commission_pct": 10, "currency": "TRY"}
    listing = {"tenant_id": "t", "hotel_name": "Otel", "currency": "TRY", "content_agency_ids": []}
    rooms = [{"id": rid, "tenant_id": "t", "room_type": "Standard", "capacity": 2, "base_price": 100} for rid in ("r1", "r2")]
    database = SimpleNamespace(rooms=_Coll(rooms), bookings=_Coll(), hotel_content=_Coll())
    monkeypatch.setattr(m, "db", database)
    monkeypatch.setattr(m, "get_system_db", lambda: database)
    monkeypatch.setattr(agency_contracts, "list_active_contracts", AsyncMock(return_value={"t": contract}))
    monkeypatch.setattr(agency_hotel_directory, "hotel_profiles", AsyncMock(return_value=[listing]))
    monkeypatch.setattr(m, "_agency_rate_plans", AsyncMock(return_value=["RO"]))
    monkeypatch.setattr(m, "_marketplace_stay_price", AsyncMock(return_value={"sellable": True, "total_price": 200, "nightly_rates": [], "shared_availability": 5}))

    async def occupancy(**kwargs):
        return kwargs["pricing"]

    monkeypatch.setattr(m, "_marketplace_occupancy_price", occupancy)
    logged = []

    async def log(agency, req, outcomes, count):
        logged.append((outcomes, count))

    monkeypatch.setattr(m, "log_agency_search", log)
    return database, logged


QUERY = m.MarketplaceSearchRequest(check_in="2026-11-20", check_out="2026-11-22")


@pytest.mark.asyncio
async def test_search_records_ok(search_world):
    _, logged = search_world
    await m.agency_search(QUERY, {"agency_id": "a"})
    assert logged == [({"t": "ok"}, 1)]


@pytest.mark.asyncio
async def test_search_records_missing_rate_and_price(search_world, monkeypatch):
    _, logged = search_world
    monkeypatch.setattr(m, "_agency_rate_plans", AsyncMock(return_value=[]))
    await m.agency_search(QUERY, {"agency_id": "a"})
    monkeypatch.setattr(m, "_agency_rate_plans", AsyncMock(return_value=["RO"]))
    monkeypatch.setattr(m, "_marketplace_stay_price", AsyncMock(return_value={"sellable": False, "total_price": 0, "nightly_rates": []}))
    await m.agency_search(QUERY, {"agency_id": "a"})
    assert [entry[0]["t"] for entry in logged] == ["no_rate", "no_price"]


@pytest.mark.asyncio
async def test_search_records_full_hotel_and_rooms_too_small(search_world, monkeypatch):
    _, logged = search_world
    monkeypatch.setattr(m, "_marketplace_stay_price", AsyncMock(return_value={"sellable": True, "total_price": 200, "nightly_rates": [], "shared_availability": 0}))
    await m.agency_search(QUERY, {"agency_id": "a"})
    await m.agency_search(m.MarketplaceSearchRequest(check_in="2026-11-20", check_out="2026-11-22", adults=5), {"agency_id": "a"})
    assert [entry[0]["t"] for entry in logged] == ["no_availability", "no_room"]


@pytest.mark.asyncio
async def test_search_without_any_contract_is_logged(search_world, monkeypatch):
    _, logged = search_world
    monkeypatch.setattr(agency_contracts, "list_active_contracts", AsyncMock(return_value={}))
    await m.agency_search(QUERY, {"agency_id": "a"})
    assert logged == [({}, 0)]


@pytest.mark.asyncio
async def test_search_log_failure_never_breaks_a_search(monkeypatch):
    monkeypatch.setattr(m, "get_system_db", lambda: SimpleNamespace())  # no collection at all
    await m.log_agency_search({"agency_id": "a"}, QUERY, {"t": "ok"}, 1)  # must not raise


# ── the hotel's checklist ────────────────────────────────────────────


def _contract(agency_id, **extra):
    return {"tenant_id": "t1", "agency_id": agency_id, "agency_name": agency_id.upper(), "contract_code": f"SOZ-{agency_id}",
            "status": "approved", "valid_from": "2026-01-01", "valid_to": "2027-12-31", "created_at": "2026-10-01", **extra}


@pytest.fixture
def world():
    recent = "2026-10-16T10:00:00+00:00"
    return SimpleNamespace(
        agency_contracts=_Coll([_contract("good"), _contract("norate"), _contract("ending", valid_to="2026-11-01"),
                                _contract("pending", status="pending"), _contract("silent")]),
        marketplace_agencies=_Coll([{"id": a, "name": a.title(), "status": "active"} for a in ("good", "norate", "ending", "pending", "silent")]),
        users=_Coll([{"agency_id": a, "role": "marketplace_agent", "is_active": True, "last_login": recent} for a in ("good", "norate", "ending", "pending")]
                    + [{"agency_id": "silent", "role": "marketplace_agent", "onboarding_status": "invited", "agency_invite_expires": "2026-10-01"}]),
        marketplace_search_log=_Coll([
            {"agency_id": "good", "at": recent, "outcomes": {"t1": "ok"}},
            {"agency_id": "norate", "at": recent, "outcomes": {"t1": "no_rate"}},
            {"agency_id": "norate", "at": recent, "outcomes": {"t1": "no_rate"}},
            {"agency_id": "norate", "at": recent, "outcomes": {"t1": "no_availability"}},
        ]),
        marketplace_bookings=_Coll([{"tenant_id": "t1", "agency_id": "good", "status": "confirmed", "created_at": "2026-10-15"}]),
    )


def _row(rows, agency_id):
    return next(row for row in rows if row["agency_id"] == agency_id)


def _find(row, key):
    return next(check for check in row["checks"] if check["key"] == key)


@pytest.mark.asyncio
async def test_checklist_explains_each_agency_and_points_to_the_fix(world):
    credit = AsyncMock(side_effect=lambda tenant, agency, contract, sysdb: {"limit": 10000, "used": 10000 if agency == "ending" else 0,
                                                                         "available": 0 if agency == "ending" else 10000, "currency": "TRY"})
    rows = await ar.agency_readiness(world, "t1", TODAY, credit=credit)
    good, norate, ending, pending, silent = (_row(rows, a) for a in ("good", "norate", "ending", "pending", "silent"))
    assert good["status"] == "ok" and good["bookings"] == 1
    searches = _find(norate, "searches")
    assert searches["level"] == "error" and "Fiyat paylaşılmamış (2)" in searches["message"]
    assert searches["action"] == {"label": "Fiyat paylaş", "path": "/unified-rate-manager"}
    assert norate["search_reasons"] == {"no_rate": 2, "no_availability": 1}
    assert _find(ending, "contract")["level"] == "warn" and _find(ending, "credit")["level"] == "error"
    assert _find(pending, "contract")["action"]["path"] == "/app/incoming-agency-contracts"
    assert _find(silent, "portal_user")["level"] == "error" and "süresi dolmuş" in _find(silent, "portal_user")["message"]
    assert _find(silent, "searches")["level"] == "warn"
    assert [row["status"] for row in rows][:1] == ["error"] and rows[-1]["agency_id"] == "good"  # problems first


@pytest.mark.asyncio
@pytest.mark.parametrize("reason,expected", [("agency_allotment_exhausted", "no_availability"), ("min_stay", "restricted"),
                                             ("agency_rate_not_shared", "no_rate"), ("zero_rate_night", "no_price")])
async def test_search_keeps_the_engine_reason(search_world, monkeypatch, reason, expected):
    _, logged = search_world
    monkeypatch.setattr(m, "_marketplace_stay_price", AsyncMock(return_value={"sellable": False, "total_price": 0, "nightly_rates": [], "reason": reason}))
    await m.agency_search(QUERY, {"agency_id": "a"})
    assert logged[-1][0]["t"] == expected


@pytest.mark.asyncio
async def test_expired_but_still_approved_contract_blocks_sales(world):
    world.agency_contracts.rows = [_contract("old", valid_to="2026-10-01")]
    world.marketplace_agencies.rows.append({"id": "old", "name": "Old", "status": "active"})
    rows = await ar.agency_readiness(world, "t1", TODAY, credit=AsyncMock(return_value=None))
    check = _find(_row(rows, "old"), "contract")
    assert check["level"] == "error" and "süresi" in check["message"] and rows[0]["status"] == "error"


@pytest.fixture
def nights_world(monkeypatch):
    import core.agency_hotel_directory as directory
    import core.database as core_database

    rooms = [{"id": "r1", "tenant_id": "t1", "room_type": "Standard", "capacity": 2, "base_price": 100}]
    monkeypatch.setattr(core_database, "db", SimpleNamespace(rooms=_Coll(rooms)))
    monkeypatch.setattr(directory, "hotel_profiles", AsyncMock(return_value=[{"tenant_id": "t1"}]))
    monkeypatch.setattr(agency_contracts, "list_active_contracts", AsyncMock(return_value={"t1": {"status": "approved"}}))
    monkeypatch.setattr(ar, "get_system_db", lambda: SimpleNamespace())
    monkeypatch.setattr(m, "_agency_rate_plans", AsyncMock(return_value=["RO"]))
    monkeypatch.setattr(m, "_occupied_room_count", AsyncMock(return_value=0))
    monkeypatch.setattr(m, "_marketplace_stay_price", AsyncMock(return_value={"sellable": True, "total_price": 100, "nightly_rates": [], "shared_availability": 3}))


@pytest.mark.asyncio
async def test_nights_apply_the_occupancy_rule_like_search(nights_world, monkeypatch):
    async def ok(**kwargs):
        return kwargs["pricing"]

    monkeypatch.setattr(m, "_marketplace_occupancy_price", ok)
    assert [n["status"] for n in await ar.sellable_nights("t1", "a1", TODAY, 2)] == ["ok", "ok"]

    async def refused(**kwargs):
        return {**kwargs["pricing"], "sellable": False, "reason": "occupancy_rule_currency_mismatch"}

    monkeypatch.setattr(m, "_marketplace_occupancy_price", refused)
    assert [n["status"] for n in await ar.sellable_nights("t1", "a1", TODAY, 1)] == ["no_price"]


@pytest.mark.asyncio
async def test_nights_show_a_full_allotment_as_no_availability(nights_world, monkeypatch):
    async def ok(**kwargs):
        return kwargs["pricing"]

    monkeypatch.setattr(m, "_marketplace_occupancy_price", ok)
    monkeypatch.setattr(m, "_marketplace_stay_price", AsyncMock(return_value={"sellable": False, "total_price": 0, "nightly_rates": [], "reason": "agency_allotment_exhausted"}))
    assert [n["status"] for n in await ar.sellable_nights("t1", "a1", TODAY, 1)] == ["no_availability"]


@pytest.mark.asyncio
async def test_nights_filter_rooms_by_capacity_like_search(nights_world, monkeypatch):
    import core.database as core_database

    async def ok(**kwargs):
        return kwargs["pricing"]

    monkeypatch.setattr(m, "_marketplace_occupancy_price", ok)
    singles = [{"id": f"s{i}", "tenant_id": "t1", "room_type": "Single", "capacity": 1, "base_price": 60} for i in range(2)]
    monkeypatch.setattr(core_database, "db", SimpleNamespace(rooms=_Coll(singles)))
    assert [n["status"] for n in await ar.sellable_nights("t1", "a1", TODAY, 1)] == ["no_room"]


@pytest.mark.asyncio
@pytest.mark.parametrize("calendar,expected", [({"stop_sell": True}, "closed"), ({"availability": 0}, "no_availability")])
async def test_engine_names_stop_sell_and_zero_allotment(calendar, expected):
    from routers.marketplace_b2b import pricing_rejection_category

    assert m._REJECTION_CATEGORY["stop_sell"] == "closed" and m._REJECTION_CATEGORY["no_allotment"] == "no_availability"
    reason = "stop_sell" if calendar.get("stop_sell") else "no_allotment"
    assert pricing_rejection_category({"sellable": False, "reason": reason}, 3) == expected
