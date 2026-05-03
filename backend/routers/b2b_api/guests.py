"""
guests

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
import hmac
import json
import logging
import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from core.atomic_booking import BookingConflictError, create_booking_atomic
from core.database import db
from core.security import _is_super_admin, get_current_user
from core.tenant_db import set_tenant_context
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v101 DW

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









# ═════════════════════════════════════════════════════════════════
# B2B ENDPOINTS — Syroce Acente Sistemi (API Key Auth)
# ═════════════════════════════════════════════════════════════════















# ═════════════════════════════════════════════════════════════════
# WEBHOOK ENDPOINTS — (API Key Auth)
# ═════════════════════════════════════════════════════════════════

VALID_WEBHOOK_EVENTS = {"reservation.created", "reservation.cancelled", "reservation.updated"}










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


# ── GET /guests/search ──
@router.get("/guests/search")
async def b2b_search_guests(
    q: str = Query(..., min_length=2, description="Isim, e-posta veya telefon ile arama"),
    limit: int = Query(20, le=100),
    agency: dict = Depends(get_b2b_agency),
):
    """Misafir arama — isim, e-posta veya telefon ile."""
    tenant_id = agency["tenant_id"]
    from security.query_safety import safe_search_term
    _s = safe_search_term(q)
    if not _s:
        return {"guests": [], "count": 0}
    regex = {"$regex": _s, "$options": "i"}
    docs = await db.guests.find(
        {"tenant_id": tenant_id, "$or": [{"name": regex}, {"email": regex}, {"phone": regex}]},
        {"_id": 0, "tenant_id": 0},
    ).sort("name", 1).to_list(limit)
    return {"guests": docs, "count": len(docs)}
# ── GET /guests/{guest_id} ──
@router.get("/guests/{guest_id}")
async def b2b_get_guest(guest_id: str, agency: dict = Depends(get_b2b_agency)):
    """Misafir profil detayi."""
    tenant_id = agency["tenant_id"]
    # v64 Bug DA: cross-agency IDOR guard — sadece kendi rezervasyonu olan misafir
    if not await _agency_owns_guest(tenant_id, agency["agency_id"], guest_id):
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")
    doc = await db.guests.find_one(
        {"tenant_id": tenant_id, "id": guest_id}, {"_id": 0, "tenant_id": 0}
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")
    return {"guest": doc}
# ── GET /guests/{guest_id}/loyalty ──
@router.get("/guests/{guest_id}/loyalty")
async def b2b_get_guest_loyalty(guest_id: str, agency: dict = Depends(get_b2b_agency)):
    """Misafir sadakat bilgisi — puan, tier, toplam konaklama."""
    tenant_id = agency["tenant_id"]
    # v64 Bug DA: cross-agency IDOR guard
    if not await _agency_owns_guest(tenant_id, agency["agency_id"], guest_id):
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")
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
# ── POST /guests/{guest_id}/loyalty/points ──
@router.post("/guests/{guest_id}/loyalty/points")
async def b2b_update_loyalty_points(
    guest_id: str,
    data: LoyaltyPointsUpdate,
    agency: dict = Depends(get_b2b_agency),
):
    """Sadakat puani ekle veya cikar."""
    tenant_id = agency["tenant_id"]

    # v64 Bug DA: cross-agency IDOR guard — kritik (yazma + mali sahtekarlik)
    if not await _agency_owns_guest(tenant_id, agency["agency_id"], guest_id):
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")

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
        # v109 round-9 IDOR DiD: pin tenant on update.
        {"_id": guest["_id"], "tenant_id": tenant_id},
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
# ── GET /guests/{guest_id}/stays ──
@router.get("/guests/{guest_id}/stays")
async def b2b_get_guest_stays(
    guest_id: str,
    limit: int = Query(50, le=200),
    agency: dict = Depends(get_b2b_agency),
):
    """Misafir konaklama gecmisi."""
    tenant_id = agency["tenant_id"]
    # v64 Bug DA: cross-agency IDOR guard
    if not await _agency_owns_guest(tenant_id, agency["agency_id"], guest_id):
        raise HTTPException(status_code=404, detail="Misafir bulunamadi")
    bookings = await db.bookings.find(
        {"tenant_id": tenant_id, "agency_id": agency["agency_id"], "guest_id": guest_id},
        {"_id": 0, "tenant_id": 0, "guest_id": 0},
    ).sort("check_in", -1).to_list(limit)
    return {"stays": bookings, "count": len(bookings)}
