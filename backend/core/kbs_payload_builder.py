"""Build a current KBS payload from canonical booking, room and guest data."""

from __future__ import annotations


async def resolve_booking_room_number(database, tenant_id: str, booking: dict) -> str:
    """Resolve the room currently assigned to a booking.

    Older/imported bookings can have an empty or stale ``room_number`` while
    ``room_id`` points at the actual room. The room record is authoritative
    whenever that relationship exists.
    """
    room_number = str(booking.get("room_number") or "").strip()
    room_id = booking.get("room_id")
    if not room_id:
        return room_number

    room = await database.rooms.find_one(
        {"tenant_id": tenant_id, "id": room_id},
        {"_id": 0, "room_number": 1},
    )
    return str((room or {}).get("room_number") or room_number).strip()


async def build_kbs_payload_snapshot(database, tenant_id: str, booking_id: str) -> tuple[dict, dict, dict]:
    """Return ``(booking, guest, payload)`` using current canonical records."""
    booking = await database.bookings.find_one(
        {"tenant_id": tenant_id, "id": booking_id},
        {
            "_id": 0,
            "id": 1,
            "guest_id": 1,
            "guest_name": 1,
            "guest_email": 1,
            "guest_phone": 1,
            "room_id": 1,
            "room_number": 1,
            "check_in": 1,
            "check_out": 1,
            "adults": 1,
            "children": 1,
            "status": 1,
            "confirmation_code": 1,
            "guest_nationality": 1,
        },
    )
    if not booking:
        return {}, {}, {}

    room_number = await resolve_booking_room_number(database, tenant_id, booking)
    guest: dict = {}
    if booking.get("guest_id"):
        from security.encrypted_lookup import decrypt_guest_doc

        guest = (
            decrypt_guest_doc(
                await database.guests.find_one(
                    {"tenant_id": tenant_id, "id": booking["guest_id"]},
                    {
                        "_id": 0,
                        "id": 1,
                        "nationality": 1,
                        "id_number": 1,
                        "passport_number": 1,
                        "birth_date": 1,
                        "date_of_birth": 1,
                        "gender": 1,
                        "address": 1,
                        "father_name": 1,
                        "mother_name": 1,
                        "birth_place": 1,
                    },
                )
            )
            or {}
        )

    snapshot = {
        "guest_name": booking.get("guest_name", ""),
        "phone": booking.get("guest_phone", ""),
        "room_number": room_number,
        "check_in": booking.get("check_in", ""),
        "check_out": booking.get("check_out", ""),
        "nationality": guest.get("nationality") or booking.get("guest_nationality") or "TC",
        "id_number": guest.get("id_number", ""),
        "passport_number": guest.get("passport_number", ""),
        "birth_date": guest.get("birth_date") or guest.get("date_of_birth", ""),
        "gender": guest.get("gender", ""),
        "father_name": guest.get("father_name", ""),
        "mother_name": guest.get("mother_name", ""),
        "birth_place": guest.get("birth_place", ""),
        "address": guest.get("address", ""),
    }
    return booking, guest, snapshot
