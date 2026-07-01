"""Tests: notifications router target_roles visibility filter (Task #105).

The notifications bell powers a shared, tenant-scoped feed. Manager-only
alarms (e.g. KVKK ID-photo burst alerts produced by
``workers/id_photo_view_alert.py``) attach a ``target_roles`` array;
the router must only surface those notifications to users whose role
matches. Notifications without ``target_roles`` keep the historical
broadcast semantics (visible to every user in the tenant).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from models.enums import UserRole
from models.schemas import User


def _user(role: UserRole) -> User:
    return User(
        id=f"user-{role.value}",
        tenant_id="tenant-1",
        email=f"{role.value}@example.com",
        username=role.value,
        name=role.value.title(),
        role=role,
    )


def test_visibility_filter_default_keeps_broadcast_for_clerks():
    from domains import notifications_router as nr

    clerk = _user(UserRole.FRONT_DESK)
    flt = nr._visibility_filter(clerk)
    assert "$or" in flt
    or_clauses = flt["$or"]

    # Without `target_roles` field → visible (preserves legacy automation broadcasts).
    assert {"target_roles": {"$exists": False}} in or_clauses
    # Empty/null target_roles → visible.
    assert {"target_roles": None} in or_clauses
    assert {"target_roles": {"$size": 0}} in or_clauses
    # Direct role match — clerk only sees notifications targeted at front_desk.
    assert {"target_roles": "front_desk"} in or_clauses


def test_visibility_filter_admin_sees_admin_targeted():
    from domains import notifications_router as nr

    admin = _user(UserRole.ADMIN)
    flt = nr._visibility_filter(admin)
    assert {"target_roles": "admin"} in flt["$or"]


def test_role_value_handles_enum_and_string():
    from domains import notifications_router as nr

    enum_user = _user(UserRole.SUPERVISOR)
    assert nr._role_value(enum_user) == "supervisor"

    # If role is already a string (loaded from DB without enum coercion),
    # the helper must still return a usable value.
    string_user = MagicMock()
    string_user.role = "supervisor"
    assert nr._role_value(string_user) == "supervisor"


@pytest.mark.asyncio
async def test_mark_read_uses_visibility_filter():
    """A clerk hitting `/mark-read` for a manager-only KVKK alert must
    not be able to mutate it: the underlying Mongo query must include
    the visibility filter so the document falls outside the update set.
    """
    from unittest.mock import AsyncMock, patch

    from domains import notifications_router as nr

    clerk = _user(UserRole.FRONT_DESK)

    fake_notifications = MagicMock()
    fake_notifications.update_one = AsyncMock(return_value=MagicMock(modified_count=0))

    fake_db = MagicMock()
    fake_db.notifications = fake_notifications

    with patch.object(nr, "db", fake_db):
        await nr.mark_notification_read("notif-123", current_user=clerk)

    fake_notifications.update_one.assert_awaited_once()
    query = fake_notifications.update_one.await_args.args[0]
    assert query["tenant_id"] == "tenant-1"
    assert query["id"] == "notif-123"
    assert "$or" in query  # visibility filter merged in
    assert {"target_roles": "front_desk"} in query["$or"]
    # Manager-only target roles MUST NOT be in clerk's allowed clauses.
    for role in ["super_admin", "admin", "supervisor"]:
        assert {"target_roles": role} not in query["$or"]


@pytest.mark.asyncio
async def test_mark_all_read_uses_visibility_filter():
    """`/mark-all-read` must scope its bulk update by visibility too,
    so a clerk cannot suppress unread manager-only alerts tenant-wide.
    """
    from unittest.mock import AsyncMock, patch

    from domains import notifications_router as nr

    clerk = _user(UserRole.FRONT_DESK)

    fake_notifications = MagicMock()
    fake_notifications.update_many = AsyncMock(return_value=MagicMock(modified_count=0))

    fake_db = MagicMock()
    fake_db.notifications = fake_notifications

    with patch.object(nr, "db", fake_db):
        await nr.mark_all_notifications_read(current_user=clerk)

    fake_notifications.update_many.assert_awaited_once()
    query = fake_notifications.update_many.await_args.args[0]
    assert query["tenant_id"] == "tenant-1"
    assert query["read"] == {"$ne": True}
    assert "$or" in query
    assert {"target_roles": "front_desk"} in query["$or"]
    for role in ["super_admin", "admin", "supervisor"]:
        assert {"target_roles": role} not in query["$or"]


@pytest.mark.asyncio
async def test_admin_mark_all_read_includes_admin_target_clause():
    """An admin's bulk mark-read query SHOULD include the admin role
    clause, so they can clear KVKK manager-only alerts."""
    from unittest.mock import AsyncMock, patch

    from domains import notifications_router as nr

    admin = _user(UserRole.ADMIN)

    fake_notifications = MagicMock()
    fake_notifications.update_many = AsyncMock(return_value=MagicMock(modified_count=2))

    fake_db = MagicMock()
    fake_db.notifications = fake_notifications

    with patch.object(nr, "db", fake_db):
        await nr.mark_all_notifications_read(current_user=admin)

    query = fake_notifications.update_many.await_args.args[0]
    assert {"target_roles": "admin"} in query["$or"]


@pytest.mark.asyncio
async def test_kvkk_alert_target_roles_excludes_clerks_in_filter():
    """A notification with ``target_roles=["admin","super_admin","supervisor"]``
    (the worker default) should not match the clerk's visibility filter
    on a direct dict comparison test — i.e. the clerk's filter only allows
    the broadcast clauses or `target_roles == "front_desk"`.

    This is a structural assertion: it verifies the router builds the
    filter such that Mongo will exclude the alert document for the clerk.
    """
    from domains import notifications_router as nr
    from workers import id_photo_view_alert as worker

    clerk = _user(UserRole.FRONT_DESK)
    flt = nr._visibility_filter(clerk)
    or_clauses = flt["$or"]

    alert_target_roles = list(worker.DEFAULT_ALERT_ROLES)
    # None of the role-matching clauses in the clerk's filter should
    # match a target_roles list of [super_admin, admin, supervisor].
    assert {"target_roles": "front_desk"} in or_clauses
    for role in alert_target_roles:
        assert {"target_roles": role} not in or_clauses
