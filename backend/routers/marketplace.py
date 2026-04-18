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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.security import get_current_user
from core.subscriptions import ensure_indexes, get_active_subscriptions
from models.schemas import User

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
    if inserted:
        logger.info("[marketplace] inserted %d new default products", inserted)

    # Deactivate legacy QR product — that module is included free in all plans.
    await db.marketplace_products.update_one(
        {"key": "qr_room_management"},
        {"$set": {"active": False, "updated_at": _now_iso(),
                  "deactivated_reason": "Tüm planlarda ücretsiz olarak dahildir"}},
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
    external: bool = False
    sso_path: str | None = None
    active: bool = True


class PurchaseRequest(BaseModel):
    product_key: str


class StartTrialRequest(BaseModel):
    product_key: str


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


# ── Tenant: my subscriptions ────────────────────────────────────
@router.get("/my-subscriptions")
async def my_subscriptions(
    current_user: User = Depends(get_current_user),
) -> dict:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    subs = await get_active_subscriptions(current_user.tenant_id)
    return {"subscriptions": subs}


# ── Purchase flow ───────────────────────────────────────────────
@router.post("/purchase")
async def purchase(
    payload: PurchaseRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Generic iyzico Checkout Form purchase. Returns paymentPageUrl."""
    from core.iyzico import init_checkout_form, is_configured, public_callback_url

    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    db = _db()
    product = await db.marketplace_products.find_one(
        {"key": payload.product_key, "active": True}, {"_id": 0}
    )
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    if not is_configured():
        raise HTTPException(
            status_code=503,
            detail="Ödeme sistemi henüz aktif değil. Lütfen kısa süre sonra tekrar deneyin.",
        )

    tenant = await db.tenants.find_one({"id": current_user.tenant_id}, {"_id": 0})
    order_id = str(uuid.uuid4())
    order_doc = {
        "order_id": order_id,
        "tenant_id": current_user.tenant_id,
        "user_id": current_user.id,
        "product_key": product["key"],
        "product_name": product["name"],
        "price_try": product["price_try"],
        "duration_days": product.get("duration_days"),
        "credits": product.get("credits"),
        "billing_type": product.get("billing_type"),
        "status": "pending",
        "created_at": _now_iso(),
    }
    await db.marketplace_orders.insert_one({**order_doc})

    callback = public_callback_url(
        f"/api/module-store/purchase/callback?order_id={order_id}"
    )
    name_parts = (current_user.name or "Otel Sahibi").split()
    first = name_parts[0] if name_parts else "Otel"
    last = " ".join(name_parts[1:]) if len(name_parts) > 1 else "Sahibi"
    buyer_email = (tenant or {}).get("email") or (current_user.email or "noreply@syroce.com")

    iyzico_payload = {
        "locale": "tr",
        "conversationId": order_id,
        "price": str(product["price_try"]),
        "paidPrice": str(product["price_try"]),
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
            "identityNumber": "11111111111",
            "registrationAddress": (tenant or {}).get("address") or "Türkiye",
            "ip": "127.0.0.1",
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
        "basketItems": [{
            "id": product["key"],
            "name": product["name"][:80],
            "category1": "Dijital",
            "itemType": "VIRTUAL",
            "price": str(product["price_try"]),
        }],
    }
    res = init_checkout_form(iyzico_payload)
    if res.get("status") != "success":
        await db.marketplace_orders.update_one(
            {"order_id": order_id},
            {"$set": {"status": "init_failed", "error": res.get("errorMessage"),
                      "updated_at": _now_iso()}},
        )
        raise HTTPException(
            status_code=502,
            detail=res.get("errorMessage") or "Ödeme başlatılamadı",
        )

    await db.marketplace_orders.update_one(
        {"order_id": order_id},
        {"$set": {"iyzico_token": res.get("token"),
                  "payment_page_url": res.get("paymentPageUrl"),
                  "updated_at": _now_iso()}},
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
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    db = _db()
    product = await db.marketplace_products.find_one(
        {"key": payload.product_key, "active": True}, {"_id": 0}
    )
    if not product:
        raise HTTPException(status_code=404, detail="Ürün bulunamadı")
    trial_days = product.get("trial_days")
    if not trial_days or trial_days <= 0:
        raise HTTPException(status_code=400,
                            detail="Bu ürün için ücretsiz deneme yok")

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
        raise HTTPException(
            status_code=409,
            detail="Bu modül için zaten aktif bir ücretli abonelik var"
        )

    if is_new:
        # Post-activation hook (provisioning) — only on first creation.
        if product["key"] == "af_sadakat":
            try:
                from core.afsadakat_provisioner import provision_tenant
                await provision_tenant(current_user.tenant_id)
            except Exception as e:
                logger.exception("[marketplace] afsadakat trial provision failed: %s", e)
        logger.info("[marketplace] trial started tenant=%s product=%s until=%s",
                    current_user.tenant_id, product["key"], sub["end_date"])

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
            {"$set": {"last_validation_error": res.get("errorMessage"),
                      "last_validation_at": _now_iso()}},
        )
        logger.warning("[marketplace] order=%s validation failed (retryable): %s",
                       order_id, res.get("errorMessage"))
        raise HTTPException(status_code=400,
                            detail=res.get("errorMessage") or "Ödeme doğrulanamadı")

    # Activate FIRST (subscription/credit grant). Activation is idempotent
    # via order_id uniqueness so safe to retry. Mark order completed only
    # after activation success — guarantees no "paid but not activated" state.
    try:
        await _activate_subscription(order)
    except Exception as e:
        logger.exception("[marketplace] activation failed for order=%s: %s",
                         order_id, e)
        raise HTTPException(status_code=500,
                            detail="Aktivasyon hatası; lütfen birkaç dakika sonra tekrar deneyin")

    await db.marketplace_orders.update_one(
        {"order_id": order_id, "status": "pending"},
        {"$set": {"status": "completed",
                  "iyzico_payment_id": res.get("paymentId"),
                  "completed_at": _now_iso()}},
    )
    return {"status": "completed", "product_key": order["product_key"]}


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

    # Idempotency guard: if a subscription record already exists for this
    # exact order, activation has already happened — no-op.
    already = await db.tenant_subscriptions.find_one({"order_id": order["order_id"]})
    if already:
        logger.info("[marketplace] order=%s already activated, skipping",
                    order["order_id"])
        return

    # Credit pack: top up the mailing credits balance.
    # Use lifetime_purchased to stay consistent with the existing mailing
    # module schema (avoids dual counter drift).
    if credits and product_key.startswith("mailing"):
        await db.mailing_credits.update_one(
            {"tenant_id": tenant_id},
            {
                "$inc": {"balance": int(credits),
                         "lifetime_purchased": int(credits)},
                "$setOnInsert": {"tenant_id": tenant_id,
                                 "created_at": _now_iso()},
                "$set": {"updated_at": _now_iso()},
            },
            upsert=True,
        )
        await db.tenant_subscriptions.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "product_key": product_key,
            "status": "active",
            "start_date": now.isoformat(),
            "end_date": None,
            "credits_granted": int(credits),
            "order_id": order["order_id"],
            "created_at": _now_iso(),
        })
        logger.info("[marketplace] tenant=%s credits +%s for %s",
                    tenant_id, credits, product_key)
        return

    # Post-activation hooks: external modules need provisioning.
    async def _post_activate() -> None:
        if product_key == "af_sadakat":
            try:
                from core.afsadakat_provisioner import provision_tenant
                await provision_tenant(tenant_id)
            except Exception as e:
                logger.exception("[marketplace] afsadakat provision failed for %s: %s",
                                 tenant_id, e)

    # Subscription: extend existing active sub, or create new one.
    existing = await db.tenant_subscriptions.find_one({
        "tenant_id": tenant_id,
        "product_key": product_key,
        "status": "active",
    })
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
            {"$set": {"end_date": new_end.isoformat(),
                      "last_renewal_order_id": order["order_id"],
                      "updated_at": _now_iso()}},
        )
        logger.info("[marketplace] tenant=%s extended %s until %s",
                    tenant_id, product_key, new_end.isoformat())
    else:
        await db.tenant_subscriptions.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "product_key": product_key,
            "status": "active",
            "start_date": now.isoformat(),
            "end_date": new_end.isoformat(),
            "order_id": order["order_id"],
            "created_at": _now_iso(),
        })
        logger.info("[marketplace] tenant=%s activated %s until %s",
                    tenant_id, product_key, new_end.isoformat())

    await _post_activate()


# ── Authorization helpers ────────────────────────────────────────
def _is_platform_admin(user: User) -> bool:
    """Platform-wide admin (Syroce staff). Manages product catalog."""
    role = (user.role or "").lower()
    return role in ("super_admin", "platform_admin")


def _is_tenant_admin(user: User) -> bool:
    """Hotel-level admin. May only see own tenant's data."""
    role = (user.role or "").lower()
    return role in ("admin", "super_admin", "owner", "gm", "platform_admin")


def _require_platform_admin(user: User) -> None:
    if not _is_platform_admin(user):
        raise HTTPException(status_code=403, detail="Platform yöneticisi yetkisi gerekli")


def _require_tenant_admin(user: User) -> None:
    if not _is_tenant_admin(user):
        raise HTTPException(status_code=403, detail="Yetki yok")


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
) -> dict:
    _require_platform_admin(current_user)
    db = _db()
    doc = payload.model_dump()
    await db.marketplace_products.update_one(
        {"key": doc["key"]},
        {"$set": {**doc, "updated_at": _now_iso()},
         "$setOnInsert": {"created_at": _now_iso()}},
        upsert=True,
    )
    return {"ok": True, "key": doc["key"]}


@router.delete("/admin/products/{key}")
async def admin_delete_product(
    key: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    _require_platform_admin(current_user)
    db = _db()
    await db.marketplace_products.update_one(
        {"key": key}, {"$set": {"active": False, "updated_at": _now_iso()}}
    )
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
    cur = (
        db.marketplace_orders
        .find({"tenant_id": current_user.tenant_id}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    return {"orders": [doc async for doc in cur]}


# ── Platform admin: ALL orders across tenants ───────────────────
@router.get("/admin/orders")
async def admin_list_all_orders(
    current_user: User = Depends(get_current_user),
    limit: int = 200,
) -> dict:
    _require_platform_admin(current_user)
    db = _db()
    cur = (
        db.marketplace_orders
        .find({}, {"_id": 0})
        .sort("created_at", -1)
        .limit(limit)
    )
    return {"orders": [doc async for doc in cur]}
