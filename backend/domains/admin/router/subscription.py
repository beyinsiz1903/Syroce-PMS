"""
subscription

Auto-split sub-router (shared imports/classes inlined).
"""

"""
Admin / Operations Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status

from core.database import db
from core.helpers import (
    get_tenant_modules,
    require_super_admin_guard,
)
from core.security import (
    _is_super_admin,
    get_current_user,
)
from modules.pms_core.role_permission_service import require_op  # v90 DW

try:
    from cache_manager import cache as _cache_mgr
    from cache_manager import cached as _cm_cached
except ImportError:
    _cache_mgr = None  # type: ignore

    def _cm_cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


def _invalidate_admin_tenants_cache(tenant_id: str | None) -> None:
    """v95.3 — admin/tenants list cache'i temizle. Super-admin tenant_id ile
    set edilir; bu fonksiyon güvenli (hata fırlatmaz)."""
    if not _cache_mgr or not tenant_id:
        return
    try:
        _cache_mgr.invalidate_tenant_cache(tenant_id, "admin_tenants_list")
    except Exception:
        pass


require_super_admin = require_super_admin_guard()
from domains.admin.subscription_models import PLAN_MODULE_DEFAULTS, SUBSCRIPTION_PLANS, SubscriptionTier, get_all_module_keys, get_feature_comparison, get_plan_default_modules
from models.enums import ROLE_PERMISSIONS, Permission, UserRole
from models.schemas import User


def _has_permission(role: UserRole | str, perm: Permission) -> bool:
    """Lightweight helper: ROLE_PERMISSIONS lookup."""
    role_key = role if isinstance(role, UserRole) else UserRole(role) if role in {r.value for r in UserRole} else None
    if role_key is None:
        return False
    perms = ROLE_PERMISSIONS.get(role_key, [])
    perm_value = perm.value if isinstance(perm, Permission) else perm
    return any((p.value if isinstance(p, Permission) else p) == perm_value for p in perms)


logger = logging.getLogger(__name__)


def _svc_enc():
    try:
        from security.field_encryption import get_field_encryption_service

        return get_field_encryption_service()
    except Exception:
        return None


ROLES_BY_TIER = {
    "mini": ["admin", "front_desk", "housekeeping"],
    "basic": ["admin", "front_desk", "housekeeping"],
    "professional": ["admin", "front_desk", "housekeeping", "manager", "revenue", "night_audit", "finance", "procurement"],
    "enterprise": ["admin", "front_desk", "housekeeping", "manager", "revenue", "night_audit", "gm", "super_admin", "finance", "procurement", "supervisor", "sales"],
}


def is_role_allowed_for_tier(role: str, tier: str) -> bool:
    allowed = ROLES_BY_TIER.get(tier, ROLES_BY_TIER["basic"])
    return role in allowed


from domains.admin.schemas import (  # noqa: E402
    ChangePlanRequest,
)

# ============= CHANNEL MANAGER & RMS =============


# ============= MOBILE APP ENDPOINTS (STAFF & GUEST) =============


# ── Task #28: Kullanıcı bazlı operasyon izinleri ──────────────────────
#
# Rol-bazlı RBAC dışında bazı operasyonlar (şu an yalnız acil mesaj
# gönderme) tek tek kullanıcılara verilip alınabilsin diye User modelinde
# `granted_permissions: list[str]` alanı tutuluyor. Endpoint'ler ADMIN ve
# SUPER_ADMIN'e açık. ADMIN sadece kendi tenant'ı içindeki kullanıcılara
# yazabilir; SUPER_ADMIN her tenant'a yazabilir.

# Whitelist: kötü niyetli/yanlış izin atamalarını önlemek için kabul
# edilen izinler dar tutulur.
GRANTABLE_PERMISSIONS: set[str] = {"send_urgent_message"}


def _require_admin_for_target_user(
    current_user: User,
    target_tenant_id: str | None,
):
    """ADMIN ve SUPER_ADMIN'e izin ver; ADMIN'in başka tenant'a yazmasını
    engelle. Diğer roller 403 alır."""
    if _is_super_admin(current_user):
        return
    role_value = getattr(current_user.role, "value", str(current_user.role))
    if role_value != UserRole.ADMIN.value:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Yalnızca yöneticiler kullanıcı izinlerini düzenleyebilir.",
        )
    # ADMIN'in tenant_id'si target ile eşleşmeli.
    if not current_user.tenant_id or current_user.tenant_id != target_tenant_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )


# ── Task #32: Web push gönderim metrikleri ────────────────────────────


# ============= ADMIN TENANT INFO & TEAM MANAGEMENT =============


# ============= BILLING HISTORY & PLAN MANAGEMENT =============


# ============= HOTEL TEAM MANAGEMENT ENDPOINTS =============


# ============= DEMO ENVIRONMENT ENDPOINTS =============


# 6. GET /api/sales/follow-ups - Follow-up reminders


# ============================================================================
# COMPREHENSIVE FINANCE MODULE - CASH FLOW & RISK MANAGEMENT
# ============================================================================

# ============================================================================
# DELAYED TASKS MONITORING & PUSH NOTIFICATIONS
# ============================================================================

# MOVED: /tasks/delayed endpoint moved earlier to avoid path conflict with /tasks/{task_id}


# ============================================================================
# SYSTEM MONITORING & PERFORMANCE - APM INTEGRATED
# ============================================================================


# api_metrics is now provided by apm_store from apm_middleware.py
# Backward compat: alias api_metrics to apm_store.requests
try:
    from apm_middleware import apm_store as _apm_store_ref

    api_metrics = _apm_store_ref.requests
except ImportError:
    from collections import deque

    api_metrics = deque(maxlen=1000)

# Legacy APIMetricsMiddleware replaced by APMMiddleware in apm_middleware.py

# 1. SYSTEM PERFORMANCE MONITORING


# 1b. APM DETAILED ENDPOINT STATS


# 1c. RATE LIMIT STATUS


# 1d. DATABASE OPTIMIZATION STATUS


# 1e. RECENT ERRORS


# 2. LOG VIEWER


# 3. NETWORK PING TEST


# 4. ENDPOINT HEALTH CHECK


# ============================================================================
# OPERA CLOUD PARITY FEATURES - CRITICAL ENTERPRISE FUNCTIONALITY
# ============================================================================

# Import night audit models

# ============= 1. NIGHT AUDIT MODULE (ENTERPRISE GRADE) =============

# ============= 2. CASHIERING & CITY LEDGER MODULE =============

# ============= 3. QUEUE ROOMS MODULE (EARLY ARRIVAL MANAGEMENT) =============

# ============= AUDIT TRAIL LOGGING (AUTO-TRACKING) =============


# ──────────────────────────────────────────────────────────────────────────────
# v95.4 — Maintenance: Oda statüsü ↔ rezervasyon defteri sync
# UctanUcaTest 2026-05-02: dashboard "OCCUPANCY-DRIFT" uyarısı için kalıcı
# çözüm. KPI zaten booking ledger'ı kaynak alıyor, bu endpoint rooms.status
# tarafındaki tortu veriyi (eski non-atomic flow'lardan kalan) düzeltir.
# ──────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/api", tags=["Admin / Operations"])


# ── GET /subscription/plans ──
@router.get("/subscription/plans")
async def get_subscription_plans():
    """Get all available subscription plans"""
    return {"plans": [plan.model_dump() for plan in SUBSCRIPTION_PLANS.values()], "currency": "EUR", "tiers": [tier.value for tier in SubscriptionTier]}


# ── GET /subscription/plan-modules ──
@router.get("/subscription/plan-modules")
async def get_plan_module_defaults():
    """Get default module mapping for each subscription tier.
    Used by admin panel to show which modules are included per plan."""
    return {"plan_modules": PLAN_MODULE_DEFAULTS, "tiers": [tier.value for tier in SubscriptionTier], "all_module_keys": get_all_module_keys()}


# ── GET /subscription/features ──
@router.get("/subscription/features")
async def get_feature_comparison_endpoint():
    """Get feature comparison across all tiers"""
    return {"features": get_feature_comparison(), "tiers": [tier.value for tier in SubscriptionTier]}



from core.entitlements.enforcement import get_tenant_active_editions
from core.entitlements.registry import ENTITLEMENT_REGISTRY


async def _get_full_entitlements(tenant_id: str) -> dict:
    result = {}
    for mod_key, mod_def in ENTITLEMENT_REGISTRY.items():
        editions = await get_tenant_active_editions(tenant_id, mod_key)
        if not editions:
            continue

        features = set()
        limits = {}
        for ed in editions:
            ed_def = mod_def.editions.get(ed)
            if ed_def:
                features.update(ed_def.features)
                for lk, lv in ed_def.limits.items():
                    limits[lk] = max(limits.get(lk, 0), lv)

        result[mod_key] = {
            "editions": editions,
            "features": list(features),
            "limits": limits
        }
    return result

# ── GET /subscription/current ──
@router.get("/subscription/current")
async def get_current_subscription(current_user: User = Depends(get_current_user)):
    """Get current user's subscription"""
    tenant = await db.tenants.find_one({"id": current_user.tenant_id})

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    subscription_tier = tenant.get("subscription_tier", "basic")
    # Handle legacy tier names
    tier_map = {"pro": "professional", "ultra": "enterprise"}
    normalized_tier = tier_map.get(subscription_tier, subscription_tier)
    try:
        plan = SUBSCRIPTION_PLANS.get(SubscriptionTier(normalized_tier))
    except ValueError:
        plan = SUBSCRIPTION_PLANS.get(SubscriptionTier.BASIC)

    entitlements = await _get_full_entitlements(current_user.tenant_id)
    return {
        "tenant_id": current_user.tenant_id,
        "tier": normalized_tier,
        "plan": plan.model_dump() if plan else None,
        "status": tenant.get("subscription_status", "active"),
        "valid_until": tenant.get("subscription_valid_until"),
        "rooms_count": await db.rooms.count_documents({"tenant_id": current_user.tenant_id}),
        "users_count": await db.users.count_documents({"tenant_id": current_user.tenant_id}),
        "modules": get_tenant_modules(tenant),
        "entitlements": entitlements,
    }


# ── POST /subscription/upgrade ──
@router.post("/subscription/upgrade")
async def upgrade_subscription(
    new_tier: SubscriptionTier,
    billing_cycle: str = "monthly",  # monthly or yearly
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v90 DW
):
    """Upgrade subscription tier"""
    tenant = await db.tenants.find_one({"id": current_user.tenant_id})

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    current_tier = tenant.get("subscription_tier", "basic")
    tier_map = {"pro": "professional", "ultra": "enterprise"}
    normalized_current = tier_map.get(current_tier, current_tier)

    try:
        if SubscriptionTier(normalized_current) == new_tier:
            raise HTTPException(status_code=400, detail="Already on this tier")
    except ValueError:
        pass

    plan = SUBSCRIPTION_PLANS.get(new_tier)
    if not plan:
        raise HTTPException(status_code=400, detail="Invalid subscription tier")

    # Calculate price
    amount = plan.price_yearly if billing_cycle == "yearly" else plan.price_monthly

    # Get default modules for new tier
    new_modules = get_plan_default_modules(new_tier.value)

    # Update subscription
    await db.tenants.update_one(
        {"id": current_user.tenant_id},
        {
            "$set": {
                "subscription_tier": new_tier.value,
                "subscription_status": "active",
                "billing_cycle": billing_cycle,
                "modules": new_modules,
                "subscription_valid_until": (datetime.now(UTC) + timedelta(days=365 if billing_cycle == "yearly" else 30)).isoformat(),
                "last_billing_date": datetime.now(UTC).isoformat(),
            }
        },
    )

    return {"success": True, "message": f"Successfully upgraded to {plan.name}", "tier": new_tier.value, "amount": amount, "billing_cycle": billing_cycle}


# ── POST /subscription/change-plan ──
@router.post("/subscription/change-plan")
async def change_subscription_plan(
    payload: ChangePlanRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v90 DW
):
    """Change subscription plan (upgrade or downgrade).
    Creates a billing history record for the change."""
    tenant = await db.tenants.find_one({"id": current_user.tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if not _is_super_admin(current_user) and current_user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(status_code=403, detail="Only administrators can change the plan")

    new_tier = payload.new_tier.lower()
    if new_tier == "pro":
        new_tier = "professional"
    if new_tier == "ultra":
        new_tier = "enterprise"

    if new_tier not in ("mini", "basic", "professional", "enterprise"):
        raise HTTPException(status_code=400, detail="Invalid plan")

    current_tier = (tenant.get("subscription_tier", "basic")).lower()
    if current_tier == "pro":
        current_tier = "professional"
    if current_tier == "ultra":
        current_tier = "enterprise"

    if current_tier == new_tier:
        raise HTTPException(status_code=400, detail="You are already on this plan")

    tier_order = {"mini": 0, "basic": 1, "professional": 2, "enterprise": 3}
    is_downgrade = tier_order.get(new_tier, 0) < tier_order.get(current_tier, 0)

    try:
        plan = SUBSCRIPTION_PLANS[SubscriptionTier(new_tier)]
    except (ValueError, KeyError):
        raise HTTPException(status_code=400, detail="Invalid plan")

    # Downgrade checks: room / user limits
    if is_downgrade:
        if plan.max_rooms:
            room_count = await db.rooms.count_documents({"tenant_id": current_user.tenant_id})
            if room_count > plan.max_rooms:
                raise HTTPException(status_code=400, detail=f"Your room count ({room_count}) exceeds the target plan limit ({plan.max_rooms}). Please reduce rooms first.")
        if plan.max_users:
            user_count = await db.users.count_documents({"tenant_id": current_user.tenant_id})
            if user_count > plan.max_users:
                raise HTTPException(status_code=400, detail=f"Your user count ({user_count}) exceeds the target plan limit ({plan.max_users}). Please reduce users first.")

    amount = plan.price_yearly if payload.billing_cycle == "yearly" else plan.price_monthly
    new_modules = get_plan_default_modules(new_tier)
    now = datetime.now(UTC)
    valid_days = 365 if payload.billing_cycle == "yearly" else 30

    # Update tenant
    await db.tenants.update_one(
        {"id": current_user.tenant_id},
        {
            "$set": {
                "subscription_tier": new_tier,
                "subscription_status": "active",
                "billing_cycle": payload.billing_cycle,
                "modules": new_modules,
                "subscription_valid_until": (now + timedelta(days=valid_days)).isoformat(),
                "last_billing_date": now.isoformat(),
                "updated_at": now.isoformat(),
            }
        },
    )

    # Create billing history record
    billing_record = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "user_id": current_user.id,
        "user_name": current_user.name,
        "action": "downgrade" if is_downgrade else "upgrade",
        "from_tier": current_tier,
        "to_tier": new_tier,
        "billing_cycle": payload.billing_cycle,
        "amount": amount,
        "currency": "EUR",
        "status": "completed",
        "description": f"{'Downgrade' if is_downgrade else 'Upgrade'}: {current_tier} → {new_tier} ({payload.billing_cycle})",
        "created_at": now.isoformat(),
        "valid_until": (now + timedelta(days=valid_days)).isoformat(),
    }
    await db.billing_history.insert_one(billing_record)

    action_label = "downgraded" if is_downgrade else "upgraded"
    return {
        "success": True,
        "message": f"Plan {action_label} to {new_tier}",
        "is_downgrade": is_downgrade,
        "tier": new_tier,
        "amount": amount,
        "billing_cycle": payload.billing_cycle,
        "valid_until": (now + timedelta(days=valid_days)).isoformat(),
    }


# ── GET /billing/history ──
@router.get("/billing/history")
async def get_billing_history(current_user: User = Depends(get_current_user)):
    """Get billing / plan change history for the current hotel"""
    records = await db.billing_history.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).sort("created_at", -1).to_list(100)

    return {"records": records, "count": len(records)}
