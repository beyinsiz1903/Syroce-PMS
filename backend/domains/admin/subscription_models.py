"""
Subscription & Pricing Models
Defines 3-tier subscription system: Basic, Professional, Enterprise
"""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel


class SubscriptionTier(str, Enum):
    """Subscription tier levels - 3 segments"""
    BASIC = "basic"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class FeatureFlag(str, Enum):
    """Feature flags for different subscription tiers"""
    # Core PMS (all plans)
    PMS = "pms"
    RESERVATION_CALENDAR = "reservation_calendar"
    DASHBOARD = "dashboard"
    GUESTS = "guests"
    HOUSEKEEPING = "housekeeping"
    BASIC_REPORTING = "basic_reporting"
    SETTINGS = "settings"
    PMS_MOBILE = "pms_mobile"
    INVOICES_BASIC = "invoices_basic"

    # Professional Features
    CHANNEL_MANAGER = "channel_manager"
    FOLIO_MANAGEMENT = "folio_management"
    NIGHT_AUDIT = "night_audit"
    INVOICES = "invoices"
    COST_MANAGEMENT = "cost_management"
    REPORTS = "reports"
    MOBILE_HOUSEKEEPING = "mobile_housekeeping"
    RATE_MANAGEMENT = "rate_management"
    BOOKING_ENGINE = "booking_engine"
    GUEST_ADVANCED = "guest_advanced"

    # Enterprise Features
    REVENUE_MANAGEMENT = "revenue_management"
    MULTI_PROPERTY = "multi_property"
    GROUP_SALES = "group_sales"
    SALES_CRM = "sales_crm"
    LOYALTY_PROGRAM = "loyalty_program"
    GM_DASHBOARDS = "gm_dashboards"
    MOBILE_REVENUE = "mobile_revenue"
    ADVANCED_ANALYTICS = "advanced_analytics"
    API_ACCESS = "api_access"
    WHITE_LABEL = "white_label"
    AUDIT_TRAIL = "audit_trail"

    # AI Features (Enterprise + add-on)
    AI = "ai"
    AI_CHATBOT = "ai_chatbot"
    AI_PRICING = "ai_pricing"
    AI_WHATSAPP = "ai_whatsapp"
    AI_PREDICTIVE = "ai_predictive"
    AI_REPUTATION = "ai_reputation"
    AI_REVENUE_AUTOPILOT = "ai_revenue_autopilot"
    AI_SOCIAL_RADAR = "ai_social_radar"


class SubscriptionPlan(BaseModel):
    """Subscription plan definition"""
    tier: SubscriptionTier
    name: str
    name_tr: str
    description: str
    description_tr: str
    price_monthly: float
    price_yearly: float
    max_rooms: Optional[int] = None
    max_users: Optional[int] = None
    features: List[FeatureFlag]
    support_level: str
    support_level_tr: str


# ──────────────────────────────────────────────────────────────
# PLAN → MODULE DEFAULTS (admin'in otel oluştururken set edeceği)
# ──────────────────────────────────────────────────────────────

PLAN_MODULE_DEFAULTS: Dict[str, Dict[str, bool]] = {
    "basic": {
        # CORE - Açık
        "pms": True,
        "reservation_calendar": True,
        "dashboard": True,
        "guests": True,
        "housekeeping": True,
        "basic_reporting": True,
        "settings": True,
        "pms_mobile": True,
        "invoices_basic": True,
        # PRO - Kapalı
        "channel_manager": False,
        "folio_management": False,
        "night_audit": False,
        "invoices": False,
        "cost_management": False,
        "reports": False,
        "mobile_housekeeping": False,
        "rate_management": False,
        "booking_engine": False,
        "guest_advanced": False,
        # ENTERPRISE - Kapalı
        "revenue_management": False,
        "multi_property": False,
        "group_sales": False,
        "sales_crm": False,
        "loyalty_program": False,
        "gm_dashboards": False,
        "mobile_revenue": False,
        "advanced_analytics": False,
        "api_access": False,
        "white_label": False,
        "audit_trail": False,
        # AI - Kapalı
        "ai": False,
        "ai_chatbot": False,
        "ai_pricing": False,
        "ai_whatsapp": False,
        "ai_predictive": False,
        "ai_reputation": False,
        "ai_revenue_autopilot": False,
        "ai_social_radar": False,
    },
    "professional": {
        # CORE - Açık
        "pms": True,
        "reservation_calendar": True,
        "dashboard": True,
        "guests": True,
        "housekeeping": True,
        "basic_reporting": True,
        "settings": True,
        "pms_mobile": True,
        "invoices_basic": True,
        # PRO - Açık
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
        # ENTERPRISE - Kapalı
        "revenue_management": False,
        "multi_property": False,
        "group_sales": False,
        "sales_crm": False,
        "loyalty_program": False,
        "gm_dashboards": False,
        "mobile_revenue": False,
        "advanced_analytics": False,
        "api_access": False,
        "white_label": False,
        "audit_trail": False,
        # AI - Kapalı (add-on olarak açılabilir)
        "ai": False,
        "ai_chatbot": False,
        "ai_pricing": False,
        "ai_whatsapp": False,
        "ai_predictive": False,
        "ai_reputation": False,
        "ai_revenue_autopilot": False,
        "ai_social_radar": False,
    },
    "enterprise": {
        # CORE - Açık
        "pms": True,
        "reservation_calendar": True,
        "dashboard": True,
        "guests": True,
        "housekeeping": True,
        "basic_reporting": True,
        "settings": True,
        "pms_mobile": True,
        "invoices_basic": True,
        # PRO - Açık
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
        # ENTERPRISE - Açık
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
        # AI - Açık
        "ai": True,
        "ai_chatbot": True,
        "ai_pricing": True,
        "ai_whatsapp": True,
        "ai_predictive": True,
        "ai_reputation": True,
        "ai_revenue_autopilot": True,
        "ai_social_radar": True,
    },
}


# Define subscription plans
SUBSCRIPTION_PLANS: Dict[SubscriptionTier, SubscriptionPlan] = {
    SubscriptionTier.BASIC: SubscriptionPlan(
        tier=SubscriptionTier.BASIC,
        name="Basic",
        name_tr="Basic",
        description="Essential PMS features for small hotels (1-15 rooms)",
        description_tr="Küçük oteller için temel PMS özellikleri (1-15 oda)",
        price_monthly=79.0,
        price_yearly=790.0,
        max_rooms=15,
        max_users=3,
        features=[
            FeatureFlag.PMS,
            FeatureFlag.RESERVATION_CALENDAR,
            FeatureFlag.DASHBOARD,
            FeatureFlag.GUESTS,
            FeatureFlag.HOUSEKEEPING,
            FeatureFlag.BASIC_REPORTING,
            FeatureFlag.SETTINGS,
            FeatureFlag.PMS_MOBILE,
            FeatureFlag.INVOICES_BASIC,
        ],
        support_level="email",
        support_level_tr="Email destek (iş saatleri)",
    ),

    SubscriptionTier.PROFESSIONAL: SubscriptionPlan(
        tier=SubscriptionTier.PROFESSIONAL,
        name="Professional",
        name_tr="Profesyonel",
        description="Advanced features for mid-size hotels (15-80 rooms)",
        description_tr="Orta ölçekli oteller için gelişmiş özellikler (15-80 oda)",
        price_monthly=299.0,
        price_yearly=2990.0,
        max_rooms=80,
        max_users=15,
        features=[
            # Core
            FeatureFlag.PMS,
            FeatureFlag.RESERVATION_CALENDAR,
            FeatureFlag.DASHBOARD,
            FeatureFlag.GUESTS,
            FeatureFlag.HOUSEKEEPING,
            FeatureFlag.BASIC_REPORTING,
            FeatureFlag.SETTINGS,
            FeatureFlag.PMS_MOBILE,
            FeatureFlag.INVOICES_BASIC,
            # Pro
            FeatureFlag.CHANNEL_MANAGER,
            FeatureFlag.FOLIO_MANAGEMENT,
            FeatureFlag.NIGHT_AUDIT,
            FeatureFlag.INVOICES,
            FeatureFlag.COST_MANAGEMENT,
            FeatureFlag.REPORTS,
            FeatureFlag.MOBILE_HOUSEKEEPING,
            FeatureFlag.RATE_MANAGEMENT,
            FeatureFlag.BOOKING_ENGINE,
            FeatureFlag.GUEST_ADVANCED,
        ],
        support_level="priority",
        support_level_tr="Öncelikli email + telefon desteği",
    ),

    SubscriptionTier.ENTERPRISE: SubscriptionPlan(
        tier=SubscriptionTier.ENTERPRISE,
        name="Enterprise",
        name_tr="Kurumsal",
        description="Full-featured solution for large hotels & chains (80+ rooms)",
        description_tr="Büyük oteller ve zincirler için tam özellikli çözüm (80+ oda)",
        price_monthly=799.0,
        price_yearly=7990.0,
        max_rooms=None,
        max_users=None,
        features=list(FeatureFlag),  # All features
        support_level="dedicated",
        support_level_tr="7/24 Dedicated Account Manager",
    ),
}


class SubscriptionStatus(str, Enum):
    """Subscription status"""
    TRIAL = "trial"
    ACTIVE = "active"
    PAST_DUE = "past_due"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


def has_feature_access(tier: SubscriptionTier, feature: FeatureFlag) -> bool:
    """Check if a subscription tier has access to a feature"""
    plan = SUBSCRIPTION_PLANS.get(tier)
    if not plan:
        return False
    return feature in plan.features


def get_plan_default_modules(tier: str) -> Dict[str, bool]:
    """Get default modules for a subscription tier"""
    tier_lower = tier.lower() if tier else "basic"
    return PLAN_MODULE_DEFAULTS.get(tier_lower, PLAN_MODULE_DEFAULTS["basic"]).copy()


def get_feature_comparison() -> Dict[str, Dict[str, bool]]:
    """Get feature comparison across all tiers"""
    comparison = {}
    for feature in FeatureFlag:
        comparison[feature.value] = {
            tier.value: has_feature_access(tier, feature)
            for tier in SubscriptionTier
        }
    return comparison


def get_all_module_keys() -> List[str]:
    """Get all module keys across all plans"""
    keys = set()
    for plan_modules in PLAN_MODULE_DEFAULTS.values():
        keys.update(plan_modules.keys())
    return sorted(keys)
