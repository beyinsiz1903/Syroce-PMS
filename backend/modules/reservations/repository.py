import hashlib
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pymongo.errors import DuplicateKeyError

from core.database import db


class ReservationsRepository:
    async def list_reservations(
        self,
        tenant_id: str,
        limit: int = 30,
        offset: int = 0,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {"tenant_id": tenant_id}

        if start_date or end_date:
            if start_date and end_date:
                query["$and"] = [
                    {"check_out": {"$gt": start_date}},
                    {"check_in": {"$lt": end_date}},
                ]
            elif start_date:
                query["check_out"] = {"$gt": start_date}
            elif end_date:
                query["check_in"] = {"$lt": end_date}

        if status:
            query["status"] = status

        cursor = db.bookings.find(query, {"_id": 0}).sort("check_in", -1).skip(offset).limit(limit)
        return await cursor.to_list(length=limit)

    async def get_guest_name(self, guest_id: str) -> Optional[str]:
        guest = await db.guests.find_one(
            {"id": guest_id},
            {"first_name": 1, "last_name": 1, "name": 1, "_id": 0},
        )
        if not guest:
            return None

        if guest.get("name"):
            return guest["name"]

        first_name = guest.get("first_name", "")
        last_name = guest.get("last_name", "")
        full_name = f"{first_name} {last_name}".strip()
        return full_name or None

    async def get_room_number(self, room_id: str) -> Optional[str]:
        room = await db.rooms.find_one({"id": room_id}, {"room_number": 1, "_id": 0})
        return room.get("room_number") if room else None

    async def get_room_for_tenant_public(self, room_id: str) -> Optional[Dict[str, Any]]:
        """Get room_number + room_type by room_id (no tenant check, for enrichment)."""
        return await db.rooms.find_one({"id": room_id}, {"_id": 0, "room_number": 1, "room_type": 1})

    async def get_room_for_tenant(self, tenant_id: str, room_id: str) -> Optional[Dict[str, Any]]:
        return await db.rooms.find_one(
            {
                "tenant_id": tenant_id,
                "id": room_id,
                "$or": [{"is_active": True}, {"is_active": {"$exists": False}}],
            },
            {"_id": 0},
        )

    async def update_room_for_tenant(self, tenant_id: str, room_id: str, update_doc: Dict[str, Any]) -> None:
        await db.rooms.update_one(
            {"tenant_id": tenant_id, "id": room_id},
            {"$set": update_doc},
        )

    async def get_guest_for_tenant(self, tenant_id: str, guest_id: str) -> Optional[Dict[str, Any]]:
        return await db.guests.find_one({"tenant_id": tenant_id, "id": guest_id}, {"_id": 0})

    async def get_booking_for_tenant(self, tenant_id: str, booking_id: str) -> Optional[Dict[str, Any]]:
        return await db.bookings.find_one(
            {"tenant_id": tenant_id, "id": booking_id},
            {"_id": 0},
        )

    async def update_booking(self, tenant_id: str, booking_id: str, update_doc: Dict[str, Any],
                             expected_version: Optional[int] = None) -> bool:
        """Update booking with optional optimistic locking (INV-4).

        If expected_version is provided, the update only succeeds if the
        current _version matches. This prevents lost updates from concurrent
        modifications (cancel vs modify race).

        Returns True if the update was applied, False if version conflict.
        """
        query = {"tenant_id": tenant_id, "id": booking_id}
        if expected_version is not None:
            query["_version"] = expected_version

        update_doc["_version"] = (expected_version or 0) + 1

        result = await db.bookings.update_one(query, {"$set": update_doc})

        if result.matched_count == 0 and expected_version is not None:
            # Version conflict — someone else modified the booking
            return False
        return True

    async def insert_booking(self, booking_doc: Dict[str, Any]) -> None:
        from core.atomic_booking import create_booking_atomic
        await create_booking_atomic(booking_doc)

    async def insert_rate_override_log(self, override_doc: Dict[str, Any]) -> None:
        await db.rate_override_logs.insert_one(override_doc)

    async def insert_folio(self, folio_doc: Dict[str, Any]) -> None:
        await db.folios.insert_one(folio_doc)

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
        reservation_id: str,
        response_body: Dict[str, Any],
    ) -> None:
        await db.idempotency_keys.update_one(
            {"_id": lock_id},
            {
                "$set": {
                    "status": "completed",
                    "reservation_id": reservation_id,
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
