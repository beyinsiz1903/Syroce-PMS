"""Tenant-facing Onboarding Wizard endpoints.

The cross-tenant admin overview lives under
`/api/admin/tenants/{tenant_id}/onboarding`. This router exposes the
SAME progress engine but scoped to the caller's own tenant — for the
in-app wizard a hotelier sees on first login.
"""

from __future__ import annotations

import logging
import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, field_validator

from cache_manager import cache as cache_manager
from cache_manager import cached
from core.onboarding import (
    DEFAULT_STEPS,
    get_onboarding_progress,
    mark_step_complete,
)
from core.security import _is_super_admin, get_current_user
from models.schemas import User

# Steps the wizard is allowed to mark complete by hand. Auto-detected
# steps (rooms_configured, rates_configured, ...) MUST come from the
# real underlying signals — never trust a client to claim them.
MANUAL_STEPS_ALLOWLIST = {"hotel_info_completed"}

# Roles allowed to mutate tenant onboarding state.
ADMIN_ROLES = {"super_admin", "platform_admin", "admin", "owner"}

# P1 #8 telefon validation — E.164 (uluslararası) + Türkiye yerel formatı.
_PHONE_RE = re.compile(r"^\+?[0-9 ()\-]{7,20}$")
_TR_PHONE_NORMALIZE = re.compile(r"[^0-9+]")
_TAX_NUMBER_RE = re.compile(r"^(?:\d{10}|\d{11})$")
_MERSIS_RE = re.compile(r"^\d{16}$")

_PROPERTY_TYPE_ALIASES = {
    "hotel": "city_hotel",
    "boutique": "boutique_hotel",
    "butik": "boutique_hotel",
    "apart": "apart_hotel",
    "resort": "resort_summer",
    "pansiyon": "pension",
}
_PROPERTY_TYPES = {
    "pension", "villa", "hostel", "motel", "apart_hotel",
    "boutique_hotel", "camping", "city_hotel", "business_hotel",
    "resort_summer", "resort_winter", "resort_thermal",
    "hotel_3star", "hotel_4star", "hotel_5star",
}
_CURRENCY_SYMBOLS = {"TRY": "₺", "USD": "$", "EUR": "€", "GBP": "£", "RUB": "₽", "JPY": "¥"}

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


def _db():
    from core.database import _raw_db

    return _raw_db


def _require_tenant(user: User) -> str:
    if not user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")
    return user.tenant_id


def _require_tenant_dep(current_user: User = Depends(get_current_user)) -> None:
    if not current_user.tenant_id:
        raise HTTPException(status_code=403, detail="Tenant gerekli")


def _user_is_admin(user: User) -> bool:
    if _is_super_admin(user):
        return True
    role = (user.role or "").lower()
    if role in ADMIN_ROLES:
        return True
    extra_roles = getattr(user, "roles", None) or []
    if isinstance(extra_roles, list) and any(((r or "").lower() in ADMIN_ROLES) for r in extra_roles):
        return True
    return False


def _require_tenant_admin(user: User) -> str:
    """Require both a tenant context AND an admin-grade role."""
    tenant_id = _require_tenant(user)
    if not _user_is_admin(user):
        raise HTTPException(
            status_code=403,
            detail="Bu işlem için yönetici yetkisi gerekli",
        )
    return tenant_id


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _invalidate_progress_cache(tenant_id: str) -> None:
    """P0 #2: cache stale fix. mark_step_complete / update_hotel_info sonrası
    onboarding_progress prefix'li tüm cache key'leri Redis'ten siler."""
    try:
        cache_manager.invalidate_tenant_cache(tenant_id, entity_type="onboarding_progress")
    except Exception as e:
        logger.warning("onboarding cache invalidation failed for %s: %s", tenant_id, e)


# ── Read progress ───────────────────────────────────────────────
# Cache yalnız tenant-bazlı veriyi (steps/dismissed) tutar; kullanıcıya
# özel `is_tenant_admin` cache'in DIŞINDA, isteğe özel hesaplanır
# (architect feedback: aksi halde aynı tenant içinde non-admin admin'in
# cache'lenmiş `true` değerini alabilir).
@cached(ttl=60, key_prefix="onboarding_progress")
async def _cached_progress(tenant_id: str) -> dict:
    """rbac-allow: cache-rbac — tenant-scoped, kullanıcı-bağımsız payload."""
    data = await get_onboarding_progress(tenant_id)
    db = _db()
    doc = await db.onboarding_progress.find_one({"tenant_id": tenant_id}, {"_id": 0, "dismissed": 1, "dismissed_at": 1}) or {}
    data["dismissed"] = bool(doc.get("dismissed"))
    data["dismissed_at"] = doc.get("dismissed_at")
    return data


@router.get("/progress")
async def progress(
    current_user: User = Depends(get_current_user),
    _tenant_dep: None = Depends(_require_tenant_dep),
) -> dict:
    tenant_id = _require_tenant(current_user)
    data = dict(await _cached_progress(tenant_id))  # copy → user flag eklerken cache mutasyonu yok
    # Kullanıcıya özel — cache DIŞINDA, request başına yeniden hesapla.
    data["is_tenant_admin"] = _user_is_admin(current_user)
    return data


# ── Manual step completion ──────────────────────────────────────
class StepIn(BaseModel):
    step_id: str


@router.post("/complete-step")
async def complete_step(
    payload: StepIn,
    current_user: User = Depends(get_current_user),
) -> dict:
    tenant_id = _require_tenant_admin(current_user)
    if payload.step_id not in MANUAL_STEPS_ALLOWLIST:
        valid_keys = {s["step_id"] for s in DEFAULT_STEPS}
        if payload.step_id not in valid_keys:
            raise HTTPException(status_code=400, detail="Geçersiz adım kimliği")
        raise HTTPException(
            status_code=400,
            detail="Bu adım otomatik algılanır; manuel işaretleme kabul edilmiyor",
        )
    await mark_step_complete(tenant_id, payload.step_id)
    _invalidate_progress_cache(tenant_id)  # P0 #2
    return await get_onboarding_progress(tenant_id)


# ── Dismiss / undismiss the wizard auto-popup ───────────────────
@router.post("/dismiss")
async def dismiss(current_user: User = Depends(get_current_user)) -> dict:
    tenant_id = _require_tenant_admin(current_user)
    await _db().onboarding_progress.update_one(
        {"tenant_id": tenant_id},
        {
            "$set": {"dismissed": True, "dismissed_at": _now_iso()},
            "$setOnInsert": {"tenant_id": tenant_id, "created_at": _now_iso()},
        },
        upsert=True,
    )
    _invalidate_progress_cache(tenant_id)
    return {"ok": True, "dismissed": True}


@router.post("/resume")
async def resume(current_user: User = Depends(get_current_user)) -> dict:
    tenant_id = _require_tenant_admin(current_user)
    await _db().onboarding_progress.update_one(
        {"tenant_id": tenant_id},
        {"$set": {"dismissed": False, "updated_at": _now_iso()}},
    )
    _invalidate_progress_cache(tenant_id)
    return {"ok": True, "dismissed": False}


# ── Step 1: Hotel info update ───────────────────────────────────
class HotelInfoIn(BaseModel):
    """P1 #6/#7/#8 genişletilmiş kurulum modeli.

    Yeni alanlar: property_type, currency, timezone, default_language,
    star_rating, opening_year, tax_number, mersis_no, vat_rate,
    accommodation_tax_exempt + yapılandırılmış adres (city, district,
    neighborhood, street, building_no, postal_code).
    """

    property_name: str | None = Field(default=None, max_length=200)
    property_type: str | None = Field(default=None, max_length=50)  # P0 #6
    star_rating: int | None = Field(default=None, ge=1, le=5)
    opening_year: int | None = Field(default=None, ge=1900, le=2100)

    contact_phone: str | None = Field(default=None, max_length=50)
    contact_email: EmailStr | None = None

    address: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    district: str | None = Field(default=None, max_length=100)
    neighborhood: str | None = Field(default=None, max_length=200)
    street: str | None = Field(default=None, max_length=200)
    building_no: str | None = Field(default=None, max_length=50)
    postal_code: str | None = Field(default=None, max_length=20)

    total_rooms: int | None = Field(default=None, ge=1, le=10000)

    # Yerel/finansal varsayılanlar
    currency: str | None = Field(default=None, max_length=10)  # TRY/USD/EUR/RUB
    timezone: str | None = Field(default=None, max_length=64)  # Europe/Istanbul
    default_language: str | None = Field(default=None, max_length=8)  # tr/en/ru/de

    # Türkiye'ye özel
    tax_number: str | None = Field(default=None, max_length=20)  # VKN/TCKN
    tax_office: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default="TR", min_length=2, max_length=2)
    mersis_no: str | None = Field(default=None, max_length=20)
    vat_rate: float | None = Field(default=None, ge=0, le=100)
    accommodation_tax_exempt: bool | None = None

    @field_validator("contact_phone")
    @classmethod
    def _ph(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            return None
        if not _PHONE_RE.match(v):
            raise ValueError("Telefon formatı geçersiz (örn. +905551234567)")
        digits = _TR_PHONE_NORMALIZE.sub("", v)
        # En az 10 rakam (Türk yerel) — daha sıkı kontrol için E.164 kütüphanesi
        # eklenebilir; buradaki minimum makul filtre.
        if len(digits.replace("+", "")) < 10:
            raise ValueError("Telefon en az 10 hane içermeli")
        return v

    @field_validator("currency")
    @classmethod
    def _cur(cls, v):
        if v is None:
            return v
        v = v.strip().upper()
        if v not in {"TRY", "USD", "EUR", "GBP", "RUB", "JPY"}:
            raise ValueError("Para birimi TRY/USD/EUR/GBP/RUB/JPY olmalı")
        return v

    @field_validator("timezone")
    @classmethod
    def _tz(cls, v):
        if v is None:
            return v
        value = v.strip()
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError("Geçersiz IANA zaman dilimi") from exc
        return value

    @field_validator("tax_number")
    @classmethod
    def _tax_number(cls, v):
        if v is None or not v.strip():
            return None
        value = v.strip()
        if not _TAX_NUMBER_RE.fullmatch(value):
            raise ValueError("VKN 10, TCKN 11 haneli olmalıdır")
        return value

    @field_validator("mersis_no")
    @classmethod
    def _mersis(cls, v):
        if v is None or not v.strip():
            return None
        value = v.strip()
        if not _MERSIS_RE.fullmatch(value):
            raise ValueError("MERSİS numarası 16 haneli olmalıdır")
        return value

    @field_validator("country")
    @classmethod
    def _country(cls, v):
        return v.strip().upper() if v else v

    @field_validator("default_language")
    @classmethod
    def _lang(cls, v):
        if v is None:
            return v
        v = v.strip().lower()
        if v not in {"tr", "en", "ru", "de", "ar", "fr"}:
            raise ValueError("Dil kodu geçersiz")
        return v

    @field_validator("property_type")
    @classmethod
    def _pt(cls, v):
        if v is None:
            return v
        v = _PROPERTY_TYPE_ALIASES.get(v.strip().lower(), v.strip().lower())
        if v not in _PROPERTY_TYPES:
            raise ValueError("Mülk tipi geçersiz")
        return v


def _compose_address(doc: dict) -> str:
    """Create the canonical printable/legal address from structured fields."""
    street_line = " ".join(
        part for part in [doc.get("street"), doc.get("building_no")] if str(part or "").strip()
    ).strip()
    locality = " / ".join(
        part for part in [doc.get("neighborhood"), doc.get("district"), doc.get("city")] if str(part or "").strip()
    )
    pieces = [part for part in [street_line, locality, doc.get("postal_code")] if str(part or "").strip()]
    return ", ".join(str(part).strip() for part in pieces)


async def _sync_hotel_info_dependencies(tenant_id: str, tenant: dict, supplied_fields: set[str]) -> list[str]:
    """Keep canonical settings stores aligned with the onboarding profile."""
    db = _db()
    synced: list[str] = []

    structured_address_fields = {"city", "district", "neighborhood", "street", "building_no", "postal_code"}
    composed_address = _compose_address(tenant)
    address = (
        composed_address
        if supplied_fields & structured_address_fields and composed_address
        else (tenant.get("address") or "").strip() or composed_address
    )
    tenant_aliases: dict = {}
    if address and address != tenant.get("address"):
        tenant_aliases["address"] = address
    if tenant.get("tax_number"):
        tenant_aliases["tax_no"] = tenant["tax_number"]
    if tenant_aliases:
        await db.tenants.update_one({"id": tenant_id}, {"$set": tenant_aliases})

    hotel_settings = {
        "tenant_id": tenant_id,
        "hotel_name": tenant.get("property_name") or "",
        "hotel_address": address,
        "hotel_phone": tenant.get("contact_phone") or "",
        "hotel_email": str(tenant.get("contact_email") or ""),
        "tax_id": tenant.get("tax_number") or "",
        "tax_office": tenant.get("tax_office") or "",
        "currency": tenant.get("currency") or "TRY",
        "currency_symbol": _CURRENCY_SYMBOLS.get(tenant.get("currency") or "TRY", tenant.get("currency") or "TRY"),
        "default_accommodation_vat_rate": float(tenant.get("vat_rate", 10.0)),
        "updated_at": _now_iso(),
    }
    await db.hotel_settings.update_one({"tenant_id": tenant_id}, {"$set": hotel_settings}, upsert=True)
    synced.append("hotel_settings")

    tenant_settings = {
        "tenant_id": tenant_id,
        "timezone": tenant.get("timezone") or "Europe/Istanbul",
        "default_language": tenant.get("default_language") or "tr",
        "updated_at": _now_iso(),
    }
    await db.tenant_settings.update_one({"tenant_id": tenant_id}, {"$set": tenant_settings}, upsert=True)
    synced.append("tenant_settings")

    if "accommodation_tax_exempt" in supplied_fields:
        await db.city_tax_rules.update_one(
            {"tenant_id": tenant_id},
            {
                "$set": {
                    "tenant_id": tenant_id,
                    "active": not bool(tenant.get("accommodation_tax_exempt")),
                    "updated_at": _now_iso(),
                },
                "$setOnInsert": {"rate_percent": 2.0, "auto_post": False, "exempt_segments": []},
            },
            upsert=True,
        )
        synced.append("accommodation_tax")

    # Prefill the fiscal seller profile only when every mandatory Nilvera
    # identity field is known. API credentials and enablement remain an
    # explicit integration step.
    seller = {
        "vkn": tenant.get("tax_number"),
        "name": tenant.get("property_name"),
        "tax_office": tenant.get("tax_office"),
        "address": address,
        "city": tenant.get("city"),
        "country": tenant.get("country") or "TR",
    }
    if all(str(value or "").strip() for value in seller.values()):
        await db.tenant_settings.update_one(
            {"tenant_id": tenant_id},
            {"$set": {"nilvera.seller": seller}},
            upsert=True,
        )
        synced.append("nilvera_seller")

    try:
        from core.tenant_currency import invalidate_tenant_currency

        invalidate_tenant_currency(tenant_id)
    except Exception:
        logger.warning("tenant currency cache invalidation failed tenant=%s", tenant_id)
    return synced


@router.patch("/hotel-info")
async def update_hotel_info(
    payload: HotelInfoIn,
    current_user: User = Depends(get_current_user),
) -> dict:
    tenant_id = _require_tenant_admin(current_user)
    update: dict = {}
    for k, v in payload.model_dump(exclude_unset=True).items():
        if v is None:
            continue
        if isinstance(v, str) and not v.strip():
            continue
        update[k] = v.strip() if isinstance(v, str) else v

    if not update:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok")

    update["updated_at"] = _now_iso()
    res = await _db().tenants.update_one({"id": tenant_id}, {"$set": update})
    if res.matched_count == 0:
        raise HTTPException(status_code=404, detail="Tenant bulunamadı")

    # Step ✓ artık SADECE auto-detect predicate (property_name +
    # contact_phone + total_rooms hepsi dolu) sağlanırsa işaretlenir
    # — yoksa kullanıcı eksik kayıtla "tamam" görünmesin (architect feedback).
    fresh = (
        await _db().tenants.find_one(
            {"id": tenant_id},
            {"_id": 0, "property_name": 1, "contact_phone": 1, "total_rooms": 1},
        )
        or {}
    )
    if (fresh.get("property_name") or "").strip() and (fresh.get("contact_phone") or "").strip() and int(fresh.get("total_rooms") or 0) > 0:
        await mark_step_complete(tenant_id, "hotel_info_completed")
    _invalidate_progress_cache(tenant_id)  # P0 #2

    tenant = await _db().tenants.find_one(
        {"id": tenant_id},
        {
            "_id": 0,
            "id": 1,
            "property_name": 1,
            "property_type": 1,
            "contact_phone": 1,
            "contact_email": 1,
            "address": 1,
            "location": 1,
            "city": 1,
            "district": 1,
            "neighborhood": 1,
            "street": 1,
            "building_no": 1,
            "postal_code": 1,
            "total_rooms": 1,
            "currency": 1,
            "timezone": 1,
            "default_language": 1,
            "star_rating": 1,
            "opening_year": 1,
            "tax_number": 1,
            "tax_office": 1,
            "country": 1,
            "mersis_no": 1,
            "vat_rate": 1,
            "accommodation_tax_exempt": 1,
        },
    )
    synced = await _sync_hotel_info_dependencies(tenant_id, tenant or {}, set(update) - {"updated_at"})
    if tenant is not None and not tenant.get("address"):
        tenant["address"] = _compose_address(tenant)
    return {"ok": True, "tenant": tenant, "updated_fields": list(update.keys()), "synced_targets": synced}
