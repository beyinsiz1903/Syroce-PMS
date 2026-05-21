"""Health Dashboard Router — Connector health metrics and scoring."""
import logging

from fastapi import APIRouter, Depends, HTTPException

from core.cache import cached
from core.security import get_current_user
from models.schemas import User

from ...application.connector_health_service import ConnectorHealthService

logger = logging.getLogger("channel_manager.routers.health_dashboard")

router = APIRouter(tags=["CM Health Dashboard"])


# Perf: N-connector × ~7 DB query seri await ≈ 4.7s ölçüldü
# (observability.middleware SLOW REQUEST). 30s tenant-scoped cache,
# admin paneli sekme değiştirme/refresh için yeterli tazelik;
# `cached` decorator zaten tenant-aware key türetir.
@router.get("/health-dashboard/connectors")
@cached(ttl=30, key_prefix="cm_health_dashboard_connectors")
async def get_all_connector_health(
    current_user: User = Depends(get_current_user),
):
    """Get health metrics for all connectors."""
    svc = ConnectorHealthService()
    return await svc.get_all_health(current_user.tenant_id)


@router.get("/health-dashboard/connectors/{connector_id}")
async def get_connector_health(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get detailed health metrics for a single connector."""
    svc = ConnectorHealthService()
    result = await svc.get_connector_health(current_user.tenant_id, connector_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/health-dashboard/properties/{property_id}")
async def get_property_health(
    property_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get health metrics for connectors of a specific property."""
    svc = ConnectorHealthService()
    return await svc.get_health_by_property(current_user.tenant_id, property_id)
