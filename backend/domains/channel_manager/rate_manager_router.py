"""
Rate Manager Router — Fiyat, Müsaitlik, Min Konaklama Yönetimi
PMS üzerinden ayarla → Exely'ye push et → OTA'lara yansısın.
"""

import asyncio
import logging
import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pymongo import UpdateOne

from core.database import db
from core.security import get_current_user
from core.tenant_currency import get_tenant_currency
from domains.channel_manager.credential_vault import get_decrypted_credentials
from domains.channel_manager.rate_utils import (
    BulkGridUpdateRequest,
    PricingSettingsRequest,
    RoomTypeValuesItem,
    StopSaleScheduleCreate,
    StopSaleScheduleUpdate,
)
from domains.channel_manager.rate_utils import (
    get_holiday_periods as _get_holiday_periods,
)
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v96 DW

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channel-manager/rate-manager", tags=["Rate Manager"])


class RateUpdateRequest(BaseModel):
    room_type_code: str
    rate_plan_code: str
    start_date: str
    end_date: str
    rate: float | None = None
    availability: int | None = None
    min_stay: int | None = None
    max_stay: int | None = None
    stop_sell: bool | None = None
    cta: bool | None = None
    ctd: bool | None = None


class BulkRateUpdateRequest(BaseModel):
    updates: list[RateUpdateRequest]


@router.get("/grid")
async def get_rate_grid(
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Return room type x date grid for the given date range."""
    tenant_id = current_user.tenant_id
    if not start_date:
        start_date = datetime.now(UTC).date().isoformat()
    if not end_date:
        end_date = (datetime.now(UTC) + timedelta(days=14)).date().isoformat()

    # Get room type mappings
    mappings = await db.exely_room_mappings.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(100)

    # Get connection for room/rate info
    conn = await db.exely_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0})
    if not conn:
        raise HTTPException(status_code=404, detail="Exely connection not found")

    room_types = conn.get("room_types", [])
    rate_plans = conn.get("rate_plans", [])

    # Get saved rate calendar data
    calendar_data = await db.rate_calendar.find(
        {
            "tenant_id": tenant_id,
            "date": {"$gte": start_date, "$lte": end_date},
        },
        {"_id": 0},
    ).to_list(5000)

    # Index by room_type_code + rate_plan_code + date
    cal_index = {}
    for entry in calendar_data:
        key = f"{entry['room_type_code']}|{entry['rate_plan_code']}|{entry['date']}"
        cal_index[key] = entry

    # Count rooms per type and collect room IDs per type
    room_counts = {}
    room_ids_by_type = {}
    rooms = await db.rooms.find({"tenant_id": tenant_id}, {"_id": 0, "id": 1, "room_type": 1, "status": 1}).to_list(500)
    for r in rooms:
        rt = r.get("room_type", "")
        room_counts.setdefault(rt, {"total": 0, "available": 0})
        room_counts[rt]["total"] += 1
        if r.get("status") == "available":
            room_counts[rt]["available"] += 1
        room_ids_by_type.setdefault(rt, []).append(r["id"])

    # Fetch active bookings in date range to calculate dynamic availability
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

    # Build a lookup: for each room_type + date -> count of sold rooms
    def count_sold_for_type(pms_room_type, day_str):
        """Count how many rooms of this type are booked on this date."""
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

    # Build grid
    grid = []
    for rt in room_types:
        pms_type = None
        for m in mappings:
            if m.get("exely_room_code") == rt["code"]:
                pms_type = m.get("pms_room_type")
                break

        counts = room_counts.get(pms_type or rt["name"], {"total": 0, "available": 0})

        for rp in rate_plans:
            dates_data = []
            d = datetime.strptime(start_date, "%Y-%m-%d").date()
            end = datetime.strptime(end_date, "%Y-%m-%d").date()

            while d <= end:
                ds = d.strftime("%Y-%m-%d")
                key = f"{rt['code']}|{rp['code']}|{ds}"
                entry = cal_index.get(key, {})

                # Dynamic availability: base availability minus sold bookings
                base_avail = entry.get("availability")
                sold_count = count_sold_for_type(pms_type or rt["name"], ds)
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

    # Fetch pricing settings
    pricing_docs = await db.pricing_settings.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(200)
    pricing_map = {}
    for doc in pricing_docs:
        pricing_map[doc["room_type_code"]] = doc.get("pricing_type", "per_person")

    currency = conn.get("currency", "TRY")

    return {
        "grid": grid,
        "room_types": room_types,
        "rate_plans": rate_plans,
        "pricing_settings": pricing_map,
        "currency": currency,
        "start_date": start_date,
        "end_date": end_date,
    }


@router.post("/update")
async def update_rates(
    request: BulkRateUpdateRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
):
    """Update rates/availability/restrictions and push to Exely."""
    tenant_id = current_user.tenant_id
    now = datetime.now(UTC).isoformat()
    saved = 0
    push_results = []

    conn = await db.exely_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0})
    if not conn:
        raise HTTPException(status_code=404, detail="Exely connection not found")

    # Get credentials for Exely push
    hotel_code = conn.get("hotel_code", "")
    creds = await get_decrypted_credentials(tenant_id, "exely", hotel_code)
    provider = None
    if creds:
        from domains.channel_manager.providers.exely.provider import ExelyProvider

        provider_kwargs = {
            "username": creds.get("username", ""),
            "password": creds.get("password", ""),
            "hotel_code": hotel_code,
            "connection_id": f"{tenant_id}:{hotel_code}",
        }
        if conn.get("endpoint_url"):
            provider_kwargs["endpoint_url"] = conn["endpoint_url"]
        try:
            provider = ExelyProvider(**provider_kwargs)
        except Exception:
            provider = None

    bulk_ops = []
    push_tasks = []

    for upd in request.updates:
        # Save each date in range to rate_calendar
        d = datetime.strptime(upd.start_date, "%Y-%m-%d").date()
        end = datetime.strptime(upd.end_date, "%Y-%m-%d").date()

        while d <= end:
            ds = d.strftime("%Y-%m-%d")
            set_fields = {
                "tenant_id": tenant_id,
                "room_type_code": upd.room_type_code,
                "rate_plan_code": upd.rate_plan_code,
                "date": ds,
                "updated_at": now,
                "updated_by": current_user.id,
            }
            if upd.rate is not None:
                set_fields["rate"] = upd.rate
            if upd.availability is not None:
                set_fields["availability"] = upd.availability
            if upd.min_stay is not None:
                set_fields["min_stay"] = upd.min_stay
            if upd.stop_sell is not None:
                set_fields["stop_sell"] = upd.stop_sell

            bulk_ops.append(
                UpdateOne(
                    {
                        "tenant_id": tenant_id,
                        "room_type_code": upd.room_type_code,
                        "rate_plan_code": upd.rate_plan_code,
                        "date": ds,
                    },
                    {"$set": set_fields},
                    upsert=True,
                )
            )
            saved += 1
            d += timedelta(days=1)

        # Prepare Exely push task (will run in parallel)
        if provider:

            async def _push(u=upd):
                try:
                    result = await provider.push_ari(
                        room_type_code=u.room_type_code,
                        rate_plan_code=u.rate_plan_code,
                        start_date=u.start_date,
                        end_date=u.end_date,
                        availability=u.availability,
                        rate_amount=u.rate,
                        currency=conn.get("currency", "TRY"),
                        stop_sell=u.stop_sell,
                        min_stay=u.min_stay,
                    )
                    return {"room_type_code": u.room_type_code, "rate_plan_code": u.rate_plan_code, "success": result.success, "error": result.error if not result.success else None}
                except Exception as e:
                    logger.error(f"[RATE-MGR] Exely push error: {e}")
                    return {"room_type_code": u.room_type_code, "rate_plan_code": u.rate_plan_code, "success": False, "error": str(e)}

            push_tasks.append(_push())
        else:
            push_results.append(
                {
                    "room_type_code": upd.room_type_code,
                    "rate_plan_code": upd.rate_plan_code,
                    "success": False,
                    "error": "Exely credentials not found",
                }
            )

    # Execute DB bulk write in one batch
    if bulk_ops:
        await db.rate_calendar.bulk_write(bulk_ops, ordered=False)

    # Execute all Exely pushes in parallel
    if push_tasks:
        push_results.extend(await asyncio.gather(*push_tasks))

    all_success = all(r["success"] for r in push_results)

    return {
        "saved": saved,
        "push_results": push_results,
        "all_pushed": all_success,
        "message": "All updates applied successfully" if all_success else "Some updates failed",
    }


@router.get("/room-types")
async def get_room_types(current_user: User = Depends(get_current_user)):
    """Return available room types, rate plans, and pricing settings."""
    tenant_id = current_user.tenant_id
    conn = await db.exely_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0})
    if not conn:
        raise HTTPException(status_code=404, detail="Exely connection not found")

    # Fetch pricing settings
    pricing_docs = await db.pricing_settings.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(200)
    pricing_map = {}
    for doc in pricing_docs:
        pricing_map[doc["room_type_code"]] = doc.get("pricing_type", "per_person")

    return {
        "room_types": conn.get("room_types", []),
        "rate_plans": conn.get("rate_plans", []),
        "pricing_settings": pricing_map,
    }


@router.post("/bulk-grid-update")
async def bulk_grid_update(
    request: BulkGridUpdateRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v96 DW
):
    """
    HotelRunner-style toplu güncelleme:
    Birden fazla oda tipi + plan için aynı değerleri tek seferde uygula.
    Gün filtreleme desteği ile (ör. sadece hafta sonu).
    """
    tenant_id = current_user.tenant_id
    now = datetime.now(UTC).isoformat()
    saved = 0
    _push_results = []

    conn = await db.exely_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0})
    if not conn:
        raise HTTPException(status_code=404, detail="Exely connection not found")

    # Get credentials for Exely push
    hotel_code = conn.get("hotel_code", "")
    creds = await get_decrypted_credentials(tenant_id, "exely", hotel_code)
    provider = None
    if creds:
        from domains.channel_manager.providers.exely.provider import ExelyProvider

        provider_kwargs = {
            "username": creds.get("username", ""),
            "password": creds.get("password", ""),
            "hotel_code": hotel_code,
            "connection_id": f"{tenant_id}:{hotel_code}",
        }
        if conn.get("endpoint_url"):
            provider_kwargs["endpoint_url"] = conn["endpoint_url"]
        try:
            provider = ExelyProvider(**provider_kwargs)
        except Exception:
            provider = None

    selected_days_set = set(request.selected_days) if request.selected_days else None
    update_fields = set(request.update_fields)

    # Build per-room-type values index for quick lookup
    per_room_map = {}
    if request.per_room_values:
        for prv in request.per_room_values:
            per_room_map[prv.room_type_code] = prv

    # Build iteration pairs
    pairs = []
    if request.per_room_values:
        # Per-room-type mode: each item has its own rate_plan_codes and values
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

    for rt_code, rp_code in pairs:
        total_room_types_set.add(rt_code)
        rv = per_room_map.get(rt_code)

        # Use per-room values if available, otherwise global
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
                    {
                        "tenant_id": tenant_id,
                        "room_type_code": rt_code,
                        "rate_plan_code": rp_code,
                        "date": ds,
                    },
                    {"$set": set_fields},
                    upsert=True,
                )
            )
            saved += 1
            d += timedelta(days=1)

        # Prepare Exely push task (will run in parallel)
        if provider:
            push_rate = v_rate if "rate" in update_fields else None
            push_avail = v_avail if "availability" in update_fields else None
            push_stop = v_stop if "stop_sell" in update_fields else None
            push_min = v_min if "min_stay" in update_fields else None
            _cur_code, _ = await get_tenant_currency(tenant_id)
            push_currency = conn.get("currency") or _cur_code

            async def _push(rt=rt_code, rp=rp_code, rate=push_rate, avail=push_avail, stop=push_stop, minstay=push_min, cur=push_currency):
                try:
                    result = await provider.push_ari(
                        room_type_code=rt,
                        rate_plan_code=rp,
                        start_date=request.start_date,
                        end_date=request.end_date,
                        availability=avail,
                        rate_amount=rate,
                        currency=cur,
                        stop_sell=stop,
                        min_stay=minstay,
                    )
                    return {"room_type_code": rt, "rate_plan_code": rp, "success": result.success, "error": result.error if not result.success else None}
                except Exception as e:
                    logger.error(f"[BULK-UPDATE] Exely push error: {e}")
                    return {"room_type_code": rt, "rate_plan_code": rp, "success": False, "error": str(e)}

            push_tasks.append(_push())

    # Execute DB bulk write in one batch
    if bulk_ops:
        await db.rate_calendar.bulk_write(bulk_ops, ordered=False)

    # Fire-and-forget: push to Exely in background (don't block response)
    if push_tasks:

        async def _background_push(tasks):
            try:
                results = await asyncio.gather(*tasks, return_exceptions=True)
                success = sum(1 for r in results if isinstance(r, dict) and r.get("success"))
                logger.info(f"[BULK-UPDATE] Background Exely push done: {success}/{len(results)} successful")
            except Exception as e:
                logger.error(f"[BULK-UPDATE] Background Exely push failed: {e}")

        asyncio.create_task(_background_push(push_tasks))

    return {
        "saved": saved,
        "push_results": [],
        "all_pushed": False,
        "background_push": len(push_tasks) > 0,
        "total_room_types": len(total_room_types_set),
        "message": f"{saved} kayıt güncellendi" + (f", {len(push_tasks)} Exely push arka planda gönderiliyor" if push_tasks else ""),
    }


@router.get("/stop-sale-summary")
async def get_stop_sale_summary(
    start_date: str | None = None,
    end_date: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Lightweight endpoint: sadece stop_sell=true olan kayıtları döndürür."""
    tenant_id = current_user.tenant_id
    if not start_date:
        start_date = datetime.now(UTC).date().isoformat()
    if not end_date:
        end_date = (datetime.now(UTC) + timedelta(days=14)).date().isoformat()

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

    results = await db.rate_calendar.aggregate(pipeline).to_list(500)

    # Get room type names
    conn = await db.exely_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0, "room_types": 1})
    rt_map = {}
    if conn:
        for rt in conn.get("room_types", []):
            rt_map[rt.get("code", "")] = rt.get("name", rt.get("code", ""))

    stops = []
    for r in results:
        code = r["_id"]
        dates = sorted(r["dates"])
        stops.append(
            {
                "room_type_code": code,
                "room_type_name": rt_map.get(code, code),
                "dates": dates,
                "count": r["count"],
            }
        )

    return {"stops": stops}


@router.get("/pricing-settings")
async def get_pricing_settings(current_user: User = Depends(get_current_user)):
    """Oda tipi bazında fiyatlandırma tipi ayarlarını döndürür (per_person / per_room)."""
    tenant_id = current_user.tenant_id
    docs = await db.pricing_settings.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(200)

    settings = {}
    for doc in docs:
        settings[doc["room_type_code"]] = doc.get("pricing_type", "per_person")

    return {"settings": settings}


@router.put("/pricing-settings")
async def update_pricing_settings(
    request: PricingSettingsRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
):
    """Oda tipi bazında fiyatlandırma tipini günceller."""
    tenant_id = current_user.tenant_id
    now = datetime.now(UTC).isoformat()
    updated = 0

    for item in request.settings:
        if item.pricing_type not in ("per_person", "per_room"):
            raise HTTPException(status_code=400, detail=f"Geçersiz fiyatlandırma tipi: {item.pricing_type}")

        await db.pricing_settings.update_one(
            {"tenant_id": tenant_id, "room_type_code": item.room_type_code},
            {
                "$set": {
                    "tenant_id": tenant_id,
                    "room_type_code": item.room_type_code,
                    "pricing_type": item.pricing_type,
                    "updated_at": now,
                    "updated_by": current_user.id,
                }
            },
            upsert=True,
        )
        updated += 1

    return {"updated": updated, "message": f"{updated} oda tipi fiyatlandırma ayarı güncellendi"}


# ─── Holiday & Scheduler ────────────────────────────────────────


@router.get("/holidays")
async def get_holidays(
    current_user: User = Depends(get_current_user),
):
    """Tatil donemlerini dondurur (Turk + uluslararasi)."""
    now = date.today()
    years = [now.year]
    if now.month >= 10:
        years.append(now.year + 1)
    else:
        years = [now.year, now.year + 1]

    all_periods = []
    for y in years:
        all_periods.extend(_get_holiday_periods(y))

    # Filter out past holidays (keep only those ending today or later)
    today_str = now.isoformat()
    upcoming = [p for p in all_periods if p["end_date"] >= today_str]

    return {"holidays": upcoming}


# ─── Stop Sale Scheduler ────────────────────────────────────────


@router.get("/stop-sale-schedules")
async def list_stop_sale_schedules(
    current_user: User = Depends(get_current_user),
):
    """Kaydedilmis stop sale zamanlayicilari listeler."""
    tenant_id = current_user.tenant_id
    docs = await db.stop_sale_schedules.find({"tenant_id": tenant_id}, {"_id": 0}).sort("start_date", 1).to_list(200)
    return {"schedules": docs}


@router.post("/stop-sale-schedules")
async def create_stop_sale_schedule(
    request: StopSaleScheduleCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
):
    """Yeni stop sale zamanlayici olusturur."""
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

    # If auto_apply is True, immediately apply the stop sale
    if request.auto_apply:
        conn = await db.exely_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0})
        if conn:
            rate_plans = conn.get("rate_plans", [])
            rp_codes = [rp["code"] for rp in rate_plans]

            per_room_values = [
                {
                    "room_type_code": rt_code,
                    "rate_plan_codes": rp_codes,
                    "stop_sell": True,
                }
                for rt_code in request.room_type_codes
            ]

            bulk_req = BulkGridUpdateRequest(
                per_room_values=[RoomTypeValuesItem(**prv) for prv in per_room_values],
                start_date=request.start_date,
                end_date=request.end_date,
                update_fields=["stop_sell"],
            )
            await bulk_grid_update(bulk_req, current_user)

            await db.stop_sale_schedules.update_one(
                {"id": schedule["id"]},
                {"$set": {"applied": True, "applied_at": now}},
            )
            schedule["applied"] = True
            schedule["applied_at"] = now

    # Remove _id before returning
    schedule.pop("_id", None)
    return {"schedule": schedule, "message": "Zamanlayici olusturuldu"}


@router.delete("/stop-sale-schedules/{schedule_id}")
async def delete_stop_sale_schedule(
    schedule_id: str,
    remove_stop_sale: bool = False,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
):
    """Stop sale zamanlayiciyi siler. remove_stop_sale=true ise stop sale'i de kaldirir."""
    tenant_id = current_user.tenant_id
    schedule = await db.stop_sale_schedules.find_one({"tenant_id": tenant_id, "id": schedule_id}, {"_id": 0})
    if not schedule:
        raise HTTPException(status_code=404, detail="Zamanlayici bulunamadi")

    # Optionally remove the stop sale
    if remove_stop_sale and schedule.get("applied"):
        conn = await db.exely_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0})
        if conn:
            rate_plans = conn.get("rate_plans", [])
            rp_codes = [rp["code"] for rp in rate_plans]

            per_room_values = [
                {
                    "room_type_code": rt_code,
                    "rate_plan_codes": rp_codes,
                    "stop_sell": False,
                }
                for rt_code in schedule["room_type_codes"]
            ]
            bulk_req = BulkGridUpdateRequest(
                per_room_values=[RoomTypeValuesItem(**prv) for prv in per_room_values],
                start_date=schedule["start_date"],
                end_date=schedule["end_date"],
                update_fields=["stop_sell"],
            )
            await bulk_grid_update(bulk_req, current_user)

    await db.stop_sale_schedules.delete_one({"tenant_id": tenant_id, "id": schedule_id})
    return {"message": "Zamanlayici silindi"}


@router.patch("/stop-sale-schedules/{schedule_id}")
async def update_stop_sale_schedule(
    schedule_id: str,
    request: StopSaleScheduleUpdate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v99 DW
):
    """Stop sale zamanlayici gunceller."""
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


@router.get("/push-providers")
async def get_push_providers(current_user: User = Depends(get_current_user)):
    """Get push status for all channel providers (Exely, HotelRunner, etc.)."""
    tenant_id = current_user.tenant_id
    providers = []

    # 1. Exely status — check exely_connections for active connection
    exely_conn = await db.exely_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0})
    exely_active = bool(exely_conn)
    providers.append(
        {
            "name": "Exely",
            "slug": "exely",
            "push_active": exely_active,
            "mode": "live" if exely_active else "inactive",
        }
    )

    # 2. HotelRunner v2 status — check connector_feature_flags
    hr_flags = await db.connector_feature_flags.find_one({"tenant_id": tenant_id, "provider": "hotelrunner_v2"}, {"_id": 0})
    if not hr_flags:
        # Fallback: check for any hotelrunner flag
        hr_flags = await db.connector_feature_flags.find_one({"provider": "hotelrunner_v2"}, {"_id": 0})
    hr_conn = await db.hotelrunner_connections.find_one({"tenant_id": tenant_id}, {"_id": 0})

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

    providers.append(
        {
            "name": "HotelRunner",
            "slug": "hotelrunner",
            "push_active": hr_write,
            "mode": hr_mode,
        }
    )

    return {"providers": providers}
