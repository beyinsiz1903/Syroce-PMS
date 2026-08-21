"""
tenants

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
)
from core.tenant_db import get_system_db

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
from domains.admin.subscription_models import get_plan_default_modules
from models.enums import ROLE_PERMISSIONS, Permission, UserRole
from models.schemas import Tenant, TenantRegister, User


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
    AdminCreateChainRequest,
    AdminCreateTeamMemberRequest,
    AdminNilveraProvisioningRequest,
    AdminProviderCredentialsRequest,
    AdminUpdateTenantInfoRequest,
    SubscriptionUpdateRequest,
    TenantModulesUpdate,
    TenantProvisioningUpdate,
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


CHANNEL_PROVIDER_FIELDS = {
    "hotelrunner": {
        "display_name": "HotelRunner",
        "fields": [
            {"key": "token", "label": "API Token", "type": "password", "required": True},
            {"key": "hr_id", "label": "HR ID (Hotel ID)", "type": "text", "required": True},
        ],
    },
    "exely": {
        "display_name": "Exely",
        "fields": [
            {"key": "username", "label": "SOAP Username", "type": "text", "required": True},
            {"key": "password", "label": "SOAP Password", "type": "password", "required": True},
            {"key": "hotel_code", "label": "Hotel Code", "type": "text", "required": True},
            {"key": "endpoint_url", "label": "SOAP Endpoint URL", "type": "text", "required": False},
        ],
    },
}


def _validate_provider_credentials(provider: str, credentials: dict[str, str]) -> dict[str, str]:
    definition = CHANNEL_PROVIDER_FIELDS.get(provider)
    if not definition:
        raise HTTPException(status_code=400, detail="Desteklenmeyen kanal yöneticisi")
    allowed = {field["key"] for field in definition["fields"]}
    cleaned = {
        key: str(value).strip()
        for key, value in credentials.items()
        if key in allowed and value is not None and str(value).strip()
    }
    missing = [field["label"] for field in definition["fields"] if field["required"] and not cleaned.get(field["key"])]
    if missing:
        raise HTTPException(status_code=400, detail=f"Zorunlu alanlar eksik: {', '.join(missing)}")
    return cleaned


async def _require_target_tenant(sys_db, tenant_id: str) -> dict:
    tenant_doc = await sys_db.tenants.find_one({"id": tenant_id}, {"_id": 0})
    if not tenant_doc:
        raise HTTPException(status_code=404, detail="Otel bulunamadı")
    return tenant_doc


@router.get("/admin/chains")
async def list_hotel_chains(current_user: User = Depends(require_super_admin)):
    """Süperadmin kurulum ekranı için zincirleri ve üye sayılarını döndürür."""
    sys_db = get_system_db()
    chains = await sys_db.hotel_chains.find({}, {"_id": 0}).sort("name", 1).to_list(1000)
    for chain in chains:
        chain["property_count"] = await sys_db.tenants.count_documents({"chain_id": chain["id"]})
    return {"chains": chains}


@router.post("/admin/chains")
async def create_hotel_chain(
    payload: AdminCreateChainRequest,
    current_user: User = Depends(require_super_admin),
):
    from core.audit import log_audit_event

    sys_db = get_system_db()
    name = payload.name.strip()
    existing = await sys_db.hotel_chains.find_one({"name_normalized": name.casefold()}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=409, detail="Bu isimde bir zincir zaten var")
    if payload.headquarters_tenant_id:
        target_tenant = await _require_target_tenant(sys_db, payload.headquarters_tenant_id)
        if target_tenant.get("chain_id"):
            raise HTTPException(status_code=409, detail="Otel zaten bir zincire bağlı; önce mevcut zincir üyeliğini kaldırın")
    now = datetime.now(UTC).isoformat()
    chain = {
        "id": str(uuid.uuid4()),
        "name": name,
        "name_normalized": name.casefold(),
        "headquarters_tenant_id": payload.headquarters_tenant_id,
        "created_at": now,
        "created_by": current_user.id,
        "updated_at": now,
    }
    await sys_db.hotel_chains.insert_one(chain.copy())
    if payload.headquarters_tenant_id:
        await sys_db.tenants.update_one(
            {"id": payload.headquarters_tenant_id},
            {"$set": {"chain_id": chain["id"], "is_chain_headquarters": True, "modules.multi_property": True}},
        )
    await log_audit_event(
        tenant_id=payload.headquarters_tenant_id or current_user.tenant_id,
        user_id=current_user.id,
        action="hotel_chain_created",
        entity_type="hotel_chain",
        entity_id=chain["id"],
        details=f"{name} zinciri oluşturuldu",
        after_value={"name": name, "headquarters_tenant_id": payload.headquarters_tenant_id},
        db=sys_db,
    )
    return {"success": True, "chain": chain}


@router.get("/admin/tenants/{tenant_id}/provisioning")
async def get_tenant_provisioning(
    tenant_id: str,
    current_user: User = Depends(require_super_admin),
):
    """Hedef otele ait zincir ve entegrasyon durumunu, sırları açmadan döndürür."""
    from core.integrations.nilvera.provisioner import get_nilvera_tenant_config
    from domains.channel_manager import credential_vault as vault

    sys_db = get_system_db()
    tenant_doc = await _require_target_tenant(sys_db, tenant_id)
    provider_summaries = []
    for provider, definition in CHANNEL_PROVIDER_FIELDS.items():
        masked = await vault.get_masked_credentials(tenant_id, provider, "default", database=sys_db)
        connection = await sys_db.provider_connections.find_one(
            {"tenant_id": tenant_id, "provider": provider, "property_id": "default"},
            {"_id": 0, "status": 1, "last_successful_sync": 1, "last_error": 1},
        )
        provider_summaries.append(
            {
                "provider": provider,
                "display_name": definition["display_name"],
                "fields": definition["fields"],
                "has_credentials": masked is not None,
                "credentials": masked,
                "connection": connection or {"status": "not_configured"},
            }
        )
    chain = None
    if tenant_doc.get("chain_id"):
        chain = await sys_db.hotel_chains.find_one({"id": tenant_doc["chain_id"]}, {"_id": 0})
    return {
        "tenant": {
            "id": tenant_doc.get("id"),
            "hotel_id": tenant_doc.get("hotel_id"),
            "property_name": tenant_doc.get("property_name"),
            "channel_manager_provider": tenant_doc.get("channel_manager_provider"),
            "chain_id": tenant_doc.get("chain_id"),
            "is_chain_headquarters": bool(tenant_doc.get("is_chain_headquarters")),
        },
        "chain": chain,
        "providers": provider_summaries,
        "nilvera": await get_nilvera_tenant_config(tenant_id),
    }


@router.patch("/admin/tenants/{tenant_id}/provisioning")
async def update_tenant_provisioning(
    tenant_id: str,
    payload: TenantProvisioningUpdate,
    current_user: User = Depends(require_super_admin),
):
    """Sağlayıcı seçimi ve zincir üyeliğini günceller; dış sağlayıcı çağrısı yapmaz."""
    from core.audit import log_audit_event

    sys_db = get_system_db()
    before = await _require_target_tenant(sys_db, tenant_id)
    updates: dict[str, object] = {"provisioning_updated_at": datetime.now(UTC).isoformat()}
    if "channel_manager_provider" in payload.model_fields_set:
        updates["channel_manager_provider"] = payload.channel_manager_provider
    if "chain_id" in payload.model_fields_set:
        chain_id = (payload.chain_id or "").strip() or None
        if chain_id:
            chain = await sys_db.hotel_chains.find_one({"id": chain_id}, {"_id": 0})
            if not chain:
                raise HTTPException(status_code=404, detail="Zincir bulunamadı")
        updates["chain_id"] = chain_id
        if chain_id:
            updates["modules.multi_property"] = True
        if chain_id is None:
            updates["is_chain_headquarters"] = False
    if "is_chain_headquarters" in payload.model_fields_set:
        if payload.is_chain_headquarters and not updates.get("chain_id", before.get("chain_id")):
            raise HTTPException(status_code=400, detail="Merkez tesis için önce zincir seçilmelidir")
        updates["is_chain_headquarters"] = bool(payload.is_chain_headquarters)
    await sys_db.tenants.update_one({"id": tenant_id}, {"$set": updates})
    after = await _require_target_tenant(sys_db, tenant_id)
    before_chain_id = before.get("chain_id")
    after_chain_id = after.get("chain_id")
    if before.get("is_chain_headquarters") and before_chain_id and (
        before_chain_id != after_chain_id or not after.get("is_chain_headquarters")
    ):
        await sys_db.hotel_chains.update_one(
            {"id": before_chain_id, "headquarters_tenant_id": tenant_id},
            {"$set": {"headquarters_tenant_id": None, "updated_at": datetime.now(UTC).isoformat()}},
        )
    if after.get("is_chain_headquarters") and after_chain_id:
        await sys_db.tenants.update_many(
            {"chain_id": after_chain_id, "id": {"$ne": tenant_id}},
            {"$set": {"is_chain_headquarters": False}},
        )
        await sys_db.hotel_chains.update_one(
            {"id": after_chain_id},
            {"$set": {"headquarters_tenant_id": tenant_id, "updated_at": datetime.now(UTC).isoformat()}},
        )
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=current_user.id,
        action="tenant_provisioning_updated",
        entity_type="tenant",
        entity_id=tenant_id,
        details="Süperadmin otel kurulum kapsamını güncelledi",
        before_value={k: before.get(k) for k in ("channel_manager_provider", "chain_id", "is_chain_headquarters")},
        after_value={k: after.get(k) for k in ("channel_manager_provider", "chain_id", "is_chain_headquarters")},
        db=sys_db,
    )
    _invalidate_admin_tenants_cache(getattr(current_user, "tenant_id", None))
    return {"success": True, "tenant": {k: after.get(k) for k in ("id", "channel_manager_provider", "chain_id", "is_chain_headquarters")}}


@router.post("/admin/tenants/{tenant_id}/integrations/{provider}/credentials")
async def save_target_provider_credentials(
    tenant_id: str,
    provider: str,
    payload: AdminProviderCredentialsRequest,
    current_user: User = Depends(require_super_admin),
):
    """Hedef otelin Exely/HotelRunner sırlarını şifreler; test veya sync çalıştırmaz."""
    from core.audit import log_audit_event
    from domains.channel_manager import credential_vault as vault

    sys_db = get_system_db()
    await _require_target_tenant(sys_db, tenant_id)
    credentials = _validate_provider_credentials(provider, payload.credentials)
    secret_id = await vault.store_secret(tenant_id, provider, "default", credentials, database=sys_db)
    now = datetime.now(UTC).isoformat()
    definition = CHANNEL_PROVIDER_FIELDS[provider]
    await sys_db.provider_connections.update_one(
        {"tenant_id": tenant_id, "provider": provider, "property_id": "default"},
        {
            "$set": {
                "credentials_ref": secret_id,
                "status": "draft",
                "display_name": f"{definition['display_name']} - default",
                "updated_at": now,
                "updated_by": current_user.id,
            },
            "$setOnInsert": {
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "provider": provider,
                "property_id": "default",
                "created_at": now,
                "created_by": current_user.id,
                "sync_inventory": True,
                "sync_rates": True,
                "sync_reservations": True,
                "sync_restrictions": True,
            },
            "$unset": {"credentials": "", "token": "", "password": "", "username": ""},
        },
        upsert=True,
    )
    await sys_db.tenants.update_one({"id": tenant_id}, {"$set": {"channel_manager_provider": provider}})
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=current_user.id,
        action="integration_credentials_stored",
        entity_type="provider_connection",
        entity_id=provider,
        details=f"{definition['display_name']} kimlik bilgileri şifreli olarak kaydedildi; bağlantı testi çalıştırılmadı",
        after_value={"provider": provider, "field_names": sorted(credentials), "status": "draft"},
        db=sys_db,
    )
    return {"success": True, "provider": provider, "has_credentials": True, "status": "draft", "connection_tested": False}


@router.put("/admin/tenants/{tenant_id}/integrations/nilvera")
async def save_target_nilvera_config(
    tenant_id: str,
    payload: AdminNilveraProvisioningRequest,
    current_user: User = Depends(require_super_admin),
):
    """Nilvera tenant ayarlarını şifreli kaydeder; Nilvera API çağrısı yapmaz."""
    from core.audit import log_audit_event
    from core.integrations.nilvera.provisioner import update_nilvera_tenant_config

    sys_db = get_system_db()
    await _require_target_tenant(sys_db, tenant_id)
    try:
        summary = await update_nilvera_tenant_config(
            tenant_id,
            enabled=payload.enabled,
            api_key=payload.api_key,
            seller=payload.seller,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await log_audit_event(
        tenant_id=tenant_id,
        user_id=current_user.id,
        action="nilvera_provisioning_updated",
        entity_type="integration",
        entity_id="nilvera",
        details="Nilvera ayarları güncellendi; dış servis çağrısı yapılmadı",
        after_value={"enabled": summary["enabled"], "api_key_set": summary["api_key_set"], "seller_configured": bool(summary["seller"])},
        db=sys_db,
    )
    return {"success": True, "nilvera": summary, "connection_tested": False}


# ── GET /admin/property-types ──
@router.get("/admin/property-types")
async def list_property_types():
    """List all available property types with their profiles (public endpoint for tenant creation form)"""
    return {"property_types": get_all_property_types()}


# ── GET /admin/property-types/{property_type} ──
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


# ── GET /admin/tenants ──
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


# ── GET /admin/module-report ──
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


# ── POST /admin/tenants ──
@router.post("/admin/tenants")
async def create_tenant(payload: TenantRegister, current_user: User = Depends(require_super_admin)):
    """Create a new hotel/tenant (SUPER ADMIN only)"""

    # Cross-tenant platform op: bypass tenant scoping for tenant/user creation.
    from core.tenant_db import get_system_db

    sys_db = get_system_db()

    # Check if tenant with same email already exists
    existing = await sys_db.tenants.find_one({"$or": [{"contact_email": payload.email}, {"email": payload.email}]})
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

    # Per-tenant module override: operator picked specific modules / sub-modules
    # in the registration form. Merge on top of property-type defaults so any
    # key the operator did NOT touch keeps its profile default.
    if payload.modules:
        for key, value in payload.modules.items():
            if not isinstance(key, str) or not key:
                continue
            try:
                combined_modules[key] = bool(value)
            except Exception:
                continue

    if payload.chain_mode != "standalone":
        combined_modules["multi_property"] = True

    from core.hotel_ids import generate_unique_hotel_id

    new_hotel_id = await generate_unique_hotel_id(sys_db)

    chain_id = None
    new_chain_doc = None
    is_chain_headquarters = False
    if payload.chain_mode == "existing_chain":
        if not payload.chain_id:
            raise HTTPException(status_code=400, detail="Mevcut zincir seçilmelidir")
        chain = await sys_db.hotel_chains.find_one({"id": payload.chain_id}, {"_id": 0})
        if not chain:
            raise HTTPException(status_code=404, detail="Zincir bulunamadı")
        chain_id = payload.chain_id
    elif payload.chain_mode == "new_chain":
        chain_name = (payload.chain_name or "").strip()
        if len(chain_name) < 2:
            raise HTTPException(status_code=400, detail="Zincir adı en az 2 karakter olmalıdır")
        duplicate_chain = await sys_db.hotel_chains.find_one({"name_normalized": chain_name.casefold()}, {"_id": 0, "id": 1})
        if duplicate_chain:
            raise HTTPException(status_code=409, detail="Bu isimde bir zincir zaten var")
        chain_id = str(uuid.uuid4())
        is_chain_headquarters = True
        new_chain_doc = {
            "id": chain_id,
            "name": chain_name,
            "name_normalized": chain_name.casefold(),
            "headquarters_tenant_id": None,
            "created_at": start_date.isoformat(),
            "created_by": current_user.id,
            "updated_at": start_date.isoformat(),
        }

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
        chain_id=chain_id,
        is_chain_headquarters=is_chain_headquarters,
    )

    tenant_dict = new_tenant.model_dump()
    tenant_dict["created_at"] = tenant_dict["created_at"].isoformat()
    tenant_dict["email"] = payload.email
    tenant_dict["phone"] = payload.phone
    tenant_dict["description"] = payload.description or ""
    tenant_dict["dashboard_layout"] = dashboard_layout
    tenant_dict["hidden_nav_groups"] = nav_config.get("hidden_nav_groups", [])
    tenant_dict["hidden_nav_items"] = nav_config.get("hidden_nav_items", [])
    if payload.channel_manager_provider:
        tenant_dict["channel_manager_provider"] = payload.channel_manager_provider
    await sys_db.tenants.insert_one(tenant_dict)
    if new_chain_doc:
        new_chain_doc["headquarters_tenant_id"] = new_tenant.id
        await sys_db.hotel_chains.insert_one(new_chain_doc)

    # B2B connect code: yeni otel icin otele ozel baglanti kodu uret (Secenek B
    # oto-saglama). Best-effort — kod uretimi otel kurulumunu engellemez.
    connect_code_raw = None
    try:
        from routers.b2b_api._provisioning import ensure_connect_code_for_tenant

        _cc = await ensure_connect_code_for_tenant(sys_db, new_tenant.id)
        if _cc:
            connect_code_raw = _cc.get("connect_code")
    except Exception as _cc_err:
        logger.warning(f"B2B connect code uretilemedi tenant={new_tenant.id}: {_cc_err}")

    # Create admin user for this tenant
    hashed_password = hash_password(payload.password)

    new_user = User(tenant_id=new_tenant.id, email=payload.email, name=payload.name, phone=payload.phone, password_hash=hashed_password, role=UserRole.ADMIN)

    user_dict = new_user.model_dump()
    user_dict["created_at"] = user_dict["created_at"].isoformat()
    # Rename password_hash to hashed_password for login compatibility
    user_dict["hashed_password"] = user_dict.pop("password_hash", hashed_password)
    user_dict = encrypt_user_doc(user_dict)
    await sys_db.users.insert_one(user_dict)

    return {
        "success": True,
        "message": "Hotel created successfully",
        "tenant_id": new_tenant.id,
        "user_id": new_user.id,
        "hotel_id": new_hotel_id,
        "b2b_connect_code": connect_code_raw,
        "subscription_start": start_date.isoformat(),
        "subscription_end": end_date.isoformat() if end_date else "Unlimited",
        "subscription_days": payload.subscription_days or "Unlimited",
    }


# ── PATCH /admin/tenants/{tenant_id}/modules ──
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
    # Kanal yoneticisi altyapisi secimi yalnizca explicit gonderildiyse yazilir
    # (modules yazimini bozmadan). None gonderilirse secim temizlenir -> auto-detect.
    if "channel_manager_provider" in payload.model_fields_set:
        update_doc["$set"]["channel_manager_provider"] = payload.channel_manager_provider

    result = await db.tenants.update_one(query, update_doc)
    if result.matched_count == 0:
        # Fallback to Mongo _id
        try:
            from bson import ObjectId

            result = await db.tenants.update_one({"_id": ObjectId(tenant_id)}, update_doc)
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

        tenant_doc = await db.tenants.find_one({"_id": ObjectId(tenant_id)}, {"_id": 0})

    if not tenant_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hotel not found",
        )

    tenant_doc["modules"] = get_tenant_modules(tenant_doc)
    return tenant_doc


# ── PATCH /admin/tenants/{tenant_id}/subscription ──
@router.patch("/admin/tenants/{tenant_id}/subscription")
async def update_tenant_subscription(tenant_id: str, payload: SubscriptionUpdateRequest, current_user: User = Depends(require_super_admin)):
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
            if len(value) == 10 and value[4] == "-" and value[7] == "-":
                dt = datetime.fromisoformat(value)
                return dt.replace(tzinfo=UTC)

            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
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

    result = await db.tenants.update_one({"id": tenant_id}, {"$set": update_data})

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


# ── PATCH /admin/tenants/{tenant_id}/tier ──
@router.patch("/admin/tenants/{tenant_id}/tier")
async def update_tenant_tier(tenant_id: str, payload: dict, current_user: User = Depends(require_super_admin)):
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


# ── PATCH /admin/tenants/{tenant_id}/info ──
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


# ── GET /admin/tenants/{tenant_id}/team ──
@router.get("/admin/tenants/{tenant_id}/team")
async def admin_list_tenant_team(
    tenant_id: str,
    current_user: User = Depends(require_super_admin),
):
    """List team members for a specific tenant (SUPER ADMIN only)"""
    # Cross-tenant admin read: the request's tenant context is the super_admin's
    # OWN tenant (set from JWT by TenantContextMiddleware), so the scoped proxy
    # would reject these explicit foreign-tenant_id queries as a TenantViolation.
    # require_super_admin already gates this; the target tenant_id is path-bound
    # and every query below carries it explicitly → use the system (unscoped) db,
    # the documented pattern for cross-tenant admin queries (see auth.py).
    sysdb = get_system_db()
    tenant = await sysdb.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Hotel not found")

    users_raw = await sysdb.users.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "hashed_password": 0, "password_hash": 0, "password": 0},
    ).to_list(200)
    users = [decrypt_user_doc(u) for u in users_raw]

    return {"users": users, "count": len(users), "tenant_id": tenant_id}


# ── POST /admin/tenants/{tenant_id}/team ──
@router.post("/admin/tenants/{tenant_id}/team")
async def admin_add_tenant_team_member(
    tenant_id: str,
    payload: AdminCreateTeamMemberRequest,
    current_user: User = Depends(require_super_admin),
):
    """Add a team member to a specific tenant (SUPER ADMIN only)"""
    # Cross-tenant admin write: scoped proxy is bound to the super_admin's own
    # tenant, so inserting {tenant_id: <target>} trips _inject_doc's TenantViolation
    # (403). The email-uniqueness check must also be GLOBAL — login resolves users
    # by email across all tenants via get_system_db (auth.py), so a scoped dup-check
    # would miss a global collision. require_super_admin gates this; tenant_id is
    # path-bound and set explicitly on the inserted doc → use the system db.
    sysdb = get_system_db()
    tenant = await sysdb.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Hotel not found")

    existing = await sysdb.users.find_one(build_user_email_query(payload.email))
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
    await sysdb.users.insert_one(new_user)

    return {
        "success": True,
        "message": f"{payload.name} added successfully ({payload.role})",
        "user_id": new_user["id"],
    }


# ── DELETE /admin/tenants/{tenant_id}/team/{user_id} ──
@router.delete("/admin/tenants/{tenant_id}/team/{user_id}")
async def admin_remove_tenant_team_member(
    tenant_id: str,
    user_id: str,
    current_user: User = Depends(require_super_admin),
):
    """Remove a team member from a specific tenant (SUPER ADMIN only)"""
    # Cross-tenant admin delete: scoped proxy bound to caller's own tenant would
    # reject the explicit foreign tenant_id filter. require_super_admin gates this;
    # both filters carry the path-bound tenant_id explicitly → use the system db.
    sysdb = get_system_db()
    target = await sysdb.users.find_one({"id": user_id, "tenant_id": tenant_id})
    if not target:
        raise HTTPException(status_code=404, detail="Team member not found")

    if target.get("role") == "super_admin":
        raise HTTPException(status_code=400, detail="Super Admin cannot be deleted")

    await sysdb.users.delete_one({"id": user_id, "tenant_id": tenant_id})
    return {"success": True, "message": "Team member removed"}


# ── PATCH /admin/tenants/{tenant_id}/team/{user_id}/role ──
@router.patch("/admin/tenants/{tenant_id}/team/{user_id}/role")
async def admin_update_tenant_team_role(
    tenant_id: str,
    user_id: str,
    payload: UpdateTeamMemberRoleRequest,
    current_user: User = Depends(require_super_admin),
):
    """Update a team member's role (SUPER ADMIN only)"""
    # Cross-tenant admin update: scoped proxy bound to caller's own tenant would
    # reject the explicit foreign tenant_id filter. require_super_admin gates this;
    # every filter carries the path-bound tenant_id explicitly → use the system db.
    sysdb = get_system_db()
    target = await sysdb.users.find_one({"id": user_id, "tenant_id": tenant_id})
    if not target:
        raise HTTPException(status_code=404, detail="Team member not found")

    if target.get("role") == "super_admin":
        raise HTTPException(status_code=400, detail="Super Admin role cannot be changed")

    tier_doc = await sysdb.tenants.find_one({"id": tenant_id})
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
    res = await sysdb.users.update_one(
        {"id": user_id, "tenant_id": tenant_id},
        {"$set": {"role": payload.role}},
    )
    if res.matched_count == 0:
        # Lost the TOCTOU race — user moved tenant or was deleted between
        # find_one and update_one. Surface as 409 instead of false-success.
        raise HTTPException(status_code=409, detail="User changed concurrently, retry")
    return {"success": True, "message": f"Role updated: {payload.role}"}


# ── GET /admin/tenants/{tenant_id}/stats ──
@router.get("/admin/tenants/{tenant_id}/stats")
async def admin_get_tenant_stats(
    tenant_id: str,
    current_user: User = Depends(require_super_admin),
):
    """Get detailed stats for a specific tenant (SUPER ADMIN only)"""
    # Cross-tenant admin read: scoped proxy bound to caller's own tenant would
    # reject these explicit foreign tenant_id counts. require_super_admin gates
    # this; every count carries the path-bound tenant_id explicitly → system db.
    sysdb = get_system_db()
    tenant = await sysdb.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Hotel not found")

    rooms = await sysdb.rooms.count_documents({"tenant_id": tenant_id})
    users = await sysdb.users.count_documents({"tenant_id": tenant_id})
    guests = await sysdb.guests.count_documents({"tenant_id": tenant_id})
    bookings = await sysdb.bookings.count_documents({"tenant_id": tenant_id})

    now = datetime.now(UTC)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0).isoformat()
    bookings_this_month = await sysdb.bookings.count_documents(
        {
            "tenant_id": tenant_id,
            "created_at": {"$gte": month_start},
        }
    )

    checked_in = await sysdb.bookings.count_documents(
        {
            "tenant_id": tenant_id,
            "status": "checked_in",
        }
    )

    return {
        "tenant_id": tenant_id,
        "rooms": rooms,
        "users": users,
        "guests": guests,
        "total_bookings": bookings,
        "bookings_this_month": bookings_this_month,
        "checked_in": checked_in,
    }
