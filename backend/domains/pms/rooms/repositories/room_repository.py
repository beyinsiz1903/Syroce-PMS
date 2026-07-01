"""
PMS Domain — Room Repository
Data access layer for room operations. No FastAPI dependencies.
"""

from datetime import UTC, datetime
from typing import Any

from core.tenant_db import LazyCollection


class RoomRepository:
    """MongoDB operations for rooms."""

    collection = LazyCollection("rooms")

    @classmethod
    async def find_by_tenant(
        cls,
        tenant_id: str,
        *,
        status: str | None = None,
        room_type: str | None = None,
        floor: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if status:
            query["status"] = status
        if room_type:
            query["room_type"] = room_type
        if floor:
            query["floor"] = floor

        cursor = cls.collection.find(query, {"_id": 0}).skip(offset).limit(limit)
        return await cursor.to_list(limit)

    @classmethod
    async def find_one(cls, tenant_id: str, room_id: str) -> dict[str, Any] | None:
        return await cls.collection.find_one({"tenant_id": tenant_id, "id": room_id}, {"_id": 0})

    @classmethod
    async def find_by_number(cls, tenant_id: str, room_number: str) -> dict[str, Any] | None:
        return await cls.collection.find_one({"tenant_id": tenant_id, "room_number": room_number}, {"_id": 0})

    @classmethod
    async def count(cls, tenant_id: str, query_filter: dict | None = None) -> int:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if query_filter:
            query.update(query_filter)
        return await cls.collection.count_documents(query)

    @classmethod
    async def insert(cls, room_dict: dict[str, Any]) -> None:
        await cls.collection.insert_one(room_dict)

    @classmethod
    async def update(cls, tenant_id: str, room_id: str, update_data: dict[str, Any]) -> bool:
        result = await cls.collection.update_one(
            {"tenant_id": tenant_id, "id": room_id},
            {"$set": update_data},
        )
        return result.modified_count > 0

    @classmethod
    async def update_status(cls, tenant_id: str, room_id: str, new_status: str) -> bool:
        return await cls.update(
            tenant_id,
            room_id,
            {
                "status": new_status,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )

    @classmethod
    async def delete(cls, tenant_id: str, room_id: str) -> bool:
        result = await cls.collection.delete_one({"tenant_id": tenant_id, "id": room_id})
        return result.deleted_count > 0

    @classmethod
    async def get_occupancy_stats(cls, tenant_id: str) -> dict[str, int]:
        total = await cls.count(tenant_id)
        occupied = await cls.count(tenant_id, {"status": "occupied"})
        available = await cls.count(tenant_id, {"status": "available"})
        maintenance = await cls.count(tenant_id, {"status": {"$in": ["maintenance", "out_of_order"]}})
        return {
            "total": total,
            "occupied": occupied,
            "available": available,
            "maintenance": maintenance,
            "occupancy_rate": round((occupied / total * 100) if total > 0 else 0, 1),
        }
