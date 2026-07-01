"""
Semantic Layer — Stays (ADR read model)

External-consumer read API for stay (reservation) projections.
Exposes a unified view combining reservation + guest + room + folios.
Intended for BI/SDK/partner integrations; main UI continues to use
domain-specific endpoints under /api/pms.
"""

from fastapi import APIRouter, Depends, HTTPException

from core.security import get_current_user
from modules.stays.schemas import StayDetailProjection
from modules.stays.services.stay_read_service import StayReadService

router = APIRouter(prefix="/api/semantic/stays", tags=["semantic-stays"])

_service = StayReadService()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "module": "semantic-stays", "version": "1.0"}


@router.get("/{stay_id}", response_model=StayDetailProjection)
async def get_stay_detail(stay_id: str, current_user=Depends(get_current_user)):
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    return await _service.get_stay_detail(tenant_id, stay_id)
