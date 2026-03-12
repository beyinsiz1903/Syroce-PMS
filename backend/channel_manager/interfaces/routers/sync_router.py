"""Inventory/rate sync, mapping, event-driven sync, scheduler, provider push endpoints."""
import logging
from typing import Optional, List
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.security import get_current_user
from models.schemas import User

from ...application.connector_service import ConnectorService
from ...application.mapping_service import MappingService
from ...application.inventory_sync_service import InventorySyncService
from ...application.scheduler_service import SchedulerService
from ...application.event_sync_service import EventSyncService
from ...application.provider_adapters import InventoryProviderAdapter, RateProviderAdapter

logger = logging.getLogger("channel_manager.routers.sync")

router = APIRouter(tags=["CM Sync"])


class CreateMappingRequest(BaseModel):
    connector_id: str
    entity_type: str
    pms_entity_id: str
    pms_entity_name: str = ""
    external_entity_id: str
    external_entity_name: str = ""
    extras: Optional[dict] = None


class TriggerSyncRequest(BaseModel):
    connector_id: str
    date_start: str = ""
    date_end: str = ""
    room_type_ids: Optional[List[str]] = None
    rate_plan_ids: Optional[List[str]] = None
    reason: str = ""


class DomainEventRequest(BaseModel):
    event_type: str
    payload: dict = Field(default_factory=dict)


class BatchEventsRequest(BaseModel):
    events: List[DomainEventRequest]


class ProviderPushRequest(BaseModel):
    connector_id: str
    updates: List[dict]
    environment: str = "sandbox"


# ─── Mapping Endpoints ────────────────────────────────────────────

@router.get("/mappings/{connector_id}")
async def list_mappings(
    connector_id: str,
    entity_type: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    svc = MappingService()
    mappings = await svc.list_mappings(current_user.tenant_id, connector_id, entity_type)
    return {"mappings": mappings, "count": len(mappings)}


@router.post("/mappings")
async def create_mapping(
    req: CreateMappingRequest,
    current_user: User = Depends(get_current_user),
):
    svc = MappingService()
    connector_svc = ConnectorService()
    connector = await connector_svc.get_connector(current_user.tenant_id, req.connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    try:
        result = await svc.create_mapping(
            tenant_id=current_user.tenant_id,
            property_id=connector.get("property_id", ""),
            connector_id=req.connector_id,
            entity_type=req.entity_type,
            pms_entity_id=req.pms_entity_id,
            pms_entity_name=req.pms_entity_name,
            external_entity_id=req.external_entity_id,
            external_entity_name=req.external_entity_name,
            actor_id=current_user.id,
            extras=req.extras,
        )
        return {"message": "Mapping created", "mapping": result}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@router.delete("/mappings/{mapping_id}")
async def delete_mapping(
    mapping_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = MappingService()
    deleted = await svc.delete_mapping(current_user.tenant_id, mapping_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Mapping not found")
    return {"message": "Mapping deleted"}


@router.post("/mappings/{connector_id}/validate")
async def validate_mappings(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = MappingService()
    result = await svc.validate_mappings(current_user.tenant_id, connector_id)
    return result


@router.post("/mappings/{connector_id}/validate/{mapping_id}")
async def validate_single_mapping(
    connector_id: str,
    mapping_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = MappingService()
    try:
        result = await svc.validate_single(current_user.tenant_id, mapping_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/mappings/{connector_id}/sync-readiness")
async def check_sync_readiness(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = MappingService()
    return await svc.check_sync_readiness(current_user.tenant_id, connector_id)


@router.get("/mappings/{connector_id}/readiness-report")
async def get_readiness_report(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = MappingService()
    return await svc.get_readiness_report(current_user.tenant_id, connector_id)


# ─── Inventory Sync ──────────────────────────────────────────────

@router.post("/sync/inventory")
async def trigger_inventory_sync(
    req: TriggerSyncRequest,
    current_user: User = Depends(get_current_user),
):
    svc = InventorySyncService()
    if not req.date_start:
        req.date_start = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not req.date_end:
        req.date_end = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
    result = await svc.trigger_inventory_sync(
        tenant_id=current_user.tenant_id,
        connector_id=req.connector_id,
        date_start=req.date_start,
        date_end=req.date_end,
        room_type_ids=req.room_type_ids,
        triggered_by="user",
        trigger_reason=req.reason or "Manual inventory sync",
        actor_id=current_user.id,
    )
    return result


@router.post("/sync/rates")
async def trigger_rate_sync(
    req: TriggerSyncRequest,
    current_user: User = Depends(get_current_user),
):
    svc = InventorySyncService()
    if not req.date_start:
        req.date_start = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if not req.date_end:
        req.date_end = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d")
    result = await svc.trigger_rate_sync(
        tenant_id=current_user.tenant_id,
        connector_id=req.connector_id,
        date_start=req.date_start,
        date_end=req.date_end,
        rate_plan_ids=req.rate_plan_ids,
        triggered_by="user",
        actor_id=current_user.id,
    )
    return result


@router.get("/sync/jobs")
async def list_sync_jobs(
    connector_id: Optional[str] = None,
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
):
    from ...infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    jobs = await repo.get_sync_jobs(current_user.tenant_id, connector_id, limit)
    return {"jobs": jobs, "count": len(jobs)}


@router.get("/sync/jobs/{job_id}")
async def get_sync_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    from ...infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    job = await repo.get_sync_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Sync job not found")
    events = await repo.get_sync_events(job_id)
    return {"job": job, "events": events, "event_count": len(events)}


@router.get("/sync/jobs/{job_id}/events")
async def get_sync_job_events(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    from ...infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    job = await repo.get_sync_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Sync job not found")
    events = await repo.get_sync_events(job_id, limit=500)
    return {"events": events, "count": len(events)}


@router.get("/sync/manual-review")
async def get_manual_review_queue(
    connector_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    svc = InventorySyncService()
    queue = await svc.get_manual_review_queue(current_user.tenant_id, connector_id)
    return {"queue": queue, "count": len(queue)}


@router.post("/sync/manual-review/{job_id}/retry")
async def retry_manual_review_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = InventorySyncService()
    try:
        result = await svc.retry_failed_job(current_user.tenant_id, job_id, current_user.id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/sync/manual-review/{job_id}/dismiss")
async def dismiss_manual_review_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = InventorySyncService()
    try:
        result = await svc.dismiss_manual_review(current_user.tenant_id, job_id, current_user.id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Scheduler ────────────────────────────────────────────────────

@router.post("/scheduler/run/{connector_id}")
async def run_scheduled_check(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = SchedulerService()
    try:
        result = await svc.run_scheduled_check(
            current_user.tenant_id, connector_id, current_user.id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/scheduler/run-all")
async def run_all_scheduled_checks(
    current_user: User = Depends(get_current_user),
):
    svc = SchedulerService()
    return await svc.run_all_connectors(current_user.tenant_id)


# ─── Event-Driven Sync ───────────────────────────────────────────

@router.post("/events/sync")
async def trigger_event_sync(
    req: DomainEventRequest,
    current_user: User = Depends(get_current_user),
):
    svc = EventSyncService()
    result = await svc.handle_event(
        current_user.tenant_id, req.event_type, req.payload,
    )
    return result


@router.post("/events/sync/batch")
async def trigger_batch_event_sync(
    req: BatchEventsRequest,
    current_user: User = Depends(get_current_user),
):
    svc = EventSyncService()
    events = [{"event_type": e.event_type, "payload": e.payload} for e in req.events]
    return await svc.handle_batch_events(current_user.tenant_id, events)


# ─── Provider Adapters ────────────────────────────────────────────

@router.post("/providers/inventory/push")
async def push_inventory_via_adapter(
    req: ProviderPushRequest,
    current_user: User = Depends(get_current_user),
):
    connector_svc = ConnectorService()
    connector = await connector_svc.get_connector(current_user.tenant_id, req.connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    adapter = InventoryProviderAdapter()
    return await adapter.push(
        tenant_id=current_user.tenant_id,
        connector_id=req.connector_id,
        property_id=connector.get("property_id", ""),
        updates=req.updates,
        credentials=connector.get("credentials", {}),
        environment=req.environment,
    )


@router.post("/providers/rates/push")
async def push_rates_via_adapter(
    req: ProviderPushRequest,
    current_user: User = Depends(get_current_user),
):
    connector_svc = ConnectorService()
    connector = await connector_svc.get_connector(current_user.tenant_id, req.connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    adapter = RateProviderAdapter()
    return await adapter.push(
        tenant_id=current_user.tenant_id,
        connector_id=req.connector_id,
        property_id=connector.get("property_id", ""),
        updates=req.updates,
        credentials=connector.get("credentials", {}),
        environment=req.environment,
    )
