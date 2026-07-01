"""
Revenue / Pricing Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, timedelta
from datetime import date as DateType
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, ConfigDict, Field

from cache_manager import cached
from core.database import db
from core.security import (
    get_current_user,
    security,
)
from models.enums import CancellationPolicyType, ChannelType, MarketSegment, RateType

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


router = APIRouter(prefix="/api", tags=["Revenue / Pricing"])


# ── Inline Models ──


class RatePlanFilter(BaseModel):
    channel: ChannelType | None = None
    company_id: str | None = None
    date: DateType | None = None


class RatePlanCreate(BaseModel):
    name: str
    code: str
    type: RateType = RateType.BAR
    currency: str = "EUR"
    base_price: float
    room_type: str = "Standard"  # Default room type
    market_segment: MarketSegment | None = None
    channel_restrictions: list[ChannelType] = []
    company_ids: list[str] = []
    valid_from: DateType | None = None
    valid_to: DateType | None = None
    days_of_week: list[int] = []
    min_stay: int | None = None
    max_stay: int | None = None
    cancellation_policy: CancellationPolicyType | None = None


class PackageCreate(BaseModel):
    name: str
    code: str
    description: str | None = None
    included_services: list[str] = []
    price_type: str = "per_room"
    additional_amount: float = 0.0
    linked_rate_plan_ids: list[str] = []


class DynamicRestrictionsRequest(BaseModel):
    date: str
    room_type: str
    min_los: int | None = None  # Minimum Length of Stay
    cta: bool = False  # Closed to Arrival
    ctd: bool = False  # Closed to Departure
    stop_sell: bool = False


class DemandForecast(BaseModel):
    """Demand forecast model"""

    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    date: str
    room_type: str | None = None
    forecasted_occupancy: float
    confidence: float
    factors: dict[str, Any] = {}  # events, seasonality, historical
    model_version: str = "ml-v1"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class CompetitorRate(BaseModel):
    """Competitor rate scraping"""

    model_config = ConfigDict(extra="ignore")
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tenant_id: str
    competitor_name: str
    date: str
    room_type: str
    rate: float
    source: str  # google_hotels, booking_com, expedia
    scraped_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class RateOverrideRequest(BaseModel):
    room_type: str
    date: str
    new_rate: float
    reason: str
    requires_approval: bool = True


# ─── Endpoints (split: revenue_analysis) ───


@router.get("/revenue/pickup-analysis")
async def get_pickup_analysis(days_back: int = 30, days_forward: int = 7, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Get pickup analysis - historical and forecast
    Shows daily occupancy, bookings, revenue trends
    """
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC).date()

    # N+1 fix: total_rooms tek sefer; per-day metrics tek aggregation
    total_rooms = await db.rooms.count_documents({"tenant_id": current_user.tenant_id})

    start_str = (today - timedelta(days=days_back)).isoformat()
    end_str = today.isoformat()
    # Per-day check_in revenue
    revenue_by_day: dict = {}
    async for r in db.bookings.aggregate(
        [
            {
                "$match": {
                    "tenant_id": current_user.tenant_id,
                    "check_in": {"$gte": start_str, "$lt": end_str},
                }
            },
            {"$group": {"_id": "$check_in", "rev": {"$sum": "$total_amount"}}},
        ]
    ):
        revenue_by_day[r["_id"]] = r["rev"] or 0

    # Per-day occupancy: tek facet ile her gun bookings sayisi
    occupancy_by_day: dict = {}
    facet = {}
    days_list = [(today - timedelta(days=i)).isoformat() for i in range(days_back, 0, -1)]
    for d in days_list:
        facet[f"d_{d}"] = [
            {
                "$match": {
                    "tenant_id": current_user.tenant_id,
                    "check_in": {"$lte": d},
                    "check_out": {"$gt": d},
                    "status": {"$in": ["confirmed", "checked_in"]},
                }
            },
            {"$count": "n"},
        ]
    if facet:
        agg = await db.bookings.aggregate([{"$facet": facet}]).to_list(1)
        row = agg[0] if agg else {}
        for d in days_list:
            arr = row.get(f"d_{d}", [])
            occupancy_by_day[d] = arr[0]["n"] if arr else 0

    historical = []
    for date_str in days_list:
        bookings = occupancy_by_day.get(date_str, 0)
        occupancy_pct = (bookings / total_rooms * 100) if total_rooms > 0 else 0
        revenue = revenue_by_day.get(date_str, 0)
        historical.append({"date": date_str, "occupancy": round(occupancy_pct, 1), "bookings": bookings, "revenue": round(revenue, 2), "type": "actual"})

    # Forecast: gerçek tahmin modeli yok -> fabrikasyon (rastgele i%3 / i%4 varyasyon) kaldırıldı.
    # Sadece gerçek geçmiş (historical) döner; ileriye dönük tahmin fail-closed.
    return {
        "historical": historical,
        "forecast": [],
        "forecast_available": False,
        "forecast_message": "İleriye dönük pickup tahmini için gerçek tahmin kaynağı yok.",
        "summary": {
            "avg_occupancy_30d": round(sum(h["occupancy"] for h in historical) / len(historical), 1) if historical else 0,
            "avg_revenue_30d": round(sum(h["revenue"] for h in historical) / len(historical), 2) if historical else 0,
            "trend": ("up" if historical[-1]["occupancy"] > historical[-7]["occupancy"] else "down") if len(historical) >= 7 else "unknown",
        },
    }


# 2. GET /api/revenue/pace-report - Booking pace comparison


@router.get("/revenue/pace-report")
@cached(ttl=300, key_prefix="rev_pace_report")  # 5dk cache (Tur 2 fix)
async def get_pace_report(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Get booking pace report - this year vs last year
    Shows on-the-books comparison
    """
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC).date()

    # Next 30 days — N+1 fix: tek aggregation ile 30 gun
    days_list = [(today + timedelta(days=i)).isoformat() for i in range(30)]
    by_day: dict = {}
    async for r in db.bookings.aggregate(
        [
            {
                "$match": {
                    "tenant_id": current_user.tenant_id,
                    "check_in": {"$in": days_list},
                    "status": {"$in": ["confirmed", "checked_in", "guaranteed"]},
                }
            },
            {"$group": {"_id": "$check_in", "n": {"$sum": 1}}},
        ]
    ):
        by_day[r["_id"]] = r["n"]

    # B: geçen yıl aynı takvim günleri (gerçek on-the-books) — uydurma (this_year +/- sabit) kaldırıldı
    last_year_days = [(today + timedelta(days=i) - timedelta(days=365)).isoformat() for i in range(30)]
    ly_by_day: dict = {}
    async for r in db.bookings.aggregate(
        [
            {
                "$match": {
                    "tenant_id": current_user.tenant_id,
                    "check_in": {"$in": last_year_days},
                    "status": {"$in": ["confirmed", "checked_in", "guaranteed", "checked_out"]},
                }
            },
            {"$group": {"_id": "$check_in", "n": {"$sum": 1}}},
        ]
    ):
        ly_by_day[r["_id"]] = r["n"]

    pace_data = []
    for i in range(30):
        date_str = days_list[i]
        this_year = by_day.get(date_str, 0)
        last_year = ly_by_day.get(last_year_days[i], 0)
        pace_data.append(
            {
                "date": date_str,
                "this_year": this_year,
                "last_year": last_year,
                "variance": this_year - last_year,
                "variance_pct": round(((this_year - last_year) / last_year * 100) if last_year > 0 else 0, 1),
            }
        )

    return {
        "pace_data": pace_data,
        "summary": {
            "total_this_year": sum(p["this_year"] for p in pace_data),
            "total_last_year": sum(p["last_year"] for p in pace_data),
            "pace_status": "ahead" if sum(p["variance"] for p in pace_data) > 0 else "behind",
        },
    }


# 3. GET /api/revenue/rate-recommendations - Dynamic pricing recommendations


@router.get("/revenue/rate-recommendations")
async def get_rate_recommendations(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Get AI-powered rate recommendations
    Based on occupancy, demand, historical data
    """
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC).date()

    # N+1 fix: total_rooms tek sefer + 7-gun bookings tek aggregation
    rec_total_rooms = await db.rooms.count_documents({"tenant_id": current_user.tenant_id})
    rec_days = [(today + timedelta(days=i)).isoformat() for i in range(7)]
    rec_by_day: dict = {}
    async for r in db.bookings.aggregate(
        [
            {
                "$match": {
                    "tenant_id": current_user.tenant_id,
                    "check_in": {"$in": rec_days},
                    "status": {"$in": ["confirmed", "guaranteed"]},
                }
            },
            {"$group": {"_id": "$check_in", "n": {"$sum": 1}}},
        ]
    ):
        rec_by_day[r["_id"]] = r["n"]

    recommendations = []
    for i in range(7):
        date_str = rec_days[i]
        bookings = rec_by_day.get(date_str, 0)
        total_rooms = rec_total_rooms
        occupancy_pct = (bookings / total_rooms * 100) if total_rooms > 0 else 0

        # Simple pricing algorithm
        base_rate = 1000  # Base rate

        if occupancy_pct > 80:
            recommended_rate = base_rate * 1.3
            strategy = "maximize"
            reason = "High occupancy - price increase recommended"
        elif occupancy_pct > 60:
            recommended_rate = base_rate * 1.1
            strategy = "optimize"
            reason = "Medium occupancy - slight price increase"
        elif occupancy_pct > 40:
            recommended_rate = base_rate
            strategy = "maintain"
            reason = "Normal occupancy - current price is appropriate"
        else:
            recommended_rate = base_rate * 0.85
            strategy = "stimulate"
            reason = "Low occupancy - demand-stimulating price"

        recommendations.append(
            {
                "date": date_str,
                "current_occupancy": round(occupancy_pct, 1),
                "current_rate": base_rate,
                "recommended_rate": round(recommended_rate, 2),
                "variance": round(recommended_rate - base_rate, 2),
                "variance_pct": round((recommended_rate - base_rate) / base_rate * 100, 1),
                "strategy": strategy,
                "reason": reason,
            }
        )

    return {"recommendations": recommendations, "summary": {"avg_recommended_increase": round(sum(r["variance_pct"] for r in recommendations) / len(recommendations), 1)}}


# 4. GET /api/revenue/historical-comparison - YoY comparison


@router.get("/revenue/historical-comparison")
async def get_historical_comparison(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Year-over-year comparison
    Revenue, occupancy, ADR comparison
    """
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC).date()
    month_start = today.replace(day=1)

    # This month-to-date window (current calendar month), excluding cancellations.
    if month_start.month == 12:
        next_month = month_start.replace(year=month_start.year + 1, month=1)
    else:
        next_month = month_start.replace(month=month_start.month + 1)
    this_month_filter = {
        "tenant_id": current_user.tenant_id,
        "check_in": {"$gte": month_start.isoformat(), "$lt": next_month.isoformat()},
        "status": {"$nin": ["cancelled", "no_show"]},
    }
    this_month_bookings = await db.bookings.count_documents(this_month_filter)
    this_month_revenue = 0
    async for booking in db.bookings.find(this_month_filter):
        this_month_revenue += booking.get("total_amount", 0)

    # Real last-year data: the SAME calendar-month window one year earlier.
    last_year_month_start = month_start.replace(year=month_start.year - 1)
    if last_year_month_start.month == 12:
        ly_next_month = last_year_month_start.replace(year=last_year_month_start.year + 1, month=1)
    else:
        ly_next_month = last_year_month_start.replace(month=last_year_month_start.month + 1)
    last_year_filter = {
        "tenant_id": current_user.tenant_id,
        "check_in": {"$gte": last_year_month_start.isoformat(), "$lt": ly_next_month.isoformat()},
        "status": {"$nin": ["cancelled", "no_show"]},
    }
    last_year_bookings = await db.bookings.count_documents(last_year_filter)
    last_year_revenue = 0
    async for booking in db.bookings.find(last_year_filter):
        last_year_revenue += booking.get("total_amount", 0)

    this_year = {
        "bookings": this_month_bookings,
        "revenue": round(this_month_revenue, 2),
        "adr": round(this_month_revenue / this_month_bookings, 2) if this_month_bookings > 0 else 0,
    }

    # Fail-closed honesty: with no real last-year data (e.g. a hotel in its first
    # year) we do NOT fabricate a baseline or variance.
    if last_year_bookings == 0 and last_year_revenue == 0:
        return {
            "this_year": this_year,
            "last_year": None,
            "variance": None,
            "data_available": False,
            "message": "Gecen yil ayni donem icin veri bulunmuyor; karsilastirma yapilamiyor.",
        }

    return {
        "this_year": this_year,
        "last_year": {"bookings": last_year_bookings, "revenue": round(last_year_revenue, 2), "adr": round(last_year_revenue / last_year_bookings, 2) if last_year_bookings > 0 else 0},
        "variance": {
            "bookings": this_month_bookings - last_year_bookings,
            "bookings_pct": round((this_month_bookings - last_year_bookings) / last_year_bookings * 100, 1) if last_year_bookings > 0 else 0,
            "revenue": round(this_month_revenue - last_year_revenue, 2),
            "revenue_pct": round((this_month_revenue - last_year_revenue) / last_year_revenue * 100, 1) if last_year_revenue > 0 else 0,
        },
        "data_available": True,
    }


# ============================================================================
# ANOMALY DETECTION SYSTEM - Anomali Tespit Sistemi
# ============================================================================

# 1. GET /api/anomaly/detect - Real-time anomaly detection
