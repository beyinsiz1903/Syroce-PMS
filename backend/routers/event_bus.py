"""
Event Bus Router - API endpoints for event bus management and monitoring.
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional, List

from core.security import get_current_user
from shared_kernel.tenancy_context import get_current_tenant, TenantContext

from modules.event_bus.abstraction import event_bus
from modules.event_bus.event_replay import replay_service

router = APIRouter(prefix="/api/event-bus", tags=["event-bus"])


@router.get("/status")
async def get_bus_status(tenant: TenantContext = Depends(get_current_tenant)):
    return await event_bus.get_status()


@router.get("/channels")
async def get_channels(tenant: TenantContext = Depends(get_current_tenant)):
    return event_bus.get_channels(tenant.tenant_id)


@router.get("/metrics")
async def get_bus_metrics(tenant: TenantContext = Depends(get_current_tenant)):
    return await event_bus.get_metrics()


@router.get("/sessions")
async def get_active_sessions(tenant: TenantContext = Depends(get_current_tenant)):
    return event_bus.get_active_sessions(tenant.tenant_id)


@router.post("/publish")
async def publish_event(
    event_type: str = Query(...),
    priority: str = Query("normal"),
    property_id: Optional[str] = None,
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await event_bus.publish(
        tenant_id=tenant.tenant_id,
        event_type=event_type,
        payload={"source": "api", "triggered_by": tenant.user_id},
        property_id=property_id,
        source="api",
        priority=priority,
    )


@router.get("/replay")
async def replay_events(
    since: Optional[str] = None,
    event_types: Optional[str] = None,
    limit: int = Query(50, le=200),
    tenant: TenantContext = Depends(get_current_tenant),
):
    types = event_types.split(",") if event_types else None
    return await event_bus.replay(tenant.tenant_id, since, types, limit)


@router.get("/replay/summary")
async def get_replay_summary(tenant: TenantContext = Depends(get_current_tenant)):
    return await replay_service.get_replay_summary(tenant.tenant_id)


@router.post("/sessions/register")
async def register_session(
    session_id: str = Query(...),
    roles: str = Query("admin"),
    tenant: TenantContext = Depends(get_current_tenant),
):
    role_list = roles.split(",")
    return event_bus.register_session(
        tenant.tenant_id, session_id,
        tenant.user_id or "anonymous", role_list,
    )


@router.delete("/sessions/{session_id}")
async def unregister_session(
    session_id: str,
    tenant: TenantContext = Depends(get_current_tenant),
):
    event_bus.unregister_session(tenant.tenant_id, session_id)
    return {"session_id": session_id, "status": "unregistered"}
