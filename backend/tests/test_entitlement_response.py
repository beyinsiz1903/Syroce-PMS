import sys
import unittest.mock as um
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.append("backend")
import domains.admin.router.subscription as sub_router
from domains.admin.router.subscription import _get_full_entitlements


@pytest.mark.asyncio
async def test_full_entitlements_no_subscription():
    mock_get_editions = AsyncMock(return_value=[])

    orig_get_editions = sub_router.get_tenant_active_editions
    sub_router.get_tenant_active_editions = mock_get_editions

    res = await _get_full_entitlements("tenant_123")
    assert res == {}

    sub_router.get_tenant_active_editions = orig_get_editions


@pytest.mark.asyncio
async def test_full_entitlements_basic():
    original_registry = sub_router.ENTITLEMENT_REGISTRY

    sub_router.ENTITLEMENT_REGISTRY = {
        "pos_fnb": MagicMock(editions={
            "basic": MagicMock(features=["orders"], limits={"outlets": 1})
        })
    }

    orig_get_editions = sub_router.get_tenant_active_editions
    sub_router.get_tenant_active_editions = AsyncMock(return_value=["basic"])

    res = await _get_full_entitlements("tenant_123")

    assert "pos_fnb" in res
    assert res["pos_fnb"]["editions"] == ["basic"]
    assert "orders" in res["pos_fnb"]["features"]
    assert "kds" not in res["pos_fnb"]["features"]
    assert res["pos_fnb"]["limits"]["outlets"] == 1

    sub_router.ENTITLEMENT_REGISTRY = original_registry
    sub_router.get_tenant_active_editions = orig_get_editions


@pytest.mark.asyncio
async def test_full_entitlements_pro():
    original_registry = sub_router.ENTITLEMENT_REGISTRY

    sub_router.ENTITLEMENT_REGISTRY = {
        "pos_fnb": MagicMock(editions={
            "pro": MagicMock(features=["orders", "kds"], limits={"outlets": 5})
        })
    }

    orig_get_editions = sub_router.get_tenant_active_editions
    sub_router.get_tenant_active_editions = AsyncMock(return_value=["pro"])

    res = await _get_full_entitlements("tenant_123")

    assert res["pos_fnb"]["editions"] == ["pro"]
    assert "kds" in res["pos_fnb"]["features"]
    assert res["pos_fnb"]["limits"]["outlets"] == 5

    sub_router.ENTITLEMENT_REGISTRY = original_registry
    sub_router.get_tenant_active_editions = orig_get_editions


# ── GET /subscription/current — HTTP endpoint tests ────────────────────────


class _MockUser:
    def __init__(self, tenant_id="tenant_1"):
        self.tenant_id = tenant_id
        self.id = "user_1"
        self.role = "admin"
        self.username = "testuser"


@pytest.fixture()
def mock_sub_db():
    with um.patch("domains.admin.router.subscription.db") as m:
        tenant_doc = {
            "id": "tenant_1",
            "subscription_tier": "basic",
            "subscription_status": "active",
            "subscription_valid_until": None,
            "modules": {"housekeeping": True},
        }
        m.tenants.find_one = AsyncMock(return_value=tenant_doc)
        m.rooms.count_documents = AsyncMock(return_value=5)
        m.users.count_documents = AsyncMock(return_value=3)
        yield m


@pytest.fixture()
def mock_entitlements_helper():
    """Patches _get_full_entitlements at module level to return predictable data."""
    sample = {
        "spa": {
            "editions": ["basic"],
            "features": [],
            "limits": {"therapists": 3, "rooms": 2},
        }
    }
    with um.patch(
        "domains.admin.router.subscription._get_full_entitlements",
        new_callable=AsyncMock,
        return_value=sample,
    ) as m:
        yield m, sample


@pytest.mark.asyncio
async def test_subscription_current_returns_entitlements(mock_sub_db, mock_entitlements_helper):
    """entitlements alanı response'da bulunmalı ve dict olmalı."""
    from domains.admin.router.subscription import get_current_subscription

    patch_fn, _expected = mock_entitlements_helper
    result = await get_current_subscription(current_user=_MockUser())
    assert "entitlements" in result
    assert isinstance(result["entitlements"], dict)


@pytest.mark.asyncio
async def test_subscription_current_entitlements_is_dict_not_none(mock_sub_db, mock_entitlements_helper):
    """entitlements hiçbir zaman None olmamalı."""
    from domains.admin.router.subscription import get_current_subscription

    result = await get_current_subscription(current_user=_MockUser())
    assert result["entitlements"] is not None
    assert isinstance(result["entitlements"], dict)



@pytest.mark.asyncio
async def test_subscription_current_preserves_modules_field(mock_sub_db, mock_entitlements_helper):
    """Mevcut modules alanı entitlements eklenmesinden etkilenmemeli."""
    from domains.admin.router.subscription import get_current_subscription

    result = await get_current_subscription(current_user=_MockUser())
    assert "modules" in result
    assert "entitlements" in result
    assert "tier" in result
    assert "tenant_id" in result


@pytest.mark.asyncio
async def test_subscription_current_returns_limits_and_features(mock_sub_db, mock_entitlements_helper):
    """entitlements alt modülleri limits ve features içermeli."""
    from domains.admin.router.subscription import get_current_subscription

    _, expected = mock_entitlements_helper
    result = await get_current_subscription(current_user=_MockUser())
    ents = result["entitlements"]
    assert ents == expected
    assert "spa" in ents
    assert ents["spa"]["limits"]["therapists"] == 3
    assert ents["spa"]["limits"]["rooms"] == 2


@pytest.mark.asyncio
async def test_subscription_current_tenant_not_found():
    """Tenant yoksa 404 dönmeli — entitlements eklenmesi bu davranışı değiştirmemeli."""
    from fastapi import HTTPException

    from domains.admin.router.subscription import get_current_subscription

    with um.patch("domains.admin.router.subscription.db") as m:
        m.tenants.find_one = AsyncMock(return_value=None)
        with pytest.raises(HTTPException) as exc_info:
            await get_current_subscription(current_user=_MockUser())
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_subscription_current_called_once_per_request(mock_sub_db, mock_entitlements_helper):
    """_get_full_entitlements aynı request içinde yalnız bir kez çağrılmalı."""
    from domains.admin.router.subscription import get_current_subscription

    patch_fn, _ = mock_entitlements_helper
    await get_current_subscription(current_user=_MockUser())
    patch_fn.assert_awaited_once()
