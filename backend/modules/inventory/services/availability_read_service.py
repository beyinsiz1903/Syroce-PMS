from typing import Any

from modules.inventory.repository import InventoryRepository


class AvailabilityReadService:
    def __init__(self, repository: InventoryRepository | None = None):
        self.repository = repository or InventoryRepository()

    async def get_availability(
        self,
        tenant_id: str,
        check_in: str,
        check_out: str,
        room_type: str | None = None,
    ) -> list[dict[str, Any]]:
        rooms = await self.repository.list_rooms(tenant_id, room_type)
        bookings = await self.repository.list_overlapping_bookings(tenant_id, check_in, check_out)
        blocks = await self.repository.list_overlapping_blocks(tenant_id, check_in, check_out)

        availability: list[dict[str, Any]] = []
        for room in rooms:
            is_booked = any(b.get("room_id") == room.get("id") for b in bookings)
            room_blocks = [block for block in blocks if block.get("room_id") == room.get("id")]
            is_blocked = any(not block.get("allow_sell", False) for block in room_blocks)

            room_projection = dict(room)
            if not is_booked and not is_blocked:
                room_projection["available"] = True
            else:
                reasons = []
                if is_booked:
                    reasons.append("booked")
                if is_blocked:
                    active_blocks = [block for block in room_blocks if not block.get("allow_sell")]
                    if active_blocks:
                        reasons.append(str(active_blocks[0].get("type")))

                room_projection.update(
                    {
                        "available": False,
                        "reason": ", ".join(reasons),
                        "blocks": room_blocks,
                    }
                )

            availability.append(room_projection)

        return availability
