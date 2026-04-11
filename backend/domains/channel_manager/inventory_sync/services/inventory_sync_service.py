"""
Channel Manager Domain — Inventory Sync Service
Business logic for channel inventory synchronization. No FastAPI dependencies.
"""
import uuid
from datetime import UTC, datetime
from typing import Any

from domains.channel_manager.inventory_sync.repositories.inventory_sync_repository import (
    InventorySyncRepository,
)


class InventorySyncService:
    """Pure business logic for channel inventory sync."""

    @staticmethod
    async def get_channel_connections(tenant_id: str) -> list[dict[str, Any]]:
        return await InventorySyncRepository.get_connections(tenant_id)

    @staticmethod
    async def create_connection(
        tenant_id: str, channel: str, credentials: dict[str, Any],
        room_mappings: list[dict] | None = None,
    ) -> dict[str, Any]:
        connection = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "channel": channel,
            "status": "active",
            "credentials": credentials,
            "room_mappings": room_mappings or [],
            "last_sync": None,
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        await InventorySyncRepository.upsert_connection(connection)
        return connection

    @staticmethod
    async def sync_availability(
        tenant_id: str, connection_id: str,
        availability_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Push availability update to an OTA channel."""
        connection = await InventorySyncRepository.get_connection(tenant_id, connection_id)
        if not connection:
            raise ValueError("Channel connection not found")

        sync_log = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "connection_id": connection_id,
            "channel": connection.get("channel"),
            "type": "availability_push",
            "data": availability_data,
            "status": "success",
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await InventorySyncRepository.log_sync(sync_log)

        # Update last_sync on connection
        await InventorySyncRepository.upsert_connection({
            **connection,
            "last_sync": datetime.now(UTC).isoformat(),
        })

        return sync_log

    @staticmethod
    async def sync_rates(
        tenant_id: str, connection_id: str,
        rate_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Push rate update to an OTA channel."""
        connection = await InventorySyncRepository.get_connection(tenant_id, connection_id)
        if not connection:
            raise ValueError("Channel connection not found")

        rate_entry = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "connection_id": connection_id,
            "channel": connection.get("channel"),
            **rate_data,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        await InventorySyncRepository.log_rate_update(rate_entry)
        return rate_entry

    @staticmethod
    async def get_sync_history(
        tenant_id: str, *, limit: int = 50, channel: str | None = None,
    ) -> list[dict[str, Any]]:
        return await InventorySyncRepository.get_sync_logs(
            tenant_id, limit=limit, channel=channel,
        )
