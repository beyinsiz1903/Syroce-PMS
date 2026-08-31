"""Auto-split from misc_router.py — backward-compatible sub-router."""

import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials

from core.database import db
from core.security import get_current_user, security
from models.schemas import User
from modules.pms_core.role_permission_service import require_op
from modules.pms_core.stay_night_metrics import load_stay_night_metrics

from ._common import (
    PingTestRequest,
    cached,
)

logger = logging.getLogger(__name__)

sub_router = APIRouter()


@sub_router.get("/analytics/7day-trend")
@cached(ttl=600, key_prefix="analytics_7day_trend")
async def get_7day_trend(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v86 DV: 7-day trend exec
):
    """
    Get 7-day trend for arrivals, departures, revenue, occupancy.
    Sprint 33: 28 sequential queries → 28 parallel via asyncio.gather (~7×).
    """
    import asyncio as _asyncio

    try:
        today = datetime.now(UTC).date()
        days = [today - timedelta(days=i) for i in range(6, -1, -1)]
        tenant_id = current_user.tenant_id

        stay_metrics = await load_stay_night_metrics(db, tenant_id, days[0], days[-1])
        stay_by_date = {row["date"]: row for row in stay_metrics}

        async def _day_metrics(date):
            date_str = date.isoformat()
            arrivals_q = db.bookings.count_documents({"check_in": date_str, "tenant_id": tenant_id})
            departures_q = db.bookings.count_documents({"check_out": date_str, "tenant_id": tenant_id})
            arrivals, departures = await _asyncio.gather(arrivals_q, departures_q)
            stay = stay_by_date[date_str]
            return {
                "date": date_str,
                "day_name": date.strftime("%a"),
                "arrivals": arrivals,
                "departures": departures,
                "occupancy": stay["occupied_rooms"],
                "revenue": stay["revenue"],
                "adr": stay["adr"],
                "revpar": stay["revpar"],
            }

        trend_data = await _asyncio.gather(*(_day_metrics(d) for d in days))

        # Calculate changes
        if len(trend_data) >= 2:
            latest = trend_data[-1]
            previous = trend_data[-2]

            changes = {
                "arrivals_change": latest["arrivals"] - previous["arrivals"],
                "departures_change": latest["departures"] - previous["departures"],
                "occupancy_change": latest["occupancy"] - previous["occupancy"],
                "revenue_change": round(latest["revenue"] - previous["revenue"], 2),
            }
        else:
            changes = {}

        return {"trend": trend_data, "changes": changes, "period": "7 days", "generated_at": datetime.now(UTC).isoformat()}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get 7-day trend: {str(e)}")


# ============================================================================
# SLA CONFIGURATION & TRACKING
# ============================================================================


@sub_router.post("/network/ping")
async def network_ping_test(
    request: PingTestRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """
    Perform ping test to measure latency
    """
    try:
        import socket
        import time

        # Use TCP connection test instead of ICMP ping (which requires root)
        ping_times = []
        successful_pings = 0

        for i in range(request.count):
            try:
                start_time = time.time()

                # Try to connect to port 80 (HTTP) or 443 (HTTPS) for web connectivity test
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(3)  # 3 second timeout

                # For IP addresses, use port 80. For domain names, try 80 first, then 443
                port = 80
                if not request.target.replace(".", "").isdigit():  # Not an IP address
                    try:
                        result = sock.connect_ex((request.target, 443))  # Try HTTPS first
                        if result != 0:
                            sock.close()
                            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                            sock.settimeout(3)
                            port = 80
                    except Exception:
                        port = 80

                result = sock.connect_ex((request.target, port))
                end_time = time.time()

                if result == 0:
                    latency_ms = (end_time - start_time) * 1000
                    ping_times.append(latency_ms)
                    successful_pings += 1

                sock.close()

                # Small delay between pings
                if i < request.count - 1:
                    time.sleep(0.5)

            except Exception:
                # Connection failed for this attempt
                pass

        if ping_times:
            avg_latency = sum(ping_times) / len(ping_times)
            min_latency = min(ping_times)
            max_latency = max(ping_times)
            packet_loss = ((request.count - successful_pings) / request.count) * 100
        else:
            avg_latency = 0
            min_latency = 0
            max_latency = 0
            packet_loss = 100

        # Determine connection quality
        if avg_latency < 50:
            quality = "excellent"
        elif avg_latency < 100:
            quality = "good"
        elif avg_latency < 200:
            quality = "fair"
        else:
            quality = "poor"

        return {
            "target": request.target,
            "packets_sent": request.count,
            "packets_received": successful_pings,
            "packet_loss_percent": round(packet_loss, 2),
            "latency": {"average": round(avg_latency, 2), "min": round(min_latency, 2), "max": round(max_latency, 2)},
            "quality": quality,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ping failed: {str(e)}")


# ===== LANDING PAGE - DEMO REQUEST ENDPOINT =====


@sub_router.get("/analytics/occupancy-trend")
async def get_occupancy_trend(days: int = 30, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get occupancy trend for the last N days"""
    current_user = await get_current_user(credentials)

    end_date = datetime.now(UTC).date()
    start_date = end_date - timedelta(days=max(days - 1, 0))
    trend_data = await load_stay_night_metrics(db, current_user.tenant_id, start_date, end_date)

    return {"success": True, "days": days, "trend": trend_data, "average_occupancy": round(sum(d["occupancy_rate"] for d in trend_data) / len(trend_data), 2) if trend_data else 0}


@sub_router.get("/analytics/revenue-trend")
async def get_revenue_trend(days: int = 30, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get revenue trend for the last N days"""
    current_user = await get_current_user(credentials)

    end_date = datetime.now(UTC)
    start_date = end_date - timedelta(days=days)

    # Get all folios in date range
    folios = await db.folios.find({"tenant_id": current_user.tenant_id, "created_at": {"$gte": start_date.isoformat(), "$lte": end_date.isoformat()}}).to_list(length=10000)

    # Calculate daily revenue
    trend_data = []
    current = start_date

    while current <= end_date:
        # Sum revenue for this date
        daily_revenue = 0
        for folio in folios:
            folio_date = datetime.fromisoformat(folio["created_at"].replace("Z", "+00:00"))
            if folio_date.date() == current.date():
                daily_revenue += folio.get("total_charges", 0)

        trend_data.append({"date": current.strftime("%Y-%m-%d"), "revenue": round(daily_revenue, 2)})

        current += timedelta(days=1)

    total_revenue = sum(d["revenue"] for d in trend_data)
    average_daily = round(total_revenue / len(trend_data), 2) if trend_data else 0

    return {"success": True, "days": days, "trend": trend_data, "total_revenue": round(total_revenue, 2), "average_daily_revenue": average_daily}


@sub_router.get("/analytics/booking-trends")
@cached(ttl=300, key_prefix="analytics_booking_trends")  # v95 — 5 min cache
async def get_booking_trends(days: int = 30, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get canonical stay-night, ADR and RevPAR trends for the last N days."""
    current_user = await get_current_user(credentials)

    end_date = datetime.now(UTC).date()
    start_date = end_date - timedelta(days=max(days - 1, 0))
    metrics = await load_stay_night_metrics(db, current_user.tenant_id, start_date, end_date)
    trend_data = [{**row, "bookings": row["occupied_rooms"]} for row in metrics]
    total_room_nights = sum(row["occupied_rooms"] for row in metrics)
    return {
        "success": True,
        "days": days,
        "trend": trend_data,
        "total_room_nights": total_room_nights,
        "average_daily_occupied_rooms": round(total_room_nights / len(metrics), 2) if metrics else 0,
    }
