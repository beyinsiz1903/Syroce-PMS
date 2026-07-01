"""
PMS Domain — Folio Repository
Data access layer for folios, charges, and payments. No FastAPI dependencies.
"""

from typing import Any

from core.tenant_db import LazyCollection


class FolioRepository:
    """MongoDB operations for folios."""

    collection = LazyCollection("folios")

    @classmethod
    async def find_by_tenant(
        cls,
        tenant_id: str,
        *,
        booking_id: str | None = None,
        guest_id: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {"tenant_id": tenant_id}
        if booking_id:
            query["booking_id"] = booking_id
        if guest_id:
            query["guest_id"] = guest_id
        if status:
            query["status"] = status

        cursor = cls.collection.find(query, {"_id": 0}).sort("created_at", -1).skip(offset).limit(limit)
        return await cursor.to_list(limit)

    @classmethod
    async def find_one(cls, tenant_id: str, folio_id: str) -> dict[str, Any] | None:
        return await cls.collection.find_one({"tenant_id": tenant_id, "id": folio_id}, {"_id": 0})

    @classmethod
    async def find_by_booking(cls, tenant_id: str, booking_id: str) -> dict[str, Any] | None:
        return await cls.collection.find_one({"tenant_id": tenant_id, "booking_id": booking_id}, {"_id": 0})

    @classmethod
    async def insert(cls, folio_dict: dict[str, Any]) -> None:
        await cls.collection.insert_one(folio_dict)

    @classmethod
    async def update(cls, tenant_id: str, folio_id: str, update_data: dict[str, Any]) -> bool:
        result = await cls.collection.update_one(
            {"tenant_id": tenant_id, "id": folio_id},
            {"$set": update_data},
        )
        return result.modified_count > 0

    @classmethod
    async def add_charge(cls, tenant_id: str, folio_id: str, charge: dict[str, Any]) -> bool:
        result = await cls.collection.update_one(
            {"tenant_id": tenant_id, "id": folio_id},
            {"$push": {"charges": charge}},
        )
        return result.modified_count > 0

    @classmethod
    async def add_payment(cls, tenant_id: str, folio_id: str, payment: dict[str, Any]) -> bool:
        result = await cls.collection.update_one(
            {"tenant_id": tenant_id, "id": folio_id},
            {"$push": {"payments": payment}},
        )
        return result.modified_count > 0


class ChargeRepository:
    """MongoDB operations for standalone charges."""

    collection = LazyCollection("charges")

    @classmethod
    async def find_by_folio(cls, tenant_id: str, folio_id: str) -> list[dict[str, Any]]:
        return await cls.collection.find({"tenant_id": tenant_id, "folio_id": folio_id}, {"_id": 0}).to_list(500)

    @classmethod
    async def insert(cls, charge_dict: dict[str, Any]) -> None:
        await cls.collection.insert_one(charge_dict)


class PaymentRepository:
    """MongoDB operations for payments."""

    collection = LazyCollection("payments")

    @classmethod
    async def find_by_folio(cls, tenant_id: str, folio_id: str) -> list[dict[str, Any]]:
        return await cls.collection.find({"tenant_id": tenant_id, "folio_id": folio_id}, {"_id": 0}).to_list(500)

    @classmethod
    async def insert(cls, payment_dict: dict[str, Any]) -> None:
        await cls.collection.insert_one(payment_dict)
