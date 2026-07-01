"""
gm

Auto-split sub-router (shared imports/classes inlined).
"""

"""
PMS / Dashboard Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.database import db
from core.security import (
    get_current_user,
    security,
)
from modules.pms_core.role_permission_service import require_op

logger = logging.getLogger(__name__)

try:
    from cache_manager import cached
except ImportError:

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


# ── Inline Models ──


class BudgetMonth(BaseModel):
    month: int
    occ_target: float = 0
    adr_target: float = 0
    rev_target: float = 0


class BudgetConfig(BaseModel):
    year: int
    currency: str = "TRY"
    months: list[BudgetMonth]


# ============= CHECK-IN ENHANCEMENTS =============


# ===== F&B MODULE ENHANCEMENTS =====


# 2. GET /api/executive/performance-alerts - Performance alerts


# 3. GET /api/executive/daily-summary - Daily summary


# ============================================================================
# NOTIFICATION SYSTEM - Push Notifications
# ============================================================================


async def _build_complaint_management(current_user) -> dict:
    """Complaint management ortak helper — 3 feedback find'ı tek gather'da paralel."""
    tid = current_user.tenant_id
    active_docs, all_low_docs, resolved_docs = await asyncio.gather(
        db.feedback.find(
            {
                "tenant_id": tid,
                "rating": {"$lte": 2},
                "resolved": {"$ne": True},
            }
        )
        .sort("created_at", -1)
        .limit(20)
        .to_list(20),
        db.feedback.find(
            {"tenant_id": tid, "rating": {"$lte": 2}},
            {"_id": 0, "category": 1},
        ).to_list(10000),
        db.feedback.find(
            {
                "tenant_id": tid,
                "rating": {"$lte": 2},
                "resolved": True,
                "resolved_at": {"$exists": True},
            }
        )
        .limit(50)
        .to_list(50),
    )

    now_utc = datetime.now(UTC)
    active_complaints = []
    for feedback in active_docs:
        try:
            ca = feedback.get("created_at") or now_utc.isoformat()
            days_open = (now_utc - datetime.fromisoformat(str(ca).replace("Z", "+00:00"))).days
        except Exception:
            days_open = 0
        active_complaints.append(
            {
                "id": feedback.get("id", str(uuid.uuid4())),
                "guest_name": feedback.get("guest_name", "Anonim"),
                "rating": feedback.get("rating", 1),
                "category": feedback.get("category", "general"),
                "comment": feedback.get("comment", ""),
                "created_at": feedback.get("created_at"),
                "days_open": days_open,
            }
        )

    categories: dict[str, int] = {}
    for feedback in all_low_docs:
        category = feedback.get("category", "general")
        categories[category] = categories.get(category, 0) + 1

    category_breakdown = [
        {
            "category": cat,
            "category_tr": {
                "room": "Oda",
                "service": "Servis",
                "cleanliness": "Temizlik",
                "fnb": "Yiyecek & İçecek",
                "general": "Genel",
            }.get(cat, cat),
            "count": count,
        }
        for cat, count in categories.items()
    ]

    resolution_hours_list = []
    for feedback in resolved_docs:
        try:
            created = datetime.fromisoformat(feedback["created_at"].replace("Z", "+00:00"))
            resolved = datetime.fromisoformat(feedback["resolved_at"].replace("Z", "+00:00"))
            resolution_hours_list.append((resolved - created).total_seconds() / 3600)
        except Exception:
            continue
    avg_resolution_time = sum(resolution_hours_list) / len(resolution_hours_list) if resolution_hours_list else 24

    return {
        "active_complaints": active_complaints,
        "active_count": len(active_complaints),
        "category_breakdown": category_breakdown,
        "avg_resolution_time_hours": round(avg_resolution_time, 1),
        "urgent_complaints": len([c for c in active_complaints if c["days_open"] > 2]),
    }


# 3. GET /api/gm/snapshot-enhanced - Enhanced snapshot mode


# 3. GET /api/gm/snapshot-enhanced - Enhanced snapshot mode


# ============================================================================
# SALES & CRM MOBILE - Satış & Müşteri Yönetimi
# ============================================================================

# Models

router = APIRouter(prefix="/api", tags=["PMS / Dashboard"])


# ── GET /gm/team-performance + GET /gm/complaint-management ──
@router.get("/gm/team-performance")
@router.get("/gm/complaint-management")
async def get_complaint_management(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_system_diagnostics")),  # v103 DX alias drift fix
):
    """
    Get complaint management overview
    Active complaints, categories, resolution times
    """
    current_user = await get_current_user(credentials)
    return await _build_complaint_management(current_user)


# ── GET /gm/complaint-management ──
@router.get("/gm/complaint-management")
async def get_complaint_management_v2(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """v2 — _build_complaint_management helper'ını kullanır (DRY + N+1 fix)."""
    current_user = await get_current_user(credentials)
    return await _build_complaint_management(current_user)


# ── GET /gm/snapshot-enhanced ──
async def _compute_period_metrics(tid: str, date, total_rooms: int) -> dict:
    """Compute real metrics for a single calendar date from bookings/payments/feedback.

    Used identically for today, yesterday and last week so the dashboard's
    period-over-period deltas reflect actual change rather than fixed offsets.
    `status` reflects the *current* booking state, so it cannot be used to
    reconstruct a past day's arrivals/departures (a booking that arrived last
    week is `checked_out` now); arrivals/departures are therefore counted as
    the day's scheduled, non-cancelled bookings. Occupancy is derived from
    bookings spanning the night (no per-date room-status history exists).
    Date fields are stored as ISO strings, so range/exact string matches hold.
    """
    date_iso = date.isoformat()
    next_iso = (date + timedelta(days=1)).isoformat()
    occupied, payment_agg, check_ins, check_outs, complaints = await asyncio.gather(
        db.bookings.count_documents(
            {
                "tenant_id": tid,
                "check_in": {"$lte": date_iso},
                "check_out": {"$gt": date_iso},
                "status": {"$nin": ["cancelled", "no_show"]},
            }
        ),
        db.payments.aggregate(
            [
                {"$match": {"tenant_id": tid, "payment_date": {"$gte": date_iso, "$lt": next_iso}}},
                {"$group": {"_id": None, "t": {"$sum": "$amount"}}},
            ]
        ).to_list(1),
        db.bookings.count_documents(
            {
                "tenant_id": tid,
                "check_in": date_iso,
                "status": {"$nin": ["cancelled", "no_show"]},
            }
        ),
        db.bookings.count_documents(
            {
                "tenant_id": tid,
                "check_out": date_iso,
                "status": {"$nin": ["cancelled", "no_show"]},
            }
        ),
        db.feedback.count_documents(
            {
                "tenant_id": tid,
                "rating": {"$lte": 2},
                "created_at": {"$gte": date_iso, "$lt": next_iso},
            }
        ),
    )
    revenue = (payment_agg[0]["t"] if payment_agg else 0) or 0
    # ADR (Average Daily Rate) = revenue / rooms sold that night.
    # RevPAR (Revenue per Available Room) = revenue / total sellable rooms.
    # Mirrors the executive dashboard convention; RevPAR = ADR * occupancy holds
    # by construction. `revenue` here is the day's collected payments (same
    # caveat as the occupancy/check-in figures: derived from real data, not a
    # dedicated room-revenue ledger).
    adr = round(revenue / occupied, 2) if occupied > 0 else 0
    revpar = round(revenue / total_rooms, 2) if total_rooms > 0 else 0
    return {
        "date": date_iso,
        "occupancy": round((occupied / total_rooms * 100) if total_rooms > 0 else 0, 1),
        "revenue": revenue,
        "adr": adr,
        "revpar": revpar,
        "check_ins": check_ins,
        "check_outs": check_outs,
        "complaints": complaints,
        "pending_tasks": 0,  # filled in by caller (current backlog, no per-date history)
    }


@router.get("/gm/snapshot-enhanced")
async def get_enhanced_snapshot(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """
    Enhanced GM snapshot - all critical metrics in one view
    Today vs Yesterday vs Last Week (all computed from real historical data).
    """
    current_user = await get_current_user(credentials)
    tid = current_user.tenant_id

    today = datetime.now(UTC).date()
    yesterday = today - timedelta(days=1)
    last_week = today - timedelta(days=7)

    # total_rooms + current high/urgent pending backlog are point-in-time reads;
    # everything else is computed per-date so the comparison is apples-to-apples.
    # open_faults / housekeeping / channels are also point-in-time ("now") since
    # no per-date history exists for them.
    #
    # Open faults span TWO collections by design (we do not reconcile them here):
    #   - maintenance_tasks: the dashboard/work-order task system.
    #   - tasks(department=maintenance): faults filed from the mobile maintenance
    #     quick-issue flow.
    # A fault only ever lands in one of them (distinct write paths), so summing
    # the non-terminal counts is an honest total, not a double-count.
    NON_TERMINAL_FAULT = ["completed", "done", "closed", "cancelled", "resolved"]
    today_iso = today.isoformat()
    last_30_iso = (today - timedelta(days=30)).isoformat()
    (
        total_rooms,
        pending_tasks,
        open_faults_mt,
        open_faults_tasks,
        room_status_rows,
        channel_rows,
    ) = await asyncio.gather(
        db.rooms.count_documents({"tenant_id": tid}),
        db.maintenance_tasks.count_documents(
            {
                "tenant_id": tid,
                "status": "pending",
                "priority": {"$in": ["high", "urgent"]},
            }
        ),
        db.maintenance_tasks.count_documents(
            {
                "tenant_id": tid,
                "status": {"$nin": NON_TERMINAL_FAULT},
            }
        ),
        db.tasks.count_documents(
            {
                "tenant_id": tid,
                "department": "maintenance",
                "status": {"$nin": NON_TERMINAL_FAULT},
            }
        ),
        db.rooms.aggregate(
            [
                {
                    "$match": {
                        "tenant_id": tid,
                        "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
                    }
                },
                {"$group": {"_id": "$status", "count": {"$sum": 1}}},
            ]
        ).to_list(20),
        db.bookings.aggregate(
            [
                {
                    "$match": {
                        "tenant_id": tid,
                        "check_in": {"$gte": last_30_iso, "$lte": today_iso},
                        "status": {"$nin": ["cancelled", "no_show"]},
                    }
                },
                {
                    "$group": {
                        "_id": {"$ifNull": ["$booking_source", "$channel"]},
                        "bookings": {"$sum": 1},
                        "revenue": {"$sum": "$total_amount"},
                    }
                },
                {"$sort": {"revenue": -1}},
            ]
        ).to_list(50),
    )
    open_faults = open_faults_mt + open_faults_tasks

    rs = {r["_id"]: r["count"] for r in room_status_rows}
    housekeeping = {
        "total_rooms": sum(rs.values()),
        "available": rs.get("available", 0),
        "occupied": rs.get("occupied", 0),
        "dirty": rs.get("dirty", 0),
        "cleaning": rs.get("cleaning", 0),
        "inspected": rs.get("inspected", 0),
        "out_of_order": rs.get("out_of_order", 0),
        "maintenance": rs.get("maintenance", 0) + rs.get("out_of_service", 0),
        "ready_rooms": rs.get("available", 0) + rs.get("inspected", 0),
        "dirty_rooms": rs.get("dirty", 0) + rs.get("cleaning", 0),
    }
    channels = [
        {
            "source": (row.get("_id") or "direct"),
            "bookings": row.get("bookings", 0),
            "revenue": round(row.get("revenue", 0) or 0, 2),
        }
        for row in channel_rows
    ]

    today_metrics, yesterday_metrics, last_week_metrics = await asyncio.gather(
        _compute_period_metrics(tid, today, total_rooms),
        _compute_period_metrics(tid, yesterday, total_rooms),
        _compute_period_metrics(tid, last_week, total_rooms),
    )

    # pending_tasks: today is the live backlog; yesterday/last-week come from the
    # daily snapshots the night audit records (no per-date backlog history
    # otherwise). When a snapshot is missing for a period, fall back to today's
    # backlog so the delta is an honest 0 rather than a fabricated offset.
    from domains.pms.dashboard_router.snapshots import get_pending_task_snapshot

    yest_snap, last_week_snap = await asyncio.gather(
        get_pending_task_snapshot(tid, yesterday.isoformat()),
        get_pending_task_snapshot(tid, last_week.isoformat()),
    )
    today_metrics["pending_tasks"] = pending_tasks
    yesterday_metrics["pending_tasks"] = yest_snap if yest_snap is not None else pending_tasks
    last_week_metrics["pending_tasks"] = last_week_snap if last_week_snap is not None else pending_tasks

    return {
        "today": today_metrics,
        "yesterday": yesterday_metrics,
        "last_week": last_week_metrics,
        "open_faults": open_faults,
        "housekeeping": housekeeping,
        "channels": channels,
        "trends": {
            "occupancy_trend": "up" if today_metrics["occupancy"] > yesterday_metrics["occupancy"] else "down",
            "revenue_trend": "up" if today_metrics["revenue"] > yesterday_metrics["revenue"] else "down",
            "complaints_trend": "up" if today_metrics["complaints"] > yesterday_metrics["complaints"] else "down",
        },
    }
