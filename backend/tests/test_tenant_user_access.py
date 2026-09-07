"""HTTP authorization regressions for the tenant admin entry point; no live DB."""
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

import domains.admin.router.users as users
from core.security import get_current_user


class Collection:
    def __init__(self, records):
        self.records = records
        self.insert_one = AsyncMock()

    def find(self, query):
        async def cursor():
            for record in self.records:
                if all(record.get(key) == value for key, value in query.items()):
                    yield record
        return cursor()

    async def find_one(self, *args, **kwargs):
        return None


@pytest.fixture
def app(monkeypatch):
    current = SimpleNamespace(id="admin", name="QA", role="admin", tenant_id="hotel-a")
    session = AsyncMock()
    session.__aenter__.return_value = session
    async def transaction(callback):
        await callback(session)
    session.with_transaction.side_effect = transaction
    database = SimpleNamespace(
        users=Collection([
            {"id": "a", "tenant_id": "hotel-a", "name": "Hotel A", "role": "staff", "hashed_password": "never-return"},
            {"id": "b", "tenant_id": "hotel-b", "name": "Hotel B", "role": "admin"},
        ]),
        tenants=SimpleNamespace(find_one=AsyncMock(return_value={"subscription_tier": "enterprise"})),
        staff_members=Collection([]),
        client=SimpleNamespace(start_session=AsyncMock(return_value=session)),
    )
    monkeypatch.setattr(users, "db", database)
    monkeypatch.setattr(users, "decrypt_user_doc", lambda doc: doc)
    monkeypatch.setattr(users, "log_audit_event", AsyncMock())
    monkeypatch.setattr("security.encrypted_lookup.encrypt_user_doc", lambda doc: doc)
    monkeypatch.setattr(import_module("core.security"), "hash_password", lambda password: "test-hash-only")
    app = FastAPI()
    app.include_router(users.router)
    app.dependency_overrides[get_current_user] = lambda: current
    return app, current, database


@pytest.mark.asyncio
async def test_admin_list_is_always_own_tenant_without_secrets(app):
    application, _, _ = app
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        response = await client.get("/api/admin/tenant-users?tenant_id=hotel-b")
    assert response.status_code == 200
    assert [row["id"] for row in response.json()["users"]] == ["a"]
    assert "hashed_password" not in response.text


@pytest.mark.asyncio
async def test_admin_can_provision_own_hotel_without_hr_module(app):
    application, _, database = app
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        response = await client.post("/api/admin/users", json={"name": "QA", "email": "qa@example.com", "role": "finance", "mode": "temp", "tenant_id": "hotel-b"})
    assert response.status_code == 200
    assert database.users.insert_one.call_args.args[0]["tenant_id"] == "hotel-a"
    assert database.staff_members.insert_one.call_args.args[0]["tenant_id"] == "hotel-a"
    assert database.users.insert_one.call_args.args[0]["requires_password_change"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["finance", "supervisor", "front_desk", "staff"])
async def test_non_admin_cannot_list_or_create(app, role):
    application, current, database = app
    current.role = role
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        assert (await client.get("/api/admin/tenant-users")).status_code == 403
        assert (await client.post("/api/admin/users", json={"name": "QA", "email": "qa@example.com", "role": "staff"})).status_code == 403
    database.users.insert_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_cannot_create_superadmin_or_see_global_users(app):
    application, _, database = app
    async with AsyncClient(transport=ASGITransport(app=application), base_url="http://test") as client:
        # Platform guard deliberately conceals these routes with 404, not 403.
        assert (await client.get("/api/admin/users")).status_code == 404
        assert (await client.patch("/api/admin/users/a/role", json={"role": "super_admin"})).status_code == 404
        assert (await client.post("/api/admin/users", json={"name": "QA", "email": "qa@example.com", "role": "super_admin"})).status_code == 400
    database.users.insert_one.assert_not_awaited()
