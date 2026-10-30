"""Remaining native guest-service paths; disposable LOCAL replica only."""

import asyncio
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from fastapi import HTTPException

from domains.guest.experience_router import guest_app
from domains.pms import activity_scheduler_router as activity
from domains.pms import function_space_router as space
from tests.test_department_live_folio_acceptance import actor, db, wired  # noqa: F401


@pytest_asyncio.fixture
async def services(wired, monkeypatch):  # noqa: F811
    for name in ("room_service_menu", "room_service_orders", "guest_service_items", "activities", "activity_resources", "activity_bookings", "function_rooms", "function_bookings", "guests"):
        await wired.create_collection(name)
    monkeypatch.setattr(guest_app, "db", wired)
    monkeypatch.setattr(guest_app, "emit_order_event", AsyncMock())
    monkeypatch.setattr(activity, "get_system_db", lambda: wired)
    monkeypatch.setattr(space, "get_system_db", lambda: wired)
    monkeypatch.setattr("core.utils.db", wired)
    await wired.hotel_settings.update_one({"tenant_id": "t"}, {"$set": {"timezone": "Europe/Istanbul", "currency": "TRY"}})
    await wired.bookings.update_one({"id": "b"}, {"$set": {"guest_id": "g", "room_id": "r"}})
    await wired.guests.insert_one({"id": "g", "tenant_id": "t", "name": "QA Synthetic"})
    await wired.room_service_menu.insert_one({"id": "food", "tenant_id": "t", "name": "QA soup", "available": True, "price": 120, "currency": "TRY", "tax_rate": 0.2})
    await wired.activities.insert_one({"id": "a", "tenant_id": "t", "name": "QA Yoga", "type": "yoga", "active": True, "price": 150, "currency": "TRY", "duration_min": 60, "capacity": 1})
    await wired.activity_resources.insert_one({"id": "instructor", "tenant_id": "t", "name": "QA Instructor", "kind": "instructor", "active": True, "capacity": 1, "activity_types": ["yoga"]})
    await wired.function_rooms.insert_one({"id": "hall", "tenant_id": "t", "name": "QA Hall", "active": True, "capacity": 10, "hourly_rate": 200, "daily_rate": 1200, "currency": "TRY"})
    return wired


def order_body(**changes):
    return guest_app._RoomServiceOrderBody.model_validate(
        {"booking_id": "b", "request_id": "qa-order", "confirm_room_charge": True, "items": [{"id": "food", "name": "QA soup", "price": 120, "currency": "TRY", "quantity": 1}], **changes}
    )


async def test_order_does_not_accept_client_price_override(services):
    with pytest.raises(HTTPException):
        await guest_app.create_room_service_order(order_body(items=[{"id": "food", "price": 1, "currency": "TRY", "quantity": 1}]), actor())
    assert not await services.room_service_orders.count_documents({})
    assert not await services.folio_charges.count_documents({})


async def test_order_uses_server_gross_and_declared_vat_without_fixed_18_percent(services):
    await guest_app.create_room_service_order(order_body(), actor())
    charge = await services.folio_charges.find_one({})
    assert charge["total"] == 120 and charge["currency"] == "TRY"
    assert charge["vat_amount"] == 20 and charge["amount"] == 100
    assert charge["business_date"] == "2026-10-26"


async def test_order_duplicate_request_is_one_source_and_receivable(services):
    await asyncio.gather(guest_app.create_room_service_order(order_body(), actor()), guest_app.create_room_service_order(order_body(), actor()))
    assert await services.room_service_orders.count_documents({}) == 1
    assert await services.folio_charges.count_documents({}) == 1


async def test_activity_does_not_overbook_one_resource_concurrently(services, monkeypatch):
    # Deterministically expose the old read-then-insert window. The patched
    # transaction path reads overlaps under a session/resource lock instead.
    collection_type = type(services.activity_bookings)
    original = collection_type.count_documents
    gate = asyncio.Barrier(2)

    async def count(collection, *args, **kwargs):
        value = await original(collection, *args, **kwargs)
        if collection.name == "activity_bookings" and kwargs.get("session") is None:
            await gate.wait()
        return value

    monkeypatch.setattr(collection_type, "count_documents", count)
    body = activity.ActivityBookingCreate(activity_id="a", resource_id="instructor", guest_id="g", starts_at="2026-11-01T10:00:00+03:00")
    results = await asyncio.gather(activity.create_booking(body, actor(), None), activity.create_booking(body, actor(), None), return_exceptions=True)
    assert sum(isinstance(result, HTTPException) and result.status_code == 409 for result in results) == 1
    assert await original(services.activity_bookings, {}) == 1


async def test_function_space_compares_instants_not_timezone_strings(services):
    await services.function_bookings.insert_one(
        {"id": "prior", "tenant_id": "t", "room_id": "hall", "status": "booked", "starts_at": "2026-11-01T10:00:00+00:00", "ends_at": "2026-11-01T11:00:00+00:00"}
    )
    body = space.FunctionBookingCreate(room_id="hall", event_name="QA clash", starts_at="2026-11-01T13:00:00+03:00", ends_at="2026-11-01T14:00:00+03:00")
    with pytest.raises(HTTPException) as error:
        await space.create_booking(body, actor())
    assert error.value.status_code == 409


async def scheduled_record(kind):
    if kind == "activity":
        return await activity.create_booking(
            activity.ActivityBookingCreate(activity_id="a", resource_id="instructor", guest_id="g", starts_at="2026-10-30T15:00:00+03:00", request_id="qa-scheduled"), actor(), None
        )
    return await space.create_booking(
        space.FunctionBookingCreate(room_id="hall", event_name="QA workshop", starts_at="2026-10-30T15:00:00+03:00", ends_at="2026-10-30T16:30:00+03:00", request_id="qa-scheduled"), actor()
    )


async def quote_payload(kind, row):
    from core.scheduled_guest_services import ScheduledFolioInput

    route = activity if kind == "activity" else space
    basis = "per_booking" if kind == "activity" else "hourly"
    quote = await route.folio_quote(row["id"], basis, actor())
    return ScheduledFolioInput(reservation_id="b", folio_id="actual-folio", quote_hash=quote["quote_hash"], billing_basis=basis, reason="QA retained service completion")


@pytest.mark.parametrize("kind,expected", [("activity", 150), ("function_space", 300)])
async def test_native_service_quote_complete_retry_and_report_source(services, kind, expected):
    row = await scheduled_record(kind)
    payload = await quote_payload(kind, row)
    route = activity if kind == "activity" else space
    first, second = await asyncio.gather(route.post_to_folio(row["id"], payload, actor()), route.post_to_folio(row["id"], payload, actor()))
    assert sorted([first["replayed"], second["replayed"]]) == [False, True]
    assert await services.folio_charges.count_documents({}) == 1
    charge = await services.folio_charges.find_one({})
    assert charge["total"] == expected and charge["charge_category"] == kind and charge["currency"] == "TRY"
    assert charge["service_date"] == "2026-10-30" and charge["service_time"] == "15:00" and charge["business_date"] == "2026-10-26"
    assert charge["vat_amount"] is None and charge["source_fingerprint"]
    assert (await services.bookings.find_one({"id": "b"}))["balance"] == expected
    assert await services.audit_logs.count_documents({"action": f"{kind}_charge_posted"}) == 1
    with pytest.raises(HTTPException):
        if kind == "activity":
            await route.cancel_booking(row["id"], actor(), None)
        else:
            await route.cancel_booking(row["id"], actor())


@pytest.mark.parametrize("kind", ["activity", "function_space"])
async def test_changed_tariff_invalidates_quote_without_posting(services, kind):
    row = await scheduled_record(kind)
    payload = await quote_payload(kind, row)
    collection = services.activities if kind == "activity" else services.function_rooms
    await collection.update_one({}, {"$set": {"price" if kind == "activity" else "hourly_rate": 250}})
    with pytest.raises(HTTPException) as error:
        await (activity if kind == "activity" else space).post_to_folio(row["id"], payload, actor())
    assert error.value.status_code == 409
    assert not await services.folio_charges.count_documents({})


@pytest.mark.parametrize("kind", ["activity", "function_space"])
async def test_native_audit_failure_rolls_back_completion_and_financial_projection(services, monkeypatch, kind):
    row = await scheduled_record(kind)
    payload = await quote_payload(kind, row)
    monkeypatch.setattr("core.department_folio.append_audit_log", AsyncMock(side_effect=RuntimeError("audit unavailable")))
    with pytest.raises(RuntimeError):
        await (activity if kind == "activity" else space).post_to_folio(row["id"], payload, actor())
    collection = services.activity_bookings if kind == "activity" else services.function_bookings
    assert (await collection.find_one({"id": row["id"]}))["status"] == "booked"
    assert not await services.folio_charges.count_documents({})


@pytest.mark.parametrize("kind", ["activity", "function_space"])
async def test_native_rejects_foreign_folio_closed_day_and_nonfinance_role(services, kind):
    row = await scheduled_record(kind)
    payload = await quote_payload(kind, row)
    route = activity if kind == "activity" else space
    staff = actor()
    staff.role = "housekeeping"
    with pytest.raises(HTTPException) as error:
        await route.post_to_folio(row["id"], payload, staff)
    assert error.value.status_code == 403
    with pytest.raises(HTTPException):
        await route.post_to_folio(row["id"], payload.model_copy(update={"folio_id": "foreign"}), actor())
    await services.night_audit_runs.insert_one({"tenant_id": "t", "business_date": "2026-10-26", "status": "completed"})
    with pytest.raises(HTTPException):
        await route.post_to_folio(row["id"], payload, actor())
    assert not await services.folio_charges.count_documents({})


async def test_native_activity_requires_same_guest_and_unknown_currency_blocks(services):
    row = await scheduled_record("activity")
    payload = await quote_payload("activity", row)
    await services.bookings.update_one({"id": "b"}, {"$set": {"guest_id": "other"}})
    with pytest.raises(HTTPException):
        await activity.post_to_folio(row["id"], payload, actor())
    await services.activities.update_one({"id": "a"}, {"$unset": {"currency": ""}})
    with pytest.raises(HTTPException):
        await activity.folio_quote(row["id"], "per_booking", actor())


async def test_schedule_midnight_adjacency_capacity_and_safe_create_retry(services):
    row = await scheduled_record("activity")
    again = await scheduled_record("activity")
    assert again["id"] == row["id"] and await services.activity_bookings.count_documents({}) == 1
    await activity.cancel_booking(row["id"], actor(), None)
    overnight = activity.ActivityBookingCreate(activity_id="a", resource_id="instructor", guest_id="g", starts_at="2026-10-29T23:30:00+03:00", duration_min=120)
    await activity.create_booking(overnight, actor(), None)
    day = await activity.list_bookings("2026-10-30", None, actor())
    assert any(record["starts_at"].startswith("2026-10-29T23:30") for record in day)
    next_one = overnight.model_copy(update={"starts_at": "2026-10-30T01:30:00+03:00"})
    await activity.create_booking(next_one, actor(), None)


@pytest.mark.parametrize(
    "change",
    [
        {"confirm_room_charge": False},
        {"items": [{"id": "food", "price": 120, "currency": "TRY", "quantity": -1}]},
        {"items": [{"id": "missing", "price": 120, "currency": "TRY", "quantity": 1}]},
        {"items": [{"id": "food", "price": 120, "currency": "EUR", "quantity": 1}]},
    ],
)
async def test_order_invalid_source_never_creates_partial_order(services, change):
    with pytest.raises(HTTPException):
        await guest_app.create_room_service_order(order_body(**change), actor())
    assert not await services.room_service_orders.count_documents({})
    assert not await services.folio_charges.count_documents({})


async def test_order_second_line_and_audit_failures_roll_back_all_sources(services, monkeypatch):
    await services.room_service_menu.insert_one({"id": "bad", "tenant_id": "t", "available": True, "price": 100, "currency": "EUR"})
    items = [*order_body().items, {"id": "bad", "price": 100, "currency": "EUR", "quantity": 1}]
    with pytest.raises(HTTPException):
        await guest_app.create_room_service_order(order_body(items=items), actor())
    assert not await services.folio_charges.count_documents({})
    monkeypatch.setattr("core.department_folio.append_audit_log", AsyncMock(side_effect=RuntimeError("audit unavailable")))
    with pytest.raises(RuntimeError):
        await guest_app.create_room_service_order(order_body(), actor())
    assert not await services.room_service_orders.count_documents({})
    assert not await services.folio_charges.count_documents({})


async def test_order_qr_menu_is_shared_but_property_and_guest_ownership_remain_enforced(services):
    await services.bookings.update_one({"id": "b"}, {"$set": {"property_id": "p"}})
    await services.guest_service_items.insert_one(
        {
            "tenant_id": "t",
            "property_id": "p",
            "service_code": "fnb.qa",
            "department_code": "fnb",
            "labels": {"tr": "QA sandwich"},
            "unit_price_minor": 22000,
            "currency": "TRY",
            "tax_rate": 0.1,
            "enabled": True,
            "room_charge_enabled": True,
        }
    )
    menu = await guest_app.get_room_service_menu(actor(), "b")
    assert any(item["id"] == "qr:p:fnb.qa" for group in menu["categories"] for item in group["items"])
    body = order_body(items=[{"id": "qr:p:fnb.qa", "price": 220, "currency": "TRY", "quantity": 1}])
    await guest_app.create_room_service_order(body, actor())
    assert (await services.folio_charges.find_one({}))["vat_amount"] == 20
    await services.bookings.update_one({"id": "b"}, {"$set": {"property_id": "foreign"}})
    with pytest.raises(HTTPException):
        await guest_app.create_room_service_order(body.model_copy(update={"request_id": "different-attempt"}), actor())
    for role in ("guest", "guest_app", "agency_agent", "housekeeping"):
        user = actor()
        user.role = role
        with pytest.raises(HTTPException):
            await guest_app.create_room_service_order(body, user)


async def test_order_unknown_vat_and_same_key_changed_payload_not_reposted(services):
    await services.room_service_menu.update_one({"id": "food"}, {"$unset": {"tax_rate": ""}})
    await guest_app.create_room_service_order(order_body(), actor())
    assert (await services.folio_charges.find_one({}))["vat_amount"] is None
    with pytest.raises(HTTPException):
        await guest_app.create_room_service_order(order_body(special_instructions="changed"), actor())
    assert await services.folio_charges.count_documents({}) == 1


async def test_order_service_time_uses_hotel_day_not_utc_and_delivery_is_separate(services):
    from core.room_service_order import change_order_status

    result = await guest_app.create_room_service_order(order_body(service_at="2026-10-29T22:30:00+00:00"), actor())
    charge = await services.folio_charges.find_one({})
    assert charge["service_date"] == "2026-10-30" and charge["service_time"] == "01:30"
    assert charge["business_date"] == "2026-10-26"
    order = await services.room_service_orders.find_one({})
    assert not order.get("delivered_at")
    first, replay = await change_order_status(services, "t", order["id"], "delivered", "operator"), await change_order_status(services, "t", order["id"], "delivered", "operator")
    assert first[0]["delivered_at"] == replay[0]["delivered_at"] and replay[1]
    assert await services.audit_logs.count_documents({"action": "room_service_order_status_changed"}) == 1
    assert result["currency"] == "TRY"
    for status in ("preparing", "cancelled"):
        with pytest.raises(HTTPException):
            await change_order_status(services, "t", order["id"], status, "operator")
    assert await services.folio_charges.count_documents({}) == 1


async def test_order_status_audit_failure_rolls_back_and_cancel_does_not_hide_debt(services, monkeypatch):
    from core.room_service_order import change_order_status

    await guest_app.create_room_service_order(order_body(), actor())
    order = await services.room_service_orders.find_one({})
    with pytest.raises(HTTPException):
        await change_order_status(services, "t", order["id"], "cancelled", "operator")
    monkeypatch.setattr("core.audit_chain.append_audit_log", AsyncMock(side_effect=RuntimeError("audit unavailable")))
    with pytest.raises(RuntimeError):
        await change_order_status(services, "t", order["id"], "delivered", "operator")
    persisted = await services.room_service_orders.find_one({})
    assert persisted["status"] == "pending" and not persisted.get("delivered_at")
    assert (await services.folios.find_one({"id": "actual-folio"}))["balance"] == 120
    assert await services.folio_charges.count_documents({"voided": {"$ne": True}}) == 1


async def test_pos_history_and_summary_select_the_same_authoritative_business_day(services, monkeypatch):
    from domains.pms.pos_fnb_router import pos_mobile
    from domains.revenue.analytics_router import pos_inventory

    for module in (pos_mobile, pos_inventory):
        monkeypatch.setattr(module, "db", services)
        monkeypatch.setattr(module, "get_current_user", AsyncMock(return_value=actor()))
        monkeypatch.setattr(module, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    await services.pos_orders.insert_many([
        {"id": "wanted", "tenant_id": "t", "business_date": "2026-10-26", "created_at": "2026-10-30T12:00:00Z", "currency": "TRY", "total_amount": 125, "status": "completed"},
        {"id": "wrong-day", "tenant_id": "t", "business_date": "2026-10-30", "created_at": "2026-10-26T12:00:00Z", "currency": "TRY", "total_amount": 999, "status": "completed"},
    ])
    history = await pos_mobile.get_order_history("2026-10-26", "2026-10-26", None, None, None, 20, object())
    summary = await pos_inventory.get_outlet_sales_breakdown("2026-10-26", "2026-10-26", object())
    assert [x["id"] for x in history["orders"]] == ["wanted"]
    assert history["orders"][0]["business_date"] == "2026-10-26"
    assert summary["total_sales_by_currency"] == {"TRY": 125}
    with pytest.raises(HTTPException):
        await pos_mobile.get_order_history("wrong-date", None, None, None, None, 20, object())


async def test_guest_order_rechecks_the_stay_guest_inside_transaction(services):
    from core.room_service_order import place_order

    with pytest.raises(HTTPException):
        await place_order(services, "t", order_body(), "guest-actor", expected_guest_id="previous-guest")
    assert not await services.room_service_orders.count_documents({})


async def test_active_room_lookup_joins_room_id_and_does_not_guess_folio_or_stay(services, monkeypatch):
    from domains.pms import cashier_router

    monkeypatch.setattr(cashier_router, "db", services)
    await services.rooms.insert_one({"tenant_id": "t", "id": "r", "room_number": "101"})
    found = await cashier_router.get_active_booking_by_room("101", actor())
    assert found["found"] and found["booking_id"] == "b" and found["folio_id"] == "actual-folio"
    await services.folios.insert_one({"tenant_id": "t", "booking_id": "b", "id": "second", "status": "open"})
    found = await cashier_router.get_active_booking_by_room("101", actor())
    assert found["found"] and not found["folio_id"] and found["folio_selection_required"]
    with pytest.raises(HTTPException):
        await cashier_router._find_open_folio_for_booking("t", "b")
    await services.bookings.insert_one({"tenant_id": "t", "id": "duplicate", "room_id": "r", "status": "checked_in"})
    with pytest.raises(HTTPException):
        await cashier_router.get_active_booking_by_room("101", actor())
