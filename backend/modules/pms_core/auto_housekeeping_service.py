"""
Auto Housekeeping Task Assignment Service.
Automatic task creation after checkout, VIP/early check-in priority,
maintenance conflict check, floor attendant workload balancing,
room readiness ETA, task assignment suggestion engine, manual override.
"""
from datetime import datetime, timezone, timedelta
from typing import Dict, List
import uuid

from core.database import db


class AutoHousekeepingService:
    """Intelligent housekeeping task assignment and workload management."""

    # Average cleaning times in minutes
    CLEANING_TIMES = {
        "Standard": 30,
        "Deluxe": 40,
        "Suite": 55,
        "Presidential": 75,
        "default": 35,
    }

    VIP_PRIORITY_BOOST = 2  # priority levels to boost for VIP
    EARLY_CHECKIN_PRIORITY_BOOST = 1

    async def auto_assign_after_checkout(self, tenant_id: str, booking_id: str, user_id: str) -> Dict:
        """Automatically create and assign housekeeping task after checkout."""
        booking = await db.bookings.find_one(
            {"id": booking_id, "tenant_id": tenant_id}, {"_id": 0}
        )
        if not booking:
            return {"success": False, "error": "Booking not found"}

        room_id = booking.get("room_id")
        room = await db.rooms.find_one({"id": room_id, "tenant_id": tenant_id}, {"_id": 0})
        if not room:
            return {"success": False, "error": "Room not found"}

        # Check for maintenance conflicts
        conflict = await self._check_maintenance_conflict(tenant_id, room_id)
        if conflict["has_conflict"]:
            return {
                "success": False,
                "error": "Maintenance conflict",
                "conflict": conflict,
            }

        # Determine priority based on next booking
        priority = await self._calculate_priority(tenant_id, room_id, room)

        # Find best assignee using workload balancing
        assignee = await self._suggest_assignee(tenant_id, room)

        # Calculate ETA
        room_type = room.get("room_type", "default")
        cleaning_time = self.CLEANING_TIMES.get(room_type, self.CLEANING_TIMES["default"])
        eta_minutes = cleaning_time
        if assignee.get("current_tasks", 0) > 0:
            eta_minutes += assignee["current_tasks"] * 15  # Queue delay estimate

        # Create the task
        task_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)

        task = {
            "id": task_id,
            "tenant_id": tenant_id,
            "room_id": room_id,
            "room_number": room.get("room_number"),
            "floor": room.get("floor", self._extract_floor(room.get("room_number", ""))),
            "room_type": room_type,
            "task_type": "cleaning",
            "priority": priority["level"],
            "priority_reason": priority["reason"],
            "assigned_to": assignee.get("staff_id"),
            "assigned_to_name": assignee.get("staff_name"),
            "status": "pending",
            "booking_id": booking_id,
            "estimated_minutes": cleaning_time,
            "eta_ready": (now + timedelta(minutes=eta_minutes)).isoformat(),
            "auto_assigned": True,
            "created_by": "system",
            "created_at": now.isoformat(),
        }

        await db.housekeeping_tasks.insert_one(task)

        # Update room status to dirty
        await db.rooms.update_one(
            {"id": room_id, "tenant_id": tenant_id},
            {"$set": {"status": "dirty", "updated_at": now.isoformat()}}
        )

        task.pop("_id", None)
        return {
            "success": True,
            "task": task,
            "assignee": assignee,
            "priority": priority,
            "eta_minutes": eta_minutes,
        }

    async def get_assignment_suggestions(self, tenant_id: str) -> Dict:
        """Get task assignment suggestions for all dirty/pending rooms."""
        # Get all dirty rooms
        dirty_rooms = await db.rooms.find(
            {"tenant_id": tenant_id, "status": {"$in": ["dirty", "cleaning"]},
             "$or": [{"is_active": True}, {"is_active": {"$exists": False}}]},
            {"_id": 0}
        ).to_list(500)

        # Get all available staff
        staff_workload = await self._get_staff_workload(tenant_id)

        suggestions = []
        for room in dirty_rooms:
            # Check if already has pending task
            existing = await db.housekeeping_tasks.find_one({
                "room_id": room["id"], "tenant_id": tenant_id,
                "status": {"$in": ["pending", "in_progress"]},
            })
            if existing:
                continue

            priority = await self._calculate_priority(tenant_id, room["id"], room)
            assignee = await self._suggest_assignee(tenant_id, room)

            room_type = room.get("room_type", "default")
            cleaning_time = self.CLEANING_TIMES.get(room_type, self.CLEANING_TIMES["default"])

            suggestions.append({
                "room_id": room["id"],
                "room_number": room.get("room_number"),
                "room_type": room_type,
                "floor": room.get("floor", self._extract_floor(room.get("room_number", ""))),
                "current_status": room["status"],
                "priority": priority,
                "suggested_assignee": assignee,
                "estimated_minutes": cleaning_time,
            })

        # Sort by priority (higher number = higher priority)
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        suggestions.sort(key=lambda s: priority_order.get(s["priority"]["level"], 99))

        return {
            "total_suggestions": len(suggestions),
            "suggestions": suggestions,
            "staff_workload": staff_workload,
        }

    async def manual_override_assignment(self, tenant_id: str, task_id: str, new_assignee_id: str, reason: str, overridden_by: str) -> Dict:
        """Manually override a task assignment."""
        task = await db.housekeeping_tasks.find_one(
            {"id": task_id, "tenant_id": tenant_id}, {"_id": 0}
        )
        if not task:
            return {"success": False, "error": "Task not found"}

        # Get assignee name
        staff = await db.users.find_one({"id": new_assignee_id}, {"_id": 0, "name": 1})
        staff_name = staff.get("name", "Unknown") if staff else "Unknown"

        now = datetime.now(timezone.utc)
        old_assignee = task.get("assigned_to")

        await db.housekeeping_tasks.update_one(
            {"id": task_id, "tenant_id": tenant_id},
            {"$set": {
                "assigned_to": new_assignee_id,
                "assigned_to_name": staff_name,
                "auto_assigned": False,
                "override_reason": reason,
                "overridden_by": overridden_by,
                "overridden_at": now.isoformat(),
            }}
        )

        # Audit trail
        await db.pms_audit_trail.insert_one({
            "tenant_id": tenant_id,
            "entity_type": "housekeeping_task",
            "entity_id": task_id,
            "action": "task_override",
            "performed_by": overridden_by,
            "metadata": {
                "old_assignee": old_assignee,
                "new_assignee": new_assignee_id,
                "reason": reason,
            },
            "timestamp": now.isoformat(),
        })

        return {"success": True, "task_id": task_id, "new_assignee": staff_name}

    async def get_room_readiness_eta(self, tenant_id: str, room_id: str) -> Dict:
        """Calculate estimated time until room is ready."""
        room = await db.rooms.find_one({"id": room_id, "tenant_id": tenant_id}, {"_id": 0})
        if not room:
            return {"ready": False, "eta_minutes": None, "reason": "Room not found"}

        if room["status"] in ["available", "inspected"]:
            return {"ready": True, "eta_minutes": 0, "reason": "Room is ready"}

        # Find active task
        task = await db.housekeeping_tasks.find_one({
            "room_id": room_id, "tenant_id": tenant_id,
            "status": {"$in": ["pending", "in_progress"]},
            "task_type": "cleaning",
        }, {"_id": 0})

        if not task:
            room_type = room.get("room_type", "default")
            base_time = self.CLEANING_TIMES.get(room_type, self.CLEANING_TIMES["default"])
            return {
                "ready": False,
                "eta_minutes": base_time + 15,  # +15 for assignment delay
                "reason": "No cleaning task assigned yet",
                "room_status": room["status"],
            }

        # Calculate remaining time
        if task["status"] == "in_progress":
            started = task.get("started_at")
            if started:
                start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                elapsed = (datetime.now(timezone.utc) - start_dt).total_seconds() / 60
                estimated = task.get("estimated_minutes", 35)
                remaining = max(estimated - elapsed, 5)
                remaining += 10  # inspection buffer
            else:
                remaining = task.get("estimated_minutes", 35) + 10
        else:
            # Pending - full estimate + queue time
            remaining = task.get("estimated_minutes", 35) + 20

        return {
            "ready": False,
            "eta_minutes": round(remaining),
            "reason": f"Task {task['status']}: ~{round(remaining)} min remaining",
            "room_status": room["status"],
            "task_status": task["status"],
            "assigned_to": task.get("assigned_to_name"),
        }

    async def _calculate_priority(self, tenant_id: str, room_id: str, room: Dict) -> Dict:
        """Calculate cleaning priority based on next booking and VIP status."""
        now = datetime.now(timezone.utc)
        today = now.date().isoformat()

        # Check next booking for this room
        next_booking = await db.bookings.find_one({
            "tenant_id": tenant_id,
            "room_id": room_id,
            "status": {"$in": ["confirmed", "guaranteed"]},
            "check_in": {"$gte": today},
        }, {"_id": 0, "check_in": 1, "guest_id": 1}, sort=[("check_in", 1)])

        base_priority = "medium"
        reason = "Standard cleaning"

        if next_booking:
            checkin_date = next_booking["check_in"][:10]

            # Check if VIP
            guest = await db.guests.find_one(
                {"id": next_booking.get("guest_id"), "tenant_id": tenant_id},
                {"_id": 0, "vip_status": 1, "tags": 1}
            )
            is_vip = False
            if guest:
                is_vip = guest.get("vip_status") or "vip" in (guest.get("tags") or [])

            if checkin_date == today:
                base_priority = "high"
                reason = "Same-day arrival"
                if is_vip:
                    base_priority = "critical"
                    reason = "VIP same-day arrival"
            elif checkin_date == (now.date() + timedelta(days=1)).isoformat():
                base_priority = "medium"
                reason = "Tomorrow arrival"
                if is_vip:
                    base_priority = "high"
                    reason = "VIP tomorrow arrival"
            else:
                if is_vip:
                    base_priority = "medium"
                    reason = "VIP future arrival"

            # Check early check-in request
            if next_booking.get("early_checkin"):
                if base_priority == "medium":
                    base_priority = "high"
                elif base_priority == "high":
                    base_priority = "critical"
                reason += " + Early check-in"

        return {"level": base_priority, "reason": reason}

    async def _suggest_assignee(self, tenant_id: str, room: Dict) -> Dict:
        """Suggest best assignee based on workload and floor proximity."""
        floor = room.get("floor", self._extract_floor(room.get("room_number", "")))

        # Get housekeeping staff
        staff = await db.users.find(
            {"tenant_id": tenant_id, "role": {"$in": ["housekeeping", "staff"]},
             "$or": [{"is_active": True}, {"is_active": {"$exists": False}}]},
            {"_id": 0, "id": 1, "name": 1}
        ).to_list(100)

        if not staff:
            return {"staff_id": None, "staff_name": "Unassigned", "current_tasks": 0, "reason": "No staff available"}

        # Calculate workload for each staff
        best = None
        best_score = float("inf")

        for s in staff:
            pending = await db.housekeeping_tasks.count_documents({
                "tenant_id": tenant_id,
                "assigned_to": s["id"],
                "status": {"$in": ["pending", "in_progress"]},
            })

            # Score: lower is better. Workload weight + floor mismatch penalty
            score = pending * 10
            # Floor proximity bonus (same floor = 0, different = 5)
            assigned_floors = await db.housekeeping_tasks.distinct("floor", {
                "tenant_id": tenant_id,
                "assigned_to": s["id"],
                "status": {"$in": ["pending", "in_progress"]},
            })
            if floor and assigned_floors and floor not in assigned_floors:
                score += 5

            if score < best_score:
                best_score = score
                best = {
                    "staff_id": s["id"],
                    "staff_name": s.get("name", "Unknown"),
                    "current_tasks": pending,
                    "score": score,
                    "reason": f"Lowest workload ({pending} tasks)",
                }

        return best or {"staff_id": None, "staff_name": "Unassigned", "current_tasks": 0, "reason": "No staff available"}

    async def _get_staff_workload(self, tenant_id: str) -> List[Dict]:
        """Get workload summary for all housekeeping staff."""
        staff = await db.users.find(
            {"tenant_id": tenant_id, "role": {"$in": ["housekeeping", "staff"]},
             "$or": [{"is_active": True}, {"is_active": {"$exists": False}}]},
            {"_id": 0, "id": 1, "name": 1}
        ).to_list(100)

        workload = []
        for s in staff:
            pending = await db.housekeeping_tasks.count_documents({
                "tenant_id": tenant_id, "assigned_to": s["id"],
                "status": "pending",
            })
            in_progress = await db.housekeeping_tasks.count_documents({
                "tenant_id": tenant_id, "assigned_to": s["id"],
                "status": "in_progress",
            })
            completed_today = await db.housekeeping_tasks.count_documents({
                "tenant_id": tenant_id, "assigned_to": s["id"],
                "status": "completed",
                "completed_at": {"$gte": datetime.now(timezone.utc).date().isoformat()},
            })

            workload.append({
                "staff_id": s["id"],
                "staff_name": s.get("name", "Unknown"),
                "pending": pending,
                "in_progress": in_progress,
                "completed_today": completed_today,
                "total_active": pending + in_progress,
            })

        workload.sort(key=lambda w: w["total_active"])
        return workload

    async def _check_maintenance_conflict(self, tenant_id: str, room_id: str) -> Dict:
        """Check if room has active maintenance blocking cleaning."""
        active_blocks = await db.room_blocks.find({
            "room_id": room_id, "tenant_id": tenant_id, "status": "active",
        }, {"_id": 0}).to_list(10)

        maintenance = await db.housekeeping_tasks.find({
            "room_id": room_id, "tenant_id": tenant_id,
            "task_type": "maintenance",
            "status": {"$in": ["pending", "in_progress"]},
        }, {"_id": 0}).to_list(10)

        has_conflict = len(active_blocks) > 0 or len(maintenance) > 0
        return {
            "has_conflict": has_conflict,
            "active_blocks": len(active_blocks),
            "active_maintenance": len(maintenance),
            "details": active_blocks[:3] + maintenance[:3],
        }

    def _extract_floor(self, room_number: str) -> str:
        """Extract floor from room number (e.g., '301' -> '3')."""
        if not room_number:
            return "0"
        digits = "".join(c for c in str(room_number) if c.isdigit())
        if len(digits) >= 3:
            return digits[0]
        elif len(digits) == 2:
            return digits[0]
        return "0"
