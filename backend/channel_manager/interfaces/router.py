"""
Channel Manager API Router - RESTful interface for the channel manager module.
Replaces legacy mock endpoints in server.py with production-grade implementations.

All routes are prefixed with /api/channel-manager/v2/ to coexist with legacy endpoints.
"""
import logging
from typing import Optional, List
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from pydantic import BaseModel, Field

from core.security import get_current_user
from models.schemas import User

from ..application.connector_service import ConnectorService
from ..application.mapping_service import MappingService
from ..application.inventory_sync_service import InventorySyncService
from ..application.reservation_import_service import ReservationImportService
from ..application.reconciliation_service import ReconciliationService
from ..application.observability_service import ObservabilityService

logger = logging.getLogger("channel_manager.interfaces.router")

router = APIRouter(prefix="/api/channel-manager/v2", tags=["Channel Manager v2"])

# ─── Request/Response Models ──────────────────────────────────────────

class CreateConnectorRequest(BaseModel):
    provider: str = "hotelrunner"
    display_name: str
    property_id: str = ""
    credentials: dict = Field(default_factory=dict)
    sync_config: Optional[dict] = None

class UpdateCredentialsRequest(BaseModel):
    credentials: dict

class CreateMappingRequest(BaseModel):
    connector_id: str
    entity_type: str  # room_type, rate_plan
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

class TriggerImportRequest(BaseModel):
    connector_id: str
    date_start: Optional[str] = None
    date_end: Optional[str] = None

class ApproveReviewRequest(BaseModel):
    reservation_id: str
    room_type_override: Optional[str] = None

class ResolveIssueRequest(BaseModel):
    resolution: str

# ─── Connector Endpoints ──────────────────────────────────────────────

@router.get("/connectors")
async def list_connectors(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    svc = ConnectorService()
    connectors = await svc.list_connectors(current_user.tenant_id, status)
    return {"connectors": connectors, "count": len(connectors)}

@router.post("/connectors")
async def create_connector(
    req: CreateConnectorRequest,
    current_user: User = Depends(get_current_user),
):
    svc = ConnectorService()
    property_id = req.property_id or getattr(current_user, "property_id", "")
    try:
        result = await svc.create_connector(
            tenant_id=current_user.tenant_id,
            property_id=property_id,
            provider=req.provider,
            display_name=req.display_name,
            credentials=req.credentials,
            actor_id=current_user.id,
            sync_config=req.sync_config,
        )
        return {"message": "Connector created", "connector": result}
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

@router.get("/connectors/{connector_id}")
async def get_connector(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ConnectorService()
    connector = await svc.get_connector(current_user.tenant_id, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    # Mask credentials in response
    if "credentials" in connector:
        connector["credentials"] = {k: "***" for k in connector["credentials"]}
    return connector

@router.post("/connectors/{connector_id}/test")
async def test_connector(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ConnectorService()
    result = await svc.test_connection(current_user.tenant_id, connector_id)
    return result

@router.post("/connectors/{connector_id}/activate")
async def activate_connector(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ConnectorService()
    result = await svc.activate_connector(current_user.tenant_id, connector_id, current_user.id)
    return {"message": "Connector activated", "connector": result}

@router.post("/connectors/{connector_id}/pause")
async def pause_connector(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ConnectorService()
    result = await svc.pause_connector(current_user.tenant_id, connector_id, current_user.id)
    return {"message": "Connector paused", "connector": result}

@router.put("/connectors/{connector_id}/credentials")
async def update_credentials(
    connector_id: str,
    req: UpdateCredentialsRequest,
    current_user: User = Depends(get_current_user),
):
    svc = ConnectorService()
    await svc.update_credentials(
        current_user.tenant_id, connector_id, req.credentials, current_user.id,
    )
    return {"message": "Credentials updated"}

@router.delete("/connectors/{connector_id}")
async def delete_connector(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ConnectorService()
    deleted = await svc.delete_connector(current_user.tenant_id, connector_id, current_user.id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Connector not found")
    return {"message": "Connector deleted"}

# ─── Mapping Endpoints ────────────────────────────────────────────────

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
    # Resolve property_id from connector
    connector_svc = ConnectorService()
    connector = await connector_svc.get_connector(current_user.tenant_id, req.connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

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

@router.get("/mappings/{connector_id}/sync-readiness")
async def check_sync_readiness(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = MappingService()
    return await svc.check_sync_readiness(current_user.tenant_id, connector_id)

# ─── Inventory Sync Endpoints ────────────────────────────────────────

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
    from ..infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    jobs = await repo.get_sync_jobs(current_user.tenant_id, connector_id, limit)
    return {"jobs": jobs, "count": len(jobs)}

@router.get("/sync/jobs/{job_id}")
async def get_sync_job(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    from ..infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    job = await repo.get_sync_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Sync job not found")
    events = await repo.get_sync_events(job_id)
    return {"job": job, "events": events}

# ─── Reservation Import Endpoints ────────────────────────────────────

@router.post("/reservations/pull")
async def trigger_reservation_pull(
    req: TriggerImportRequest,
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    result = await svc.pull_and_import(
        tenant_id=current_user.tenant_id,
        connector_id=req.connector_id,
        date_start=req.date_start,
        date_end=req.date_end,
        triggered_by="user",
    )
    return result

@router.get("/reservations/imported")
async def list_imported_reservations(
    connector_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    reservations = await svc.get_imported_reservations(
        current_user.tenant_id, connector_id, status, limit,
    )
    return {"reservations": reservations, "count": len(reservations)}

@router.get("/reservations/review-queue")
async def get_review_queue(
    connector_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    queue = await svc.get_review_queue(current_user.tenant_id, connector_id)
    return {"queue": queue, "count": len(queue)}

@router.post("/reservations/approve")
async def approve_review(
    req: ApproveReviewRequest,
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    result = await svc.approve_review(
        current_user.tenant_id, req.reservation_id,
        current_user.id, req.room_type_override,
    )
    return result

@router.get("/reservations/batches")
async def list_import_batches(
    connector_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    batches = await svc.get_import_batches(current_user.tenant_id, connector_id)
    return {"batches": batches, "count": len(batches)}

# ─── Reconciliation Endpoints ────────────────────────────────────────

@router.post("/reconciliation/run")
async def run_reconciliation(
    connector_id: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user),
):
    svc = ReconciliationService()
    result = await svc.run_reconciliation(current_user.tenant_id, connector_id, current_user.id)
    return result

@router.get("/reconciliation/issues")
async def list_reconciliation_issues(
    connector_id: Optional[str] = None,
    status: str = Query("open"),
    current_user: User = Depends(get_current_user),
):
    svc = ReconciliationService()
    issues = await svc.get_issues(current_user.tenant_id, connector_id, status)
    return {"issues": issues, "count": len(issues)}

@router.post("/reconciliation/issues/{issue_id}/resolve")
async def resolve_issue(
    issue_id: str,
    req: ResolveIssueRequest,
    current_user: User = Depends(get_current_user),
):
    svc = ReconciliationService()
    return await svc.resolve_issue(current_user.tenant_id, issue_id, req.resolution, current_user.id)

@router.post("/reconciliation/issues/{issue_id}/dismiss")
async def dismiss_issue(
    issue_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ReconciliationService()
    return await svc.dismiss_issue(current_user.tenant_id, issue_id, current_user.id)

# ─── Observability Endpoints ─────────────────────────────────────────

@router.get("/dashboard")
async def get_dashboard(
    current_user: User = Depends(get_current_user),
):
    svc = ObservabilityService()
    return await svc.get_dashboard_overview(current_user.tenant_id)

@router.get("/health/{connector_id}")
async def get_connector_health(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ObservabilityService()
    return await svc.get_connector_health(current_user.tenant_id, connector_id)

@router.get("/audit")
async def get_audit_log(
    connector_id: Optional[str] = None,
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    from ..infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    logs = await repo.get_audit_logs(current_user.tenant_id, connector_id, limit)
    return {"logs": logs, "count": len(logs)}
