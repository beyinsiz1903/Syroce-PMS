"""
server.py — Bootstrap Orchestrator

This is the uvicorn entrypoint.  It creates the FastAPI app, registers
middleware and routers via bootstrap modules, wires startup/shutdown
lifecycle events, and re-exports key symbols for backward compatibility.

All endpoint definitions live in domain-specific router modules under
domains/ and routers/.

Target: < 300 lines.
"""
import os
import logging
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

# ── Core (single-instance DB, auth) ────────────────────────────────
from core.database import db, client  # noqa: E402
from core.security import (  # noqa: E402
    get_current_user,
    create_token,
    hash_password,
    verify_password,
    security,
    JWT_SECRET,
    JWT_ALGORITHM,
    JWT_EXPIRATION_HOURS,
)
from core.helpers import (  # noqa: E402
    require_feature,
    require_super_admin_guard,
    require_module,
    require_admin,
)
from models.schemas import User  # noqa: E402
from models.enums import ChannelType  # noqa: E402

# Backward compat alias
require_super_admin = require_super_admin_guard()

# Expose db on app.state early
app.state.db = db

# ── Middleware (via bootstrap) ──────────────────────────────────────
from bootstrap.middleware_registry import register_middleware  # noqa: E402

register_middleware(app)

# Additional CORS with explicit origins
from starlette.middleware.cors import CORSMiddleware  # noqa: E402

_cors_raw = os.environ.get("CORS_ORIGINS", "")
_cors_origins = [o.strip() for o in _cors_raw.split(",") if o.strip()] if _cors_raw else []
_always_allowed = [
    "https://pms.syroce.com",
    "https://www.pms.syroce.com",
    "https://syroce.com",
    "http://localhost:3000",
]
for origin in _always_allowed:
    if origin not in _cors_origins:
        _cors_origins.append(origin)
if not _cors_origins:
    _cors_origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=_cors_origins,
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
    from datetime import datetime, timezone

    class _FallbackStore:
        requests = deque(maxlen=100)
        rate_limit_hits = 0
        started_at = datetime.now(timezone.utc)
        def get_summary(self, minutes=10): return {"total_requests": 0, "error_rate_percent": 0}
        def get_recent_errors(self, limit=50): return []
        def record_request(self, **kw): pass
        def record_rate_limit_hit(self, p): pass

    apm_store = _FallbackStore()
    def get_rate_limit_stats(): return {}

# Request tracing
try:
    from modules.observability.request_tracing_middleware import RequestTracingMiddleware
    app.add_middleware(RequestTracingMiddleware)
except Exception:
    pass

# ── Global exception handler for Exely provider errors ──────────────
from fastapi import Request
from fastapi.responses import JSONResponse
try:
    from domains.channel_manager.providers.exely.errors import ExelyError

    @app.exception_handler(ExelyError)
    async def exely_error_handler(request: Request, exc: ExelyError):
        return JSONResponse(status_code=502, content={"detail": f"Exely provider hatasi: {exc.message}"})
except ImportError:
    pass

# ── Additional API router (AI endpoints) ─────────────────────────────
from fastapi import APIRouter
api_router = APIRouter(prefix="/api")

try:
    from ai_endpoints import api_router as ai_ai_router
    api_router.include_router(ai_ai_router, tags=["AI Intelligence"])
    logger.info("  ✅ AI Intelligence endpoints loaded")
except Exception:
    pass

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
_optional_factory_routers = [
    ("security_2fa", "create_2fa_routes", "2FA Security"),
    ("ip_access_control", "create_ip_access_routes", "IP Access Control"),
    ("gdpr_compliance", "create_gdpr_routes", "GDPR/KVKK Compliance"),
    ("central_office_endpoints", "create_central_office_routes", "Central Office Dashboard"),
    ("central_pricing_endpoints", "create_central_pricing_routes", "Central Pricing"),
    ("cross_property_guests", "create_cross_property_guest_routes", "Cross-Property Guests"),
    ("ml_real_models", "create_ml_routes", "ML/AI Models"),
    ("tenant_isolation", "create_tenant_isolation_routes", "Tenant Isolation"),
    ("pci_dss_compliance", "create_pci_dss_routes", "PCI DSS Compliance"),
]

for mod_name, factory_name, tag in _optional_factory_routers:
    try:
        mod = __import__(mod_name)
        factory = getattr(mod, factory_name)
        router = factory(db, get_current_user)
        app.include_router(router, tags=[tag])
        logger.info(f"  ✅ {tag}")
    except Exception:
        pass

# Report Builder & Guest Messaging (init pattern)
try:
    from routers.report_builder import router as report_builder_router, init_report_builder
    init_report_builder(db, get_current_user)
    app.include_router(report_builder_router, tags=["Report Builder"])
except Exception:
    pass

try:
    from routers.guest_messaging import router as guest_messaging_router, init_guest_messaging
    init_guest_messaging(db, get_current_user)
    app.include_router(guest_messaging_router, tags=["Guest Messaging"])
except Exception:
    pass

# GraphQL
try:
    from strawberry.fastapi import GraphQLRouter
    from graphql_schema import schema

    graphql_app = GraphQLRouter(schema, context_getter=lambda: {"db": db, "cache": None, "materialized_views": None})
    app.include_router(graphql_app, prefix="/api/graphql", tags=["graphql"])
except Exception:
    pass

# WebSocket
try:
    from websocket_server import socket_app
    app.mount("/ws", socket_app)
except Exception:
    pass

# Channel Manager — Hardening (runtime status, drift, reconciliation, etc.)
try:
    from domains.channel_manager.hardening_router import router as cm_hardening_router
    app.include_router(cm_hardening_router)
    print("✅ Channel Manager hardening router included")
except Exception:
    pass

# Channel Manager v2
try:
    from channel_manager.interfaces.router_registry import router as cm_v2_router
    app.include_router(cm_v2_router, tags=["Channel Manager v2"])
    print("✅ Channel Manager v2 router included (connector-first architecture)")
except Exception:
    pass

# ── Lifecycle events ────────────────────────────────────────────────
from startup import on_startup, on_shutdown  # noqa: E402


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
