"""
PMS Domain — Housekeeping Repository
Data access layer for housekeeping tasks. No FastAPI dependencies.
"""

from datetime import UTC, datetime
from typing import Any

from core.tenant_db import LazyCollection


class HousekeepingRepository:
    """MongoDB operations for housekeeping tasks."""

    collection = LazyCollection("tasks")

    @classmethod
    async def find_by_tenant(
        cls,
        tenant_id: str,
        *,
        status: str | None = None,
        assigned_to: str | None = None,
        room_id: str | None = None,
        task_type: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if status:
            query["status"] = status
        if assigned_to:
            query["assigned_to"] = assigned_to
        if room_id:
            query["room_id"] = room_id
        if task_type:
            query["task_type"] = task_type

        cursor = cls.collection.find(query, {"_id": 0}).sort("created_at", -1).skip(offset).limit(limit)
        return await cursor.to_list(limit)

    @classmethod
    async def find_one(cls, tenant_id: str, task_id: str) -> dict[str, Any] | None:
        return await cls.collection.find_one({"tenant_id": tenant_id, "id": task_id}, {"_id": 0})

    @classmethod
    async def insert(cls, task_dict: dict[str, Any]) -> None:
        await cls.collection.insert_one(task_dict)

    @classmethod
    async def update(cls, tenant_id: str, task_id: str, update_data: dict[str, Any]) -> bool:
        result = await cls.collection.update_one(
            {"tenant_id": tenant_id, "id": task_id},
            {"$set": update_data},
        )
        return result.modified_count > 0

    @classmethod
    async def update_status(cls, tenant_id: str, task_id: str, new_status: str) -> bool:
        return await cls.update(
            tenant_id,
            task_id,
            {
                "status": new_status,
                "updated_at": datetime.now(UTC).isoformat(),
            },
        )

    @classmethod
    async def count_by_status(cls, tenant_id: str) -> dict[str, int]:
        pipeline = [
            {"$match": {"tenant_id": tenant_id}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        result = {}
        async for doc in cls.collection.aggregate(pipeline):
            result[doc["_id"]] = doc["count"]
        return result
