"""
Housekeeping Router - Room status, tasks, assignments, reports
Extracted from server.py for modularity.
"""

import logging

from modules.pms_core.role_permission_service import require_module as require_module_v99  # v99 DW

logger = logging.getLogger(__name__)
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer
from pydantic import BaseModel, Field

from core.database import db
from core.entitlements.enforcement import get_tenant_limit, require_feature
from core.entitlements.quota import QuotaExceededException, release_quota, reserve_quota
from core.security import get_current_user
from models.schemas import HousekeepingTask, User
from modules.inventory.services.create_room_block_service import CreateRoomBlockService
from modules.inventory.services.release_room_block_service import ReleaseRoomBlockService
from modules.pms_core.role_permission_service import require_op  # v77 Bug DM
from shared_kernel.idempotency import (
    begin_idempotency,
    claim_idempotency,
    complete_idempotency,
    get_idempotency_key,
    release_idempotency,
)

try:
    from domains.pms.room_block_models import BlockStatus, RoomBlock, RoomBlockCreate, RoomBlockUpdate
except ImportError:
    RoomBlock = RoomBlockCreate = RoomBlockUpdate = BlockStatus = None

try:
    from cache_manager import cache, cached
except ImportError:
    cache = None  # type: ignore

    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func

        return decorator


def _invalidate_hk_caches(tenant_id: str) -> None:
    """v95.2 — HK task değişikliklerinde aktif timer + performance cache temizle."""
    if not cache:
        return
    try:
        cache.invalidate_tenant_cache(tenant_id, "hk_active_timers")
        cache.invalidate_tenant_cache(tenant_id, "housekeeping_performance")
        cache.invalidate_tenant_cache(tenant_id, "housekeeping_room_status")
    except Exception:
        pass


router = APIRouter(prefix="/api", tags=["housekeeping"])
security = HTTPBearer()
create_room_block_service = CreateRoomBlockService()
release_room_block_service = ReleaseRoomBlockService()


# ============= HOUSEKEEPING =============


# rbac-allow: cache-rbac — operasyonel oda görevleri tüm rolelere açık (FO koordinasyon, sales availability)
@router.get("/housekeeping/tasks")
@cached(ttl=120, key_prefix="housekeeping_tasks")  # Cache for 2 minutes
async def get_housekeeping_tasks(status: str | None = None, current_user: User = Depends(get_current_user)):
    query = {"tenant_id": current_user.tenant_id}
    if status:
        query["status"] = status
    tasks = await db.housekeeping_tasks.find(query, {"_id": 0}).to_list(1000)
    room_ids = list({t["room_id"] for t in tasks if t.get("room_id")})
    rooms_by_id = {}
    if room_ids:
        rooms_cursor = db.rooms.find({"id": {"$in": room_ids}, "tenant_id": current_user.tenant_id}, {"_id": 0})
        async for r in rooms_cursor:
            rooms_by_id[r["id"]] = r
    return [{**task, "room": rooms_by_id.get(task.get("room_id"))} for task in tasks]


class HousekeepingTaskCreate(BaseModel):
    """Body schema for POST /housekeeping/tasks.

    Backwards-compatible: previous callers used query params. The new endpoint
    accepts a JSON body matching the same fields. Frontend should pass these
    as the request body, not querystring.
    """

    room_id: str = Field(..., min_length=1)
    task_type: str = Field(..., min_length=1)
    priority: str = "normal"
    notes: str | None = None


_HK_VALID_TASK_TYPES = {"cleaning", "inspection", "maintenance", "deep_cleaning", "turndown", "linen_change"}
_HK_VALID_PRIORITIES = {"low", "normal", "high", "urgent"}

ACTIVE_QUOTA_STATUSES = {"pending", "in_progress"}


@router.post("/housekeeping/tasks")
async def create_housekeeping_task(
    payload: HousekeepingTaskCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("housekeeping")),  # v99 DW
):
    if payload.task_type not in _HK_VALID_TASK_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Gecersiz task_type. Izinli={sorted(_HK_VALID_TASK_TYPES)}",
        )
    if payload.priority not in _HK_VALID_PRIORITIES:
        raise HTTPException(
            status_code=422,
            detail=f"Gecersiz priority. Izinli={sorted(_HK_VALID_PRIORITIES)}",
        )
    # Feature Guard
    if payload.task_type == "inspection":
        await require_feature("housekeeping", "quality_control")(request, current_user)

    # Optional Idempotency-Key replay protection
    idem_key = get_idempotency_key(request)
    lock_id = None
    if idem_key:
        claim = await claim_idempotency(
            db,
            tenant_id=current_user.tenant_id,
            scope="housekeeping_task_create",
            idempotency_key=idem_key,
        )
        if claim["status"] == "replay":
            return claim["response"]
        if claim["status"] == "in_flight":
            raise HTTPException(
                status_code=409,
                detail="Ayni Idempotency-Key ile baska bir istek isleniyor",
            )
        lock_id = claim["lock_id"]

    task = HousekeepingTask(
        tenant_id=current_user.tenant_id,
        room_id=payload.room_id,
        task_type=payload.task_type,
        priority=payload.priority,
        notes=payload.notes,
    )

    quota_reserved = False
    try:
        # Quota Reservation (After Idempotency)
        limit = await get_tenant_limit(current_user.tenant_id, "housekeeping", "active_tasks")
        try:
            await reserve_quota(current_user.tenant_id, "housekeeping", "active_tasks", task.id, limit)
            quota_reserved = True
        except QuotaExceededException as e:
            raise HTTPException(status_code=403, detail=str(e))

        # Verify room exists in this tenant — prevents cross-tenant id forging.
        room = await db.rooms.find_one({"id": payload.room_id, "tenant_id": current_user.tenant_id}, {"_id": 0, "id": 1})
        if not room:
            raise HTTPException(status_code=404, detail="Oda bulunamadi")

        task_dict = task.model_dump()
        task_dict["created_at"] = task_dict["created_at"].isoformat()

        await db.housekeeping_tasks.insert_one(task_dict.copy())
        task_dict.pop("_id", None)
        _invalidate_hk_caches(current_user.tenant_id)  # v95.2

        if lock_id:
            await complete_idempotency(db, lock_id=lock_id, response_body=task_dict)
        return task
    except Exception as exc:
        if quota_reserved:
            try:
                await release_quota(current_user.tenant_id, "housekeeping", "active_tasks", task.id)
            except Exception:
                pass
        if lock_id:
            await release_idempotency(db, lock_id=lock_id, error=str(exc))
        raise


@router.delete("/housekeeping/tasks/{task_id}")
async def delete_housekeeping_task(
    task_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("housekeeping")),
):
    """Hard-delete a housekeeping task scoped to the caller's tenant.

    In-progress tasks are protected: the status guard is applied inside the
    delete filter itself (atomic). Splitting find + delete would let a task
    that flips to in_progress between the two ops still be removed.
    """
    # Find before delete to know status
    task = await db.housekeeping_tasks.find_one({"id": task_id, "tenant_id": current_user.tenant_id})
    if not task:
        raise HTTPException(status_code=404, detail="Gorev bulunamadi")

    # Atomic guarded delete — status check is part of the WHERE clause.
    result = await db.housekeeping_tasks.delete_one(
        {
            "id": task_id,
            "tenant_id": current_user.tenant_id,
            "status": {"$ne": "in_progress"},
        }
    )
    if result.deleted_count == 1:
        if task.get("status", "pending") in ACTIVE_QUOTA_STATUSES:
            await release_quota(current_user.tenant_id, "housekeeping", "active_tasks", task_id)
        _invalidate_hk_caches(current_user.tenant_id)  # v95.2
        return {"success": True, "task_id": task_id, "deleted": 1}

    # Disambiguate 404 vs 409: re-read without the status filter to see why
    # the delete didn't match.
    existing = await db.housekeeping_tasks.find_one({"id": task_id, "tenant_id": current_user.tenant_id}, {"_id": 0, "status": 1})
    if not existing:
        raise HTTPException(status_code=404, detail="Gorev bulunamadi")
    raise HTTPException(status_code=409, detail="Devam eden gorev silinemez")


@router.put("/housekeeping/tasks/{task_id}")
async def update_housekeeping_task(
    task_id: str,
    status: str | None = None,
    assigned_to: str | None = None,
    assigned_to_user_id: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("housekeeping")),  # v99 DW
):
    task_before = await db.housekeeping_tasks.find_one({"id": task_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not task_before:
        raise HTTPException(status_code=404, detail="Görev bulunamadı")

    updates = {}
    if status:
        updates["status"] = status
        if status == "in_progress":
            updates["started_at"] = datetime.now(UTC).isoformat()
        elif status == "completed":
            updates["completed_at"] = datetime.now(UTC).isoformat()
            # v109 round-9 IDOR: scope find + chained room update by tenant.
            task = await db.housekeeping_tasks.find_one({"id": task_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
            if task and task.get("task_type") == "cleaning" and task.get("room_id"):
                await db.rooms.update_one(
                    {"id": task.get("room_id"), "tenant_id": current_user.tenant_id},
                    {"$set": {"status": "inspected", "last_cleaned": datetime.now(UTC).isoformat()}},
                )
    # Task #441: relational assignment — bind to an active user in the caller's
    # tenant (fail-closed). Free-text `assigned_to` is no longer accepted as a
    # mutation source; the display snapshot is derived from the validated user.
    if assigned_to_user_id:
        assignee = await db.users.find_one(
            {"id": assigned_to_user_id, "tenant_id": current_user.tenant_id, "is_active": True},
            {"_id": 0, "id": 1, "name": 1},
        )
        if not assignee:
            raise HTTPException(status_code=400, detail="Geçersiz veya pasif kullanıcı: atama reddedildi")
        updates["assigned_to_user_id"] = assignee["id"]
        updates["assigned_to"] = assignee.get("name") or "Personel"
    if not updates:
        raise HTTPException(status_code=400, detail="Güncellenecek alan yok")

    # Check quota status transition
    old_status = task_before.get("status", "pending")
    new_status = updates.get("status", old_status)

    was_counted = old_status in ACTIVE_QUOTA_STATUSES
    will_be_counted = new_status in ACTIVE_QUOTA_STATUSES

    reserved = False
    try:
        if not was_counted and will_be_counted:
            limit = await get_tenant_limit(current_user.tenant_id, "housekeeping", "active_tasks")
            try:
                await reserve_quota(current_user.tenant_id, "housekeeping", "active_tasks", task_id, limit)
                reserved = True
            except QuotaExceededException as e:
                raise HTTPException(status_code=403, detail=str(e))

        result = await db.housekeeping_tasks.update_one({"id": task_id, "tenant_id": current_user.tenant_id}, {"$set": updates})

        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Görev bulunamadı")

        if was_counted and not will_be_counted:
            await release_quota(current_user.tenant_id, "housekeeping", "active_tasks", task_id)

    except Exception:
        if reserved:
            await release_quota(current_user.tenant_id, "housekeeping", "active_tasks", task_id)
        raise

    task = await db.housekeeping_tasks.find_one({"id": task_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    _invalidate_hk_caches(current_user.tenant_id)  # v95.2
    return task


# rbac-allow: cache-rbac — oda durumu tablosu tüm rolelere açık (cross-departman koordinasyon)
@router.get("/housekeeping/room-status")
@cached(ttl=60, key_prefix="housekeeping_room_status")  # Cache for 1 minute (real-time data)
async def get_room_status_board(current_user: User = Depends(get_current_user)):
    """Get comprehensive room status board"""
    rooms = await db.rooms.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(1000)
    status_counts = dict.fromkeys(["available", "occupied", "dirty", "cleaning", "inspected", "maintenance", "out_of_order"], 0)
    for room in rooms:
        status_counts[room["status"]] += 1
    return {"rooms": rooms, "status_counts": status_counts, "total_rooms": len(rooms)}


# rbac-allow: cache-rbac — due-out listesi tüm rolelere açık (FO check-out koordinasyon)
@router.get("/housekeeping/due-out")
@cached(ttl=120, key_prefix="hk_due_out")  # Cache for 2 min
async def get_due_out_rooms(current_user: User = Depends(get_current_user)):
    """Get rooms with guests checking out today"""
    today = datetime.now(UTC).date()
    tomorrow = today + timedelta(days=1)

    # Find bookings checking out today
    bookings = await db.bookings.find({"tenant_id": current_user.tenant_id, "status": "checked_in"}).to_list(1000)

    # First pass: filter bookings by date in Python (date format mixed)
    matched = []
    for booking in bookings:
        try:
            checkout = booking.get("check_out")
            if isinstance(checkout, datetime):
                checkout_date = checkout.date()
            elif isinstance(checkout, str):
                checkout_date = datetime.fromisoformat(checkout.replace("Z", "+00:00")).date()
            else:
                continue
            if checkout_date == today or checkout_date == tomorrow:
                matched.append((booking, checkout, checkout_date))
        except Exception as e:
            logger.info(f"Error processing booking {booking.get('id')}: {e}")
            continue

    # Batch fetch rooms + guests for all matched bookings
    room_ids = list({b["room_id"] for b, _, _ in matched if b.get("room_id")})
    guest_ids = list({b["guest_id"] for b, _, _ in matched if b.get("guest_id")})
    rooms_by_id, guests_by_id = {}, {}
    if room_ids:
        async for r in db.rooms.find({"id": {"$in": room_ids}, "tenant_id": current_user.tenant_id}, {"_id": 0}):
            rooms_by_id[r["id"]] = r
    if guest_ids:
        async for g in db.guests.find({"id": {"$in": guest_ids}, "tenant_id": current_user.tenant_id}, {"_id": 0}):
            guests_by_id[g["id"]] = g

    from core.guest_name_utils import display_guest_name

    due_out_rooms = []
    for booking, checkout, checkout_date in matched:
        room = rooms_by_id.get(booking.get("room_id"))
        guest = guests_by_id.get(booking.get("guest_id"))
        # Guest doc yoksa bile bookings.guest_name'i veya guest_id fallback'ini kullan.
        raw_name = (guest.get("name") if guest else None) or booking.get("guest_name")
        due_out_rooms.append(
            {
                "room_number": room["room_number"] if room else "N/A",
                "room_type": room["room_type"] if room else "N/A",
                "guest_name": display_guest_name(raw_name, booking.get("guest_id")),
                "checkout_date": checkout.isoformat() if isinstance(checkout, datetime) else checkout,
                "booking_id": booking["id"],
                "is_today": checkout_date == today,
            }
        )

    return {"due_out_rooms": due_out_rooms, "count": len(due_out_rooms)}


# rbac-allow: cache-rbac — stayovers listesi tüm rolelere açık (operasyonel oda durumu)
@router.get("/housekeeping/stayovers")
@cached(ttl=120, key_prefix="hk_stayovers")  # Cache for 2 min
async def get_stayover_rooms(current_user: User = Depends(get_current_user)):
    """Get rooms with guests staying beyond today"""
    today = datetime.now(UTC).date()

    # Find checked-in bookings not checking out today
    bookings = await db.bookings.find({"tenant_id": current_user.tenant_id, "status": "checked_in"}).to_list(1000)

    matched = []
    for booking in bookings:
        try:
            checkout = booking.get("check_out")
            if isinstance(checkout, datetime):
                checkout_date = checkout.date()
            elif isinstance(checkout, str):
                checkout_date = datetime.fromisoformat(checkout.replace("Z", "+00:00")).date()
            else:
                continue
            if checkout_date > today:
                matched.append((booking, checkout, checkout_date))
        except Exception as e:
            logger.info(f"Error processing stayover booking {booking.get('id')}: {e}")
            continue

    room_ids = list({b["room_id"] for b, _, _ in matched if b.get("room_id")})
    guest_ids = list({b["guest_id"] for b, _, _ in matched if b.get("guest_id")})
    rooms_by_id, guests_by_id = {}, {}
    if room_ids:
        async for r in db.rooms.find({"id": {"$in": room_ids}, "tenant_id": current_user.tenant_id}, {"_id": 0}):
            rooms_by_id[r["id"]] = r
    if guest_ids:
        async for g in db.guests.find({"id": {"$in": guest_ids}, "tenant_id": current_user.tenant_id}, {"_id": 0}):
            guests_by_id[g["id"]] = g

    from core.guest_name_utils import display_guest_name

    stayover_rooms = []
    for booking, checkout, checkout_date in matched:
        room = rooms_by_id.get(booking.get("room_id"))
        guest = guests_by_id.get(booking.get("guest_id"))
        raw_name = (guest.get("name") if guest else None) or booking.get("guest_name")
        stayover_rooms.append(
            {
                "room_number": room["room_number"] if room else "N/A",
                "room_type": room["room_type"] if room else "N/A",
                "guest_name": display_guest_name(raw_name, booking.get("guest_id")),
                "checkout_date": checkout.isoformat() if isinstance(checkout, datetime) else checkout,
                "nights_remaining": (checkout_date - today).days,
                "booking_id": booking["id"],
            }
        )

    return {"stayover_rooms": stayover_rooms, "count": len(stayover_rooms)}


# rbac-allow: cache-rbac — oda durumu raporu tüm rolelere açık (operasyonel)
@router.get("/housekeeping/room-status-report")
@cached(ttl=120, key_prefix="hk_room_status_report")
async def get_room_status_report(current_user: User = Depends(get_current_user)):
    """Comprehensive room status report with DND, Sleep Out, OOO details"""

    # Get all rooms
    rooms = await db.rooms.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(1000)

    # Calculate summary
    summary = {
        "total_rooms": len(rooms),
        "occupied": sum(1 for r in rooms if r.get("status") == "occupied"),
        "vacant_clean": sum(1 for r in rooms if r.get("status") in ["available", "inspected"]),
        "vacant_dirty": sum(1 for r in rooms if r.get("status") == "dirty"),
        "out_of_order": sum(1 for r in rooms if r.get("status") == "out_of_order"),
        "out_of_service": sum(1 for r in rooms if r.get("status") == "maintenance"),
    }

    # Get DND (Do Not Disturb) rooms - occupied rooms with DND flag
    dnd_rooms = []
    sleep_out_rooms = []
    out_of_order_rooms = []

    # Get current bookings for occupied rooms
    bookings = await db.bookings.find({"tenant_id": current_user.tenant_id, "status": "checked_in"}, {"_id": 0}).to_list(1000)

    for booking in bookings:
        room = next((r for r in rooms if r.get("id") == booking.get("room_id")), None)
        if not room:
            continue

        guest = await db.guests.find_one({"id": booking.get("guest_id")}, {"_id": 0})
        from core.guest_name_utils import display_guest_name

        raw_name = (guest.get("name") if guest else None) or booking.get("guest_name")
        guest_name = display_guest_name(raw_name, booking.get("guest_id"))
        room_number = room.get("room_number")

        # Check for DND flag
        if booking.get("dnd_status") or room.get("dnd_status"):
            dnd_since = booking.get("dnd_since") or room.get("dnd_since", datetime.now(UTC).isoformat())
            try:
                dnd_time = datetime.fromisoformat(dnd_since.replace("Z", "+00:00"))
                duration_hours = int((datetime.now(UTC) - dnd_time).total_seconds() / 3600)
            except Exception:
                duration_hours = 0

            dnd_rooms.append({"room": room_number, "guest": guest_name, "dnd_since": dnd_since[:16] if isinstance(dnd_since, str) else dnd_since.strftime("%H:%M"), "duration_hours": duration_hours})

        # Check for Sleep Out (guest hasn't been in room for 24h+)
        last_activity = booking.get("last_room_activity")
        if last_activity:
            try:
                activity_time = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
                hours_since = (datetime.now(UTC) - activity_time).total_seconds() / 3600
                if hours_since > 24:
                    sleep_out_rooms.append(
                        {
                            "room": room_number,
                            "guest": guest_name,
                            "last_activity": last_activity[:16] if isinstance(last_activity, str) else last_activity.strftime("%Y-%m-%d %H:%M"),
                            "status": "suspected",
                        }
                    )
            except Exception:
                pass

    # Get Out of Order rooms
    for room in rooms:
        if room.get("status") == "out_of_order":
            out_of_order_rooms.append(
                {"room": room.get("room_number"), "reason": room.get("ooo_reason", "Maintenance required"), "since": room.get("ooo_since", "N/A"), "expected_fix": room.get("ooo_until", "TBD")}
            )

    return {"summary": summary, "dnd_rooms": dnd_rooms, "sleep_out": sleep_out_rooms, "out_of_order": out_of_order_rooms}


@router.get("/housekeeping/staff-performance-detailed")
@cached(ttl=300, key_prefix="hk_staff_perf_detailed")
async def get_staff_performance_detailed(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_executive_reports")),  # v77 Bug DM: HR/staff metrics
    _feat=Depends(require_feature("housekeeping", "advanced_reporting")),
):
    """Detailed staff performance metrics"""

    # Get completed tasks from last 30 days
    start_date = (datetime.now(UTC) - timedelta(days=30)).isoformat()

    tasks = await db.housekeeping_tasks.find({"tenant_id": current_user.tenant_id, "status": "completed", "completed_at": {"$gte": start_date}}, {"_id": 0}).to_list(5000)

    # Group by staff
    staff_stats = {}
    for task in tasks:
        staff = task.get("assigned_to", "Unassigned")
        if staff not in staff_stats:
            staff_stats[staff] = {"staff_name": staff, "tasks_completed": 0, "durations": [], "quality_scores": []}

        staff_stats[staff]["tasks_completed"] += 1

        # Calculate duration if available
        if task.get("started_at") and task.get("completed_at"):
            try:
                started = datetime.fromisoformat(task["started_at"].replace("Z", "+00:00"))
                completed = datetime.fromisoformat(task["completed_at"].replace("Z", "+00:00"))
                duration = (completed - started).total_seconds() / 60
                staff_stats[staff]["durations"].append(duration)
            except Exception:
                pass

        # Quality score (from inspections or ratings)
        if task.get("quality_score"):
            staff_stats[staff]["quality_scores"].append(task["quality_score"])

    # Calculate final metrics
    staff_performance = []
    for staff, data in staff_stats.items():
        avg_duration = sum(data["durations"]) / len(data["durations"]) if data["durations"] else 0
        avg_quality = sum(data["quality_scores"]) / len(data["quality_scores"]) if data["quality_scores"] else 95

        # Performance rating
        if avg_duration > 0:
            speed_rating = "Fast" if avg_duration < 20 else "Average" if avg_duration < 30 else "Slow"
        else:
            speed_rating = "N/A"

        staff_performance.append(
            {
                "staff_name": staff,
                "tasks_completed": data["tasks_completed"],
                "avg_duration_minutes": round(avg_duration, 1),
                "quality_score": round(avg_quality, 1),
                "speed_rating": speed_rating,
                "efficiency_rating": "⭐⭐⭐⭐⭐" if avg_quality >= 95 and avg_duration < 20 else "⭐⭐⭐⭐" if avg_quality >= 90 else "⭐⭐⭐",
            }
        )

    # Sort by tasks completed
    staff_performance.sort(key=lambda x: x["tasks_completed"], reverse=True)

    return {"staff_performance": staff_performance, "total_staff": len(staff_performance), "total_tasks": sum(s["tasks_completed"] for s in staff_performance)}


# rbac-allow: cache-rbac — arrival rooms listesi tüm rolelere açık (FO check-in koordinasyon)
@router.get("/housekeeping/arrivals")
@cached(ttl=120, key_prefix="hk_arrivals")  # Cache for 2 min
async def get_arrival_rooms(current_user: User = Depends(get_current_user)):
    """Get rooms with guests arriving today"""
    today = datetime.now(UTC).date()
    today_iso = today.isoformat()
    tomorrow_iso = (today + timedelta(days=1)).isoformat()
    today_dt = datetime.combine(today, datetime.min.time(), tzinfo=UTC)
    tomorrow_dt = today_dt + timedelta(days=1)

    # v95.2 — DB-side check_in date range. Karma tip (string ISO + datetime)
    # için $or; lex order ISO string'lerde tarih sırasını korur, böylece
    # check_in indeksi varsa range scan kullanılır.
    bookings = await db.bookings.find(
        {
            "tenant_id": current_user.tenant_id,
            "status": {"$in": ["confirmed", "guaranteed", "pending"]},
            "$or": [
                {"check_in": {"$gte": today_iso, "$lt": tomorrow_iso}},
                {"check_in": {"$gte": today_dt, "$lt": tomorrow_dt}},
            ],
        }
    ).to_list(1000)

    matched = []
    for booking in bookings:
        try:
            checkin = booking.get("check_in")
            if isinstance(checkin, datetime):
                checkin_date = checkin.date()
            elif isinstance(checkin, str):
                checkin_date = datetime.fromisoformat(checkin.replace("Z", "+00:00")).date()
            else:
                continue
            if checkin_date == today:
                matched.append((booking, checkin))
        except Exception as e:
            logger.info(f"Error processing arrival booking {booking.get('id')}: {e}")
            continue

    room_ids = list({b["room_id"] for b, _ in matched if b.get("room_id")})
    guest_ids = list({b["guest_id"] for b, _ in matched if b.get("guest_id")})
    rooms_by_id, guests_by_id = {}, {}
    if room_ids:
        async for r in db.rooms.find({"id": {"$in": room_ids}, "tenant_id": current_user.tenant_id}, {"_id": 0}):
            rooms_by_id[r["id"]] = r
    if guest_ids:
        async for g in db.guests.find({"id": {"$in": guest_ids}, "tenant_id": current_user.tenant_id}, {"_id": 0}):
            guests_by_id[g["id"]] = g

    from core.guest_name_utils import display_guest_name

    arrival_rooms = []
    for booking, checkin in matched:
        room = rooms_by_id.get(booking.get("room_id"))
        guest = guests_by_id.get(booking.get("guest_id"))
        raw_name = (guest.get("name") if guest else None) or booking.get("guest_name")
        arrival_rooms.append(
            {
                "room_number": room["room_number"] if room else "N/A",
                "room_type": room["room_type"] if room else "N/A",
                "room_status": room["status"] if room else "unknown",
                "guest_name": display_guest_name(raw_name, booking.get("guest_id")),
                "checkin_time": checkin.isoformat() if isinstance(checkin, datetime) else checkin,
                "booking_id": booking["id"],
                "booking_status": booking["status"],
                "ready": room["status"] in ["available", "inspected"] if room else False,
            }
        )

    return {"arrival_rooms": arrival_rooms, "count": len(arrival_rooms), "ready_count": sum(1 for r in arrival_rooms if r["ready"])}


@router.put("/housekeeping/room/{room_id}/status")
async def update_room_status_hk(
    room_id: str,
    new_status: str,
    notes: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("housekeeping")),  # v99 DW
):
    """Quick room status update from housekeeping"""
    valid_statuses = ["available", "occupied", "dirty", "cleaning", "inspected", "maintenance", "out_of_order"]

    if new_status not in valid_statuses:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of: {valid_statuses}")

    room = await db.rooms.find_one({"id": room_id, "tenant_id": current_user.tenant_id})

    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    update_data = {"status": new_status, "updated_at": datetime.now(UTC).isoformat()}

    if notes:
        update_data["hk_notes"] = notes

    await db.rooms.update_one(
        {"id": room_id, "tenant_id": current_user.tenant_id},  # v109 round-9 IDOR
        {"$set": update_data},
    )

    return {"message": f"Room {room['room_number']} status updated to {new_status}", "room_number": room["room_number"], "new_status": new_status}


@router.post("/housekeeping/assign")
async def assign_housekeeping_task(
    request: Request,
    room_id: str,
    assigned_to: str,
    task_type: str = "cleaning",
    priority: str = "normal",
    notes: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("housekeeping")),  # v99 DW
):
    """Assign housekeeping task to staff.

    Quota: /assign creates a new HousekeepingTask with status='pending'
    which is counted in ACTIVE_QUOTA_STATUSES — reserve_quota fires before
    insert so the ledger stays consistent. On insert failure the reservation
    is rolled back. HTTP Idempotency-Key is supported: a repeated request
    with the same key returns the cached response without re-reserving quota.
    """
    room = await db.rooms.find_one({"id": room_id, "tenant_id": current_user.tenant_id})
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")

    # Build the task object upfront so task.id is stable for idempotency + quota.
    task = HousekeepingTask(
        tenant_id=current_user.tenant_id,
        room_id=room_id,
        assigned_to=assigned_to,
        task_type=task_type,
        priority=priority,
        notes=notes or f"{task_type.title()} for Room {room['room_number']}",
    )

    # Idempotency: optional Idempotency-Key header prevents duplicate quota + insert.
    guard, replay = await begin_idempotency(
        db,
        request,
        tenant_id=current_user.tenant_id,
        scope="hk_assign",
        payload={"room_id": room_id, "assigned_to": assigned_to, "task_type": task_type},
    )
    if replay is not None:
        return replay

    # Reserve active-task quota BEFORE inserting.
    limit = await get_tenant_limit(current_user.tenant_id, "housekeeping", "active_tasks")
    if limit is not None:
        try:
            await reserve_quota(current_user.tenant_id, "housekeeping", "active_tasks", task.id, limit)
        except QuotaExceededException as e:
            await guard.release(error=str(e))
            raise HTTPException(status_code=403, detail=str(e))

    task_dict = task.model_dump()
    task_dict["created_at"] = task_dict["created_at"].isoformat()
    try:
        await db.housekeeping_tasks.insert_one(task_dict)
    except Exception as exc:
        # Insert failed — roll back quota reservation to keep ledger consistent.
        if limit is not None:
            await release_quota(current_user.tenant_id, "housekeeping", "active_tasks", task.id)
        await guard.release(error=str(exc))
        raise HTTPException(status_code=500, detail="Görev atanamadı") from exc

    _invalidate_hk_caches(current_user.tenant_id)  # v95.2
    result = {"message": f"Task assigned to {assigned_to}", "task": task.model_dump()}
    await guard.complete(result)
    return result


# ============= ROOM BLOCKS (OUT OF ORDER / OUT OF SERVICE) =============


# rbac-allow: cache-rbac — room blocks operasyonel listesi tüm rolelere açık (maintenance/group koordinasyon)
@router.get("/pms/room-blocks")
@cached(ttl=300, key_prefix="pms_room_blocks")  # Cache for 5 min
async def get_room_blocks(room_id: str | None = None, status: str | None = None, from_date: str | None = None, to_date: str | None = None, current_user: User = Depends(get_current_user)):
    """Get room blocks with optional filters"""
    query = {"tenant_id": current_user.tenant_id}

    if room_id:
        query["room_id"] = room_id

    if status:
        query["status"] = status

    # Date range filtering
    if from_date or to_date:
        date_query = {}
        if from_date:
            # Block overlaps if: block_start <= to_date AND (block_end >= from_date OR block_end is null)
            date_query["start_date"] = {"$lte": to_date if to_date else from_date}
        if to_date:
            # Also check end_date or open-ended blocks
            query["$or"] = [{"end_date": {"$gte": from_date if from_date else to_date}}, {"end_date": None}]

    blocks = await db.room_blocks.find(query, {"_id": 0}).to_list(1000)

    # Batch enrich with room information
    room_ids = list({b["room_id"] for b in blocks if b.get("room_id")})
    rooms_by_id = {}
    if room_ids:
        async for r in db.rooms.find({"id": {"$in": room_ids}, "tenant_id": current_user.tenant_id}, {"_id": 0, "id": 1, "room_number": 1, "room_type": 1}):
            rooms_by_id[r["id"]] = r

    for block in blocks:
        room = rooms_by_id.get(block.get("room_id"))
        if room:
            block["room_number"] = room.get("room_number")
            block["room_type"] = room.get("room_type")

    return {"blocks": blocks, "count": len(blocks)}


@router.post("/pms/room-blocks")
async def create_room_block(
    block_data: RoomBlockCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("housekeeping")),  # v99 DW
):
    return await create_room_block_service.create(block_data, current_user, request)


@router.patch("/pms/room-blocks/{block_id}")
async def update_room_block(
    block_id: str,
    block_data: RoomBlockUpdate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("housekeeping")),  # v99 DW
):
    """Update an existing room block"""
    block = await db.room_blocks.find_one({"id": block_id, "tenant_id": current_user.tenant_id}, {"_id": 0})

    if not block:
        raise HTTPException(status_code=404, detail="Room block not found")

    # Build update dict
    update_data = {}
    changes = {}

    if block_data.reason is not None:
        update_data["reason"] = block_data.reason
        changes["reason"] = {"old": block.get("reason"), "new": block_data.reason}

    if block_data.details is not None:
        update_data["details"] = block_data.details
        changes["details"] = {"old": block.get("details"), "new": block_data.details}

    if block_data.start_date is not None:
        update_data["start_date"] = block_data.start_date
        changes["start_date"] = {"old": block.get("start_date"), "new": block_data.start_date}

    if block_data.end_date is not None:
        update_data["end_date"] = block_data.end_date
        changes["end_date"] = {"old": block.get("end_date"), "new": block_data.end_date}

    if block_data.allow_sell is not None:
        update_data["allow_sell"] = block_data.allow_sell
        changes["allow_sell"] = {"old": block.get("allow_sell"), "new": block_data.allow_sell}

    if block_data.status is not None:
        update_data["status"] = block_data.status
        changes["status"] = {"old": block.get("status"), "new": block_data.status}

    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Update block
    await db.room_blocks.update_one({"id": block_id, "tenant_id": current_user.tenant_id}, {"$set": update_data})

    # Create audit log
    await db.audit_logs.insert_one(
        {
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "user_id": current_user.id,
            "user_name": current_user.name,
            "user_role": current_user.role,
            "action": "UPDATE_ROOM_BLOCK",
            "entity_type": "room_block",
            "entity_id": block_id,
            "changes": changes,
            "timestamp": datetime.now(UTC).isoformat(),
        }
    )

    # Get updated block
    updated_block = await db.room_blocks.find_one({"id": block_id, "tenant_id": current_user.tenant_id}, {"_id": 0})

    return {"message": "Room block updated successfully", "block": updated_block}


@router.post("/pms/room-blocks/{block_id}/cancel")
async def cancel_room_block(
    block_id: str,
    request: Request,
    reason: str | None = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("housekeeping")),  # v99 DW
):
    """Release a room block through the semantic inventory service."""
    return await release_room_block_service.release(block_id, current_user, request, reason=reason)


# ============= LOYALTY PROGRAM =============
