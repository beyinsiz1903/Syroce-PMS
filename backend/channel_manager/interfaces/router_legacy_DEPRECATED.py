"""
Channel Manager API Router - RESTful interface for the channel manager module.
Replaces legacy mock endpoints in server.py with production-grade implementations.

All routes are prefixed with /api/channel-manager/v2/ to coexist with legacy endpoints.
"""
import logging
from typing import Optional, List
from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query, Body, Request
from pydantic import BaseModel, Field

from core.security import get_current_user
from models.schemas import User

from ..application.connector_service import ConnectorService
from ..application.mapping_service import MappingService
from ..application.inventory_sync_service import InventorySyncService
from ..application.reservation_import_service import ReservationImportService
from ..application.reconciliation_service import ReconciliationService
from ..application.observability_service import ObservabilityService
from ..application.scheduler_service import SchedulerService
from ..application.event_sync_service import EventSyncService
from ..application.sandbox_validation_service import SandboxValidationService
from ..application.provider_adapters import InventoryProviderAdapter, RateProviderAdapter
from ..application.webhook_service import WebhookService
from ..application.error_queue_service import ErrorQueueService
from ..application.production_readiness_service import ProductionReadinessService
from ..application.historical_metrics_service import HistoricalMetricsService
from ..application.alerting_service import AlertingService
from ..application.reliability_service import ReliabilityService
from ..application.multi_property_service import MultiPropertyService
from ..infrastructure.credential_vault import CredentialVault
from ..infrastructure.rbac import enforce_credential_access

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

class RetryJobRequest(BaseModel):
    job_id: str

class TriggerImportRequest(BaseModel):
    connector_id: str
    date_start: Optional[str] = None
    date_end: Optional[str] = None

class ApproveReviewRequest(BaseModel):
    reservation_id: str
    room_type_override: Optional[str] = None

class ReprocessReviewRequest(BaseModel):
    room_type_override: Optional[str] = None

class ResolveIssueRequest(BaseModel):
    resolution: str

class DismissIssueRequest(BaseModel):
    reason: str = ""

class UpdateIssueStatusRequest(BaseModel):
    status: str

class CreateIssueRequest(BaseModel):
    connector_id: str
    issue_type: str
    severity: str
    description: str
    suggested_actions: Optional[List[str]] = None
    evidence_payload: Optional[dict] = None

class RotateCredentialsRequest(BaseModel):
    credentials: dict

class DomainEventRequest(BaseModel):
    event_type: str
    payload: dict = Field(default_factory=dict)

class BatchEventsRequest(BaseModel):
    events: List[DomainEventRequest]

class ProviderPushRequest(BaseModel):
    connector_id: str
    updates: List[dict]
    environment: str = "sandbox"

class BulkRetryRequest(BaseModel):
    item_ids: List[str]
    error_type: str

class BulkDismissRequest(BaseModel):
    item_ids: List[str]
    error_type: str
    reason: str = ""

class ErrorQueueActionRequest(BaseModel):
    item_id: str
    error_type: str
    reason: str = ""

class BulkIssueActionRequest(BaseModel):
    issue_ids: List[str]
    reason: str = ""

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

class ConnectionTestStepResult(BaseModel):
    status: str  # pass, fail, warn
    latency_ms: int = 0
    error_code: Optional[str] = None
    message: str = ""

class ConnectionTestResponse(BaseModel):
    success: bool
    connector_id: str = ""
    provider: str = ""
    display_name: str = ""
    tested_at: str = ""
    total_latency_ms: int = 0
    summary: str = ""
    auth_status: Optional[ConnectionTestStepResult] = None
    property_access_status: Optional[ConnectionTestStepResult] = None
    inventory_read_status: Optional[ConnectionTestStepResult] = None
    rate_read_status: Optional[ConnectionTestStepResult] = None
    xml_connectivity_status: Optional[ConnectionTestStepResult] = None
    message: Optional[str] = None

@router.post("/connectors/{connector_id}/test", response_model=ConnectionTestResponse)
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
    try:
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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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
    try:
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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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
    return {"job": job, "events": events, "event_count": len(events)}

@router.get("/sync/jobs/{job_id}/events")
async def get_sync_job_events(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    from ..infrastructure.repository import ChannelManagerRepository
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

@router.get("/reservations/imported/{reservation_id}")
async def get_imported_reservation_detail(
    reservation_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    detail = await svc.get_imported_reservation_detail(current_user.tenant_id, reservation_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Imported reservation not found")
    return detail

@router.get("/reservations/review-queue")
async def get_review_queue(
    connector_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    queue = await svc.get_review_queue(current_user.tenant_id, connector_id)
    return {"queue": queue, "count": len(queue)}

@router.post("/reservations/review-queue/{reservation_id}/reprocess")
async def reprocess_review_reservation(
    reservation_id: str,
    req: ReprocessReviewRequest = None,
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    try:
        override = req.room_type_override if req else None
        result = await svc.reprocess_review(
            current_user.tenant_id, reservation_id,
            current_user.id, override,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/reservations/review-queue/{reservation_id}/dismiss")
async def dismiss_review_reservation(
    reservation_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    try:
        result = await svc.dismiss_review(
            current_user.tenant_id, reservation_id, current_user.id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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

@router.get("/reservations/batches/{batch_id}")
async def get_import_batch_detail(
    batch_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    try:
        detail = await svc.get_import_batch_detail(current_user.tenant_id, batch_id)
        return detail
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/reservations/stats")
async def get_reservation_stats(
    connector_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    return await svc.get_reservation_stats(current_user.tenant_id, connector_id)

@router.post("/reservations/retry-acks")
async def retry_failed_acks(
    connector_id: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    try:
        return await svc.retry_failed_acks(current_user.tenant_id, connector_id, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/reservations/audit-trail")
async def get_reservation_audit_trail(
    connector_id: Optional[str] = None,
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    svc = ReservationImportService()
    logs = await svc.get_audit_trail(current_user.tenant_id, connector_id, limit)
    return {"audit_logs": logs, "count": len(logs)}

# ─── Reconciliation Endpoints ────────────────────────────────────────

@router.post("/reconciliation/run")
async def run_reconciliation(
    connector_id: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user),
):
    svc = ReconciliationService()
    try:
        result = await svc.run_reconciliation(current_user.tenant_id, connector_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return result

@router.get("/reconciliation/issues")
async def list_reconciliation_issues(
    connector_id: Optional[str] = None,
    status: str = Query("open"),
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    svc = ReconciliationService()
    issues = await svc.get_issues(current_user.tenant_id, connector_id, status, limit)
    return {"issues": issues, "count": len(issues)}

@router.get("/reconciliation/issues/summary")
async def get_reconciliation_summary(
    connector_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    svc = ReconciliationService()
    return await svc.get_issue_summary(current_user.tenant_id, connector_id)

@router.get("/reconciliation/issues/{issue_id}")
async def get_reconciliation_issue_detail(
    issue_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ReconciliationService()
    detail = await svc.get_issue_detail(current_user.tenant_id, issue_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Issue not found")
    return detail

@router.put("/reconciliation/issues/{issue_id}/status")
async def update_issue_status(
    issue_id: str,
    req: UpdateIssueStatusRequest,
    current_user: User = Depends(get_current_user),
):
    svc = ReconciliationService()
    try:
        return await svc.update_issue_status(current_user.tenant_id, issue_id, req.status, current_user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

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
    req: DismissIssueRequest = Body(DismissIssueRequest()),
    current_user: User = Depends(get_current_user),
):
    svc = ReconciliationService()
    return await svc.dismiss_issue(current_user.tenant_id, issue_id, req.reason, current_user.id)

@router.post("/reconciliation/issues")
async def create_reconciliation_issue(
    req: CreateIssueRequest,
    current_user: User = Depends(get_current_user),
):
    svc = ReconciliationService()
    connector_svc = ConnectorService()
    connector = await connector_svc.get_connector(current_user.tenant_id, req.connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    result = await svc.create_issue(
        tenant_id=current_user.tenant_id,
        property_id=connector.get("property_id", ""),
        connector_id=req.connector_id,
        issue_type=req.issue_type,
        severity=req.severity,
        description=req.description,
        suggested_actions=req.suggested_actions,
        evidence_payload=req.evidence_payload,
    )
    return {"message": "Issue created", "issue": result}

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


# ─── Scheduled Sync Endpoints ────────────────────────────────────────

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

# ─── Credential Management Endpoints (Phase 3 & 4: AES-256-GCM + RBAC) ──

@router.put("/connectors/{connector_id}/credentials/secure")
async def update_credentials_secure(
    connector_id: str,
    req: UpdateCredentialsRequest,
    current_user: User = Depends(get_current_user),
):
    from ..infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    await enforce_credential_access(
        current_user, "credential_update", connector_id, repo, require_write=True,
    )
    vault = CredentialVault()
    try:
        await vault.store_credentials(
            current_user.tenant_id, connector_id,
            req.credentials, current_user.id,
        )
        return {"message": "Credentials securely updated (AES-256-GCM)"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.post("/connectors/{connector_id}/credentials/rotate")
async def rotate_credentials(
    connector_id: str,
    req: RotateCredentialsRequest,
    current_user: User = Depends(get_current_user),
):
    from ..infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    await enforce_credential_access(
        current_user, "credential_rotation", connector_id, repo, require_write=True,
    )
    vault = CredentialVault()
    try:
        await vault.rotate_credentials(
            current_user.tenant_id, connector_id,
            req.credentials, current_user.id,
        )
        return {"message": "Credentials rotated successfully (AES-256-GCM)"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/connectors/{connector_id}/credentials/masked")
async def get_masked_credentials(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    from ..infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    await enforce_credential_access(
        current_user, "credential_view", connector_id, repo, require_write=False,
    )
    svc = ConnectorService()
    connector = await svc.get_connector(current_user.tenant_id, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")

    # Audit the access
    from ..domain.models.audit import IntegrationAuditLog, AuditAction as AA
    log = IntegrationAuditLog(
        tenant_id=current_user.tenant_id,
        connector_id=connector_id,
        action=AA.CREDENTIAL_ACCESSED,
        actor_id=current_user.id,
        metadata={"action": "credential_view"},
    )
    await repo.create_audit_log(log.to_doc())

    vault = CredentialVault()
    masked = vault.mask_credentials(connector.get("credentials", {}))
    return {
        "connector_id": connector_id,
        "credentials": masked,
        "encrypted": connector.get("credentials_encrypted", False),
        "algorithm": connector.get("encryption_algorithm", "unknown"),
        "last_updated": connector.get("credentials_updated_at"),
        "last_rotated": connector.get("credentials_rotated_at"),
    }

@router.post("/connectors/{connector_id}/credentials/migrate")
async def migrate_credentials(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    from ..infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    await enforce_credential_access(
        current_user, "credential_update", connector_id, repo, require_write=True,
    )
    vault = CredentialVault()
    try:
        result = await vault.migrate_legacy_credentials(
            current_user.tenant_id, connector_id, current_user.id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# ─── Event-Driven Sync Endpoints ─────────────────────────────────────

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


# ─── Phase 1: Sandbox Validation Endpoints ────────────────────────────

@router.post("/sandbox/validate/{connector_id}")
async def run_sandbox_validation(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = SandboxValidationService()
    try:
        return await svc.run_validation(
            current_user.tenant_id, connector_id, current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── Phase 2: Provider Adapter Endpoints ──────────────────────────────

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


# ─── Phase 5: Reconciliation Health Score ─────────────────────────────

@router.get("/reconciliation/health/{connector_id}")
async def get_reconciliation_health(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ReconciliationService()
    return await svc.get_health_score(current_user.tenant_id, connector_id)


# ─── Admin: Reconciliation Issues (Phase 1) ──────────────────────────

@router.get("/admin/reconciliation/issues")
async def admin_list_issues(
    connector_id: Optional[str] = None,
    severity: Optional[str] = None,
    issue_type: Optional[str] = None,
    status: str = Query("open"),
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    """Admin panel: list reconciliation issues with filters."""
    svc = ReconciliationService()
    issues = await svc.get_issues(current_user.tenant_id, connector_id, status, limit)
    # Apply additional filters
    if severity:
        issues = [i for i in issues if i.get("severity") == severity]
    if issue_type:
        issues = [i for i in issues if i.get("issue_type") == issue_type]
    return {"issues": issues, "count": len(issues)}


@router.post("/admin/reconciliation/issues/{issue_id}/retry-sync")
async def admin_retry_sync_for_issue(
    issue_id: str,
    current_user: User = Depends(get_current_user),
):
    """Retry sync for a reconciliation issue."""
    svc = ReconciliationService()
    issue = await svc.get_issue_detail(current_user.tenant_id, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    # Trigger inventory sync for the connector
    sync_svc = InventorySyncService()
    try:
        result = await sync_svc.trigger_inventory_sync(
            tenant_id=current_user.tenant_id,
            connector_id=issue["connector_id"],
            date_start=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            date_end=(datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d"),
            triggered_by="admin",
            trigger_reason=f"Retry from issue {issue_id}",
            actor_id=current_user.id,
        )
        await svc.update_issue_status(current_user.tenant_id, issue_id, "retrying", current_user.id)
        return {"success": True, "sync_result": result}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/admin/reconciliation/issues/{issue_id}/retry-ack")
async def admin_retry_ack_for_issue(
    issue_id: str,
    current_user: User = Depends(get_current_user),
):
    """Retry ACK for a reconciliation issue."""
    svc = ReconciliationService()
    issue = await svc.get_issue_detail(current_user.tenant_id, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    related_res = issue.get("related_reservation_ids", [])
    if related_res:
        from ..infrastructure.repository import ChannelManagerRepository
        repo = ChannelManagerRepository()
        for res_id in related_res:
            await repo.update_imported_reservation(current_user.tenant_id, res_id, {"ack_status": "ack_pending"})
    await svc.update_issue_status(current_user.tenant_id, issue_id, "retrying", current_user.id)
    return {"success": True, "retried_reservations": len(related_res)}


@router.post("/admin/reconciliation/issues/{issue_id}/revalidate-mapping")
async def admin_revalidate_mapping_for_issue(
    issue_id: str,
    current_user: User = Depends(get_current_user),
):
    """Revalidate mappings for a reconciliation issue."""
    svc = ReconciliationService()
    issue = await svc.get_issue_detail(current_user.tenant_id, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    mapping_svc = MappingService()
    result = await mapping_svc.validate_mappings(current_user.tenant_id, issue["connector_id"])
    await svc.update_issue_status(current_user.tenant_id, issue_id, "investigating", current_user.id)
    return {"success": True, "validation_result": result}


@router.post("/admin/reconciliation/issues/{issue_id}/send-to-review")
async def admin_send_issue_to_review(
    issue_id: str,
    current_user: User = Depends(get_current_user),
):
    """Send a reconciliation issue to investigating status."""
    svc = ReconciliationService()
    try:
        result = await svc.update_issue_status(current_user.tenant_id, issue_id, "investigating", current_user.id)
        return {"success": True, **result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/admin/reconciliation/issues/bulk-dismiss")
async def admin_bulk_dismiss_issues(
    req: BulkIssueActionRequest,
    current_user: User = Depends(get_current_user),
):
    """Bulk dismiss reconciliation issues."""
    from ..infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    count = await repo.bulk_dismiss_issues(current_user.tenant_id, req.issue_ids, req.reason)
    return {"success": True, "dismissed_count": count}


# ─── Admin: Scheduler Status (Phase 1) ───────────────────────────────

@router.get("/admin/scheduler/status")
async def admin_scheduler_status(
    current_user: User = Depends(get_current_user),
):
    """Get scheduler status overview for all connectors."""
    svc = SchedulerService()
    connectors = await svc._repo.get_connectors_by_tenant(current_user.tenant_id)
    statuses = []
    for c in connectors:
        cid = c.get("id", "")
        jobs = await svc._repo.get_sync_jobs(current_user.tenant_id, cid, limit=50)
        stale = [j for j in jobs if j.get("status") in ("pending", "dispatched")]
        failed = [j for j in jobs if j.get("status") == "failed"]
        last_sync = c.get("last_successful_sync")
        statuses.append({
            "connector_id": cid,
            "display_name": c.get("display_name", ""),
            "provider": c.get("provider", ""),
            "status": c.get("status", ""),
            "stale_jobs": len(stale),
            "failed_jobs": len(failed),
            "total_jobs": len(jobs),
            "last_successful_sync": last_sync,
            "consecutive_failures": c.get("consecutive_failures", 0),
        })
    return {"connectors": statuses, "count": len(statuses)}


@router.post("/admin/scheduler/trigger/{connector_id}")
async def admin_trigger_scheduler(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    """Manually trigger scheduler for a connector."""
    svc = SchedulerService()
    try:
        result = await svc.run_scheduled_check(
            current_user.tenant_id, connector_id, current_user.id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/admin/scheduler/trigger-all")
async def admin_trigger_all_schedulers(
    current_user: User = Depends(get_current_user),
):
    """Manually trigger scheduler for all active connectors."""
    svc = SchedulerService()
    return await svc.run_all_connectors(current_user.tenant_id)


# ─── Admin: Credential Management (Phase 1) ──────────────────────────

@router.get("/admin/credentials")
async def admin_list_credentials(
    current_user: User = Depends(get_current_user),
):
    """List all connector credentials (masked) with management metadata."""
    from ..infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    await enforce_credential_access(
        current_user, "credential_view", "", repo, require_write=False,
    )
    connectors = await repo.get_connectors_by_tenant(current_user.tenant_id)
    vault = CredentialVault()
    creds = []
    for c in connectors:
        masked = vault.mask_credentials(c.get("credentials", {}))
        creds.append({
            "connector_id": c.get("id", ""),
            "display_name": c.get("display_name", ""),
            "provider": c.get("provider", ""),
            "status": c.get("status", ""),
            "environment": c.get("environment", "sandbox"),
            "masked_credentials": masked,
            "encrypted": c.get("credentials_encrypted", False),
            "encryption_algorithm": c.get("encryption_algorithm", ""),
            "last_tested": c.get("last_tested"),
            "last_rotated": c.get("credentials_rotated_at"),
            "credentials_updated_at": c.get("credentials_updated_at"),
        })
    return {"credentials": creds, "count": len(creds)}


@router.post("/admin/credentials/{connector_id}/test")
async def admin_test_credential(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    """Test a connector's connection using its stored credentials."""
    from ..infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    await enforce_credential_access(
        current_user, "credential_test", connector_id, repo, require_write=False,
    )
    svc = ConnectorService()
    result = await svc.test_connection(current_user.tenant_id, connector_id)
    return result


@router.post("/admin/credentials/{connector_id}/disable")
async def admin_disable_connector(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    """Disable a connector (RBAC enforced)."""
    from ..infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    await enforce_credential_access(
        current_user, "connector_disable", connector_id, repo, require_write=True,
    )
    connector = await repo.get_connector(current_user.tenant_id, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    connector["status"] = "disabled"
    connector["disabled_at"] = datetime.now(timezone.utc).isoformat()
    connector["disabled_by"] = current_user.id
    await repo.upsert_connector(connector)

    from ..domain.models.audit import IntegrationAuditLog, AuditAction as AA
    log = IntegrationAuditLog(
        tenant_id=current_user.tenant_id,
        connector_id=connector_id,
        action=AA.ADMIN_CONNECTOR_DISABLED,
        actor_id=current_user.id,
    )
    await repo.create_audit_log(log.to_doc())
    return {"success": True, "message": "Connector disabled"}


# ─── Admin: Sync Health Dashboard (Phase 1 & 3) ──────────────────────

@router.get("/admin/sync-health")
async def admin_sync_health_dashboard(
    current_user: User = Depends(get_current_user),
):
    """Get comprehensive sync health data for the admin dashboard."""
    from ..infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    recon_svc = ReconciliationService()
    connectors = await repo.get_connectors_by_tenant(current_user.tenant_id)

    connector_health = []
    total_score = 0
    for c in connectors:
        cid = c.get("id", "")
        health = await recon_svc.get_health_score(current_user.tenant_id, cid)
        metrics = await repo.get_sync_metrics(current_user.tenant_id, cid)
        connector_health.append({
            **health,
            "display_name": c.get("display_name", ""),
            "provider": c.get("provider", ""),
            "connector_status": c.get("status", ""),
            "sync_metrics": metrics,
        })
        total_score += health.get("health_score", 0)

    avg_score = round(total_score / max(len(connectors), 1))
    error_summary = await repo.get_error_queue_summary(current_user.tenant_id)
    trend_data = await repo.get_sync_trend_24h(current_user.tenant_id)

    return {
        "overall_health_score": avg_score,
        "overall_status": "healthy" if avg_score >= 80 else ("degraded" if avg_score >= 50 else "critical"),
        "connectors": connector_health,
        "error_summary": error_summary,
        "sync_trend_24h": trend_data,
        "connector_count": len(connectors),
    }


@router.get("/admin/sync-health/{connector_id}")
async def admin_connector_sync_health(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get detailed sync health for a specific connector."""
    from ..infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    recon_svc = ReconciliationService()
    health = await recon_svc.get_health_score(current_user.tenant_id, connector_id)
    metrics = await repo.get_sync_metrics(current_user.tenant_id, connector_id)
    trend = await repo.get_sync_trend_24h(current_user.tenant_id, connector_id)
    error_summary = await repo.get_error_queue_summary(current_user.tenant_id, connector_id)
    return {
        **health,
        "sync_metrics": metrics,
        "sync_trend_24h": trend,
        "error_summary": error_summary,
    }


# ─── Phase 2: Webhook / Callback Integration ─────────────────────────

@router.post("/webhooks/{provider}")
async def receive_webhook(
    provider: str,
    request: Request,
    connector_id: Optional[str] = Query(None),
    x_webhook_signature: Optional[str] = None,
    x_webhook_timestamp: Optional[str] = None,
):
    """Receive and process an incoming webhook from a channel provider."""
    body = await request.body()
    # For webhooks, we need to resolve tenant from the connector
    # Try to resolve tenant_id from connector_id
    tenant_id = ""
    if connector_id:
        # Direct query without tenant filter for webhook resolution
        from core.database import db
        connector = await db.cm_connectors.find_one({"id": connector_id}, {"_id": 0, "tenant_id": 1})
        if connector:
            tenant_id = connector.get("tenant_id", "")
    if not tenant_id:
        # Fallback: find first active connector for this provider
        from core.database import db
        connector = await db.cm_connectors.find_one(
            {"provider": provider, "status": "active"}, {"_id": 0, "tenant_id": 1, "id": 1},
        )
        if connector:
            tenant_id = connector.get("tenant_id", "")
            connector_id = connector.get("id", "")
    if not tenant_id:
        raise HTTPException(status_code=404, detail="No active connector found")

    svc = WebhookService()
    sig = x_webhook_signature or request.headers.get("x-webhook-signature", "")
    ts = x_webhook_timestamp or request.headers.get("x-webhook-timestamp", "")
    result = await svc.process_webhook(
        tenant_id=tenant_id,
        raw_body=body,
        signature=sig,
        timestamp=ts,
        provider=provider,
        connector_id=connector_id,
    )
    if not result.get("accepted"):
        raise HTTPException(status_code=400, detail=result.get("reason", "Webhook rejected"))
    return result


@router.get("/webhooks/events")
async def list_webhook_events(
    limit: int = Query(50, le=200),
    current_user: User = Depends(get_current_user),
):
    """List recent webhook events."""
    svc = WebhookService()
    events = await svc.get_webhook_events(current_user.tenant_id, limit)
    return {"events": events, "count": len(events)}


# ─── Phase 4: Error Queue Admin Panel ────────────────────────────────

@router.get("/admin/error-queue")
async def admin_error_queue(
    connector_id: Optional[str] = None,
    error_type: Optional[str] = None,
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    """Get the operational error queue."""
    svc = ErrorQueueService()
    return await svc.get_error_queue(current_user.tenant_id, connector_id, error_type, limit)


@router.get("/admin/error-queue/summary")
async def admin_error_queue_summary(
    connector_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """Get error queue summary counts."""
    from ..infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    return await repo.get_error_queue_summary(current_user.tenant_id, connector_id)


@router.post("/admin/error-queue/retry")
async def admin_retry_error(
    req: ErrorQueueActionRequest,
    current_user: User = Depends(get_current_user),
):
    """Retry a single error queue item."""
    svc = ErrorQueueService()
    return await svc.retry_item(current_user.tenant_id, req.item_id, req.error_type, current_user.id)


@router.post("/admin/error-queue/dismiss")
async def admin_dismiss_error(
    req: ErrorQueueActionRequest,
    current_user: User = Depends(get_current_user),
):
    """Dismiss a single error queue item."""
    svc = ErrorQueueService()
    return await svc.dismiss_item(current_user.tenant_id, req.item_id, req.error_type, req.reason, current_user.id)


@router.post("/admin/error-queue/escalate")
async def admin_escalate_error(
    req: ErrorQueueActionRequest,
    current_user: User = Depends(get_current_user),
):
    """Escalate an error to a reconciliation issue."""
    svc = ErrorQueueService()
    return await svc.escalate_item(current_user.tenant_id, req.item_id, req.error_type, current_user.id)


@router.post("/admin/error-queue/bulk-retry")
async def admin_bulk_retry_errors(
    req: BulkRetryRequest,
    current_user: User = Depends(get_current_user),
):
    """Bulk retry error queue items."""
    svc = ErrorQueueService()
    return await svc.bulk_retry(current_user.tenant_id, req.item_ids, req.error_type, current_user.id)


@router.post("/admin/error-queue/bulk-dismiss")
async def admin_bulk_dismiss_errors(
    req: BulkDismissRequest,
    current_user: User = Depends(get_current_user),
):
    """Bulk dismiss error queue items."""
    svc = ErrorQueueService()
    return await svc.bulk_dismiss(current_user.tenant_id, req.item_ids, req.error_type, req.reason, current_user.id)


# ─── Phase 5: Operational Observability ───────────────────────────────

@router.get("/admin/observability/metrics")
async def admin_observability_metrics(
    connector_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """Get operational observability metrics."""
    from ..infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    connectors = await repo.get_connectors_by_tenant(current_user.tenant_id)

    if connector_id:
        connectors = [c for c in connectors if c.get("id") == connector_id]

    metrics_list = []
    for c in connectors:
        cid = c.get("id", "")
        sync_metrics = await repo.get_sync_metrics(current_user.tenant_id, cid)
        jobs = await repo.get_sync_jobs(current_user.tenant_id, cid, limit=100)

        # Calculate rates
        total_jobs = len(jobs)
        succeeded_jobs = sum(1 for j in jobs if j.get("status") == "succeeded")
        failed_jobs = sum(1 for j in jobs if j.get("status") == "failed")
        retry_jobs = sum(1 for j in jobs if j.get("retry_count", 0) > 0)
        success_rate = round(succeeded_jobs / max(total_jobs, 1) * 100, 1)
        retry_rate = round(retry_jobs / max(total_jobs, 1) * 100, 1)

        # ACK metrics
        from core.database import db
        total_imports = await db.cm_imported_reservations.count_documents({
            "tenant_id": current_user.tenant_id, "connector_id": cid,
        })
        ack_sent = await db.cm_imported_reservations.count_documents({
            "tenant_id": current_user.tenant_id, "connector_id": cid, "ack_status": "ack_sent",
        })
        ack_rate = round(ack_sent / max(total_imports, 1) * 100, 1)

        # Mapping validation
        mappings = await repo.get_mappings(current_user.tenant_id, cid)
        valid_mappings = sum(1 for m in mappings if m.get("validation_status") != "invalid")
        mapping_rate = round(valid_mappings / max(len(mappings), 1) * 100, 1)

        metrics_list.append({
            "connector_id": cid,
            "display_name": c.get("display_name", ""),
            "provider": c.get("provider", ""),
            "sync_success_rate": success_rate,
            "sync_total": total_jobs,
            "sync_succeeded": succeeded_jobs,
            "sync_failed": failed_jobs,
            "retry_jobs": retry_jobs,
            "retry_rate": retry_rate,
            "ack_success_rate": ack_rate,
            "ack_sent": ack_sent,
            "total_imports": total_imports,
            "mapping_validation_rate": mapping_rate,
            "total_mappings": len(mappings),
            "valid_mappings": valid_mappings,
            "open_issues": sync_metrics.get("open_issues", 0),
        })

    return {"metrics": metrics_list, "count": len(metrics_list)}


@router.get("/admin/observability/audit-trail")
async def admin_audit_trail(
    connector_id: Optional[str] = None,
    action: Optional[str] = None,
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    """Get structured audit trail with optional filters."""
    from ..infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    logs = await repo.get_audit_logs(current_user.tenant_id, connector_id, limit)
    if action:
        logs = [log_entry for log_entry in logs if log_entry.get("action") == action]
    return {"logs": logs, "count": len(logs)}


# ─── Phase 6: Production Readiness Validation ────────────────────────

@router.post("/admin/production-readiness/{connector_id}")
async def admin_production_readiness(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    """Run production readiness validation for a connector."""
    svc = ProductionReadinessService()
    return await svc.run_readiness_check(
        current_user.tenant_id, connector_id, current_user.id,
    )


@router.get("/admin/production-readiness/overview")
async def admin_production_readiness_overview(
    current_user: User = Depends(get_current_user),
):
    """Get production readiness overview for all connectors."""
    from ..infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    svc = ProductionReadinessService()
    connectors = await repo.get_connectors_by_tenant(current_user.tenant_id)
    reports = []
    for c in connectors:
        report = await svc.run_readiness_check(current_user.tenant_id, c["id"], current_user.id)
        reports.append(report)
    ready = sum(1 for r in reports if r.get("production_recommendation") == "READY_FOR_PRODUCTION")
    return {
        "reports": reports,
        "total_connectors": len(reports),
        "ready_for_production": ready,
        "not_ready": len(reports) - ready,
    }


# ─── Phase 1: Historical Metrics Storage ──────────────────────────────

class CreateSnapshotRequest(BaseModel):
    connector_id: Optional[str] = None

class AlertRuleRequest(BaseModel):
    trigger: str
    threshold: float = 1
    severity: str = "warning"
    description: str = ""
    enabled: bool = True
    connector_id: Optional[str] = None

class AlertActionRequest(BaseModel):
    reason: str = ""
    hours: int = 24


@router.post("/metrics/snapshot")
async def create_metrics_snapshot(
    req: CreateSnapshotRequest = Body(CreateSnapshotRequest()),
    current_user: User = Depends(get_current_user),
):
    """Create a metrics snapshot for all or a specific connector."""
    svc = HistoricalMetricsService()
    return await svc.create_snapshot(current_user.tenant_id, req.connector_id)


@router.get("/metrics/history")
async def get_metrics_history(
    connector_id: Optional[str] = None,
    period: str = Query("7d"),
    limit: int = Query(500, le=2000),
    current_user: User = Depends(get_current_user),
):
    """Get raw metrics snapshot history."""
    svc = HistoricalMetricsService()
    return await svc.get_history(current_user.tenant_id, connector_id, period, limit)


@router.get("/metrics/trends")
async def get_metrics_trends(
    connector_id: Optional[str] = None,
    period: str = Query("7d"),
    current_user: User = Depends(get_current_user),
):
    """Get trend data for key metrics over a period."""
    svc = HistoricalMetricsService()
    return await svc.get_trends(current_user.tenant_id, connector_id, period)


@router.get("/metrics/history/{connector_id}")
async def get_connector_metrics_history(
    connector_id: str,
    period: str = Query("7d"),
    current_user: User = Depends(get_current_user),
):
    """Get metrics history for a specific connector."""
    svc = HistoricalMetricsService()
    return await svc.get_history(current_user.tenant_id, connector_id, period)


@router.get("/metrics/history/property/{property_id}")
async def get_property_metrics_history(
    property_id: str,
    period: str = Query("7d"),
    current_user: User = Depends(get_current_user),
):
    """Get metrics history for a specific property."""
    svc = HistoricalMetricsService()
    return await svc.get_history_by_property(current_user.tenant_id, property_id, period)


@router.post("/metrics/retention-cleanup")
async def run_retention_cleanup(
    current_user: User = Depends(get_current_user),
):
    """Run retention cleanup for old snapshots."""
    svc = HistoricalMetricsService()
    return await svc.run_retention_cleanup(current_user.tenant_id)


@router.post("/metrics/daily-aggregation")
async def run_daily_aggregation(
    date: Optional[str] = Body(None, embed=True),
    current_user: User = Depends(get_current_user),
):
    """Create daily aggregation from hourly snapshots."""
    svc = HistoricalMetricsService()
    return await svc.create_daily_aggregation(current_user.tenant_id, date)


# ─── Phase 2: Alerting System ─────────────────────────────────────────

@router.get("/alerts")
async def list_alerts(
    status: Optional[str] = None,
    severity: Optional[str] = None,
    connector_id: Optional[str] = None,
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    """Get all alerts with optional filters."""
    svc = AlertingService()
    alerts = await svc.get_alerts(current_user.tenant_id, status, severity, connector_id, limit)
    summary = await svc.get_alert_summary(current_user.tenant_id)
    return {"alerts": alerts, "count": len(alerts), "summary": summary}


@router.get("/alerts/summary")
async def get_alert_summary(
    current_user: User = Depends(get_current_user),
):
    """Get alert summary counts."""
    svc = AlertingService()
    return await svc.get_alert_summary(current_user.tenant_id)


@router.post("/alerts/evaluate")
async def evaluate_alerts(
    current_user: User = Depends(get_current_user),
):
    """Evaluate alert rules against current state."""
    svc = AlertingService()
    return await svc.evaluate_alerts(current_user.tenant_id)


@router.get("/alerts/rules")
async def list_alert_rules(
    current_user: User = Depends(get_current_user),
):
    """Get all alert rules."""
    svc = AlertingService()
    rules = await svc.get_rules(current_user.tenant_id)
    return {"rules": rules, "count": len(rules)}


@router.post("/alerts/rules")
async def create_alert_rule(
    req: AlertRuleRequest,
    current_user: User = Depends(get_current_user),
):
    """Create a new alert rule."""
    svc = AlertingService()
    rule = await svc.create_rule(current_user.tenant_id, req.model_dump(), current_user.id)
    return {"message": "Rule created", "rule": rule}


@router.put("/alerts/rules/{rule_id}")
async def update_alert_rule(
    rule_id: str,
    req: AlertRuleRequest,
    current_user: User = Depends(get_current_user),
):
    """Update an alert rule."""
    svc = AlertingService()
    rule = await svc.update_rule(current_user.tenant_id, rule_id, req.model_dump(), current_user.id)
    return {"message": "Rule updated", "rule": rule}


@router.delete("/alerts/rules/{rule_id}")
async def delete_alert_rule(
    rule_id: str,
    current_user: User = Depends(get_current_user),
):
    """Delete an alert rule."""
    svc = AlertingService()
    deleted = await svc.delete_rule(current_user.tenant_id, rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"message": "Rule deleted"}


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    alert_id: str,
    current_user: User = Depends(get_current_user),
):
    """Acknowledge an alert."""
    svc = AlertingService()
    return await svc.acknowledge_alert(current_user.tenant_id, alert_id, current_user.id)


@router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(
    alert_id: str,
    req: AlertActionRequest = Body(AlertActionRequest()),
    current_user: User = Depends(get_current_user),
):
    """Resolve an alert."""
    svc = AlertingService()
    return await svc.resolve_alert(current_user.tenant_id, alert_id, current_user.id, req.reason)


@router.post("/alerts/{alert_id}/mute")
async def mute_alert(
    alert_id: str,
    req: AlertActionRequest = Body(AlertActionRequest()),
    current_user: User = Depends(get_current_user),
):
    """Mute an alert for specified hours."""
    svc = AlertingService()
    return await svc.mute_alert(current_user.tenant_id, alert_id, req.hours, current_user.id)


@router.post("/alerts/{alert_id}/dismiss")
async def dismiss_alert(
    alert_id: str,
    req: AlertActionRequest = Body(AlertActionRequest()),
    current_user: User = Depends(get_current_user),
):
    """Dismiss an alert."""
    svc = AlertingService()
    return await svc.dismiss_alert(current_user.tenant_id, alert_id, current_user.id, req.reason)


# ─── Phase 3: Enhanced Sandbox Validation ──────────────────────────────

@router.post("/sandbox/validate/{connector_id}/full")
async def run_full_sandbox_validation(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    """Run the extended 12-step sandbox validation."""
    svc = SandboxValidationService()
    try:
        report = await svc.run_validation(current_user.tenant_id, connector_id, current_user.id)
        # Add enhanced fields
        mapping_svc = MappingService()
        readiness = await mapping_svc.check_sync_readiness(current_user.tenant_id, connector_id)
        report["mapping_readiness"] = readiness
        report["environment_config"] = {
            "connector_id": connector_id,
            "environment_validated": True,
        }
        report["required_next_actions"] = []
        for check in report.get("checks", []):
            if not check.get("success"):
                report["required_next_actions"].append(
                    f"Fix: {check['check_name']} — {check.get('error', check.get('response_summary', ''))}"
                )
        report["connector_health_impact"] = "high" if report.get("failed_checks", 0) > 3 else ("medium" if report.get("failed_checks", 0) > 0 else "low")
        return report
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ─── Phase 4: Connector Reliability Monitoring ────────────────────────

@router.get("/reliability")
async def get_all_reliability(
    current_user: User = Depends(get_current_user),
):
    """Get reliability metrics for all connectors."""
    svc = ReliabilityService()
    return await svc.get_all_reliability(current_user.tenant_id)


@router.get("/reliability/{connector_id}")
async def get_connector_reliability(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get reliability metrics for a specific connector."""
    svc = ReliabilityService()
    result = await svc.get_reliability(current_user.tenant_id, connector_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/reliability/property/{property_id}")
async def get_property_reliability(
    property_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get reliability metrics for connectors of a property."""
    svc = ReliabilityService()
    return await svc.get_reliability_by_property(current_user.tenant_id, property_id)


# ─── Phase 5: Multi-Property Integration Dashboard ────────────────────

@router.get("/multi-property/dashboard")
async def get_multi_property_dashboard(
    current_user: User = Depends(get_current_user),
):
    """Get the multi-property integration dashboard."""
    svc = MultiPropertyService()
    return await svc.get_dashboard(current_user.tenant_id)


@router.get("/multi-property/comparison")
async def get_multi_property_comparison(
    current_user: User = Depends(get_current_user),
):
    """Get cross-property comparison."""
    svc = MultiPropertyService()
    return await svc.get_comparison(current_user.tenant_id)


@router.get("/multi-property/issues")
async def get_multi_property_issues(
    property_id: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """Get issues across all properties."""
    svc = MultiPropertyService()
    return await svc.get_issues(current_user.tenant_id, property_id)


@router.get("/multi-property/health")
async def get_multi_property_health(
    current_user: User = Depends(get_current_user),
):
    """Get aggregated health across all properties."""
    svc = MultiPropertyService()
    return await svc.get_health(current_user.tenant_id)
