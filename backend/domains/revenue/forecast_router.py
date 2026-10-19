"""Forecast / Pace / Pickup raporları — RM odaklı 10/30/90 gün."""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from core.security import get_current_user
from core.tenant_currency import get_tenant_currency
from core.tenant_db import get_system_db
from models.schemas import User
from modules.pms_core.report_money import add_amount, currency_code, money, rounded, rounded_totals, single_amount
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.stay_night_metrics import (
    ACTUAL_OCCUPANCY_STATUSES,
    OCCUPYING_STATUSES,
    allocated_revenue_for_night,
    as_date,
    booking_nights,
    booking_occupies_night,
    calculate_stay_night_metrics,
    room_block_overlap_match,
    stay_overlap_match,
)

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
        "status": {"$in": sorted(ACTUAL_OCCUPANCY_STATUSES if actual_only else OCCUPYING_STATUSES)},
    }
    if segment:
        q["market_segment"] = segment
    cur = db.bookings.find(q)
    async for b in cur:
        yield b


def _parse_booking_dates(booking: dict) -> tuple[datetime, datetime] | None:
    try:
        ci_day, co_day = as_date(booking.get("check_in")), as_date(booking.get("check_out"))
        if not ci_day or not co_day:
            return None
        ci, co = datetime.combine(ci_day, datetime.min.time(), UTC), datetime.combine(co_day, datetime.min.time(), UTC)
        if co <= ci:
            return None
        return ci, co
    except (TypeError, ValueError):
        return None


def _allocate_booking(booking: dict, start: datetime, end: datetime, daily: dict[str, dict[str, float]], *, preserve_currencies=False, default_currency="TRY", actual_only=False) -> None:
    dates = _parse_booking_dates(booking)
    if not dates:
        return
    ci, co = dates
    normalized = {**booking, "status": booking.get("status") or "confirmed",
        "total_amount": booking.get("total_amount") if booking.get("total_amount") is not None else booking.get("total", 0)}
    actual_stay = str(normalized["status"]).strip().lower() in ACTUAL_OCCUPANCY_STATUSES
    cursor = max(ci.replace(hour=0, minute=0, second=0, microsecond=0), start)
    stay_end = min(co.replace(hour=0, minute=0, second=0, microsecond=0), end)
    while cursor < stay_end:
        key = cursor.strftime("%Y-%m-%d")
        if key in daily and booking_occupies_night(normalized, cursor.date(), actual_only=actual_only or actual_stay):
            daily[key]["rooms"] += 1
            amount = allocated_revenue_for_night(normalized, cursor.date())
            if preserve_currencies:
                daily[key]["sold_rooms"] = daily[key].get("sold_rooms", 0) + int(not booking.get("is_complimentary") and money(normalized["total_amount"]) > 0)
                totals = daily[key].setdefault("revenue_by_currency", {})
                add_amount(totals, currency_code(booking.get("currency"), default_currency), amount)
                daily[key]["revenue"] = single_amount(totals)
            else:
                daily[key]["revenue"] += float(amount)
        cursor += timedelta(days=1)


def _build_forecast_rows(
    daily_otb: dict[str, dict[str, float]],
    historical_daily: dict[str, dict[str, float]],
    total_rooms: int,
    today: datetime,
    *,
    capacity_by_day: dict[str, int] | None = None,
    default_currency: str = "TRY",
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    weekday_stats = {day: {"rooms": 0.0, "sold_rooms": 0.0, "revenue_by_currency": {}, "sample_days": 0} for day in range(7)}
    for key, values in historical_daily.items():
        weekday = datetime.fromisoformat(key).weekday()
        weekday_stats[weekday]["rooms"] += values["rooms"]
        weekday_stats[weekday]["sold_rooms"] += values.get("sold_rooms", values["rooms"])
        for code, amount in (values.get("revenue_by_currency") or {default_currency: values.get("revenue") or 0}).items():
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
        sold_otb = values.get("sold_rooms", rooms_otb)
        available_rooms = (capacity_by_day or {}).get(day_key, total_rooms)
        revenue_otb_by_currency = rounded_totals(values.get("revenue_by_currency") or {default_currency: values.get("revenue") or 0})
        forecast_totals = dict(revenue_otb_by_currency)
        sold_forecast = float(sold_otb)
        if historical_room_nights:
            # Already committed rooms cannot disappear just because the hotel
            # is oversold. Cap only the additional modelled demand, not OTB.
            rooms_forecast = max(rooms_otb, min(float(available_rooms), historical_rooms))
            incremental_rooms = max(0.0, rooms_forecast - rooms_otb)
            basis = stats["revenue_by_currency"] if stats["rooms"] else revenue_otb_by_currency
            denominator = stats["rooms"] or rooms_otb
            for code, amount in basis.items():
                add_amount(forecast_totals, code, money(incremental_rooms) * money(amount) / money(denominator) if denominator else 0)
            paid_share = stats["sold_rooms"] / stats["rooms"] if stats["rooms"] else (sold_otb / rooms_otb if rooms_otb else 0)
            sold_forecast += incremental_rooms * paid_share
            source = "otb_plus_historical_weekday"
        else:
            rooms_forecast = rooms_otb
            source = "on_the_books_only"
        days_out = max(0, (target - today).days)
        confidence = min(0.95, 0.35 + min(sample_days, 26) / 52 + (0.1 if days_out <= 14 else 0)) if historical_room_nights else 0.25
        revenue_forecast_by_currency = rounded_totals(forecast_totals)
        capacity_conflict = available_rooms == 0 and rooms_forecast > 0
        adr_by_currency = {code: rounded(money(amount) / money(sold_forecast)) if sold_forecast else 0 for code, amount in revenue_forecast_by_currency.items()}
        revpar_by_currency = {} if capacity_conflict else {code: rounded(money(amount) / available_rooms) if available_rooms else 0 for code, amount in revenue_forecast_by_currency.items()}
        rows.append(
            {
                "date": day_key,
                "rooms_otb": int(rooms_otb),
                "rooms_forecast": round(rooms_forecast, 2),
                "sold_rooms_otb": int(sold_otb),
                "sold_rooms_forecast": round(sold_forecast, 4),
                "available_rooms": available_rooms,
                "overbooked_rooms": max(0, int(rooms_otb - available_rooms)),
                "capacity_conflict": capacity_conflict,
                "revenue_otb": single_amount(revenue_otb_by_currency),
                "revenue_otb_by_currency": revenue_otb_by_currency,
                "revenue_forecast": single_amount(revenue_forecast_by_currency),
                "revenue_forecast_by_currency": revenue_forecast_by_currency,
                "occupancy_pct": None if capacity_conflict else (round((rooms_forecast / available_rooms) * 100, 1) if available_rooms else 0),
                "adr": single_amount(adr_by_currency),
                "adr_by_currency": adr_by_currency,
                "revpar": None if capacity_conflict else single_amount(revpar_by_currency),
                "revpar_by_currency": revpar_by_currency,
                "historical_weekday_rooms": round(historical_rooms, 2) if historical_room_nights else None,
                "confidence": round(confidence, 2),
                "source": source,
            }
        )
    quality = {
        "historical_days": len(historical_daily),
        "historical_room_nights": historical_room_nights,
        "method": "otb_plus_historical_weekday" if historical_room_nights else "on_the_books_only",
        "warning": None if historical_room_nights else "Geçmiş konaklama verisi yok; tahmin yalnız mevcut rezervasyonları gösterir.",
        "confidence_basis": "heuristic_not_calibrated_probability",
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

    Mevcut geçerli rezervasyonları, gerçekleşmiş hafta-günü ortalamasıyla
    tamamlar. Ek talep günlük satılabilir kapasiteyle sınırlanır; mevcut fazla
    rezervasyonlar silinmez. Tahmin tahsilat/defter geliri değildir.
    """
    try:
        db = get_system_db()
        rooms = await db.rooms.find({"tenant_id": user.tenant_id, "is_active": {"$ne": False}}, {"_id": 0, "id": 1, "room_number": 1, "is_active": 1}).to_list(None)
        total_rooms = len(rooms)
        default_currency, _ = await get_tenant_currency(user.tenant_id)
        default_currency = currency_code(default_currency)
        today = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        horizon = today + timedelta(days=days)
        blocks = await db.room_blocks.find({"tenant_id": user.tenant_id, "status": "active", "allow_sell": {"$ne": True},
            **room_block_overlap_match(today.date(), (horizon - timedelta(days=1)).date())}, {"_id": 0}).to_list(None)
        capacity = {row["date"]: row["total_rooms"] for row in calculate_stay_night_metrics([], rooms, today.date(), (horizon - timedelta(days=1)).date(), room_blocks=blocks)}

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
            _allocate_booking(booking, history_start, today, historical_daily, preserve_currencies=True, default_currency=default_currency, actual_only=True)

        out, data_quality = _build_forecast_rows(daily, historical_daily, total_rooms, today, capacity_by_day=capacity, default_currency=default_currency)
        if any(row["overbooked_rooms"] for row in out):
            warning = "Kapasiteyi aşan mevcut rezervasyonlar var; bu odalar tahminden silinmedi. Satışa kapalı oda aralıklarını ve oda atamalarını kontrol edin."
            data_quality["warning"] = " ".join(filter(None, [data_quality["warning"], warning]))
        return {
            "horizon_days": days,
            "segment": segment,
            "total_rooms": total_rooms,
            "currency": default_currency,
            "start_date": today.date().isoformat(),
            "end_date": (horizon - timedelta(days=1)).date().isoformat(),
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
    compare_year: int | None = Query(None, ge=1, le=9999, description="Karşılaştırılacak yıl (geçen yıl gibi)"),
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),
):
    """Booking pace: bir hedef tarih için zaman içinde rezervasyon birikimi.

    Hedef geceyi kapsayan bugünkü geçerli kayıtların 'created_at' birikimi.
    Geçmiş iptal/değişiklik durumlarının tarihsel snapshot'ı değildir.
    """
    try:
        target_day = date.fromisoformat(target_date)
        if target_day.isoformat() != target_date:
            raise ValueError("Non-canonical day")
        td = datetime.combine(target_day, datetime.min.time(), UTC)
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "target_date YYYY-MM-DD olmalı") from exc
    comp_dt = None
    if compare_year is not None:
        try:
            if not isinstance(compare_year, int) or not 1 <= compare_year <= 9999:
                raise ValueError("Invalid year")
            comp_dt = td.replace(year=compare_year)
        except (TypeError, ValueError) as exc:
            raise HTTPException(422, "Karşılaştırma yılında bu tarih yok; geçerli bir yıl/tarih seçin.") from exc
    db = get_system_db()
    as_of = datetime.now(UTC).date()

    async def _pace_for(date_dt: datetime) -> list[dict[str, Any]]:
        cur = db.bookings.find(
            {
                "tenant_id": user.tenant_id,
                **stay_overlap_match(date_dt.date(), date_dt.date()),
                "status": {"$in": sorted(OCCUPYING_STATUSES)},
            }
        )
        by_lead: dict[int, int] = {}
        async for b in cur:
            try:
                created = as_date(b.get("created_at"))
                if not created or created > as_of or not booking_occupies_night(b, date_dt.date()):
                    continue
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
        observed_lead = max(0, (date_dt.date() - as_of).days)
        for lead in range(max_lead, observed_lead - 1, -1):
            cumulative += by_lead.get(lead, 0)
            series.append({"days_out": lead, "rooms_on_books": cumulative})
        return series

    current = await _pace_for(td)
    out: dict[str, Any] = {"target_date": target_date, "current": current, "as_of_date": as_of.isoformat(),
        "basis": "current_valid_bookings_created_at_not_historical_snapshots"}
    if comp_dt is not None:
        out["compare_year"] = compare_year
        out["compare"] = await _pace_for(comp_dt)
    return out


@router.get("/pickup-report")
async def pickup_report(
    period_days: int = Query(7, ge=1, le=90, description="Son N gündeki pickup"),
    user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_reports")),
):
    """Son N günde oluşturulan geçerli konaklamalar; net hareket pickup'ı değildir."""
    db = get_system_db()
    now = datetime.now(UTC)
    since = now - timedelta(days=period_days)
    cur = db.bookings.find(
        {
            "tenant_id": user.tenant_id,
            "$or": [{"created_at": {"$gte": since.isoformat(), "$lte": now.isoformat()}}, {"created_at": {"$gte": since, "$lte": now}}],
            "status": {"$in": sorted(OCCUPYING_STATUSES)},
        }
    )
    by_ci_date = {}
    total_rooms = 0
    total_revenue = {}
    default_currency, _ = await get_tenant_currency(user.tenant_id)
    async for b in cur:
        arrival = as_date(b.get("check_in"))
        ci = arrival.isoformat() if arrival else None
        if not ci or not booking_nights(b):
            continue
        rec = by_ci_date.setdefault(ci, {"rooms": 0, "revenue": {}})
        rec["rooms"] += 1
        code = currency_code(b.get("currency"), default_currency)
        amount = 0 if b.get("is_complimentary") else (b.get("total_amount") if b.get("total_amount") is not None else b.get("total", 0))
        add_amount(rec["revenue"], code, amount)
        total_rooms += 1
        add_amount(total_revenue, code, amount)
    daily = [{"check_in": d, "rooms": int(by_ci_date[d]["rooms"]), "revenue": single_amount(by_ci_date[d]["revenue"]),
        "revenue_by_currency": rounded_totals(by_ci_date[d]["revenue"])} for d in sorted(by_ci_date)]
    return {
        "period_days": period_days,
        "currency": currency_code(default_currency),
        "start_at": since.isoformat(),
        "end_at": now.isoformat(),
        "revenue_basis": "valid_reservation_value_not_posted_revenue_or_collections",
        "total_rooms_picked": total_rooms,
        "total_revenue_picked": single_amount(total_revenue),
        "total_revenue_picked_by_currency": rounded_totals(total_revenue),
        "daily": daily,
    }
