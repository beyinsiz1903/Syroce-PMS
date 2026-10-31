"""Normal HTTP write -> real Mongo -> room/search/cache read, LOCAL only."""
# ruff: noqa: F811
from copy import deepcopy
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

import cache_warmer
import redis_cache
from core.security import get_current_user
from domains.pms import operations_router as operations
from routers import pms_rooms
from tests.test_pos_final_consistency_replica import db  # noqa: F401


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["database", "redis", "warmer"])
async def test_public_dnd_roundtrip_survives_list_search_and_stale_cache(db, monkeypatch, source):
    user = SimpleNamespace(id="qa-operator", email="qa@example.invalid", name="Synthetic QA", tenant_id="t", role="super_admin", is_super_admin=True, granted_permissions=None)
    rooms = [{"id": f"room-{i}", "room_number": f"QA{i:03}", "tenant_id": "t", "dnd": False, "status": "occupied"} for i in range(100)]
    await db.rooms.insert_many(deepcopy(rooms))
    await db.rooms.insert_one({"id": "foreign", "tenant_id": "other", "dnd": False})
    stale = deepcopy(rooms)
    untouched = deepcopy(stale)
    monkeypatch.setattr(pms_rooms, "db", db)
    monkeypatch.setattr(operations, "db", db)
    monkeypatch.setattr(redis_cache, "redis_cache", SimpleNamespace(get=lambda key: stale, clear_pattern=lambda key: None) if source == "redis" else None)
    monkeypatch.setattr(cache_warmer, "cache_warmer", SimpleNamespace(get_cached=lambda key, **kwargs: stale, invalidate=lambda *keys: None) if source == "warmer" else None)
    app = FastAPI()
    app.include_router(operations.router)
    app.include_router(pms_rooms.router)
    app.dependency_overrides[get_current_user] = lambda: user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local-dnd-qa") as client:
        for before, desired in ((False, True), (True, False)):
            result = await client.patch("/api/pms/rooms/room-0/features", json={"dnd": desired, "expected_dnd": before})
            assert result.status_code == 200 and result.json()["dnd"] is desired
            response = await client.get("/api/pms/rooms?limit=100")
            assert response.status_code == 200
            row = next(room for room in response.json() if room["id"] == "room-0")
            assert row["dnd"] is desired and "features_audit" not in row
            search = await client.get("/api/pms/rooms?search=QA000&limit=3")
            assert search.status_code == 200 and len(search.json()) == 1
            assert search.json()[0]["dnd"] is desired
        denied = await client.patch("/api/pms/rooms/foreign/features", json={"dnd": True})
        assert denied.status_code == 404
    saved = await db.rooms.find_one({"id": "room-0", "tenant_id": "t"})
    assert saved["dnd"] is False and len(saved["features_audit"]) == 2
    assert all(event["actor_id"] == user.id for event in saved["features_audit"])
    assert stale == untouched
    assert (await db.rooms.find_one({"id": "foreign"}))["dnd"] is False
    for name in ("bookings", "payments", "folio_charges", "stock_movements"):
        assert await db[name].count_documents({}) == 0
