from __future__ import annotations

import argparse
from datetime import UTC, datetime

import pytest

from scripts.pre_pilot_reset import (
    MODULE_USER_SPECS,
    CollectionSpec,
    PrePilotSafetyError,
    RESET_COLLECTIONS,
    RESET_CONFIRMATION,
    build_module_user_document,
    build_tenant_filter,
    build_user_delete_filter,
    validate_reset_execution_args,
)


def _reset_args(**overrides):
    values = {
        "execute": False,
        "confirmation": None,
        "expected_database_name": None,
        "expected_super_admin_email": None,
        "backup_reference": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_reset_is_dry_run_without_execution_gates(monkeypatch):
    monkeypatch.delenv("ALLOW_PRE_PILOT_RESET", raising=False)
    validate_reset_execution_args(_reset_args())


def test_execute_requires_environment_gate(monkeypatch):
    monkeypatch.delenv("ALLOW_PRE_PILOT_RESET", raising=False)
    args = _reset_args(
        execute=True,
        confirmation=RESET_CONFIRMATION,
        expected_database_name="hotel_pms",
        expected_super_admin_email="root@example.com",
        backup_reference="backup-123",
    )
    with pytest.raises(PrePilotSafetyError, match="BLOCKED_PRE_PILOT_RESET_ENV_GATE"):
        validate_reset_execution_args(args)


def test_execute_requires_exact_confirmation(monkeypatch):
    monkeypatch.setenv("ALLOW_PRE_PILOT_RESET", "true")
    args = _reset_args(
        execute=True,
        confirmation="close-enough",
        expected_database_name="hotel_pms",
        expected_super_admin_email="root@example.com",
        backup_reference="backup-123",
    )
    with pytest.raises(PrePilotSafetyError, match="BLOCKED_PRE_PILOT_RESET_CONFIRMATION"):
        validate_reset_execution_args(args)


def test_allowlisted_collection_filter_is_always_tenant_scoped():
    spec = RESET_COLLECTIONS[0]
    query = build_tenant_filter(spec, ["tenant-b", "tenant-a", "tenant-a"])
    assert query == {"tenant_id": {"$in": ["tenant-a", "tenant-b"]}}
    assert query != {}


def test_empty_tenant_scope_is_blocked():
    with pytest.raises(PrePilotSafetyError, match="BLOCKED_EMPTY_TENANT_SCOPE"):
        build_tenant_filter(RESET_COLLECTIONS[0], [])


def test_non_allowlisted_collection_is_blocked():
    with pytest.raises(PrePilotSafetyError, match="BLOCKED_COLLECTION_NOT_ALLOWLISTED"):
        build_tenant_filter(CollectionSpec("system_settings"), ["tenant-a"])


def test_user_delete_filter_can_never_match_super_admin():
    scoped = build_user_delete_filter(["tenant-a"], all_non_super_admin_users=False)
    assert scoped == {
        "$and": [
            {"role": {"$ne": "super_admin"}},
            {"tenant_id": {"$in": ["tenant-a"]}},
        ]
    }
    global_non_admin = build_user_delete_filter([], all_non_super_admin_users=True)
    assert global_non_admin == {"role": {"$ne": "super_admin"}}


def test_module_seed_manifest_has_unique_single_scope_accounts():
    slugs = [spec.slug for spec in MODULE_USER_SPECS]
    scopes = [spec.module_scope for spec in MODULE_USER_SPECS]
    assert len(slugs) == len(set(slugs)) == 14
    assert len(scopes) == len(set(scopes)) == 14
    assert all(spec.role != "super_admin" for spec in MODULE_USER_SPECS)


def test_module_user_document_is_restricted_and_requires_password_change():
    spec = next(item for item in MODULE_USER_SPECS if item.slug == "frontdesk")
    now = datetime(2026, 8, 18, tzinfo=UTC)
    document = build_module_user_document(
        tenant_id="tenant-a",
        spec=spec,
        email_domain="qa.example.com",
        password_hash="hashed-secret",
        now=now,
    )

    assert document["role"] == "front_desk"
    assert document["module_scopes"] == ["frontdesk"]
    assert document["password"] == "hashed-secret"
    assert document["must_change_password"] is True
    assert document["is_internal_test_user"] is True
    assert document["tenant_id"] == "tenant-a"
    assert document["email"].endswith("@qa.example.com")
    assert "module:frontdesk" in document["granted_permissions"]
