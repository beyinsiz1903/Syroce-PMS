"""
Entitlement Enforcement Middleware
Intercepts API requests and enforces plan-based access + quota limits.
Integrates with metering to record usage events.

Uses pure ASGI middleware (not BaseHTTPMiddleware) to avoid event-loop
conflicts in async test runners and improve performance.
"""
import logging
import time
from datetime import UTC, datetime
from typing import Any

from starlette.datastructures import MutableHeaders
from starlette.responses import JSONResponse

from core.database import db
from core.metering import UsageEventType, record_usage

logger = logging.getLogger(__name__)

# ─── Route → Required Module Mapping ───
ROUTE_MODULE_MAP: dict[str, str] = {
    "/api/channel-manager": "channel_manager",
    "/api/cm/": "channel_manager",
    "/api/webhooks/exely": "channel_manager",
    "/api/webhooks/hotelrunner": "channel_manager",
    "/api/lockdown": "channel_manager",
    "/api/night-audit": "night_audit",
    "/api/pos/": "invoices",
    "/api/revenue/": "revenue_management",
    "/api/rms/": "revenue_management",
    "/api/ai/": "ai",
    "/api/sales/": "sales_crm",
    "/api/groups/": "group_sales",
    "/api/loyalty/": "loyalty_program",
    "/api/analytics/gm": "gm_dashboards",
    "/api/marketplace/": "channel_manager",
    # Marketplace-purchased integration. Aliases (quick_id_integration)
    # are resolved inside core.subscriptions.tenant_has_module.
    "/api/quick-id/": "quick_id",
    # Add-on modules — sold separately, default OFF for all tiers.
    # Super-admin enables per-tenant from Admin > Modül Yönetimi.
    "/api/spa": "spa",
    "/api/mice": "mice",
    # Syroce Academy — add-on training module, default OFF for all tiers.
    "/api/academy/": "academy",
    # Syroce Contact Center — omnichannel add-on, default OFF for all tiers.
    "/api/contact-center/": "contact_center",
    # Alternate MICE entry-point in sales router (Meeting & Events).
    # Without this mapping, MICE-equivalent functionality is reachable
    # via /api/events/* even when the `mice` add-on is disabled.
    "/api/events/": "mice",
    # NOTE: /api/mailing/ is intentionally NOT entitlement-gated.
    # Mailing is sold as credit packs and is enforced at send-time
    # by the mailing credit balance check, not by route gating.
}

# Routes that are always allowed (no module check needed)
EXEMPT_PREFIXES = [
    "/api/auth/",
    "/api/health",
    "/api/admin/",
    "/api/subscription/",
    "/api/hotel/",
    "/api/demo/",
    "/api/settings/",
    "/api/system/",
    "/api/ops/",
    "/api/rbac/",
    "/api/permissions/",
    "/api/billing/",
    "/api/docs",
    "/api/openapi",
    "/api/pms-lite/",
]


def _get_token_from_headers(headers: list) -> str | None:
    """Extract JWT token from raw ASGI headers."""
    for key, value in headers:
        if key == b"authorization":
            val = value.decode("latin-1")
            if val.startswith("Bearer "):
                return val[7:]
    return None


def _decode_tenant_from_token(token: str) -> str | None:
    """Decode tenant_id from JWT.

    Uses the SAME secret as core.security so middleware and auth layer
    cannot diverge (which would silently bypass entitlement checks).
    """
    try:
        import jwt

        from core.security import JWT_SECRET
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload.get("tenant_id")
    except Exception:
        return None


def _decode_token_payload(token: str) -> dict | None:
    """Decode the full JWT payload (used to read user_id alongside tenant_id)."""
    try:
        import jwt

        from core.security import JWT_SECRET
        return jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
    except Exception:
        return None


# Lightweight in-process TTL cache for super-admin lookups in the
# entitlement middleware. Entries expire after 60 seconds so role
# revocations are reflected reasonably quickly without hitting the DB
# on every API call.
_SUPER_ADMIN_CACHE: dict[str, tuple[bool, float]] = {}
_SUPER_ADMIN_TTL_SECONDS = 60.0
_SUPER_ADMIN_CACHE_MAX = 512


def _local_evict_super_admin(user_id: str | None = None) -> None:
    """Drop super-admin lookup cache entries on THIS worker only.

    Wired into the same user-doc invalidation flow that profile/password/
    role changes already trigger (``core.security.invalidate_user_doc_cache``
    locally + the ``auth_cache_pubsub`` listener cross-worker), so a role
    change is reflected fleet-wide within milliseconds instead of waiting
    up to ``_SUPER_ADMIN_TTL_SECONDS``.

    Like the user/tenant doc evictors, this is *evict-only* and never
    re-publishes — the listener calls it on receipt, so it must not loop.
    Crucially, only eviction crosses Redis: the authoritative super_admin
    decision is always re-read from the DB by ``_is_super_admin_user`` on
    the next request (fail-closed — Redis can never assert super_admin=True).
    """
    if user_id is None:
        _SUPER_ADMIN_CACHE.clear()
    else:
        _SUPER_ADMIN_CACHE.pop(user_id, None)


async def _is_super_admin_user(user_id: str) -> bool:
    """Return True if *user_id* corresponds to a super_admin user.

    Uses a small TTL cache so the middleware does not pay a DB roundtrip
    on every authenticated request.
    """
    if not user_id:
        return False
    now = time.time()
    cached = _SUPER_ADMIN_CACHE.get(user_id)
    if cached and (now - cached[1]) < _SUPER_ADMIN_TTL_SECONDS:
        return cached[0]
    try:
        # Legacy user docs may key by "user_id" instead of "id".
        doc = await db.users.find_one(
            {"$or": [{"id": user_id}, {"user_id": user_id}]},
            {"_id": 0, "role": 1, "roles": 1},
        )
    except Exception:
        return False
    is_sa = False
    if doc:
        if (doc.get("role") or "") == "super_admin":
            is_sa = True
        else:
            roles = doc.get("roles") or []
            if isinstance(roles, list) and "super_admin" in roles:
                is_sa = True
    # Bound cache size with a simple eviction of oldest entries.
    if len(_SUPER_ADMIN_CACHE) >= _SUPER_ADMIN_CACHE_MAX:
        try:
            oldest = min(_SUPER_ADMIN_CACHE.items(), key=lambda kv: kv[1][1])[0]
            _SUPER_ADMIN_CACHE.pop(oldest, None)
        except ValueError:
            pass
    _SUPER_ADMIN_CACHE[user_id] = (is_sa, now)
    return is_sa


def _match_route_module(path: str) -> str | None:
    """Find the required module for a given route path."""
    for prefix, module in ROUTE_MODULE_MAP.items():
        if path.startswith(prefix):
            return module
    return None


async def check_module_access(tenant_id: str, module: str) -> bool:
    """Public re-export of `_check_module_access` for use by routes that
    bypass the path-based middleware (e.g. B2B API-key endpoints whose
    tenant is resolved from an agency record, not a JWT)."""
    return await _check_module_access(tenant_id, module)


async def _check_module_access(tenant_id: str, module: str) -> bool:
    """Check if tenant has access to the required module.

    Access granted when EITHER:
    1. The tenant's plan includes the module (legacy `modules` map), OR
    2. There is an active marketplace subscription for the module key
       (tenant_subscriptions, status=active, end_date in the future).
    """
    try:
        tenant_doc = await db.tenants.find_one(
            {"id": tenant_id}, {"_id": 0, "modules": 1, "subscription_tier": 1}
        )
        if not tenant_doc:
            return True

        from core.helpers import get_tenant_modules
        modules = get_tenant_modules(tenant_doc)
        if modules.get(module, False):
            return True

        # Fall back to marketplace subscription check.
        from core.subscriptions import tenant_has_module
        return await tenant_has_module(tenant_id, module)
    except Exception as e:
        # Fail CLOSED on errors so a transient DB outage cannot
        # silently grant access to paid modules. The middleware only
        # reaches this code path when a route IS module-gated.
        logger.error(f"Entitlement check error for module={module}: {e}")
        return False


class EntitlementMiddleware:
    """Pure ASGI middleware for entitlement enforcement.
    1. Records API usage per tenant (metering)
    2. Enforces module-level access based on tenant plan
    3. Adds X-Tenant-ID and X-Response-Time-Ms headers
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        method = scope.get("method", "GET")

        # Skip non-API routes
        if not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return

        # Skip exempt routes
        for prefix in EXEMPT_PREFIXES:
            if path.startswith(prefix):
                await self.app(scope, receive, send)
                return

        # Skip OPTIONS
        if method == "OPTIONS":
            await self.app(scope, receive, send)
            return

        # Extract tenant + user from token
        raw_headers = scope.get("headers", [])
        token = _get_token_from_headers(raw_headers)
        tenant_id = None
        user_id = None
        if token:
            payload = _decode_token_payload(token)
            if payload:
                tenant_id = payload.get("tenant_id")
                user_id = payload.get("user_id")

        # Record API usage (fire-and-forget)
        if tenant_id:
            try:
                await record_usage(tenant_id, UsageEventType.API_CALL)
            except Exception:
                pass

        # Module enforcement (super_admin bypasses paid-module gating)
        if tenant_id:
            required_module = _match_route_module(path)
            if required_module:
                if user_id and await _is_super_admin_user(user_id):
                    allowed = True
                else:
                    allowed = await _check_module_access(tenant_id, required_module)
                if not allowed:
                    resp = JSONResponse(
                        status_code=403,
                        content={
                            "detail": f"Bu ozellik planınıza dahil degil: {required_module}",
                            "error_code": "ENTITLEMENT_DENIED",
                            "required_module": required_module,
                            "upgrade_url": "/settings?tab=subscription",
                        },
                    )
                    await resp(scope, receive, send)
                    return

        # Wrap send to inject response headers
        start = time.time()

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if tenant_id:
                    headers.append("X-Tenant-ID", tenant_id)
                elapsed_ms = (time.time() - start) * 1000
                headers.append("X-Response-Time-Ms", f"{elapsed_ms:.1f}")
            await send(message)

        await self.app(scope, receive, send_with_headers)


async def check_quota(tenant_id: str, resource: str) -> dict[str, Any]:
    """Check if tenant is within quota limits.
    Uses _raw_db for cross-tenant admin queries.

    Returns: {"allowed": bool, "current": int, "limit": int|None, "resource": str}
    """
    from core.database import _raw_db
    from domains.admin.subscription_models import SUBSCRIPTION_PLANS, SubscriptionTier

    tenant = await _raw_db.tenants.find_one({"id": tenant_id}, {"_id": 0, "subscription_tier": 1})
    if not tenant:
        return {"allowed": True, "current": 0, "limit": None, "resource": resource}

    tier = (tenant.get("subscription_tier") or "basic").lower()
    tier_map = {"pro": "professional", "ultra": "enterprise"}
    tier = tier_map.get(tier, tier)

    try:
        plan = SUBSCRIPTION_PLANS[SubscriptionTier(tier)]
    except (ValueError, KeyError):
        return {"allowed": True, "current": 0, "limit": None, "resource": resource}

    if resource == "rooms":
        current = await _raw_db.rooms.count_documents({"tenant_id": tenant_id})
        limit = plan.max_rooms
    elif resource == "users":
        current = await _raw_db.users.count_documents({"tenant_id": tenant_id})
        limit = plan.max_users
    else:
        return {"allowed": True, "current": 0, "limit": None, "resource": resource}

    return {
        "allowed": limit is None or current < limit,
        "current": current,
        "limit": limit,
        "resource": resource,
    }


async def get_tenant_entitlements(tenant_id: str) -> dict[str, Any]:
    """Get full entitlement view for a tenant.
    Uses _raw_db for cross-tenant admin queries.
    """
    from core.database import _raw_db
    from core.helpers import get_tenant_modules
    from domains.admin.subscription_models import SUBSCRIPTION_PLANS, SubscriptionTier

    tenant = await _raw_db.tenants.find_one({"id": tenant_id}, {"_id": 0})
    if not tenant:
        return {"error": "Tenant not found"}

    tier = (tenant.get("subscription_tier") or "basic").lower()
    tier_map = {"pro": "professional", "ultra": "enterprise"}
    tier = tier_map.get(tier, tier)

    try:
        plan = SUBSCRIPTION_PLANS[SubscriptionTier(tier)]
    except (ValueError, KeyError):
        plan = SUBSCRIPTION_PLANS[SubscriptionTier.BASIC]

    modules = get_tenant_modules(tenant)

    # Quota checks
    rooms_quota = await check_quota(tenant_id, "rooms")
    users_quota = await check_quota(tenant_id, "users")

    # Subscription status
    sub_end = tenant.get("subscription_end_date")
    sub_status = tenant.get("subscription_status", "active")
    is_expired = False
    if sub_end:
        try:
            end_dt = datetime.fromisoformat(sub_end.replace("Z", "+00:00"))
            if datetime.now(UTC) > end_dt:
                is_expired = True
                sub_status = "expired"
        except Exception:
            pass

    return {
        "tenant_id": tenant_id,
        "property_name": tenant.get("property_name"),
        "tier": tier,
        "plan_name": plan.name,
        "subscription_status": sub_status,
        "is_expired": is_expired,
        "modules": modules,
        "quotas": {
            "rooms": rooms_quota,
            "users": users_quota,
        },
        "plan_limits": {
            "max_rooms": plan.max_rooms,
            "max_users": plan.max_users,
            "support_level": plan.support_level,
        },
    }
