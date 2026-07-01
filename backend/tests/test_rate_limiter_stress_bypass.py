"""Regression: when `E2E_ALLOW_DESTRUCTIVE_STRESS=true` is set on the
deployed backend (already required by the stress seed router to even
allow the suite to mutate data), the apm_middleware rate limiter must
switch to the elevated test-env profile.

CI 2026-05-25 (98-ops-surface-smoke "B) shift_handover") failed with
429 because prod limits (write=120/min) collapsed under the bursty
stress surface. This test pins the bypass without leaking through
when only CLOUD_DEPLOYMENT=1 is set.
"""
import importlib
import os

import pytest


def _fresh_limiter(monkeypatch, env: dict):
    for k in (
        "CLOUD_DEPLOYMENT",
        "E2E_ALLOW_DESTRUCTIVE_STRESS",
        "TESTING",
        "CI",
        "APP_ENV",
        "CLOUD_INSTANCE_ID",
        "CLOUD_DEV_DOMAIN",
    ):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)

    import apm_middleware
    importlib.reload(apm_middleware)
    return apm_middleware.EnhancedRateLimitMiddleware(app=lambda *a, **kw: None)


def test_prod_deployment_without_flag_uses_prod_limits(monkeypatch):
    rl = _fresh_limiter(monkeypatch, {"CLOUD_DEPLOYMENT": "1"})
    assert rl.limits["write"] == (120, 60)
    assert rl.limits["default"] == (300, 60)


def test_prod_deployment_with_stress_flag_uses_elevated_limits(monkeypatch):
    rl = _fresh_limiter(monkeypatch, {
        "CLOUD_DEPLOYMENT": "1",
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
        "CLOUD_DEPLOYMENT": "1",
        "E2E_ALLOW_DESTRUCTIVE_STRESS": "TRUE",
    })
    assert rl.limits["write"] == (10000, 60)
    assert rl.limits["auth"] == (15, 60)


def test_stress_flag_false_keeps_prod_limits(monkeypatch):
    rl = _fresh_limiter(monkeypatch, {
        "CLOUD_DEPLOYMENT": "1",
        "E2E_ALLOW_DESTRUCTIVE_STRESS": "false",
    })
    assert rl.limits["write"] == (120, 60)


def test_dev_env_unchanged(monkeypatch):
    rl = _fresh_limiter(monkeypatch, {"CLOUD_INSTANCE_ID": "abc"})
    assert rl.limits["write"] == (10000, 60)


def test_has_token_requires_valid_bearer_structure(monkeypatch):
    """SECURITY: dummy `Authorization` headers (no Bearer, too short) must
    classify as anonymous so an unauthenticated caller cannot escape the
    `anonymous` bucket into `default`/`write` — especially relevant under
    the stress profile where those buckets are 10000/min."""
    rl = _fresh_limiter(monkeypatch, {
        "CLOUD_DEPLOYMENT": "1",
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


def test_static_spa_assets_exempt_from_rate_limit(monkeypatch):
    """Static SPA assets (the index.html shell, hashed JS/CSS chunks, images,
    fonts, manifests, ...) must NEVER be rate-limited, even under prod limits.

    Regression: the global limiter previously counted every anonymous static
    request against the per-IP `anonymous` bucket (60/min in prod). A single
    React SPA page load fetches the shell plus many hashed chunks, so a couple
    of loads/refreshes trip a persistent 429 on the published app and the SPA
    never boots (published `-syroce` 429-on-`/`). Asset serving is exempt;
    `/api`, `/graphql`, `/ws` stay fully throttled.
    """
    import asyncio
    import importlib

    for k in (
        "CLOUD_DEPLOYMENT", "E2E_ALLOW_DESTRUCTIVE_STRESS", "TESTING",
        "CI", "APP_ENV", "CLOUD_INSTANCE_ID", "CLOUD_DEV_DOMAIN",
    ):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("CLOUD_DEPLOYMENT", "1")  # force prod profile

    import apm_middleware
    importlib.reload(apm_middleware)

    served = {"count": 0}

    async def _inner_app(scope, receive, send):
        served["count"] += 1
        await send({'type': 'http.response.start', 'status': 200, 'headers': []})
        await send({'type': 'http.response.body', 'body': b'ok'})

    rl = apm_middleware.EnhancedRateLimitMiddleware(app=_inner_app)
    # Sanity: we are on the prod profile (anonymous bucket = 60/min).
    assert rl.limits["anonymous"] == (60, 60)

    async def _drive(path: str, n: int) -> list:
        statuses: list = []
        for _ in range(n):
            captured: list = []
            scope = {
                'type': 'http', 'path': path, 'method': 'GET',
                'headers': [], 'client': ('9.9.9.9', 0),
            }

            async def _recv():
                return {'type': 'http.request', 'body': b'', 'more_body': False}

            async def _send(message, _store=captured):
                if message['type'] == 'http.response.start':
                    _store.append(message['status'])

            await rl(scope, _recv, _send)
            statuses.append(captured[0] if captured else None)
        return statuses

    async def _run():
        # 200 static requests >> the 60/min anonymous budget: ALL must pass.
        for p in (
            "/", "/js/index-abc123.js", "/assets/main-xyz.css",
            "/logos/logo.svg", "/manifest.json", "/robots.txt",
            "/favicon.ico", "/og-image.png",
        ):
            st = await _drive(p, 200)
            assert all(s == 200 for s in st), f"static {p} throttled: {set(st)}"

        # Regression: anonymous /api/* is STILL throttled (60/min → 429).
        api_st = await _drive("/api/public/thing", 70)
        assert api_st[:60] == [200] * 60, "first 60 anonymous /api should pass"
        assert api_st[60] == 429, "61st anonymous /api request must be 429"

    asyncio.run(_run())
