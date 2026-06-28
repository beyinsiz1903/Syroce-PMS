"""Auto-split from hotel_services.py — backward-compatible sub-router."""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.schemas import User, _ensure_hotel_context
from modules.pms_core.role_permission_service import require_module as require_module_v99
from modules.pms_core.role_permission_service import require_module as require_module_v101

from ._common import (
    LostFoundCreate,
    LostFoundUpdate,
    WakeUpCallCreate,
    WakeUpCallUpdate,
    _annotate_due,
    _fire_due_wake_up_alerts,
)

logger = logging.getLogger(__name__)
sub_router = APIRouter()


@sub_router.get("/wake-up-calls")
async def get_wake_up_calls(
    date: str | None = None,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Get wake-up calls, optionally filtered by date and status.

    Side-effect: any pending call whose scheduled time has arrived gets a
    notification created (once) so the bell-center picks it up. The
    response also carries `is_due=true` for those rows so the UI can
    play an alarm sound and show a desktop notification.
    """
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    query = {"tenant_id": tid}
    if date:
        query["wake_date"] = date
    if status:
        query["status"] = status

    calls = []
    async for c in db.wake_up_calls.find(query, {"_id": 0}).sort([("wake_date", 1), ("wake_time", 1)]):
        calls.append(c)

    # Fire alerts for any newly-due pending calls in the returned set.
    await _fire_due_wake_up_alerts(tid, calls)
    _annotate_due(calls)

    # Stats — use hotel-local (Istanbul) date, not UTC, so the dashboard
    # matches what the front-desk operator considers "today" near midnight.
    try:
        from zoneinfo import ZoneInfo

        today = datetime.now(ZoneInfo("Europe/Istanbul")).strftime("%Y-%m-%d")
    except Exception:
        today = (datetime.now(UTC) + timedelta(hours=3)).strftime("%Y-%m-%d")
    today_calls = [c for c in calls if c.get("wake_date") == today]
    pending = len([c for c in today_calls if c.get("status") == "pending"])
    completed = len([c for c in today_calls if c.get("status") == "completed"])
    missed = len([c for c in today_calls if c.get("status") == "missed"])
    due_now = len([c for c in calls if c.get("is_due")])

    return {
        "calls": calls,
        "stats": {
            "total_today": len(today_calls),
            "pending": pending,
            "completed": completed,
            "missed": missed,
            "due_now": due_now,
        },
    }


@sub_router.post("/wake-up-calls")
async def create_wake_up_call(
    data: WakeUpCallCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    """Create a new wake-up call."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    call = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "room_number": data.room_number,
        "guest_name": data.guest_name,
        "booking_id": data.booking_id,
        "wake_time": data.wake_time,
        "wake_date": data.wake_date,
        "recurring": data.recurring,
        "recurrence_end_date": data.recurrence_end_date,
        "notes": data.notes,
        "method": data.method,
        "status": "pending",
        "attempt_count": 0,
        "created_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.wake_up_calls.insert_one(call)
    call.pop("_id", None)

    return {"success": True, "call": call}


@sub_router.put("/wake-up-calls/{call_id}")
async def update_wake_up_call(
    call_id: str,
    data: WakeUpCallUpdate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    """Update a wake-up call status."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    updates = {}
    if data.wake_time:
        updates["wake_time"] = data.wake_time
    if data.wake_date:
        updates["wake_date"] = data.wake_date
    if data.status:
        updates["status"] = data.status
        if data.status == "completed":
            updates["completed_at"] = datetime.now(UTC).isoformat()
            updates["completed_by"] = data.completed_by or current_user.name
    if data.notes is not None:
        updates["notes"] = data.notes
    if data.attempt_count is not None:
        updates["attempt_count"] = data.attempt_count
    if data.response:
        updates["response"] = data.response

    updates["updated_at"] = datetime.now(UTC).isoformat()

    result = await db.wake_up_calls.update_one({"id": call_id, "tenant_id": tid}, {"$set": updates})

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Wake-up call bulunamadi")

    updated = await db.wake_up_calls.find_one({"id": call_id}, {"_id": 0})
    return {"success": True, "call": updated}


@sub_router.delete("/wake-up-calls/{call_id}")
async def delete_wake_up_call(
    call_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v101("frontdesk")),  # v101 DW
):
    """Delete a wake-up call."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    result = await db.wake_up_calls.delete_one({"id": call_id, "tenant_id": tid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Wake-up call bulunamadi")

    return {"success": True}


# ═══════════════════════════════════════════════════
# 3. LOST & FOUND MODULE
# ═══════════════════════════════════════════════════


@sub_router.get("/lost-found")
async def get_lost_found_items(
    status: str | None = None,
    category: str | None = None,
    search: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Get lost & found items."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    query = {"tenant_id": tid}
    if status:
        query["status"] = status
    if category:
        query["category"] = category

    items = []
    async for item in db.lost_found.find(query, {"_id": 0}).sort("created_at", -1):
        if search:
            search_lower = search.lower()
            if (
                search_lower not in (item.get("item_name", "").lower())
                and search_lower not in (item.get("description", "") or "").lower()
                and search_lower not in (item.get("guest_name", "") or "").lower()
            ):
                continue
        items.append(item)

    stats = {
        "total": len(items),
        "found": len([i for i in items if i.get("status") == "found"]),
        "claimed": len([i for i in items if i.get("status") == "claimed"]),
        "returned": len([i for i in items if i.get("status") == "returned"]),
        "stored": len([i for i in items if i.get("status") == "stored"]),
    }

    return {"items": items, "stats": stats}


@sub_router.post("/lost-found")
async def create_lost_found_item(
    data: LostFoundCreate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("housekeeping")),  # v99 DW
):
    """Register a new lost & found item."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    item = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "item_name": data.item_name,
        "description": data.description,
        "category": data.category,
        "found_location": data.found_location,
        "found_date": data.found_date,
        "found_by": data.found_by or current_user.name,
        "room_number": data.room_number,
        "guest_name": data.guest_name,
        "guest_contact": data.guest_contact,
        "booking_id": data.booking_id,
        "storage_location": data.storage_location,
        "photo_data": data.photo_data,
        "status": "found",
        "created_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.lost_found.insert_one(item)
    item.pop("_id", None)

    return {"success": True, "item": item}


@sub_router.put("/lost-found/{item_id}")
async def update_lost_found_item(
    item_id: str,
    data: LostFoundUpdate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("housekeeping")),  # v99 DW
):
    """Update a lost & found item."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    updates = {"updated_at": datetime.now(UTC).isoformat()}
    if data.status:
        updates["status"] = data.status
    if data.claimed_by:
        updates["claimed_by"] = data.claimed_by
    if data.claimed_date:
        updates["claimed_date"] = data.claimed_date
    if data.return_method:
        updates["return_method"] = data.return_method
    if data.tracking_number:
        updates["tracking_number"] = data.tracking_number
    if data.notes is not None:
        updates["notes"] = data.notes
    if data.guest_name:
        updates["guest_name"] = data.guest_name
    if data.guest_contact:
        updates["guest_contact"] = data.guest_contact

    result = await db.lost_found.update_one({"id": item_id, "tenant_id": tid}, {"$set": updates})

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Kayit bulunamadi")

    updated = await db.lost_found.find_one({"id": item_id}, {"_id": 0})
    return {"success": True, "item": updated}


@sub_router.delete("/lost-found/{item_id}")
async def delete_lost_found_item(
    item_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("housekeeping")),  # v99 DW
):
    """Delete a lost & found item."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    result = await db.lost_found.delete_one({"id": item_id, "tenant_id": tid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Kayit bulunamadi")

    return {"success": True}


@sub_router.post("/lost-found/{item_id}/match-guest")
async def match_guest_to_item(
    item_id: str,
    guest_name: str = "",
    guest_contact: str = "",
    booking_id: str = "",
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("housekeeping")),  # v99 DW
):
    """Match a guest to a lost & found item."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    updates = {"updated_at": datetime.now(UTC).isoformat()}
    if guest_name:
        updates["guest_name"] = guest_name
    if guest_contact:
        updates["guest_contact"] = guest_contact
    if booking_id:
        updates["booking_id"] = booking_id
        # Try to get guest info from booking
        booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
        if booking:
            updates["guest_name"] = booking.get("guest_name", guest_name)
            updates["room_number"] = booking.get("room_number")

    result = await db.lost_found.update_one({"id": item_id, "tenant_id": tid}, {"$set": updates})

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Kayit bulunamadi")

    updated = await db.lost_found.find_one({"id": item_id}, {"_id": 0})
    return {"success": True, "item": updated}


# ═══════════════════════════════════════════════════
# 4. HOTEL SETTINGS - Logo & Invoice Template
# ═══════════════════════════════════════════════════
