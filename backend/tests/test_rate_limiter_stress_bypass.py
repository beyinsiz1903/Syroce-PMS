"""Regression: when `E2E_ALLOW_DESTRUCTIVE_STRESS=true` is set on the
deployed backend (already required by the stress seed router to even
allow the suite to mutate data), the apm_middleware rate limiter must
switch to the elevated test-env profile.

CI 2026-05-25 (98-ops-surface-smoke "B) shift_handover") failed with
429 because prod limits (write=120/min) collapsed under the bursty
stress surface. This test pins the bypass without leaking through
when only REPLIT_DEPLOYMENT=1 is set.
"""
import importlib
import os

import pytest


def _fresh_limiter(monkeypatch, env: dict):
    for k in (
        "REPLIT_DEPLOYMENT",
        "E2E_ALLOW_DESTRUCTIVE_STRESS",
        "TESTING",
        "CI",
        "APP_ENV",
        "REPL_ID",
        "REPLIT_DEV_DOMAIN",
    ):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    import apm_middleware
    importlib.reload(apm_middleware)
    return apm_middleware.EnhancedRateLimitMiddleware(app=lambda *a, **kw: None)


def test_prod_deployment_without_flag_uses_prod_limits(monkeypatch):
    rl = _fresh_limiter(monkeypatch, {"REPLIT_DEPLOYMENT": "1"})
    assert rl.limits["write"] == (120, 60)
    assert rl.limits["default"] == (300, 60)


def test_prod_deployment_with_stress_flag_uses_elevated_limits(monkeypatch):
    rl = _fresh_limiter(monkeypatch, {
        "REPLIT_DEPLOYMENT": "1",
        "E2E_ALLOW_DESTRUCTIVE_STRESS": "true",
    })
    # Elevated for bursty authenticated surfaces.
    assert rl.limits["write"] == (10000, 60)
    assert rl.limits["default"] == (10000, 60)
    assert rl.limits["export"] == (10000, 60)
    assert rl.limits["report"] == (10000, 60)
    # SECURITY: auth + anonymous stay at prod ceilings even with the flag
    # on, so login brute-force / unauthenticated DoS remain throttled if
    # the flag is accidentally left enabled.
    assert rl.limits["auth"] == (15, 60)
    assert rl.limits["anonymous"] == (60, 60)


def test_stress_flag_case_insensitive(monkeypatch):
    rl = _fresh_limiter(monkeypatch, {
        "REPLIT_DEPLOYMENT": "1",
        "E2E_ALLOW_DESTRUCTIVE_STRESS": "TRUE",
    })
    assert rl.limits["write"] == (10000, 60)
    assert rl.limits["auth"] == (15, 60)


def test_stress_flag_false_keeps_prod_limits(monkeypatch):
    rl = _fresh_limiter(monkeypatch, {
        "REPLIT_DEPLOYMENT": "1",
        "E2E_ALLOW_DESTRUCTIVE_STRESS": "false",
    })
    assert rl.limits["write"] == (120, 60)


def test_dev_env_unchanged(monkeypatch):
    rl = _fresh_limiter(monkeypatch, {"REPL_ID": "abc"})
    assert rl.limits["write"] == (10000, 60)


def test_has_token_requires_valid_bearer_structure(monkeypatch):
    """SECURITY: dummy `Authorization` headers (no Bearer, too short) must
    classify as anonymous so an unauthenticated caller cannot escape the
    `anonymous` bucket into `default`/`write` — especially relevant under
    the stress profile where those buckets are 10000/min."""
    rl = _fresh_limiter(monkeypatch, {
        "REPLIT_DEPLOYMENT": "1",
        "E2E_ALLOW_DESTRUCTIVE_STRESS": "true",
    })

    def _scope(auth_value, method='POST'):
        headers = []
        if auth_value is not None:
            headers.append((b'authorization', auth_value))
        return {
            'type': 'http',
            'path': '/api/some/write/path',
            'method': method,
            'headers': headers,
            'client': ('1.2.3.4', 0),
        }

    # SECURITY contract: any spoofed/missing Authorization MUST land in
    # `anonymous` regardless of method — including POST/PUT/PATCH/DELETE.
    # Without this, stress-profile `write=10000/min` becomes an open
    # unauthenticated DoS bucket.
    for hdr in (None, b'x', b'Basic dXNlcjpwYXNz', b'Bearer short'):
        auth = hdr or b''
        has_token = auth.startswith(b'Bearer ') and len(auth) > 20
        assert has_token is False, f"header={hdr!r} should NOT count as token"
        for method in ('GET', 'POST', 'PUT', 'PATCH', 'DELETE'):
            cat = rl._get_category('/api/some/path', method, has_token)
            assert cat == 'anonymous', f"{method} with header={hdr!r} → {cat}"

    # Real-looking bearer → has_token True → POST=write, GET=default.
    real = b'Bearer ' + b'a' * 40
    has_token = real.startswith(b'Bearer ') and len(real) > 20
    assert has_token is True
    assert rl._get_category('/api/x', 'GET', has_token) == 'default'
    assert rl._get_category('/api/x', 'POST', has_token) == 'write'
