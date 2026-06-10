"""Regression: the apm_middleware rate limiter must NOT throttle static SPA
asset serving — only the dynamic API surface (/api, /graphql, /ws).

Production incident (2026-06-10): the published login appeared broken with
HTTP 429 {"detail":"Rate limit exceeded","limit":60,...}. Deployment logs
showed POST /api/auth/login returned 200, but the SPA's code-split static
chunks (GET /js/*.js) were 429-ing mid-load: a single page load fetches
dozens of /js chunks, all anonymous (no Authorization header), all counted
against the anonymous 60/min bucket — exhausting it so the SPA could never
finish booting. Fix: static SPA serving bypasses the limiter; /api throttling
(auth 15/min, anonymous 60/min, ...) is unchanged.
"""
import asyncio
import importlib

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

    async def _dummy_app(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    return apm_middleware.EnhancedRateLimitMiddleware(app=_dummy_app)


def _call(rl, path, method="GET", ip="9.9.9.9"):
    """Drive one request through the middleware; return the response status."""
    captured = {}

    async def _send(msg):
        if msg["type"] == "http.response.start":
            captured["status"] = msg["status"]

    async def _receive():
        return {}

    scope = {
        "type": "http",
        "path": path,
        "method": method,
        "headers": [(b"x-forwarded-for", ip.encode())],
        "client": (ip, 0),
    }
    asyncio.run(rl(scope, _receive, _send))
    return captured["status"]


def test_static_js_chunks_never_throttled(monkeypatch):
    """A code-split page load (>60 /js chunks) must all pass — zero 429s."""
    rl = _fresh_limiter(monkeypatch, {"REPLIT_DEPLOYMENT": "1"})
    statuses = [_call(rl, f"/js/chunk-{i}.js") for i in range(120)]
    assert set(statuses) == {200}, "static /js chunks must never be rate-limited"


def test_static_asset_prefixes_bypass(monkeypatch):
    """All non-API static surfaces (assets/logos/landing/root/favicon) bypass."""
    rl = _fresh_limiter(monkeypatch, {"REPLIT_DEPLOYMENT": "1"})
    for path in (
        "/assets/index-abc.css",
        "/logos/brand.svg",
        "/landing/hero.png",
        "/favicon.ico",
        "/manifest.json",
    ):
        statuses = [_call(rl, path) for _ in range(100)]
        assert set(statuses) == {200}, f"{path} must bypass rate limiting"


def test_api_auth_login_still_throttled(monkeypatch):
    """The /api auth surface MUST stay throttled (15/min) — no weakening."""
    rl = _fresh_limiter(monkeypatch, {"REPLIT_DEPLOYMENT": "1"})
    assert rl.limits["auth"] == (15, 60)
    statuses = [_call(rl, "/api/auth/login", method="POST") for _ in range(40)]
    assert 429 in statuses, "login brute-force must still trip the auth limiter"
    first_429 = next(i for i, s in enumerate(statuses) if s == 429)
    assert first_429 == 15, f"auth limit should trip on the 16th attempt, got {first_429}"


def test_api_anonymous_still_throttled(monkeypatch):
    """A non-whitelisted anonymous /api path keeps the 60/min anon bucket."""
    rl = _fresh_limiter(monkeypatch, {"REPLIT_DEPLOYMENT": "1"})
    assert rl.limits["anonymous"] == (60, 60)
    statuses = [_call(rl, "/api/public/some-endpoint") for _ in range(100)]
    assert 429 in statuses, "anonymous /api DoS surface must still be throttled"
