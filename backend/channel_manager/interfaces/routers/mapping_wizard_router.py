"""
Auto Room Mapping Wizard Router.

Endpoints:
  GET  /mapping-wizard/{connector_id}/suggest-rooms   — Auto-suggest room type mappings
  GET  /mapping-wizard/{connector_id}/suggest-rates   — Auto-suggest rate plan mappings
  POST /mapping-wizard/{connector_id}/bulk-create      — Bulk-create confirmed mappings
"""
import logging
from modules.pms_core.role_permission_service import require_op  # v96 DW

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.security import get_current_user
from models.schemas import User

from ...application.auto_mapping_service import AutoMappingService

logger = logging.getLogger("channel_manager.routers.mapping_wizard")

router = APIRouter(tags=["CM Mapping Wizard"])


class MappingPair(BaseModel):
    pms_entity_id: str
    pms_entity_name: str = ""
    external_entity_id: str
    external_entity_name: str = ""


class BulkCreateRequest(BaseModel):
    entity_type: str = "room_type"
    pairs: list[MappingPair] = Field(default_factory=list)


@router.post("/mapping-wizard/{connector_id}/fetch-external")
async def fetch_external_data(
    connector_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    """Fetch real room types and rate plans from the channel provider API."""
    svc = AutoMappingService()
    result = await svc.fetch_external_data_from_channel(current_user.tenant_id, connector_id)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error", "Veri cekilemedi"))
    return result


@router.get("/mapping-wizard/{connector_id}/suggest-rooms")
async def suggest_room_mappings(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    """Auto-suggest room type mappings using fuzzy name matching."""
    svc = AutoMappingService()
    result = await svc.suggest_room_mappings(current_user.tenant_id, connector_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/mapping-wizard/{connector_id}/suggest-rates")
async def suggest_rate_mappings(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    """Auto-suggest rate plan mappings using fuzzy name matching."""
    svc = AutoMappingService()
    result = await svc.suggest_rate_plan_mappings(current_user.tenant_id, connector_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/mapping-wizard/{connector_id}/bulk-create")
async def bulk_create_mappings(
    connector_id: str,
    req: BulkCreateRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v96 DW
):
    """Bulk-create mappings from confirmed wizard suggestions."""
    if not req.pairs:
        raise HTTPException(status_code=400, detail="En az bir eslestirme cifti gerekli")

    svc = AutoMappingService()
    result = await svc.bulk_create_mappings(
        tenant_id=current_user.tenant_id,
        connector_id=connector_id,
        entity_type=req.entity_type,
        pairs=[p.model_dump() for p in req.pairs],
        actor_id=current_user.id,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result
