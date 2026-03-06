import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo.errors import DuplicateKeyError

from core.database import db


class InventoryRepository:
    async def list_rooms(self, tenant_id: str, room_type: Optional[str] = None) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {"tenant_id": tenant_id}
        if room_type:
            query["room_type"] = room_type
        return await db.rooms.find(query, {"_id": 0}).to_list(1000)

    async def list_overlapping_bookings(self, tenant_id: str, check_in: str, check_out: str) -> List[Dict[str, Any]]:
        return await db.bookings.find(
            {
                "tenant_id": tenant_id,
                "status": {"$in": ["confirmed", "checked_in", "guaranteed"]},
                "check_in": {"$lt": check_out},
                "check_out": {"$gt": check_in},
            },
            {"_id": 0},
        ).to_list(1000)

    async def list_overlapping_blocks(self, tenant_id: str, check_in: str, check_out: str) -> List[Dict[str, Any]]:
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

    async def get_room_for_tenant(self, tenant_id: str, room_id: str) -> Optional[Dict[str, Any]]:
        return await db.rooms.find_one(
            {
                "tenant_id": tenant_id,
                "id": room_id,
                "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
            },
            {"_id": 0},
        )

    async def get_room_block_for_tenant(self, tenant_id: str, block_id: str) -> Optional[Dict[str, Any]]:
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
        end_date: Optional[str],
    ) -> List[Dict[str, Any]]:
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

    async def insert_room_block(self, block_doc: Dict[str, Any]) -> None:
        await db.room_blocks.insert_one(block_doc)

    async def update_room_block(self, tenant_id: str, block_id: str, update_doc: Dict[str, Any]) -> None:
        await db.room_blocks.update_one(
            {
                "tenant_id": tenant_id,
                "id": block_id,
            },
            {"$set": update_doc},
        )

    async def insert_exception(self, exception_doc: Dict[str, Any]) -> None:
        await db.exceptions.insert_one(exception_doc)

    async def insert_outbox_event(self, event_doc: Dict[str, Any]) -> None:
        await db.outbox_events.insert_one(event_doc)

    async def acquire_idempotency_lock(
        self,
        tenant_id: str,
        scope: str,
        idempotency_key: str,
        request_hash: str,
        correlation_id: Optional[str],
    ) -> Dict[str, Any]:
        lock_id = hashlib.sha256(f"{tenant_id}:{scope}:{idempotency_key}".encode("utf-8")).hexdigest()
        lock_doc = {
            "_id": lock_id,
            "tenant_id": tenant_id,
            "scope": scope,
            "idempotency_key": idempotency_key,
            "request_hash": request_hash,
            "correlation_id": correlation_id,
            "status": "processing",
            "created_at": datetime.now(timezone.utc).isoformat(),
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
        response_body: Dict[str, Any],
    ) -> None:
        await db.idempotency_keys.update_one(
            {"_id": lock_id},
            {
                "$set": {
                    "status": "completed",
                    "room_block_id": room_block_id,
                    "response_body": response_body,
                    "completed_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )

    async def fail_idempotency_lock(self, lock_id: str, error_message: str) -> None:
        await db.idempotency_keys.update_one(
            {"_id": lock_id},
            {
                "$set": {
                    "status": "failed",
                    "error_message": error_message,
                    "failed_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )