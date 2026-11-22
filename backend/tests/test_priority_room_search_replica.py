"""Date-aware room search and current group assignments on isolated local Mongo."""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.revenue.analytics_router.frontdesk import get_available_rooms_for_assignment
from modules.inventory import repository as inventory
from tests.test_frontdesk_acceptance_replica import frontdesk_acceptance as frontdesk_acceptance  # noqa: F401


@pytest.mark.asyncio
async def test_room_search_checks_each_night_blocks_tenant_and_fresh_bookings(acceptance, monkeypatch):
    a = acceptance
    monkeypatch.setattr(inventory, "db", a.db)
    for rid, status in [("free", "occupied"), ("overlap", "available"), ("blocked", "available"),
                        ("boundary", "dirty"), ("maintenance", "out_of_order")]:
        await a.db.rooms.insert_one({"id": rid, "tenant_id": "qa", "room_number": rid,
                                    "room_type": "Superior", "status": status, "capacity": 2})
    await a.db.bookings.insert_many([
        {"id": "future", "tenant_id": "qa", "room_id": "overlap", "status": "confirmed", "check_in": "2026-11-13", "check_out": "2026-11-15"},
        {"id": "previous", "tenant_id": "qa", "room_id": "boundary", "status": "checked_in", "check_in": "2026-11-10", "check_out": "2026-11-12"},
        {"id": "next", "tenant_id": "qa", "room_id": "boundary", "status": "guaranteed", "check_in": "2026-11-14", "check_out": "2026-11-17"},
        {"id": "cancelled", "tenant_id": "qa", "room_id": "free", "status": "cancelled", "check_in": "2026-11-12", "check_out": "2026-11-14"},
        {"id": "other-hotel", "tenant_id": "foreign", "room_id": "free", "status": "confirmed", "check_in": "2026-11-12", "check_out": "2026-11-14"},
    ])
    await a.db.room_blocks.insert_many([
        {"id": "block", "tenant_id": "qa", "room_id": "blocked", "status": "active", "type": "maintenance", "start_date": "2026-11-13", "end_date": "2026-11-14", "allow_sell": False},
        {"id": "sellable", "tenant_id": "qa", "room_id": "free", "status": "active", "start_date": "2026-11-12", "end_date": None, "allow_sell": True},
    ])
    async def search():
        return await get_available_rooms_for_assignment("2026-11-12", "2026-11-14", "Superior", a.user)
    before = await search()
    assert {r["id"] for r in before["rooms"]} == {"free", "boundary"}
    assert before["count"] == 2
    assert before["check_in"] == "2026-11-12" and before["check_out"] == "2026-11-14"
    await a.db.bookings.insert_one({"id": "new-stay", "tenant_id": "qa", "room_id": "free", "status": "confirmed", "check_in": "2026-11-12", "check_out": "2026-11-14"})
    assert {r["id"] for r in (await search())["rooms"]} == {"boundary"}
    foreign = await get_available_rooms_for_assignment("2026-11-12", "2026-11-14", "Superior", SimpleNamespace(tenant_id="foreign"))
    assert foreign["rooms"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("arrival,departure", [("2026-11-14", "2026-11-12"), ("2026-11-12", "2026-11-12"), ("2026-02-30", "2026-03-01"), ("bad", "2026-11-14")])
async def test_room_search_rejects_invalid_range(arrival, departure):
    with pytest.raises(HTTPException) as error:
        await get_available_rooms_for_assignment(arrival, departure, None, SimpleNamespace(tenant_id="qa"))
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_group_list_and_detail_resolve_current_room_without_foreign_data(acceptance):
    a = acceptance
    await a.db.group_bookings.insert_one({"id": "group-a", "tenant_id": "qa", "group_name": "Local group", "booking_ids": ["synthetic-stay", "unassigned", "foreign-room"], "created_at": "2026-11-12"})
    await a.db.rooms.insert_one({"id": "room-elsewhere", "tenant_id": "foreign", "room_number": "SECRET", "room_type": "Suite"})
    await a.db.bookings.insert_many([
        {"id": "unassigned", "tenant_id": "qa", "room_number": "OLD", "total_amount": 100},
        {"id": "foreign-room", "tenant_id": "qa", "room_id": "room-elsewhere", "room_number": "STALE", "total_amount": 100},
    ])
    async def read_group():
        listing = await a.api.get("/api/pms/group-bookings?nocache=true")
        detail = await a.api.get("/api/pms/group-bookings/group-a")
        assert listing.status_code == detail.status_code == 200
        for group in [listing.json()["groups"][0], detail.json()]:
            assert group["total_amount"] == 760
            rows = {b["id"]: b for b in group["bookings"]}
            assert rows["unassigned"]["room_number"] is None
            assert rows["foreign-room"]["room_number"] is None
            yield rows["synthetic-stay"]["room_number"]
    assert [number async for number in read_group()] == ["QA104", "QA104"]
    await a.db.rooms.insert_one({"id": "new-room", "tenant_id": "qa", "room_number": "QA118", "room_type": "Superior"})
    await a.db.bookings.update_one({"id": "synthetic-stay"}, {"$set": {"room_id": "new-room"}})
    assert [number async for number in read_group()] == ["QA118", "QA118"]
    a.user.tenant_id = "foreign"
    assert (await a.api.get("/api/pms/group-bookings/group-a")).status_code == 404


@pytest.mark.asyncio
@pytest.mark.parametrize('suffix', ['T12:00:00+00:00', 'T12:00:00+03:00', 'T12:00:00Z'])
async def test_room_search_excludes_checkout_day_even_with_operational_hours(acceptance, monkeypatch, suffix):
    a = acceptance
    monkeypatch.setattr(inventory, 'db', a.db)
    await a.db.rooms.insert_one({'id': 'turnover', 'tenant_id': 'qa', 'room_number': '118', 'room_type': 'Superior', 'status': 'occupied'})
    await a.db.bookings.insert_one({'id': 'leaving', 'tenant_id': 'qa', 'room_id': 'turnover', 'status': 'checked_in',
                                  'check_in': '2026-11-12T14:00:00+00:00', 'check_out': '2026-11-14' + suffix})
    during = await get_available_rooms_for_assignment('2026-11-13', '2026-11-14', 'Superior', a.user)
    assert during['count'] == 0
    turnover = await get_available_rooms_for_assignment('2026-11-14', '2026-11-15', 'Superior', a.user)
    assert [r['room_number'] for r in turnover['rooms']] == ['118']
    await a.db.bookings.insert_one({'id': 'next', 'tenant_id': 'qa', 'room_id': 'turnover', 'status': 'confirmed',
                                  'check_in': '2026-11-15T14:00:00+00:00', 'check_out': '2026-11-17T12:00:00+00:00'})
    assert (await get_available_rooms_for_assignment('2026-11-14', '2026-11-15', 'Superior', a.user))['count'] == 1
    assert (await get_available_rooms_for_assignment('2026-11-15', '2026-11-16', 'Superior', a.user))['count'] == 0
