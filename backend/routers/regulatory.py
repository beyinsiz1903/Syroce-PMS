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

from datetime import UTC, datetime
from typing import Any

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from cache_manager import cache as _cache
from cache_manager import cached
from core.database import db
from core.helpers import create_audit_log
from core.security import get_current_user
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
        {"_id": 0, "check_in": 1, "check_out": 1, "adults": 1,
         "children": 1, "nationality": 1, "guest_country": 1,
         "country": 1}).to_list(length=20000)

    nights_total = 0
    nights_by_country: dict[str, int] = {}
    guest_total = 0
    domestic_nights = 0
    foreign_nights = 0
    unspecified_nights = 0
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
        guests = int(bk.get("adults") or 1) + int(bk.get("children") or 0)
        country = _normalize_country(
            bk.get("nationality") or bk.get("guest_country") or bk.get("country"))
        person_nights = nights * guests
        nights_total += nights
        guest_total += guests
        nights_by_country[country] = nights_by_country.get(country, 0) + person_nights
        if country == "Türkiye":
            domestic_nights += person_nights
        elif country == "Belirtilmemiş":
            unspecified_nights += person_nights
        else:
            foreign_nights += person_nights

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
        "tuik_form_reference": "Aylık Konaklama İstatistikleri Anketi",
    }


# ─────────────────────────────────────────────────────────────────────
# Inspection readiness
# ─────────────────────────────────────────────────────────────────────

@router.get("/inspection-readiness")
@cached(ttl=300, key_prefix="regulatory_inspection_readiness")
async def inspection_readiness(
    current_user: User = Depends(get_current_user),
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

    checks = [
        {"key": "tesis_kunyesi", "label": "Tesis künyesi tam",
         "ok": bool(tenant.get("hotel_name") and tenant.get("address")
                    and tenant.get("phone"))},
        {"key": "vergi_no", "label": "Vergi numarası kayıtlı",
         "ok": bool(tenant.get("tax_no"))},
        {"key": "isletme_belgesi", "label": "İşletme belgesi numarası kayıtlı",
         "ok": bool(tenant.get("license_number"))},
        {"key": "isletme_belgesi_gecerli",
         "label": "İşletme belgesi süresi (en az 30 gün)",
         "ok": (license_days_left is not None and license_days_left > 30)},
        {"key": "yildiz_atanmis", "label": "Yıldız sınıflaması atanmış",
         "ok": bool(tenant.get("star_rating"))},
        {"key": "oda_envanteri",
         "label": "Oda envanteri tanımlı (>0)", "ok": total_rooms > 0},
        {"key": "personel", "label": "Aktif personel kayıtlı (>0)",
         "ok": total_users > 0},
    ]
    score = round(sum(1 for c in checks if c["ok"]) / len(checks) * 100)

    return {
        "tenant": tenant,
        "rooms_total": total_rooms,
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
