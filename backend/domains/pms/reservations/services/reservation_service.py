"""
PMS Domain — Reservation Service
Business logic for booking/reservation operations. No FastAPI dependencies.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

from domains.pms.reservations.repositories.reservation_repository import ReservationRepository
from domains.pms.rooms.repositories.room_repository import RoomRepository


class ReservationService:
    """Pure business logic for reservation management."""

    @staticmethod
    async def get_reservations(
        tenant_id: str,
        *,
        status: str | None = None,
        check_in_from: str | None = None,
        check_in_to: str | None = None,
        guest_id: str | None = None,
        room_id: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return await ReservationRepository.find_by_tenant(
            tenant_id,
            status=status,
            check_in_from=check_in_from,
            check_in_to=check_in_to,
            guest_id=guest_id,
            room_id=room_id,
            limit=limit,
            offset=offset,
        )

    @staticmethod
    async def get_reservation(tenant_id: str, booking_id: str) -> dict[str, Any] | None:
        return await ReservationRepository.find_one(tenant_id, booking_id)

    @staticmethod
    async def create_reservation(tenant_id: str, booking_data: dict[str, Any]) -> dict[str, Any]:
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
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        await ReservationRepository.insert(tenant_id, booking)
        return booking

    @staticmethod
    async def update_reservation(tenant_id: str, booking_id: str, update_data: dict[str, Any]) -> bool:
        update_data["updated_at"] = datetime.now(UTC).isoformat()
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
    async def cancel_reservation(tenant_id: str, booking_id: str, reason: str | None = None) -> bool:
        booking = await ReservationRepository.find_one(tenant_id, booking_id)
        if not booking:
            raise ValueError("Booking not found")
        if booking.get("status") in ("checked_in", "checked_out", "cancelled"):
            raise ValueError(f"Cannot cancel booking with status: {booking.get('status')}")

        update = {"status": "cancelled", "updated_at": datetime.now(UTC).isoformat()}
        if reason:
            update["cancellation_reason"] = reason
        result = await ReservationRepository.update(tenant_id, booking_id, update)

        # Inventory release: room_night_locks temizle ve audit timeline'a yaz (INV-6).
        try:
            from core.atomic_booking import release_booking_nights

            await release_booking_nights(tenant_id=tenant_id, booking_id=booking_id, reason="cancelled")
        except Exception:
            import logging

            logging.getLogger(__name__).exception("Lock release failed for booking %s", booking_id)

        return result

    @staticmethod
    async def get_arrivals(tenant_id: str, target_date: str) -> list[dict[str, Any]]:
        return await ReservationRepository.get_arrivals(tenant_id, target_date)

    @staticmethod
    async def get_departures(tenant_id: str, target_date: str) -> list[dict[str, Any]]:
        return await ReservationRepository.get_departures(tenant_id, target_date)

    @staticmethod
    async def get_inhouse_guests(tenant_id: str) -> list[dict[str, Any]]:
        return await ReservationRepository.get_inhouse(tenant_id)
