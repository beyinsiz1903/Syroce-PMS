"""Forecast / Pace / Pickup raporları — RM odaklı 10/30/90 gün."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from core.security import get_current_user
from core.tenant_currency import get_tenant_currency
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.report_money import add_amount, currency_code, rounded_totals, single_amount
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.stay_night_metrics import NON_COMMERCIAL_STATUSES, allocated_revenue_for_night, as_date

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["Revenue / Forecast"])


async def _iter_bookings_in_range(db, tenant_id: str, start: datetime, end: datetime, segment: str | None = None, *, actual_only=False):
    q: dict[str, Any] = {
        "tenant_id": tenant_id,
        # Include stays which started before the window but overlap it.
        "$and": [
            {"$or": [{"check_in": {"$lt": end.date().isoformat()}}, {"check_in": {"$lt": end}}]},
            {"$or": [{"check_out": {"$gt": start.date().isoformat()}}, {"check_out": {"$gt": start}}]},
        ],
        "status": {"$in": ["checked_in", "checked_out"]} if actual_only else {"$nin": sorted(NON_COMMERCIAL_STATUSES)},
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


def _allocate_booking(booking: dict, start: datetime, end: datetime, daily: dict[str, dict[str, float]], *, preserve_currencies=False, default_currency="TRY") -> None:
    dates = _parse_booking_dates(booking)
    if not dates:
        return
    ci, co = dates
    cursor = max(ci.replace(hour=0, minute=0, second=0, microsecond=0), start)
    stay_end = min(co.replace(hour=0, minute=0, second=0, microsecond=0), end)
    while cursor < stay_end:
        key = cursor.strftime("%Y-%m-%d")
        if key in daily:
            daily[key]["rooms"] += 1
            amount = float(allocated_revenue_for_night({**booking, "status": booking.get("status") or "confirmed",
                "total_amount": booking.get("total_amount") if booking.get("total_amount") is not None else booking.get("total", 0)}, cursor.date()))
            if preserve_currencies:
                totals = daily[key].setdefault("revenue_by_currency", {})
                add_amount(totals, currency_code(booking.get("currency"), default_currency), amount)
                daily[key]["revenue"] = single_amount(totals)
            else:
                daily[key]["revenue"] += amount
        cursor += timedelta(days=1)


def _build_forecast_rows(
    daily_otb: dict[str, dict[str, float]],
    historical_daily: dict[str, dict[str, float]],
    total_rooms: int,
    today: datetime,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    weekday_stats = {day: {"rooms": 0.0, "revenue_by_currency": {}, "sample_days": 0} for day in range(7)}
    for key, values in historical_daily.items():
        weekday = datetime.fromisoformat(key).weekday()
        weekday_stats[weekday]["rooms"] += values["rooms"]
        for code, amount in (values.get("revenue_by_currency") or {"TRY": values.get("revenue") or 0}).items():
            add_amount(weekday_stats[weekday]["revenue_by_currency"], code, amount)
        weekday_stats[weekday]["sample_days"] += 1
    historical_room_nights = int(sum(item["rooms"] for item in historical_daily.values()))
    rows = []
    for day_key in sorted(daily_otb):
        values = daily_otb[day_key]
        target = datetime.fromisoformat(day_key).replace(tzinfo=UTC)
        stats = weekday_stats[target.weekday()]
        sample_days = stats["sample_days"]
        historical_rooms = stats["rooms"] / sample_days if sample_days else 0.0
        rooms_otb = values["rooms"]
        revenue_otb_by_currency = rounded_totals(values.get("revenue_by_currency") or {"TRY": values.get("revenue") or 0})
        forecast_totals = dict(revenue_otb_by_currency)
        if historical_room_nights:
            rooms_forecast = min(float(total_rooms), max(rooms_otb, historical_rooms))
            incremental_rooms = max(0.0, rooms_forecast - rooms_otb)
            basis = stats["revenue_by_currency"] if stats["rooms"] else revenue_otb_by_currency
            denominator = stats["rooms"] or rooms_otb
            for code, amount in basis.items():
                add_amount(forecast_totals, code, incremental_rooms * float(amount) / denominator if denominator else 0)
            source = "otb_plus_historical_weekday"
        else:
            rooms_forecast = min(float(total_rooms), rooms_otb)
            source = "on_the_books_only"
        days_out = max(0, (target - today).days)
        confidence = min(0.95, 0.35 + min(sample_days, 26) / 52 + (0.1 if days_out <= 14 else 0)) if historical_room_nights else 0.25
        revenue_forecast_by_currency = rounded_totals(forecast_totals)
        adr_by_currency = {code: round(amount / rooms_forecast, 2) if rooms_forecast else 0 for code, amount in revenue_forecast_by_currency.items()}
        revpar_by_currency = {code: round(amount / total_rooms, 2) if total_rooms else 0 for code, amount in revenue_forecast_by_currency.items()}
        rows.append(
            {
                "date": day_key,
                "rooms_otb": int(rooms_otb),
                "rooms_forecast": round(rooms_forecast, 1),
                "revenue_otb": single_amount(revenue_otb_by_currency),
                "revenue_otb_by_currency": revenue_otb_by_currency,
                "revenue_forecast": single_amount(revenue_forecast_by_currency),
                "revenue_forecast_by_currency": revenue_forecast_by_currency,
                "occupancy_pct": round((rooms_forecast / total_rooms) * 100, 1) if total_rooms else 0,
                "adr": single_amount(adr_by_currency),
                "adr_by_currency": adr_by_currency,
                "revpar": single_amount(revpar_by_currency),
                "revpar_by_currency": revpar_by_currency,
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
    _perm=Depends(require_op("view_reports")),
):
    """Önümüzdeki N gün için günlük occupancy / ADR / RevPAR forecast.

    Mevcut on-the-books rezervasyonlarını alır, sezonsal/tarihsel
    multiplier basit bir oranla uygular (geleceğe doğru pickup curve).
    """
    try:
        db = get_system_db()
        total_rooms = await db.rooms.count_documents({"tenant_id": user.tenant_id, "is_active": {"$ne": False}})
        default_currency, _ = await get_tenant_currency(user.tenant_id)
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        horizon = today + timedelta(days=days)

        daily: dict[str, dict[str, float]] = {}
        for i in range(days):
            d = (today + timedelta(days=i)).strftime("%Y-%m-%d")
            daily[d] = {"rooms": 0.0, "revenue": 0.0}

        async for booking in _iter_bookings_in_range(db, user.tenant_id, today, horizon, segment):
            _allocate_booking(booking, today, horizon, daily, preserve_currencies=True, default_currency=default_currency)

        history_start = today - timedelta(days=364)
        historical_daily = {}
        cursor = history_start
        while cursor < today:
            historical_daily[cursor.strftime("%Y-%m-%d")] = {"rooms": 0.0, "revenue": 0.0}
            cursor += timedelta(days=1)
        async for booking in _iter_bookings_in_range(db, user.tenant_id, history_start, today, segment, actual_only=True):
            _allocate_booking(booking, history_start, today, historical_daily, preserve_currencies=True, default_currency=default_currency)

        out, data_quality = _build_forecast_rows(daily, historical_daily, total_rooms, today)
        return {
            "horizon_days": days,
            "segment": segment,
            "total_rooms": total_rooms,
            "generated_at": datetime.now(UTC).isoformat(),
            "data_quality": data_quality,
            "daily": out,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("forecast failed")
        raise HTTPException(500, "Tahmin raporu oluşturulamadı; lütfen tekrar deneyin") from e


@router.get("/pace")
async def pace(
    target_date: str = Query(..., description="YYYY-MM-DD: hangi gün için pace?"),
    compare_year: int | None = Query(None, description="Karşılaştırılacak yıl (geçen yıl gibi)"),
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),
):
    """Booking pace: bir hedef tarih için zaman içinde rezervasyon birikimi.

    'created_at' temelli kümülatif eğri. compare_year verilirse aynı eğri
    geçen yıl aynı tarih için de döner.
    """
    db = get_system_db()
    try:
        td = datetime.fromisoformat(target_date).replace(tzinfo=UTC)
    except Exception:
        raise HTTPException(422, "target_date YYYY-MM-DD olmalı")

    async def _pace_for(date_dt: datetime) -> list[dict[str, Any]]:
        cur = db.bookings.find(
            {
                "tenant_id": user.tenant_id,
                "$or": [
                    {"check_in": {"$gte": date_dt.date().isoformat(), "$lt": (date_dt + timedelta(days=1)).date().isoformat()}},
                    {"check_in": {"$gte": date_dt, "$lt": date_dt + timedelta(days=1)}},
                ],
                "status": {"$nin": sorted(NON_COMMERCIAL_STATUSES)},
            }
        )
        by_lead: dict[int, int] = {}
        async for b in cur:
            try:
                created = as_date(b.get("created_at"))
                lead_days = (date_dt.date() - created).days
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
    _perm=Depends(require_op("view_reports")),
):
    """Son N gün içinde alınan rezervasyonların check-in tarihine göre pickup tablosu."""
    db = get_system_db()
    now = datetime.now(UTC)
    since = now - timedelta(days=period_days)
    cur = db.bookings.find(
        {
            "tenant_id": user.tenant_id,
            "$or": [{"created_at": {"$gte": since.isoformat(), "$lte": now.isoformat()}}, {"created_at": {"$gte": since, "$lte": now}}],
            "status": {"$nin": sorted(NON_COMMERCIAL_STATUSES)},
        }
    )
    by_ci_date = {}
    total_rooms = 0
    total_revenue = {}
    default_currency, _ = await get_tenant_currency(user.tenant_id)
    async for b in cur:
        arrival = as_date(b.get("check_in"))
        ci = arrival.isoformat() if arrival else None
        if not ci:
            continue
        rec = by_ci_date.setdefault(ci, {"rooms": 0, "revenue": {}})
        rec["rooms"] += 1
        code = currency_code(b.get("currency"), default_currency)
        amount = b.get("total_amount") if b.get("total_amount") is not None else b.get("total", 0)
        add_amount(rec["revenue"], code, amount)
        total_rooms += 1
        add_amount(total_revenue, code, amount)
    daily = [{"check_in": d, "rooms": int(by_ci_date[d]["rooms"]), "revenue": single_amount(by_ci_date[d]["revenue"]),
        "revenue_by_currency": rounded_totals(by_ci_date[d]["revenue"])} for d in sorted(by_ci_date)]
    return {
        "period_days": period_days,
        "total_rooms_picked": total_rooms,
        "total_revenue_picked": single_amount(total_revenue),
        "total_revenue_picked_by_currency": rounded_totals(total_revenue),
        "daily": daily,
    }
