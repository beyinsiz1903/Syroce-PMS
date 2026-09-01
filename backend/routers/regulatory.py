"""Regulatory reports — Turkish Ministry & TÜİK self-service exports.

Provides:
  GET /api/regulatory/ktb/monthly?year=&month=
      → Kültür ve Turizm Bakanlığı aylık konaklama istatistikleri
        (tesise geliş, kişi-gece, uyruk, doluluk). Legacy
        /tuik/monthly aliası korunur.
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
from modules.regulatory.ktb_monthly import calculate_ktb_stays

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/regulatory", tags=["regulatory"])


# ─────────────────────────────────────────────────────────────────────
# TÜİK Monthly
# ─────────────────────────────────────────────────────────────────────


def _period_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    if month < 1 or month > 12:
        raise HTTPException(400, "month must be 1-12")
    start = datetime(year, month, 1, tzinfo=UTC)
    end = datetime(year + 1, 1, 1, tzinfo=UTC) if month == 12 else datetime(year, month + 1, 1, tzinfo=UTC)
    return start, end


def _days_in_month(year: int, month: int) -> int:
    s, e = _period_bounds(year, month)
    return (e - s).days


# Common TR locale country normalization.
_TR_COUNTRY_ALIASES = {
    "TR": "Türkiye",
    "TURKEY": "Türkiye",
    "TÜRKİYE": "Türkiye",
    "TURKİYE": "Türkiye",
    "TÜRKIYE": "Türkiye",
    "DE": "Almanya",
    "GERMANY": "Almanya",
    "GB": "Birleşik Krallık",
    "UK": "Birleşik Krallık",
    "RU": "Rusya",
    "RUSSIA": "Rusya",
    "US": "ABD",
    "USA": "ABD",
    "FR": "Fransa",
    "NL": "Hollanda",
    "IT": "İtalya",
    "BE": "Belçika",
    "AT": "Avusturya",
    "CH": "İsviçre",
    "PL": "Polonya",
    "UA": "Ukrayna",
}


def _normalize_country(raw: str | None) -> str:
    if not raw:
        return "Belirtilmemiş"
    key = raw.strip().upper()
    return _TR_COUNTRY_ALIASES.get(key, raw.strip().title())


@router.get("/ktb/monthly")
@router.get("/tuik/monthly")
async def tuik_monthly(
    year: int,
    month: int,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_regulatory_reports")),
) -> dict[str, Any]:
    start, end = _period_bounds(year, month)
    days = _days_in_month(year, month)

    # Capacity: count active rooms for the tenant.
    active_room_filter = {
        "tenant_id": current_user.tenant_id,
        "status": {"$nin": ["out_of_service", "inactive"]},
        "active": {"$ne": False},
        "is_active": {"$ne": False},
    }
    total_rooms = await db.rooms.count_documents(active_room_filter)
    bed_pipeline = [
        {"$match": active_room_filter},
        {"$group": {"_id": None, "beds": {"$sum": {"$ifNull": ["$bed_capacity", 2]}}}},
    ]
    bed_doc = await db.rooms.aggregate(bed_pipeline).to_list(length=1)
    total_beds = bed_doc[0]["beds"] if bed_doc else total_rooms * 2

    # Stays: bookings that overlap the period.
    bookings = await db.bookings.find(
        {"tenant_id": current_user.tenant_id, "status": {"$nin": ["cancelled", "no_show"]}, "check_in": {"$lt": end.isoformat()}, "check_out": {"$gt": start.isoformat()}},
        {
            "_id": 0,
            "id": 1,
            "booking_id": 1,
            "confirmation_number": 1,
            "check_in": 1,
            "check_out": 1,
            "adults": 1,
            "children": 1,
            "nationality": 1,
            "guest_country": 1,
            "country": 1,
            "guest_name": 1,
            "primary_guest_name": 1,
        },
    ).to_list(length=20000)

    metrics = calculate_ktb_stays(bookings, start, end, _normalize_country)
    nights_total = metrics["room_nights_sold"]
    nights_by_country = metrics["nights_by_country"]
    arrivals_total = metrics["arrivals_total"]
    arrivals_domestic = metrics["arrivals_domestic"]
    arrivals_foreign = metrics["arrivals_foreign"]
    arrivals_unspecified = metrics["arrivals_unspecified"]
    carried_in_guests = metrics["carried_in_guests"]
    domestic_nights = metrics["person_nights_domestic"]
    foreign_nights = metrics["person_nights_foreign"]
    unspecified_nights = metrics["person_nights_unspecified"]
    missing_nationality_bookings = metrics["missing_nationality"]
    missing_nationality_total = metrics["missing_nationality_total"]
    adults_fallback_count = metrics["adults_fallback_count"]

    if adults_fallback_count:
        logger.warning("tuik_monthly tenant=%s period=%s-%02d: %d bookings missing 'adults' (defaulted to 1)", current_user.tenant_id, year, month, adults_fallback_count)

    capacity_room_nights = total_rooms * days
    occupancy_pct = round(nights_total / capacity_room_nights * 100, 2) if capacity_room_nights > 0 else 0.0
    person_nights_total = metrics["person_nights_total"]
    alos = round(person_nights_total / arrivals_total, 2) if arrivals_total > 0 else 0.0

    # Top 20 countries.
    top = sorted(nights_by_country.items(), key=lambda x: -x[1])[:20]
    other = sum(v for k, v in nights_by_country.items() if k not in {kk for kk, _ in top})

    return {
        "period": f"{year}-{month:02d}",
        "days_in_month": days,
        "capacity": {
            "rooms": total_rooms,
            "beds": total_beds,
            "room_nights_capacity": capacity_room_nights,
        },
        "stays": {
            "booking_count": metrics["valid_booking_count"],
            # Backwards-compatible alias used by the existing UI.
            "guest_count": arrivals_total,
            "arrivals_total": arrivals_total,
            "arrivals_domestic": arrivals_domestic,
            "arrivals_foreign": arrivals_foreign,
            "arrivals_unspecified": arrivals_unspecified,
            "carried_in_guests": carried_in_guests,
            "room_nights_sold": nights_total,
            "person_nights_domestic": domestic_nights,
            "person_nights_foreign": foreign_nights,
            "person_nights_unspecified": unspecified_nights,
            "person_nights_total": person_nights_total,
        },
        "occupancy_pct": occupancy_pct,
        "average_length_of_stay": alos,
        "nationality_top20": [{"country": k, "person_nights": v} for k, v in top],
        "nationality_other_total": other,
        "missing_nationality": {
            "booking_count": missing_nationality_total,
            "samples": missing_nationality_bookings,
        },
        "data_quality": {
            "adults_defaulted_count": adults_fallback_count,
        },
        "submission_window": {
            "opens_on_day": 1,
            "due_on_day": 10,
            "correction_until_day": 25,
            "portal_url": "https://is.kultur.gov.tr/public/login.xhtml",
            "automatic_submission": False,
        },
        "calculation_rules": {
            "stay_interval": "check_in <= day < check_out",
            "month_boundary_carry_in": True,
            "inactive_rooms_excluded": True,
        },
        "ktb_form_reference": "Konaklama İstatistikleri Sistemi - Aylık Veri Girişi",
        "tuik_form_reference": "Aylık Konaklama İstatistikleri Anketi (geriye dönük uyumluluk)",
    }


# ─────────────────────────────────────────────────────────────────────
# Inspection readiness
# ─────────────────────────────────────────────────────────────────────


def _normalize_tenant_legal_profile(tenant: dict[str, Any]) -> dict[str, Any]:
    """Return the canonical regulatory view of a historically mixed tenant.

    Older tenants use ``hotel_name``/``tax_no`` while the current hotel
    settings and onboarding flows write ``property_name``/``tax_number``.
    Regulatory readiness must not report valid data as missing merely because
    it was stored by the newer flow.
    """
    normalized = dict(tenant)
    normalized["hotel_name"] = tenant.get("hotel_name") or tenant.get("property_name") or tenant.get("name")
    normalized["tax_no"] = tenant.get("tax_no") or tenant.get("tax_number")
    normalized["phone"] = tenant.get("phone") or tenant.get("contact_phone")
    return normalized


@router.get("/inspection-readiness")
@cached(ttl=300, key_prefix="regulatory_inspection_readiness")
async def inspection_readiness(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_regulatory_reports")),
    _nocache: bool = Query(False, alias="nocache"),
) -> dict[str, Any]:
    tenant = _normalize_tenant_legal_profile(
        await db.tenants.find_one(
            {"id": current_user.tenant_id},
            {
                "_id": 0,
                "hotel_name": 1,
                "property_name": 1,
                "name": 1,
                "hotel_id": 1,
                "tax_no": 1,
                "tax_number": 1,
                "star_rating": 1,
                "address": 1,
                "phone": 1,
                "contact_phone": 1,
                "license_number": 1,
                "license_expires_at": 1,
            },
        )
        or {}
    )

    total_rooms = await db.rooms.count_documents({"tenant_id": current_user.tenant_id})
    total_users = await db.users.count_documents({"tenant_id": current_user.tenant_id, "active": {"$ne": False}})
    rooms_missing_bed_capacity = await db.rooms.count_documents({"tenant_id": current_user.tenant_id, "$or": [{"bed_capacity": {"$exists": False}}, {"bed_capacity": None}]})

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
    counts = await _asyncio.gather(
        *[
            db.bookings.count_documents(
                {
                    "tenant_id": current_user.tenant_id,
                    "status": {"$nin": ["cancelled", "no_show"]},
                    "check_in": {"$lt": e.isoformat()},
                    "check_out": {"$gt": s.isoformat()},
                }
            )
            for (_, _, s, e, _) in spec
        ]
    )
    months: list[dict[str, Any]] = [
        {"period": f"{y}-{m:02d}", "booking_count": bks, "capacity_room_nights": cap, "occupancy_pct": (round(bks * 100 / cap, 1) if cap else 0.0)}
        for (y, m, _, _, cap), bks in zip(spec, counts, strict=True)
    ]

    # Sertifika & belge kontrolleri
    license_expiry_iso = tenant.get("license_expires_at")
    license_days_left: int | None = None
    if license_expiry_iso:
        try:
            le = datetime.fromisoformat(license_expiry_iso.replace("Z", "+00:00"))
            if le.tzinfo is None:
                le = le.replace(tzinfo=UTC)
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
        tenant_missing.append({"field": "license_number", "label": "İşletme belgesi numarası"})
    if not tenant.get("license_expires_at"):
        tenant_missing.append({"field": "license_expires_at", "label": "İşletme belgesi son geçerlilik tarihi"})
    if not tenant.get("star_rating"):
        tenant_missing.append({"field": "star_rating", "label": "Yıldız sınıflaması"})

    checks = [
        {"key": "tesis_kunyesi", "label": "Tesis künyesi tam", "ok": bool(tenant.get("hotel_name") and tenant.get("address") and tenant.get("phone")), "fields": ["hotel_name", "address", "phone"]},
        {"key": "vergi_no", "label": "Vergi numarası kayıtlı", "ok": bool(tenant.get("tax_no")), "fields": ["tax_no"]},
        {"key": "isletme_belgesi", "label": "İşletme belgesi numarası kayıtlı", "ok": bool(tenant.get("license_number")), "fields": ["license_number"]},
        {"key": "isletme_belgesi_gecerli", "label": "İşletme belgesi süresi (en az 30 gün)", "ok": (license_days_left is not None and license_days_left > 30), "fields": ["license_expires_at"]},
        {"key": "yildiz_atanmis", "label": "Yıldız sınıflaması atanmış", "ok": bool(tenant.get("star_rating")), "fields": ["star_rating"]},
        {"key": "oda_envanteri", "label": "Oda envanteri tanımlı (>0)", "ok": total_rooms > 0, "fields": []},
        {"key": "personel", "label": "Aktif personel kayıtlı (>0)", "ok": total_users > 0, "fields": []},
    ]
    score = round(sum(1 for c in checks if c["ok"]) / len(checks) * 100)

    if rooms_missing_bed_capacity:
        logger.warning("inspection_readiness tenant=%s: %d/%d rooms missing 'bed_capacity' — TÜİK bed totals fall back to 2/oda", current_user.tenant_id, rooms_missing_bed_capacity, total_rooms)

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
    {"key": "klima_oda", "category": "Fiziksel Donanım", "label": "Tüm odalarda klima", "required_for": [3, 4, 5]},
    {"key": "minibar", "category": "Fiziksel Donanım", "label": "Tüm odalarda mini bar", "required_for": [4, 5]},
    {"key": "banyo_ozel", "category": "Fiziksel Donanım", "label": "Her odada özel banyo", "required_for": [1, 2, 3, 4, 5]},
    {"key": "oda_buyukluk_min", "category": "Fiziksel Donanım", "label": "Standart oda en az 14 m²", "required_for": [3, 4, 5]},
    # SERVICES
    {"key": "resepsiyon_24", "category": "Hizmetler", "label": "7/24 resepsiyon hizmeti", "required_for": [3, 4, 5]},
    {"key": "bell_boy", "category": "Hizmetler", "label": "Bell-boy / bagaj hizmeti", "required_for": [4, 5]},
    {"key": "concierge", "category": "Hizmetler", "label": "Concierge hizmeti", "required_for": [5]},
    {"key": "camasirhane", "category": "Hizmetler", "label": "Çamaşırhane / kuru temizleme servisi", "required_for": [3, 4, 5]},
    # F&B
    {"key": "restoran", "category": "Yiyecek-İçecek", "label": "En az bir restoran", "required_for": [2, 3, 4, 5]},
    {"key": "alacarte", "category": "Yiyecek-İçecek", "label": "À la carte servis", "required_for": [4, 5]},
    {"key": "room_service_24", "category": "Yiyecek-İçecek", "label": "7/24 oda servisi", "required_for": [5]},
    # COMMON AREAS
    {"key": "lobi_oturma", "category": "Ortak Alanlar", "label": "Lobide yeterli oturma alanı", "required_for": [1, 2, 3, 4, 5]},
    {"key": "havuz", "category": "Ortak Alanlar", "label": "Yüzme havuzu (iç veya dış)", "required_for": [4, 5]},
    {"key": "fitness", "category": "Ortak Alanlar", "label": "Fitness merkezi", "required_for": [4, 5]},
    {"key": "spa", "category": "Ortak Alanlar", "label": "SPA / sağlık merkezi", "required_for": [5]},
    {"key": "toplanti_odasi", "category": "Ortak Alanlar", "label": "Toplantı odası", "required_for": [4, 5]},
    {"key": "otopark", "category": "Ortak Alanlar", "label": "Otopark", "required_for": [3, 4, 5]},
    # SAFETY
    {"key": "yangin_alarm", "category": "Güvenlik", "label": "Yangın alarm sistemi", "required_for": [1, 2, 3, 4, 5]},
    {"key": "kamera", "category": "Güvenlik", "label": "Ortak alanlarda kamera", "required_for": [3, 4, 5]},
    {"key": "kasa_oda", "category": "Güvenlik", "label": "Tüm odalarda kasa", "required_for": [4, 5]},
    # ENV / OTHER
    {"key": "engelli_oda", "category": "Erişilebilirlik", "label": "Engelli misafirler için en az 1 oda", "required_for": [3, 4, 5]},
    {"key": "yabanci_dil_personel", "category": "Personel", "label": "Yabancı dil bilen resepsiyon personeli", "required_for": [3, 4, 5]},
    {"key": "uniform", "category": "Personel", "label": "Üniformalı personel", "required_for": [3, 4, 5]},
    {"key": "atik_yonetim", "category": "Çevre", "label": "Atık ayrıştırma sistemi", "required_for": [4, 5]},
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
    saved = await db.regulatory_star_checklists.find_one({"tenant_id": current_user.tenant_id}, {"_id": 0}) or {}
    state_map = {e["key"]: e for e in saved.get("entries", [])}
    target_star = saved.get("target_star")
    if not target_star:
        tenant = await db.tenants.find_one({"id": current_user.tenant_id}, {"star_rating": 1, "_id": 0})
        target_star = int((tenant or {}).get("star_rating") or 4)
    items = []
    for c in _STAR_CRITERIA:
        e = state_map.get(c["key"], {})
        items.append(
            {
                **c,
                "required": target_star in c["required_for"],
                "state": e.get("state", "no"),
                "note": e.get("note"),
            }
        )
    # Score: required olanlardan kaç tanesi yes (partial = 0.5).
    required = [i for i in items if i["required"]]
    if required:
        scored = sum(1.0 if i["state"] == "yes" else 0.5 if i["state"] == "partial" else 0.0 for i in required)
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
    cleaned = [e.model_dump() for e in payload.entries if e.key in valid_keys]
    doc = {
        "tenant_id": current_user.tenant_id,
        "target_star": payload.target_star,
        "entries": cleaned,
        "saved_at": datetime.now(UTC).isoformat(),
        "saved_by": current_user.id,
    }
    await db.regulatory_star_checklists.update_one({"tenant_id": current_user.tenant_id}, {"$set": doc}, upsert=True)
    await create_audit_log(
        tenant_id=current_user.tenant_id,
        user=current_user,
        action="SAVE_STAR_CHECKLIST",
        entity_type="regulatory_checklist",
        entity_id=current_user.tenant_id,
        changes={"target_star": payload.target_star, "entry_count": len(cleaned)},
    )
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
        tenant_id=current_user.tenant_id,
        user=current_user,
        action="UPDATE_TGA_CONFIG",
        entity_type="integration_tga",
        entity_id=current_user.tenant_id,
        changes={k: v for k, v in payload.model_dump().items() if v is not None and k != "api_key"},
    )
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
        current_user.tenant_id,
        end_d,
        days=days,
        triggered_by="manual",
    )
    await create_audit_log(
        tenant_id=current_user.tenant_id,
        user=current_user,
        action="SEND_TGA_BATCH",
        entity_type="integration_tga",
        entity_id=current_user.tenant_id,
        changes={"end_date": end_date, "days": days, "status": res.get("status"), "http_status": res.get("http_status")},
    )
    return res


@router.get("/tga/log")
async def tga_log(
    days: int = Query(30, ge=1, le=180),
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_op("manage_settings")),
) -> dict[str, Any]:
    items = await list_send_log(current_user.tenant_id, days=days)
    return {"days": days, "count": len(items), "items": items}
