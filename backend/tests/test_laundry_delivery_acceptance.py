"""Normal HTTP laundry delivery against a disposable real replica set."""
import asyncio

import pytest

from tests.test_frontdesk_acceptance_replica import frontdesk_acceptance as frontdesk_acceptance

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
async def laundry(acceptance, monkeypatch):
    from core import audit_chain, utils
    from domains.pms import cashier_router
    a = acceptance
    monkeypatch.setattr(cashier_router, "db", a.db)
    monkeypatch.setattr(audit_chain, "_system_db", lambda: a.db)
    monkeypatch.setattr(utils, "db", a.db)
    a.api._transport.app.include_router(cashier_router.router)
    await a.db.tenant_settings.update_one({"tenant_id": "qa"}, {"$set": {"laundry_orders": [{
        "id": "wash", "room_number": "QA104", "booking_id": "synthetic-stay", "folio_id": "synthetic-folio",
        "status": "pending", "total": 15, "currency": "USD", "folio_charged": False, "items": [{"name": "QA Gömlek", "quantity": 1}]}]}})
    await a.db.folio_ledger.create_index([("tenant_id", 1), ("folio_id", 1), ("sequence_number", 1)], unique=True)


async def deliver(a):
    return await a.api.patch("/api/laundry/orders/wash", json={"status": "delivered"})


async def test_delivery_and_concurrent_retry_create_one_visible_charge(acceptance):
    a = acceptance
    results = await asyncio.gather(deliver(a), deliver(a))
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert await a.db.folio_ledger.count_documents({}) == 1
    assert await a.db.folio_charges.count_documents({"charge_type": "laundry"}) == 1
    assert await a.db.audit_logs.count_documents({"action": "laundry_delivered"}) == 1
    response = await a.api.get("/api/frontdesk/folio/synthetic-stay")
    assert response.json()["balance"] == 575
    assert (await deliver(a)).json()["folio_charge"]["replayed"]


async def test_failure_does_not_mark_delivered_or_leave_hidden_ledger_fee(acceptance, monkeypatch):
    a = acceptance
    original = a.db.folio_charges.update_one
    async def unavailable(self, *args, **kwargs):
        if self.name == "folio_charges":
            raise RuntimeError("QA charge storage unavailable")
        return await original.__func__(self, *args, **kwargs)
    monkeypatch.setattr(type(a.db.folio_charges), "update_one", unavailable)
    with pytest.raises(RuntimeError, match="charge storage unavailable"):
        await deliver(a)
    order = (await a.db.tenant_settings.find_one({"tenant_id": "qa"}))["laundry_orders"][0]
    assert order["status"] == "pending" and not order["folio_charged"]
    assert await a.db.folio_ledger.count_documents({}) == 0


async def test_legacy_same_open_day_ledger_projection_is_repaired_once_without_reposting(acceptance):
    a = acceptance
    await a.db.folio_ledger.insert_one({"tenant_id": "qa", "folio_id": "synthetic-folio", "id": "legacy",
        "booking_id": "synthetic-stay", "sequence_number": 1, "entry_type": "charge", "amount": 15,
        "currency": "USD", "business_date": "2026-10-26", "idempotency_key": "laundry:wash",
        "posted_at": "2026-10-26T10:00:00Z", "posted_by": "QA operator", "description": "QA eski teslim"})
    await a.db.tenant_settings.update_one({"tenant_id": "qa"}, {"$set": {"laundry_orders.0.folio_charged": True, "laundry_orders.0.folio_entry_id": "legacy"}})
    assert (await deliver(a)).status_code == 200
    assert (await deliver(a)).status_code == 200
    assert await a.db.folio_ledger.count_documents({}) == 1
    charge = await a.db.folio_charges.find_one({"charge_type": "laundry"})
    assert charge["source_ledger_entry_id"] == "legacy" and charge["total"] == 15


async def test_currency_mismatch_fails_closed_without_fabricated_exchange_rate(acceptance):
    a = acceptance
    await a.db.tenant_settings.update_one({"tenant_id": "qa"}, {"$set": {"laundry_orders.0.currency": "TRY"}})
    assert (await deliver(a)).status_code == 409
    assert await a.db.folio_ledger.count_documents({}) == 0
