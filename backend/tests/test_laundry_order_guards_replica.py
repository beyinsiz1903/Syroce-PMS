"""Mounted, production-first laundry routes; disposable LOCAL replica only."""
import asyncio

import pytest

from bootstrap.router_registry import _EXTRACTED_ROUTERS
from domains.pms import cashier_router, laundry_router
from tests.test_frontdesk_acceptance_replica import frontdesk_acceptance as frontdesk_acceptance
from tests.test_laundry_delivery_acceptance import laundry as laundry

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def catalog(acceptance, laundry, monkeypatch):
    modules = [entry[0] for entry in _EXTRACTED_ROUTERS]
    assert modules.index("domains.pms.cashier_router") < modules.index("domains.pms.laundry_router")
    # Preserve actual registry order, including both duplicate URL definitions.
    monkeypatch.setattr(laundry_router, "db", acceptance.db)
    acceptance.api._transport.app.include_router(laundry_router.router)
    matching = [route for route in acceptance.api._transport.app.routes if getattr(route, "path", None) == "/api/laundry/orders" and "POST" in getattr(route, "methods", ())]
    assert [route.endpoint for route in matching] == [cashier_router.create_laundry_order, laundry_router.create_order]
    await acceptance.db.tenant_settings.update_one({"tenant_id": "qa"}, {"$set": {
        "laundry_items": [{"id": "shirt", "code": "shirt", "name": "Gömlek", "price": 30, "active": True},
                          {"id": "old", "code": "old", "name": "Eski", "price": 10, "active": False}]}})
    await acceptance.db.hotel_settings.insert_one({"tenant_id": "qa", "currency": "USD"})


def payload(**extra):
    return {"room_number": "QA104", "booking_id": "synthetic-stay", "folio_id": "synthetic-folio",
            "service_type": "dry_clean", "items": [{"code": "shirt", "quantity": 2, "total": 0.01}], **extra}


async def create(a, body=None, key=None):
    return await a.api.post("/api/laundry/orders", json=body or payload(), headers={"Idempotency-Key": key} if key else {})


async def test_server_prices_snapshot_not_client_total_and_delivery_reports_one_charge(acceptance):
    a = acceptance
    response = await create(a)
    assert response.status_code == 200, response.text
    order = response.json()
    assert order["total"] == 90 and order["items"][0]["total"] == 90
    assert order["currency"] == "USD"
    url = "/api/laundry/orders/" + order["id"]
    assert (await a.api.patch(url, json={"status": "in_progress"})).status_code == 200
    assert (await a.api.patch(url, json={"status": "ready"})).status_code == 200
    results = await asyncio.gather(*(a.api.patch(url, json={"status": "delivered"}) for _ in range(2)))
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert await a.db.folio_charges.count_documents({"source_laundry_order_id": order["id"]}) == 1
    assert (await a.api.get("/api/frontdesk/folio/synthetic-stay")).json()["balance"] == 650


@pytest.mark.parametrize("extra", [
    {"booking_id": "other"}, {"folio_id": "foreign"}, {"room_number": "missing"},
    {"items": [{"code": "old", "quantity": 1}]},
    {"items": [{"code": "shirt", "quantity": True}]},
    {"items": [{"code": "shirt", "quantity": 1.5}]},
    {"items": [{"code": "shirt", "quantity": 1001}]},
    {"service_type": "surprise"}, {"priority": "anything"},
])
async def test_bad_binding_and_line_inputs_do_not_create_sources(acceptance, extra):
    response = await create(acceptance, payload(**extra))
    assert response.status_code in {400, 409, 422}, response.text
    rows = (await acceptance.db.tenant_settings.find_one({"tenant_id": "qa"}))["laundry_orders"]
    assert len(rows) == 1 and rows[0]["id"] == "wash"


async def test_concurrent_create_retry_is_one_order_and_changed_payload_conflicts(acceptance):
    a = acceptance
    results = await asyncio.gather(*(create(a, key="qa-laundry-retry") for _ in range(3)))
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert len({r.json()["id"] for r in results}) == 1
    assert (await create(a, payload(notes="changed"), "qa-laundry-retry")).status_code == 409
    rows = (await a.db.tenant_settings.find_one({"tenant_id": "qa"}))["laundry_orders"]
    assert len(rows) == 2


async def test_cancelled_order_cannot_be_delivered_or_reopened(acceptance):
    a = acceptance
    response = await create(a)
    url = "/api/laundry/orders/" + response.json()["id"]
    assert (await a.api.patch(url, json={"status": "cancelled"})).status_code == 200
    for status in ("delivered", "pending", "invented"):
        assert (await a.api.patch(url, json={"status": status})).status_code in {400, 409, 422}
    assert await a.db.folio_ledger.count_documents({}) == 0


async def test_source_cannot_be_rebound_or_repriced_through_status_endpoint(acceptance):
    a = acceptance
    assert (await a.api.patch("/api/laundry/orders/wash", json={"total": 999, "folio_id": "other"})).status_code in {400, 422}
    order = (await a.db.tenant_settings.find_one({"tenant_id": "qa"}))["laundry_orders"][0]
    assert order["total"] == 15 and order["folio_id"] == "synthetic-folio"


async def test_room_move_after_creation_fails_delivery_without_fee(acceptance):
    a = acceptance
    await a.db.bookings.update_one({"id": "synthetic-stay"}, {"$set": {"room_id": "other-room"}})
    response = await a.api.patch("/api/laundry/orders/wash", json={"status": "delivered"})
    assert response.status_code == 409, response.text
    assert await a.db.folio_ledger.count_documents({}) == 0


@pytest.mark.parametrize("price", [True, "NaN", "Infinity", "12x", -1, 1.001])
async def test_catalog_rejects_invalid_money_without_writing(acceptance, price):
    a = acceptance
    for method, path, body in [(a.api.post, "/api/laundry/items", {"code": "new", "name": "Yeni", "price": price}),
                                (a.api.put, "/api/laundry/items/shirt", {"price": price})]:
        response = await method(path, json=body)
        assert response.status_code in {400, 422}, response.text
    items = (await a.db.tenant_settings.find_one({"tenant_id": "qa"}))["laundry_items"]
    assert len(items) == 2 and items[0]["price"] == 30


async def test_replay_keeps_original_catalog_snapshot_and_delivered_source_is_immutable(acceptance):
    a = acceptance
    order = (await create(a, payload(guest_name="Wrong person"), "snapshot-key")).json()
    assert order["guest_name"] != "Wrong person"
    await a.db.tenant_settings.update_one({"tenant_id": "qa"}, {"$set": {"laundry_items.0.price": 99}})
    assert (await create(a, payload(guest_name="Wrong person"), "snapshot-key")).json()["total"] == 90
    url = "/api/laundry/orders/" + order["id"]
    assert (await a.api.patch(url, json={"status": "delivered"})).status_code == 200
    assert (await a.api.delete(url)).status_code == 409
    assert (await a.api.patch(url, json={"status": "pending"})).status_code == 409
    charge = await a.db.folio_charges.find_one({"source_laundry_order_id": order["id"]})
    assert charge["total"] == 90


async def test_ambiguous_folio_and_closed_business_day_fail_closed(acceptance):
    a = acceptance
    await a.db.folios.insert_one({"id": "second", "tenant_id": "qa", "booking_id": "synthetic-stay", "status": "open"})
    assert (await create(a, payload(folio_id=""))).status_code == 409
    await a.db.night_audit_runs.insert_one({"tenant_id": "qa", "business_date": "2026-10-26", "status": "completed"})
    assert (await a.api.patch("/api/laundry/orders/wash", json={"status": "delivered"})).status_code == 409
    assert await a.db.folio_ledger.count_documents({}) == 0


async def test_catalog_duplicate_race_and_boolean_boundary(acceptance):
    a = acceptance
    results = await asyncio.gather(*(a.api.post("/api/laundry/items", json={"code": "new", "name": "Yeni", "price": 25}) for _ in range(2)))
    assert sorted(r.status_code for r in results) == [200, 409]
    assert (await a.api.put("/api/laundry/items/shirt", json={"active": "false"})).status_code == 400
    assert (await create(a, payload(service_type=[]))).status_code == 400


@pytest.mark.parametrize("service,total", [("wash_iron", 60), ("dry_clean", 90), ("iron_only", 30), ("express", 120)])
async def test_each_service_uses_its_server_multiplier(acceptance, service, total):
    response = await create(acceptance, payload(service_type=service))
    assert response.status_code == 200 and response.json()["total"] == total


async def test_status_input_and_role_tenant_boundaries_fail_closed(acceptance):
    a = acceptance
    assert (await a.api.patch("/api/laundry/orders/wash", json={"status": []})).status_code == 400
    a.user.role = "guest"
    assert (await create(a)).status_code == 403
    a.user.role = "admin"
    a.user.tenant_id = "other-tenant"
    assert (await create(a)).status_code == 409
    assert (await a.api.patch("/api/laundry/orders/wash", json={"status": "ready"})).status_code == 404
