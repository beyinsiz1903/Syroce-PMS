"""
PMS Domain — Housekeeping Repository
Data access layer for housekeeping tasks. No FastAPI dependencies.
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from core.database import db


class HousekeepingRepository:
    """MongoDB operations for housekeeping tasks."""

    collection = db.tasks

    @classmethod
    async def find_by_tenant(
        cls, tenant_id: str, *, status: Optional[str] = None,
        assigned_to: Optional[str] = None, room_id: Optional[str] = None,
        task_type: Optional[str] = None,
        limit: int = 100, offset: int = 0,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {"tenant_id": tenant_id}
        if status:
            query["status"] = status
        if assigned_to:
            query["assigned_to"] = assigned_to
        if room_id:
            query["room_id"] = room_id
        if task_type:
            query["task_type"] = task_type

        cursor = (
            cls.collection.find(query, {"_id": 0})
            .sort("created_at", -1)
            .skip(offset)
            .limit(limit)
        )
        return await cursor.to_list(limit)

    @classmethod
    async def find_one(cls, tenant_id: str, task_id: str) -> Optional[Dict[str, Any]]:
        return await cls.collection.find_one(
            {"tenant_id": tenant_id, "id": task_id}, {"_id": 0}
        )

    @classmethod
    async def insert(cls, task_dict: Dict[str, Any]) -> None:
        await cls.collection.insert_one(task_dict)

    @classmethod
    async def update(cls, tenant_id: str, task_id: str, update_data: Dict[str, Any]) -> bool:
        result = await cls.collection.update_one(
            {"tenant_id": tenant_id, "id": task_id},
            {"$set": update_data},
        )
        return result.modified_count > 0

    @classmethod
    async def update_status(cls, tenant_id: str, task_id: str, new_status: str) -> bool:
        return await cls.update(tenant_id, task_id, {
            "status": new_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    @classmethod
    async def count_by_status(cls, tenant_id: str) -> Dict[str, int]:
        pipeline = [
            {"$match": {"tenant_id": tenant_id}},
            {"$group": {"_id": "$status", "count": {"$sum": 1}}},
        ]
        result = {}
        async for doc in cls.collection.aggregate(pipeline):
            result[doc["_id"]] = doc["count"]
        return result
