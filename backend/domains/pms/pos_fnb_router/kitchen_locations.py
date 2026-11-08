"""Resolve room-service labels without changing the saved order or folio."""

import logging
from uuid import UUID

logger = logging.getLogger(__name__)
IN_HOUSE_STATUSES = ("checked_in", "in_house")


async def booking_room_numbers(db, tenant_id: str, bookings: list[dict]) -> dict[str, str]:
    room_ids = {row["room_id"] for row in bookings if row.get("room_id")}
    if not room_ids:
        return {}
    try:
        rooms = await db.rooms.find(
            {"tenant_id": tenant_id, "id": {"$in": list(room_ids)}},
            {"_id": 0, "id": 1, "room_number": 1, "room_no": 1},
        ).to_list(len(room_ids))
    except Exception:
        logger.warning("Could not resolve kitchen room labels", exc_info=True)
        return {}
    numbers = {row["id"]: row.get("room_number") or row.get("room_no") for row in rooms}
    return {
        row["id"]: str(numbers[row["room_id"]])
        for row in bookings
        if row.get("id") and numbers.get(row.get("room_id"))
    }


def _legacy_booking_id(order: dict) -> str | None:
    table_number = order.get("table_number")
    if order.get("room_number") or order.get("table_name") or not order.get("source_pos_order_id"):
        return None
    if not isinstance(table_number, str) or not table_number.startswith("Oda "):
        return None
    booking_id = table_number[4:]
    try:
        UUID(booking_id)
    except ValueError:
        return None
    return booking_id


async def with_kitchen_room_labels(db, tenant_id: str, orders: list[dict]) -> list[dict]:
    booking_ids = [_legacy_booking_id(order) for order in orders]
    legacy_ids = {booking_id for booking_id in booking_ids if booking_id}
    if not legacy_ids:
        return orders
    try:
        bookings = await db.bookings.find(
            {"tenant_id": tenant_id, "id": {"$in": list(legacy_ids)}, "status": {"$in": list(IN_HOUSE_STATUSES)}},
            {"_id": 0, "id": 1, "room_id": 1},
        ).to_list(len(legacy_ids))
    except Exception:
        logger.warning("Could not resolve legacy kitchen bookings", exc_info=True)
        bookings = []
    room_numbers = await booking_room_numbers(db, tenant_id, bookings)
    result = []
    for order, booking_id in zip(orders, booking_ids, strict=True):
        if booking_id:
            room_number = room_numbers.get(booking_id)
            order = {
                **order,
                "table_number": None,
                "table_name": None if room_number else "Oda servisi",
                "room_number": room_number,
            }
        result.append(order)
    return result
