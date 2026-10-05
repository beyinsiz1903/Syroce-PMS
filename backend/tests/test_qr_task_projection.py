from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.guest import qr_task_projection as projection


def _request(**overrides):
    doc = {
        "_id": "request-1",
        "tenant_id": "tenant-1",
        "property_id": "property-1",
        "room_id": "room-208",
        "room_number": "208",
        "department": "rooms",
        "title": "Ek havlu — Oda 208",
        "description": "2 adet",
        "priority": "high",
        "status": "new",
        "status_history": [],
    }
    doc.update(overrides)
    return doc


def test_task_document_is_deterministic_and_routes_department():
    task = projection.task_document(_request(), "qr_requests")

    assert task["id"] == "guest-qr:request-1"
    assert task["source"] == "guest_qr"
    assert task["source_collection"] == "qr_requests"
    assert task["department"] == "housekeeping"
    assert task["status"] == "pending"
    assert task["room_number"] == "208"


@pytest.mark.asyncio
async def test_project_request_upserts_one_shared_task(monkeypatch):
    staff_tasks = SimpleNamespace(update_one=AsyncMock())
    monkeypatch.setattr(
        projection,
        "get_db_for_tenant",
        lambda tenant_id: {"staff_tasks": staff_tasks},
    )

    task = await projection.project_request(_request(), "qr_requests")

    assert task["id"] == "guest-qr:request-1"
    staff_tasks.update_one.assert_awaited_once()
    query, update = staff_tasks.update_one.await_args.args
    assert query == {"tenant_id": "tenant-1", "id": "guest-qr:request-1"}
    assert update["$set"]["source_request_id"] == "request-1"
    assert staff_tasks.update_one.await_args.kwargs == {"upsert": True}


@pytest.mark.asyncio
async def test_complete_task_updates_source_and_returns_projected_task(monkeypatch):
    source = _request(status="in_progress", assigned_to="Resepsiyon")
    source_collection = SimpleNamespace(
        find_one=AsyncMock(return_value=source),
        update_one=AsyncMock(),
    )
    staff_tasks = SimpleNamespace(update_one=AsyncMock())
    tenant_db = {
        "qr_requests": source_collection,
        "staff_tasks": staff_tasks,
    }
    monkeypatch.setattr(projection, "get_db_for_tenant", lambda tenant_id: tenant_db)

    from domains.guest.messaging import guest_requests as guest_messages

    add_message = AsyncMock()
    emit_ping = AsyncMock()
    monkeypatch.setattr(guest_messages, "add_guest_message", add_message)
    monkeypatch.setattr(guest_messages, "emit_guest_requests_ping", emit_ping)
    from modules.event_system import event_bus

    monkeypatch.setattr(event_bus.EventBus, "publish", AsyncMock())

    task = projection.task_document(source, "qr_requests")
    projected = await projection.update_qr_task(
        task,
        {"status": "completed", "resolution_note": "Havlular teslim edildi."},
        actor_id="user-1",
        actor_name="Ayşe",
    )

    source_collection.update_one.assert_awaited_once()
    update = source_collection.update_one.await_args.args[1]
    assert update["$set"]["status"] == "completed"
    assert update["$set"]["resolution_note"] == "Havlular teslim edildi."
    assert update["$push"]["status_history"]["by"] == "Ayşe"
    add_message.assert_awaited_once()
    assert add_message.await_args.kwargs["property_id"] == "property-1"
    assert add_message.await_args.kwargs["body"] == "Havlular teslim edildi."
    emit_ping.assert_awaited_once_with("tenant-1", "room-208")
    assert projected["status"] == "completed"


@pytest.mark.asyncio
async def test_find_source_request_checks_legacy_and_structured(monkeypatch):
    legacy = SimpleNamespace(find_one=AsyncMock(return_value=None))
    structured_doc = _request()
    structured = SimpleNamespace(find_one=AsyncMock(return_value=structured_doc))
    monkeypatch.setattr(
        projection,
        "get_db_for_tenant",
        lambda tenant_id: {
            "room_qr_requests": legacy,
            "qr_requests": structured,
        },
    )

    found = await projection.find_source_request("tenant-1", "request-1")

    assert found == ("qr_requests", structured_doc)
    legacy.find_one.assert_awaited_once()
    structured.find_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_reconcile_only_projects_missing_requests(monkeypatch):
    class Cursor:
        def __init__(self, rows):
            self.rows = rows

        def sort(self, *_args):
            return self

        def limit(self, *_args):
            return self

        def __aiter__(self):
            self._iter = iter(self.rows)
            return self

        async def __anext__(self):
            try:
                return next(self._iter)
            except StopIteration as exc:
                raise StopAsyncIteration from exc

    staff_tasks = SimpleNamespace(
        find=lambda *_args: Cursor([{"id": "guest-qr:request-1"}]),
        update_one=AsyncMock(),
    )
    legacy = SimpleNamespace(find=lambda *_args: Cursor([_request()]))
    structured = SimpleNamespace(find=lambda *_args: Cursor([_request(_id="request-2")]))
    monkeypatch.setattr(
        projection,
        "get_db_for_tenant",
        lambda tenant_id: {
            "staff_tasks": staff_tasks,
            "room_qr_requests": legacy,
            "qr_requests": structured,
        },
    )

    count = await projection.reconcile_tenant_requests("tenant-1")

    assert count == 1
    staff_tasks.update_one.assert_awaited_once()
    assert staff_tasks.update_one.await_args.args[0]["id"] == "guest-qr:request-2"
