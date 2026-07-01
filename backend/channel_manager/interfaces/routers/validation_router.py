"""
Enhanced Sandbox Validation Router + Mapping Completeness + Rate Push Tracking +
Health Trend Analytics + WebSocket endpoints.
"""

import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect

from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v101 DW

from ...application.health_trend_service import HealthTrendService
from ...application.mapping_completeness_service import MappingCompletenessService
from ...application.rate_push_tracking_service import RatePushTrackingService
from ...application.realtime_service import ws_manager
from ...application.sandbox_validation_service import SandboxValidationService

logger = logging.getLogger("channel_manager.routers.validation")

router = APIRouter(tags=["CM Validation & Analytics"])


# ─── Enhanced Sandbox Validation ──────────────────────────────────────


@router.post("/validation/sandbox/{connector_id}")
async def run_sandbox_validation(
    connector_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    """Run full HotelRunner sandbox validation and produce integration readiness report."""
    svc = SandboxValidationService()
    return await svc.run_validation(
        current_user.tenant_id,
        connector_id,
        actor_id=current_user.id,
    )


# ─── Mapping Completeness ────────────────────────────────────────────


@router.get("/mapping-completeness/{connector_id}")
async def get_mapping_completeness(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get mapping completeness validation report."""
    svc = MappingCompletenessService()
    return await svc.validate_completeness(current_user.tenant_id, connector_id)


@router.get("/mapping-completeness/{connector_id}/sync-gate")
async def check_sync_gate(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    """Quick check if sync is allowed for this connector."""
    svc = MappingCompletenessService()
    return await svc.check_sync_gate(current_user.tenant_id, connector_id)


@router.get("/mapping-completeness/{connector_id}/import-gate")
async def check_import_gate(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    """Quick check if reservation import should proceed."""
    svc = MappingCompletenessService()
    return await svc.check_import_gate(current_user.tenant_id, connector_id)


# ─── Rate Push Tracking ─────────────────────────────────────────────


@router.get("/rate-push-metrics/{connector_id}")
async def get_rate_push_metrics(
    connector_id: str,
    days: int = Query(default=7, ge=1, le=90),
    current_user: User = Depends(get_current_user),
):
    """Get rate push success tracking metrics."""
    svc = RatePushTrackingService()
    return await svc.get_metrics(current_user.tenant_id, connector_id, days)


# ─── Health Trend Analytics ──────────────────────────────────────────


@router.get("/health-trend/{connector_id}/daily")
async def get_daily_health_trend(
    connector_id: str,
    days: int = Query(default=30, ge=1, le=90),
    current_user: User = Depends(get_current_user),
):
    """Get daily health score trend for a connector."""
    svc = HealthTrendService()
    return await svc.get_daily_trend(current_user.tenant_id, connector_id, days)


@router.get("/health-trend/{connector_id}/weekly")
async def get_weekly_health_trend(
    connector_id: str,
    weeks: int = Query(default=12, ge=1, le=52),
    current_user: User = Depends(get_current_user),
):
    """Get weekly health score trend for a connector."""
    svc = HealthTrendService()
    return await svc.get_weekly_trend(current_user.tenant_id, connector_id, weeks)


@router.get("/health-trend/{connector_id}/summary")
async def get_health_trend_summary(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get trend summary comparing recent vs previous period."""
    svc = HealthTrendService()
    return await svc.get_trend_summary(current_user.tenant_id, connector_id)


# ─── WebSocket Endpoint ─────────────────────────────────────────────


@router.websocket("/ws/admin-updates")
async def websocket_admin_updates(websocket: WebSocket):
    """WebSocket endpoint for real-time admin dashboard updates."""
    # Extract tenant_id from query params
    tenant_id = websocket.query_params.get("tenant_id", "")
    if not tenant_id:
        await websocket.close(code=4001, reason="tenant_id required")
        return

    await ws_manager.connect(websocket, tenant_id)
    try:
        while True:
            # Keep alive - client can send pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"type":"pong"}')
    except WebSocketDisconnect:
        await ws_manager.disconnect(websocket, tenant_id)
    except Exception:
        await ws_manager.disconnect(websocket, tenant_id)
