from __future__ import annotations

import pytest
from fastapi import HTTPException

from models.enums import UserRole
from models.schemas import User
from modules.pms_core.module_scope_service import (
    filter_modules_for_scopes,
    module_scope_allows,
    normalize_module_scopes,
)
from modules.pms_core.role_permission_service import require_module


def _user(*, role: UserRole, module_scopes: list[str] | None = None) -> User:
    return User(
        id=f"user-{role.value}",
        tenant_id="tenant-1",
        email=f"{role.value}@example.com",
        name=role.value,
        role=role,
        module_scopes=module_scopes or [],
    )


def test_empty_scope_list_preserves_legacy_access() -> None:
    assert module_scope_allows([], "pms") is True
    assert module_scope_allows(None, "invoices") is True


def test_exact_wildcard_and_prefix_scopes_are_normalized() -> None:
    assert normalize_module_scopes([" Channel-Manager ", "PMS", "pms"]) == (
        "channel_manager",
        "pms",
    )
    assert module_scope_allows(["channel-manager"], "channel_manager") is True
    assert module_scope_allows(["finance.*"], "finance_reports") is True
    assert module_scope_allows(["finance.*"], "finance.general_ledger") is True
    assert module_scope_allows(["*"], "maintenance") is True
    assert module_scope_allows(["pms"], "reports") is False


def test_module_map_is_overlaid_without_dropping_keys() -> None:
    filtered = filter_modules_for_scopes(
        {"pms": True, "reports": True, "invoices": False},
        ["pms"],
    )

    assert filtered == {"pms": True, "reports": False, "invoices": False}


@pytest.mark.asyncio
async def test_scoped_staff_can_pass_only_the_selected_role_module() -> None:
    housekeeping_user = _user(
        role=UserRole.STAFF,
        module_scopes=["housekeeping"],
    )

    await require_module("housekeeping")(current_user=housekeeping_user)

    with pytest.raises(HTTPException) as exc_info:
        await require_module("pos")(current_user=housekeeping_user)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_unscoped_staff_keeps_legacy_role_denial() -> None:
    legacy_staff = _user(role=UserRole.STAFF)

    with pytest.raises(HTTPException) as exc_info:
        await require_module("housekeeping")(current_user=legacy_staff)
    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_super_admin_bypasses_user_module_scope() -> None:
    super_admin = _user(
        role=UserRole.SUPER_ADMIN,
        module_scopes=["reports"],
    )

    await require_module("pos")(current_user=super_admin)
