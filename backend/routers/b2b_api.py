"""
Syroce Open API — Kapsamli Otel PMS Entegrasyon API'si
======================================================
Tüm Syroce PMS modüllerini dış uygulamalarla entegre etmek için
tek bir API. Sadakat programi, acente otomasyon, KBS bildirim,
pasaport/kimlik okuma, housekeeping, lost & found, wake-up call,
misafir yolculugu, MICE/grup, folio/fatura ve daha fazlasi.

Admin (Hotel) Endpoints — JWT Auth:
  POST   /api/b2b/api-keys                       - API key olustur
  GET    /api/b2b/api-keys/{agency_id}           - API key bilgisi
  DELETE /api/b2b/api-keys/{agency_id}           - API key iptal
  POST   /api/b2b/api-keys/{agency_id}/regenerate - API key yenile

Reservations — API Key Auth:
  GET    /api/b2b/content                        - Otel icerigi
  GET    /api/b2b/availability                   - Musaitlik sorgusu
  GET    /api/b2b/rates                          - Fiyat sorgusu
  POST   /api/b2b/reservations                   - Rezervasyon olustur
  GET    /api/b2b/reservations                   - Rezervasyon listesi
  GET    /api/b2b/reservations/{id}              - Rezervasyon detay
  PUT    /api/b2b/reservations/{id}/cancel       - Rezervasyon iptali

Guest & Loyalty — API Key Auth:
  GET    /api/b2b/guests/search                  - Misafir arama
  GET    /api/b2b/guests/{guest_id}              - Misafir profili
  GET    /api/b2b/guests/{guest_id}/loyalty       - Sadakat bilgisi
  POST   /api/b2b/guests/{guest_id}/loyalty/points - Puan ekle/cikar
  GET    /api/b2b/guests/{guest_id}/stays         - Konaklama gecmisi

Housekeeping — API Key Auth:
  GET    /api/b2b/housekeeping/rooms             - Oda durumlari
  PUT    /api/b2b/housekeeping/rooms/{room_id}   - Durum guncelle

KBS/Police Notification — API Key Auth:
  GET    /api/b2b/kbs/guests                     - KBS bildirim listesi
  POST   /api/b2b/kbs/report                     - KBS bildirimi olustur
  GET    /api/b2b/kbs/report/{report_id}         - Bildirim detay

Passport/ID — API Key Auth:
  POST   /api/b2b/identity/scan                  - Kimlik/pasaport verisi gonder
  GET    /api/b2b/identity/guest/{guest_id}      - Kimlik bilgisi sorgula

Lost & Found — API Key Auth:
  GET    /api/b2b/lost-found                     - Kayip esya listesi
  POST   /api/b2b/lost-found                     - Kayip esya kaydet
  PUT    /api/b2b/lost-found/{item_id}           - Esya guncelle

Wake-up Calls — API Key Auth:
  GET    /api/b2b/wake-up-calls                  - Uyandirma listesi
  POST   /api/b2b/wake-up-calls                  - Uyandirma olustur
  PUT    /api/b2b/wake-up-calls/{call_id}        - Uyandirma guncelle
  DELETE /api/b2b/wake-up-calls/{call_id}        - Uyandirma iptal

Guest Journey — API Key Auth:
  POST   /api/b2b/guest-journey/online-checkin   - Online check-in
  GET    /api/b2b/guest-journey/pre-arrival/{id} - Pre-arrival durumu
  POST   /api/b2b/guest-journey/request          - Misafir talebi
  GET    /api/b2b/guest-journey/requests         - Talep listesi

Concierge & Spa — API Key Auth:
  POST   /api/b2b/concierge/request             - Concierge talebi
  GET    /api/b2b/concierge/services             - Hizmet listesi
  POST   /api/b2b/spa/booking                    - Spa rezervasyonu
  GET    /api/b2b/spa/services                   - Spa hizmetleri

MICE & Groups — API Key Auth:
  GET    /api/b2b/groups                         - Grup listesi
  POST   /api/b2b/groups/block                   - Blok olustur
  GET    /api/b2b/groups/{block_id}              - Blok detay
  POST   /api/b2b/groups/{block_id}/rooming-list - Rooming list yukle

Folio & Billing — API Key Auth:
  GET    /api/b2b/folio/{booking_id}             - Folio detay
  POST   /api/b2b/folio/{booking_id}/charge      - Masraf ekle
  GET    /api/b2b/folio/{booking_id}/invoice      - Fatura getir

Webhooks — API Key Auth:
  POST   /api/b2b/webhooks                       - Webhook kaydet
  GET    /api/b2b/webhooks                       - Webhook listesi
  DELETE /api/b2b/webhooks/{webhook_id}          - Webhook sil
  POST   /api/b2b/webhooks/{webhook_id}/test     - Webhook test
"""
import hashlib
import hmac
import json
import logging
import secrets
import uuid
from datetime import UTC, datetime

import httpx
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from core.database import db
from core.security import get_current_user
from core.tenant_db import set_tenant_context
from models.schemas import User

logger = logging.getLogger(__name__)

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


# ── Webhook Delivery Helper (with retry + DLQ) ──────────────────

from routers.webhook_retry_service import (
    deliver_webhook_with_retry,
    fire_webhooks_with_retry,
)


async def _deliver_webhook(webhook_doc: dict, event: str, data: dict):
    """Webhook delivery with exponential backoff retry + DLQ.
    Replaces the old fire-and-forget approach.
    """
    return await deliver_webhook_with_retry(webhook_doc, event, data)


async def fire_webhooks(tenant_id: str, agency_id: str, event: str, data: dict):
    """Find all active webhooks for agency subscribed to event and deliver with retry."""
    return await fire_webhooks_with_retry(tenant_id, agency_id, event, data)


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

    try:
        ci = datetime.fromisoformat(check_in + "T00:00:00+00:00")
        co = datetime.fromisoformat(check_out + "T00:00:00+00:00")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Gecersiz tarih formati. YYYY-MM-DD kullanin.")
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

    try:
        ci = datetime.fromisoformat(data.check_in + "T14:00:00+00:00")
        co = datetime.fromisoformat(data.check_out + "T11:00:00+00:00")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Gecersiz tarih formati. YYYY-MM-DD kullanin.")
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

    # SSRF guard: localhost, link-local, private network, metadata endpoints reddedilir
    try:
        import ipaddress
        import socket
        from urllib.parse import urlparse
        parsed = urlparse(data.url)
        host = (parsed.hostname or "").lower()
        if not host:
            raise ValueError("hostname yok")
        forbidden_hostnames = {"localhost", "metadata.google.internal", "metadata.goog"}
        if host in forbidden_hostnames or host.endswith(".internal") or host.endswith(".local"):
            raise ValueError("internal hostname")
        # Resolve to all addresses; ANY private/loopback/link-local → reddet
        addrs = set()
        try:
            for r in socket.getaddrinfo(host, None):
                addrs.add(r[4][0])
        except Exception:
            # Hostname resolve edilemiyorsa kabul etme (DNS rebinding riski)
            raise ValueError("DNS cozumlenemedi")
        for a in addrs:
            ip = ipaddress.ip_address(a)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
                raise ValueError(f"izinsiz IP: {a}")
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=f"Webhook URL gecersiz veya icsel hedef: {ve}")

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


# ═════════════════════════════════════════════════════════════════
# GUEST & LOYALTY — Misafir ve Sadakat Programi
# ═════════════════════════════════════════════════════════════════

@router.get("/guests/search")
async def b2b_search_guests(
    q: str = Query(..., min_length=2, description="Isim, e-posta veya telefon ile arama"),
    limit: int = Query(20, le=100),
    agency: dict = Depends(get_b2b_agency),
):
    """Misafir arama — isim, e-posta veya telefon ile."""
    tenant_id = agency["tenant_id"]
    regex = {"$regex": q, "$options": "i"}
    docs = await db.guests.find(
        {"tenant_id": tenant_id, "$or": [{"name": regex}, {"email": regex}, {"phone": regex}]},
        {"_id": 0, "tenant_id": 0},
    ).sort("name", 1).to_list(limit)
    return {"guests": docs, "count": len(docs)}


@router.get("/guests/{guest_id}")
async def b2b_get_guest(guest_id: str, agency: dict = Depends(get_b2b_agency)):
    """Misafir profil detayi."""
    tenant_id = agency["tenant_id"]
    doc = await db.guests.find_one(
        {"tenant_id": tenant_id, "id": guest_id}, {"_id": 0, "tenant_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")
    return {"guest": doc}


@router.get("/guests/{guest_id}/loyalty")
async def b2b_get_guest_loyalty(guest_id: str, agency: dict = Depends(get_b2b_agency)):
    """Misafir sadakat bilgisi — puan, tier, toplam konaklama."""
    tenant_id = agency["tenant_id"]
    guest = await db.guests.find_one(
        {"tenant_id": tenant_id, "id": guest_id},
        {"_id": 0, "id": 1, "name": 1, "loyalty_points": 1, "loyalty_tier": 1,
         "vip_status": 1, "total_stays": 1, "total_spend": 1},
    )
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")

    points = guest.get("loyalty_points", 0)
    tier = guest.get("loyalty_tier", "")
    if not tier:
        if points >= 10000:
            tier = "platinum"
        elif points >= 5000:
            tier = "gold"
        elif points >= 2000:
            tier = "silver"
        else:
            tier = "bronze"

    return {
        "guest_id": guest["id"],
        "guest_name": guest.get("name", ""),
        "loyalty_points": points,
        "loyalty_tier": tier,
        "vip_status": guest.get("vip_status", False),
        "total_stays": guest.get("total_stays", 0),
        "total_spend": guest.get("total_spend", 0),
    }


class LoyaltyPointsUpdate(BaseModel):
    points: int = Field(..., gt=0, le=100000)
    reason: str = Field(..., min_length=1)
    operation: str = "add"


@router.post("/guests/{guest_id}/loyalty/points")
async def b2b_update_loyalty_points(
    guest_id: str,
    data: LoyaltyPointsUpdate,
    agency: dict = Depends(get_b2b_agency),
):
    """Sadakat puani ekle veya cikar."""
    tenant_id = agency["tenant_id"]

    guest = await db.guests.find_one({"tenant_id": tenant_id, "id": guest_id})
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")

    if data.operation not in ("add", "subtract"):
        raise HTTPException(status_code=400, detail="operation must be 'add' or 'subtract'")

    current_points = guest.get("loyalty_points", 0)
    if data.operation == "subtract":
        new_points = max(0, current_points - data.points)
    else:
        new_points = current_points + data.points

    new_tier = "bronze"
    if new_points >= 10000:
        new_tier = "platinum"
    elif new_points >= 5000:
        new_tier = "gold"
    elif new_points >= 2000:
        new_tier = "silver"

    await db.guests.update_one(
        {"_id": guest["_id"]},
        {"$set": {"loyalty_points": new_points, "loyalty_tier": new_tier}},
    )

    await db.loyalty_transactions.insert_one({
        "id": _uuid(),
        "tenant_id": tenant_id,
        "guest_id": guest_id,
        "points": data.points,
        "operation": data.operation,
        "reason": data.reason,
        "previous_balance": current_points,
        "new_balance": new_points,
        "source": f"b2b_api:{agency['agency_id']}",
        "created_at": _now_iso(),
    })

    return {
        "ok": True,
        "guest_id": guest_id,
        "previous_points": current_points,
        "new_points": new_points,
        "new_tier": new_tier,
    }


@router.get("/guests/{guest_id}/stays")
async def b2b_get_guest_stays(
    guest_id: str,
    limit: int = Query(50, le=200),
    agency: dict = Depends(get_b2b_agency),
):
    """Misafir konaklama gecmisi."""
    tenant_id = agency["tenant_id"]
    bookings = await db.bookings.find(
        {"tenant_id": tenant_id, "guest_id": guest_id},
        {"_id": 0, "tenant_id": 0, "guest_id": 0},
    ).sort("check_in", -1).to_list(limit)
    return {"stays": bookings, "count": len(bookings)}


# ═════════════════════════════════════════════════════════════════
# HOUSEKEEPING — Kat Hizmetleri
# ═════════════════════════════════════════════════════════════════

@router.get("/housekeeping/rooms")
async def b2b_get_housekeeping_rooms(
    status: str = Query(None, description="Filtre: clean, dirty, inspected, maintenance, out_of_order"),
    floor: str = Query(None),
    agency: dict = Depends(get_b2b_agency),
):
    """Odalar ve temizlik durumlarini listele."""
    tenant_id = agency["tenant_id"]
    query = {"tenant_id": tenant_id}
    if status:
        query["housekeeping_status"] = status
    if floor:
        query["floor"] = floor

    rooms = await db.rooms.find(
        query,
        {"_id": 0, "id": 1, "room_number": 1, "room_type": 1, "floor": 1,
         "housekeeping_status": 1, "status": 1, "last_cleaned_at": 1, "last_cleaned_by": 1},
    ).sort("room_number", 1).to_list(500)

    for r in rooms:
        r["housekeeping_status"] = r.get("housekeeping_status", "clean")

    return {"rooms": rooms, "count": len(rooms)}


class HousekeepingStatusUpdate(BaseModel):
    status: str
    notes: str = ""


@router.put("/housekeeping/rooms/{room_id}")
async def b2b_update_housekeeping_status(
    room_id: str,
    data: HousekeepingStatusUpdate,
    agency: dict = Depends(get_b2b_agency),
):
    """Oda temizlik durumunu guncelle."""
    tenant_id = agency["tenant_id"]
    valid_statuses = {"clean", "dirty", "inspected", "maintenance", "out_of_order"}
    if data.status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Gecersiz durum. Gecerli: {', '.join(sorted(valid_statuses))}")

    room = await db.rooms.find_one({"tenant_id": tenant_id, "id": room_id})
    if not room:
        raise HTTPException(status_code=404, detail="Oda bulunamadi")

    update_fields = {
        "housekeeping_status": data.status,
        "updated_at": _now_iso(),
    }
    if data.status == "clean":
        update_fields["last_cleaned_at"] = _now_iso()
        update_fields["last_cleaned_by"] = f"b2b_api:{agency['agency_id']}"

    await db.rooms.update_one({"_id": room["_id"]}, {"$set": update_fields})

    return {
        "ok": True,
        "room_id": room_id,
        "room_number": room.get("room_number", ""),
        "new_status": data.status,
    }


# ═════════════════════════════════════════════════════════════════
# KBS / POLICE NOTIFICATION — Emniyet Bildirim Sistemi
# ═════════════════════════════════════════════════════════════════

@router.get("/kbs/guests")
async def b2b_kbs_guest_list(
    date: str = Query(None, description="YYYY-MM-DD (varsayilan: bugun)"),
    status: str = Query(None, description="Filtre: pending, submitted, confirmed, error"),
    limit: int = Query(100, le=500),
    agency: dict = Depends(get_b2b_agency),
):
    """KBS bildirimi icin check-in yapan misafir listesi."""
    tenant_id = agency["tenant_id"]
    target_date = date or datetime.now(UTC).strftime("%Y-%m-%d")

    bookings = await db.bookings.find(
        {
            "tenant_id": tenant_id,
            "status": {"$in": ["checked_in", "confirmed", "guaranteed"]},
            "check_in": {"$gte": target_date + "T00:00:00", "$lte": target_date + "T23:59:59"},
        },
        {"_id": 0, "id": 1, "guest_name": 1, "guest_email": 1, "guest_phone": 1,
         "room_number": 1, "check_in": 1, "check_out": 1, "adults": 1, "children": 1,
         "status": 1, "confirmation_code": 1},
    ).sort("check_in", 1).to_list(limit)

    for b in bookings:
        guest = await db.guests.find_one(
            {"tenant_id": tenant_id, "name": b.get("guest_name", "")},
            {"_id": 0, "nationality": 1, "id_number": 1, "passport_number": 1,
             "birth_date": 1, "gender": 1},
        )
        if guest:
            b["nationality"] = guest.get("nationality", "")
            b["id_number"] = guest.get("id_number", "")
            b["passport_number"] = guest.get("passport_number", "")
            b["birth_date"] = guest.get("birth_date", "")
            b["gender"] = guest.get("gender", "")

    kbs_reports = await db.kbs_reports.find(
        {"tenant_id": tenant_id, "date": target_date},
        {"_id": 0},
    ).to_list(100)

    return {
        "date": target_date,
        "guests": bookings,
        "guest_count": len(bookings),
        "reports": kbs_reports,
        "report_count": len(kbs_reports),
    }


class KBSReportCreate(BaseModel):
    date: str
    guest_ids: list[str] = []
    notes: str = ""


@router.post("/kbs/report")
async def b2b_kbs_create_report(
    data: KBSReportCreate,
    agency: dict = Depends(get_b2b_agency),
):
    """KBS bildirim raporu olustur."""
    tenant_id = agency["tenant_id"]
    report_id = _uuid()

    report = {
        "id": report_id,
        "tenant_id": tenant_id,
        "date": data.date,
        "status": "submitted",
        "guest_count": len(data.guest_ids),
        "guest_ids": data.guest_ids,
        "notes": data.notes,
        "submitted_by": f"b2b_api:{agency['agency_id']}",
        "created_at": _now_iso(),
    }
    await db.kbs_reports.insert_one(report)
    report.pop("_id", None)

    return {"ok": True, "report": report}


@router.get("/kbs/report/{report_id}")
async def b2b_kbs_get_report(report_id: str, agency: dict = Depends(get_b2b_agency)):
    """KBS bildirim raporu detayi."""
    tenant_id = agency["tenant_id"]
    doc = await db.kbs_reports.find_one(
        {"tenant_id": tenant_id, "id": report_id}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="KBS raporu bulunamadi")
    return {"report": doc}


# ═════════════════════════════════════════════════════════════════
# PASSPORT / ID — Kimlik ve Pasaport Okuma
# ═════════════════════════════════════════════════════════════════

class IdentityScanData(BaseModel):
    guest_id: str
    scan_type: str  # passport, id_card, driving_license
    document_number: str
    first_name: str
    last_name: str
    nationality: str = ""
    birth_date: str = ""  # YYYY-MM-DD
    gender: str = ""  # M, F
    expiry_date: str = ""  # YYYY-MM-DD
    issuing_country: str = ""
    mrz_line1: str = ""
    mrz_line2: str = ""
    scan_quality: float = 0.0  # 0-100
    raw_ocr_data: dict | None = None


@router.post("/identity/scan")
async def b2b_identity_scan(
    data: IdentityScanData,
    agency: dict = Depends(get_b2b_agency),
):
    """Kimlik/pasaport tarama verisini kaydet — OCR sonuclari buraya gonderilir."""
    tenant_id = agency["tenant_id"]

    guest = await db.guests.find_one({"tenant_id": tenant_id, "id": data.guest_id})
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")

    scan_id = _uuid()
    scan_doc = {
        "id": scan_id,
        "tenant_id": tenant_id,
        "guest_id": data.guest_id,
        "scan_type": data.scan_type,
        "document_number": data.document_number,
        "first_name": data.first_name,
        "last_name": data.last_name,
        "nationality": data.nationality,
        "birth_date": data.birth_date,
        "gender": data.gender,
        "expiry_date": data.expiry_date,
        "issuing_country": data.issuing_country,
        "mrz_line1": data.mrz_line1,
        "mrz_line2": data.mrz_line2,
        "scan_quality": data.scan_quality,
        "raw_ocr_data": data.raw_ocr_data or {},
        "verified": data.scan_quality >= 80,
        "source": f"b2b_api:{agency['agency_id']}",
        "created_at": _now_iso(),
    }
    await db.identity_scans.insert_one(scan_doc)
    scan_doc.pop("_id", None)

    guest_update = {}
    if data.nationality:
        guest_update["nationality"] = data.nationality
    if data.birth_date:
        guest_update["birth_date"] = data.birth_date
    if data.gender:
        guest_update["gender"] = data.gender
    if data.scan_type == "passport" and data.document_number:
        guest_update["passport_number"] = data.document_number
    elif data.scan_type == "id_card" and data.document_number:
        guest_update["id_number"] = data.document_number

    if guest_update:
        guest_update["updated_at"] = _now_iso()
        await db.guests.update_one({"_id": guest["_id"]}, {"$set": guest_update})

    return {"ok": True, "scan": scan_doc}


@router.get("/identity/guest/{guest_id}")
async def b2b_identity_get(guest_id: str, agency: dict = Depends(get_b2b_agency)):
    """Misafir kimlik/pasaport bilgilerini getir."""
    tenant_id = agency["tenant_id"]

    guest = await db.guests.find_one(
        {"tenant_id": tenant_id, "id": guest_id},
        {"_id": 0, "id": 1, "name": 1, "nationality": 1, "id_number": 1,
         "passport_number": 1, "birth_date": 1, "gender": 1},
    )
    if not guest:
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")

    scans = await db.identity_scans.find(
        {"tenant_id": tenant_id, "guest_id": guest_id},
        {"_id": 0, "tenant_id": 0, "raw_ocr_data": 0},
    ).sort("created_at", -1).to_list(10)

    return {"guest": guest, "scans": scans}


# ═════════════════════════════════════════════════════════════════
# LOST & FOUND — Kayip Esya
# ═════════════════════════════════════════════════════════════════

@router.get("/lost-found")
async def b2b_list_lost_found(
    status: str = Query(None, description="Filtre: found, claimed, returned, disposed"),
    category: str = Query(None),
    limit: int = Query(50, le=200),
    agency: dict = Depends(get_b2b_agency),
):
    """Kayip/bulunan esya listesi."""
    tenant_id = agency["tenant_id"]
    query = {"tenant_id": tenant_id}
    if status:
        query["status"] = status
    if category:
        query["category"] = category

    items = await db.lost_found.find(
        query, {"_id": 0, "tenant_id": 0}
    ).sort("created_at", -1).to_list(limit)
    return {"items": items, "count": len(items)}


class LostFoundCreate(BaseModel):
    item_name: str
    description: str = ""
    category: str = "other"
    location_found: str = ""
    found_by: str = ""
    guest_name: str = ""
    room_number: str = ""


@router.post("/lost-found")
async def b2b_create_lost_found(
    data: LostFoundCreate,
    agency: dict = Depends(get_b2b_agency),
):
    """Bulunan esya kaydet."""
    tenant_id = agency["tenant_id"]
    item_id = _uuid()

    item = {
        "id": item_id,
        "tenant_id": tenant_id,
        "item_name": data.item_name,
        "description": data.description,
        "category": data.category,
        "location_found": data.location_found,
        "found_by": data.found_by,
        "guest_name": data.guest_name,
        "room_number": data.room_number,
        "status": "found",
        "reported_by": f"b2b_api:{agency['agency_id']}",
        "created_at": _now_iso(),
    }
    await db.lost_found.insert_one(item)
    item.pop("_id", None)
    return {"ok": True, "item": item}


class LostFoundUpdate(BaseModel):
    status: str | None = None
    guest_name: str | None = None
    notes: str | None = None
    claimed_by: str | None = None


@router.put("/lost-found/{item_id}")
async def b2b_update_lost_found(
    item_id: str,
    data: LostFoundUpdate,
    agency: dict = Depends(get_b2b_agency),
):
    """Kayip esya durumunu guncelle."""
    tenant_id = agency["tenant_id"]
    item = await db.lost_found.find_one({"tenant_id": tenant_id, "id": item_id})
    if not item:
        raise HTTPException(status_code=404, detail="Esya bulunamadi")

    updates = {"updated_at": _now_iso()}
    if data.status:
        valid = {"found", "claimed", "returned", "disposed"}
        if data.status not in valid:
            raise HTTPException(status_code=400, detail=f"Gecersiz durum. Gecerli: {', '.join(sorted(valid))}")
        updates["status"] = data.status
    if data.guest_name is not None:
        updates["guest_name"] = data.guest_name
    if data.notes is not None:
        updates["notes"] = data.notes
    if data.claimed_by is not None:
        updates["claimed_by"] = data.claimed_by

    await db.lost_found.update_one({"_id": item["_id"]}, {"$set": updates})
    updated = await db.lost_found.find_one({"id": item_id}, {"_id": 0, "tenant_id": 0})
    return {"ok": True, "item": updated}


# ═════════════════════════════════════════════════════════════════
# WAKE-UP CALLS — Uyandirma Servisi
# ═════════════════════════════════════════════════════════════════

@router.get("/wake-up-calls")
async def b2b_list_wake_up_calls(
    date: str = Query(None, description="YYYY-MM-DD"),
    status: str = Query(None, description="Filtre: pending, completed, cancelled, missed"),
    agency: dict = Depends(get_b2b_agency),
):
    """Uyandirma listesi."""
    tenant_id = agency["tenant_id"]
    query = {"tenant_id": tenant_id}
    if date:
        query["wake_date"] = date
    if status:
        query["status"] = status

    calls = await db.wake_up_calls.find(
        query, {"_id": 0, "tenant_id": 0}
    ).sort([("wake_date", 1), ("wake_time", 1)]).to_list(200)
    return {"wake_up_calls": calls, "count": len(calls)}


class WakeUpCallCreate(BaseModel):
    room_number: str
    guest_name: str
    wake_date: str  # YYYY-MM-DD
    wake_time: str  # HH:MM
    notes: str = ""
    recurring: bool = False
    recurring_until: str = ""  # YYYY-MM-DD


@router.post("/wake-up-calls")
async def b2b_create_wake_up_call(
    data: WakeUpCallCreate,
    agency: dict = Depends(get_b2b_agency),
):
    """Uyandirma talebi olustur."""
    tenant_id = agency["tenant_id"]
    call_id = _uuid()

    call = {
        "id": call_id,
        "tenant_id": tenant_id,
        "room_number": data.room_number,
        "guest_name": data.guest_name,
        "wake_date": data.wake_date,
        "wake_time": data.wake_time,
        "notes": data.notes,
        "recurring": data.recurring,
        "recurring_until": data.recurring_until,
        "status": "pending",
        "created_by": f"b2b_api:{agency['agency_id']}",
        "created_at": _now_iso(),
    }
    await db.wake_up_calls.insert_one(call)
    call.pop("_id", None)
    return {"ok": True, "wake_up_call": call}


class WakeUpCallUpdate(BaseModel):
    wake_time: str | None = None
    status: str | None = None
    notes: str | None = None


@router.put("/wake-up-calls/{call_id}")
async def b2b_update_wake_up_call(
    call_id: str,
    data: WakeUpCallUpdate,
    agency: dict = Depends(get_b2b_agency),
):
    """Uyandirma talebini guncelle."""
    tenant_id = agency["tenant_id"]
    call = await db.wake_up_calls.find_one({"tenant_id": tenant_id, "id": call_id})
    if not call:
        raise HTTPException(status_code=404, detail="Uyandirma talebi bulunamadi")

    updates = {"updated_at": _now_iso()}
    if data.wake_time:
        updates["wake_time"] = data.wake_time
    if data.status:
        valid = {"pending", "completed", "cancelled", "missed"}
        if data.status not in valid:
            raise HTTPException(status_code=400, detail=f"Gecersiz durum. Gecerli: {', '.join(sorted(valid))}")
        updates["status"] = data.status
    if data.notes is not None:
        updates["notes"] = data.notes

    await db.wake_up_calls.update_one({"_id": call["_id"]}, {"$set": updates})
    updated = await db.wake_up_calls.find_one({"id": call_id}, {"_id": 0, "tenant_id": 0})
    return {"ok": True, "wake_up_call": updated}


@router.delete("/wake-up-calls/{call_id}")
async def b2b_delete_wake_up_call(call_id: str, agency: dict = Depends(get_b2b_agency)):
    """Uyandirma talebini iptal et."""
    tenant_id = agency["tenant_id"]
    result = await db.wake_up_calls.delete_one({"tenant_id": tenant_id, "id": call_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Uyandirma talebi bulunamadi")
    return {"ok": True, "message": "Uyandirma talebi iptal edildi"}


# ═════════════════════════════════════════════════════════════════
# GUEST JOURNEY — Misafir Yolculugu
# ═════════════════════════════════════════════════════════════════

class B2BOnlineCheckin(BaseModel):
    booking_id: str
    arrival_time: str | None = None
    flight_number: str | None = None
    room_preference: str | None = None
    special_requests: str | None = None
    passport_number: str | None = None
    nationality: str | None = None


@router.post("/guest-journey/online-checkin")
async def b2b_online_checkin(
    data: B2BOnlineCheckin,
    agency: dict = Depends(get_b2b_agency),
):
    """Online check-in bilgilerini gonder."""
    tenant_id = agency["tenant_id"]

    booking = await db.bookings.find_one(
        {"tenant_id": tenant_id, "id": data.booking_id},
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    checkin_data = {k: v for k, v in data.model_dump().items() if v is not None and k != "booking_id"}
    checkin_data["online_checkin_completed"] = True
    checkin_data["online_checkin_at"] = _now_iso()
    checkin_data["online_checkin_source"] = f"b2b_api:{agency['agency_id']}"

    await db.bookings.update_one(
        {"_id": booking["_id"]},
        {"$set": checkin_data},
    )

    if data.passport_number or data.nationality:
        guest_update = {}
        if data.passport_number:
            guest_update["passport_number"] = data.passport_number
        if data.nationality:
            guest_update["nationality"] = data.nationality
        if guest_update and booking.get("guest_id"):
            await db.guests.update_one(
                {"tenant_id": tenant_id, "id": booking["guest_id"]},
                {"$set": guest_update},
            )

    return {"ok": True, "booking_id": data.booking_id, "message": "Online check-in tamamlandi"}


@router.get("/guest-journey/pre-arrival/{booking_id}")
async def b2b_pre_arrival_status(booking_id: str, agency: dict = Depends(get_b2b_agency)):
    """Rezervasyon pre-arrival durumunu sorgula."""
    tenant_id = agency["tenant_id"]
    booking = await db.bookings.find_one(
        {"tenant_id": tenant_id, "id": booking_id},
        {"_id": 0, "id": 1, "status": 1, "check_in": 1, "check_out": 1,
         "guest_name": 1, "room_number": 1, "room_type": 1,
         "online_checkin_completed": 1, "special_requests": 1,
         "arrival_time": 1, "flight_number": 1},
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")
    return {"booking": booking}


class B2BGuestRequest(BaseModel):
    booking_id: str
    request_type: str  # concierge, spa, room_service, maintenance, transport, other
    description: str
    priority: str = "normal"


@router.post("/guest-journey/request")
async def b2b_create_guest_request(
    data: B2BGuestRequest,
    agency: dict = Depends(get_b2b_agency),
):
    """Misafir talebi olustur — her turlu servis talebi icin."""
    tenant_id = agency["tenant_id"]

    booking = await db.bookings.find_one(
        {"tenant_id": tenant_id, "id": data.booking_id},
        {"_id": 0, "id": 1, "guest_name": 1, "room_number": 1},
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    request_id = _uuid()
    req_doc = {
        "id": request_id,
        "tenant_id": tenant_id,
        "booking_id": data.booking_id,
        "guest_name": booking.get("guest_name", ""),
        "room_number": booking.get("room_number", ""),
        "request_type": data.request_type,
        "description": data.description,
        "priority": data.priority,
        "status": "pending",
        "source": f"b2b_api:{agency['agency_id']}",
        "created_at": _now_iso(),
    }
    await db.guest_requests.insert_one(req_doc)
    req_doc.pop("_id", None)
    return {"ok": True, "request": req_doc}


@router.get("/guest-journey/requests")
async def b2b_list_guest_requests(
    booking_id: str = Query(None),
    status: str = Query(None, description="pending, in_progress, completed, cancelled"),
    request_type: str = Query(None),
    limit: int = Query(50, le=200),
    agency: dict = Depends(get_b2b_agency),
):
    """Misafir taleplerini listele."""
    tenant_id = agency["tenant_id"]
    query = {"tenant_id": tenant_id}
    if booking_id:
        query["booking_id"] = booking_id
    if status:
        query["status"] = status
    if request_type:
        query["request_type"] = request_type

    docs = await db.guest_requests.find(
        query, {"_id": 0, "tenant_id": 0}
    ).sort("created_at", -1).to_list(limit)
    return {"requests": docs, "count": len(docs)}


# ═════════════════════════════════════════════════════════════════
# CONCIERGE & SPA — Concierge ve Spa Hizmetleri
# ═════════════════════════════════════════════════════════════════

@router.get("/concierge/services")
async def b2b_concierge_services(agency: dict = Depends(get_b2b_agency)):
    """Otel concierge hizmet listesi."""
    tenant_id = agency["tenant_id"]
    services = await db.concierge_services.find(
        {"tenant_id": tenant_id, "is_active": True},
        {"_id": 0, "tenant_id": 0},
    ).sort("category", 1).to_list(100)

    if not services:
        services = [
            {"id": "transfer", "name": "Airport Transfer", "name_tr": "Havaalani Transferi", "category": "transport", "price_range": "50-150"},
            {"id": "restaurant", "name": "Restaurant Reservation", "name_tr": "Restoran Rezervasyonu", "category": "dining", "price_range": "Free"},
            {"id": "tour", "name": "City Tour", "name_tr": "Sehir Turu", "category": "activities", "price_range": "30-200"},
            {"id": "valet", "name": "Valet Parking", "name_tr": "Vale Park", "category": "transport", "price_range": "20-50"},
            {"id": "laundry", "name": "Laundry & Dry Cleaning", "name_tr": "Camasir & Kuru Temizleme", "category": "services", "price_range": "10-80"},
            {"id": "flowers", "name": "Flower Arrangement", "name_tr": "Cicek Aranjmani", "category": "special", "price_range": "30-200"},
            {"id": "babysitter", "name": "Babysitter Service", "name_tr": "Bebek Bakicisi", "category": "services", "price_range": "25-60/hr"},
        ]
    return {"services": services}


class ConciergeRequest(BaseModel):
    booking_id: str
    service_id: str
    description: str = ""
    preferred_date: str = ""
    preferred_time: str = ""
    guest_count: int = 1


@router.post("/concierge/request")
async def b2b_concierge_request(
    data: ConciergeRequest,
    agency: dict = Depends(get_b2b_agency),
):
    """Concierge hizmet talebi olustur."""
    tenant_id = agency["tenant_id"]
    booking = await db.bookings.find_one(
        {"tenant_id": tenant_id, "id": data.booking_id},
        {"_id": 0, "guest_name": 1, "room_number": 1},
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    req_id = _uuid()
    req_doc = {
        "id": req_id,
        "tenant_id": tenant_id,
        "booking_id": data.booking_id,
        "guest_name": booking.get("guest_name", ""),
        "room_number": booking.get("room_number", ""),
        "request_type": "concierge",
        "service_id": data.service_id,
        "description": data.description,
        "preferred_date": data.preferred_date,
        "preferred_time": data.preferred_time,
        "guest_count": data.guest_count,
        "status": "pending",
        "source": f"b2b_api:{agency['agency_id']}",
        "created_at": _now_iso(),
    }
    await db.guest_requests.insert_one(req_doc)
    req_doc.pop("_id", None)
    return {"ok": True, "request": req_doc}


@router.get("/spa/services")
async def b2b_spa_services(agency: dict = Depends(get_b2b_agency)):
    """Spa hizmet ve fiyat listesi."""
    tenant_id = agency["tenant_id"]
    services = await db.spa_services.find(
        {"tenant_id": tenant_id, "is_active": True},
        {"_id": 0, "tenant_id": 0},
    ).sort("category", 1).to_list(100)

    if not services:
        services = [
            {"id": "massage_60", "name": "Swedish Massage 60min", "name_tr": "Isveç Masaji 60dk", "category": "massage", "duration": 60, "price": 120},
            {"id": "massage_90", "name": "Deep Tissue Massage 90min", "name_tr": "Derin Doku Masaji 90dk", "category": "massage", "duration": 90, "price": 180},
            {"id": "facial", "name": "Hydrating Facial", "name_tr": "Nemlendirici Yüz Bakimi", "category": "facial", "duration": 45, "price": 90},
            {"id": "hammam", "name": "Turkish Hammam", "name_tr": "Türk Hamami", "category": "bath", "duration": 75, "price": 100},
            {"id": "couples", "name": "Couples Spa Package", "name_tr": "Çift Spa Paketi", "category": "package", "duration": 120, "price": 300},
            {"id": "sauna", "name": "Sauna & Steam Room", "name_tr": "Sauna & Buhar Odasi", "category": "facility", "duration": 60, "price": 40},
            {"id": "aromatherapy", "name": "Aromatherapy Massage", "name_tr": "Aromaterapi Masaji", "category": "massage", "duration": 60, "price": 140},
        ]
    return {"services": services}


class SpaBookingCreate(BaseModel):
    booking_id: str
    service_id: str
    preferred_date: str  # YYYY-MM-DD
    preferred_time: str  # HH:MM
    guest_count: int = 1
    notes: str = ""


@router.post("/spa/booking")
async def b2b_spa_booking(
    data: SpaBookingCreate,
    agency: dict = Depends(get_b2b_agency),
):
    """Spa randevusu olustur."""
    tenant_id = agency["tenant_id"]
    booking = await db.bookings.find_one(
        {"tenant_id": tenant_id, "id": data.booking_id},
        {"_id": 0, "guest_name": 1, "room_number": 1},
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    spa_id = _uuid()
    spa_doc = {
        "id": spa_id,
        "tenant_id": tenant_id,
        "booking_id": data.booking_id,
        "guest_name": booking.get("guest_name", ""),
        "room_number": booking.get("room_number", ""),
        "service_id": data.service_id,
        "preferred_date": data.preferred_date,
        "preferred_time": data.preferred_time,
        "guest_count": data.guest_count,
        "notes": data.notes,
        "status": "confirmed",
        "source": f"b2b_api:{agency['agency_id']}",
        "created_at": _now_iso(),
    }
    await db.spa_bookings.insert_one(spa_doc)
    spa_doc.pop("_id", None)
    return {"ok": True, "spa_booking": spa_doc}


# ═════════════════════════════════════════════════════════════════
# MICE & GROUPS — Grup ve Toplanti Yonetimi
# ═════════════════════════════════════════════════════════════════

@router.get("/groups")
async def b2b_list_groups(
    status: str = Query(None, description="tentative, confirmed, cancelled"),
    limit: int = Query(50, le=200),
    agency: dict = Depends(get_b2b_agency),
):
    """Grup/blok listesi."""
    tenant_id = agency["tenant_id"]
    query = {"tenant_id": tenant_id}
    if status:
        query["status"] = status

    groups = await db.room_blocks.find(
        query, {"_id": 0, "tenant_id": 0}
    ).sort("created_at", -1).to_list(limit)
    return {"groups": groups, "count": len(groups)}


class GroupBlockCreate(BaseModel):
    group_name: str
    contact_name: str
    contact_email: str = ""
    contact_phone: str = ""
    check_in: str  # YYYY-MM-DD
    check_out: str  # YYYY-MM-DD
    rooms_requested: int
    room_type: str = ""
    event_type: str = ""  # conference, wedding, corporate, tour_group, other
    estimated_revenue: float = 0
    notes: str = ""


@router.post("/groups/block")
async def b2b_create_group_block(
    data: GroupBlockCreate,
    agency: dict = Depends(get_b2b_agency),
):
    """Grup blok olustur."""
    tenant_id = agency["tenant_id"]

    try:
        ci = datetime.fromisoformat(data.check_in + "T14:00:00+00:00")
        co = datetime.fromisoformat(data.check_out + "T11:00:00+00:00")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Gecersiz tarih formati. YYYY-MM-DD kullanin.")
    if co <= ci:
        raise HTTPException(status_code=400, detail="check_out, check_in'den sonra olmali")

    block_id = _uuid()
    block = {
        "id": block_id,
        "tenant_id": tenant_id,
        "group_name": data.group_name,
        "contact_name": data.contact_name,
        "contact_email": data.contact_email,
        "contact_phone": data.contact_phone,
        "check_in": data.check_in,
        "check_out": data.check_out,
        "nights": (co - ci).days,
        "rooms_requested": data.rooms_requested,
        "rooms_picked_up": 0,
        "room_type": data.room_type,
        "event_type": data.event_type,
        "estimated_revenue": data.estimated_revenue,
        "notes": data.notes,
        "status": "tentative",
        "agency_id": agency["agency_id"],
        "agency_name": agency.get("agency_name", ""),
        "source": "b2b_api",
        "created_at": _now_iso(),
    }
    await db.room_blocks.insert_one(block)
    block.pop("_id", None)
    return {"ok": True, "block": block}


@router.get("/groups/{block_id}")
async def b2b_get_group_block(block_id: str, agency: dict = Depends(get_b2b_agency)):
    """Grup blok detayi."""
    tenant_id = agency["tenant_id"]
    block = await db.room_blocks.find_one(
        {"tenant_id": tenant_id, "id": block_id}, {"_id": 0, "tenant_id": 0}
    )
    if not block:
        raise HTTPException(status_code=404, detail="Blok bulunamadi")

    rooms = await db.bookings.find(
        {"tenant_id": tenant_id, "block_id": block_id},
        {"_id": 0, "id": 1, "guest_name": 1, "room_number": 1, "room_type": 1,
         "check_in": 1, "check_out": 1, "status": 1},
    ).to_list(500)

    return {"block": block, "rooming_list": rooms, "rooms_picked_up": len(rooms)}


class RoomingListEntry(BaseModel):
    guest_name: str
    room_type: str = ""
    check_in: str = ""
    check_out: str = ""
    special_requests: str = ""


class RoomingListUpload(BaseModel):
    guests: list[RoomingListEntry]


@router.post("/groups/{block_id}/rooming-list")
async def b2b_upload_rooming_list(
    block_id: str,
    data: RoomingListUpload,
    agency: dict = Depends(get_b2b_agency),
):
    """Grup icin rooming list yukle — toplu misafir girisi."""
    tenant_id = agency["tenant_id"]
    block = await db.room_blocks.find_one({"tenant_id": tenant_id, "id": block_id})
    if not block:
        raise HTTPException(status_code=404, detail="Blok bulunamadi")

    created = []
    for entry in data.guests:
        guest_id = _uuid()
        await db.guests.insert_one({
            "id": guest_id,
            "tenant_id": tenant_id,
            "name": entry.guest_name,
            "email": "",
            "phone": "",
            "id_number": "",
            "vip_status": False,
            "loyalty_points": 0,
            "total_stays": 0,
            "total_spend": 0.0,
            "created_at": _now_iso(),
        })

        booking_id = _uuid()
        conf_code = f"GRP-{booking_id[:8].upper()}"
        ci = entry.check_in or block.get("check_in", "")
        co = entry.check_out or block.get("check_out", "")

        booking_doc = {
            "id": booking_id,
            "tenant_id": tenant_id,
            "guest_id": guest_id,
            "guest_name": entry.guest_name,
            "block_id": block_id,
            "group_name": block.get("group_name", ""),
            "room_type": entry.room_type or block.get("room_type", ""),
            "check_in": ci + "T14:00:00" if ci and "T" not in ci else ci,
            "check_out": co + "T11:00:00" if co and "T" not in co else co,
            "status": "confirmed",
            "payment_status": "pending",
            "channel": "b2b_api",
            "source_channel": "b2b_api",
            "agency_id": agency["agency_id"],
            "confirmation_code": conf_code,
            "special_requests": entry.special_requests,
            "origin": "syroce_b2b_group",
            "created_at": _now_iso(),
        }
        await db.bookings.insert_one(booking_doc)
        booking_doc.pop("_id", None)
        created.append({"guest_name": entry.guest_name, "booking_id": booking_id, "confirmation_code": conf_code})

    await db.room_blocks.update_one(
        {"_id": block["_id"]},
        {"$inc": {"rooms_picked_up": len(created)}},
    )

    return {"ok": True, "created_count": len(created), "reservations": created}


# ═════════════════════════════════════════════════════════════════
# FOLIO & BILLING — Folio ve Fatura
# ═════════════════════════════════════════════════════════════════

@router.get("/folio/{booking_id}")
async def b2b_get_folio(booking_id: str, agency: dict = Depends(get_b2b_agency)):
    """Rezervasyon folio detayi — tum masraflar ve odemeler."""
    tenant_id = agency["tenant_id"]

    booking = await db.bookings.find_one(
        {"tenant_id": tenant_id, "id": booking_id},
        {"_id": 0, "id": 1, "guest_name": 1, "room_number": 1, "room_type": 1,
         "check_in": 1, "check_out": 1, "total_amount": 1, "balance": 1,
         "payment_status": 1, "status": 1},
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    charges = await db.folio_charges.find(
        {"tenant_id": tenant_id, "booking_id": booking_id},
        {"_id": 0, "tenant_id": 0},
    ).sort("created_at", 1).to_list(500)

    payments = await db.folio_payments.find(
        {"tenant_id": tenant_id, "booking_id": booking_id},
        {"_id": 0, "tenant_id": 0},
    ).sort("created_at", 1).to_list(100)

    total_charges = sum(c.get("amount", 0) for c in charges)
    total_payments = sum(p.get("amount", 0) for p in payments)

    return {
        "booking": booking,
        "charges": charges,
        "payments": payments,
        "total_charges": round(total_charges, 2),
        "total_payments": round(total_payments, 2),
        "balance": round(total_charges - total_payments, 2),
    }


class FolioChargeCreate(BaseModel):
    charge_type: str  # room, minibar, restaurant, spa, laundry, phone, other
    description: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0, le=1000000)
    quantity: int = Field(1, ge=1, le=9999)


@router.post("/folio/{booking_id}/charge")
async def b2b_add_folio_charge(
    booking_id: str,
    data: FolioChargeCreate,
    agency: dict = Depends(get_b2b_agency),
):
    """Folio'ya masraf ekle."""
    tenant_id = agency["tenant_id"]

    valid_charge_types = {"room", "minibar", "restaurant", "spa", "laundry", "phone", "other"}
    if data.charge_type not in valid_charge_types:
        raise HTTPException(status_code=400, detail=f"Gecersiz charge_type. Gecerli: {', '.join(sorted(valid_charge_types))}")

    booking = await db.bookings.find_one({"tenant_id": tenant_id, "id": booking_id})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    charge_id = _uuid()
    total = round(data.amount * data.quantity, 2)
    charge = {
        "id": charge_id,
        "tenant_id": tenant_id,
        "booking_id": booking_id,
        "charge_type": data.charge_type,
        "description": data.description,
        "amount": total,
        "unit_price": data.amount,
        "quantity": data.quantity,
        "posted_by": f"b2b_api:{agency['agency_id']}",
        "created_at": _now_iso(),
    }
    await db.folio_charges.insert_one(charge)
    charge.pop("_id", None)

    await db.bookings.update_one(
        {"_id": booking["_id"]},
        {"$inc": {"total_amount": total, "balance": total}},
    )

    return {"ok": True, "charge": charge}


@router.get("/folio/{booking_id}/invoice")
async def b2b_get_invoice(booking_id: str, agency: dict = Depends(get_b2b_agency)):
    """Fatura bilgisi getir (JSON formatinda)."""
    tenant_id = agency["tenant_id"]

    booking = await db.bookings.find_one(
        {"tenant_id": tenant_id, "id": booking_id},
        {"_id": 0, "tenant_id": 0},
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    charges = await db.folio_charges.find(
        {"tenant_id": tenant_id, "booking_id": booking_id},
        {"_id": 0, "tenant_id": 0},
    ).sort("created_at", 1).to_list(500)

    payments = await db.folio_payments.find(
        {"tenant_id": tenant_id, "booking_id": booking_id},
        {"_id": 0, "tenant_id": 0},
    ).sort("created_at", 1).to_list(100)

    hotel_info = await db.hotel_settings.find_one(
        {"tenant_id": tenant_id},
        {"_id": 0, "hotel_name": 1, "address": 1, "phone": 1, "email": 1,
         "tax_number": 1, "tax_office": 1},
    )

    total_charges = sum(c.get("amount", 0) for c in charges)
    total_payments = sum(p.get("amount", 0) for p in payments)

    return {
        "invoice_number": f"INV-{booking_id[:8].upper()}",
        "invoice_date": _now_iso()[:10],
        "hotel": hotel_info or {},
        "guest_name": booking.get("guest_name", ""),
        "room_number": booking.get("room_number", ""),
        "check_in": booking.get("check_in", ""),
        "check_out": booking.get("check_out", ""),
        "confirmation_code": booking.get("confirmation_code", ""),
        "charges": charges,
        "payments": payments,
        "subtotal": round(total_charges, 2),
        "total_paid": round(total_payments, 2),
        "balance_due": round(total_charges - total_payments, 2),
        "currency": "TRY",
    }
