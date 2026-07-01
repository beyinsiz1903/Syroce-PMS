"""
revenue_mobile

Auto-split sub-router (shared imports/classes inlined).
"""

"""
Domain Router: POS & F&B

Extracted from legacy_routes.py — Point of Sale, F&B operations, kitchen, transactions.
"""
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user, security
from modules.pms_core.role_permission_service import (
    require_op,  # v88 DW
)

# ============= POS / F&B ENDPOINTS =============

# NOTE: GET /pos/outlets and GET /pos/menu-items are served by marketplace_router
# (richer logic with today_transactions enrichment). The duplicates that used to
# live here have been removed to keep a single canonical source of truth.


async def _query_pos_transactions(
    tenant_id: str,
    *,
    limit: int = 50,
    outlet_id: str | None = None,
    booking_id: str | None = None,
    start_date: str | None = None,
    end_date: str | None = None,
    date: str | None = None,
) -> list[dict]:
    """Canonical POS transaction query.

    Reads from pos_menu_transactions (same source as /pos/z-report and
    /pos/void-transactions). Falls back to legacy collections (transactions,
    pos_orders) so older data still surfaces.
    """
    base_q: dict[str, Any] = {"tenant_id": tenant_id}
    if outlet_id:
        base_q["outlet_id"] = outlet_id
    if booking_id:
        base_q["booking_id"] = booking_id
    if date:
        base_q["transaction_date"] = date
    elif start_date or end_date:
        rng: dict[str, Any] = {}
        if start_date:
            rng["$gte"] = start_date
        if end_date:
            rng["$lte"] = end_date
        if rng:
            base_q["transaction_date"] = rng

    try:
        rows = await db.pos_menu_transactions.find(base_q, {"_id": 0}).sort("created_at", -1).to_list(limit)
        if rows:
            return rows
        # Legacy fallback #1: db.transactions
        rows = await db.transactions.find(base_q, {"_id": 0}).sort("created_at", -1).to_list(limit)
        if rows:
            return rows
        # Legacy fallback #2: db.pos_orders
        return await db.pos_orders.find(base_q, {"_id": 0}).sort("created_at", -1).to_list(limit)
    except Exception:
        return []


async def get_anomaly_detection(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Detect anomalies in room operations"""
    current_user = await get_current_user(credentials)

    anomalies = []

    # 1. Price Anomalies - Rooms priced significantly below average
    avg_rate_pipeline = [
        {"$match": {"tenant_id": current_user.tenant_id, "status": {"$in": ["confirmed", "guaranteed", "checked_in"]}, "created_at": {"$gte": datetime.now(UTC) - timedelta(days=30)}}},
        {"$group": {"_id": "$room_type", "avg_rate": {"$avg": "$room_rate"}, "min_rate": {"$min": "$room_rate"}, "max_rate": {"$max": "$room_rate"}}},
    ]

    rate_stats = {}
    async for stat in db.bookings.aggregate(avg_rate_pipeline):
        rate_stats[stat["_id"]] = stat

    # Check for low-priced bookings
    async for booking in db.bookings.find({"tenant_id": current_user.tenant_id, "check_in": {"$gte": datetime.now(UTC)}, "status": {"$in": ["confirmed", "guaranteed"]}}):
        room_type = booking.get("room_type")
        room_rate = booking.get("room_rate", 0)

        if room_type in rate_stats:
            avg_rate = rate_stats[room_type]["avg_rate"]
            if room_rate < avg_rate * 0.7:  # 30% below average
                anomalies.append(
                    {
                        "type": "low_price",
                        "severity": "medium",
                        "booking_id": booking.get("id"),
                        "room_number": booking.get("room_number"),
                        "guest_name": booking.get("guest_name"),
                        "current_rate": room_rate,
                        "average_rate": avg_rate,
                        "difference_pct": ((avg_rate - room_rate) / avg_rate * 100),
                        "message": f"Oda {booking.get('room_number')} ortalamanın %{((avg_rate - room_rate) / avg_rate * 100):.0f} altında fiyatlandırılmış",
                    }
                )

    # 2. Cleaning Delay Anomalies (batched room lookup)
    delay_tasks = await db.housekeeping_tasks.find(
        {"tenant_id": current_user.tenant_id, "task_type": "cleaning", "status": "in_progress", "started_at": {"$lte": datetime.now(UTC) - timedelta(hours=1)}}
    ).to_list(length=None)
    dt_room_ids = [t.get("room_id") for t in delay_tasks if t.get("room_id")]
    dt_rooms_by_id: dict = {}
    if dt_room_ids:
        async for r in db.rooms.find(
            {"id": {"$in": dt_room_ids}, "tenant_id": current_user.tenant_id},
            {"_id": 0, "id": 1, "room_number": 1},
        ):
            dt_rooms_by_id[r["id"]] = r
    for task in delay_tasks:
        duration = (datetime.now(UTC) - task.get("started_at")).total_seconds() / 60
        room = dt_rooms_by_id.get(task.get("room_id"))
        room_num = room.get("room_number") if room else "N/A"
        anomalies.append(
            {
                "type": "cleaning_delay",
                "severity": "high" if duration > 90 else "medium",
                "room_id": task.get("room_id"),
                "room_number": room_num,
                "duration_minutes": int(duration),
                "assigned_to": task.get("assigned_to"),
                "message": f"Oda {room_num} {int(duration)} dakikadır temizleniyor",
            }
        )

    # 3. Overstay Risk Detection
    today = datetime.now(UTC).replace(hour=0, minute=0, second=0)
    async for booking in db.bookings.find({"tenant_id": current_user.tenant_id, "check_out": {"$lte": today}, "status": "checked_in"}):
        days_over = (today - booking.get("check_out")).days

        anomalies.append(
            {
                "type": "overstay",
                "severity": "high",
                "booking_id": booking.get("id"),
                "room_number": booking.get("room_number"),
                "guest_name": booking.get("guest_name"),
                "days_over": days_over,
                "original_checkout": booking.get("check_out").date().isoformat(),
                "message": f"Misafir {booking.get('guest_name')} check-out yapması gerekirken hala odada ({days_over} gün geçti)",
            }
        )

    # 4. High Maintenance Frequency Rooms
    maintenance_pipeline = [
        {"$match": {"tenant_id": current_user.tenant_id, "department": "maintenance", "created_at": {"$gte": datetime.now(UTC) - timedelta(days=30)}}},
        {"$group": {"_id": "$room_id", "count": {"$sum": 1}, "room_number": {"$first": "$room_number"}}},
        {"$match": {"count": {"$gte": 3}}},
        {"$sort": {"count": -1}},
    ]

    async for room_stat in db.tasks.aggregate(maintenance_pipeline):
        anomalies.append(
            {
                "type": "high_maintenance",
                "severity": "medium",
                "room_id": room_stat["_id"],
                "room_number": room_stat["room_number"],
                "maintenance_count": room_stat["count"],
                "message": f"Oda {room_stat['room_number']} son 30 günde {room_stat['count']} kez bakıma girdi",
            }
        )

    return {
        "anomalies": anomalies,
        "count": len(anomalies),
        "by_severity": {
            "high": len([a for a in anomalies if a["severity"] == "high"]),
            "medium": len([a for a in anomalies if a["severity"] == "medium"]),
            "low": len([a for a in anomalies if a["severity"] == "low"]),
        },
    }


# --------------------------------------------------------------------------
# Front Office - Enhanced Features
# --------------------------------------------------------------------------

# rbac-allow: cache-rbac — FO rooms filter operasyonel


# --------------------------------------------------------------------------
# Front Office Mobile - Check-in, ID Scan, Guest Requests, Folio Operations
# --------------------------------------------------------------------------

# rbac-allow: cache-rbac — FO available rooms operasyonel


# --------------------------------------------------------------------------
# Revenue Management - ADR, RevPAR, Forecasting, Rate Override, Analytics
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# Housekeeping - Enhanced Features
# --------------------------------------------------------------------------


class LostFoundItemCreate(BaseModel):
    item_description: str
    location_found: str
    found_by: str
    category: str | None = "other"
    room_number: str | None = None
    guest_name: str | None = None
    notes: str | None = None


# --------------------------------------------------------------------------
# Maintenance - Asset History
# --------------------------------------------------------------------------


# --------------------------------------------------------------------------
# F&B - Z Report, Void Report, Menu Management
# --------------------------------------------------------------------------


class MenuItemCreate(BaseModel):
    name: str
    category: str
    price: float
    description: str | None = None
    cost: float | None = None
    available: bool = True
    image_url: str | None = None
    tax_rate: float = 0.10  # KDV (varsayilan %10)
    outlet_id: str | None = None


# --------------------------------------------------------------------------
# Finance - P&L Report and Cashier Shift Report
# --------------------------------------------------------------------------

router = APIRouter(prefix="/api", tags=["pos-fnb"])


# ── GET /revenue/mobile/dashboard ──
@router.get("/revenue/mobile/dashboard")
async def get_revenue_dashboard_mobile(start_date: str | None = None, end_date: str | None = None, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get comprehensive revenue dashboard"""
    current_user = await get_current_user(credentials)

    # Default to current month
    if not start_date or not end_date:
        today = datetime.now(UTC).date()
        start_date = today.replace(day=1).isoformat()
        last_day = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        end_date = last_day.isoformat()

    start_dt = datetime.fromisoformat(start_date).replace(tzinfo=UTC)
    end_dt = datetime.fromisoformat(end_date).replace(tzinfo=UTC)

    # Total rooms
    total_rooms = await db.rooms.count_documents({"tenant_id": current_user.tenant_id})

    # Bookings in period
    bookings_query = {
        "tenant_id": current_user.tenant_id,
        "check_in": {"$lte": end_date},
        "check_out": {"$gte": start_date},
        "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]},
    }

    total_revenue = 0.0
    total_room_nights = 0
    bookings_list = []

    async for booking in db.bookings.find(bookings_query):
        revenue = booking.get("total_amount", 0)
        nights = booking.get("nights", 1)
        total_revenue += revenue
        total_room_nights += nights
        bookings_list.append(booking)

    # Calculate metrics
    days_in_period = (end_dt - start_dt).days + 1
    total_room_nights_available = total_rooms * days_in_period

    occupancy = (total_room_nights / total_room_nights_available * 100) if total_room_nights_available > 0 else 0
    adr = (total_revenue / total_room_nights) if total_room_nights > 0 else 0
    revpar = (total_revenue / total_room_nights_available) if total_room_nights_available > 0 else 0

    return {
        "period": {"start_date": start_date, "end_date": end_date, "days": days_in_period},
        "key_metrics": {
            "total_revenue": total_revenue,
            "adr": adr,  # Average Daily Rate
            "revpar": revpar,  # Revenue Per Available Room
            "occupancy_percentage": occupancy,
            "total_bookings": len(bookings_list),
            "room_nights_sold": total_room_nights,
            "room_nights_available": total_room_nights_available,
        },
    }


# ── GET /revenue/mobile/segment-analysis ──
@router.get("/revenue/mobile/segment-analysis")
async def get_segment_analysis_mobile(start_date: str | None = None, end_date: str | None = None, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get revenue by market segment"""
    current_user = await get_current_user(credentials)

    # Default to current month
    if not start_date or not end_date:
        today = datetime.now(UTC).date()
        start_date = today.replace(day=1).isoformat()
        last_day = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        end_date = last_day.isoformat()

    bookings_query = {
        "tenant_id": current_user.tenant_id,
        "check_in": {"$lte": end_date},
        "check_out": {"$gte": start_date},
        "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]},
    }

    segments = {}

    async for booking in db.bookings.find(bookings_query):
        segment = booking.get("market_segment", "other")
        revenue = booking.get("total_amount", 0)
        nights = booking.get("nights", 1)

        if segment not in segments:
            segments[segment] = {"segment": segment, "revenue": 0, "bookings": 0, "room_nights": 0, "adr": 0}

        segments[segment]["revenue"] += revenue
        segments[segment]["bookings"] += 1
        segments[segment]["room_nights"] += nights

    # Calculate ADR for each segment
    for segment in segments.values():
        if segment["room_nights"] > 0:
            segment["adr"] = segment["revenue"] / segment["room_nights"]

    # Sort by revenue
    segments_list = sorted(segments.values(), key=lambda x: x["revenue"], reverse=True)

    total_revenue = sum(s["revenue"] for s in segments_list)

    # Add percentage
    for segment in segments_list:
        segment["percentage"] = (segment["revenue"] / total_revenue * 100) if total_revenue > 0 else 0

    return {"period": {"start_date": start_date, "end_date": end_date}, "segments": segments_list, "total_revenue": total_revenue}


# ── GET /revenue/mobile/channel-distribution ──
@router.get("/revenue/mobile/channel-distribution", operation_id="pos_get_channel_distribution_mobile")
async def get_channel_distribution_mobile(start_date: str | None = None, end_date: str | None = None, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get revenue by booking channel"""
    current_user = await get_current_user(credentials)

    # Default to current month
    if not start_date or not end_date:
        today = datetime.now(UTC).date()
        start_date = today.replace(day=1).isoformat()
        last_day = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        end_date = last_day.isoformat()

    bookings_query = {
        "tenant_id": current_user.tenant_id,
        "check_in": {"$lte": end_date},
        "check_out": {"$gte": start_date},
        "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]},
    }

    channels = {}

    async for booking in db.bookings.find(bookings_query):
        channel = booking.get("channel", "direct")
        revenue = booking.get("total_amount", 0)

        if channel not in channels:
            channels[channel] = {"channel": channel, "revenue": 0, "bookings": 0, "adr": 0}

        channels[channel]["revenue"] += revenue
        channels[channel]["bookings"] += 1

    # Calculate ADR
    for channel in channels.values():
        if channel["bookings"] > 0:
            channel["adr"] = channel["revenue"] / channel["bookings"]

    channels_list = sorted(channels.values(), key=lambda x: x["revenue"], reverse=True)
    total_revenue = sum(c["revenue"] for c in channels_list)

    for channel in channels_list:
        channel["percentage"] = (channel["revenue"] / total_revenue * 100) if total_revenue > 0 else 0

    return {"period": {"start_date": start_date, "end_date": end_date}, "channels": channels_list, "total_revenue": total_revenue}


# ── GET /revenue/mobile/pickup-graph ──
@router.get("/revenue/mobile/pickup-graph", operation_id="pos_get_pickup_graph_mobile")
async def get_pickup_graph_mobile(arrival_date: str, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get booking pickup graph for specific arrival date"""
    current_user = await get_current_user(credentials)

    arrival_dt = datetime.fromisoformat(arrival_date).date()

    # Get bookings for this arrival date
    bookings = []
    async for booking in db.bookings.find({"tenant_id": current_user.tenant_id, "check_in": arrival_date, "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]}}).sort(
        "created_at", 1
    ):
        bookings.append({"created_at": booking.get("created_at"), "room_nights": booking.get("nights", 1)})

    # Generate pickup data points
    pickup_points = []

    # Group by days before arrival
    today = datetime.now(UTC).date()
    days_until_arrival = (arrival_dt - today).days

    for i in range(365, -1, -7):  # Weekly points going back 1 year
        cutoff_date = arrival_dt - timedelta(days=i)
        cutoff_dt = datetime.combine(cutoff_date, datetime.max.time()).replace(tzinfo=UTC)

        rooms_at_cutoff = sum(b["room_nights"] for b in bookings if b["created_at"] <= cutoff_dt)

        pickup_points.append({"days_before_arrival": i, "date": cutoff_date.isoformat(), "cumulative_rooms": rooms_at_cutoff})

    return {"arrival_date": arrival_date, "days_until_arrival": days_until_arrival, "current_bookings": len(bookings), "pickup_data": pickup_points}


# ── GET /revenue/mobile/forecast ──
@router.get("/revenue/mobile/forecast", operation_id="pos_get_revenue_forecast_mobile")
async def get_revenue_forecast_mobile(forecast_days: int = 90, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get revenue forecast"""
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC).date()
    total_rooms = await db.rooms.count_documents({"tenant_id": current_user.tenant_id})

    # Get historical data for forecasting
    lookback_days = 30
    start_historical = (today - timedelta(days=lookback_days)).isoformat()
    end_historical = today.isoformat()

    historical_query = {
        "tenant_id": current_user.tenant_id,
        "check_in": {"$gte": start_historical, "$lte": end_historical},
        "status": {"$in": ["confirmed", "guaranteed", "checked_in", "checked_out"]},
    }

    historical_revenue = 0.0
    historical_nights = 0

    async for booking in db.bookings.find(historical_query):
        historical_revenue += booking.get("total_amount", 0)
        historical_nights += booking.get("nights", 1)

    # Calculate historical averages
    avg_daily_revenue = historical_revenue / lookback_days if lookback_days > 0 else 0
    avg_occupancy = (historical_nights / (total_rooms * lookback_days) * 100) if lookback_days > 0 else 0
    avg_adr = (historical_revenue / historical_nights) if historical_nights > 0 else 0

    # Generate forecast
    forecast_data = []

    for i in range(forecast_days):
        forecast_date = today + timedelta(days=i)

        # Get existing bookings
        existing_bookings = await db.bookings.count_documents({"tenant_id": current_user.tenant_id, "check_in": forecast_date.isoformat(), "status": {"$in": ["confirmed", "guaranteed"]}})

        # Simple projection (can be enhanced with ML)
        projected_occupancy = min((existing_bookings / total_rooms * 100) + (avg_occupancy * 0.3), 100)
        projected_rooms = total_rooms * (projected_occupancy / 100)
        projected_adr = avg_adr * (1 + (projected_occupancy - 70) * 0.002)  # Price elasticity
        projected_revenue = projected_rooms * projected_adr
        projected_revpar = projected_revenue / total_rooms

        forecast_data.append(
            {
                "date": forecast_date.isoformat(),
                "day_of_week": forecast_date.strftime("%A"),
                "current_bookings": existing_bookings,
                "projected_occupancy": round(projected_occupancy, 1),
                "projected_adr": round(projected_adr, 2),
                "projected_revpar": round(projected_revpar, 2),
                "projected_revenue": round(projected_revenue, 2),
            }
        )

    return {
        "forecast_period": {"start_date": today.isoformat(), "end_date": (today + timedelta(days=forecast_days - 1)).isoformat(), "days": forecast_days},
        "historical_reference": {"avg_occupancy": round(avg_occupancy, 1), "avg_adr": round(avg_adr, 2), "avg_daily_revenue": round(avg_daily_revenue, 2)},
        "forecast_data": forecast_data,
    }


# ── GET /revenue/mobile/demand-heatmap ──
@router.get("/revenue/mobile/demand-heatmap")
async def get_demand_heatmap_mobile(months_ahead: int = 3, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get demand heatmap"""
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC).date()
    end_date = today + timedelta(days=months_ahead * 30)
    total_rooms = await db.rooms.count_documents({"tenant_id": current_user.tenant_id})

    heatmap_data = []

    # Generate data for each day
    current_date = today
    while current_date <= end_date:
        # Count bookings for this date
        bookings_count = await db.bookings.count_documents({"tenant_id": current_user.tenant_id, "check_in": current_date.isoformat(), "status": {"$in": ["confirmed", "guaranteed", "checked_in"]}})

        occupancy = (bookings_count / total_rooms * 100) if total_rooms > 0 else 0

        # Determine demand level
        if occupancy >= 90:
            demand_level = "very_high"
        elif occupancy >= 70:
            demand_level = "high"
        elif occupancy >= 40:
            demand_level = "medium"
        else:
            demand_level = "low"

        heatmap_data.append(
            {
                "date": current_date.isoformat(),
                "day_of_week": current_date.strftime("%A"),
                "bookings": bookings_count,
                "occupancy": round(occupancy, 1),
                "demand_level": demand_level,
                "available_rooms": total_rooms - bookings_count,
            }
        )

        current_date += timedelta(days=1)

    return {"period": {"start_date": today.isoformat(), "end_date": end_date.isoformat()}, "total_rooms": total_rooms, "heatmap_data": heatmap_data}


# ── GET /revenue/mobile/cancellations-noshows ──
@router.get("/revenue/mobile/cancellations-noshows")
async def get_cancellations_noshows_mobile(start_date: str | None = None, end_date: str | None = None, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get cancellation and no-show analysis"""
    current_user = await get_current_user(credentials)

    # Default to current month
    if not start_date or not end_date:
        today = datetime.now(UTC).date()
        start_date = today.replace(day=1).isoformat()
        last_day = (today.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        end_date = last_day.isoformat()

    # Cancelled bookings
    cancelled_bookings = []
    cancelled_revenue = 0.0

    async for booking in db.bookings.find({"tenant_id": current_user.tenant_id, "status": "cancelled", "check_in": {"$gte": start_date, "$lte": end_date}}):
        revenue_lost = booking.get("total_amount", 0)
        cancelled_revenue += revenue_lost

        cancelled_bookings.append(
            {
                "booking_id": booking.get("id"),
                "confirmation_number": booking.get("confirmation_number"),
                "check_in": booking.get("check_in"),
                "nights": booking.get("nights", 0),
                "revenue_lost": revenue_lost,
                "cancelled_at": (booking["cancelled_at"].isoformat() if hasattr(booking.get("cancelled_at"), "isoformat") else booking.get("cancelled_at")),
                "channel": booking.get("channel", "unknown"),
            }
        )

    # No-show bookings
    noshow_bookings = []
    noshow_revenue = 0.0

    async for booking in db.bookings.find({"tenant_id": current_user.tenant_id, "status": "no_show", "check_in": {"$gte": start_date, "$lte": end_date}}):
        revenue_lost = booking.get("total_amount", 0)
        noshow_revenue += revenue_lost

        noshow_bookings.append(
            {
                "booking_id": booking.get("id"),
                "confirmation_number": booking.get("confirmation_number"),
                "check_in": booking.get("check_in"),
                "nights": booking.get("nights", 0),
                "revenue_lost": revenue_lost,
                "channel": booking.get("channel", "unknown"),
            }
        )

    # Total bookings in period for comparison
    total_bookings = await db.bookings.count_documents({"tenant_id": current_user.tenant_id, "check_in": {"$gte": start_date, "$lte": end_date}})

    cancellation_rate = (len(cancelled_bookings) / total_bookings * 100) if total_bookings > 0 else 0
    noshow_rate = (len(noshow_bookings) / total_bookings * 100) if total_bookings > 0 else 0

    return {
        "period": {"start_date": start_date, "end_date": end_date},
        "cancellations": {"count": len(cancelled_bookings), "rate_percentage": round(cancellation_rate, 2), "revenue_lost": cancelled_revenue, "bookings": cancelled_bookings},
        "noshows": {"count": len(noshow_bookings), "rate_percentage": round(noshow_rate, 2), "revenue_lost": noshow_revenue, "bookings": noshow_bookings},
        "total_bookings": total_bookings,
        "combined_loss": cancelled_revenue + noshow_revenue,
    }


# ── POST /revenue/mobile/rate-override ──
@router.post("/revenue/mobile/rate-override", operation_id="pos_create_rate_override_mobile")
async def create_rate_override_mobile(
    room_type: str,
    date: str,
    override_rate: float,
    reason: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("manage_rates")),  # v89 DW
):
    """Create rate override for specific date"""
    current_user = await get_current_user(credentials)

    # Gercek "mevcut rate" kaynagi (rate tablosu) bu ucta yok; uydurma 1000.0
    # baz alip sahte fark/yuzde uretmek yerine None birak (fail-closed).
    original_rate = None

    override_id = str(uuid.uuid4())
    override = {
        "id": override_id,
        "tenant_id": current_user.tenant_id,
        "room_type": room_type,
        "date": datetime.fromisoformat(date),
        "original_rate": original_rate,
        "override_rate": override_rate,
        "reason": reason,
        "approved_by": current_user.username,
        "created_by": current_user.username,
        "created_at": datetime.now(UTC),
    }

    await db.rate_overrides.insert_one(override)

    return {
        "message": "Rate override created",
        "override_id": override_id,
        "room_type": room_type,
        "date": date,
        "original_rate": original_rate,
        "override_rate": override_rate,
        "difference": (override_rate - original_rate) if original_rate is not None else None,
        "percentage_change": ((override_rate - original_rate) / original_rate * 100) if original_rate else None,
    }


# ── GET /revenue/mobile/rate-overrides ──
@router.get("/revenue/mobile/rate-overrides")
async def get_rate_overrides_mobile(start_date: str | None = None, end_date: str | None = None, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get rate overrides"""
    current_user = await get_current_user(credentials)

    query = {"tenant_id": current_user.tenant_id}

    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter["$gte"] = datetime.fromisoformat(start_date)
        if end_date:
            date_filter["$lte"] = datetime.fromisoformat(end_date)
        query["date"] = date_filter

    overrides = []
    async for override in db.rate_overrides.find(query).sort("date", 1):
        _orig = override.get("original_rate")
        _ovr = override.get("override_rate")
        overrides.append(
            {
                "id": override.get("id"),
                "room_type": override.get("room_type"),
                "date": override.get("date").isoformat() if override.get("date") else None,
                "original_rate": _orig,
                "override_rate": _ovr,
                # original_rate yoksa fark hesaplanamaz (None); POST ile tutarli, None-safe
                "difference": (_ovr - _orig) if (_orig is not None and _ovr is not None) else None,
                "reason": override.get("reason"),
                "approved_by": override.get("approved_by"),
                "created_at": override.get("created_at").isoformat() if override.get("created_at") else None,
            }
        )

    return {"overrides": overrides, "count": len(overrides)}
