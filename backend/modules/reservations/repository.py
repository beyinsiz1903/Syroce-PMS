from typing import Any, Dict, List, Optional

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