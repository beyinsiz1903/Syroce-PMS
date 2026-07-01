"""
Semantic Layer — Inventory (ADR read model)

External-consumer read API for room inventory & availability.
Wraps AvailabilityReadService for BI/SDK/partner integrations; main UI
continues to use domain-specific endpoints under /api/pms and
/api/channel-manager.
"""

from fastapi import APIRouter, Depends, HTTPException, Query

from core.security import get_current_user
from modules.inventory.services.availability_read_service import AvailabilityReadService

router = APIRouter(prefix="/api/semantic/inventory", tags=["semantic-inventory"])

_availability = AvailabilityReadService()


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "module": "semantic-inventory", "version": "1.0"}


@router.get("/availability")
async def get_availability(
    check_in: str = Query(..., description="YYYY-MM-DD"),
    check_out: str = Query(..., description="YYYY-MM-DD"),
    room_type: str | None = Query(None),
    current_user=Depends(get_current_user),
):
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    rooms = await _availability.get_availability(tenant_id, check_in, check_out, room_type)
    return {"check_in": check_in, "check_out": check_out, "rooms": rooms, "count": len(rooms)}
