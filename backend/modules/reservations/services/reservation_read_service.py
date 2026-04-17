from typing import Any

from core.database import db
from modules.reservations.repository import ReservationsRepository


class ReservationReadService:
    def __init__(self, repository: ReservationsRepository | None = None):
        self.repository = repository or ReservationsRepository()

    async def list_reservations(
        self,
        tenant_id: str,
        limit: int = 30,
        offset: int = 0,
        start_date: str | None = None,
        end_date: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        bookings = await self.repository.list_reservations(
            tenant_id=tenant_id,
            limit=limit,
            offset=offset,
            start_date=start_date,
            end_date=end_date,
            status=status,
        )

        if not bookings:
            return []

        # Batch-fetch guests and rooms to avoid N+1 lookups
        missing_guest_ids = {
            b["guest_id"]
            for b in bookings
            if b.get("guest_id") and not b.get("guest_name")
        }
        room_ids = {b["room_id"] for b in bookings if b.get("room_id")}

        guest_map: dict[str, str] = {}
        if missing_guest_ids:
            async for g in db.guests.find(
                {"id": {"$in": list(missing_guest_ids)}},
                {"_id": 0, "id": 1, "name": 1, "first_name": 1, "last_name": 1},
            ):
                name = g.get("name") or f"{g.get('first_name', '')} {g.get('last_name', '')}".strip()
                if name:
                    guest_map[g["id"]] = name

        room_map: dict[str, dict[str, Any]] = {}
        if room_ids:
            async for r in db.rooms.find(
                {"id": {"$in": list(room_ids)}},
                {"_id": 0, "id": 1, "room_number": 1, "room_type": 1},
            ):
                room_map[r["id"]] = r

        rate_map = {"advance_purchase": "promotional", "member": "promotional"}
        segment_map = {"business": "corporate"}

        enriched: list[dict[str, Any]] = []
        for booking in bookings:
            booking = dict(booking)
            if not booking.get("guest_name") and booking.get("guest_id"):
                booking["guest_name"] = guest_map.get(booking["guest_id"], "Unknown Guest")

            if booking.get("room_id"):
                room_doc = room_map.get(booking["room_id"])
                if room_doc:
                    booking["room_number"] = room_doc.get("room_number") or booking.get("room_number") or "Unknown Room"
                    if not booking.get("room_type"):
                        booking["room_type"] = room_doc.get("room_type")
                else:
                    booking["room_number"] = booking.get("room_number") or "Unknown Room"

            if booking.get("rate_type") in rate_map:
                booking["rate_type"] = rate_map[booking["rate_type"]]
            if booking.get("market_segment") in segment_map:
                booking["market_segment"] = segment_map[booking["market_segment"]]

            enriched.append(booking)

        return enriched
