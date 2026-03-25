"""
PMS / Mobile Ops — Service Layer
Orchestrates mobile check-in, quick tasks, no-show processing,
room changes, and active order management. No FastAPI dependencies.
"""
import logging
import uuid
from datetime import UTC, datetime

from common.audit_hook import SEVERITY_INFO, SEVERITY_WARNING, audited
from common.context import OperationContext
from common.result import ServiceResult

logger = logging.getLogger(__name__)


class MobileOpsService:
    """Business logic for mobile hotel operations."""

    def __init__(self):
        from core.database import db
        self._db = db

    @audited("mobile.process_no_show", "booking", severity=SEVERITY_WARNING, capture_before=True)
    async def process_no_show(self, ctx: OperationContext, booking_id: str) -> ServiceResult:
        booking = await self._db.bookings.find_one({"id": booking_id, "tenant_id": ctx.tenant_id})
        if not booking:
            return ServiceResult.fail("Booking not found", "NOT_FOUND")
        await self._db.bookings.update_one(
            {"id": booking_id},
            {"$set": {"status": "no_show", "no_show_at": datetime.now(UTC).isoformat()}},
        )
        if booking.get("room_id"):
            await self._db.rooms.update_one(
                {"id": booking["room_id"]},
                {"$set": {"status": "available", "current_booking_id": None}},
            )
        return ServiceResult.success({"message": "Booking marked as no-show", "booking_id": booking_id})

    @audited("mobile.change_room", "booking", severity=SEVERITY_WARNING, capture_before=True)
    async def change_room(self, ctx: OperationContext, booking_id: str, new_room_id: str, reason: str | None = None) -> ServiceResult:
        booking = await self._db.bookings.find_one({"id": booking_id, "tenant_id": ctx.tenant_id})
        if not booking:
            return ServiceResult.fail("Booking not found", "NOT_FOUND")
        new_room = await self._db.rooms.find_one({"id": new_room_id, "tenant_id": ctx.tenant_id})
        if not new_room:
            return ServiceResult.fail("New room not found", "NOT_FOUND")
        if new_room.get("status") not in ("available", "inspected"):
            return ServiceResult.fail("New room not available", "ROOM_NOT_AVAILABLE")

        old_room_id = booking.get("room_id")
        await self._db.bookings.update_one({"id": booking_id}, {"$set": {"room_id": new_room_id}})
        if old_room_id:
            await self._db.rooms.update_one({"id": old_room_id}, {"$set": {"status": "dirty", "current_booking_id": None}})
        await self._db.rooms.update_one({"id": new_room_id}, {"$set": {"status": "occupied", "current_booking_id": booking_id}})

        return ServiceResult.success({
            "message": "Room changed successfully",
            "old_room": old_room_id,
            "new_room": new_room_id,
            "new_room_number": new_room.get("room_number"),
            "reason": reason,
        })

    @audited("mobile.create_quick_task", "housekeeping_task", severity=SEVERITY_INFO)
    async def create_quick_task(self, ctx: OperationContext, data: dict) -> ServiceResult:
        task = {
            "id": str(uuid.uuid4()),
            "tenant_id": ctx.tenant_id,
            "room_id": data["room_id"],
            "task_type": data["task_type"],
            "priority": data.get("priority", "normal"),
            "assigned_to": data.get("assigned_to"),
            "notes": data.get("notes"),
            "status": "new",
            "created_by": ctx.actor_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await self._db.housekeeping_tasks.insert_one(task)
        return ServiceResult.success(task)

    @audited("mobile.create_quick_issue", "maintenance_task", severity=SEVERITY_INFO)
    async def create_quick_issue(self, ctx: OperationContext, data: dict) -> ServiceResult:
        issue = {
            "id": str(uuid.uuid4()),
            "tenant_id": ctx.tenant_id,
            "room_id": data["room_id"],
            "issue_type": data["issue_type"],
            "description": data["description"],
            "priority": data.get("priority", "normal"),
            "status": "open",
            "reported_by": ctx.actor_id,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await self._db.maintenance_issues.insert_one(issue)
        return ServiceResult.success(issue)

    async def get_mobile_dashboard(self, ctx: OperationContext) -> ServiceResult:
        today = datetime.now(UTC).date().isoformat()
        arrivals = await self._db.bookings.count_documents({"tenant_id": ctx.tenant_id, "check_in": today, "status": {"$in": ["confirmed", "guaranteed"]}})
        departures = await self._db.bookings.count_documents({"tenant_id": ctx.tenant_id, "check_out": today, "status": "checked_in"})
        in_house = await self._db.bookings.count_documents({"tenant_id": ctx.tenant_id, "status": "checked_in"})
        total_rooms = await self._db.rooms.count_documents({"tenant_id": ctx.tenant_id})
        occupied = await self._db.rooms.count_documents({"tenant_id": ctx.tenant_id, "status": "occupied"})
        available = await self._db.rooms.count_documents({"tenant_id": ctx.tenant_id, "status": "available"})
        dirty = await self._db.rooms.count_documents({"tenant_id": ctx.tenant_id, "status": "dirty"})
        pending_tasks = await self._db.housekeeping_tasks.count_documents({"tenant_id": ctx.tenant_id, "status": {"$in": ["new", "in_progress"]}})

        return ServiceResult.success({
            "arrivals_today": arrivals,
            "departures_today": departures,
            "in_house": in_house,
            "total_rooms": total_rooms,
            "occupied_rooms": occupied,
            "available_rooms": available,
            "dirty_rooms": dirty,
            "occupancy_rate": round(occupied / total_rooms * 100, 1) if total_rooms > 0 else 0,
            "pending_tasks": pending_tasks,
        })


mobile_ops_service = MobileOpsService()
