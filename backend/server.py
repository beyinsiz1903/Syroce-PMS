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
from app import create_app  # noqa: E402

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

# Allow any *.replit.dev / *.replit.app preview when not in production
_env_mode = (os.environ.get("ENVIRONMENT") or os.environ.get("ENV") or "development").lower()
_cors_origin_regex = None
if _env_mode != "production":
    _cors_origin_regex = r"^https://[a-z0-9-]+\.(replit\.dev|replit\.app|riker\.replit\.dev)$"

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
from bootstrap.router_registry import register_routers  # noqa: E402

register_routers(app, api_router, require_super_admin_dep=require_super_admin)

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
    from routers.report_builder import init_report_builder
    from routers.report_builder import router as report_builder_router
    init_report_builder(db, get_current_user)
    app.include_router(report_builder_router, tags=["Report Builder"])
except Exception as _rb_err:
    logger.warning("Report Builder router skipped: %s", _rb_err)

try:
    from routers.guest_messaging import init_guest_messaging
    from routers.guest_messaging import router as guest_messaging_router
    init_guest_messaging(db, get_current_user)
    app.include_router(guest_messaging_router, tags=["Guest Messaging"])
except Exception as _gm_err:
    logger.warning("Guest Messaging router skipped: %s", _gm_err)

# Supplies Marketplace (B2B) — vendor portal + hotel storefront + admin
try:
    from modules.supplies_market.repository import ensure_indexes as _sm_ensure_indexes
    from modules.supplies_market.router_admin import router as _sm_admin_router
    from modules.supplies_market.router_hotel import router as _sm_hotel_router
    from modules.supplies_market.router_vendor import router as _sm_vendor_router

    app.include_router(_sm_vendor_router)
    app.include_router(_sm_hotel_router)
    app.include_router(_sm_admin_router)

    @app.on_event("startup")
    async def _supplies_market_indexes():
        await _sm_ensure_indexes()

    logger.info("✅ Supplies Marketplace routers mounted")
except Exception as _sm_err:
    logger.warning("Supplies Marketplace router skipped: %s", _sm_err)

# GraphQL
try:
    from strawberry.fastapi import GraphQLRouter

    from _legacy.graphql_schema import schema

    graphql_app = GraphQLRouter(schema, context_getter=lambda: {"db": db, "cache": None, "materialized_views": None})
    app.include_router(graphql_app, prefix="/api/graphql", tags=["graphql"])
except Exception as _gql_err:
    logger.warning("GraphQL router skipped: %s", _gql_err)

# WebSocket
try:
    from websocket_server import socket_app
    app.mount("/ws", socket_app)
except Exception as _ws_sock_err:
    logger.warning("WebSocket server skipped: %s", _ws_sock_err)

# Channel Manager — Hardening (runtime status, drift, reconciliation, etc.)
try:
    from domains.channel_manager.hardening_router import router as cm_hardening_router
    app.include_router(cm_hardening_router)
    logger.info("  ✅ Channel Manager hardening router loaded")
except Exception as _cmh_err:
    logger.warning("Channel Manager hardening router skipped: %s", _cmh_err)

# Channel Manager v2
try:
    from channel_manager.interfaces.router_registry import router as cm_v2_router
    app.include_router(cm_v2_router, tags=["Channel Manager v2"])
    logger.info("  ✅ Channel Manager v2 router loaded (connector-first architecture)")
except Exception as _cmv2_err:
    logger.warning("Channel Manager v2 router skipped: %s", _cmv2_err)

# OTA-002: Outbox Admin endpoints (requeue, replay, status)
try:
    from routers.outbox_admin import outbox_admin_router
    app.include_router(outbox_admin_router, prefix="/api", tags=["Outbox Admin"])
    logger.info("  ✅ OTA Outbox Admin router loaded (requeue/replay/status)")
except Exception as _outbox_err:
    logger.warning("Outbox Admin router skipped: %s", _outbox_err)

# Webhook Admin endpoints (deliveries, DLQ, manual retry)
try:
    from routers.webhook_admin import webhook_admin_router
    app.include_router(webhook_admin_router, prefix="/api", tags=["Webhook Admin"])
    logger.info("  ✅ Webhook Admin router loaded (deliveries/DLQ/retry)")
except Exception as _wh_err:
    logger.warning("Webhook Admin router skipped: %s", _wh_err)

# DATA-001: Import Admin endpoints (review queue, retry, approve, dismiss)
try:
    from routers.import_admin import import_admin_router
    app.include_router(import_admin_router, prefix="/api", tags=["Import Admin"])
    logger.info("  ✅ Import Admin router loaded (DATA-001 review queue/retry)")
except Exception as _import_err:
    logger.warning("Import Admin router skipped: %s", _import_err)

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
try:
    from routers.quick_id_proxy import router as quick_id_proxy_router
    app.include_router(quick_id_proxy_router)
    from routers.room_qr_requests import router as room_qr_router
    app.include_router(room_qr_router)
    logger.info("  ✅ Quick-ID proxy router loaded")
except Exception as _qid_err:
    logger.warning(f"Quick-ID proxy router skipped: {_qid_err}")

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
try:
    from routers.ops_events_router import router as ops_events_router
    app.include_router(ops_events_router, tags=["Ops Events & Telemetry"])
    logger.info("  ✅ Ops Events & Telemetry router loaded")
except Exception as _ops_err:
    logger.warning(f"Ops Events router skipped: {_ops_err}")

# ── Ops Timeline & Incident Correlation Router ──────────────────────
try:
    from routers.ops_timeline_router import router as ops_timeline_router
    app.include_router(ops_timeline_router, tags=["Ops Timeline & Incidents"])
    logger.info("  ✅ Ops Timeline & Incidents router loaded")
except Exception as _timeline_err:
    logger.warning(f"Ops Timeline router skipped: {_timeline_err}")

# ── Encryption Management Router ─────────────────────────────────────
try:
    from security.encryption_management_router import router as encryption_mgmt_router
    app.include_router(encryption_mgmt_router, tags=["Encryption Management"])
    logger.info("  ✅ Encryption Management router loaded")
except Exception as _enc_mgmt_err:
    logger.warning(f"Encryption Management router skipped: {_enc_mgmt_err}")

# ── Early Warning & Predictive Alerting Router ───────────────────────
try:
    from routers.early_warning_router import router as early_warning_router
    app.include_router(early_warning_router, tags=["Early Warning & Predictive"])
    logger.info("  ✅ Early Warning router loaded")
except Exception as _ew_err:
    logger.warning(f"Early Warning router skipped: {_ew_err}")


# ── Lifecycle events ────────────────────────────────────────────────
from startup import on_shutdown, on_startup  # noqa: E402


@app.on_event("startup")
async def _startup():
    await on_startup(app)


@app.on_event("shutdown")
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
