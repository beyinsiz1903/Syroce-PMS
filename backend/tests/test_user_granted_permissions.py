"""
Tests: Task #28 — Kullanıcı bazlı operasyon izinleri.

Kapsam:
1. RolePermissionService.check_permission, granted_permissions ile rol-bazlı
   bir izinden yoksun bir kullanıcıya yetki verebiliyor mu?
2. /api/admin/users/{user_id}/granted-permissions GET / PATCH endpoint'leri:
   - ADMIN kendi tenant'ı içindeki bir kullanıcıyı görür / günceller.
   - ADMIN başka tenant'a yazamaz (404).
   - FRONT_DESK reddedilir (403).
   - Whitelist dışı izin → 400.
   - Audit kaydı yazılır (severity=warning).
"""
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"):
    pytest.skip("Motor event loop conflict in CI", allow_module_level=True)

from models.enums import UserRole
from models.schemas import User


def _make_user(role: UserRole = UserRole.ADMIN, tenant_id: str = "tenant-A",
               granted: list[str] | None = None) -> User:
    return User(
        id=f"user-{role.value}-{tenant_id}",
        tenant_id=tenant_id,
        email=f"{role.value}@example.com",
        username=role.value,
        name=role.value.title(),
        role=role,
        granted_permissions=granted or [],
    )


# ── Service: check_permission with granted_permissions ─────────────────


def test_front_desk_cannot_send_urgent_by_default():
    from modules.pms_core.role_permission_service import RolePermissionService
    svc = RolePermissionService()
    assert svc.check_permission("front_desk", "send_urgent_message") is False


def test_front_desk_with_granted_permission_can_send_urgent():
    """Task #28 çekirdek davranış: granted_permissions ile rol-bazlı eksik
    izin tek tek verilebilir."""
    from modules.pms_core.role_permission_service import RolePermissionService
    svc = RolePermissionService()
    assert svc.check_permission(
        "front_desk", "send_urgent_message",
        granted_permissions=["send_urgent_message"],
    ) is True


def test_granted_permissions_does_not_affect_unrelated_operation():
    """granted_permissions sadece eklediği izine yarar; diğer operasyonlar
    için yine rol-bazlı kontrol uygulanır."""
    from modules.pms_core.role_permission_service import RolePermissionService
    svc = RolePermissionService()
    assert svc.check_permission(
        "front_desk", "delete_booking",
        granted_permissions=["send_urgent_message"],
    ) is False


def test_granted_permissions_empty_list_unchanged_behavior():
    """Geriye dönük uyum: boş liste verilse bile davranış değişmez."""
    from modules.pms_core.role_permission_service import RolePermissionService
    svc = RolePermissionService()
    assert svc.check_permission(
        "front_desk", "send_urgent_message",
        granted_permissions=[],
    ) is False


# ── Endpoint helpers ───────────────────────────────────────────────────


def _mock_db_with_user(target_doc: dict | None) -> MagicMock:
    mock_db = MagicMock()
    mock_db.users = MagicMock()
    mock_db.users.find_one = AsyncMock(return_value=target_doc)
    mock_db.users.update_one = AsyncMock()
    mock_db.audit_logs = MagicMock()
    mock_db.audit_logs.insert_one = AsyncMock()
    return mock_db


# ── Endpoint: GET ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_granted_permissions_returns_current_list_for_admin():
    from domains.admin import router as admin_router

    target_doc = {
        "id": "user-fd-1", "tenant_id": "tenant-A",
        "granted_permissions": ["send_urgent_message"],
    }
    mock_db = _mock_db_with_user(target_doc)
    admin = _make_user(role=UserRole.ADMIN, tenant_id="tenant-A")

    with patch.object(admin_router, "db", mock_db):
        result = await admin_router.get_user_granted_permissions(
            user_id="user-fd-1", current_user=admin,
        )

    assert result["user_id"] == "user-fd-1"
    assert result["permissions"] == ["send_urgent_message"]
    assert "send_urgent_message" in result["grantable"]


@pytest.mark.asyncio
async def test_get_granted_permissions_filters_legacy_unknown_perms():
    """Legacy/whitelist-dışı izinler GET cevabında sızdırılmamalı; aksi
    halde frontend toggle PATCH'e bunları geri taşır ve 400 alır
    (admin için fiili kilit)."""
    from domains.admin import router as admin_router

    target_doc = {
        "id": "user-fd-1", "tenant_id": "tenant-A",
        "granted_permissions": ["delete_booking", "send_urgent_message", 42],
    }
    mock_db = _mock_db_with_user(target_doc)
    admin = _make_user(role=UserRole.ADMIN, tenant_id="tenant-A")

    with patch.object(admin_router, "db", mock_db):
        result = await admin_router.get_user_granted_permissions(
            user_id="user-fd-1", current_user=admin,
        )

    assert result["permissions"] == ["send_urgent_message"]


@pytest.mark.asyncio
async def test_get_granted_permissions_404_for_missing_user():
    from domains.admin import router as admin_router

    mock_db = _mock_db_with_user(None)
    admin = _make_user(role=UserRole.ADMIN, tenant_id="tenant-A")

    with patch.object(admin_router, "db", mock_db):
        with pytest.raises(HTTPException) as exc:
            await admin_router.get_user_granted_permissions(
                user_id="missing", current_user=admin,
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_granted_permissions_blocks_admin_other_tenant():
    """ADMIN başka tenant'a okumaya da yazmaya da bakamasın — bilgi sızdırma
    olmasın diye 404 (aynı kod yolunu kullanır)."""
    from domains.admin import router as admin_router

    target_doc = {
        "id": "user-x", "tenant_id": "tenant-B",
        "granted_permissions": [],
    }
    mock_db = _mock_db_with_user(target_doc)
    admin = _make_user(role=UserRole.ADMIN, tenant_id="tenant-A")

    with patch.object(admin_router, "db", mock_db):
        with pytest.raises(HTTPException) as exc:
            await admin_router.get_user_granted_permissions(
                user_id="user-x", current_user=admin,
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_get_granted_permissions_blocks_non_admin_role():
    from domains.admin import router as admin_router

    target_doc = {
        "id": "user-fd-2", "tenant_id": "tenant-A",
        "granted_permissions": [],
    }
    mock_db = _mock_db_with_user(target_doc)
    fd = _make_user(role=UserRole.FRONT_DESK, tenant_id="tenant-A")

    with patch.object(admin_router, "db", mock_db):
        with pytest.raises(HTTPException) as exc:
            await admin_router.get_user_granted_permissions(
                user_id="user-fd-2", current_user=fd,
            )
    assert exc.value.status_code == 403


# ── Endpoint: PATCH ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_update_granted_permissions_writes_set_and_audit():
    from domains.admin import router as admin_router
    from domains.admin.schemas import UpdateGrantedPermissionsRequest

    target_doc = {
        "id": "user-fd-1", "tenant_id": "tenant-A",
        "granted_permissions": [],
    }
    mock_db = _mock_db_with_user(target_doc)
    admin = _make_user(role=UserRole.ADMIN, tenant_id="tenant-A")

    payload = UpdateGrantedPermissionsRequest(permissions=["send_urgent_message"])
    with patch.object(admin_router, "db", mock_db), \
         patch("core.audit.db", mock_db, create=True):
        result = await admin_router.update_user_granted_permissions(
            user_id="user-fd-1", payload=payload, current_user=admin,
        )

    assert result["success"] is True
    assert result["permissions"] == ["send_urgent_message"]

    mock_db.users.update_one.assert_awaited_once()
    args, _ = mock_db.users.update_one.call_args
    assert args[0] == {"id": "user-fd-1"}
    assert args[1] == {"$set": {"granted_permissions": ["send_urgent_message"]}}

    # Audit yazıldı, severity=warning.
    mock_db.audit_logs.insert_one.assert_awaited_once()
    audit_entry = mock_db.audit_logs.insert_one.call_args[0][0]
    assert audit_entry["action"] == "update_user_granted_permissions"
    assert audit_entry["severity"] == "warning"
    assert audit_entry["target_id"] == "user-fd-1"
    assert audit_entry["before_snapshot"] == {"granted_permissions": []}
    assert audit_entry["after_snapshot"] == {"granted_permissions": ["send_urgent_message"]}


@pytest.mark.asyncio
async def test_update_granted_permissions_rejects_non_whitelisted():
    from domains.admin import router as admin_router
    from domains.admin.schemas import UpdateGrantedPermissionsRequest

    target_doc = {
        "id": "user-fd-1", "tenant_id": "tenant-A",
        "granted_permissions": [],
    }
    mock_db = _mock_db_with_user(target_doc)
    admin = _make_user(role=UserRole.ADMIN, tenant_id="tenant-A")

    payload = UpdateGrantedPermissionsRequest(permissions=["delete_booking"])
    with patch.object(admin_router, "db", mock_db):
        with pytest.raises(HTTPException) as exc:
            await admin_router.update_user_granted_permissions(
                user_id="user-fd-1", payload=payload, current_user=admin,
            )
    assert exc.value.status_code == 400
    assert "delete_booking" in exc.value.detail


@pytest.mark.asyncio
async def test_update_granted_permissions_blocks_admin_other_tenant():
    from domains.admin import router as admin_router
    from domains.admin.schemas import UpdateGrantedPermissionsRequest

    target_doc = {
        "id": "user-x", "tenant_id": "tenant-B",
        "granted_permissions": [],
    }
    mock_db = _mock_db_with_user(target_doc)
    admin = _make_user(role=UserRole.ADMIN, tenant_id="tenant-A")

    payload = UpdateGrantedPermissionsRequest(permissions=["send_urgent_message"])
    with patch.object(admin_router, "db", mock_db):
        with pytest.raises(HTTPException) as exc:
            await admin_router.update_user_granted_permissions(
                user_id="user-x", payload=payload, current_user=admin,
            )
    assert exc.value.status_code == 404
    # Yazma yapılmamalı.
    mock_db.users.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_granted_permissions_dedupes_input():
    from domains.admin import router as admin_router
    from domains.admin.schemas import UpdateGrantedPermissionsRequest

    target_doc = {
        "id": "user-fd-1", "tenant_id": "tenant-A",
        "granted_permissions": [],
    }
    mock_db = _mock_db_with_user(target_doc)
    admin = _make_user(role=UserRole.ADMIN, tenant_id="tenant-A")

    payload = UpdateGrantedPermissionsRequest(
        permissions=["send_urgent_message", "send_urgent_message"],
    )
    with patch.object(admin_router, "db", mock_db), \
         patch("core.audit.db", mock_db, create=True):
        result = await admin_router.update_user_granted_permissions(
            user_id="user-fd-1", payload=payload, current_user=admin,
        )
    # Tek sefer yer alır.
    assert result["permissions"] == ["send_urgent_message"]


@pytest.mark.asyncio
async def test_list_tenant_users_admin_returns_own_tenant_only():
    from domains.admin import router as admin_router

    docs = [
        {"id": "u1", "tenant_id": "tenant-A", "name": "Bilge", "email": "b@x",
         "role": "front_desk", "granted_permissions": ["send_urgent_message"]},
        {"id": "u2", "tenant_id": "tenant-A", "name": "Ali", "email": "a@x",
         "role": "housekeeping", "granted_permissions": []},
    ]

    class _Cursor:
        def __aiter__(self):
            self._i = iter(docs)
            return self

        async def __anext__(self):
            try:
                return next(self._i)
            except StopIteration:
                raise StopAsyncIteration

    mock_db = MagicMock()
    mock_db.users = MagicMock()
    mock_db.users.find = MagicMock(return_value=_Cursor())

    admin = _make_user(role=UserRole.ADMIN, tenant_id="tenant-A")
    with patch.object(admin_router, "db", mock_db):
        result = await admin_router.list_tenant_users(
            tenant_id=None, current_user=admin,
        )
    assert result["tenant_id"] == "tenant-A"
    assert {u["id"] for u in result["users"]} == {"u1", "u2"}
    # Sıralama: Ali, Bilge.
    assert [u["id"] for u in result["users"]] == ["u2", "u1"]
    # Whitelist döner.
    assert "send_urgent_message" in result["grantable"]
    # Filtre tenant'a bağlı yapıldı.
    args, _ = mock_db.users.find.call_args
    assert args[0] == {"tenant_id": "tenant-A"}


@pytest.mark.asyncio
async def test_list_tenant_users_super_admin_requires_tenant_id():
    from domains.admin import router as admin_router

    mock_db = MagicMock()
    sa = _make_user(role=UserRole.SUPER_ADMIN, tenant_id="tenant-A")
    with patch.object(admin_router, "db", mock_db):
        with pytest.raises(HTTPException) as exc:
            await admin_router.list_tenant_users(
                tenant_id=None, current_user=sa,
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_list_tenant_users_blocks_non_admin():
    from domains.admin import router as admin_router

    mock_db = MagicMock()
    fd = _make_user(role=UserRole.FRONT_DESK, tenant_id="tenant-A")
    with patch.object(admin_router, "db", mock_db):
        with pytest.raises(HTTPException) as exc:
            await admin_router.list_tenant_users(
                tenant_id=None, current_user=fd,
            )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_update_granted_permissions_super_admin_can_write_any_tenant():
    from domains.admin import router as admin_router
    from domains.admin.schemas import UpdateGrantedPermissionsRequest

    target_doc = {
        "id": "user-x", "tenant_id": "tenant-B",
        "granted_permissions": [],
    }
    mock_db = _mock_db_with_user(target_doc)
    sa = _make_user(role=UserRole.SUPER_ADMIN, tenant_id="tenant-A")

    payload = UpdateGrantedPermissionsRequest(permissions=["send_urgent_message"])
    with patch.object(admin_router, "db", mock_db), \
         patch("core.audit.db", mock_db, create=True):
        result = await admin_router.update_user_granted_permissions(
            user_id="user-x", payload=payload, current_user=sa,
        )
    assert result["success"] is True
    mock_db.users.update_one.assert_awaited_once()
