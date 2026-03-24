"""
PMS Domain — Housekeeping Service
Business logic for housekeeping task operations. No FastAPI dependencies.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from domains.pms.housekeeping.repositories.housekeeping_repository import HousekeepingRepository
from domains.pms.rooms.repositories.room_repository import RoomRepository


class HousekeepingService:
    """Pure business logic for housekeeping management."""

    @staticmethod
    async def get_tasks(
        tenant_id: str, *, status: Optional[str] = None,
        assigned_to: Optional[str] = None, room_id: Optional[str] = None,
        task_type: Optional[str] = None, limit: int = 100, offset: int = 0,
    ) -> List[Dict[str, Any]]:
        return await HousekeepingRepository.find_by_tenant(
            tenant_id, status=status, assigned_to=assigned_to,
            room_id=room_id, task_type=task_type,
            limit=limit, offset=offset,
        )

    @staticmethod
    async def create_task(tenant_id: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        task = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            **task_data,
            "status": task_data.get("status", "pending"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await HousekeepingRepository.insert(task)
        return task

    @staticmethod
    async def start_task(tenant_id: str, task_id: str) -> bool:
        task = await HousekeepingRepository.find_one(tenant_id, task_id)
        if not task:
            raise ValueError("Task not found")
        if task.get("status") != "pending":
            raise ValueError(f"Cannot start task with status: {task.get('status')}")

        return await HousekeepingRepository.update(tenant_id, task_id, {
            "status": "in_progress",
            "started_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    @staticmethod
    async def complete_task(tenant_id: str, task_id: str) -> bool:
        task = await HousekeepingRepository.find_one(tenant_id, task_id)
        if not task:
            raise ValueError("Task not found")

        await HousekeepingRepository.update(tenant_id, task_id, {
            "status": "completed",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

        # Update room status to clean
        room_id = task.get("room_id")
        if room_id:
            await RoomRepository.update_status(tenant_id, room_id, "clean")

        return True

    @staticmethod
    async def get_stats(tenant_id: str) -> Dict[str, Any]:
        return await HousekeepingRepository.count_by_status(tenant_id)

    @staticmethod
    async def assign_task(tenant_id: str, task_id: str, staff_id: str) -> bool:
        return await HousekeepingRepository.update(tenant_id, task_id, {
            "assigned_to": staff_id,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })
