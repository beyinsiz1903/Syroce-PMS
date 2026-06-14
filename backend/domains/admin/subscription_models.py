"""
Subscription & Pricing Models
Defines 4-tier subscription system: Mini, Basic, Professional, Enterprise.

Mini, Elektraweb Mini muadili olarak küçük tesisler (1-15 oda) için
minimum çalışır PMS paketidir; Basic, küçük şehir oteli için Mini'nin
üstüne büyüyen paket; Professional ve Enterprise üst kademelerdir.
"""

from enum import Enum

from pydantic import BaseModel


class SubscriptionTier(str, Enum):
    """Subscription tier levels — 4 segments (Mini → Enterprise)."""
    MINI = "mini"
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

    # Operations Add-ons
    ROOM_QR_REQUESTS = "room_qr_requests"  # Oda QR talep sistemi (misafir → departman)
    QUICK_ID = "quick_id"  # Kimlik OCR taraması (Quick-ID microservice)
    MARKETPLACE = "marketplace"  # Modül marketplace / eklenti mağazası
    AF_SADAKAT = "af_sadakat"  # Sadakat & misafir inbox entegrasyonu (Afsadakat)

    # Mini-tier ek modülleri (Elektraweb Mini muadili — pansiyon/butik baseline)
    FOLIO_BASIC = "folio_basic"                  # basit folyo (split/route yok)
    NIGHT_AUDIT_BASIC = "night_audit_basic"      # tek-tıkla gün sonu
    CHANNEL_MANAGER_LITE = "channel_manager_lite"  # 3 kanal limiti
    PAYMENTS_LINK = "payments_link"              # sanal POS + ödeme linki
    KBS_NOTIFY = "kbs_notify"                    # KBS polis kimlik bildirimi
    # Basic-tier ek modülleri
    MAILING = "mailing"
    HOUSEKEEPING_ADVANCED = "housekeeping_advanced"
    # Professional-tier ek modülleri
    POS_BASIC = "pos_basic"
    MAINTENANCE = "maintenance"


class SubscriptionPlan(BaseModel):
    """Subscription plan definition"""
    tier: SubscriptionTier
    name: str
    name_tr: str
    description: str
    description_tr: str
    price_monthly: float
    price_yearly: float
    max_rooms: int | None = None
    max_users: int | None = None
    features: list[FeatureFlag]
    support_level: str
    support_level_tr: str


# ──────────────────────────────────────────────────────────────
# PLAN → MODULE DEFAULTS (admin'in otel oluştururken set edeceği)
# ──────────────────────────────────────────────────────────────

PLAN_MODULE_DEFAULTS: dict[str, dict[str, bool]] = {
    # ──────────────────────────────────────────────────────────────
    # MINI — Elektraweb Mini muadili; pansiyon / butik (1-15 oda)
    # Çekirdek PMS + basit folyo/fatura/gün sonu + Lite channel manager
    # (3 kanal) + sanal POS / ödeme linki + KBS polis bildirimi.
    # ──────────────────────────────────────────────────────────────
    "mini": {
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
        # MINI ek modüller - Açık
        "folio_basic": True,
        "night_audit_basic": True,
        "channel_manager_lite": True,
        "payments_link": True,
        "kbs_notify": True,
        # PRO - Kapalı (Lite versiyonları açık)
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
        "mailing": False,
        "housekeeping_advanced": False,
        "pos_basic": False,
        "maintenance": False,
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
        # OPERATIONS ADD-ONS
        "room_qr_requests": True,
        "quick_id": True,           # Mini'de açık (Quick-ID = KBS akışı için kritik)
        "marketplace": False,
        "af_sadakat": False,
        # ADD-ON MODULES
        "spa": False,
        "mice": False,
    },
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
        # MINI ek modülleri - Açık (Basic, Mini'yi kapsar)
        "folio_basic": True,
        "night_audit_basic": True,
        "channel_manager_lite": True,
        "payments_link": True,
        "kbs_notify": True,
        # BASIC ek modülleri - Açık
        "mailing": True,
        "guest_advanced": True,
        "housekeeping_advanced": True,
        "cost_management": True,
        "reports": True,
        "channel_manager": True,
        # PRO - Kapalı
        "folio_management": False,
        "night_audit": False,
        "invoices": False,
        "mobile_housekeeping": False,
        "rate_management": False,
        "booking_engine": False,
        "pos_basic": False,
        "maintenance": False,
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
        # OPERATIONS ADD-ONS
        "room_qr_requests": True,
        "quick_id": True,           # Basic'te de açık (KBS akışına bağlı)
        "marketplace": False,
        "af_sadakat": False,
        # ADD-ON MODULES (sold separately, super-admin enables per-tenant)
        "spa": False,
        "mice": False,
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
        # MINI ek modülleri - Açık
        "folio_basic": True,
        "night_audit_basic": True,
        "channel_manager_lite": True,
        "payments_link": True,
        "kbs_notify": True,
        # BASIC ek modülleri - Açık
        "mailing": True,
        "housekeeping_advanced": True,
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
        "pos_basic": True,
        "maintenance": True,
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
        # OPERATIONS ADD-ONS
        "room_qr_requests": True,
        "quick_id": True,
        "marketplace": False,
        "af_sadakat": False,
        # ADD-ON MODULES (sold separately, super-admin enables per-tenant)
        "spa": False,
        "mice": False,
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
        # MINI ek modülleri - Açık
        "folio_basic": True,
        "night_audit_basic": True,
        "channel_manager_lite": True,
        "payments_link": True,
        "kbs_notify": True,
        # BASIC ek modülleri - Açık
        "mailing": True,
        "housekeeping_advanced": True,
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
        "pos_basic": True,
        "maintenance": True,
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
        # OPERATIONS ADD-ONS
        "room_qr_requests": True,
        "quick_id": True,
        "marketplace": True,
        "af_sadakat": True,
        # ADD-ON MODULES (sold separately, super-admin enables per-tenant)
        "spa": False,
        "mice": False,
    },
}


# Define subscription plans
SUBSCRIPTION_PLANS: dict[SubscriptionTier, SubscriptionPlan] = {
    SubscriptionTier.MINI: SubscriptionPlan(
        tier=SubscriptionTier.MINI,
        name="Mini",
        name_tr="Mini",
        description="Minimum viable PMS for pensions / boutique stays (1-15 rooms) — Elektraweb Mini equivalent",
        description_tr="Pansiyon / butik tesisler için minimum çalışır PMS (1-15 oda) — Elektraweb Mini muadili",
        price_monthly=35.0,
        price_yearly=350.0,
        max_rooms=15,
        max_users=2,
        features=[
            # Core PMS
            FeatureFlag.PMS,
            FeatureFlag.RESERVATION_CALENDAR,
            FeatureFlag.DASHBOARD,
            FeatureFlag.GUESTS,
            FeatureFlag.HOUSEKEEPING,
            FeatureFlag.BASIC_REPORTING,
            FeatureFlag.SETTINGS,
            FeatureFlag.PMS_MOBILE,
            FeatureFlag.INVOICES_BASIC,
            # Mini-specific essentials
            FeatureFlag.FOLIO_BASIC,
            FeatureFlag.NIGHT_AUDIT_BASIC,
            FeatureFlag.CHANNEL_MANAGER_LITE,
            FeatureFlag.PAYMENTS_LINK,
            FeatureFlag.KBS_NOTIFY,
            FeatureFlag.QUICK_ID,
            FeatureFlag.ROOM_QR_REQUESTS,
        ],
        support_level="email",
        support_level_tr="E-posta destek (iş saatleri)",
    ),

    SubscriptionTier.BASIC: SubscriptionPlan(
        tier=SubscriptionTier.BASIC,
        name="Basic",
        name_tr="Basic",
        description="Essential PMS features for small city hotels (16-30 rooms)",
        description_tr="Küçük şehir otelleri için temel PMS özellikleri (16-30 oda)",
        price_monthly=79.0,
        price_yearly=790.0,
        max_rooms=30,
        max_users=4,
        features=[
            # Inherits all Mini features
            FeatureFlag.PMS,
            FeatureFlag.RESERVATION_CALENDAR,
            FeatureFlag.DASHBOARD,
            FeatureFlag.GUESTS,
            FeatureFlag.HOUSEKEEPING,
            FeatureFlag.BASIC_REPORTING,
            FeatureFlag.SETTINGS,
            FeatureFlag.PMS_MOBILE,
            FeatureFlag.INVOICES_BASIC,
            FeatureFlag.FOLIO_BASIC,
            FeatureFlag.NIGHT_AUDIT_BASIC,
            FeatureFlag.CHANNEL_MANAGER_LITE,
            FeatureFlag.PAYMENTS_LINK,
            FeatureFlag.KBS_NOTIFY,
            FeatureFlag.QUICK_ID,
            FeatureFlag.ROOM_QR_REQUESTS,
            # Basic-only additions
            FeatureFlag.CHANNEL_MANAGER,
            FeatureFlag.MAILING,
            FeatureFlag.GUEST_ADVANCED,
            FeatureFlag.HOUSEKEEPING_ADVANCED,
            FeatureFlag.COST_MANAGEMENT,
            FeatureFlag.REPORTS,
        ],
        support_level="email",
        support_level_tr="Email destek (iş saatleri)",
    ),

    SubscriptionTier.PROFESSIONAL: SubscriptionPlan(
        tier=SubscriptionTier.PROFESSIONAL,
        name="Professional",
        name_tr="Profesyonel",
        description="Advanced features for mid-size hotels (31-80 rooms)",
        description_tr="Orta ölçekli oteller için gelişmiş özellikler (31-80 oda)",
        price_monthly=299.0,
        price_yearly=2990.0,
        max_rooms=80,
        max_users=15,
        features=[
            # Core (inherits Mini + Basic)
            FeatureFlag.PMS,
            FeatureFlag.RESERVATION_CALENDAR,
            FeatureFlag.DASHBOARD,
            FeatureFlag.GUESTS,
            FeatureFlag.HOUSEKEEPING,
            FeatureFlag.BASIC_REPORTING,
            FeatureFlag.SETTINGS,
            FeatureFlag.PMS_MOBILE,
            FeatureFlag.INVOICES_BASIC,
            FeatureFlag.FOLIO_BASIC,
            FeatureFlag.NIGHT_AUDIT_BASIC,
            FeatureFlag.CHANNEL_MANAGER_LITE,
            FeatureFlag.PAYMENTS_LINK,
            FeatureFlag.KBS_NOTIFY,
            FeatureFlag.QUICK_ID,
            FeatureFlag.ROOM_QR_REQUESTS,
            FeatureFlag.MAILING,
            FeatureFlag.HOUSEKEEPING_ADVANCED,
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
            FeatureFlag.POS_BASIC,
            FeatureFlag.MAINTENANCE,
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


def get_plan_default_modules(tier: str) -> dict[str, bool]:
    """Get default modules for a subscription tier"""
    tier_lower = tier.lower() if tier else "basic"
    return PLAN_MODULE_DEFAULTS.get(tier_lower, PLAN_MODULE_DEFAULTS["basic"]).copy()


def get_feature_comparison() -> dict[str, dict[str, bool]]:
    """Get feature comparison across all tiers"""
    comparison = {}
    for feature in FeatureFlag:
        comparison[feature.value] = {
            tier.value: has_feature_access(tier, feature)
            for tier in SubscriptionTier
        }
    return comparison


def get_all_module_keys() -> list[str]:
    """Get all module keys across all plans"""
    keys = set()
    for plan_modules in PLAN_MODULE_DEFAULTS.values():
        keys.update(plan_modules.keys())
    return sorted(keys)
