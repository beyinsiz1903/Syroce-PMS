"""Normal HTTP/RBAC + durable local Mongo; never production or providers."""
# ruff: noqa: F811
import asyncio
from types import SimpleNamespace

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI

from core.security import get_current_user
from domains.guest import profile_udf_router as udf
from domains.pms import operations_router as ops
from tests.test_pos_final_consistency_replica import db  # noqa: F401


@pytest_asyncio.fixture
async def api(db, monkeypatch):
    monkeypatch.setattr(ops, "db", db)
    monkeypatch.setattr(udf, "get_system_db", lambda: db)
    user = SimpleNamespace(id="qa-operator", name="Synthetic QA", email="qa@example.invalid", tenant_id="t", role="admin", is_super_admin=False, granted_permissions=None)
    app = FastAPI()
    app.include_router(ops.router)
    app.include_router(udf.router)
    app.dependency_overrides[get_current_user] = lambda: user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local-frontdesk-qa") as client:
        yield client, user


@pytest.mark.asyncio
async def test_room_public_id_reload_audit_retry_and_foreign_tenant_are_isolated(db, api):
    client, user = api
    await db.rooms.insert_many([
        {"_id": "internal", "id": "public", "tenant_id": "t", "dnd": False, "status": "occupied", "room_number": "QA101"},
        {"_id": "foreign-storage", "id": "foreign", "tenant_id": "other", "dnd": False},
    ])
    before = await db.rooms.find_one({"_id": "internal"})
    response = await client.patch("/api/pms/rooms/public/features", json={"dnd": True, "expected_dnd": False})
    assert response.status_code == 200, response.text
    row = await db.rooms.find_one({"_id": "internal"})
    assert row["dnd"] is True and row["status"] == before["status"] and row["room_number"] == before["room_number"]
    assert row["features_updated_by_id"] == user.id
    assert len(row["features_audit"]) == 1 and row["features_audit"][0]["actor_id"] == user.id
    assert (await client.patch("/api/pms/rooms/public/features", json={"dnd": True})).json()["already_applied"] is True
    assert len((await db.rooms.find_one({"_id": "internal"}))["features_audit"]) == 1
    assert (await client.patch("/api/pms/rooms/public/features", json={"dnd": False, "expected_dnd": False})).status_code == 409
    assert (await client.patch("/api/pms/rooms/foreign/features", json={"dnd": True})).status_code == 404
    assert (await client.patch("/api/pms/rooms/internal/features", json={"dnd": False})).status_code == 404
    assert (await db.rooms.find_one({"id": "foreign"}))["dnd"] is False


@pytest.mark.asyncio
async def test_room_legacy_id_and_absent_dnd_work_without_touching_other_sources(db, api):
    client, _ = api
    await db.rooms.insert_one({"_id": "legacy", "tenant_id": "t", "status": "available"})
    assert (await client.patch("/api/pms/rooms/legacy/features", json={"dnd": True})).status_code == 200
    await db.rooms.insert_one({"_id": "new-storage", "id": "new-public", "tenant_id": "t"})
    assert (await client.patch("/api/pms/rooms/new-public/features", json={"dnd": True})).status_code == 200
    for collection in ("bookings", "payments", "folio_charges", "stock_movements", "outbox_events"):
        assert await db[collection].count_documents({}) == 0


async def seed_guest(db):
    await db.guests.insert_one({"_id": "stored-guest", "id": "guest", "tenant_id": "t", "name": "Synthetic QA", "custom_fields": {"score": 0, "keep": "old source"}})
    await db.profile_udf_defs.insert_one({"id": "score-def", "tenant_id": "t", "key": "score", "type": "number", "label": "QA score", "required": True, "active": True})


@pytest.mark.asyncio
async def test_udf_roundtrip_zero_required_partial_merge_and_stale_browser_revision(db, api):
    client, user = api
    await seed_guest(db)
    before = (await client.get("/api/profile-udf/guests/guest")).json()
    result = await client.put("/api/profile-udf/guests/guest", json={"values": {"score": "12.5"}, "expected_revision": before["revision"]})
    assert result.status_code == 200, result.text
    assert result.json()["values"] == {"score": 12.5, "keep": "old source"}
    reloaded = (await client.get("/api/profile-udf/guests/guest")).json()
    assert reloaded["revision"] == result.json()["revision"] != before["revision"]
    stale = await client.put("/api/profile-udf/guests/guest", json={"values": {"score": 0}, "expected_revision": before["revision"]})
    assert stale.status_code == 409
    row = await db.guests.find_one({"id": "guest"})
    assert row["custom_fields"] == reloaded["values"] and row["custom_fields_updated_by_id"] == user.id
    zero = await client.put("/api/profile-udf/guests/guest", json={"values": {"score": 0}, "expected_revision": reloaded["revision"]})
    assert zero.status_code == 200 and zero.json()["values"]["score"] == 0


@pytest.mark.asyncio
async def test_udf_concurrent_same_revision_allows_one_writer(db, api):
    client, _ = api
    await seed_guest(db)
    revision = (await client.get("/api/profile-udf/guests/guest")).json()["revision"]
    results = await asyncio.gather(*(client.put("/api/profile-udf/guests/guest", json={"values": {"score": score}, "expected_revision": revision}) for score in (8, 9)))
    assert sorted(response.status_code for response in results) == [200, 409]
    assert (await db.guests.find_one({"id": "guest"}))["custom_fields"]["keep"] == "old source"


@pytest.mark.asyncio
async def test_udf_invalid_unknown_required_and_tenant_checks_leave_source_intact(db, api):
    client, user = api
    await seed_guest(db)
    before = await db.guests.find_one({"id": "guest"})
    for values in ({"score": "NaN"}, {"score": "Infinity"}, {"score": True}, {"score": None}, {"scroe": 1}):
        response = await client.put("/api/profile-udf/guests/guest", json={"values": values})
        assert response.status_code == 400, response.text
    assert await db.guests.find_one({"id": "guest"}) == before
    user.tenant_id = "other"
    assert (await client.get("/api/profile-udf/guests/guest")).status_code == 404
    assert (await client.put("/api/profile-udf/guests/guest", json={"values": {"score": 1}})).status_code == 404
    assert await db.guests.find_one({"id": "guest"}) == before


@pytest.mark.asyncio
async def test_write_permissions_still_deny_housekeeping_profile_and_sales_changes(db, api):
    client, user = api
    user.role = "housekeeping"
    assert (await client.put("/api/profile-udf/guests/guest", json={"values": {}})).status_code == 403
    assert (await client.patch("/api/pms/rooms/public/features", json={"dnd": True})).status_code == 403
