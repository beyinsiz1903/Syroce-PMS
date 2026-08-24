"""Forecast / Pace / Pickup raporları — RM odaklı 10/30/90 gün."""

from __future__ import annotations

import logging
import traceback
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from core.security import get_current_user
from core.tenant_db import get_system_db
from models.schemas import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["Revenue / Forecast"])


async def _iter_bookings_in_range(db, tenant_id: str, start: datetime, end: datetime, segment: str | None = None):
    q: dict[str, Any] = {
        "tenant_id": tenant_id,
        # Include stays which started before the window but overlap it.
        "check_in": {"$lt": end.isoformat()},
        "check_out": {"$gt": start.isoformat()},
        "status": {"$nin": ["cancelled", "no_show"]},
    }
    if segment:
        q["market_segment"] = segment
    cur = db.bookings.find(q)
    async for b in cur:
        yield b


def _parse_booking_dates(booking: dict) -> tuple[datetime, datetime] | None:
    try:
        ci_raw = booking.get("check_in")
        co_raw = booking.get("check_out")
        if not ci_raw or not co_raw:
            return None
        ci = ci_raw if isinstance(ci_raw, datetime) else datetime.fromisoformat(str(ci_raw).replace("Z", "+00:00"))
        co = co_raw if isinstance(co_raw, datetime) else datetime.fromisoformat(str(co_raw).replace("Z", "+00:00"))
        if ci.tzinfo is None:
            ci = ci.replace(tzinfo=UTC)
        if co.tzinfo is None:
            co = co.replace(tzinfo=UTC)
        if co <= ci:
            return None
        return ci, co
    except (TypeError, ValueError):
        return None


def _allocate_booking(booking: dict, start: datetime, end: datetime, daily: dict[str, dict[str, float]]) -> None:
    dates = _parse_booking_dates(booking)
    if not dates:
        return
    ci, co = dates
    nights = max((co.date() - ci.date()).days, 1)
    try:
        amount = float(booking.get("total_amount") or booking.get("total") or 0)
    except (TypeError, ValueError):
        amount = 0.0
    nightly_rate = amount / nights
    cursor = max(ci.replace(hour=0, minute=0, second=0, microsecond=0), start)
    stay_end = min(co.replace(hour=0, minute=0, second=0, microsecond=0), end)
    while cursor < stay_end:
        key = cursor.strftime("%Y-%m-%d")
        if key in daily:
            daily[key]["rooms"] += 1
            daily[key]["revenue"] += nightly_rate
        cursor += timedelta(days=1)


def _build_forecast_rows(
    daily_otb: dict[str, dict[str, float]],
    historical_daily: dict[str, dict[str, float]],
    total_rooms: int,
    today: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    weekday_stats = {day: {"rooms": 0.0, "revenue": 0.0, "sample_days": 0} for day in range(7)}
    for key, values in historical_daily.items():
        weekday = datetime.fromisoformat(key).weekday()
        weekday_stats[weekday]["rooms"] += values["rooms"]
        weekday_stats[weekday]["revenue"] += values["revenue"]
        weekday_stats[weekday]["sample_days"] += 1
    historical_room_nights = int(sum(item["rooms"] for item in historical_daily.values()))
    rows = []
    for day_key in sorted(daily_otb):
        values = daily_otb[day_key]
        target = datetime.fromisoformat(day_key).replace(tzinfo=UTC)
        stats = weekday_stats[target.weekday()]
        sample_days = stats["sample_days"]
        historical_rooms = stats["rooms"] / sample_days if sample_days else 0.0
        historical_adr = stats["revenue"] / stats["rooms"] if stats["rooms"] else 0.0
        rooms_otb = values["rooms"]
        revenue_otb = values["revenue"]
        if historical_room_nights:
            rooms_forecast = min(float(total_rooms), max(rooms_otb, historical_rooms))
            incremental_rooms = max(0.0, rooms_forecast - rooms_otb)
            otb_adr = revenue_otb / rooms_otb if rooms_otb else 0.0
            forecast_adr = historical_adr or otb_adr
            revenue_forecast = revenue_otb + incremental_rooms * forecast_adr
            source = "otb_plus_historical_weekday"
        else:
            rooms_forecast = min(float(total_rooms), rooms_otb)
            revenue_forecast = revenue_otb
            source = "on_the_books_only"
        days_out = max(0, (target - today).days)
        confidence = min(0.95, 0.35 + min(sample_days, 26) / 52 + (0.1 if days_out <= 14 else 0)) if historical_room_nights else 0.25
        adr = revenue_forecast / rooms_forecast if rooms_forecast else 0.0
        rows.append(
            {
                "date": day_key,
                "rooms_otb": int(rooms_otb),
                "rooms_forecast": round(rooms_forecast, 1),
                "revenue_otb": round(revenue_otb, 2),
                "revenue_forecast": round(revenue_forecast, 2),
                "occupancy_pct": round((rooms_forecast / total_rooms) * 100, 1),
                "adr": round(adr, 2),
                "revpar": round(revenue_forecast / total_rooms, 2),
                "historical_weekday_rooms": round(historical_rooms, 1) if historical_room_nights else None,
                "confidence": round(confidence, 2),
                "source": source,
            }
        )
    quality = {
        "historical_days": len(historical_daily),
        "historical_room_nights": historical_room_nights,
        "method": "otb_plus_historical_weekday" if historical_room_nights else "on_the_books_only",
        "warning": None if historical_room_nights else "Geçmiş konaklama verisi yok; tahmin yalnız mevcut rezervasyonları gösterir.",
    }
    return rows, quality


@router.get("/forecast")
async def forecast(
    days: int = Query(30, ge=1, le=365, description="Forecast horizon (10/30/90)"),
    segment: str | None = Query(None, description="Market segment filtresi"),
    user: User = Depends(get_current_user),
):
    """Önümüzdeki N gün için günlük occupancy / ADR / RevPAR forecast.

    Mevcut on-the-books rezervasyonlarını alır, sezonsal/tarihsel
    multiplier basit bir oranla uygular (geleceğe doğru pickup curve).
    """
    try:
        db = get_system_db()
        try:
            total_rooms = await db.rooms.count_documents({"tenant_id": user.tenant_id})
        except Exception:
            total_rooms = 0
        if not total_rooms:
            total_rooms = 1
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        horizon = today + timedelta(days=days)

        daily: dict[str, dict[str, float]] = {}
        for i in range(days + 1):
            d = (today + timedelta(days=i)).strftime("%Y-%m-%d")
            daily[d] = {"rooms": 0.0, "revenue": 0.0}

        async for booking in _iter_bookings_in_range(db, user.tenant_id, today, horizon + timedelta(days=1), segment):
            _allocate_booking(booking, today, horizon + timedelta(days=1), daily)

        history_start = today - timedelta(days=364)
        historical_daily = {}
        cursor = history_start
        while cursor < today:
            historical_daily[cursor.strftime("%Y-%m-%d")] = {"rooms": 0.0, "revenue": 0.0}
            cursor += timedelta(days=1)
        async for booking in _iter_bookings_in_range(db, user.tenant_id, history_start, today, segment):
            _allocate_booking(booking, history_start, today, historical_daily)

        out, data_quality = _build_forecast_rows(daily, historical_daily, total_rooms, today)
        return {
            "horizon_days": days,
            "segment": segment,
            "total_rooms": total_rooms,
            "generated_at": datetime.now(UTC).isoformat(),
            "data_quality": data_quality,
            "daily": out,
        }
    except Exception as e:
        logger.exception("forecast failed")
        raise HTTPException(500, f"Forecast hata: {e!s}\n{traceback.format_exc()[-400:]}")


@router.get("/pace")
async def pace(
    target_date: str = Query(..., description="YYYY-MM-DD: hangi gün için pace?"),
    compare_year: int | None = Query(None, description="Karşılaştırılacak yıl (geçen yıl gibi)"),
    user: User = Depends(get_current_user),
):
    """Booking pace: bir hedef tarih için zaman içinde rezervasyon birikimi.

    'created_at' temelli kümülatif eğri. compare_year verilirse aynı eğri
    geçen yıl aynı tarih için de döner.
    """
    db = get_system_db()
    try:
        td = datetime.fromisoformat(target_date).replace(tzinfo=UTC)
    except Exception:
        return {"error": "target_date YYYY-MM-DD olmalı"}

    async def _pace_for(date_dt: datetime) -> list[dict[str, Any]]:
        cur = db.bookings.find(
            {
                "tenant_id": user.tenant_id,
                "check_in": {
                    "$gte": date_dt.replace(hour=0, minute=0, second=0).isoformat(),
                    "$lt": (date_dt + timedelta(days=1)).isoformat(),
                },
                "status": {"$nin": ["cancelled", "no_show"]},
            }
        )
        by_lead: dict[int, int] = {}
        async for b in cur:
            try:
                created = datetime.fromisoformat(str(b.get("created_at", "")).replace("Z", "+00:00"))
                lead_days = (date_dt - created).days
                if lead_days < 0:
                    continue
                by_lead[lead_days] = by_lead.get(lead_days, 0) + 1
            except Exception:
                continue
        # En yüksek lead'den 0'a kümülatif
        if not by_lead:
            return []
        max_lead = max(by_lead.keys())
        cumulative = 0
        series = []
        for lead in range(max_lead, -1, -1):
            cumulative += by_lead.get(lead, 0)
            series.append({"days_out": lead, "rooms_on_books": cumulative})
        return series

    current = await _pace_for(td)
    out: dict[str, Any] = {"target_date": target_date, "current": current}
    if compare_year:
        try:
            comp_dt = td.replace(year=compare_year)
            out["compare_year"] = compare_year
            out["compare"] = await _pace_for(comp_dt)
        except Exception:
            out["compare"] = []
    return out


@router.get("/pickup-report")
async def pickup_report(
    period_days: int = Query(7, ge=1, le=90, description="Son N gündeki pickup"),
    user: User = Depends(get_current_user),
):
    """Son N gün içinde alınan rezervasyonların check-in tarihine göre pickup tablosu."""
    db = get_system_db()
    now = datetime.now(UTC)
    since = (now - timedelta(days=period_days)).isoformat()
    cur = db.bookings.find(
        {
            "tenant_id": user.tenant_id,
            "created_at": {"$gte": since},
            "status": {"$nin": ["cancelled", "no_show"]},
        }
    )
    by_ci_date: dict[str, dict[str, float]] = {}
    total_rooms = 0
    total_revenue = 0.0
    async for b in cur:
        ci = (b.get("check_in") or "")[:10]
        if not ci:
            continue
        rec = by_ci_date.setdefault(ci, {"rooms": 0, "revenue": 0.0})
        rec["rooms"] += 1
        rec["revenue"] += float(b.get("total_amount", 0))
        total_rooms += 1
        total_revenue += float(b.get("total_amount", 0))
    daily = [{"check_in": d, "rooms": int(by_ci_date[d]["rooms"]), "revenue": round(by_ci_date[d]["revenue"], 2)} for d in sorted(by_ci_date.keys())]
    return {
        "period_days": period_days,
        "total_rooms_picked": total_rooms,
        "total_revenue_picked": round(total_revenue, 2),
        "daily": daily,
    }
