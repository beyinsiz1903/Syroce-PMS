"""
hotel

Auto-split sub-router (shared imports/classes inlined).
"""
"""
Admin / Operations Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, datetime

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
from domains.admin.subscription_models import SUBSCRIPTION_PLANS, SubscriptionTier
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
from security.encrypted_lookup import (
    build_user_email_query,
    decrypt_user_doc,
    encrypt_user_doc,
)

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


from core.security import hash_password
from domains.admin.schemas import (  # noqa: E402
    CreateTeamMemberRequest,
    UpdateHotelInfoRequest,
    UpdateTeamMemberRoleRequest,
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
    current_user: User, target_tenant_id: str | None,
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


# ── PATCH /hotel/info ──
@router.patch("/hotel/info")
async def update_hotel_info(
    payload: UpdateHotelInfoRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """Update hotel/tenant information (admin only)"""
    if not _is_super_admin(current_user) and current_user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(status_code=403, detail="Only administrators can update hotel information")

    tenant = await db.tenants.find_one({"id": current_user.tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Hotel not found")

    update_data = {}
    if payload.property_name is not None:
        update_data["property_name"] = payload.property_name
    if payload.phone is not None:
        update_data["phone"] = payload.phone
        update_data["contact_phone"] = payload.phone
    if payload.email is not None:
        update_data["email"] = payload.email
        update_data["contact_email"] = payload.email
    if payload.address is not None:
        update_data["address"] = payload.address
    if payload.location is not None:
        update_data["location"] = payload.location
    if payload.description is not None:
        update_data["description"] = payload.description
    if payload.total_rooms is not None:
        # Check plan limit
        tier = (tenant.get("subscription_tier", "basic")).lower()
        if tier == "pro": tier = "professional"
        if tier == "ultra": tier = "enterprise"
        try:
            plan = SUBSCRIPTION_PLANS[SubscriptionTier(tier)]
            if plan.max_rooms and payload.total_rooms > plan.max_rooms:
                raise HTTPException(
                    status_code=400,
                    detail=f"Your plan room limit: {plan.max_rooms}. Upgrade your plan for more rooms."
                )
        except (ValueError, KeyError):
            pass
        update_data["total_rooms"] = payload.total_rooms

    if not update_data:
        raise HTTPException(status_code=400, detail="No field to update")

    update_data["updated_at"] = datetime.now(UTC).isoformat()
    await db.tenants.update_one({"id": current_user.tenant_id}, {"$set": update_data})

    updated = await db.tenants.find_one({"id": current_user.tenant_id}, {"_id": 0})
    return {
        "success": True,
        "message": "Hotel information updated",
        "tenant": updated,
    }
# ── GET /hotel/team ──
@router.get("/hotel/team")
async def list_hotel_team(current_user: User = Depends(get_current_user)):
    """List all team members for the current hotel (hotel admin only)"""
    if not _is_super_admin(current_user) and current_user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(status_code=403, detail="Only administrators can view team members")

    users_raw = await db.users.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0, "hashed_password": 0, "password_hash": 0, "password": 0}
    ).to_list(200)
    users = [decrypt_user_doc(u) for u in users_raw]

    # Get tier info
    tenant = await db.tenants.find_one({"id": current_user.tenant_id})
    tier = (tenant.get("subscription_tier", "basic") if tenant else "basic").lower()
    if tier == "pro": tier = "professional"
    if tier == "ultra": tier = "enterprise"

    allowed_roles = ROLES_BY_TIER.get(tier, ROLES_BY_TIER["basic"])

    # Max users check
    plan = SUBSCRIPTION_PLANS.get(SubscriptionTier(tier))
    max_users = plan.max_users if plan and plan.max_users else 999

    return {
        "users": users,
        "count": len(users),
        "tier": tier,
        "allowed_roles": allowed_roles,
        "max_users": max_users,
        "can_add": len(users) < max_users,
    }
# ── POST /hotel/team ──
@router.post("/hotel/team")
async def add_team_member(
    payload: CreateTeamMemberRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """Add a new team member to the current hotel"""
    if not _is_super_admin(current_user) and current_user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(status_code=403, detail="Only administrators can add team members")

    # Get tenant tier
    tenant = await db.tenants.find_one({"id": current_user.tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Hotel not found")

    tier = (tenant.get("subscription_tier", "basic")).lower()
    if tier == "pro": tier = "professional"
    if tier == "ultra": tier = "enterprise"

    # RBAC: Check if role is allowed for tier
    if not is_role_allowed_for_tier(payload.role, tier):
        allowed = ROLES_BY_TIER.get(tier, ROLES_BY_TIER["basic"])
        raise HTTPException(
            status_code=400,
            detail=f"Role '{payload.role}' is not available for the {tier} plan. Allowed roles: {', '.join(allowed)}"
        )

    # Max users check
    plan = SUBSCRIPTION_PLANS.get(SubscriptionTier(tier))
    max_users = plan.max_users if plan and plan.max_users else 999
    current_count = await db.users.count_documents({"tenant_id": current_user.tenant_id})
    if current_count >= max_users:
        raise HTTPException(
            status_code=400,
            detail=f"User limit reached ({max_users}). Upgrade your plan to add more users."
        )

    # Check duplicate email
    existing = await db.users.find_one(build_user_email_query(payload.email))
    if existing:
        raise HTTPException(status_code=400, detail="This email address is already registered")

    hashed = hash_password(payload.password)
    new_user = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "email": payload.email,
        "name": payload.name,
        "phone": payload.phone or "",
        "role": payload.role,
        "is_active": True,
        "hashed_password": hashed,
        "created_at": datetime.now(UTC).isoformat(),
    }
    new_user = encrypt_user_doc(new_user)
    await db.users.insert_one(new_user)

    return {
        "success": True,
        "message": f"{payload.name} added successfully ({payload.role})",
        "user_id": new_user["id"],
    }
# ── PATCH /hotel/team/{user_id}/role ──
@router.patch("/hotel/team/{user_id}/role")
async def update_team_member_role(
    user_id: str,
    payload: UpdateTeamMemberRoleRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """Update a team member's role"""
    if not _is_super_admin(current_user) and current_user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(status_code=403, detail="Only administrators can change roles")

    # Find team member
    target = await db.users.find_one({"id": user_id, "tenant_id": current_user.tenant_id})
    if not target:
        raise HTTPException(status_code=404, detail="Team member not found")

    # Can't change own role
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot change your own role")

    # Can't change super_admin
    if target.get("role") == "super_admin":
        raise HTTPException(status_code=400, detail="Super Admin role cannot be changed")

    # Tier check
    tenant = await db.tenants.find_one({"id": current_user.tenant_id})
    tier = (tenant.get("subscription_tier", "basic") if tenant else "basic").lower()
    if tier == "pro": tier = "professional"
    if tier == "ultra": tier = "enterprise"

    if not is_role_allowed_for_tier(payload.role, tier):
        allowed = ROLES_BY_TIER.get(tier, ROLES_BY_TIER["basic"])
        raise HTTPException(
            status_code=400,
            detail=f"Role '{payload.role}' is not available for the {tier} plan. Allowed: {', '.join(allowed)}"
        )

    # v106 audit T03 spot-fix: defense-in-depth — tenant-scope the update
    # filter. find_one above already enforces tenant; this closes a TOCTOU
    # window where a concurrent re-tenant could leak a role write.
    res = await db.users.update_one(
        {"id": user_id, "tenant_id": current_user.tenant_id},
        {"$set": {"role": payload.role}},
    )
    if res.matched_count == 0:
        raise HTTPException(status_code=409, detail="User changed concurrently, retry")
    return {"success": True, "message": f"Role updated: {payload.role}"}
# ── DELETE /hotel/team/{user_id} ──
@router.delete("/hotel/team/{user_id}")
async def remove_team_member(
    user_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """Remove a team member"""
    if not _is_super_admin(current_user) and current_user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(status_code=403, detail="Only administrators can remove members")

    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot remove yourself")

    target = await db.users.find_one({"id": user_id, "tenant_id": current_user.tenant_id})
    if not target:
        raise HTTPException(status_code=404, detail="Team member not found")
    if target.get("role") == "super_admin":
        raise HTTPException(status_code=400, detail="Super Admin cannot be deleted")

    await db.users.delete_one({"id": user_id, "tenant_id": current_user.tenant_id})
    return {"success": True, "message": "Team member removed"}
