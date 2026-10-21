"""One synthetic event through real HTTP handlers + local Mongo + real GL.

No live hotel, SMTP, bank, card provider or government endpoint is contacted.
"""
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI, HTTPException

from core.entitlements import enforcement
from core.mice_integrity import local_instant
from core.security import get_current_user
from routers import mice, mice_consumption, mice_documents, mice_finance, mice_seating, sales_catering
from tests.test_mice_mongo_acceptance import USER, wired  # noqa: F401
from tests.test_report_ledger_mongo_acceptance import ledger_db  # noqa: F401


@pytest.mark.asyncio
async def test_complete_local_event_chain_reconciles_sales_stock_cash_and_group_folio(wired, monkeypatch):  # noqa: F811
    db = wired
    for module in (mice_consumption, mice_documents, mice_finance, mice_seating):
        monkeypatch.setattr(module, "get_system_db", lambda: db)
    monkeypatch.setattr(sales_catering, "db", db)
    monkeypatch.setattr(sales_catering, "_ensure_indexes", AsyncMock())
    monkeypatch.setattr(enforcement, "tenant_has_feature", AsyncMock(return_value=True))
    monkeypatch.setattr(mice, "get_tenant_limit", AsyncMock(return_value=None))
    monkeypatch.setattr(mice_consumption, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    await db.tenant_settings.insert_one({"tenant_id": "A", "business_date": "2026-10-21", "timezone": "Europe/Istanbul"})
    await db.mice_locks.create_index([("tenant_id", 1), ("kind", 1), ("resource_id", 1)], unique=True)
    await db.cashier_shifts.insert_one({"_id": "shift", "tenant_id": "A", "status": "open", "cash_in": 0, "cash_out": 0, "transactions": []})
    await db.gl_accounts.insert_many([{"tenant_id": "A", "code": code, "name": code, "type": "asset", "active": True} for code in ("100", "120")])
    await db.mice_accounts.insert_one({"tenant_id": "A", "id": "client", "name": "Synthetic client", "account_type": "client"})
    await db.users.insert_one({"tenant_id": "A", "id": "u", "role": "admin", "name": "Synthetic operator"})
    await db.mice_opportunities.insert_one({"tenant_id": "A", "id": "opp", "title": "Synthetic conference", "account_id": "client", "currency": "TRY", "stage": "contract", "pax": 8, "estimated_value": 99999, "expected_start": "2026-10-21", "expected_end": "2026-10-21"})
    await db.group_blocks.insert_one({"tenant_id": "A", "id": "group", "master_folio_id": "master", "status": "definite"})
    await db.folios.insert_one({"tenant_id": "A", "id": "master", "folio_type": "group_master", "status": "open", "currency": "TRY", "balance": 0, "total_charges": 0})
    await db.mice_spaces.insert_one({"tenant_id": "A", "id": "hall", "name": "Synthetic hall", "capacity_theatre": 20, "hourly_rate": 50, "currency": "TRY"})
    await db.mice_menus.insert_one({"tenant_id": "A", "id": "menu", "name": "Synthetic menu", "type": "fb", "price_per_person": 5, "currency": "TRY"})
    await db.ingredients.insert_one({"tenant_id": "A", "id": "ingredient", "name": "Synthetic ingredient", "current_stock": 10, "unit_cost": 3, "unit": "kg", "currency": "TRY"})
    await db.recipes.insert_one({"tenant_id": "A", "id": "recipe", "menu_item_name": "Synthetic recipe", "serving_size": 4, "ingredients": [{"ingredient_id": "ingredient", "quantity": 2, "unit": "kg"}]})
    app = FastAPI()
    app.include_router(mice.router)
    app.include_router(sales_catering.router)
    app.dependency_overrides[get_current_user] = lambda: USER
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local-only") as client:
        draft = (await client.get("/api/mice/sales/opportunities/opp/event-draft")).json()["draft"]
        draft.update(status="confirmed", group_block_id="group", pricing={"tax_percent": 20}, space_bookings=[{"space_id": "hall", "starts_at": "2026-10-21T10:00", "ends_at": "2026-10-21T12:00"}], resources=[{"menu_id": "menu", "name": "Synthetic menu", "quantity": 8, "quantity_mode": "explicit"}])
        created = await client.post("/api/mice/events", json=draft)
        assert created.status_code == 200, created.text
        event = created.json()
        eid = event["id"]
        assert event["totals"]["grand_total"] == 168
        assert event["timezone"] == "Europe/Istanbul" and event["space_bookings"][0]["starts_at"].endswith("+03:00")
        assert (await client.post("/api/mice/events", json=draft)).json()["id"] == eid
        won = await client.post("/api/mice/sales/opportunities/opp/transition", json={"to_stage": "won"})
        assert won.status_code == 200, won.text
        layout = await client.put(f"/api/mice/events/{eid}/seating-plan", json={"booking_index": 0, "expected_revision": event["created_at"], "width": 10, "height": 10, "tables": [{"label": "Table 1", "seats": 8, "x": 1, "y": 1, "width": 2, "height": 2}]})
        assert layout.status_code == 200, layout.text
        task = await client.post(f"/api/mice/events/{eid}/tasks", json={"title": "Prepare service", "department": "banquet", "owner_name": "Synthetic operator", "owner_user_id": "u", "client_request_id": "local-task-request"})
        assert task.status_code == 200, task.text
        event = (await client.get(f"/api/mice/events/{eid}")).json()
        version = await client.post(f"/api/mice/events/{eid}/documents", json={"reason": "Synthetic offer frozen", "client_request_id": "local-document-request", "expected_revision": event["updated_at"]})
        assert version.status_code == 200, version.text
        doc = version.json()
        assert (await client.post(f"/api/mice/events/{eid}/documents/{doc['id']}/distribute")).status_code == 200
        assert (await client.post(f"/api/mice/events/{eid}/documents/{doc['id']}/acknowledge")).status_code == 200
        # The kitchen lifecycle already has its own concurrency tests. Use a
        # completed synthetic production to test the actual stock boundary.
        await db.mice_fnb_orders.insert_one({"tenant_id": "A", "event_id": eid, "id": "production", "status": "completed", "lines": [{"name": "Synthetic menu", "quantity": 8, "unit": "pax"}]})
        consumption = {"order_id": "production", "line_index": 0, "recipe_id": "recipe", "batches": 2, "reason": "Synthetic actual ingredient usage"}
        used = await client.post(f"/api/mice/events/{eid}/stock-consumptions", json=consumption)
        assert used.status_code == 200, used.text
        assert (await client.post(f"/api/mice/events/{eid}/stock-consumptions", json=consumption)).json()["replayed"]
        assert (await db.ingredients.find_one({"id": "ingredient"}))["current_stock"] == 6
        payment = await client.post(f"/api/mice/events/{eid}/settlements", json={"request_id": "synthetic-cash-request", "amount": 100, "method": "cash", "reference": "CASH-1", "reason": "Synthetic cash receipt"})
        assert payment.status_code == 200, payment.text
        pid = payment.json()["payment"]["id"]
        refund = await client.post(f"/api/mice/events/{eid}/settlements", json={"request_id": "synthetic-refund-request", "kind": "refund", "original_payment_id": pid, "amount": 10, "method": "cash", "reference": "REF-1", "reason": "Synthetic partial refund"})
        assert refund.status_code == 200, refund.text
        closed = await client.post(f"/api/mice/events/{eid}/status", json={"status": "completed"})
        assert closed.status_code == 200, closed.text
        assert (await db.folios.find_one({"id": "master"}))["balance"] == 78
        totals = (await client.get(f"/api/mice/events/{eid}/settlements")).json()["totals"]
        assert totals["outstanding"] == 78 and totals["net_collected"] == 90
        costs = (await client.get(f"/api/mice/events/{eid}/actuals")).json()
        assert costs["report"]["actual_cost"] == 12 and costs["report"]["quote_based_contribution"] is None
        assert costs["report"]["posted_net_revenue"] == 140 and costs["report"]["revenue_source"] == "folio_charges"
        complete_costs = await client.put(f"/api/mice/events/{eid}/actuals", json={"actual_pax": 8, "costs_complete": True, "expected_revision": costs["expected_revision"], "costs": [{"name": "Synthetic actual staff hours", "category": "staff", "quantity": 2, "unit_cost": 10}]})
        assert complete_costs.status_code == 200, complete_costs.text
        final_costs = (await client.get(f"/api/mice/events/{eid}/actuals")).json()["report"]
        assert final_costs["actual_cost"] == 32 and final_costs["posted_revenue_less_recorded_cost"] == 108
        replay = await client.post("/api/mice/events", json=draft)
        assert replay.status_code == 200 and replay.json()["id"] == eid
        assert not {"actuals", "generated_costs", "operations_tasks", "stock_consumption_jobs", "document_history"} & replay.json().keys()
        ingredient_usage = await db.stock_consumptions.find_one({"mice_event_id": eid, "ingredient_id": "ingredient"})
        assert ingredient_usage["consumed_quantity"] == 4
        frozen = (await db.mice_events.find_one({"id": eid}))["document_history"][0]["snapshot"]
        assert frozen["event"]["totals"]["grand_total"] == 168 and len(frozen["seating_plans"]) == 1
        assert await db.folio_charges.count_documents({"mice_event_id": eid}) == 1


@pytest.mark.asyncio
async def test_group_master_read_is_uncapped_tenant_scoped_and_refund_aware(wired, monkeypatch):  # noqa: F811
    from domains.pms import groups_router
    monkeypatch.setattr(groups_router, "db", wired)
    await wired.group_blocks.insert_one({"tenant_id": "A", "id": "g", "group_name": "Synthetic group", "currency": "TRY"})
    await wired.folios.insert_many([{"tenant_id": tid, "id": "same-id", "group_block_id": "g", "folio_type": "group_master", "currency": "TRY"} for tid in ["B", "A"]])
    await wired.folio_charges.insert_many([{"id": str(i), "tenant_id": "A", "folio_id": "same-id", "total": 1, "currency": "TRY"} for i in range(1001)])
    await wired.folio_charges.insert_one({"tenant_id": "B", "folio_id": "same-id", "total": 999999, "currency": "EUR"})
    await wired.payments.insert_many([
        {"id": "cash", "tenant_id": "A", "folio_id": "same-id", "amount": 100, "status": "paid", "currency": "TRY"},
        {"id": "refund", "tenant_id": "A", "folio_id": "same-id", "amount": 10, "payment_type": "refund", "status": "refunded", "currency": "TRY"},
        {"id": "pending", "tenant_id": "A", "folio_id": "same-id", "amount": 999, "status": "pending", "currency": "TRY"},
        {"id": "foreign", "tenant_id": "B", "folio_id": "same-id", "amount": 999, "currency": "EUR"},
    ])
    result = await groups_router.get_group_master_folio("g", USER)
    assert result["folio"]["total_charges"] == 1001
    assert result["folio"]["total_payments"] == 90 and result["folio"]["balance"] == 911
    assert result["charges_count"] == 1001 and result["payments_count"] == 2
    await wired.payments.insert_one({"id": "mixed", "tenant_id": "A", "folio_id": "same-id", "amount": 20, "currency": "EUR"})
    with pytest.raises(HTTPException) as error:
        await groups_router.get_group_master_folio("g", USER)
    assert error.value.status_code == 409


@pytest.mark.asyncio
async def test_group_handoff_failure_rolls_back_status_and_charge_together(wired):  # noqa: F811
    await wired.tenant_settings.insert_one({"tenant_id": "A", "business_date": "2026-10-21"})
    await wired.mice_events.insert_one({"tenant_id": "A", "id": "event", "name": "Synthetic", "status": "confirmed", "group_block_id": "group", "currency": "TRY", "totals": {"grand_total": 120, "tax_total": 20}})
    await wired.group_blocks.insert_one({"tenant_id": "A", "id": "group", "master_folio_id": "missing"})
    with pytest.raises(HTTPException) as error:
        await mice.change_status("event", mice.StatusUpdate(status="completed"), USER)
    assert error.value.status_code == 409
    assert (await wired.mice_events.find_one({"id": "event"}))["status"] == "confirmed"
    assert await wired.folio_charges.count_documents({}) == 0


def test_property_clock_rejects_dst_gaps_and_ambiguous_wall_times():
    for value in ("2026-03-29T02:30", "2026-10-25T02:30"):
        with pytest.raises(ValueError): local_instant(value, "Europe/Berlin")
    assert local_instant("2026-10-21T07:00:00Z", "Europe/Istanbul").hour == 10


@pytest.mark.asyncio
async def test_stock_failure_rolls_back_all_ingredients_and_costs(wired, monkeypatch):  # noqa: F811
    monkeypatch.setattr(mice_consumption, "get_system_db", lambda: wired)
    monkeypatch.setattr(mice_consumption, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    await wired.mice_events.insert_one({"tenant_id": "A", "id": "event", "currency": "TRY"})
    await wired.mice_fnb_orders.insert_one({"tenant_id": "A", "event_id": "event", "id": "production", "status": "completed", "lines": [{}]})
    await wired.ingredients.insert_many([{"tenant_id": "A", "id": iid, "name": iid, "current_stock": stock, "unit": "kg", "unit_cost": 1} for iid, stock in [("available", 10), ("empty", 0)]])
    await wired.recipes.insert_one({"tenant_id": "A", "id": "recipe", "ingredients": [{"ingredient_id": iid, "quantity": 1, "unit": "kg"} for iid in ["available", "empty"]]})
    with pytest.raises(HTTPException) as error:
        await mice_consumption.consume_recipe("event", mice_consumption.ConsumeIn(order_id="production", line_index=0, recipe_id="recipe", batches=1, reason="Synthetic rollback test"), USER)
    assert error.value.status_code == 409
    assert (await wired.ingredients.find_one({"id": "available"}))["current_stock"] == 10
    assert await wired.stock_consumptions.count_documents({}) == 0
