from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException, Request, Response

from core.security import (
    JWT_ALGORITHM,
    JWT_SECRET,
    create_admin_tenant_context_token,
    create_token,
    get_current_user,
)
from domains.admin.router.tenants import (
    enter_tenant_context,
    exit_tenant_context,
    router,
)
from models.schemas import User


def _user_doc(role="super_admin"):
    return {
        "id": "super-1",
        "tenant_id": "tenant-origin",
        "email": "admin@syroce.com",
        "name": "Platform Admin",
        "role": role,
        "is_active": True,
    }


def _tenant(tenant_id, name):
    return {
        "id": tenant_id,
        "property_name": name,
        "subscription_status": "active",
        "subscription_tier": "enterprise",
        "modules": {"pms": True, "channel_manager": True},
    }


@pytest.mark.asyncio
async def test_signed_superadmin_context_changes_only_effective_tenant():
    token, expires_at = create_admin_tenant_context_token(
        "super-1",
        "tenant-origin",
        "tenant-target",
    )
    credentials = MagicMock()
    credentials.credentials = token
    sys_db = AsyncMock()
    sys_db.users.find_one = AsyncMock(return_value=_user_doc())
    sys_db.tenants.find_one = AsyncMock(return_value=_tenant("tenant-target", "Target Hotel"))

    with (
        patch("core.security.is_jti_revoked", new=AsyncMock(return_value=False)),
        patch("core.security._user_doc_cache_get", return_value=None),
        patch("security.encrypted_lookup.decrypt_user_doc", side_effect=lambda value: value),
        patch("core.tenant_db.get_system_db", return_value=sys_db),
    ):
        user = await get_current_user(credentials=credentials)

    assert user.id == "super-1"
    assert user.role.value == "super_admin"
    assert user.tenant_id == "tenant-target"
    assert user.actor_tenant_id == "tenant-origin"
    assert user.is_impersonating is True
    assert user.impersonated_tenant_name == "Target Hotel"
    assert user.impersonation_expires_at == expires_at


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin", "manager"])
async def test_non_superadmin_cannot_use_cross_tenant_context_token(role):
    token, _ = create_admin_tenant_context_token(
        "super-1",
        "tenant-origin",
        "tenant-target",
    )
    credentials = MagicMock()
    credentials.credentials = token
    sys_db = AsyncMock()
    sys_db.users.find_one = AsyncMock(return_value=_user_doc(role=role))

    with (
        patch("core.security.is_jti_revoked", new=AsyncMock(return_value=False)),
        patch("core.security._user_doc_cache_get", return_value=None),
        patch("core.tenant_db.get_system_db", return_value=sys_db),
    ):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials=credentials)

    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_plain_cross_tenant_access_token_remains_rejected():
    credentials = MagicMock()
    credentials.credentials = create_token("super-1", "tenant-target")
    sys_db = AsyncMock()
    sys_db.users.find_one = AsyncMock(return_value=_user_doc())

    with (
        patch("core.security.is_jti_revoked", new=AsyncMock(return_value=False)),
        patch("core.security._user_doc_cache_get", return_value=None),
        patch("core.tenant_db.get_system_db", return_value=sys_db),
    ):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials=credentials)

    assert exc.value.status_code == 401
    assert "mismatch" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_context_is_rejected_after_target_hotel_is_disabled():
    token, _ = create_admin_tenant_context_token(
        "super-1",
        "tenant-origin",
        "tenant-target",
    )
    credentials = MagicMock()
    credentials.credentials = token
    sys_db = AsyncMock()
    sys_db.users.find_one = AsyncMock(return_value=_user_doc())
    sys_db.tenants.find_one = AsyncMock(
        return_value={**_tenant("tenant-target", "Target Hotel"), "is_active": False}
    )

    with (
        patch("core.security.is_jti_revoked", new=AsyncMock(return_value=False)),
        patch("core.security._user_doc_cache_get", return_value=None),
        patch("core.tenant_db.get_system_db", return_value=sys_db),
    ):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials=credentials)

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_same_tenant_context_token_is_rejected():
    token, _ = create_admin_tenant_context_token(
        "super-1",
        "tenant-origin",
        "tenant-origin",
    )
    credentials = MagicMock()
    credentials.credentials = token
    sys_db = AsyncMock()
    sys_db.users.find_one = AsyncMock(return_value=_user_doc())

    with (
        patch("core.security.is_jti_revoked", new=AsyncMock(return_value=False)),
        patch("core.security._user_doc_cache_get", return_value=None),
        patch("core.tenant_db.get_system_db", return_value=sys_db),
    ):
        with pytest.raises(HTTPException) as exc:
            await get_current_user(credentials=credentials)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid admin hotel context"


@pytest.mark.asyncio
async def test_enter_context_sets_short_lived_cookie_and_audits():
    current_user = User(**_user_doc())
    response = Response()
    sys_db = AsyncMock()
    sys_db.tenants.find_one = AsyncMock(
        side_effect=[
            _tenant("tenant-target", "Target Hotel"),
            _tenant("tenant-origin", "Platform Hotel"),
        ]
    )
    sys_db.audit_logs.insert_one = AsyncMock()

    with patch("domains.admin.router.tenants.get_system_db", return_value=sys_db):
        payload = await enter_tenant_context(
            tenant_id="tenant-target",
            response=response,
            current_user=current_user,
        )

    claims = jwt.decode(payload["access_token"], JWT_SECRET, algorithms=[JWT_ALGORITHM])
    assert claims["tenant_id"] == "tenant-target"
    assert claims["actor_tenant_id"] == "tenant-origin"
    assert claims["purpose"] == "admin_tenant_context"
    assert payload["user"]["is_impersonating"] is True
    assert payload["tenant"]["property_name"] == "Target Hotel"
    assert payload["origin"]["tenant"]["property_name"] == "Platform Hotel"
    assert "HttpOnly" in response.headers["set-cookie"]
    assert response.headers["cache-control"] == "no-store"
    audit = sys_db.audit_logs.insert_one.await_args.args[0]
    assert audit["action"] == "admin_tenant_context_enter"
    assert audit["target_tenant_id"] == "tenant-target"


@pytest.mark.asyncio
async def test_exit_context_revokes_context_token_and_restores_origin():
    context_token, expires_at = create_admin_tenant_context_token(
        "super-1",
        "tenant-origin",
        "tenant-target",
    )
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/admin/tenant-context/exit",
            "headers": [(b"cookie", f"access_token={context_token}".encode())],
        }
    )
    response = Response()
    current_user = User(
        **{
            **_user_doc(),
            "tenant_id": "tenant-target",
            "is_impersonating": True,
            "actor_tenant_id": "tenant-origin",
            "impersonated_tenant_name": "Target Hotel",
            "impersonation_expires_at": expires_at,
        }
    )
    sys_db = AsyncMock()
    sys_db.tenants.find_one = AsyncMock(return_value=_tenant("tenant-origin", "Platform Hotel"))
    sys_db.audit_logs.insert_one = AsyncMock()

    with (
        patch("domains.admin.router.tenants.get_system_db", return_value=sys_db),
        patch("domains.admin.router.tenants.revoke_jti", new=AsyncMock(return_value=True)) as revoke,
    ):
        payload = await exit_tenant_context(
            request=request,
            response=response,
            current_user=current_user,
        )

    restored = jwt.decode(payload["access_token"], JWT_SECRET, algorithms=[JWT_ALGORITHM])
    assert restored["tenant_id"] == "tenant-origin"
    assert "impersonation" not in restored
    assert payload["user"]["is_impersonating"] is False
    assert payload["tenant"]["property_name"] == "Platform Hotel"
    assert revoke.await_args.kwargs["tenant_id"] == "tenant-target"
    audit = sys_db.audit_logs.insert_one.await_args.args[0]
    assert audit["action"] == "admin_tenant_context_exit"


def test_admin_tenant_context_routes_are_registered():
    routes = {(route.path, method) for route in router.routes for method in route.methods}
    assert ("/api/admin/tenants/{tenant_id}/context", "POST") in routes
    assert ("/api/admin/tenant-context/exit", "POST") in routes
