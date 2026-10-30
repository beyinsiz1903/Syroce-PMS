"""
upsell

Auto-split sub-router (shared imports/classes inlined).
"""

"""
Domain Router: Guest Experience

Guest CRM, upsell AI, messaging, feedback/reviews, guest mobile app.
"""
import logging
import math
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pymongo.errors import DuplicateKeyError

from core.database import db
from core.helpers import create_audit_log
from core.security import get_current_user
from core.tenant_currency import get_tenant_currency
from models.schemas import (
    User,
)
from modules.pms_core.role_permission_service import require_op  # v98 DW
from shared_kernel.idempotency import (
    build_request_hash,
    claim_idempotency,
    complete_idempotency,
    get_idempotency_key,
    release_idempotency,
)

DEFAULT_UPSELL_PRICES = {
    "early_checkin": 25.00,
    "late_checkout": 35.00,
    "airport_transfer": 50.00,
}


async def _get_upsell_prices(tenant_id: str) -> dict:
    """Return per-tenant upsell prices, falling back to defaults for any missing key."""
    prices = dict(DEFAULT_UPSELL_PRICES)
    doc = await db.upsell_settings.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if doc and isinstance(doc.get("prices"), dict):
        for k, v in doc["prices"].items():
            if k in prices:
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                if fv >= 0:
                    prices[k] = fv
    return prices


# ============= PHASE H: GUEST CRM + UPSELL AI + MESSAGING =============


_MANUAL_UPSELL_TYPES = {
    "early_checkin",
    "late_checkout",
    "airport_transfer",
    "room_upgrade",
    "spa_package",
    "dining_credit",
    "champagne",
    "custom",
}


async def check_rate_limit(tenant_id: str, channel: str, limit_per_hour: int = 100) -> bool:
    """Check if rate limit is exceeded for messaging"""
    one_hour_ago = (datetime.now(UTC) - timedelta(hours=1)).isoformat()

    count = await db.messages.count_documents({"tenant_id": tenant_id, "channel": channel, "sent_at": {"$gte": one_hour_ago}})

    return count < limit_per_hour


async def _posted_upsell_totals(tenant_id, offers):
    """Read posted source-linked gross amounts; never add currencies or old guesses."""
    from decimal import Decimal, InvalidOperation

    missing_ids = sum(1 for offer in offers if offer.get("status") == "accepted" and not offer.get("id"))
    accepted = {offer["id"]: offer for offer in offers if offer.get("status") == "accepted" and offer.get("id")}
    ids = [offer["folio_charge_id"] for offer in accepted.values() if offer.get("folio_charge_id")]
    charges = await db.folio_charges.find({"tenant_id": tenant_id, "id": {"$in": ids}, "voided": {"$ne": True}}, {"_id": 0}).to_list(len(ids)) if ids else []
    groups, verified = {}, set()
    for charge in charges:
        source_id = charge.get("source_upsell_offer_id")
        offer = accepted.get(source_id)
        code = charge.get("currency")
        if not offer or charge.get("id") != offer.get("folio_charge_id") or charge.get("booking_id") != offer.get("booking_id") or not isinstance(code, str) or len(code) != 3 or source_id in verified:
            continue
        try:
            amount = Decimal(str(charge.get("total")))
            if not amount.is_finite() or amount < 0:
                continue
        except InvalidOperation:
            continue
        groups[code] = groups.get(code, Decimal(0)) + amount
        verified.add(source_id)
    values = {code: float(total) for code, total in sorted(groups.items())}
    return {
        "revenue_by_currency": values,
        "revenue": next(iter(values.values())) if len(values) == 1 else None,
        "revenue_currency": next(iter(values)) if len(values) == 1 else None,
        "unreconciled_accepted": len(accepted) - len(verified) + missing_ids,
        "revenue_source": "folio_charges",
    }


# Router will be included at the very end after ALL endpoints are defined

logger = logging.getLogger(__name__)


# ========================================

# 1. EXTERNAL REVIEW API INTEGRATION (Booking.com, Google, TripAdvisor)


# 2. IN-HOUSE SURVEY SYSTEM


# 3. DEPARTMENT-BASED SATISFACTION TRACKING


# ============= GUEST MOBILE APP ENDPOINTS =============

# rbac-allow: cache-rbac — GUEST portal — kendi rezervasyonları


router = APIRouter(prefix="/api", tags=["guest-experience"])


# ── POST /ai/upsell/generate ──
@router.post("/ai/upsell/generate")
async def generate_upsell_offers(
    booking_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    # Calendar/list payloads can temporarily retain a superseded internal id
    # after OTA reconciliation. Accept tenant-scoped canonical and stable
    # external references so the same reservation remains selectable.
    booking = await db.bookings.find_one(
        {
            "tenant_id": current_user.tenant_id,
            "$or": [
                {"id": booking_id},
                {"booking_id": booking_id},
                {"reservation_id": booking_id},
                {"booking_number": booking_id},
                {"channel_booking_id": booking_id},
                {"external_id": booking_id},
                {"external_reservation_id": booking_id},
            ],
        },
        {"_id": 0},
    )

    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    canonical_booking_id = booking.get("id") or booking_id
    guest_id = booking.get("guest_id")

    guest = None
    if guest_id:
        guest = await db.guests.find_one(
            {"id": guest_id, "tenant_id": current_user.tenant_id},
            {"_id": 0},
        )
    guest = guest or {
        "name": booking.get("guest_name") or "Misafir",
        "loyalty_tier": booking.get("loyalty_tier") or "standard",
    }

    room = None
    if booking.get("room_id"):
        room = await db.rooms.find_one(
            {"id": booking["room_id"], "tenant_id": current_user.tenant_id},
            {"_id": 0},
        )

    check_in = booking["check_in"]
    check_out = booking["check_out"]
    offers = []

    rooms = await db.rooms.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(1000)
    # An unassigned reservation can still receive generic service offers.
    # Only a room upgrade requires a valid current room.
    better_rooms = [r for r in rooms if r.get("base_price", 0) > room.get("base_price", 0)] if room else []

    loyalty_tier = guest.get("loyalty_tier", "standard")
    past_bookings = 0
    if guest_id:
        past_bookings = await db.bookings.count_documents({"guest_id": guest_id, "tenant_id": current_user.tenant_id, "status": "checked_out"})

    for better_room in better_rooms[:3]:
        conflicts = await db.bookings.count_documents(
            {
                "tenant_id": current_user.tenant_id,
                "room_id": better_room["id"],
                "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
                "check_in": {"$lt": check_out},
                "check_out": {"$gt": check_in},
            }
        )

        if conflicts == 0:
            confidence = 0.5
            if loyalty_tier == "vip":
                confidence = 0.9
            elif loyalty_tier == "gold":
                confidence = 0.75
            elif loyalty_tier == "silver":
                confidence = 0.6
            if past_bookings > 5:
                confidence += 0.1
            confidence = min(0.95, confidence)

            price_diff = better_room.get("base_price", 0) - room.get("base_price", 0)
            nights = max((datetime.fromisoformat(check_out) - datetime.fromisoformat(check_in)).days, 1)
            total_upgrade_cost = price_diff * nights

            offers.append(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": current_user.tenant_id,
                    "guest_id": guest_id,
                    "booking_id": canonical_booking_id,
                    "type": "room_upgrade",
                    "current_item": room.get("room_type", ""),
                    "target_item": better_room.get("room_type", ""),
                    "price": round(total_upgrade_cost, 2),
                    "confidence": round(confidence, 2),
                    "reason": f"{loyalty_tier.upper()} misafir, {better_room.get('room_type', '')} musait",
                    "valid_until": (datetime.now(UTC) + timedelta(days=3)).isoformat(),
                    "status": "pending",
                    "created_at": datetime.now(UTC).isoformat(),
                }
            )

    arrival_date = datetime.fromisoformat(check_in).date()
    today = datetime.now(UTC).date()

    tenant_prices = await _get_upsell_prices(current_user.tenant_id)

    if arrival_date > today:
        offers.append(
            {
                "id": str(uuid.uuid4()),
                "tenant_id": current_user.tenant_id,
                "guest_id": guest_id,
                "booking_id": canonical_booking_id,
                "type": "early_checkin",
                "current_item": "Standart 15:00 giris",
                "target_item": "Erken 12:00 giris",
                "price": tenant_prices["early_checkin"],
                "confidence": 0.65,
                "reason": "Yuksek degerli hizmet, dusuk maliyet",
                "valid_until": (datetime.fromisoformat(check_in) - timedelta(days=1)).isoformat(),
                "status": "pending",
                "created_at": datetime.now(UTC).isoformat(),
            }
        )

    offers.append(
        {
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "guest_id": guest_id,
            "booking_id": canonical_booking_id,
            "type": "late_checkout",
            "current_item": "Standart 11:00 cikis",
            "target_item": "Gec 14:00 cikis",
            "price": tenant_prices["late_checkout"],
            "confidence": 0.70,
            "reason": "Populer ek hizmet, yuksek memnuniyet",
            "valid_until": (datetime.fromisoformat(check_out) - timedelta(days=1)).isoformat(),
            "status": "pending",
            "created_at": datetime.now(UTC).isoformat(),
        }
    )

    offers.append(
        {
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "guest_id": guest_id,
            "booking_id": canonical_booking_id,
            "type": "airport_transfer",
            "current_item": None,
            "target_item": "Premium havaalani transferi",
            "price": tenant_prices["airport_transfer"],
            "confidence": 0.55,
            "reason": "Konfor hizmeti, iyi marj",
            "valid_until": (datetime.fromisoformat(check_in) - timedelta(days=1)).isoformat(),
            "status": "pending",
            "created_at": datetime.now(UTC).isoformat(),
        }
    )

    offers.sort(key=lambda x: x["confidence"], reverse=True)

    if offers:
        offer_currency, _ = await get_tenant_currency(current_user.tenant_id)
        for offer in offers:
            offer["currency"] = offer_currency
        await db.upsell_offers.insert_many(offers)
        for o in offers:
            o.pop("_id", None)

    estimated_revenue = sum(o["price"] * o["confidence"] for o in offers)

    return {"booking_id": canonical_booking_id, "guest_name": guest.get("name", "Bilinmiyor"), "offers": offers, "total_offers": len(offers), "estimated_revenue": round(estimated_revenue, 2)}


# ── POST /ai/upsell/offers ──
@router.post("/ai/upsell/offers")
async def create_upsell_offer(
    payload: dict,
    request: Request,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    """Manually create a single upsell offer (alternative to AI bulk generate).

    Body fields:
      - booking_id (required): owning reservation, must belong to caller tenant.
      - type (required): one of _MANUAL_UPSELL_TYPES, or 'custom' for ad-hoc.
      - price (required): non-negative number.
      - target_item (optional): human label of what's being offered.
      - reason (optional): note shown to guest.
      - valid_until (optional ISO string): expiry; defaults to booking checkout.

    Idempotency-Key header is honored: re-sending the same key returns the
    originally-created offer instead of creating a duplicate row.
    """
    booking_id = payload.get("booking_id")
    offer_type = payload.get("type")
    price_raw = payload.get("price")

    if not booking_id or not isinstance(booking_id, str):
        raise HTTPException(status_code=422, detail="booking_id zorunlu")
    if offer_type not in _MANUAL_UPSELL_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Gecersiz type. Izinli={sorted(_MANUAL_UPSELL_TYPES)}",
        )
    if isinstance(price_raw, bool):
        raise HTTPException(status_code=422, detail="price sayi olmali")
    try:
        price = float(price_raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="price sayi olmali")
    if not math.isfinite(price) or price < 0 or price > 1_000_000:
        raise HTTPException(status_code=422, detail="price gecersiz")

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    from datetime import date, time

    from core.guest_service_folio import inclusive_tax
    from modules.pms_core.folio_selection import select_booking_folio
    from modules.pms_core.revenue_categories import LABELS

    offer_currency, _ = await get_tenant_currency(current_user.tenant_id)
    currency = str(payload.get("currency") or offer_currency).strip().upper()
    if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
        raise HTTPException(422, "Teklif para birimi açık üç harfli ISO kodu olmalı")
    category = payload.get("service_category")
    if category is not None and category not in LABELS:
        raise HTTPException(422, "Geçersiz hizmet kategorisi")
    tax_rate = payload.get("tax_rate")
    inclusive_tax(round(price, 2), tax_rate)
    service_date, service_time = payload.get("service_date"), payload.get("service_time")
    try:
        if service_date:
            date.fromisoformat(service_date)
        if service_time:
            time.fromisoformat(service_time)
    except (TypeError, ValueError):
        raise HTTPException(422, "Hizmet tarih/saat biçimi geçersiz") from None
    if payload.get("folio_id"):
        await select_booking_folio(db, current_user.tenant_id, booking_id, payload["folio_id"])

    # Optional Idempotency-Key replay protection.
    idem_key = get_idempotency_key(request)
    lock_id = None
    source_hash = build_request_hash(payload)
    offer_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"syroce:upsell:{current_user.tenant_id}:{idem_key}")) if idem_key else str(uuid.uuid4())

    async def persisted_offer():
        row = await db.upsell_offers.find_one({"tenant_id": current_user.tenant_id, "id": offer_id}, {"_id": 0})
        if row and row.get("request_hash") != source_hash:
            raise HTTPException(409, "Aynı istek anahtarı farklı teklif içeriğiyle kullanılamaz")
        return row

    if idem_key:
        existing = await persisted_offer()
        if existing:
            return existing
        claim = await claim_idempotency(
            db,
            tenant_id=current_user.tenant_id,
            scope="upsell_offer_create",
            idempotency_key=idem_key,
            request_hash=source_hash,
        )
        if claim["status"] == "replay":
            existing = await persisted_offer()
            if existing:
                return existing
            raise HTTPException(409, "Önceki teklifin kalıcı kaydı doğrulanamadı")
        if claim["status"] == "mismatch":
            raise HTTPException(409, "Aynı istek anahtarı farklı teklif içeriğiyle kullanılamaz")
        if claim["status"] == "in_flight":
            raise HTTPException(
                status_code=409,
                detail="Ayni Idempotency-Key ile baska bir istek isleniyor",
            )
        lock_id = claim["lock_id"]

    try:
        valid_until = payload.get("valid_until") or booking.get("check_out")
        offer_doc = {
            "_id": f"upsell-offer:{current_user.tenant_id}:{offer_id}",
            "id": offer_id,
            "request_hash": source_hash,
            "tenant_id": current_user.tenant_id,
            "guest_id": booking.get("guest_id"),
            "booking_id": booking_id,
            "type": offer_type,
            "current_item": payload.get("current_item"),
            "target_item": payload.get("target_item"),
            "price": round(price, 2),
            "currency": currency,
            "folio_id": payload.get("folio_id"),
            "tax_rate": tax_rate,
            "service_category": category,
            "service_date": service_date,
            "service_time": service_time,
            "confidence": 1.0,  # manual = full confidence
            "reason": payload.get("reason") or "Manuel teklif",
            "valid_until": valid_until,
            "status": "pending",
            "created_at": datetime.now(UTC).isoformat(),
            "created_by": getattr(current_user, "id", None),
            "source": "manual",
        }
        try:
            await db.upsell_offers.insert_one(offer_doc.copy())
        except DuplicateKeyError:
            existing = await persisted_offer()
            if existing:
                return existing
            raise
        offer_doc.pop("_id", None)
        if lock_id:
            await complete_idempotency(db, lock_id=lock_id, response_body=offer_doc)
        return offer_doc
    except Exception as exc:
        if lock_id:
            await release_idempotency(db, lock_id=lock_id, error=str(exc))
        raise


# ── GET /ai/upsell/offers ──
@router.get("/ai/upsell/offers")
async def list_upsell_offers(status: str | None = None, current_user: User = Depends(get_current_user)):
    query = {"tenant_id": current_user.tenant_id}
    if status:
        query["status"] = status
    offers = await db.upsell_offers.find(query, {"_id": 0}).sort("created_at", -1).to_list(200)
    accepted = sum(1 for o in offers if o.get("status") == "accepted")
    rejected = sum(1 for o in offers if o.get("status") == "rejected")
    pending = sum(1 for o in offers if o.get("status") == "pending")
    posted = await _posted_upsell_totals(current_user.tenant_id, offers)
    return {
        "offers": offers,
        "summary": {
            "total": len(offers),
            "accepted": accepted,
            "rejected": rejected,
            "pending": pending,
            "total_revenue": posted["revenue"],
            "scope": "latest_200_offers",
            "limit_reached": len(offers) == 200,
            **posted,
        },
    }


# ── GET /ai/upsell/settings ──
@router.get("/ai/upsell/settings")
async def get_upsell_settings(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    """Return current per-tenant upsell prices alongside the system defaults."""
    prices = await _get_upsell_prices(current_user.tenant_id)
    return {
        "prices": prices,
        "defaults": dict(DEFAULT_UPSELL_PRICES),
    }


# ── PUT /ai/upsell/settings ──
@router.put("/ai/upsell/settings")
async def update_upsell_settings(
    payload: dict,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    """Update per-tenant upsell prices. Body: {"prices": {"early_checkin": 30, ...}}.

    Validation:
      - 'prices' must be a dict.
      - Only the keys in DEFAULT_UPSELL_PRICES are accepted; any other key returns 400.
      - Values must be finite numbers (no NaN/Inf), >= 0 and <= 1_000_000.
      - At least one valid price must be supplied.

    Concurrency: each provided price is written with a per-field $set
    (e.g. {"prices.early_checkin": 30}), so concurrent partial updates do
    not overwrite each other.
    """
    incoming = payload.get("prices") if isinstance(payload, dict) else None
    if not isinstance(incoming, dict):
        raise HTTPException(status_code=400, detail="'prices' alani sozluk olmali")

    allowed_keys = set(DEFAULT_UPSELL_PRICES.keys())
    unknown_keys = sorted(set(incoming.keys()) - allowed_keys)
    if unknown_keys:
        raise HTTPException(
            status_code=400,
            detail=f"Bilinmeyen fiyat anahtari: {', '.join(unknown_keys)}",
        )

    sanitized: dict[str, float] = {}
    for key in DEFAULT_UPSELL_PRICES.keys():
        if key not in incoming:
            continue
        raw = incoming[key]
        # bool is a subclass of int in Python — explicitly reject it
        if isinstance(raw, bool):
            raise HTTPException(status_code=400, detail=f"{key} icin gecersiz fiyat")
        try:
            value = float(raw)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"{key} icin gecersiz fiyat")
        if not math.isfinite(value):
            raise HTTPException(status_code=400, detail=f"{key} icin gecersiz fiyat")
        if value < 0:
            raise HTTPException(status_code=400, detail=f"{key} fiyati negatif olamaz")
        if value > 1_000_000:
            raise HTTPException(status_code=400, detail=f"{key} fiyati cok yuksek")
        sanitized[key] = round(value, 2)

    if not sanitized:
        raise HTTPException(status_code=400, detail="Guncellenecek fiyat bulunamadi")

    now_iso = datetime.now(UTC).isoformat()
    update_doc: dict = {f"prices.{k}": v for k, v in sanitized.items()}
    update_doc["tenant_id"] = current_user.tenant_id
    update_doc["updated_at"] = now_iso
    update_doc["updated_by"] = getattr(current_user, "id", None)

    await db.upsell_settings.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$set": update_doc},
        upsert=True,
    )

    # Re-read post-write so the response and audit log reflect the actual stored state
    final_prices = await _get_upsell_prices(current_user.tenant_id)

    try:
        await create_audit_log(
            tenant_id=current_user.tenant_id,
            user=current_user,
            action="update_upsell_prices",
            entity_type="upsell_settings",
            entity_id=current_user.tenant_id,
            changes={"updated_fields": sanitized, "prices": final_prices},
        )
    except Exception as exc:  # audit failure must not block the save
        logging.warning("Audit log failed for upsell price update: %s", exc)

    return {
        "success": True,
        "prices": final_prices,
        "defaults": dict(DEFAULT_UPSELL_PRICES),
    }


# ── PUT /ai/upsell/offers/{offer_id} ──
@router.put("/ai/upsell/offers/{offer_id}")
async def update_upsell_offer(
    offer_id: str,
    action: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),  # v100 DW
):
    if action not in ("accepted", "rejected"):
        raise HTTPException(status_code=400, detail="Gecersiz aksiyon. 'accepted' veya 'rejected' olmali.")

    if action == "accepted":
        from core.guest_service_folio import accept_upsell
        from core.spa_mice_authz import require_finance

        require_finance(current_user)
        return await accept_upsell(db, current_user.tenant_id, offer_id, current_user.id)

    offer = await db.upsell_offers.find_one({"id": offer_id, "tenant_id": current_user.tenant_id})
    if not offer:
        raise HTTPException(status_code=404, detail="Teklif bulunamadi")

    if offer.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Bu teklif zaten islem gormus")

    update_data = {"status": action, "updated_at": datetime.now(UTC).isoformat(), "updated_by": current_user.email}

    changed = await db.upsell_offers.update_one({"id": offer_id, "tenant_id": current_user.tenant_id, "status": "pending"}, {"$set": update_data})
    if changed.matched_count != 1:
        raise HTTPException(409, "Teklif eşzamanlı değişti; sayfayı yenileyin")
    return {"message": f"Teklif {'kabul edildi' if action == 'accepted' else 'reddedildi'}", "offer_id": offer_id, "status": action}


# ── GET /ai/upsell/revenue-insights ──
@router.get("/ai/upsell/revenue-insights")
async def get_revenue_insights(current_user: User = Depends(get_current_user)):
    tenant_id = current_user.tenant_id
    now = datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today.replace(day=1)
    next_month = (month_start.replace(day=28) + timedelta(days=4)).replace(day=1)

    total_rooms = await db.rooms.count_documents({"tenant_id": tenant_id})
    today_occupied = await db.bookings.count_documents(
        {"tenant_id": tenant_id, "status": {"$in": ["checked_in", "confirmed", "guaranteed"]}, "check_in": {"$lte": today.isoformat()}, "check_out": {"$gt": today.isoformat()}}
    )
    occupancy_rate = round((today_occupied / total_rooms * 100) if total_rooms > 0 else 0, 1)

    monthly_bookings = await db.bookings.find(
        {"tenant_id": tenant_id, "check_in": {"$gte": month_start.date().isoformat(), "$lt": next_month.date().isoformat()}, "status": {"$nin": ["cancelled", "no_show"]}},
        {"total_amount": 1, "currency": 1, "check_in": 1, "check_out": 1, "_id": 0},
    ).to_list(5000)

    revenue_by_currency, nights_by_currency = {}, {}
    unknown_currency_count = 0
    for b in monthly_bookings:
        code = b.get("currency")
        if not code:
            unknown_currency_count += 1
            continue
        try:
            ci = datetime.fromisoformat(b["check_in"])
            co = datetime.fromisoformat(b["check_out"])
            revenue_by_currency[code] = revenue_by_currency.get(code, 0) + b.get("total_amount", 0)
            nights_by_currency[code] = nights_by_currency.get(code, 0) + max((co - ci).days, 1)
        except (ValueError, KeyError, TypeError):
            pass
    adr_by_currency = {code: round(total / nights_by_currency[code], 2) for code, total in revenue_by_currency.items()}
    revpar_by_currency = {code: round(value * occupancy_rate / 100, 2) for code, value in adr_by_currency.items()}
    adr = next(iter(adr_by_currency.values())) if len(adr_by_currency) == 1 else None
    revpar = next(iter(revpar_by_currency.values())) if len(revpar_by_currency) == 1 else None

    upsell_stats = await db.upsell_offers.find({"tenant_id": tenant_id, "created_at": {"$gte": month_start.isoformat()}}, {"_id": 0}).to_list(5000)
    upsell_total = len(upsell_stats)
    upsell_accepted = sum(1 for u in upsell_stats if u.get("status") == "accepted")
    posted = await _posted_upsell_totals(tenant_id, upsell_stats)
    acceptance_rate = round((upsell_accepted / upsell_total * 100) if upsell_total > 0 else 0, 1)

    type_breakdown = {}
    for u in upsell_stats:
        t = u.get("type", "diger")
        if t not in type_breakdown:
            type_breakdown[t] = {"total": 0, "accepted": 0}
        type_breakdown[t]["total"] += 1
        if u.get("status") == "accepted":
            type_breakdown[t]["accepted"] += 1
    for offer_type, stats in type_breakdown.items():
        stats.update(await _posted_upsell_totals(tenant_id, [u for u in upsell_stats if u.get("type", "diger") == offer_type]))

    insights = []
    if occupancy_rate < 60:
        insights.append(
            {
                "type": "warning",
                "title": "Dusuk Doluluk",
                "text": f"Guncel doluluk %{occupancy_rate}. Hafta ici kurumsal segment ve OTA kampanyalari ile dolulugu artirabilirsiniz.",
                "metric": f"%{occupancy_rate}",
            }
        )
    elif occupancy_rate > 85:
        insights.append(
            {"type": "success", "title": "Yuksek Doluluk", "text": f"Doluluk %{occupancy_rate} ile yuksek seviyede. ADR artisi icin fiyat optimizasyonu uygulayin.", "metric": f"%{occupancy_rate}"}
        )

    if acceptance_rate > 0:
        insights.append(
            {
                "type": "info",
                "title": "Upsell Performansi",
                "text": f"Bu ay {upsell_total} teklif üretildi; kabul oranı %{acceptance_rate}. Folyoya işlenen tutarlar para birimi bazında gösterilir; mutabakatı eksik eski teklifler gelire eklenmez.",
                "metric": f"%{acceptance_rate}",
            }
        )

    best_type = max(type_breakdown.items(), key=lambda x: x[1]["revenue"] or 0, default=None) if len(posted["revenue_by_currency"]) == 1 else None
    if best_type and (best_type[1]["revenue"] or 0) > 0:
        type_labels = {"room_upgrade": "Oda Yukseltme", "early_checkin": "Erken Check-in", "late_checkout": "Gec Check-out", "airport_transfer": "Transfer"}
        insights.append(
            {
                "type": "success",
                "title": "En Iyi Upsell Kategorisi",
                "text": f"{type_labels.get(best_type[0], best_type[0])}: {best_type[1]['revenue']:.2f} {best_type[1]['revenue_currency']} folyoya işlendi.",
                "metric": f"{best_type[1]['revenue']:.2f} {best_type[1]['revenue_currency']}",
            }
        )

    return {
        "kpis": {
            "occupancy_rate": occupancy_rate,
            "adr": adr,
            "revpar": revpar,
            "adr_by_currency": adr_by_currency,
            "revpar_by_currency": revpar_by_currency,
            "monthly_revenue_by_currency": revenue_by_currency,
            "monthly_revenue": next(iter(revenue_by_currency.values())) if len(revenue_by_currency) == 1 else None,
            "unknown_currency_count": unknown_currency_count,
            "limit_reached": len(monthly_bookings) == 5000,
            "total_rooms": total_rooms,
            "occupied_rooms": today_occupied,
        },
        "upsell_summary": {
            "total": upsell_total,
            "accepted": upsell_accepted,
            **posted,
            "acceptance_rate": acceptance_rate,
            "type_breakdown": type_breakdown,
            "limit_reached": len(upsell_stats) == 5000,
        },
        "insights": insights,
    }
