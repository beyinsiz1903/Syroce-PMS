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

from core.database import db
from core.helpers import create_audit_log
from core.security import get_current_user
from models.schemas import (
    User,
)
from modules.pms_core.role_permission_service import require_op  # v98 DW
from shared_kernel.idempotency import (
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
    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": current_user.tenant_id}, {"_id": 0})

    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    guest = await db.guests.find_one({"id": booking.get("guest_id"), "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bilgisi bulunamadi")

    room = await db.rooms.find_one({"id": booking.get("room_id"), "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not room:
        raise HTTPException(status_code=404, detail="Oda bilgisi bulunamadi")

    check_in = booking["check_in"]
    check_out = booking["check_out"]
    offers = []

    rooms = await db.rooms.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(1000)
    better_rooms = [r for r in rooms if r.get("base_price", 0) > room.get("base_price", 0)]

    loyalty_tier = guest.get("loyalty_tier", "standard")
    past_bookings = await db.bookings.count_documents({"guest_id": booking["guest_id"], "tenant_id": current_user.tenant_id, "status": "checked_out"})

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
                    "guest_id": booking["guest_id"],
                    "booking_id": booking_id,
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
                "guest_id": booking["guest_id"],
                "booking_id": booking_id,
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
            "guest_id": booking["guest_id"],
            "booking_id": booking_id,
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
            "guest_id": booking["guest_id"],
            "booking_id": booking_id,
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
        await db.upsell_offers.insert_many(offers)
        for o in offers:
            o.pop("_id", None)

    estimated_revenue = sum(o["price"] * o["confidence"] for o in offers)

    return {"booking_id": booking_id, "guest_name": guest.get("name", "Bilinmiyor"), "offers": offers, "total_offers": len(offers), "estimated_revenue": round(estimated_revenue, 2)}


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

    # Optional Idempotency-Key replay protection.
    idem_key = get_idempotency_key(request)
    lock_id = None
    if idem_key:
        claim = await claim_idempotency(
            db,
            tenant_id=current_user.tenant_id,
            scope="upsell_offer_create",
            idempotency_key=idem_key,
        )
        if claim["status"] == "replay":
            return claim["response"]
        if claim["status"] == "in_flight":
            raise HTTPException(
                status_code=409,
                detail="Ayni Idempotency-Key ile baska bir istek isleniyor",
            )
        lock_id = claim["lock_id"]

    try:
        valid_until = payload.get("valid_until") or booking.get("check_out")
        offer_doc = {
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "guest_id": booking.get("guest_id"),
            "booking_id": booking_id,
            "type": offer_type,
            "current_item": payload.get("current_item"),
            "target_item": payload.get("target_item"),
            "price": round(price, 2),
            "confidence": 1.0,  # manual = full confidence
            "reason": payload.get("reason") or "Manuel teklif",
            "valid_until": valid_until,
            "status": "pending",
            "created_at": datetime.now(UTC).isoformat(),
            "created_by": getattr(current_user, "id", None),
            "source": "manual",
        }
        await db.upsell_offers.insert_one(offer_doc.copy())
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
    total_revenue = sum(o.get("price", 0) for o in offers if o.get("status") == "accepted")
    return {"offers": offers, "summary": {"total": len(offers), "accepted": accepted, "rejected": rejected, "pending": pending, "total_revenue": round(total_revenue, 2)}}


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

    offer = await db.upsell_offers.find_one({"id": offer_id, "tenant_id": current_user.tenant_id})
    if not offer:
        raise HTTPException(status_code=404, detail="Teklif bulunamadi")

    if offer.get("status") != "pending":
        raise HTTPException(status_code=409, detail="Bu teklif zaten islem gormus")

    update_data = {"status": action, "updated_at": datetime.now(UTC).isoformat(), "updated_by": current_user.email}

    if action == "accepted":
        existing_charge = await db.folio_charges.find_one({"upsell_offer_id": offer_id, "tenant_id": current_user.tenant_id})
        if not existing_charge:
            folio_charge = {
                "id": str(uuid.uuid4()),
                "upsell_offer_id": offer_id,
                "booking_id": offer["booking_id"],
                "tenant_id": current_user.tenant_id,
                "description": f"Upsell: {offer.get('target_item', offer.get('type', 'Ek Hizmet'))}",
                "amount": offer.get("price", 0),
                "charge_type": "upsell",
                "status": "posted",
                "created_at": datetime.now(UTC).isoformat(),
                "created_by": current_user.email,
            }
            await db.folio_charges.insert_one(folio_charge)

    await db.upsell_offers.update_one({"id": offer_id}, {"$set": update_data})
    return {"message": f"Teklif {'kabul edildi' if action == 'accepted' else 'reddedildi'}", "offer_id": offer_id, "status": action}


# ── GET /ai/upsell/revenue-insights ──
@router.get("/ai/upsell/revenue-insights")
async def get_revenue_insights(current_user: User = Depends(get_current_user)):
    tenant_id = current_user.tenant_id
    now = datetime.now(UTC)
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = today.replace(day=1)

    total_rooms = await db.rooms.count_documents({"tenant_id": tenant_id})
    today_occupied = await db.bookings.count_documents(
        {"tenant_id": tenant_id, "status": {"$in": ["checked_in", "confirmed", "guaranteed"]}, "check_in": {"$lte": today.isoformat()}, "check_out": {"$gt": today.isoformat()}}
    )
    occupancy_rate = round((today_occupied / total_rooms * 100) if total_rooms > 0 else 0, 1)

    monthly_bookings = await db.bookings.find(
        {"tenant_id": tenant_id, "check_in": {"$gte": month_start.isoformat()}, "status": {"$nin": ["cancelled", "no_show"]}}, {"total_amount": 1, "check_in": 1, "check_out": 1, "_id": 0}
    ).to_list(5000)

    total_revenue = sum(b.get("total_amount", 0) for b in monthly_bookings)
    total_nights = 0
    for b in monthly_bookings:
        try:
            ci = datetime.fromisoformat(b["check_in"])
            co = datetime.fromisoformat(b["check_out"])
            total_nights += max((co - ci).days, 1)
        except Exception:
            total_nights += 1
    adr = round(total_revenue / total_nights, 2) if total_nights > 0 else 0
    revpar = round(adr * occupancy_rate / 100, 2)

    upsell_stats = await db.upsell_offers.find({"tenant_id": tenant_id, "created_at": {"$gte": month_start.isoformat()}}, {"_id": 0, "status": 1, "price": 1, "type": 1}).to_list(5000)
    upsell_total = len(upsell_stats)
    upsell_accepted = sum(1 for u in upsell_stats if u.get("status") == "accepted")
    upsell_revenue = sum(u.get("price", 0) for u in upsell_stats if u.get("status") == "accepted")
    acceptance_rate = round((upsell_accepted / upsell_total * 100) if upsell_total > 0 else 0, 1)

    type_breakdown = {}
    for u in upsell_stats:
        t = u.get("type", "diger")
        if t not in type_breakdown:
            type_breakdown[t] = {"total": 0, "accepted": 0, "revenue": 0}
        type_breakdown[t]["total"] += 1
        if u.get("status") == "accepted":
            type_breakdown[t]["accepted"] += 1
            type_breakdown[t]["revenue"] += u.get("price", 0)

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
                "text": f"Bu ay {upsell_total} teklif uretildi, %{acceptance_rate} kabul orani ile {upsell_revenue:.0f} TL ek gelir saglandi.",
                "metric": f"%{acceptance_rate}",
            }
        )

    best_type = max(type_breakdown.items(), key=lambda x: x[1]["revenue"], default=None)
    if best_type and best_type[1]["revenue"] > 0:
        type_labels = {"room_upgrade": "Oda Yukseltme", "early_checkin": "Erken Check-in", "late_checkout": "Gec Check-out", "airport_transfer": "Transfer"}
        insights.append(
            {
                "type": "success",
                "title": "En Iyi Upsell Kategorisi",
                "text": f"{type_labels.get(best_type[0], best_type[0])} kategorisi {best_type[1]['revenue']:.0f} TL ile en cok gelir getiren upsell tipi.",
                "metric": f"{best_type[1]['revenue']:.0f} TL",
            }
        )

    if adr > 0:
        insights.append({"type": "info", "title": "Ortalama Gunluk Fiyat (ADR)", "text": f"Bu ayin ADR degeri {adr:.0f} TL, RevPAR {revpar:.0f} TL.", "metric": f"{adr:.0f} TL"})

    return {
        "kpis": {"occupancy_rate": occupancy_rate, "adr": adr, "revpar": revpar, "monthly_revenue": round(total_revenue, 2), "total_rooms": total_rooms, "occupied_rooms": today_occupied},
        "upsell_summary": {"total": upsell_total, "accepted": upsell_accepted, "revenue": round(upsell_revenue, 2), "acceptance_rate": acceptance_rate, "type_breakdown": type_breakdown},
        "insights": insights,
    }
