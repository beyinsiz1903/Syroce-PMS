"""
Channel Manager — Sync Scheduler
Manages scheduled and event-driven inventory synchronization.
"""
import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

# v42 round-5: cross-tenant scheduler runs without per-request tenant_context.
# All per-tenant queries below carry manual `tenant_id` filters; use the raw
# system DB to bypass STRICT_TENANT_MODE without weakening isolation.
from core.tenant_db import get_system_db as _get_system_db

db = _get_system_db()

logger = logging.getLogger(__name__)


class SyncScheduler:
    """Coordinates periodic and event-driven sync between PMS and OTA channels."""

    _instance = None
    _running = False
    _interval_seconds = 300  # 5 minutes default

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    async def start(self, interval_seconds: int = 300):
        """Start the periodic sync scheduler."""
        self._interval_seconds = interval_seconds
        if self._running:
            logger.warning("SyncScheduler already running")
            return
        self._running = True
        asyncio.create_task(self._run_loop())
        logger.info(f"SyncScheduler started (interval={interval_seconds}s)")

    async def stop(self):
        """Stop the periodic sync scheduler."""
        self._running = False
        logger.info("SyncScheduler stopped")

    async def _run_loop(self):
        """Main scheduling loop."""
        while self._running:
            try:
                await self._execute_scheduled_sync()
            except Exception as e:
                logger.error(f"Scheduled sync error: {e}")
            await asyncio.sleep(self._interval_seconds)

    async def _execute_scheduled_sync(self):
        """Execute sync for all active connections that need syncing."""
        connections = await db.channel_connections.find(
            {"status": "active"},
            {"_id": 0},
        ).to_list(500)

        now = datetime.now(UTC)
        threshold = now - timedelta(seconds=self._interval_seconds)

        for conn in connections:
            last_sync = conn.get("last_sync")
            if last_sync and last_sync > threshold.isoformat():
                continue  # Recently synced, skip

            try:
                await self.sync_connection(conn)
            except Exception as e:
                logger.error(f"Sync failed for connection {conn.get('id')}: {e}")
                await self._log_sync_failure(conn, str(e))

    async def sync_connection(self, connection: dict[str, Any]) -> dict[str, Any]:
        """Sync a single channel connection."""
        tenant_id = connection["tenant_id"]
        connection_id = connection["id"]
        channel = connection.get("channel", "unknown")

        # Get current PMS availability
        rooms = await db.rooms.find(
            {"tenant_id": tenant_id}, {"_id": 0, "id": 1, "room_type": 1, "status": 1}
        ).to_list(1000)

        # Get active bookings
        active_bookings = await db.bookings.count_documents({
            "tenant_id": tenant_id,
            "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
        })

        sync_result = {
            "connection_id": connection_id,
            "channel": channel,
            "total_rooms": len(rooms),
            "active_bookings": active_bookings,
            "available_rooms": sum(1 for r in rooms if r.get("status") == "available"),
            "synced_at": datetime.now(UTC).isoformat(),
            "status": "success",
        }

        # Log sync
        await db.channel_sync_logs.insert_one({
            "tenant_id": tenant_id,
            "connection_id": connection_id,
            "channel": channel,
            "type": "scheduled_sync",
            "result": sync_result,
            "timestamp": datetime.now(UTC).isoformat(),
        })

        # Update last_sync (tenant_id filter included for defense-in-depth)
        await db.channel_connections.update_one(
            {"id": connection_id, "tenant_id": tenant_id},
            {"$set": {"last_sync": datetime.now(UTC).isoformat()}},
        )

        logger.info(f"Synced {channel} for tenant {tenant_id}: {sync_result['available_rooms']} available rooms")
        return sync_result

    async def trigger_event_sync(self, tenant_id: str, event_type: str, event_data: dict):
        """Trigger an immediate sync based on a PMS event (booking, room status change, etc.)."""
        connections = await db.channel_connections.find(
            {"tenant_id": tenant_id, "status": "active"},
            {"_id": 0},
        ).to_list(100)

        results = []
        for conn in connections:
            try:
                result = await self.sync_connection(conn)
                result["trigger"] = event_type
                results.append(result)
            except Exception as e:
                results.append({"connection_id": conn["id"], "status": "error", "error": str(e)})

        return results

    async def _log_sync_failure(self, connection: dict, error: str):
        """Log a sync failure."""
        await db.channel_sync_logs.insert_one({
            "tenant_id": connection.get("tenant_id"),
            "connection_id": connection.get("id"),
            "channel": connection.get("channel"),
            "type": "scheduled_sync",
            "status": "error",
            "error": error,
            "timestamp": datetime.now(UTC).isoformat(),
        })


# Singleton
sync_scheduler = SyncScheduler()
