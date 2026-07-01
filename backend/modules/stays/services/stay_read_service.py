from typing import Any

from fastapi import HTTPException

from modules.stays.repository import StaysRepository
from security.encrypted_lookup import decrypt_booking_doc, decrypt_guest_doc


class StayReadService:
    def __init__(self, repository: StaysRepository | None = None):
        self.repository = repository or StaysRepository()

    async def get_stay_detail(self, tenant_id: str, stay_id: str) -> dict[str, Any]:
        reservation = await self.repository.get_booking_projection(tenant_id, stay_id)
        if not reservation:
            raise HTTPException(status_code=404, detail="Stay not found")

        # PII (guest email/phone/id + booking guest_email/guest_phone) is encrypted
        # at-rest; decrypt before returning to BI/SDK/partner clients so they never
        # receive AES envelopes or internal blind-index tokens.
        reservation = decrypt_booking_doc(reservation)

        guest = None
        if reservation.get("guest_id"):
            guest = decrypt_guest_doc(await self.repository.get_guest(reservation["guest_id"]))

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
