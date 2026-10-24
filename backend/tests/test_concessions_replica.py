"""Direct concessions: real local Mongo transactions, HTTP permissions and audit.

CONCESSION_TEST_MONGO_URI must point to an isolated localhost replica set.
Only a freshly created UUID database is ever modified or dropped.
"""
import asyncio
import os
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import urlparse
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI, HTTPException
from motor.motor_asyncio import AsyncIOMotorClient

from core import audit_chain
from core import database as database_module
from core.security import get_current_user
from domains.pms import enterprise_billing_router as routes
from models.schemas import User
from modules.pms_core import enterprise_billing as billing
from modules.pms_core.reporting_financials import effective_collection

REFRESH_AFTER_COMMIT = routes._refresh_after_commit


@pytest_asyncio.fixture
async def db(monkeypatch):
    uri = os.getenv("CONCESSION_TEST_MONGO_URI")
    assert uri, "Set CONCESSION_TEST_MONGO_URI to a local replica set; never silently skip financial acceptance"
    assert urlparse(uri).hostname in {"127.0.0.1", "localhost"}, "Production databases are forbidden"
    client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=3000)
    assert (await client.admin.command("hello")).get("setName"), "Transactions require a replica set"
    database = client["concession_acceptance_" + uuid4().hex]
    for name in ("bookings", "folios", "folio_charges", "payments", "billing_concessions", "invoices",
                 "tenant_settings", "pms_audit_trail", "audit_logs", "audit_chain_state", "reservation_financial_locks"):
        await database.create_collection(name)
    await database.reservation_financial_locks.create_index(
        [("tenant_id", 1), ("kind", 1), ("resource_id", 1)], unique=True)
    await database.bookings.insert_one({"id": "booking", "tenant_id": "A", "currency": "TRY", "status": "checked_in"})
    await database.folios.insert_one({"id": "guest", "tenant_id": "A", "booking_id": "booking", "status": "open", "currency": "TRY", "balance": 999999})
    await database.folio_charges.insert_one({"id": "room", "tenant_id": "A", "booking_id": "booking", "folio_id": "guest",
        "charge_category": "room", "amount": 900, "tax_amount": 100, "total": 1000, "currency": "TRY", "voided": False})
    await database.tenant_settings.insert_one({"tenant_id": "A", "business_date": "2026-10-24"})
    monkeypatch.setattr(routes, "db", database)
    monkeypatch.setattr(database_module, "client", client)
    monkeypatch.setattr(audit_chain, "_system_db", lambda: database)
    monkeypatch.setattr(routes, "_refresh_after_commit", AsyncMock())
    try:
        yield database
    finally:
        await client.drop_database(database.name)
        client.close()


def user(role="super_admin", tenant="A", permissions=()):
    return User(id="operator", name="Ayşe Yılmaz", email="operator@example.com", tenant_id=tenant,
                role=role, granted_permissions=list(permissions))


def payload(**changes):
    return billing.ConcessionRequest(**{"request_id": uuid4(), "booking_id": "booking", "folio_id": "guest", "charge_ids": ["room"],
        "kind": "room_comp", "mode": "full", "reason": "Yönetim misafiri için oda ikramı", **changes})


async def apply(db, data, *, tenant="A"):
    async def commit(session):
        return await billing.request_concession(db, tenant, "operator", data, session=session,
            actor_name="Ayşe Yılmaz", actor_role="super_admin")

    return await routes._transaction(user(tenant=tenant), data.booking_id, commit)


@pytest.mark.asyncio
async def test_direct_apply_audits_actor_reason_allocation_and_replays_once(db):
    original = await db.folio_charges.find_one({})
    data = payload()
    result = await apply(db, data)
    assert result["status"] == "applied" and result["decided_by"] == "operator"
    assert await apply(db, data) == result
    assert await db.payments.count_documents({}) == await db.billing_concessions.count_documents({}) == 1
    assert await db.audit_logs.count_documents({}) == await db.pms_audit_trail.count_documents({}) == 1
    assert (await db.folios.find_one({}))["balance"] == 0
    assert await db.folio_charges.find_one({}) == original
    payment = await db.payments.find_one({})
    assert effective_collection(payment) == 0 and payment["business_date"] == "2026-10-24"
    entry = await db.audit_logs.find_one({})
    assert entry["actor_name"] == "Ayşe Yılmaz" and entry["override_reason"] == data.reason
    assert entry["after_snapshot"]["allocated_charge_minor"] == {"room": 100000}
    assert entry["record_hash"] == audit_chain.compute_record_hash(entry, entry["seq"], entry["prev_hash"])
    tampered = deepcopy(entry)
    tampered["after_snapshot"]["reason"] = "Değiştirilmiş"
    assert audit_chain.compute_record_hash(tampered, entry["seq"], entry["prev_hash"]) != entry["record_hash"]
    assert (await audit_chain.verify_chain("A"))["ok"]
    with pytest.raises(HTTPException) as exc:
        await apply(db, data.model_copy(update={"reason": "Başka açıklama"}))
    assert exc.value.status_code == 409


@pytest.mark.asyncio
@pytest.mark.parametrize("collection", ["audit_logs", "pms_audit_trail"])
async def test_log_insert_failure_rolls_back_payment_balance_operation_and_chain(db, monkeypatch, collection):
    real = db[collection]

    class FailingDatabase:
        def __getattr__(self, name):
            if name == collection:
                return SimpleNamespace(insert_one=AsyncMock(side_effect=RuntimeError("Injected log storage failure")))
            return db[name]

    data = payload()

    async def commit(session):
        return await billing.request_concession(FailingDatabase(), "A", "operator", data, session=session)

    with pytest.raises(RuntimeError, match="Injected log storage failure"):
        await routes._transaction(user(), "booking", commit)
    for name in ("payments", "billing_concessions", "audit_logs", "pms_audit_trail", "audit_chain_state"):
        assert await db[name].count_documents({}) == 0
    assert await real.count_documents({}) == 0
    assert (await db.folios.find_one({}))["balance"] == 999999


@pytest.mark.asyncio
async def test_concurrent_double_click_is_one_operation(db):
    data = payload()
    results = await asyncio.gather(*(apply(db, data) for _ in range(6)))
    assert all(result == results[0] for result in results)
    assert await db.payments.count_documents({}) == await db.audit_logs.count_documents({}) == 1


@pytest.mark.asyncio
async def test_concurrent_different_operations_cannot_comp_same_service_twice(db):
    outcomes = await asyncio.gather(*(apply(db, payload()) for _ in range(4)), return_exceptions=True)
    assert sum(isinstance(outcome, dict) for outcome in outcomes) == 1
    assert all(isinstance(outcome, dict) or isinstance(outcome, HTTPException) and outcome.status_code == 409 for outcome in outcomes)
    assert await db.payments.count_documents({}) == await db.audit_logs.count_documents({}) == 1
    assert (await db.folios.find_one({}))["balance"] == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("role,permissions,status", [
    ("super_admin", (), 201),
    ("front_desk", (), 403),
    ("front_desk", ("override_rate",), 201),
    ("housekeeping", ("override_rate",), 403),
])
async def test_http_enforces_existing_charge_and_override_permissions(db, role, permissions, status):
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: user(role, permissions=permissions)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        policy = (await client.get("/api/enterprise-billing/policy")).json()
        if status == 201:
            assert policy["can_apply"] and policy["concession_mode"] == "direct" and policy["reason_required"]
            assert not policy["can_approve"]
        response = await client.post("/api/enterprise-billing/concessions", json=payload().model_dump(mode="json"))
    assert response.status_code == status, response.text
    assert await db.payments.count_documents({}) == (1 if status == 201 else 0)


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", [None, "", "  ", "x", "a" * 501])
async def test_http_requires_explanation(db, reason):
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: user()
    data = payload().model_dump(mode="json")
    data["reason"] = reason
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.post("/api/enterprise-billing/concessions", json=data)).status_code == 422
    assert await db.payments.count_documents({}) == await db.audit_logs.count_documents({}) == 0


@pytest.mark.asyncio
async def test_other_tenant_cannot_apply_or_discover_concessions(db):
    data = payload()
    await apply(db, data)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: user(tenant="B")
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/api/enterprise-billing/concessions?booking_id=booking")).json() == {"items": []}
        assert (await client.post(f"/api/enterprise-billing/concessions/{data.request_id}/apply", json={"reason": data.reason})).status_code == 404
        assert (await client.post("/api/enterprise-billing/concessions", json=data.model_dump(mode="json"))).status_code == 404
    assert await db.payments.count_documents({}) == 1


@pytest.mark.asyncio
async def test_three_legacy_pending_operations_apply_sequentially_by_their_creator(db):
    original = await db.folio_charges.find_one({}, {"_id": 0})
    await db.folio_charges.insert_many([
        {**original, "id": "spa", "total": 1100, "charge_category": "spa", "description": "SPA masaj hizmeti"},
        {**original, "id": "food", "total": 200, "charge_category": "food", "description": "Akşam yemeği"},
    ])
    operations = [payload(mode="percentage", percentage=50), payload(charge_ids=["spa"], kind="selected_services_comp"),
                  payload(charge_ids=["food"], kind="service_recovery", mode="amount", amount_minor=10000)]
    for body in operations:
        fields = body.model_dump(mode="json")
        async with await db.client.start_session() as session:
            basis = await billing.concession_basis(db, "A", body, session=session)
        await db.billing_concessions.insert_one({"_id": f"concession:A:{body.request_id}", "id": str(body.request_id),
            "tenant_id": "A", **fields, **basis, "request_payload": fields, "fingerprint": billing.fingerprint(fields),
            "requested_by": "operator", "status": "requested"})
    assert await db.payments.count_documents({}) == 0  # deployment does not auto-apply old records
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: user()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        for body in operations:
            path = f"/api/enterprise-billing/concessions/{body.request_id}/apply"
            result = await client.post(path, json={"reason": "Sunum için yönetim ikramı"})
            assert result.status_code == 200, result.text
            assert result.json()["status"] == "applied"
            assert (await client.post(path, json={"reason": "Sunum için yönetim ikramı"})).json() == result.json()
    assert await db.payments.count_documents({}) == await db.audit_logs.count_documents({}) == 3
    assert (await db.folios.find_one({}))["balance"] == 600


@pytest.mark.asyncio
async def test_projection_failure_does_not_report_a_committed_concession_as_failed(db, monkeypatch):
    from core import booking_payment_state, report_cache

    monkeypatch.setattr(routes, "_refresh_after_commit", REFRESH_AFTER_COMMIT)
    monkeypatch.setattr(booking_payment_state, "refresh_booking_payment_state", AsyncMock(side_effect=RuntimeError("projection unavailable")))

    def fail_cache(*args):
        raise RuntimeError("cache unavailable")

    monkeypatch.setattr(report_cache, "invalidate_financial_report_caches", fail_cache)
    app = FastAPI()
    app.include_router(routes.router)
    app.dependency_overrides[get_current_user] = lambda: user()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/enterprise-billing/concessions", json=payload().model_dump(mode="json"))
    assert response.status_code == 201 and response.json()["status"] == "applied"
    assert await db.payments.count_documents({}) == await db.audit_logs.count_documents({}) == 1


@pytest.mark.asyncio
async def test_request_ip_and_device_do_not_invalidate_hash_in_production_db_proxy(db, monkeypatch):
    from common.request_context import clear_request_context, set_request_context
    from core.tenant_db import TenantAwareDBProxy, clear_tenant_context, set_tenant_context

    monkeypatch.setattr(routes, 'db', TenantAwareDBProxy(db))
    set_tenant_context('A')
    set_request_context('192.0.2.42', 'Concession Acceptance Browser')
    try:
        async def commit(session):
            return await billing.request_concession(routes.db, 'A', 'operator', payload(), session=session)

        await routes._transaction(user(), 'booking', commit)
        row = await db.audit_logs.find_one({})
        assert row['ip_address'] == '192.0.2.42' and row['user_agent'] == 'Concession Acceptance Browser'
        assert (await audit_chain.verify_chain('A'))['ok']
    finally:
        clear_request_context()
        clear_tenant_context()


@pytest.mark.asyncio
async def test_audit_chain_failure_aborts_concession_without_unchained_fallback(db, monkeypatch):
    monkeypatch.setattr(audit_chain, '_link_chain', AsyncMock(side_effect=RuntimeError('audit chain unavailable')))
    with pytest.raises(RuntimeError, match='audit chain unavailable'):
        await apply(db, payload())
    for name in ('payments', 'billing_concessions', 'audit_logs', 'pms_audit_trail', 'audit_chain_state'):
        assert await db[name].count_documents({}) == 0
    assert (await db.folios.find_one({}))['balance'] == 999999
