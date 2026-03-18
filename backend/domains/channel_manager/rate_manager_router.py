"""
Rate Manager Router — Fiyat, Müsaitlik, Min Konaklama Yönetimi
PMS üzerinden ayarla → Exely'ye push et → OTA'lara yansısın.
"""
import logging
import uuid
from datetime import datetime, timezone, date, timedelta
from typing import Optional, List
from pydantic import BaseModel

from fastapi import APIRouter, Depends, HTTPException
from core.database import db
from core.security import get_current_user
from models.schemas import User
from domains.channel_manager.credential_vault import get_decrypted_credentials

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channel-manager/rate-manager", tags=["Rate Manager"])


class RateUpdateRequest(BaseModel):
    room_type_code: str
    rate_plan_code: str
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD
    rate: Optional[float] = None
    availability: Optional[int] = None
    min_stay: Optional[int] = None
    max_stay: Optional[int] = None
    stop_sell: Optional[bool] = None
    cta: Optional[bool] = None  # Close to Arrival
    ctd: Optional[bool] = None  # Close to Departure


class BulkRateUpdateRequest(BaseModel):
    updates: List[RateUpdateRequest]


class BulkGridUpdateRequest(BaseModel):
    """HotelRunner-style bulk update: apply same values to multiple room types at once."""
    room_type_codes: List[str]          # Selected room type codes
    rate_plan_codes: List[str]          # Selected rate plan codes
    start_date: str                     # YYYY-MM-DD
    end_date: str                       # YYYY-MM-DD
    selected_days: Optional[List[int]] = None  # 0=Sun..6=Sat, None=all days
    # Fields to update (only non-None fields get applied)
    rate: Optional[float] = None
    availability: Optional[int] = None
    min_stay: Optional[int] = None
    max_stay: Optional[int] = None
    stop_sell: Optional[bool] = None
    cta: Optional[bool] = None
    ctd: Optional[bool] = None
    # Which update fields are enabled
    update_fields: List[str] = []       # e.g. ["rate", "availability", "min_stay"]


@router.get("/grid")
async def get_rate_grid(
    start_date: str,
    end_date: str,
    current_user: User = Depends(get_current_user),
):
    """Tarih aralığı için oda tipi x tarih grid'ini döndürür."""
    tenant_id = current_user.tenant_id

    # Get room type mappings
    mappings = await db.exely_room_mappings.find(
        {"tenant_id": tenant_id}, {"_id": 0}
    ).to_list(100)

    # Get connection for room/rate info
    conn = await db.exely_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely bağlantısı bulunamadı")

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

    return {
        "grid": grid,
        "room_types": room_types,
        "rate_plans": rate_plans,
        "start_date": start_date,
        "end_date": end_date,
    }


@router.post("/update")
async def update_rates(
    request: BulkRateUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    """Fiyat/müsaitlik/kısıtlama güncelle ve Exely'ye push et."""
    tenant_id = current_user.tenant_id
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    push_results = []

    conn = await db.exely_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely bağlantısı bulunamadı")

    # Get credentials for Exely push
    creds = await get_decrypted_credentials(tenant_id, "exely", conn["hotel_code"])
    provider = None
    if creds:
        from domains.channel_manager.providers.exely.provider import ExelyProvider
        provider_kwargs = {
            "username": creds["username"],
            "password": creds["password"],
            "hotel_code": conn["hotel_code"],
        }
        if conn.get("endpoint_url"):
            provider_kwargs["endpoint_url"] = conn["endpoint_url"]
        provider = ExelyProvider(**provider_kwargs)

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

            await db.rate_calendar.update_one(
                {
                    "tenant_id": tenant_id,
                    "room_type_code": upd.room_type_code,
                    "rate_plan_code": upd.rate_plan_code,
                    "date": ds,
                },
                {"$set": set_fields},
                upsert=True,
            )
            saved += 1
            d += timedelta(days=1)

        # Push to Exely
        if provider:
            try:
                result = await provider.push_ari(
                    room_type_code=upd.room_type_code,
                    rate_plan_code=upd.rate_plan_code,
                    start_date=upd.start_date,
                    end_date=upd.end_date,
                    availability=upd.availability,
                    rate_amount=upd.rate,
                    currency=conn.get("currency", "USD"),
                    stop_sell=upd.stop_sell,
                    min_stay=upd.min_stay,
                )
                push_results.append({
                    "room_type_code": upd.room_type_code,
                    "rate_plan_code": upd.rate_plan_code,
                    "success": result.success,
                    "error": result.error if not result.success else None,
                })
            except Exception as e:
                logger.error(f"[RATE-MGR] Exely push error: {e}")
                push_results.append({
                    "room_type_code": upd.room_type_code,
                    "rate_plan_code": upd.rate_plan_code,
                    "success": False,
                    "error": str(e),
                })
        else:
            push_results.append({
                "room_type_code": upd.room_type_code,
                "rate_plan_code": upd.rate_plan_code,
                "success": False,
                "error": "Exely kimlik bilgileri bulunamadı",
            })

    all_success = all(r["success"] for r in push_results)

    return {
        "saved": saved,
        "push_results": push_results,
        "all_pushed": all_success,
        "message": "Tüm güncellemeler başarıyla uygulandı" if all_success else "Bazı güncellemeler başarısız oldu",
    }


@router.get("/room-types")
async def get_room_types(current_user: User = Depends(get_current_user)):
    """Mevcut oda tiplerini ve fiyat planlarını döndürür."""
    tenant_id = current_user.tenant_id
    conn = await db.exely_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely bağlantısı bulunamadı")

    return {
        "room_types": conn.get("room_types", []),
        "rate_plans": conn.get("rate_plans", []),
    }



@router.post("/bulk-grid-update")
async def bulk_grid_update(
    request: BulkGridUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    """
    HotelRunner-style toplu güncelleme:
    Birden fazla oda tipi + plan için aynı değerleri tek seferde uygula.
    Gün filtreleme desteği ile (ör. sadece hafta sonu).
    """
    tenant_id = current_user.tenant_id
    now = datetime.now(timezone.utc).isoformat()
    saved = 0
    push_results = []

    conn = await db.exely_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely bağlantısı bulunamadı")

    # Get credentials for Exely push
    creds = await get_decrypted_credentials(tenant_id, "exely", conn["hotel_code"])
    provider = None
    if creds:
        from domains.channel_manager.providers.exely.provider import ExelyProvider
        provider_kwargs = {
            "username": creds["username"],
            "password": creds["password"],
            "hotel_code": conn["hotel_code"],
        }
        if conn.get("endpoint_url"):
            provider_kwargs["endpoint_url"] = conn["endpoint_url"]
        provider = ExelyProvider(**provider_kwargs)

    selected_days_set = set(request.selected_days) if request.selected_days else None
    update_fields = set(request.update_fields)

    for rt_code in request.room_type_codes:
        for rp_code in request.rate_plan_codes:
            d = datetime.strptime(request.start_date, "%Y-%m-%d").date()
            end = datetime.strptime(request.end_date, "%Y-%m-%d").date()

            while d <= end:
                # Day-of-week filter: 0=Sun..6=Sat (JS convention)
                js_dow = d.isoweekday() % 7  # Python: Mon=1..Sun=7 -> JS: Sun=0..Sat=6
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

                if "rate" in update_fields and request.rate is not None:
                    set_fields["rate"] = request.rate
                if "availability" in update_fields and request.availability is not None:
                    set_fields["availability"] = request.availability
                if "min_stay" in update_fields and request.min_stay is not None:
                    set_fields["min_stay"] = request.min_stay
                if "max_stay" in update_fields and request.max_stay is not None:
                    set_fields["max_stay"] = request.max_stay
                if "stop_sell" in update_fields and request.stop_sell is not None:
                    set_fields["stop_sell"] = request.stop_sell
                if "cta" in update_fields and request.cta is not None:
                    set_fields["cta"] = request.cta
                if "ctd" in update_fields and request.ctd is not None:
                    set_fields["ctd"] = request.ctd

                await db.rate_calendar.update_one(
                    {
                        "tenant_id": tenant_id,
                        "room_type_code": rt_code,
                        "rate_plan_code": rp_code,
                        "date": ds,
                    },
                    {"$set": set_fields},
                    upsert=True,
                )
                saved += 1
                d += timedelta(days=1)

            # Push to Exely
            if provider:
                try:
                    push_rate = request.rate if "rate" in update_fields else None
                    push_avail = request.availability if "availability" in update_fields else None
                    push_stop = request.stop_sell if "stop_sell" in update_fields else None
                    push_min = request.min_stay if "min_stay" in update_fields else None

                    result = await provider.push_ari(
                        room_type_code=rt_code,
                        rate_plan_code=rp_code,
                        start_date=request.start_date,
                        end_date=request.end_date,
                        availability=push_avail,
                        rate_amount=push_rate,
                        currency=conn.get("currency", "TRY"),
                        stop_sell=push_stop,
                        min_stay=push_min,
                    )
                    push_results.append({
                        "room_type_code": rt_code,
                        "rate_plan_code": rp_code,
                        "success": result.success,
                        "error": result.error if not result.success else None,
                    })
                except Exception as e:
                    logger.error(f"[BULK-UPDATE] Exely push error: {e}")
                    push_results.append({
                        "room_type_code": rt_code,
                        "rate_plan_code": rp_code,
                        "success": False,
                        "error": str(e),
                    })

    all_success = len(push_results) > 0 and all(r["success"] for r in push_results)

    return {
        "saved": saved,
        "push_results": push_results,
        "all_pushed": all_success,
        "total_room_types": len(request.room_type_codes),
        "total_rate_plans": len(request.rate_plan_codes),
        "message": f"{saved} kayıt güncellendi" + (
            " ve Exely'ye gönderildi" if all_success else ""
        ),
    }
