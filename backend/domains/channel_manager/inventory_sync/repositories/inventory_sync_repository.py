"""
Channel Manager Domain — Inventory Sync Repository
Data access layer for channel inventory sync operations. No FastAPI dependencies.
"""
from typing import Any

from core.tenant_db import LazyCollection


class InventorySyncRepository:
    """MongoDB operations for channel inventory sync."""

    connections = LazyCollection("channel_connections")
    sync_logs = LazyCollection("channel_sync_logs")
    rate_updates = LazyCollection("rate_updates")

    @classmethod
    async def get_connections(cls, tenant_id: str, *, active_only: bool = True) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if active_only:
            query["status"] = "active"
        return await cls.connections.find(query, {"_id": 0}).to_list(100)

    @classmethod
    async def get_connection(cls, tenant_id: str, connection_id: str) -> dict[str, Any] | None:
        return await cls.connections.find_one(
            {"tenant_id": tenant_id, "id": connection_id}, {"_id": 0}
        )

    @classmethod
    async def upsert_connection(cls, connection: dict[str, Any]) -> None:
        await cls.connections.update_one(
            {"tenant_id": connection["tenant_id"], "id": connection["id"]},
            {"$set": connection},
            upsert=True,
        )

    @classmethod
    async def log_sync(cls, sync_entry: dict[str, Any]) -> None:
        await cls.sync_logs.insert_one(sync_entry)

    @classmethod
    async def get_sync_logs(
        cls, tenant_id: str, *, limit: int = 50, channel: str | None = None,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if channel:
            query["channel"] = channel
        return await cls.sync_logs.find(
            query, {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(limit)

    @classmethod
    async def log_rate_update(cls, rate_entry: dict[str, Any]) -> None:
        await cls.rate_updates.insert_one(rate_entry)
