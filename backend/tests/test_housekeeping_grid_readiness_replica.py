"""The room grid and check-in must agree on vacant room readiness."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from routers.hotel_services_pkg import housekeeping_settings as hk
from routers.hotel_services_pkg._common import RoomStatusUpdate
from tests.test_pos_final_consistency_replica import db as db


@pytest.fixture
def user():
    return SimpleNamespace(tenant_id="t", name="Operator", tenant_type="hotel")


@pytest.fixture
def wired(db, monkeypatch):
    monkeypatch.setattr(hk, "db", db)
    monkeypatch.setattr(hk, "_ensure_hotel_context", lambda *_: None)
    monkeypatch.setattr(hk, "_invalidate_housekeeping", lambda *_: None)
    monkeypatch.setattr("websocket_server.broadcast_room_status_update", AsyncMock())


@pytest.mark.asyncio
@pytest.mark.parametrize("initial,owner,new,expected", [
    ("dirty", None, "clean", "available"), ("dirty", None, "inspected", "inspected"),
    ("available", None, "cleaning", "cleaning"), ("inspected", None, "dirty", "dirty"),
    ("available", None, "out_of_order", "out_of_order"),
    ("occupied", "guest", "inspected", "occupied"),
    ("dirty", "guest", "clean", "dirty"),
    ("maintenance", None, "clean", "maintenance"),
    ("out_of_order", None, "inspected", "out_of_order"),
])
async def test_grid_updates_readiness_without_releasing_occupancy_or_a_block(db, wired, user, initial, owner, new, expected):
    await db.rooms.insert_many([
        {"id": "r", "tenant_id": "t", "room_number": "101", "status": initial, "current_booking_id": owner},
        {"id": "r", "tenant_id": "other", "status": "dirty"},
    ])
    await hk.update_room_housekeeping_status("r", RoomStatusUpdate(status=new), user, None)
    room = await db.rooms.find_one({"tenant_id": "t"})
    assert room["status"] == expected and room["current_booking_id"] == owner
    assert room["housekeeping_status"] == room["hk_status"] == new
    assert (await db.rooms.find_one({"tenant_id": "other"}))["status"] == "dirty"


@pytest.mark.asyncio
@pytest.mark.parametrize("bulk", [False, True])
async def test_grid_rejects_cleaning_when_occupancy_changed_during_the_action(db, wired, user, monkeypatch, bulk):
    await db.rooms.insert_one({"id": "r", "tenant_id": "t", "status": "available", "current_booking_id": None})
    original = type(db.rooms).update_one

    async def race(self, query, update, *args, **kwargs):
        if self.name == "rooms" and "housekeeping_status" in update.get("$set", {}):
            await original(self, {"id": "r", "tenant_id": "t"}, {"$set": {"status": "occupied", "current_booking_id": "new-guest"}})
        return await original(self, query, update, *args, **kwargs)

    monkeypatch.setattr(type(db.rooms), "update_one", race)
    if bulk:
        result = await hk.bulk_update_room_status(["r"], "clean", user, None)
        assert result == {"success": False, "updated_count": 0, "conflicted_room_ids": ["r"]}
    else:
        with pytest.raises(HTTPException) as rejected:
            await hk.update_room_housekeeping_status("r", RoomStatusUpdate(status="clean"), user, None)
        assert rejected.value.status_code == 409
    room = await db.rooms.find_one({"tenant_id": "t"})
    assert "housekeeping_status" not in room
    assert room["status"] == "occupied" and room["current_booking_id"] == "new-guest"
    assert await db.housekeeping_log.count_documents({}) == 0


@pytest.mark.asyncio
async def test_bulk_keeps_occupied_and_blocked_rooms_and_ignores_foreign_ids(db, wired, user):
    await db.rooms.insert_many([
        {"id": "vacant", "tenant_id": "t", "status": "dirty"},
        {"id": "busy", "tenant_id": "t", "status": "occupied", "current_booking_id": "guest"},
        {"id": "blocked", "tenant_id": "t", "status": "out_of_order"},
        {"id": "foreign", "tenant_id": "other", "status": "dirty"},
    ])
    result = await hk.bulk_update_room_status(["vacant", "busy", "blocked", "foreign"], "inspected", user, None)
    assert result == {"success": True, "updated_count": 3, "conflicted_room_ids": []}
    rooms = {row["id"]: row async for row in db.rooms.find({})}
    assert rooms["vacant"]["status"] == "inspected" and rooms["busy"]["status"] == "occupied"
    assert rooms["blocked"]["status"] == "out_of_order" and rooms["foreign"]["status"] == "dirty"


@pytest.mark.asyncio
@pytest.mark.parametrize("bulk", [False, True])
async def test_grid_rejects_unknown_status_without_writing(db, wired, user, bulk):
    await db.rooms.insert_one({"id": "r", "tenant_id": "t", "status": "dirty"})
    with pytest.raises(HTTPException) as rejected:
        if bulk:
            await hk.bulk_update_room_status(["r"], "anything", user, None)
        else:
            await hk.update_room_housekeeping_status("r", RoomStatusUpdate(status="anything"), user, None)
    assert rejected.value.status_code == 422
    assert "housekeeping_status" not in await db.rooms.find_one({"tenant_id": "t"})
