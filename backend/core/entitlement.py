"""
Entitlement Enforcement Middleware
Intercepts API requests and enforces plan-based access + quota limits.
Integrates with metering to record usage events.
"""
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from core.database import db
from core.metering import record_usage, UsageEventType

logger = logging.getLogger(__name__)

# ─── Route → Required Module Mapping ───
# Routes that require specific modules to be enabled.
# If a route prefix matches and the tenant doesn't have the module, return 403.
ROUTE_MODULE_MAP: Dict[str, str] = {
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


def _get_token_from_request(request: Request) -> Optional[str]:
    """Extract JWT token from Authorization header."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        return auth[7:]
    return None


def _decode_tenant_from_token(token: str) -> Optional[str]:
    """Decode tenant_id from JWT without full validation (for middleware speed)."""
    try:
        import jwt
        import os
        secret = os.environ.get("JWT_SECRET", "secret-key-change-in-production")
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        return payload.get("tenant_id")
    except Exception:
        return None


class EntitlementMiddleware(BaseHTTPMiddleware):
    """Global middleware that:
    1. Records API usage per tenant (metering)
    2. Enforces module-level access based on tenant plan
    3. Checks quota limits (rooms, users)
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method

        # Skip non-API routes
        if not path.startswith("/api/"):
            return await call_next(request)

        # Skip exempt routes
        for prefix in EXEMPT_PREFIXES:
            if path.startswith(prefix):
                return await call_next(request)

        # Skip OPTIONS
        if method == "OPTIONS":
            return await call_next(request)

        # Extract tenant from token
        token = _get_token_from_request(request)
        tenant_id = None
        if token:
            tenant_id = _decode_tenant_from_token(token)

        # Record API usage (fire-and-forget)
        if tenant_id:
            try:
                await record_usage(tenant_id, UsageEventType.API_CALL)
            except Exception:
                pass

        # Module enforcement
        if tenant_id:
            required_module = self._match_route_module(path)
            if required_module:
                allowed = await self._check_module_access(tenant_id, required_module)
                if not allowed:
                    return JSONResponse(
                        status_code=403,
                        content={
                            "detail": f"Bu ozellik planınıza dahil degil: {required_module}",
                            "error_code": "ENTITLEMENT_DENIED",
                            "required_module": required_module,
                            "upgrade_url": "/settings?tab=subscription",
                        },
                    )

        start = time.time()
        response = await call_next(request)
        elapsed_ms = (time.time() - start) * 1000

        # Add entitlement headers
        if tenant_id:
            response.headers["X-Tenant-ID"] = tenant_id
        response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.1f}"

        return response

    def _match_route_module(self, path: str) -> Optional[str]:
        """Find the required module for a given route path."""
        for prefix, module in ROUTE_MODULE_MAP.items():
            if path.startswith(prefix):
                return module
        return None

    async def _check_module_access(self, tenant_id: str, module: str) -> bool:
        """Check if tenant has access to the required module."""
        try:
            tenant_doc = await db.tenants.find_one({"id": tenant_id}, {"_id": 0, "modules": 1, "subscription_tier": 1})
            if not tenant_doc:
                return True  # Let downstream handle missing tenant

            from core.helpers import get_tenant_modules
            modules = get_tenant_modules(tenant_doc)
            return bool(modules.get(module, False))
        except Exception as e:
            logger.warning(f"Entitlement check error: {e}")
            return True  # Fail open on errors


async def check_quota(tenant_id: str, resource: str) -> Dict[str, Any]:
    """Check if tenant is within quota limits.
    Uses _raw_db for cross-tenant admin queries.

    Returns: {"allowed": bool, "current": int, "limit": int|None, "resource": str}
    """
    from subscription_models import SUBSCRIPTION_PLANS, SubscriptionTier
    from core.database import _raw_db

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


async def get_tenant_entitlements(tenant_id: str) -> Dict[str, Any]:
    """Get full entitlement view for a tenant.
    Uses _raw_db for cross-tenant admin queries.
    """
    from subscription_models import SUBSCRIPTION_PLANS, SubscriptionTier
    from core.helpers import get_tenant_modules
    from core.feature_flags import is_flag_enabled
    from core.database import _raw_db

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
            if datetime.now(timezone.utc) > end_dt:
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
