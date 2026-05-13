"""
Kill-switch / feature flag standard helper.

Production Safety #6 — pilot operator needs a single, auditable,
fail-closed way to read environment-driven kill-switches.

Why a helper instead of ad-hoc os.environ calls?
- Inconsistent parsing across the codebase (`"1"` vs `"1"/"true"/"yes"/"on"`,
  case-sensitivity, whitespace handling) led to silently-different behaviour
  for the same env-var name across modules.
- No single place to snapshot active kill-switches for the readiness API or
  admin UI.
- Kill-switches that bypass production safety (e.g. DISABLE_AUTH_THROTTLE)
  must be ignored in production unless explicitly opted-in. That guard was
  open-coded in only one place (auth_throttle.py) — easy to forget.

Naming conventions (registry: docs/KILL_SWITCH_REGISTRY.md)
- `ENABLE_*` — opt-in, default off, fail-closed (e.g. ENABLE_QUICKID_DEMO).
- `DISABLE_*` — opt-out, default on, requires production_guard for security
  features (e.g. DISABLE_AUTH_THROTTLE only honoured in dev/test).

This module never raises on bad input. Bad/missing values resolve to the
caller-provided default. Logging is at INFO when a flag flips a behaviour
from its default (read once at module import, not per-call) — never includes
secret values, only flag names + boolean state.
"""

from __future__ import annotations

import logging
import os
from typing import Iterable

logger = logging.getLogger(__name__)

# Truthy tokens accepted across the codebase. Lowercased + stripped on read.
# Order intentional: "1" first because it's the most common in our codebase.
_TRUTHY = frozenset({"1", "true", "yes", "on", "y", "t"})
_FALSY = frozenset({"0", "false", "no", "off", "n", "f", ""})

# Environments where DISABLE_* security guards may be honoured. Anything
# outside this set is treated as production for the purposes of the guard.
_NON_PROD_ENVS = frozenset({
    "development", "dev", "test", "testing", "local", "ci", "sandbox",
})


def _read_raw(flag: str) -> str | None:
    """Return raw env value (lowercased, stripped) or None if unset/empty."""
    raw = os.environ.get(flag)
    if raw is None:
        return None
    raw = raw.strip().lower()
    return raw or None


def is_enabled(flag: str, default: bool = False) -> bool:
    """
    Read an `ENABLE_*` flag. Default OFF (fail-closed).

    Returns True only when the env-var is explicitly set to a truthy token.
    Bad/missing values fall through to `default`.
    """
    raw = _read_raw(flag)
    if raw is None:
        return default
    if raw in _TRUTHY:
        return True
    if raw in _FALSY:
        return False
    # Unknown token — log once and fall back to default to avoid silent
    # behaviour drift from typos like "yse" or "trrue".
    logger.warning(
        "feature_flags: unknown value for %s, falling back to default=%s",
        flag, default,
    )
    return default


def is_disabled(flag: str, default: bool = False) -> bool:
    """
    Read a `DISABLE_*` flag. Default OFF (i.e. feature stays enabled).

    Returns True only when the env-var is explicitly set to a truthy token.
    Bad/missing values fall through to `default`.
    """
    return is_enabled(flag, default=default)


def production_guard(
    flag: str,
    *,
    allowed_envs: Iterable[str] | None = None,
) -> bool:
    """
    Read a `DISABLE_*` flag that bypasses a security/safety control.

    Returns True (the security guard MAY be skipped) ONLY when:
      1. the env-var is truthy, AND
      2. the current runtime is in `allowed_envs` (default: dev/test/local/ci/sandbox).

    Use for switches that, if leaked into production, would weaken security:
    DISABLE_AUTH_THROTTLE, DISABLE_TENANT_GUARD, DISABLE_RATE_LIMIT, etc.

    Production leakage is silently ignored — the guard stays active. A WARNING
    is logged so operators see the leak in Sentry / log search.
    """
    if not is_disabled(flag):
        return False

    allowed = frozenset(
        e.lower() for e in (allowed_envs or _NON_PROD_ENVS)
    )
    env = (
        os.environ.get("APP_ENV")
        or os.environ.get("ENVIRONMENT")
        or "development"
    ).strip().lower()

    if env in allowed:
        return True

    logger.warning(
        "feature_flags: %s is set but ignored — current env=%s is not in "
        "allowed_envs=%s. Security guard remains active.",
        flag, env, sorted(allowed),
    )
    return False


# ---------------------------------------------------------------------------
# Snapshot — for readiness API / admin "Sistem Sağlığı" / cron tools.
# Returns ONLY flag names + boolean state. Never includes raw env values
# (some env-vars unrelated to flags may share names with secrets).
# ---------------------------------------------------------------------------

# Registry of known kill-switches. Mirrors docs/KILL_SWITCH_REGISTRY.md.
# Add new flags here when wiring them; keep doc + code in lock-step.
KNOWN_FLAGS: tuple[tuple[str, str, bool], ...] = (
    # (flag_name, kind, default_value_when_unset)
    # kind: "enable" (opt-in) | "disable" (opt-out) | "guard" (prod-guarded disable)
    ("ENABLE_QUICKID_DEMO", "enable", False),
    ("ENABLE_SETUP_ENDPOINTS", "enable", False),
    ("ENABLE_LEGACY_SECRET_FALLBACK", "enable", True),
    ("DISABLE_EXPO_PUSH", "disable", False),
    ("DISABLE_AUTH_THROTTLE", "guard", False),
)


def snapshot() -> dict:
    """
    Return a privacy-safe snapshot of all known kill-switches.

    Shape:
      {
        "flags": [
          {"name": "ENABLE_QUICKID_DEMO", "kind": "enable", "active": false, "default": false},
          ...
        ],
        "active_count": 0,
        "non_default_count": 0,
      }

    Used by:
    - `/api/production-golive/readiness` (future: kill_switches check)
    - `frontend/src/pages/SystemHealthDashboard.jsx` admin panel
    - cron audit scripts

    Privacy: never returns raw env values. Only flag names (already public,
    documented in registry) + boolean state.
    """
    flags = []
    active = 0
    non_default = 0
    for name, kind, default in KNOWN_FLAGS:
        if kind == "guard":
            state = production_guard(name)
            raw_state = is_disabled(name)
        elif kind == "disable":
            state = is_disabled(name, default=default)
            raw_state = state
        else:  # "enable"
            state = is_enabled(name, default=default)
            raw_state = state
        flags.append({
            "name": name,
            "kind": kind,
            "active": state,
            "default": default,
            # `requested` differs from `active` only for prod-guarded flags
            # that were set but ignored — operators see the leak.
            "requested": raw_state,
        })
        if state:
            active += 1
        if state != default:
            non_default += 1
    return {
        "flags": flags,
        "active_count": active,
        "non_default_count": non_default,
    }
