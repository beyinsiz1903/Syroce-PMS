"""
booking_engine

Auto-split sub-router (shared imports/classes inlined).
"""

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
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from core.atomic_booking import BookingConflictError, create_booking_atomic
from core.database import db
from core.security import _is_super_admin
from models.schemas import User
from services.b2b_booking_guards import (
    GuardRejection,
    release_allotment,
    release_credit,
    reserve_allotment,
    reserve_credit,
)
from services.b2b_partner_contract import build_snapshot

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────


def _now_iso():
    return datetime.now(UTC).isoformat()


def _uuid():
    return str(uuid.uuid4())


def _hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _require_hotel_staff(user: User):
    if _is_super_admin(user):
        return
    if user.role in ("agency_admin", "agency_agent"):
        raise HTTPException(status_code=403, detail="Acente kullanicilari bu islemi yapamaz")


# ── Bug DA v64 — cross-agency IDOR guards ──────────────────────
async def _agency_owns_booking(tenant_id: str, agency_id: str, booking_id: str) -> dict | None:
    """Acentenin bu rezervasyona sahip olup olmadigini dogrular (cross-agency IDOR koruma)."""
    return await db.bookings.find_one(
        {
            "tenant_id": tenant_id,
            "agency_id": agency_id,
            "$or": [{"id": booking_id}, {"confirmation_code": booking_id}],
        },
    )


async def _agency_owns_guest(tenant_id: str, agency_id: str, guest_id: str) -> bool:
    """Acentenin bu misafire ait en az bir rezervasyonu olup olmadigini dogrular."""
    n = await db.bookings.count_documents(
        {"tenant_id": tenant_id, "agency_id": agency_id, "guest_id": guest_id},
    )
    return n > 0


async def _agency_owns_block(tenant_id: str, agency_id: str, block_id: str) -> dict | None:
    """Acentenin bu grup blok'una sahip olup olmadigini dogrular (v65)."""
    return await db.room_blocks.find_one(
        {"tenant_id": tenant_id, "agency_id": agency_id, "id": block_id},
    )


# ── API Key Auth Dependency ──────────────────────────────────────


async def get_b2b_agency(x_api_key: str | None = Header(None, alias="X-API-Key")):
    """API key ile acente kimlik dogrulamasi + per-subrouter scope kontrolu."""
    from ._scope import authenticate_b2b_agency

    return await authenticate_b2b_agency(x_api_key, required_scope="booking_engine")


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


# ═════════════════════════════════════════════════════════════════
# B2B ENDPOINTS — Syroce Acente Sistemi (API Key Auth)
# ═════════════════════════════════════════════════════════════════


# ═════════════════════════════════════════════════════════════════
# WEBHOOK ENDPOINTS — (API Key Auth)
# ═════════════════════════════════════════════════════════════════

VALID_WEBHOOK_EVENTS = {"reservation.created", "reservation.cancelled", "reservation.updated", "rates.updated", "availability.updated"}


# ═════════════════════════════════════════════════════════════════
# GUEST & LOYALTY — Misafir ve Sadakat Programi
# ═════════════════════════════════════════════════════════════════


class LoyaltyPointsUpdate(BaseModel):
    points: int = Field(..., gt=0, le=100000)
    reason: str = Field(..., min_length=1)
    operation: str = "add"


# ═════════════════════════════════════════════════════════════════
# HOUSEKEEPING — Kat Hizmetleri
# ═════════════════════════════════════════════════════════════════


class HousekeepingStatusUpdate(BaseModel):
    status: str
    notes: str = ""


# ═════════════════════════════════════════════════════════════════
# KBS / POLICE NOTIFICATION — Emniyet Bildirim Sistemi
# ═════════════════════════════════════════════════════════════════


class KBSReportCreate(BaseModel):
    date: str
    guest_ids: list[str] = []
    notes: str = ""


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


# ═════════════════════════════════════════════════════════════════
# LOST & FOUND — Kayip Esya
# ═════════════════════════════════════════════════════════════════


class LostFoundCreate(BaseModel):
    item_name: str
    description: str = ""
    category: str = "other"
    location_found: str = ""
    found_by: str = ""
    guest_name: str = ""
    room_number: str = ""


class LostFoundUpdate(BaseModel):
    status: str | None = None
    guest_name: str | None = None
    notes: str | None = None
    claimed_by: str | None = None


# ═════════════════════════════════════════════════════════════════
# WAKE-UP CALLS — Uyandirma Servisi
# ═════════════════════════════════════════════════════════════════


class WakeUpCallCreate(BaseModel):
    room_number: str
    guest_name: str
    wake_date: str  # YYYY-MM-DD
    wake_time: str  # HH:MM
    notes: str = ""
    recurring: bool = False
    recurring_until: str = ""  # YYYY-MM-DD


class WakeUpCallUpdate(BaseModel):
    wake_time: str | None = None
    status: str | None = None
    notes: str | None = None


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


class B2BGuestRequest(BaseModel):
    booking_id: str
    request_type: str  # concierge, spa, room_service, maintenance, transport, other
    description: str
    priority: str = "normal"


# ═════════════════════════════════════════════════════════════════
# CONCIERGE & SPA — Concierge ve Spa Hizmetleri
# ═════════════════════════════════════════════════════════════════


class ConciergeRequest(BaseModel):
    booking_id: str
    service_id: str
    description: str = ""
    preferred_date: str = ""
    preferred_time: str = ""
    guest_count: int = 1


class SpaBookingCreate(BaseModel):
    booking_id: str
    service_id: str
    preferred_date: str  # YYYY-MM-DD
    preferred_time: str  # HH:MM
    guest_count: int = 1
    notes: str = ""


# ═════════════════════════════════════════════════════════════════
# MICE & GROUPS — Grup ve Toplanti Yonetimi
# ═════════════════════════════════════════════════════════════════


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


class RoomingListEntry(BaseModel):
    guest_name: str
    room_type: str = ""
    check_in: str = ""
    check_out: str = ""
    special_requests: str = ""


class RoomingListUpload(BaseModel):
    guests: list[RoomingListEntry]


# ═════════════════════════════════════════════════════════════════
# FOLIO & BILLING — Folio ve Fatura
# ═════════════════════════════════════════════════════════════════


class FolioChargeCreate(BaseModel):
    charge_type: str  # room, minibar, restaurant, spa, laundry, phone, other
    description: str = Field(..., min_length=1)
    amount: float = Field(..., gt=0, le=1000000)
    quantity: int = Field(1, ge=1, le=9999)


router = APIRouter(prefix="/api/b2b", tags=["B2B API - Syroce"])


# ── GET /hotel-info ──
@router.get("/hotel-info")
async def b2b_get_hotel_info(agency: dict = Depends(get_b2b_agency)):
    """Discovery endpoint: minimal otel kartı (acente onboarding icin).

    `/content` farkli olarak `published_content` flag'ine BAGIMLI DEGIL — her
    aktif API key sahibi acente otelin temel bilgilerine ulasabilir, boylece
    Syroce Agency programi otel listesini olusturup eslesirme yapabilir.
    """
    tenant_id = agency["tenant_id"]

    tenant = (
        await db.tenants.find_one(
            {"id": tenant_id},
            {"_id": 0, "name": 1, "currency": 1, "country": 1, "city": 1, "address": 1, "phone": 1, "email": 1, "website": 1, "timezone": 1, "property_type": 1, "star_rating": 1},
        )
        or {}
    )

    # Lightweight room type catalog (no rates, no availability)
    rooms = await db.rooms.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "room_type": 1, "capacity": 1, "base_price": 1, "bed_type": 1},
    ).to_list(2000)
    rt_summary = {}
    for r in rooms:
        rt = r.get("room_type", "Standard")
        if rt not in rt_summary:
            rt_summary[rt] = {
                "room_type": rt,
                "capacity": r.get("capacity", 2),
                "base_price": r.get("base_price", 0),
                "bed_type": r.get("bed_type", ""),
                "total_rooms": 0,
            }
        rt_summary[rt]["total_rooms"] += 1

    return {
        "tenant_id": tenant_id,
        "hotel": {
            "name": tenant.get("name", ""),
            "currency": tenant.get("currency", "TRY"),
            "country": tenant.get("country", ""),
            "city": tenant.get("city", ""),
            "address": tenant.get("address", ""),
            "phone": tenant.get("phone", ""),
            "email": tenant.get("email", ""),
            "website": tenant.get("website", ""),
            "timezone": tenant.get("timezone", "Europe/Istanbul"),
            "property_type": tenant.get("property_type", "hotel"),
            "star_rating": tenant.get("star_rating"),
        },
        "agency": {
            "id": agency.get("agency_id"),
            "name": agency.get("agency_name", ""),
            "commission_rate": agency.get("commission_rate", 0),
        },
        "room_types": list(rt_summary.values()),
        "content_published": bool(
            await db.agencies.find_one(
                {"id": agency.get("agency_id"), "tenant_id": tenant_id, "published_content": True},
                {"_id": 1},
            )
        ),
    }


# ── GET /content ──
@router.get("/content")
async def b2b_get_content(agency: dict = Depends(get_b2b_agency)):
    """Otel icerigini getir (oda tipleri, hizmetler, genel bilgi)."""
    tenant_id = agency["tenant_id"]
    agency_id = agency["agency_id"]

    # Check if content is published to this agency
    agency_doc = await db.agencies.find_one({"id": agency_id, "tenant_id": tenant_id}, {"_id": 0})
    if not agency_doc or not agency_doc.get("published_content"):
        return {
            "published": False,
            "message": "Bu acente icin henuz icerik yayinlanmamis",
            "hotel_content": None,
        }

    content = await db.hotel_content.find_one({"tenant_id": tenant_id}, {"_id": 0, "id": 0})
    if not content:
        return {"published": False, "hotel_content": None}

    content.pop("tenant_id", None)
    return {"published": True, "hotel_content": content}


# ── GET /availability ──
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
        booked = await db.bookings.count_documents(
            {
                "tenant_id": tenant_id,
                "room_id": {"$in": rt_data["room_ids"]},
                "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
                "check_in": {"$lt": check_out + "T23:59:59"},
                "check_out": {"$gt": check_in + "T00:00:00"},
            }
        )
        rt_data["available_rooms"] = max(0, rt_data["total_rooms"] - booked)
        del rt_data["room_ids"]

    results = list(room_types.values())
    return {
        "check_in": check_in,
        "check_out": check_out,
        "room_types": results,
    }


# ── GET /rates ──
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

    rates = await db.agency_rate_calendar.find(query, {"_id": 0, "tenant_id": 0, "agency_id": 0, "updated_by": 0}).sort("date", 1).to_list(5000)

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
        rates = await db.hr_rate_calendar.find(base_query, {"_id": 0, "tenant_id": 0, "updated_by": 0}).sort("date", 1).to_list(5000)

        if not rates:
            rates = await db.rate_calendar.find(base_query, {"_id": 0, "tenant_id": 0, "updated_by": 0}).sort("date", 1).to_list(5000)

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


# ── POST /reservations ──
async def _b2b_create_reservation_impl(
    data: B2BReservationCreate,
    background_tasks: BackgroundTasks,
    tenant_id: str,
    agency_id: str,
    agency: dict,
    idempotency_key: str | None = None,
) -> dict:
    """Core B2B reservation creation. Returns the success response dict.

    Wrapped by the route below so optional Idempotency-Key handling stays additive
    and the legacy (no-header) path is byte-identical to the original behaviour.

    When ``idempotency_key`` is supplied the created booking is stamped with it
    (``b2b_idempotency_key``) so a post-crash retry that took over an abandoned
    sentinel can find the existing booking and replay it instead of creating a
    second one. Additive field, B2B path only (None => legacy, no stamp).
    """
    try:
        ci = datetime.fromisoformat(data.check_in + "T14:00:00+00:00")
        co = datetime.fromisoformat(data.check_out + "T11:00:00+00:00")
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail="Gecersiz tarih formati. YYYY-MM-DD kullanin.")
    if co <= ci:
        raise HTTPException(status_code=400, detail="check_out, check_in'den sonra olmali")

    # Partner contract layer (T002): one consolidated read of the agency's
    # effective terms. Contract value wins; no-contract agencies fall back to
    # the legacy commission. Credit/allotment are surfaced read-only here and
    # HARD-enforced in T003.
    snapshot = await build_snapshot(tenant_id, agency_id, agency_doc=agency)
    # Opt-in contract room-type restriction (empty allowed_room_types => no limit).
    if not snapshot.is_room_type_allowed(data.room_type):
        raise HTTPException(
            status_code=422,
            detail=f"Oda tipi '{data.room_type}' sozlesme kapsaminda degil",
        )

    rooms = await db.rooms.find({"tenant_id": tenant_id, "room_type": data.room_type}, {"_id": 0}).to_list(500)

    if not rooms:
        raise HTTPException(status_code=404, detail="Oda tipi bulunamadi")

    available_room = None
    for room in rooms:
        conflict = await db.bookings.count_documents(
            {
                "tenant_id": tenant_id,
                "room_id": room["id"],
                "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
                "check_in": {"$lt": data.check_out + "T23:59:59"},
                "check_out": {"$gt": data.check_in + "T00:00:00"},
            }
        )
        if conflict == 0:
            available_room = room
            break

    if not available_room:
        raise HTTPException(status_code=409, detail="Secilen tarihler icin musait oda bulunamadi")

    commission_rate = snapshot.commission_pct
    agency_name = agency.get("agency_name", "")

    booking_id = _uuid()
    confirmation_code = f"B2B-{booking_id[:8].upper()}"
    nights = (co - ci).days
    total = data.total_amount if data.total_amount > 0 else available_room.get("base_price", 0) * max(nights, 1)
    commission_amount = round(total * commission_rate / 100, 2)

    # T003: HARD, race-safe allotment + credit reservation BEFORE any persistence.
    # Opt-in (returns None when uncapped). Saga-compensated (released) if the
    # booking cannot be completed. GuardRejection => deterministic business reject
    # (cached failed_final by the idempotency layer; a retry replays it, no double
    # reserve). Reserve allotment first, then credit; release in reverse on failure.
    allot_handle = None
    credit_handle = None
    try:
        allot_handle = await reserve_allotment(
            snapshot,
            available_room.get("room_type", data.room_type),
            data.check_in,
            data.check_out,
        )
        credit_handle = await reserve_credit(snapshot, total)

        # Create guest
        guest_id = _uuid()
        from security.guest_write import encrypt_guest_insert

        await db.guests.insert_one(
            encrypt_guest_insert(
                {
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
                }
            )
        )

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
        if idempotency_key:
            # Idempotency RECOVER backstop: stamp the key onto the booking so a
            # post-crash retry (which took over an abandoned sentinel) can find
            # THIS booking and replay it instead of creating a duplicate. Additive
            # field, persisted atomically with the booking; B2B path only.
            booking_doc["b2b_idempotency_key"] = idempotency_key
        # v106 architect follow-up (race-safety): direct insert_one bypassed
        # the room_night_locks atomic guard → double-booking risk on B2B API
        # bookings. Now routed through create_booking_atomic.
        booking_doc = await create_booking_atomic(tenant_id=tenant_id, booking_doc=booking_doc)
    except GuardRejection as gr:
        await release_credit(credit_handle)
        await release_allotment(allot_handle)
        raise HTTPException(status_code=gr.status_code, detail=gr.detail)
    except BookingConflictError as conflict_err:
        await release_credit(credit_handle)
        await release_allotment(allot_handle)
        raise HTTPException(status_code=409, detail=str(conflict_err))
    except DuplicateKeyError:
        # Durable idempotency backstop tripped: a concurrent retry under the SAME
        # Idempotency-Key already created this booking while we were mid-flight
        # (slow-owner takeover race — the original owner exceeded the processing
        # lock, this retry took over, found no booking yet, and we collided on
        # insert). Release the counters WE reserved (the winning request holds its
        # own), then replay the existing booking instead of surfacing an error or
        # creating a duplicate. The only unique index this path can violate is
        # uniq_b2b_booking_idem_key (partial on a string key), so this branch is
        # unreachable for the keyless legacy path.
        await release_credit(credit_handle)
        await release_allotment(allot_handle)
        existing = (
            await db.bookings.find_one(
                {
                    "tenant_id": tenant_id,
                    "agency_id": agency_id,
                    "b2b_idempotency_key": idempotency_key,
                },
                {"_id": 0},
            )
            if idempotency_key
            else None
        )
        if existing is not None:
            return _b2b_reservation_response_from_booking(existing)
        raise
    except Exception:
        await release_credit(credit_handle)
        await release_allotment(allot_handle)
        raise

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


def _b2b_reservation_response_from_booking(b: dict) -> dict:
    """Rebuild the create-reservation success response from a persisted booking.

    Used ONLY by the idempotency RECOVER path: a prior attempt created the booking
    but its process crashed before finalizing the sentinel. We replay the same
    logical result from the stored booking instead of creating a second one
    (no double-create). check_in/check_out are stored with T-times, so we trim
    back to the YYYY-MM-DD shape the create response uses.
    """
    cc = b.get("confirmation_code", "")
    return {
        "ok": True,
        "reservation": {
            "id": b.get("id"),
            "confirmation_code": cc,
            "status": b.get("status", "confirmed"),
            "room_type": b.get("room_type", ""),
            "room_number": b.get("room_number", ""),
            "check_in": (b.get("check_in") or "")[:10],
            "check_out": (b.get("check_out") or "")[:10],
            "guest_name": b.get("guest_name", ""),
            "total_amount": b.get("total_amount"),
            "commission_rate": b.get("agency_commission_rate"),
            "commission_amount": b.get("agency_commission_amount"),
            "created_at": b.get("created_at"),
        },
        "message": f"Rezervasyon olusturuldu: {cc}",
    }


@router.post("/reservations")
async def b2b_create_reservation(
    data: B2BReservationCreate,
    background_tasks: BackgroundTasks,
    idempotency_key: str | None = Header(None, alias="Idempotency-Key"),
    agency: dict = Depends(get_b2b_agency),
):
    """Rezervasyon olustur — otomatik PMS'e duser.

    Idempotency: istemci `Idempotency-Key` (UUID) basligi gonderirse, ayni istegin
    tekrari (ornegin timeout sonrasi yeniden deneme) ikinci bir rezervasyon
    olusturmaz; orijinal yanit aynen dondurulur. Baslik gonderilmezse eski davranis
    aynen korunur (geriye uyumlu).
    """
    tenant_id = agency["tenant_id"]
    agency_id = agency["agency_id"]

    # Geriye uyumlu yol: Idempotency-Key yoksa eski davranis.
    if not idempotency_key:
        return await _b2b_create_reservation_impl(
            data,
            background_tasks,
            tenant_id,
            agency_id,
            agency,
        )

    from services.b2b_booking_idempotency import (
        begin as _idem_begin,
    )
    from services.b2b_booking_idempotency import (
        finalize_failure as _idem_fail,
    )
    from services.b2b_booking_idempotency import (
        finalize_success as _idem_ok,
    )

    idem = await _idem_begin(tenant_id, agency_id, idempotency_key, data.model_dump())
    action = idem["action"]
    if action == "replay":
        # Orijinal sonucu (basari ya da is-kurali hatasi) aynen don.
        return JSONResponse(status_code=idem["status_code"], content=idem["body"])
    if action == "conflict":
        raise HTTPException(
            status_code=409,
            detail="Idempotency-Key daha once farkli bir istek govdesiyle kullanildi",
        )
    if action == "in_flight":
        raise HTTPException(
            status_code=429,
            detail="Ayni Idempotency-Key su an isleniyor, lutfen tekrar deneyin",
            headers={"Retry-After": "2"},
        )

    if action == "recover":
        # Onceki bir deneme bu anahtarla bir rezervasyon olusturmus, ancak sentinel'i
        # "succeeded" olarak isaretleyemeden (proses cokmesi / Mongo hatasi) dusmus
        # olabilir. Cift-create'i onlemek icin once ayni anahtarla damgalanmis bir
        # booking var mi diye bak; varsa orijinal sonucu yeniden uret ve don.
        existing = await db.bookings.find_one(
            {
                "tenant_id": tenant_id,
                "agency_id": agency_id,
                "b2b_idempotency_key": idempotency_key,
            },
            {"_id": 0},
        )
        if existing is not None:
            response = _b2b_reservation_response_from_booking(existing)
            await _idem_ok(
                tenant_id,
                agency_id,
                idempotency_key,
                200,
                response,
                booking_id=existing.get("id"),
            )
            return response
        # Damgalanmis booking yok -> onceki deneme create'ten ONCE coktu;
        # normal create yoluna devam et (asagidaki proceed mantigi).

    # action in ("proceed", "recover-without-existing-booking"): bu istek anahtarin sahibi.
    try:
        response = await _b2b_create_reservation_impl(
            data,
            background_tasks,
            tenant_id,
            agency_id,
            agency,
            idempotency_key=idempotency_key,
        )
    except HTTPException as he:
        # Is-kurali 4xx -> kalici (ayni anahtarla yeniden deneme ayni hatayi alir).
        # Beklenmeyen 5xx -> tekrar denenebilir (sentinel silinir).
        await _idem_fail(
            tenant_id,
            agency_id,
            idempotency_key,
            he.status_code,
            {"ok": False, "detail": he.detail},
            terminal=(400 <= he.status_code < 500),
        )
        raise
    except Exception:
        await _idem_fail(
            tenant_id,
            agency_id,
            idempotency_key,
            500,
            {"ok": False, "detail": "Sunucu hatasi"},
            terminal=False,
        )
        raise

    await _idem_ok(
        tenant_id,
        agency_id,
        idempotency_key,
        200,
        response,
        booking_id=response.get("reservation", {}).get("id"),
    )
    return response


# ── GET /reservations ──
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

    docs = (
        await db.bookings.find(
            query,
            {
                "_id": 0,
                "tenant_id": 0,
                "guest_id": 0,
                "room_id": 0,
                "updated_by": 0,
            },
        )
        .sort("created_at", -1)
        .to_list(limit)
    )

    return {"reservations": docs, "count": len(docs)}


# ── GET /reservations/{reservation_id} ──
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


# ── PUT /reservations/{reservation_id}/cancel ──
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
        {
            "$set": {
                "status": "cancelled",
                "cancelled_at": _now_iso(),
                "cancelled_by": f"b2b_api:{agency_id}",
                "updated_at": _now_iso(),
            }
        },
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
