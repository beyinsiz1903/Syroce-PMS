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

import csv
import hashlib
import html
import io
import logging
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt as pyjwt
from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Query, Request, Response
from pydantic import BaseModel, EmailStr, Field, model_validator

from core.atomic_booking import BookingConflictError, assign_room_atomic, create_booking_atomic
from core.database import db
from core.occupancy_pricing import OccupancyPricingError, calculate_occupancy_quote, find_occupancy_rule
from core.security import _is_super_admin, get_current_user, verify_password
from core.tenant_db import get_system_db, tenant_context
from models.schemas import User
from shared_kernel.idempotency import (
    build_request_hash,
    claim_idempotency,
    complete_idempotency,
    release_idempotency,
)

# Server-side fiyat hesaplamasının istemciden gelen total_amount'tan tolerans
# (TRY) — bu eşiği aşan farklarda istek reddedilir (price-spoofing koruması).
PRICE_TOLERANCE = 0.50

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/marketplace/v1", tags=["Marketplace v1"])

# ─── Global Extranet UI ───────────────────────────────────────────────────


class MarketplaceLoginRequest(BaseModel):
    email: str
    password: str


@router.post("/extranet/auth/login")
async def marketplace_extranet_login(req: MarketplaceLoginRequest, request: Request):
    """Global B2B Extranet arayüzü (Marketplace UI) için giriş."""
    from core.security import create_token

    sysdb = get_system_db()
    normalized_email = req.email.strip().lower()
    client_ip = request.client.host if request.client else "unknown"
    attempt_key = hashlib.sha256(f"{normalized_email}|{client_ip}".encode()).hexdigest()
    window_start = datetime.now(UTC) - timedelta(minutes=15)
    recent_failures = await sysdb.marketplace_login_attempts.count_documents(
        {"key": attempt_key, "success": False, "created_at": {"$gte": window_start}}
    )
    if recent_failures >= 5:
        raise HTTPException(status_code=429, detail="Çok fazla başarısız giriş. 15 dakika sonra tekrar deneyin")

    # Global users (tenant_id = null or "SYROCE_GLOBAL" etc.)
    # Assuming marketplace_agent users are in the global users collection.
    user = await sysdb.users.find_one({"email": normalized_email})

    if not user or user.get("is_active") is False or not verify_password(req.password, user.get("hashed_password", "")):
        await sysdb.marketplace_login_attempts.insert_one(
            {"key": attempt_key, "email_hash": hashlib.sha256(normalized_email.encode()).hexdigest(), "success": False, "created_at": datetime.now(UTC)}
        )
        raise HTTPException(status_code=401, detail="E-posta veya şifre hatalı")

    role = getattr(user.get("role"), "value", user.get("role"))
    roles = user.get("roles") or []
    if role != "marketplace_agent" and "marketplace_agent" not in roles:
        raise HTTPException(status_code=403, detail="Sadece global acente kullanıcıları girebilir")

    if not user.get("agency_id"):
        raise HTTPException(status_code=403, detail="Kullanıcıya atanmış bir marketplace acentesi yok")

    agency = await sysdb.marketplace_agencies.find_one({"id": user["agency_id"], "status": "active"})
    if not agency:
        raise HTTPException(status_code=403, detail="Marketplace acentesi aktif değil")

    token = create_token(user["id"], None)
    await sysdb.marketplace_login_attempts.delete_many({"key": attempt_key})

    return {
        "token": token,
        "user": {"id": user["id"], "name": user.get("name", ""), "email": user.get("email", ""), "role": "marketplace_agent", "agency_id": user["agency_id"]},
        "agency": {"id": agency["id"], "name": agency.get("name", "")},
    }


async def get_marketplace_agency(x_api_key: str | None = Header(None, alias="X-API-Key"), authorization: str | None = Header(None)) -> dict:
    """Cross-tenant API key veya JWT doğrulama.
    Acenteler Syroce Agency otomasyonu için X-API-Key,
    Global Extranet UI üzerinden giriş için JWT Bearer token kullanabilir."""
    sysdb = get_system_db()
    agency_id = None
    actor_user = None

    if authorization and authorization.lower().startswith("bearer "):
        try:
            from core.security import JWT_ALGORITHM, JWT_SECRET, is_jti_revoked

            token = authorization.split(" ", 1)[1]
            payload = pyjwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
            if payload.get("type") not in (None, "access") or not payload.get("user_id"):
                raise HTTPException(401, "Geçersiz acente erişim token'ı")
            if payload.get("jti") and await is_jti_revoked(payload["jti"]):
                raise HTTPException(401, "Acente oturumu sonlandırılmış")
            user = await sysdb.users.find_one(
                {"$or": [{"id": payload["user_id"]}, {"user_id": payload["user_id"]}]},
                {"_id": 0},
            )
            if not user or user.get("is_active") is False:
                raise HTTPException(401, "Acente kullanıcısı aktif değil")
            invalid_before = user.get("tokens_invalid_before")
            if invalid_before and float(payload.get("iat") or 0) < float(invalid_before):
                raise HTTPException(401, "Acente oturumu artık geçerli değil")
            raw_role = user.get("role")
            role = getattr(raw_role, "value", raw_role)
            roles = user.get("roles") or []
            if role != "marketplace_agent" and "marketplace_agent" not in roles:
                raise HTTPException(403, "Kullanıcı bir global acente yetkilisi değil")
            agency_id = user.get("agency_id")
            actor_user = {
                "id": user.get("id") or user.get("user_id"),
                "name": user.get("name", ""),
                "email": user.get("email", ""),
                "role": "marketplace_agent",
            }
        except (pyjwt.ExpiredSignatureError, pyjwt.InvalidTokenError):
            raise HTTPException(401, "Geçersiz veya süresi dolmuş acente token'ı")
        except Exception as e:
            if isinstance(e, HTTPException):
                raise e
            raise HTTPException(401, "Geçersiz token")
    elif x_api_key:
        key_hash = _hash_key(x_api_key)
        key_doc = await sysdb.marketplace_api_keys.find_one({"key_hash": key_hash, "is_active": True}, {"_id": 0})
        if not key_doc:
            raise HTTPException(401, "Geçersiz veya devre dışı marketplace API key")
        agency_id = key_doc["agency_id"]

        await sysdb.marketplace_api_keys.update_one(
            {"key_hash": key_hash},
            {"$set": {"last_used_at": _now_iso()}, "$inc": {"usage_count": 1}},
        )
    else:
        raise HTTPException(401, "Kimlik doğrulama gereklidir (X-API-Key veya JWT)")

    if not agency_id:
        raise HTTPException(403, "Acente ID bulunamadı")

    agency = await sysdb.marketplace_agencies.find_one({"id": agency_id, "status": "active"}, {"_id": 0})
    if not agency:
        raise HTTPException(403, "Marketplace acentesi aktif değil")

    # Determine source for %1 vs %2 billing differentiation
    source = "extranet_ui" if authorization else "syroce_agency_app"

    return {
        "agency_id": agency["id"],
        "agency_name": agency.get("name", ""),
        "default_commission_pct": agency.get("default_commission_pct", 12.0),
        "platform_fee_pct": agency.get("platform_fee_pct"),
        "contact_email": agency.get("contact_email", ""),
        "source": source,
        "user": actor_user,
    }

@router.get("/extranet/my-hotels")
async def marketplace_my_hotels(agency: dict = Depends(get_marketplace_agency)):
    """Acentenin aktif sözleşmesi olan otelleri listeler."""
    from routers.agency_contracts import list_partner_tenant_ids

    sysdb = get_system_db()
    tenant_ids = await list_partner_tenant_ids(agency["agency_id"])

    hotels = []
    if tenant_ids:
        listings = await sysdb.marketplace_listings.find(
            {"tenant_id": {"$in": tenant_ids}, "is_listed": True}, {"_id": 0}
        ).to_list(1000)

        for listing in listings:
            hotels.append({
                "tenant_id": listing["tenant_id"],
                "name": listing.get("hotel_name", "Bilinmeyen Otel"),
                "city": listing.get("city", ""),
                "country": listing.get("country", ""),
                "currency": listing.get("currency", "TRY"),
            })

    return {"hotels": hotels}


class MarketplaceNotificationSettings(BaseModel):
    new_reservation: bool = True
    reservation_change: bool = True
    cancellation_request: bool = True
    payment_reconciliation: bool = True


class MarketplacePortalSettingsUpdate(BaseModel):
    name: str = Field(..., min_length=2, max_length=160)
    contact_email: EmailStr
    contact_phone: str = Field(default="", max_length=40)
    address: str = Field(default="", max_length=500)
    website: str = Field(default="", max_length=300)
    notification_preferences: MarketplaceNotificationSettings = Field(default_factory=MarketplaceNotificationSettings)
    allowed_widget_origins: list[str] = Field(default_factory=list, max_length=20)
    widget_brand_color: str = Field(default="#047857", pattern=r"^#[0-9A-Fa-f]{6}$")

    @model_validator(mode="after")
    def normalize_widget_origins(self):
        normalized = []
        for value in self.allowed_widget_origins:
            origin = str(value or "").strip().rstrip("/")
            if not origin:
                continue
            if not origin.startswith(("https://", "http://localhost", "http://127.0.0.1")):
                raise ValueError("Web sitesi adresi HTTPS ile başlamalıdır")
            normalized.append(origin)
        self.allowed_widget_origins = list(dict.fromkeys(normalized))
        return self


@router.get("/extranet/profile")
async def marketplace_extranet_profile(agency: dict = Depends(get_marketplace_agency)):
    """Reload-safe identity for the multi-property agency portal."""
    hotel_result = await marketplace_my_hotels(agency)
    return {
        "agency": {
            "id": agency["agency_id"],
            "name": agency.get("agency_name", ""),
            "contact_email": agency.get("contact_email", ""),
        },
        "user": agency.get("user"),
        "hotels": hotel_result["hotels"],
    }


@router.get("/extranet/settings")
async def marketplace_extranet_settings(agency: dict = Depends(get_marketplace_agency)):
    """Return agency-scoped account settings without exposing credentials."""
    sysdb = get_system_db()
    agency_doc = await sysdb.marketplace_agencies.find_one(
        {"id": agency["agency_id"], "status": "active"}, {"_id": 0}
    )
    if not agency_doc:
        raise HTTPException(404, "Acente hesabı bulunamadı")
    users = await sysdb.users.find(
        {"agency_id": agency["agency_id"], "is_active": {"$ne": False}},
        {"_id": 0, "id": 1, "name": 1, "email": 1, "role": 1, "roles": 1, "last_login": 1, "created_at": 1},
    ).to_list(200)
    keys = await sysdb.marketplace_api_keys.find(
        {"agency_id": agency["agency_id"], "is_active": True},
        {"_id": 0, "id": 1, "key_prefix": 1, "created_at": 1, "last_used_at": 1, "usage_count": 1},
    ).to_list(50)
    return {
        "agency": {
            "id": agency_doc["id"],
            "name": agency_doc.get("name", ""),
            "contact_email": agency_doc.get("contact_email", ""),
            "contact_phone": agency_doc.get("contact_phone", ""),
            "address": agency_doc.get("address", ""),
            "website": agency_doc.get("website", ""),
            "status": agency_doc.get("status", "active"),
        },
        "notification_preferences": agency_doc.get("notification_preferences") or MarketplaceNotificationSettings().model_dump(),
        "widget": {
            "allowed_origins": agency_doc.get("allowed_widget_origins") or [],
            "brand_color": agency_doc.get("widget_brand_color") or "#047857",
            "agency_id": agency_doc["id"],
        },
        "users": users,
        "api_keys": keys,
    }


@router.patch("/extranet/settings")
async def update_marketplace_extranet_settings(
    data: MarketplacePortalSettingsUpdate,
    agency: dict = Depends(get_marketplace_agency),
):
    """Update only the signed-in agency's editable portal settings."""
    sysdb = get_system_db()
    updates = {
        "name": data.name.strip(),
        "contact_email": str(data.contact_email).strip().lower(),
        "contact_phone": data.contact_phone.strip(),
        "address": data.address.strip(),
        "website": data.website.strip(),
        "notification_preferences": data.notification_preferences.model_dump(),
        "allowed_widget_origins": data.allowed_widget_origins,
        "widget_brand_color": data.widget_brand_color.lower(),
        "updated_at": _now_iso(),
        "updated_by": (agency.get("user") or {}).get("id"),
    }
    result = await sysdb.marketplace_agencies.update_one(
        {"id": agency["agency_id"], "status": "active"}, {"$set": updates}
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Acente hesabı bulunamadı")
    await sysdb.marketplace_audit_logs.insert_one(
        {
            "id": str(uuid.uuid4()),
            "agency_id": agency["agency_id"],
            "actor_user_id": (agency.get("user") or {}).get("id"),
            "action": "portal_settings_updated",
            "changed_fields": sorted(updates.keys()),
            "created_at": datetime.now(UTC).isoformat(),
        }
    )
    return {"ok": True, "message": "Acente ayarları güncellendi"}


# ─── Helpers ──────────────────────────────────────────────────────────────


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _uuid() -> str:
    return str(uuid.uuid4())


def _last_occupied_date(check_in: str, check_out: str) -> str:
    """Convert the exclusive checkout boundary to the final sold room-night."""
    from datetime import timedelta

    ci = datetime.fromisoformat(check_in).date()
    co = datetime.fromisoformat(check_out).date()
    if co <= ci:
        raise HTTPException(400, "check_out, check_in'den sonra olmalı")
    return (co - timedelta(days=1)).isoformat()


def _hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def _require_hotel_admin(user: User) -> str:
    """Otel admin/sahibi rollerini doğrular ve tenant_id döner. Super_admin always allowed."""
    if _is_super_admin(user):
        if not user.tenant_id:
            raise HTTPException(403, "Geçerli bir otel kiracısı yok")
        return user.tenant_id
    role = getattr(user.role, "value", user.role)
    if role not in ("admin", "super_admin", "supervisor"):
        raise HTTPException(403, "Marketplace otel ayarlarını yalnız yönetici roller yönetebilir")
    if not user.tenant_id:
        raise HTTPException(403, "Geçerli bir otel kiracısı yok")
    return user.tenant_id


async def _try_get_super_admin(authorization: str | None = Header(None)) -> bool:
    """Authorization header'dan opsiyonel super_admin tespiti (401 atmaz)."""
    if not authorization or not authorization.lower().startswith("bearer "):
        return False
    try:
        from fastapi.security import HTTPAuthorizationCredentials

        creds = HTTPAuthorizationCredentials(scheme="Bearer", credentials=authorization.split(" ", 1)[1])
        user = await get_current_user(creds)
        return _is_super_admin(user)
    except Exception:
        return False


def _require_system_admin(
    token: str | None = Header(None, alias="X-Marketplace-Admin-Token"),
    is_sa: bool = Depends(_try_get_super_admin),
) -> bool:
    """Sistem yöneticisi yetkisi: env var token VEYA super_admin JWT ile koruma.

    Super_admin (role veya roles[]) her zaman geçerli sayılır.
    """
    if is_sa:
        return True
    expected = os.getenv("MARKETPLACE_ADMIN_TOKEN")
    if not expected:
        raise HTTPException(503, "Marketplace admin yapılandırılmamış")
    if not token or not secrets.compare_digest(token, expected):
        raise HTTPException(401, "Geçersiz marketplace admin token")
    return True


# ─── Cross-tenant Agency Auth ─────────────────────────────────────────────





async def _get_listing_or_404(tenant_id: str) -> dict:
    """Bir otelin marketplace listing'ini döner. Liste edilmemişse 404."""
    sysdb = get_system_db()
    listing = await sysdb.marketplace_listings.find_one({"tenant_id": tenant_id, "is_listed": True}, {"_id": 0})
    if not listing:
        raise HTTPException(404, "Bu otel marketplace'te listelenmemiş")
    tenant = await sysdb.tenants.find_one({"id": tenant_id}, {"_id": 0, "subscription_status": 1, "is_active": 1})
    if not tenant or tenant.get("is_active") is False or tenant.get("subscription_status", "active") != "active":
        raise HTTPException(404, "Bu otel şu anda rezervasyon kabul etmiyor")
    return listing


async def _marketplace_stay_price(
    *, tenant_id: str, agency_id: str, room_type: str, check_in: str, check_out: str, fallback_rate: float
) -> dict:
    """Return the exact sellable nightly rates shared with this agency.

    Agency calendar wins per night, then the hotel's public calendar, then the
    room base rate. A stop-sell or zero agency allotment closes the whole stay.
    """
    dates = _date_range(check_in, check_out)
    query = {"tenant_id": tenant_id, "room_type_code": room_type, "date": {"$in": dates}}
    agency_rows = await db.agency_rate_calendar.find(
        {**query, "agency_id": agency_id}, {"_id": 0}
    ).to_list(max(len(dates) * 8, 32))
    base_rows = await db.hr_rate_calendar.find(query, {"_id": 0}).to_list(max(len(dates) * 8, 32))
    if not base_rows:
        base_rows = await db.rate_calendar.find(query, {"_id": 0}).to_list(max(len(dates) * 8, 32))

    agency_by_date = {row.get("date"): row for row in agency_rows}
    base_by_date = {row.get("date"): row for row in base_rows}
    nightly_rates: list[dict] = []
    shared_availability: list[int] = []
    for date in dates:
        row = agency_by_date.get(date) or base_by_date.get(date) or {}
        if row.get("stop_sell") is True or (
            date in agency_by_date
            and row.get("availability") is not None
            and int(row["availability"]) <= 0
        ):
            return {"sellable": False, "nightly_rates": [], "total_price": 0.0}
        rate = row.get("rate")
        if rate is None:
            rate = fallback_rate
        if date in agency_by_date and row.get("availability") is not None:
            shared_availability.append(max(0, int(row["availability"])))
        nightly_rates.append({"date": date, "rate": round(float(rate or 0), 2)})
    result = {
        "sellable": True,
        "nightly_rates": nightly_rates,
        "total_price": round(sum(item["rate"] for item in nightly_rates), 2),
    }
    if shared_availability:
        # A stay can only sell the lowest allotment available on any occupied
        # night. Physical PMS inventory remains the upper safety bound.
        result["shared_availability"] = min(shared_availability)
    return result


async def _marketplace_occupancy_price(
    *, tenant_id: str, room: dict, pricing: dict, adults: int, child_ages: list[int]
) -> dict:
    """Apply the hotel's saved occupancy policy to each shared nightly rate."""
    rule = await find_occupancy_rule(db, tenant_id, room)
    if not rule:
        return {**pricing, "occupancy_pricing": None}

    quoted_nights = []
    total = 0.0
    try:
        for item in pricing.get("nightly_rates", []):
            quote = calculate_occupancy_quote(
                base_nightly_rate=item["rate"],
                nights=1,
                adults=adults,
                children_ages=child_ages,
                rule=rule,
            )
            quoted_nights.append({**item, "base_rate": item["rate"], "rate": quote["nightly_total"]})
            total += quote["nightly_total"]
    except OccupancyPricingError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    summary = calculate_occupancy_quote(
        base_nightly_rate=pricing["nightly_rates"][0]["rate"] if pricing.get("nightly_rates") else 0,
        nights=max(len(quoted_nights), 1),
        adults=adults,
        children_ages=child_ages,
        rule=rule,
    )
    return {
        **pricing,
        "nightly_rates": quoted_nights,
        "total_price": round(total, 2),
        "occupancy_pricing": {
            "pricing_version": summary["pricing_version"],
            "pricing_type": summary["pricing_type"],
            "children_ages": summary["children_ages"],
            "child_breakdown": summary["child_breakdown"],
            "adult_supplement_nightly": summary["adult_supplement_nightly"],
            "child_supplement_nightly": summary["child_supplement_nightly"],
        },
    }


def _commission_for(agency: dict, listing: dict) -> float:
    """Listing'de komisyon override varsa onu, yoksa agency default'unu kullan."""
    pct = listing.get("commission_pct")
    if pct is None:
        pct = agency.get("default_commission_pct", 12.0)
    return float(pct)


def _syroce_b2b_fee(total: float, source: str, agency_fee_pct: float | None = None) -> tuple[float, float]:
    """Return the marketplace service fee used in the hotel net calculation.

    Direct API integrations are billed at 1%; reservations created in the
    hosted extranet include the additional UI/operations service and are
    billed at 2%.  Keeping this calculation next to commission setup ensures
    the values exist before the PMS booking becomes durable.
    """
    fee_pct = float(agency_fee_pct) if agency_fee_pct is not None else (2.0 if source == "extranet_ui" else 1.0)
    if fee_pct < 0 or fee_pct > 100:
        raise ValueError("Platform hizmet bedeli 0 ile 100 arasında olmalıdır")
    return fee_pct, round(float(total) * fee_pct / 100, 2)


def _marketplace_financials(total: float, commission_pct: float, fee_pct: float) -> dict[str, float]:
    commission_amount = round(float(total) * float(commission_pct) / 100, 2)
    fee_amount = round(float(total) * float(fee_pct) / 100, 2)
    return {
        "commission_amount": commission_amount,
        "syroce_b2b_fee_amount": fee_amount,
        "net_to_hotel": round(float(total) - commission_amount - fee_amount, 2),
    }


def _reservation_room_snapshot(room: dict) -> dict:
    """Canonical room fields shared by PMS, ledger and API responses."""
    return {
        "room_type": room.get("room_type", ""),
        "room_number": room.get("room_number", ""),
    }


def _reservation_agency_snapshot(agency: dict) -> dict:
    """Canonical marketplace source fields shared by PMS and ledger records."""
    return {
        "marketplace_agency_id": agency["agency_id"],
        "marketplace_agency_name": agency["agency_name"],
        "agency_id": agency["agency_id"],
        "agency_name": agency["agency_name"],
        "channel": "marketplace",
        "source_channel": "marketplace",
        "origin": "syroce_marketplace",
    }


# ─── Pydantic Modelleri ───────────────────────────────────────────────────


class MarketplaceAgencyCreate(BaseModel):
    name: str
    contact_email: str = ""
    contact_phone: str = ""
    country: str = "TR"
    default_commission_pct: float = Field(default=12.0, ge=0, le=100)
    platform_fee_pct: float | None = Field(default=None, ge=0, le=100)


class MarketplaceAgencyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=160)
    contact_email: str | None = Field(default=None, max_length=320)
    contact_phone: str | None = Field(default=None, max_length=40)
    country: str | None = Field(default=None, min_length=2, max_length=2)
    default_commission_pct: float | None = Field(default=None, ge=0, le=100)
    platform_fee_pct: float | None = Field(default=None, ge=0, le=100)
    status: str | None = Field(default=None, pattern="^(active|disabled)$")


class MarketplaceListingCreate(BaseModel):
    hotel_name: str
    city: str
    country: str = "TR"
    address: str = ""
    description: str = ""
    photos: list[str] = []
    amenities: list[str] = []
    meal_plans: list[str] = []
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
    meal_plans: list[str] | None = None
    star_rating: int | None = Field(default=None, ge=1, le=5)
    commission_pct: float | None = Field(default=None, ge=0, le=100)
    allowed_room_types: list[str] | None = None
    blocked_dates: list[str] | None = None
    is_listed: bool | None = None


class MarketplaceSearchRequest(BaseModel):
    check_in: str  # YYYY-MM-DD
    check_out: str  # YYYY-MM-DD
    adults: int = Field(default=2, ge=1, le=20)
    children: int = Field(default=0, ge=0, le=20)
    child_ages: list[int] = Field(default_factory=list, max_length=20)
    city: str | None = None
    country: str | None = None
    q: str | None = None
    amenities: list[str] = Field(default_factory=list, max_length=30)
    meal_plans: list[str] = Field(default_factory=list, max_length=10)
    min_star_rating: int | None = Field(default=None, ge=1, le=5)
    max_price: float | None = None
    limit: int = Field(default=50, le=200)

    @model_validator(mode="after")
    def validate_child_ages(self):
        if any(age < 0 or age > 17 for age in self.child_ages):
            raise ValueError("Çocuk yaşları 0-17 arasında olmalıdır")
        if len(self.child_ages) != self.children:
            raise ValueError("Her çocuk için yaş bilgisi girilmelidir")
        return self


def _filter_token(value: object) -> str:
    """Normalize marketplace facets without relying on display language/casing."""
    import re
    import unicodedata

    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    token = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    aliases = {
        "havuz": "pool", "jakuzi": "jacuzzi", "plaj": "beach",
        "deniz_manzarasi": "sea_view", "deniz_manzaras": "sea_view",
        "oda_kahvalti": "bb", "bed_breakfast": "bb", "breakfast_included": "bb",
        "sadece_oda": "ro", "room_only": "ro",
        "yarim_pansiyon": "hb", "half_board": "hb",
        "tam_pansiyon": "fb", "full_board": "fb",
        "her_sey_dahil": "ai", "all_inclusive": "ai",
    }
    return aliases.get(token, token)


def _normalized_tokens(values: list[object] | None) -> set[str]:
    return {token for value in (values or []) if (token := _filter_token(value))}


class MarketplaceReservationCreate(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=128)
    room_type: str = Field(..., min_length=1, max_length=160)
    check_in: str  # YYYY-MM-DD
    check_out: str  # YYYY-MM-DD
    guest_name: str = Field(..., min_length=2, max_length=160)
    guest_email: EmailStr | None = None
    guest_phone: str = Field(default="", max_length=40)
    adults: int = Field(default=2, ge=1, le=20)
    children: int = Field(default=0, ge=0, le=20)
    child_ages: list[int] = Field(default_factory=list, max_length=20)
    special_requests: str = Field(default="", max_length=1000)
    total_amount: float = Field(default=0, ge=0)
    external_reference: str = Field(default="", max_length=160)  # Acentenin kendi PNR/voucher kodu
    idempotency_key: str | None = Field(default=None, min_length=8, max_length=128)

    @model_validator(mode="after")
    def validate_child_ages(self):
        if any(age < 0 or age > 17 for age in self.child_ages):
            raise ValueError("Çocuk yaşları 0-17 arasında olmalıdır")
        if len(self.child_ages) != self.children:
            raise ValueError("Her çocuk için yaş bilgisi girilmelidir")
        return self


class CancellationProposalCreate(BaseModel):
    reason: str = Field(..., min_length=5, max_length=1000)


class CancellationProposalDecision(BaseModel):
    accept: bool
    response_note: str = Field(default="", max_length=1000)


class VoucherEmailRequest(BaseModel):
    email: EmailStr


class ModificationProposalCreate(BaseModel):
    check_in: str
    check_out: str
    room_type: str = Field(..., min_length=1, max_length=160)
    reason: str = Field(..., min_length=5, max_length=1000)


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
    if data.platform_fee_pct is not None:
        agency_doc["platform_fee_pct"] = data.platform_fee_pct
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
    contract_rows = await sysdb.agency_contracts.aggregate([
        {"$match": {"status": "approved"}},
        {"$group": {"_id": "$agency_id", "connected_hotels": {"$addToSet": "$tenant_id"}}},
    ]).to_list(500)
    booking_rows = await sysdb.marketplace_bookings.aggregate([
        {"$match": {"status": {"$ne": "cancelled"}}},
        {"$group": {"_id": "$agency_id", "booking_count": {"$sum": 1}, "gross_volume": {"$sum": "$total_amount"}, "platform_revenue": {"$sum": "$syroce_b2b_fee_amount"}}},
    ]).to_list(500)
    contract_stats = {row["_id"]: len(row.get("connected_hotels") or []) for row in contract_rows}
    booking_stats = {row["_id"]: row for row in booking_rows}
    for agency in docs:
        agency_id = agency.get("id")
        stats = booking_stats.get(agency_id, {})
        agency["connected_hotels"] = contract_stats.get(agency_id, 0)
        agency["booking_count"] = int(stats.get("booking_count", 0) or 0)
        agency["gross_volume"] = round(float(stats.get("gross_volume", 0) or 0), 2)
        agency["platform_revenue"] = round(float(stats.get("platform_revenue", 0) or 0), 2)
    return {"agencies": docs, "total": len(docs)}


@router.patch("/admin/agencies/{agency_id}")
async def admin_update_agency(
    agency_id: str,
    data: MarketplaceAgencyUpdate,
    _: bool = Depends(_require_system_admin),
):
    sysdb = get_system_db()
    updates = data.model_dump(exclude_none=True)
    if "name" in updates:
        updates["name"] = updates["name"].strip()
    if "contact_email" in updates:
        updates["contact_email"] = updates["contact_email"].strip().lower()
    if "contact_phone" in updates:
        updates["contact_phone"] = updates["contact_phone"].strip()
    if "country" in updates:
        updates["country"] = updates["country"].upper()
    if not updates:
        raise HTTPException(400, "Güncellenecek alan bulunamadı")
    updates["updated_at"] = _now_iso()
    result = await sysdb.marketplace_agencies.update_one({"id": agency_id}, {"$set": updates})
    if result.matched_count == 0:
        raise HTTPException(404, "Acente bulunamadı")
    agency = await sysdb.marketplace_agencies.find_one({"id": agency_id}, {"_id": 0})
    return {"ok": True, "agency": agency}


@router.delete("/admin/agencies/{agency_id}")
async def admin_disable_agency(
    agency_id: str,
    _: bool = Depends(_require_system_admin),
):
    sysdb = get_system_db()
    res = await sysdb.marketplace_agencies.update_one({"id": agency_id}, {"$set": {"status": "disabled", "disabled_at": _now_iso()}})
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
    await sysdb.marketplace_api_keys.insert_one(
        {
            "id": _uuid(),
            "agency_id": agency_id,
            "key_hash": _hash_key(raw_key),
            "key_prefix": raw_key[:18] + "...",
            "is_active": True,
            "usage_count": 0,
            "created_at": _now_iso(),
            "last_used_at": None,
        }
    )
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
        "meal_plans": data.meal_plans or [],
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
        await sysdb.marketplace_listings.update_one({"tenant_id": tenant_id}, {"$set": {**{k: v for k, v in doc.items() if k != "id"}, "id": existing["id"]}})
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
        return {"hotels": [], "total": 0, "message": "Henüz onaylı sözleşmeniz olan otel yok. Önce otele teklif gönderin."}

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

    docs = (
        await sysdb.marketplace_listings.find(
            query,
            {"_id": 0, "blocked_dates": 0, "created_by": 0},
        )
        .limit(limit)
        .to_list(limit)
    )
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
        if r.get("is_active") is False or r.get("status") in {"maintenance", "out_of_order", "blocked"}:
            continue
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

    last_night = _last_occupied_date(req.check_in, req.check_out)
    partner_tenant_ids = await list_partner_tenant_ids(
        agency["agency_id"], on_date=req.check_in, through_date=last_night
    )
    if not partner_tenant_ids:
        return {"check_in": req.check_in, "check_out": req.check_out, "results": [], "total_hotels": 0, "message": "Henüz onaylı sözleşmeniz olan otel yok."}

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
    if req.min_star_rating:
        list_query["star_rating"] = {"$gte": req.min_star_rating}

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

            requested_amenities = _normalized_tokens(req.amenities)
            listing_amenities = _normalized_tokens(listing.get("amenities"))
            requested_meals = _normalized_tokens(req.meal_plans)
            known_meals = {"ro", "bb", "hb", "fb", "ai"}
            listing_meals = _normalized_tokens(listing.get("meal_plans")) | (
                listing_amenities & known_meals
            )
            room_amenities = set().union(*(
                _normalized_tokens(room.get("amenities")) for room in rooms
            )) if rooms else set()
            room_meals = set()
            for room in rooms:
                room_meals |= _normalized_tokens([room.get("meal_plan"), room.get("board_type")])
                room_meals |= _normalized_tokens(room.get("amenities")) & known_meals
            if not requested_amenities.issubset(listing_amenities | room_amenities):
                continue
            if requested_meals and not requested_meals.intersection(listing_meals | room_meals):
                continue

            room_types: dict[str, dict] = {}
            for r in rooms:
                if r.get("is_active") is False or r.get("status") in {"maintenance", "out_of_order", "blocked"}:
                    continue
                rt = r.get("room_type", "Standard")
                if listing.get("allowed_room_types") and rt not in listing["allowed_room_types"]:
                    continue
                if r.get("capacity", 2) < capacity_needed:
                    continue
                # Hotel-level features (pool, beach, etc.) apply to every room;
                # room-level features (jacuzzi, sea view, etc.) must be present on
                # the selected room type when not declared by the hotel listing.
                required_room_amenities = requested_amenities - listing_amenities
                if not required_room_amenities.issubset(_normalized_tokens(r.get("amenities"))):
                    continue
                current_room_meals = _normalized_tokens([r.get("meal_plan"), r.get("board_type")])
                current_room_meals |= _normalized_tokens(r.get("amenities")) & known_meals
                if requested_meals and not requested_meals.intersection(listing_meals | current_room_meals):
                    continue
                rt_data = room_types.setdefault(
                    rt,
                    {
                        "room_type": rt,
                        "capacity": r.get("capacity", 2),
                        "base_price": r.get("base_price", 0),
                        "total_rooms": 0,
                        "available_rooms": 0,
                        "amenities": r.get("amenities", []),
                        "meal_plan": r.get("meal_plan") or r.get("board_type") or "",
                        "_room_ids": [],
                    },
                )
                rt_data["total_rooms"] += 1
                rt_data["_room_ids"].append(r.get("id"))

            for rt_data in room_types.values():
                booked = await db.bookings.count_documents(
                    {
                        "tenant_id": tenant_id,
                        "room_id": {"$in": rt_data["_room_ids"]},
                        "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
                        # Half-open hotel-night overlap. A same-day departure
                        # must not consume the arriving guest's room-night.
                        "check_in": {"$lt": req.check_out + "T00:00:00"},
                        "check_out": {"$gt": req.check_in + "T00:00:00"},
                    }
                )
                rt_data["available_rooms"] = max(0, rt_data["total_rooms"] - booked)
                pricing = await _marketplace_stay_price(
                    tenant_id=tenant_id,
                    agency_id=agency["agency_id"],
                    room_type=rt_data["room_type"],
                    check_in=req.check_in,
                    check_out=req.check_out,
                    fallback_rate=float(rt_data["base_price"] or 0),
                )
                pricing = await _marketplace_occupancy_price(
                    tenant_id=tenant_id,
                    room=rt_data,
                    pricing=pricing,
                    adults=req.adults,
                    child_ages=req.child_ages,
                )
                if pricing.get("shared_availability") is not None:
                    rt_data["available_rooms"] = min(
                        rt_data["available_rooms"], pricing["shared_availability"]
                    )
                rt_data["pricing"] = pricing
                del rt_data["_room_ids"]

        # Sadece müsait oda tipleri olan otelleri ekle
        nights = (co - ci).days
        commission_pct = _commission_for(agency, listing)
        available = []
        for rt_data in room_types.values():
            pricing = rt_data.pop("pricing")
            if rt_data["available_rooms"] <= 0 or not pricing["sellable"]:
                continue
            total_price = pricing["total_price"]
            if req.max_price and total_price > req.max_price:
                continue
            available.append(
                {
                    **rt_data,
                    "nights": nights,
                    "total_price": total_price,
                    "nightly_rates": pricing["nightly_rates"],
                    "currency": listing.get("currency", "TRY"),
                    "commission_pct": commission_pct,
                    "agency_payable": round(total_price * (1 - commission_pct / 100), 2),
                }
            )

        if available:
            results.append(
                {
                    "tenant_id": tenant_id,
                    "hotel_name": listing.get("hotel_name"),
                    "city": listing.get("city"),
                    "country": listing.get("country"),
                    "star_rating": listing.get("star_rating"),
                    "photos": listing.get("photos", [])[:3],
                    "description": listing.get("description", ""),
                    "amenities": listing.get("amenities", []),
                    "meal_plans": listing.get("meal_plans", []),
                    "currency": listing.get("currency", "TRY"),
                    "available_room_types": available,
                }
            )

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

    last_night = _last_occupied_date(check_in, check_out)
    if not await has_active_contract(
        agency["agency_id"], tenant_id, on_date=check_in, through_date=last_night
    ):
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
            if r.get("is_active") is False or r.get("status") in {"maintenance", "out_of_order", "blocked"}:
                continue
            rt = r.get("room_type", "Standard")
            if listing.get("allowed_room_types") and rt not in listing["allowed_room_types"]:
                continue
            rt_data = room_types.setdefault(
                rt,
                {
                    "room_type": rt,
                    "capacity": r.get("capacity", 2),
                    "base_price": r.get("base_price", 0),
                    "amenities": r.get("amenities", []),
                    "total_rooms": 0,
                    "available_rooms": 0,
                    "_room_ids": [],
                },
            )
            rt_data["total_rooms"] += 1
            rt_data["_room_ids"].append(r.get("id"))

        nights = (co - ci).days
        commission_pct = _commission_for(agency, listing)
        for rt_data in room_types.values():
            booked = await db.bookings.count_documents(
                {
                    "tenant_id": tenant_id,
                    "room_id": {"$in": rt_data["_room_ids"]},
                    "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
                    "check_in": {"$lt": check_out + "T00:00:00"},
                    "check_out": {"$gt": check_in + "T00:00:00"},
                }
            )
            rt_data["available_rooms"] = max(0, rt_data["total_rooms"] - booked)
            pricing = await _marketplace_stay_price(
                tenant_id=tenant_id,
                agency_id=agency["agency_id"],
                room_type=rt_data["room_type"],
                check_in=check_in,
                check_out=check_out,
                fallback_rate=float(rt_data["base_price"] or 0),
            )
            pricing = await _marketplace_occupancy_price(
                tenant_id=tenant_id,
                room=rt_data,
                pricing=pricing,
                adults=req.adults,
                child_ages=req.child_ages,
            )
            if pricing.get("shared_availability") is not None:
                rt_data["available_rooms"] = min(
                    rt_data["available_rooms"], pricing["shared_availability"]
                )
            rt_data["nights"] = nights
            rt_data["total_price"] = pricing["total_price"]
            rt_data["nightly_rates"] = pricing["nightly_rates"]
            rt_data["occupancy_pricing"] = pricing["occupancy_pricing"]
            if not pricing["sellable"]:
                rt_data["available_rooms"] = 0
            rt_data["commission_pct"] = commission_pct
            rt_data["agency_payable"] = round(rt_data["total_price"] * (1 - commission_pct / 100), 2)
            del rt_data["_room_ids"]

    return {
        "check_in": check_in,
        "check_out": check_out,
        "hotel_name": listing.get("hotel_name"),
        "currency": listing.get("currency", "TRY"),
        "room_types": list(room_types.values()),
    }


@router.get("/hotels/{tenant_id}/rates")
async def agency_hotel_rates(
    tenant_id: str,
    start_date: str = Query(..., description="YYYY-MM-DD"),
    end_date: str = Query(..., description="YYYY-MM-DD"),
    room_type: str | None = Query(None),
    agency: dict = Depends(get_marketplace_agency),
):
    from routers.agency_contracts import has_active_contract

    if not await has_active_contract(
        agency["agency_id"], tenant_id, on_date=start_date, through_date=end_date
    ):
        raise HTTPException(403, "Bu otelle aktif sözleşmeniz yok")
    await _get_listing_or_404(tenant_id)
    base_query = {
        "tenant_id": tenant_id,
        "date": {"$gte": start_date, "$lte": end_date},
    }
    if room_type:
        base_query["room_type_code"] = room_type

    with tenant_context(tenant_id):
        rates = await db.agency_rate_calendar.find(
            {**base_query, "agency_id": agency["agency_id"]},
            {"_id": 0, "tenant_id": 0, "agency_id": 0},
        ).sort("date", 1).to_list(5000)
        source = "agency_rates"
        if not rates:
            source = "hotel_rates"
            rates = await db.hr_rate_calendar.find(base_query, {"_id": 0, "tenant_id": 0}).sort("date", 1).to_list(5000)
        if not rates:
            rates = await db.rate_calendar.find(base_query, {"_id": 0, "tenant_id": 0}).sort("date", 1).to_list(5000)
    return {"start_date": start_date, "end_date": end_date, "source": source, "rates": rates}


# ═══════════════════════════════════════════════════════════════════════
# AGENCY — Reservation Lifecycle (Cross-tenant)
# ═══════════════════════════════════════════════════════════════════════


async def agency_create_reservation(
    data: MarketplaceReservationCreate,
    background_tasks: BackgroundTasks,
    agency: dict = Depends(get_marketplace_agency),
):
    """Listed otele cross-tenant rezervasyon oluştur. Mevcut bookings koleksiyonuna düşer."""
    from routers.agency_contracts import has_active_contract

    sysdb = get_system_db()
    if data.idempotency_key:
        existing = await sysdb.marketplace_bookings.find_one(
            {
                "agency_id": agency["agency_id"],
                "idempotency_key": data.idempotency_key,
            },
            {"_id": 0},
        )
        if existing:
            if existing.get("tenant_id") != data.tenant_id:
                raise HTTPException(409, "Bu işlem anahtarı farklı bir tesis rezervasyonunda kullanılmış")
            return {"ok": True, "reservation": existing, "idempotent_replay": True}

    last_night = _last_occupied_date(data.check_in, data.check_out)
    contract = await has_active_contract(
        agency["agency_id"],
        data.tenant_id,
        on_date=data.check_in,
        through_date=last_night,
    )
    if not contract:
        raise HTTPException(403, "Bu otelle bu tarih için aktif sözleşmeniz yok. Önce sözleşme teklifi gönderip otelin onayını bekleyin.")

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

    # Room selection is followed by create_booking_atomic below; its room-night
    # lock is the authoritative race-safety guard under concurrent requests.
    with tenant_context(data.tenant_id):
        rooms = await db.rooms.find(
            {
                "tenant_id": data.tenant_id,
                "room_type": data.room_type,
                "is_active": {"$ne": False},
                "status": {"$nin": ["maintenance", "out_of_order", "blocked"]},
            },
            {"_id": 0},
        ).to_list(500)
        rooms = [room for room in rooms if int(room.get("capacity") or 2) >= data.adults + data.children]
        if not rooms:
            raise HTTPException(404, "Uygun kapasitede, satışa açık oda tipi bulunamadı")

        available_room = None
        for room in rooms:
            conflict = await db.bookings.count_documents(
                {
                    "tenant_id": data.tenant_id,
                    "room_id": room["id"],
                    "status": {"$in": ["confirmed", "guaranteed", "checked_in", "pending"]},
                    "check_in": {"$lt": data.check_out + "T00:00:00"},
                    "check_out": {"$gt": data.check_in + "T00:00:00"},
                }
            )
            if conflict == 0:
                available_room = room
                break

        if not available_room:
            raise HTTPException(409, "Seçilen tarihler için müsait oda yok")

        # Komisyon: sözleşmede otelin onayladığı oran (override edilmiş olabilir) kullanılır
        commission_pct = float(contract.get("commission_pct", _commission_for(agency, listing)))
        # Retain the explicit calendar-night/base calculation as a safe
        # fallback and as executable documentation of checkout exclusivity.
        nights = (co.date() - ci.date()).days
        server_total = float(available_room.get("base_price", 0)) * max(nights, 1)
        pricing = await _marketplace_stay_price(
            tenant_id=data.tenant_id,
            agency_id=agency["agency_id"],
            room_type=data.room_type,
            check_in=data.check_in,
            check_out=data.check_out,
            fallback_rate=float(available_room.get("base_price", 0) or 0),
        )
        if not pricing["sellable"]:
            raise HTTPException(409, "Seçilen oda tipi bu tarihlerde acente satışına kapalı")
        pricing = await _marketplace_occupancy_price(
            tenant_id=data.tenant_id,
            room=available_room,
            pricing=pricing,
            adults=data.adults,
            child_ages=data.child_ages,
        )
        # Server-side "ground truth" price. Search and booking use this exact helper.
        server_total: float = pricing["total_price"]
        if data.total_amount and data.total_amount > 0:
            if abs(data.total_amount - server_total) > PRICE_TOLERANCE:
                raise HTTPException(
                    422,
                    f"Fiyat uyuşmazlığı: gönderilen {data.total_amount}, beklenen {server_total} (tolerans ±{PRICE_TOLERANCE}). Lütfen güncel fiyat için /search çağrısını tekrarlayın.",
                )
        total = server_total
        commission_amount = round(total * commission_pct / 100, 2)
        syroce_b2b_fee_pct, syroce_b2b_fee_amount = _syroce_b2b_fee(
            total,
            agency.get("source", "syroce_agency_app"),
            agency.get("platform_fee_pct"),
        )
        # The platform fee is the agency's liability to Syroce; it must not
        # reduce the hotel's contracted payout a second time.
        net_to_hotel = round(total - commission_amount, 2)
        credit_limit = contract.get("credit_limit")
        if credit_limit is not None:
            debt_pipeline = [
                {"$match": {"agency_id": agency["agency_id"], "tenant_id": data.tenant_id, "status": {"$ne": "cancelled"}, "payment_status": {"$ne": "paid"}}},
                {"$group": {"_id": None, "amount": {"$sum": "$net_to_hotel"}}},
            ]
            debt_rows = await sysdb.marketplace_bookings.aggregate(debt_pipeline).to_list(1)
            current_debt = float(debt_rows[0].get("amount", 0)) if debt_rows else 0.0
            if current_debt + net_to_hotel > float(credit_limit):
                raise HTTPException(409, "Acente kredi limiti bu rezervasyon için yetersiz")

        guest_id = _uuid()
        from security.guest_write import encrypt_guest_insert

        await db.guests.insert_one(
            encrypt_guest_insert(
                {
                    "id": guest_id,
                    "tenant_id": data.tenant_id,
                    "name": data.guest_name.strip(),
                    "email": str(data.guest_email or "").strip().lower() or f"agency-{guest_id[:8]}@placeholder.local",
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

        booking_id = _uuid()
        confirmation_code = f"MKT-{booking_id[:8].upper()}"
        room_snapshot = _reservation_room_snapshot(available_room)
        agency_snapshot = _reservation_agency_snapshot(agency)
        booking_doc = {
            "id": booking_id,
            "tenant_id": data.tenant_id,
            "guest_id": guest_id,
            "room_id": available_room["id"],
            **room_snapshot,
            "check_in": data.check_in + "T14:00:00",
            "check_out": data.check_out + "T11:00:00",
            "adults": data.adults,
            "children": data.children,
            "child_ages": data.child_ages,
            "guests_count": data.adults + data.children,
            "status": "confirmed",
            "payment_status": "pending",
            "payment_terms": contract.get("payment_terms", "on_arrival"),
            "cancellation_policy": contract.get("cancellation_policy") or {},
            "total_amount": total,
            "currency": listing.get("currency", "TRY"),
            "nightly_rates": pricing["nightly_rates"],
            "balance": total,
            # Canonical fields are shared with hotel-created agency bookings so
            # every PMS surface can identify the exact seller consistently.
            **agency_snapshot,
            "agency_commission_rate": commission_pct,
            "agency_commission_amount": commission_amount,
            "net_to_hotel": net_to_hotel,
            "confirmation_code": confirmation_code,
            "external_reference": data.external_reference,
            "special_requests": data.special_requests,
            "guest_name": data.guest_name.strip(),
            "guest_email": str(data.guest_email or "").strip().lower(),
            "guest_phone": data.guest_phone.strip(),
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        }
        # v106 architect follow-up (race-safety): direct insert_one bypassed
        # the room_night_locks atomic guard → marketplace agencies could
        # double-book the same room across concurrent requests. Now routed
        # through create_booking_atomic.
        try:
            booking_doc = await create_booking_atomic(tenant_id=data.tenant_id, booking_doc=booking_doc)
        except BookingConflictError as conflict_err:
            await db.guests.delete_one({"id": guest_id, "tenant_id": data.tenant_id})
            raise HTTPException(status_code=409, detail=str(conflict_err))
        except Exception:
            await db.guests.delete_one({"id": guest_id, "tenant_id": data.tenant_id})
            raise

        # The booking is durable from this point. Ancillary delivery failures
        # are logged instead of returning an error that could cause a duplicate
        # agency retry.
        try:
            from models.schemas import Folio, FolioType

            folio = Folio(
                id=_uuid(),
                tenant_id=data.tenant_id,
                booking_id=booking_id,
                folio_type=FolioType.GUEST,
                guest_id=guest_id,
            )
            folio_dict = folio.model_dump()
            folio_dict["created_at"] = folio_dict["created_at"].isoformat()
            await db.folios.insert_one(folio_dict)
        except Exception as exc:
            logger.warning("Marketplace folio creation failed booking=%s error=%s", booking_id, type(exc).__name__)

        try:
            from routers.pms_bookings import _publish_multi_room_booking_created_events

            property_id = data.tenant_id
            await _publish_multi_room_booking_created_events(
                tenant_id=data.tenant_id,
                property_id=property_id,
                bookings=[booking_doc],
            )
            from core.ws_rooms import tenant_broadcast_room
            from websocket_server import sio

            await sio.emit("booking_created", {"booking": booking_doc}, room=tenant_broadcast_room(data.tenant_id))
        except Exception as exc:
            logger.warning("Marketplace live publish failed booking=%s error=%s", booking_id, type(exc).__name__)

        try:
            await db.notifications.insert_one(
                {
                    "id": _uuid(),
                    "tenant_id": data.tenant_id,
                    "user_id": None,
                    "type": "reservation",
                    "title": f"Yeni Acente Rezervasyonu: {data.guest_name.strip()}",
                    "message": (
                        f"{agency['agency_name']} tarafından yeni rezervasyon oluşturuldu. "
                        f"Giriş: {data.check_in}, Çıkış: {data.check_out}, "
                        f"Oda: {available_room.get('room_number', '-')}, "
                        f"Tutar: {total:.2f} {listing.get('currency', 'TRY')}"
                    ),
                    "priority": "high",
                    "read": False,
                    "action_url": f"/reservations?booking_id={booking_id}",
                    "metadata": {
                        "booking_id": booking_id,
                        "agency_id": agency["agency_id"],
                        "agency_name": agency["agency_name"],
                        "channel": "marketplace",
                    },
                    "created_at": _now_iso(),
                }
            )
        except Exception as exc:
            logger.warning("Marketplace notification failed booking=%s error=%s", booking_id, type(exc).__name__)

    # Cross-tenant ledger (ileride mutabakat için) — sysdb tenant-bağımsız
    ledger_doc = {
            "id": booking_id,
            **agency_snapshot,
            "tenant_id": data.tenant_id,
            "hotel_name": listing.get("hotel_name"),
            **room_snapshot,
            "confirmation_code": confirmation_code,
            "external_reference": data.external_reference,
            "idempotency_key": data.idempotency_key,
            "check_in": data.check_in,
            "check_out": data.check_out,
            "guest_name": data.guest_name,
            "total_amount": total,
            "currency": listing.get("currency", "TRY"),
            "nightly_rates": pricing["nightly_rates"],
            "commission_pct": commission_pct,
            "commission_amount": commission_amount,
            "syroce_b2b_fee_pct": syroce_b2b_fee_pct,
            "syroce_b2b_fee_amount": syroce_b2b_fee_amount,
            "net_to_hotel": net_to_hotel,
            "status": "confirmed",
            "payment_status": "pending",
            "payment_terms": contract.get("payment_terms", "on_arrival"),
            "cancellation_policy": contract.get("cancellation_policy") or {},
            "created_at": _now_iso(),
        }
    try:
        await sysdb.marketplace_bookings.update_one(
            {"agency_id": agency["agency_id"], "id": booking_id},
            {"$setOnInsert": ledger_doc},
            upsert=True,
        )
    except Exception as exc:
        # The PMS booking is already durable. Never return a false failure that
        # encourages the agency to submit a second reservation.
        logger.error("Marketplace ledger write failed booking=%s error=%s", booking_id, type(exc).__name__)

    # Webhook bildirimi (otele)
    try:
        from routers.b2b_api import fire_webhooks

        background_tasks.add_task(
            fire_webhooks,
            data.tenant_id,
            agency["agency_id"],
            "marketplace.reservation.created",
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
            **room_snapshot,
            "check_in": data.check_in,
            "check_out": data.check_out,
            "guest_name": data.guest_name,
            "total_amount": total,
            "currency": listing.get("currency", "TRY"),
            "nightly_rates": pricing["nightly_rates"],
            "commission_pct": commission_pct,
            "commission_amount": commission_amount,
            "syroce_b2b_fee_pct": syroce_b2b_fee_pct,
            "syroce_b2b_fee_amount": syroce_b2b_fee_amount,
            "net_to_hotel": net_to_hotel,
        },
    }


@router.post("/reservations")
async def agency_create_reservation_endpoint(
    data: MarketplaceReservationCreate,
    background_tasks: BackgroundTasks,
    agency: dict = Depends(get_marketplace_agency),
):
    """Create once even when the agency retries concurrently after a timeout."""
    sysdb = get_system_db()
    guard = None
    if data.idempotency_key:
        claim = await claim_idempotency(
            sysdb,
            tenant_id=agency["agency_id"],
            scope="marketplace_reservation",
            idempotency_key=data.idempotency_key,
            request_hash=build_request_hash(data.model_dump()),
        )
        if claim["status"] == "replay":
            response = claim.get("response") or {}
            if response:
                return response
            existing = await sysdb.marketplace_bookings.find_one(
                {"agency_id": agency["agency_id"], "idempotency_key": data.idempotency_key}, {"_id": 0}
            )
            if existing:
                return {"ok": True, "reservation": existing, "idempotent_replay": True}
            raise HTTPException(409, "Önceki rezervasyon işlendi; sonucu rezervasyon listesinden kontrol edin")
        if claim["status"] == "in_flight":
            raise HTTPException(409, "Aynı rezervasyon isteği halen işleniyor")
        if claim["status"] == "mismatch":
            raise HTTPException(409, "Bu işlem anahtarı farklı rezervasyon bilgileriyle kullanılmış")
        guard = claim["lock_id"]
    try:
        result = await agency_create_reservation(data, background_tasks, agency)
        if guard:
            try:
                await complete_idempotency(sysdb, lock_id=guard, response_body=result)
            except Exception as exc:
                # Reservation and cross-tenant ledger are already durable.
                logger.error("Marketplace idempotency completion failed: %s", type(exc).__name__)
        return result
    except Exception as exc:
        if guard:
            await release_idempotency(sysdb, lock_id=guard, error=type(exc).__name__)
        raise


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

    docs = await sysdb.marketplace_bookings.find(query, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"reservations": docs, "total": len(docs)}


@router.get("/reservations/{reservation_id}")
async def agency_get_reservation(
    reservation_id: str,
    agency: dict = Depends(get_marketplace_agency),
):
    sysdb = get_system_db()
    doc = await sysdb.marketplace_bookings.find_one({"id": reservation_id, "agency_id": agency["agency_id"]}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "Rezervasyon bulunamadı")

    with tenant_context(doc["tenant_id"]):
        booking = await db.bookings.find_one(
            {"id": reservation_id, "tenant_id": doc["tenant_id"]},
            {
                "_id": 0,
                "tenant_id": 0,
                "guest_id": 0,
                "room_id": 0,
                "guest_email": 0,
                "guest_phone": 0,
                "_hash_guest_email": 0,
                "_hash_guest_phone": 0,
                "_enc_version": 0,
                "_encrypted_at": 0,
                "guest_name_lower": 0,
            },
        )
    return {"summary": doc, "booking": booking}


def _voucher_html(doc: dict) -> str:
    safe = lambda value: html.escape(str(value or "—"))
    return f"""<!doctype html><html><head><meta charset='utf-8'><style>body{{font-family:Arial;color:#172033;padding:32px}}.sheet{{border:1px solid #ccd5e1;border-radius:12px;padding:24px}}table{{width:100%;border-collapse:collapse}}td{{padding:10px;border-bottom:1px solid #eee}}</style></head><body><div class='sheet'><h1>Rezervasyon Voucher</h1><table><tr><td>Onay kodu</td><td>{safe(doc.get('confirmation_code'))}</td></tr><tr><td>Otel</td><td>{safe(doc.get('hotel_name'))}</td></tr><tr><td>Misafir</td><td>{safe(doc.get('guest_name'))}</td></tr><tr><td>Giriş / Çıkış</td><td>{safe(doc.get('check_in'))} / {safe(doc.get('check_out'))}</td></tr><tr><td>Tutar</td><td>{safe(doc.get('total_amount'))} {safe(doc.get('currency', 'TRY'))}</td></tr></table><p>Syroce Acente Portalı tarafından oluşturulmuştur.</p></div></body></html>"""


@router.get("/reservations/{reservation_id}/voucher.pdf")
async def agency_reservation_voucher_pdf(reservation_id: str, agency: dict = Depends(get_marketplace_agency)):
    doc = await get_system_db().marketplace_bookings.find_one(
        {"id": reservation_id, "agency_id": agency["agency_id"]}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(404, "Rezervasyon bulunamadı")
    try:
        from weasyprint import HTML
        pdf = HTML(string=_voucher_html(doc)).write_pdf()
    except Exception as exc:
        raise HTTPException(503, "PDF oluşturucu şu anda kullanılamıyor") from exc
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={doc.get('confirmation_code', reservation_id)}.pdf"})


@router.post("/reservations/{reservation_id}/voucher-email")
async def agency_email_reservation_voucher(
    reservation_id: str, data: VoucherEmailRequest, agency: dict = Depends(get_marketplace_agency)
):
    doc = await get_system_db().marketplace_bookings.find_one(
        {"id": reservation_id, "agency_id": agency["agency_id"]}, {"_id": 0}
    )
    if not doc:
        raise HTTPException(404, "Rezervasyon bulunamadı")
    from core.email import send_email
    result = await send_email(str(data.email), f"Rezervasyon Voucher · {doc.get('confirmation_code')}", _voucher_html(doc))
    if not result:
        raise HTTPException(502, "Voucher e-postası gönderilemedi")
    return {"ok": True, "message": "Voucher e-postası gönderildi"}


@router.delete("/reservations/{reservation_id}")
async def agency_cancel_reservation(
    reservation_id: str,
    reason: str = Query("agency_request"),
    agency: dict = Depends(get_marketplace_agency),
):
    """Open a cancellation negotiation; hotel approval is mandatory."""
    sysdb = get_system_db()
    summary = await sysdb.marketplace_bookings.find_one({"id": reservation_id, "agency_id": agency["agency_id"]}, {"_id": 0})
    if not summary:
        raise HTTPException(404, "Rezervasyon bulunamadı")
    if summary.get("status") == "cancelled":
        return {"ok": True, "message": "Rezervasyon zaten iptal edilmiş"}
    normalized_reason = reason.strip()
    if len(normalized_reason) < 5:
        raise HTTPException(400, "İptal gerekçesi en az 5 karakter olmalıdır")
    existing = await sysdb.marketplace_negotiations.find_one(
        {"reservation_id": reservation_id, "type": "agency_cancellation", "status": "awaiting_hotel"},
        {"_id": 0},
    )
    if existing:
        raise HTTPException(409, "Bu rezervasyon için otel yanıtı bekleyen iptal talebi zaten var")
    proposal = {
        "id": _uuid(),
        "reservation_id": reservation_id,
        "tenant_id": summary["tenant_id"],
        "agency_id": agency["agency_id"],
        "hotel_name": summary.get("hotel_name"),
        "confirmation_code": summary.get("confirmation_code"),
        "guest_name": summary.get("guest_name"),
        "type": "agency_cancellation",
        "reason": normalized_reason,
        "status": "awaiting_hotel",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await sysdb.marketplace_negotiations.insert_one(proposal)
    with tenant_context(summary["tenant_id"]):
        await db.notifications.insert_one(
            {
                "id": _uuid(),
                "tenant_id": summary["tenant_id"],
                "type": "agency_negotiation",
                "title": "Acente iptal onayı bekliyor",
                "message": f"{summary.get('confirmation_code')} için iptal talebi iletildi.",
                "read": False,
                "metadata": {"proposal_id": proposal["id"], "reservation_id": reservation_id},
                "created_at": _now_iso(),
            }
        )
    return {"ok": True, "message": "İptal talebi otele iletildi", "proposal": {k: v for k, v in proposal.items() if k != "_id"}}


@router.post("/reservations/{reservation_id}/modification-proposals")
async def agency_propose_reservation_modification(
    reservation_id: str,
    data: ModificationProposalCreate,
    agency: dict = Depends(get_marketplace_agency),
):
    """Request a stay/room change; PMS approval is mandatory before mutation."""
    if data.check_out <= data.check_in:
        raise HTTPException(400, "Çıkış tarihi giriş tarihinden sonra olmalıdır")
    sysdb = get_system_db()
    booking = await sysdb.marketplace_bookings.find_one(
        {"id": reservation_id, "agency_id": agency["agency_id"], "status": "confirmed"}, {"_id": 0}
    )
    if not booking:
        raise HTTPException(404, "Değiştirilebilir aktif rezervasyon bulunamadı")
    existing = await sysdb.marketplace_negotiations.find_one(
        {"reservation_id": reservation_id, "type": "agency_modification", "status": "awaiting_hotel"}
    )
    if existing:
        raise HTTPException(409, "Bu rezervasyon için otel yanıtı bekleyen değişiklik zaten var")
    proposal = {
        "id": _uuid(),
        "reservation_id": reservation_id,
        "tenant_id": booking["tenant_id"],
        "agency_id": agency["agency_id"],
        "hotel_name": booking.get("hotel_name"),
        "confirmation_code": booking.get("confirmation_code"),
        "guest_name": booking.get("guest_name"),
        "type": "agency_modification",
        "reason": data.reason.strip(),
        "requested": data.model_dump(exclude={"reason"}),
        "current": {key: booking.get(key) for key in ("check_in", "check_out", "room_type", "total_amount")},
        "status": "awaiting_hotel",
        "expires_at": (datetime.now(UTC) + timedelta(hours=48)).isoformat(),
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }
    await sysdb.marketplace_negotiations.insert_one(proposal)
    with tenant_context(booking["tenant_id"]):
        await db.notifications.insert_one(
            {
                "id": _uuid(),
                "tenant_id": booking["tenant_id"],
                "type": "agency_negotiation",
                "title": "Acente değişiklik onayı bekliyor",
                "message": f"{booking.get('confirmation_code')} için tarih/oda tipi değişikliği talep edildi.",
                "read": False,
                "metadata": {"proposal_id": proposal["id"], "reservation_id": reservation_id},
                "created_at": _now_iso(),
            }
        )
    proposal.pop("_id", None)
    return {"ok": True, "proposal": proposal}


@router.post("/hotel/negotiations/{proposal_id}/decision")
async def hotel_decide_marketplace_modification(
    proposal_id: str,
    data: CancellationProposalDecision,
    current_user: User = Depends(get_current_user),
):
    tenant_id = _require_hotel_admin(current_user)
    sysdb = get_system_db()
    proposal = await sysdb.marketplace_negotiations.find_one(
        {
            "id": proposal_id,
            "tenant_id": tenant_id,
            "type": {"$in": ["agency_modification", "agency_cancellation"]},
            "status": "awaiting_hotel",
        },
        {"_id": 0},
    )
    if not proposal:
        raise HTTPException(404, "Yanıt bekleyen değişiklik talebi bulunamadı")
    if proposal.get("expires_at") and datetime.fromisoformat(proposal["expires_at"]) < datetime.now(UTC):
        await sysdb.marketplace_negotiations.update_one({"id": proposal_id}, {"$set": {"status": "expired"}})
        raise HTTPException(409, "Değişiklik teklifinin 48 saatlik süresi dolmuş")

    if data.accept and proposal["type"] == "agency_modification":
        requested = proposal["requested"]
        from routers.agency_contracts import has_active_contract

        last_night = _last_occupied_date(requested["check_in"], requested["check_out"])
        contract = await has_active_contract(
            proposal["agency_id"], tenant_id, on_date=requested["check_in"], through_date=last_night
        )
        if not contract:
            raise HTTPException(409, "Yeni tarihler aktif acente sözleşmesi kapsamında değil")
        listing = await _get_listing_or_404(tenant_id)
        allowed = contract.get("allowed_room_types") or listing.get("allowed_room_types") or []
        if allowed and requested["room_type"] not in allowed:
            raise HTTPException(409, "İstenen oda tipi acente satışına açık değil")
        with tenant_context(tenant_id):
            rooms = await db.rooms.find(
                {"tenant_id": tenant_id, "room_type": requested["room_type"], "is_active": {"$ne": False}}, {"_id": 0}
            ).to_list(500)
            booking = await db.bookings.find_one({"id": proposal["reservation_id"], "tenant_id": tenant_id}, {"_id": 0})
        if not booking or booking.get("status") != "confirmed":
            raise HTTPException(409, "Rezervasyon artık değiştirilebilir durumda değil")
        if not rooms:
            raise HTTPException(409, "İstenen oda tipinde aktif oda bulunamadı")
        pricing = await _marketplace_stay_price(
            tenant_id=tenant_id,
            agency_id=proposal["agency_id"],
            room_type=requested["room_type"],
            check_in=requested["check_in"],
            check_out=requested["check_out"],
            fallback_rate=float(rooms[0].get("base_price", 0) or 0),
        )
        if not pricing["sellable"]:
            raise HTTPException(409, "Yeni tarihler satışa kapalı")
        selected_room = None
        for room in rooms:
            try:
                await assign_room_atomic(
                    tenant_id=tenant_id,
                    booking_id=proposal["reservation_id"],
                    room_id=room["id"],
                    check_in=requested["check_in"] + "T14:00:00",
                    check_out=requested["check_out"] + "T11:00:00",
                )
                selected_room = room
                break
            except BookingConflictError:
                continue
        if not selected_room:
            raise HTTPException(409, "İstenen tarihlerde uygun fiziksel oda bulunamadı")
        total = float(pricing["total_price"])
        paid = float(booking.get("total_paid", 0) or 0)
        commission_pct = float(booking.get("agency_commission_rate", 0) or 0)
        fee_pct = float(booking.get("syroce_b2b_fee_pct", 0) or 0)
        if not fee_pct:
            fee_pct = float((await sysdb.marketplace_bookings.find_one(
                {"id": proposal["reservation_id"], "tenant_id": tenant_id},
                {"syroce_b2b_fee_pct": 1, "_id": 0},
            ) or {}).get("syroce_b2b_fee_pct", 0) or 0)
        financials = _marketplace_financials(total, commission_pct, fee_pct)
        changes = {
            "check_in": requested["check_in"] + "T14:00:00",
            "check_out": requested["check_out"] + "T11:00:00",
            "room_id": selected_room["id"],
            "room_number": selected_room.get("room_number", ""),
            "room_type": requested["room_type"],
            "nightly_rates": pricing["nightly_rates"],
            "total_amount": total,
            "balance": max(0, round(total - paid, 2)),
            "agency_commission_amount": financials["commission_amount"],
            "syroce_b2b_fee_pct": fee_pct,
            **financials,
            "updated_at": _now_iso(),
        }
        with tenant_context(tenant_id):
            await db.bookings.update_one({"id": proposal["reservation_id"], "tenant_id": tenant_id}, {"$set": changes})
        await sysdb.marketplace_bookings.update_one(
            {"id": proposal["reservation_id"], "tenant_id": tenant_id}, {"$set": changes}
        )
    elif data.accept:
        with tenant_context(tenant_id):
            booking = await db.bookings.find_one({"id": proposal["reservation_id"], "tenant_id": tenant_id})
            if not booking or booking.get("status") in {"checked_in", "checked_out", "cancelled"}:
                raise HTTPException(409, "Rezervasyon artık iptal edilebilir durumda değil")
            await db.bookings.update_one(
                {"id": proposal["reservation_id"], "tenant_id": tenant_id},
                {"$set": {"status": "cancelled", "cancellation_reason": proposal["reason"], "cancelled_by": "mutual_agreement", "cancelled_at": _now_iso(), "updated_at": _now_iso()}},
            )
            from core.atomic_booking import release_booking_nights

            await release_booking_nights(tenant_id, proposal["reservation_id"], reason="mutual_agreement")
        await sysdb.marketplace_bookings.update_one(
            {"id": proposal["reservation_id"], "tenant_id": tenant_id},
            {"$set": {"status": "cancelled", "cancelled_at": _now_iso(), "cancellation_reason": proposal["reason"]}},
        )

    status_value = "accepted" if data.accept else "declined"
    await sysdb.marketplace_negotiations.update_one(
        {"id": proposal_id, "status": "awaiting_hotel"},
        {"$set": {"status": status_value, "response_note": data.response_note.strip(), "responded_at": _now_iso(), "updated_at": _now_iso()}},
    )
    return {
        "ok": True,
        "status": status_value,
        "reservation_modified": bool(data.accept and proposal["type"] == "agency_modification"),
        "reservation_cancelled": bool(data.accept and proposal["type"] == "agency_cancellation"),
    }


@router.post("/hotel/reservations/{reservation_id}/cancellation-proposals")
async def hotel_propose_marketplace_cancellation(
    reservation_id: str,
    data: CancellationProposalCreate,
    current_user: User = Depends(get_current_user),
):
    """Hotel may propose, but never unilaterally execute, an agency cancellation."""
    tenant_id = _require_hotel_admin(current_user)
    sysdb = get_system_db()
    booking = await sysdb.marketplace_bookings.find_one(
        {"id": reservation_id, "tenant_id": tenant_id, "status": {"$ne": "cancelled"}}, {"_id": 0}
    )
    if not booking:
        raise HTTPException(404, "Aktif acente rezervasyonu bulunamadı")
    existing = await sysdb.marketplace_negotiations.find_one(
        {"reservation_id": reservation_id, "type": "hotel_cancellation", "status": "awaiting_agency"}, {"_id": 0}
    )
    if existing:
        raise HTTPException(409, "Bu rezervasyon için acente yanıtı bekleyen bir teklif zaten var")
    proposal = {
        "id": _uuid(), "reservation_id": reservation_id, "tenant_id": tenant_id,
        "agency_id": booking["agency_id"], "hotel_name": booking.get("hotel_name"),
        "confirmation_code": booking.get("confirmation_code"), "guest_name": booking.get("guest_name"),
        "type": "hotel_cancellation", "reason": data.reason.strip(), "status": "awaiting_agency",
        "created_by": current_user.id, "created_at": _now_iso(), "updated_at": _now_iso(),
    }
    await sysdb.marketplace_negotiations.insert_one(proposal)
    with tenant_context(tenant_id):
        await db.notifications.insert_one({
            "id": _uuid(), "tenant_id": tenant_id, "type": "agency_negotiation", "title": "Acente yanıtı bekleniyor",
            "message": f"{booking.get('confirmation_code')} için iptal önerisi acenteye iletildi.", "read": False,
            "metadata": {"proposal_id": proposal["id"], "reservation_id": reservation_id}, "created_at": _now_iso(),
        })
    return {"ok": True, "proposal": {k: v for k, v in proposal.items() if k != "_id"}}


@router.get("/hotel/negotiations")
async def hotel_list_marketplace_negotiations(current_user: User = Depends(get_current_user)):
    tenant_id = _require_hotel_admin(current_user)
    docs = await get_system_db().marketplace_negotiations.find(
        {"tenant_id": tenant_id}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    return {"items": docs}


@router.get("/negotiations")
async def agency_list_negotiations(agency: dict = Depends(get_marketplace_agency)):
    docs = await get_system_db().marketplace_negotiations.find(
        {"agency_id": agency["agency_id"]}, {"_id": 0}
    ).sort("created_at", -1).to_list(500)
    return {"items": docs}


@router.post("/negotiations/{proposal_id}/decision")
async def agency_decide_negotiation(
    proposal_id: str,
    data: CancellationProposalDecision,
    agency: dict = Depends(get_marketplace_agency),
):
    sysdb = get_system_db()
    proposal = await sysdb.marketplace_negotiations.find_one(
        {"id": proposal_id, "agency_id": agency["agency_id"], "status": "awaiting_agency"}, {"_id": 0}
    )
    if not proposal:
        raise HTTPException(404, "Yanıt bekleyen teklif bulunamadı")
    status_value = "accepted" if data.accept else "declined"
    if data.accept:
        with tenant_context(proposal["tenant_id"]):
            booking = await db.bookings.find_one({"id": proposal["reservation_id"], "tenant_id": proposal["tenant_id"]})
            if not booking or booking.get("status") in {"checked_in", "checked_out", "cancelled"}:
                raise HTTPException(409, "Rezervasyon artık iptal edilebilir durumda değil")
            await db.bookings.update_one(
                {"id": proposal["reservation_id"], "tenant_id": proposal["tenant_id"]},
                {"$set": {"status": "cancelled", "cancellation_reason": proposal["reason"], "cancelled_by": "mutual_agreement", "cancelled_at": _now_iso(), "updated_at": _now_iso()}},
            )
            from core.atomic_booking import release_booking_nights
            await release_booking_nights(proposal["tenant_id"], proposal["reservation_id"], reason="mutual_agreement")
        await sysdb.marketplace_bookings.update_one(
            {"id": proposal["reservation_id"], "agency_id": agency["agency_id"]},
            {"$set": {"status": "cancelled", "cancelled_at": _now_iso(), "cancellation_reason": proposal["reason"]}},
        )
    await sysdb.marketplace_negotiations.update_one(
        {"id": proposal_id, "status": "awaiting_agency"},
        {"$set": {"status": status_value, "response_note": data.response_note.strip(), "responded_at": _now_iso(), "updated_at": _now_iso()}},
    )
    return {"ok": True, "status": status_value, "reservation_cancelled": bool(data.accept)}


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
    totals = {"gross_revenue": 0.0, "commission": 0.0, "platform_fee": 0.0, "net_to_hotels": 0.0, "bookings": 0, "cancelled": 0}
    for d in docs:
        if d.get("status") == "cancelled":
            totals["cancelled"] += 1
            continue
        tid = d["tenant_id"]
        bucket = by_hotel.setdefault(
            tid,
            {
                "tenant_id": tid,
                "hotel_name": d.get("hotel_name"),
                "bookings": 0,
                "gross_revenue": 0.0,
                "commission": 0.0,
                "platform_fee": 0.0,
                "net_to_hotel": 0.0,
            },
        )
        gross = float(d.get("total_amount", 0))
        comm = float(d.get("commission_amount", 0))
        platform_fee = float(d.get("syroce_b2b_fee_amount", 0))
        net = float(d.get("net_to_hotel", gross - comm))
        bucket["bookings"] += 1
        bucket["gross_revenue"] += gross
        bucket["commission"] += comm
        bucket["platform_fee"] += platform_fee
        bucket["net_to_hotel"] += net
        totals["bookings"] += 1
        totals["gross_revenue"] += gross
        totals["commission"] += comm
        totals["platform_fee"] += platform_fee
        totals["net_to_hotels"] += net

    return {
        "period_start": period_start,
        "period_end": period_end,
        "agency_id": agency["agency_id"],
        "totals": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in totals.items()},
        "by_hotel": [{**v, "gross_revenue": round(v["gross_revenue"], 2), "commission": round(v["commission"], 2), "platform_fee": round(v["platform_fee"], 2), "net_to_hotel": round(v["net_to_hotel"], 2)} for v in by_hotel.values()],
    }


@router.get("/reconciliation/agency.csv")
async def agency_reconciliation_csv(
    period_start: str = Query(..., description="YYYY-MM-DD"),
    period_end: str = Query(..., description="YYYY-MM-DD"),
    agency: dict = Depends(get_marketplace_agency),
):
    """Download an agency-owned, spreadsheet-safe reconciliation detail."""
    docs = await get_system_db().marketplace_bookings.find(
        {
            "agency_id": agency["agency_id"],
            "check_in": {"$gte": period_start, "$lte": period_end},
        },
        {"_id": 0},
    ).sort("check_in", 1).to_list(5000)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Onay Kodu", "Otel", "Misafir", "Giriş", "Çıkış", "Durum", "Para Birimi", "Brüt", "Komisyon", "Platform Bedeli", "Otele Net"])
    for item in docs:
        # A leading apostrophe prevents spreadsheet formula execution while
        # preserving user-entered references as visible text.
        safe_code = "'" + str(item.get("confirmation_code") or item.get("id") or "").replace("\n", " ").replace("\r", " ")
        writer.writerow(
            [
                safe_code,
                item.get("hotel_name", ""),
                item.get("guest_name", ""),
                str(item.get("check_in", ""))[:10],
                str(item.get("check_out", ""))[:10],
                item.get("status", ""),
                item.get("currency", "TRY"),
                round(float(item.get("total_amount", 0) or 0), 2),
                round(float(item.get("commission_amount", 0) or 0), 2),
                round(float(item.get("syroce_b2b_fee_amount", 0) or 0), 2),
                round(float(item.get("net_to_hotel", 0) or 0), 2),
            ]
        )
    filename = f"acente-mutabakat-{period_start}-{period_end}.csv"
    return Response(
        "\ufeff" + output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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
    totals = {"gross_revenue": 0.0, "commission": 0.0, "platform_fee": 0.0, "net_to_hotel": 0.0, "bookings": 0, "cancelled": 0}
    for d in docs:
        if d.get("status") == "cancelled":
            totals["cancelled"] += 1
            continue
        aid = d["agency_id"]
        bucket = by_agency.setdefault(
            aid,
            {
                "agency_id": aid,
                "bookings": 0,
                "gross_revenue": 0.0,
                "commission_owed": 0.0,
                "platform_fee": 0.0,
                "net_received": 0.0,
            },
        )
        gross = float(d.get("total_amount", 0))
        comm = float(d.get("commission_amount", 0))
        platform_fee = float(d.get("syroce_b2b_fee_amount", 0))
        net = float(d.get("net_to_hotel", gross - comm))
        bucket["bookings"] += 1
        bucket["gross_revenue"] += gross
        bucket["commission_owed"] += comm
        bucket["platform_fee"] += platform_fee
        bucket["net_received"] += net
        totals["bookings"] += 1
        totals["gross_revenue"] += gross
        totals["commission"] += comm
        totals["platform_fee"] += platform_fee
        totals["net_to_hotel"] += net

    return {
        "period_start": period_start,
        "period_end": period_end,
        "tenant_id": tenant_id,
        "totals": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in totals.items()},
        "by_agency": [{**v, "gross_revenue": round(v["gross_revenue"], 2), "commission_owed": round(v["commission_owed"], 2), "platform_fee": round(v["platform_fee"], 2), "net_received": round(v["net_received"], 2)} for v in by_agency.values()],
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
