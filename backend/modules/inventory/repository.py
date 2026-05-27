import hashlib
from datetime import UTC, datetime
from typing import Any

from pymongo.errors import DuplicateKeyError

from core.database import db


class InventoryRepository:
    async def list_rooms(self, tenant_id: str, room_type: str | None = None) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if room_type:
            query["room_type"] = room_type
        return await db.rooms.find(query, {"_id": 0}).to_list(1000)

    async def list_overlapping_bookings(self, tenant_id: str, check_in: str, check_out: str) -> list[dict[str, Any]]:
        return await db.bookings.find(
            {
                "tenant_id": tenant_id,
                "status": {"$in": ["confirmed", "checked_in", "guaranteed"]},
                "check_in": {"$lt": check_out},
                "check_out": {"$gt": check_in},
            },
            {"_id": 0},
        ).to_list(1000)

    async def list_overlapping_blocks(self, tenant_id: str, check_in: str, check_out: str) -> list[dict[str, Any]]:
        return await db.room_blocks.find(
            {
                "tenant_id": tenant_id,
                "status": "active",
                "start_date": {"$lt": check_out},
                "$or": [
                    {"end_date": {"$gt": check_in}},
                    {"end_date": None},
                ],
            },
            {"_id": 0},
        ).to_list(1000)

    async def get_room_for_tenant(self, tenant_id: str, room_id: str) -> dict[str, Any] | None:
        return await db.rooms.find_one(
            {
                "tenant_id": tenant_id,
                "id": room_id,
                "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
            },
            {"_id": 0},
        )

    async def get_room_block_for_tenant(self, tenant_id: str, block_id: str) -> dict[str, Any] | None:
        return await db.room_blocks.find_one(
            {
                "tenant_id": tenant_id,
                "id": block_id,
            },
            {"_id": 0},
        )

    async def list_conflicting_bookings(
        self,
        tenant_id: str,
        room_id: str,
        start_date: str,
        end_date: str | None,
    ) -> list[dict[str, Any]]:
        return await db.bookings.find(
            {
                'tenant_id': tenant_id,
                'room_id': room_id,
                'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']},
                'check_in': {'$lt': end_date or '9999-12-31'},
                'check_out': {'$gt': start_date},
            },
            {'_id': 0},
        ).to_list(100)

    async def insert_room_block(self, block_doc: dict[str, Any]) -> None:
        await db.room_blocks.insert_one(block_doc)

    async def update_room_block(self, tenant_id: str, block_id: str, update_doc: dict[str, Any]) -> None:
        await db.room_blocks.update_one(
            {
                "tenant_id": tenant_id,
                "id": block_id,
            },
            {"$set": update_doc},
        )

    async def insert_exception(self, exception_doc: dict[str, Any]) -> None:
        await db.exceptions.insert_one(exception_doc)

    async def insert_outbox_event(self, event_doc: dict[str, Any]) -> None:
        await db.outbox_events.insert_one(event_doc)

    async def acquire_idempotency_lock(
        self,
        tenant_id: str,
        scope: str,
        idempotency_key: str,
        request_hash: str,
        correlation_id: str | None,
    ) -> dict[str, Any]:
        from shared_kernel.idempotency import (
            IDEMPOTENCY_PROCESSING_GRACE_SECONDS,
        )
        from datetime import timedelta as _td
        lock_id = hashlib.sha256(f"{tenant_id}:{scope}:{idempotency_key}".encode()).hexdigest()
        now = datetime.now(UTC)
        lock_doc = {
            "_id": lock_id,
            "tenant_id": tenant_id,
            "scope": scope,
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
            "correlation_id": correlation_id,
            "status": "processing",
            "created_at": now.isoformat(),
            # Task #81 — TTL sweep field; processing rows expire after grace.
            "expires_at": now + _td(seconds=IDEMPOTENCY_PROCESSING_GRACE_SECONDS),
        }
        try:
            await db.idempotency_keys.insert_one(lock_doc)
            lock_doc.pop("_id", None)
            return {"status": "acquired", "document": lock_doc, "lock_id": lock_id}
        except DuplicateKeyError:
            existing = await db.idempotency_keys.find_one({"_id": lock_id}, {"_id": 0})
            return {"status": "existing", "document": existing or {}, "lock_id": lock_id}

    async def complete_idempotency_lock(
        self,
        lock_id: str,
        room_block_id: str,
        response_body: dict[str, Any],
    ) -> None:
        from shared_kernel.idempotency import IDEMPOTENCY_RETENTION_SECONDS
        from datetime import timedelta as _td
        now = datetime.now(UTC)
        await db.idempotency_keys.update_one(
            {"_id": lock_id},
            {
                "$set": {
                    "status": "completed",
                    "room_block_id": room_block_id,
                    "response_body": response_body,
                    "completed_at": now.isoformat(),
                    # Task #81 — extend TTL to retention window on completion.
                    "expires_at": now + _td(seconds=IDEMPOTENCY_RETENTION_SECONDS),
                }
            },
        )

    async def fail_idempotency_lock(self, lock_id: str, error_message: str) -> None:
        from shared_kernel.idempotency import IDEMPOTENCY_RETENTION_SECONDS
        from datetime import timedelta as _td
        now = datetime.now(UTC)
        await db.idempotency_keys.update_one(
            {"_id": lock_id},
            {
                "$set": {
                    "status": "failed",
                    "error_message": error_message,
                    "failed_at": now.isoformat(),
                    # Task #81 — failed rows kept for replay; expire at 24h.
                    "expires_at": now + _td(seconds=IDEMPOTENCY_RETENTION_SECONDS),
                }
            },
        )
