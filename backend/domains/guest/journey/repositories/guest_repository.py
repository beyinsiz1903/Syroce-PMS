"""
Guest Domain — Guest Journey Repository
Data access layer for guest profile and journey operations. No FastAPI dependencies.
"""
from typing import Any

from core.tenant_db import LazyCollection


class GuestRepository:
    """MongoDB operations for guest profiles."""

    collection = LazyCollection("guests")

    @classmethod
    async def find_by_tenant(
        cls, tenant_id: str, *, search: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[dict[str, Any]]:
        from security.query_safety import safe_search_term
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if (s := safe_search_term(search)):
            query["$or"] = [
                {"name": {"$regex": s, "$options": "i"}},
                {"email": {"$regex": s, "$options": "i"}},
                {"phone": {"$regex": s, "$options": "i"}},
            ]
        cursor = cls.collection.find(query, {"_id": 0}).sort("created_at", -1).skip(offset).limit(limit)
        return await cursor.to_list(limit)

    @classmethod
    async def find_one(cls, tenant_id: str, guest_id: str) -> dict[str, Any] | None:
        return await cls.collection.find_one(
            {"tenant_id": tenant_id, "id": guest_id}, {"_id": 0}
        )

    @classmethod
    async def find_by_email(cls, tenant_id: str, email: str) -> dict[str, Any] | None:
        return await cls.collection.find_one(
            {"tenant_id": tenant_id, "email": email}, {"_id": 0}
        )

    @classmethod
    async def insert(cls, guest_dict: dict[str, Any]) -> None:
        await cls.collection.insert_one(guest_dict)

    @classmethod
    async def update(cls, tenant_id: str, guest_id: str, update_data: dict[str, Any]) -> bool:
        result = await cls.collection.update_one(
            {"tenant_id": tenant_id, "id": guest_id},
            {"$set": update_data},
        )
        return result.modified_count > 0

    @classmethod
    async def count(cls, tenant_id: str) -> int:
        return await cls.collection.count_documents({"tenant_id": tenant_id})

    @classmethod
    async def get_vip_guests(cls, tenant_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        return await cls.collection.find(
            {"tenant_id": tenant_id, "vip_status": {"$ne": None}}, {"_id": 0}
        ).sort("total_stays", -1).limit(limit).to_list(limit)
