"""
Domain Router: RMS Revenue

Revenue management system, comp-set, yield management, Faz 2 sales/revenue features.
"""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user
from models.schemas import (
    AutoPricingRequest,
    User,
)
from modules.pms_core.role_permission_service import require_op  # v98 DW

router = APIRouter(prefix="/api", tags=["rms-revenue"])

# ========================================


# ─── Endpoints (split: dashboards) ───


@router.get("/rms/dashboard-kpis")
async def get_rms_dashboard_kpis(
    period: str = "30",
    current_user: User = Depends(get_current_user)
):
    """Comprehensive RMS dashboard KPIs based on internal hotel data only."""
    clean = period.rstrip("dDmM").strip()
    days = int(clean) if clean else 30
    now = datetime.now(UTC)
    period_start = (now - timedelta(days=days)).isoformat()
    prev_period_start = (now - timedelta(days=days * 2)).isoformat()
    prev_period_end = period_start
    tid = current_user.tenant_id

    total_rooms = await db.rooms.count_documents({"tenant_id": tid})
    if total_rooms == 0:
        total_rooms = 30

    # Current period bookings
    current_bookings = await db.bookings.find(
        {"tenant_id": tid, "check_in": {"$gte": period_start},
         "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]}},
        {"_id": 0, "total_amount": 1, "nights": 1, "base_rate": 1, "channel": 1,
         "source_channel": 1, "status": 1, "check_in": 1, "room_type": 1}
    ).to_list(10000)

    # Previous period bookings (for YoY-like comparison)
    prev_bookings = await db.bookings.find(
        {"tenant_id": tid, "check_in": {"$gte": prev_period_start, "$lt": prev_period_end},
         "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]}},
        {"_id": 0, "total_amount": 1, "nights": 1}
    ).to_list(10000)

    # Cancelled bookings
    cancelled = await db.bookings.count_documents(
        {"tenant_id": tid, "check_in": {"$gte": period_start}, "status": "cancelled"}
    )
    total_with_cancelled = len(current_bookings) + cancelled

    # Calculate KPIs
    total_revenue = sum(b.get("total_amount", 0) for b in current_bookings)
    total_nights = sum(b.get("nights", 1) for b in current_bookings)
    sold_room_nights = total_nights
    total_room_nights = total_rooms * days

    adr = round(total_revenue / sold_room_nights, 0) if sold_room_nights > 0 else 0
    occupancy = round(sold_room_nights / total_room_nights * 100, 1) if total_room_nights > 0 else 0
    revpar = round(total_revenue / total_room_nights, 0) if total_room_nights > 0 else 0
    cancel_rate = round(cancelled / total_with_cancelled * 100, 1) if total_with_cancelled > 0 else 0

    # Previous period KPIs
    prev_revenue = sum(b.get("total_amount", 0) for b in prev_bookings)
    prev_nights = sum(b.get("nights", 1) for b in prev_bookings)
    prev_adr = round(prev_revenue / prev_nights, 0) if prev_nights > 0 else 0
    prev_revpar = round(prev_revenue / (total_rooms * days), 0) if total_rooms > 0 else 0
    prev_occ = round(prev_nights / total_room_nights * 100, 1) if total_room_nights > 0 else 0

    # Pickup: new bookings in last 7 days
    seven_days_ago = (now - timedelta(days=7)).isoformat()
    pickup_count = await db.bookings.count_documents(
        {"tenant_id": tid, "created_at": {"$gte": seven_days_ago},
         "status": {"$in": ["confirmed", "guaranteed"]}}
    )
    pickup_rate = round(pickup_count / 7, 1)

    # Channel breakdown
    channel_map = {}
    for b in current_bookings:
        ch = b.get("channel") or b.get("source_channel") or "direct"
        if ch not in channel_map:
            channel_map[ch] = {"count": 0, "revenue": 0, "nights": 0}
        channel_map[ch]["count"] += 1
        channel_map[ch]["revenue"] += b.get("total_amount", 0)
        channel_map[ch]["nights"] += b.get("nights", 1)

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

    # Room type breakdown
    rt_map = {}
    for b in current_bookings:
        rt = b.get("room_type", "Standard")
        if rt not in rt_map:
            rt_map[rt] = {"count": 0, "revenue": 0}
        rt_map[rt]["count"] += 1
        rt_map[rt]["revenue"] += b.get("total_amount", 0)

    room_type_perf = [{"room_type": rt, **data} for rt, data in rt_map.items()]

    # Daily occupancy trend (last N days)
    daily_trend = []
    for d in range(min(days, 30)):
        day_date = (now - timedelta(days=d)).date().isoformat()
        day_bookings = await db.bookings.count_documents({
            "tenant_id": tid,
            "check_in": {"$lte": day_date},
            "check_out": {"$gt": day_date},
            "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]},
        })
        day_occ = round(day_bookings / total_rooms * 100, 1) if total_rooms > 0 else 0
        daily_trend.append({"date": day_date, "occupancy": day_occ, "rooms_sold": day_bookings})
    daily_trend.reverse()

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

    room_types_query = {"tenant_id": tid}
    if request.room_type:
        room_types_query["name"] = request.room_type
    room_types = await db.room_types.find(room_types_query, {"_id": 0}).to_list(100)
    if not room_types:
        room_types = [{"name": "Standard", "base_rate": 4500, "min_rate": 2500, "max_rate": 9000}]

    total_rooms = await db.rooms.count_documents({"tenant_id": tid})
    if total_rooms == 0:
        total_rooms = 30

    # Load yield rules
    yield_rules = await db.yield_rules.find(
        {"tenant_id": tid, "is_active": True}, {"_id": 0}
    ).sort("priority", 1).to_list(100)

    # Load seasonal calendar
    seasons = await db.seasonal_calendar.find(
        {"tenant_id": tid, "is_active": True}, {"_id": 0}
    ).to_list(50)

    # Historical cancellation rate (last 90 days)
    ninety_days_ago = (now - timedelta(days=90)).isoformat()
    total_hist = await db.bookings.count_documents(
        {"tenant_id": tid, "check_in": {"$gte": ninety_days_ago}}
    )
    cancelled_hist = await db.bookings.count_documents(
        {"tenant_id": tid, "check_in": {"$gte": ninety_days_ago}, "status": "cancelled"}
    )
    hist_cancel_rate = cancelled_hist / total_hist if total_hist > 0 else 0.1

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
            base_rate = rt.get("base_rate", 4500)
            min_rate = rt.get("min_rate", base_rate * 0.5)
            max_rate = rt.get("max_rate", base_rate * 2)

            # Current occupancy for this date
            occ_count = await db.bookings.count_documents({
                "tenant_id": tid,
                "check_in": {"$lte": current_date},
                "check_out": {"$gt": current_date},
                "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
            })
            rt_rooms = await db.rooms.count_documents({"tenant_id": tid, "room_type": rt["name"]})
            if rt_rooms == 0:
                rt_rooms = rt.get("total_rooms", 5)
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

            # FACTOR 5: Cancellation Rate (10%)
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

