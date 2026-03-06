from typing import Any, Dict, List, Optional

from core.database import db
from core.utils import calculate_folio_balance


class FolioRepository:
    async def get_folio(self, tenant_id: str, folio_id: str) -> Optional[Dict[str, Any]]:
        return await db.folios.find_one({"id": folio_id, "tenant_id": tenant_id}, {"_id": 0})

    async def get_charges(self, tenant_id: str, folio_id: str) -> List[Dict[str, Any]]:
        return await db.folio_charges.find({"folio_id": folio_id, "tenant_id": tenant_id}, {"_id": 0}).to_list(1000)

    async def get_payments(self, tenant_id: str, folio_id: str) -> List[Dict[str, Any]]:
        return await db.payments.find({"folio_id": folio_id, "tenant_id": tenant_id}, {"_id": 0}).to_list(1000)

    async def get_balance(self, tenant_id: str, folio_id: str) -> float:
        return await calculate_folio_balance(folio_id, tenant_id)