import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from core.mice_integrity import space_leaves
from domains.notifications_router import _visibility_filter
from domains.pms.notification_router import _notification_scope
from routers import mice, mice_documents, mice_seating
from tests.test_mice_commercial_workflows import event
from tests.test_mice_mongo_acceptance import USER, booking, wired  # noqa: F401
from tests.test_report_ledger_mongo_acceptance import ledger_db  # noqa: F401


def test_combined_spaces_are_leaf_sets_and_reject_cycles_or_duplicate_area():
    spaces = {"A": {}, "B": {}, "AB": {"component_space_ids": ["A", "B"]}}
    spaces = {k: {"id": k, **v} for k, v in spaces.items()}
    assert space_leaves("AB", spaces) == {"A", "B"}
    with pytest.raises(ValueError): space_leaves("AB", {**spaces, "B": {"component_space_ids": ["AB"]}})
    with pytest.raises(ValueError): space_leaves("AB", {**spaces, "AB": {"component_space_ids": ["A", "A"]}})


@pytest.mark.asyncio
async def test_inactive_combined_hall_is_valid_but_cannot_hide_a_cycle(wired, monkeypatch):  # noqa: F811
    monkeypatch.setattr(mice, "get_tenant_limit", AsyncMock(return_value=None))
    await wired.mice_spaces.insert_one({"tenant_id": "A", "id": "A", "name": "Part A", "active": True})
    created = await mice.create_space(mice.FunctionSpaceIn(name="Closed combined hall", active=False, component_space_ids=["A"]), USER)
    assert created["active"] is False
    with pytest.raises(HTTPException) as error:
        await mice.update_space(created["id"], mice.FunctionSpaceIn(name="Invalid cycle", active=False, component_space_ids=[created["id"]]), USER)
    assert error.value.status_code == 422


@pytest.mark.asyncio
async def test_combined_venue_race_has_only_one_winner(wired, monkeypatch):  # noqa: F811
    monkeypatch.setattr(mice, "get_tenant_limit", AsyncMock(return_value=None))
    await wired.mice_locks.create_index([("tenant_id", 1), ("kind", 1), ("resource_id", 1)], unique=True)
    await wired.mice_spaces.insert_many([{"id": sid, "tenant_id": "A", "name": sid, "currency": "TRY", "capacity_theatre": 20, **extra} for sid, extra in [("A", {}), ("B", {}), ("AB", {"component_space_ids": ["A", "B"]})]])
    def payload(sid):
        return mice.EventIn(name=sid, client_name="Synthetic client", status="confirmed", expected_pax=10, start_date="2026-10-21", end_date="2026-10-21", space_bookings=[{**booking(), "space_id": sid}])
    results = await asyncio.gather(mice.create_event(payload("A"), USER), mice.create_event(payload("AB"), USER), return_exceptions=True)
    assert sum(isinstance(r, dict) for r in results) == 1
    assert sum(isinstance(r, HTTPException) and r.status_code == 409 for r in results) == 1, repr(results)
    assert await wired.mice_events.count_documents({}) == 1


@pytest.mark.asyncio
async def test_same_event_cannot_use_combined_and_child_simultaneously(wired):  # noqa: F811
    await wired.mice_spaces.insert_many([{"id": "A", "tenant_id": "A"}, {"id": "AB", "tenant_id": "A", "component_space_ids": ["A"]}])
    with pytest.raises(HTTPException) as error:
        await mice._validate_setup_capacity("A", [{**booking(), "space_id": sid} for sid in ["A", "AB"]])
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_partial_delivery_return_scope_and_duplicate_request(wired):  # noqa: F811
    staff = SimpleNamespace(tenant_id="A", username="assigned", id="operator", role="staff", granted_permissions=[])
    outsider = SimpleNamespace(tenant_id="A", username="other", id="other", role="staff", granted_permissions=[])
    await wired.users.insert_one({"tenant_id": "A", "id": "operator", "name": "Synthetic staff", "role": "staff"})
    await event(wired, resources=[{"inventory_id": "chair", "name": "Chair", "quantity": 10}])
    task = await mice.create_operation_task("event", mice.OperationTaskIn(title="Chair dispatch", department="banquet", owner_name="Synthetic staff", owner_user_id="operator", kind="equipment", inventory_id="chair", quantity=10, client_request_id="task-request-123"), USER)
    assert not (await mice.list_operation_tasks("event", outsider))["tasks"]
    assert (await mice.list_operation_tasks("event", staff))["tasks"][0]["can_transition"]
    request = mice.EquipmentHandoverIn(action="deliver", quantity=4, request_id="deliver-request-123")
    await mice.record_equipment_handover("event", task["id"], request, staff)
    assert (await mice.record_equipment_handover("event", task["id"], request, staff))["replayed"]
    await mice.record_equipment_handover("event", task["id"], mice.EquipmentHandoverIn(action="return", quantity=2, request_id="return-request-123"), staff)
    result = (await mice.list_operation_tasks("event", staff))["tasks"][0]
    assert (result["delivered_quantity"], result["returned_quantity"]) == (4, 2)
    with pytest.raises(HTTPException) as over:
        await mice.record_equipment_handover("event", task["id"], mice.EquipmentHandoverIn(action="return", quantity=3, request_id="excess-request-123"), staff)
    assert over.value.status_code == 409
    with pytest.raises(HTTPException) as forbidden:
        await mice.record_equipment_handover("event", task["id"], request, outsider)
    assert forbidden.value.status_code == 403
    assert await wired.notifications.count_documents({"tenant_id": "A", **_visibility_filter(staff)}) == 3
    assert await wired.notifications.count_documents({"tenant_id": "A", **_visibility_filter(outsider)}) == 0
    assert await wired.notifications.count_documents(_notification_scope(staff)) == 3
    assert await wired.notifications.count_documents(_notification_scope(outsider)) == 0


def test_document_diff_uses_saved_contents_not_issue_timestamps():
    before = {"event": {"expected_pax": 10, "updated_at": "old"}, "resources": [{"quantity": 10}], "document": {"id": "old"}}
    after = {"event": {"expected_pax": 12, "updated_at": "new"}, "resources": [{"quantity": 12}], "document": {"id": "new"}}
    assert [c["field"] for c in mice_documents.snapshot_changes(before, after)] == ["event.expected_pax", "resources[1].quantity"]


@pytest.mark.asyncio
async def test_document_distribution_is_idempotent_and_only_recipient_can_acknowledge(wired, monkeypatch):  # noqa: F811
    monkeypatch.setattr(mice_documents, "get_system_db", lambda: wired)
    recipient = SimpleNamespace(tenant_id="A", id="recipient", username="recipient")
    outsider = SimpleNamespace(tenant_id="A", id="other", username="other")
    await event(wired, active_document_id="doc", document_history=[{"id": "doc", "number": 1, "snapshot": {"event": {"name": "Synthetic"}}}], operations_tasks=[{"department": "av", "owner_user_id": "recipient", "status": "pending"}])
    await mice_documents.distribute_document("event", "doc", USER)
    await mice_documents.distribute_document("event", "doc", USER)
    assert await wired.notifications.count_documents({}) == 1
    with pytest.raises(HTTPException): await mice_documents.acknowledge_document("event", "doc", outsider)
    await mice_documents.acknowledge_document("event", "doc", recipient)
    result = await mice_documents.document_changes("event", "doc", None, recipient)
    assert result["deliveries"][0]["acknowledged_at"]
    assert not result["can_acknowledge"]


@pytest.mark.parametrize("tables,capacity,pax,status", [
    ([{"label": "T", "seats": 8, "x": 9, "y": 0, "width": 2, "height": 2}], 20, 8, 422),
    ([{"label": "T", "seats": 8, "x": 0, "y": 0, "width": 2, "height": 2}], 6, 8, 409),
    ([{"label": "T", "seats": 8, "x": 0, "y": 0, "width": 2, "height": 2}], 20, 10, 409),
    ([{"label": label, "seats": 8, "x": 0, "y": 0, "width": 2, "height": 2} for label in ["T", "t"]], 20, 8, 422),
    ([{"label": label, "seats": 8, "x": 0, "y": 0, "width": 2, "height": 2} for label in ["A", "B"]], 20, 8, 409),
])
def test_layout_rejects_overlap_bounds_duplicate_labels_and_capacity(tables, capacity, pax, status):
    body = mice_seating.SeatingIn(booking_index=0, width=10, height=10, tables=tables, expected_revision="revision")
    with pytest.raises(HTTPException) as error:
        mice_seating.validate_layout(body, pax, capacity)
    assert error.value.status_code == status


@pytest.mark.asyncio
async def test_cashier_cannot_close_or_handover_a_pending_mice_settlement(wired, monkeypatch):  # noqa: F811
    from domains.pms import cashier_router, cashier_service
    monkeypatch.setattr(cashier_router, "db", wired)
    monkeypatch.setattr(cashier_service, "reconcile_open_shift_payments", AsyncMock())
    monkeypatch.setattr(cashier_router, "ensure_business_date_initialized", AsyncMock(return_value={"business_date": "2026-10-21"}))
    await wired.cashier_shifts.insert_one({"_id": "shift", "tenant_id": "A", "status": "open", "cash_in": 0, "cash_out": 0, "mice_pending_ids": ["payment"]})
    user = SimpleNamespace(tenant_id="A", email="synthetic@example.invalid", name="Synthetic")
    with pytest.raises(HTTPException) as error:
        await cashier_router.close_shift({"counted_amount": 0}, user)
    assert error.value.status_code == 409
    assert (await wired.cashier_shifts.find_one({"_id": "shift"}))["status"] == "open"
