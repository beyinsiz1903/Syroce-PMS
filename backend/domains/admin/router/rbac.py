"""
rbac

Auto-split sub-router (shared imports/classes inlined).
"""

"""
Admin / Operations Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, status

from core.database import db
from core.helpers import (
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
    PermissionCheckRequest,
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


# ── POST /permissions/check ──
@router.post("/permissions/check")
async def check_permission(
    request: PermissionCheckRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_users")),  # v90 DW
):
    """Check if current user has a specific permission"""
    if not request.permission or request.permission.strip() == "":
        raise HTTPException(status_code=400, detail="Permission field is required and cannot be empty")

    try:
        perm = Permission(request.permission)
        has_perm = _has_permission(current_user.role, perm)
        return {"user_role": current_user.role, "permission": request.permission, "has_permission": has_perm}
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid permission: {request.permission}")


# ── GET /rbac/permissions/{user_role}/{resource} ──
@router.get("/rbac/permissions/{user_role}/{resource}")
async def get_resource_permissions(user_role: UserRole, resource: str, current_user: User = Depends(get_current_user)):
    """
    Get detailed permissions for a resource based on user role
    RBAC 2.0 - Granular access control
    """
    # RBAC v2 detayli izin matrisi henuz tamamlanmadi; ROLE_PERMISSIONS uzerinden
    # kaynak bazli kaba bir hak ozeti dondururuz.
    if user_role not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=404, detail="Role not found")
    role_perms = {(p.value if isinstance(p, Permission) else p) for p in ROLE_PERMISSIONS[user_role]}
    resource_match = [p for p in role_perms if resource.lower() in p.lower()]
    return {
        "user_role": user_role.value,
        "resource": resource,
        "permissions": dict.fromkeys(resource_match, True),
        "has_access": bool(resource_match),
    }


# ── GET /rbac/my-permissions ──
@router.get("/rbac/my-permissions")
async def get_my_permissions(current_user: User = Depends(get_current_user)):
    """Get current user's all resource permissions"""
    user_role = current_user.role

    if user_role not in ROLE_PERMISSIONS:
        return {"error": "Invalid role"}
    perms = [(p.value if isinstance(p, Permission) else p) for p in ROLE_PERMISSIONS[user_role]]
    return {
        "user_id": current_user.id,
        "user_name": current_user.name,
        "user_role": user_role.value,
        "permissions": perms,
    }


# ── GET /rbac/roles ──
@router.get("/rbac/roles")
async def get_available_roles(current_user: User = Depends(get_current_user)):
    """Get available roles for the current tenant's subscription tier"""
    tenant = await db.tenants.find_one({"id": current_user.tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tier = tenant.get("subscription_tier", "basic")
    tier_lower = (tier or "basic").lower()
    if tier_lower == "pro":
        tier_lower = "professional"
    if tier_lower == "ultra":
        tier_lower = "enterprise"

    allowed_roles = ROLES_BY_TIER.get(tier_lower, ROLES_BY_TIER["basic"])
    return {
        "tier": tier_lower,
        "allowed_roles": allowed_roles,
        "all_roles": [r.value for r in UserRole if r.value not in ("super_admin", "guest", "agency_admin", "agency_agent")],
    }
