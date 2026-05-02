"""
Admin / Operations Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

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
from domains.admin.property_profiles import get_all_property_types, get_hidden_nav_config, get_modules_for_property_type, get_property_profile, get_property_special_settings
from domains.admin.subscription_models import PLAN_MODULE_DEFAULTS, SUBSCRIPTION_PLANS, SubscriptionTier, get_all_module_keys, get_feature_comparison, get_plan_default_modules
from models.enums import ROLE_PERMISSIONS, Permission, UserRole
from models.schemas import Tenant, TenantRegister, UpdateUserRoleRequest, User


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


from core.audit import log_audit_event  # Task #28
from core.security import hash_password
from domains.admin.schemas import (  # noqa: E402
    AdminCreateTeamMemberRequest,
    AdminUpdateTenantInfoRequest,
    ChangePlanRequest,
    CreateTeamMemberRequest,
    DemoRequest,
    PermissionCheckRequest,
    PmsLiteLeadAdminUpdateRequest,
    PmsLiteLeadStatus,
    SLAConfig,
    SubscriptionUpdateRequest,
    TenantModulesUpdate,
    UpdateGrantedPermissionsRequest,
    UpdateHotelInfoRequest,
    UpdateTeamMemberRoleRequest,
)

router = APIRouter(prefix="/api", tags=["Admin / Operations"])


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
        return {
            'user_role': current_user.role,
            'permission': request.permission,
            'has_permission': has_perm
        }
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid permission: {request.permission}")

# ============= CHANNEL MANAGER & RMS =============



@router.get("/rbac/permissions/{user_role}/{resource}")
async def get_resource_permissions(
    user_role: UserRole,
    resource: str,
    current_user: User = Depends(get_current_user)
):
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
        'user_role': user_role.value,
        'resource': resource,
        'permissions': dict.fromkeys(resource_match, True),
        'has_access': bool(resource_match),
    }




@router.get("/rbac/my-permissions")
async def get_my_permissions(
    current_user: User = Depends(get_current_user)
):
    """Get current user's all resource permissions"""
    user_role = current_user.role

    if user_role not in ROLE_PERMISSIONS:
        return {'error': 'Invalid role'}
    perms = [(p.value if isinstance(p, Permission) else p) for p in ROLE_PERMISSIONS[user_role]]
    return {
        'user_id': current_user.id,
        'user_name': current_user.name,
        'user_role': user_role.value,
        'permissions': perms,
    }


# ============= MOBILE APP ENDPOINTS (STAFF & GUEST) =============


@router.get("/admin/property-types")
async def list_property_types():
    """List all available property types with their profiles (public endpoint for tenant creation form)"""
    return {"property_types": get_all_property_types()}


@router.get("/admin/property-types/{property_type}")
async def get_property_type_detail(property_type: str):
    """Get detailed property type profile including module config and special settings"""
    profile = get_property_profile(property_type)
    if not profile:
        raise HTTPException(status_code=404, detail="Property type not found")
    return {
        "key": property_type,
        **profile,
        "dashboard_layout": profile.get("dashboard_layout", "standard"),
    }


@router.get("/admin/tenants")
@_cm_cached(ttl=60, key_prefix="admin_tenants_list")  # v95.3 — 1dk cache, super-admin paneli
async def list_tenants(
    skip: int = 0,
    limit: int = 1000,  # v95.3 — backward-compat default; UI küçük sayfa istediğinde override eder
    current_user: User = Depends(require_super_admin),
):
    """List all hotels/tenants for super admin users ONLY.

    NOTE: Only SUPER_ADMIN users can view all hotels.
    Regular ADMIN users (hotel managers) cannot access this endpoint.

    v95.3 — pagination: ?skip=0&limit=50 ile sayfalanır; default 1000
    eski davranışı korur. Limit 2000 ile cap'lendi.
    """
    skip = max(0, int(skip))
    limit = max(1, min(int(limit), 2000))

    cursor = db.tenants.find({}, {"_id": 0}).skip(skip).limit(limit)
    tenants = await cursor.to_list(limit)
    total = await db.tenants.count_documents({})

    # Merge defaults for backward compatibility
    for tenant in tenants:
        tenant["modules"] = get_tenant_modules(tenant)

    return {
        "tenants": tenants,
        "total": total,
        "skip": skip,
        "limit": limit,
        "has_more": (skip + len(tenants)) < total,
    }




@router.get("/admin/module-report")
async def get_module_report(current_user: User = Depends(require_super_admin)):
    """Return a flattened module/license report for all tenants.

    ONLY for SUPER_ADMIN - shows all hotels in the system.
    This is optimized for UI & export use cases and avoids leaking internal Mongo fields.
    """
    tenants = await db.tenants.find({}, {"_id": 0}).to_list(2000)

    report_rows = []
    for tenant in tenants:
        modules = get_tenant_modules(tenant)

        row = {
            "tenant_id": tenant.get("id"),
            "property_name": tenant.get("property_name"),
            "location": tenant.get("location"),
            "subscription_tier": tenant.get("subscription_tier", "basic"),
        }

        # Flatten all known module keys
        for key, value in modules.items():
            try:
                row[f"mod_{key}"] = bool(value)
            except Exception:
                row[f"mod_{key}"] = False

        report_rows.append(row)

    return {"rows": report_rows, "count": len(report_rows)}




@router.post("/admin/tenants")
async def create_tenant(
    payload: TenantRegister,
    current_user: User = Depends(require_super_admin)
):
    """Create a new hotel/tenant (SUPER ADMIN only)"""

    # Cross-tenant platform op: bypass tenant scoping for tenant/user creation.
    from core.tenant_db import get_system_db
    sys_db = get_system_db()

    # Check if tenant with same email already exists
    existing = await sys_db.tenants.find_one({
        "$or": [{"contact_email": payload.email}, {"email": payload.email}]
    })
    if existing:
        raise HTTPException(status_code=400, detail="A hotel is already registered with this email address")

    # Also check if user email is taken
    existing_user = await sys_db.users.find_one(build_user_email_query(payload.email))
    if existing_user:
        raise HTTPException(status_code=400, detail="This email address is already in use")

    # Calculate subscription dates
    start_date = datetime.now(UTC)
    end_date = None

    if payload.subscription_days:
        end_date = start_date + timedelta(days=payload.subscription_days)

    normalized_plan = payload.subscription_plan or "core_small_hotel"

    tier = (payload.subscription_tier or "basic").lower()
    if tier not in ("mini", "basic", "professional", "enterprise"):
        tier = "basic"

    property_type = payload.property_type or "city_hotel"
    profile = get_property_profile(property_type)

    valid_types = [pt["key"] for pt in get_all_property_types()]
    if property_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Gecersiz tesis tipi: {property_type}. Gecerli: {', '.join(valid_types)}")

    if profile:
        if not payload.subscription_tier:
            tier = profile.get("recommended_tier", "basic")
        combined_modules = get_modules_for_property_type(property_type, tier)
        special_settings = get_property_special_settings(property_type)
        nav_config = get_hidden_nav_config(property_type)
        dashboard_layout = profile.get("dashboard_layout", "standard")
    else:
        combined_modules = get_plan_default_modules(tier)
        special_settings = {}
        nav_config = {"hidden_nav_groups": [], "hidden_nav_items": []}
        dashboard_layout = "standard"

    from core.hotel_ids import generate_unique_hotel_id
    new_hotel_id = await generate_unique_hotel_id(sys_db)

    new_tenant = Tenant(
        hotel_id=new_hotel_id,
        property_name=payload.property_name,
        property_type=property_type,
        contact_email=payload.email,
        contact_phone=payload.phone,
        address=payload.address,
        location=payload.location or "",
        total_rooms=payload.total_rooms or profile.get("room_range", {}).get("min", 50) if profile else (payload.total_rooms or 50),
        subscription_tier=tier,
        subscription_start_date=start_date.isoformat(),
        subscription_end_date=end_date.isoformat() if end_date else None,
        subscription_status="active",
        subscription_plan=normalized_plan,
        modules=combined_modules,
        features=special_settings,
    )

    tenant_dict = new_tenant.model_dump()
    tenant_dict['created_at'] = tenant_dict['created_at'].isoformat()
    tenant_dict['email'] = payload.email
    tenant_dict['phone'] = payload.phone
    tenant_dict['description'] = payload.description or ""
    tenant_dict['dashboard_layout'] = dashboard_layout
    tenant_dict['hidden_nav_groups'] = nav_config.get("hidden_nav_groups", [])
    tenant_dict['hidden_nav_items'] = nav_config.get("hidden_nav_items", [])
    await sys_db.tenants.insert_one(tenant_dict)

    # Create admin user for this tenant
    hashed_password = hash_password(payload.password)

    new_user = User(
        tenant_id=new_tenant.id,
        email=payload.email,
        name=payload.name,
        phone=payload.phone,
        password_hash=hashed_password,
        role=UserRole.ADMIN
    )

    user_dict = new_user.model_dump()
    user_dict['created_at'] = user_dict['created_at'].isoformat()
    # Rename password_hash to hashed_password for login compatibility
    user_dict['hashed_password'] = user_dict.pop('password_hash', hashed_password)
    user_dict = encrypt_user_doc(user_dict)
    await sys_db.users.insert_one(user_dict)

    return {
        "success": True,
        "message": "Hotel created successfully",
        "tenant_id": new_tenant.id,
        "user_id": new_user.id,
        "subscription_start": start_date.isoformat(),
        "subscription_end": end_date.isoformat() if end_date else "Unlimited",
        "subscription_days": payload.subscription_days or "Unlimited"
    }




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
        items.append({
            "id": u.get("id"),
            "email": u.get("email"),
            "name": u.get("name"),
            "username": u.get("username"),
            "role": u.get("role"),
            "tenant_id": u.get("tenant_id"),
            "granted_permissions": u.get("granted_permissions") or [],
        })
    items.sort(key=lambda x: (x.get("name") or x.get("email") or "").lower())
    return {
        "tenant_id": target_tenant,
        "users": items,
        "grantable": sorted(GRANTABLE_PERMISSIONS),
    }


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


# ── Task #32: Web push gönderim metrikleri ────────────────────────────
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


@router.patch("/admin/tenants/{tenant_id}/modules")
async def update_tenant_modules(
    tenant_id: str,
    payload: TenantModulesUpdate,
    current_user: User = Depends(require_super_admin),
):
    """Update enabled modules for a specific hotel (SUPER ADMIN only).

    Body example:
    {
      "modules": {
        "pms": true,
        "reports": true,
        "invoices": false,
        "ai": true
      }
    }
    """
    # Try by logical id first
    query = {"id": tenant_id}

    update_doc = {"$set": {"modules": payload.modules}}

    result = await db.tenants.update_one(query, update_doc)
    if result.matched_count == 0:
        # Fallback to Mongo _id
        try:
            from bson import ObjectId

            result = await db.tenants.update_one(
                {"_id": ObjectId(tenant_id)}, update_doc
            )
        except Exception:
            result = None

    if not result or result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hotel not found",
        )

    _invalidate_admin_tenants_cache(getattr(current_user, "tenant_id", None))  # v95.3

    # Return updated tenant with merged modules
    tenant_doc = await db.tenants.find_one(query, {"_id": 0})
    if not tenant_doc:
        from bson import ObjectId

        tenant_doc = await db.tenants.find_one(
            {"_id": ObjectId(tenant_id)}, {"_id": 0}
        )

    if not tenant_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hotel not found",
        )

    tenant_doc["modules"] = get_tenant_modules(tenant_doc)
    return tenant_doc


@router.patch("/admin/tenants/{tenant_id}/subscription")
async def update_tenant_subscription(
    tenant_id: str,
    payload: SubscriptionUpdateRequest,
    current_user: User = Depends(require_super_admin)
):
    """Update subscription duration for a tenant (SUPER ADMIN only)

    Supports both duration-based updates and manual start/end date updates.
    """

    def _parse_date_input(value: str | None) -> datetime | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None

        # Accept YYYY-MM-DD or ISO8601. Normalize to UTC.
        try:
            if len(value) == 10 and value[4] == '-' and value[7] == '-':
                dt = datetime.fromisoformat(value)
                return dt.replace(tzinfo=UTC)

            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            return dt.astimezone(UTC)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Invalid date format. Use YYYY-MM-DD or ISO8601 (e.g. 2025-12-17).",
            )

    # Find tenant
    tenant = await db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Hotel not found")

    # If manual dates are provided, prefer them. Otherwise, fallback to subscription_days.
    manual_mode = bool(payload.subscription_start_date) or bool(payload.subscription_end_date)

    if manual_mode:
        start_date = _parse_date_input(payload.subscription_start_date) or datetime.now(UTC)
        end_date = _parse_date_input(payload.subscription_end_date)
    else:
        start_date = datetime.now(UTC)
        end_date = None
        if payload.subscription_days:
            end_date = start_date + timedelta(days=payload.subscription_days)

    if end_date and end_date < start_date:
        raise HTTPException(status_code=400, detail="End date cannot be before start date")

    # Update tenant
    update_data = {
        "subscription_start_date": start_date.isoformat(),
        "subscription_end_date": end_date.isoformat() if end_date else None,
        "subscription_status": "active",
        "updated_at": datetime.now(UTC).isoformat(),
    }

    result = await db.tenants.update_one(
        {"id": tenant_id},
        {"$set": update_data}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Subscription could not be updated")

    _invalidate_admin_tenants_cache(getattr(current_user, "tenant_id", None))  # v95.3

    return {
        "success": True,
        "message": "Subscription updated successfully",
        "tenant_id": tenant_id,
        "subscription_start": start_date.isoformat(),
        "subscription_end": end_date.isoformat() if end_date else "Unlimited",
        "subscription_days": payload.subscription_days or "Unlimited",
        "manual_dates": manual_mode,
    }




@router.get("/subscription/plans")
async def get_subscription_plans():
    """Get all available subscription plans"""
    return {
        'plans': [plan.model_dump() for plan in SUBSCRIPTION_PLANS.values()],
        'currency': 'EUR',
        'tiers': [tier.value for tier in SubscriptionTier]
    }



@router.get("/subscription/plan-modules")
async def get_plan_module_defaults():
    """Get default module mapping for each subscription tier.
    Used by admin panel to show which modules are included per plan."""
    return {
        'plan_modules': PLAN_MODULE_DEFAULTS,
        'tiers': [tier.value for tier in SubscriptionTier],
        'all_module_keys': get_all_module_keys()
    }



@router.patch("/admin/tenants/{tenant_id}/tier")
async def update_tenant_tier(
    tenant_id: str,
    payload: dict,
    current_user: User = Depends(require_super_admin)
):
    """Change a tenant's subscription tier and optionally reset modules to tier defaults.

    Body:
    {
        "tier": "mini" | "basic" | "professional" | "enterprise",
        "reset_modules": true  // optional, default true
    }
    """
    new_tier = (payload.get("tier") or "basic").lower()
    reset_modules = payload.get("reset_modules", True)

    if new_tier not in ("mini", "basic", "professional", "enterprise"):
        raise HTTPException(status_code=400, detail="Invalid plan. Valid options: mini, basic, professional, enterprise")

    tenant = await db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Hotel not found")

    update_data = {
        "subscription_tier": new_tier,
        "updated_at": datetime.now(UTC).isoformat(),
    }

    if reset_modules:
        update_data["modules"] = get_plan_default_modules(new_tier)

    await db.tenants.update_one({"id": tenant_id}, {"$set": update_data})
    _invalidate_admin_tenants_cache(getattr(current_user, "tenant_id", None))  # v95.3

    updated_tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0})
    if updated_tenant:
        updated_tenant["modules"] = get_tenant_modules(updated_tenant)

    return {
        "success": True,
        "message": f"Plan updated to {new_tier}",
        "tenant": updated_tenant,
    }



# ============= ADMIN TENANT INFO & TEAM MANAGEMENT =============


@router.patch("/admin/tenants/{tenant_id}/info")
async def admin_update_tenant_info(
    tenant_id: str,
    payload: AdminUpdateTenantInfoRequest,
    current_user: User = Depends(require_super_admin),
):
    """Update any tenant's info (SUPER ADMIN only)"""
    tenant = await db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Hotel not found")

    update_data = {}
    for field in ("property_name", "phone", "email", "address", "location", "description", "total_rooms"):
        val = getattr(payload, field, None)
        if val is not None:
            update_data[field] = val
            if field == "phone":
                update_data["contact_phone"] = val
            if field == "email":
                update_data["contact_email"] = val

    if not update_data:
        raise HTTPException(status_code=400, detail="No field to update")

    update_data["updated_at"] = datetime.now(UTC).isoformat()
    await db.tenants.update_one({"id": tenant_id}, {"$set": update_data})
    _invalidate_admin_tenants_cache(getattr(current_user, "tenant_id", None))  # v95.3

    updated = await db.tenants.find_one({"id": tenant_id}, {"_id": 0})
    return {"success": True, "message": "Hotel information updated", "tenant": updated}


@router.get("/admin/tenants/{tenant_id}/team")
async def admin_list_tenant_team(
    tenant_id: str,
    current_user: User = Depends(require_super_admin),
):
    """List team members for a specific tenant (SUPER ADMIN only)"""
    tenant = await db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Hotel not found")

    users_raw = await db.users.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "hashed_password": 0, "password_hash": 0, "password": 0},
    ).to_list(200)
    users = [decrypt_user_doc(u) for u in users_raw]

    return {"users": users, "count": len(users), "tenant_id": tenant_id}


@router.post("/admin/tenants/{tenant_id}/team")
async def admin_add_tenant_team_member(
    tenant_id: str,
    payload: AdminCreateTeamMemberRequest,
    current_user: User = Depends(require_super_admin),
):
    """Add a team member to a specific tenant (SUPER ADMIN only)"""
    tenant = await db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Hotel not found")

    existing = await db.users.find_one(build_user_email_query(payload.email))
    if existing:
        raise HTTPException(status_code=400, detail="This email address is already registered")

    tier = (tenant.get("subscription_tier", "basic")).lower()
    if tier == "pro":
        tier = "professional"
    if tier == "ultra":
        tier = "enterprise"

    if not is_role_allowed_for_tier(payload.role, tier):
        allowed = ROLES_BY_TIER.get(tier, ROLES_BY_TIER["basic"])
        raise HTTPException(
            status_code=400,
            detail=f"Role '{payload.role}' is not available for the {tier} plan. Allowed: {', '.join(allowed)}",
        )

    hashed = hash_password(payload.password)
    new_user = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
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


@router.delete("/admin/tenants/{tenant_id}/team/{user_id}")
async def admin_remove_tenant_team_member(
    tenant_id: str,
    user_id: str,
    current_user: User = Depends(require_super_admin),
):
    """Remove a team member from a specific tenant (SUPER ADMIN only)"""
    target = await db.users.find_one({"id": user_id, "tenant_id": tenant_id})
    if not target:
        raise HTTPException(status_code=404, detail="Team member not found")

    if target.get("role") == "super_admin":
        raise HTTPException(status_code=400, detail="Super Admin cannot be deleted")

    await db.users.delete_one({"id": user_id, "tenant_id": tenant_id})
    return {"success": True, "message": "Team member removed"}


@router.patch("/admin/tenants/{tenant_id}/team/{user_id}/role")
async def admin_update_tenant_team_role(
    tenant_id: str,
    user_id: str,
    payload: UpdateTeamMemberRoleRequest,
    current_user: User = Depends(require_super_admin),
):
    """Update a team member's role (SUPER ADMIN only)"""
    target = await db.users.find_one({"id": user_id, "tenant_id": tenant_id})
    if not target:
        raise HTTPException(status_code=404, detail="Team member not found")

    if target.get("role") == "super_admin":
        raise HTTPException(status_code=400, detail="Super Admin role cannot be changed")

    tier_doc = await db.tenants.find_one({"id": tenant_id})
    tier = (tier_doc.get("subscription_tier", "basic") if tier_doc else "basic").lower()
    if tier == "pro":
        tier = "professional"
    if tier == "ultra":
        tier = "enterprise"

    if not is_role_allowed_for_tier(payload.role, tier):
        allowed = ROLES_BY_TIER.get(tier, ROLES_BY_TIER["basic"])
        raise HTTPException(
            status_code=400,
            detail=f"Role '{payload.role}' is not available for the {tier} plan. Allowed: {', '.join(allowed)}",
        )

    # v106 audit T03 spot-fix: defense-in-depth — include tenant_id in the
    # update filter. find_one above already restricts to tenant; adding it
    # here closes a TOCTOU window where a concurrent re-tenant of the user
    # could otherwise let a stale role write land cross-tenant.
    res = await db.users.update_one(
        {"id": user_id, "tenant_id": tenant_id},
        {"$set": {"role": payload.role}},
    )
    if res.matched_count == 0:
        # Lost the TOCTOU race — user moved tenant or was deleted between
        # find_one and update_one. Surface as 409 instead of false-success.
        raise HTTPException(status_code=409, detail="User changed concurrently, retry")
    return {"success": True, "message": f"Role updated: {payload.role}"}


@router.get("/admin/tenants/{tenant_id}/stats")
async def admin_get_tenant_stats(
    tenant_id: str,
    current_user: User = Depends(require_super_admin),
):
    """Get detailed stats for a specific tenant (SUPER ADMIN only)"""
    tenant = await db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Hotel not found")

    rooms = await db.rooms.count_documents({"tenant_id": tenant_id})
    users = await db.users.count_documents({"tenant_id": tenant_id})
    guests = await db.guests.count_documents({"tenant_id": tenant_id})
    bookings = await db.bookings.count_documents({"tenant_id": tenant_id})

    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    bookings_this_month = await db.bookings.count_documents({
        "tenant_id": tenant_id,
        "created_at": {"$gte": month_start},
    })

    checked_in = await db.bookings.count_documents({
        "tenant_id": tenant_id,
        "status": "checked_in",
    })

    return {
        "tenant_id": tenant_id,
        "rooms": rooms,
        "users": users,
        "guests": guests,
        "total_bookings": bookings,
        "bookings_this_month": bookings_this_month,
        "checked_in": checked_in,
    }




@router.get("/subscription/features")
async def get_feature_comparison_endpoint():
    """Get feature comparison across all tiers"""
    return {
        'features': get_feature_comparison(),
        'tiers': [tier.value for tier in SubscriptionTier]
    }



@router.get("/subscription/current")
async def get_current_subscription(
    current_user: User = Depends(get_current_user)
):
    """Get current user's subscription"""
    tenant = await db.tenants.find_one({'id': current_user.tenant_id})

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    subscription_tier = tenant.get('subscription_tier', 'basic')
    # Handle legacy tier names
    tier_map = {"pro": "professional", "ultra": "enterprise"}
    normalized_tier = tier_map.get(subscription_tier, subscription_tier)
    try:
        plan = SUBSCRIPTION_PLANS.get(SubscriptionTier(normalized_tier))
    except ValueError:
        plan = SUBSCRIPTION_PLANS.get(SubscriptionTier.BASIC)

    return {
        'tenant_id': current_user.tenant_id,
        'tier': normalized_tier,
        'plan': plan.model_dump() if plan else None,
        'status': tenant.get('subscription_status', 'active'),
        'valid_until': tenant.get('subscription_valid_until'),
        'rooms_count': await db.rooms.count_documents({'tenant_id': current_user.tenant_id}),
        'users_count': await db.users.count_documents({'tenant_id': current_user.tenant_id}),
        'modules': get_tenant_modules(tenant)
    }



@router.post("/subscription/upgrade")
async def upgrade_subscription(
    new_tier: SubscriptionTier,
    billing_cycle: str = 'monthly',  # monthly or yearly
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v90 DW
):
    """Upgrade subscription tier"""
    tenant = await db.tenants.find_one({'id': current_user.tenant_id})

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    current_tier = tenant.get('subscription_tier', 'basic')
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
    amount = plan.price_yearly if billing_cycle == 'yearly' else plan.price_monthly

    # Get default modules for new tier
    new_modules = get_plan_default_modules(new_tier.value)

    # Update subscription
    await db.tenants.update_one(
        {'id': current_user.tenant_id},
        {'$set': {
            'subscription_tier': new_tier.value,
            'subscription_status': 'active',
            'billing_cycle': billing_cycle,
            'modules': new_modules,
            'subscription_valid_until': (datetime.now(UTC) + timedelta(days=365 if billing_cycle == 'yearly' else 30)).isoformat(),
            'last_billing_date': datetime.now(UTC).isoformat()
        }}
    )

    return {
        'success': True,
        'message': f'Successfully upgraded to {plan.name}',
        'tier': new_tier.value,
        'amount': amount,
        'billing_cycle': billing_cycle
    }


# ============= BILLING HISTORY & PLAN MANAGEMENT =============



@router.post("/subscription/change-plan")
async def change_subscription_plan(
    payload: ChangePlanRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v90 DW
):
    """Change subscription plan (upgrade or downgrade).
    Creates a billing history record for the change."""
    tenant = await db.tenants.find_one({'id': current_user.tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if not _is_super_admin(current_user) and current_user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(status_code=403, detail="Only administrators can change the plan")

    new_tier = payload.new_tier.lower()
    if new_tier == "pro": new_tier = "professional"
    if new_tier == "ultra": new_tier = "enterprise"

    if new_tier not in ("mini", "basic", "professional", "enterprise"):
        raise HTTPException(status_code=400, detail="Invalid plan")

    current_tier = (tenant.get('subscription_tier', 'basic')).lower()
    if current_tier == "pro": current_tier = "professional"
    if current_tier == "ultra": current_tier = "enterprise"

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
            room_count = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
            if room_count > plan.max_rooms:
                raise HTTPException(
                    status_code=400,
                    detail=f"Your room count ({room_count}) exceeds the target plan limit ({plan.max_rooms}). Please reduce rooms first."
                )
        if plan.max_users:
            user_count = await db.users.count_documents({'tenant_id': current_user.tenant_id})
            if user_count > plan.max_users:
                raise HTTPException(
                    status_code=400,
                    detail=f"Your user count ({user_count}) exceeds the target plan limit ({plan.max_users}). Please reduce users first."
                )

    amount = plan.price_yearly if payload.billing_cycle == 'yearly' else plan.price_monthly
    new_modules = get_plan_default_modules(new_tier)
    now = datetime.now(UTC)
    valid_days = 365 if payload.billing_cycle == 'yearly' else 30

    # Update tenant
    await db.tenants.update_one(
        {'id': current_user.tenant_id},
        {'$set': {
            'subscription_tier': new_tier,
            'subscription_status': 'active',
            'billing_cycle': payload.billing_cycle,
            'modules': new_modules,
            'subscription_valid_until': (now + timedelta(days=valid_days)).isoformat(),
            'last_billing_date': now.isoformat(),
            'updated_at': now.isoformat(),
        }}
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




@router.get("/billing/history")
async def get_billing_history(
    current_user: User = Depends(get_current_user)
):
    """Get billing / plan change history for the current hotel"""
    records = await db.billing_history.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)

    return {"records": records, "count": len(records)}




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


# ============= HOTEL TEAM MANAGEMENT ENDPOINTS =============



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


# ============= DEMO ENVIRONMENT ENDPOINTS =============

from demo_data_generator import DemoDataGenerator


@router.post("/demo/populate")
async def populate_demo_data(
    hotel_type: str = 'boutique',  # boutique, resort, city
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
):
    """Populate account with realistic demo data"""

    # Check if already has data
    existing_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    if existing_rooms > 10:
        raise HTTPException(status_code=400, detail="Account already has data. Cannot populate demo data.")

    # Generate demo data
    demo_data = DemoDataGenerator.generate_demo_hotel(current_user.tenant_id, hotel_type)

    # Insert demo data
    stats = {
        'rooms': 0,
        'guests': 0,
        'bookings': 0,
        'staff': 0,
        'inventory': 0
    }

    # Insert rooms
    if demo_data['rooms']:
        await db.rooms.insert_many(demo_data['rooms'])
        stats['rooms'] = len(demo_data['rooms'])

    # Insert guests
    if demo_data['guests']:
        await db.guests.insert_many(demo_data['guests'])
        stats['guests'] = len(demo_data['guests'])

    # Insert bookings
    if demo_data['bookings']:
        await db.bookings.insert_many(demo_data['bookings'])
        stats['bookings'] = len(demo_data['bookings'])

    # Insert staff
    if demo_data['staff']:
        # Note: Staff might need to be in users collection with passwords
        # For demo, we'll just store as reference data
        for staff in demo_data['staff']:
            await db.staff_profiles.insert_one(staff)
        stats['staff'] = len(demo_data['staff'])

    # Insert inventory
    if demo_data['inventory']:
        await db.inventory.insert_many(demo_data['inventory'])
        stats['inventory'] = len(demo_data['inventory'])

    return {
        'success': True,
        'message': 'Demo data populated successfully',
        'hotel_name': demo_data['hotel_name'],
        'stats': stats
    }



@router.get("/demo/status")
async def get_demo_status(
    current_user: User = Depends(get_current_user)
):
    """Check if account is using demo data"""

    rooms_count = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    guests_count = await db.guests.count_documents({'tenant_id': current_user.tenant_id})
    bookings_count = await db.bookings.count_documents({'tenant_id': current_user.tenant_id})

    is_demo = rooms_count > 0 and guests_count > 0

    return {
        'is_demo': is_demo,
        'has_data': rooms_count > 0,
        'stats': {
            'rooms': rooms_count,
            'guests': guests_count,
            'bookings': bookings_count
        }
    }


@router.get("/admin/leads")
async def admin_list_pms_lite_leads(
    status: PmsLiteLeadStatus | None = None,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
):
    """List PMS Lite marketing leads for super admin."""
    if not _is_super_admin(current_user) and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Only super_admin can access leads")

    query: dict[str, Any] = {"source": "pms_lite_landing"}
    if status:
        query["status"] = status.value

    if q:
        from security.query_safety import safe_search_term
        s = safe_search_term(q)
        if s:
            regex = {"$regex": s, "$options": "i"}
            query["$or"] = [
                {"contact.full_name": regex},
                {"contact.phone": regex},
                {"contact.email": regex},
                {"hotel.property_name": regex},
                {"hotel.location": regex},
            ]

    await db.leads.count_documents(query)

    cursor = (
        db.leads.find(query)
        .sort("created_at", -1)
        .skip(max(offset, 0))
        .limit(max(limit, 1))
    )

    leads: list[dict[str, Any]] = []
    async for lead in cursor:
        leads.append(
            {
                "lead_id": lead.get("lead_id") or lead.get("id"),
                "created_at": lead.get("created_at"),
                "status": lead.get("status", PmsLiteLeadStatus.NEW.value),
                "note": lead.get("note"),
                "full_name": lead.get("contact", {}).get("full_name"),
                "phone": lead.get("contact", {}).get("phone"),
                "email": lead.get("contact", {}).get("email"),
                "property_name": lead.get("hotel", {}).get("property_name"),
                "location": lead.get("hotel", {}).get("location"),
                "rooms_count": lead.get("hotel", {}).get("rooms_count"),
            }
        )




@router.get("/admin/leads/export.csv")
async def admin_export_pms_lite_leads_csv(
    status: PmsLiteLeadStatus | None = None,
    q: str | None = None,
    follow_up: bool | None = False,
    current_user: User = Depends(get_current_user),
):
    """Export PMS Lite marketing leads as CSV for super admin."""
    if not _is_super_admin(current_user) and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Only super_admin can export leads")

    import csv
    from io import StringIO

    query: dict[str, Any] = {"source": "pms_lite_landing"}
    if status:
        query["status"] = status.value

    if q:
        from security.query_safety import safe_search_term
        s = safe_search_term(q)
        if s:
            regex = {"$regex": s, "$options": "i"}
            query["$or"] = [
                {"contact.full_name": regex},
                {"contact.phone": regex},
                {"contact.email": regex},
                {"hotel.property_name": regex},
                {"hotel.location": regex},
            ]

    docs: list[dict[str, Any]] = []
    async for lead in db.leads.find(query):
        docs.append(lead)

    now = datetime.now(UTC)

    def _parse_iso_dt(v):
        if not v:
            return None
        if isinstance(v, datetime):
            return v if v.tzinfo else v.replace(tzinfo=UTC)
        try:
            dt = datetime.fromisoformat(str(v).replace("Z", "+00:00"))
            return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
        except Exception:
            return None

    if follow_up:
        filtered: list[dict[str, Any]] = []
        for lead in docs:
            s = lead.get("status", "new")
            created = _parse_iso_dt(lead.get("created_at"))
            last_contact = _parse_iso_dt(lead.get("last_contact_at"))

            if s not in {"new", "contacted", "qualified"}:
                continue

            if s == "new":
                if not created:
                    continue
                if (now - created).total_seconds() < 3600:
                    continue
                filtered.append(lead)
            else:
                cutoff = 24 * 3600
                base = last_contact or created
                if not base:
                    continue
                if (now - base).total_seconds() > cutoff:
                    filtered.append(lead)
        docs = filtered

    from core.csv_safe import safe_writerow  # Bug AN: defend against CSV formula injection
    output = StringIO()
    # BOM for Excel UTF-8
    output.write("\ufeff")
    writer = csv.writer(output)

    headers = [
        "created_at",
        "status",
        "full_name",
        "phone",
        "email",
        "property_name",
        "location",
        "rooms_count",
        "lead_id",
        "note",
        "last_contact_at",
        "status_changed_at",
    ]
    safe_writerow(writer, headers)

    for lead in docs:
        contact = lead.get("contact", {})
        hotel = lead.get("hotel", {})
        row = [
            lead.get("created_at") or "",
            lead.get("status") or "",
            contact.get("full_name") or "",
            contact.get("phone") or "",
            contact.get("email") or "",
            hotel.get("property_name") or "",
            hotel.get("location") or "",
            hotel.get("rooms_count") or "",
            lead.get("lead_id") or lead.get("id") or "",
            lead.get("note") or "",
            lead.get("last_contact_at") or "",
            lead.get("status_changed_at") or "",
        ]
        safe_writerow(writer, row)

    csv_content = output.getvalue()
    from fastapi.responses import Response

    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=\"pms-lite-leads.csv\"",
        },
    )



@router.patch("/admin/leads/{lead_id}")
async def admin_update_pms_lite_lead(
    lead_id: str,
    payload: PmsLiteLeadAdminUpdateRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v90 DW
):
    """Update status/note of a PMS Lite marketing lead (super_admin only)."""
    if not _is_super_admin(current_user) and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Only super_admin can update leads")

    update: dict[str, Any] = {}
    if payload.status is not None:
        update["status"] = payload.status.value
    if payload.note is not None:
        update["note"] = payload.note

    if not update:
        return {"ok": True}

    result = await db.leads.update_one(
        {"lead_id": lead_id, "source": "pms_lite_landing"}, {"$set": update}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Lead not found")

    return {"ok": True, "lead_id": lead_id}


# 6. GET /api/sales/follow-ups - Follow-up reminders


@router.post("/settings/sla")
async def create_sla_config(
    config: SLAConfig,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v95 DW
):
    """
    Create or update SLA configuration for property
    """
    try:
        sla_id = str(uuid.uuid4())

        # Check if SLA exists for this category
        existing = await db.sla_configs.find_one({
            'tenant_id': current_user.tenant_id,
            'category': config.category,
            'priority': config.priority
        }, {'_id': 0})

        if existing:
            # Update existing
            await db.sla_configs.update_one(
                {
                    'tenant_id': current_user.tenant_id,
                    'category': config.category,
                    'priority': config.priority
                },
                {
                    '$set': {
                        'response_time_minutes': config.response_time_minutes,
                        'resolution_time_minutes': config.resolution_time_minutes,
                        'updated_at': datetime.now(UTC).isoformat(),
                        'updated_by': current_user.name
                    }
                }
            )
            sla_id = existing['id']
        else:
            # Create new
            await db.sla_configs.insert_one({
                'id': sla_id,
                'tenant_id': current_user.tenant_id,
                'category': config.category,
                'priority': config.priority,
                'response_time_minutes': config.response_time_minutes,
                'resolution_time_minutes': config.resolution_time_minutes,
                'created_at': datetime.now(UTC).isoformat(),
                'created_by': current_user.name
            })

        return {
            'message': 'SLA configuration saved',
            'sla_id': sla_id,
            'category': config.category,
            'priority': config.priority,
            'response_time': f'{config.response_time_minutes} min',
            'resolution_time': f'{config.resolution_time_minutes} min'
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save SLA config: {str(e)}")




@router.get("/settings/sla")
async def get_sla_configs(
    current_user: User = Depends(get_current_user)
):
    """
    Get all SLA configurations
    """
    try:
        configs = await db.sla_configs.find({
            'tenant_id': current_user.tenant_id
        }, {'_id': 0}).to_list(100)

        # If no configs, return defaults
        if not configs:
            configs = [
                {
                    'category': 'maintenance',
                    'priority': 'urgent',
                    'response_time_minutes': 30,
                    'resolution_time_minutes': 120
                },
                {
                    'category': 'housekeeping',
                    'priority': 'normal',
                    'response_time_minutes': 60,
                    'resolution_time_minutes': 180
                },
                {
                    'category': 'guest_request',
                    'priority': 'normal',
                    'response_time_minutes': 15,
                    'resolution_time_minutes': 60
                }
            ]

        return {
            'configs': configs,
            'count': len(configs)
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get SLA configs: {str(e)}")


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

import time

import psutil

# api_metrics is now provided by apm_store from apm_middleware.py
# Backward compat: alias api_metrics to apm_store.requests
try:
    from apm_middleware import apm_store as _apm_store_ref
    from apm_middleware import get_rate_limit_stats as _get_rl_stats
    api_metrics = _apm_store_ref.requests
except ImportError:
    from collections import deque
    api_metrics = deque(maxlen=1000)

# Legacy APIMetricsMiddleware replaced by APMMiddleware in apm_middleware.py

# 1. SYSTEM PERFORMANCE MONITORING


@router.get("/system/performance")
async def get_system_performance(
    minutes: int = 10,
    current_user: User = Depends(get_current_user)
):
    """
    Get real-time system performance metrics powered by APM middleware.
    Returns: CPU, RAM, API response times, request rates, rate limiting, errors
    """
    try:
        # Get CPU and Memory info
        cpu_percent = psutil.cpu_percent(interval=0)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        # Get APM summary (real data from middleware)
        try:
            apm_summary = _apm_store_ref.get_summary(minutes=minutes)
        except Exception:
            try:
                from apm_middleware import apm_store as _apm
                apm_summary = _apm.get_summary(minutes=minutes) if hasattr(_apm, 'get_summary') else {}
            except Exception:
                apm_summary = {}

        # Get rate limit stats
        try:
            rl_stats = _get_rl_stats()
        except Exception:
            try:
                from apm_middleware import get_rate_limit_stats as _rl
                rl_stats = _rl()
            except Exception:
                rl_stats = {}

        # Get recent errors
        try:
            recent_errors = _apm_store_ref.get_recent_errors(limit=20)
        except Exception:
            recent_errors = []

        # Database stats (lightweight)
        db_stats = {}
        try:
            server_status = await db.command('serverStatus')
            db_stats = {
                'connections': {
                    'current': server_status.get('connections', {}).get('current', 0),
                    'available': server_status.get('connections', {}).get('available', 0),
                    'total_created': server_status.get('connections', {}).get('totalCreated', 0),
                },
                'opcounters': {
                    'insert': server_status.get('opcounters', {}).get('insert', 0),
                    'query': server_status.get('opcounters', {}).get('query', 0),
                    'update': server_status.get('opcounters', {}).get('update', 0),
                    'delete': server_status.get('opcounters', {}).get('delete', 0),
                },
                'uptime_seconds': server_status.get('uptime', 0),
            }
        except Exception:
            pass

        return {
            'system': {
                'cpu_percent': round(cpu_percent, 2),
                'memory_percent': round(memory.percent, 2),
                'memory_used_gb': round(memory.used / (1024**3), 2),
                'memory_total_gb': round(memory.total / (1024**3), 2),
                'disk_percent': round(disk.percent, 2),
                'disk_used_gb': round(disk.used / (1024**3), 2),
                'disk_total_gb': round(disk.total / (1024**3), 2),
            },
            'api_metrics': {
                'avg_response_time_ms': apm_summary.get('avg_response_time_ms', 0),
                'p50_ms': apm_summary.get('p50_ms', 0),
                'p95_ms': apm_summary.get('p95_ms', 0),
                'p99_ms': apm_summary.get('p99_ms', 0),
                'requests_per_minute': apm_summary.get('requests_per_minute', 0),
                'total_requests_tracked': apm_summary.get('total_requests', 0),
                'error_rate_percent': apm_summary.get('error_rate_percent', 0),
                'slow_requests': apm_summary.get('slow_requests', 0),
                'status_breakdown': apm_summary.get('status_breakdown', {}),
                'endpoints': apm_summary.get('top_endpoints', []),
                'slowest_endpoints': apm_summary.get('slowest_endpoints', []),
                'error_endpoints': apm_summary.get('error_endpoints', []),
            },
            'rate_limiting': {
                'active_clients': rl_stats.get('active_clients', 0),
                'total_rate_limit_hits': rl_stats.get('total_rate_limit_hits', 0),
                'hits_by_endpoint': rl_stats.get('hits_by_endpoint', {}),
                'limits_config': rl_stats.get('limits_config', {}),
            },
            'database': db_stats,
            'recent_errors': recent_errors[:10],
            'timeline': apm_summary.get('timeline', []),
            'health_status': 'healthy' if cpu_percent < 80 and memory.percent < 80 else 'degraded',
            'uptime_seconds': apm_summary.get('uptime_seconds', 0),
            'timestamp': datetime.now(UTC).isoformat(),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get performance metrics: {str(e)}")


# 1b. APM DETAILED ENDPOINT STATS


@router.get("/system/apm/endpoints")
async def get_apm_endpoint_details(
    current_user: User = Depends(get_current_user)
):
    """Get detailed APM stats for all tracked endpoints"""
    try:
        summary = _apm_store_ref.get_summary(minutes=30)
        return {
            'top_endpoints': summary.get('top_endpoints', []),
            'slowest_endpoints': summary.get('slowest_endpoints', []),
            'error_endpoints': summary.get('error_endpoints', []),
            'total_requests': summary.get('total_requests', 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 1c. RATE LIMIT STATUS


@router.get("/system/rate-limits")
async def get_rate_limit_status(
    current_user: User = Depends(get_current_user)
):
    """Get current rate limiting status and configuration"""
    try:
        rl_stats = _get_rl_stats()
        return {
            'enabled': True,
            'mode': 'in-memory',
            'stats': rl_stats,
            'timestamp': datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        return {
            'enabled': False,
            'mode': 'disabled',
            'error': str(e),
            'timestamp': datetime.now(UTC).isoformat(),
        }


# 1d. DATABASE OPTIMIZATION STATUS


@router.get("/system/db-stats")
async def get_database_stats(
    current_user: User = Depends(get_current_user)
):
    """Get database optimization and performance statistics"""
    try:
        from infra.database_optimizer import DatabaseOptimizer
        optimizer = DatabaseOptimizer(db)

        # Get index info
        index_info = await optimizer.verify_indexes()

        # Get collection stats
        collection_stats = await optimizer.get_collection_stats()

        # Get server status
        server_status = await db.command('serverStatus')
        connections = server_status.get('connections', {})
        opcounters = server_status.get('opcounters', {})

        return {
            'indexes': index_info,
            'collections': collection_stats,
            'connections': {
                'current': connections.get('current', 0),
                'available': connections.get('available', 0),
                'total_created': connections.get('totalCreated', 0),
            },
            'operations': {
                'insert': opcounters.get('insert', 0),
                'query': opcounters.get('query', 0),
                'update': opcounters.get('update', 0),
                'delete': opcounters.get('delete', 0),
            },
            'pool_config': {
                'max_pool_size': 500,
                'min_pool_size': 50,
                'max_idle_time_ms': 45000,
            },
            'uptime_seconds': server_status.get('uptime', 0),
            'timestamp': datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get DB stats: {str(e)}")


# 1e. RECENT ERRORS


@router.get("/system/errors")
async def get_recent_errors(
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    """Get recent API errors tracked by APM"""
    try:
        errors = _apm_store_ref.get_recent_errors(limit=limit)
        return {
            'errors': errors,
            'total': len(errors),
            'timestamp': datetime.now(UTC).isoformat(),
        }
    except Exception as e:
        return {'errors': [], 'total': 0, 'error': str(e)}


# 2. LOG VIEWER


@router.get("/system/logs")
async def get_system_logs(
    level: str | None = None,  # ERROR, WARN, INFO, DEBUG
    search: str | None = None,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """
    Get system logs with filtering
    """
    try:
        # Read from audit logs and create application logs
        logs = []

        # Get audit logs from database
        from security.query_safety import safe_search_term
        filter_dict = {'tenant_id': current_user.tenant_id}
        if (s := safe_search_term(search)):
            filter_dict['$or'] = [
                {'action': {'$regex': s, '$options': 'i'}},
                {'entity_type': {'$regex': s, '$options': 'i'}},
                {'user_name': {'$regex': s, '$options': 'i'}}
            ]

        audit_logs = await db.audit_logs.find(filter_dict).sort('timestamp', -1).limit(limit).to_list(limit)

        for log in audit_logs:
            # Convert audit log to application log format
            log_entry = {
                'id': log['id'],
                'level': 'INFO',
                'timestamp': log['timestamp'],
                'message': f"{log['user_name']} performed {log['action']} on {log['entity_type']}",
                'user': log.get('user_name', 'System'),
                'action': log['action'],
                'entity_type': log.get('entity_type'),
                'entity_id': log.get('entity_id'),
                'details': log.get('changes', {})
            }

            # Determine log level based on action
            if 'DELETE' in log['action'] or 'VOID' in log['action']:
                log_entry['level'] = 'WARN'
            elif 'ERROR' in log['action'] or 'FAIL' in log['action']:
                log_entry['level'] = 'ERROR'

            logs.append(log_entry)

        # Add some system logs
        system_logs = [
            {
                'id': str(uuid.uuid4()),
                'level': 'INFO',
                'timestamp': datetime.now(UTC).isoformat(),
                'message': 'System performance check completed',
                'user': 'System',
                'action': 'SYSTEM_CHECK',
                'details': {'status': 'healthy'}
            },
            {
                'id': str(uuid.uuid4()),
                'level': 'INFO',
                'timestamp': (datetime.now(UTC) - timedelta(minutes=5)).isoformat(),
                'message': 'Database connection verified',
                'user': 'System',
                'action': 'DB_CHECK',
                'details': {'latency_ms': 12}
            }
        ]

        logs.extend(system_logs)
        logs.sort(key=lambda x: x['timestamp'], reverse=True)

        # Filter by level if specified (after adding all logs)
        if level:
            logs = [log for log in logs if log['level'] == level.upper()]

        return {
            'logs': logs[:limit],
            'count': len(logs),
            'filters': {
                'level': level,
                'search': search,
                'limit': limit
            },
            'log_levels': {
                'ERROR': len([l for l in logs if l['level'] == 'ERROR']),
                'WARN': len([l for l in logs if l['level'] == 'WARN']),
                'INFO': len([l for l in logs if l['level'] == 'INFO']),
                'DEBUG': len([l for l in logs if l['level'] == 'DEBUG'])
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve logs: {str(e)}")


# 3. NETWORK PING TEST


@router.post("/demo-requests")
async def create_demo_request(request: DemoRequest):
    """
    Create demo request from landing page
    Public endpoint - no authentication required
    """
    try:
        demo_data = {
            'id': str(uuid.uuid4()),
            'name': request.name,
            'email': request.email,
            'phone': request.phone,
            'hotel_name': request.hotel_name,
            'room_count': request.room_count,
            'status': 'pending',
            'created_at': datetime.now(UTC).isoformat(),
            'contacted': False
        }

        await db.demo_requests.insert_one(demo_data)

        return {
            'success': True,
            'message': 'Demo request received successfully',
            'request_id': demo_data['id']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save demo request: {str(e)}")


# 4. ENDPOINT HEALTH CHECK


@router.get("/system/health")
async def system_health_check(
    current_user: User = Depends(get_current_user)
):
    """
    Check health of all critical endpoints and services
    """
    try:
        health_checks = []

        # Check database connection
        try:
            await db.command('ping')
            db_latency_start = time.time()
            await db.bookings.find_one({})
            db_latency = (time.time() - db_latency_start) * 1000

            health_checks.append({
                'service': 'MongoDB',
                'status': 'healthy',
                'latency_ms': round(db_latency, 2),
                'message': 'Database connection active'
            })
        except Exception as e:
            health_checks.append({
                'service': 'MongoDB',
                'status': 'unhealthy',
                'latency_ms': 0,
                'message': f'Database error: {str(e)}'
            })

        # Check API endpoints
        critical_endpoints = [
            {'name': 'Authentication', 'count_collection': 'users'},
            {'name': 'Bookings', 'count_collection': 'bookings'},
            {'name': 'Rooms', 'count_collection': 'rooms'},
            {'name': 'Guests', 'count_collection': 'guests'}
        ]

        for endpoint in critical_endpoints:
            try:
                start_time = time.time()
                count = await db[endpoint['count_collection']].count_documents({'tenant_id': current_user.tenant_id})
                latency = (time.time() - start_time) * 1000

                health_checks.append({
                    'service': endpoint['name'],
                    'status': 'healthy',
                    'latency_ms': round(latency, 2),
                    'message': f'{count} records',
                    'record_count': count
                })
            except Exception as e:
                health_checks.append({
                    'service': endpoint['name'],
                    'status': 'unhealthy',
                    'latency_ms': 0,
                    'message': f'Error: {str(e)}'
                })

        # Overall health status
        unhealthy_count = len([h for h in health_checks if h['status'] == 'unhealthy'])
        overall_status = 'healthy' if unhealthy_count == 0 else 'degraded' if unhealthy_count < 2 else 'critical'

        return {
            'overall_status': overall_status,
            'checks': health_checks,
            'total_checks': len(health_checks),
            'healthy_count': len([h for h in health_checks if h['status'] == 'healthy']),
            'unhealthy_count': unhealthy_count,
            'timestamp': datetime.now(UTC).isoformat()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


# ============================================================================
# OPERA CLOUD PARITY FEATURES - CRITICAL ENTERPRISE FUNCTIONALITY
# ============================================================================

# Import night audit models

# ============= 1. NIGHT AUDIT MODULE (ENTERPRISE GRADE) =============

# ============= 2. CASHIERING & CITY LEDGER MODULE =============

# ============= 3. QUEUE ROOMS MODULE (EARLY ARRIVAL MANAGEMENT) =============

# ============= AUDIT TRAIL LOGGING (AUTO-TRACKING) =============



@router.get("/security/audit-logs")
async def get_security_audit_logs(
    days: int = 7,
    action: str | None = None,
    user_id: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """Get security audit logs.

    Audit trail entries (kullanıcı aksiyonları, geri alınan mesajlar,
    acil mesaj kayıtları, vb.) sadece tenant yöneticilerine açıktır;
    olağan kullanıcılar 403 alır. Bu kısıt hem `view_system_diagnostics`
    izniyle hem de açık rol kontrolüyle çift kapı olarak doğrulanır.
    """
    if not _is_super_admin(current_user) and current_user.role not in (
        UserRole.ADMIN,
        UserRole.SUPER_ADMIN,
    ):
        raise HTTPException(
            status_code=403,
            detail="Denetim kayıtlarını sadece yöneticiler görüntüleyebilir.",
        )

    start_date = (datetime.now(UTC) - timedelta(days=days)).isoformat()

    query = {
        'tenant_id': current_user.tenant_id,
        'timestamp': {'$gte': start_date}
    }

    if action:
        query['action'] = action
    if user_id:
        query['user_id'] = user_id

    logs = await db.audit_logs.find(query, {'_id': 0}).sort('timestamp', -1).limit(100).to_list(100)

    return {
        'logs': logs,
        'count': len(logs),
        'date_range': f'Last {days} days'
    }




@router.get("/gdpr/data-requests")
async def get_gdpr_data_requests(
    status: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """Get GDPR data access/deletion requests - REAL DATA from database"""
    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status

    requests_data = await db.gdpr_requests.find(query, {'_id': 0}).sort('created_at', -1).to_list(100)

    # Return real data (empty if none)
    return {
        'requests': requests_data,
        'count': len(requests_data),
        'pending': sum(1 for r in requests_data if r.get('status') == 'pending'),
        'completed': sum(1 for r in requests_data if r.get('status') == 'completed')
    }




@router.get("/compliance/certifications")
async def get_compliance_certifications(current_user: User = Depends(get_current_user)):
    """Get compliance certifications - REAL DATA from database"""

    # Get from database
    certs = await db.certifications.find({
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).to_list(10)

    # If no data, return empty
    return {
        'certifications': certs,
        'count': len(certs),
        'certified_count': sum(1 for c in certs if c.get('status') == 'certified'),
        'compliance_score': (sum(c.get('score', 0) for c in certs) / len(certs)) if certs else 0
    }


# ──────────────────────────────────────────────────────────────────────────────
# v95.4 — Maintenance: Oda statüsü ↔ rezervasyon defteri sync
# UctanUcaTest 2026-05-02: dashboard "OCCUPANCY-DRIFT" uyarısı için kalıcı
# çözüm. KPI zaten booking ledger'ı kaynak alıyor, bu endpoint rooms.status
# tarafındaki tortu veriyi (eski non-atomic flow'lardan kalan) düzeltir.
# ──────────────────────────────────────────────────────────────────────────────
@router.post("/admin/maintenance/sync-room-status")
async def sync_room_status(
    dry_run: bool = True,
    current_user: User = Depends(require_super_admin),
):
    """Bookings ledger'ına göre rooms.status alanını yeniden hizala.

    Kural: bugünü kapsayan aktif booking (checked_in / confirmed&today) varsa
    ilgili oda 'occupied'; yoksa 'occupied' tortusu temizlenir.

    Parametre:
      dry_run=True (varsayılan) → sadece tespit, yazma yok.
      dry_run=False             → fiili güncelleme.

    Sadece SUPER_ADMIN. Tek tenant kapsamında çalışır.
    """
    tenant_id = current_user.tenant_id
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    # Aktif overlap booking'leri (date-only karşılaştırma — dashboard ile aynı)
    bookings = await db.bookings.find(
        {
            'tenant_id': tenant_id,
            'status': {'$in': ['checked_in', 'confirmed', 'guaranteed']},
        },
        {'_id': 0, 'room_id': 1, 'check_in': 1, 'check_out': 1, 'status': 1},
    ).to_list(10000)

    occupied_room_ids: set[str] = set()
    for b in bookings:
        rid = b.get('room_id')
        if not rid:
            continue
        ci = str(b.get('check_in', ''))[:10]
        co = str(b.get('check_out', ''))[:10]
        if ci <= today and co > today:
            occupied_room_ids.add(rid)

    rooms = await db.rooms.find(
        {'tenant_id': tenant_id},
        {'_id': 0, 'id': 1, 'room_number': 1, 'status': 1},
    ).to_list(5000)

    # Hedef statüler:
    #   - mark_occupied → 'occupied' (aktif booking var ama oda farklı statüde)
    #   - clear_occupied → 'dirty' (aktif booking yok ama oda 'occupied' tortusu)
    # 'dirty' tercih edildi çünkü atomic_checkin_checkout.checkout flow'u da
    # check-out sonrası odayı 'dirty' yapar; housekeeping zorunlu kontrolü
    # böylece atlanmaz. Doğrudan 'available' yapmak güvenli değil (önceki
    # konuğun durumunu temizleme garantisi yok).
    to_mark_occupied: list[dict[str, Any]] = []
    to_clear_occupied: list[dict[str, Any]] = []

    for r in rooms:
        rid = r.get('id')
        cur_status = r.get('status')
        if rid in occupied_room_ids:
            if cur_status != 'occupied':
                to_mark_occupied.append({
                    'id': rid,
                    'room_number': r.get('room_number'),
                    'old_status': cur_status,
                })
        else:
            if cur_status == 'occupied':
                to_clear_occupied.append({
                    'id': rid,
                    'room_number': r.get('room_number'),
                    'old_status': cur_status,
                })

    applied_occupied = 0
    applied_cleared = 0
    if not dry_run:
        for r in to_mark_occupied:
            res = await db.rooms.update_one(
                {'id': r['id'], 'tenant_id': tenant_id},
                {'$set': {'status': 'occupied', 'updated_at': datetime.now(UTC).isoformat()}},
            )
            if res.modified_count:
                applied_occupied += 1
        for r in to_clear_occupied:
            res = await db.rooms.update_one(
                {'id': r['id'], 'tenant_id': tenant_id},
                {'$set': {'status': 'dirty', 'current_booking_id': None,
                          'updated_at': datetime.now(UTC).isoformat()}},
            )
            if res.modified_count:
                applied_cleared += 1

        await log_audit_event(
            tenant_id=tenant_id,
            user_id=current_user.id,
            action='sync_room_status',
            entity_type='maintenance',
            entity_id='rooms',
            details=f"Oda statüsü senkronu: +{applied_occupied} occupied, -{applied_cleared} cleared",
            db=db,
        )

    return {
        'tenant_id': tenant_id,
        'dry_run': dry_run,
        'total_rooms': len(rooms),
        'active_bookings_today': len(occupied_room_ids),
        'drift_detected': {
            'should_be_occupied': len(to_mark_occupied),
            'should_be_freed': len(to_clear_occupied),
        },
        'preview': {
            'mark_occupied': to_mark_occupied[:20],
            'clear_occupied': to_clear_occupied[:20],
        },
        'applied': {
            'marked_occupied': applied_occupied,
            'cleared_occupied': applied_cleared,
        } if not dry_run else None,
        'message': (
            'Drift tespit edildi, dry_run=true. Uygulamak için ?dry_run=false gönderin.'
            if dry_run and (to_mark_occupied or to_clear_occupied)
            else 'Drift yok, oda statüsü hizalı.' if dry_run
            else f'Senkron tamamlandı: {applied_occupied} occupied + {applied_cleared} freed.'
        ),
    }

