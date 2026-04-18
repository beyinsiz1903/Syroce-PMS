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
        "key": "qr_room_management",
        "name": "QR Oda Yönetimi",
        "description": "Her oda için QR kod üretimi, misafir self-servis talepleri.",
        "category": "module",
        "billing_type": "subscription",
        "price_try": 199.0,
        "duration_days": 30,
        "icon": "QrCode",
        "features": [
            "Oda başına benzersiz QR kod",
            "Misafir talep formu",
            "Talep yönetim paneli",
        ],
        "active": True,
    },
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
]


def _db():
    from server import db
    return db


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _seed_products_if_empty() -> None:
    db = _db()
    await ensure_indexes()
    count = await db.marketplace_products.count_documents({})
    if count == 0:
        for p in DEFAULT_PRODUCTS:
            await db.marketplace_products.update_one(
                {"key": p["key"]},
                {"$setOnInsert": {**p, "created_at": _now_iso()}},
                upsert=True,
            )
        logger.info("[marketplace] seeded %d default products", len(DEFAULT_PRODUCTS))


# ── Schemas ─────────────────────────────────────────────────────
class ProductIn(BaseModel):
    key: str
    name: str
    description: str = ""
    category: str = Field(default="module")  # module|integration|credit_pack
    billing_type: str = Field(default="subscription")  # subscription|one_time
    price_try: float = 0
    duration_days: int | None = 30
    icon: str | None = None
    credits: int | None = None
    features: list[str] = Field(default_factory=list)
    active: bool = True


class PurchaseRequest(BaseModel):
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
