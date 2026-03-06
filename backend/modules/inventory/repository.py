from typing import Any, Dict, List, Optional

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