"""Atomic reservation room swaps.

Moving a reservation into an occupied room is normally (and correctly)
rejected by the room-night uniqueness guard.  A room swap is different: two
existing reservations exchange their physical rooms as one unit.  This module
performs that unit inside a MongoDB transaction so neither reservation is ever
left unassigned and the room-night locks remain authoritative.
"""

from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import Any

from pymongo import ReadPreference
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern

from core.atomic_booking import TERMINAL_BOOKING_STATUSES, _night_dates
from core.database import db


class RoomSwapError(Exception):
    """A safe, operator-readable room swap rejection."""

    def __init__(self, message: str, code: str = "ROOM_SWAP_REJECTED"):
        super().__init__(message)
        self.code = code


class RoomSwapService:
    """Swap the rooms of two active reservations without an unassigned gap."""

    @staticmethod
    def _is_active(booking: dict[str, Any]) -> bool:
        return (booking.get("status") or "").lower() not in TERMINAL_BOOKING_STATUSES

    @staticmethod
    def _update_filter(tenant_id: str, booking: dict[str, Any]) -> dict[str, Any]:
        query: dict[str, Any] = {"tenant_id": tenant_id, "id": booking["id"]}
        if booking.get("_version") is not None:
            query["_version"] = booking["_version"]
        return query

    async def swap(
        self,
        *,
        tenant_id: str,
        booking_id: str,
        target_booking_id: str,
        reason: str,
        moved_by: str,
    ) -> dict[str, Any]:
        if not reason.strip():
            raise RoomSwapError("Oda takası için neden zorunludur.", "REASON_REQUIRED")
        if booking_id == target_booking_id:
            raise RoomSwapError("Aynı rezervasyonla oda takası yapılamaz.", "SAME_BOOKING")

        async def _transaction(session):
            source = await db.bookings.find_one(
                {"tenant_id": tenant_id, "id": booking_id},
                session=session,
            )
            target = await db.bookings.find_one(
                {"tenant_id": tenant_id, "id": target_booking_id},
                session=session,
            )
            if not source or not target:
                raise RoomSwapError("Takas edilecek rezervasyon bulunamadı.", "BOOKING_NOT_FOUND")
            if not self._is_active(source) or not self._is_active(target):
                raise RoomSwapError("İptal, no-show veya çıkış yapılmış rezervasyon takas edilemez.", "INACTIVE_BOOKING")
            if source.get("status") == "checked_in" or target.get("status") == "checked_in":
                raise RoomSwapError(
                    "Giriş yapılmış misafirlerde oda takası yerine ön büro oda taşıma işlemini kullanın.",
                    "CHECKED_IN_BOOKING",
                )

            source_room_id = source.get("room_id")
            target_room_id = target.get("room_id")
            if not source_room_id or not target_room_id:
                raise RoomSwapError("Her iki rezervasyonun da atanmış odası olmalıdır.", "UNASSIGNED_BOOKING")
            if source_room_id == target_room_id:
                raise RoomSwapError("Rezervasyonlar zaten aynı odada.", "SAME_ROOM")

            try:
                source_nights = _night_dates(source["check_in"], source["check_out"])
                target_nights = _night_dates(target["check_in"], target["check_out"])
            except (KeyError, TypeError, ValueError) as exc:
                raise RoomSwapError("Rezervasyon tarihleri oda takası için geçersiz.", "INVALID_DATES") from exc
            if not source_nights or not target_nights:
                raise RoomSwapError("Sıfır gecelik rezervasyonlarda oda takası yapılamaz.", "INVALID_DATES")

            rooms = await db.rooms.find(
                {"tenant_id": tenant_id, "id": {"$in": [source_room_id, target_room_id]}},
                session=session,
            ).to_list(2)
            rooms_by_id = {room["id"]: room for room in rooms}
            if source_room_id not in rooms_by_id or target_room_id not in rooms_by_id:
                raise RoomSwapError("Takas odalarından biri artık mevcut değil.", "ROOM_NOT_FOUND")
            source_room = rooms_by_id[source_room_id]
            target_room = rooms_by_id[target_room_id]

            active_statuses = ["confirmed", "guaranteed", "checked_in", "pending"]
            for booking, destination_room_id in ((source, target_room_id), (target, source_room_id)):
                conflict = await db.bookings.find_one(
                    {
                        "tenant_id": tenant_id,
                        "id": {"$nin": [booking_id, target_booking_id]},
                        "room_id": destination_room_id,
                        "status": {"$in": active_statuses},
                        "check_in": {"$lt": booking["check_out"]},
                        "check_out": {"$gt": booking["check_in"]},
                    },
                    {"_id": 0, "id": 1, "guest_name": 1},
                    session=session,
                )
                if conflict:
                    raise RoomSwapError(
                        f"Hedef oda başka bir rezervasyonla çakışıyor: {conflict.get('guest_name') or conflict['id']}.",
                        "TARGET_ROOM_CONFLICT",
                    )

            desired_locks = [
                (target_room_id, night, booking_id) for night in source_nights
            ] + [
                (source_room_id, night, target_booking_id) for night in target_nights
            ]
            desired_pairs = {(room_id, night) for room_id, night, _ in desired_locks}
            existing_locks = await db.room_night_locks.find(
                {
                    "tenant_id": tenant_id,
                    "room_id": {"$in": [source_room_id, target_room_id]},
                    "night_date": {"$in": sorted({night for _, night in desired_pairs})},
                },
                {"_id": 0, "room_id": 1, "night_date": 1, "booking_id": 1, "lock_type": 1},
                session=session,
            ).to_list(1000)
            for lock in existing_locks:
                if (lock.get("room_id"), lock.get("night_date")) not in desired_pairs:
                    continue
                if lock.get("booking_id") not in {booking_id, target_booking_id}:
                    raise RoomSwapError(
                        "Hedef odalardan biri bakım, servis dışı veya başka bir rezervasyon tarafından kilitli.",
                        "TARGET_LOCK_CONFLICT",
                    )

            # Removing only these two owners' locks and recreating their final
            # state in the *same transaction* is what makes a true swap safe.
            # The unique (tenant, room, night) index is checked against the
            # transaction's final state, not a transient unassigned state.
            await db.room_night_locks.delete_many(
                {"tenant_id": tenant_id, "booking_id": {"$in": [booking_id, target_booking_id]}},
                session=session,
            )
            now_iso = datetime.now(UTC).isoformat()
            await db.room_night_locks.insert_many(
                [
                    {
                        "tenant_id": tenant_id,
                        "room_id": room_id,
                        "night_date": night,
                        "booking_id": owner_booking_id,
                        "lock_type": "booking",
                        "created_at": now_iso,
                    }
                    for room_id, night, owner_booking_id in desired_locks
                ],
                session=session,
            )

            source_result = await db.bookings.update_one(
                self._update_filter(tenant_id, source),
                {
                    "$set": {
                        "room_id": target_room_id,
                        "room_type": target_room.get("room_type", source.get("room_type")),
                        "room_moved_at": now_iso,
                        "room_move_reason": reason,
                        "updated_at": now_iso,
                    },
                    "$inc": {"_version": 1},
                },
                session=session,
            )
            target_result = await db.bookings.update_one(
                self._update_filter(tenant_id, target),
                {
                    "$set": {
                        "room_id": source_room_id,
                        "room_type": source_room.get("room_type", target.get("room_type")),
                        "room_moved_at": now_iso,
                        "room_move_reason": reason,
                        "updated_at": now_iso,
                    },
                    "$inc": {"_version": 1},
                },
                session=session,
            )
            if source_result.matched_count != 1 or target_result.matched_count != 1:
                raise RoomSwapError("Rezervasyon başka bir kullanıcı tarafından güncellendi. Yeniden deneyin.", "CONCURRENT_MODIFICATION")

            history_records = [
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "booking_id": booking_id,
                    "from_room_id": source_room_id,
                    "from_room_number": source_room.get("room_number"),
                    "to_room_id": target_room_id,
                    "to_room_number": target_room.get("room_number"),
                    "reason": reason,
                    "moved_by": moved_by,
                    "moved_at": now_iso,
                    "swap_booking_id": target_booking_id,
                },
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "booking_id": target_booking_id,
                    "from_room_id": target_room_id,
                    "from_room_number": target_room.get("room_number"),
                    "to_room_id": source_room_id,
                    "to_room_number": source_room.get("room_number"),
                    "reason": reason,
                    "moved_by": moved_by,
                    "moved_at": now_iso,
                    "swap_booking_id": booking_id,
                },
            ]
            await db.room_move_history.insert_many(history_records, session=session)

            return {
                "message": "Oda takası tamamlandı.",
                "source_booking_id": booking_id,
                "target_booking_id": target_booking_id,
                "source_room": target_room.get("room_number"),
                "target_room": source_room.get("room_number"),
                "moved_at": now_iso,
            }

        # Atlas/production is a replica set.  Local standalone development may
        # opt in to the identical workflow only when its test environment has
        # explicitly disabled transactions.
        if os.environ.get("MONGO_DISABLE_TRANSACTIONS") == "1":
            return await _transaction(None)

        async with await db.client.start_session() as session:
            return await session.with_transaction(
                _transaction,
                read_concern=ReadConcern("snapshot"),
                write_concern=WriteConcern("majority"),
                read_preference=ReadPreference.PRIMARY,
            )


room_swap_service = RoomSwapService()
