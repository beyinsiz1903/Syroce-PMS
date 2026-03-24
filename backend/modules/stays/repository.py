from typing import Any, Dict, List, Optional

from core.database import db


class StaysRepository:
    async def get_booking_projection(self, tenant_id: str, stay_id: str) -> Optional[Dict[str, Any]]:
        return await db.bookings.find_one({"tenant_id": tenant_id, "id": stay_id}, {"_id": 0})

    async def get_guest(self, guest_id: str) -> Optional[Dict[str, Any]]:
        return await db.guests.find_one({"id": guest_id}, {"_id": 0})

    async def get_room(self, room_id: str) -> Optional[Dict[str, Any]]:
        return await db.rooms.find_one({"id": room_id}, {"_id": 0})

    async def get_folios_for_booking(self, tenant_id: str, booking_id: str) -> List[Dict[str, Any]]:
        return await db.folios.find({"tenant_id": tenant_id, "booking_id": booking_id}, {"_id": 0}).to_list(100)
