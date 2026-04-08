"""
Syroce B2B API — Acente Otomasyon Sistemi Entegrasyonu
======================================================
Acenteler API key ile bu endpoint'leri kullanarak:
  - Otel icerigi (oda tipi, hizmet) cekebilir
  - Musaitlik ve fiyat sorgulayabilir
  - Rezervasyon olusturup takip edebilir
  - Webhook ile bildirim alabilir

Admin (Hotel) Endpoints:
  POST   /api/b2b/api-keys                  - Acente icin API key olustur
  GET    /api/b2b/api-keys/{agency_id}      - Acente API key bilgisi
  DELETE /api/b2b/api-keys/{agency_id}      - API key sil/iptal et
  POST   /api/b2b/api-keys/{agency_id}/regenerate - API key yenile

B2B (Agency) Endpoints (API Key Auth):
  GET    /api/b2b/content                   - Otel icerigi
  GET    /api/b2b/availability              - Musaitlik sorgusu
  GET    /api/b2b/rates                     - Fiyat sorgusu
  POST   /api/b2b/reservations              - Rezervasyon olustur
  GET    /api/b2b/reservations              - Rezervasyon listesi
  GET    /api/b2b/reservations/{id}         - Rezervasyon detay
  PUT    /api/b2b/reservations/{id}/cancel  - Rezervasyon iptali

Webhook Endpoints (API Key Auth):
  POST   /api/b2b/webhooks                  - Webhook kaydet
  GET    /api/b2b/webhooks                  - Webhook listesi
  DELETE /api/b2b/webhooks/{webhook_id}     - Webhook sil
  POST   /api/b2b/webhooks/{webhook_id}/test - Webhook test
"""
import hashlib
import hmac
import logging
import secrets
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Header, Query
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user

logger = logging.getLogger(__name__)
from core.tenant_db import set_tenant_context
from models.schemas import User

router = APIRouter(prefix="/api/b2b", tags=["B2B API - Syroce"])


# ── Helpers ──────────────────────────────────────────────────────

def _now_iso():
    return datetime.now(UTC).isoformat()


def _uuid():
    return str(uuid.uuid4())


def _hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _require_hotel_staff(user: User):
    if user.role in ("agency_admin", "agency_agent"):
        raise HTTPException(status_code=403, detail="Acente kullanicilari bu islemi yapamaz")


# ── API Key Auth Dependency ──────────────────────────────────────

async def get_b2b_agency(x_api_key: str = Header(..., alias="X-API-Key")):
    """API key ile acente kimlik dogrulamasi."""
    from core.tenant_db import get_system_db
    sysdb = get_system_db()

    key_hash = _hash_api_key(x_api_key)
    key_doc = await sysdb.agency_api_keys.find_one(
        {"key_hash": key_hash, "is_active": True}, {"_id": 0}
    )
    if not key_doc:
        raise HTTPException(status_code=401, detail="Gecersiz veya devre disi API key")

    agency = await sysdb.agencies.find_one(
        {"id": key_doc["agency_id"], "status": "active"}, {"_id": 0}
    )
    if not agency:
        raise HTTPException(status_code=403, detail="Acente hesabi aktif degil")

    # Set tenant context for downstream DB queries
    set_tenant_context(key_doc["tenant_id"])

    # Update last_used
    await sysdb.agency_api_keys.update_one(
        {"key_hash": key_hash},
        {"$set": {"last_used_at": _now_iso()}, "$inc": {"usage_count": 1}},
    )

    return {
        "agency_id": key_doc["agency_id"],
        "tenant_id": key_doc["tenant_id"],
        "agency_name": agency.get("name", ""),
        "commission_rate": agency.get("commission_rate", 0),
    }


# ── Request Models ───────────────────────────────────────────────

class B2BReservationCreate(BaseModel):
    room_type: str
    check_in: str  # YYYY-MM-DD
    check_out: str  # YYYY-MM-DD
    guest_name: str
    guest_email: str = ""
    guest_phone: str = ""
    adults: int = 2
    children: int = 0
    special_requests: str = ""
    total_amount: float = 0


class WebhookRegister(BaseModel):
    url: str
    events: list[str]
    secret: str | None = None


# ── Webhook Delivery Helper ─────────────────────────────────────

async def _deliver_webhook(webhook_doc: dict, event: str, data: dict):
    """Fire-and-forget webhook delivery with signature."""
    delivery_id = _uuid()
    payload = {
        "event": event,
        "timestamp": _now_iso(),
        "delivery_id": delivery_id,
        "data": data,
    }
    import json
    body = json.dumps(payload, default=str)

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Event": event,
        "X-Webhook-Delivery": delivery_id,
    }

    secret = webhook_doc.get("secret")
    if secret:
        sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        headers["X-Webhook-Signature"] = f"sha256={sig}"

    status_code = 0
    error_msg = None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(webhook_doc["url"], content=body, headers=headers)
            status_code = resp.status_code
    except Exception as exc:
        error_msg = str(exc)
        logger.warning("Webhook delivery failed for %s: %s", webhook_doc["url"], exc)

    from core.tenant_db import get_system_db
    sysdb = get_system_db()
    await sysdb.webhook_deliveries.insert_one({
        "id": delivery_id,
        "webhook_id": webhook_doc["id"],
        "agency_id": webhook_doc["agency_id"],
        "tenant_id": webhook_doc["tenant_id"],
        "event": event,
        "url": webhook_doc["url"],
        "status_code": status_code,
        "error": error_msg,
        "created_at": _now_iso(),
    })


async def fire_webhooks(tenant_id: str, agency_id: str, event: str, data: dict):
    """Find all active webhooks for agency subscribed to event and deliver."""
    from core.tenant_db import get_system_db
    sysdb = get_system_db()
    webhooks = await sysdb.agency_webhooks.find({
        "tenant_id": tenant_id,
        "agency_id": agency_id,
        "is_active": True,
        "events": event,
    }, {"_id": 0}).to_list(50)

    for wh in webhooks:
        try:
            await _deliver_webhook(wh, event, data)
        except Exception as exc:
            logger.error("Webhook fire error: %s", exc)


# ═════════════════════════════════════════════════════════════════
# ADMIN ENDPOINTS — API Key Yonetimi (Hotel Staff)
# ═════════════════════════════════════════════════════════════════

@router.post("/api-keys")
async def create_api_key(
    agency_id: str = Query(...),
    current_user: User = Depends(get_current_user),
):
    """Acente icin API key olustur."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id

    agency = await db.agencies.find_one(
        {"id": agency_id, "tenant_id": tenant_id}, {"_id": 0}
    )
    if not agency:
        raise HTTPException(status_code=404, detail="Acente bulunamadi")

    # Check if key already exists
    existing = await db.agency_api_keys.find_one(
        {"agency_id": agency_id, "tenant_id": tenant_id, "is_active": True}
    )
    if existing:
        raise HTTPException(status_code=409, detail="Bu acente icin zaten aktif bir API key var. Yenilemek icin regenerate endpoint'ini kullanin.")

    # Generate key: syroce_b2b_{random}
    raw_key = f"syroce_b2b_{secrets.token_urlsafe(32)}"
    key_hash = _hash_api_key(raw_key)

    key_doc = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "agency_id": agency_id,
        "agency_name": agency.get("name", ""),
        "key_hash": key_hash,
        "key_prefix": raw_key[:16] + "...",
        "is_active": True,
        "usage_count": 0,
        "created_at": _now_iso(),
        "created_by": current_user.id,
        "last_used_at": None,
    }
    await db.agency_api_keys.insert_one(key_doc)
    key_doc.pop("_id", None)

    return {
        "api_key": raw_key,
        "key_prefix": key_doc["key_prefix"],
        "agency_id": agency_id,
        "agency_name": agency.get("name", ""),
        "message": "API key olusturuldu. Bu key sadece bir kez gosterilir, guvenli bir yerde saklayin.",
    }


@router.get("/api-keys/{agency_id}")
async def get_api_key_info(
    agency_id: str,
    current_user: User = Depends(get_current_user),
):
    """Acente API key bilgisini getir (key gosterilmez)."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id

    key_doc = await db.agency_api_keys.find_one(
        {"agency_id": agency_id, "tenant_id": tenant_id, "is_active": True},
        {"_id": 0, "key_hash": 0},
    )
    if not key_doc:
        return {"has_key": False, "agency_id": agency_id}

    return {
        "has_key": True,
        "agency_id": agency_id,
        "key_prefix": key_doc.get("key_prefix", ""),
        "created_at": key_doc.get("created_at"),
        "last_used_at": key_doc.get("last_used_at"),
        "usage_count": key_doc.get("usage_count", 0),
    }


@router.delete("/api-keys/{agency_id}")
async def revoke_api_key(
    agency_id: str,
    current_user: User = Depends(get_current_user),
):
    """Acente API key'ini iptal et."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id

    result = await db.agency_api_keys.update_many(
        {"agency_id": agency_id, "tenant_id": tenant_id, "is_active": True},
        {"$set": {"is_active": False, "revoked_at": _now_iso(), "revoked_by": current_user.id}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Aktif API key bulunamadi")

    return {"ok": True, "message": "API key iptal edildi"}


@router.post("/api-keys/{agency_id}/regenerate")
async def regenerate_api_key(
    agency_id: str,
    current_user: User = Depends(get_current_user),
):
    """Mevcut key'i iptal edip yeni key olustur."""
    _require_hotel_staff(current_user)
    tenant_id = current_user.tenant_id

    agency = await db.agencies.find_one(
        {"id": agency_id, "tenant_id": tenant_id}, {"_id": 0}
    )
    if not agency:
        raise HTTPException(status_code=404, detail="Acente bulunamadi")

    # Revoke old keys
    await db.agency_api_keys.update_many(
        {"agency_id": agency_id, "tenant_id": tenant_id, "is_active": True},
        {"$set": {"is_active": False, "revoked_at": _now_iso(), "revoked_by": current_user.id}},
    )

    # Generate new key
    raw_key = f"syroce_b2b_{secrets.token_urlsafe(32)}"
    key_hash = _hash_api_key(raw_key)

    key_doc = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "agency_id": agency_id,
        "agency_name": agency.get("name", ""),
        "key_hash": key_hash,
        "key_prefix": raw_key[:16] + "...",
        "is_active": True,
        "usage_count": 0,
        "created_at": _now_iso(),
        "created_by": current_user.id,
        "last_used_at": None,
    }
    await db.agency_api_keys.insert_one(key_doc)
    key_doc.pop("_id", None)

    return {
        "api_key": raw_key,
        "key_prefix": key_doc["key_prefix"],
        "agency_id": agency_id,
        "message": "API key yenilendi. Eski key artik gecersiz.",
    }


# ═════════════════════════════════════════════════════════════════
# B2B ENDPOINTS — Syroce Acente Sistemi (API Key Auth)
# ═════════════════════════════════════════════════════════════════

@router.get("/content")
async def b2b_get_content(agency: dict = Depends(get_b2b_agency)):
    """Otel icerigini getir (oda tipleri, hizmetler, genel bilgi)."""
    tenant_id = agency["tenant_id"]
    agency_id = agency["agency_id"]

    # Check if content is published to this agency
    agency_doc = await db.agencies.find_one(
        {"id": agency_id, "tenant_id": tenant_id}, {"_id": 0}
    )
    if not agency_doc or not agency_doc.get("published_content"):
        return {
            "published": False,
            "message": "Bu acente icin henuz icerik yayinlanmamis",
            "hotel_content": None,
        }

    content = await db.hotel_content.find_one(
        {"tenant_id": tenant_id}, {"_id": 0, "id": 0}
    )
    if not content:
        return {"published": False, "hotel_content": None}

    content.pop("tenant_id", None)
    return {"published": True, "hotel_content": content}


@router.get("/availability")
async def b2b_get_availability(
    check_in: str = Query(..., description="YYYY-MM-DD"),
    check_out: str = Query(..., description="YYYY-MM-DD"),
    room_type: str = Query(None, description="Oda tipi filtresi (opsiyonel)"),
    agency: dict = Depends(get_b2b_agency),
):
    """Gercek zamanli musaitlik sorgusu."""
    tenant_id = agency["tenant_id"]

    ci = datetime.fromisoformat(check_in + "T00:00:00+00:00")
    co = datetime.fromisoformat(check_out + "T00:00:00+00:00")
    if co <= ci:
        raise HTTPException(status_code=400, detail="check_out, check_in'den sonra olmali")

    room_query = {"tenant_id": tenant_id}
    if room_type:
        room_query["room_type"] = room_type

    rooms = await db.rooms.find(room_query, {"_id": 0}).to_list(1000)

    room_types = {}
    for r in rooms:
        rt = r.get("room_type", "Standard")
        if rt not in room_types:
            room_types[rt] = {
                "room_type": rt,
                "capacity": r.get("capacity", 2),
                "base_price": r.get("base_price", 0),
                "amenities": r.get("amenities", []),
                "bed_type": r.get("bed_type", ""),
                "total_rooms": 0,
                "available_rooms": 0,
                "room_ids": [],
            }
        room_types[rt]["total_rooms"] += 1
        room_types[rt]["room_ids"].append(r.get("id"))

    for rt_data in room_types.values():
        booked = await db.bookings.count_documents({
            "tenant_id": tenant_id,
            "room_id": {"$in": rt_data["room_ids"]},
            "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
            "check_in": {"$lt": check_out + "T23:59:59"},
            "check_out": {"$gt": check_in + "T00:00:00"},
        })
        rt_data["available_rooms"] = max(0, rt_data["total_rooms"] - booked)
        del rt_data["room_ids"]

    results = list(room_types.values())
    return {
        "check_in": check_in,
        "check_out": check_out,
        "room_types": results,
    }


@router.get("/rates")
async def b2b_get_rates(
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    room_type: str = Query(None, description="Oda tipi filtresi (opsiyonel)"),
    agency: dict = Depends(get_b2b_agency),
):
    """Acenteye ozel fiyatlari getir (agency_rate_calendar'dan)."""
    tenant_id = agency["tenant_id"]
    agency_id = agency["agency_id"]

    query = {
        "tenant_id": tenant_id,
        "agency_id": agency_id,
        "date": {"$gte": start_date, "$lte": end_date},
    }
    if room_type:
        query["room_type_code"] = room_type

    rates = await db.agency_rate_calendar.find(
        query, {"_id": 0, "tenant_id": 0, "agency_id": 0, "updated_by": 0}
    ).sort("date", 1).to_list(5000)

    # If no agency-specific rates, fall back to base hotel rates
    if not rates:
        # Try main rate calendar
        base_query = {
            "tenant_id": tenant_id,
            "date": {"$gte": start_date, "$lte": end_date},
        }
        if room_type:
            base_query["room_type_code"] = room_type

        # Try HR calendar first, then Exely calendar
        rates = await db.hr_rate_calendar.find(
            base_query, {"_id": 0, "tenant_id": 0, "updated_by": 0}
        ).sort("date", 1).to_list(5000)

        if not rates:
            rates = await db.rate_calendar.find(
                base_query, {"_id": 0, "tenant_id": 0, "updated_by": 0}
            ).sort("date", 1).to_list(5000)

        return {
            "start_date": start_date,
            "end_date": end_date,
            "source": "base_rates",
            "rates": rates,
        }

    return {
        "start_date": start_date,
        "end_date": end_date,
        "source": "agency_rates",
        "rates": rates,
    }


@router.post("/reservations")
async def b2b_create_reservation(
    data: B2BReservationCreate,
    background_tasks: BackgroundTasks,
    agency: dict = Depends(get_b2b_agency),
):
    """Rezervasyon olustur — otomatik PMS'e duser."""
    tenant_id = agency["tenant_id"]
    agency_id = agency["agency_id"]

    ci = datetime.fromisoformat(data.check_in + "T14:00:00+00:00")
    co = datetime.fromisoformat(data.check_out + "T11:00:00+00:00")
    if co <= ci:
        raise HTTPException(status_code=400, detail="check_out, check_in'den sonra olmali")

    rooms = await db.rooms.find(
        {"tenant_id": tenant_id, "room_type": data.room_type}, {"_id": 0}
    ).to_list(500)

    if not rooms:
        raise HTTPException(status_code=404, detail="Oda tipi bulunamadi")

    available_room = None
    for room in rooms:
        conflict = await db.bookings.count_documents({
            "tenant_id": tenant_id,
            "room_id": room["id"],
            "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
            "check_in": {"$lt": data.check_out + "T23:59:59"},
            "check_out": {"$gt": data.check_in + "T00:00:00"},
        })
        if conflict == 0:
            available_room = room
            break

    if not available_room:
        raise HTTPException(status_code=409, detail="Secilen tarihler icin musait oda bulunamadi")

    commission_rate = agency.get("commission_rate", 0)
    agency_name = agency.get("agency_name", "")

    # Create guest
    guest_id = _uuid()
    await db.guests.insert_one({
        "id": guest_id,
        "tenant_id": tenant_id,
        "name": data.guest_name.strip(),
        "email": data.guest_email.strip() or f"b2b-{guest_id[:8]}@placeholder.local",
        "phone": data.guest_phone.strip(),
        "id_number": "",
        "vip_status": False,
        "loyalty_points": 0,
        "total_stays": 0,
        "total_spend": 0.0,
        "created_at": _now_iso(),
    })

    booking_id = _uuid()
    confirmation_code = f"B2B-{booking_id[:8].upper()}"
    nights = (co - ci).days
    total = data.total_amount if data.total_amount > 0 else available_room.get("base_price", 0) * max(nights, 1)
    commission_amount = round(total * commission_rate / 100, 2)

    booking_doc = {
        "id": booking_id,
        "tenant_id": tenant_id,
        "guest_id": guest_id,
        "room_id": available_room["id"],
        "room_number": available_room.get("room_number", ""),
        "room_type": available_room.get("room_type", ""),
        "check_in": data.check_in + "T14:00:00",
        "check_out": data.check_out + "T11:00:00",
        "adults": data.adults,
        "children": data.children,
        "guests_count": data.adults + data.children,
        "status": "confirmed",
        "payment_status": "pending",
        "total_amount": total,
        "balance": total,
        "channel": "b2b_api",
        "source_channel": "b2b_api",
        "agency_id": agency_id,
        "agency_name": agency_name,
        "agency_commission_rate": commission_rate,
        "agency_commission_amount": commission_amount,
        "confirmation_code": confirmation_code,
        "special_requests": data.special_requests,
        "guest_name": data.guest_name.strip(),
        "guest_email": data.guest_email.strip(),
        "guest_phone": data.guest_phone.strip(),
        "origin": "syroce_b2b",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await db.bookings.insert_one(booking_doc)
    booking_doc.pop("_id", None)

    # Fire webhook: reservation.created
    res_data = {
        "reservation_id": booking_id,
        "confirmation_code": confirmation_code,
        "status": "confirmed",
        "room_type": available_room.get("room_type", ""),
        "check_in": data.check_in,
        "check_out": data.check_out,
        "guest_name": data.guest_name,
        "total_amount": total,
    }
    background_tasks.add_task(fire_webhooks, tenant_id, agency_id, "reservation.created", res_data)

    return {
        "ok": True,
        "reservation": {
            "id": booking_id,
            "confirmation_code": confirmation_code,
            "status": "confirmed",
            "room_type": available_room.get("room_type", ""),
            "room_number": available_room.get("room_number", ""),
            "check_in": data.check_in,
            "check_out": data.check_out,
            "guest_name": data.guest_name,
            "total_amount": total,
            "commission_rate": commission_rate,
            "commission_amount": commission_amount,
            "created_at": booking_doc["created_at"],
        },
        "message": f"Rezervasyon olusturuldu: {confirmation_code}",
    }


@router.get("/reservations")
async def b2b_list_reservations(
    status: str = Query(None, description="Durum filtresi: confirmed, cancelled, checked_in, checked_out"),
    check_in_from: str = Query(None, description="YYYY-MM-DD"),
    check_in_to: str = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(100, le=500),
    agency: dict = Depends(get_b2b_agency),
):
    """Acente rezervasyonlarini listele."""
    tenant_id = agency["tenant_id"]
    agency_id = agency["agency_id"]

    query = {
        "tenant_id": tenant_id,
        "agency_id": agency_id,
        "source_channel": {"$in": ["agency", "b2b_api"]},
    }
    if status:
        query["status"] = status
    if check_in_from:
        query.setdefault("check_in", {})["$gte"] = check_in_from
    if check_in_to:
        query.setdefault("check_in", {})["$lte"] = check_in_to + "T23:59:59"

    docs = await db.bookings.find(
        query,
        {
            "_id": 0, "tenant_id": 0, "guest_id": 0, "room_id": 0,
            "updated_by": 0,
        },
    ).sort("created_at", -1).to_list(limit)

    return {"reservations": docs, "count": len(docs)}


@router.get("/reservations/{reservation_id}")
async def b2b_get_reservation(
    reservation_id: str,
    agency: dict = Depends(get_b2b_agency),
):
    """Tek rezervasyon detayi."""
    tenant_id = agency["tenant_id"]
    agency_id = agency["agency_id"]

    doc = await db.bookings.find_one(
        {
            "tenant_id": tenant_id,
            "agency_id": agency_id,
            "$or": [{"id": reservation_id}, {"confirmation_code": reservation_id}],
        },
        {"_id": 0, "tenant_id": 0, "guest_id": 0, "room_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    return {"reservation": doc}


@router.put("/reservations/{reservation_id}/cancel")
async def b2b_cancel_reservation(
    reservation_id: str,
    background_tasks: BackgroundTasks,
    agency: dict = Depends(get_b2b_agency),
):
    """Rezervasyon iptal et."""
    tenant_id = agency["tenant_id"]
    agency_id = agency["agency_id"]

    doc = await db.bookings.find_one(
        {
            "tenant_id": tenant_id,
            "agency_id": agency_id,
            "$or": [{"id": reservation_id}, {"confirmation_code": reservation_id}],
        },
        {"_id": 0},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    if doc.get("status") in ("cancelled", "checked_out", "checked_in"):
        raise HTTPException(
            status_code=400,
            detail=f"Bu rezervasyon iptal edilemez (mevcut durum: {doc.get('status')})",
        )

    await db.bookings.update_one(
        {"id": doc["id"], "tenant_id": tenant_id},
        {"$set": {
            "status": "cancelled",
            "cancelled_at": _now_iso(),
            "cancelled_by": f"b2b_api:{agency_id}",
            "updated_at": _now_iso(),
        }},
    )

    # Fire webhook: reservation.cancelled
    cancel_data = {
        "reservation_id": doc["id"],
        "confirmation_code": doc.get("confirmation_code", ""),
        "status": "cancelled",
        "room_type": doc.get("room_type", ""),
        "check_in": doc.get("check_in", ""),
        "check_out": doc.get("check_out", ""),
        "guest_name": doc.get("guest_name", ""),
    }
    background_tasks.add_task(fire_webhooks, tenant_id, agency_id, "reservation.cancelled", cancel_data)

    return {
        "ok": True,
        "reservation_id": doc["id"],
        "confirmation_code": doc.get("confirmation_code", ""),
        "status": "cancelled",
        "message": "Rezervasyon iptal edildi",
    }


# ═════════════════════════════════════════════════════════════════
# WEBHOOK ENDPOINTS — (API Key Auth)
# ═════════════════════════════════════════════════════════════════

VALID_WEBHOOK_EVENTS = {"reservation.created", "reservation.cancelled", "reservation.updated"}


@router.post("/webhooks")
async def b2b_register_webhook(
    data: WebhookRegister,
    agency: dict = Depends(get_b2b_agency),
):
    """Webhook URL kaydet."""
    tenant_id = agency["tenant_id"]
    agency_id = agency["agency_id"]

    if not data.url.startswith("https://"):
        raise HTTPException(status_code=400, detail="Webhook URL must use HTTPS")

    invalid_events = set(data.events) - VALID_WEBHOOK_EVENTS
    if invalid_events:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid events: {', '.join(invalid_events)}. Valid: {', '.join(sorted(VALID_WEBHOOK_EVENTS))}",
        )

    from core.tenant_db import get_system_db
    sysdb = get_system_db()

    existing = await sysdb.agency_webhooks.count_documents({
        "agency_id": agency_id, "tenant_id": tenant_id, "is_active": True,
    })
    if existing >= 5:
        raise HTTPException(status_code=400, detail="Maximum 5 active webhooks per agency")

    webhook_id = _uuid()
    doc = {
        "id": webhook_id,
        "tenant_id": tenant_id,
        "agency_id": agency_id,
        "url": data.url,
        "events": list(set(data.events)),
        "secret": data.secret or "",
        "is_active": True,
        "created_at": _now_iso(),
    }
    await sysdb.agency_webhooks.insert_one(doc)
    doc.pop("_id", None)
    doc.pop("secret", None)

    return {
        "ok": True,
        "webhook": {
            "id": webhook_id,
            "url": data.url,
            "events": doc["events"],
            "is_active": True,
            "created_at": doc["created_at"],
        },
        "message": "Webhook kaydedildi",
    }


@router.get("/webhooks")
async def b2b_list_webhooks(agency: dict = Depends(get_b2b_agency)):
    """Acente webhook'larini listele."""
    tenant_id = agency["tenant_id"]
    agency_id = agency["agency_id"]

    from core.tenant_db import get_system_db
    sysdb = get_system_db()

    docs = await sysdb.agency_webhooks.find(
        {"agency_id": agency_id, "tenant_id": tenant_id, "is_active": True},
        {"_id": 0, "secret": 0, "tenant_id": 0},
    ).to_list(50)

    return {"webhooks": docs, "count": len(docs)}


@router.delete("/webhooks/{webhook_id}")
async def b2b_delete_webhook(
    webhook_id: str,
    agency: dict = Depends(get_b2b_agency),
):
    """Webhook sil."""
    tenant_id = agency["tenant_id"]
    agency_id = agency["agency_id"]

    from core.tenant_db import get_system_db
    sysdb = get_system_db()

    result = await sysdb.agency_webhooks.update_one(
        {"id": webhook_id, "agency_id": agency_id, "tenant_id": tenant_id, "is_active": True},
        {"$set": {"is_active": False, "deleted_at": _now_iso()}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Webhook bulunamadi")

    return {"ok": True, "message": "Webhook silindi"}


@router.post("/webhooks/{webhook_id}/test")
async def b2b_test_webhook(
    webhook_id: str,
    agency: dict = Depends(get_b2b_agency),
):
    """Webhook'a test olayi gonder."""
    tenant_id = agency["tenant_id"]
    agency_id = agency["agency_id"]

    from core.tenant_db import get_system_db
    sysdb = get_system_db()

    wh = await sysdb.agency_webhooks.find_one(
        {"id": webhook_id, "agency_id": agency_id, "tenant_id": tenant_id, "is_active": True},
        {"_id": 0},
    )
    if not wh:
        raise HTTPException(status_code=404, detail="Webhook bulunamadi")

    test_data = {
        "reservation_id": "test-00000000",
        "confirmation_code": "B2B-TEST0000",
        "status": "confirmed",
        "room_type": "Test Room",
        "check_in": "2026-01-01",
        "check_out": "2026-01-03",
        "guest_name": "Test Guest",
        "total_amount": 100.00,
    }

    delivery_id = _uuid()
    import json
    payload = {
        "event": "test",
        "timestamp": _now_iso(),
        "delivery_id": delivery_id,
        "data": test_data,
    }
    body = json.dumps(payload, default=str)

    headers = {
        "Content-Type": "application/json",
        "X-Webhook-Event": "test",
        "X-Webhook-Delivery": delivery_id,
    }
    secret = wh.get("secret")
    if secret:
        sig = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
        headers["X-Webhook-Signature"] = f"sha256={sig}"

    status_code = 0
    error_msg = None
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(wh["url"], content=body, headers=headers)
            status_code = resp.status_code
    except Exception as exc:
        error_msg = str(exc)

    return {
        "ok": error_msg is None and 200 <= status_code < 300,
        "delivery_id": delivery_id,
        "status_code": status_code,
        "error": error_msg,
        "message": "Test olayi gonderildi" if not error_msg else f"Teslimat hatasi: {error_msg}",
    }
