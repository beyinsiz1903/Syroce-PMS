from typing import Any, Dict, List, Optional

from modules.reservations.repository import ReservationsRepository


class ReservationReadService:
    def __init__(self, repository: Optional[ReservationsRepository] = None):
        self.repository = repository or ReservationsRepository()

    async def list_reservations(
        self,
        tenant_id: str,
        limit: int = 30,
        offset: int = 0,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        bookings = await self.repository.list_reservations(
            tenant_id=tenant_id,
            limit=limit,
            offset=offset,
            start_date=start_date,
            end_date=end_date,
            status=status,
        )

        enriched: List[Dict[str, Any]] = []
        for booking in bookings:
            booking = dict(booking)
            guest_name = booking.get("guest_name")
            if not guest_name and booking.get("guest_id"):
                booking["guest_name"] = await self.repository.get_guest_name(booking["guest_id"]) or "Unknown Guest"

            if booking.get("room_id"):
                room_doc = await self.repository.get_room_for_tenant_public(booking["room_id"])
                if room_doc:
                    booking["room_number"] = room_doc.get("room_number") or booking.get("room_number") or "Unknown Room"
                    if not booking.get("room_type"):
                        booking["room_type"] = room_doc.get("room_type")
                else:
                    booking["room_number"] = booking.get("room_number") or "Unknown Room"

            rate_map = {
                "advance_purchase": "promotional",
                "member": "promotional",
            }
            if booking.get("rate_type") in rate_map:
                booking["rate_type"] = rate_map[booking["rate_type"]]

            segment_map = {"business": "corporate"}
            if booking.get("market_segment") in segment_map:
                booking["market_segment"] = segment_map[booking["market_segment"]]

            enriched.append(booking)

        return enriched