"""
Housekeeping State Service - Room status state machine, task lifecycle, readiness logic.
"""
from datetime import datetime, timezone
from typing import Dict, Tuple
import uuid

from core.database import db

# Room status state machine
# Transitions: {from_status: [allowed_to_statuses]}
ROOM_STATUS_TRANSITIONS = {
    "available": ["occupied", "dirty", "out_of_order", "out_of_service", "cleaning"],
    "occupied": ["dirty"],  # Only through checkout
    "dirty": ["cleaning", "out_of_order", "out_of_service"],
    "cleaning": ["inspected", "dirty"],  # dirty = failed / revert
    "inspected": ["available", "dirty", "out_of_order"],  # available = approved
    "out_of_order": ["dirty", "available"],
    "out_of_service": ["dirty", "available"],
    "maintenance": ["dirty", "available"],  # alias for out_of_service
}

# Statuses that make a room unavailable for booking
UNAVAILABLE_STATUSES = {"out_of_order", "out_of_service", "maintenance"}


class HousekeepingStateService:
    """Manages room status transitions and housekeeping task lifecycle."""

    def validate_room_transition(self, current: str, target: str) -> Tuple[bool, str]:
        """Validate if a room status transition is allowed."""
        if current == target:
            return True, "no_change"
        allowed = ROOM_STATUS_TRANSITIONS.get(current, [])
        if target not in allowed:
            return False, f"Cannot transition room from '{current}' to '{target}'. Allowed: {allowed}"
        return True, "ok"

    async def update_room_status(self, tenant_id: str, room_id: str, new_status: str, user_id: str, notes: str = None, force: bool = False) -> Dict:
        """Update room status with state machine validation."""
        room = await db.rooms.find_one({"id": room_id, "tenant_id": tenant_id}, {"_id": 0})
        if not room:
            return {"success": False, "error": "Room not found"}

        current_status = room.get("status", "available")

        if not force:
            valid, msg = self.validate_room_transition(current_status, new_status)
            if not valid:
                return {"success": False, "error": msg}

        now = datetime.now(timezone.utc)
        update_data = {"status": new_status, "updated_at": now.isoformat()}

        if new_status in UNAVAILABLE_STATUSES:
            update_data["ooo_since"] = now.isoformat()
            if notes:
                update_data["ooo_reason"] = notes

        if new_status == "available" and current_status in UNAVAILABLE_STATUSES:
            update_data["ooo_since"] = None
            update_data["ooo_reason"] = None

        if new_status == "inspected":
            update_data["last_inspected"] = now.isoformat()
            update_data["last_inspected_by"] = user_id

        await db.rooms.update_one({"id": room_id, "tenant_id": tenant_id}, {"$set": update_data})

        # Audit trail
        await db.pms_audit_trail.insert_one({
            "tenant_id": tenant_id,
            "entity_type": "room",
            "entity_id": room_id,
            "action": "room_status_change",
            "performed_by": user_id,
            "metadata": {
                "from": current_status,
                "to": new_status,
                "room_number": room.get("room_number"),
                "notes": notes,
                "forced": force,
            },
            "timestamp": now.isoformat(),
        })

        return {"success": True, "room_number": room["room_number"], "from": current_status, "to": new_status}

    async def create_housekeeping_task(self, tenant_id: str, room_id: str, task_type: str, assigned_to: str, priority: str, user_id: str, notes: str = None) -> Dict:
        """Create a housekeeping task with lifecycle tracking."""
        room = await db.rooms.find_one({"id": room_id, "tenant_id": tenant_id}, {"_id": 0})
        if not room:
            return {"success": False, "error": "Room not found"}

        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        task = {
            "id": task_id,
            "tenant_id": tenant_id,
            "room_id": room_id,
            "room_number": room["room_number"],
            "task_type": task_type,
            "assigned_to": assigned_to,
            "priority": priority,
            "status": "pending",
            "notes": notes,
            "created_by": user_id,
            "created_at": now.isoformat(),
        }

        await db.housekeeping_tasks.insert_one(task)

        # If task assigned, move room to cleaning
        if task_type == "cleaning" and room["status"] == "dirty":
            await self.update_room_status(tenant_id, room_id, "cleaning", user_id, force=True)

        task.pop("_id", None)
        return {"success": True, "task": task}

    async def complete_housekeeping_task(self, tenant_id: str, task_id: str, user_id: str) -> Dict:
        """Complete a housekeeping task and update room status."""
        task = await db.housekeeping_tasks.find_one({"id": task_id, "tenant_id": tenant_id}, {"_id": 0})
        if not task:
            return {"success": False, "error": "Task not found"}

        now = datetime.now(timezone.utc)
        await db.housekeeping_tasks.update_one(
            {"id": task_id, "tenant_id": tenant_id},
            {"$set": {"status": "completed", "completed_at": now.isoformat()}}
        )

        # If cleaning task, move room to inspected
        if task["task_type"] == "cleaning":
            room = await db.rooms.find_one({"id": task["room_id"], "tenant_id": tenant_id}, {"_id": 0})
            if room and room["status"] == "cleaning":
                await self.update_room_status(tenant_id, task["room_id"], "inspected", user_id, force=True)

        return {"success": True, "task_id": task_id}

    async def approve_room_inspection(self, tenant_id: str, room_id: str, user_id: str, approved: bool) -> Dict:
        """Approve or reject a room inspection. Approved -> available, Rejected -> dirty."""
        room = await db.rooms.find_one({"id": room_id, "tenant_id": tenant_id}, {"_id": 0})
        if not room:
            return {"success": False, "error": "Room not found"}

        if room["status"] != "inspected":
            return {"success": False, "error": f"Room must be in 'inspected' status, currently: {room['status']}"}

        new_status = "available" if approved else "dirty"
        result = await self.update_room_status(tenant_id, room_id, new_status, user_id, force=True)
        return {**result, "approved": approved}

    async def check_room_readiness(self, tenant_id: str, room_id: str) -> Dict:
        """Check if a room is ready for check-in."""
        room = await db.rooms.find_one({"id": room_id, "tenant_id": tenant_id}, {"_id": 0})
        if not room:
            return {"ready": False, "reason": "Room not found"}

        ready_statuses = {"available", "inspected"}
        is_ready = room["status"] in ready_statuses

        # Check for active OOO/OOS blocks
        active_blocks = await db.room_blocks.find({
            "room_id": room_id, "tenant_id": tenant_id, "status": "active"
        }, {"_id": 0}).to_list(10)

        ooo_blocked = any(not b.get("allow_sell", False) for b in active_blocks)

        # Check for pending maintenance
        pending_maintenance = await db.housekeeping_tasks.count_documents({
            "room_id": room_id, "tenant_id": tenant_id,
            "status": {"$in": ["pending", "in_progress"]},
            "task_type": {"$in": ["maintenance", "deep_clean"]},
        })

        reasons = []
        if not is_ready:
            reasons.append(f"Room status is '{room['status']}'")
        if ooo_blocked:
            reasons.append("Room has active OOO/OOS block")
        if pending_maintenance > 0:
            reasons.append(f"{pending_maintenance} pending maintenance task(s)")

        return {
            "room_id": room_id,
            "room_number": room.get("room_number"),
            "ready": is_ready and not ooo_blocked and pending_maintenance == 0,
            "room_status": room["status"],
            "ooo_blocked": ooo_blocked,
            "pending_maintenance": pending_maintenance,
            "reasons": reasons,
        }

    async def get_room_status_summary(self, tenant_id: str) -> Dict:
        """Get room status summary for dashboard."""
        pipeline = [
            {"$match": {"tenant_id": tenant_id, "$or": [{"is_active": True}, {"is_active": {"$exists": False}}]}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        results = await db.rooms.aggregate(pipeline).to_list(20)
        summary = {r["_id"]: r["count"] for r in results}
        total = sum(summary.values())

        return {
            "total_rooms": total,
            "available": summary.get("available", 0),
            "occupied": summary.get("occupied", 0),
            "dirty": summary.get("dirty", 0),
            "cleaning": summary.get("cleaning", 0),
            "inspected": summary.get("inspected", 0),
            "out_of_order": summary.get("out_of_order", 0),
            "out_of_service": summary.get("out_of_service", 0) + summary.get("maintenance", 0),
            "ready_rooms": summary.get("available", 0) + summary.get("inspected", 0),
            "dirty_rooms": summary.get("dirty", 0) + summary.get("cleaning", 0),
        }

    async def maintenance_impact_on_availability(self, tenant_id: str, room_id: str, start_date: str, end_date: str) -> Dict:
        """Check if putting a room in maintenance affects active bookings."""
        affected = await db.bookings.find({
            "tenant_id": tenant_id,
            "room_id": room_id,
            "status": {"$in": ["confirmed", "guaranteed"]},
            "check_in": {"$lt": end_date},
            "check_out": {"$gt": start_date},
        }, {"_id": 0, "id": 1, "check_in": 1, "check_out": 1, "guest_id": 1}).to_list(20)

        return {
            "room_id": room_id,
            "has_impact": len(affected) > 0,
            "affected_bookings": affected,
            "affected_count": len(affected),
        }
