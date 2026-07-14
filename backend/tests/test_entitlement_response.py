import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from fastapi.testclient import TestClient
import sys

sys.path.append('backend')
from domains.admin.router.subscription import _get_full_entitlements
import domains.admin.router.subscription as sub_router

@pytest.mark.asyncio
async def test_full_entitlements_no_subscription():
    import core.entitlements.enforcement as enf
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
