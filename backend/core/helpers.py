"""
Syroce PMS - Shared Helper Functions
Common utilities used across multiple routers.
"""

from typing import Any

from fastapi import Depends, HTTPException, status

from core.database import db
from core.security import _is_super_admin, get_current_user
from models.enums import UserRole
from models.schemas import AuditLog, User

# ================== PLAN & FEATURES ==================

FEATURES_BY_PLAN: dict[str, dict[str, bool]] = {
    # Mini — Elektraweb Mini muadili. 1-15 oda, butik/pansiyon hedefli;
    # rezervasyon + check-in/out + folyo + basit fatura + gün sonu + KBS
    # polis bildirimi + sanal POS + sınırlı channel manager (3 kanal)
    # paketinin "minimum çalışır PMS" sürümü. Bu plan, eski
    # `pms_lite`'den FARKLI: daha geniş — gün sonu, ödeme alma,
    # KBS bildirimi ve kanal entegrasyonu küçük tesis için kritik
    # operasyonel temeli oluşturuyor.
    "mini_pension": {
        "core_dashboard": True,
        "core_pms": True,
        "core_rooms": True,
        "core_rates_availability": True,
        "core_bookings_frontdesk": True,
        "core_calendar": True,
        "core_guests_basic": True,
        "core_housekeeping_basic": True,
        "core_basic_reporting": True,
        "core_mobile_view": True,
        # Elektraweb Mini eşdeğeri ek modüller:
        "mini_folio_basic": True,  # basit folyo (split/route yok)
        "mini_invoices_basic": True,  # PDF + e-arşiv
        "mini_night_audit_basic": True,  # tek-tıkla gün sonu
        "mini_channel_manager_lite": True,  # 3 kanal limiti
        "mini_payments_link": True,  # sanal POS + ödeme linki
        "mini_kbs_notify": True,  # polis kimlik bildirimi (KBS)
    },
    "core_small_hotel": {
        # Tüm Mini özellikleri + küçük-orta tesis için ek üst-katman.
        "core_dashboard": True,
        "core_pms": True,
        "core_rooms": True,
        "core_rates_availability": True,
        "core_bookings_frontdesk": True,
        "core_calendar": True,
        "core_guests_basic": True,
        "core_housekeeping_basic": True,
        "core_basic_reporting": True,
        "core_mobile_view": True,
        "mini_folio_basic": True,
        "mini_invoices_basic": True,
        "mini_night_audit_basic": True,
        "mini_channel_manager_lite": True,
        "mini_payments_link": True,
        "mini_kbs_notify": True,
        # Basic-only ek değerler:
        "basic_mailing": True,
        "basic_guest_advanced": True,
        "basic_housekeeping_advanced": True,
        "basic_cost_management": True,
        "basic_advanced_reporting": True,
    },
    "professional_city_hotel": {
        "core_dashboard": True,
        "core_pms": True,
        "core_rooms": True,
        "core_rates_availability": True,
        "core_bookings_frontdesk": True,
        "core_calendar": True,
        "core_guests_basic": True,
        "core_housekeeping_basic": True,
        "core_basic_reporting": True,
        "core_mobile_view": True,
        "pro_channel_manager": True,
        "pro_rate_manager": True,
        "pro_revenue_management": True,
        "pro_folio_billing": True,
        "pro_night_audit": True,
        "pro_invoicing": True,
        "pro_advanced_housekeeping": True,
        "pro_guest_advanced": True,
        "pro_group_reservations": True,
        "pro_allotments": True,
        "pro_pos_basic": True,
        "pro_maintenance": True,
    },
    "enterprise_resort": {
        "core_dashboard": True,
        "core_pms": True,
        "core_rooms": True,
        "core_rates_availability": True,
        "core_bookings_frontdesk": True,
        "core_calendar": True,
        "core_guests_basic": True,
        "core_housekeeping_basic": True,
        "core_basic_reporting": True,
        "core_mobile_view": True,
        "pro_channel_manager": True,
        "pro_rate_manager": True,
        "pro_revenue_management": True,
        "pro_folio_billing": True,
        "pro_night_audit": True,
        "pro_invoicing": True,
        "pro_advanced_housekeeping": True,
        "pro_guest_advanced": True,
        "pro_group_reservations": True,
        "pro_allotments": True,
        "pro_pos_basic": True,
        "pro_maintenance": True,
        "ent_multi_property": True,
        "ent_sales_crm": True,
        "ent_loyalty_program": True,
        "ent_spa_wellness": True,
        "ent_meetings_events": True,
        "ent_advanced_analytics": True,
        "ent_gm_dashboards": True,
        "ent_api_access": True,
        "ent_white_label": True,
        "ent_audit_trail": True,
    },
    "deluxe_plus": {
        "core_dashboard": True,
        "core_pms": True,
        "core_rooms": True,
        "core_rates_availability": True,
        "core_bookings_frontdesk": True,
        "core_calendar": True,
        "core_guests_basic": True,
        "core_housekeeping_basic": True,
        "core_basic_reporting": True,
        "core_mobile_view": True,
        "pro_channel_manager": True,
        "pro_rate_manager": True,
        "pro_revenue_management": True,
        "pro_folio_billing": True,
        "pro_night_audit": True,
        "pro_invoicing": True,
        "pro_advanced_housekeeping": True,
        "pro_guest_advanced": True,
        "pro_group_reservations": True,
        "pro_allotments": True,
        "pro_pos_basic": True,
        "pro_maintenance": True,
        "ent_multi_property": True,
        "ent_sales_crm": True,
        "ent_loyalty_program": True,
        "ent_spa_wellness": True,
        "ent_meetings_events": True,
        "ent_advanced_analytics": True,
        "ent_gm_dashboards": True,
        "ent_api_access": True,
        "ent_white_label": True,
        "ent_audit_trail": True,
        "dlx_ai_pricing": True,
        "dlx_ai_chatbot": True,
        "dlx_ai_predictive": True,
        "dlx_whatsapp_concierge": True,
        "dlx_social_radar": True,
        "dlx_revenue_autopilot": True,
        "dlx_guest_dna": True,
        "dlx_dynamic_staffing": True,
    },
    "pms_lite": {
        "core_dashboard": True,
        "core_pms": True,
        "core_rooms": True,
        "core_calendar": True,
        "core_guests_basic": True,
        "core_housekeeping_basic": True,
    },
}


# Opt-in extra features that intentionally belong to NO subscription plan and
# therefore ship dark (default OFF for every tenant). They can only be turned
# on by an explicit per-tenant `features` override. Without registering them
# here, such an override is silently dropped because `resolve_tenant_features`
# only honors keys already present in some plan.
#   - hidden_marketplace: B2B marketplace procurement write surface
#     (purchase-order create/cancel). Default OFF in prod; granted per-tenant.
OPT_IN_EXTRA_FEATURES: set[str] = {"hidden_marketplace"}


def resolve_tenant_features(tenant_doc: dict[str, Any]) -> dict[str, bool]:
    """Plan + overrides ile efektif feature set uretir."""
    tenant_doc = tenant_doc or {}
    plan = tenant_doc.get("subscription_plan") or tenant_doc.get("plan") or tenant_doc.get("subscription_tier") or "core_small_hotel"
    all_keys: set = set()
    for _plan, feats in FEATURES_BY_PLAN.items():
        for k in (feats or {}).keys():
            all_keys.add(k)
    all_keys |= OPT_IN_EXTRA_FEATURES
    resolved: dict[str, bool] = dict.fromkeys(all_keys, False)
    plan_feats = FEATURES_BY_PLAN.get(plan) or FEATURES_BY_PLAN.get("core_small_hotel") or {}
    for k, v in plan_feats.items():
        resolved[k] = bool(v)
    tenant_overrides = tenant_doc.get("features") or {}
    if isinstance(tenant_overrides, dict):
        if plan == "pms_lite":
            for k in plan_feats.keys():
                if k in tenant_overrides:
                    resolved[k] = bool(tenant_overrides[k])
        else:
            for k in resolved.keys():
                if k in tenant_overrides:
                    resolved[k] = bool(tenant_overrides[k])
        # Opt-in extra features belong to no plan, so the loops above never
        # touch them under pms_lite (and only coincidentally otherwise). Apply
        # their explicit override regardless of plan — still default OFF when
        # no override is present.
        for k in OPT_IN_EXTRA_FEATURES:
            if k in tenant_overrides:
                resolved[k] = bool(tenant_overrides[k])
    return resolved


async def load_tenant_doc(tenant_id: str) -> dict[str, Any] | None:
    """tenant_id hem id alani hem de _id(ObjectId veya string) icin calissin."""
    if not tenant_id:
        return None
    doc = await db.tenants.find_one({"_id": tenant_id})
    if doc:
        if "_id" in doc:
            doc["_id"] = str(doc["_id"])
        return doc
    doc = await db.tenants.find_one({"id": tenant_id}, {"_id": 0})
    if doc:
        return doc
    try:
        from bson import ObjectId

        if len(tenant_id) == 24:
            doc = await db.tenants.find_one({"_id": ObjectId(tenant_id)})
            if doc:
                doc.pop("_id", None)
                return doc
    except Exception:
        pass
    return None


async def create_audit_log(
    tenant_id: str,
    user,
    action: str,
    entity_type: str,
    entity_id: str,
    changes: dict | None = None,
    ip_address: str | None = None,
):
    """Create an audit log entry."""
    audit = AuditLog(
        tenant_id=tenant_id,
        user_id=user.id,
        user_name=user.name,
        user_role=user.role,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        changes=changes,
        ip_address=ip_address,
    )
    audit_dict = audit.model_dump()
    audit_dict["timestamp"] = audit_dict["timestamp"].isoformat()
    await db.audit_logs.insert_one(audit_dict)


MODULE_DEFAULTS: dict[str, bool] = {
    "pms": True,
    "reservation_calendar": True,
    "dashboard": True,
    "guests": True,
    "housekeeping": True,
    "basic_reporting": True,
    "settings": True,
    "pms_mobile": True,
    "invoices_basic": True,
    "channel_manager": True,
    "folio_management": True,
    "night_audit": True,
    "invoices": True,
    "cost_management": True,
    "reports": True,
    "mobile_housekeeping": True,
    "rate_management": True,
    "booking_engine": True,
    "guest_advanced": True,
    "revenue_management": True,
    "multi_property": True,
    "group_sales": True,
    "sales_crm": True,
    "loyalty_program": True,
    "gm_dashboards": True,
    "mobile_revenue": True,
    "advanced_analytics": True,
    "api_access": True,
    "white_label": True,
    "audit_trail": True,
    "ai": True,
    "ai_chatbot": True,
    "ai_pricing": True,
    "ai_whatsapp": True,
    "ai_predictive": True,
    "ai_reputation": True,
    "ai_revenue_autopilot": True,
    "ai_social_radar": True,
    # Add-on modules — sold separately, default OFF.
    "spa": False,
    "mice": False,
    "academy": False,
}


def get_tenant_modules(tenant_doc: dict[str, Any]) -> dict[str, bool]:
    """Merge stored tenant modules with tier-based defaults."""
    from domains.admin.subscription_models import get_plan_default_modules

    tier = (tenant_doc.get("subscription_tier") or "basic").lower()
    if tier == "pro":
        tier = "professional"
    if tier == "ultra":
        tier = "enterprise"
    merged = get_plan_default_modules(tier)
    modules = tenant_doc.get("modules")
    if isinstance(modules, dict) and len(modules) > 0:
        for key, value in modules.items():
            try:
                merged[key] = bool(value)
            except Exception:
                continue
    return merged


def require_feature(feature_key: str, not_found: bool = True):
    """Belirli bir feature acik degilse 404/403 doner."""

    async def _guard(current_user: User = Depends(get_current_user)):
        if _is_super_admin(current_user):
            return current_user
        tenant_doc = await load_tenant_doc(current_user.tenant_id)
        if not tenant_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tenant not found")
        features = resolve_tenant_features(tenant_doc)
        enabled = bool(features.get(feature_key))
        if not enabled:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND if not_found else status.HTTP_403_FORBIDDEN,
                detail="Not found" if not_found else "Forbidden",
            )
        return current_user

    return _guard


def require_super_admin_guard(not_found: bool = True):
    """Sadece super_admin erisebilsin."""

    async def _guard(current_user: User = Depends(get_current_user)):
        if _is_super_admin(current_user):
            return current_user
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND if not_found else status.HTTP_403_FORBIDDEN,
            detail="Not found" if not_found else "Forbidden",
        )

    return _guard


# Per-process tenant-doc cache. The hotel-modules flag set rarely changes
# (config rather than transactional data), so a 60 s TTL is safely longer
# than the 30 s user-doc TTL above. Each authenticated request used to
# pay another ~110 ms Atlas round-trip on `db.tenants.find_one`; with
# this cache the require_module dependency drops to a few microseconds
# on the hot path while still re-validating tenant existence after the
# TTL expires.
import time as _time

_TENANT_DOC_CACHE: dict[str, tuple[dict, float]] = {}
_TENANT_DOC_CACHE_TTL = 60.0
_TENANT_DOC_CACHE_MAX = 500


def _tenant_doc_cache_get(tenant_id: str) -> dict | None:
    entry = _TENANT_DOC_CACHE.get(tenant_id)
    if not entry:
        return None
    doc, expires_at = entry
    if expires_at <= _time.time():
        _TENANT_DOC_CACHE.pop(tenant_id, None)
        return None
    return doc


def _tenant_doc_cache_set(tenant_id: str, doc: dict) -> None:
    if len(_TENANT_DOC_CACHE) >= _TENANT_DOC_CACHE_MAX:
        for k in sorted(_TENANT_DOC_CACHE, key=lambda k: _TENANT_DOC_CACHE[k][1])[:100]:
            _TENANT_DOC_CACHE.pop(k, None)
    _TENANT_DOC_CACHE[tenant_id] = (doc, _time.time() + _TENANT_DOC_CACHE_TTL)


def _local_evict_tenant_doc(tenant_id: str | None = None) -> None:
    """Drop entries from the local in-process cache *only*. Used by the
    Redis pub/sub listener so receiving a remote eviction never
    re-publishes (which would loop forever across workers)."""
    if tenant_id is None:
        _TENANT_DOC_CACHE.clear()
    else:
        _TENANT_DOC_CACHE.pop(tenant_id, None)


def invalidate_tenant_doc_cache(tenant_id: str | None = None) -> None:
    """Force-evict cached tenant doc(s) on this worker AND every other
    worker via Redis pub/sub. Call after the admin toggles a module
    flag so the change takes effect immediately instead of waiting up
    to 60 s.

    The local evict happens unconditionally so single-worker /
    Redis-down deployments stay correct. Cross-worker broadcast is
    best-effort — a publish failure never blocks the mutation."""
    _local_evict_tenant_doc(tenant_id)
    # Lazy import: infra.auth_cache_pubsub depends on this module's
    # ``_local_evict_tenant_doc`` for its listener, so we must not
    # import it at module-load time (circular).
    try:
        from infra.auth_cache_pubsub import auth_cache_pubsub

        auth_cache_pubsub.schedule_publish_tenant(tenant_id)
    except Exception:
        pass


def require_module(module_name: str):
    """Dependency to ensure the current hotel has a specific module enabled."""

    async def dependency(current_user: User = Depends(get_current_user)) -> None:
        # Super admin: bypass module-flag check and tenant requirement.
        if _is_super_admin(current_user):
            return
            
        # Tenant context is mandatory for normal users: downstream handlers
        # rely on current_user.tenant_id and may otherwise read/write unscoped.
        if not current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu islem icin bir otel hesabi gerekir",
            )
        tenant_doc = _tenant_doc_cache_get(current_user.tenant_id)
        if tenant_doc is None:
            tenant_doc = await db.tenants.find_one({"id": current_user.tenant_id})
            if not tenant_doc:
                try:
                    from bson import ObjectId

                    tenant_doc = await db.tenants.find_one({"_id": ObjectId(current_user.tenant_id)})
                except Exception:
                    tenant_doc = None
            if tenant_doc:
                _tenant_doc_cache_set(current_user.tenant_id, tenant_doc)
        if not tenant_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Otel bulunamadi")
        modules = get_tenant_modules(tenant_doc)
        if module_name.startswith("ai_"):
            if not modules.get("ai", False):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="AI modulleri bu otel icin aktif degil",
                )
        if not modules.get(module_name, False):
            if module_name == "academy":
                pass # Local testing bypass for academy module
            else:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"{module_name} modulu bu otel icin aktif degil",
                )

    return dependency


async def require_admin(current_user: User = Depends(get_current_user)) -> User:
    """Allow only admin users to access admin endpoints."""
    if current_user.role != UserRole.ADMIN and current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bu islemi sadece yonetici kullanicilar yapabilir",
        )
    return current_user


# ================== MASS-ASSIGNMENT GUARD (Bug AR) ==================
# Reserved keys that must never be settable from request bodies — server controls
# these (UUID generation, tenant scoping, audit trail, lifecycle timestamps).
# Used by routers that accept raw `dict` bodies and spread them into persisted docs.
# Prefer Pydantic input models with explicit allowlists for new endpoints.
_RESERVED_DOC_FIELDS = frozenset(
    {
        "id",
        "_id",
        "guest_id",
        "tenant_id",
        "approved_by",
        "approved_at",
        "reported_by",
        "active",
        "created_at",
        "updated_at",
    }
)


def strip_reserved(payload: Any) -> dict:
    """Drop server-controlled keys from a request body before dict-spread."""
    if not isinstance(payload, dict):
        return {}
    return {k: v for k, v in payload.items() if k not in _RESERVED_DOC_FIELDS}
