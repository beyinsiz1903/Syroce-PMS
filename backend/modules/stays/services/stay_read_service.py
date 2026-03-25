from typing import Any

from fastapi import HTTPException

from modules.stays.repository import StaysRepository


class StayReadService:
    def __init__(self, repository: StaysRepository | None = None):
        self.repository = repository or StaysRepository()

    async def get_stay_detail(self, tenant_id: str, stay_id: str) -> dict[str, Any]:
        reservation = await self.repository.get_booking_projection(tenant_id, stay_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Stay not found")

        guest = None
        if reservation.get("guest_id"):
            guest = await self.repository.get_guest(reservation["guest_id"])

        room = None
        if reservation.get("room_id"):
            room = await self.repository.get_room(reservation["room_id"])

        folios = await self.repository.get_folios_for_booking(tenant_id, reservation["id"])
        return {
            "stay_id": reservation["id"],
            "reservation": reservation,
            "guest": guest,
            "room": room,
            "folios": folios,
            "timeline": [],
        }
