"""
PMS Domain — Reservation Repository
Data access layer for bookings/reservations. No FastAPI dependencies.
"""
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

from core.database import db


class ReservationRepository:
    """MongoDB operations for bookings/reservations."""

    collection = db.bookings

    @classmethod
    async def find_by_tenant(
        cls, tenant_id: str, *, status: Optional[str] = None,
        check_in_from: Optional[str] = None, check_in_to: Optional[str] = None,
        guest_id: Optional[str] = None, room_id: Optional[str] = None,
        limit: int = 50, offset: int = 0, sort_field: str = "check_in",
        sort_order: int = -1,
    ) -> List[Dict[str, Any]]:
        query: Dict[str, Any] = {"tenant_id": tenant_id}
        if status:
            query["status"] = status
        if guest_id:
            query["guest_id"] = guest_id
        if room_id:
            query["room_id"] = room_id
        if check_in_from:
            query.setdefault("check_in", {})["$gte"] = check_in_from
        if check_in_to:
            query.setdefault("check_in", {})["$lte"] = check_in_to

        cursor = (
            cls.collection.find(query, {"_id": 0})
            .sort(sort_field, sort_order)
            .skip(offset)
            .limit(limit)
        )
        return await cursor.to_list(limit)

    @classmethod
    async def find_one(cls, tenant_id: str, booking_id: str) -> Optional[Dict[str, Any]]:
        return await cls.collection.find_one(
            {"tenant_id": tenant_id, "id": booking_id}, {"_id": 0}
        )

    @classmethod
    async def count(cls, tenant_id: str, query_filter: Optional[Dict] = None) -> int:
        query: Dict[str, Any] = {"tenant_id": tenant_id}
        if query_filter:
            query.update(query_filter)
        return await cls.collection.count_documents(query)

    @classmethod
    async def insert(cls, booking_dict: Dict[str, Any]) -> None:
        await cls.collection.insert_one(booking_dict)

    @classmethod
    async def update(cls, tenant_id: str, booking_id: str, update_data: Dict[str, Any]) -> bool:
        result = await cls.collection.update_one(
            {"tenant_id": tenant_id, "id": booking_id},
            {"$set": update_data},
        )
        return result.modified_count > 0

    @classmethod
    async def update_status(cls, tenant_id: str, booking_id: str, new_status: str) -> bool:
        return await cls.update(tenant_id, booking_id, {
            "status": new_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        })

    @classmethod
    async def get_arrivals(cls, tenant_id: str, target_date: str) -> List[Dict[str, Any]]:
        return await cls.collection.find(
            {"tenant_id": tenant_id, "check_in": target_date, "status": {"$in": ["confirmed", "guaranteed"]}},
            {"_id": 0},
        ).to_list(500)

    @classmethod
    async def get_departures(cls, tenant_id: str, target_date: str) -> List[Dict[str, Any]]:
        return await cls.collection.find(
            {"tenant_id": tenant_id, "check_out": target_date, "status": "checked_in"},
            {"_id": 0},
        ).to_list(500)

    @classmethod
    async def get_inhouse(cls, tenant_id: str) -> List[Dict[str, Any]]:
        return await cls.collection.find(
            {"tenant_id": tenant_id, "status": "checked_in"},
            {"_id": 0},
        ).to_list(1000)
