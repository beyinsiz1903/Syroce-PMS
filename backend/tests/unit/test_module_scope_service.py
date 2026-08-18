from __future__ import annotations

from modules.pms_core.module_scope_service import (
    effective_module_scopes,
    has_module_scope,
    normalize_module_scope,
)


def test_super_admin_has_every_registered_scope():
    user = {"role": "super_admin", "module_scopes": []}
    assert has_module_scope(user, "frontdesk") is True
    assert has_module_scope(user, "invoice") is True
    assert effective_module_scopes(user) == frozenset({"*"})


def test_explicit_scope_is_authoritative_over_broad_role_defaults():
    user = {"role": "finance", "module_scopes": ["invoice"]}
    assert has_module_scope(user, "invoice") is True
    assert has_module_scope(user, "finance") is False
    assert has_module_scope(user, "cashier") is False
    assert has_module_scope(user, "reports") is False


def test_explicit_empty_scope_list_denies_every_module():
    user = {"role": "admin", "module_scopes": []}
    assert has_module_scope(user, "frontdesk") is False
    assert has_module_scope(user, "finance") is False


def test_legacy_user_without_explicit_scopes_uses_conservative_role_defaults():
    user = {"role": "front_desk"}
    assert has_module_scope(user, "frontdesk") is True
    assert has_module_scope(user, "housekeeping") is False


def test_unknown_or_malformed_stored_scope_fails_closed():
    user = {"role": "staff", "module_scopes": ["invoice", "not-a-real-module", 42]}
    assert has_module_scope(user, "invoice") is True
    assert has_module_scope(user, "finance") is False
    assert has_module_scope(user, "not-a-real-module") is False


def test_scope_normalization_accepts_hyphen_and_wildcard_suffix():
    assert normalize_module_scope("channel-manager.*") == "channel_manager"
