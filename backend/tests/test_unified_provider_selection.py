"""
Unified Rate Manager — Per-Tenant Provider Selection (fail-closed)
==================================================================
Targeted unit tests for `_detect_active_provider` covering the new
super_admin-selected per-hotel channel-manager provider behaviour.

Scenarios:
- null-single        : no configured provider, single active connection -> auto-detect
- null-both          : no configured provider, both connections -> fail closed
- configured-present : configured provider present -> ONLY that provider (beats default)
- configured-missing : configured provider's connection absent -> FAIL-CLOSED (no fallback)
- configured-auth    : super_admin selection is AUTHORITATIVE; client prefer= cannot
                       override it (conflicting prefer -> FAIL-CLOSED), while a matching
                       prefer is honoured.
- unconfigured-prefer: client input cannot choose between two active providers.

The module-level Motor `db` is replaced with an in-memory async double so the
function logic is exercised without a live MongoDB.
"""

import asyncio
import types
from unittest.mock import AsyncMock

import pytest

TENANT = "t-test-1"


def _fake_db(*, configured=None, hr=False, exely=False, pc=None):
    """Build an in-memory async db double for the collections the detector touches."""
    db = types.SimpleNamespace()
    db.tenants = types.SimpleNamespace(find_one=AsyncMock(return_value=({"channel_manager_provider": configured} if configured is not None else {})))
    hr_doc = {"tenant_id": TENANT, "is_active": True, "cached_rooms": [1, 2]} if hr else None
    db.hotelrunner_connections = types.SimpleNamespace(find_one=AsyncMock(return_value=hr_doc))
    db.provider_connections = types.SimpleNamespace(find_one=AsyncMock(return_value=pc))
    exely_doc = {"tenant_id": TENANT, "is_active": True, "room_types": [1]} if exely else None
    db.exely_connections = types.SimpleNamespace(find_one=AsyncMock(return_value=exely_doc))
    return db


def _detect(db, **kwargs):
    """Run the async detector against a fake db, restoring the global afterwards."""
    import services.cm_provider as cm_provider

    original = cm_provider.db
    cm_provider.db = db
    try:
        return asyncio.run(cm_provider._detect_active_provider(TENANT, **kwargs))
    finally:
        cm_provider.db = original


def test_null_single_autodetect_exely():
    """No configured provider + only Exely active -> auto-detect picks exely."""
    res = _detect(_fake_db(configured=None, hr=False, exely=True))
    assert res["provider"] == "exely"
    assert res["connection"] is not None


def test_null_both_fails_closed_until_superadmin_selects_provider():
    """No configured provider + both active -> client cannot choose the route."""
    res = _detect(_fake_db(configured=None, hr=True, exely=True))
    assert res["provider"] is None
    assert res["connection"] is None
    assert res["configuration_error"] == "multiple_active_providers"


def test_configured_exely_present_beats_default_priority():
    """Configured=exely + both active -> ONLY exely (overrides HR default order)."""
    res = _detect(_fake_db(configured="exely", hr=True, exely=True))
    assert res["provider"] == "exely"
    assert res["connection"] is not None


def test_configured_exely_missing_is_fail_closed():
    """Configured=exely but exely connection absent -> fail-closed, NO HR fallback."""
    res = _detect(_fake_db(configured="exely", hr=True, exely=False))
    assert res["provider"] is None
    assert res["connection"] is None
    assert res["configured_provider"] == "exely"
    assert res["configuration_error"] == "connection_missing"


def test_configured_hotelrunner_missing_is_fail_closed():
    """Configured=hotelrunner but HR connection absent -> fail-closed, NO exely fallback."""
    res = _detect(_fake_db(configured="hotelrunner", hr=False, exely=True))
    assert res["provider"] is None
    assert res["connection"] is None
    assert res["configured_provider"] == "hotelrunner"
    assert res["configuration_error"] == "connection_missing"


def test_configured_provider_is_authoritative_over_matching_prefer():
    """Configured=exely + client prefer=exely -> exely (selection honoured)."""
    res = _detect(_fake_db(configured="exely", hr=True, exely=True), prefer="exely")
    assert res["provider"] == "exely"
    assert res["connection"] is not None


def test_configured_provider_overrides_conflicting_prefer_fail_closed():
    """Configured=exely + client prefer=hotelrunner -> FAIL-CLOSED (client cannot override)."""
    res = _detect(_fake_db(configured="exely", hr=True, exely=True), prefer="hotelrunner")
    assert res["provider"] is None
    assert res["connection"] is None
    assert res["configured_provider"] == "exely"
    assert res["configuration_error"] == "provider_not_selected"


def test_unconfigured_prefer_cannot_select_between_two_active_providers():
    """No configured provider + both active remains fail-closed despite client input."""
    res = _detect(_fake_db(configured=None, hr=True, exely=True), prefer="exely")
    assert res["provider"] is None
    assert res["connection"] is None
    assert res["configuration_error"] == "multiple_active_providers"


def test_no_connections_returns_none():
    """No configured provider and no active connections -> provider None (unchanged)."""
    res = _detect(_fake_db(configured=None, hr=False, exely=False))
    assert res["provider"] is None
    assert res["connection"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
