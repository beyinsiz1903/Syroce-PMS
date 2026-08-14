from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.pms import cashier_router


@pytest.mark.asyncio
async def test_peer_verify_finds_canonical_id_in_same_tenant(monkeypatch):
    user = SimpleNamespace(id="user-1", tenant_id="tenant-1")
    credential_row = {
        "id": "user-1",
        "tenant_id": "tenant-1",
        "hashed_password": "redacted-hash",
    }
    find_one = AsyncMock(return_value=credential_row)
    monkeypatch.setattr(
        cashier_router,
        "db",
        SimpleNamespace(users=SimpleNamespace(find_one=find_one)),
    )

    result = await cashier_router._find_peer_verify_user(user)

    assert result is credential_row
    find_one.assert_awaited_once_with(
        {
            "tenant_id": "tenant-1",
            "$or": [{"id": "user-1"}, {"user_id": "user-1"}],
        }
    )


@pytest.mark.asyncio
async def test_peer_verify_does_not_lookup_without_tenant(monkeypatch):
    find_one = AsyncMock()
    monkeypatch.setattr(
        cashier_router,
        "db",
        SimpleNamespace(users=SimpleNamespace(find_one=find_one)),
    )

    result = await cashier_router._find_peer_verify_user(SimpleNamespace(id="user-1", tenant_id=None))

    assert result is None
    find_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_peer_verify_does_not_fallback_to_email_or_other_tenant(monkeypatch):
    find_one = AsyncMock(return_value=None)
    monkeypatch.setattr(
        cashier_router,
        "db",
        SimpleNamespace(users=SimpleNamespace(find_one=find_one)),
    )

    result = await cashier_router._find_peer_verify_user(
        SimpleNamespace(
            id="user-1",
            tenant_id="tenant-1",
            email="operator@example.invalid",
        )
    )

    assert result is None
    query = find_one.await_args.args[0]
    assert query["tenant_id"] == "tenant-1"
    assert "email" not in str(query).lower()
