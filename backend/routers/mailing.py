"""Mailing module — Phase 1.

Endpoints to manage email templates, recipients (guests with email),
campaigns, and per-tenant credits. Sending uses the shared `core.email`
helper (Resend). The hotelier's own email is set as Reply-To so guest
replies go straight to them; the visible "From" remains the verified
Syroce domain for deliverability.
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.email import send_email
from core.security import get_current_user
from models.schemas import User
from security.encrypted_lookup import decrypt_user_doc

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/mailing", tags=["mailing"])

DEFAULT_FREE_CREDITS = 100
RECIPIENT_FETCH_LIMIT = 1000
SEND_BATCH_LIMIT = 500  # max recipients per single campaign send

# ── Kredi paketleri (TRY, KDV dahil) ────────────────────────────────────
CREDIT_PACKAGES = [
    {"code": "starter",  "name": "Başlangıç", "credits": 1000,  "price_try": 299,
     "per_email": 0.299, "popular": False, "description": "Küçük kampanyalar için ideal"},
    {"code": "growth",   "name": "Büyüme",    "credits": 5000,  "price_try": 999,
     "per_email": 0.200, "popular": True,  "description": "En çok tercih edilen paket"},
    {"code": "scale",    "name": "Profesyonel", "credits": 25000, "price_try": 3499,
     "per_email": 0.140, "popular": False, "description": "Yoğun kullanım için en avantajlı"},
]
PACKAGE_BY_CODE = {p["code"]: p for p in CREDIT_PACKAGES}

# Automation trigger types
AUTOMATION_TRIGGERS = {
    "booking_created": {
        "label": "Rezervasyon Onayı",
        "description": "Rezervasyon oluşturulur oluşturulmaz misafire onay e-postası gönderilir",
        "default_offset_days": 0,
    },
    "checkin_reminder": {
        "label": "Check-in Hatırlatma",
        "description": "Check-in tarihinden 1 gün önce hatırlatma e-postası gönderilir",
        "default_offset_days": -1,
    },
    "checkout_thanks": {
        "label": "Check-out Sonrası Teşekkür",
        "description": "Check-out'tan 2 gün sonra teşekkür / anket e-postası gönderilir",
        "default_offset_days": 2,
    },
    "in_house_guests": {
        "label": "Konaklayan Misafirler (Hoş Geldin)",
        "description": "Şu an otelde konaklayan her misafire bir kez (örn. hoş geldin) e-postası gönderilir",
        "default_offset_days": 0,
    },
}


def _db():
    from server import db  # late import to avoid circulars
    return db


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ── Schemas ─────────────────────────────────────────────────────────────
class TemplateIn(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    subject: str = Field(..., min_length=1, max_length=200)
    html: str = Field(..., min_length=1)
    description: str | None = None


class TemplateOut(TemplateIn):
    id: str
    tenant_id: str
    created_at: str
    updated_at: str


class AutomationConfig(BaseModel):
    enabled: bool = False
    template_id: str | None = None
    offset_days: int | None = None  # negative = days BEFORE event, positive = AFTER


class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    template_id: str | None = None
    subject: str | None = None
    html: str | None = None
    recipient_ids: list[str] = Field(default_factory=list)
    test_email: str | None = None  # if set, sends only to this address (1 credit)


# ── Credit helpers ──────────────────────────────────────────────────────
async def _get_or_init_credits(tenant_id: str) -> dict:
    db = _db()
    doc = await db.mailing_credits.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if doc:
        return doc
    doc = {
        "tenant_id": tenant_id,
        "balance": DEFAULT_FREE_CREDITS,
        "lifetime_used": 0,
        "lifetime_purchased": 0,
        "free_granted": DEFAULT_FREE_CREDITS,
        "updated_at": _now_iso(),
    }
    await db.mailing_credits.insert_one({**doc})
    return doc


async def _consume_credits(tenant_id: str, n: int) -> int:
    """Atomically deduct `n` credits. Returns new balance.
    Raises HTTPException(402) if insufficient.
    """
    db = _db()
    await _get_or_init_credits(tenant_id)
    res = await db.mailing_credits.find_one_and_update(
        {"tenant_id": tenant_id, "balance": {"$gte": n}},
        {"$inc": {"balance": -n, "lifetime_used": n}, "$set": {"updated_at": _now_iso()}},
        return_document=True,
    )
    if not res:
        cur = await db.mailing_credits.find_one({"tenant_id": tenant_id}, {"balance": 1, "_id": 0})
        bal = (cur or {}).get("balance", 0)
        raise HTTPException(
            status_code=402,
            detail=f"Yetersiz mailing kredisi. Gerekli: {n}, Mevcut: {bal}. Lütfen paket yükseltin.",
        )
    return res.get("balance", 0)


# ── Credit packages & purchase (iyzico) ────────────────────────────────
class PurchaseRequest(BaseModel):
    package_code: str


_PURCHASE_INDEXES_DONE = False


async def _ensure_purchase_indexes() -> None:
    global _PURCHASE_INDEXES_DONE
    if _PURCHASE_INDEXES_DONE:
        return
    db = _db()
    try:
        await db.mailing_purchases.create_index("id", unique=True, name="uniq_purchase_id")
        await db.mailing_purchases.create_index(
            "iyzico_payment_id", unique=True, sparse=True,
            name="uniq_iyzico_payment_id",
        )
        await db.mailing_credits.create_index("tenant_id", unique=True, name="uniq_credits_tenant")
        _PURCHASE_INDEXES_DONE = True
    except Exception as e:
        logger.warning("[mailing] purchase index create skipped: %s", e)


@router.get("/packages")
async def list_packages() -> dict:
    """Public list of credit packages — also tells frontend if iyzico is configured."""
    from core.iyzico import is_configured
    await _ensure_purchase_indexes()
    return {
        "packages": CREDIT_PACKAGES,
        "payment_ready": is_configured(),
        "currency": "TRY",
    }


@router.post("/purchase")
async def purchase_package(
    payload: PurchaseRequest,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Initiate iyzico Checkout Form. Returns paymentPageUrl for redirect."""
    from core.iyzico import init_checkout_form, is_configured, public_callback_url

    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    pkg = PACKAGE_BY_CODE.get(payload.package_code)
    if not pkg:
        raise HTTPException(status_code=404, detail="Paket bulunamadı")
    if not is_configured():
        raise HTTPException(
            status_code=503,
            detail="Ödeme sistemi henüz aktif değil. Lütfen kısa süre sonra tekrar deneyin.",
        )

    db = _db()
    tenant = await db.tenants.find_one({"id": current_user.tenant_id}, {"_id": 0})
    order_id = str(uuid.uuid4())
    purchase_doc = {
        "id": order_id,
        "tenant_id": current_user.tenant_id,
        "user_id": current_user.id,
        "package_code": pkg["code"],
        "credits": pkg["credits"],
        "price_try": pkg["price_try"],
        "status": "pending",
        "created_at": _now_iso(),
    }
    await db.mailing_purchases.insert_one({**purchase_doc})

    callback = public_callback_url(f"/api/mailing/purchase/callback?order_id={order_id}")
    buyer_name = (current_user.name or "Otel Sahibi").split()
    first = buyer_name[0] if buyer_name else "Otel"
    last = " ".join(buyer_name[1:]) if len(buyer_name) > 1 else "Sahibi"
    buyer_email = (tenant or {}).get("email") or (current_user.email or "noreply@syroce.com")

    iyzico_payload = {
        "locale": "tr",
        "conversationId": order_id,
        "price": str(pkg["price_try"]),
        "paidPrice": str(pkg["price_try"]),
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
            "id": pkg["code"],
            "name": f"Mailing Kredisi - {pkg['name']} ({pkg['credits']} adet)",
            "category1": "Dijital",
            "itemType": "VIRTUAL",
            "price": str(pkg["price_try"]),
        }],
    }
    res = init_checkout_form(iyzico_payload)
    if res.get("status") != "success":
        await db.mailing_purchases.update_one(
            {"id": order_id},
            {"$set": {"status": "init_failed", "error": res.get("errorMessage"),
                      "updated_at": _now_iso()}},
        )
        raise HTTPException(status_code=502,
                            detail=res.get("errorMessage") or "Ödeme başlatılamadı")

    await db.mailing_purchases.update_one(
        {"id": order_id},
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
    """iyzico kullanıcıyı bu URL'ye yönlendirir. Token DB'den alınır
    (dış girdiyle override edilemez). Yanıt sıkı kontrollerden geçirilir,
    kredi yükleme atomik+idempotent şekilde yapılır."""
    from core.iyzico import retrieve_checkout_form
    db = _db()
    order = await db.mailing_purchases.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Sipariş bulunamadı")
    if order.get("status") == "completed":
        return {"status": "already_completed", "credits": order["credits"]}
    iyzico_token = order.get("iyzico_token")
    if not iyzico_token:
        raise HTTPException(status_code=400, detail="Token bulunamadı")

    res = retrieve_checkout_form(iyzico_token)

    # ── Strict validation: id/amount/currency must match the saved order ──
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

    if valid:
        # ── Atomic transition: pending → completed in a single update ──
        # Only ONE concurrent request can win; others see modified_count == 0.
        upd = await db.mailing_purchases.update_one(
            {"id": order_id, "status": "pending"},
            {"$set": {"status": "completed",
                      "iyzico_payment_id": res.get("paymentId"),
                      "completed_at": _now_iso()}},
        )
        if upd.modified_count == 1:
            await _get_or_init_credits(order["tenant_id"])
            await db.mailing_credits.update_one(
                {"tenant_id": order["tenant_id"]},
                {"$inc": {"balance": order["credits"],
                          "lifetime_purchased": order["credits"]},
                 "$set": {"updated_at": _now_iso()}},
            )
            logger.info("[mailing-purchase] tenant=%s package=%s credits=+%s OK",
                        order["tenant_id"], order["package_code"], order["credits"])
        return {"status": "completed", "credits": order["credits"]}

    await db.mailing_purchases.update_one(
        {"id": order_id, "status": "pending"},
        {"$set": {"status": "failed",
                  "error": res.get("errorMessage") or "Doğrulama hatası",
                  "updated_at": _now_iso()}},
    )
    logger.warning("[mailing-purchase] tenant=%s order=%s validation failed: %s",
                   order.get("tenant_id"), order_id, res.get("errorMessage"))
    return {"status": "failed", "error": res.get("errorMessage", "Ödeme başarısız")}


@router.get("/purchases")
async def list_purchases(current_user: User = Depends(get_current_user)) -> list[dict]:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    cursor = _db().mailing_purchases.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("created_at", -1).limit(100)
    return await cursor.to_list(100)


# ── Credits endpoints ──────────────────────────────────────────────────
@router.get("/credits")
async def get_credits(current_user: User = Depends(get_current_user)) -> dict:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    doc = await _get_or_init_credits(current_user.tenant_id)
    db = _db()
    sent_30d = await db.mailing_sends.count_documents({
        "tenant_id": current_user.tenant_id,
        "sent_at": {"$gte": (datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)).isoformat()[:10]},
    })
    return {
        "balance": doc.get("balance", 0),
        "lifetime_used": doc.get("lifetime_used", 0),
        "free_granted": doc.get("free_granted", DEFAULT_FREE_CREDITS),
        "sent_today": sent_30d,
    }


# ── Email tracking webhook (Resend) ────────────────────────────────────
from fastapi import Request

# Map Resend webhook event types to our internal status fields
_EVENT_MAP = {
    "email.delivered": ("delivered_at", "delivered"),
    "email.opened":    ("opened_at",    "opened"),
    "email.clicked":   ("clicked_at",   "clicked"),
    "email.bounced":   ("bounced_at",   "bounced"),
    "email.complained":("complained_at","complained"),
}


@router.post("/webhook/resend")
async def resend_webhook(request: Request) -> dict:
    """Receive open/click/delivery events from Resend.
    Configure in Resend dashboard → Webhooks: POST {PUBLIC_BASE_URL}/api/mailing/webhook/resend
    Optional: set RESEND_WEBHOOK_SECRET env (svix-style) for signature verification."""
    raw = await request.body()
    secret = os.environ.get("RESEND_WEBHOOK_SECRET")
    if secret:
        # Best-effort svix signature check (optional — don't break if header missing)
        try:
            from svix.webhooks import Webhook  # type: ignore
            headers = dict(request.headers.items())
            Webhook(secret).verify(raw, headers)
        except Exception as e:
            logger.warning("[mailing-webhook] signature verify failed: %s", e)
            raise HTTPException(status_code=401, detail="Invalid signature")
    try:
        import json as _json
        payload = _json.loads(raw or b"{}")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    evt_type = payload.get("type") or ""
    data = payload.get("data") or {}
    email_id = data.get("email_id") or data.get("id")
    if not email_id or evt_type not in _EVENT_MAP:
        return {"ok": True, "ignored": True}

    db = _db()

    # ── Event-level dedup: ignore duplicate webhook deliveries ──
    # Use svix-id header if present, else synthesize a stable id from payload.
    evt_id = (
        request.headers.get("svix-id")
        or data.get("created_at")
        or payload.get("created_at")
        or ""
    )
    dedup_key = f"{email_id}:{evt_type}:{evt_id}"
    try:
        await db.mailing_webhook_events.create_index("dedup_key", unique=True, name="uniq_webhook_dedup")
    except Exception:
        pass
    try:
        await db.mailing_webhook_events.insert_one(
            {"dedup_key": dedup_key, "received_at": _now_iso(), "type": evt_type, "email_id": email_id}
        )
    except Exception:
        # Duplicate delivery — already processed
        return {"ok": True, "duplicate": True}

    field, status_label = _EVENT_MAP[evt_type]
    now = _now_iso()
    set_part = {"last_event": status_label, "last_event_at": now}

    # ── Only-once timestamp + counter via field-not-exists filter ──
    base_filter = {"provider_id": email_id, field: {"$exists": False}}
    update_first = {"$set": {field: now, **set_part}}
    if evt_type == "email.opened":
        update_first["$inc"] = {"open_count": 1}
    elif evt_type == "email.clicked":
        update_first["$inc"] = {"click_count": 1}

    res = await db.mailing_sends.update_one(base_filter, update_first)
    if res.matched_count == 0:
        # Already had this event — just refresh last_event tracker
        res = await db.mailing_sends.update_one({"provider_id": email_id}, {"$set": set_part})
    if res.matched_count == 0:
        # Try automation log table
        r2 = await db.mailing_automation_log.update_one(base_filter, update_first)
        if r2.matched_count == 0:
            await db.mailing_automation_log.update_one({"provider_id": email_id}, {"$set": set_part})

    logger.info("[mailing-webhook] %s email_id=%s", evt_type, email_id)
    return {"ok": True}


# ── Stats endpoint ─────────────────────────────────────────────────────
@router.get("/stats")
async def mailing_stats(current_user: User = Depends(get_current_user)) -> dict:
    """Aggregated open/click/delivery rates for this tenant (last 90 days)."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    db = _db()
    since = (datetime.now(UTC) - timedelta(days=90)).isoformat()
    base = {"tenant_id": current_user.tenant_id, "sent_at": {"$gte": since}}
    sent     = await db.mailing_sends.count_documents({**base, "status": "sent"})
    delivered= await db.mailing_sends.count_documents({**base, "delivered_at": {"$exists": True}})
    opened   = await db.mailing_sends.count_documents({**base, "opened_at":    {"$exists": True}})
    clicked  = await db.mailing_sends.count_documents({**base, "clicked_at":   {"$exists": True}})
    bounced  = await db.mailing_sends.count_documents({**base, "bounced_at":   {"$exists": True}})

    def _rate(n: int, d: int) -> float:
        return round((n / d) * 100, 1) if d else 0.0

    return {
        "window_days": 90,
        "sent": sent,
        "delivered": delivered,
        "opened": opened,
        "clicked": clicked,
        "bounced": bounced,
        "delivery_rate": _rate(delivered, sent),
        "open_rate":     _rate(opened, delivered or sent),
        "click_rate":    _rate(clicked, opened or delivered or sent),
        "bounce_rate":   _rate(bounced, sent),
        "provider": (os.environ.get("MAIL_PROVIDER") or "resend").lower(),
    }


# ── Templates ──────────────────────────────────────────────────────────
@router.get("/templates")
async def list_templates(current_user: User = Depends(get_current_user)) -> list[dict]:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    cursor = _db().mailing_templates.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("updated_at", -1).limit(200)
    return await cursor.to_list(200)


@router.post("/templates")
async def create_template(payload: TemplateIn, current_user: User = Depends(get_current_user)) -> dict:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        **payload.model_dump(),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await _db().mailing_templates.insert_one({**doc})
    doc.pop("_id", None)
    return doc


@router.put("/templates/{template_id}")
async def update_template(
    template_id: str,
    payload: TemplateIn,
    current_user: User = Depends(get_current_user),
) -> dict:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    res = await _db().mailing_templates.find_one_and_update(
        {"id": template_id, "tenant_id": current_user.tenant_id},
        {"$set": {**payload.model_dump(), "updated_at": _now_iso()}},
        return_document=True,
        projection={"_id": 0},
    )
    if not res:
        raise HTTPException(status_code=404, detail="Şablon bulunamadı")
    return res


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str, current_user: User = Depends(get_current_user)) -> dict:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    res = await _db().mailing_templates.delete_one(
        {"id": template_id, "tenant_id": current_user.tenant_id}
    )
    if res.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Şablon bulunamadı")
    return {"success": True}


# ── Recipients (guests with email) ──────────────────────────────────────
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _extract_guest_email(g: dict) -> str | None:
    """Try to surface a usable email from a (possibly encrypted) guest doc."""
    raw = g.get("email")
    if isinstance(raw, str) and _EMAIL_RE.match(raw):
        return raw.strip().lower()
    try:
        dec = decrypt_user_doc({**g})
        e = dec.get("email")
        if isinstance(e, str) and _EMAIL_RE.match(e):
            return e.strip().lower()
    except Exception:
        return None
    return None


def _guest_display_name(g: dict) -> str:
    if g.get("name"):
        return str(g["name"])
    fn = g.get("first_name") or ""
    ln = g.get("last_name") or ""
    full = f"{fn} {ln}".strip()
    return full or "Misafir"


@router.get("/recipients")
async def list_recipients(
    search: str | None = None,
    current_user: User = Depends(get_current_user),
) -> list[dict]:
    """Return guests of this tenant who have a valid email."""
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    query: dict[str, Any] = {"tenant_id": current_user.tenant_id}
    if search:
        rgx = re.escape(search.strip())
        query["$or"] = [
            {"name": {"$regex": rgx, "$options": "i"}},
            {"first_name": {"$regex": rgx, "$options": "i"}},
            {"last_name": {"$regex": rgx, "$options": "i"}},
        ]
    cursor = _db().guests.find(query, {"_id": 0}).sort("created_at", -1).limit(RECIPIENT_FETCH_LIMIT)
    out: list[dict] = []
    async for g in cursor:
        email = _extract_guest_email(g)
        if not email:
            continue
        out.append({
            "id": g.get("id") or g.get("guest_id") or email,
            "name": _guest_display_name(g),
            "email": email,
        })
    return out


# ── Quick recipient filters (today's check-in/out, in-house) ────────────
@router.get("/recipients/quick/{filter_type}")
async def quick_recipients(
    filter_type: str,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Build a recipient list from current bookings using a simple filter:
    - in_house    : currently staying (check_in <= today < check_out)
    - today_in    : today's arrivals (check_in == today)
    - today_out   : today's departures (check_out == today)
    """
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    if filter_type not in {"in_house", "today_in", "today_out"}:
        raise HTTPException(status_code=400, detail="Geçersiz filtre")
    db = _db()
    today = datetime.now(UTC).date().isoformat()

    if filter_type == "today_in":
        bq = {"tenant_id": current_user.tenant_id,
              "check_in": {"$regex": f"^{today}"}}
    elif filter_type == "today_out":
        bq = {"tenant_id": current_user.tenant_id,
              "check_out": {"$regex": f"^{today}"}}
    else:  # in_house
        bq = {"tenant_id": current_user.tenant_id,
              "check_in": {"$lte": today + "T23:59:59"},
              "check_out": {"$gt": today}}

    bookings = await db.bookings.find(bq, {"_id": 0, "guest_id": 1, "guest_name": 1}).limit(RECIPIENT_FETCH_LIMIT).to_list(RECIPIENT_FETCH_LIMIT)
    guest_ids = list({b.get("guest_id") for b in bookings if b.get("guest_id")})
    if not guest_ids:
        return {"filter_type": filter_type, "count": 0, "recipients": []}

    guests = await db.guests.find(
        {"id": {"$in": guest_ids}, "tenant_id": current_user.tenant_id}, {"_id": 0}
    ).to_list(len(guest_ids))
    by_id = {g["id"]: g for g in guests if g.get("id")}

    out: list[dict] = []
    seen: set[str] = set()
    for b in bookings:
        gid = b.get("guest_id")
        if not gid or gid in seen:
            continue
        g = by_id.get(gid)
        if not g:
            continue
        email = _extract_guest_email(g)
        if not email:
            continue
        seen.add(gid)
        out.append({
            "id": gid,
            "name": _guest_display_name(g) or b.get("guest_name") or "Misafir",
            "email": email,
        })
    return {"filter_type": filter_type, "count": len(out), "recipients": out}


# ── Automations ────────────────────────────────────────────────────────
@router.get("/automations")
async def list_automations(current_user: User = Depends(get_current_user)) -> dict:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    db = _db()
    docs = await db.mailing_automations.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).to_list(50)
    by_type = {d["trigger_type"]: d for d in docs}
    out = []
    for trig, meta in AUTOMATION_TRIGGERS.items():
        existing = by_type.get(trig, {})
        out.append({
            "trigger_type": trig,
            "label": meta["label"],
            "description": meta["description"],
            "default_offset_days": meta["default_offset_days"],
            "enabled": bool(existing.get("enabled", False)),
            "template_id": existing.get("template_id"),
            "offset_days": existing.get("offset_days", meta["default_offset_days"]),
            "last_run_at": existing.get("last_run_at"),
            "last_sent_count": existing.get("last_sent_count", 0),
        })
    return {"automations": out}


@router.put("/automations/{trigger_type}")
async def update_automation(
    trigger_type: str,
    payload: AutomationConfig,
    current_user: User = Depends(get_current_user),
) -> dict:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    if trigger_type not in AUTOMATION_TRIGGERS:
        raise HTTPException(status_code=400, detail="Bilinmeyen tetikleyici")
    db = _db()
    if payload.enabled and not payload.template_id:
        raise HTTPException(status_code=400, detail="Aktif etmek için bir şablon seçin")
    if payload.template_id:
        tpl = await db.mailing_templates.find_one(
            {"id": payload.template_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
        )
        if not tpl:
            raise HTTPException(status_code=404, detail="Şablon bulunamadı")
    update = {
        "tenant_id": current_user.tenant_id,
        "trigger_type": trigger_type,
        "enabled": payload.enabled,
        "template_id": payload.template_id,
        "offset_days": payload.offset_days if payload.offset_days is not None
        else AUTOMATION_TRIGGERS[trigger_type]["default_offset_days"],
        "updated_at": _now_iso(),
    }
    await db.mailing_automations.update_one(
        {"tenant_id": current_user.tenant_id, "trigger_type": trigger_type},
        {"$set": update}, upsert=True,
    )
    return {"success": True, **update}


# ── Campaigns ──────────────────────────────────────────────────────────
@router.get("/campaigns")
async def list_campaigns(current_user: User = Depends(get_current_user)) -> list[dict]:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    cursor = _db().mailing_campaigns.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("created_at", -1).limit(200)
    return await cursor.to_list(200)


def _resolve_campaign_content(payload: CampaignCreate, template: dict | None) -> tuple[str, str]:
    subject = (payload.subject or (template or {}).get("subject") or "").strip()
    html = (payload.html or (template or {}).get("html") or "").strip()
    if not subject or not html:
        raise HTTPException(status_code=400, detail="Konu ve içerik zorunlu")
    return subject, html


def _personalize(html: str, subject: str, recipient_name: str, hotel_name: str) -> tuple[str, str]:
    repl = {
        "{{name}}": recipient_name,
        "{{hotel}}": hotel_name,
        "{{misafir}}": recipient_name,
        "{{otel}}": hotel_name,
    }
    for k, v in repl.items():
        html = html.replace(k, v)
        subject = subject.replace(k, v)
    return subject, html


@router.post("/campaigns")
async def create_and_send_campaign(
    payload: CampaignCreate,
    current_user: User = Depends(get_current_user),
) -> dict:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    db = _db()
    tenant = await db.tenants.find_one({"id": current_user.tenant_id}, {"_id": 0})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant bulunamadı")

    template = None
    if payload.template_id:
        template = await db.mailing_templates.find_one(
            {"id": payload.template_id, "tenant_id": current_user.tenant_id}, {"_id": 0}
        )
        if not template:
            raise HTTPException(status_code=404, detail="Şablon bulunamadı")
    subject, html = _resolve_campaign_content(payload, template)

    # ── Build recipient list ────────────────────────────────────────
    recipients: list[dict] = []
    if payload.test_email:
        if not _EMAIL_RE.match(payload.test_email):
            raise HTTPException(status_code=400, detail="Geçersiz test e-posta")
        recipients = [{"id": "test", "name": "Test", "email": payload.test_email.lower()}]
    else:
        if not payload.recipient_ids:
            raise HTTPException(status_code=400, detail="En az 1 alıcı seçin")
        all_recipients = await list_recipients(current_user=current_user)
        wanted = set(payload.recipient_ids)
        recipients = [r for r in all_recipients if r["id"] in wanted]
        if not recipients:
            raise HTTPException(status_code=400, detail="Seçili alıcılar bulunamadı veya e-postaları yok")

    if len(recipients) > SEND_BATCH_LIMIT:
        raise HTTPException(status_code=400, detail=f"Tek seferde en fazla {SEND_BATCH_LIMIT} alıcı")

    # ── Reserve credits up-front ────────────────────────────────────
    await _consume_credits(current_user.tenant_id, len(recipients))

    # ── Persist campaign as queued ──────────────────────────────────
    campaign_id = str(uuid.uuid4())
    hotel_name = tenant.get("property_name") or tenant.get("name") or "Otel"
    reply_to = tenant.get("email") or None
    campaign_doc = {
        "id": campaign_id,
        "tenant_id": current_user.tenant_id,
        "name": payload.name,
        "subject": subject,
        "template_id": payload.template_id,
        "recipient_count": len(recipients),
        "status": "sending",
        "sent_count": 0,
        "failed_count": 0,
        "created_by": current_user.id,
        "created_at": _now_iso(),
        "is_test": bool(payload.test_email),
    }
    await db.mailing_campaigns.insert_one({**campaign_doc})

    # ── Send synchronously (Phase 1: small batches only) ────────────
    sent = 0
    failed = 0
    for r in recipients:
        psubj, phtml = _personalize(html, subject, r["name"], hotel_name)
        result = await send_email(
            to=r["email"], subject=psubj, html=phtml, reply_to=reply_to
        )
        ok = bool(result.get("sent"))
        if ok:
            sent += 1
        else:
            failed += 1
        await db.mailing_sends.insert_one({
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "campaign_id": campaign_id,
            "recipient_email": r["email"],
            "recipient_id": r["id"],
            "status": "sent" if ok else "failed",
            "provider_id": result.get("id"),
            "error": result.get("error"),
            "sent_at": _now_iso(),
        })

    # ── Refund failed sends ─────────────────────────────────────────
    if failed:
        await db.mailing_credits.update_one(
            {"tenant_id": current_user.tenant_id},
            {"$inc": {"balance": failed, "lifetime_used": -failed}, "$set": {"updated_at": _now_iso()}},
        )

    await db.mailing_campaigns.update_one(
        {"id": campaign_id},
        {"$set": {
            "status": "completed",
            "sent_count": sent,
            "failed_count": failed,
            "completed_at": _now_iso(),
        }},
    )

    return {
        "campaign_id": campaign_id,
        "recipient_count": len(recipients),
        "sent_count": sent,
        "failed_count": failed,
    }
