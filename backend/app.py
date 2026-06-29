"""
app.py — FastAPI Application Factory

Creates the FastAPI instance and mounts static files.
This is the single source of truth for the application object.
server.py imports from here and orchestrates bootstrap.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, ORJSONResponse
from fastapi.routing import APIRoute
from fastapi.staticfiles import StaticFiles

# ── Lifespan registry ────────────────────────────────────────────────
# Modules import `register_startup` / `register_shutdown` to schedule
# coroutines that should run during the FastAPI lifespan. Replaces the
# deprecated `@app.on_event("startup"|"shutdown")` decorators.
_startup_callbacks: list = []
_shutdown_callbacks: list = []


def register_startup(fn):
    """Register a coroutine to be awaited during application startup."""
    _startup_callbacks.append(fn)
    return fn


def register_startup_first(fn):
    """Register a startup coroutine to run BEFORE all others.

    Used by the DB migration runner so versioned schema migrations execute
    ahead of every index/bootstrap phase. Inserts at the head of the queue;
    if called multiple times the most-recently registered runs first.
    """
    _startup_callbacks.insert(0, fn)
    return fn


def register_shutdown(fn):
    """Register a coroutine to be awaited during application shutdown."""
    _shutdown_callbacks.append(fn)
    return fn


@asynccontextmanager
async def _lifespan(application: FastAPI):
    import logging as _logging

    _log = _logging.getLogger(__name__)

    # Replit autoscale (and similar PaaS) wait ~60s for the listening port
    # to open. Our bootstrap (control plane indexes, channel manager init,
    # outbox workers, event bus, etc.) takes longer than that, so when
    # DEFER_STARTUP_BOOTSTRAP=1 we fire the callbacks in a background task
    # and yield immediately — the HTTP port opens right away while heavy
    # init continues asynchronously. Endpoints that depend on a specific
    # subsystem already check readiness/raise on uninitialised state, so
    # early requests fail-closed rather than serve partial results.
    defer = os.getenv("DEFER_STARTUP_BOOTSTRAP", "").lower() in ("1", "true", "yes")

    async def _run_startup_callbacks():
        # When defer=True, yield event-loop control briefly so uvicorn can
        # finish its startup phase and BIND the listening socket BEFORE we
        # start invoking heavy (and often synchronous) bootstrap callbacks
        # like register_routers(). Without this, the scheduler can pick up
        # this background task immediately after `yield` in _lifespan and
        # the sync work blocks the loop for 20+s — uvicorn never gets the
        # tick it needs to call socket.bind(), and Replit autoscale fails
        # the deploy with "expected port 5000 never opened".
        if defer:
            await asyncio.sleep(0.5)
        any_failed = False
        for cb in list(_startup_callbacks):
            try:
                await cb()
            except Exception as _e:
                any_failed = True
                _log.exception("startup callback %s failed: %s", getattr(cb, "__name__", cb), _e)
                if not defer:
                    raise
        # Flip readiness only after ALL callbacks finish so the warm-up
        # gate keeps shedding traffic until indexes/workers/event-bus are
        # online. On any failure in defer mode we mark startup_failed and
        # keep the gate closed (fail-closed) — operator must inspect logs.
        if any_failed:
            application.state.startup_failed = True
            _log.error("startup callbacks completed with failures — warm-up gate kept closed")
        else:
            application.state.routes_ready = True

    if defer:
        application.state._bootstrap_task = asyncio.create_task(_run_startup_callbacks())
        _log.warning("DEFER_STARTUP_BOOTSTRAP=1 — bootstrap running in background; port will open immediately")
    else:
        await _run_startup_callbacks()

    yield

    for cb in list(_shutdown_callbacks):
        try:
            await cb()
        except Exception as _e:
            _log.warning("shutdown callback %s failed: %s", getattr(cb, "__name__", cb), _e)


def _unique_operation_id(route: "APIRoute") -> str:
    """Tag + method + path-based operation_id so every route gets a unique OpenAPI id."""

    def _safe(value: str) -> str:
        return "".join(c if c.isalnum() else "_" for c in value).strip("_").lower()

    tag = route.tags[0] if route.tags else "default"
    methods = "_".join(sorted(route.methods or ["any"])).lower()
    return f"{_safe(tag)}__{methods}__{_safe(route.path)}"


# Public static-asset extensions allowed through the warm-up gate. These are
# files served by the eager StaticFiles mounts (no DB/worker dependency), so
# letting them through during cold-start lets the SPA shell render its logo +
# hero imagery instead of a white screen with broken images. API/WS/GraphQL
# paths are excluded explicitly (see _warmup_gate), so this only widens the
# public static surface.
_WARMUP_STATIC_EXT = frozenset(
    {
        ".js",
        ".mjs",
        ".css",
        ".map",
        ".svg",
        ".png",
        ".jpg",
        ".jpeg",
        ".webp",
        ".gif",
        ".ico",
        ".avif",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".otf",
        ".json",
        ".webmanifest",
        ".txt",
        ".xml",
    }
)


class _CachedStaticFiles(StaticFiles):
    """StaticFiles that stamps a fixed Cache-Control on 200 responses.

    Used for the hashed SPA bundles (/js, /assets): Vite embeds a content
    hash in every filename, so they can be cached immutably. Without an
    explicit Cache-Control the browser revalidates/refetches all ~27 chunks
    on every load; on the combined deployment (a single uvicorn worker
    serving BOTH the API and the static SPA) that per-load request storm
    helps tip the event loop over into edge-proxy 502s -> white screen.
    304/404 responses are left untouched.
    """

    def __init__(self, *args, cache_control: str, **kwargs):
        self._cache_control = cache_control
        super().__init__(*args, **kwargs)

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 200:
            response.headers["Cache-Control"] = self._cache_control
        return response


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""

    application = FastAPI(
        lifespan=_lifespan,
        generate_unique_id_function=_unique_operation_id,
        title="Syroce PMS - Otel Yönetim Sistemi",
        description="""
## Syroce PMS - Kapsamlı Otel Yönetim Platformu

### Temel Moduller
- **PMS**: Oda, Rezervasyon, Check-in/Check-out Yonetimi
- **Housekeeping**: Temizlik ve Oda Bakim Yonetimi
- **Finance**: Fatura, Folio, Muhasebe
- **Reports**: Raporlama ve Analitik
- **AI / ML**: Yapay Zeka ve Makine Ogrenmesi
- **Revenue**: Gelir Yonetimi ve Fiyatlandirma
- **Channel Manager**: OTA Kanal Yonetimi
- **Sales / CRM**: Satis ve Musteri Iliskileri

### API Kimlik Dogrulama
Tum API istekleri `Authorization: Bearer <token>` header'i gerektirir.
Token almak icin `/api/auth/login` endpoint'ini kullanin.
        """,
        version="3.2.0",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        default_response_class=ORJSONResponse,
        openapi_tags=[
            {"name": "PMS / Dashboard", "description": "Dashboard, KPI ve Executive raporlari"},
            {"name": "PMS / Front Desk", "description": "Check-in, Check-out, Walk-in, Folio islemleri"},
            {"name": "PMS / Housekeeping", "description": "Temizlik gorevleri, oda durumu, personel performansi"},
            {"name": "PMS / Night Audit", "description": "Gece auditi, log kayitlari, OTA sync loglari"},
            {"name": "PMS / Notifications", "description": "Bildirimler, inbox, sistem uyarilari"},
            {"name": "PMS / Groups", "description": "Grup ve blok rezervasyonlari"},
            {"name": "PMS / Calendar", "description": "Takvim, rate code yonetimi, kanal miks"},
            {"name": "PMS / Approvals", "description": "Onay surecleri, butce yonetimi"},
            {"name": "PMS / POS & F&B", "description": "POS islemleri, mutfak siparisleri, F&B yonetimi"},
            {"name": "PMS / Maintenance", "description": "Bakim, onarim, IoT sensor yonetimi"},
            {"name": "PMS / Operations", "description": "Coklu tesis, HR, odeme, envanter islemleri"},
            {"name": "AI / ML", "description": "Yapay zeka chat, tahminleme, ML modelleri, sosyal medya analizi"},
            {"name": "Revenue / Pricing", "description": "Fiyatlandirma, rate planlari, gelir yonetimi, RMS"},
            {"name": "Guest / Messaging", "description": "WhatsApp, SMS, e-posta mesajlasma"},
            {"name": "Guest / Operations", "description": "Misafir profili, sadakat programi, NPS, tercihler"},
            {"name": "Channel Manager / Operations", "description": "OTA baglantilari, oda eslestirme, envanter senkronizasyonu"},
            {"name": "Sales / CRM", "description": "Satis, kurumsal musteri, lead yonetimi"},
            {"name": "Admin / Operations", "description": "Tenant yonetimi, abonelik, RBAC, sistem ayarlari"},
            {"name": "Channel Manager / Hardening", "description": "CM runtime status, drift detection, reconciliation, provider health"},
            {"name": "Workers / Hardening", "description": "Queue health, stuck tasks, failure archive, retry summary"},
            {"name": "Security / Hardening", "description": "Audit status, rate limiting, credential check, tenant guard"},
            {"name": "Observability / Runtime", "description": "Runtime metrics, alerts, system health aggregation"},
        ],
    )

    # ── Warm-up gate (Replit autoscale: port must open within ~30s) ─
    # When DEFER_STARTUP_BOOTSTRAP=1, server.py defers the heavy
    # register_routers() call into a background startup callback so the
    # port opens immediately. During the warm-up window (typ. 20-30s),
    # routes are not yet mounted; we return 503 for everything except
    # /health* so the platform's health check passes while user traffic
    # gets a clean "Retry-After" instead of a confusing 404.
    # `routes_ready` defaults True (eager mode) — server.py flips it to
    # False before deferring and back to True when mounting completes.
    @application.middleware("http")
    async def _warmup_gate(request, call_next):
        if not getattr(application.state, "routes_ready", True):
            path = request.url.path
            # Allow lightweight probes AND static SPA assets during warm-up:
            #   - /health* (explicit health endpoints)
            #   - /favicon.ico (browser noise)
            #   - "/" (Replit autoscale default HTTP probe path —
            #     served by the deploy_root_probe handler below)
            #   - public static files: the /js, /assets, /logos, /landing
            #     eager StaticFiles mounts plus any root-level static asset
            #     (logo svg/png, og images, robots, manifest, fonts, ...).
            #     These are public files with no DB/worker dependency, so
            #     serving them during warm-up lets the SPA shell boot AND
            #     render its logo + hero imagery instead of a white screen
            #     with broken images. API/WS/GraphQL stay gated below (503,
            #     fail-closed) until bootstrap completes, so no data is
            #     served early.
            _is_dynamic = path.startswith("/api") or path.startswith("/graphql") or path.startswith("/ws")
            _, _ext = os.path.splitext(path)
            _spa_static = not _is_dynamic and (path.startswith("/js/") or path.startswith("/assets/") or path.startswith("/logos/") or path.startswith("/landing/") or _ext in _WARMUP_STATIC_EXT)
            if not (path.startswith("/health") or path == "/favicon.ico" or path == "/" or _spa_static):
                from fastapi.responses import JSONResponse

                return JSONResponse(
                    {"status": "starting", "detail": "Server is warming up"},
                    status_code=503,
                    headers={"Retry-After": "5"},
                )
        return await call_next(request)

    # ── Deployment health check (lightweight, no DB/Redis) ──────────
    @application.get("/health", include_in_schema=False)
    @application.get("/health/", include_in_schema=False)
    async def deployment_health_check():
        return {"status": "healthy"}

    # ── Frontend build location (defined early; used by the root route
    #    and the SPA static serving block further below) ─────────────
    _backend_dir = Path(__file__).parent
    frontend_build = Path(os.environ.get("FRONTEND_BUILD_DIR", str(_backend_dir.parent / "frontend" / "build")))

    # ── Root route (Replit autoscale default health path + SPA entry) ─
    # The autoscale HTTP probe hits "/". When the built frontend is
    # present we serve index.html so the SPA landing page shows at the
    # root URL (the HTML response is a 200, so the probe still passes).
    # When the build is absent (pure-backend dev mode) we return cheap
    # health JSON so the probe passes during warm-up, before user
    # routers are mounted.
    @application.get("/", include_in_schema=False)
    @application.head("/", include_in_schema=False)
    async def deploy_root_probe():
        _index = frontend_build / "index.html"
        if _index.is_file():
            # index.html must NEVER be cached: it pins the current build's
            # hashed chunk filenames. A cached copy survives a redeploy and
            # then points at chunks that no longer exist → those requests
            # fall through to the SPA fallback and the browser throws
            # "'text/html' is not a valid JavaScript MIME type". Hashed
            # assets under /js,/assets,/logos stay immutably cacheable.
            return FileResponse(
                str(_index),
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )
        return {"status": "ok", "service": "syroce-pms"}

    # ── Liveness vs Readiness ayrımı (Kubernetes/Replit Deploy uyumlu) ──
    # /health/live  → süreç ayakta mı? (her zaman 200 — DB sorgulamaz)
    # /health/ready → trafik almaya hazır mı? (DB ping + boot tamam mı)
    # Platform readiness 503 görürse trafiği başka instance'a yönlendirir;
    # liveness 200 olduğu için konteyneri öldürmez. Bu sayede Atlas yavaşlığı
    # gibi geçici durumlarda restart döngüsüne girmiyoruz.
    @application.get("/health/live", include_in_schema=False)
    async def liveness_check():
        return {"status": "alive"}

    @application.get("/health/ready", include_in_schema=False)
    async def readiness_check():
        from fastapi.responses import JSONResponse

        try:
            from bootstrap.phases.d_perf import BOOT_READY
        except Exception:
            BOOT_READY = False
        if not BOOT_READY:
            return JSONResponse({"status": "starting"}, status_code=503)
        try:
            # Hızlı DB ping (~1-2 ms) — Atlas erişilemiyorsa 503
            from core.database import _raw_db

            await asyncio.wait_for(_raw_db.command("ping"), timeout=2.0)
        except Exception as e:
            return JSONResponse({"status": "db_unavailable", "error": str(e)[:120]}, status_code=503)
        return {"status": "ready"}

    # ── Cosmetic favicon (kill noisy 404s in logs) ──────────────────
    # `/` is intentionally NOT registered here: when frontend/build exists
    # the SPA 404-handler below serves index.html. When it doesn't exist
    # (pure backend dev mode), a 404 is the honest response.
    from fastapi.responses import Response

    @application.get("/favicon.ico", include_in_schema=False)
    async def _favicon_noop():
        return Response(status_code=204)

    # ── Screenshots download ────────────────────────────────────────
    @application.get("/api/download/screenshots", include_in_schema=False)
    async def download_screenshots_zip():
        zip_path = _backend_dir / "Syroce_PMS_AppStore_Screenshots.zip"
        if not zip_path.exists():
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Screenshots ZIP not found")
        return FileResponse(
            path=str(zip_path),
            filename="Syroce_PMS_AppStore_Screenshots.zip",
            media_type="application/zip",
        )

    # ── Uploads are now served via the authenticated /api/uploads endpoint ──
    # The static mount was removed for security (authorization enforcement).
    upload_dir = Path(os.environ.get("UPLOAD_DIR", str(_backend_dir / "uploads")))
    try:
        upload_dir.mkdir(parents=True, exist_ok=True)
    except (PermissionError, OSError) as e:
        import logging
        logging.getLogger(__name__).warning("Upload dir creation failed (%s): %s", upload_dir, e)

    # ── Frontend SPA static serving (combined deployment) ───────────
    # Replit autoscale: serve built frontend through FastAPI so one URL
    # hosts both API (/api/*, /ws, /docs) and SPA. Skipped when build dir
    # is absent (dev mode uses Vite on a separate port).
    # frontend_build is defined above (near the root route). Deep links use
    # a 404 exception handler instead of a catch-all GET route so we don't
    # shadow trailing-slash redirects or other framework routes.
    if frontend_build.is_dir() and (frontend_build / "index.html").is_file():
        from starlette.exceptions import HTTPException as _StarletteHTTPException
        from starlette.requests import Request as _Request
        from starlette.responses import FileResponse as _FR
        from starlette.responses import JSONResponse as _JR

        # Hashed SPA assets are content-addressed (Vite embeds a content hash
        # in every /js and /assets filename) so they are safe to cache
        # forever. Stamping immutable Cache-Control means a warm browser
        # refetches nothing on reload, cutting the per-load chunk request
        # storm that helps the single-worker event loop tip into edge-proxy
        # 502s (white screen). /logos are not content-hashed (brand files
        # served by path) so they get a modest TTL instead of immutable.
        _IMMUTABLE_CC = "public, max-age=31536000, immutable"
        _cc_by_sub = {
            "assets": _IMMUTABLE_CC,
            "js": _IMMUTABLE_CC,
            "logos": "public, max-age=3600",
        }
        for _sub in ("assets", "js", "logos"):
            _d = frontend_build / _sub
            if _d.is_dir():
                application.mount(
                    f"/{_sub}",
                    _CachedStaticFiles(directory=str(_d), cache_control=_cc_by_sub[_sub]),
                    name=f"spa_{_sub}",
                )

        _SPA_PROTECTED_PREFIXES = ("/api", "/ws", "/docs", "/redoc", "/openapi", "/graphql")

        @application.exception_handler(404)
        async def _spa_404_handler(request: _Request, exc: _StarletteHTTPException):
            path = request.url.path
            if path.startswith(_SPA_PROTECTED_PREFIXES):
                return _JR({"detail": "Not Found"}, status_code=404)
            candidate = frontend_build / path.lstrip("/")
            if path != "/" and candidate.is_file():
                return _FR(str(candidate))
            # A request for a static asset (hashed JS/CSS chunk, image, font,
            # ...) that does NOT exist must return a real 404 — never the SPA
            # shell. Otherwise a stale cached index.html requesting a now-
            # deleted chunk gets index.html (text/html) back and the browser
            # module loader throws "'text/html' is not a valid JavaScript MIME
            # type". Only extension-less deep-link routes fall through to
            # index.html for client-side routing.
            _, _ext = os.path.splitext(path)
            if _ext:
                return _JR({"detail": "Not Found"}, status_code=404)
            return _FR(
                str(frontend_build / "index.html"),
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )

    # ── OpenAPI schema cache ────────────────────────────────────────
    # With ~2435 paths, FastAPI's default openapi() rebuild costs ~1.5s per request
    # (called by /docs, /redoc, /api/openapi.json). Cache the generated dict so the
    # second and later calls are served from memory.
    from fastapi.openapi.utils import get_openapi as _get_openapi

    # Task-170 (Bug AZ) — paths that must not appear in the public schema when
    # setup/debug endpoints are disabled.  The routes themselves return 404 via
    # _enforce_setup_enabled(), but they were still listed in the OpenAPI schema,
    # giving attackers a ready inventory of super-admin elevation and cross-tenant
    # user-listing endpoints.  Filter them out of the generated schema whenever
    # ENABLE_SETUP_ENDPOINTS != "1" so their existence is not disclosed.
    _SETUP_HIDDEN_PATHS = (
        "/api/setup/make-super-admin",
        "/api/setup/make-me-super-admin",
        "/api/admin/quick-super-admin",
        "/api/admin/list-all-users-debug",
    )

    def _cached_openapi():
        if application.openapi_schema is None:
            schema = _get_openapi(
                title=application.title,
                version=application.version,
                description=application.description,
                routes=application.routes,
                tags=application.openapi_tags,
                servers=application.servers,
            )
            if os.environ.get("ENABLE_SETUP_ENDPOINTS", "").strip() != "1":
                schema["paths"] = {path: ops for path, ops in schema.get("paths", {}).items() if path not in _SETUP_HIDDEN_PATHS}
            application.openapi_schema = schema
        return application.openapi_schema

    application.openapi = _cached_openapi  # type: ignore[assignment]

    return application
