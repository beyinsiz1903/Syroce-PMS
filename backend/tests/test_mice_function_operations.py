"""Setup/teardown, departmental handover and immutable kitchen revisions."""
import asyncio

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from core.mice_integrity import overlaps, peak_usage
from routers import mice
from tests.test_mice_commercial_workflows import event
from tests.test_mice_mongo_acceptance import USER, booking, wired  # noqa: F401
from tests.test_report_ledger_mongo_acceptance import ledger_db  # noqa: F401


def request():
    return Request({"type": "http", "headers": [], "method": "POST", "path": "/local-only"})


def test_buffers_block_availability_but_do_not_increase_rent():
    occupied = {**booking(), "teardown_minutes": 60}
    desired = booking("12:30", "13:30")
    assert overlaps(occupied, desired)
    assert not overlaps(occupied, booking("13:00", "14:00"))
    assert peak_usage([desired], [([occupied], 2)]) == 2
    assert mice._compute_totals({"space_bookings": [occupied]}, {"hall": {"hourly_rate": 100, "daily_rate": 500}})["space_total"] == 200


@pytest.mark.asyncio
async def test_real_venue_conflict_accounts_for_setup_on_adjacent_day(wired):  # noqa: F811
    await event(wired, start_date="2026-10-21", end_date="2026-10-21", space_bookings=[{**booking("00:15", "01:00"), "setup_minutes": 60}])
    assert await mice._check_space_conflict("A", [{"space_id": "hall", "starts_at": "2026-10-20T23:30", "ends_at": "2026-10-21T00:00"}])
    rows = await mice.ops_sheet("2026-10-20", USER)
    assert rows["count"] == 1
    assert rows["rows"][0]["setup_minutes"] == 60


def task(**extras):
    return mice.OperationTaskIn(title="AV setup", department="av", owner_name="Synthetic technician", client_request_id="request-task-1", **extras)


@pytest.mark.asyncio
async def test_task_steps_replay_and_cross_tenant_guard(wired):  # noqa: F811
    await event(wired)
    created = await mice.create_operation_task("event", task(), USER)
    replay = await mice.create_operation_task("event", task(), USER)
    assert replay["id"] == created["id"]
    with pytest.raises(HTTPException) as skipped:
        await mice.transition_operation_task("event", created["id"], mice.OperationTaskTransitionIn(status="completed"), USER)
    assert skipped.value.status_code == 409
    await mice.transition_operation_task("event", created["id"], mice.OperationTaskTransitionIn(status="acknowledged"), USER)
    first = (await mice.list_operation_tasks("event", USER))["tasks"][0]
    retry = await mice.transition_operation_task("event", created["id"], mice.OperationTaskTransitionIn(status="acknowledged"), USER)
    assert retry["unchanged"]
    assert (await mice.list_operation_tasks("event", USER))["tasks"][0]["acknowledged_at"] == first["acknowledged_at"]
    await wired.mice_events.insert_one({"id": "secret", "tenant_id": "B", "status": "confirmed"})
    with pytest.raises(HTTPException) as other: await mice.list_operation_tasks("secret", USER)
    assert other.value.status_code == 404


@pytest.mark.asyncio
async def test_equipment_delivery_respects_reserved_quantity_and_requires_return(wired):  # noqa: F811
    await event(wired, resources=[{"inventory_id": "projector", "name": "Projector", "quantity": 2}])
    body = task(kind="equipment", inventory_id="projector", quantity=2)
    created = await mice.create_operation_task("event", body, USER)
    with pytest.raises(HTTPException) as excess:
        await mice.create_operation_task("event", body.model_copy(update={"client_request_id": "second-task"}), USER)
    assert excess.value.status_code == 409
    await mice.transition_operation_task("event", created["id"], mice.OperationTaskTransitionIn(status="acknowledged"), USER)
    with pytest.raises(HTTPException) as cancel:
        await mice.transition_operation_task("event", created["id"], mice.OperationTaskTransitionIn(status="cancelled", reason="Equipment is out at event"), USER)
    assert cancel.value.status_code == 409
    await wired.mice_events.update_one({"id": "event", "tenant_id": "A"}, {"$set": {"status": "cancelled"}})
    await mice.transition_operation_task("event", created["id"], mice.OperationTaskTransitionIn(status="completed"), USER)
    assert (await mice.list_operation_tasks("event", USER))["tasks"][0]["status"] == "completed"


@pytest.mark.asyncio
async def test_kitchen_cancel_acknowledgement_and_changed_event_revision(wired):  # noqa: F811
    await event(wired, resources=[{"name": "Synthetic menu", "type": "fb", "quantity": 20, "unit_price": 10, "menu_snapshot": {"allergens": ["milk"]}}])
    sent = await mice.send_fnb_order("event", mice.FnbOrderSendRequest(), request(), USER)
    assert sent["lines"][0]["menu_snapshot"]["allergens"] == ["milk"]
    replay = await mice.send_fnb_order("event", mice.FnbOrderSendRequest(), request(), USER)
    assert replay["id"] == sent["id"]
    assert await wired.mice_fnb_orders.count_documents({"tenant_id": "A"}) == 1
    with pytest.raises(HTTPException) as history_guard: await mice.delete_event("event", USER)
    assert history_guard.value.status_code == 409
    await wired.mice_events.update_one({"id": "event", "tenant_id": "A"}, {"$set": {"resources.0.quantity": 30}})
    orders = await mice.list_open_fnb_orders(USER)
    assert orders["orders"][0]["needs_review"]
    with pytest.raises(HTTPException): await mice.transition_fnb_order("event", sent["id"], mice.FnbOrderTransitionRequest(status="acknowledged"), USER)
    with pytest.raises(HTTPException): await mice.send_fnb_order("event", mice.FnbOrderSendRequest(), request(), USER)
    await mice.request_fnb_cancellation("event", sent["id"], mice.FnbCancelIn(reason="Guest count changed substantially"), USER)
    waiting = await mice.list_open_fnb_orders(USER)
    assert waiting["orders"][0]["status"] == "cancel_requested"
    await mice.transition_fnb_order("event", sent["id"], mice.FnbOrderTransitionRequest(status="cancelled"), USER)
    revised = await mice.send_fnb_order("event", mice.FnbOrderSendRequest(), request(), USER)
    assert revised["id"] != sent["id"] and revised["lines"][0]["quantity"] == 30
    assert await wired.mice_fnb_orders.count_documents({"tenant_id": "A"}) == 2


@pytest.mark.asyncio
async def test_parallel_kitchen_dispatch_does_not_duplicate_the_production_order(wired):  # noqa: F811
    await event(wired, resources=[{"name": "Synthetic menu", "type": "fb", "quantity": 20, "unit_price": 10}])
    await wired.mice_locks.create_index([("tenant_id", 1), ("kind", 1), ("resource_id", 1)], unique=True)
    await wired.mice_locks.insert_one({"tenant_id": "A", "kind": "dispatch", "resource_id": "event"})
    outcomes = await asyncio.gather(*[mice.send_fnb_order("event", mice.FnbOrderSendRequest(), request(), USER) for _ in range(2)], return_exceptions=True)
    assert all(isinstance(o, dict) for o in outcomes), outcomes
    assert outcomes[0]["id"] == outcomes[1]["id"]
    assert await wired.mice_fnb_orders.count_documents({"tenant_id": "A"}) == 1


@pytest.mark.asyncio
async def test_same_menu_can_be_reissued_only_with_explicit_cancelled_predecessor(wired):  # noqa: F811
    await event(wired, resources=[{"name": "Synthetic menu", "type": "fb", "quantity": 20, "unit_price": 10}])
    original = await mice.send_fnb_order("event", mice.FnbOrderSendRequest(), request(), USER)
    await mice.request_fnb_cancellation("event", original["id"], mice.FnbCancelIn(reason="Service moved and then reinstated"), USER)
    with pytest.raises(HTTPException):
        await mice.send_fnb_order("event", mice.FnbOrderSendRequest(replaces_order_id=original["id"]), request(), USER)
    await mice.transition_fnb_order("event", original["id"], mice.FnbOrderTransitionRequest(status="cancelled"), USER)
    with pytest.raises(HTTPException): await mice.send_fnb_order("event", mice.FnbOrderSendRequest(), request(), USER)
    replacement = await mice.send_fnb_order("event", mice.FnbOrderSendRequest(replaces_order_id=original["id"]), request(), USER)
    assert replacement["id"] != original["id"]
    assert replacement["replaces_order_id"] == original["id"]


@pytest.mark.asyncio
async def test_partial_costs_do_not_present_a_positive_contribution(wired):  # noqa: F811
    original = await event(wired)
    await mice.save_event_actuals("event", mice.EventActualsIn(actual_pax=20, expected_revision=original["created_at"]), USER)
    result = await mice.get_event_actuals("event", USER)
    assert result["report"]["quote_based_contribution"] is None


@pytest.mark.asyncio
async def test_zero_quantity_flat_menu_remains_zero(wired):  # noqa: F811
    await wired.mice_menus.insert_one({"id": "menu", "tenant_id": "A", "name": "Flat menu", "flat_price": 100, "currency": "TRY"})
    lines = await mice._expand_resource_prices("A", [{"menu_id": "menu", "quantity": 0}], 20, "TRY", "TRY")
    assert lines[0]["quantity"] == 0
    assert mice._compute_totals({"resources": lines}, {})["grand_total"] == 0


@pytest.mark.asyncio
async def test_fractional_inventory_is_not_rejected_by_binary_float_error(wired):  # noqa: F811
    await wired.mice_resources.insert_one({"tenant_id": "A", "id": "fraction", "name": "Fractional stock", "total_stock": 0.3})
    lines = [{"inventory_id": "fraction", "quantity": 0.1}, {"inventory_id": "fraction", "quantity": 0.2}]
    assert await mice._check_resource_inventory_conflict("A", lines, [booking()]) is None


@pytest.mark.asyncio
async def test_one_explicit_meal_does_not_become_full_event_pax(wired):  # noqa: F811
    await wired.mice_menus.insert_one({"id": "menu", "tenant_id": "A", "name": "Single meal", "price_per_person": 100, "currency": "TRY"})
    lines = await mice._expand_resource_prices("A", [{"menu_id": "menu", "quantity": 1, "quantity_mode": "explicit"}], 200, "TRY", "TRY")
    assert lines[0]["quantity"] == 1
    assert mice._compute_totals({"resources": lines}, {})["grand_total"] == 100
