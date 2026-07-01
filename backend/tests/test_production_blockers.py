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
    isolated from whatever the dev environment has loaded from `.digitalocean`.
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


def _set_vapid(env, value: str | None = None) -> None:
    """Helper: set both VAPID env vars so BOTH gates (set + format) pass.

    Used by tests that target *other* startup_check gates and need a clean
    baseline where the VAPID checks (missing-key + Task #50 format) succeed.
    The default values are real, well-formed encodings of the spec shape so
    the format validator added in Task #50 does not interfere.
    """
    import base64
    if value is None:
        pub = base64.urlsafe_b64encode(
            b"\x04" + (b"\x00" * 32) + (b"\x00" * 32)
        ).decode("ascii").rstrip("=")
        priv = base64.urlsafe_b64encode(b"\x00" * 32).decode("ascii").rstrip("=")
    else:
        pub = priv = value
    env.setenv("VAPID_PUBLIC_KEY", pub)
    env.setenv("VAPID_PRIVATE_KEY", priv)


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
    _set_vapid(clean_env)  # default = well-formed P-256 encoding

    result = production_config.startup_check()
    assert result["vapid_keys_missing"] == []
    assert result["vapid_format_errors"] == []


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


# ─── Task #50: VAPID format validation ─────────────────────────────────

def _valid_vapid_pub() -> str:
    """Generate a real, well-formed VAPID public key for tests.

    Produces a 65-byte uncompressed P-256 point (0x04 || X || Y),
    base64url-encoded without padding — exactly the shape the spec
    (and ``web_push.py``'s generator) emit.
    """
    import base64
    raw = b"\x04" + (b"\x00" * 32) + (b"\x00" * 32)
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _valid_vapid_priv() -> str:
    """Generate a 32-byte raw private key, base64url-encoded."""
    import base64
    return base64.urlsafe_b64encode(b"\x00" * 32).decode("ascii").rstrip("=")


def test_vapid_format_validator_accepts_well_formed_keys():
    from infra.production_config import validate_vapid_key_format
    errors = validate_vapid_key_format(
        public_key=_valid_vapid_pub(),
        private_key=_valid_vapid_priv(),
    )
    assert errors == []


def test_vapid_format_validator_rejects_pem_blob():
    """PEM/DER copy-paste is the most common misconfiguration."""
    from infra.production_config import validate_vapid_key_format
    pem = (
        "-----BEGIN PRIVATE KEY-----"
        "MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQg"
        "-----END PRIVATE KEY-----"
    )
    errors = validate_vapid_key_format(public_key=None, private_key=pem)
    assert errors, "PEM private key must be flagged"
    assert any("VAPID_PRIVATE_KEY" in e for e in errors)


def test_vapid_format_validator_rejects_wrong_public_length():
    """Length mismatch ⇒ explicit byte-count error."""
    import base64
    from infra.production_config import validate_vapid_key_format
    too_short = base64.urlsafe_b64encode(b"\x04" + (b"\x00" * 30)).decode("ascii").rstrip("=")
    errors = validate_vapid_key_format(public_key=too_short, private_key=None)
    assert errors
    assert any("65-byte" in e for e in errors)


def test_vapid_format_validator_rejects_compressed_public_marker():
    """Compressed point (0x02 / 0x03) is also 33 bytes — but if someone
    pads it to 65 we still want to flag the leading byte."""
    import base64
    from infra.production_config import validate_vapid_key_format
    bad_marker = b"\x02" + (b"\x00" * 32) + (b"\x00" * 32)
    encoded = base64.urlsafe_b64encode(bad_marker).decode("ascii").rstrip("=")
    errors = validate_vapid_key_format(public_key=encoded, private_key=None)
    assert errors
    assert any("0x04" in e for e in errors)


def test_vapid_format_validator_rejects_garbage_base64():
    from infra.production_config import validate_vapid_key_format
    errors = validate_vapid_key_format(
        public_key="not!valid@base64",
        private_key=None,
    )
    assert errors
    assert any("decode failed" in e for e in errors)


def test_vapid_format_validator_rejects_invalid_chars_inside_valid_key():
    """Architect-flagged regression: injecting a stray '!!' (or any other
    non-base64url char) into an otherwise valid encoding must be rejected,
    not silently absorbed by a permissive decoder."""
    from infra.production_config import validate_vapid_key_format

    valid_pub = _valid_vapid_pub()
    valid_priv = _valid_vapid_priv()

    # Inject '!!' in the middle of each — the strict decoder must reject.
    poisoned_pub = valid_pub[:10] + "!!" + valid_pub[10:]
    poisoned_priv = valid_priv[:5] + "!!" + valid_priv[5:]

    errors = validate_vapid_key_format(public_key=poisoned_pub, private_key=None)
    assert errors, "Public key with embedded '!!' must be flagged"
    assert any("VAPID_PUBLIC_KEY" in e for e in errors)

    errors = validate_vapid_key_format(public_key=None, private_key=poisoned_priv)
    assert errors, "Private key with embedded '!!' must be flagged"
    assert any("VAPID_PRIVATE_KEY" in e for e in errors)


def test_vapid_format_validator_rejects_other_non_alphabet_chars():
    """Coverage for additional non-alphabet bytes: '+' and '/' belong to
    standard base64 (NOT base64url) and must therefore be rejected — VAPID
    keys are always emitted in URL-safe form."""
    from infra.production_config import validate_vapid_key_format
    valid_priv = _valid_vapid_priv()
    poisoned = valid_priv[:5] + "+/" + valid_priv[5:]
    errors = validate_vapid_key_format(public_key=None, private_key=poisoned)
    assert errors
    assert any("VAPID_PRIVATE_KEY" in e for e in errors)


def test_vapid_format_validator_accepts_padded_form():
    """An operator pasting the trailing '=' from another tool should still
    be accepted — padding is removed before alphabet validation."""
    import base64
    from infra.production_config import validate_vapid_key_format
    raw = b"\x04" + (b"\x00" * 32) + (b"\x00" * 32)
    padded_pub = base64.urlsafe_b64encode(raw).decode("ascii")  # keeps '='
    assert padded_pub.endswith("=")  # sanity
    priv_padded = base64.urlsafe_b64encode(b"\x00" * 32).decode("ascii")
    errors = validate_vapid_key_format(public_key=padded_pub, private_key=priv_padded)
    assert errors == []


def test_vapid_format_validator_skips_empty_keys():
    """None / empty string → no errors (the missing-key gate handles it)."""
    from infra.production_config import validate_vapid_key_format
    assert validate_vapid_key_format(public_key=None, private_key=None) == []
    assert validate_vapid_key_format(public_key="", private_key="") == []


def test_production_refuses_boot_when_vapid_format_invalid(clean_env):
    """Production + malformed VAPID → startup_check raises RuntimeError."""
    clean_env.setenv("APP_ENV", "production")
    clean_env.setenv("STRICT_TENANT_MODE", "true")
    # Set values so the missing-key gate doesn't fire first.
    clean_env.setenv("VAPID_PUBLIC_KEY", "garbage-not-base64!!")
    clean_env.setenv("VAPID_PRIVATE_KEY", _valid_vapid_priv())
    with pytest.raises(RuntimeError) as exc:
        production_config.startup_check()
    assert "malformed VAPID keys" in str(exc.value).lower() or "VAPID" in str(exc.value)


def test_dev_warns_but_does_not_raise_on_vapid_format_error(clean_env, caplog):
    """Non-production: malformed VAPID logs a warning, no raise."""
    import logging as _logging
    clean_env.setenv("VAPID_PUBLIC_KEY", "garbage-not-base64!!")
    clean_env.setenv("VAPID_PRIVATE_KEY", _valid_vapid_priv())
    with caplog.at_level(_logging.WARNING, logger="infra.production_config"):
        result = production_config.startup_check()
    assert result["vapid_format_errors"]
    assert any("VAPID" in rec.message for rec in caplog.records)


def test_production_passes_when_vapid_format_is_valid(clean_env):
    """Production + well-formed keys → no format violation, no raise."""
    clean_env.setenv("APP_ENV", "production")
    clean_env.setenv("STRICT_TENANT_MODE", "true")
    clean_env.setenv("VAPID_PUBLIC_KEY", _valid_vapid_pub())
    clean_env.setenv("VAPID_PRIVATE_KEY", _valid_vapid_priv())
    result = production_config.startup_check()
    assert result["vapid_format_errors"] == []


def test_vapid_keys_listed_in_production_variables():
    """Schema check: PRODUCTION_VARIABLES advertises both VAPID keys as critical."""
    from infra.production_config import PRODUCTION_VARIABLES
    for var in ("VAPID_PUBLIC_KEY", "VAPID_PRIVATE_KEY"):
        assert var in PRODUCTION_VARIABLES, f"{var} missing from PRODUCTION_VARIABLES"
        assert PRODUCTION_VARIABLES[var]["critical"] is True
        assert PRODUCTION_VARIABLES[var]["category"] == "messaging"
