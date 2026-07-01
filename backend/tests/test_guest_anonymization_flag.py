"""F8 § 66 (Wave 3) — KVKK/GDPR guest anonymization feature-flag gate.

The anonymize route is destructive (irreversible PII scrub), so it is gated
fail-closed behind ENABLE_GUEST_ANONYMIZATION. These tests lock the flag
semantics and route registration without touching the database.
"""

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from core.helpers import require_super_admin_guard
from domains.admin.router.compliance import (
    _GUEST_PII_FIELDS,
    guest_anonymization_enabled,
    router as compliance_router,
)


def _paths():
    return {r.path for r in compliance_router.routes}


def _anonymize_route():
    for r in compliance_router.routes:
        if getattr(r, "path", "") == "/api/gdpr/guests/{guest_id}/anonymize":
            return r
    return None


def test_flag_default_disabled(monkeypatch):
    monkeypatch.delenv("ENABLE_GUEST_ANONYMIZATION", raising=False)
    assert guest_anonymization_enabled() is False


def test_flag_explicit_off(monkeypatch):
    monkeypatch.setenv("ENABLE_GUEST_ANONYMIZATION", "false")
    assert guest_anonymization_enabled() is False


def test_flag_explicit_on(monkeypatch):
    for v in ("1", "true", "yes", "on"):
        monkeypatch.setenv("ENABLE_GUEST_ANONYMIZATION", v)
        assert guest_anonymization_enabled() is True


def test_route_registered():
    assert "/api/gdpr/guests/{guest_id}/anonymize" in _paths()


def test_pii_field_set_covers_core_identifiers():
    for f in ("full_name", "email", "phone", "passport_number", "id_number"):
        assert f in _GUEST_PII_FIELDS


# --- authz: super-admin guard must be a CALLED dependency, not the factory ---

@pytest.mark.asyncio
async def test_super_admin_guard_denies_non_super_admin():
    guard = require_super_admin_guard(not_found=False)
    non_admin = SimpleNamespace(role="staff", roles=["staff"], id="u1")
    with pytest.raises(HTTPException) as ei:
        await guard(current_user=non_admin)
    assert ei.value.status_code == 403


@pytest.mark.asyncio
async def test_super_admin_guard_allows_super_admin():
    guard = require_super_admin_guard(not_found=False)
    admin = SimpleNamespace(role="super_admin", roles=["super_admin"], id="u2")
    result = await guard(current_user=admin)
    assert result is admin


def test_anonymize_route_wires_called_guard_dependency():
    # Regression: route must depend on the guard returned by the factory,
    # not the factory object itself (otherwise every authenticated user passes).
    route = _anonymize_route()
    assert route is not None
    sub_dep_names = []
    for d in route.dependant.dependencies:
        for sub in d.dependencies:
            sub_dep_names.append(getattr(sub.call, "__name__", str(sub.call)))
    # require_super_admin_guard() returns an inner coroutine named `_guard`.
    assert "_guard" in [getattr(d.call, "__name__", "") for d in route.dependant.dependencies] \
        or "_guard" in sub_dep_names
