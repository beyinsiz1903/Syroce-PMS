"""Regulatory reports — Turkish Ministry & TÜİK self-service exports.

Provides:
  GET /api/regulatory/tuik/monthly?year=&month=
      → TÜİK Aylık Konaklama İstatistikleri (room nights, occupancy,
        nationality breakdown, ALOS).
  GET /api/regulatory/inspection-readiness
      → Bakanlık denetim hazırlık dashboard (oda/çalışan/sertifika
        özet + 12 aylık doluluk).
  GET /api/regulatory/star-classification/checklist
      → Yıldız sınıflama self-check kriter listesi + tesisin durumu.
  POST /api/regulatory/star-classification/checklist
      → kullanıcının "var/yok/kısmen" işaretlerini kaydeder.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from cache_manager import cache as _cache
from cache_manager import cached
from core.database import db
from core.helpers import create_audit_log
from core.security import get_current_user
from core.tga_outbound import (
    build_batch_envelope,
    build_daily_payload,
    get_tga_config,
    list_send_log,
    send_batch,
    set_tga_config,
)
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v98 DW

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/regulatory", tags=["regulatory"])


# ─────────────────────────────────────────────────────────────────────
# TÜİK Monthly
# ─────────────────────────────────────────────────────────────────────

def _period_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    if month < 1 or month > 12:
        raise HTTPException(400, "month must be 1-12")
    start = datetime(year, month, 1, tzinfo=UTC)
    end = (datetime(year + 1, 1, 1, tzinfo=UTC) if month == 12
           else datetime(year, month + 1, 1, tzinfo=UTC))
    return start, end


def _days_in_month(year: int, month: int) -> int:
    s, e = _period_bounds(year, month)
    return (e - s).days


# Common TR locale country normalization.
_TR_COUNTRY_ALIASES = {
    "TR": "Türkiye", "TURKEY": "Türkiye", "TÜRKİYE": "Türkiye",
    "TURKİYE": "Türkiye", "TÜRKIYE": "Türkiye",
    "DE": "Almanya", "GERMANY": "Almanya",
    "GB": "Birleşik Krallık", "UK": "Birleşik Krallık",
    "RU": "Rusya", "RUSSIA": "Rusya",
    "US": "ABD", "USA": "ABD",
    "FR": "Fransa", "NL": "Hollanda", "IT": "İtalya",
    "BE": "Belçika", "AT": "Avusturya", "CH": "İsviçre",
    "PL": "Polonya", "UA": "Ukrayna",
}


def _normalize_country(raw: str | None) -> str:
    if not raw:
        return "Belirtilmemiş"
    key = raw.strip().upper()
    return _TR_COUNTRY_ALIASES.get(key, raw.strip().title())


@router.get("/tuik/monthly")
async def tuik_monthly(
    year: int, month: int,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_regulatory_reports")),
) -> dict[str, Any]:
    start, end = _period_bounds(year, month)
    days = _days_in_month(year, month)

    # Capacity: count active rooms for the tenant.
    total_rooms = await db.rooms.count_documents(
        {"tenant_id": current_user.tenant_id,
         "status": {"$ne": "out_of_service"}})
    if total_rooms == 0:
        # Fallback: all rooms regardless of status.
        total_rooms = await db.rooms.count_documents(
            {"tenant_id": current_user.tenant_id})
    bed_pipeline = [
        {"$match": {"tenant_id": current_user.tenant_id}},
        {"$group": {"_id": None,
                    "beds": {"$sum": {"$ifNull": ["$bed_capacity", 2]}}}},
    ]
    bed_doc = await db.rooms.aggregate(bed_pipeline).to_list(length=1)
    total_beds = (bed_doc[0]["beds"] if bed_doc else total_rooms * 2)

    # Stays: bookings that overlap the period.
    bookings = await db.bookings.find(
        {"tenant_id": current_user.tenant_id,
         "status": {"$nin": ["cancelled", "no_show"]},
         "check_in": {"$lt": end.isoformat()},
         "check_out": {"$gt": start.isoformat()}},
        {"_id": 0, "id": 1, "booking_id": 1, "confirmation_number": 1,
         "check_in": 1, "check_out": 1, "adults": 1, "children": 1,
         "nationality": 1, "guest_country": 1, "country": 1,
         "guest_name": 1, "primary_guest_name": 1}).to_list(length=20000)

    nights_total = 0
    nights_by_country: dict[str, int] = {}
    guest_total = 0
    domestic_nights = 0
    foreign_nights = 0
    unspecified_nights = 0
    missing_nationality_bookings: list[dict[str, Any]] = []
    missing_nationality_total = 0
    adults_fallback_count = 0
    for bk in bookings:
        try:
            ci = datetime.fromisoformat(str(bk["check_in"]).replace("Z", "+00:00"))
            co = datetime.fromisoformat(str(bk["check_out"]).replace("Z", "+00:00"))
            if ci.tzinfo is None:
                ci = ci.replace(tzinfo=UTC)
            if co.tzinfo is None:
                co = co.replace(tzinfo=UTC)
        except Exception:
            continue
        # Clip to period.
        ci_eff = max(ci, start)
        co_eff = min(co, end)
        nights = max(0, (co_eff - ci_eff).days)
        if nights == 0:
            continue
        if bk.get("adults") in (None, 0):
            adults_fallback_count += 1
        guests = int(bk.get("adults") or 1) + int(bk.get("children") or 0)
        raw_country = bk.get("nationality") or bk.get("guest_country") or bk.get("country")
        country = _normalize_country(raw_country)
        person_nights = nights * guests
        nights_total += nights
        guest_total += guests
        nights_by_country[country] = nights_by_country.get(country, 0) + person_nights
        if country == "Türkiye":
            domestic_nights += person_nights
        elif country == "Belirtilmemiş":
            unspecified_nights += person_nights
            missing_nationality_total += 1
            if len(missing_nationality_bookings) < 50:
                missing_nationality_bookings.append({
                    "id": bk.get("id") or bk.get("booking_id"),
                    "confirmation_number": bk.get("confirmation_number"),
                    "guest_name": bk.get("primary_guest_name") or bk.get("guest_name"),
                    "check_in": str(bk.get("check_in") or "")[:10],
                    "check_out": str(bk.get("check_out") or "")[:10],
                })
        else:
            foreign_nights += person_nights

    if adults_fallback_count:
        logger.warning(
            "tuik_monthly tenant=%s period=%s-%02d: %d bookings missing 'adults' (defaulted to 1)",
            current_user.tenant_id, year, month, adults_fallback_count)

    capacity_room_nights = total_rooms * days
    occupancy_pct = (round(nights_total / capacity_room_nights * 100, 2)
                     if capacity_room_nights > 0 else 0.0)
    alos = (round(nights_total / guest_total, 2)
            if guest_total > 0 else 0.0)

    # Top 20 countries.
    top = sorted(nights_by_country.items(), key=lambda x: -x[1])[:20]
    other = sum(v for k, v in nights_by_country.items()
                if k not in {kk for kk, _ in top})

    return {
        "period": f"{year}-{month:02d}",
        "days_in_month": days,
        "capacity": {
            "rooms": total_rooms,
            "beds": total_beds,
            "room_nights_capacity": capacity_room_nights,
        },
        "stays": {
            "booking_count": len(bookings),
            "guest_count": guest_total,
            "room_nights_sold": nights_total,
            "person_nights_domestic": domestic_nights,
            "person_nights_foreign": foreign_nights,
            "person_nights_unspecified": unspecified_nights,
            "person_nights_total": (
                domestic_nights + foreign_nights + unspecified_nights),
        },
        "occupancy_pct": occupancy_pct,
        "average_length_of_stay": alos,
        "nationality_top20": [{"country": k, "person_nights": v}
                              for k, v in top],
        "nationality_other_total": other,
        "missing_nationality": {
            "booking_count": missing_nationality_total,
            "samples": missing_nationality_bookings,
        },
        "data_quality": {
            "adults_defaulted_count": adults_fallback_count,
        },
        "tuik_form_reference": "Aylık Konaklama İstatistikleri Anketi",
    }


# ─────────────────────────────────────────────────────────────────────
# Inspection readiness
# ─────────────────────────────────────────────────────────────────────

@router.get("/inspection-readiness")
@cached(ttl=300, key_prefix="regulatory_inspection_readiness")
async def inspection_readiness(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_regulatory_reports")),
    _nocache: bool = Query(False, alias="nocache"),
) -> dict[str, Any]:
    tenant = await db.tenants.find_one(
        {"id": current_user.tenant_id},
        {"_id": 0, "hotel_name": 1, "hotel_id": 1, "tax_no": 1,
         "star_rating": 1, "address": 1, "phone": 1,
         "license_number": 1, "license_expires_at": 1}) or {}

    total_rooms = await db.rooms.count_documents(
        {"tenant_id": current_user.tenant_id})
    total_users = await db.users.count_documents(
        {"tenant_id": current_user.tenant_id, "active": {"$ne": False}})
    rooms_missing_bed_capacity = await db.rooms.count_documents(
        {"tenant_id": current_user.tenant_id,
         "$or": [{"bed_capacity": {"$exists": False}}, {"bed_capacity": None}]})

    # 12 aylık doluluk trend — paralel sorgular (asyncio.gather).
    import asyncio as _asyncio
    now = datetime.now(UTC)
    spec: list[tuple[int, int, datetime, datetime, int]] = []
    for i in range(11, -1, -1):
        y = now.year + ((now.month - 1 - i) // 12)
        m = ((now.month - 1 - i) % 12) + 1
        s, e = _period_bounds(y, m)
        cap = total_rooms * (e - s).days
        spec.append((y, m, s, e, cap))
    counts = await _asyncio.gather(*[
        db.bookings.count_documents({
            "tenant_id": current_user.tenant_id,
            "status": {"$nin": ["cancelled", "no_show"]},
            "check_in": {"$lt": e.isoformat()},
            "check_out": {"$gt": s.isoformat()},
        }) for (_, _, s, e, _) in spec
    ])
    months: list[dict[str, Any]] = [
        {"period": f"{y}-{m:02d}", "booking_count": bks,
         "capacity_room_nights": cap,
         "occupancy_pct": (round(bks * 100 / cap, 1) if cap else 0.0)}
        for (y, m, _, _, cap), bks in zip(spec, counts, strict=True)
    ]

    # Sertifika & belge kontrolleri
    license_expiry_iso = tenant.get("license_expires_at")
    license_days_left: int | None = None
    if license_expiry_iso:
        try:
            le = datetime.fromisoformat(license_expiry_iso.replace("Z", "+00:00"))
            license_days_left = (le - now).days
        except Exception:
            license_days_left = None

    # Tenant künyesi eksik alan listesi (FE'de tek-tek gösterilir + admin
    # tenant edit deep link aksiyonu ile birlikte).
    tenant_missing: list[dict[str, str]] = []
    if not tenant.get("hotel_name"):
        tenant_missing.append({"field": "hotel_name", "label": "Tesis adı"})
    if not tenant.get("address"):
        tenant_missing.append({"field": "address", "label": "Tesis adresi"})
    if not tenant.get("phone"):
        tenant_missing.append({"field": "phone", "label": "Tesis telefonu"})
    if not tenant.get("tax_no"):
        tenant_missing.append({"field": "tax_no", "label": "Vergi numarası"})
    if not tenant.get("license_number"):
        tenant_missing.append({"field": "license_number",
                               "label": "İşletme belgesi numarası"})
    if not tenant.get("license_expires_at"):
        tenant_missing.append({"field": "license_expires_at",
                               "label": "İşletme belgesi son geçerlilik tarihi"})
    if not tenant.get("star_rating"):
        tenant_missing.append({"field": "star_rating",
                               "label": "Yıldız sınıflaması"})

    checks = [
        {"key": "tesis_kunyesi", "label": "Tesis künyesi tam",
         "ok": bool(tenant.get("hotel_name") and tenant.get("address")
                    and tenant.get("phone")),
         "fields": ["hotel_name", "address", "phone"]},
        {"key": "vergi_no", "label": "Vergi numarası kayıtlı",
         "ok": bool(tenant.get("tax_no")),
         "fields": ["tax_no"]},
        {"key": "isletme_belgesi", "label": "İşletme belgesi numarası kayıtlı",
         "ok": bool(tenant.get("license_number")),
         "fields": ["license_number"]},
        {"key": "isletme_belgesi_gecerli",
         "label": "İşletme belgesi süresi (en az 30 gün)",
         "ok": (license_days_left is not None and license_days_left > 30),
         "fields": ["license_expires_at"]},
        {"key": "yildiz_atanmis", "label": "Yıldız sınıflaması atanmış",
         "ok": bool(tenant.get("star_rating")),
         "fields": ["star_rating"]},
        {"key": "oda_envanteri",
         "label": "Oda envanteri tanımlı (>0)", "ok": total_rooms > 0,
         "fields": []},
        {"key": "personel", "label": "Aktif personel kayıtlı (>0)",
         "ok": total_users > 0, "fields": []},
    ]
    score = round(sum(1 for c in checks if c["ok"]) / len(checks) * 100)

    if rooms_missing_bed_capacity:
        logger.warning(
            "inspection_readiness tenant=%s: %d/%d rooms missing 'bed_capacity' "
            "— TÜİK bed totals fall back to 2/oda",
            current_user.tenant_id, rooms_missing_bed_capacity, total_rooms)

    return {
        "tenant": tenant,
        "tenant_missing_fields": tenant_missing,
        "rooms_total": total_rooms,
        "rooms_missing_bed_capacity": rooms_missing_bed_capacity,
        "active_users": total_users,
        "license_days_left": license_days_left,
        "checks": checks,
        "readiness_score": score,
        "booking_trend_12m": months,
    }


# ─────────────────────────────────────────────────────────────────────
# Star classification self-check
# ─────────────────────────────────────────────────────────────────────

# Catalog of criteria. Per-star "required" flags (True = zorunlu).
# Source: Türkiye Turizm Tesisleri Yönetmeliği özet kuralları.
_STAR_CRITERIA: list[dict[str, Any]] = [
    # PHYSICAL
    {"key": "klima_oda", "category": "Fiziksel Donanım",
     "label": "Tüm odalarda klima",
     "required_for": [3, 4, 5]},
    {"key": "minibar", "category": "Fiziksel Donanım",
     "label": "Tüm odalarda mini bar",
     "required_for": [4, 5]},
    {"key": "banyo_ozel", "category": "Fiziksel Donanım",
     "label": "Her odada özel banyo",
     "required_for": [1, 2, 3, 4, 5]},
    {"key": "oda_buyukluk_min",
     "category": "Fiziksel Donanım",
     "label": "Standart oda en az 14 m²",
     "required_for": [3, 4, 5]},
    # SERVICES
    {"key": "resepsiyon_24", "category": "Hizmetler",
     "label": "7/24 resepsiyon hizmeti",
     "required_for": [3, 4, 5]},
    {"key": "bell_boy", "category": "Hizmetler",
     "label": "Bell-boy / bagaj hizmeti",
     "required_for": [4, 5]},
    {"key": "concierge", "category": "Hizmetler",
     "label": "Concierge hizmeti",
     "required_for": [5]},
    {"key": "camasirhane", "category": "Hizmetler",
     "label": "Çamaşırhane / kuru temizleme servisi",
     "required_for": [3, 4, 5]},
    # F&B
    {"key": "restoran", "category": "Yiyecek-İçecek",
     "label": "En az bir restoran",
     "required_for": [2, 3, 4, 5]},
    {"key": "alacarte", "category": "Yiyecek-İçecek",
     "label": "À la carte servis",
     "required_for": [4, 5]},
    {"key": "room_service_24", "category": "Yiyecek-İçecek",
     "label": "7/24 oda servisi",
     "required_for": [5]},
    # COMMON AREAS
    {"key": "lobi_oturma", "category": "Ortak Alanlar",
     "label": "Lobide yeterli oturma alanı",
     "required_for": [1, 2, 3, 4, 5]},
    {"key": "havuz", "category": "Ortak Alanlar",
     "label": "Yüzme havuzu (iç veya dış)",
     "required_for": [4, 5]},
    {"key": "fitness", "category": "Ortak Alanlar",
     "label": "Fitness merkezi",
     "required_for": [4, 5]},
    {"key": "spa", "category": "Ortak Alanlar",
     "label": "SPA / sağlık merkezi",
     "required_for": [5]},
    {"key": "toplanti_odasi", "category": "Ortak Alanlar",
     "label": "Toplantı odası",
     "required_for": [4, 5]},
    {"key": "otopark", "category": "Ortak Alanlar",
     "label": "Otopark",
     "required_for": [3, 4, 5]},
    # SAFETY
    {"key": "yangin_alarm", "category": "Güvenlik",
     "label": "Yangın alarm sistemi",
     "required_for": [1, 2, 3, 4, 5]},
    {"key": "kamera", "category": "Güvenlik",
     "label": "Ortak alanlarda kamera",
     "required_for": [3, 4, 5]},
    {"key": "kasa_oda", "category": "Güvenlik",
     "label": "Tüm odalarda kasa",
     "required_for": [4, 5]},
    # ENV / OTHER
    {"key": "engelli_oda", "category": "Erişilebilirlik",
     "label": "Engelli misafirler için en az 1 oda",
     "required_for": [3, 4, 5]},
    {"key": "yabanci_dil_personel",
     "category": "Personel",
     "label": "Yabancı dil bilen resepsiyon personeli",
     "required_for": [3, 4, 5]},
    {"key": "uniform", "category": "Personel",
     "label": "Üniformalı personel",
     "required_for": [3, 4, 5]},
    {"key": "atik_yonetim", "category": "Çevre",
     "label": "Atık ayrıştırma sistemi",
     "required_for": [4, 5]},
]


class ChecklistEntry(BaseModel):
    key: str
    state: str = Field(pattern=r"^(yes|no|partial)$")
    note: str | None = None


class ChecklistSubmission(BaseModel):
    target_star: int = Field(ge=1, le=5)
    entries: list[ChecklistEntry]


@router.get("/star-classification/checklist")
@cached(ttl=300, key_prefix="regulatory_star_checklist")
async def get_star_checklist(
    current_user: User = Depends(get_current_user),
    _nocache: bool = Query(False, alias="nocache"),
) -> dict[str, Any]:
    saved = await db.regulatory_star_checklists.find_one(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}) or {}
    state_map = {e["key"]: e for e in saved.get("entries", [])}
    target_star = saved.get("target_star")
    if not target_star:
        tenant = await db.tenants.find_one(
            {"id": current_user.tenant_id}, {"star_rating": 1, "_id": 0})
        target_star = int((tenant or {}).get("star_rating") or 4)
    items = []
    for c in _STAR_CRITERIA:
        e = state_map.get(c["key"], {})
        items.append({
            **c,
            "required": target_star in c["required_for"],
            "state": e.get("state", "no"),
            "note": e.get("note"),
        })
    # Score: required olanlardan kaç tanesi yes (partial = 0.5).
    required = [i for i in items if i["required"]]
    if required:
        scored = sum(
            1.0 if i["state"] == "yes"
            else 0.5 if i["state"] == "partial" else 0.0
            for i in required)
        score = round(scored / len(required) * 100)
    else:
        score = 100
    missing = [i for i in required if i["state"] != "yes"]
    return {
        "target_star": target_star,
        "items": items,
        "compliance_score": score,
        "required_total": len(required),
        "required_missing": len(missing),
        "missing_keys": [m["key"] for m in missing],
        "saved_at": saved.get("saved_at"),
    }


@router.post("/star-classification/checklist")
async def save_star_checklist(
    payload: ChecklistSubmission,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v98 DW
) -> dict[str, Any]:
    valid_keys = {c["key"] for c in _STAR_CRITERIA}
    cleaned = [e.model_dump() for e in payload.entries
               if e.key in valid_keys]
    doc = {
        "tenant_id": current_user.tenant_id,
        "target_star": payload.target_star,
        "entries": cleaned,
        "saved_at": datetime.now(UTC).isoformat(),
        "saved_by": current_user.id,
    }
    await db.regulatory_star_checklists.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$set": doc}, upsert=True)
    await create_audit_log(
        tenant_id=current_user.tenant_id, user=current_user,
        action="SAVE_STAR_CHECKLIST", entity_type="regulatory_checklist",
        entity_id=current_user.tenant_id,
        changes={"target_star": payload.target_star,
                 "entry_count": len(cleaned)})
    # Invalidate cached checklist so next GET reads fresh state.
    try:
        _cache.safe_invalidate(current_user.tenant_id, "regulatory_star_checklist")
    except Exception as e:  # pragma: no cover
        logger.debug("regulatory_star_checklist cache invalidation skipped: %s", e)
    # Bypass cache on the immediate read-back (write-through guarantee).
    return await get_star_checklist(current_user, _nocache=True)


# ─────────────────────────────────────────────────────────────────────
# TGA Tesis Entegrasyon — Türkiye Turizm Tanıtım ve Geliştirme Ajansı
# Doc: https://tesis-entegrasyon.tga.gov.tr/docs
# ─────────────────────────────────────────────────────────────────────


class TgaConfigPayload(BaseModel):
    belge_no: str | None = None
    vergi_no: str | None = None
    api_key: str | None = None  # boş bırakılırsa mevcut korunur
    environment: str | None = Field(default=None, pattern="^(test|live)$")
    enabled: bool | None = None


@router.get("/tga/config")
async def tga_config_get(
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_op("manage_settings")),
) -> dict[str, Any]:
    return await get_tga_config(current_user.tenant_id)


@router.put("/tga/config")
async def tga_config_set(
    payload: TgaConfigPayload,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_op("manage_settings")),
) -> dict[str, Any]:
    try:
        out = await set_tga_config(
            current_user.tenant_id,
            belge_no=payload.belge_no,
            vergi_no=payload.vergi_no,
            api_key=payload.api_key,
            environment=payload.environment,
            enabled=payload.enabled,
        )
    except ValueError as ve:
        raise HTTPException(400, str(ve)) from ve
    await create_audit_log(
        tenant_id=current_user.tenant_id, user=current_user,
        action="UPDATE_TGA_CONFIG", entity_type="integration_tga",
        entity_id=current_user.tenant_id,
        changes={k: v for k, v in payload.model_dump().items()
                 if v is not None and k != "api_key"})
    return out


@router.get("/tga/preview")
async def tga_preview(
    date: str = Query(..., description="YYYY-MM-DD"),
    days: int = Query(1, ge=1, le=7),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_op("manage_settings")),
) -> dict[str, Any]:
    """Belirtilen tarihe kadar son `days` günün TGA payload önizlemesi
    (gönderim YAPILMAZ)."""
    try:
        end_d = datetime.fromisoformat(date).date()
    except Exception as ex:
        raise HTTPException(400, "date must be YYYY-MM-DD") from ex
    if days == 1:
        body = await build_daily_payload(current_user.tenant_id, end_d)
        return {"single": body}
    envelope = await build_batch_envelope(current_user.tenant_id, end_d, days=days)
    # API anahtarı önizleme yanıtında dönmez — envelope sadece veri tarafı.
    return envelope


@router.post("/tga/send")
async def tga_send_manual(
    end_date: str = Query(..., description="YYYY-MM-DD (dahil)"),
    days: int = Query(7, ge=1, le=7),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_op("manage_settings")),
) -> dict[str, Any]:
    try:
        end_d = datetime.fromisoformat(end_date).date()
    except Exception as ex:
        raise HTTPException(400, "end_date must be YYYY-MM-DD") from ex
    res = await send_batch(
        current_user.tenant_id, end_d, days=days, triggered_by="manual",
    )
    await create_audit_log(
        tenant_id=current_user.tenant_id, user=current_user,
        action="SEND_TGA_BATCH", entity_type="integration_tga",
        entity_id=current_user.tenant_id,
        changes={"end_date": end_date, "days": days,
                 "status": res.get("status"),
                 "http_status": res.get("http_status")})
    return res


@router.get("/tga/log")
async def tga_log(
    days: int = Query(30, ge=1, le=180),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_op("manage_settings")),
) -> dict[str, Any]:
    items = await list_send_log(current_user.tenant_id, days=days)
    return {"days": days, "count": len(items), "items": items}
