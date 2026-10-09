"""Marketplace router: ürün kataloğu, satın alma, abonelikler.

Tüm modülleri / entegrasyonları / kredi paketlerini tek noktadan satar.
iyzico Checkout Form üzerinden ödeme alır, başarılı ödeme sonrası
`tenant_subscriptions` koleksiyonuna abonelik kaydı düşer.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from core.security import get_current_user
from core.subscriptions import ensure_indexes, get_active_subscriptions
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v93 DW

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/module-store", tags=["module-store"])


# ── Default catalog (seed) ──────────────────────────────────────
DEFAULT_PRODUCTS: list[dict[str, Any]] = [
    {
        "key": "quick_id_integration",
        "name": "Quick-ID Kimlik Okuma",
        "description": "Pasaport / TC kimlik OCR entegrasyonu, KBS hazır.",
        "category": "integration",
        "billing_type": "subscription",
        "price_try": 299.0,
        "duration_days": 30,
        "icon": "ScanLine",
        "features": [
            "Otomatik OCR ile kimlik tarama",
            "KBS uyumlu çıktı",
            "Misafir profiline otomatik aktarım",
        ],
        "active": True,
    },
    {
        "key": "mailing_starter",
        "name": "Mailing Başlangıç (5.000 mail)",
        "description": "5.000 e-posta gönderim kredisi. Süresiz kullanım.",
        "category": "credit_pack",
        "billing_type": "one_time",
        "price_try": 149.0,
        "duration_days": None,
        "icon": "Mail",
        "credits": 5000,
        "features": ["5.000 e-posta kredisi", "Süresiz geçerli"],
        "active": True,
    },
    {
        "key": "mailing_pro",
        "name": "Mailing Pro (25.000 mail)",
        "description": "25.000 e-posta gönderim kredisi. Süresiz kullanım.",
        "category": "credit_pack",
        "billing_type": "one_time",
        "price_try": 599.0,
        "duration_days": None,
        "icon": "Mail",
        "credits": 25000,
        "features": ["25.000 e-posta kredisi", "Süresiz geçerli", "%20 indirim"],
        "active": True,
    },
    {
        "key": "af_sadakat",
        "name": "Sadakat & Omni Inbox (Af-sadakat)",
        "description": (
            "Misafir sadakat programı (Silver/Gold/Platinum), AI destekli yorum "
            "yönetimi, WhatsApp/Meta/web sohbet birleşik kutusu, oda servisi & "
            "spa & uyandırma & misafir QR paneli. PMS ile otomatik entegre."
        ),
        "category": "module",
        "billing_type": "subscription",
        "price_try": 1499.0,
        "duration_days": 30,
        "trial_days": 14,
        "icon": "Sparkles",
        "external": True,
        "sso_path": "/integrations/afsadakat/launch",
        "features": [
            "Sadakat programı: tier, puan, otomatik kazanım",
            "Yorumlar: AI duygu analizi + AI yanıt önerileri",
            "Birleşik mesaj kutusu: WhatsApp, Meta, web sohbet",
            "Misafir servisleri: oda servisi, spa, çamaşır, uyandırma",
            "QR ile misafir paneli (giriş gerektirmez)",
            "14 gün ücretsiz deneme",
        ],
        "active": True,
    },
]

# Public add-on prices are intentionally transparent. Large global PMS vendors
# generally require a sales quote for these capabilities; Syroce publishes a
# predictable monthly TRY price and keeps usage-based third-party costs explicit.
# Only modules that already have a product route and entitlement key are listed.
DEFAULT_PRODUCTS += [
    {
        "key": "hr",
        "name": "İnsan Kaynakları & Vardiya",
        "name_en": "Human Resources & Scheduling",
        "description": "Personel, vardiya, izin, özlük, performans ve bordro hazırlığını PMS verisiyle birlikte yönetin.",
        "description_en": "Manage staff, schedules, leave, employee records, performance and payroll preparation with PMS data.",
        "category": "module", "billing_type": "subscription", "price_try": 1490.0,
        "duration_days": 30, "trial_days": 14, "icon": "Users", "route_path": "/hr?tab=suite",
        "badge": "Operasyon", "badge_en": "Operations", "popular": True, "active": True,
        "features": ["Vardiya ve izin yönetimi", "Personel özlük dosyası", "Performans ve bordro hazırlığı", "Rol bazlı erişim"],
        "features_en": ["Scheduling and leave", "Employee records", "Performance and payroll preparation", "Role-based access"],
    },
    {
        "key": "pos_fnb",
        "name": "Restoran POS & F&B",
        "name_en": "Restaurant POS & F&B",
        "description": "Restoran, bar ve oda servisi satışlarını adisyondan misafir folyosuna kadar tek akışta yönetin.",
        "description_en": "Run restaurant, bar and room-service sales from order to guest folio in one workflow.",
        "category": "module", "billing_type": "subscription", "price_try": 1990.0,
        "duration_days": 30, "trial_days": 14, "icon": "Utensils", "route_path": "/fnb-complete",
        "badge": "En çok tercih edilen", "badge_en": "Most popular", "popular": True, "active": True,
        "features": ["Masa planı ve adisyon", "Mutfak ekranı", "Odaya/folyoya aktarım", "Ürün ve satış raporları"],
        "features_en": ["Table plan and orders", "Kitchen display", "Room and folio posting", "Product and sales reports"],
    },
    {
        "key": "invoices",
        "name": "Genel Muhasebe & Finans",
        "name_en": "General Accounting & Finance",
        "description": "Ön muhasebe, cari hesap, kasa-banka, gelir-gider, fatura ve büyük defteri otel operasyonuyla birleştirin.",
        "description_en": "Connect ledgers, accounts, cash and bank, income and expenses, invoices and general ledger to hotel operations.",
        "category": "module", "billing_type": "subscription", "price_try": 2490.0,
        "duration_days": 30, "trial_days": 14, "icon": "Landmark", "route_path": "/app/general-ledger",
        "badge": "Finans", "badge_en": "Finance", "popular": True, "active": True,
        "features": ["Cari hesap ve yaşlandırma", "Kasa ve banka hareketleri", "Gelir-gider ve fatura", "Genel muhasebe raporları"],
        "features_en": ["Accounts and aging", "Cash and bank activity", "Income, expenses and invoices", "General-ledger reports"],
    },
    {
        "key": "revenue_management", "name": "Gelir Yönetimi (RMS)", "name_en": "Revenue Management (RMS)",
        "description": "Doluluk, talep ve kanal performansından fiyat önerileri ve gelir fırsatları üretin.",
        "description_en": "Turn occupancy, demand and channel performance into rate recommendations and revenue opportunities.",
        "category": "module", "billing_type": "subscription", "price_try": 2990.0, "duration_days": 30,
        "trial_days": 14, "icon": "ChartNoAxesCombined", "route_path": "/app/revenue-hub", "badge": "Gelir", "badge_en": "Revenue", "active": True,
        "features": ["ADR, RevPAR ve pickup", "Doluluk tahmini", "Fiyat önerileri", "Kanal performansı"],
        "features_en": ["ADR, RevPAR and pickup", "Occupancy forecast", "Rate recommendations", "Channel performance"],
    },
    {
        "key": "spa", "name": "Spa & Wellness", "name_en": "Spa & Wellness",
        "description": "Terapist, hizmet kataloğu, oda ve randevu planlamasını folyo entegrasyonuyla yönetin.",
        "description_en": "Manage therapists, services, rooms and appointments with folio integration.",
        "category": "module", "billing_type": "subscription", "price_try": 1490.0, "duration_days": 30,
        "trial_days": 14, "icon": "HeartPulse", "route_path": "/spa-wellness", "active": True,
        "features": ["Randevu takvimi", "Terapist ve oda planı", "Hizmet kataloğu", "Folyoya aktarım"],
        "features_en": ["Appointment calendar", "Therapist and room planning", "Service catalog", "Folio posting"],
    },
    {
        "key": "mice", "name": "MICE & Etkinlik", "name_en": "MICE & Events",
        "description": "Toplantı, düğün, banket, teklif, etkinlik alanı ve catering operasyonlarını yönetin.",
        "description_en": "Manage meetings, weddings, banquets, proposals, function spaces and catering operations.",
        "category": "module", "billing_type": "subscription", "price_try": 1990.0, "duration_days": 30,
        "trial_days": 14, "icon": "CalendarRange", "route_path": "/app/mice", "active": True,
        "features": ["Satış pipeline", "Etkinlik ve salon takvimi", "Teklif yönetimi", "Catering ve BEO"],
        "features_en": ["Sales pipeline", "Event and venue calendar", "Proposal management", "Catering and BEO"],
    },
    {
        "key": "maintenance", "name": "Teknik Servis & Bakım", "name_en": "Maintenance & Engineering",
        "description": "Arıza kayıtlarını, iş emirlerini, varlıkları ve planlı bakımı operasyon ekipleriyle yönetin.",
        "description_en": "Manage incidents, work orders, assets and preventive maintenance with operations teams.",
        "category": "module", "billing_type": "subscription", "price_try": 790.0, "duration_days": 30,
        "trial_days": 14, "icon": "Wrench", "route_path": "/maintenance/work-orders", "active": True,
        "features": ["İş emri ve SLA", "Varlık envanteri", "Planlı bakım", "Mobil görev takibi"],
        "features_en": ["Work orders and SLA", "Asset inventory", "Preventive maintenance", "Mobile task tracking"],
    },
    {
        "key": "sales_crm", "name": "Otel Satış CRM", "name_en": "Hotel Sales CRM",
        "description": "Kurumsal müşteri, fırsat, aktivite ve satış pipeline yönetimini tek çalışma alanında toplayın.",
        "description_en": "Manage corporate accounts, opportunities, activities and sales pipeline in one workspace.",
        "category": "module", "billing_type": "subscription", "price_try": 1490.0, "duration_days": 30,
        "trial_days": 14, "icon": "Handshake", "route_path": "/crm", "active": True,
        "features": ["Müşteri ve fırsat yönetimi", "Aktivite takibi", "Satış pipeline", "Kurumsal hesaplar"],
        "features_en": ["Account and opportunity management", "Activity tracking", "Sales pipeline", "Corporate accounts"],
    },
    {
        "key": "contact_center", "name": "İletişim Merkezi", "name_en": "Communication Center",
        "description": "WhatsApp, çağrı, web ve sosyal kanalları birleşik gelen kutusunda yönetin.",
        "description_en": "Manage WhatsApp, calls, web and social channels from a unified inbox.",
        "category": "integration", "billing_type": "subscription", "price_try": 2990.0, "duration_days": 30,
        "trial_days": 14, "icon": "Headset", "route_path": "/app/call-center", "price_note": "Mesaj ve çağrı kullanımı hariçtir.", "price_note_en": "Message and call usage is excluded.", "active": True,
        "features": ["Birleşik gelen kutusu", "Çağrı ve mesaj geçmişi", "Ekip atama", "Misafir profili bağlantısı"],
        "features_en": ["Unified inbox", "Call and message history", "Team assignment", "Guest-profile linking"],
    },
    {
        "key": "academy", "name": "Syroce Academy", "name_en": "Syroce Academy",
        "description": "Departmana özel eğitim, sınav, ilerleme ve sertifika süreçlerini yönetin.",
        "description_en": "Manage department training, exams, progress and certification.",
        "category": "module", "billing_type": "subscription", "price_try": 590.0, "duration_days": 30,
        "trial_days": 14, "icon": "GraduationCap", "route_path": "/app/academy", "active": True,
        "features": ["Rol bazlı eğitim yolları", "Sınav ve başarı takibi", "PDF sertifika", "Yönetici raporu"],
        "features_en": ["Role-based learning paths", "Exam and progress tracking", "PDF certificates", "Manager reports"],
    },
    {
        "key": "booking_engine", "name": "Web Rezervasyon Motoru", "name_en": "Web Booking Engine",
        "description": "Otel web sitesinden komisyonsuz, mobil uyumlu ve anlık müsaitlikli doğrudan rezervasyon alın.",
        "description_en": "Accept commission-free, mobile-ready direct bookings with live availability on your website.",
        "category": "integration", "billing_type": "subscription", "price_try": 1290.0, "duration_days": 30,
        "trial_days": 14, "icon": "Globe2", "route_path": "/app/wbe-settings", "active": True,
        "features": ["Komisyonsuz rezervasyon", "Anlık fiyat ve müsaitlik", "Mobil uyumlu deneyim", "PMS'e otomatik kayıt"],
        "features_en": ["Commission-free bookings", "Live rates and availability", "Mobile-ready experience", "Automatic PMS posting"],
    },
    {
        "key": "multi_property", "name": "Çoklu Tesis Yönetimi", "name_en": "Multi-property Management",
        "description": "Zincir oteller için tesisler arası performans, misafir ve yönetim görünümü sağlayın.",
        "description_en": "Give hotel groups a cross-property view of performance, guests and operations.",
        "category": "module", "billing_type": "subscription", "price_try": 3490.0, "duration_days": 30,
        "icon": "Building2", "route_path": "/app/multi-property", "price_note": "Tesis başına fiyatlandırılır.", "price_note_en": "Priced per property.", "active": True,
        "features": ["Zincir performans paneli", "Tesisler arası misafir görünümü", "Merkezi raporlama", "Rol bazlı yönetim"],
        "features_en": ["Group performance dashboard", "Cross-property guest view", "Central reporting", "Role-based management"],
    },
]

# Keep the public catalog, checkout and renewal worker on one commercial
# contract.  Existing admin edits remain authoritative because seeding uses
# $setOnInsert.
from core.marketplace_contracts import calculate_price, enrich_product, provision_subscription

DEFAULT_PRODUCTS = [enrich_product(product) for product in DEFAULT_PRODUCTS]


def _db():
    """Return raw, non-tenant-scoped DB.

    Marketplace_products is a PLATFORM-WIDE catalog (no tenant_id field).
    marketplace_orders / tenant_subscriptions store tenant_id explicitly
    and we always filter on it manually, so the tenant-scoping wrapper
    would cause duplicate-key insert errors and miss-filtering. Use raw.
    """
    from core.database import _raw_db

    return _raw_db


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _seed_products_if_empty() -> None:
    """Idempotent catalog upsert.

    Inserts any DEFAULT_PRODUCTS entry that doesn't yet exist by key.
    Existing entries are left untouched (so admin edits via
    /admin/products are preserved). New products added to
    DEFAULT_PRODUCTS in code automatically appear after restart.
    """
    db = _db()
    await ensure_indexes()
    inserted = 0
    for p in DEFAULT_PRODUCTS:
        result = await db.marketplace_products.update_one(
            {"key": p["key"]},
            {"$setOnInsert": {**p, "created_at": _now_iso()}},
            upsert=True,
        )
        if result.upserted_id is not None:
            inserted += 1
        # Backfill newly introduced contract fields without overwriting any
        # price or policy that a platform administrator already set.
        existing = await db.marketplace_products.find_one({"key": p["key"]}, {"_id": 0}) or {}
        missing = {key: value for key, value in p.items() if key not in existing and key in {
            "pricing_model", "included_units", "unit_price_try", "tax_rate_pct", "setup_minutes",
            "provisioning_strategy", "readiness_checks", "price_version", "price_valid_from",
            "price_source", "price_source_url", "auto_renew",
        }}
        if missing:
            await db.marketplace_products.update_one({"key": p["key"]}, {"$set": missing})
    if inserted:
        logger.info("[marketplace] inserted %d new default products", inserted)

    # Deactivate legacy QR product — that module is included free in all plans.
    await db.marketplace_products.update_one(
        {"key": "qr_room_management"},
        {"$set": {"active": False, "updated_at": _now_iso(), "deactivated_reason": "Tüm planlarda ücretsiz olarak dahildir"}},
    )


# ── Schemas ─────────────────────────────────────────────────────
class ProductIn(BaseModel):
    key: str
    name: str
    description: str = ""
    category: str = Field(default="module")  # module|integration|credit_pack
    billing_type: str = Field(default="subscription")  # subscription|one_time
    price_try: float = 0
    duration_days: int | None = 30
    trial_days: int | None = None
    icon: str | None = None
    credits: int | None = None
    features: list[str] = Field(default_factory=list)
    features_en: list[str] = Field(default_factory=list)
    external: bool = False
    sso_path: str | None = None
    active: bool = True
    name_en: str | None = None
    description_en: str | None = None
    route_path: str | None = None
    badge: str | None = None
    badge_en: str | None = None
    popular: bool = False
    price_note: str | None = None
    price_note_en: str | None = None
    pricing_model: str = "property"
    included_units: int = Field(default=1, ge=1)
    unit_price_try: float | None = Field(default=None, ge=0)
    tax_rate_pct: float = Field(default=20, ge=0, le=100)
    setup_minutes: int = Field(default=30, ge=0)
    provisioning_strategy: str = "native"
    readiness_checks: list[str] = Field(default_factory=list)
    price_source: str = "Syroce commercial review"
    price_source_url: str | None = None
    price_valid_from: str | None = None
    price_valid_until: str | None = None
    price_version: int = Field(default=1, ge=1)
    auto_renew: bool = True


class PurchaseRequest(BaseModel):
    product_key: str
    quantity: int = Field(default=1, ge=1, le=10000)


class StartTrialRequest(BaseModel):
    product_key: str


class QuoteRequest(BaseModel):
    product_key: str
    note: str | None = Field(default=None, max_length=1000)


class SubscriptionAction(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


class ReadinessStepUpdate(BaseModel):
    step_key: str
    completed: bool = True


class RefundRequest(BaseModel):
    order_id: str
    reason: str = Field(min_length=3, max_length=500)


# ── Public catalog ──────────────────────────────────────────────
@router.get("/products")
async def list_products() -> dict:
    from core.iyzico import is_configured

    await _seed_products_if_empty()
    db = _db()
    cur = db.marketplace_products.find({"active": True}, {"_id": 0}).sort("name", 1)
    items = [doc async for doc in cur]
    return {
        "products": items,
        "payment_ready": is_configured(),
        "currency": "TRY",
    }


@router.get("/products/{product_key}/quote")
async def product_quote(product_key: str, quantity: int = 1) -> dict:
    await _seed_products_if_empty()
    product = await _db().marketplace_products.find_one({"key": product_key, "active": True}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    return {"product_key": product_key, "pricing_model": product.get("pricing_model", "property"), "included_units": product.get("included_units", 1), **calculate_price(product, quantity)}


# ── Tenant: my subscriptions ────────────────────────────────────
@router.get("/my-subscriptions")
async def my_subscriptions(
    current_user: User = Depends(get_current_user),
) -> dict:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    subs = await get_active_subscriptions(current_user.tenant_id)
    return {"subscriptions": subs}


@router.post("/request-quote")
async def request_quote(
    payload: QuoteRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Record an actionable sales request when self-service payment is unavailable."""
    _require_tenant_admin(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    db = _db()
    product = await db.marketplace_products.find_one(
        {"key": payload.product_key, "active": True}, {"_id": 0, "key": 1, "name": 1, "price_try": 1}
    )
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")

    request_id = str(uuid.uuid4())
    await db.marketplace_quote_requests.insert_one({
        "id": request_id,
        "tenant_id": current_user.tenant_id,
        "user_id": current_user.id,
        "user_email": current_user.email,
        "product_key": product["key"],
        "product_name": product["name"],
        "listed_price_try": product.get("price_try"),
        "note": payload.note,
        "status": "new",
        "created_at": _now_iso(),
    })
    return {"ok": True, "request_id": request_id, "status": "new"}


# ── Purchase flow ───────────────────────────────────────────────
@router.post("/purchase")
async def purchase(
    payload: PurchaseRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generic iyzico Checkout Form purchase. Returns paymentPageUrl."""
    from core.iyzico import init_checkout_form, is_configured, public_callback_url

    _require_tenant_admin(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    db = _db()
    product = await db.marketplace_products.find_one({"key": payload.product_key, "active": True}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    if not is_configured():
        raise HTTPException(
            status_code=503,
            detail="Ödeme sistemi henüz aktif değil. Lütfen kısa süre sonra tekrar deneyin.",
        )

    tenant = await db.tenants.find_one({"id": current_user.tenant_id}, {"_id": 0})
    quote = calculate_price(product, payload.quantity)
    order_id = str(uuid.uuid4())
    order_doc = {
        "order_id": order_id,
        "tenant_id": current_user.tenant_id,
        "user_id": current_user.id,
        "product_key": product["key"],
        "product_name": product["name"],
        "price_try": quote["total_try"],
        "subtotal_try": quote["subtotal_try"],
        "tax_try": quote["tax_try"],
        "tax_rate_pct": quote["tax_rate_pct"],
        "quantity": quote["quantity"],
        "billable_units": quote["billable_units"],
        "price_version": quote["price_version"],
        "duration_days": product.get("duration_days"),
        "credits": product.get("credits"),
        "billing_type": product.get("billing_type"),
        "status": "pending",
        "created_at": _now_iso(),
    }
    await db.marketplace_orders.insert_one({**order_doc})

    callback = public_callback_url(f"/api/module-store/purchase/callback?order_id={order_id}")
    name_parts = (current_user.name or "Otel Sahibi").split()
    first = name_parts[0] if name_parts else "Otel"
    last = " ".join(name_parts[1:]) if len(name_parts) > 1 else "Sahibi"
    buyer_email = (tenant or {}).get("email") or (current_user.email or "noreply@syroce.com")

    iyzico_payload = {
        "locale": "tr",
        "conversationId": order_id,
        "price": str(quote["total_try"]),
        "paidPrice": str(quote["total_try"]),
        "currency": "TRY",
        "basketId": order_id,
        "paymentGroup": "PRODUCT",
        "callbackUrl": callback,
        "enabledInstallments": [2, 3, 6, 9],
        "buyer": {
            "id": current_user.id,
            "name": first,
            "surname": last,
            "gsmNumber": (tenant or {}).get("phone") or "+905555555555",
            "email": buyer_email,
            "identityNumber": (tenant or {}).get("tax_number") or (tenant or {}).get("identity_number") or "11111111111",
            "registrationAddress": (tenant or {}).get("address") or "Türkiye",
            "ip": request.client.host if request.client else "127.0.0.1",
            "city": (tenant or {}).get("city") or "Istanbul",
            "country": "Turkey",
        },
        "shippingAddress": {
            "contactName": (tenant or {}).get("property_name") or "Otel",
            "city": (tenant or {}).get("city") or "Istanbul",
            "country": "Turkey",
            "address": (tenant or {}).get("address") or "Türkiye",
        },
        "billingAddress": {
            "contactName": (tenant or {}).get("property_name") or "Otel",
            "city": (tenant or {}).get("city") or "Istanbul",
            "country": "Turkey",
            "address": (tenant or {}).get("address") or "Türkiye",
        },
        "basketItems": [
            {
                "id": product["key"],
                "name": product["name"][:80],
                "category1": "Dijital",
                "itemType": "VIRTUAL",
                "price": str(quote["total_try"]),
            }
        ],
    }
    res = init_checkout_form(iyzico_payload)
    if res.get("status") != "success":
        await db.marketplace_orders.update_one(
            {"order_id": order_id},
            {"$set": {"status": "init_failed", "error": res.get("errorMessage"), "updated_at": _now_iso()}},
        )
        raise HTTPException(
            status_code=502,
            detail=res.get("errorMessage") or "Ödeme başlatılamadı",
        )

    await db.marketplace_orders.update_one(
        {"order_id": order_id},
        {"$set": {"iyzico_token": res.get("token"), "payment_page_url": res.get("paymentPageUrl"), "updated_at": _now_iso()}},
    )
    return {
        "order_id": order_id,
        "payment_page_url": res.get("paymentPageUrl"),
        "token": res.get("token"),
    }


# ── Free trial activation (no payment) ──────────────────────────
@router.post("/start-trial")
async def start_trial(
    payload: StartTrialRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Activate a free trial for products that advertise trial_days.

    One trial per (tenant, product). Idempotent: returns existing trial
    if already started. After expiry, the entitlement check naturally
    returns False until the tenant pays for the real subscription.
    """
    _require_tenant_admin(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    db = _db()
    product = await db.marketplace_products.find_one({"key": payload.product_key, "active": True}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    trial_days = product.get("trial_days")
    if not trial_days or trial_days <= 0:
        raise HTTPException(status_code=400, detail="Bu ürün için ücretsiz deneme yok")

    # Atomic idempotent activation. The unique partial index on
    # (tenant_id, product_key, status=active) guarantees only one ACTIVE
    # sub per (tenant, product). We use update_one + $setOnInsert so:
    #   - First call inserts a brand-new trial sub.
    #   - Concurrent/replay calls observe the existing doc and return it
    #     unchanged (idempotent — same response on retry).
    now = datetime.now(UTC)
    end = now + timedelta(days=int(trial_days))
    new_sub_id = str(uuid.uuid4())
    trial_order_id = f"trial-{new_sub_id}"

    try:
        await db.tenant_subscriptions.update_one(
            {
                "tenant_id": current_user.tenant_id,
                "product_key": product["key"],
                "status": "active",
            },
            {
                "$setOnInsert": {
                    "id": new_sub_id,
                    "tenant_id": current_user.tenant_id,
                    "product_key": product["key"],
                    "status": "active",
                    "trial": True,
                    "start_date": now.isoformat(),
                    "end_date": end.isoformat(),
                    "order_id": trial_order_id,
                    "created_at": _now_iso(),
                }
            },
            upsert=True,
        )
    except Exception as e:
        # Race: a concurrent request inserted between our upsert attempts.
        # The partial unique index made the upsert raise — fall through
        # to read the now-existing doc and return it idempotently.
        logger.info("[marketplace] start-trial concurrent insert resolved: %s", e)

    sub = await db.tenant_subscriptions.find_one(
        {
            "tenant_id": current_user.tenant_id,
            "product_key": product["key"],
            "status": "active",
        },
        {"_id": 0},
    )
    if not sub:
        # Should never happen — upsert + read both failed.
        raise HTTPException(status_code=500, detail="Deneme oluşturulamadı")

    is_new = sub.get("id") == new_sub_id

    # If a paid (non-trial) subscription already exists for this product,
    # block trial start to avoid downgrading the user's status.
    if not sub.get("trial") and not is_new:
        raise HTTPException(status_code=409, detail="Bu modül için zaten aktif bir ücretli abonelik var")

    if is_new:
        # Post-activation hook (provisioning) — only on first creation.
        if product["key"] == "af_sadakat":
            try:
                from core.afsadakat_provisioner import provision_tenant

                await provision_tenant(current_user.tenant_id)
            except Exception as e:
                logger.exception("[marketplace] afsadakat trial provision failed: %s", e)
        await provision_subscription(db, current_user.tenant_id, product, sub["id"])
        logger.info("[marketplace] trial started tenant=%s product=%s until=%s", current_user.tenant_id, product["key"], sub["end_date"])

    return {
        "ok": True,
        "subscription_id": sub["id"],
        "product_key": product["key"],
        "trial": bool(sub.get("trial")),
        "end_date": sub.get("end_date"),
        "already_existed": not is_new,
    }


@router.post("/purchase/callback")
@router.get("/purchase/callback")
async def purchase_callback(order_id: str) -> dict:
    """iyzico callback. Atomic + idempotent subscription activation."""
    from core.iyzico import retrieve_checkout_form

    db = _db()
    order = await db.marketplace_orders.find_one({"order_id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    if order.get("status") == "completed":
        return {"status": "already_completed", "product_key": order["product_key"]}
    iyzico_token = order.get("iyzico_token")
    if not iyzico_token:
        raise HTTPException(status_code=400, detail="Token bulunamadı")

    res = retrieve_checkout_form(iyzico_token)
    paid_price = res.get("paidPrice")
    try:
        paid_ok = paid_price is not None and float(paid_price) == float(order["price_try"])
    except (TypeError, ValueError):
        paid_ok = False
    valid = (
        res.get("status") == "success"
        and res.get("paymentStatus") == "SUCCESS"
        and (res.get("conversationId") == order_id or res.get("basketId") == order_id)
        and res.get("currency") == "TRY"
        and paid_ok
    )

    if not valid:
        # NOT terminal: leave as pending so iyzico/operator can retry.
        # Just log the latest attempt for diagnostics.
        await db.marketplace_orders.update_one(
            {"order_id": order_id},
            {"$set": {"last_validation_error": res.get("errorMessage"), "last_validation_at": _now_iso()}},
        )
        logger.warning("[marketplace] order=%s validation failed (retryable): %s", order_id, res.get("errorMessage"))
        raise HTTPException(status_code=400, detail=res.get("errorMessage") or "Ödeme doğrulanamadı")

    # Activate FIRST (subscription/credit grant). Activation is idempotent
    # via order_id uniqueness so safe to retry. Mark order completed only
    # after activation success — guarantees no "paid but not activated" state.
    try:
        await _activate_subscription(order)
    except Exception as e:
        logger.exception("[marketplace] activation failed for order=%s: %s", order_id, e)
        raise HTTPException(status_code=500, detail="Aktivasyon hatası; lütfen birkaç dakika sonra tekrar deneyin")

    # Some iyzico merchant configurations return a reusable card token.  Store
    # it server-side only so the renewal worker can charge without exposing it.
    if res.get("cardToken") and res.get("cardUserKey"):
        tenant = await db.tenants.find_one({"id": order["tenant_id"]}, {"_id": 0}) or {}
        contact = tenant.get("property_name") or "Otel"
        address = {"contactName": contact, "city": tenant.get("city") or "Istanbul", "country": "Turkey", "address": tenant.get("address") or "Türkiye"}
        await db.marketplace_payment_methods.update_many({"tenant_id": order["tenant_id"]}, {"$set": {"is_default": False}})
        await db.marketplace_payment_methods.insert_one({"id": str(uuid.uuid4()), "tenant_id": order["tenant_id"], "provider": "iyzico", "status": "active", "is_default": True, "card_user_key": res["cardUserKey"], "card_token": res["cardToken"], "last4": res.get("lastFourDigits"), "card_family": res.get("cardFamily"), "buyer": {"id": order["user_id"], "name": contact, "surname": "Yetkilisi", "gsmNumber": tenant.get("phone") or "+905555555555", "email": tenant.get("email") or "noreply@syroce.com", "identityNumber": tenant.get("tax_number") or "11111111111", "registrationAddress": address["address"], "ip": "127.0.0.1", "city": address["city"], "country": "Turkey"}, "address": address, "created_at": _now_iso()})

    await db.marketplace_orders.update_one(
        {"order_id": order_id, "status": "pending"},
        {"$set": {"status": "completed", "iyzico_payment_id": res.get("paymentId"), "completed_at": _now_iso()}},
    )
    return {"status": "completed", "product_key": order["product_key"]}


@router.get("/billing")
async def billing_overview(current_user: User = Depends(get_current_user)) -> dict:
    _require_tenant_admin(current_user)
    db = _db()
    subscriptions = await get_active_subscriptions(current_user.tenant_id)
    orders = [row async for row in db.marketplace_orders.find({"tenant_id": current_user.tenant_id, "status": "completed"}, {"_id": 0, "iyzico_token": 0}).sort("created_at", -1).limit(100)]
    methods = [row async for row in db.marketplace_payment_methods.find({"tenant_id": current_user.tenant_id, "status": "active"}, {"_id": 0, "card_token": 0, "card_user_key": 0, "buyer": 0, "address": 0})]
    return {"subscriptions": subscriptions, "invoices": orders, "payment_methods": methods}


@router.delete("/payment-methods/{payment_method_id}")
async def remove_payment_method(payment_method_id: str, current_user: User = Depends(get_current_user)) -> dict:
    """Revoke a saved renewal mandate without ever returning provider tokens."""
    _require_tenant_admin(current_user)
    db = _db()
    result = await db.marketplace_payment_methods.update_one(
        {"id": payment_method_id, "tenant_id": current_user.tenant_id, "status": "active"},
        {"$set": {"status": "revoked", "is_default": False, "revoked_by": current_user.id, "revoked_at": _now_iso()}},
    )
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Ödeme yöntemi bulunamadı")
    return {"ok": True}


@router.post("/subscriptions/{subscription_id}/cancel")
async def cancel_subscription(subscription_id: str, payload: SubscriptionAction, current_user: User = Depends(get_current_user)) -> dict:
    _require_tenant_admin(current_user)
    db = _db()
    result = await db.tenant_subscriptions.update_one({"id": subscription_id, "tenant_id": current_user.tenant_id, "status": {"$in": ["active", "past_due"]}}, {"$set": {"auto_renew": False, "cancel_at_period_end": True, "cancel_reason": payload.reason, "cancelled_by": current_user.id, "updated_at": _now_iso()}})
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Abonelik bulunamadı")
    return {"ok": True, "cancel_at_period_end": True}


@router.post("/orders/refund-request")
async def request_refund(payload: RefundRequest, current_user: User = Depends(get_current_user)) -> dict:
    _require_tenant_admin(current_user)
    db = _db()
    order = await db.marketplace_orders.find_one({"order_id": payload.order_id, "tenant_id": current_user.tenant_id, "status": "completed"}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="İade edilebilir sipariş bulunamadı")
    request_id = str(uuid.uuid4())
    await db.marketplace_refund_requests.update_one({"order_id": payload.order_id}, {"$setOnInsert": {"id": request_id, "tenant_id": current_user.tenant_id, "order_id": payload.order_id, "reason": payload.reason, "status": "new", "created_by": current_user.id, "created_at": _now_iso()}}, upsert=True)
    return {"ok": True, "request_id": request_id, "status": "new"}


@router.get("/subscriptions/{subscription_id}/readiness")
async def subscription_readiness(subscription_id: str, current_user: User = Depends(get_current_user)) -> dict:
    _require_tenant_admin(current_user)
    plan = await _db().marketplace_provisioning.find_one({"subscription_id": subscription_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not plan:
        raise HTTPException(status_code=404, detail="Kurulum planı bulunamadı")
    complete = sum(1 for step in plan.get("steps", []) if step.get("status") == "complete")
    return {**plan, "health": "healthy" if complete == len(plan.get("steps", [])) else "setup_required", "completed_steps": complete, "total_steps": len(plan.get("steps", []))}


@router.patch("/subscriptions/{subscription_id}/readiness")
async def update_readiness(subscription_id: str, payload: ReadinessStepUpdate, current_user: User = Depends(get_current_user)) -> dict:
    _require_tenant_admin(current_user)
    db = _db()
    plan = await db.marketplace_provisioning.find_one({"subscription_id": subscription_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not plan:
        raise HTTPException(status_code=404, detail="Kurulum planı bulunamadı")
    found = False
    for step in plan.get("steps", []):
        if step.get("key") == payload.step_key:
            step["status"] = "complete" if payload.completed else "pending"; step["updated_at"] = _now_iso(); found = True
    if not found:
        raise HTTPException(status_code=404, detail="Kurulum adımı bulunamadı")
    ready = all(step.get("status") == "complete" for step in plan.get("steps", []))
    await db.marketplace_provisioning.update_one({"subscription_id": subscription_id}, {"$set": {"steps": plan["steps"], "status": "ready" if ready else "setup_required", "updated_at": _now_iso()}})
    return {"ok": True, "status": "ready" if ready else "setup_required"}


async def _activate_subscription(order: dict) -> None:
    """Create or extend a tenant subscription based on a paid order.

    Idempotent: a unique index on (order_id) for tenant_subscriptions
    guarantees a given order can grant entitlement only once even if
    the callback is replayed.
    """
    db = _db()
    tenant_id = order["tenant_id"]
    product_key = order["product_key"]
    duration_days = order.get("duration_days")
    credits = order.get("credits")
    now = datetime.now(UTC)
    product = await db.marketplace_products.find_one({"key": product_key}, {"_id": 0}) or enrich_product({"key": product_key, "price_try": order.get("subtotal_try", order.get("price_try", 0)), "billing_type": order.get("billing_type", "subscription")})

    # Atomic idempotency guard: insert a marker row keyed by order_id
    # BEFORE any entitlement mutation. Unique index on order_id (see
    # core.subscriptions.ensure_indexes) makes the second insert raise
    # DuplicateKeyError, so concurrent callbacks and replays cannot
    # double-extend a subscription — even in the "extend existing"
    # branch where tenant_subscriptions.order_id is not persisted.
    from pymongo.errors import DuplicateKeyError

    try:
        await db.tenant_subscription_activations.insert_one(
            {
                "order_id": order["order_id"],
                "tenant_id": tenant_id,
                "product_key": product_key,
                "activated_at": _now_iso(),
            }
        )
    except DuplicateKeyError:
        logger.info("[marketplace] order=%s already activated (atomic guard)", order["order_id"])
        return

    # Credit pack: top up the mailing credits balance.
    # Use lifetime_purchased to stay consistent with the existing mailing
    # module schema (avoids dual counter drift).
    if credits and product_key.startswith("mailing"):
        await db.mailing_credits.update_one(
            {"tenant_id": tenant_id},
            {
                "$inc": {"balance": int(credits), "lifetime_purchased": int(credits)},
                "$setOnInsert": {"tenant_id": tenant_id, "created_at": _now_iso()},
                "$set": {"updated_at": _now_iso()},
            },
            upsert=True,
        )
        await db.marketplace_credit_grants.insert_one({"id": str(uuid.uuid4()), "tenant_id": tenant_id, "product_key": product_key, "credits_granted": int(credits), "order_id": order["order_id"], "created_at": _now_iso()})
        logger.info("[marketplace] tenant=%s credits +%s for %s", tenant_id, credits, product_key)
        return

    # Post-activation hooks: external modules need provisioning.
    async def _post_activate() -> None:
        if product_key == "af_sadakat":
            try:
                from core.afsadakat_provisioner import provision_tenant

                await provision_tenant(tenant_id)
            except Exception as e:
                logger.exception("[marketplace] afsadakat provision failed for %s: %s", tenant_id, e)

    # Subscription: extend existing active sub, or create new one.
    existing = await db.tenant_subscriptions.find_one(
        {
            "tenant_id": tenant_id,
            "product_key": product_key,
            "status": "active",
        }
    )
    new_end = now + timedelta(days=duration_days or 30)
    if existing and existing.get("end_date"):
        try:
            curr_end = datetime.fromisoformat(existing["end_date"].replace("Z", "+00:00"))
            base = curr_end if curr_end > now else now
            new_end = base + timedelta(days=duration_days or 30)
        except Exception:
            pass
        await db.tenant_subscriptions.update_one(
            {"id": existing["id"]},
            {"$set": {"end_date": new_end.isoformat(), "last_renewal_order_id": order["order_id"], "trial": False, "auto_renew": bool(product.get("auto_renew", True)), "quantity": order.get("quantity", 1), "updated_at": _now_iso()}},
        )
        subscription_id = existing["id"]
        logger.info("[marketplace] tenant=%s extended %s until %s", tenant_id, product_key, new_end.isoformat())
    else:
        subscription_id = str(uuid.uuid4())
        await db.tenant_subscriptions.insert_one(
            {
                "id": subscription_id,
                "tenant_id": tenant_id,
                "product_key": product_key,
                "status": "active",
                "start_date": now.isoformat(),
                "end_date": new_end.isoformat(),
                "order_id": order["order_id"],
                "trial": False,
                "auto_renew": bool(product.get("auto_renew", True)),
                "quantity": order.get("quantity", 1),
                "renewal_status": "scheduled",
                "created_at": _now_iso(),
            }
        )
        logger.info("[marketplace] tenant=%s activated %s until %s", tenant_id, product_key, new_end.isoformat())

    await _post_activate()
    await provision_subscription(db, tenant_id, product, subscription_id)


# ── Authorization helpers ────────────────────────────────────────
def _is_platform_admin(user: User) -> bool:
    """Platform-wide admin (Syroce staff). Manages product catalog."""
    from core.security import _is_super_admin

    if _is_super_admin(user):
        return True
    role = (user.role or "").lower()
    if role in ("super_admin", "platform_admin"):
        return True
    roles = getattr(user, "roles", None) or []
    return any(r in ("super_admin", "platform_admin") for r in roles)


def _is_tenant_admin(user: User) -> bool:
    """Hotel-level admin. May only see own tenant's data."""
    from core.security import _is_super_admin

    if _is_super_admin(user):
        return True
    role = (user.role or "").lower()
    if role in ("admin", "super_admin", "owner", "gm", "platform_admin"):
        return True
    roles = getattr(user, "roles", None) or []
    return any(r in ("admin", "super_admin", "owner", "gm", "platform_admin") for r in roles)


def _require_platform_admin(user: User) -> None:
    if not _is_platform_admin(user):
        raise HTTPException(status_code=403, detail="Platform yöneticisi yetkisi gerekli")


def _require_tenant_admin(user: User) -> None:
    if not _is_tenant_admin(user):
        raise HTTPException(status_code=403, detail="Yetki yok")
    if not getattr(user, "tenant_id", None):
        raise HTTPException(status_code=422, detail="Bu işlem için bir otel hesabı seçilmelidir")


# ── Platform admin: product catalog CRUD ────────────────────────
@router.get("/admin/products")
async def admin_list_products(
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_platform_admin(current_user)
    await _seed_products_if_empty()
    db = _db()
    cur = db.marketplace_products.find({}, {"_id": 0}).sort("name", 1)
    return {"products": [doc async for doc in cur]}


@router.post("/admin/products")
async def admin_upsert_product(
    payload: ProductIn,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
) -> dict:
    _require_platform_admin(current_user)
    db = _db()
    doc = enrich_product(payload.model_dump())
    existing = await db.marketplace_products.find_one({"key": doc["key"]}, {"_id": 0})
    price_changed = bool(existing) and any(existing.get(field) != doc.get(field) for field in ("price_try", "unit_price_try", "tax_rate_pct", "included_units", "pricing_model"))
    if price_changed:
        doc["price_version"] = int(existing.get("price_version", 1)) + 1
        await db.marketplace_price_history.insert_one({"id": str(uuid.uuid4()), "product_key": doc["key"], "version": doc["price_version"], "previous": {field: existing.get(field) for field in ("price_try", "unit_price_try", "tax_rate_pct", "included_units", "pricing_model", "price_source", "price_valid_from", "price_valid_until")}, "next": {field: doc.get(field) for field in ("price_try", "unit_price_try", "tax_rate_pct", "included_units", "pricing_model", "price_source", "price_valid_from", "price_valid_until")}, "changed_by": current_user.id, "changed_at": _now_iso()})
    await db.marketplace_products.update_one(
        {"key": doc["key"]},
        {"$set": {**doc, "updated_at": _now_iso()}, "$setOnInsert": {"created_at": _now_iso()}},
        upsert=True,
    )
    return {"ok": True, "key": doc["key"], "price_version": doc.get("price_version", 1)}


@router.get("/admin/products/{key}/price-history")
async def admin_price_history(key: str, current_user: User = Depends(get_current_user)) -> dict:
    _require_platform_admin(current_user)
    rows = [row async for row in _db().marketplace_price_history.find({"product_key": key}, {"_id": 0}).sort("changed_at", -1).limit(100)]
    return {"history": rows}


@router.get("/admin/setup-tasks")
async def admin_setup_tasks(current_user: User = Depends(get_current_user), status_filter: str | None = None) -> dict:
    _require_platform_admin(current_user)
    query = {"status": status_filter} if status_filter else {}
    rows = [row async for row in _db().marketplace_setup_tasks.find(query, {"_id": 0}).sort("created_at", -1).limit(200)]
    return {"tasks": rows}


@router.post("/admin/run-renewals")
async def admin_run_renewals(current_user: User = Depends(get_current_user)) -> dict:
    _require_platform_admin(current_user)
    from workers.marketplace_renewal_worker import process_due_renewals
    return await process_due_renewals(_db())


@router.delete("/admin/products/{key}")
async def admin_delete_product(
    key: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
) -> dict:
    _require_platform_admin(current_user)
    db = _db()
    await db.marketplace_products.update_one({"key": key}, {"$set": {"active": False, "updated_at": _now_iso()}})
    return {"ok": True}


# ── Hotel admin: own tenant's orders only ───────────────────────
@router.get("/orders")
async def list_my_orders(
    current_user: User = Depends(get_current_user),
    limit: int = 100,
) -> dict:
    """Tenant-scoped order history. Hotel admin sees only own orders."""
    _require_tenant_admin(current_user)
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    db = _db()
    cur = db.marketplace_orders.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).sort("created_at", -1).limit(limit)
    return {"orders": [doc async for doc in cur]}


# ── Platform admin: ALL orders across tenants ───────────────────
@router.get("/admin/orders")
async def admin_list_all_orders(
    current_user: User = Depends(get_current_user),
    limit: int = 200,
) -> dict:
    _require_platform_admin(current_user)
    db = _db()
    cur = db.marketplace_orders.find({}, {"_id": 0}).sort("created_at", -1).limit(limit)
    return {"orders": [doc async for doc in cur]}
