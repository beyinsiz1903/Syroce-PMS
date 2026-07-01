"""
webhooks

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
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from core.database import db
from core.security import _is_super_admin
from models.schemas import User

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

    return await authenticate_b2b_agency(x_api_key, required_scope="webhooks")


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


# ── POST /webhooks ──
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

    existing = await sysdb.agency_webhooks.count_documents(
        {
            "agency_id": agency_id,
            "tenant_id": tenant_id,
            "is_active": True,
        }
    )
    if existing >= 5:
        raise HTTPException(status_code=400, detail="Maximum 5 active webhooks per agency")

    # Auto-generate HMAC signing secret if client did not supply one. The raw
    # secret is returned ONCE here and is required for verifying webhook
    # signatures on the receiver side.
    import secrets as _secrets

    auto_generated_secret = False
    secret_value = (data.secret or "").strip()
    if not secret_value:
        secret_value = f"whsec_{_secrets.token_urlsafe(32)}"
        auto_generated_secret = True

    webhook_id = _uuid()
    doc = {
        "id": webhook_id,
        "tenant_id": tenant_id,
        "agency_id": agency_id,
        "url": data.url,
        "events": list(set(data.events)),
        "secret": secret_value,
        "is_active": True,
        "created_at": _now_iso(),
    }
    await sysdb.agency_webhooks.insert_one(doc)
    doc.pop("_id", None)

    return {
        "ok": True,
        "webhook": {
            "id": webhook_id,
            "url": data.url,
            "events": doc["events"],
            "is_active": True,
            "created_at": doc["created_at"],
        },
        "secret": secret_value,
        "secret_auto_generated": auto_generated_secret,
        "message": ("Webhook kaydedildi. Bu secret SADECE bir kez gosterilir — imza dogrulamak icin guvenli sekilde saklayin.") if auto_generated_secret else "Webhook kaydedildi",
    }


# ── GET /webhooks ──
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


# ── DELETE /webhooks/{webhook_id} ──
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


# ── POST /webhooks/{webhook_id}/test ──
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
    # v109 Bug DAL round-7 follow-up #3: webhook URL is tenant-configurable.
    # Use rebinding-safe helper instead of raw httpx client.
    from integrations.xchange.safety import EgressDenied, safe_post_async

    try:
        resp = await safe_post_async(wh["url"], timeout=10, content=body, headers=headers)
        status_code = resp.status_code
    except EgressDenied as exc:
        error_msg = f"SSRF engellendi: {exc}"
    except Exception as exc:
        error_msg = str(exc)

    return {
        "ok": error_msg is None and 200 <= status_code < 300,
        "delivery_id": delivery_id,
        "status_code": status_code,
        "error": error_msg,
        "message": "Test olayi gonderildi" if not error_msg else f"Teslimat hatasi: {error_msg}",
    }
