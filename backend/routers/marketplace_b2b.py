"""Syroce Marketplace v1 — Cross-tenant B2B köprüsü.

Bu modül, Syroce Agent (acente otomasyonu) gibi dış uygulamaların birden çok
Syroce-PMS otelini tek API anahtarı ile aramasına, fiyatları görmesine ve
rezervasyon oluşturmasına olanak tanır.

Mimari farklar (mevcut /api/b2b ile karşılaştırma):
  • API key TENANT-BAĞIMSIZ tutulur (sysdb.marketplace_api_keys).
  • Otel kendi marketplace listing'ini açar/kapar (db.marketplace_listings, per-tenant).
  • Tüm agency endpoint'leri her istekte hangi otele yönelik olduğunu kabul eder
    (`tenant_id` veya `hotel_code` parametresi). Her istek için tenant context
    geçici olarak set edilir, sonra resetlenir.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field

from core.atomic_booking import BookingConflictError, create_booking_atomic
from core.database import db
from core.security import get_current_user
from core.tenant_db import get_system_db, tenant_context
from models.schemas import User

# Server-side fiyat hesaplamasının istemciden gelen total_amount'tan tolerans
# (TRY) — bu eşiği aşan farklarda istek reddedilir (price-spoofing koruması).
PRICE_TOLERANCE = 0.50

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/marketplace/v1", tags=["Marketplace v1"])


# ─── Helpers ──────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _require_hotel_admin(user: User) -> str:
    """Otel admin/sahibi rollerini doğrular ve tenant_id döner."""
    if user.role in ("agency_admin", "agency_agent"):
        raise HTTPException(403, "Acente kullanıcıları otel listing yönetemez")
    if not user.tenant_id:
        raise HTTPException(403, "Geçerli bir otel kiracısı yok")
    return user.tenant_id


def _require_system_admin(token: str | None = Header(None, alias="X-Marketplace-Admin-Token")) -> bool:
    """Sistem yöneticisi yetkisi: env var ile koruma.

    Production'da gerçek bir super-admin paneline bağlanır; MVP için
    MARKETPLACE_ADMIN_TOKEN env variable'ı yeterli.
    """
    expected = os.getenv("MARKETPLACE_ADMIN_TOKEN")
    if not expected:
        raise HTTPException(503, "Marketplace admin yapılandırılmamış")
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(401, "Geçersiz marketplace admin token")
    return True


# ─── Cross-tenant Agency Auth ─────────────────────────────────────────────

async def get_marketplace_agency(x_api_key: str = Header(..., alias="X-API-Key")) -> dict:
    """Cross-tenant API key doğrulama. Tenant context BURADA SET EDİLMEZ;
    her endpoint istek bazında set eder."""
    sysdb = get_system_db()
    key_hash = _hash_key(x_api_key)

    key_doc = await sysdb.marketplace_api_keys.find_one(
        {"key_hash": key_hash, "is_active": True}, {"_id": 0}
    )
    if not key_doc:
        raise HTTPException(401, "Geçersiz veya devre dışı marketplace API key")

    agency = await sysdb.marketplace_agencies.find_one(
        {"id": key_doc["agency_id"], "status": "active"}, {"_id": 0}
    )
    if not agency:
        raise HTTPException(403, "Marketplace acentesi aktif değil")

    await sysdb.marketplace_api_keys.update_one(
        {"key_hash": key_hash},
        {"$set": {"last_used_at": _now_iso()}, "$inc": {"usage_count": 1}},
    )

    return {
        "agency_id": agency["id"],
        "agency_name": agency.get("name", ""),
        "default_commission_pct": agency.get("default_commission_pct", 12.0),
        "contact_email": agency.get("contact_email", ""),
    }


async def _get_listing_or_404(tenant_id: str) -> dict:
    """Bir otelin marketplace listing'ini döner. Liste edilmemişse 404."""
    sysdb = get_system_db()
    listing = await sysdb.marketplace_listings.find_one(
        {"tenant_id": tenant_id, "is_listed": True}, {"_id": 0}
    )
    if not listing:
        raise HTTPException(404, "Bu otel marketplace'te listelenmemiş")
    return listing


def _commission_for(agency: dict, listing: dict) -> float:
    """Listing'de komisyon override varsa onu, yoksa agency default'unu kullan."""
    pct = listing.get("commission_pct")
    if pct is None:
        pct = agency.get("default_commission_pct", 12.0)
    return float(pct)


# ─── Pydantic Modelleri ───────────────────────────────────────────────────

class MarketplaceAgencyCreate(BaseModel):
    name: str
    contact_email: str = ""
    contact_phone: str = ""
    country: str = "TR"
    default_commission_pct: float = Field(default=12.0, ge=0, le=100)


class MarketplaceListingCreate(BaseModel):
    hotel_name: str
    city: str
    country: str = "TR"
    address: str = ""
    description: str = ""
    photos: list[str] = []
    amenities: list[str] = []
    star_rating: int | None = Field(default=None, ge=1, le=5)
    commission_pct: float | None = Field(default=None, ge=0, le=100)
    allowed_room_types: list[str] = []
    blocked_dates: list[str] = []  # YYYY-MM-DD


class MarketplaceListingUpdate(BaseModel):
    hotel_name: str | None = None
    city: str | None = None
    country: str | None = None
    address: str | None = None
    description: str | None = None
    photos: list[str] | None = None
    amenities: list[str] | None = None
    star_rating: int | None = Field(default=None, ge=1, le=5)
    commission_pct: float | None = Field(default=None, ge=0, le=100)
    allowed_room_types: list[str] | None = None
    blocked_dates: list[str] | None = None
    is_listed: bool | None = None


class MarketplaceSearchRequest(BaseModel):
    check_in: str  # YYYY-MM-DD
    check_out: str  # YYYY-MM-DD
    adults: int = 2
    children: int = 0
    city: str | None = None
    country: str | None = None
    q: str | None = None
    max_price: float | None = None
    limit: int = Field(default=50, le=200)


class MarketplaceReservationCreate(BaseModel):
    tenant_id: str
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
    external_reference: str = ""  # Acentenin kendi PNR/voucher kodu


# ═══════════════════════════════════════════════════════════════════════
# SYSTEM ADMIN — Marketplace Agency Yönetimi
# ═══════════════════════════════════════════════════════════════════════

@router.post("/admin/agencies")
async def admin_create_agency(
    data: MarketplaceAgencyCreate,
    _: bool = Depends(_require_system_admin),
):
    """Yeni marketplace acentesi oluştur ve ilk API key'i döndür.

    API key sadece bir kez gösterilir; saklanması acentenin sorumluluğundadır.
    """
    sysdb = get_system_db()

    agency_id = _uuid()
    agency_doc = {
        "id": agency_id,
        "name": data.name.strip(),
        "contact_email": data.contact_email.strip(),
        "contact_phone": data.contact_phone.strip(),
        "country": data.country,
        "default_commission_pct": data.default_commission_pct,
        "status": "active",
        "created_at": _now_iso(),
    }
    await sysdb.marketplace_agencies.insert_one(agency_doc)

    raw_key = f"syroce_mkt_{secrets.token_urlsafe(32)}"
    key_doc = {
        "id": _uuid(),
        "agency_id": agency_id,
        "key_hash": _hash_key(raw_key),
        "key_prefix": raw_key[:18] + "...",
        "is_active": True,
        "usage_count": 0,
        "created_at": _now_iso(),
        "last_used_at": None,
    }
    await sysdb.marketplace_api_keys.insert_one(key_doc)

    return {
        "agency": {k: v for k, v in agency_doc.items() if k != "_id"},
        "api_key": raw_key,
        "key_prefix": key_doc["key_prefix"],
        "warning": "Bu API key sadece bir kez gösterilir. Güvenli bir yerde saklayın.",
    }


@router.get("/admin/agencies")
async def admin_list_agencies(_: bool = Depends(_require_system_admin)):
    sysdb = get_system_db()
    docs = await sysdb.marketplace_agencies.find({}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"agencies": docs, "total": len(docs)}


@router.delete("/admin/agencies/{agency_id}")
async def admin_disable_agency(
    agency_id: str,
    _: bool = Depends(_require_system_admin),
):
    sysdb = get_system_db()
    res = await sysdb.marketplace_agencies.update_one(
        {"id": agency_id}, {"$set": {"status": "disabled", "disabled_at": _now_iso()}}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Acente bulunamadı")
    await sysdb.marketplace_api_keys.update_many(
        {"agency_id": agency_id, "is_active": True},
        {"$set": {"is_active": False, "revoked_at": _now_iso()}},
    )
    return {"ok": True, "message": "Acente devre dışı bırakıldı, tüm API key'ler iptal edildi"}


@router.post("/admin/agencies/{agency_id}/api-keys/regenerate")
async def admin_regenerate_key(
    agency_id: str,
    _: bool = Depends(_require_system_admin),
):
    sysdb = get_system_db()
    agency = await sysdb.marketplace_agencies.find_one({"id": agency_id}, {"_id": 0})
    if not agency:
        raise HTTPException(404, "Acente bulunamadı")

    await sysdb.marketplace_api_keys.update_many(
        {"agency_id": agency_id, "is_active": True},
        {"$set": {"is_active": False, "revoked_at": _now_iso()}},
    )
    raw_key = f"syroce_mkt_{secrets.token_urlsafe(32)}"
    await sysdb.marketplace_api_keys.insert_one({
        "id": _uuid(),
        "agency_id": agency_id,
        "key_hash": _hash_key(raw_key),
        "key_prefix": raw_key[:18] + "...",
        "is_active": True,
        "usage_count": 0,
        "created_at": _now_iso(),
        "last_used_at": None,
    })
    return {"api_key": raw_key, "warning": "Bu key sadece bir kez gösterilir"}


# ═══════════════════════════════════════════════════════════════════════
# HOTEL ADMIN — Marketplace Listing (Opt-in)
# ═══════════════════════════════════════════════════════════════════════

@router.post("/listings/me")
async def listing_opt_in(
    data: MarketplaceListingCreate,
    current_user: User = Depends(get_current_user),
):
    """Bu oteli marketplace'e listele (opt-in)."""
    tenant_id = _require_hotel_admin(current_user)
    sysdb = get_system_db()

    existing = await sysdb.marketplace_listings.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if existing and existing.get("is_listed"):
        raise HTTPException(409, "Otel zaten marketplace'te listelenmiş, güncellemek için PUT kullanın")

    doc = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "hotel_name": data.hotel_name.strip(),
        "city": data.city.strip().title(),
        "country": data.country,
        "address": data.address.strip(),
        "description": data.description.strip(),
        "photos": data.photos or [],
        "amenities": data.amenities or [],
        "star_rating": data.star_rating,
        "commission_pct": data.commission_pct,
        "allowed_room_types": data.allowed_room_types or [],
        "blocked_dates": data.blocked_dates or [],
        "is_listed": True,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "created_by": current_user.id,
    }
    if existing:
        await sysdb.marketplace_listings.update_one(
            {"tenant_id": tenant_id}, {"$set": {**{k: v for k, v in doc.items() if k != "id"}, "id": existing["id"]}}
        )
        doc["id"] = existing["id"]
    else:
        await sysdb.marketplace_listings.insert_one(doc)
    doc.pop("_id", None)
    return {"ok": True, "listing": doc}


@router.get("/listings/me")
async def listing_get_mine(current_user: User = Depends(get_current_user)):
    tenant_id = _require_hotel_admin(current_user)
    sysdb = get_system_db()
    listing = await sysdb.marketplace_listings.find_one({"tenant_id": tenant_id}, {"_id": 0})
    if not listing:
        return {"is_listed": False, "listing": None}
    return {"is_listed": listing.get("is_listed", False), "listing": listing}


@router.put("/listings/me")
async def listing_update_mine(
    data: MarketplaceListingUpdate,
    current_user: User = Depends(get_current_user),
):
    tenant_id = _require_hotel_admin(current_user)
    sysdb = get_system_db()
    update = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None}
    if not update:
        raise HTTPException(400, "Güncellenecek alan yok")
    update["updated_at"] = _now_iso()
    res = await sysdb.marketplace_listings.update_one({"tenant_id": tenant_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(404, "Listing bulunamadı, önce opt-in yapın")
    listing = await sysdb.marketplace_listings.find_one({"tenant_id": tenant_id}, {"_id": 0})
    return {"ok": True, "listing": listing}


@router.delete("/listings/me")
async def listing_opt_out(current_user: User = Depends(get_current_user)):
    tenant_id = _require_hotel_admin(current_user)
    sysdb = get_system_db()
    res = await sysdb.marketplace_listings.update_one(
        {"tenant_id": tenant_id},
        {"$set": {"is_listed": False, "updated_at": _now_iso()}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Listing yok")
    return {"ok": True, "message": "Otel marketplace'ten çıkarıldı"}


# ═══════════════════════════════════════════════════════════════════════
# AGENCY (X-API-Key) — Hotel Discovery & Search
# ═══════════════════════════════════════════════════════════════════════

@router.get("/hotels")
async def agency_list_hotels(
    city: str | None = Query(None),
    country: str | None = Query(None),
    q: str | None = Query(None, description="Ad veya açıklamada ara"),
    limit: int = Query(50, le=200),
    agency: dict = Depends(get_marketplace_agency),
):
    """Marketplace'te listelenen ve aktif sözleşmesi bulunan otelleri keşfet."""
    from routers.agency_contracts import list_partner_tenant_ids
    partner_tenant_ids = await list_partner_tenant_ids(agency["agency_id"])
    if not partner_tenant_ids:
        return {"hotels": [], "total": 0,
                "message": "Henüz onaylı sözleşmeniz olan otel yok. Önce otele teklif gönderin."}

    sysdb = get_system_db()
    query: dict = {"is_listed": True, "tenant_id": {"$in": partner_tenant_ids}}
    from security.query_safety import safe_search_term
    if city and (_c := safe_search_term(city)):
        query["city"] = {"$regex": f"^{_c}$", "$options": "i"}
    if country:
        query["country"] = country.upper()
    if q and (_s := safe_search_term(q)):
        query["$or"] = [
            {"hotel_name": {"$regex": _s, "$options": "i"}},
            {"description": {"$regex": _s, "$options": "i"}},
        ]

    docs = await sysdb.marketplace_listings.find(
        query,
        {"_id": 0, "blocked_dates": 0, "created_by": 0},
    ).limit(limit).to_list(limit)
    return {"hotels": docs, "total": len(docs)}


@router.get("/hotels/{tenant_id}")
async def agency_get_hotel(
    tenant_id: str,
    agency: dict = Depends(get_marketplace_agency),
):
    from routers.agency_contracts import has_active_contract
    if not await has_active_contract(agency["agency_id"], tenant_id):
        raise HTTPException(403, "Bu otelle aktif sözleşmeniz yok")
    listing = await _get_listing_or_404(tenant_id)

    with tenant_context(tenant_id):
        rooms = await db.rooms.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(500)
    room_types = {}
    for r in rooms:
        rt = r.get("room_type", "Standard")
        if listing.get("allowed_room_types") and rt not in listing["allowed_room_types"]:
            continue
        if rt not in room_types:
            room_types[rt] = {
                "room_type": rt,
                "capacity": r.get("capacity", 2),
                "base_price": r.get("base_price", 0),
                "amenities": r.get("amenities", []),
                "bed_type": r.get("bed_type", ""),
                "total_rooms": 0,
            }
        room_types[rt]["total_rooms"] += 1

    return {"listing": listing, "room_types": list(room_types.values())}


@router.post("/search")
async def agency_search(
    req: MarketplaceSearchRequest,
    agency: dict = Depends(get_marketplace_agency),
):
    """Çoklu otel müsaitlik araması.

    Şehir/ülke/sorgu filtreleriyle eşleşen tüm listed otellerde tarih aralığı
    için müsait oda tiplerini döndürür. Engelli tarih kuralları uygulanır.
    """
    try:
        ci = datetime.fromisoformat(req.check_in + "T00:00:00+00:00")
        co = datetime.fromisoformat(req.check_out + "T00:00:00+00:00")
    except (ValueError, TypeError):
        raise HTTPException(400, "Geçersiz tarih (YYYY-MM-DD)")
    if co <= ci:
        raise HTTPException(400, "check_out, check_in'den sonra olmalı")

    from routers.agency_contracts import list_partner_tenant_ids
    partner_tenant_ids = await list_partner_tenant_ids(agency["agency_id"], on_date=req.check_in)
    if not partner_tenant_ids:
        return {"check_in": req.check_in, "check_out": req.check_out,
                "results": [], "total_hotels": 0,
                "message": "Henüz onaylı sözleşmeniz olan otel yok."}

    sysdb = get_system_db()
    list_query: dict = {"is_listed": True, "tenant_id": {"$in": partner_tenant_ids}}
    from security.query_safety import safe_search_term
    if req.city and (_c := safe_search_term(req.city)):
        list_query["city"] = {"$regex": f"^{_c}$", "$options": "i"}
    if req.country:
        list_query["country"] = req.country.upper()
    if req.q and (_s := safe_search_term(req.q)):
        list_query["$or"] = [
            {"hotel_name": {"$regex": _s, "$options": "i"}},
            {"description": {"$regex": _s, "$options": "i"}},
        ]

    listings = await sysdb.marketplace_listings.find(list_query, {"_id": 0}).limit(req.limit).to_list(req.limit)

    capacity_needed = max(1, req.adults + req.children)
    results: list[dict] = []

    for listing in listings:
        tenant_id = listing["tenant_id"]
        # Tarih engeli kontrolü
        if any(d in listing.get("blocked_dates", []) for d in _date_range(req.check_in, req.check_out)):
            continue

        with tenant_context(tenant_id):
            rooms = await db.rooms.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(500)

            room_types: dict[str, dict] = {}
            for r in rooms:
                rt = r.get("room_type", "Standard")
                if listing.get("allowed_room_types") and rt not in listing["allowed_room_types"]:
                    continue
                if r.get("capacity", 2) < capacity_needed:
                    continue
                rt_data = room_types.setdefault(rt, {
                    "room_type": rt,
                    "capacity": r.get("capacity", 2),
                    "base_price": r.get("base_price", 0),
                    "total_rooms": 0,
                    "available_rooms": 0,
                    "_room_ids": [],
                })
                rt_data["total_rooms"] += 1
                rt_data["_room_ids"].append(r.get("id"))

            for rt_data in room_types.values():
                booked = await db.bookings.count_documents({
                    "tenant_id": tenant_id,
                    "room_id": {"$in": rt_data["_room_ids"]},
                    "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
                    "check_in": {"$lt": req.check_out + "T23:59:59"},
                    "check_out": {"$gt": req.check_in + "T00:00:00"},
                })
                rt_data["available_rooms"] = max(0, rt_data["total_rooms"] - booked)
                del rt_data["_room_ids"]

        # Sadece müsait oda tipleri olan otelleri ekle
        nights = (co - ci).days
        commission_pct = _commission_for(agency, listing)
        available = []
        for rt_data in room_types.values():
            if rt_data["available_rooms"] <= 0:
                continue
            total_price = rt_data["base_price"] * nights
            if req.max_price and total_price > req.max_price:
                continue
            available.append({
                **rt_data,
                "nights": nights,
                "total_price": total_price,
                "commission_pct": commission_pct,
                "agency_payable": round(total_price * (1 - commission_pct / 100), 2),
            })

        if available:
            results.append({
                "tenant_id": tenant_id,
                "hotel_name": listing.get("hotel_name"),
                "city": listing.get("city"),
                "country": listing.get("country"),
                "star_rating": listing.get("star_rating"),
                "photos": listing.get("photos", [])[:3],
                "available_room_types": available,
            })

    return {
        "check_in": req.check_in,
        "check_out": req.check_out,
        "results": results,
        "total_hotels": len(results),
    }


@router.get("/hotels/{tenant_id}/availability")
async def agency_hotel_availability(
    tenant_id: str,
    check_in: str = Query(..., description="YYYY-MM-DD"),
    check_out: str = Query(..., description="YYYY-MM-DD"),
    agency: dict = Depends(get_marketplace_agency),
):
    from routers.agency_contracts import has_active_contract
    if not await has_active_contract(agency["agency_id"], tenant_id, on_date=check_in):
        raise HTTPException(403, "Bu otelle bu tarih için aktif sözleşmeniz yok")
    listing = await _get_listing_or_404(tenant_id)
    if any(d in listing.get("blocked_dates", []) for d in _date_range(check_in, check_out)):
        return {"check_in": check_in, "check_out": check_out, "room_types": [], "blocked": True}

    try:
        ci = datetime.fromisoformat(check_in + "T00:00:00+00:00")
        co = datetime.fromisoformat(check_out + "T00:00:00+00:00")
    except (ValueError, TypeError):
        raise HTTPException(400, "Geçersiz tarih")
    if co <= ci:
        raise HTTPException(400, "check_out, check_in'den sonra olmalı")

    with tenant_context(tenant_id):
        rooms = await db.rooms.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(1000)
        room_types: dict[str, dict] = {}
        for r in rooms:
            rt = r.get("room_type", "Standard")
            if listing.get("allowed_room_types") and rt not in listing["allowed_room_types"]:
                continue
            rt_data = room_types.setdefault(rt, {
                "room_type": rt,
                "capacity": r.get("capacity", 2),
                "base_price": r.get("base_price", 0),
                "amenities": r.get("amenities", []),
                "total_rooms": 0,
                "available_rooms": 0,
                "_room_ids": [],
            })
            rt_data["total_rooms"] += 1
            rt_data["_room_ids"].append(r.get("id"))

        nights = (co - ci).days
        commission_pct = _commission_for(agency, listing)
        for rt_data in room_types.values():
            booked = await db.bookings.count_documents({
                "tenant_id": tenant_id,
                "room_id": {"$in": rt_data["_room_ids"]},
                "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
                "check_in": {"$lt": check_out + "T23:59:59"},
                "check_out": {"$gt": check_in + "T00:00:00"},
            })
            rt_data["available_rooms"] = max(0, rt_data["total_rooms"] - booked)
            rt_data["nights"] = nights
            rt_data["total_price"] = rt_data["base_price"] * nights
            rt_data["commission_pct"] = commission_pct
            rt_data["agency_payable"] = round(rt_data["total_price"] * (1 - commission_pct / 100), 2)
            del rt_data["_room_ids"]

    return {
        "check_in": check_in,
        "check_out": check_out,
        "hotel_name": listing.get("hotel_name"),
        "room_types": list(room_types.values()),
    }


@router.get("/hotels/{tenant_id}/rates")
async def agency_hotel_rates(
    tenant_id: str,
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    room_type: str | None = Query(None),
    _agency: dict = Depends(get_marketplace_agency),
):
    await _get_listing_or_404(tenant_id)
    base_query = {
        "tenant_id": tenant_id,
        "date": {"$gte": start_date, "$lte": end_date},
    }
    if room_type:
        base_query["room_type_code"] = room_type

    with tenant_context(tenant_id):
        rates = await db.hr_rate_calendar.find(base_query, {"_id": 0, "tenant_id": 0}).sort("date", 1).to_list(5000)
        if not rates:
            rates = await db.rate_calendar.find(base_query, {"_id": 0, "tenant_id": 0}).sort("date", 1).to_list(5000)
    return {"start_date": start_date, "end_date": end_date, "rates": rates}


# ═══════════════════════════════════════════════════════════════════════
# AGENCY — Reservation Lifecycle (Cross-tenant)
# ═══════════════════════════════════════════════════════════════════════

@router.post("/reservations")
async def agency_create_reservation(
    data: MarketplaceReservationCreate,
    background_tasks: BackgroundTasks,
    agency: dict = Depends(get_marketplace_agency),
):
    """Listed otele cross-tenant rezervasyon oluştur. Mevcut bookings koleksiyonuna düşer."""
    from routers.agency_contracts import has_active_contract
    contract = await has_active_contract(agency["agency_id"], data.tenant_id, on_date=data.check_in)
    if not contract:
        raise HTTPException(
            403,
            "Bu otelle bu tarih için aktif sözleşmeniz yok. Önce sözleşme teklifi "
            "gönderip otelin onayını bekleyin."
        )

    listing = await _get_listing_or_404(data.tenant_id)

    if any(d in listing.get("blocked_dates", []) for d in _date_range(data.check_in, data.check_out)):
        raise HTTPException(409, "Bu tarih aralığı otel tarafından kapatılmış")

    # Sözleşmedeki oda tipi kısıtı (varsa) listing kısıtının üzerine biner
    contract_room_types = contract.get("allowed_room_types") or []
    if contract_room_types and data.room_type not in contract_room_types:
        raise HTTPException(403, f"Bu oda tipi sözleşmenizde tanımlı değil: {contract_room_types}")
    if listing.get("allowed_room_types") and data.room_type not in listing["allowed_room_types"]:
        raise HTTPException(403, "Bu oda tipi marketplace satışına açık değil")

    try:
        ci = datetime.fromisoformat(data.check_in + "T14:00:00+00:00")
        co = datetime.fromisoformat(data.check_out + "T11:00:00+00:00")
    except (ValueError, TypeError):
        raise HTTPException(400, "Geçersiz tarih")
    if co <= ci:
        raise HTTPException(400, "check_out, check_in'den sonra olmalı")

    # NOTE: Mevcut /api/b2b/reservations ile paylaşılan davranış — "check-then-act"
    # rezervasyon akışı, yüksek eş zamanlılıkta aynı son odaya çift booking
    # üretebilir. Bu kapsamda kabul edilmiştir; gelecek sprint'te per-room
    # atomic find_and_modify lock'a geçirilecek.
    with tenant_context(data.tenant_id):
        rooms = await db.rooms.find(
            {"tenant_id": data.tenant_id, "room_type": data.room_type}, {"_id": 0}
        ).to_list(500)
        if not rooms:
            raise HTTPException(404, "Oda tipi bulunamadı")

        available_room = None
        for room in rooms:
            conflict = await db.bookings.count_documents({
                "tenant_id": data.tenant_id,
                "room_id": room["id"],
                "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
                "check_in": {"$lt": data.check_out + "T23:59:59"},
                "check_out": {"$gt": data.check_in + "T00:00:00"},
            })
            if conflict == 0:
                available_room = room
                break

        if not available_room:
            raise HTTPException(409, "Seçilen tarihler için müsait oda yok")

        # Komisyon: sözleşmede otelin onayladığı oran (override edilmiş olabilir) kullanılır
        commission_pct = float(contract.get("commission_pct", _commission_for(agency, listing)))
        nights = (co - ci).days
        # Server-side "ground truth" fiyat — istemcinin gönderdiği total_amount'a güvenme.
        server_total = float(available_room.get("base_price", 0)) * max(nights, 1)
        if data.total_amount and data.total_amount > 0:
            if abs(data.total_amount - server_total) > PRICE_TOLERANCE:
                raise HTTPException(
                    422,
                    f"Fiyat uyuşmazlığı: gönderilen {data.total_amount}, beklenen {server_total} "
                    f"(tolerans ±{PRICE_TOLERANCE}). Lütfen güncel fiyat için /search çağrısını tekrarlayın.",
                )
        total = server_total
        commission_amount = round(total * commission_pct / 100, 2)
        net_to_hotel = round(total - commission_amount, 2)

        guest_id = _uuid()
        await db.guests.insert_one({
            "id": guest_id,
            "tenant_id": data.tenant_id,
            "name": data.guest_name.strip(),
            "email": data.guest_email.strip() or f"mkt-{guest_id[:8]}@placeholder.local",
            "phone": data.guest_phone.strip(),
            "id_number": "",
            "vip_status": False,
            "loyalty_points": 0,
            "total_stays": 0,
            "total_spend": 0.0,
            "created_at": _now_iso(),
        })

        booking_id = _uuid()
        confirmation_code = f"MKT-{booking_id[:8].upper()}"
        booking_doc = {
        "id": booking_id,
        "tenant_id": data.tenant_id,
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
        "channel": "marketplace",
        "source_channel": "marketplace",
        "marketplace_agency_id": agency["agency_id"],
        "marketplace_agency_name": agency["agency_name"],
        "agency_commission_rate": commission_pct,
        "agency_commission_amount": commission_amount,
        "net_to_hotel": net_to_hotel,
        "confirmation_code": confirmation_code,
        "external_reference": data.external_reference,
        "special_requests": data.special_requests,
        "guest_name": data.guest_name.strip(),
        "guest_email": data.guest_email.strip(),
        "guest_phone": data.guest_phone.strip(),
            "origin": "syroce_marketplace",
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        # v106 architect follow-up (race-safety): direct insert_one bypassed
        # the room_night_locks atomic guard → marketplace agencies could
        # double-book the same room across concurrent requests. Now routed
        # through create_booking_atomic.
        try:
            booking_doc = await create_booking_atomic(booking_doc)
        except BookingConflictError as conflict_err:
            raise HTTPException(status_code=409, detail=str(conflict_err))

    # Cross-tenant ledger (ileride mutabakat için) — sysdb tenant-bağımsız
    sysdb = get_system_db()
    await sysdb.marketplace_bookings.insert_one({
        "id": booking_id,
        "agency_id": agency["agency_id"],
        "tenant_id": data.tenant_id,
        "hotel_name": listing.get("hotel_name"),
        "confirmation_code": confirmation_code,
        "external_reference": data.external_reference,
        "check_in": data.check_in,
        "check_out": data.check_out,
        "guest_name": data.guest_name,
        "total_amount": total,
        "commission_pct": commission_pct,
        "commission_amount": commission_amount,
        "net_to_hotel": net_to_hotel,
        "status": "confirmed",
        "created_at": _now_iso(),
    })

    # Webhook bildirimi (otele)
    try:
        from routers.b2b_api import fire_webhooks
        background_tasks.add_task(
            fire_webhooks, data.tenant_id, agency["agency_id"], "marketplace.reservation.created",
            {
                "reservation_id": booking_id,
                "confirmation_code": confirmation_code,
                "hotel_name": listing.get("hotel_name"),
                "agency_name": agency["agency_name"],
                "check_in": data.check_in,
                "check_out": data.check_out,
                "total_amount": total,
            },
        )
    except Exception as e:
        logger.warning(f"Marketplace webhook fire failed: {e}")

    return {
        "ok": True,
        "reservation": {
            "id": booking_id,
            "confirmation_code": confirmation_code,
            "external_reference": data.external_reference,
            "tenant_id": data.tenant_id,
            "hotel_name": listing.get("hotel_name"),
            "status": "confirmed",
            "room_type": available_room.get("room_type"),
            "room_number": available_room.get("room_number"),
            "check_in": data.check_in,
            "check_out": data.check_out,
            "guest_name": data.guest_name,
            "total_amount": total,
            "commission_pct": commission_pct,
            "commission_amount": commission_amount,
            "net_to_hotel": net_to_hotel,
        },
    }


@router.get("/reservations")
async def agency_list_reservations(
    status: str | None = Query(None),
    tenant_id: str | None = Query(None, description="Belirli bir otele filtrele"),
    check_in_from: str | None = Query(None),
    check_in_to: str | None = Query(None),
    limit: int = Query(100, le=500),
    agency: dict = Depends(get_marketplace_agency),
):
    """Acentenin tüm marketplace rezervasyonları (cross-tenant)."""
    sysdb = get_system_db()
    query: dict = {"agency_id": agency["agency_id"]}
    if status:
        query["status"] = status
    if tenant_id:
        query["tenant_id"] = tenant_id
    if check_in_from:
        query.setdefault("check_in", {})["$gte"] = check_in_from
    if check_in_to:
        query.setdefault("check_in", {})["$lte"] = check_in_to

    docs = await sysdb.marketplace_bookings.find(
        query, {"_id": 0}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    return {"reservations": docs, "total": len(docs)}


@router.get("/reservations/{reservation_id}")
async def agency_get_reservation(
    reservation_id: str,
    agency: dict = Depends(get_marketplace_agency),
):
    sysdb = get_system_db()
    doc = await sysdb.marketplace_bookings.find_one(
        {"id": reservation_id, "agency_id": agency["agency_id"]}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(404, "Rezervasyon bulunamadı")

    with tenant_context(doc["tenant_id"]):
        booking = await db.bookings.find_one(
            {"id": reservation_id, "tenant_id": doc["tenant_id"]},
            {"_id": 0, "tenant_id": 0, "guest_id": 0, "room_id": 0},
        )
    return {"summary": doc, "booking": booking}


@router.delete("/reservations/{reservation_id}")
async def agency_cancel_reservation(
    reservation_id: str,
    background_tasks: BackgroundTasks,
    reason: str = Query("agency_request"),
    agency: dict = Depends(get_marketplace_agency),
):
    sysdb = get_system_db()
    summary = await sysdb.marketplace_bookings.find_one(
        {"id": reservation_id, "agency_id": agency["agency_id"]}, {"_id": 0}
    )
    if not summary:
        raise HTTPException(404, "Rezervasyon bulunamadı")
    if summary.get("status") == "cancelled":
        return {"ok": True, "message": "Rezervasyon zaten iptal edilmiş"}

    with tenant_context(summary["tenant_id"]):
        booking = await db.bookings.find_one({"id": reservation_id, "tenant_id": summary["tenant_id"]})
        if booking and booking.get("status") in ("checked_in", "checked_out"):
            raise HTTPException(409, "Otele giriş yapılmış rezervasyon iptal edilemez")

        await db.bookings.update_one(
            {"id": reservation_id, "tenant_id": summary["tenant_id"]},
            {"$set": {
                "status": "cancelled",
                "cancellation_reason": reason,
                "cancelled_by": "marketplace_agency",
                "cancelled_at": _now_iso(),
                "updated_at": _now_iso(),
            }},
        )
    await sysdb.marketplace_bookings.update_one(
        {"id": reservation_id},
        {"$set": {"status": "cancelled", "cancelled_at": _now_iso(), "cancellation_reason": reason}},
    )

    try:
        from routers.b2b_api import fire_webhooks
        background_tasks.add_task(
            fire_webhooks, summary["tenant_id"], agency["agency_id"], "marketplace.reservation.cancelled",
            {
                "reservation_id": reservation_id,
                "confirmation_code": summary.get("confirmation_code"),
                "reason": reason,
            },
        )
    except Exception as e:
        logger.warning(f"Marketplace cancel webhook failed: {e}")

    return {"ok": True, "message": "Rezervasyon iptal edildi"}


# ═══════════════════════════════════════════════════════════════════════
# Reconciliation — Cross-tenant Komisyon Raporu
# ═══════════════════════════════════════════════════════════════════════

@router.get("/reconciliation/agency")
async def agency_reconciliation(
    period_start: str = Query(..., description="YYYY-MM-DD"),
    period_end: str = Query(..., description="YYYY-MM-DD"),
    agency: dict = Depends(get_marketplace_agency),
):
    """Acente için dönem bazlı komisyon ve ciro özeti."""
    sysdb = get_system_db()
    docs = await sysdb.marketplace_bookings.find(
        {
            "agency_id": agency["agency_id"],
            "check_in": {"$gte": period_start, "$lte": period_end},
        },
        {"_id": 0},
    ).to_list(5000)

    by_hotel: dict[str, dict] = {}
    totals = {"gross_revenue": 0.0, "commission": 0.0, "net_to_hotels": 0.0, "bookings": 0, "cancelled": 0}
    for d in docs:
        if d.get("status") == "cancelled":
            totals["cancelled"] += 1
            continue
        tid = d["tenant_id"]
        bucket = by_hotel.setdefault(tid, {
            "tenant_id": tid,
            "hotel_name": d.get("hotel_name"),
            "bookings": 0,
            "gross_revenue": 0.0,
            "commission": 0.0,
            "net_to_hotel": 0.0,
        })
        gross = float(d.get("total_amount", 0))
        comm = float(d.get("commission_amount", 0))
        net = float(d.get("net_to_hotel", gross - comm))
        bucket["bookings"] += 1
        bucket["gross_revenue"] += gross
        bucket["commission"] += comm
        bucket["net_to_hotel"] += net
        totals["bookings"] += 1
        totals["gross_revenue"] += gross
        totals["commission"] += comm
        totals["net_to_hotels"] += net

    return {
        "period_start": period_start,
        "period_end": period_end,
        "agency_id": agency["agency_id"],
        "totals": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in totals.items()},
        "by_hotel": [
            {**v, "gross_revenue": round(v["gross_revenue"], 2),
             "commission": round(v["commission"], 2),
             "net_to_hotel": round(v["net_to_hotel"], 2)}
            for v in by_hotel.values()
        ],
    }


@router.get("/reconciliation/hotel")
async def hotel_reconciliation(
    period_start: str = Query(..., description="YYYY-MM-DD"),
    period_end: str = Query(..., description="YYYY-MM-DD"),
    current_user: User = Depends(get_current_user),
):
    """Otel için marketplace üzerinden gelen rezervasyonların komisyon raporu."""
    tenant_id = _require_hotel_admin(current_user)
    sysdb = get_system_db()
    docs = await sysdb.marketplace_bookings.find(
        {
            "tenant_id": tenant_id,
            "check_in": {"$gte": period_start, "$lte": period_end},
        },
        {"_id": 0},
    ).to_list(5000)

    by_agency: dict[str, dict] = {}
    totals = {"gross_revenue": 0.0, "commission": 0.0, "net_to_hotel": 0.0, "bookings": 0, "cancelled": 0}
    for d in docs:
        if d.get("status") == "cancelled":
            totals["cancelled"] += 1
            continue
        aid = d["agency_id"]
        bucket = by_agency.setdefault(aid, {
            "agency_id": aid,
            "bookings": 0,
            "gross_revenue": 0.0,
            "commission_owed": 0.0,
            "net_received": 0.0,
        })
        gross = float(d.get("total_amount", 0))
        comm = float(d.get("commission_amount", 0))
        net = float(d.get("net_to_hotel", gross - comm))
        bucket["bookings"] += 1
        bucket["gross_revenue"] += gross
        bucket["commission_owed"] += comm
        bucket["net_received"] += net
        totals["bookings"] += 1
        totals["gross_revenue"] += gross
        totals["commission"] += comm
        totals["net_to_hotel"] += net

    return {
        "period_start": period_start,
        "period_end": period_end,
        "tenant_id": tenant_id,
        "totals": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in totals.items()},
        "by_agency": [
            {**v, "gross_revenue": round(v["gross_revenue"], 2),
             "commission_owed": round(v["commission_owed"], 2),
             "net_received": round(v["net_received"], 2)}
            for v in by_agency.values()
        ],
    }


# ─── Utility ──────────────────────────────────────────────────────────────

def _date_range(start: str, end: str) -> list[str]:
    """[start, end) aralığındaki YYYY-MM-DD listesi."""
    from datetime import date, timedelta
    s = date.fromisoformat(start)
    e = date.fromisoformat(end)
    out = []
    while s < e:
        out.append(s.isoformat())
        s += timedelta(days=1)
    return out
