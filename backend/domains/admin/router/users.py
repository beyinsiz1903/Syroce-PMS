"""
users

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
from models.schemas import UpdateUserRoleRequest, User


def _has_permission(role: UserRole | str, perm: Permission) -> bool:
    """Lightweight helper: ROLE_PERMISSIONS lookup."""
    role_key = role if isinstance(role, UserRole) else UserRole(role) if role in {r.value for r in UserRole} else None
    if role_key is None:
        return False
    perms = ROLE_PERMISSIONS.get(role_key, [])
    perm_value = perm.value if isinstance(perm, Permission) else perm
    return any((p.value if isinstance(p, Permission) else p) == perm_value for p in perms)
from security.encrypted_lookup import (
    decrypt_user_doc,
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


from core.audit import log_audit_event  # Task #28
from domains.admin.schemas import (  # noqa: E402
    UpdateGrantedPermissionsRequest,
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


# ── GET /admin/users ──
@router.get("/admin/users")
async def list_all_users(
    email_filter: str | None = None,
    role_filter: str | None = None,
    tenant_id_filter: str | None = None,
    current_user: User = Depends(require_super_admin)
):
    """List all users in the system (SUPER ADMIN only)"""

    from security.query_safety import safe_search_term
    query = {}
    if email_filter:
        s = safe_search_term(email_filter)
        if s:
            svc = _svc_enc()
            if svc:
                email_hash = svc.compute_search_hash(email_filter)
                query['$or'] = [
                    {'_hash_email': email_hash},
                    {'email': {'$regex': s, '$options': 'i'}},
                ]
            else:
                query['email'] = {'$regex': s, '$options': 'i'}
        else:
            # email_filter explicitly provided but blank/whitespace → return empty (no drift).
            # Use regex-impossible sentinel `a^` (literal 'a' followed by start-anchor never matches)
            query['email'] = {'$regex': 'a^'}
    if role_filter:
        query['role'] = role_filter
    if tenant_id_filter:
        query['tenant_id'] = tenant_id_filter

    users_raw = await db.users.find(query, {'_id': 0, 'hashed_password': 0, 'password_hash': 0}).to_list(100)
    users = [decrypt_user_doc(u) for u in users_raw]

    return {
        "users": users,
        "count": len(users)
    }
# ── PATCH /admin/users/{user_id}/role ──
@router.patch("/admin/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    payload: UpdateUserRoleRequest,
    current_user: User = Depends(require_super_admin)
):
    """Update user role (SUPER ADMIN only)

    Allows super admin to change any user's role including making other super admins.
    """

    # Validate role
    valid_roles = [role.value for role in UserRole]
    if payload.role not in valid_roles:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role. Valid roles: {', '.join(valid_roles)}"
        )

    # Find user
    target_user = await db.users.find_one({"id": user_id})
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    # Update role
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": {"role": payload.role}}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Role could not be updated")

    return {
        "success": True,
        "message": f"User role updated successfully: {payload.role}",
        "user_id": user_id,
        "user_email": target_user.get('email'),
        "old_role": target_user.get('role'),
        "new_role": payload.role
    }
# ── GET /admin/tenant-users ──
@router.get("/admin/tenant-users")
async def list_tenant_users(
    tenant_id: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """ADMIN/SUPER_ADMIN için tenant kullanıcı listesi.

    - ADMIN: kendi tenant'ındaki kullanıcılar (tenant_id parametresi yok
      sayılır).
    - SUPER_ADMIN: `tenant_id` query parametresi zorunlu.

    UrgentPermissionAdminPage gibi izin yönetim ekranlarının kullandığı
    hafif endpoint — tek tek `granted_permissions` da döner.
    """
    if _is_super_admin(current_user):
        # SUPER_ADMIN: tenant_id verilmezse kendi tenant'ı default.
        target_tenant = tenant_id or current_user.tenant_id
    else:
        role_value = getattr(current_user.role, "value", str(current_user.role))
        if role_value != UserRole.ADMIN.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Yalnızca yöneticiler kullanıcı listesini görebilir.",
            )
        if not current_user.tenant_id:
            raise HTTPException(status_code=400, detail="Tenant tanımsız.")
        target_tenant = current_user.tenant_id

    cursor = db.users.find({"tenant_id": target_tenant})
    items: list[dict] = []
    async for u in cursor:
        # KVKK strict mode: email/name/username DB'de aes256gcm:/SYR1: olarak
        # şifreli tutuluyor. Frontend'e ciphertext sızdırmamak için
        # decrypt_user_doc ile plaintext'e çeviriyoruz (admin RBAC zaten
        # endpoint'te uygulanıyor; aynı helper /admin/users ve
        # /admin/hotel/* listelerinde de kullanılıyor).
        decoded = decrypt_user_doc(u)
        items.append({
            "id": decoded.get("id") or u.get("id"),
            "email": decoded.get("email"),
            "name": decoded.get("name"),
            "username": decoded.get("username"),
            "role": decoded.get("role") or u.get("role"),
            "tenant_id": decoded.get("tenant_id") or u.get("tenant_id"),
            "granted_permissions": (
                decoded.get("granted_permissions")
                or u.get("granted_permissions")
                or []
            ),
        })
    items.sort(key=lambda x: (x.get("name") or x.get("email") or "").lower())
    return {
        "tenant_id": target_tenant,
        "users": items,
        "grantable": sorted(GRANTABLE_PERMISSIONS),
    }
# ── GET /admin/users/{user_id}/granted-permissions ──
@router.get("/admin/users/{user_id}/granted-permissions")
async def get_user_granted_permissions(
    user_id: str,
    current_user: User = Depends(get_current_user),
):
    """Kullanıcıya tek tek verilmiş operasyon izinlerini döner.

    Yetki: ADMIN (kendi tenant'ı), SUPER_ADMIN (her tenant).
    """
    target_user = await db.users.find_one({"id": user_id})
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    _require_admin_for_target_user(current_user, target_user.get("tenant_id"))
    raw = target_user.get("granted_permissions") or []
    # Whitelist gerçekten uygulanır: legacy/unknown permission değerleri
    # frontend'e sızdırılmaz. Aksi halde UI toggle'ı bu değerleri payload'a
    # taşır ve PATCH whitelist kontrolü 400 verir → admin için fiili kilit.
    perms = [
        p for p in raw
        if isinstance(p, str) and p in GRANTABLE_PERMISSIONS
    ]
    return {
        "user_id": user_id,
        "permissions": perms,
        "grantable": sorted(GRANTABLE_PERMISSIONS),
    }
# ── PATCH /admin/users/{user_id}/granted-permissions ──
@router.patch("/admin/users/{user_id}/granted-permissions")
async def update_user_granted_permissions(
    user_id: str,
    payload: UpdateGrantedPermissionsRequest,
    current_user: User = Depends(get_current_user),
):
    """Kullanıcının operasyon-seviyesi izin listesini değiştirir.

    Yetki: ADMIN (kendi tenant'ı), SUPER_ADMIN (her tenant).
    Whitelist dışı bir izin gönderilirse 400 döner; mevcut izinler
    payload ile YERİ DEĞİŞTİRİLİR (idempotent set semantics).
    """
    target_user = await db.users.find_one({"id": user_id})
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")
    _require_admin_for_target_user(current_user, target_user.get("tenant_id"))

    # Whitelist + tekilleştirme.
    requested = []
    for p in payload.permissions or []:
        if not isinstance(p, str):
            continue
        if p not in GRANTABLE_PERMISSIONS:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Permission '{p}' atanabilir izinler arasında değil. "
                    f"İzinler: {sorted(GRANTABLE_PERMISSIONS)}"
                ),
            )
        if p not in requested:
            requested.append(p)

    before = list(target_user.get("granted_permissions") or [])

    await db.users.update_one(
        {"id": user_id},
        {"$set": {"granted_permissions": requested}},
    )

    # Audit: izin değişiklikleri yöneticiler tarafından izlenebilsin diye
    # warning seviyesinde yazılır (Task #27 desenine paralel).
    await log_audit_event(
        tenant_id=target_user.get("tenant_id") or "",
        user_id=current_user.id,
        action="update_user_granted_permissions",
        entity_type="user",
        entity_id=user_id,
        details=(
            f"{current_user.name} kullanıcı {user_id} izinlerini güncelledi: "
            f"{before} -> {requested}"
        ),
        before_value={"granted_permissions": before},
        after_value={"granted_permissions": requested},
        severity="warning",
        db=db,
    )

    return {
        "success": True,
        "user_id": user_id,
        "permissions": requested,
    }
# ── GET /admin/web-push/metrics ──
@router.get("/admin/web-push/metrics")
async def get_web_push_metrics(
    days: int = 30,
    tenant_id: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Web push gönderim sayaçlarının günlük rollup özeti.

    - ADMIN: kendi tenant'ı (tenant_id parametresi yok sayılır).
    - SUPER_ADMIN: `tenant_id` query parametresi zorunlu (cross-tenant).
    Diğer roller 403.

    Sistem-genelinde çalışan otomatik temizlik worker'ının silmesi
    `system_scheduled_pruned` alanında ayrıca döner.
    """
    if _is_super_admin(current_user):
        # SUPER_ADMIN: tenant_id verilmezse kendi tenant'ı default.
        if not tenant_id:
            tenant_id = current_user.tenant_id
        target_tenant = tenant_id
    else:
        role_value = getattr(current_user.role, "value", str(current_user.role))
        if role_value != UserRole.ADMIN.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Yalnızca yöneticiler push metriklerini görebilir.",
            )
        if not current_user.tenant_id:
            raise HTTPException(status_code=400, detail="Tenant tanımsız.")
        target_tenant = current_user.tenant_id

    from shared_kernel.web_push_metrics import get_metrics_summary
    summary = await get_metrics_summary(db, tenant_id=target_tenant, days=days)
    return summary
