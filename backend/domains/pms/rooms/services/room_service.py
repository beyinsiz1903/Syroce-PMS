"""
PMS Domain — Room Service
Business logic for room operations. No FastAPI dependencies.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from domains.pms.rooms.repositories.room_repository import RoomRepository


class RoomService:
    """Pure business logic for room management."""

    @staticmethod
    async def get_rooms(
        tenant_id: str,
        *,
        status: str | None = None,
        room_type: str | None = None,
        floor: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return await RoomRepository.find_by_tenant(
            tenant_id,
            status=status,
            room_type=room_type,
            floor=floor,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    async def get_room(tenant_id: str, room_id: str) -> dict[str, Any] | None:
        return await RoomRepository.find_one(tenant_id, room_id)

    @staticmethod
    async def create_room(tenant_id: str, room_data: dict[str, Any]) -> dict[str, Any]:
        existing = await RoomRepository.find_by_number(tenant_id, room_data.get("room_number", ""))
        if existing:
            raise ValueError(f"Room {room_data['room_number']} already exists")

        room = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            **room_data,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        await RoomRepository.insert(room)
        return room

    @staticmethod
    async def update_room(tenant_id: str, room_id: str, update_data: dict[str, Any]) -> bool:
        update_data["updated_at"] = datetime.now(UTC).isoformat()
        return await RoomRepository.update(tenant_id, room_id, update_data)

    @staticmethod
    async def change_room_status(tenant_id: str, room_id: str, new_status: str) -> bool:
        valid_statuses = {"available", "occupied", "dirty", "clean", "inspected", "maintenance", "out_of_order", "out_of_service"}
        if new_status not in valid_statuses:
            raise ValueError(f"Invalid status: {new_status}")
        return await RoomRepository.update_status(tenant_id, room_id, new_status)

    @staticmethod
    async def get_occupancy_stats(tenant_id: str) -> dict[str, Any]:
        return await RoomRepository.get_occupancy_stats(tenant_id)

    @staticmethod
    async def delete_room(tenant_id: str, room_id: str) -> bool:
        return await RoomRepository.delete(tenant_id, room_id)
