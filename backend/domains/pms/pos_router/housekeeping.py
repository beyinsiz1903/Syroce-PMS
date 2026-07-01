"""
housekeeping

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
    require_module,  # v89 DW
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


# ── GET /housekeeping/status-change-logs ──
@router.get("/housekeeping/status-change-logs")
async def get_status_change_logs(room_id: str | None = None, limit: int = 50, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get room status change logs (audit trail)"""
    current_user = await get_current_user(credentials)

    query = {"tenant_id": current_user.tenant_id, "action": "ROOM_STATUS_CHANGE"}

    if room_id:
        query["entity_id"] = room_id

    logs = []
    async for log in db.audit_logs.find(query).sort("timestamp", -1).limit(limit):
        room = await db.rooms.find_one({"id": log.get("entity_id"), "tenant_id": current_user.tenant_id})

        logs.append(
            {
                "log_id": log.get("id"),
                "room_id": log.get("entity_id"),
                "room_number": room.get("room_number") if room else "N/A",
                "old_status": log.get("changes", {}).get("old_status"),
                "new_status": log.get("changes", {}).get("new_status"),
                "changed_by": log.get("user_name"),
                "timestamp": log.get("timestamp").isoformat() if log.get("timestamp") else None,
                "reason": log.get("changes", {}).get("reason", ""),
            }
        )

    return {"logs": logs, "count": len(logs)}


# ── POST /housekeeping/lost-found/item ──
@router.post("/housekeeping/lost-found/item")
async def create_lost_found_item(
    item: LostFoundItemCreate,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_module("housekeeping")),  # v89 DW
):
    """Create a new lost and found item"""
    current_user = await get_current_user(credentials)

    item_id = str(uuid.uuid4())
    lost_found_item = {
        "id": item_id,
        "tenant_id": current_user.tenant_id,
        "item_description": item.item_description,
        "location_found": item.location_found,
        "found_by": item.found_by,
        "category": item.category,
        "room_number": item.room_number,
        "guest_name": item.guest_name,
        "notes": item.notes,
        "status": "unclaimed",
        "found_date": datetime.now(UTC),
        "created_by": current_user.username,
        "created_at": datetime.now(UTC),
    }

    await db.lost_found.insert_one(lost_found_item)

    return {"message": "Lost & found item created", "item_id": item_id, "item_description": item.item_description}


# ── GET /housekeeping/lost-found/items ──
@router.get("/housekeeping/lost-found/items")
async def get_lost_found_items(status: str | None = None, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get lost and found items"""
    current_user = await get_current_user(credentials)

    query = {"tenant_id": current_user.tenant_id}
    if status:
        query["status"] = status

    items = []
    async for item in db.lost_found.find(query).sort("found_date", -1):
        items.append(
            {
                "id": item.get("id"),
                "item_description": item.get("item_description"),
                "category": item.get("category"),
                "location_found": item.get("location_found"),
                "room_number": item.get("room_number"),
                "guest_name": item.get("guest_name"),
                "found_by": item.get("found_by"),
                "found_date": item.get("found_date").isoformat() if item.get("found_date") else None,
                "status": item.get("status"),
                "notes": item.get("notes"),
            }
        )

    return {
        "items": items,
        "count": len(items),
        "by_status": {
            "unclaimed": len([i for i in items if i["status"] == "unclaimed"]),
            "claimed": len([i for i in items if i["status"] == "claimed"]),
            "disposed": len([i for i in items if i["status"] == "disposed"]),
        },
    }


# ── GET /housekeeping/task-assignments ──
@router.get("/housekeeping/task-assignments")
async def get_task_assignments(date: str | None = None, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get housekeeping task assignments and routes"""
    current_user = await get_current_user(credentials)

    if date:
        target_date = datetime.fromisoformat(date).replace(tzinfo=UTC)
    else:
        target_date = datetime.now(UTC)

    start_of_day = target_date.replace(hour=0, minute=0, second=0)
    end_of_day = target_date.replace(hour=23, minute=59, second=59)

    # Get all housekeeping staff
    staff_list = []
    async for task in db.housekeeping_tasks.find({"tenant_id": current_user.tenant_id, "assigned_to": {"$exists": True, "$ne": None}}).limit(100):
        staff_name = task.get("assigned_to")
        if staff_name and staff_name not in staff_list:
            staff_list.append(staff_name)

    # Get assignments for each staff
    assignments = []

    for staff_name in staff_list:
        staff_tasks = []
        completed_count = 0

        async for task in db.housekeeping_tasks.find({"tenant_id": current_user.tenant_id, "assigned_to": staff_name, "created_at": {"$gte": start_of_day, "$lte": end_of_day}}).sort("room_number", 1):
            room = await db.rooms.find_one({"id": task.get("room_id"), "tenant_id": current_user.tenant_id})

            task_info = {
                "task_id": task.get("id"),
                "room_id": task.get("room_id"),
                "room_number": room.get("room_number") if room else task.get("room_number"),
                "floor": room.get("floor") if room else 0,
                "task_type": task.get("task_type"),
                "status": task.get("status"),
                "priority": task.get("priority", "normal"),
                "started_at": task.get("started_at").isoformat() if task.get("started_at") else None,
            }

            staff_tasks.append(task_info)

            if task.get("status") == "completed":
                completed_count += 1

        # Sort tasks by floor and room number for optimal route
        staff_tasks.sort(key=lambda x: (x["floor"], x["room_number"]))

        assignments.append(
            {
                "staff_name": staff_name,
                "total_tasks": len(staff_tasks),
                "completed": completed_count,
                "in_progress": len([t for t in staff_tasks if t["status"] == "in_progress"]),
                "pending": len([t for t in staff_tasks if t["status"] in ["new", "assigned"]]),
                "tasks": staff_tasks,
                "route": [t["room_number"] for t in staff_tasks],
            }
        )

    return {"date": target_date.date().isoformat(), "assignments": assignments, "total_staff": len(assignments), "total_tasks": sum(a["total_tasks"] for a in assignments)}
