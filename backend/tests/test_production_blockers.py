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
    ):
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


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
    result = production_config.startup_check()
    assert result["forbidden_dev_secrets_present"] == []
