"""
Observability — Night Audit & Operational Metrics API
Exposes runtime metrics for load tests, night audit, and operational monitoring.
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from common.context import OperationContext
from core.database import db
from core.security import get_current_user
from models.schemas import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/metrics", tags=["Operational Metrics"])


@router.get("/night-audit")
async def get_night_audit_metrics(
    current_user: User = Depends(get_current_user),
):
    """Night audit operational metrics for dashboard and alerting."""
    ctx = OperationContext.from_user(current_user)
    tid = ctx.tenant_id

    # Last 10 runs
    runs = await db.night_audit_runs.find(
        {"tenant_id": tid}, {"_id": 0}
    ).sort("started_at", -1).limit(10).to_list(10)

    last_run = runs[0] if runs else None
    durations = [r.get("duration_ms", 0) for r in runs if r.get("duration_ms")]
    avg_duration = sum(durations) / len(durations) if durations else 0
    exception_counts = [r.get("exceptions_count", 0) for r in runs]
    avg_exceptions = sum(exception_counts) / len(exception_counts) if exception_counts else 0

    # Business date status
    settings = await db.tenant_settings.find_one({"tenant_id": tid}, {"_id": 0})
    business_date = (settings or {}).get("business_date", datetime.now(timezone.utc).date().isoformat())
    today = datetime.now(timezone.utc).date().isoformat()
    is_stale = business_date < today

    return {
        "business_date": business_date,
        "is_business_date_stale": is_stale,
        "last_run": {
            "audit_id": last_run.get("id") if last_run else None,
            "status": last_run.get("status") if last_run else None,
            "business_date": last_run.get("business_date") if last_run else None,
            "duration_ms": last_run.get("duration_ms") if last_run else None,
            "exceptions_count": last_run.get("exceptions_count", 0) if last_run else 0,
            "rooms_processed": last_run.get("rooms_processed", 0) if last_run else 0,
            "total_room_revenue": last_run.get("total_room_revenue", 0) if last_run else 0,
        },
        "trends": {
            "avg_duration_ms": round(avg_duration),
            "avg_exceptions": round(avg_exceptions, 1),
            "total_runs": len(runs),
            "success_rate": round(
                len([r for r in runs if r.get("status") in ("completed", "completed_with_exceptions")]) / len(runs) * 100, 1
            ) if runs else 0,
        },
    }


@router.get("/operational")
async def get_operational_metrics(
    current_user: User = Depends(get_current_user),
):
    """Aggregated operational metrics for load testing and monitoring."""
    ctx = OperationContext.from_user(current_user)
    tid = ctx.tenant_id
    now = datetime.now(timezone.utc)

    # Room status distribution
    room_statuses = {}
    async for doc in db.rooms.aggregate([
        {"$match": {"tenant_id": tid}},
        {"$group": {"_id": "$status", "count": {"$sum": 1}}},
    ]):
        room_statuses[doc["_id"] or "unknown"] = doc["count"]

    total_rooms = sum(room_statuses.values())
    occupancy = room_statuses.get("occupied", 0) / total_rooms * 100 if total_rooms else 0

    # Today's booking pipeline
    today = now.date().isoformat()
    arrivals = await db.bookings.count_documents({
        "tenant_id": tid, "check_in": today,
        "status": {"$in": ["confirmed", "guaranteed"]},
    })
    departures = await db.bookings.count_documents({
        "tenant_id": tid, "check_out": today, "status": "checked_in",
    })
    in_house = await db.bookings.count_documents({
        "tenant_id": tid, "status": "checked_in",
    })

    # Open folios
    open_folios = await db.folios.count_documents({
        "tenant_id": tid, "status": "open",
    })

    # HK tasks
    hk_pending = await db.housekeeping_tasks.count_documents({
        "tenant_id": tid, "status": {"$in": ["new", "assigned"]},
    })
    hk_in_progress = await db.housekeeping_tasks.count_documents({
        "tenant_id": tid, "status": "in_progress",
    })

    # Audit events last hour
    one_hour_ago = (now - timedelta(hours=1)).isoformat()
    audit_events_1h = await db.audit_logs.count_documents({
        "tenant_id": tid, "timestamp": {"$gte": one_hour_ago},
    })

    return {
        "timestamp": now.isoformat(),
        "rooms": {
            "total": total_rooms,
            "occupancy_pct": round(occupancy, 1),
            "status_distribution": room_statuses,
        },
        "bookings": {
            "arrivals_today": arrivals,
            "departures_today": departures,
            "in_house": in_house,
        },
        "folios": {"open": open_folios},
        "housekeeping": {
            "pending": hk_pending,
            "in_progress": hk_in_progress,
        },
        "audit": {"events_last_hour": audit_events_1h},
    }
