"""
server.py — Bootstrap Orchestrator

This is the uvicorn entrypoint.  It creates the FastAPI app, registers
middleware and routers via bootstrap modules, wires startup/shutdown
lifecycle events, and re-exports key symbols for backward compatibility.

All endpoint definitions live in domain-specific router modules under
domains/ and routers/.

Target: < 300 lines.
"""
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# ── Environment ─────────────────────────────────────────────────────
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

# ── App factory ─────────────────────────────────────────────────────
from app import create_app, register_shutdown, register_startup  # noqa: E402

app = create_app()

# ── Observability (before anything else touches logging) ────────────
from bootstrap.observability_init import init_observability  # noqa: E402

init_observability()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Attach PII sanitization filter to root logger
try:
    from security.log_sanitizer import SanitizedLogFilter
    for handler in logging.root.handlers:
        handler.addFilter(SanitizedLogFilter())
    logger.info("Log sanitization filter attached to all handlers")
except Exception as _log_err:
    logger.warning("Log sanitization filter skipped: %s", _log_err)

# ── Core (single-instance DB, auth) ────────────────────────────────
from core.database import client, db  # noqa: E402
from core.helpers import (  # noqa: E402
    require_admin,
    require_feature,
    require_module,
    require_super_admin_guard,
)
from core.security import (  # noqa: E402
    JWT_ALGORITHM,
    JWT_EXPIRATION_HOURS,
    JWT_SECRET,
    create_token,
    get_current_user,
    hash_password,
    security,
    verify_password,
)
from models.enums import ChannelType  # noqa: E402
from models.schemas import User  # noqa: E402

# Backward compat alias
require_super_admin = require_super_admin_guard()

# Expose db on app.state early
app.state.db = db

# Expose cache manager on app.state so health checks (and any other
# read-only consumer) can resolve a Redis-or-fallback client without
# importing module-level singletons. Defensive: cache_manager import is
# wrapped because a misconfigured cache must NEVER prevent server boot.
try:
    # The module-level singleton is named ``cache`` (created at import
    # time, see ``cache_manager.py``: ``cache = CacheManager()``).
    from cache_manager import cache as _cache_manager_singleton
    app.state.cache_manager = _cache_manager_singleton
except Exception as _cm_err:
    app.state.cache_manager = None
    logger.warning("cache_manager not exposed on app.state: %s", _cm_err)

# ── Middleware (via bootstrap) ──────────────────────────────────────
from bootstrap.middleware_registry import register_middleware  # noqa: E402

register_middleware(app)

# Additional CORS with explicit origins
from datetime import UTC

from starlette.middleware.cors import CORSMiddleware  # noqa: E402

_cors_raw = os.environ.get("CORS_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()] if _cors_raw else []
_always_allowed = [
    "https://pms.syroce.com",
    "https://www.pms.syroce.com",
    "https://syroce.com",
    "http://localhost:3000",
    "http://localhost:5000",
    "https://syroce-b2b-api.syroce.com",
]
for origin in _always_allowed:
    if origin not in _cors_origins:
        _cors_origins.append(origin)

# Replit dev domain auto-detection (development convenience)
_replit_dev = os.environ.get("REPLIT_DEV_DOMAIN")
if _replit_dev and f"https://{_replit_dev}" not in _cors_origins:
    _cors_origins.append(f"https://{_replit_dev}")

# Bug AL: previous regex allowed ANY *.replit.app subdomain — an attacker
# could publish their own evil.replit.app and ride credentials=true to
# perform CSRF/XHR against a logged-in user. Production hosts MUST be
# enumerated explicitly via CORS_ORIGINS or _always_allowed; we only
# auto-allow ephemeral *.replit.dev preview hosts here (those are
# tied to a single Repl owner and not registrable by attackers).
_env_mode = (os.environ.get("ENVIRONMENT") or os.environ.get("ENV") or "development").lower()
_cors_origin_regex = None
if _env_mode != "production":
    _cors_origin_regex = r"^https://[a-z0-9-]+\.(replit\.dev|riker\.replit\.dev)$"

# Avoid the wildcard + credentials CORS protocol violation
_allow_credentials = True
if not _cors_origins:
    _cors_origins = ["*"]
    _allow_credentials = False  # Cannot combine `*` with credentials per CORS spec.

app.add_middleware(
    CORSMiddleware,
    allow_credentials=_allow_credentials,
    allow_origins=_cors_origins,
    allow_origin_regex=_cors_origin_regex,
    allow_methods=["*"],
    allow_headers=["*"],
)

# APM & rate limiting
try:
    from apm_middleware import APMMiddleware, EnhancedRateLimitMiddleware, apm_store, get_rate_limit_stats

    app.add_middleware(EnhancedRateLimitMiddleware)
    app.add_middleware(APMMiddleware)
    logger.info("APM & Rate Limiting middleware activated")
except Exception:
    from collections import deque
    from datetime import datetime

    class _FallbackStore:
        requests = deque(maxlen=100)
        rate_limit_hits = 0
        started_at = datetime.now(UTC)
        def get_summary(self, minutes=10): return {"total_requests": 0, "error_rate_percent": 0}
        def get_recent_errors(self, limit=50): return []
        def record_request(self, **kw): pass
        def record_rate_limit_hit(self, p): pass

    apm_store = _FallbackStore()
    def get_rate_limit_stats(): return {}

# Entitlement enforcement
try:
    from core.entitlement import EntitlementMiddleware
    app.add_middleware(EntitlementMiddleware)
    logger.info("Entitlement enforcement middleware activated")
except Exception as _ent_err:
    logger.warning(f"Entitlement middleware skipped: {_ent_err}")

# Error response normalizer (O2 — standardize all errors to {"detail": ...})
try:
    from middleware.error_normalizer import ErrorNormalizerMiddleware
    app.add_middleware(ErrorNormalizerMiddleware)
    logger.info("Error response normalizer middleware activated")
except Exception as _norm_err:
    logger.warning("Error normalizer middleware skipped: %s", _norm_err)

# Request tracing
try:
    from modules.observability.request_tracing_middleware import RequestTracingMiddleware
    app.add_middleware(RequestTracingMiddleware)
except Exception as _trace_err:
    logger.warning("Request tracing middleware skipped: %s", _trace_err)

# Upload body-size guard (v39 — architect feedback D): fail-fast on oversized
# multipart/JSON bodies via Content-Length, before downstream parsers spool to disk.
try:
    from middleware.upload_size_limit import UploadSizeLimitMiddleware
    app.add_middleware(UploadSizeLimitMiddleware)
    logger.info("Upload size-limit middleware activated")
except Exception as _usl_err:
    logger.warning("Upload size-limit middleware skipped: %s", _usl_err)

# PII masking disabled at middleware level to avoid GZip conflicts.
# Masking is applied at the application layer via security/sensitive_output.py
# and security/pii_registry.py which are used by individual endpoints.
logger.info("PII Masking: application-layer masking active (middleware bypassed)")

# ── Global exception handler for Exely provider errors ──────────────
from fastapi import Request
from fastapi.responses import JSONResponse

try:
    from domains.channel_manager.providers.exely.errors import ExelyError

    @app.exception_handler(ExelyError)
    async def exely_error_handler(request: Request, exc: ExelyError):
        return JSONResponse(status_code=502, content={"detail": f"Exely provider error: {exc.message}"})
except ImportError:
    pass

# ── 422 validation handler: NaN/Infinity input echo'sunu temizle ───────
# Pydantic 422 hatalarında payload input'u response'a yansıtılır;
# Starlette JSONResponse `allow_nan=False` kullandığından NaN/Inf 500 verir.
import math as _math

from fastapi.exceptions import RequestValidationError


def _scrub_non_finite(obj):
    if isinstance(obj, float):
        if _math.isnan(obj) or _math.isinf(obj):
            return str(obj)
        return obj
    if isinstance(obj, (bytes, bytearray)):
        try:
            return obj.decode("utf-8", errors="replace")
        except Exception:
            return repr(obj)
    if isinstance(obj, list):
        return [_scrub_non_finite(x) for x in obj]
    if isinstance(obj, tuple):
        return tuple(_scrub_non_finite(x) for x in obj)
    if isinstance(obj, dict):
        return {k: _scrub_non_finite(v) for k, v in obj.items()}
    # Fallback: JSON-serialize edilemeyen herhangi bir tip → str
    if not isinstance(obj, (str, int, bool, type(None))):
        try:
            import json as _json
            _json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)
    return obj

_PII_FIELD_PATTERNS = (
    "password", "passwd", "secret", "token", "api_key", "apikey",
    "authorization", "card", "credit_card", "cvv", "cvc", "pan",
    "iban", "ssn", "tckn", "tc_kimlik", "passport", "otp", "pin",
    "private_key", "client_secret", "session", "cookie",
)

def _redact_pii(value):
    """Recursively redact PII-suspicious fields and any string longer than 200 chars."""
    if isinstance(value, dict):
        out = {}
        for k, v in value.items():
            kl = str(k).lower()
            if any(p in kl for p in _PII_FIELD_PATTERNS):
                out[k] = "***REDACTED***"
            else:
                out[k] = _redact_pii(v)
        return out
    if isinstance(value, list):
        return [_redact_pii(v) for v in value]
    if isinstance(value, str) and len(value) > 200:
        return value[:50] + "...[truncated]"
    return value

from core.tenant_db import TenantViolationError as _TenantViolationError  # Bug AR follow-up


@app.exception_handler(_TenantViolationError)
async def _tenant_violation_handler(request: Request, exc: _TenantViolationError):
    # Bug AR (architect follow-up, April 2026): map TenantViolationError → 403
    # so cross-tenant smuggle attempts return a controlled authorization
    # response rather than a noisy 500 + stack trace, while still logging
    # the violation server-side for forensics.
    import logging as _log
    _log.getLogger("core.tenant_db").warning(
        "tenant violation rejected: path=%s method=%s detail=%s",
        request.url.path, request.method, str(exc),
    )
    return JSONResponse(status_code=403, content={"detail": "Yetkisiz islem"})


@app.exception_handler(RequestValidationError)
async def _validation_handler(request: Request, exc: RequestValidationError):
    # Strip echoed `input` (which contains raw request body, often with PII like
    # credit cards, passwords, tokens). Replace with a redacted summary so debugging
    # is still possible without leaking sensitive data.
    safe_errors = []
    for err in _scrub_non_finite(exc.errors()):
        if isinstance(err, dict):
            err = dict(err)
            if "input" in err:
                err["input"] = _redact_pii(err["input"])
            # Drop the pydantic doc URL which is verbose and not needed by clients
            err.pop("url", None)
        safe_errors.append(err)
    return JSONResponse(status_code=422, content={"detail": safe_errors})

# ── Additional API router (AI endpoints) ─────────────────────────────
from fastapi import APIRouter

api_router = APIRouter(prefix="/api")

try:
    from domains.ai.endpoints import api_router as ai_ai_router
    api_router.include_router(ai_ai_router, tags=["AI Intelligence"])
    logger.info("  ✅ AI Intelligence endpoints loaded")
except Exception as _ai_err:
    logger.warning("AI Intelligence endpoints skipped: %s", _ai_err)

# Mount the main API router
app.include_router(api_router)

# ── Health check router ─────────────────────────────────────────────
try:
    from health_check import health_router
    app.include_router(health_router)
except ImportError:
    pass

# ── External routers (via bootstrap registry) ───────────────────────
# This is the slow step: register_routers() imports ~189 router modules
# synchronously (~17-34s). On Replit autoscale the port-open window is
# ~30s, so when DEFER_STARTUP_BOOTSTRAP=1 we defer the call into a
# startup callback. The app.py warm-up middleware returns 503 for
# non-health requests until app.state.routes_ready flips to True.
from bootstrap.router_registry import register_routers  # noqa: E402

_DEFER_ROUTER_MOUNT = os.getenv("DEFER_STARTUP_BOOTSTRAP", "").lower() in ("1", "true", "yes")

if _DEFER_ROUTER_MOUNT:
    # Warm-up gate stays closed until ALL startup callbacks finish (app.py
    # _run_startup_callbacks flips routes_ready=True on full success, or
    # startup_failed=True on any error — fail-closed).
    app.state.routes_ready = False
    app.state.startup_failed = False

    @register_startup
    async def _deferred_router_mount():
        import time as _t
        _t0 = _t.time()
        logger.warning("DEFER_STARTUP_BOOTSTRAP=1 — deferred router registration starting (port already open)")
        register_routers(app, api_router, require_super_admin_dep=require_super_admin)
        logger.warning("Deferred router registration complete in %.2fs", _t.time() - _t0)
else:
    app.state.routes_ready = True
    register_routers(app, api_router, require_super_admin_dep=require_super_admin)

# ── Compatibility / stub endpoints (UI-required modules not yet
# (re)implemented — see backend/routers/missing_endpoints_compat.py) ──
try:
    from routers.missing_endpoints_compat import router as missing_endpoints_router
    app.include_router(missing_endpoints_router)
    logger.info("  ✅ routers.missing_endpoints_compat")
except Exception as _compat_err:
    logger.warning("Compatibility router skipped: %s", _compat_err)

# ── Additional optional routers (factory-pattern modules) ───────────
# NOT: Asagidaki 9 modulun hicbiri kod tabaninda artik mevcut degil
# (security_2fa, ip_access_control, gdpr_compliance, central_office_endpoints,
# central_pricing_endpoints, cross_property_guests, ml_real_models,
# tenant_isolation, pci_dss_compliance). Bu ozellikler basta domains/admin,
# domains/security ve security/tenant_isolation_router altinda yeniden
# konumlanmis durumda. Bu liste sessizce yukleme denemesini sonlandiriyor.
_optional_factory_routers: list[tuple[str, str, str]] = [
    # ("module_name", "factory_function", "Display Tag")  -- eklemek istersen buraya yaz.
]

_failed_routers = []
for mod_name, factory_name, tag in _optional_factory_routers:
    try:
        mod = __import__(mod_name)
        factory = getattr(mod, factory_name)
        router = factory(db, get_current_user)
        app.include_router(router, tags=[tag])
        logger.info(f"  ✅ {tag}")
    except Exception as _fac_err:
        _failed_routers.append(tag)
        logger.warning("Factory router '%s' skipped: %s", tag, _fac_err)
if _failed_routers:
    logger.warning("⚠️ %d factory router(s) failed to load: %s", len(_failed_routers), ", ".join(_failed_routers))

# Report Builder & Guest Messaging (init pattern)
try:
    # Router itself is mounted via bootstrap/router_registry.py:72 — we only
    # need to call init_report_builder here so the handlers see db + auth.
    from routers.report_builder import init_report_builder
    init_report_builder(db, get_current_user)
except Exception as _rb_err:
    logger.warning("Report Builder init skipped: %s", _rb_err)

try:
    # Router itself is mounted via bootstrap/router_registry.py:73 — we only
    # need to call init_guest_messaging here so the handlers see db + auth.
    from routers.guest_messaging import init_guest_messaging
    init_guest_messaging(db, get_current_user)
except Exception as _gm_err:
    logger.warning("Guest Messaging init skipped: %s", _gm_err)

# Supplies Marketplace (B2B) — vendor portal + hotel storefront + admin
try:
    from modules.supplies_market.repository import ensure_indexes as _sm_ensure_indexes
    from modules.supplies_market.router_admin import router as _sm_admin_router
    from modules.supplies_market.router_hotel import router as _sm_hotel_router
    from modules.supplies_market.router_vendor import router as _sm_vendor_router

    app.include_router(_sm_vendor_router)
    app.include_router(_sm_hotel_router)
    app.include_router(_sm_admin_router)

    @register_startup
    async def _supplies_market_indexes():
        await _sm_ensure_indexes()

    logger.info("✅ Supplies Marketplace routers mounted")
except Exception as _sm_err:
    logger.warning("Supplies Marketplace router skipped: %s", _sm_err)

# GraphQL
try:
    from fastapi import Depends
    from strawberry.fastapi import GraphQLRouter

    from graphql_api.schema import schema

    async def _graphql_context_getter(
        _current_user=Depends(get_current_user),
    ) -> dict:
        # get_current_user enforces: access-token-only (rejects refresh tokens),
        # JTI revocation, tokens_invalid_before, user existence, and tenant
        # consistency. Any failure raises HTTP 401 before a resolver runs.
        return {"db": db, "cache": None, "materialized_views": None}

    graphql_app = GraphQLRouter(schema, context_getter=_graphql_context_getter)
    app.include_router(graphql_app, prefix="/api/graphql", tags=["graphql"])
except Exception as _gql_err:
    logger.warning("GraphQL router skipped: %s", _gql_err)

# WebSocket
try:
    from websocket_server import socket_app
    app.mount("/ws", socket_app)
except Exception as _ws_sock_err:
    logger.warning("WebSocket server skipped: %s", _ws_sock_err)

# Channel Manager — Hardening: mounted via bootstrap/router_registry.py:122.
# DO NOT re-include here — it would double-register all hardening routes and
# emit "Duplicate Operation ID" warnings at OpenAPI generation time.

# Channel Manager v2 — included via bootstrap/router_registry.py:256.
# DO NOT also include it here, it would double-mount 147 routes and emit
# ~213 "Duplicate Operation ID" warnings at OpenAPI generation time.

# OTA-002: Outbox Admin endpoints (requeue, replay, status)
# Mounted via bootstrap/router_registry.py:247 — not here.

# Webhook Admin endpoints (deliveries, DLQ, manual retry)
try:
    from routers.webhook_admin import webhook_admin_router
    app.include_router(webhook_admin_router, prefix="/api", tags=["Webhook Admin"])
    logger.info("  ✅ Webhook Admin router loaded (deliveries/DLQ/retry)")
except Exception as _wh_err:
    logger.warning("Webhook Admin router skipped: %s", _wh_err)

# DATA-001: Import Admin endpoints (review queue, retry, approve, dismiss)
# Mounted via bootstrap/router_registry.py:248 — not here.

# Entitlement, Metering & Feature Flags Admin API
try:
    from domains.admin.entitlement_router import router as entitlement_admin_router
    app.include_router(entitlement_admin_router, tags=["Entitlement & Metering"])
    logger.info("  ✅ Entitlement & Metering admin router loaded")
except Exception as _e:
    logger.warning(f"Entitlement admin router skipped: {_e}")

# Deploy Pipeline — Hard Gate CI/CD, Progressive Deploy, Auto-Rollback
try:
    from ops.deploy_router import router as deploy_router
    app.include_router(deploy_router, tags=["Deploy Pipeline"])
    logger.info("  ✅ Deploy Pipeline router loaded")
except Exception as _dep_err:
    logger.warning(f"Deploy Pipeline router skipped: {_dep_err}")

# Wire Status — Unified failure chain visibility
try:
    from routers.wire_status import router as wire_status_router
    app.include_router(wire_status_router, tags=["Wire Status"])
    logger.info("  ✅ Wire Status router loaded")
except Exception as _ws_err:
    logger.warning(f"Wire Status router skipped: {_ws_err}")

# Quick-ID Microservice Proxy (kimlik tarama)
# Note: room_qr_router is mounted via bootstrap/router_registry.py:250 — not here.
try:
    from routers.quick_id_proxy import public_router as quick_id_public_router
    from routers.quick_id_proxy import router as quick_id_proxy_router
    app.include_router(quick_id_proxy_router)
    app.include_router(quick_id_public_router)
    logger.info("  ✅ Quick-ID proxy router loaded")
except Exception as _qid_err:
    logger.warning(f"Quick-ID proxy router skipped: {_qid_err}")

# WhatsApp Business Cloud API — Inbound webhook (Meta verification + messages + statuses)
try:
    from routers.whatsapp_webhook import router as whatsapp_webhook_router
    app.include_router(whatsapp_webhook_router)
    logger.info("  ✅ WhatsApp webhook router loaded")
except Exception as _wa_wh_err:
    logger.warning(f"WhatsApp webhook router skipped: {_wa_wh_err}")

# Integrations Overview (super-admin) — kod hazır / API gerekli / geliştirme
try:
    from routers.integrations_overview import router as integrations_overview_router
    app.include_router(integrations_overview_router)
    logger.info("  ✅ Integrations Overview router loaded")
except Exception as _io_err:
    logger.warning(f"Integrations Overview router skipped: {_io_err}")

# Security Classification & PII Management
try:
    from security.classification_router import router as classification_router
    app.include_router(classification_router, tags=["Security — Classification & PII"])
    logger.info("  ✅ Security Classification & PII router loaded")
except Exception as _cls_err:
    logger.warning(f"Security Classification router skipped: {_cls_err}")

# Secret Rotation — Safe rotate + test + activate + rollback
try:
    from security.rotation_router import router as rotation_router
    app.include_router(rotation_router, tags=["Security — Secret Rotation"])
    logger.info("  ✅ Secret Rotation router loaded")
except Exception as _rot_err:
    logger.warning(f"Secret Rotation router skipped: {_rot_err}")

# Field-Level Encryption — At-rest PII encryption ops
try:
    from security.field_encryption_router import router as field_enc_router
    app.include_router(field_enc_router, tags=["Security — Field Encryption"])
    logger.info("  ✅ Field Encryption router loaded")
except Exception as _fenc_err:
    logger.warning(f"Field Encryption router skipped: {_fenc_err}")

# ── Notifications Router ────────────────────────────────────────────
try:
    from domains.notifications_router import router as notifications_router
    app.include_router(notifications_router, tags=["Notifications"])
    logger.info("  ✅ Notifications router loaded")
except Exception as _notif_err:
    logger.warning(f"Notifications router skipped: {_notif_err}")

# ── Ops Events & Telemetry Router ───────────────────────────────────
# Mounted via bootstrap/router_registry.py:243 — not here.

# ── Ops Timeline & Incident Correlation Router ──────────────────────
# Mounted via bootstrap/router_registry.py:244 — not here.

# ── Encryption Management Router ─────────────────────────────────────
try:
    from security.encryption_management_router import router as encryption_mgmt_router
    app.include_router(encryption_mgmt_router, tags=["Encryption Management"])
    logger.info("  ✅ Encryption Management router loaded")
except Exception as _enc_mgmt_err:
    logger.warning(f"Encryption Management router skipped: {_enc_mgmt_err}")

# ── Early Warning & Predictive Alerting Router ───────────────────────
# Mounted via bootstrap/router_registry.py:245 — not here.


# ── Lifecycle events ────────────────────────────────────────────────
from startup import on_shutdown, on_startup  # noqa: E402


@register_startup
async def _startup():
    await on_startup(app)
    try:
        from routers.integration_credentials import load_credentials_to_env
        await load_credentials_to_env()
    except Exception as _e:
        logging.getLogger(__name__).warning("integration credentials startup skipped: %s", _e)
    # Pre-create notifications compound indexes so the very first dashboard
    # poll after a cold start hits an indexed query (was 1.2s, now < 50ms).
    try:
        from domains.pms.notification_router import _ensure_notif_indexes
        await _ensure_notif_indexes()
    except Exception as _e:
        logging.getLogger(__name__).warning("notif index prewarm skipped: %s", _e)
    try:
        from core.database import db as _db
        from scripts.ensure_demo_user import ensure_demo_user
        await ensure_demo_user(_db)
    except Exception as _e:
        logging.getLogger(__name__).warning("demo user seed skipped: %s", _e)
    # v109 Bug DAJ round-4 (architect P1 follow-up): startup security guardrails.
    # Several env vars exist as breakglass / dev escape hatches that silently
    # disable webhook signature checks, retention floors, or restore safety. If
    # any are enabled in a production-flagged environment, log a CRITICAL line
    # at every boot so it appears in deployment log monitoring and can be caught
    # by operators before damage. We do not abort boot (some breakglass paths
    # are legitimate during incidents) but we make the override impossible to
    # miss in log review.
    import os as _os
    _env = (_os.environ.get("ENVIRONMENT") or _os.environ.get("APP_ENV") or "").lower()
    _is_prod = _env in ("production", "prod", "live")
    _bypass_flags = [
        "ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK",
        "ALLOW_UNSIGNED_HOTELRUNNER_WEBHOOK",
        "ALLOW_UNSIGNED_CM_WEBHOOK",
        "ALLOW_AUDIT_RETENTION_OVERRIDE",
        "ENABLE_BACKUP_RESTORE",
    ]
    _enabled = [f for f in _bypass_flags if _os.environ.get(f) == "1"]
    if _enabled:
        _log = logging.getLogger("security.startup_guardrail")
        for _flag in _enabled:
            _log.critical(
                "SECURITY_BYPASS_ENV_ENABLED flag=%s env=%s prod=%s — webhook/audit/restore "
                "safety check is DISABLED. Verify this is intentional and time-bounded.",
                _flag, _env or "unset", _is_prod,
            )
        if _is_prod:
            _log.critical(
                "SECURITY_BYPASS_ENV_PRODUCTION count=%d flags=%s — bypass(es) active in "
                "PRODUCTION environment. Disable at first opportunity.",
                len(_enabled), ",".join(_enabled),
            )
    # v109 Bug DAJ round-5 (architect P1 follow-up): trusted-proxy misconfig.
    # If EXELY_TRUST_FORWARDED=1 is set without EXELY_TRUSTED_PROXY_IPS, the
    # webhook code falls back to peer IP (safe by design), but the operator
    # almost certainly intended XFF to be honored — silently degrading to
    # peer-only allowlist matching can cause production outages OR mask an
    # attacker's spoofed XFF (the webhook now ignores it). Surface the
    # misconfig at boot.
    if _os.environ.get("EXELY_TRUST_FORWARDED") == "1":
        _spec = (_os.environ.get("EXELY_TRUSTED_PROXY_IPS") or "").strip()
        _g = logging.getLogger("security.startup_guardrail")
        if not _spec:
            _g.critical(
                "EXELY_TRUST_FORWARDED=1 without EXELY_TRUSTED_PROXY_IPS — "
                "X-Forwarded-For will NOT be honored. Set EXELY_TRUSTED_PROXY_IPS "
                "to your edge proxy IP/CIDR list to enable real-client extraction."
            )
        else:
            import ipaddress as _ipa2
            _valid = 0
            for _tok in _spec.split(","):
                _tok = _tok.strip()
                if not _tok:
                    continue
                try:
                    _ipa2.ip_network(_tok, strict=False)
                    _valid += 1
                except ValueError:
                    pass
            if _valid == 0:
                _g.critical(
                    "EXELY_TRUSTED_PROXY_IPS contains no valid IP/CIDR entries — "
                    "X-Forwarded-For will NOT be honored. Verify configuration."
                )

    # Pilot Readiness hard-blocker #1 — Exely IP-allowlist startup audit.
    # Reuses scripts/verify_exely_whitelist.verify so verdict matches the
    # CLI and readiness API exactly. We log CRITICAL when production has
    # blockers but DO NOT abort startup — the rest of the PMS must keep
    # serving even if Exely is misconfigured. Readiness/deploy smoke is
    # the gate that should reject the deploy. Counts only — no raw IPs.
    if _is_prod:
        try:
            from scripts.verify_exely_whitelist import verify as _verify_exely
            _exely_findings = _verify_exely(
                dict(_os.environ), environment=_env, expect_ips=[]
            )
            _exely_log = logging.getLogger("security.startup_guardrail")
            if _exely_findings.blockers:
                _exely_log.critical(
                    "EXELY_WHITELIST_PRODUCTION_BLOCKER verdict=%s blockers=%d "
                    "warnings=%d — run `python backend/scripts/verify_exely_whitelist.py "
                    "--env production` for redacted details. Webhook deliveries "
                    "will be rejected until configuration is fixed.",
                    _exely_findings.verdict,
                    len(_exely_findings.blockers),
                    len(_exely_findings.warnings),
                )
            elif _exely_findings.warnings:
                _exely_log.warning(
                    "EXELY_WHITELIST_PRODUCTION_REVIEW verdict=REVIEW warnings=%d — "
                    "non-blocking but operator should inspect via the CLI.",
                    len(_exely_findings.warnings),
                )
        except Exception as _exely_exc:
            logging.getLogger("security.startup_guardrail").error(
                "EXELY_WHITELIST_AUDIT_ERROR type=%s — startup audit failed; "
                "readiness check still active.",
                type(_exely_exc).__name__,
            )


@register_shutdown
async def _shutdown():
    await on_shutdown(app)


# ── Backward-compatibility re-exports ───────────────────────────────
# Many external modules do `from server import db, get_current_user, ...`
cm_push_event = None
try:
    from domains.channel_manager.router import cm_push_event  # noqa: F811
except ImportError:
    async def cm_push_event(event):
        pass

__all__ = [
    "app",
    "db",
    "client",
    "get_current_user",
    "create_token",
    "hash_password",
    "verify_password",
    "require_feature",
    "require_super_admin",
    "require_module",
    "require_admin",
    "security",
    "User",
    "JWT_SECRET",
    "JWT_ALGORITHM",
    "JWT_EXPIRATION_HOURS",
    "ChannelType",
    "apm_store",
    "get_rate_limit_stats",
    "cm_push_event",
]
