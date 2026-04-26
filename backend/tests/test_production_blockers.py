"""Regression tests for v109 round-8 production fail-closed blockers.

Verifies that ``infra.production_config.startup_check()``:

  1. Raises ``RuntimeError`` in production when an env var matches one of
     the forbidden dev-secret SHA-256 fingerprints.
  2. Raises ``RuntimeError`` in production when ``STRICT_TENANT_MODE`` is
     not ``true``.
  3. Treats **any** of ``APP_ENV``/``ENVIRONMENT``/``NODE_ENV`` =
     ``production`` as production (unified detection — addresses the
     5th-pass review finding that mismatched env-var keys could bypass
     the fail-closed logic).
  4. Returns ``status='pass'`` in development (no production env) — local
     dev is unaffected even if a forbidden value is present.

To avoid embedding actual leaked secret values in the repository (which
would trigger secret-scanning and create compliance friction), this test
monkey-patches ``FORBIDDEN_DEV_HASHES`` with a synthetic sentinel hash
and exercises the blocker behavior with that. The real hash list lives
in ``infra/production_config.py`` and is verified by the live boot path.
"""
from __future__ import annotations

import hashlib

import pytest

from infra import production_config as pc_mod
from infra.production_config import is_production_env, production_config


SENTINEL_VALUE = "synthetic-test-only-not-a-real-secret-2026"
SENTINEL_HASH = hashlib.sha256(SENTINEL_VALUE.encode()).hexdigest()
SENTINEL_VAR = "JWT_SECRET"  # any var name in PRODUCTION_VARIABLES is fine


@pytest.fixture
def clean_env(monkeypatch):
    """Strip env keys that influence startup_check.

    Includes all 5 forbidden-fingerprinted vars so the test process is
    isolated from whatever the dev environment has loaded from `.replit`.
    """
    for k in (
        "APP_ENV",
        "NODE_ENV",
        "ENVIRONMENT",
        "STRICT_TENANT_MODE",
        # All 5 vars whose dev-leaked values are fingerprinted in
        # production_config.startup_check — must be cleared so the test
        # has a clean baseline.
        "JWT_SECRET",
        "QUICKID_SERVICE_KEY",
        "AFSADAKAT_ADMIN_TOKEN",
        "CM_MASTER_KEY_CURRENT",
        "HR_TOKEN",
        # Task #33: VAPID gate is also exercised by startup_check; clear
        # the env so each test opts in to the values it wants to assert
        # on. Tests that drive other gates (tenant/forbidden) set both
        # VAPID vars to a sentinel so the VAPID gate does not interfere.
        "VAPID_PUBLIC_KEY",
        "VAPID_PRIVATE_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


def _set_vapid(env, value: str = "test-only") -> None:
    """Helper: set both VAPID env vars so the VAPID gate is satisfied.

    Used by tests that target *other* startup_check gates and need a clean
    baseline where the VAPID check passes.
    """
    env.setenv("VAPID_PUBLIC_KEY", value)
    env.setenv("VAPID_PRIVATE_KEY", value)


# ─── Production-mode detection (unified APP_ENV/ENVIRONMENT/NODE_ENV) ───────

@pytest.mark.parametrize("env_key", ["APP_ENV", "ENVIRONMENT", "NODE_ENV"])
def test_is_production_env_detects_each_key(clean_env, env_key):
    assert is_production_env() is False
    clean_env.setenv(env_key, "production")
    assert is_production_env() is True


def test_is_production_env_case_insensitive(clean_env):
    clean_env.setenv("APP_ENV", "Production")
    assert is_production_env() is True


def test_is_production_env_false_for_dev_values(clean_env):
    for v in ("development", "staging", "test", ""):
        clean_env.setenv("APP_ENV", v)
        assert is_production_env() is False, f"APP_ENV={v!r} should not be production"


# ─── STRICT_TENANT_MODE blocker (works under any production env key) ────────

@pytest.mark.parametrize("env_key", ["APP_ENV", "ENVIRONMENT", "NODE_ENV"])
def test_production_requires_strict_tenant_mode(clean_env, env_key):
    """Setting ANY of the 3 env keys to production triggers the tenant guard."""
    clean_env.setenv(env_key, "production")
    _set_vapid(clean_env)  # isolate: only the tenant gate should fire
    # STRICT_TENANT_MODE intentionally unset
    with pytest.raises(RuntimeError) as exc:
        production_config.startup_check()
    assert "STRICT_TENANT_MODE" in str(exc.value)


# ─── Forbidden-secret blocker (sentinel-hash variant, no real secrets) ──────

def test_production_refuses_boot_with_forbidden_secret(clean_env, monkeypatch):
    """Production + env var matching a forbidden hash ⇒ real startup_check raises.

    Monkey-patches only the module-scope FORBIDDEN_DEV_HASHES table with a
    sentinel entry, then calls the actual ``startup_check()`` so the real
    hash compare + RuntimeError code path is exercised. No real leaked
    secret bytes are referenced anywhere in this test.
    """
    clean_env.setenv("APP_ENV", "production")
    clean_env.setenv("STRICT_TENANT_MODE", "true")
    clean_env.setenv(SENTINEL_VAR, SENTINEL_VALUE)
    _set_vapid(clean_env)  # isolate: only the forbidden-secret gate should fire

    monkeypatch.setattr(
        pc_mod,
        "FORBIDDEN_DEV_HASHES",
        {SENTINEL_VAR: SENTINEL_HASH},
    )

    with pytest.raises(RuntimeError) as exc:
        production_config.startup_check()
    assert SENTINEL_VAR in str(exc.value)


def test_production_pass_when_sentinel_value_does_not_match(clean_env, monkeypatch):
    """Same code path, but env value differs from sentinel ⇒ no RuntimeError.

    Confirms the hash compare is genuinely the gate (not a blanket reject).
    """
    clean_env.setenv("APP_ENV", "production")
    clean_env.setenv("STRICT_TENANT_MODE", "true")
    clean_env.setenv(SENTINEL_VAR, "different-fresh-value-2026")
    _set_vapid(clean_env)

    monkeypatch.setattr(
        pc_mod,
        "FORBIDDEN_DEV_HASHES",
        {SENTINEL_VAR: SENTINEL_HASH},
    )

    result = production_config.startup_check()
    assert result["forbidden_dev_secrets_present"] == []


def test_dev_mode_ignores_forbidden_values(clean_env):
    """No production env ⇒ even a known-bad value does not block boot."""
    # Real fingerprints are checked here; we just assert the gate is OFF
    # and the function returns without raising.
    clean_env.setenv(SENTINEL_VAR, "anything-not-production-still-fine")
    result = production_config.startup_check()
    assert result["forbidden_dev_secrets_present"] == []


def test_production_accepts_rotated_secrets(clean_env):
    """Production with all-fresh values + STRICT_TENANT_MODE=true ⇒ no forbidden hits."""
    clean_env.setenv("APP_ENV", "production")
    clean_env.setenv("STRICT_TENANT_MODE", "true")
    clean_env.setenv(SENTINEL_VAR, "freshly-rotated-2026-not-a-leak")
    _set_vapid(clean_env)
    result = production_config.startup_check()
    assert result["forbidden_dev_secrets_present"] == []
    assert result["vapid_keys_missing"] == []


# ─── Task #33: Web Push VAPID boot-time gate ─────────────────────────────

@pytest.mark.parametrize("env_key", ["APP_ENV", "ENVIRONMENT", "NODE_ENV"])
def test_production_refuses_boot_when_vapid_keys_missing(clean_env, env_key):
    """Production + missing VAPID env vars ⇒ startup_check raises RuntimeError.

    Mirrors `web_push.get_vapid_keys()`'s production fail-hard behaviour but
    surfaces the failure at boot instead of at first push delivery.
    """
    clean_env.setenv(env_key, "production")
    clean_env.setenv("STRICT_TENANT_MODE", "true")
    # VAPID_PUBLIC_KEY / VAPID_PRIVATE_KEY intentionally unset by clean_env

    with pytest.raises(RuntimeError) as exc:
        production_config.startup_check()
    msg = str(exc.value)
    assert "VAPID_PUBLIC_KEY" in msg
    assert "VAPID_PRIVATE_KEY" in msg


def test_production_refuses_boot_when_only_one_vapid_key_set(clean_env):
    """Half-configured VAPID (only public, missing private) still aborts."""
    clean_env.setenv("APP_ENV", "production")
    clean_env.setenv("STRICT_TENANT_MODE", "true")
    clean_env.setenv("VAPID_PUBLIC_KEY", "pub-only")

    with pytest.raises(RuntimeError) as exc:
        production_config.startup_check()
    assert "VAPID_PRIVATE_KEY" in str(exc.value)
    assert "VAPID_PUBLIC_KEY" not in str(exc.value).split("VAPID_PRIVATE_KEY")[0]


def test_production_passes_vapid_gate_when_keys_present(clean_env):
    """Production + both VAPID keys set ⇒ no VAPID violation, no raise.

    We don't assert the overall ``status`` because the test environment
    intentionally omits unrelated critical vars (MONGO_URL, JWT_SECRET,
    CORS_ORIGINS) — those drive ``status='fail'`` via the missing-vars
    branch, which is logged-only and does not raise. The contract for
    this test is specifically the VAPID gate.
    """
    clean_env.setenv("APP_ENV", "production")
    clean_env.setenv("STRICT_TENANT_MODE", "true")
    _set_vapid(clean_env, "real-rotated-key-2026")

    result = production_config.startup_check()
    assert result["vapid_keys_missing"] == []


def test_dev_warns_but_does_not_raise_when_vapid_missing(clean_env, caplog):
    """Non-production: missing VAPID keys log a warning but do not raise.

    The dev fallback in `web_push.get_vapid_keys()` (db-persisted
    auto-generated keypair) must keep working for local development.
    """
    # No APP_ENV / ENVIRONMENT / NODE_ENV set ⇒ dev mode
    import logging as _logging
    with caplog.at_level(_logging.WARNING, logger="infra.production_config"):
        result = production_config.startup_check()
    assert result["vapid_keys_missing"] == ["VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY"]
    # Warning was emitted so a developer notices the missing config.
    assert any("VAPID" in rec.message for rec in caplog.records)


def test_vapid_keys_listed_in_production_variables():
    """Schema check: PRODUCTION_VARIABLES advertises both VAPID keys as critical."""
    from infra.production_config import PRODUCTION_VARIABLES
    for var in ("VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY"):
        assert var in PRODUCTION_VARIABLES, f"{var} missing from PRODUCTION_VARIABLES"
        assert PRODUCTION_VARIABLES[var]["critical"] is True
        assert PRODUCTION_VARIABLES[var]["category"] == "messaging"
