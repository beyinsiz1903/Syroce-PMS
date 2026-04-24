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
    "core_small_hotel": {
        "core_dashboard": True, "core_pms": True, "core_rooms": True,
        "core_rates_availability": True, "core_bookings_frontdesk": True,
        "core_calendar": True, "core_guests_basic": True,
        "core_housekeeping_basic": True, "core_basic_reporting": True,
        "core_mobile_view": True,
    },
    "professional_city_hotel": {
        "core_dashboard": True, "core_pms": True, "core_rooms": True,
        "core_rates_availability": True, "core_bookings_frontdesk": True,
        "core_calendar": True, "core_guests_basic": True,
        "core_housekeeping_basic": True, "core_basic_reporting": True,
        "core_mobile_view": True,
        "pro_channel_manager": True, "pro_rate_manager": True,
        "pro_revenue_management": True, "pro_folio_billing": True,
        "pro_night_audit": True, "pro_invoicing": True,
        "pro_advanced_housekeeping": True, "pro_guest_advanced": True,
        "pro_group_reservations": True, "pro_allotments": True,
        "pro_pos_basic": True, "pro_maintenance": True,
    },
    "enterprise_resort": {
        "core_dashboard": True, "core_pms": True, "core_rooms": True,
        "core_rates_availability": True, "core_bookings_frontdesk": True,
        "core_calendar": True, "core_guests_basic": True,
        "core_housekeeping_basic": True, "core_basic_reporting": True,
        "core_mobile_view": True,
        "pro_channel_manager": True, "pro_rate_manager": True,
        "pro_revenue_management": True, "pro_folio_billing": True,
        "pro_night_audit": True, "pro_invoicing": True,
        "pro_advanced_housekeeping": True, "pro_guest_advanced": True,
        "pro_group_reservations": True, "pro_allotments": True,
        "pro_pos_basic": True, "pro_maintenance": True,
        "ent_multi_property": True, "ent_sales_crm": True,
        "ent_loyalty_program": True, "ent_spa_wellness": True,
        "ent_meetings_events": True, "ent_advanced_analytics": True,
        "ent_gm_dashboards": True, "ent_api_access": True,
        "ent_white_label": True, "ent_audit_trail": True,
    },
    "deluxe_plus": {
        "core_dashboard": True, "core_pms": True, "core_rooms": True,
        "core_rates_availability": True, "core_bookings_frontdesk": True,
        "core_calendar": True, "core_guests_basic": True,
        "core_housekeeping_basic": True, "core_basic_reporting": True,
        "core_mobile_view": True,
        "pro_channel_manager": True, "pro_rate_manager": True,
        "pro_revenue_management": True, "pro_folio_billing": True,
        "pro_night_audit": True, "pro_invoicing": True,
        "pro_advanced_housekeeping": True, "pro_guest_advanced": True,
        "pro_group_reservations": True, "pro_allotments": True,
        "pro_pos_basic": True, "pro_maintenance": True,
        "ent_multi_property": True, "ent_sales_crm": True,
        "ent_loyalty_program": True, "ent_spa_wellness": True,
        "ent_meetings_events": True, "ent_advanced_analytics": True,
        "ent_gm_dashboards": True, "ent_api_access": True,
        "ent_white_label": True, "ent_audit_trail": True,
        "dlx_ai_pricing": True, "dlx_ai_chatbot": True,
        "dlx_ai_predictive": True, "dlx_whatsapp_concierge": True,
        "dlx_social_radar": True, "dlx_revenue_autopilot": True,
        "dlx_guest_dna": True, "dlx_dynamic_staffing": True,
    },
    "pms_lite": {
        "core_dashboard": True, "core_pms": True, "core_rooms": True,
        "core_calendar": True, "core_guests_basic": True,
        "core_housekeeping_basic": True,
    },
}


def resolve_tenant_features(tenant_doc: dict[str, Any]) -> dict[str, bool]:
    """Plan + overrides ile efektif feature set uretir."""
    tenant_doc = tenant_doc or {}
    plan = (
        tenant_doc.get("subscription_plan")
        or tenant_doc.get("plan")
        or tenant_doc.get("subscription_tier")
        or "core_small_hotel"
    )
    all_keys: set = set()
    for _plan, feats in FEATURES_BY_PLAN.items():
        for k in (feats or {}).keys():
            all_keys.add(k)
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
    "pms": True, "reservation_calendar": True, "dashboard": True,
    "guests": True, "housekeeping": True, "basic_reporting": True,
    "settings": True, "pms_mobile": True, "invoices_basic": True,
    "channel_manager": True, "folio_management": True, "night_audit": True,
    "invoices": True, "cost_management": True, "reports": True,
    "mobile_housekeeping": True, "rate_management": True, "booking_engine": True,
    "guest_advanced": True, "revenue_management": True, "multi_property": True,
    "group_sales": True, "sales_crm": True, "loyalty_program": True,
    "gm_dashboards": True, "mobile_revenue": True, "advanced_analytics": True,
    "api_access": True, "white_label": True, "audit_trail": True,
    "ai": True, "ai_chatbot": True, "ai_pricing": True, "ai_whatsapp": True,
    "ai_predictive": True, "ai_reputation": True, "ai_revenue_autopilot": True,
    "ai_social_radar": True,
    # Add-on modules — sold separately, default OFF.
    "spa": False, "mice": False,
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


def require_module(module_name: str):
    """Dependency to ensure the current hotel has a specific module enabled."""
    async def dependency(current_user: User = Depends(get_current_user)) -> None:
        if not current_user.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bu islem icin bir otel hesabi gerekir",
            )
        tenant_doc = await db.tenants.find_one({"id": current_user.tenant_id})
        if not tenant_doc:
            try:
                from bson import ObjectId
                tenant_doc = await db.tenants.find_one({"_id": ObjectId(current_user.tenant_id)})
            except Exception:
                tenant_doc = None
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
_RESERVED_DOC_FIELDS = frozenset({
    "id", "_id", "guest_id", "tenant_id", "approved_by", "approved_at",
    "reported_by", "active", "created_at", "updated_at",
})


def strip_reserved(payload: Any) -> dict:
    """Drop server-controlled keys from a request body before dict-spread."""
    if not isinstance(payload, dict):
        return {}
    return {k: v for k, v in payload.items() if k not in _RESERVED_DOC_FIELDS}
