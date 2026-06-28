"""
Auto Housekeeping Task Assignment Service.
Automatic task creation after checkout, VIP/early check-in priority,
maintenance conflict check, floor attendant workload balancing,
room readiness ETA, task assignment suggestion engine, manual override.
"""

import uuid
from datetime import UTC, datetime, timedelta

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

    async def auto_assign_after_checkout(self, tenant_id: str, booking_id: str, user_id: str) -> dict:
        """Automatically create and assign housekeeping task after checkout."""
        booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
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
        now = datetime.now(UTC)

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
        await db.rooms.update_one({"id": room_id, "tenant_id": tenant_id}, {"$set": {"status": "dirty", "updated_at": now.isoformat()}})

        task.pop("_id", None)
        return {
            "success": True,
            "task": task,
            "assignee": assignee,
            "priority": priority,
            "eta_minutes": eta_minutes,
        }

    async def get_assignment_suggestions(self, tenant_id: str) -> dict:
        """Get task assignment suggestions for all dirty/pending rooms.

        Optimized: previous implementation was O(N_rooms * (M_staff + 3))
        sequential queries (~132s).  Now uses bulk fetches + in-memory
        priority/assignee computation.
        """
        # Get all dirty rooms
        dirty_rooms = await db.rooms.find({"tenant_id": tenant_id, "status": {"$in": ["dirty", "cleaning"]}, "$or": [{"is_active": True}, {"is_active": {"$exists": False}}]}, {"_id": 0}).to_list(500)

        # Get staff workload (uses its own bulk aggregation)
        staff_workload = await self._get_staff_workload(tenant_id)

        if not dirty_rooms:
            return {
                "total_suggestions": 0,
                "suggestions": [],
                "staff_workload": staff_workload,
            }

        room_ids = [r["id"] for r in dirty_rooms]

        # 1) Bulk: which rooms already have a pending/in_progress task?
        existing_room_ids: set[str] = set()
        async for t in db.housekeeping_tasks.find(
            {"room_id": {"$in": room_ids}, "tenant_id": tenant_id, "status": {"$in": ["pending", "in_progress"]}},
            {"_id": 0, "room_id": 1},
        ):
            existing_room_ids.add(t["room_id"])

        rooms_to_process = [r for r in dirty_rooms if r["id"] not in existing_room_ids]
        if not rooms_to_process:
            return {
                "total_suggestions": 0,
                "suggestions": [],
                "staff_workload": staff_workload,
            }

        # 2) Bulk: next confirmed booking per room (for priority)
        now = datetime.now(UTC)
        today = now.date().isoformat()
        tomorrow = (now.date() + timedelta(days=1)).isoformat()
        target_room_ids = [r["id"] for r in rooms_to_process]
        next_bookings: dict[str, dict] = {}
        async for b in db.bookings.find(
            {"tenant_id": tenant_id, "room_id": {"$in": target_room_ids}, "status": {"$in": ["confirmed", "guaranteed"]}, "check_in": {"$gte": today}},
            {"_id": 0, "room_id": 1, "check_in": 1, "guest_id": 1, "early_checkin": 1},
            sort=[("check_in", 1)],
        ):
            rid = b["room_id"]
            if rid not in next_bookings:
                next_bookings[rid] = b

        # 3) Bulk: VIP guest lookup
        guest_ids = [b["guest_id"] for b in next_bookings.values() if b.get("guest_id")]
        guest_map: dict[str, dict] = {}
        if guest_ids:
            async for g in db.guests.find(
                {"id": {"$in": guest_ids}, "tenant_id": tenant_id},
                {"_id": 0, "id": 1, "vip_status": 1, "tags": 1},
            ):
                guest_map[g["id"]] = g

        # 4) Bulk: housekeeping staff
        staff = await db.users.find(
            {"tenant_id": tenant_id, "role": {"$in": ["housekeeping", "staff"]}, "$or": [{"is_active": True}, {"is_active": {"$exists": False}}]},
            {"_id": 0, "id": 1, "name": 1},
        ).to_list(100)
        staff_ids = [s["id"] for s in staff]

        # 5) Bulk-aggregate workload + assigned floors per staff member
        staff_pending_count: dict[str, int] = {}
        staff_floors: dict[str, set[str]] = {}
        if staff_ids:
            count_pipeline = [
                {"$match": {"tenant_id": tenant_id, "assigned_to": {"$in": staff_ids}, "status": {"$in": ["pending", "in_progress"]}}},
                {"$group": {"_id": "$assigned_to", "count": {"$sum": 1}}},
            ]
            async for doc in db.housekeeping_tasks.aggregate(count_pipeline):
                staff_pending_count[doc["_id"]] = doc.get("count") or 0

            floor_pipeline = [
                {"$match": {"tenant_id": tenant_id, "assigned_to": {"$in": staff_ids}, "status": {"$in": ["pending", "in_progress"]}}},
                {"$group": {"_id": "$assigned_to", "floors": {"$addToSet": "$floor"}}},
            ]
            async for doc in db.housekeeping_tasks.aggregate(floor_pipeline):
                staff_floors[doc["_id"]] = {f for f in (doc.get("floors") or []) if f}

        suggestions = []
        for room in rooms_to_process:
            priority = self._priority_inline(
                room=room,
                next_booking=next_bookings.get(room["id"]),
                guest_map=guest_map,
                today=today,
                tomorrow=tomorrow,
            )
            assignee = self._assignee_inline(
                room=room,
                staff=staff,
                staff_pending_count=staff_pending_count,
                staff_floors=staff_floors,
            )

            room_type = room.get("room_type", "default")
            cleaning_time = self.CLEANING_TIMES.get(room_type, self.CLEANING_TIMES["default"])

            suggestions.append(
                {
                    "room_id": room["id"],
                    "room_number": room.get("room_number"),
                    "room_type": room_type,
                    "floor": room.get("floor", self._extract_floor(room.get("room_number", ""))),
                    "current_status": room["status"],
                    "priority": priority,
                    "suggested_assignee": assignee,
                    "estimated_minutes": cleaning_time,
                }
            )

        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        suggestions.sort(key=lambda s: priority_order.get(s["priority"]["level"], 99))

        return {
            "total_suggestions": len(suggestions),
            "suggestions": suggestions,
            "staff_workload": staff_workload,
        }

    def _priority_inline(self, room: dict, next_booking: dict | None, guest_map: dict, today: str, tomorrow: str) -> dict:
        """Pure-Python priority calc using pre-fetched next_booking + guest_map."""
        if not next_booking:
            return {"level": "medium", "reason": "Standard cleaning"}

        checkin_date = (next_booking.get("check_in") or "")[:10]
        guest = guest_map.get(next_booking.get("guest_id"))
        is_vip = False
        if guest:
            is_vip = bool(guest.get("vip_status")) or "vip" in (guest.get("tags") or [])

        base_priority = "medium"
        reason = "Future arrival"
        if checkin_date == today:
            base_priority = "critical" if is_vip else "high"
            reason = "VIP same-day arrival" if is_vip else "Same-day arrival"
        elif checkin_date == tomorrow:
            base_priority = "high" if is_vip else "medium"
            reason = "VIP tomorrow arrival" if is_vip else "Tomorrow arrival"
        elif is_vip:
            reason = "VIP future arrival"

        if next_booking.get("early_checkin"):
            if base_priority == "medium":
                base_priority = "high"
            elif base_priority == "high":
                base_priority = "critical"
            reason += " + Early check-in"

        return {"level": base_priority, "reason": reason}

    def _assignee_inline(self, room: dict, staff: list[dict], staff_pending_count: dict, staff_floors: dict) -> dict:
        """Pure-Python assignee selection using pre-fetched workload counts."""
        if not staff:
            return {"staff_id": None, "staff_name": "Unassigned", "current_tasks": 0, "reason": "No staff available"}

        floor = room.get("floor", self._extract_floor(room.get("room_number", "")))
        best = None
        best_score = float("inf")
        for s in staff:
            pending = staff_pending_count.get(s["id"], 0)
            score = pending * 10
            assigned_floors = staff_floors.get(s["id"], set())
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

    async def manual_override_assignment(self, tenant_id: str, task_id: str, new_assignee_id: str, reason: str, overridden_by: str) -> dict:
        """Manually override a task assignment."""
        task = await db.housekeeping_tasks.find_one({"id": task_id, "tenant_id": tenant_id}, {"_id": 0})
        if not task:
            return {"success": False, "error": "Task not found"}

        # Get assignee name
        staff = await db.users.find_one({"id": new_assignee_id}, {"_id": 0, "name": 1})
        staff_name = staff.get("name", "Unknown") if staff else "Unknown"

        now = datetime.now(UTC)
        old_assignee = task.get("assigned_to")

        await db.housekeeping_tasks.update_one(
            {"id": task_id, "tenant_id": tenant_id},
            {
                "$set": {
                    "assigned_to": new_assignee_id,
                    "assigned_to_name": staff_name,
                    "auto_assigned": False,
                    "override_reason": reason,
                    "overridden_by": overridden_by,
                    "overridden_at": now.isoformat(),
                }
            },
        )

        # Audit trail
        await db.pms_audit_trail.insert_one(
            {
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
            }
        )

        return {"success": True, "task_id": task_id, "new_assignee": staff_name}

    async def get_room_readiness_eta(self, tenant_id: str, room_id: str) -> dict:
        """Calculate estimated time until room is ready."""
        room = await db.rooms.find_one({"id": room_id, "tenant_id": tenant_id}, {"_id": 0})
        if not room:
            return {"ready": False, "eta_minutes": None, "reason": "Room not found"}

        if room["status"] in ["available", "inspected"]:
            return {"ready": True, "eta_minutes": 0, "reason": "Room is ready"}

        # Find active task
        task = await db.housekeeping_tasks.find_one(
            {
                "room_id": room_id,
                "tenant_id": tenant_id,
                "status": {"$in": ["pending", "in_progress"]},
                "task_type": "cleaning",
            },
            {"_id": 0},
        )

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
                elapsed = (datetime.now(UTC) - start_dt).total_seconds() / 60
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

    async def _calculate_priority(self, tenant_id: str, room_id: str, room: dict) -> dict:
        """Calculate cleaning priority based on next booking and VIP status."""
        now = datetime.now(UTC)
        today = now.date().isoformat()

        # Check next booking for this room
        next_booking = await db.bookings.find_one(
            {
                "tenant_id": tenant_id,
                "room_id": room_id,
                "status": {"$in": ["confirmed", "guaranteed"]},
                "check_in": {"$gte": today},
            },
            {"_id": 0, "check_in": 1, "guest_id": 1},
            sort=[("check_in", 1)],
        )

        base_priority = "medium"
        reason = "Standard cleaning"

        if next_booking:
            checkin_date = next_booking["check_in"][:10]

            # Check if VIP
            guest = await db.guests.find_one({"id": next_booking.get("guest_id"), "tenant_id": tenant_id}, {"_id": 0, "vip_status": 1, "tags": 1})
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

    async def _suggest_assignee(self, tenant_id: str, room: dict) -> dict:
        """Suggest best assignee based on workload and floor proximity."""
        floor = room.get("floor", self._extract_floor(room.get("room_number", "")))

        # Get housekeeping staff
        staff = await db.users.find(
            {"tenant_id": tenant_id, "role": {"$in": ["housekeeping", "staff"]}, "$or": [{"is_active": True}, {"is_active": {"$exists": False}}]}, {"_id": 0, "id": 1, "name": 1}
        ).to_list(100)

        if not staff:
            return {"staff_id": None, "staff_name": "Unassigned", "current_tasks": 0, "reason": "No staff available"}

        # Calculate workload for each staff
        best = None
        best_score = float("inf")

        for s in staff:
            pending = await db.housekeeping_tasks.count_documents(
                {
                    "tenant_id": tenant_id,
                    "assigned_to": s["id"],
                    "status": {"$in": ["pending", "in_progress"]},
                }
            )

            # Score: lower is better. Workload weight + floor mismatch penalty
            score = pending * 10
            # Floor proximity bonus (same floor = 0, different = 5)
            assigned_floors = await db.housekeeping_tasks.distinct(
                "floor",
                {
                    "tenant_id": tenant_id,
                    "assigned_to": s["id"],
                    "status": {"$in": ["pending", "in_progress"]},
                },
            )
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

    async def _get_staff_workload(self, tenant_id: str) -> list[dict]:
        """Get workload summary for all housekeeping staff.

        Optimized: replaces 3 sequential count_documents per staff member
        with a single grouped aggregate over all relevant tasks.
        """
        staff = await db.users.find(
            {"tenant_id": tenant_id, "role": {"$in": ["housekeeping", "staff"]}, "$or": [{"is_active": True}, {"is_active": {"$exists": False}}]}, {"_id": 0, "id": 1, "name": 1}
        ).to_list(100)

        if not staff:
            return []

        staff_ids = [s["id"] for s in staff]
        today_iso = datetime.now(UTC).date().isoformat()

        # Single aggregation: count by (assigned_to, bucketed status)
        pipeline = [
            {
                "$match": {
                    "tenant_id": tenant_id,
                    "assigned_to": {"$in": staff_ids},
                    "$or": [
                        {"status": {"$in": ["pending", "in_progress"]}},
                        {"status": "completed", "completed_at": {"$gte": today_iso}},
                    ],
                }
            },
            {
                "$project": {
                    "assigned_to": 1,
                    "bucket": {
                        "$switch": {
                            "branches": [
                                {"case": {"$eq": ["$status", "pending"]}, "then": "pending"},
                                {"case": {"$eq": ["$status", "in_progress"]}, "then": "in_progress"},
                                {"case": {"$eq": ["$status", "completed"]}, "then": "completed_today"},
                            ],
                            "default": "other",
                        }
                    },
                }
            },
            {
                "$group": {
                    "_id": {"staff": "$assigned_to", "bucket": "$bucket"},
                    "count": {"$sum": 1},
                }
            },
        ]

        counts: dict[str, dict[str, int]] = {sid: {"pending": 0, "in_progress": 0, "completed_today": 0} for sid in staff_ids}
        async for doc in db.housekeeping_tasks.aggregate(pipeline):
            sid = doc["_id"].get("staff")
            bucket = doc["_id"].get("bucket")
            if sid in counts and bucket in counts[sid]:
                counts[sid][bucket] = doc.get("count") or 0

        workload = []
        for s in staff:
            c = counts.get(s["id"], {"pending": 0, "in_progress": 0, "completed_today": 0})
            workload.append(
                {
                    "staff_id": s["id"],
                    "staff_name": s.get("name", "Unknown"),
                    "pending": c["pending"],
                    "in_progress": c["in_progress"],
                    "completed_today": c["completed_today"],
                    "total_active": c["pending"] + c["in_progress"],
                }
            )

        workload.sort(key=lambda w: w["total_active"])
        return workload

    async def _check_maintenance_conflict(self, tenant_id: str, room_id: str) -> dict:
        """Check if room has active maintenance blocking cleaning."""
        active_blocks = await db.room_blocks.find(
            {
                "room_id": room_id,
                "tenant_id": tenant_id,
                "status": "active",
            },
            {"_id": 0},
        ).to_list(10)

        maintenance = await db.housekeeping_tasks.find(
            {
                "room_id": room_id,
                "tenant_id": tenant_id,
                "task_type": "maintenance",
                "status": {"$in": ["pending", "in_progress"]},
            },
            {"_id": 0},
        ).to_list(10)

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
