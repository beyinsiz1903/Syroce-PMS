"""
Domain Router: RMS Revenue

Revenue management system, comp-set, yield management, Faz 2 sales/revenue features.
"""
import asyncio
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.cache import cached
from core.database import db
from core.security import get_current_user
from models.schemas import (
    AutoPricingRequest,
    User,
)
from modules.pms_core.role_permission_service import require_op  # v98 DW

router = APIRouter(prefix="/api", tags=["rms-revenue"])

# ========================================
# Demo mode constants (kept identical to legacy hardcoded fallbacks
# so that turning the flag on reproduces the previous behaviour).
DEMO_FALLBACK_TOTAL_ROOMS = 30
DEMO_FALLBACK_RT_ROOMS = 5
DEMO_FALLBACK_CANCEL_RATE = 0.10
DEMO_FALLBACK_ROOM_TYPE = {
    "name": "Standard",
    "base_rate": 4500,
    "min_rate": 2500,
    "max_rate": 9000,
}
# Pricing engine needs *some* historical signal to be meaningful.
PRICING_MIN_BOOKINGS = 10
PRICING_MIN_HISTORY_DAYS = 14
KPI_MIN_BOOKINGS = 1


def _compute_nights(check_in, check_out) -> int:
    """Bookings collection'da `nights` field'ı stored DEĞİL — check_out − check_in
    farkından hesaplanır. Boş/format bozuksa 1 fallback (en az 1 gece)."""
    try:
        ci = str(check_in or "")[:10]
        co = str(check_out or "")[:10]
        if not ci or not co:
            return 1
        ci_d = datetime.fromisoformat(ci)
        co_d = datetime.fromisoformat(co)
        n = (co_d - ci_d).days
        return max(1, n)
    except Exception:
        return 1


async def is_rms_demo_mode(tenant_id: str) -> bool:
    """Read tenant.settings.rms_demo_mode (default False).

    When True the legacy hardcoded fallbacks are used so a freshly
    provisioned tenant can demo the RMS module without real data.
    """
    doc = await db.tenants.find_one(
        {"id": tenant_id}, {"_id": 0, "settings": 1}
    )
    if not doc:
        return False
    return bool((doc.get("settings") or {}).get("rms_demo_mode", False))


async def _build_data_quality(tenant_id: str, period_days: int = 30) -> dict:
    """Inspect tenant's RMS-relevant data and report sufficiency."""
    now = datetime.now(UTC)
    period_start_iso = (now - timedelta(days=period_days)).isoformat()

    # Perf: 5 count + 1 find (earliest) önceden seri yapılıyordu (~6×RTT).
    # Hepsi bağımsız — tek asyncio.gather ile paralel. Bu helper dashboard-kpis
    # endpoint'inin dış gather'ı içinde de çalıştığından, içeride seri kalması
    # dış gather'ın tail-latency'sini belirliyordu.
    (
        rooms_count,
        room_types_count,
        yield_rules_count,
        seasons_count,
        bookings_in_period,
        earliest,
    ) = await asyncio.gather(
        db.rooms.count_documents({"tenant_id": tenant_id}),
        db.room_types.count_documents({"tenant_id": tenant_id}),
        db.yield_rules.count_documents(
            {"tenant_id": tenant_id, "is_active": True}
        ),
        db.seasonal_calendar.count_documents(
            {"tenant_id": tenant_id, "is_active": True}
        ),
        db.bookings.count_documents({
            "tenant_id": tenant_id,
            "check_in": {"$gte": period_start_iso},
            "status": {"$in": [
                "confirmed", "guaranteed", "checked_in", "checked_out"
            ]},
        }),
        db.bookings.find(
            {"tenant_id": tenant_id},
            {"_id": 0, "created_at": 1, "check_in": 1},
        ).sort("created_at", 1).limit(1).to_list(1),
    )

    days_of_history = 0
    if earliest:
        try:
            stamp = earliest[0].get("created_at") or earliest[0].get("check_in")
            if stamp:
                stamp_dt = datetime.fromisoformat(str(stamp).replace("Z", "+00:00"))
                if stamp_dt.tzinfo is None:
                    stamp_dt = stamp_dt.replace(tzinfo=UTC)
                days_of_history = max(0, (now - stamp_dt).days)
        except Exception:
            days_of_history = 0

    warnings: list[str] = []
    if rooms_count == 0:
        warnings.append("no_rooms")
    if room_types_count == 0:
        warnings.append("no_room_types")
    if bookings_in_period < KPI_MIN_BOOKINGS:
        warnings.append("no_bookings_in_period")
    if bookings_in_period < PRICING_MIN_BOOKINGS:
        warnings.append("insufficient_bookings_for_pricing")
    if days_of_history < PRICING_MIN_HISTORY_DAYS:
        warnings.append("insufficient_history_for_pricing")
    if yield_rules_count == 0:
        warnings.append("no_yield_rules")
    if seasons_count == 0:
        warnings.append("no_seasons")

    sufficient_for_kpis = (
        rooms_count > 0 and bookings_in_period >= KPI_MIN_BOOKINGS
    )
    sufficient_for_pricing = (
        rooms_count > 0
        and room_types_count > 0
        and bookings_in_period >= PRICING_MIN_BOOKINGS
        and days_of_history >= PRICING_MIN_HISTORY_DAYS
    )

    return {
        "has_rooms": rooms_count > 0,
        "rooms_count": rooms_count,
        "has_room_types": room_types_count > 0,
        "room_types_count": room_types_count,
        "has_bookings": bookings_in_period > 0,
        "bookings_count": bookings_in_period,
        "days_of_history": days_of_history,
        "yield_rules_count": yield_rules_count,
        "seasons_count": seasons_count,
        "sufficient_for_kpis": sufficient_for_kpis,
        "sufficient_for_pricing": sufficient_for_pricing,
        "warnings": warnings,
        "thresholds": {
            "min_bookings_for_kpis": KPI_MIN_BOOKINGS,
            "min_bookings_for_pricing": PRICING_MIN_BOOKINGS,
            "min_history_days_for_pricing": PRICING_MIN_HISTORY_DAYS,
        },
    }


# ─── Endpoints (split: dashboards) ───


@router.get("/rms/settings")
async def get_rms_settings(current_user: User = Depends(get_current_user)):
    """Return RMS-specific tenant settings (currently just demo mode flag)."""
    doc = await db.tenants.find_one(
        {"id": current_user.tenant_id}, {"_id": 0, "settings": 1}
    )
    settings = (doc or {}).get("settings") or {}
    return {
        "rms_demo_mode": bool(settings.get("rms_demo_mode", False)),
    }


class RMSSettingsUpdate(BaseModel):
    rms_demo_mode: bool


@router.patch("/rms/settings")
async def update_rms_settings(
    payload: RMSSettingsUpdate,
    current_user: User = Depends(get_current_user),
):
    """Toggle RMS demo mode (super_admin / hotel admin only)."""
    if current_user.role not in ("super_admin", "admin", "hotel_admin"):
        raise HTTPException(
            status_code=403,
            detail="Only super_admin or hotel admin can change RMS settings",
        )
    await db.tenants.update_one(
        {"id": current_user.tenant_id},
        {"$set": {
            "settings.rms_demo_mode": bool(payload.rms_demo_mode),
            "settings.rms_demo_mode_updated_at": datetime.now(UTC).isoformat(),
            "settings.rms_demo_mode_updated_by": current_user.email,
        }},
    )
    # Toggle değişti — dashboard cache'ini hemen düşür ki eski demo değerleri görünmesin.
    try:
        from cache_manager import cache as _cache  # noqa: WPS433
        if _cache is not None:
            _cache.safe_invalidate(current_user.tenant_id, "rms_dashboard_kpis")
    except Exception:
        pass
    return {"rms_demo_mode": bool(payload.rms_demo_mode)}


@router.get("/rms/dashboard-kpis")
@cached(ttl=300, key_prefix="rms_dashboard_kpis")  # 5 min cache; period+tenant scoped
async def get_rms_dashboard_kpis(
    period: str = "30",
    # `?refresh=1` (UI Yenile butonu) → cache_manager.cached wrapper'ında `_nocache`
    # kwarg'ı pop edilir, fresh fetch yapılır + sonuç cache'e tazelenir. Query alias
    # ile public adı `refresh`, internal adı `_nocache`.
    _nocache: bool = Query(False, alias="refresh"),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_revenue")),  # RBAC — finance-grade dashboard
):
    """Comprehensive RMS dashboard KPIs based on internal hotel data only."""
    clean = period.rstrip("dDmM").strip()
    days = int(clean) if clean else 30
    now = datetime.now(UTC)
    period_start = (now - timedelta(days=days)).isoformat()
    prev_period_start = (now - timedelta(days=days * 2)).isoformat()
    prev_period_end = period_start
    tid = current_user.tenant_id
    demo_mode = await is_rms_demo_mode(tid)

    # Daily-trend window: up to last 30 days within the requested period.
    trend_days = min(days, 30)
    trend_window_start = (now - timedelta(days=trend_days)).date().isoformat()
    trend_window_end_exclusive = (now + timedelta(days=1)).date().isoformat()

    seven_days_ago = (now - timedelta(days=7)).isoformat()
    booking_statuses = ["confirmed", "guaranteed", "checked_in", "checked_out"]

    # Run independent reads in parallel — fan-out replaces serial 5-call chain.
    (
        real_total_rooms,
        current_bookings,
        prev_bookings,
        cancelled,
        pickup_count,
        overlap_bookings,
        data_quality,
    ) = await asyncio.gather(
        db.rooms.count_documents({"tenant_id": tid}),
        db.bookings.find(
            {"tenant_id": tid, "check_in": {"$gte": period_start},
             "status": {"$in": booking_statuses}},
            {"_id": 0, "total_amount": 1, "nights": 1, "base_rate": 1, "channel": 1,
             "source_channel": 1, "status": 1, "check_in": 1, "check_out": 1,
             "room_type": 1, "room_id": 1, "room_number": 1},
        ).to_list(10000),
        db.bookings.find(
            {"tenant_id": tid, "check_in": {"$gte": prev_period_start, "$lt": prev_period_end},
             "status": {"$in": booking_statuses}},
            {"_id": 0, "total_amount": 1, "nights": 1, "check_in": 1, "check_out": 1},
        ).to_list(10000),
        db.bookings.count_documents(
            {"tenant_id": tid, "check_in": {"$gte": period_start}, "status": "cancelled"}
        ),
        db.bookings.count_documents(
            {"tenant_id": tid, "created_at": {"$gte": seven_days_ago},
             "status": {"$in": ["confirmed", "guaranteed"]}}
        ),
        db.bookings.find(
            {"tenant_id": tid,
             "status": {"$in": booking_statuses},
             "check_in": {"$lt": trend_window_end_exclusive},
             "check_out": {"$gt": trend_window_start}},
            {"_id": 0, "check_in": 1, "check_out": 1},
        ).to_list(20000),
        _build_data_quality(tid, period_days=days),
    )

    if real_total_rooms == 0 and demo_mode:
        total_rooms = DEMO_FALLBACK_TOTAL_ROOMS
    else:
        total_rooms = real_total_rooms

    # Bookings.nights field stored DEĞİL — check_out − check_in farkından hesaplanır.
    # `b.get("nights", 1)` her zaman 1 dönüyordu → ADR/RevPAR ve oda-tipi/kanal
    # gece sayıları gerçek değer yerine her rezervasyona "1 gece" atıyordu.
    for b in current_bookings:
        b["_computed_nights"] = (
            int(b["nights"]) if isinstance(b.get("nights"), (int, float)) and b.get("nights")
            else _compute_nights(b.get("check_in"), b.get("check_out"))
        )
    for b in prev_bookings:
        b["_computed_nights"] = (
            int(b["nights"]) if isinstance(b.get("nights"), (int, float)) and b.get("nights")
            else _compute_nights(b.get("check_in"), b.get("check_out"))
        )

    # Bookings'te `room_type` alanı stored değil; `room_id` üzerinden rooms
    # koleksiyonundan çözülür. Dashboard daha önce her rezervasyonu "Standard"
    # olarak gruplamıştı — gerçek oda tipi dağılımı görünmüyordu.
    room_ids = {b.get("room_id") for b in current_bookings if b.get("room_id")}
    room_type_map: dict[str, str] = {}
    if room_ids:
        rooms_docs = await db.rooms.find(
            {"tenant_id": tid, "id": {"$in": list(room_ids)}},
            {"_id": 0, "id": 1, "room_type": 1, "type": 1},
        ).to_list(len(room_ids))
        for rd in rooms_docs:
            rid = rd.get("id")
            if rid:
                room_type_map[rid] = rd.get("room_type") or rd.get("type") or "Standard"

    total_with_cancelled = len(current_bookings) + cancelled

    # Calculate KPIs
    total_revenue = sum(b.get("total_amount", 0) for b in current_bookings)
    total_nights = sum(b["_computed_nights"] for b in current_bookings)
    sold_room_nights = total_nights
    total_room_nights = total_rooms * days

    adr = round(total_revenue / sold_room_nights, 0) if sold_room_nights > 0 else 0
    occupancy = round(sold_room_nights / total_room_nights * 100, 1) if total_room_nights > 0 else 0
    revpar = round(total_revenue / total_room_nights, 0) if total_room_nights > 0 else 0
    cancel_rate = round(cancelled / total_with_cancelled * 100, 1) if total_with_cancelled > 0 else 0

    # Previous period KPIs
    prev_revenue = sum(b.get("total_amount", 0) for b in prev_bookings)
    prev_nights = sum(b["_computed_nights"] for b in prev_bookings)
    prev_adr = round(prev_revenue / prev_nights, 0) if prev_nights > 0 else 0
    prev_revpar = round(prev_revenue / (total_rooms * days), 0) if total_rooms > 0 else 0
    prev_occ = round(prev_nights / total_room_nights * 100, 1) if total_room_nights > 0 else 0

    pickup_rate = round(pickup_count / 7, 1)

    # Channel breakdown
    channel_map = {}
    for b in current_bookings:
        ch = b.get("channel") or b.get("source_channel") or "direct"
        if ch not in channel_map:
            channel_map[ch] = {"count": 0, "revenue": 0, "nights": 0}
        channel_map[ch]["count"] += 1
        channel_map[ch]["revenue"] += b.get("total_amount", 0)
        channel_map[ch]["nights"] += b["_computed_nights"]

    channel_labels = {"direct": "Direkt", "booking_com": "Booking.com",
                      "expedia": "Expedia", "airbnb": "Airbnb", "own_website": "Web Sitesi"}
    channels = []
    for ch, data in channel_map.items():
        channels.append({
            "channel": ch,
            "label": channel_labels.get(ch, ch),
            "bookings": data["count"],
            "revenue": round(data["revenue"], 0),
            "nights": data["nights"],
            "share_pct": round(data["revenue"] / total_revenue * 100, 1) if total_revenue > 0 else 0,
        })
    channels.sort(key=lambda x: x["revenue"], reverse=True)

    # Room type breakdown — bookings.room_id → rooms.room_type lookup,
    # b.get("room_type") legacy/external (Exely/HotelRunner) için fallback.
    rt_map = {}
    for b in current_bookings:
        rt = (
            b.get("room_type")
            or room_type_map.get(b.get("room_id"))
            or "Belirtilmemiş"
        )
        if rt not in rt_map:
            rt_map[rt] = {"count": 0, "revenue": 0, "nights": 0}
        rt_map[rt]["count"] += 1
        rt_map[rt]["revenue"] += b.get("total_amount", 0)
        rt_map[rt]["nights"] += b["_computed_nights"]

    room_type_perf = [{"room_type": rt, **data} for rt, data in rt_map.items()]

    # Daily occupancy trend — single fetch, computed in-memory.
    # Replaces the previous 30 sequential count_documents calls.
    day_dates = [(now - timedelta(days=d)).date().isoformat() for d in range(trend_days)]
    day_counts = dict.fromkeys(day_dates, 0)
    for b in overlap_bookings:
        ci = (b.get("check_in") or "")[:10]
        co = (b.get("check_out") or "")[:10]
        if not ci or not co:
            continue
        for dd in day_dates:
            if ci <= dd < co:
                day_counts[dd] += 1
    daily_trend = [
        {
            "date": dd,
            "occupancy": round(day_counts[dd] / total_rooms * 100, 1) if total_rooms > 0 else 0,
            "rooms_sold": day_counts[dd],
        }
        for dd in day_dates
    ]
    daily_trend.reverse()
    # Reflect demo mode in the contract so the frontend can show a badge.
    data_quality["demo_mode"] = demo_mode
    data_quality["effective_total_rooms"] = total_rooms

    return {
        "kpis": {
            "occupancy": occupancy,
            "occupancy_prev": prev_occ,
            "adr": adr,
            "adr_prev": prev_adr,
            "revpar": revpar,
            "revpar_prev": prev_revpar,
            "total_revenue": round(total_revenue, 0),
            "total_bookings": len(current_bookings),
            "cancel_rate": cancel_rate,
            "pickup_rate": pickup_rate,
            "pickup_count_7d": pickup_count,
            "sold_room_nights": sold_room_nights,
            "total_room_nights": total_room_nights,
        },
        "channels": channels,
        "room_type_performance": room_type_perf,
        "daily_trend": daily_trend,
        "period_days": days,
        "data_quality": data_quality,
    }




@router.get("/rms/channel-performance")
async def get_channel_performance(
    months: int = 6,
    current_user: User = Depends(get_current_user)
):
    """Monthly channel performance breakdown."""
    tid = current_user.tenant_id
    now = datetime.now(UTC)
    result = []

    for m in range(months):
        month_start = (now - timedelta(days=30 * (m + 1)))
        month_end = (now - timedelta(days=30 * m))
        month_label = month_start.strftime("%Y-%m")

        bookings = await db.bookings.find(
            {"tenant_id": tid,
             "check_in": {"$gte": month_start.isoformat(), "$lt": month_end.isoformat()},
             "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]}},
            {"_id": 0, "channel": 1, "source_channel": 1, "total_amount": 1}
        ).to_list(5000)

        ch_data = {}
        for b in bookings:
            ch = b.get("channel") or b.get("source_channel") or "direct"
            if ch not in ch_data:
                ch_data[ch] = {"count": 0, "revenue": 0}
            ch_data[ch]["count"] += 1
            ch_data[ch]["revenue"] += b.get("total_amount", 0)

        result.append({"month": month_label, "channels": ch_data, "total_bookings": len(bookings)})

    result.reverse()
    return {"monthly_performance": result}


# ── YIELD RULES CRUD ──

class YieldRuleCreate(BaseModel):
    name: str
    description: str = ""
    condition_type: str
    condition_value: float | str
    action_type: str
    action_value: float
    is_active: bool = True
    priority: int = 10
    room_types: list[str] = []




@router.get("/rms/yield-rules")
async def get_yield_rules(current_user: User = Depends(get_current_user)):
    rules = await db.yield_rules.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("priority", 1).to_list(100)
    return {"rules": rules, "count": len(rules)}




@router.post("/rms/yield-rules")
async def create_yield_rule(
    rule: YieldRuleCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v98 DW
):
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        **rule.model_dump(),
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.id,
    }
    await db.yield_rules.insert_one(doc)
    doc.pop("_id", None)
    return doc




@router.put("/rms/yield-rules/{rule_id}")
async def update_yield_rule(
    rule_id: str,
    rule: YieldRuleCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v98 DW
):
    result = await db.yield_rules.update_one(
        {"id": rule_id, "tenant_id": current_user.tenant_id},
        {"$set": {**rule.model_dump(), "updated_at": datetime.now(UTC).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"message": "Kural guncellendi", "id": rule_id}




@router.delete("/rms/yield-rules/{rule_id}")
async def delete_yield_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v98 DW
):
    result = await db.yield_rules.delete_one(
        {"id": rule_id, "tenant_id": current_user.tenant_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"message": "Kural silindi"}


# ── SEASONAL CALENDAR CRUD ──

class SeasonCreate(BaseModel):
    name: str
    season_type: str
    start_date: str
    end_date: str
    rate_multiplier: float = 1.0
    min_stay: int = 1
    color: str = "#3b82f6"
    is_active: bool = True




@router.get("/rms/seasonal-calendar")
async def get_seasonal_calendar(current_user: User = Depends(get_current_user)):
    seasons = await db.seasonal_calendar.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0}
    ).sort("start_date", 1).to_list(100)
    return {"seasons": seasons, "count": len(seasons)}




@router.post("/rms/seasonal-calendar")
async def create_season(
    season: SeasonCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v98 DW
):
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        **season.model_dump(),
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.seasonal_calendar.insert_one(doc)
    doc.pop("_id", None)
    return doc




@router.put("/rms/seasonal-calendar/{season_id}")
async def update_season(
    season_id: str,
    season: SeasonCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v98 DW
):
    result = await db.seasonal_calendar.update_one(
        {"id": season_id, "tenant_id": current_user.tenant_id},
        {"$set": {**season.model_dump(), "updated_at": datetime.now(UTC).isoformat()}}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Season not found")
    return {"message": "Sezon guncellendi", "id": season_id}




@router.delete("/rms/seasonal-calendar/{season_id}")
async def delete_season(
    season_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v98 DW
):
    result = await db.seasonal_calendar.delete_one(
        {"id": season_id, "tenant_id": current_user.tenant_id}
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Season not found")
    return {"message": "Sezon silindi"}


# ── REWRITTEN AUTO-PRICING (7 Internal Factors) ──



@router.post("/rms/generate-pricing")
async def generate_internal_pricing(
    request: AutoPricingRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_rates")),  # v98 DW
):
    """Generate pricing recommendations using 7 internal data factors (no competitor dependency)."""
    start = datetime.fromisoformat(request.start_date)
    end = datetime.fromisoformat(request.end_date)
    days_count = (end - start).days + 1
    tid = current_user.tenant_id
    now = datetime.now(UTC)
    demo_mode = await is_rms_demo_mode(tid)

    # Data sufficiency guard — refuse to invent numbers in prod mode.
    data_quality = await _build_data_quality(tid, period_days=30)
    if not demo_mode and not data_quality["sufficient_for_pricing"]:
        raise HTTPException(
            status_code=422,
            detail={
                "error": "insufficient_data_for_pricing",
                "message": (
                    "Fiyat onerisi uretmek icin yeterli veri yok. "
                    "Once oda tipi tanimlayin, oda envanteri girin "
                    "ve en az birkac gun rezervasyon verisi biriktirin. "
                    "Sandbox/test icin RMS Demo modunu acabilirsiniz."
                ),
                "data_quality": data_quality,
            },
        )

    room_types_query = {"tenant_id": tid}
    if request.room_type:
        room_types_query["name"] = request.room_type
    room_types = await db.room_types.find(room_types_query, {"_id": 0}).to_list(100)
    if not room_types:
        if demo_mode:
            room_types = [dict(DEMO_FALLBACK_ROOM_TYPE)]
        else:
            # Should be caught by sufficiency guard, but be defensive.
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "no_room_types",
                    "message": (
                        "Once oda tipi tanimlamaniz gerekiyor."
                    ),
                },
            )

    # Load yield rules
    yield_rules = await db.yield_rules.find(
        {"tenant_id": tid, "is_active": True}, {"_id": 0}
    ).sort("priority", 1).to_list(100)

    # Load seasonal calendar
    seasons = await db.seasonal_calendar.find(
        {"tenant_id": tid, "is_active": True}, {"_id": 0}
    ).to_list(50)

    # Historical cancellation rate (last 90 days). When no history exists
    # we leave the signal *unset* in prod mode — the cancel-rate factor
    # in the loop will then skip its multiplier instead of inventing 10%.
    ninety_days_ago = (now - timedelta(days=90)).isoformat()
    total_hist = await db.bookings.count_documents(
        {"tenant_id": tid, "check_in": {"$gte": ninety_days_ago}}
    )
    cancelled_hist = await db.bookings.count_documents(
        {"tenant_id": tid, "check_in": {"$gte": ninety_days_ago}, "status": "cancelled"}
    )
    if total_hist > 0:
        hist_cancel_rate = cancelled_hist / total_hist
    elif demo_mode:
        hist_cancel_rate = DEMO_FALLBACK_CANCEL_RATE
    else:
        hist_cancel_rate = None

    # Channel performance (last 30 days)
    thirty_days = (now - timedelta(days=30)).isoformat()
    recent_bookings = await db.bookings.find(
        {"tenant_id": tid, "created_at": {"$gte": thirty_days},
         "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]}},
        {"_id": 0, "channel": 1, "total_amount": 1, "nights": 1}
    ).to_list(5000)

    channel_adr = {}
    for b in recent_bookings:
        ch = b.get("channel", "direct")
        if ch not in channel_adr:
            channel_adr[ch] = {"revenue": 0, "nights": 0}
        channel_adr[ch]["revenue"] += b.get("total_amount", 0)
        channel_adr[ch]["nights"] += b.get("nights", 1)

    # YoY comparison data
    year_ago_start = (start - timedelta(days=365)).isoformat()
    year_ago_end = (end - timedelta(days=365)).isoformat()
    yoy_bookings = await db.bookings.count_documents({
        "tenant_id": tid,
        "check_in": {"$gte": year_ago_start, "$lte": year_ago_end},
        "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]},
    })

    recommendations = []

    for day_offset in range(days_count):
        current_date = (start + timedelta(days=day_offset)).date().isoformat()
        date_obj = datetime.fromisoformat(current_date).replace(tzinfo=UTC)
        day_of_week = date_obj.weekday()
        month = date_obj.month
        days_to_arrival = (date_obj - now).days

        for rt in room_types:
            raw_base = rt.get("base_rate")
            if raw_base in (None, 0):
                if not demo_mode:
                    # Prod mode: skip room types missing rate config so we
                    # don't fabricate a price out of thin air.
                    continue
                raw_base = DEMO_FALLBACK_ROOM_TYPE["base_rate"]
            base_rate = raw_base
            min_rate = rt.get("min_rate") or base_rate * 0.5
            max_rate = rt.get("max_rate") or base_rate * 2

            # Current occupancy for this date
            occ_count = await db.bookings.count_documents({
                "tenant_id": tid,
                "check_in": {"$lte": current_date},
                "check_out": {"$gt": current_date},
                "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
            })
            rt_rooms = await db.rooms.count_documents({"tenant_id": tid, "room_type": rt["name"]})
            if rt_rooms == 0:
                # In demo mode, fall back to legacy 5-rooms guess so the
                # rest of the algorithm has something to chew on. In prod
                # mode, prefer the room_type's declared inventory if any,
                # otherwise leave 0 so occupancy_pct stays 0 (no false
                # signal).
                if demo_mode:
                    rt_rooms = rt.get("total_rooms", DEMO_FALLBACK_RT_ROOMS)
                else:
                    rt_rooms = rt.get("total_rooms", 0) or 0
            occupancy_pct = (occ_count / rt_rooms * 100) if rt_rooms > 0 else 0

            # Booking pace (last 7 days for this target date)
            seven_ago = (now - timedelta(days=7)).isoformat()
            pace_count = await db.bookings.count_documents({
                "tenant_id": tid,
                "check_in": {"$lte": current_date},
                "check_out": {"$gt": current_date},
                "created_at": {"$gte": seven_ago},
            })
            daily_pace = pace_count / 7

            multiplier = 1.0
            reasons = []

            # FACTOR 1: Occupancy (25%)
            if occupancy_pct > 90:
                multiplier *= 1.25
                reasons.append(f"Cok yuksek doluluk ({occupancy_pct:.0f}%): +25%")
            elif occupancy_pct > 75:
                multiplier *= 1.15
                reasons.append(f"Yuksek doluluk ({occupancy_pct:.0f}%): +15%")
            elif occupancy_pct > 50:
                multiplier *= 1.05
                reasons.append(f"Orta doluluk ({occupancy_pct:.0f}%): +5%")
            elif occupancy_pct > 25:
                multiplier *= 0.95
                reasons.append(f"Dusuk doluluk ({occupancy_pct:.0f}%): -5%")
            else:
                multiplier *= 0.85
                reasons.append(f"Cok dusuk doluluk ({occupancy_pct:.0f}%): -15%")

            # FACTOR 2: Booking Pace / Pickup (20%)
            if daily_pace > 2:
                multiplier *= 1.10
                reasons.append(f"Guclu rez. hizi ({daily_pace:.1f}/gun): +10%")
            elif daily_pace > 1:
                multiplier *= 1.05
                reasons.append(f"Iyi rez. hizi ({daily_pace:.1f}/gun): +5%")
            elif daily_pace < 0.3 and occupancy_pct < 50:
                multiplier *= 0.92
                reasons.append(f"Yavas rez. hizi ({daily_pace:.1f}/gun): -8%")

            # FACTOR 3: Lead Time (15%)
            if days_to_arrival <= 3:
                if occupancy_pct < 50:
                    multiplier *= 0.90
                    reasons.append("Son dakika + dusuk doluluk: -10%")
                else:
                    multiplier *= 1.08
                    reasons.append("Son dakika + yuksek doluluk: +8%")
            elif days_to_arrival <= 14:
                multiplier *= 1.03
                reasons.append("Kisa vadeli talep: +3%")
            elif days_to_arrival > 60:
                multiplier *= 0.95
                reasons.append("Erken rezervasyon: -5%")

            # FACTOR 4: Day of Week & Seasonality (15%)
            is_weekend = day_of_week in [4, 5]
            if is_weekend:
                multiplier *= 1.12
                reasons.append("Hafta sonu talebi: +12%")

            # Check seasonal calendar
            season_applied = False
            for s in seasons:
                if s.get("start_date", "") <= current_date <= s.get("end_date", ""):
                    sm = s.get("rate_multiplier", 1.0)
                    multiplier *= sm
                    reasons.append(f"{s['name']} ({sm:.0%})")
                    season_applied = True
                    break
            if not season_applied:
                if month in [6, 7, 8]:
                    multiplier *= 1.20
                    reasons.append("Yaz sezonu: +20%")
                elif month in [12, 1]:
                    multiplier *= 1.10
                    reasons.append("Kis tatili: +10%")

            # FACTOR 5: Cancellation Rate (10%) — only apply if we have a
            # real measurement. None means no booking history yet.
            if hist_cancel_rate is not None:
                if hist_cancel_rate > 0.2:
                    multiplier *= 1.05
                    reasons.append(f"Yuksek iptal orani ({hist_cancel_rate:.0%}): +5% (telafi)")
                elif hist_cancel_rate < 0.05:
                    multiplier *= 0.98
                    reasons.append("Dusuk iptal orani: -2%")

            # FACTOR 6: Channel Performance (10%)
            best_ch = max(channel_adr.items(), key=lambda x: x[1]["revenue"] / max(x[1]["nights"], 1), default=None)
            if best_ch and best_ch[1]["nights"] > 0:
                best_adr = best_ch[1]["revenue"] / best_ch[1]["nights"]
                if best_adr > base_rate * 1.1:
                    multiplier *= 1.03
                    reasons.append("Kanallar yuksek ADR sagliyor: +3%")

            # FACTOR 7: YoY Comparison (5%)
            if yoy_bookings > 0:
                yoy_ratio = len(recent_bookings) / max(yoy_bookings, 1)
                if yoy_ratio > 1.2:
                    multiplier *= 1.04
                    reasons.append("Gecen yila gore talep artisi: +4%")
                elif yoy_ratio < 0.8:
                    multiplier *= 0.97
                    reasons.append("Gecen yila gore talep dususu: -3%")

            # Apply yield rules
            for yr in yield_rules:
                if yr.get("room_types") and rt["name"] not in yr["room_types"]:
                    continue
                ct = yr["condition_type"]
                cv = yr["condition_value"]
                at = yr["action_type"]
                av = yr["action_value"]

                rule_applies = False
                if ct == "occupancy_above" and occupancy_pct > float(cv):
                    rule_applies = True
                elif ct == "occupancy_below" and occupancy_pct < float(cv):
                    rule_applies = True
                elif ct == "lead_time_below" and days_to_arrival < float(cv) and occupancy_pct < 60:
                    rule_applies = True
                elif ct == "lead_time_above" and days_to_arrival > float(cv):
                    rule_applies = True
                elif ct == "day_of_week":
                    dow_names = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
                    if dow_names[day_of_week] in str(cv).lower():
                        rule_applies = True

                if rule_applies:
                    if at == "increase_percent":
                        multiplier *= (1 + av / 100)
                        reasons.append(f"Kural '{yr['name']}': +{av}%")
                    elif at == "decrease_percent":
                        multiplier *= (1 - av / 100)
                        reasons.append(f"Kural '{yr['name']}': -{av}%")

            suggested_rate = round(base_rate * multiplier)
            suggested_rate = max(min_rate, min(suggested_rate, max_rate))

            # Confidence scoring
            conf = 0.3
            if occ_count > 0:
                conf += 0.2
            if pace_count > 0:
                conf += 0.15
            if days_to_arrival < 30:
                conf += 0.15
            if len(recent_bookings) > 20:
                conf += 0.1
            if season_applied:
                conf += 0.1
            conf = min(conf, 0.95)

            rec = {
                "id": str(uuid.uuid4()),
                "tenant_id": tid,
                "date": current_date,
                "room_type": rt["name"],
                "current_rate": base_rate,
                "suggested_rate": suggested_rate,
                "change_pct": round((multiplier - 1) * 100, 1),
                "occupancy": round(occupancy_pct, 1),
                "booking_pace": round(daily_pace, 2),
                "confidence": round(conf, 2),
                "confidence_level": "Yuksek" if conf >= 0.7 else ("Orta" if conf >= 0.45 else "Dusuk"),
                "reasoning": " | ".join(reasons),
                "reasons": reasons,
                "is_weekend": is_weekend,
                "lead_time_days": days_to_arrival,
                "status": "pending",
                "generated_at": now.isoformat(),
            }
            recommendations.append(rec)

    if recommendations:
        await db.rms_pricing_recommendations.insert_many([r.copy() for r in recommendations])

    return {
        "message": f"{len(recommendations)} fiyat onerisi uretildi",
        "recommendations": recommendations,
        "summary": {
            "total": len(recommendations),
            "avg_change": round(sum(r["change_pct"] for r in recommendations) / len(recommendations), 1) if recommendations else 0,
            "increases": sum(1 for r in recommendations if r["change_pct"] > 0),
            "decreases": sum(1 for r in recommendations if r["change_pct"] < 0),
            "avg_confidence": round(sum(r["confidence"] for r in recommendations) / len(recommendations), 2) if recommendations else 0,
        },
    }

