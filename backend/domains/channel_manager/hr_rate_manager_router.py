"""
HotelRunner Rate Manager Router — Fiyat, Müsaitlik, Min Konaklama Yönetimi
HotelRunner üzerinden ayarla → HR API'ye push et → OTA'lara yansısın.
"""
import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

import holidays as holidays_lib
from dateutil.easter import easter
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pymongo import UpdateOne

from core.database import db
from core.security import get_current_user
from domains.channel_manager.hr_push_queue_worker import (
    clear_completed,
    clear_cooldown,
    enqueue_failed_push,
    get_cooldown_remaining,
    get_queue_status,
    reset_auto_retry,
    schedule_auto_retry,
)
from domains.channel_manager.providers.hotelrunner.errors import HotelRunnerRateLimitError
from models.schemas import User

logger = logging.getLogger(__name__)

# ── Rate-limit aware push helper ────────────────────────────────
MAX_RETRIES = 1           # fail-fast: tek deneme, 429'da hemen kuyruga ekle
INITIAL_BACKOFF = 5.0    # seconds — base backoff (kullanilmiyor, fail-fast)
MAX_PUSH_WAIT = 5.0      # seconds — max wait (kullanilmiyor, fail-fast)
INTER_PUSH_DELAY = 2.0  # seconds between sequential room-type pushes

router = APIRouter(prefix="/api/channel-manager/hr-rate-manager", tags=["HR Rate Manager"])


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


class BulkGridUpdateRequest(BaseModel):
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


class PricingSettingItem(BaseModel):
    room_type_code: str
    pricing_type: str


class PricingSettingsRequest(BaseModel):
    settings: list[PricingSettingItem]


# ── Helpers ──────────────────────────────────────────────────────


def _extract_room_types_and_rate_plans(cached_rooms: list) -> tuple[list, list]:
    """Extract unique room types and rate plans from HR cached_rooms."""
    room_types_map = {}
    rate_plans_map = {}

    for room in cached_rooms:
        inv_code = room.get("inv_code", "")
        name = room.get("name", "")
        rp_id = str(room.get("rate_plan_id", ""))
        rp_name = room.get("rate_plan_name", "")

        if inv_code and inv_code not in room_types_map:
            room_types_map[inv_code] = {
                "code": inv_code,
                "name": name,
                "capacity": room.get("room_capacity"),
                "pricing_type": room.get("pricing_type", "guest_based"),
                "availability_update": room.get("availability_update", True),
                "price_update": room.get("price_update", True),
                "restrictions_update": room.get("restrictions_update", True),
            }
        elif inv_code:
            # Merge permission flags: if ANY rate plan for this room type
            # has the flag true, mark it true
            existing = room_types_map[inv_code]
            existing["availability_update"] = existing["availability_update"] or room.get("availability_update", True)
            existing["price_update"] = existing["price_update"] or room.get("price_update", True)
            existing["restrictions_update"] = existing["restrictions_update"] or room.get("restrictions_update", True)

        if rp_id and rp_id not in rate_plans_map:
            rate_plans_map[rp_id] = {
                "code": rp_id,
                "name": rp_name,
            }

    return list(room_types_map.values()), list(rate_plans_map.values())


async def _get_hr_provider(tenant_id: str):
    """Get HotelRunner provider instance."""
    from domains.channel_manager.providers.hotelrunner_router import _get_provider
    try:
        provider, conn = await _get_provider(tenant_id)
        return provider, conn
    except Exception as exc:
        logger.warning("[HR-RATE-MGR] Provider alinamadi tenant=%s: %s", tenant_id, exc)
        return None, None


def _group_consecutive_dates(date_strings: list[str]) -> list[tuple[str, str]]:
    """Group sorted date strings into consecutive ranges.

    Returns list of (range_start, range_end) tuples.
    Example: ['2025-01-04', '2025-01-11', '2025-01-12'] ->
             [('2025-01-04','2025-01-04'), ('2025-01-11','2025-01-12')]
    """
    if not date_strings:
        return []
    ranges: list[tuple[str, str]] = []
    sorted_dates = sorted(date_strings)
    range_start = sorted_dates[0]
    prev = datetime.strptime(sorted_dates[0], "%Y-%m-%d").date()
    for ds in sorted_dates[1:]:
        curr = datetime.strptime(ds, "%Y-%m-%d").date()
        if (curr - prev).days != 1:
            ranges.append((range_start, prev.strftime("%Y-%m-%d")))
            range_start = ds
        prev = curr
    ranges.append((range_start, prev.strftime("%Y-%m-%d")))
    return ranges


async def _push_with_retry(
    provider, rt_code: str, start_date: str, end_date: str,
    *, rate=None, avail=None, stop=None, minstay=None,
) -> dict:
    """Push ARI update to HotelRunner — fail-fast, no retries."""
    update_data = {"inv_code": rt_code, "start_date": start_date, "end_date": end_date}
    if avail is not None:
        update_data["availability"] = int(avail)
    if rate is not None:
        update_data["price"] = float(rate)
    if stop is not None:
        update_data["stop_sale"] = 1 if stop else 0
    if minstay is not None:
        update_data["min_stay"] = int(minstay)

    try:
        result = await provider.update_room(**update_data)
        return {"room_type_code": rt_code, "success": result.get("success", False), "error": result.get("error")}
    except HotelRunnerRateLimitError as e:
        logger.warning("[HR-BULK-UPDATE] Rate limit for %s — hemen kuyruga ekleniyor (server: %ds)", rt_code, e.retry_after_seconds)
        return {"room_type_code": rt_code, "success": False, "error": f"Rate limit: {e}", "retry_after_seconds": e.retry_after_seconds}
    except Exception as e:
        logger.error("[HR-BULK-UPDATE] push error for %s: %s", rt_code, e)
        return {"room_type_code": rt_code, "success": False, "error": str(e)}


# ── Grid Endpoint ────────────────────────────────────────────────


@router.get("/grid")
async def get_hr_rate_grid(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user),
):
    """HotelRunner tarih aralığı için oda tipi x tarih grid'ini döndürür."""
    tenant_id = current_user.tenant_id

    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
    )
    if not conn:
        raise HTTPException(status_code=404, detail="HotelRunner bağlantısı bulunamadı")

    cached_rooms = conn.get("cached_rooms", [])
    if not cached_rooms:
        return {
            "grid": [], "room_types": [], "rate_plans": [],
            "pricing_settings": {}, "currency": "TRY",
            "start_date": start_date, "end_date": end_date,
        }

    room_types, rate_plans = _extract_room_types_and_rate_plans(cached_rooms)

    # Get room mappings for PMS room type lookups
    mappings = await db.hotelrunner_room_mappings.find(
        {"tenant_id": tenant_id}, {"_id": 0}
    ).to_list(100)

    mapping_by_inv = {}
    for m in mappings:
        mapping_by_inv[m.get("hr_inv_code", "")] = m.get("pms_room_type", "")

    # Get saved rate calendar data
    calendar_data = await db.hr_rate_calendar.find(
        {
            "tenant_id": tenant_id,
            "date": {"$gte": start_date, "$lte": end_date},
        },
        {"_id": 0},
    ).to_list(5000)

    cal_index = {}
    for entry in calendar_data:
        key = f"{entry['room_type_code']}|{entry['rate_plan_code']}|{entry['date']}"
        cal_index[key] = entry

    # Count rooms per PMS type
    room_counts = {}
    room_ids_by_type = {}
    rooms = await db.rooms.find(
        {"tenant_id": tenant_id}, {"_id": 0, "id": 1, "room_type": 1, "status": 1}
    ).to_list(500)
    for r in rooms:
        rt = r.get("room_type", "")
        room_counts.setdefault(rt, {"total": 0, "available": 0})
        room_counts[rt]["total"] += 1
        if r.get("status") == "available":
            room_counts[rt]["available"] += 1
        room_ids_by_type.setdefault(rt, []).append(r["id"])

    # Active bookings for dynamic availability
    ACTIVE_STATUSES = ["pending", "confirmed", "guaranteed", "checked_in"]
    active_bookings = await db.bookings.find(
        {
            "tenant_id": tenant_id,
            "status": {"$in": ACTIVE_STATUSES},
            "check_in": {"$lt": end_date},
            "check_out": {"$gt": start_date},
        },
        {"_id": 0, "room_id": 1, "check_in": 1, "check_out": 1},
    ).to_list(10000)

    def count_sold_for_type(pms_room_type, day_str):
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

    # Build valid (room_type, rate_plan) pairs from cached_rooms
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

            dates_data = []
            d = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()

            while d <= end:
                ds = d.strftime("%Y-%m-%d")
                key = f"{rt['code']}|{rp['code']}|{ds}"
                entry = cal_index.get(key, {})

                base_avail = entry.get("availability")
                sold_count = count_sold_for_type(pms_type, ds) if pms_type else 0
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

            grid.append({
                "room_type_code": rt["code"],
                "room_type_name": rt["name"],
                "rate_plan_code": rp["code"],
                "rate_plan_name": rp["name"],
                "pms_room_type": pms_type or rt["name"],
                "total_rooms": counts["total"],
                "dates": dates_data,
            })

    # Pricing settings
    pricing_docs = await db.hr_pricing_settings.find(
        {"tenant_id": tenant_id}, {"_id": 0}
    ).to_list(200)
    pricing_map = {}
    for doc in pricing_docs:
        pricing_map[doc["room_type_code"]] = doc.get("pricing_type", "per_person")

    currency = "TRY"
    if cached_rooms:
        currency = cached_rooms[0].get("sales_currency", "TRY")

    return {
        "grid": grid,
        "room_types": room_types,
        "rate_plans": rate_plans,
        "pricing_settings": pricing_map,
        "currency": currency,
        "start_date": start_date,
        "end_date": end_date,
    }


@router.get("/room-types")
async def get_hr_room_types(current_user: User = Depends(get_current_user)):
    """HotelRunner oda tiplerini ve fiyat planlarını döndürür."""
    tenant_id = current_user.tenant_id
    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
    )
    if not conn:
        raise HTTPException(status_code=404, detail="HotelRunner bağlantısı bulunamadı")

    cached_rooms = conn.get("cached_rooms", [])
    room_types, rate_plans = _extract_room_types_and_rate_plans(cached_rooms)

    pricing_docs = await db.hr_pricing_settings.find(
        {"tenant_id": tenant_id}, {"_id": 0}
    ).to_list(200)
    pricing_map = {}
    for doc in pricing_docs:
        pricing_map[doc["room_type_code"]] = doc.get("pricing_type", "per_person")

    return {
        "room_types": room_types,
        "rate_plans": rate_plans,
        "pricing_settings": pricing_map,
    }


# ── Bulk Grid Update ────────────────────────────────────────────


@router.post("/bulk-grid-update")
async def hr_bulk_grid_update(
    request: BulkGridUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    """HotelRunner toplu fiyat/müsaitlik güncelleme."""
    tenant_id = current_user.tenant_id
    now = datetime.now(UTC).isoformat()
    saved = 0

    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
    )
    if not conn:
        raise HTTPException(status_code=404, detail="HotelRunner bağlantısı bulunamadı")

    selected_days_set = set(request.selected_days) if request.selected_days else None
    update_fields = set(request.update_fields)

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

    total_room_types_set = set()
    bulk_ops = []
    push_tasks = []
    pushed_room_types = set()  # Deduplicate: only push once per room type
    matching_dates_per_rt: dict[str, set[str]] = {}  # rt_code -> set of matching date strings

    # Get HR provider for push
    provider, _ = await _get_hr_provider(tenant_id)

    # Build room type permission map from cached_rooms
    rt_permissions = {}
    if conn:
        cached_rooms = conn.get("cached_rooms", [])
        for room in cached_rooms:
            ic = room.get("inv_code", "")
            if ic and ic not in rt_permissions:
                rt_permissions[ic] = {
                    "availability_update": room.get("availability_update", True),
                    "price_update": room.get("price_update", True),
                    "restrictions_update": room.get("restrictions_update", True),
                }

    permission_warnings = []

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
                {
                    "tenant_id": tenant_id,
                    "room_type_code": rt_code,
                    "rate_plan_code": rp_code,
                    "date": ds,
                },
                {"$set": set_fields},
                upsert=True,
            ))
            saved += 1

            # Track matching dates for push (per room type)
            if rt_code not in matching_dates_per_rt:
                matching_dates_per_rt[rt_code] = set()
            matching_dates_per_rt[rt_code].add(ds)

            d += timedelta(days=1)

        # Push to HotelRunner — deduplicate per room type
        if provider and rt_code not in pushed_room_types:
            pushed_room_types.add(rt_code)

            # Check permission flags from cached_rooms
            perms = rt_permissions.get(rt_code, {})
            push_rate = v_rate if "rate" in update_fields else None
            push_avail = v_avail if "availability" in update_fields else None
            push_stop = v_stop if "stop_sell" in update_fields else None
            push_min = v_min if "min_stay" in update_fields else None

            # Warn about permission issues
            if push_avail is not None and not perms.get("availability_update", True):
                permission_warnings.append(
                    f"{rt_code}: HotelRunner bu oda tipi icin musaitlik guncellemesine izin vermiyor (availability_update=false)"
                )
                logger.warning("[HR-BULK-UPDATE] availability_update=false for %s — availability will be skipped by HR", rt_code)
            if push_rate is not None and not perms.get("price_update", True):
                permission_warnings.append(
                    f"{rt_code}: HotelRunner bu oda tipi icin fiyat guncellemesine izin vermiyor (price_update=false)"
                )
                logger.warning("[HR-BULK-UPDATE] price_update=false for %s — price will be skipped by HR", rt_code)

            # Build push tasks: when day filter is active, group consecutive
            # matching dates into sub-ranges so HR only gets those dates.
            rt_dates = matching_dates_per_rt.get(rt_code, set())
            if selected_days_set is not None and rt_dates:
                date_ranges = _group_consecutive_dates(list(rt_dates))
            else:
                date_ranges = [(request.start_date, request.end_date)]

            for range_start, range_end in date_ranges:
                push_tasks.append({
                    "rt": rt_code,
                    "rate": push_rate,
                    "avail": push_avail,
                    "stop": push_stop,
                    "minstay": push_min,
                    "start_date": range_start,
                    "end_date": range_end,
                })

    if bulk_ops:
        await db.hr_rate_calendar.bulk_write(bulk_ops, ordered=False)

    provider_warning = None
    if not provider and len(pairs) > 0:
        provider_warning = "HotelRunner kimlik bilgileri alinamadi — veriler yerel olarak kaydedildi ancak HotelRunner'a gonderilemedi"
        logger.warning("[HR-BULK-UPDATE] Provider is None, skipping push for tenant=%s", tenant_id)

    if push_tasks and provider:
        # ── Arka planda sıralı gönder, hemen yanıt dön ──
        # Exely tarzı: UI hemen döner. Arka planda sıralı push (2s arayla).
        # Sadece gerçek 429 rate limit alanlar kuyruğa eklenir.
        # Her push_task kendi start_date/end_date aralığını taşır (gün filtrelemeli).
        async def _background_push(tasks, prov, t_id):
            await asyncio.sleep(0.2)  # HTTP yanıtı dönmesini bekle
            success_count = 0
            for i, task_info in enumerate(tasks):
                rt = task_info["rt"]
                t_start = task_info["start_date"]
                t_end = task_info["end_date"]
                try:
                    result = await _push_with_retry(
                        prov, rt, t_start, t_end,
                        rate=task_info["rate"],
                        avail=task_info["avail"],
                        stop=task_info["stop"],
                        minstay=task_info["minstay"],
                    )
                    if result.get("success"):
                        clear_cooldown(t_id)
                        reset_auto_retry(t_id)
                        success_count += 1
                    elif "rate limit" in str(result.get("error", "")).lower():
                        # Rate limit → kalan push'ları da dahil kuyruğa ekle
                        retry_secs = result.get("retry_after_seconds", 65)
                        for remaining in tasks[i:]:
                            await enqueue_failed_push(
                                t_id, remaining["rt"],
                                remaining["start_date"], remaining["end_date"],
                                rate=remaining["rate"], avail=remaining["avail"],
                                stop=remaining["stop"], minstay=remaining["minstay"],
                                error=result.get("error", ""),
                                retry_after_seconds=retry_secs,
                            )
                        await schedule_auto_retry(t_id, retry_secs + 5)
                        logger.warning("[HR-BULK-UPDATE] Rate limit at %s — %d remaining queued for retry", rt, len(tasks) - i)
                        break
                except Exception as e:
                    logger.error("[HR-BULK-UPDATE] Background push error for %s (%s→%s): %s", rt, t_start, t_end, e)

                # Kısa ara ile rate limit'e takılmayı engelle
                if i < len(tasks) - 1:
                    await asyncio.sleep(2)

            logger.info("[HR-BULK-UPDATE] Background push done: %d/%d successful (tenant=%s)", success_count, len(tasks), t_id)

        asyncio.create_task(_background_push(
            push_tasks, provider, tenant_id,
        ))

    msg = f"{saved} kayıt güncellendi"
    if push_tasks and provider:
        msg += f", {len(push_tasks)} HotelRunner push arka planda gönderiliyor"
    if permission_warnings:
        msg += f" | UYARI: {len(permission_warnings)} izin sorunu tespit edildi"
    if provider_warning:
        msg += f" | {provider_warning}"

    return {
        "saved": saved,
        "push_results": [],
        "all_pushed": False,
        "background_push": len(push_tasks) > 0,
        "total_room_types": len(total_room_types_set),
        "permission_warnings": permission_warnings,
        "provider_warning": provider_warning,
        "message": msg,
    }


# ── Stop Sale Summary ────────────────────────────────────────────


@router.get("/stop-sale-summary")
async def get_hr_stop_sale_summary(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user),
):
    """HotelRunner stop_sell=true olan kayıtları döndürür."""
    tenant_id = current_user.tenant_id

    pipeline = [
        {
            "$match": {
                "tenant_id": tenant_id,
                "date": {"$gte": start_date, "$lte": end_date},
                "stop_sell": True,
            }
        },
        {
            "$group": {
                "_id": "$room_type_code",
                "dates": {"$addToSet": "$date"},
                "count": {"$sum": 1},
            }
        },
    ]

    results = await db.hr_rate_calendar.aggregate(pipeline).to_list(500)

    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0, "cached_rooms": 1}
    )
    rt_map = {}
    if conn:
        for room in conn.get("cached_rooms", []):
            rt_map[room.get("inv_code", "")] = room.get("name", "")

    stops = []
    for r in results:
        code = r["_id"]
        dates = sorted(r["dates"])
        stops.append({
            "room_type_code": code,
            "room_type_name": rt_map.get(code, code),
            "dates": dates,
            "count": r["count"],
        })

    return {"stops": stops}


# ── Pricing Settings ─────────────────────────────────────────────


@router.get("/pricing-settings")
async def get_hr_pricing_settings(current_user: User = Depends(get_current_user)):
    tenant_id = current_user.tenant_id
    docs = await db.hr_pricing_settings.find(
        {"tenant_id": tenant_id}, {"_id": 0}
    ).to_list(200)

    settings = {}
    for doc in docs:
        settings[doc["room_type_code"]] = doc.get("pricing_type", "per_person")

    return {"settings": settings}


@router.put("/pricing-settings")
async def update_hr_pricing_settings(
    request: PricingSettingsRequest,
    current_user: User = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id
    now = datetime.now(UTC).isoformat()
    updated = 0

    for item in request.settings:
        if item.pricing_type not in ("per_person", "per_room"):
            raise HTTPException(status_code=400, detail=f"Geçersiz fiyatlandırma tipi: {item.pricing_type}")

        await db.hr_pricing_settings.update_one(
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

    return {"updated": updated, "message": f"{updated} oda tipi fiyatlandırma ayarı güncellendi"}


# ── Holidays (shared logic) ─────────────────────────────────────


def _get_holiday_periods(year: int) -> list:
    tr = holidays_lib.Turkey(years=[year])
    groups = defaultdict(list)
    for d, name in sorted(tr.items()):
        parts = [n.strip() for n in name.split(";")]
        for part in parts:
            groups[part].append(d)

    periods = []
    tr_names = {
        "New Year's Day": "Yilbasi",
        "Eid al-Fitr": "Ramazan Bayrami",
        "Eid al-Adha": "Kurban Bayrami",
        "National Sovereignty and Children's Day": "23 Nisan Ulusal Egemenlik ve Cocuk Bayrami",
        "Labour and Solidarity Day": "1 Mayis Isci Bayrami",
        "Commemoration of Atatürk, Youth and Sports Day": "19 Mayis Ataturk'u Anma",
        "Democracy and National Unity Day": "15 Temmuz Demokrasi Bayrami",
        "Victory Day": "30 Agustos Zafer Bayrami",
        "Republic Day": "29 Ekim Cumhuriyet Bayrami",
    }

    for en_name, dates in groups.items():
        sorted_dates = sorted(dates)
        tr_name = tr_names.get(en_name, en_name)
        key = en_name.lower().replace(" ", "_").replace("'", "")
        periods.append({
            "key": f"tr_{key}_{year}",
            "name": tr_name,
            "category": "turkey",
            "start_date": sorted_dates[0].isoformat(),
            "end_date": sorted_dates[-1].isoformat(),
            "days": len(sorted_dates),
            "year": year,
        })

    easter_date = easter(year)
    orthodox_easter = easter(year, method=2)

    intl = [
        {"key": f"easter_{year}", "name": "Paskalya (Bati)", "category": "international",
         "start_date": (easter_date - timedelta(days=2)).isoformat(),
         "end_date": (easter_date + timedelta(days=1)).isoformat(), "days": 4, "year": year},
        {"key": f"orthodox_easter_{year}", "name": "Ortodoks Paskalya", "category": "international",
         "start_date": (orthodox_easter - timedelta(days=2)).isoformat(),
         "end_date": (orthodox_easter + timedelta(days=1)).isoformat(), "days": 4, "year": year},
        {"key": f"christmas_{year}", "name": "Noel Tatili", "category": "international",
         "start_date": f"{year}-12-23", "end_date": f"{year}-12-26", "days": 4, "year": year},
        {"key": f"russian_newyear_{year}", "name": "Rus Yilbasi Tatili", "category": "international",
         "start_date": f"{year}-01-01", "end_date": f"{year}-01-08", "days": 8, "year": year},
        {"key": f"summer_peak_{year}", "name": "Yaz Sezonu (Yuksek)", "category": "season",
         "start_date": f"{year}-07-01", "end_date": f"{year}-08-31", "days": 62, "year": year},
        {"key": f"winter_break_{year}", "name": "Soemestr Tatili", "category": "season",
         "start_date": f"{year}-01-20", "end_date": f"{year}-02-03", "days": 15, "year": year},
    ]
    periods.extend(intl)
    periods.sort(key=lambda x: x["start_date"])
    return periods


@router.get("/holidays")
async def get_hr_holidays(current_user: User = Depends(get_current_user)):
    now = date.today()
    years = [now.year, now.year + 1]
    all_periods = []
    for y in years:
        all_periods.extend(_get_holiday_periods(y))

    today_str = now.isoformat()
    upcoming = [p for p in all_periods if p["end_date"] >= today_str]
    return {"holidays": upcoming}


# ── Stop Sale Schedules ──────────────────────────────────────────


class StopSaleScheduleCreate(BaseModel):
    name: str
    holiday_key: str | None = None
    start_date: str
    end_date: str
    room_type_codes: list[str]
    auto_apply: bool = True


class StopSaleScheduleUpdate(BaseModel):
    name: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    room_type_codes: list[str] | None = None
    auto_apply: bool | None = None


@router.get("/stop-sale-schedules")
async def list_hr_stop_sale_schedules(current_user: User = Depends(get_current_user)):
    tenant_id = current_user.tenant_id
    docs = await db.hr_stop_sale_schedules.find(
        {"tenant_id": tenant_id}, {"_id": 0}
    ).sort("start_date", 1).to_list(200)
    return {"schedules": docs}


@router.post("/stop-sale-schedules")
async def create_hr_stop_sale_schedule(
    request: StopSaleScheduleCreate,
    current_user: User = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id
    now = datetime.now(UTC).isoformat()

    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0, "cached_rooms": 1}
    )

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

    await db.hr_stop_sale_schedules.insert_one(schedule)

    if request.auto_apply and conn:
        cached_rooms = conn.get("cached_rooms", [])
        _, rate_plans = _extract_room_types_and_rate_plans(cached_rooms)
        rp_codes = [rp["code"] for rp in rate_plans]

        per_room_values = [
            RoomTypeValuesItem(
                room_type_code=rt_code,
                rate_plan_codes=rp_codes,
                stop_sell=True,
            )
            for rt_code in request.room_type_codes
        ]

        bulk_req = BulkGridUpdateRequest(
            per_room_values=per_room_values,
            start_date=request.start_date,
            end_date=request.end_date,
            update_fields=["stop_sell"],
        )
        await hr_bulk_grid_update(bulk_req, current_user)

        await db.hr_stop_sale_schedules.update_one(
            {"id": schedule["id"]},
            {"$set": {"applied": True, "applied_at": now}},
        )
        schedule["applied"] = True
        schedule["applied_at"] = now

    schedule.pop("_id", None)
    return {"schedule": schedule, "message": "Zamanlayici olusturuldu"}


@router.delete("/stop-sale-schedules/{schedule_id}")
async def delete_hr_stop_sale_schedule(
    schedule_id: str,
    remove_stop_sale: bool = False,
    current_user: User = Depends(get_current_user),
):
    tenant_id = current_user.tenant_id
    schedule = await db.hr_stop_sale_schedules.find_one(
        {"tenant_id": tenant_id, "id": schedule_id}, {"_id": 0}
    )
    if not schedule:
        raise HTTPException(status_code=404, detail="Zamanlayici bulunamadi")

    if remove_stop_sale and schedule.get("applied"):
        conn = await db.hotelrunner_connections.find_one(
            {"tenant_id": tenant_id, "is_active": True}, {"_id": 0, "cached_rooms": 1}
        )
        if conn:
            cached_rooms = conn.get("cached_rooms", [])
            _, rate_plans = _extract_room_types_and_rate_plans(cached_rooms)
            rp_codes = [rp["code"] for rp in rate_plans]

            per_room_values = [
                RoomTypeValuesItem(
                    room_type_code=rt_code,
                    rate_plan_codes=rp_codes,
                    stop_sell=False,
                )
                for rt_code in schedule["room_type_codes"]
            ]

            bulk_req = BulkGridUpdateRequest(
                per_room_values=per_room_values,
                start_date=schedule["start_date"],
                end_date=schedule["end_date"],
                update_fields=["stop_sell"],
            )
            await hr_bulk_grid_update(bulk_req, current_user)

    await db.hr_stop_sale_schedules.delete_one(
        {"tenant_id": tenant_id, "id": schedule_id}
    )
    return {"message": "Zamanlayici silindi"}


@router.patch("/stop-sale-schedules/{schedule_id}")
async def update_hr_stop_sale_schedule(
    schedule_id: str,
    request: StopSaleScheduleUpdate,
    current_user: User = Depends(get_current_user),
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

    result = await db.hr_stop_sale_schedules.update_one(
        {"tenant_id": tenant_id, "id": schedule_id},
        {"$set": update_fields},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Zamanlayici bulunamadi")

    return {"message": "Zamanlayici guncellendi"}


# ── Push Providers (HR specific) ─────────────────────────────────


@router.get("/push-providers")
async def get_hr_push_providers(current_user: User = Depends(get_current_user)):
    """HotelRunner push provider durumu."""
    tenant_id = current_user.tenant_id

    hr_flags = await db.connector_feature_flags.find_one(
        {"tenant_id": tenant_id, "provider": "hotelrunner_v2"}, {"_id": 0}
    )
    if not hr_flags:
        hr_flags = await db.connector_feature_flags.find_one(
            {"provider": "hotelrunner_v2"}, {"_id": 0}
        )

    hr_conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
    )

    if hr_flags and hr_flags.get("connector_enabled"):
        hr_shadow = hr_flags.get("shadow_mode", True)
        hr_write = hr_flags.get("write_enabled", False) and not hr_shadow
        if hr_shadow:
            hr_mode = "shadow"
        elif hr_write:
            hr_mode = "live"
        else:
            hr_mode = "read_only"
    elif hr_conn:
        hr_mode = "shadow"
        hr_write = False
    else:
        hr_mode = "inactive"
        hr_write = False

    return {
        "providers": [{
            "name": "HotelRunner",
            "slug": "hotelrunner",
            "push_active": hr_write,
            "mode": hr_mode,
        }]
    }


# ── Room Type Management (remove from cached_rooms) ──────────────


@router.delete("/room-types/{inv_code}")
async def remove_hr_room_type(
    inv_code: str,
    current_user: User = Depends(get_current_user),
):
    """Remove a room type from cached_rooms (hides from rate manager)."""
    tenant_id = current_user.tenant_id

    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0, "cached_rooms": 1}
    )
    if not conn:
        raise HTTPException(status_code=404, detail="HotelRunner baglantisi bulunamadi")

    cached_rooms = conn.get("cached_rooms", [])
    original_count = len(cached_rooms)
    filtered_rooms = [r for r in cached_rooms if r.get("inv_code") != inv_code]

    if len(filtered_rooms) == original_count:
        raise HTTPException(status_code=404, detail=f"Oda tipi bulunamadi: {inv_code}")

    removed_count = original_count - len(filtered_rooms)

    await db.hotelrunner_connections.update_one(
        {"tenant_id": tenant_id, "is_active": True},
        {"$set": {"cached_rooms": filtered_rooms}},
    )

    # Also clean up related calendar data
    await db.hr_rate_calendar.delete_many({
        "tenant_id": tenant_id,
        "room_type_code": inv_code,
    })

    logger.info("[HR-ROOM-TYPE] Removed inv_code=%s from cached_rooms (%d entries removed)", inv_code, removed_count)

    return {
        "message": f"Oda tipi '{inv_code}' basariyla kaldirildi ({removed_count} kayit silindi)",
        "removed_inv_code": inv_code,
        "removed_count": removed_count,
    }


# ── Push Queue Endpoints ──────────────────────────────────────────


@router.get("/queue-status")
async def get_hr_queue_status(current_user: User = Depends(get_current_user)):
    """Kuyruk durumunu döndürür — bekleyen, başarılı ve başarısız push'lar."""
    tenant_id = current_user.tenant_id
    status = await get_queue_status(tenant_id)
    return status


@router.post("/queue-retry")
async def retry_queue_items(current_user: User = Depends(get_current_user)):
    """Kuyruktaki tüm bekleyen push'ları tekrar dene — cooldown kontrolü ile."""
    from domains.channel_manager.hr_push_queue_worker import push_queue_worker

    tenant_id = current_user.tenant_id

    # Check cooldown
    cooldown = get_cooldown_remaining(tenant_id)
    if cooldown > 0:
        status = await get_queue_status(tenant_id)
        # Schedule auto-retry if not already scheduled
        if not status.get("auto_retry_scheduled"):
            await schedule_auto_retry(tenant_id, cooldown + 2)
        return {
            "message": f"Rate limit aktif — {cooldown} saniye sonra otomatik gonderilecek",
            "cooldown_remaining": cooldown,
            "auto_retry_scheduled": True,
            **status,
        }

    # Reset rate limit counter to allow immediate retry
    push_queue_worker._consecutive_rate_limits = 0
    reset_auto_retry(tenant_id)

    # Run queue processing for this tenant
    await push_queue_worker._process_tenant_queue(tenant_id)

    status = await get_queue_status(tenant_id)
    return {
        "message": "Kuyruk isleme alindi" if status["total_in_queue"] == 0 else f"{status['total_in_queue']} push hala kuyrukta",
        "cooldown_remaining": status.get("cooldown_remaining", 0),
        **status,
    }


@router.delete("/queue-clear")
async def clear_queue(current_user: User = Depends(get_current_user)):
    """Tamamlanan kuyruk öğelerini temizle."""
    tenant_id = current_user.tenant_id
    deleted = await clear_completed(tenant_id)
    return {"message": f"{deleted} tamamlanan kayit temizlendi", "deleted": deleted}


@router.delete("/queue-cancel/{item_id}")
async def cancel_queue_item(item_id: str, current_user: User = Depends(get_current_user)):
    """Kuyruktaki belirli bir push görevini iptal et."""
    tenant_id = current_user.tenant_id
    result = await db.hr_push_queue.delete_one({"id": item_id, "tenant_id": tenant_id, "status": {"$in": ["pending", "retrying"]}})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Kuyruk ogesi bulunamadi veya zaten tamamlanmis")
    return {"message": "Kuyruk ogesi iptal edildi"}
