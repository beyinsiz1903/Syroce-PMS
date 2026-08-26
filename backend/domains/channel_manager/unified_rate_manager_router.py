"""
Unified Rate Manager Router — Tek Noktadan Fiyat, Musaitlik, Kontenjan Yonetimi
================================================================================
Otelde aktif olan kanal saglayiciyi (HotelRunner veya Exely) otomatik tespit eder.
Guncelleme yapildiginda:
  1. PMS veritabanina kaydeder
  2. Aktif kanal saglayiciya push eder
  3. Secilen acentelere fiyat/musaitlik iletir

Endpoints:
  GET  /detect-provider          — Aktif saglayiciyi tespit et
  GET  /grid                     — Takvim grid (aktif saglayicidan)
  GET  /room-types               — Oda tipleri ve fiyat planlari
  POST /bulk-grid-update         — Toplu guncelle + kanal push + acente push
  GET  /agencies                 — Fiyat iletilecek acenteleri listele
  GET  /agency-rates             — Acente bazli ozel fiyatlari getir
  POST /agency-rates             — Acente bazli ozel fiyat tanimla
  DELETE /agency-rates/{agency_id} — Acente ozel fiyatini sil
  GET  /push-providers           — Push saglayici durumu
  GET  /pricing-settings         — Fiyatlandirma tipi ayarlari
  PUT  /pricing-settings         — Fiyatlandirma tipi guncelle
  GET  /holidays                 — Tatil donemleri
  GET  /stop-sale-summary        — Stop sale ozet
"""

import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from pymongo import UpdateOne

from cache_manager import cached
from core.database import db
from core.occupancy_pricing import (
    OccupancyPricingError,
    calculate_occupancy_quote,
    normalize_occupancy_rule,
)
from core.security import get_current_user
from core.tenant_currency import get_tenant_currency
from domains.channel_manager.providers.exely.production_safety import (
    ari_write_block_reason as exely_ari_write_block_reason,
)
from domains.channel_manager.providers.exely.security import exely_connection_projection
from domains.channel_manager.providers.hotelrunner.production_safety import (
    ari_write_block_reason as hotelrunner_ari_write_block_reason,
)
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v96 DW
from services.cm_provider import _detect_active_provider, _tenant_configured_provider

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/channel-manager/unified-rate-manager",
    tags=["Unified Rate Manager"],
)


# ── Request / Response Models ────────────────────────────────────


class RoomTypeValuesItem(BaseModel):
    room_type_code: str
    rate_plan_codes: list[str]
    rate: float | None = None
    availability: int | None = None
    min_stay: int | None = None
    max_stay: int | None = None
    stop_sell: bool | None = None
    cta: bool | None = None
    ctd: bool | None = None


class RoomTypeSelection(BaseModel):
    room_type_code: str
    rate_plan_codes: list[str]


class UnifiedBulkUpdateRequest(BaseModel):
    provider: str | None = None
    room_type_codes: list[str] | None = None
    rate_plan_codes: list[str] | None = None
    selections: list[RoomTypeSelection] | None = None
    per_room_values: list[RoomTypeValuesItem] | None = None
    start_date: str
    end_date: str
    selected_days: list[int] | None = None
    rate: float | None = None
    availability: int | None = None
    min_stay: int | None = None
    max_stay: int | None = None
    stop_sell: bool | None = None
    cta: bool | None = None
    ctd: bool | None = None
    update_fields: list[str] = []
    agency_ids: list[str] | None = None


class AgencyRateOverride(BaseModel):
    agency_id: str
    room_type_code: str
    rate_plan_code: str | None = None  # null = tum planlar
    rate_multiplier: float | None = None  # ornegin 0.90 = %10 indirim
    fixed_rate: float | None = None  # sabit fiyat
    start_date: str | None = None
    end_date: str | None = None


class AgencyRateOverrideRequest(BaseModel):
    overrides: list[AgencyRateOverride]


class PricingSettingItem(BaseModel):
    room_type_code: str
    pricing_type: str
    base_occupancy: int = Field(2, ge=1, le=20)
    extra_adult_rate: float = Field(0, ge=0, le=1e12)
    extra_child_rate: float = Field(0, ge=0, le=1e12)
    child_free_age_max: int = Field(0, ge=0, le=17)
    max_occupancy: int | None = Field(None, ge=1, le=50)


class PricingSettingsRequest(BaseModel):
    settings: list[PricingSettingItem]


class OccupancyPricePreviewRequest(BaseModel):
    room_type_code: str
    base_nightly_rate: float = Field(..., ge=0, le=1e12)
    nights: int = Field(1, ge=1, le=750)
    adults: int = Field(1, ge=1, le=50)
    children_ages: list[int] = Field(default_factory=list, max_length=50)


def _pricing_payload(docs: list[dict]) -> tuple[dict[str, str], dict[str, dict]]:
    settings: dict[str, str] = {}
    rules: dict[str, dict] = {}
    for doc in docs:
        room_type_code = doc.get("room_type_code")
        if not room_type_code:
            continue
        try:
            rule = normalize_occupancy_rule(doc)
        except (OccupancyPricingError, TypeError, ValueError):
            rule = normalize_occupancy_rule({"pricing_type": doc.get("pricing_type", "per_room")})
        settings[room_type_code] = rule["pricing_type"]
        rules[room_type_code] = rule
    return settings, rules


async def _add_pms_rule_aliases(tenant_id: str, provider: str, rules: dict) -> dict:
    """Expose provider-code rules under their mapped PMS room type as well."""
    aliased = dict(rules)
    if provider == "hotelrunner":
        mappings = await db.hotelrunner_room_mappings.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(200)
        pairs = ((m.get("hr_inv_code"), m.get("pms_room_type")) for m in mappings)
    else:
        mappings = await db.exely_room_mappings.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(200)
        pairs = ((m.get("exely_room_code"), m.get("pms_room_type")) for m in mappings)
    for remote_code, pms_type in pairs:
        if remote_code in rules and pms_type:
            aliased.setdefault(str(pms_type), rules[remote_code])
    return aliased


def _ari_write_block_for_targets(targets: list[dict]) -> str:
    """Resolve runtime write gates without credentials or provider access."""
    for target in targets:
        provider = target.get("provider")
        if provider == "hotelrunner":
            reason = hotelrunner_ari_write_block_reason()
        elif provider == "exely":
            reason = exely_ari_write_block_reason()
        else:
            reason = "UNSUPPORTED_CHANNEL_PROVIDER"
        if reason:
            return reason
    return ""


def _provider_delivery_summary(results: list[dict]) -> dict:
    pending = [result for result in results if result.get("task_count", 0) > 0]
    if not pending:
        return {
            "provider_verified": False,
            "provider_delivery_state": "NOT_SENT",
            "provider_write_count": 0,
        }

    states = {result["delivery_state"] for result in pending}
    return {
        "provider_verified": False,
        "provider_delivery_state": states.pop() if len(states) == 1 else "PENDING",
        # Scheduled or durable-queued work is not proof of a provider mutation.
        "provider_write_count": None,
    }


# ── Provider Detection ───────────────────────────────────────────


# ── Detect Provider Endpoint ─────────────────────────────────────


@router.get("/detect-provider")
async def detect_provider(current_user: User = Depends(get_current_user)):
    """Aktif kanal saglayicilari tespit et.

    Returns the primary `provider` (back-compat) AND the full list of
    active providers in `available` so the UI can render tabs for each.
    Uses `_detect_active_provider` so legacy HR tenants (provider_connections
    fallback) are also recognised.
    """
    tenant_id = current_user.tenant_id

    # HR through canonical detector (handles legacy provider_connections)
    hr_detect = await _detect_active_provider(tenant_id, prefer="hotelrunner")
    hr_conn = hr_detect["connection"] if hr_detect["provider"] == "hotelrunner" else None

    exely_conn = await db.exely_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True},
        exely_connection_projection(),
    )

    # Otel icin super_admin bir altyapi sectiyse, operatore YALNIZCA o
    # saglayici gosterilir (fail-closed: secilenin baglantisi yoksa liste bos).
    configured = await _tenant_configured_provider(tenant_id)

    available: list[dict] = []
    if hr_conn and configured in (None, "hotelrunner"):
        available.append(
            {
                "provider": "hotelrunner",
                "provider_name": "HotelRunner",
                "room_count": len(hr_conn.get("cached_rooms", [])),
            }
        )
    if exely_conn and configured in (None, "exely"):
        available.append(
            {
                "provider": "exely",
                "provider_name": "Exely",
                "room_count": len(exely_conn.get("room_types", [])),
            }
        )

    if not available:
        return {
            "provider": None,
            "provider_name": None,
            "has_connection": False,
            "room_count": 0,
            "available": [],
        }

    primary = available[0]
    return {
        "provider": primary["provider"],
        "provider_name": primary["provider_name"],
        "has_connection": True,
        "room_count": primary["room_count"],
        "available": available,
    }


# ── Unified Grid ─────────────────────────────────────────────────


@router.get("/grid")
async def get_unified_grid(
    start_date: str | None = None,
    end_date: str | None = None,
    provider: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Aktif saglayicinin takvim grid'ini dondurur.

    `provider`: opsiyonel — UI'daki sekmeye gore "hotelrunner" veya "exely"
    secilince o saglayicinin grid'i dondurulur. Belirtilmezse otomatik
    tespit (HR oncelikli).

    STRICT mode: explicit `provider=hotelrunner|exely` istenmis ve o
    saglayicinin aktif baglantisi yoksa, baska saglayiciya DUSULMEZ —
    bos grid donulur. Boylece UI'da yanlis sekme + yanlis veri eslesmesi
    olusmaz.
    """
    tenant_id = current_user.tenant_id
    if not start_date:
        start_date = datetime.now(UTC).date().isoformat()
    if not end_date:
        end_date = (datetime.now(UTC) + timedelta(days=14)).date().isoformat()
    explicit = provider in ("hotelrunner", "exely")
    detection = await _detect_active_provider(tenant_id, prefer=provider)

    if explicit and detection["provider"] != provider:
        return {
            "grid": [],
            "room_types": [],
            "rate_plans": [],
            "pricing_settings": {},
            "occupancy_pricing_rules": {},
            "currency": "TRY",
            "start_date": start_date,
            "end_date": end_date,
            "provider": provider,
        }

    if not detection["provider"]:
        return {
            "grid": [],
            "room_types": [],
            "rate_plans": [],
            "pricing_settings": {},
            "occupancy_pricing_rules": {},
            "currency": "TRY",
            "start_date": start_date,
            "end_date": end_date,
            "provider": None,
        }

    provider_type = detection["provider"]
    conn = detection["connection"]

    if provider_type == "hotelrunner":
        return await _build_hr_grid(tenant_id, conn, start_date, end_date)
    else:
        return await _build_exely_grid(tenant_id, conn, start_date, end_date)


async def _build_hr_grid(tenant_id, conn, start_date, end_date):
    """HotelRunner grid olustur."""
    cached_rooms = conn.get("cached_rooms", [])
    if not cached_rooms:
        return {
            "grid": [],
            "room_types": [],
            "rate_plans": [],
            "pricing_settings": {},
            "occupancy_pricing_rules": {},
            "currency": "TRY",
            "start_date": start_date,
            "end_date": end_date,
            "provider": "hotelrunner",
        }

    room_types, rate_plans = _extract_hr_room_types(cached_rooms)

    mappings = await db.hotelrunner_room_mappings.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(100)
    mapping_by_inv = {m.get("hr_inv_code", ""): m.get("pms_room_type", "") for m in mappings}

    calendar_data = await db.hr_rate_calendar.find(
        {"tenant_id": tenant_id, "date": {"$gte": start_date, "$lte": end_date}},
        {"_id": 0},
    ).to_list(5000)

    cal_index = {}
    for entry in calendar_data:
        key = f"{entry['room_type_code']}|{entry['rate_plan_code']}|{entry['date']}"
        cal_index[key] = entry

    room_counts, room_ids_by_type = await _get_room_counts(tenant_id)
    active_bookings = await _get_active_bookings(tenant_id, start_date, end_date)

    valid_pairs = set()
    for room in cached_rooms:
        inv_code = room.get("inv_code", "")
        rp_id = str(room.get("rate_plan_id", ""))
        if inv_code and rp_id:
            valid_pairs.add((inv_code, rp_id))

    grid = []
    for rt in room_types:
        pms_type = mapping_by_inv.get(rt["code"], "")
        counts = room_counts.get(pms_type, {"total": 0, "available": 0})

        for rp in rate_plans:
            if (rt["code"], rp["code"]) not in valid_pairs:
                continue
            dates_data = _build_dates(
                start_date,
                end_date,
                rt["code"],
                rp["code"],
                cal_index,
                pms_type,
                counts,
                room_ids_by_type,
                active_bookings,
            )
            grid.append(
                {
                    "room_type_code": rt["code"],
                    "room_type_name": rt["name"],
                    "rate_plan_code": rp["code"],
                    "rate_plan_name": rp["name"],
                    "pms_room_type": pms_type or rt["name"],
                    "total_rooms": counts["total"],
                    "dates": dates_data,
                }
            )

    pricing_docs = await db.hr_pricing_settings.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(200)
    pricing_map, pricing_rules = _pricing_payload(pricing_docs)

    currency = cached_rooms[0].get("sales_currency", "TRY") if cached_rooms else "TRY"

    return {
        "grid": grid,
        "room_types": room_types,
        "rate_plans": rate_plans,
        "pricing_settings": pricing_map,
        "occupancy_pricing_rules": pricing_rules,
        "currency": currency,
        "start_date": start_date,
        "end_date": end_date,
        "provider": "hotelrunner",
    }


async def _build_exely_grid(tenant_id, conn, start_date, end_date):
    """Exely grid olustur."""
    room_types = conn.get("room_types", [])
    rate_plans = conn.get("rate_plans", [])

    mappings = await db.exely_room_mappings.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(100)

    calendar_data = await db.rate_calendar.find(
        {"tenant_id": tenant_id, "date": {"$gte": start_date, "$lte": end_date}},
        {"_id": 0},
    ).to_list(5000)

    cal_index = {}
    for entry in calendar_data:
        key = f"{entry['room_type_code']}|{entry['rate_plan_code']}|{entry['date']}"
        cal_index[key] = entry

    room_counts, room_ids_by_type = await _get_room_counts(tenant_id)
    active_bookings = await _get_active_bookings(tenant_id, start_date, end_date)

    grid = []
    for rt in room_types:
        pms_type = None
        for m in mappings:
            if m.get("exely_room_code") == rt["code"]:
                pms_type = m.get("pms_room_type")
                break

        counts = room_counts.get(pms_type or rt["name"], {"total": 0, "available": 0})

        for rp in rate_plans:
            dates_data = _build_dates(
                start_date,
                end_date,
                rt["code"],
                rp["code"],
                cal_index,
                pms_type or rt["name"],
                counts,
                room_ids_by_type,
                active_bookings,
            )
            grid.append(
                {
                    "room_type_code": rt["code"],
                    "room_type_name": rt["name"],
                    "rate_plan_code": rp["code"],
                    "rate_plan_name": rp["name"],
                    "pms_room_type": pms_type or rt["name"],
                    "total_rooms": counts["total"],
                    "dates": dates_data,
                }
            )

    pricing_docs = await db.pricing_settings.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(200)
    pricing_map, pricing_rules = _pricing_payload(pricing_docs)

    currency = conn.get("currency", "TRY")

    return {
        "grid": grid,
        "room_types": room_types,
        "rate_plans": rate_plans,
        "pricing_settings": pricing_map,
        "occupancy_pricing_rules": pricing_rules,
        "currency": currency,
        "start_date": start_date,
        "end_date": end_date,
        "provider": "exely",
    }


# ── Shared Grid Helpers ──────────────────────────────────────────


def _extract_hr_room_types(cached_rooms):
    room_types_map = {}
    rate_plans_map = {}
    for room in cached_rooms:
        inv_code = room.get("inv_code", "")
        name = room.get("name", "")
        rp_id = str(room.get("rate_plan_id", ""))
        rp_name = room.get("rate_plan_name", "")
        if inv_code and inv_code not in room_types_map:
            room_types_map[inv_code] = {"code": inv_code, "name": name}
        if rp_id and rp_id not in rate_plans_map:
            rate_plans_map[rp_id] = {"code": rp_id, "name": rp_name}
    return list(room_types_map.values()), list(rate_plans_map.values())


async def _get_room_counts(tenant_id):
    rooms = await db.rooms.find({"tenant_id": tenant_id}, {"_id": 0, "id": 1, "room_type": 1, "status": 1}).to_list(500)
    room_counts = {}
    room_ids_by_type = {}
    for r in rooms:
        rt = r.get("room_type", "")
        room_counts.setdefault(rt, {"total": 0, "available": 0})
        room_counts[rt]["total"] += 1
        if r.get("status") == "available":
            room_counts[rt]["available"] += 1
        room_ids_by_type.setdefault(rt, []).append(r["id"])
    return room_counts, room_ids_by_type


async def _get_active_bookings(tenant_id, start_date, end_date):
    return await db.bookings.find(
        {
            "tenant_id": tenant_id,
            "status": {"$in": ["pending", "confirmed", "guaranteed", "checked_in"]},
            "check_in": {"$lt": end_date},
            "check_out": {"$gt": start_date},
        },
        {"_id": 0, "room_id": 1, "check_in": 1, "check_out": 1},
    ).to_list(10000)


def _count_sold(pms_room_type, day_str, room_ids_by_type, active_bookings):
    rt_room_ids = set(room_ids_by_type.get(pms_room_type, []))
    if not rt_room_ids:
        return 0
    sold = 0
    for b in active_bookings:
        rid = b.get("room_id")
        if rid not in rt_room_ids:
            continue
        ci = (b.get("check_in") or "")[:10]
        co = (b.get("check_out") or "")[:10]
        if ci <= day_str < co:
            sold += 1
    return sold


def _build_dates(start_date, end_date, rt_code, rp_code, cal_index, pms_type, counts, room_ids_by_type, active_bookings):
    dates_data = []
    d = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    while d <= end:
        ds = d.strftime("%Y-%m-%d")
        key = f"{rt_code}|{rp_code}|{ds}"
        entry = cal_index.get(key, {})
        base_avail = entry.get("availability")
        sold_count = _count_sold(pms_type, ds, room_ids_by_type, active_bookings) if pms_type else 0
        if base_avail is not None:
            real_avail = max(base_avail - sold_count, 0)
        else:
            real_avail = max(counts["total"] - sold_count, 0)
        dates_data.append(
            {
                "date": ds,
                "rate": entry.get("rate"),
                "availability": real_avail,
                "base_availability": base_avail if base_avail is not None else counts["total"],
                "sold": sold_count,
                "min_stay": entry.get("min_stay", 1),
                "stop_sell": entry.get("stop_sell", False),
            }
        )
        d += timedelta(days=1)
    return dates_data


# ── Room Types ───────────────────────────────────────────────────


@router.get("/room-types")
async def get_unified_room_types(current_user: User = Depends(get_current_user)):
    """Aktif saglayicinin oda tiplerini dondurur."""
    tenant_id = current_user.tenant_id
    detection = await _detect_active_provider(tenant_id)

    if not detection["provider"]:
        return {
            "room_types": [],
            "rate_plans": [],
            "pricing_settings": {},
            "occupancy_pricing_rules": {},
            "provider": None,
        }

    conn = detection["connection"]
    if detection["provider"] == "hotelrunner":
        room_types, rate_plans = _extract_hr_room_types(conn.get("cached_rooms", []))
        pricing_docs = await db.hr_pricing_settings.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(200)
    else:
        room_types = conn.get("room_types", [])
        rate_plans = conn.get("rate_plans", [])
        pricing_docs = await db.pricing_settings.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(200)

    pricing_map, pricing_rules = _pricing_payload(pricing_docs)

    return {
        "room_types": room_types,
        "rate_plans": rate_plans,
        "pricing_settings": pricing_map,
        "occupancy_pricing_rules": pricing_rules,
        "provider": detection["provider"],
    }


# ── Bulk Grid Update ─────────────────────────────────────────────


@router.post("/bulk-grid-update")
async def unified_bulk_grid_update(
    request: UnifiedBulkUpdateRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v96 DW
):
    """Toplu fiyat/musaitlik guncelle. Kanal saglayiciya + acentelere push."""
    tenant_id = current_user.tenant_id

    # Resolve target providers.
    # If `request.provider` is one of "hotelrunner" / "exely", STRICTLY
    # restrict the push to that single provider — the UI's per-provider
    # tab is the source of truth and avoids cross-channel mix-ups.
    # Otherwise (None / "all" / unknown) fan out to every active provider.
    targets: list[dict] = []

    hr_conn = await db.hotelrunner_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0})
    if not hr_conn:
        pc = await db.provider_connections.find_one({"tenant_id": tenant_id, "provider": "hotelrunner", "status": "active"})
        if pc:
            legacy = await db.hotelrunner_connections.find_one({"tenant_id": tenant_id}, {"_id": 0, "cached_rooms": 1})
            hr_conn = {
                "tenant_id": tenant_id,
                "is_active": True,
                "hr_id": pc.get("credentials", {}).get("hr_id", ""),
                "environment": pc.get("environment", "live"),
                "cached_rooms": (legacy or {}).get("cached_rooms", []),
            }

    exely_conn = await db.exely_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True},
        exely_connection_projection(),
    )

    # Per-tenant secili altyapi (super_admin) OTORITERDIR; istemcinin
    # request.provider'i bunu ezemez: configured-exely otel yalnizca Exely'ye
    # push eder (baglantisi yoksa 404), HR'a ASLA. Secimi seciliyle CAKISAN
    # request.provider -> target bos -> 404 (fail-closed). Secim yoksa (alan
    # null) eski explicit/fan-out davranisi korunur (pilot_drift=0).
    configured = await _tenant_configured_provider(tenant_id)
    explicit = request.provider if request.provider in ("hotelrunner", "exely") else None

    if configured is not None:
        if explicit is None or explicit == configured:
            if configured == "hotelrunner" and hr_conn:
                targets.append({"provider": "hotelrunner", "connection": hr_conn})
            elif configured == "exely" and exely_conn:
                targets.append({"provider": "exely", "connection": exely_conn})
        # explicit != configured -> targets bos kalir -> 404 (fail-closed)
    elif explicit == "hotelrunner":
        if hr_conn:
            targets.append({"provider": "hotelrunner", "connection": hr_conn})
    elif explicit == "exely":
        if exely_conn:
            targets.append({"provider": "exely", "connection": exely_conn})
    else:
        if hr_conn:
            targets.append({"provider": "hotelrunner", "connection": hr_conn})
        if exely_conn:
            targets.append({"provider": "exely", "connection": exely_conn})

    if not targets:
        raise HTTPException(status_code=404, detail="Aktif kanal saglayici bulunamadi")

    runtime_block = _ari_write_block_for_targets(targets)
    if runtime_block:
        raise HTTPException(
            status_code=409,
            detail={
                "error_code": runtime_block,
                "delivery_state": "BLOCKED",
                "provider_status_class": "NOT_SENT",
                "provider_write_count": 0,
            },
        )

    logger.info(
        "[UNIFIED] bulk-grid-update fan-out targets=%s tenant=%s primary=%s",
        [t["provider"] for t in targets],
        tenant_id,
        request.provider,
    )

    # Keep `detection` / `provider_type` populated for downstream code that
    # still references the "primary" provider (e.g. cal_collection choice).
    detection = targets[0]
    provider_type = detection["provider"]
    now = datetime.now(UTC).isoformat()

    # Build pairs
    per_room_map = {}
    if request.per_room_values:
        for prv in request.per_room_values:
            per_room_map[prv.room_type_code] = prv

    pairs = []
    if request.per_room_values:
        for prv in request.per_room_values:
            for rp_code in prv.rate_plan_codes:
                pairs.append((prv.room_type_code, rp_code))
    elif request.selections:
        for sel in request.selections:
            for rp_code in sel.rate_plan_codes:
                pairs.append((sel.room_type_code, rp_code))
    elif request.room_type_codes and request.rate_plan_codes:
        for rt_code in request.room_type_codes:
            for rp_code in request.rate_plan_codes:
                pairs.append((rt_code, rp_code))

    selected_days_set = set(request.selected_days) if request.selected_days else None
    update_fields = set(request.update_fields)

    # Determine which calendar collection to use
    cal_collection = "hr_rate_calendar" if provider_type == "hotelrunner" else "rate_calendar"

    total_room_types_set = set()
    bulk_ops = []
    saved = 0

    for rt_code, rp_code in pairs:
        total_room_types_set.add(rt_code)
        rv = per_room_map.get(rt_code)

        v_rate = rv.rate if rv else request.rate
        v_avail = rv.availability if rv else request.availability
        v_min = rv.min_stay if rv else request.min_stay
        v_max = rv.max_stay if rv else request.max_stay
        v_stop = rv.stop_sell if rv else request.stop_sell
        v_cta = rv.cta if rv else request.cta
        v_ctd = rv.ctd if rv else request.ctd

        d = datetime.strptime(request.start_date, "%Y-%m-%d").date()
        end = datetime.strptime(request.end_date, "%Y-%m-%d").date()

        while d <= end:
            js_dow = d.isoweekday() % 7
            if selected_days_set is not None and js_dow not in selected_days_set:
                d += timedelta(days=1)
                continue

            ds = d.strftime("%Y-%m-%d")
            set_fields = {
                "tenant_id": tenant_id,
                "room_type_code": rt_code,
                "rate_plan_code": rp_code,
                "date": ds,
                "updated_at": now,
                "updated_by": current_user.id,
            }

            if "rate" in update_fields and v_rate is not None:
                set_fields["rate"] = v_rate
            if "availability" in update_fields and v_avail is not None:
                set_fields["availability"] = v_avail
            if "min_stay" in update_fields and v_min is not None:
                set_fields["min_stay"] = v_min
            if "max_stay" in update_fields and v_max is not None:
                set_fields["max_stay"] = v_max
            if "stop_sell" in update_fields and v_stop is not None:
                set_fields["stop_sell"] = v_stop
            if "cta" in update_fields and v_cta is not None:
                set_fields["cta"] = v_cta
            if "ctd" in update_fields and v_ctd is not None:
                set_fields["ctd"] = v_ctd

            bulk_ops.append(
                UpdateOne(
                    {"tenant_id": tenant_id, "room_type_code": rt_code, "rate_plan_code": rp_code, "date": ds},
                    {"$set": set_fields},
                    upsert=True,
                )
            )
            saved += 1
            d += timedelta(days=1)

    # Save to main rate calendar
    if bulk_ops:
        await db[cal_collection].bulk_write(bulk_ops, ordered=False)

    # Push to every resolved channel provider (background)
    channel_push_count = 0
    provider_delivery_results: list[dict] = []
    for tgt in targets:
        try:
            if tgt["provider"] == "hotelrunner":
                cnt = await _push_to_hotelrunner(
                    tenant_id,
                    request,
                    pairs,
                    per_room_map,
                    update_fields,
                    selected_days_set,
                )
                delivery_state = "SCHEDULED" if cnt else "NOT_SENT"
            else:
                cnt = await _push_to_exely(
                    tenant_id,
                    tgt["connection"],
                    request,
                    pairs,
                    per_room_map,
                    update_fields,
                    selected_days_set,
                )
                delivery_state = "QUEUED" if cnt else "NOT_SENT"
            channel_push_count += cnt or 0
            provider_delivery_results.append(
                {
                    "provider": tgt["provider"],
                    "delivery_state": delivery_state,
                    "task_count": cnt or 0,
                }
            )
        except Exception as e:
            logger.error("[UNIFIED] %s push exception_class=%s", tgt["provider"], type(e).__name__)
            provider_delivery_results.append(
                {
                    "provider": tgt["provider"],
                    "delivery_state": "NOT_SENT",
                    "task_count": 0,
                }
            )

    # Push to agencies (background)
    agency_push_count = 0
    if request.agency_ids:
        agency_push_count = await _push_to_agencies(
            tenant_id,
            request.agency_ids,
            pairs,
            per_room_map,
            request,
            update_fields,
            selected_days_set,
            now,
            current_user.id,
        )

    msg = f"{saved} kayit guncellendi"
    if channel_push_count > 0:
        msg += ", kanal teslimati kuyruga alindi; provider sonucu henuz dogrulanmadi"
    else:
        msg += ", provider teslimati baslatilmadi"
    if agency_push_count > 0:
        msg += f", {agency_push_count} acenteye fiyat iletildi"

    delivery_summary = _provider_delivery_summary(provider_delivery_results)
    return {
        "saved": saved,
        "provider": provider_type,
        "channel_push_count": channel_push_count,
        "provider_delivery": provider_delivery_results,
        **delivery_summary,
        "agency_push_count": agency_push_count,
        "total_room_types": len(total_room_types_set),
        "message": msg,
    }


async def _push_to_hotelrunner(tenant_id, request, pairs, per_room_map, update_fields, selected_days_set):
    """HotelRunner'a arka planda push gonder."""
    try:
        from domains.channel_manager.providers.hotelrunner.factory import get_provider as _get_provider

        logger.info("[UNIFIED] HR delivery preparation started")
        provider, conn = await _get_provider(tenant_id)
        if not provider:
            logger.warning("[UNIFIED] HR provider unavailable")
            return 0
        logger.info("[UNIFIED] HR provider alindi, environment=%s", conn.get("environment", "?"))
    except Exception as e:
        logger.error("[UNIFIED] HR provider creation failed: %s", type(e).__name__)
        return 0

    cached_rooms = conn.get("cached_rooms", [])
    pms_to_inv = {}
    for cr in cached_rooms:
        pms_code = cr.get("pms_code", "")
        inv = cr.get("inv_code", "")
        if pms_code and inv:
            pms_to_inv[pms_code] = inv
    logger.info("[UNIFIED] HR room mappings loaded: count=%d", len(pms_to_inv))

    from domains.channel_manager.hr_push_queue_worker import enqueue_failed_push, schedule_auto_retry
    from domains.channel_manager.hr_rate_manager_router import _push_with_retry

    pushed_room_types = set()
    push_tasks = []

    for rt_code, _ in pairs:
        if rt_code in pushed_room_types:
            continue
        pushed_room_types.add(rt_code)

        hr_inv_code = pms_to_inv.get(rt_code, rt_code)

        rv = per_room_map.get(rt_code)
        push_rate = (rv.rate if rv else request.rate) if "rate" in update_fields else None
        push_avail = (rv.availability if rv else request.availability) if "availability" in update_fields else None
        push_stop = (rv.stop_sell if rv else request.stop_sell) if "stop_sell" in update_fields else None
        push_min = (rv.min_stay if rv else request.min_stay) if "min_stay" in update_fields else None
        push_max = (rv.max_stay if rv else request.max_stay) if "max_stay" in update_fields else None
        push_cta = (rv.cta if rv else request.cta) if "cta" in update_fields else None
        push_ctd = (rv.ctd if rv else request.ctd) if "ctd" in update_fields else None

        push_tasks.append(
            {
                "rt": hr_inv_code,
                "pms_rt": rt_code,
                "rate": push_rate,
                "avail": push_avail,
                "stop": push_stop,
                "minstay": push_min,
                "maxstay": push_max,
                "cta": push_cta,
                "ctd": push_ctd,
                "start_date": request.start_date,
                "end_date": request.end_date,
                "days": sorted(selected_days_set) if selected_days_set else None,
            }
        )

    if push_tasks:

        async def _single_push(t, prov, tenant):
            try:
                logger.info("[UNIFIED] HR delivery started")
                result = await _push_with_retry(
                    prov,
                    tenant,
                    t["rt"],
                    t["start_date"],
                    t["end_date"],
                    rate=t["rate"],
                    avail=t["avail"],
                    stop=t["stop"],
                    minstay=t["minstay"],
                    maxstay=t["maxstay"],
                    cta=t["cta"],
                    ctd=t["ctd"],
                    days=t["days"],
                )
                logger.info(
                    "[UNIFIED] HR delivery finished: state=%s",
                    result.get("delivery_state", "unknown"),
                )
                return t, result
            except Exception as e:
                logger.error("[UNIFIED] HR delivery failed: %s", type(e).__name__)
                return t, {
                    "success": False,
                    "error": f"ARI_DELIVERY_{type(e).__name__.upper()}",
                    "delivery_state": "ambiguous",
                }

        async def _bg(tasks, prov, t_id):
            logger.info("[UNIFIED] HR background delivery starting: tasks=%d", len(tasks))
            for index, task in enumerate(tasks):
                _, result = await _single_push(task, prov, t_id)
                if result.get("success"):
                    continue
                if result.get("provider_status_class") == "RATE_LIMITED":
                    retry_after = result.get("retry_after_seconds", 65)
                    for remaining in tasks[index:]:
                        await enqueue_failed_push(
                            t_id,
                            remaining["rt"],
                            remaining["start_date"],
                            remaining["end_date"],
                            rate=remaining["rate"],
                            avail=remaining["avail"],
                            stop=remaining["stop"],
                            minstay=remaining["minstay"],
                            maxstay=remaining["maxstay"],
                            cta=remaining["cta"],
                            ctd=remaining["ctd"],
                            days=remaining.get("days"),
                            error=result.get("error", ""),
                            retry_after_seconds=retry_after,
                        )
                    await schedule_auto_retry(t_id, retry_after + 5)
                break
            logger.info("[UNIFIED] HR background push tamamlandi")

        asyncio.create_task(_bg(push_tasks, provider, tenant_id))

    return len(push_tasks)


async def _push_to_exely(tenant_id, conn, request, pairs, per_room_map, update_fields, selected_days_set):
    """Queue Exely changes through the canonical durable ARI outbox.

    Frontend grid'i HotelRunner tabanli oda kodlari (HR:xxx) ile geliyor.
    Exely'nin kendi room_code + rate_plan_code'larina ceviriyoruz:
      HR:xxx -> hotelrunner_room_mappings.pms_room_type_name -> exely_room_mappings.exely_room_code
      rate_plan -> Exely connection'daki rate_plans listesi.
    """
    del selected_days_set
    hotel_code = str(conn.get("hotel_code") or "")
    if not hotel_code:
        logger.warning("[UNIFIED] Exely mapping_state=missing mapping_type=property")
        return 0
    from domains.channel_manager.providers.exely.ari_publish import enqueue_exely_ari_update

    # ── HR room code (HR:xxx / xxx) -> pms_room_type -> exely_room_code ──
    # Birincil kaynak: HotelRunner connection.cached_rooms
    hr_to_pms: dict[str, str] = {}
    try:
        hr_conn = await db.hotelrunner_connections.find_one(
            {"tenant_id": tenant_id},
            {"_id": 0, "cached_rooms": 1},
        )
        if hr_conn:
            for cr in hr_conn.get("cached_rooms") or []:
                inv = cr.get("inv_code") or ""
                pms = cr.get("pms_code") or ""
                if not inv or not pms:
                    continue
                # Hem "HR:1271568" hem "1271568" formatlarini kaydet
                hr_to_pms[inv] = pms
                if inv.startswith("HR:"):
                    hr_to_pms[inv.split(":", 1)[1]] = pms
    except Exception as exc:
        logger.warning("[UNIFIED] Exely room_cache_read_failed exception_class=%s", type(exc).__name__)

    # Fallback: birlesik room_mappings (provider=hotelrunner)
    rt_codes_norm = sorted({rt for rt, _ in pairs} | {rt.split(":", 1)[1] for rt, _ in pairs if rt.startswith("HR:")})
    missing = [c for c in rt_codes_norm if c not in hr_to_pms]
    if missing:
        rm = await db.room_mappings.find(
            {"tenant_id": tenant_id, "provider": "hotelrunner", "provider_room_code": {"$in": missing}, "is_active": True},
            {"_id": 0, "provider_room_code": 1, "pms_room_type_name": 1, "pms_room_type_id": 1},
        ).to_list(200)
        for m in rm:
            pms_name = m.get("pms_room_type_name") or m.get("pms_room_type_id")
            code = m.get("provider_room_code")
            if pms_name and code and code not in hr_to_pms:
                hr_to_pms[code] = pms_name

    pms_types = sorted(set(hr_to_pms.values()))
    pms_to_exely_codes: dict[str, list[str]] = {}
    # 1) Birincil: exely_room_mappings (legacy/exely_router seması)
    exely_mappings = await db.exely_room_mappings.find(
        {"tenant_id": tenant_id, "pms_room_type": {"$in": pms_types}},
        {"_id": 0, "pms_room_type": 1, "exely_room_code": 1},
    ).to_list(200)
    for m in exely_mappings:
        rc = m.get("exely_room_code", "")
        pt = m.get("pms_room_type", "")
        if rc and pt:
            pms_to_exely_codes.setdefault(pt, []).append(rc)
    # 2) Birlesik room_mappings (provider=exely): provider_room_id -> Exely API kodu
    rm_exely = await db.room_mappings.find(
        {"tenant_id": tenant_id, "provider": "exely", "provider_room_code": {"$in": pms_types}, "is_active": True},
        {"_id": 0, "provider_room_code": 1, "provider_room_id": 1},
    ).to_list(200)
    for m in rm_exely:
        ex_code = m.get("provider_room_id") or m.get("provider_room_code")
        pt = m.get("provider_room_code", "")
        if ex_code and pt and ex_code not in pms_to_exely_codes.get(pt, []):
            pms_to_exely_codes.setdefault(pt, []).append(ex_code)

    # Exely connection'in kendi room_code'lari (Exely sekmesinden gelen pair'lar zaten bu formatta)
    native_exely_codes: set[str] = set()
    for rt in conn.get("room_types") or []:
        c = rt.get("code")
        if c:
            native_exely_codes.add(str(c))
    for codes in pms_to_exely_codes.values():
        for c in codes:
            native_exely_codes.add(str(c))

    # Frontend hangi rate plan'lari sectiyse onlari kullan (Exely sekmesinden geldigi icin
    # rate_plan_code zaten Exely plan ID'si). Liste bossa connection'daki tum planlara fallback.
    selected_exely_plans = sorted({rp_code for _, rp_code in pairs if rp_code})
    conn_exely_plans = [rp.get("code") for rp in (conn.get("rate_plans") or []) if rp.get("code")]
    valid_plan_set = {str(p) for p in conn_exely_plans}
    if valid_plan_set and selected_exely_plans:
        # Sadece Exely connection'da bilinen plan id'lerini kullan
        filtered = [p for p in selected_exely_plans if str(p) in valid_plan_set]
        if not filtered:
            logger.warning("[UNIFIED] Exely mapping_state=missing mapping_type=rate_plan")
            return 0
        exely_rate_plans = filtered
    else:
        exely_rate_plans = conn_exely_plans

    if not exely_rate_plans:
        logger.warning("[UNIFIED] Exely mapping_state=missing mapping_type=rate_plan")
        return 0

    logger.info(
        "[UNIFIED] Exely mapping_state=ready room_mapping_count=%d rate_plan_count=%d",
        len(pms_to_exely_codes),
        len(exely_rate_plans),
    )

    # rt_code -> liste[Exely room code] cevirisini yap (HR akisi VEYA dogrudan Exely akisi)
    seen_exely_for_rt: dict[str, list[str]] = {}
    for rt_code, _rp_code_ignored in pairs:
        if rt_code in seen_exely_for_rt:
            continue
        rt_str = str(rt_code)
        # 1) Dogrudan Exely kodu mu? (Exely sekmesinden gelen kayit)
        if rt_str in native_exely_codes:
            seen_exely_for_rt[rt_code] = [rt_str]
            continue
        # 2) HR akisi: HR:xxx / xxx -> PMS -> Exely
        hr_only = rt_str.split(":", 1)[1] if rt_str.startswith("HR:") else rt_str
        pms_type = hr_to_pms.get(hr_only)
        if not pms_type:
            logger.warning("[UNIFIED] Exely mapping_state=missing mapping_type=room")
            continue
        exely_codes = pms_to_exely_codes.get(pms_type) or []
        if not exely_codes:
            logger.warning("[UNIFIED] Exely mapping_state=missing mapping_type=provider_room")
            continue
        seen_exely_for_rt[rt_code] = exely_codes

    push_tasks = []
    _cur_code, _ = await get_tenant_currency(tenant_id)
    push_currency = conn.get("currency") or _cur_code
    for rt_code, _rp_code_ignored in pairs:
        exely_codes = seen_exely_for_rt.get(rt_code)
        if not exely_codes:
            continue

        rv = per_room_map.get(rt_code)
        push_rate = (rv.rate if rv else request.rate) if "rate" in update_fields else None
        push_avail = (rv.availability if rv else request.availability) if "availability" in update_fields else None
        push_stop = (rv.stop_sell if rv else request.stop_sell) if "stop_sell" in update_fields else None
        push_min = (rv.min_stay if rv else request.min_stay) if "min_stay" in update_fields else None
        push_max = (rv.max_stay if rv else request.max_stay) if "max_stay" in update_fields else None
        push_cta = (rv.cta if rv else request.cta) if "cta" in update_fields else None
        push_ctd = (rv.ctd if rv else request.ctd) if "ctd" in update_fields else None

        for ex_code in exely_codes:
            for rp in exely_rate_plans:

                async def _push(
                    rt=ex_code,
                    rp=rp,
                    rate=push_rate,
                    avail=push_avail,
                    stop=push_stop,
                    minstay=push_min,
                    maxstay=push_max,
                    cta=push_cta,
                    ctd=push_ctd,
                    cur=push_currency,
                ):
                    try:
                        result = await enqueue_exely_ari_update(
                            tenant_id,
                            hotel_code,
                            room_type_code=rt,
                            rate_plan_code=rp,
                            start_date=request.start_date,
                            end_date=request.end_date,
                            source_service="unified_rate_manager",
                            availability=avail,
                            rate_amount=rate,
                            currency=cur,
                            stop_sell=stop,
                            min_los=minstay,
                            max_los=maxstay,
                            cta=cta,
                            ctd=ctd,
                        )
                        logger.info(
                            "[UNIFIED] Exely delivery_state=%s queued_operation_count=%d",
                            result["delivery_state"],
                            result["queued_operation_count"],
                        )
                        return result
                    except Exception as exc:
                        logger.error("[UNIFIED] Exely queue_failed exception_class=%s", type(exc).__name__)

                push_tasks.append(_push())

    if push_tasks:
        results = await asyncio.gather(*push_tasks, return_exceptions=True)
        failures = sum(1 for result in results if isinstance(result, Exception) or result is None)
        if failures:
            logger.error("[UNIFIED] Exely queue_failed count=%d", failures)
        logger.info("[UNIFIED] Exely durable queue completed: %d tasks", len(results))
        return sum(int(result.get("queued_operation_count", 0)) for result in results if isinstance(result, dict) and result.get("accepted") is True)

    return 0


async def _push_to_agencies(tenant_id, agency_ids, pairs, per_room_map, request, update_fields, selected_days_set, now, user_id):
    """Secilen acentelere fiyat/musaitlik bilgisi kaydet."""
    if not agency_ids:
        return 0

    # Verify agencies exist and are active
    agencies = await db.agencies.find(
        {"tenant_id": tenant_id, "id": {"$in": agency_ids}, "status": "active"},
        {"_id": 0, "id": 1, "name": 1},
    ).to_list(100)

    if not agencies:
        return 0

    valid_agency_ids = [a["id"] for a in agencies]

    # Check for agency-specific rate overrides
    overrides = await db.agency_rate_overrides.find(
        {"tenant_id": tenant_id, "agency_id": {"$in": valid_agency_ids}},
        {"_id": 0},
    ).to_list(1000)

    override_map = {}
    for o in overrides:
        key = f"{o['agency_id']}|{o.get('room_type_code', '*')}"
        override_map[key] = o

    bulk_ops = []
    for agency_id in valid_agency_ids:
        for rt_code, rp_code in pairs:
            rv = per_room_map.get(rt_code)
            v_rate = rv.rate if rv else request.rate
            v_avail = rv.availability if rv else request.availability
            v_min = rv.min_stay if rv else request.min_stay
            v_stop = rv.stop_sell if rv else request.stop_sell

            # Apply agency override if exists
            override_key = f"{agency_id}|{rt_code}"
            override_any = f"{agency_id}|*"
            override = override_map.get(override_key) or override_map.get(override_any)

            if override and v_rate is not None and "rate" in update_fields:
                if override.get("fixed_rate") is not None:
                    v_rate = override["fixed_rate"]
                elif override.get("rate_multiplier") is not None:
                    v_rate = round(v_rate * override["rate_multiplier"], 2)

            d = datetime.strptime(request.start_date, "%Y-%m-%d").date()
            end = datetime.strptime(request.end_date, "%Y-%m-%d").date()

            while d <= end:
                js_dow = d.isoweekday() % 7
                if selected_days_set is not None and js_dow not in selected_days_set:
                    d += timedelta(days=1)
                    continue

                ds = d.strftime("%Y-%m-%d")
                set_fields = {
                    "tenant_id": tenant_id,
                    "agency_id": agency_id,
                    "room_type_code": rt_code,
                    "rate_plan_code": rp_code,
                    "date": ds,
                    "updated_at": now,
                    "updated_by": user_id,
                }

                if "rate" in update_fields and v_rate is not None:
                    set_fields["rate"] = v_rate
                if "availability" in update_fields and v_avail is not None:
                    set_fields["availability"] = v_avail
                if "min_stay" in update_fields and v_min is not None:
                    set_fields["min_stay"] = v_min
                if "stop_sell" in update_fields and v_stop is not None:
                    set_fields["stop_sell"] = v_stop

                bulk_ops.append(
                    UpdateOne(
                        {"tenant_id": tenant_id, "agency_id": agency_id, "room_type_code": rt_code, "rate_plan_code": rp_code, "date": ds},
                        {"$set": set_fields},
                        upsert=True,
                    )
                )
                d += timedelta(days=1)

    if bulk_ops:
        await db.agency_rate_calendar.bulk_write(bulk_ops, ordered=False)

    # Notify subscribed agency webhooks (rates.updated / availability.updated)
    # so external programs (e.g. Syroce Agency) can invalidate their cache
    # instead of polling. Best-effort; webhook_retry_service handles DLQ.
    try:
        from routers.webhook_retry_service import fire_webhooks_with_retry

        events_to_fire = []
        if "rate" in update_fields:
            events_to_fire.append("rates.updated")
        if "availability" in update_fields or "stop_sell" in update_fields:
            events_to_fire.append("availability.updated")
        if events_to_fire:
            payload_base = {
                "tenant_id": tenant_id,
                "date_range": {"start": request.start_date, "end": request.end_date},
                "room_type_codes": sorted({rt for rt, _ in pairs}),
                "rate_plan_codes": sorted({rp for _, rp in pairs}),
                "fields_changed": sorted(update_fields),
                "updated_at": now,
            }
            for agency_id in valid_agency_ids:
                payload = dict(payload_base, agency_id=agency_id)
                for ev in events_to_fire:
                    asyncio.create_task(fire_webhooks_with_retry(tenant_id, agency_id, ev, payload))
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("agency rates webhook dispatch failed: %s", exc)

    # Bust agency list cache so urm UI sees fresh last_rate_push timestamps
    try:
        from cache_manager import cache as _cache

        _cache.invalidate_tenant_cache(tenant_id, "urm_agencies")
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug("urm_agencies cache invalidate skipped: %s", exc)

    return len(valid_agency_ids)


# ── Agency Endpoints ─────────────────────────────────────────────


@router.get("/agencies")
@cached(ttl=300, key_prefix="urm_agencies")  # 5dk cache (Tur 2 fix)
async def list_agencies_for_rates(current_user: User = Depends(get_current_user)):
    """Fiyat iletilecek aktif acenteleri listele."""
    tenant_id = current_user.tenant_id

    agencies = await db.agencies.find(
        {"tenant_id": tenant_id, "status": "active"},
        {"_id": 0, "id": 1, "name": 1, "contact_name": 1, "commission_rate": 1},
    ).to_list(200)

    # Get override counts per agency
    for agency in agencies:
        override_count = await db.agency_rate_overrides.count_documents({"tenant_id": tenant_id, "agency_id": agency["id"]})
        agency["has_custom_rates"] = override_count > 0
        agency["override_count"] = override_count

        # Last rate push date
        last_push = await db.agency_rate_calendar.find_one(
            {"tenant_id": tenant_id, "agency_id": agency["id"]},
            {"_id": 0, "updated_at": 1},
            sort=[("updated_at", -1)],
        )
        agency["last_rate_push"] = last_push.get("updated_at") if last_push else None

    return {"agencies": agencies}


@router.get("/agency-rates/{agency_id}")
async def get_agency_rate_overrides(
    agency_id: str,
    current_user: User = Depends(get_current_user),
):
    """Acente bazli ozel fiyat tanimlarini getir."""
    tenant_id = current_user.tenant_id

    overrides = await db.agency_rate_overrides.find(
        {"tenant_id": tenant_id, "agency_id": agency_id},
        {"_id": 0},
    ).to_list(200)

    return {"agency_id": agency_id, "overrides": overrides}


@router.post("/agency-rates")
async def set_agency_rate_overrides(
    request: AgencyRateOverrideRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v101 DW
):
    """Acente bazli ozel fiyat tanimla."""
    tenant_id = current_user.tenant_id
    now = datetime.now(UTC).isoformat()
    saved = 0

    for override in request.overrides:
        doc = {
            "tenant_id": tenant_id,
            "agency_id": override.agency_id,
            "room_type_code": override.room_type_code,
            "rate_plan_code": override.rate_plan_code or "*",
            "updated_at": now,
            "updated_by": current_user.id,
        }
        if override.rate_multiplier is not None:
            doc["rate_multiplier"] = override.rate_multiplier
        if override.fixed_rate is not None:
            doc["fixed_rate"] = override.fixed_rate
        if override.start_date:
            doc["start_date"] = override.start_date
        if override.end_date:
            doc["end_date"] = override.end_date

        await db.agency_rate_overrides.update_one(
            {
                "tenant_id": tenant_id,
                "agency_id": override.agency_id,
                "room_type_code": override.room_type_code,
                "rate_plan_code": override.rate_plan_code or "*",
            },
            {"$set": doc},
            upsert=True,
        )
        saved += 1

    return {"saved": saved, "message": f"{saved} acente fiyat tanimi kaydedildi"}


@router.delete("/agency-rates/{agency_id}")
async def delete_agency_rate_overrides(
    agency_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v101 DW
):
    """Acentenin tum ozel fiyat tanimlarini sil."""
    tenant_id = current_user.tenant_id
    result = await db.agency_rate_overrides.delete_many({"tenant_id": tenant_id, "agency_id": agency_id})
    return {"deleted": result.deleted_count, "message": f"{result.deleted_count} fiyat tanimi silindi"}


# ── Push Providers ───────────────────────────────────────────────


@router.get("/push-providers")
async def get_push_providers(current_user: User = Depends(get_current_user)):
    """Aktif push saglayicilarini dondurur."""
    tenant_id = current_user.tenant_id
    providers = []

    hr_conn = await db.hotelrunner_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0})
    exely_conn = await db.exely_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True},
        exely_connection_projection(),
    )

    hr_flags = await db.connector_flags.find_one({"tenant_id": tenant_id, "provider": "hotelrunner"}, {"_id": 0})
    ex_flags = await db.connector_flags.find_one({"tenant_id": tenant_id, "provider": "exely"}, {"_id": 0})

    def _derive_mode(flags, conn_doc):
        if flags:
            if not flags.get("connector_enabled", False):
                return "inactive"
            shadow = flags.get("shadow_mode", True)
            write = flags.get("write_enabled", False) and not shadow
            return "shadow" if shadow else ("live" if write else "read_only")
        return conn_doc.get("push_mode", "shadow")

    # Otel icin super_admin bir altyapi sectiyse YALNIZCA o listelenir
    # ("otel basina tek saglayici"); secim yoksa (configured=None) eski liste
    # aynen korunur (pilot_drift=0). Syroce B2B her zaman ayri eklenir.
    configured = await _tenant_configured_provider(tenant_id)

    if hr_conn and configured in (None, "hotelrunner"):
        hr_mode = _derive_mode(hr_flags, hr_conn)
        if hr_mode != "inactive":
            providers.append({"slug": "hotelrunner", "name": "HotelRunner", "mode": hr_mode})

    if exely_conn and configured in (None, "exely"):
        ex_mode = _derive_mode(ex_flags, exely_conn)
        if ex_mode != "inactive":
            providers.append({"slug": "exely", "name": "Exely", "mode": ex_mode})

    # Syroce B2B provider — aktif acente varsa ekle
    active_agency_count = await db.agencies.count_documents({"tenant_id": tenant_id, "status": "active"})
    if active_agency_count > 0:
        api_key_count = await db.agency_api_keys.count_documents({"tenant_id": tenant_id, "is_active": True})
        providers.append(
            {
                "slug": "syroce_b2b",
                "name": "Syroce B2B",
                "mode": "live",
                "agency_count": active_agency_count,
                "api_key_count": api_key_count,
            }
        )

    return {"providers": providers}


# ── Pricing Settings ─────────────────────────────────────────────


@router.get("/pricing-settings")
async def get_pricing_settings(current_user: User = Depends(get_current_user)):
    tenant_id = current_user.tenant_id
    detection = await _detect_active_provider(tenant_id)

    # Fail-closed: secili saglayici yapilandirilmis ama aktif baglantisi yok ->
    # yanlis (digerine ait) yerel koleksiyona DUSME, bos don. configured=None
    # (legacy) tenant'larda configuration_error olusmaz -> eski davranis korunur.
    if detection.get("configuration_error"):
        return {"settings": {}, "rules": {}}

    if detection["provider"] == "hotelrunner":
        docs = await db.hr_pricing_settings.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(200)
    else:
        docs = await db.pricing_settings.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(200)

    settings, rules = _pricing_payload(docs)
    rules = await _add_pms_rule_aliases(tenant_id, detection["provider"], rules)
    return {"settings": settings, "rules": rules}


@router.put("/pricing-settings")
async def update_pricing_settings(
    request: PricingSettingsRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
):
    tenant_id = current_user.tenant_id
    detection = await _detect_active_provider(tenant_id)

    # Fail-closed: secili saglayicinin aktif baglantisi yoksa yanlis (digerine
    # ait) yerel koleksiyona YAZMA. configured=None (legacy) -> eski davranis.
    if detection.get("configuration_error"):
        raise HTTPException(status_code=409, detail="Secili kanal saglayicinin aktif baglantisi yok")

    now = datetime.now(UTC).isoformat()
    updated = 0

    collection = "hr_pricing_settings" if detection["provider"] == "hotelrunner" else "pricing_settings"

    for item in request.settings:
        try:
            rule = normalize_occupancy_rule(item.model_dump())
        except OccupancyPricingError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await db[collection].update_one(
            {"tenant_id": tenant_id, "room_type_code": item.room_type_code},
            {
                "$set": {
                    "tenant_id": tenant_id,
                    "room_type_code": item.room_type_code,
                    **rule,
                    "updated_at": now,
                    "updated_by": current_user.id,
                }
            },
            upsert=True,
        )
        updated += 1

    return {"updated": updated, "message": f"{updated} fiyatlandirma ayari guncellendi"}


@router.post("/occupancy-price-preview")
async def preview_occupancy_price(
    request: OccupancyPricePreviewRequest,
    current_user: User = Depends(get_current_user),
):
    """Calculate a read-only PMS quote from the stored occupancy rule."""

    tenant_id = current_user.tenant_id
    detection = await _detect_active_provider(tenant_id)
    if detection.get("configuration_error"):
        raise HTTPException(status_code=409, detail="Secili kanal saglayicinin aktif baglantisi yok")
    collection = "hr_pricing_settings" if detection["provider"] == "hotelrunner" else "pricing_settings"
    rule = await db[collection].find_one(
        {"tenant_id": tenant_id, "room_type_code": request.room_type_code},
        {"_id": 0},
    )
    if not rule:
        raise HTTPException(status_code=404, detail="Bu oda tipi icin kisi fiyatlandirma kurali bulunamadi")
    try:
        return calculate_occupancy_quote(
            base_nightly_rate=request.base_nightly_rate,
            nights=request.nights,
            adults=request.adults,
            children_ages=request.children_ages,
            rule=rule,
        )
    except OccupancyPricingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── Stop Sale Summary ────────────────────────────────────────────


@router.get("/circuit-breakers")
async def get_circuit_breakers(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """Return per-provider circuit breaker status, scoped to this tenant.

    Strict tenant scope: only breaker keys prefixed with this tenant's id
    (`hotelrunner:{tenant_id}:...` / `exely:{tenant_id}:...`) are aggregated.
    Foreign tenants' breaker keys and identifiers are NEVER returned, even
    in the same process — prevents cross-tenant observability leakage.

    Severity rule: per provider, the worst state across this tenant's
    breakers wins (OPEN > HALF_OPEN > CLOSED). When no breaker has been
    touched yet for a provider, defaults to CLOSED with failure_count=0.
    `connection_id` in the response strips the tenant prefix to avoid
    leaking the full key shape.
    """
    from domains.channel_manager.provider_failover import CircuitState, provider_failover

    tenant_id = current_user.tenant_id
    raw = await provider_failover.get_all_status_shared()

    severity = {
        CircuitState.CLOSED.value: 0,
        CircuitState.HALF_OPEN.value: 1,
        CircuitState.OPEN.value: 2,
    }
    by_provider: dict[str, dict] = {}
    for entry in raw:
        key = entry.get("provider", "")
        if ":" not in key:
            continue
        provider_name, conn_id = key.split(":", 1)
        if provider_name not in ("hotelrunner", "exely"):
            continue
        # Tenant scope: conn_id MUST start with current tenant's id.
        # Legacy `_default` keys (no tenant prefix) are always excluded
        # from per-tenant views.
        if not conn_id.startswith(f"{tenant_id}:"):
            continue
        local_conn_suffix = conn_id[len(tenant_id) + 1 :]
        cur = by_provider.get(provider_name)
        if cur is None or severity.get(entry["state"], 0) > severity.get(cur["state"], 0):
            by_provider[provider_name] = {
                "provider": provider_name,
                "state": entry["state"],
                "failure_count": entry["failure_count"],
                "failure_threshold": entry["failure_threshold"],
                "recovery_timeout": entry["recovery_timeout"],
                "last_failure": entry["last_failure"],
                "connection_id": local_conn_suffix,
            }

    for p in ("hotelrunner", "exely"):
        by_provider.setdefault(
            p,
            {
                "provider": p,
                "state": CircuitState.CLOSED.value,
                "failure_count": 0,
                "failure_threshold": 5,
                "recovery_timeout": 60,
                "last_failure": None,
                "connection_id": "",
            },
        )

    return {"breakers": list(by_provider.values())}


@router.get("/stop-sale-summary")
async def get_stop_sale_summary(
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: User = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id
    if not start_date:
        start_date = datetime.now(UTC).date().isoformat()
    if not end_date:
        end_date = (datetime.now(UTC) + timedelta(days=14)).date().isoformat()
    detection = await _detect_active_provider(tenant_id)

    # Fail-closed: secili saglayicinin aktif baglantisi yoksa yanlis (digerine
    # ait) yerel takvimi OKUMA, bos don. configured=None (legacy) -> eski davranis.
    if detection.get("configuration_error"):
        return {"stops": []}

    cal_collection = "hr_rate_calendar" if detection["provider"] == "hotelrunner" else "rate_calendar"

    pipeline = [
        {"$match": {"tenant_id": tenant_id, "date": {"$gte": start_date, "$lte": end_date}, "stop_sell": True}},
        {"$group": {"_id": "$room_type_code", "dates": {"$addToSet": "$date"}, "count": {"$sum": 1}}},
    ]
    results = await db[cal_collection].aggregate(pipeline).to_list(500)

    conn = detection.get("connection")
    rt_map = {}
    if conn and detection["provider"] == "hotelrunner":
        for room in conn.get("cached_rooms", []):
            rt_map[room.get("inv_code", "")] = room.get("name", "")
    elif conn:
        for rt in conn.get("room_types", []):
            rt_map[rt.get("code", "")] = rt.get("name", rt.get("code", ""))

    stops = []
    for r in results:
        code = r["_id"]
        stops.append(
            {
                "room_type_code": code,
                "room_type_name": rt_map.get(code, code),
                "dates": sorted(r["dates"]),
                "count": r["count"],
            }
        )

    return {"stops": stops}


# ── Stop Sale Schedules (CRUD) ───────────────────────────────────


class StopSaleScheduleCreate(BaseModel):
    name: str
    holiday_key: str | None = None
    start_date: str
    end_date: str
    room_type_codes: list[str] = []
    auto_apply: bool = False


class StopSaleScheduleUpdate(BaseModel):
    name: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    room_type_codes: list[str] | None = None
    auto_apply: bool | None = None


@router.get("/stop-sale-schedules")
async def list_unified_stop_sale_schedules(
    current_user: User = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id
    docs = await db.stop_sale_schedules.find({"tenant_id": tenant_id}, {"_id": 0}).sort("start_date", 1).to_list(200)
    return {"schedules": docs}


@router.post("/stop-sale-schedules")
async def create_unified_stop_sale_schedule(
    request: StopSaleScheduleCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v101 DW
):
    tenant_id = current_user.tenant_id
    now = datetime.now(UTC).isoformat()
    schedule = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "name": request.name,
        "holiday_key": request.holiday_key,
        "start_date": request.start_date,
        "end_date": request.end_date,
        "room_type_codes": request.room_type_codes,
        "auto_apply": request.auto_apply,
        "applied": False,
        "created_at": now,
        "updated_at": now,
        "created_by": current_user.id,
    }
    await db.stop_sale_schedules.insert_one(schedule)
    schedule.pop("_id", None)
    return {"schedule": schedule, "message": "Zamanlayici olusturuldu"}


@router.delete("/stop-sale-schedules/{schedule_id}")
async def delete_unified_stop_sale_schedule(
    schedule_id: str,
    remove_stop_sale: bool = False,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v101 DW
):
    tenant_id = current_user.tenant_id
    result = await db.stop_sale_schedules.delete_one({"tenant_id": tenant_id, "id": schedule_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Zamanlayici bulunamadi")
    return {"message": "Zamanlayici silindi"}


@router.patch("/stop-sale-schedules/{schedule_id}")
async def update_unified_stop_sale_schedule(
    schedule_id: str,
    request: StopSaleScheduleUpdate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v101 DW
):
    tenant_id = current_user.tenant_id
    now = datetime.now(UTC).isoformat()
    update_fields = {"updated_at": now}
    if request.name is not None:
        update_fields["name"] = request.name
    if request.start_date is not None:
        update_fields["start_date"] = request.start_date
    if request.end_date is not None:
        update_fields["end_date"] = request.end_date
    if request.room_type_codes is not None:
        update_fields["room_type_codes"] = request.room_type_codes
    if request.auto_apply is not None:
        update_fields["auto_apply"] = request.auto_apply
    result = await db.stop_sale_schedules.update_one(
        {"tenant_id": tenant_id, "id": schedule_id},
        {"$set": update_fields},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Zamanlayici bulunamadi")
    return {"message": "Zamanlayici guncellendi"}


# ── Holidays ─────────────────────────────────────────────────────


@router.get("/holidays")
async def get_holidays(current_user: User = Depends(get_current_user)):
    """Tatil donemlerini dondurur."""
    # Import from existing router to reuse logic
    from datetime import date

    try:
        from domains.channel_manager.rate_utils import get_holiday_periods as _get_holiday_periods

        now = date.today()
        all_periods = []
        for y in [now.year, now.year + 1]:
            all_periods.extend(_get_holiday_periods(y))
        upcoming = [p for p in all_periods if p["end_date"] >= now.isoformat()]
        return {"holidays": upcoming}
    except Exception:
        return {"holidays": []}
