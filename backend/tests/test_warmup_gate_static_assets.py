"""Regression for the warm-up gate static-asset allow-list (white-screen fix).

Production incident (2026-06-05): on Replit autoscale cold start the heavy
bootstrap (cache warming 10k+ bookings + schedulers) keeps
`app.state.routes_ready=False` for several minutes. The `_warmup_gate`
middleware returned 503 "Server is warming up" for EVERYTHING except
`/health*`, `/favicon.ico`, and exactly `/`. So `/` served index.html (200)
but its referenced `/js/*` and `/assets/*` bundles returned 503 -> the SPA
never booted -> blank white screen for the whole warm-up window.

The fix adds `/js/`, `/assets/`, `/logos/`, `/landing/` plus any root-level
public static asset (by extension: logo svg/png, hero webp, fonts, manifest,
...) to the gate allow-list (those are eager public StaticFiles mounts with no
DB/worker dependency) while keeping `/api/*`, `/graphql`, `/ws` gated (503,
fail-closed). This test locks that behavior: static SPA bundle/image paths
must NOT be 503 during warm-up, while dynamic/data surfaces must stay 503.

Follow-up (2026-06-05): the first fix only allow-listed `/js`,`/assets`,
`/logos`, so the landing logo (`/syroce-logo.svg`, root) and hero image
(`/landing/hero-hotel.png`) still 503'd during warm-up -> visible but with
broken logo + hotel image. This widens the allow-list to `/landing/` and
root-level static extensions.
"""
from fastapi.testclient import TestClient

from app import create_app


def _client_in_warmup():
    app = create_app()
    # Simulate the cold-start window: bootstrap callbacks not yet finished.
    app.state.routes_ready = False
    # No `with` context -> lifespan startup does not run / cannot flip the flag.
    return TestClient(app, raise_server_exceptions=False)


def test_api_paths_gated_503_during_warmup():
    client = _client_in_warmup()
    for path in ("/api/health", "/api/auth/login", "/graphql"):
        resp = client.get(path)
        assert resp.status_code == 503, f"{path} should be gated during warm-up"
        assert resp.json().get("status") == "starting"


def test_spa_static_assets_not_gated_during_warmup():
    client = _client_in_warmup()
    # These prefixes/files must pass the gate. Whether the concrete file exists
    # depends on the build dir; the regression target is simply that the gate
    # does NOT short-circuit them with a 503 "warming up" response.
    for path in (
        "/js/index.js",
        "/assets/index.css",
        "/logos/x.png",
        # landing logo (root) + hero image (under /landing/) — the assets the
        # 2026-06-05 follow-up unblocked so they render during warm-up.
        "/syroce-logo.svg",
        "/syroce-logo.png",
        "/landing/hero-hotel.png",
        "/landing/hero-hotel-960.webp",
    ):
        resp = client.get(path)
        assert resp.status_code != 503, f"{path} must not be gated during warm-up"


def test_static_extension_cannot_bypass_dynamic_gate_during_warmup():
    """A static-looking extension on a dynamic prefix must stay gated (503).

    Locks the fail-closed invariant: the root-level extension allow-list must
    NOT open `/api`, `/graphql`, or `/ws` just because the path ends in a
    static extension (e.g. an attacker probing `/api/secret.json`).
    """
    client = _client_in_warmup()
    for path in ("/api/secret.json", "/graphql/schema.json", "/ws/client.js"):
        resp = client.get(path)
        assert resp.status_code == 503, f"{path} must stay gated during warm-up"
        assert resp.json().get("status") == "starting"


def test_root_and_health_allowed_during_warmup():
    client = _client_in_warmup()
    for path in ("/", "/health", "/favicon.ico"):
        resp = client.get(path)
        assert resp.status_code != 503, f"{path} must not be gated during warm-up"
