import importlib
from types import SimpleNamespace
from unittest.mock import AsyncMock

import jwt
import pytest
from fastapi import HTTPException

from core.security import JWT_ALGORITHM, JWT_SECRET
from routers import marketplace_b2b


def _superadmin(**overrides):
    values = {
        "id": "super-1",
        "role": "super_admin",
        "roles": ["super_admin"],
        "is_impersonating": False,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def _system_db(*, agency=None, target_user=None):
    return SimpleNamespace(
        marketplace_agencies=SimpleNamespace(find_one=AsyncMock(return_value=agency)),
        users=SimpleNamespace(find_one=AsyncMock(return_value=target_user)),
        marketplace_audit_logs=SimpleNamespace(insert_one=AsyncMock()),
    )


@pytest.mark.asyncio
async def test_superadmin_gets_short_lived_scoped_agency_context(monkeypatch):
    db = _system_db(agency={"id": "agency-1", "name": "Kartepe Travel", "status": "active"})
    monkeypatch.setattr(marketplace_b2b, "get_system_db", lambda: db)
    request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"))

    result = await marketplace_b2b.admin_enter_agency_portal("agency-1", request, _superadmin())
    claims = jwt.decode(result["token"], JWT_SECRET, algorithms=[JWT_ALGORITHM])

    assert claims["purpose"] == "admin_agency_context"
    assert claims["impersonation"] is True
    assert claims["actor_user_id"] == "super-1"
    assert claims["user_id"] == "admin-agency-context:agency-1"
    assert claims["agency_id"] == "agency-1"
    assert claims["exp"] - claims["iat"] <= 15 * 60 + 1
    audit = db.marketplace_audit_logs.insert_one.await_args.args[0]
    assert audit["action"] == "admin_agency_context_enter"
    assert audit["details"]["context_identity"] == "scoped_superadmin_preview"
    assert audit["details"]["source_ip"] == "127.0.0.1"


@pytest.mark.asyncio
async def test_impersonated_hotel_admin_cannot_enter_agency_context(monkeypatch):
    monkeypatch.setattr(marketplace_b2b, "get_system_db", lambda: _system_db())
    request = SimpleNamespace(client=None)

    with pytest.raises(HTTPException) as exc:
        await marketplace_b2b.admin_enter_agency_portal(
            "agency-1", request, _superadmin(is_impersonating=True)
        )

    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_agency_context_does_not_require_an_active_portal_user(monkeypatch):
    db = _system_db(agency={"id": "agency-1", "status": "active"}, target_user=None)
    monkeypatch.setattr(marketplace_b2b, "get_system_db", lambda: db)

    result = await marketplace_b2b.admin_enter_agency_portal(
        "agency-1", SimpleNamespace(client=None), _superadmin()
    )

    assert result["portal_path"] == "/agency-portal"
    db.users.find_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_context_revalidates_superadmin_on_every_portal_request(monkeypatch):
    token, _ = marketplace_b2b._create_admin_agency_context_token(
        actor_user_id="super-1", agency_id="agency-1"
    )
    users = SimpleNamespace(find_one=AsyncMock(return_value={
        "id": "super-1", "role": "super_admin", "roles": ["super_admin"], "is_active": True,
    }))
    db = SimpleNamespace(
        users=users,
        marketplace_agencies=SimpleNamespace(find_one=AsyncMock(return_value={"id": "agency-1", "status": "active"})),
    )
    monkeypatch.setattr(marketplace_b2b, "get_system_db", lambda: db)
    security_module = importlib.import_module("core.security")
    monkeypatch.setattr(security_module, "is_jti_revoked", AsyncMock(return_value=False))

    result = await marketplace_b2b.get_marketplace_agency(
        SimpleNamespace(client=None), authorization=f"Bearer {token}"
    )

    assert result["agency_id"] == "agency-1"
    assert result["impersonation"]["actor_id"] == "super-1"
    assert result["impersonation"]["active"] is True
    assert result["user"]["id"] == "admin-agency-context:agency-1"
    users.find_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_context_exit_revokes_token_and_writes_audit(monkeypatch):
    db = _system_db()
    monkeypatch.setattr(marketplace_b2b, "get_system_db", lambda: db)
    security_module = importlib.import_module("core.security")
    revoke = AsyncMock(return_value=True)
    monkeypatch.setattr(security_module, "revoke_jti", revoke)

    result = await marketplace_b2b.marketplace_admin_context_exit({
        "agency_id": "agency-1",
        "impersonation": {
            "active": True,
            "actor_id": "super-1",
            "jti": "preview-jti",
            "expires_at": 2_000_000_000,
        },
    })

    assert result == {"ok": True}
    revoke.assert_awaited_once_with(
        "preview-jti", 2_000_000_000, user_id="super-1", reason="admin_agency_context_exit"
    )
    audit = db.marketplace_audit_logs.insert_one.await_args.args[0]
    assert audit["action"] == "admin_agency_context_exit"
