from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from domains.admin.router.tenants import update_tenant_modules
from domains.admin.schemas import TenantModulesUpdate
from models.schemas import User


@pytest.mark.asyncio
async def test_superadmin_module_update_uses_system_db_for_cross_tenant_audit():
    """Publishing another hotel's modules must not hit request-scoped audit DB."""
    before = {
        "id": "hotel-target",
        "property_name": "Target Hotel",
        "modules": {"pms": True, "quick_id": False},
    }
    after = {
        **before,
        "modules": {"pms": True, "quick_id": True},
    }
    system_db = SimpleNamespace(
        tenants=SimpleNamespace(
            find_one=AsyncMock(side_effect=[before, after]),
            update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)),
        )
    )
    actor = User(
        id="platform-operator",
        tenant_id="platform-home",
        email="operator@syroce.com",
        name="Operator",
        role="super_admin",
        is_active=True,
    )

    with (
        patch("domains.admin.router.tenants.get_system_db", return_value=system_db),
        patch("core.audit.log_audit_event", new=AsyncMock()) as audit,
        patch("core.helpers.invalidate_tenant_doc_cache") as invalidate,
    ):
        result = await update_tenant_modules(
            tenant_id="hotel-target",
            payload=TenantModulesUpdate(modules=after["modules"]),
            current_user=actor,
        )

    assert result["modules"]["quick_id"] is True
    system_db.tenants.update_one.assert_awaited_once()
    invalidate.assert_called_once_with("hotel-target")
    assert audit.await_args.kwargs["tenant_id"] == "hotel-target"
    assert audit.await_args.kwargs["db"] is system_db

