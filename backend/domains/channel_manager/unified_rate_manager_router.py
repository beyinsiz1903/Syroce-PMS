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
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pymongo import UpdateOne

from core.database import db
from core.security import get_current_user
from models.schemas import User

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


class PricingSettingsRequest(BaseModel):
    settings: list[PricingSettingItem]


# ── Provider Detection ───────────────────────────────────────────

async def _detect_active_provider(tenant_id: str) -> dict:
    """Otelde aktif olan kanal saglayiciyi tespit et."""
    hr_conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
    )
    if not hr_conn:
        pc = await db.provider_connections.find_one(
            {"tenant_id": tenant_id, "provider": "hotelrunner", "status": "active"}
        )
        if pc:
            legacy = await db.hotelrunner_connections.find_one(
                {"tenant_id": tenant_id}, {"_id": 0, "cached_rooms": 1}
            )
            hr_conn = {"tenant_id": tenant_id, "is_active": True,
                        "hr_id": pc.get("credentials", {}).get("hr_id", ""),
                        "environment": pc.get("environment", "live"),
                        "cached_rooms": (legacy or {}).get("cached_rooms", [])}

    exely_conn = await db.exely_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
    )

    if hr_conn and exely_conn:
        return {"provider": "hotelrunner", "connection": hr_conn}

    if hr_conn:
        return {"provider": "hotelrunner", "connection": hr_conn}
    if exely_conn:
        return {"provider": "exely", "connection": exely_conn}

    return {"provider": None, "connection": None}


# ── Detect Provider Endpoint ─────────────────────────────────────

@router.get("/detect-provider")
async def detect_provider(current_user: User = Depends(get_current_user)):
    """Aktif kanal saglayiciyi tespit et."""
    tenant_id = current_user.tenant_id
    result = await _detect_active_provider(tenant_id)

    if not result["provider"]:
        return {
            "provider": None,
            "provider_name": None,
            "has_connection": False,
            "room_count": 0,
        }

    conn = result["connection"]
    if result["provider"] == "hotelrunner":
        room_count = len(conn.get("cached_rooms", []))
        provider_name = "HotelRunner"
    else:
        room_count = len(conn.get("room_types", []))
        provider_name = "Exely"

    return {
        "provider": result["provider"],
        "provider_name": provider_name,
        "has_connection": True,
        "room_count": room_count,
    }


# ── Unified Grid ─────────────────────────────────────────────────

@router.get("/grid")
async def get_unified_grid(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user),
):
    """Aktif saglayicinin takvim grid'ini dondurur."""
    tenant_id = current_user.tenant_id
    detection = await _detect_active_provider(tenant_id)

    if not detection["provider"]:
        return {
            "grid": [], "room_types": [], "rate_plans": [],
            "pricing_settings": {}, "currency": "TRY",
            "start_date": start_date, "end_date": end_date,
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
            "grid": [], "room_types": [], "rate_plans": [],
            "pricing_settings": {}, "currency": "TRY",
            "start_date": start_date, "end_date": end_date,
            "provider": "hotelrunner",
        }

    room_types, rate_plans = _extract_hr_room_types(cached_rooms)

    mappings = await db.hotelrunner_room_mappings.find(
        {"tenant_id": tenant_id}, {"_id": 0}
    ).to_list(100)
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
                start_date, end_date, rt["code"], rp["code"],
                cal_index, pms_type, counts, room_ids_by_type, active_bookings,
            )
            grid.append({
                "room_type_code": rt["code"],
                "room_type_name": rt["name"],
                "rate_plan_code": rp["code"],
                "rate_plan_name": rp["name"],
                "pms_room_type": pms_type or rt["name"],
                "total_rooms": counts["total"],
                "dates": dates_data,
            })

    pricing_docs = await db.hr_pricing_settings.find(
        {"tenant_id": tenant_id}, {"_id": 0}
    ).to_list(200)
    pricing_map = {doc["room_type_code"]: doc.get("pricing_type", "per_person") for doc in pricing_docs}

    currency = cached_rooms[0].get("sales_currency", "TRY") if cached_rooms else "TRY"

    return {
        "grid": grid, "room_types": room_types, "rate_plans": rate_plans,
        "pricing_settings": pricing_map, "currency": currency,
        "start_date": start_date, "end_date": end_date,
        "provider": "hotelrunner",
    }


async def _build_exely_grid(tenant_id, conn, start_date, end_date):
    """Exely grid olustur."""
    room_types = conn.get("room_types", [])
    rate_plans = conn.get("rate_plans", [])

    mappings = await db.exely_room_mappings.find(
        {"tenant_id": tenant_id}, {"_id": 0}
    ).to_list(100)

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
                start_date, end_date, rt["code"], rp["code"],
                cal_index, pms_type or rt["name"], counts, room_ids_by_type, active_bookings,
            )
            grid.append({
                "room_type_code": rt["code"],
                "room_type_name": rt["name"],
                "rate_plan_code": rp["code"],
                "rate_plan_name": rp["name"],
                "pms_room_type": pms_type or rt["name"],
                "total_rooms": counts["total"],
                "dates": dates_data,
            })

    pricing_docs = await db.pricing_settings.find(
        {"tenant_id": tenant_id}, {"_id": 0}
    ).to_list(200)
    pricing_map = {doc["room_type_code"]: doc.get("pricing_type", "per_person") for doc in pricing_docs}

    currency = conn.get("currency", "TRY")

    return {
        "grid": grid, "room_types": room_types, "rate_plans": rate_plans,
        "pricing_settings": pricing_map, "currency": currency,
        "start_date": start_date, "end_date": end_date,
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
    rooms = await db.rooms.find(
        {"tenant_id": tenant_id}, {"_id": 0, "id": 1, "room_type": 1, "status": 1}
    ).to_list(500)
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


def _build_dates(start_date, end_date, rt_code, rp_code,
                 cal_index, pms_type, counts, room_ids_by_type, active_bookings):
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
        dates_data.append({
            "date": ds,
            "rate": entry.get("rate"),
            "availability": real_avail,
            "base_availability": base_avail if base_avail is not None else counts["total"],
            "sold": sold_count,
            "min_stay": entry.get("min_stay", 1),
            "stop_sell": entry.get("stop_sell", False),
        })
        d += timedelta(days=1)
    return dates_data


# ── Room Types ───────────────────────────────────────────────────

@router.get("/room-types")
async def get_unified_room_types(current_user: User = Depends(get_current_user)):
    """Aktif saglayicinin oda tiplerini dondurur."""
    tenant_id = current_user.tenant_id
    detection = await _detect_active_provider(tenant_id)

    if not detection["provider"]:
        return {"room_types": [], "rate_plans": [], "pricing_settings": {}, "provider": None}

    conn = detection["connection"]
    if detection["provider"] == "hotelrunner":
        room_types, rate_plans = _extract_hr_room_types(conn.get("cached_rooms", []))
        pricing_docs = await db.hr_pricing_settings.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(200)
    else:
        room_types = conn.get("room_types", [])
        rate_plans = conn.get("rate_plans", [])
        pricing_docs = await db.pricing_settings.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(200)

    pricing_map = {doc["room_type_code"]: doc.get("pricing_type", "per_person") for doc in pricing_docs}

    return {
        "room_types": room_types,
        "rate_plans": rate_plans,
        "pricing_settings": pricing_map,
        "provider": detection["provider"],
    }


# ── Bulk Grid Update ─────────────────────────────────────────────

@router.post("/bulk-grid-update")
async def unified_bulk_grid_update(
    request: UnifiedBulkUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    """Toplu fiyat/musaitlik guncelle. Kanal saglayiciya + acentelere push."""
    tenant_id = current_user.tenant_id

    if request.provider:
        if request.provider == "hotelrunner":
            conn = await db.hotelrunner_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0})
            if not conn:
                pc = await db.provider_connections.find_one(
                    {"tenant_id": tenant_id, "provider": "hotelrunner", "status": "active"}
                )
                if pc:
                    legacy = await db.hotelrunner_connections.find_one(
                        {"tenant_id": tenant_id}, {"_id": 0, "cached_rooms": 1}
                    )
                    conn = {"tenant_id": tenant_id, "is_active": True,
                            "hr_id": pc.get("credentials", {}).get("hr_id", ""),
                            "environment": pc.get("environment", "live"),
                            "cached_rooms": (legacy or {}).get("cached_rooms", [])}
            detection = {"provider": "hotelrunner", "connection": conn} if conn else {"provider": None, "connection": None}
        elif request.provider == "exely":
            conn = await db.exely_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0})
            detection = {"provider": "exely", "connection": conn} if conn else {"provider": None, "connection": None}
        else:
            detection = await _detect_active_provider(tenant_id)
    else:
        detection = await _detect_active_provider(tenant_id)

    if not detection["provider"]:
        raise HTTPException(status_code=404, detail="Aktif kanal saglayici bulunamadi")

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

            bulk_ops.append(UpdateOne(
                {"tenant_id": tenant_id, "room_type_code": rt_code, "rate_plan_code": rp_code, "date": ds},
                {"$set": set_fields},
                upsert=True,
            ))
            saved += 1
            d += timedelta(days=1)

    # Save to main rate calendar
    if bulk_ops:
        await db[cal_collection].bulk_write(bulk_ops, ordered=False)

    # Push to channel provider (background)
    channel_push_count = 0
    if provider_type == "hotelrunner":
        channel_push_count = await _push_to_hotelrunner(tenant_id, request, pairs, per_room_map, update_fields, selected_days_set)
    else:
        channel_push_count = await _push_to_exely(tenant_id, detection["connection"], request, pairs, per_room_map, update_fields, selected_days_set)

    # Push to agencies (background)
    agency_push_count = 0
    if request.agency_ids:
        agency_push_count = await _push_to_agencies(
            tenant_id, request.agency_ids, pairs, per_room_map,
            request, update_fields, selected_days_set, now, current_user.id,
        )

    msg = f"{saved} kayit guncellendi"
    if channel_push_count > 0:
        provider_name = "HotelRunner" if provider_type == "hotelrunner" else "Exely"
        msg += f", {provider_name}'a push gonderiliyor"
    if agency_push_count > 0:
        msg += f", {agency_push_count} acenteye fiyat iletildi"

    return {
        "saved": saved,
        "provider": provider_type,
        "channel_push_count": channel_push_count,
        "agency_push_count": agency_push_count,
        "total_room_types": len(total_room_types_set),
        "message": msg,
    }


async def _push_to_hotelrunner(tenant_id, request, pairs, per_room_map, update_fields, selected_days_set):
    """HotelRunner'a arka planda push gonder."""
    try:
        from domains.channel_manager.providers.hotelrunner_router import _get_provider
        logger.info("[UNIFIED] HR push baslatiliyor tenant=%s", tenant_id)
        provider, conn = await _get_provider(tenant_id)
        if not provider:
            logger.warning("[UNIFIED] HR provider alinamadi tenant=%s", tenant_id)
            return 0
        logger.info("[UNIFIED] HR provider alindi, environment=%s", conn.get("environment", "?"))
    except Exception as e:
        logger.error("[UNIFIED] HR provider olusturma hatasi tenant=%s: %s", tenant_id, e)
        return 0

    cached_rooms = conn.get("cached_rooms", [])
    pms_to_inv = {}
    for cr in cached_rooms:
        pms_code = cr.get("pms_code", "")
        inv = cr.get("inv_code", "")
        if pms_code and inv:
            pms_to_inv[pms_code] = inv
    logger.info("[UNIFIED] HR room mapping: %s", pms_to_inv)

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

        push_tasks.append({
            "rt": hr_inv_code,
            "pms_rt": rt_code,
            "rate": push_rate, "avail": push_avail,
            "stop": push_stop, "minstay": push_min,
            "start_date": request.start_date, "end_date": request.end_date,
            "days": sorted(selected_days_set) if selected_days_set else None,
        })

    if push_tasks:
        async def _bg(tasks, prov, t_id):
            await asyncio.sleep(0.2)
            logger.info("[UNIFIED] HR background push basliyor, %d oda tipi", len(tasks))
            for i, t in enumerate(tasks):
                try:
                    logger.info("[UNIFIED] HR push: rt=%s tarih=%s→%s rate=%s avail=%s",
                                t["rt"], t["start_date"], t["end_date"], t["rate"], t["avail"])
                    result = await _push_with_retry(
                        prov, t["rt"], t["start_date"], t["end_date"],
                        rate=t["rate"], avail=t["avail"], stop=t["stop"], minstay=t["minstay"], days=t["days"],
                    )
                    logger.info("[UNIFIED] HR push sonucu rt=%s: %s", t["rt"], result)
                    if not result.get("success") and "rate limit" in str(result.get("error", "")).lower():
                        for remaining in tasks[i:]:
                            await enqueue_failed_push(
                                t_id, remaining["rt"], remaining["start_date"], remaining["end_date"],
                                rate=remaining["rate"], avail=remaining["avail"],
                                stop=remaining["stop"], minstay=remaining["minstay"],
                                days=remaining.get("days"), error=result.get("error", ""),
                                retry_after_seconds=result.get("retry_after_seconds", 65),
                            )
                        await schedule_auto_retry(t_id, result.get("retry_after_seconds", 65) + 5)
                        break
                except Exception as e:
                    logger.error("[UNIFIED] HR push hatasi %s: %s", t["rt"], e)
                if i < len(tasks) - 1:
                    await asyncio.sleep(2)
            logger.info("[UNIFIED] HR background push tamamlandi")

        asyncio.create_task(_bg(push_tasks, provider, tenant_id))

    return len(push_tasks)


async def _push_to_exely(tenant_id, conn, request, pairs, per_room_map, update_fields, selected_days_set):
    """Exely'ye arka planda push gonder."""
    try:
        from domains.channel_manager.credential_vault import get_decrypted_credentials
        hotel_code = conn.get("hotel_code", "")
        creds = await get_decrypted_credentials(tenant_id, "exely", hotel_code)
        if not creds:
            creds = {"username": conn.get("username", ""), "password": conn.get("password", "")}
            if not creds.get("username"):
                logger.warning("[UNIFIED] Exely credentials bulunamadi tenant=%s", tenant_id)
                return 0
        logger.info("[UNIFIED] Exely push baslatiliyor tenant=%s hotel_code=%s user=%s",
                    tenant_id, hotel_code, creds.get("username", "?"))
        from domains.channel_manager.providers.exely.provider import ExelyProvider
        kwargs = {"username": creds.get("username", ""), "password": creds.get("password", ""), "hotel_code": hotel_code}
        if conn.get("endpoint_url"):
            kwargs["endpoint_url"] = conn["endpoint_url"]
        provider = ExelyProvider(**kwargs)
    except Exception as e:
        logger.error("[UNIFIED] Exely provider olusturulamadi: %s", e)
        return 0

    push_tasks = []
    for rt_code, rp_code in pairs:
        rv = per_room_map.get(rt_code)
        push_rate = (rv.rate if rv else request.rate) if "rate" in update_fields else None
        push_avail = (rv.availability if rv else request.availability) if "availability" in update_fields else None
        push_stop = (rv.stop_sell if rv else request.stop_sell) if "stop_sell" in update_fields else None
        push_min = (rv.min_stay if rv else request.min_stay) if "min_stay" in update_fields else None

        async def _push(rt=rt_code, rp=rp_code, rate=push_rate, avail=push_avail, stop=push_stop, minstay=push_min):
            try:
                logger.info("[UNIFIED] Exely push: rt=%s rp=%s rate=%s avail=%s", rt, rp, rate, avail)
                result = await provider.push_ari(
                    room_type_code=rt, rate_plan_code=rp,
                    start_date=request.start_date, end_date=request.end_date,
                    availability=avail, rate_amount=rate,
                    currency=conn.get("currency", "TRY"),
                    stop_sell=stop, min_stay=minstay,
                )
                logger.info("[UNIFIED] Exely push sonucu rt=%s: %s", rt, result)
                return result
            except Exception as e:
                logger.error("[UNIFIED] Exely push hatasi rt=%s: %s", rt, e)
        push_tasks.append(_push())

    if push_tasks:
        async def _bg(tasks):
            try:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                logger.info("[UNIFIED] Exely background push tamamlandi: %d gorev", len(results))
            except Exception as e:
                logger.error("[UNIFIED] Exely background push hatasi: %s", e)
        asyncio.create_task(_bg(push_tasks))

    return len(push_tasks)


async def _push_to_agencies(tenant_id, agency_ids, pairs, per_room_map,
                            request, update_fields, selected_days_set, now, user_id):
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

                bulk_ops.append(UpdateOne(
                    {"tenant_id": tenant_id, "agency_id": agency_id,
                     "room_type_code": rt_code, "rate_plan_code": rp_code, "date": ds},
                    {"$set": set_fields},
                    upsert=True,
                ))
                d += timedelta(days=1)

    if bulk_ops:
        await db.agency_rate_calendar.bulk_write(bulk_ops, ordered=False)

    return len(valid_agency_ids)


# ── Agency Endpoints ─────────────────────────────────────────────

@router.get("/agencies")
async def list_agencies_for_rates(current_user: User = Depends(get_current_user)):
    """Fiyat iletilecek aktif acenteleri listele."""
    tenant_id = current_user.tenant_id

    agencies = await db.agencies.find(
        {"tenant_id": tenant_id, "status": "active"},
        {"_id": 0, "id": 1, "name": 1, "contact_name": 1, "commission_rate": 1},
    ).to_list(200)

    # Get override counts per agency
    for agency in agencies:
        override_count = await db.agency_rate_overrides.count_documents(
            {"tenant_id": tenant_id, "agency_id": agency["id"]}
        )
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
):
    """Acentenin tum ozel fiyat tanimlarini sil."""
    tenant_id = current_user.tenant_id
    result = await db.agency_rate_overrides.delete_many(
        {"tenant_id": tenant_id, "agency_id": agency_id}
    )
    return {"deleted": result.deleted_count, "message": f"{result.deleted_count} fiyat tanimi silindi"}


# ── Push Providers ───────────────────────────────────────────────

@router.get("/push-providers")
async def get_push_providers(current_user: User = Depends(get_current_user)):
    """Aktif push saglayicilarini dondurur."""
    tenant_id = current_user.tenant_id
    providers = []

    hr_conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
    )
    exely_conn = await db.exely_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
    )

    hr_flags = await db.connector_flags.find_one(
        {"tenant_id": tenant_id, "provider": "hotelrunner"}, {"_id": 0}
    )
    ex_flags = await db.connector_flags.find_one(
        {"tenant_id": tenant_id, "provider": "exely"}, {"_id": 0}
    )

    def _derive_mode(flags, conn_doc):
        if flags:
            if not flags.get("connector_enabled", False):
                return "inactive"
            shadow = flags.get("shadow_mode", True)
            write = flags.get("write_enabled", False) and not shadow
            return "shadow" if shadow else ("live" if write else "read_only")
        return conn_doc.get("push_mode", "shadow")

    if hr_conn:
        hr_mode = _derive_mode(hr_flags, hr_conn)
        if hr_mode != "inactive":
            providers.append({"slug": "hotelrunner", "name": "HotelRunner", "mode": hr_mode})

    if exely_conn:
        ex_mode = _derive_mode(ex_flags, exely_conn)
        if ex_mode != "inactive":
            providers.append({"slug": "exely", "name": "Exely", "mode": ex_mode})

    # Syroce B2B provider — aktif acente varsa ekle
    active_agency_count = await db.agencies.count_documents(
        {"tenant_id": tenant_id, "status": "active"}
    )
    if active_agency_count > 0:
        api_key_count = await db.agency_api_keys.count_documents(
            {"tenant_id": tenant_id, "is_active": True}
        )
        providers.append({
            "slug": "syroce_b2b",
            "name": "Syroce B2B",
            "mode": "live",
            "agency_count": active_agency_count,
            "api_key_count": api_key_count,
        })

    return {"providers": providers}


# ── Pricing Settings ─────────────────────────────────────────────

@router.get("/pricing-settings")
async def get_pricing_settings(current_user: User = Depends(get_current_user)):
    tenant_id = current_user.tenant_id
    detection = await _detect_active_provider(tenant_id)

    if detection["provider"] == "hotelrunner":
        docs = await db.hr_pricing_settings.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(200)
    else:
        docs = await db.pricing_settings.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(200)

    settings = {doc["room_type_code"]: doc.get("pricing_type", "per_person") for doc in docs}
    return {"settings": settings}


@router.put("/pricing-settings")
async def update_pricing_settings(
    request: PricingSettingsRequest,
    current_user: User = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id
    detection = await _detect_active_provider(tenant_id)
    now = datetime.now(UTC).isoformat()
    updated = 0

    collection = "hr_pricing_settings" if detection["provider"] == "hotelrunner" else "pricing_settings"

    for item in request.settings:
        if item.pricing_type not in ("per_person", "per_room"):
            raise HTTPException(status_code=400, detail=f"Gecersiz fiyatlandirma tipi: {item.pricing_type}")
        await db[collection].update_one(
            {"tenant_id": tenant_id, "room_type_code": item.room_type_code},
            {"$set": {
                "tenant_id": tenant_id,
                "room_type_code": item.room_type_code,
                "pricing_type": item.pricing_type,
                "updated_at": now,
                "updated_by": current_user.id,
            }},
            upsert=True,
        )
        updated += 1

    return {"updated": updated, "message": f"{updated} fiyatlandirma ayari guncellendi"}


# ── Stop Sale Summary ────────────────────────────────────────────

@router.get("/stop-sale-summary")
async def get_stop_sale_summary(
    start_date: str, end_date: str,
    current_user: User = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id
    detection = await _detect_active_provider(tenant_id)

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
        stops.append({
            "room_type_code": code,
            "room_type_name": rt_map.get(code, code),
            "dates": sorted(r["dates"]),
            "count": r["count"],
        })

    return {"stops": stops}


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
