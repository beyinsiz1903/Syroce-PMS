"""Exely webhook EXELY_TEST_WEBHOOK_AUTH_MODE multi-condition gate.

W6-deferred deliverable. The stress/E2E-only IP-allowlist bypass must be
fail-closed: it activates ONLY when ALL five conditions hold in a NON-prod
environment. Production default stays fail-closed (helper returns False), so
the webhook continues to require EXELY_IP_WHITELIST (503 when unset).

These tests exercise the pure env-gate logic directly (no DB / HTTP needed),
covering: the fully-satisfied active path, each single missing condition, and
explicit production denial even when the test mode is requested.
"""
from domains.channel_manager.providers.exely import exely_webhook_router as ewr

# The complete set of env vars that, together in a non-prod environment, open
# the stress/E2E bypass. Each test starts from this and removes/changes one.
_FULL_OPEN = {
    "EXELY_TEST_WEBHOOK_AUTH_MODE": "open_for_testing",
    "E2E_EXTERNAL_DRY_RUN": "true",
    "E2E_ALLOW_DESTRUCTIVE_STRESS": "true",
    "E2E_STRESS_TENANT_ID": "stress-tenant-123",
}

# Env vars that influence the gate and must be cleared for a clean baseline so
# the host environment cannot leak in and flip a result.
_GATE_VARS = [
    "EXELY_TEST_WEBHOOK_AUTH_MODE",
    "E2E_EXTERNAL_DRY_RUN",
    "E2E_ALLOW_DESTRUCTIVE_STRESS",
    "E2E_STRESS_TENANT_ID",
    "ENVIRONMENT",
    "APP_ENV",
]


def _apply(monkeypatch, env: dict):
    for k in _GATE_VARS:
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def test_all_conditions_met_non_prod_opens(monkeypatch):
    _apply(monkeypatch, _FULL_OPEN)
    assert ewr._exely_test_auth_open() is True


def test_missing_mode_fail_closed(monkeypatch):
    env = dict(_FULL_OPEN)
    del env["EXELY_TEST_WEBHOOK_AUTH_MODE"]
    _apply(monkeypatch, env)
    assert ewr._exely_test_auth_open() is False


def test_wrong_mode_value_fail_closed(monkeypatch):
    env = dict(_FULL_OPEN)
    env["EXELY_TEST_WEBHOOK_AUTH_MODE"] = "open"  # not the exact sentinel
    _apply(monkeypatch, env)
    assert ewr._exely_test_auth_open() is False


def test_missing_dry_run_fail_closed(monkeypatch):
    env = dict(_FULL_OPEN)
    del env["E2E_EXTERNAL_DRY_RUN"]
    _apply(monkeypatch, env)
    assert ewr._exely_test_auth_open() is False


def test_dry_run_not_true_fail_closed(monkeypatch):
    env = dict(_FULL_OPEN)
    env["E2E_EXTERNAL_DRY_RUN"] = "false"
    _apply(monkeypatch, env)
    assert ewr._exely_test_auth_open() is False


def test_missing_destructive_optin_fail_closed(monkeypatch):
    env = dict(_FULL_OPEN)
    del env["E2E_ALLOW_DESTRUCTIVE_STRESS"]
    _apply(monkeypatch, env)
    assert ewr._exely_test_auth_open() is False


def test_destructive_optin_not_true_fail_closed(monkeypatch):
    env = dict(_FULL_OPEN)
    env["E2E_ALLOW_DESTRUCTIVE_STRESS"] = "0"
    _apply(monkeypatch, env)
    assert ewr._exely_test_auth_open() is False


def test_missing_stress_tenant_fail_closed(monkeypatch):
    env = dict(_FULL_OPEN)
    del env["E2E_STRESS_TENANT_ID"]
    _apply(monkeypatch, env)
    assert ewr._exely_test_auth_open() is False


def test_blank_stress_tenant_fail_closed(monkeypatch):
    env = dict(_FULL_OPEN)
    env["E2E_STRESS_TENANT_ID"] = "   "  # whitespace-only is not "set"
    _apply(monkeypatch, env)
    assert ewr._exely_test_auth_open() is False


def test_production_denied_even_with_all_flags(monkeypatch):
    env = dict(_FULL_OPEN)
    env["ENVIRONMENT"] = "production"
    _apply(monkeypatch, env)
    assert ewr._exely_test_auth_open() is False


def test_prod_via_app_env_denied(monkeypatch):
    env = dict(_FULL_OPEN)
    env["APP_ENV"] = "prod"
    _apply(monkeypatch, env)
    assert ewr._exely_test_auth_open() is False


def test_live_env_denied(monkeypatch):
    env = dict(_FULL_OPEN)
    env["ENVIRONMENT"] = "live"
    _apply(monkeypatch, env)
    assert ewr._exely_test_auth_open() is False


def test_clean_env_fail_closed(monkeypatch):
    # No test-mode env at all → production-equivalent default → fail-closed.
    _apply(monkeypatch, {})
    assert ewr._exely_test_auth_open() is False


def test_is_prod_env_detection(monkeypatch):
    for val in ("production", "prod", "live", "PRODUCTION", "Prod"):
        _apply(monkeypatch, {"ENVIRONMENT": val})
        assert ewr._is_prod_env() is True
    for val in ("staging", "stress", "test", "development", ""):
        _apply(monkeypatch, {"ENVIRONMENT": val})
        assert ewr._is_prod_env() is False


# ── Tenant binding under test-auth-open ──────────────────────────────
# When the bypass is active the resolved tenant MUST equal E2E_STRESS_TENANT_ID,
# else the request is rejected — this prevents a HotelCode that maps to another
# (e.g. pilot) tenant in the same non-prod deployment from being processed.

def test_tenant_binding_allows_matching_stress_tenant(monkeypatch):
    _apply(monkeypatch, {"E2E_STRESS_TENANT_ID": "stress-tenant-123"})
    assert ewr._exely_test_tenant_allowed("stress-tenant-123") is True


def test_tenant_binding_rejects_other_tenant(monkeypatch):
    _apply(monkeypatch, {"E2E_STRESS_TENANT_ID": "stress-tenant-123"})
    assert ewr._exely_test_tenant_allowed("pilot-tenant-999") is False


def test_tenant_binding_rejects_empty_resolved_tenant(monkeypatch):
    _apply(monkeypatch, {"E2E_STRESS_TENANT_ID": "stress-tenant-123"})
    assert ewr._exely_test_tenant_allowed("") is False


def test_tenant_binding_fail_closed_when_stress_tenant_unset(monkeypatch):
    _apply(monkeypatch, {})
    # Even if some tenant string is supplied, no stress tenant configured → deny.
    assert ewr._exely_test_tenant_allowed("stress-tenant-123") is False


def test_tenant_binding_fail_closed_blank_stress_tenant(monkeypatch):
    _apply(monkeypatch, {"E2E_STRESS_TENANT_ID": "   "})
    assert ewr._exely_test_tenant_allowed("   ") is False


def test_tenant_binding_trims_whitespace(monkeypatch):
    _apply(monkeypatch, {"E2E_STRESS_TENANT_ID": "  stress-tenant-123  "})
    assert ewr._exely_test_tenant_allowed("stress-tenant-123") is True
