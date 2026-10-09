from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from routers import shift_handover as module


@pytest.fixture
def user():
    return SimpleNamespace(id="operator-1", tenant_id="hotel-1", name="Operator", email="operator@example.test", role="front_desk")


@pytest.fixture
def collection(monkeypatch):
    result = SimpleNamespace(insert_one=AsyncMock(), find_one=AsyncMock(), find_one_and_update=AsyncMock(), count_documents=AsyncMock())
    monkeypatch.setattr(module, "db", {"shift_handovers": result})
    return result


@pytest.mark.parametrize("doc,expected", [
    ({"acknowledged": False}, "open"), ({"acknowledged": True}, "acknowledged"),
    ({"acknowledged": True, "status": "in_progress"}, "in_progress"),
    ({"status": "resolved"}, "resolved"),
])
def test_legacy_status_is_explicit(doc, expected):
    assert module._serialize(doc)["status"] == expected


@pytest.mark.asyncio
async def test_create_validates_and_scopes_record(collection, user):
    result = await module.create_handover(module.HandoverCreate(business_date="2026-10-09", shift="morning", to_shift="night", note="  Klima kontrolü  "), user)
    assert result["status"] == "open"
    assert result["note"] == "Klima kontrolü"
    assert result["tenant_id"] == user.tenant_id
    collection.insert_one.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize("override", [{"note": "   "}, {"business_date": "2026-99-99"}, {"to_shift": "morning"}, {"to_shift": "invalid"}])
async def test_invalid_handover_never_writes(collection, user, override):
    payload = {"business_date": "2026-10-09", "shift": "morning", "note": "Kontrol", **override}
    with pytest.raises(HTTPException) as error:
        await module.create_handover(module.HandoverCreate(**payload), user)
    assert error.value.status_code == 400
    collection.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_acknowledgement_retry_preserves_original_operator(collection, user):
    collection.find_one_and_update.return_value = None
    collection.find_one.return_value = {"id": "note-1", "acknowledged": True, "acknowledged_by_id": "first-operator"}
    result = await module.acknowledge("note-1", module.HandoverAck(), user)
    assert result["acknowledged_by_id"] == "first-operator"
    assert collection.find_one_and_update.call_args.args[0] == {"id": "note-1", "tenant_id": "hotel-1", "acknowledged": False}


@pytest.mark.asyncio
async def test_resolution_is_not_acknowledgement_and_records_actor(collection, user):
    collection.find_one.return_value = {"id": "note-1", "acknowledged": True}  # legacy record
    collection.find_one_and_update.return_value = {"id": "note-1", "status": "resolved"}
    await module.progress("note-1", module.HandoverProgress(status="resolved", resolution_note="  Bakım tamamlandı  "), user)
    scope, update = collection.find_one_and_update.call_args.args
    assert scope == {"id": "note-1", "tenant_id": "hotel-1", "status": None, "acknowledged": True}
    assert update["$set"]["resolution_note"] == "Bakım tamamlandı"
    assert update["$set"]["resolved_by_id"] == user.id
    assert update["$set"]["resolved_at"]


@pytest.mark.asyncio
@pytest.mark.parametrize("previous,target", [("open", "resolved"), ("resolved", "in_progress"), ("open", "in_progress")])
async def test_invalid_transition_is_rejected(collection, user, previous, target):
    collection.find_one.return_value = {"id": "note-1", "status": previous}
    with pytest.raises(HTTPException) as error:
        await module.progress("note-1", module.HandoverProgress(status=target, resolution_note="Sonuç"), user)
    assert error.value.status_code == 409
    collection.find_one_and_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_concurrent_update_cannot_overwrite_resolution(collection, user):
    collection.find_one.return_value = {"status": "acknowledged", "acknowledged": True}
    collection.find_one_and_update.return_value = None
    with pytest.raises(HTTPException) as error:
        await module.progress("note-1", module.HandoverProgress(status="in_progress"), user)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_foreign_tenant_note_is_not_visible(collection, user):
    collection.find_one.return_value = None
    with pytest.raises(HTTPException) as error:
        await module.progress("foreign-note", module.HandoverProgress(status="in_progress"), user)
    assert error.value.status_code == 404
    collection.find_one.assert_awaited_once_with({"id": "foreign-note", "tenant_id": "hotel-1"})
    collection.find_one_and_update.assert_not_awaited()


@pytest.mark.asyncio
async def test_scope_is_enforced_before_router_reads(collection, user):
    user.module_scopes = []
    app = FastAPI()
    app.include_router(module.router)
    app.dependency_overrides[module.get_current_user] = lambda: user
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/api/pms/shift-handover")
    assert response.status_code == 403
    collection.count_documents.assert_not_awaited()
