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


async def _iter_bookings_in_range(
    db, tenant_id: str, start: datetime, end: datetime, segment: str | None = None
):
    q: dict[str, Any] = {
        "tenant_id": tenant_id,
        "check_in": {"$gte": start.isoformat(), "$lte": end.isoformat()},
        "status": {"$nin": ["cancelled", "no_show"]},
    }
    if segment:
        q["market_segment"] = segment
    cur = db.bookings.find(q)
    async for b in cur:
        yield b


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

        async for b in _iter_bookings_in_range(db, user.tenant_id, today, horizon, segment):
            try:
                ci_raw = b.get("check_in")
                co_raw = b.get("check_out")
                if not ci_raw or not co_raw:
                    continue
                ci = (
                    ci_raw if isinstance(ci_raw, datetime)
                    else datetime.fromisoformat(str(ci_raw).replace("Z", "+00:00"))
                )
                co = (
                    co_raw if isinstance(co_raw, datetime)
                    else datetime.fromisoformat(str(co_raw).replace("Z", "+00:00"))
                )
                if ci.tzinfo is None:
                    ci = ci.replace(tzinfo=UTC)
                if co.tzinfo is None:
                    co = co.replace(tzinfo=UTC)
            except Exception:
                continue
            nights = max((co - ci).days, 1)
            try:
                amt = float(b.get("total_amount") or b.get("total") or 0)
            except (TypeError, ValueError):
                amt = 0.0
            rate = amt / nights if nights else 0
            cur = ci.replace(hour=0, minute=0, second=0, microsecond=0)
            while cur < co and cur <= horizon:
                key = cur.strftime("%Y-%m-%d")
                if key in daily:
                    daily[key]["rooms"] += 1
                    daily[key]["revenue"] += rate
                cur += timedelta(days=1)

        out = []
        for d in sorted(daily.keys()):
            rooms_otb = daily[d]["rooms"]
            rev_otb = daily[d]["revenue"]
            days_out = (datetime.fromisoformat(d).replace(tzinfo=UTC) - today).days
            pickup_mult = 1.0 + min(max(days_out, 0) * 0.015, 0.6)
            rooms_fcst = round(rooms_otb * pickup_mult, 1)
            rev_fcst = round(rev_otb * pickup_mult, 2)
            occupancy = round((rooms_fcst / total_rooms) * 100, 1)
            adr = round((rev_fcst / rooms_fcst) if rooms_fcst else 0, 2)
            revpar = round(rev_fcst / total_rooms, 2)
            out.append({
                "date": d,
                "rooms_otb": int(rooms_otb),
                "rooms_forecast": rooms_fcst,
                "revenue_otb": round(rev_otb, 2),
                "revenue_forecast": rev_fcst,
                "occupancy_pct": occupancy,
                "adr": adr,
                "revpar": revpar,
            })
        return {
            "horizon_days": days,
            "segment": segment,
            "total_rooms": total_rooms,
            "generated_at": datetime.now(UTC).isoformat(),
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
        cur = db.bookings.find({
            "tenant_id": user.tenant_id,
            "check_in": {
                "$gte": date_dt.replace(hour=0, minute=0, second=0).isoformat(),
                "$lt": (date_dt + timedelta(days=1)).isoformat(),
            },
            "status": {"$nin": ["cancelled", "no_show"]},
        })
        by_lead: dict[int, int] = {}
        async for b in cur:
            try:
                created = datetime.fromisoformat(
                    str(b.get("created_at", "")).replace("Z", "+00:00")
                )
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
    cur = db.bookings.find({
        "tenant_id": user.tenant_id,
        "created_at": {"$gte": since},
        "status": {"$nin": ["cancelled", "no_show"]},
    })
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
    daily = [
        {"check_in": d, "rooms": int(by_ci_date[d]["rooms"]), "revenue": round(by_ci_date[d]["revenue"], 2)}
        for d in sorted(by_ci_date.keys())
    ]
    return {
        "period_days": period_days,
        "total_rooms_picked": total_rooms,
        "total_revenue_picked": round(total_revenue, 2),
        "daily": daily,
    }
