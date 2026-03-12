"""
PMS Domain — Reservation Service
Business logic for booking/reservation operations. No FastAPI dependencies.
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from domains.pms.reservations.repositories.reservation_repository import ReservationRepository
from domains.pms.rooms.repositories.room_repository import RoomRepository


class ReservationService:
    """Pure business logic for reservation management."""

    @staticmethod
    async def get_reservations(
        tenant_id: str, *, status: Optional[str] = None,
        check_in_from: Optional[str] = None, check_in_to: Optional[str] = None,
        guest_id: Optional[str] = None, room_id: Optional[str] = None,
        limit: int = 50, offset: int = 0,
    ) -> List[Dict[str, Any]]:
        return await ReservationRepository.find_by_tenant(
            tenant_id, status=status, check_in_from=check_in_from,
            check_in_to=check_in_to, guest_id=guest_id, room_id=room_id,
            limit=limit, offset=offset,
        )

    @staticmethod
    async def get_reservation(tenant_id: str, booking_id: str) -> Optional[Dict[str, Any]]:
        return await ReservationRepository.find_one(tenant_id, booking_id)

    @staticmethod
    async def create_reservation(tenant_id: str, booking_data: Dict[str, Any]) -> Dict[str, Any]:
        room_id = booking_data.get("room_id")
        if room_id:
            room = await RoomRepository.find_one(tenant_id, room_id)
            if not room:
                raise ValueError(f"Room {room_id} not found")

        booking = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            **booking_data,
            "status": booking_data.get("status", "confirmed"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await ReservationRepository.insert(booking)
        return booking

    @staticmethod
    async def update_reservation(tenant_id: str, booking_id: str, update_data: Dict[str, Any]) -> bool:
        update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
        return await ReservationRepository.update(tenant_id, booking_id, update_data)

    @staticmethod
    async def check_in(tenant_id: str, booking_id: str) -> bool:
        booking = await ReservationRepository.find_one(tenant_id, booking_id)
        if not booking:
            raise ValueError("Booking not found")
        if booking.get("status") not in ("confirmed", "guaranteed"):
            raise ValueError(f"Cannot check in booking with status: {booking.get('status')}")

        # Update booking status
        await ReservationRepository.update_status(tenant_id, booking_id, "checked_in")

        # Update room status to occupied
        room_id = booking.get("room_id")
        if room_id:
            await RoomRepository.update_status(tenant_id, room_id, "occupied")

        return True

    @staticmethod
    async def check_out(tenant_id: str, booking_id: str) -> bool:
        booking = await ReservationRepository.find_one(tenant_id, booking_id)
        if not booking:
            raise ValueError("Booking not found")
        if booking.get("status") != "checked_in":
            raise ValueError(f"Cannot check out booking with status: {booking.get('status')}")

        await ReservationRepository.update_status(tenant_id, booking_id, "checked_out")

        room_id = booking.get("room_id")
        if room_id:
            await RoomRepository.update_status(tenant_id, room_id, "dirty")

        return True

    @staticmethod
    async def cancel_reservation(tenant_id: str, booking_id: str, reason: Optional[str] = None) -> bool:
        booking = await ReservationRepository.find_one(tenant_id, booking_id)
        if not booking:
            raise ValueError("Booking not found")
        if booking.get("status") in ("checked_in", "checked_out", "cancelled"):
            raise ValueError(f"Cannot cancel booking with status: {booking.get('status')}")

        update = {"status": "cancelled", "updated_at": datetime.now(timezone.utc).isoformat()}
        if reason:
            update["cancellation_reason"] = reason
        return await ReservationRepository.update(tenant_id, booking_id, update)

    @staticmethod
    async def get_arrivals(tenant_id: str, target_date: str) -> List[Dict[str, Any]]:
        return await ReservationRepository.get_arrivals(tenant_id, target_date)

    @staticmethod
    async def get_departures(tenant_id: str, target_date: str) -> List[Dict[str, Any]]:
        return await ReservationRepository.get_departures(tenant_id, target_date)

    @staticmethod
    async def get_inhouse_guests(tenant_id: str) -> List[Dict[str, Any]]:
        return await ReservationRepository.get_inhouse(tenant_id)
