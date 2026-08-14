from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.pms import cashier_router


def _install_identity_store(monkeypatch, credential_row, *, active_tenant="tenant-1"):
    find_one = AsyncMock(return_value=credential_row)
    system_db = SimpleNamespace(users=SimpleNamespace(find_one=find_one))
    monkeypatch.setattr(cashier_router, "get_system_db", lambda: system_db)
    monkeypatch.setattr(cashier_router, "get_current_tenant_id", lambda: active_tenant)
    return find_one


@pytest.mark.asyncio
async def test_peer_verify_finds_canonical_id_in_same_tenant(monkeypatch):
    credential_row = {
        "id": "user-1",
        "tenant_id": "tenant-1",
        "role": "admin",
        "hashed_password": "redacted-hash",
    }
    find_one = _install_identity_store(monkeypatch, credential_row)
    user = SimpleNamespace(id="user-1", tenant_id="tenant-1", role="admin")

    result = await cashier_router._find_peer_verify_user(user)

    assert result is credential_row
    find_one.assert_awaited_once_with({"$or": [{"id": "user-1"}, {"user_id": "user-1"}]})


@pytest.mark.asyncio
async def test_peer_verify_allows_tenantless_platform_admin_in_active_tenant(monkeypatch):
    credential_row = {
        "id": "platform-user-1",
        "role": "super_admin",
        "hashed_password": "redacted-hash",
    }
    _install_identity_store(monkeypatch, credential_row)
    user = SimpleNamespace(
        id="platform-user-1",
        tenant_id=None,
        role="super_admin",
    )

    result = await cashier_router._find_peer_verify_user(user)

    assert result is credential_row


@pytest.mark.asyncio
async def test_peer_verify_rejects_tenantless_non_platform_user(monkeypatch):
    credential_row = {
        "id": "user-1",
        "role": "admin",
        "hashed_password": "redacted-hash",
    }
    _install_identity_store(monkeypatch, credential_row)
    user = SimpleNamespace(id="user-1", tenant_id=None, role="admin")

    result = await cashier_router._find_peer_verify_user(user)

    assert result is None


@pytest.mark.asyncio
async def test_peer_verify_rejects_tenant_mismatch(monkeypatch):
    credential_row = {
        "id": "user-1",
        "tenant_id": "tenant-2",
        "role": "admin",
        "hashed_password": "redacted-hash",
    }
    _install_identity_store(monkeypatch, credential_row, active_tenant="tenant-1")
    user = SimpleNamespace(id="user-1", tenant_id="tenant-2", role="admin")

    result = await cashier_router._find_peer_verify_user(user)

    assert result is None


@pytest.mark.asyncio
async def test_peer_verify_does_not_lookup_without_active_tenant(monkeypatch):
    find_one = _install_identity_store(monkeypatch, None, active_tenant=None)
    user = SimpleNamespace(id="user-1", tenant_id=None, role="super_admin")

    result = await cashier_router._find_peer_verify_user(user)

    assert result is None
    find_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_peer_verify_does_not_fallback_to_email(monkeypatch):
    find_one = _install_identity_store(monkeypatch, None)
    user = SimpleNamespace(
        id="user-1",
        tenant_id="tenant-1",
        role="admin",
        email="operator@example.invalid",
    )

    result = await cashier_router._find_peer_verify_user(user)

    assert result is None
    query = find_one.await_args.args[0]
    assert "email" not in str(query).lower()
