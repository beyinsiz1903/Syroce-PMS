"""Real API handlers + durable LOCAL Mongo rows; no production credentials/providers.

Authentication is injected, but the normal route RBAC and business guards run.
Only a UUID-named database on an explicitly selected loopback replica is used.
"""
import os
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlparse

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from motor.motor_asyncio import AsyncIOMotorClient

from core.security import get_current_user
from domains.pms import cashier_service, frontdesk_router, frontdesk_service
from routers import early_late_pricing, reservation_detail, webhook_retry_service


@pytest_asyncio.fixture(name="acceptance")
async def frontdesk_acceptance(monkeypatch):
    # The complete offline CI job already provisions POS_TEST_MONGO_URI as a
    # loopback replica. Run here too; never turn missing infrastructure green
    # by skipping the lifecycle acceptance tests.
    uri = os.getenv("FRONTDESK_TEST_MONGO_URI") or os.getenv("POS_TEST_MONGO_URI")
    assert uri and urlparse(uri).hostname in {"127.0.0.1", "localhost"}, (
        "Set FRONTDESK_TEST_MONGO_URI or POS_TEST_MONGO_URI to an isolated LOCAL replica; acceptance must not silently skip"
    )
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
    database = client["frontdesk_acceptance_" + uuid.uuid4().hex]
    assert (await client.admin.command("hello")).get("setName"), "Replica set required"
    await database.tenant_settings.insert_one({"tenant_id": "qa", "business_date": "2026-10-26"})
    await database.bookings.insert_one({"tenant_id": "qa", "id": "synthetic-stay", "guest_id": "synthetic-guest",
        "room_id": "synthetic-room", "room_number": "QA104", "currency": "USD", "total_amount": 560,
        "paid_amount": 0, "check_in": "2026-10-21", "check_out": "2026-10-26", "status": "checked_in"})
    await database.rooms.insert_one({"tenant_id": "qa", "id": "synthetic-room", "room_number": "QA104",
        "status": "occupied", "current_booking_id": "synthetic-stay"})
    await database.folios.insert_one({"tenant_id": "qa", "id": "synthetic-folio", "booking_id": "synthetic-stay",
        "folio_number": "QA-FOLIO", "folio_type": "guest", "status": "open", "currency": "USD", "balance": 560})
    await database.folio_charges.insert_one({"tenant_id": "qa", "id": "synthetic-room-charge", "booking_id": "synthetic-stay",
        "folio_id": "synthetic-folio", "charge_type": "room_charge", "charge_category": "room", "total": 560,
        "amount": 560, "quantity": 1, "currency": "USD", "tax_amount": 0, "voided": False})
    for module in (reservation_detail, frontdesk_router, early_late_pricing, cashier_service):
        monkeypatch.setattr(module, "db", database)
    from core import audit_chain, utils
    monkeypatch.setattr(audit_chain, "_system_db", lambda: database)
    monkeypatch.setattr(utils, "db", database)
    monkeypatch.setattr(frontdesk_router.frontdesk_service, "_db", database)
    monkeypatch.setattr(early_late_pricing, "get_tenant_currency", AsyncMock(return_value=("TRY", "₺")))
    monkeypatch.setattr(reservation_detail, "invalidate_financial_report_caches", lambda *_: None)
    # Integration hand-offs are captured, never delivered to KBS/OTA/real banks.
    webhook = []
    monkeypatch.setattr(webhook_retry_service, "schedule_emit_reservation_updated", lambda *args, **kwargs: webhook.append(args))
    kbs = AsyncMock(return_value=None)
    monkeypatch.setattr(frontdesk_service, "_enqueue_kbs_after_frontdesk_transition", kbs)
    monkeypatch.setattr("routers.finance.konaklama_vergisi_core.load_tax_config", AsyncMock(return_value={"active": False}))
    monkeypatch.setattr("shared_kernel.loyalty_award.award_points_for_stay", AsyncMock(return_value=None))
    user = SimpleNamespace(id="qa-operator", name="Synthetic QA Operator", tenant_id="qa", role="admin",
        email="qa@example.invalid", granted_permissions=None, is_super_admin=False)
    app = FastAPI()
    app.include_router(reservation_detail.router)
    app.include_router(frontdesk_router.router)
    app.include_router(early_late_pricing.router)
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://local-acceptance") as api:
            yield SimpleNamespace(db=database, api=api, user=user, webhook=webhook, kbs=kbs)
    finally:
        # Exact generated test database only; never a shared/default database.
        assert database.name.startswith("frontdesk_acceptance_")
        await client.drop_database(database.name)
        client.close()


async def add_fee(acceptance, **overrides):
    return await acceptance.api.post("/api/pms/reservations/synthetic-stay/add-extra-charge", json={
        "description": "QA geç çıkış ek ücreti", "category": "other", "amount": 56, "quantity": 1,
        "input_currency": "USD", "service_date": "2026-10-26", "service_time": "14:30", **overrides})


@pytest.mark.asyncio
async def test_fee_partial_payment_balance_guard_final_payment_and_checkout(acceptance):
    a = acceptance
    source = await a.db.folio_charges.find_one({"id": "synthetic-room-charge"})
    quote = await a.api.post("/api/pms/early-late/calculate", json={"booking_id": "synthetic-stay", "direction": "late_checkout", "actual_hour": 14.5})
    assert quote.status_code == 200, quote.text
    assert (quote.json()["nights"], quote.json()["amount"], quote.json()["currency"]) == (5, 56, "USD")
    result = await add_fee(a)
    assert result.status_code == 200, result.text
    charge = result.json()["charge"]
    assert (charge["total"], charge["currency"], charge["business_date"], charge["service_time"]) == (56, "USD", "2026-10-26", "14:30")
    assert (await a.db.reservation_activity_log.find_one({"action": "extra_charge_added"}))["actor"] == "Synthetic QA Operator"
    assert len(a.webhook) == 1
    payment_url = "/api/frontdesk/folio/synthetic-stay/payment"
    # Explicit synthetic FX fixture; this is not a market quote or production rate.
    payment = {"amount": 600, "method": "card", "payment_type": "interim", "currency": "USD", "received_to_try_rate": 40, "reference": "LOCAL-QA-NOT-A-BANK-TRANSACTION"}
    paid = await a.api.post(payment_url, json=payment, headers={"Idempotency-Key": "qa-partial"})
    assert paid.status_code == 200, paid.text
    # A successful response lost in transit is reconciled by the same durable key.
    replay = await a.api.post(payment_url, json=payment, headers={"Idempotency-Key": "qa-partial"})
    assert replay.status_code == 200 and replay.json()["id"] == paid.json()["id"]
    blocked = await a.api.post("/api/frontdesk/checkout/synthetic-stay")
    assert blocked.status_code == 402, blocked.text
    assert (await a.db.bookings.find_one({"id": "synthetic-stay"}))["status"] == "checked_in"
    final = await a.api.post(payment_url, json={**payment, "amount": 16, "payment_type": "final"}, headers={"Idempotency-Key": "qa-final"})
    assert final.status_code == 200, final.text
    checked_out = await a.api.post("/api/frontdesk/checkout/synthetic-stay")
    assert checked_out.status_code == 200, checked_out.text
    assert checked_out.json()["total_balance"] == 0
    assert checked_out.json()["currency"] == "USD"
    assert (await a.api.post("/api/frontdesk/checkout/synthetic-stay")).status_code == 400
    assert await a.db.housekeeping_tasks.count_documents({"booking_id": "synthetic-stay"}) == 1
    assert (await a.db.rooms.find_one({"id": "synthetic-room"}))["status"] == "dirty"
    assert (await a.db.folios.find_one({"id": "synthetic-folio"}))["status"] == "closed"
    booking = await a.db.bookings.find_one({"id": "synthetic-stay"})
    assert (booking["status"], booking["total_amount"], booking["currency"], booking["checked_out_business_date"]) == ("checked_out", 560, "USD", "2026-10-26")
    assert await a.db.payments.count_documents({}) == 2
    assert await a.db.folio_charges.find_one({"id": "synthetic-room-charge"}) == source
    assert (await a.db.tenant_settings.find_one({"tenant_id": "qa"}))["business_date"] == "2026-10-26"
    assert await a.db.stock_movements.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["checked_out", "cancelled", "no_show"])
async def test_extra_charge_cannot_be_posted_to_a_terminal_reservation(acceptance, status):
    await acceptance.db.bookings.update_one({"id": "synthetic-stay"}, {"$set": {"status": status}})
    result = await add_fee(acceptance)
    assert result.status_code == 409, result.text
    assert await acceptance.db.extra_charges.count_documents({}) == 0
    assert acceptance.webhook == []


@pytest.mark.asyncio
async def test_foreign_tenant_and_read_only_role_cannot_add_a_fee(acceptance):
    acceptance.user.tenant_id = "different-tenant"
    assert (await add_fee(acceptance)).status_code == 404
    acceptance.user.tenant_id = "qa"
    acceptance.user.role = "housekeeping"
    assert (await add_fee(acceptance)).status_code == 403
    assert await acceptance.db.extra_charges.count_documents({}) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("overrides", [{"amount": -1}, {"service_time": "24:00"}, {"service_date": None}, {"input_currency": "EUR"}])
async def test_invalid_fee_or_missing_exchange_rate_is_rejected_without_writes(acceptance, overrides):
    result = await add_fee(acceptance, **overrides)
    assert result.status_code == 422, result.text
    assert await acceptance.db.extra_charges.count_documents({}) == 0


@pytest.mark.asyncio
async def test_departures_use_open_business_day_and_keep_currency_and_added_fee(acceptance):
    assert (await add_fee(acceptance)).status_code == 200
    result = await acceptance.api.get("/api/frontdesk/departures")
    assert result.status_code == 200, result.text
    rows = result.json()
    assert len(rows) == 1
    assert (rows[0]["id"], rows[0]["currency"], rows[0]["balance"], rows[0]["room_number"]) == ("synthetic-stay", "USD", 616, "QA104")
    assert (await acceptance.api.get("/api/frontdesk/departures?date=2026-10-30")).json() == []
    assert (await acceptance.api.get("/api/frontdesk/arrivals?date=2026-02-30")).status_code == 400


@pytest.mark.asyncio
async def test_foreign_payment_requires_explicit_cashier_fx_before_any_durable_write(acceptance):
    url = "/api/frontdesk/folio/synthetic-stay/payment"
    payload = {"amount": 56, "method": "card", "currency": "USD"}
    result = await acceptance.api.post(url, json=payload, headers={"Idempotency-Key": "qa-missing-fx"})
    assert result.status_code == 422, result.text
    assert await acceptance.db.payments.count_documents({}) == 0
    result = await acceptance.api.post(url, json={**payload, "currency": "TRY", "received_to_try_rate": 40})
    assert result.status_code == 422
    assert (await acceptance.db.bookings.find_one({"id": "synthetic-stay"}))["paid_amount"] == 0


@pytest.mark.asyncio
async def test_duplicate_payment_reference_is_a_conflict_without_balance_or_cashier_mutation(acceptance):
    a = acceptance
    await a.db.payments.create_index([('tenant_id', 1), ('booking_id', 1), ('reference', 1)], unique=True, name='uniq_payment_reference_active')
    url = '/api/frontdesk/folio/synthetic-stay/payment'
    body = {'amount': 10, 'currency': 'USD', 'method': 'card', 'received_to_try_rate': 40, 'reference': 'LOCAL-QA-UNIQUE-REF'}
    first = await a.api.post(url, json=body, headers={'Idempotency-Key': 'reference-first'})
    assert first.status_code == 200, first.text
    before_folio = await a.db.folios.find_one({'id': 'synthetic-folio'})
    before_booking = await a.db.bookings.find_one({'id': 'synthetic-stay'})
    before_cash = await a.db.cashier_transactions.count_documents({})
    replay = await a.api.post(url, json=body, headers={'Idempotency-Key': 'reference-first'})
    assert replay.status_code == 200 and replay.json()['id'] == first.json()['id']
    conflict = await a.api.post(url, json={**body, 'amount': 20}, headers={'Idempotency-Key': 'reference-conflict'})
    assert conflict.status_code == 409, conflict.text
    assert await a.db.payments.count_documents({}) == 1
    assert await a.db.folios.find_one({'id': 'synthetic-folio'}) == before_folio
    assert await a.db.bookings.find_one({'id': 'synthetic-stay'}) == before_booking
    assert await a.db.cashier_transactions.count_documents({}) == before_cash
