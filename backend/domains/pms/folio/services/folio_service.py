"""
PMS Domain — Folio Service
Business logic for folio, charge, and payment operations. No FastAPI dependencies.
"""
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from domains.pms.folio.repositories.folio_repository import (
    FolioRepository,
)


async def generate_folio_number(tenant_id: str) -> str:
    """Generate sequential folio number for a tenant."""
    from core.database import db
    counter = await db.counters.find_one_and_update(
        {"tenant_id": tenant_id, "type": "folio"},
        {"$inc": {"seq": 1}},
        upsert=True,
        return_document=True,
        projection={"_id": 0},
    )
    seq = counter.get("seq", 1) if counter else 1
    return f"F-{seq:06d}"


class FolioService:
    """Pure business logic for folio management."""

    @staticmethod
    async def get_folios(
        tenant_id: str, *, booking_id: Optional[str] = None,
        guest_id: Optional[str] = None, status: Optional[str] = None,
        limit: int = 50, offset: int = 0,
    ) -> List[Dict[str, Any]]:
        return await FolioRepository.find_by_tenant(
            tenant_id, booking_id=booking_id, guest_id=guest_id,
            status=status, limit=limit, offset=offset,
        )

    @staticmethod
    async def get_folio(tenant_id: str, folio_id: str) -> Optional[Dict[str, Any]]:
        return await FolioRepository.find_one(tenant_id, folio_id)

    @staticmethod
    async def create_folio(
        tenant_id: str, booking_id: str, guest_id: str,
        folio_type: str = "guest",
    ) -> Dict[str, Any]:
        folio_number = await generate_folio_number(tenant_id)
        folio = {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "guest_id": guest_id,
            "folio_number": folio_number,
            "folio_type": folio_type,
            "status": "open",
            "charges": [],
            "payments": [],
            "balance": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await FolioRepository.insert(folio)
        return folio

    @staticmethod
    async def post_charge(
        tenant_id: str, folio_id: str, charge_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        folio = await FolioRepository.find_one(tenant_id, folio_id)
        if not folio:
            raise ValueError("Folio not found")
        if folio.get("status") == "closed":
            raise ValueError("Cannot post charge to a closed folio")

        charge = {
            "id": str(uuid.uuid4()),
            "folio_id": folio_id,
            **charge_data,
            "posted_at": datetime.now(timezone.utc).isoformat(),
        }
        await FolioRepository.add_charge(tenant_id, folio_id, charge)

        # Update balance
        new_balance = folio.get("balance", 0) + charge_data.get("amount", 0)
        await FolioRepository.update(tenant_id, folio_id, {"balance": new_balance})

        return charge

    @staticmethod
    async def post_payment(
        tenant_id: str, folio_id: str, payment_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        folio = await FolioRepository.find_one(tenant_id, folio_id)
        if not folio:
            raise ValueError("Folio not found")

        payment = {
            "id": str(uuid.uuid4()),
            "folio_id": folio_id,
            **payment_data,
            "posted_at": datetime.now(timezone.utc).isoformat(),
        }
        await FolioRepository.add_payment(tenant_id, folio_id, payment)

        # Update balance
        new_balance = folio.get("balance", 0) - payment_data.get("amount", 0)
        await FolioRepository.update(tenant_id, folio_id, {"balance": new_balance})

        return payment

    @staticmethod
    async def close_folio(tenant_id: str, folio_id: str) -> bool:
        folio = await FolioRepository.find_one(tenant_id, folio_id)
        if not folio:
            raise ValueError("Folio not found")
        if abs(folio.get("balance", 0)) > 0.01:
            raise ValueError(f"Cannot close folio with outstanding balance: {folio.get('balance')}")

        return await FolioRepository.update(tenant_id, folio_id, {
            "status": "closed",
            "closed_at": datetime.now(timezone.utc).isoformat(),
        })
