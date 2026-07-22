"""
White-screen static-serving guards — regression
================================================

Background
----------
The combined production deployment runs a SINGLE uvicorn worker that serves
BOTH the API and the static React SPA (``frontend/build``). The recurring
"white screen" was traced to static-asset handling on that shared worker:

1. The per-IP rate limiter counted every SPA shell + hashed JS/CSS chunk
   against the ``anonymous`` budget (60/min in prod). One page load fetches
   the shell plus ~27 hashed chunks, so a couple of loads/refreshes tripped a
   429 on ``/js`` / ``/assets`` and the SPA never booted.
2. Without an explicit ``Cache-Control`` the browser revalidated/refetched
   every hashed chunk on each load, amplifying the request storm into edge
   502s.

These tests pin the two guards down so a future refactor cannot silently
re-open the vector:

* ``apm_middleware.is_static_exempt_path`` correctly classifies static SPA
  assets as exempt while keeping ``/api`` / ``/graphql`` / ``/ws`` throttled,
  and the rate-limit middleware actually passes those requests straight
  through (never emitting its own 429).
* ``app._CachedStaticFiles`` stamps the configured ``Cache-Control`` on 200
  responses and leaves 404s untouched.
"""
import apm_middleware as apm


# ── 1. Static-exempt predicate ───────────────────────────────────────────

def test_static_exempt_predicate_positive_cases():
    """SPA shell + hashed chunks + public media must be exempt."""
    exempt = [
        "/",                       # index.html shell
        "/js/app.abc123.js",       # hashed JS chunk
        "/js/vendor.def456.mjs",
        "/assets/index.aa11.css",  # hashed CSS chunk
        "/assets/index.aa11.css.map",
        "/logos/brand.png",        # logo mount
        "/landing/hero.webp",      # landing media
        "/favicon.ico",            # root static by extension
        "/manifest.webmanifest",
        "/illustration.svg",
        "/fonts/inter.woff2",
    ]
    for path in exempt:
        assert apm.is_static_exempt_path(path) is True, f"{path} should be exempt"


def test_static_exempt_predicate_negative_cases():
    """Dynamic API/GraphQL/WS surfaces stay throttled — never exempt."""
    throttled = [
        "/api/auth/login",
        "/api/pms/rooms",
        "/api/dashboard",
        "/graphql",
        "/ws/notifications",
        "/dashboard",              # SPA deep-link document (single request)
    ]
    for path in throttled:
        assert apm.is_static_exempt_path(path) is False, f"{path} must stay throttled"


def test_static_exempt_predicate_api_wins_over_extension():
    """An API path that merely *ends* in a static extension must NOT be
    exempted — otherwise ``/api/export/data.json`` would escape the limiter.
    """
    assert apm.is_static_exempt_path("/api/export/data.json") is False
    assert apm.is_static_exempt_path("/api/v2/assets/export") is False


# ── 2. Rate-limit middleware passes static through (no 429) ───────────────

async def test_rate_limiter_passes_static_through_without_429():
    """Static paths reach the inner app every time; the limiter never sends
    its own response (a 429) for them, regardless of request volume."""
    seen = []

    async def inner_app(scope, receive, send):
        seen.append(scope["path"])

    mw = apm.EnhancedRateLimitMiddleware(inner_app)

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    sent = []

    async def send(message):
        sent.append(message)

    static_paths = ["/", "/js/app.abc.js", "/assets/x.css", "/logos/l.png", "/favicon.ico"]
    # Hammer well past the prod anonymous budget (60/min) to prove exemption.
    for _ in range(80):
        for path in static_paths:
            scope = {"type": "http", "path": path, "method": "GET", "headers": []}
            await mw(scope, receive, send)

    assert len(seen) == 80 * len(static_paths)
    # The middleware emits a response itself ONLY on a 429; static must never.
    assert sent == []
    # Stronger proof (the TESTING profile uses a huge limit, so absence of a 429
    # alone is weak): static requests must never even be recorded in the per-IP
    # sliding windows the limiter counts against. If exemption regressed, these
    # paths would land in `_windows`.
    assert len(mw._windows) == 0


# ── 3. _CachedStaticFiles Cache-Control stamping ─────────────────────────

def test_cached_static_files_stamps_cache_control_on_200(tmp_path):
    from starlette.applications import Starlette
    from starlette.testclient import TestClient

    from app import _CachedStaticFiles

    js_dir = tmp_path / "js"
    js_dir.mkdir()
    (js_dir / "app.hash123.js").write_text("console.log('ok')")

    immutable = "public, max-age=31536000, immutable"
    application = Starlette()
    application.mount(
        "/js",
        _CachedStaticFiles(directory=str(js_dir), cache_control=immutable),
        name="js",
    )
    with TestClient(application) as client:
        ok = client.get("/js/app.hash123.js")
        assert ok.status_code == 200
        assert ok.headers["cache-control"] == immutable

        # A missing chunk must 404 (no stale index.html / MIME trap) and must NOT
        # inherit the immutable header.
        missing = client.get("/js/does-not-exist.js")
        assert missing.status_code == 404
        assert "immutable" not in missing.headers.get("cache-control", "")
