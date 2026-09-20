import importlib
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from models.enums import UserRole
from models.schemas import User
from modules.pms_core.user_access_policy import (
    CATALOG,
    can_access_page,
    effective_permissions,
    enforce_request_access,
    role_access_matrix,
)


def user(role="front_desk", **kwargs):
    return User(id="actor", tenant_id="hotel-a", email="test@example.com", name="Test", role=role, **kwargs)


def test_frontend_and_backend_catalogs_are_identical():
    frontend = Path(__file__).resolve().parents[3] / "frontend/src/config/userAccessCatalog.json"
    assert json.loads(frontend.read_text()) == CATALOG


@pytest.mark.parametrize("role", list(UserRole))
def test_all_roles_have_auditable_matrix(role):
    entry = next(entry for entry in role_access_matrix() if entry["role"] == role.value)
    assert entry["permissions"] == sorted(effective_permissions(user(role)))


def test_reception_can_run_audit_and_use_cashier_not_accounting_or_admin():
    reception = user()
    assert can_access_page(reception, "night_audit")
    assert can_access_page(reception, "cashier")
    assert not can_access_page(reception, "finance")
    assert not can_access_page(reception, "hr")
    from modules.pms_core.role_permission_service import RolePermissionService
    service = RolePermissionService()
    assert service.check_permission(reception.role, "view_night_audit")
    assert service.check_permission(reception.role, "run_night_audit")
    assert not service.check_permission(reception.role, "manage_night_audit")
    assert not service.check_permission(reception.role, "view_finance_reports")


def test_page_denial_cannot_be_overridden_by_permission_grant():
    limited = user(module_scopes=["reports"], page_access={"reports": False}, granted_permissions=["view_reports"])
    assert not can_access_page(limited, "reports")
    with pytest.raises(HTTPException) as exc:
        enforce_request_access(limited, "/api/reports/daily-flash", "GET")
    assert exc.value.status_code == 403


def test_extra_read_permission_does_not_grant_financial_mutation():
    from modules.pms_core.role_permission_service import RolePermissionService
    staff = user("staff", module_scopes=["finance"], granted_permissions=["view_financial_reports"])
    assert can_access_page(staff, "finance")
    assert not RolePermissionService().check_permission(staff.role, "post_payment", staff.granted_permissions)
    assert not can_access_page(user("staff", module_scopes=["finance"]), "finance")


def test_night_audit_grant_includes_metadata_but_not_schedule_management():
    from modules.pms_core.role_permission_service import RolePermissionService
    actor = user("staff", module_scopes=["night_audit"], granted_permissions=["run_night_audit"])
    assert can_access_page(actor, "night_audit")
    service = RolePermissionService()
    assert service.check_permission(actor.role, "view_business_date", actor.granted_permissions)
    assert not service.check_permission(actor.role, "manage_night_audit", actor.granted_permissions)
    assert not can_access_page(user("staff", module_scopes=["night_audit"]), "night_audit")


def test_shared_resource_is_available_to_other_authorized_consumers():
    reception = user(page_access={"rooms": False})
    assert not can_access_page(reception, "rooms")
    enforce_request_access(reception, "/api/pms/rooms", "GET")  # calendar still needs room names
    with pytest.raises(HTTPException):
        enforce_request_access(user(module_scopes=[]), "/api/pms/rooms", "GET")


def test_auth_response_keeps_scopes_and_page_denials():
    from routers.auth import _USER_RESPONSE_SAFE
    assert {"module_scopes", "page_access", "effective_permissions"}.issubset(_USER_RESPONSE_SAFE)


@pytest.mark.parametrize("denied", [True, False])
def test_real_auth_dependency_checks_page_policy_before_handler(monkeypatch, denied):
    from fastapi import Depends, FastAPI
    from fastapi.testclient import TestClient

    security = importlib.import_module("core.security")
    stored = user("staff", module_scopes=["reports"], page_access={"reports": not denied},
                  granted_permissions=["view_reports"]).model_dump()
    monkeypatch.setattr(security, "_user_doc_cache_get", lambda _: stored.copy())
    monkeypatch.setattr(security.jwt, "decode", lambda *args, **kwargs: {
        "user_id": "actor", "tenant_id": "hotel-a", "type": "access"})
    monkeypatch.setattr("security.encrypted_lookup.decrypt_user_doc", lambda doc: doc)
    app = FastAPI()
    calls = []

    @app.get("/api/reports/daily-flash")
    def report(current_user=Depends(security.get_current_user)):
        calls.append(current_user.id)
        return {"ok": True}

    with TestClient(app) as client:
        response = client.get("/api/reports/daily-flash", headers={"Authorization": "Bearer test"})
    assert response.status_code == (403 if denied else 200)
    assert calls == ([] if denied else ["actor"])


def test_legacy_body_guard_accepts_user_grants_without_broadening_role():
    from routers.finance.cashiering import _enforce

    staff = user("staff", granted_permissions=["post_payment"])
    _enforce(staff, "post_payment")
    with pytest.raises(HTTPException):
        _enforce(staff, "manage_credit_limit")
    with pytest.raises(HTTPException):
        _enforce("staff", "post_payment")


@pytest.fixture
def admin_api(monkeypatch):
    from domains.admin.router import users
    database = MagicMock()
    database.users.find_one = AsyncMock(return_value={"id": "target", "tenant_id": "hotel-a", "role": "staff"})
    database.users.update_one = AsyncMock(return_value=SimpleNamespace(matched_count=1))
    monkeypatch.setattr(users, "db", database)
    monkeypatch.setattr(users, "log_audit_event", AsyncMock())
    security = importlib.import_module("core.security")
    monkeypatch.setattr(security, "invalidate_user_doc_cache", MagicMock())
    return users, database, security.invalidate_user_doc_cache


def payload(api, **kwargs):
    return api.UpdateUserAccessRequest(module_scopes=kwargs.pop("module_scopes", ["reports"]),
        page_access=kwargs.pop("page_access", {}), granted_permissions=kwargs.pop("granted_permissions", ["view_reports"]),
        revision=kwargs.pop("revision", 0), **kwargs)


@pytest.mark.asyncio
async def test_non_admin_rejected_before_lookup(admin_api):
    api, db, _ = admin_api
    with pytest.raises(HTTPException) as exc:
        await api.update_user_access("target", payload(api), user())
    assert exc.value.status_code == 403
    db.users.find_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_admin_change_scoped_audited_and_cache_evicted(admin_api):
    api, db, evict = admin_api
    result = await api.update_user_access("target", payload(api), user("admin"))
    assert result == {"success": True, "revision": 1}
    assert db.users.find_one.call_args.args[0] == {"id": "target", "tenant_id": "hotel-a"}
    assert db.users.update_one.call_args.args[0]["tenant_id"] == "hotel-a"
    api.log_audit_event.assert_awaited_once()
    evict.assert_called_once_with("target")


@pytest.mark.asyncio
async def test_missing_or_other_tenant_cannot_be_changed(admin_api):
    api, db, _ = admin_api
    db.users.find_one.return_value = None
    with pytest.raises(HTTPException) as exc:
        await api.update_user_access("foreign-user", payload(api), user("admin"))
    assert exc.value.status_code == 404
    db.users.update_one.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["admin", "super_admin", "guest", "agency_agent"])
async def test_privileged_and_portal_accounts_protected(admin_api, role):
    api, db, _ = admin_api
    db.users.find_one.return_value["role"] = role
    with pytest.raises(HTTPException) as exc:
        await api.update_user_access("target", payload(api), user("admin"))
    assert exc.value.status_code == 403
    db.users.update_one.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("changes", [
    {"module_scopes": ["*"]}, {"page_access": {"invented": True}},
    {"granted_permissions": ["system_settings"]}, {"granted_permissions": ["manage_users"]},
])
async def test_unknown_or_administrative_grants_rejected(admin_api, changes):
    api, db, _ = admin_api
    with pytest.raises(HTTPException) as exc:
        await api.update_user_access("target", payload(api, **changes), user("admin"))
    assert exc.value.status_code == 400
    db.users.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_stale_edit_conflicts_without_write(admin_api):
    api, db, _ = admin_api
    db.users.find_one.return_value["access_revision"] = 2
    with pytest.raises(HTTPException) as exc:
        await api.update_user_access("target", payload(api), user("admin"))
    assert exc.value.status_code == 409
    db.users.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_audit_does_not_modify_permissions(admin_api):
    api, db, _ = admin_api
    api.log_audit_event.side_effect = RuntimeError("audit storage failed")
    with pytest.raises(RuntimeError):
        await api.update_user_access("target", payload(api), user("admin"))
    db.users.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_reset_unsets_explicit_scopes(admin_api):
    api, db, _ = admin_api
    await api.update_user_access("target", payload(api, reset_to_role=True), user("admin"))
    assert db.users.update_one.call_args.args[1]["$unset"] == {"module_scopes": ""}
