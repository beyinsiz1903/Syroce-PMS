"""
Guest Domain — Guest Journey Service
Business logic for guest profile and journey management. No FastAPI dependencies.
"""
import uuid
from datetime import UTC, datetime
from typing import Any

from domains.guest.journey.repositories.guest_repository import GuestRepository


class GuestJourneyService:
    """Pure business logic for guest lifecycle management."""

    @staticmethod
    async def get_guests(
        tenant_id: str, *, search: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[dict[str, Any]]:
        return await GuestRepository.find_by_tenant(
            tenant_id, search=search, limit=limit, offset=offset,
        )

    @staticmethod
    async def get_guest(tenant_id: str, guest_id: str) -> dict[str, Any] | None:
        return await GuestRepository.find_one(tenant_id, guest_id)

    @staticmethod
    async def create_guest(tenant_id: str, guest_data: dict[str, Any]) -> dict[str, Any]:
        email = guest_data.get("email")
        if email:
            existing = await GuestRepository.find_by_email(tenant_id, email)
            if existing:
                raise ValueError(f"Guest with email {email} already exists")

        guest = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            **guest_data,
            "total_stays": 0,
            "total_revenue": 0,
            "loyalty_tier": "bronze",
            "created_at": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        await GuestRepository.insert(guest)
        return guest

    @staticmethod
    async def update_guest(tenant_id: str, guest_id: str, update_data: dict[str, Any]) -> bool:
        update_data["updated_at"] = datetime.now(UTC).isoformat()
        return await GuestRepository.update(tenant_id, guest_id, update_data)

    @staticmethod
    async def record_stay(tenant_id: str, guest_id: str, revenue: float) -> bool:
        """Increment stay count and total revenue after checkout."""
        guest = await GuestRepository.find_one(tenant_id, guest_id)
        if not guest:
            raise ValueError("Guest not found")

        new_stays = guest.get("total_stays", 0) + 1
        new_revenue = guest.get("total_revenue", 0) + revenue

        # Auto-upgrade loyalty tier
        tier = "bronze"
        if new_stays >= 20 or new_revenue >= 50000:
            tier = "platinum"
        elif new_stays >= 10 or new_revenue >= 20000:
            tier = "gold"
        elif new_stays >= 5 or new_revenue >= 5000:
            tier = "silver"

        return await GuestRepository.update(tenant_id, guest_id, {
            "total_stays": new_stays,
            "total_revenue": new_revenue,
            "loyalty_tier": tier,
            "last_stay": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        })

    @staticmethod
    async def get_vip_guests(tenant_id: str) -> list[dict[str, Any]]:
        return await GuestRepository.get_vip_guests(tenant_id)

    @staticmethod
    async def get_guest_count(tenant_id: str) -> int:
        return await GuestRepository.count(tenant_id)
