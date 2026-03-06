from typing import Any, Dict, Optional

from fastapi import HTTPException

from modules.folio.repository import FolioRepository


class FolioBalanceReadService:
    def __init__(self, repository: Optional[FolioRepository] = None):
        self.repository = repository or FolioRepository()

    async def get_folio_details(self, tenant_id: str, folio_id: str) -> Dict[str, Any]:
        folio = await self.repository.get_folio(tenant_id, folio_id)
        if not folio:
            raise HTTPException(status_code=404, detail="Folio not found")

        charges = await self.repository.get_charges(tenant_id, folio_id)
        payments = await self.repository.get_payments(tenant_id, folio_id)
        balance = await self.repository.get_balance(tenant_id, folio_id)
        folio["balance"] = balance

        return {
            "folio": folio,
            "charges": charges,
            "payments": payments,
            "balance": balance,
        }