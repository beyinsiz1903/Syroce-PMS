"""Reconciliation, observability, audit-trail, webhook, error-queue, admin endpoints."""
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v90 DW

from ...application.connector_service import ConnectorService
from ...application.error_queue_service import ErrorQueueService
from ...application.inventory_sync_service import InventorySyncService
from ...application.mapping_service import MappingService
from ...application.observability_service import ObservabilityService
from ...application.production_readiness_service import ProductionReadinessService
from ...application.reconciliation_service import ReconciliationService
from ...application.sandbox_validation_service import SandboxValidationService
from ...application.scheduler_service import SchedulerService
from ...application.webhook_service import WebhookService
from ...infrastructure.credential_vault import CredentialVault
from ...infrastructure.rbac import enforce_credential_access

logger = logging.getLogger("channel_manager.routers.audit")

router = APIRouter(tags=["CM Audit & Admin"])


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
    suggested_actions: list[str] | None = None
    evidence_payload: dict | None = None


class ErrorQueueActionRequest(BaseModel):
    item_id: str
    error_type: str
    reason: str = ""


class BulkRetryRequest(BaseModel):
    item_ids: list[str]
    error_type: str


class BulkDismissRequest(BaseModel):
    item_ids: list[str]
    error_type: str
    reason: str = ""


class BulkIssueActionRequest(BaseModel):
    issue_ids: list[str]
    reason: str = ""


# ─── Reconciliation ──────────────────────────────────────────────

@router.post("/reconciliation/run")
async def run_reconciliation(
    connector_id: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    svc = ReconciliationService()
    result = await svc.run_reconciliation(current_user.tenant_id, connector_id, current_user.id)
    return result


@router.get("/reconciliation/issues")
async def list_reconciliation_issues(
    connector_id: str | None = None,
    status: str = Query("open"),
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    svc = ReconciliationService()
    issues = await svc.get_issues(current_user.tenant_id, connector_id, status, limit)
    return {"issues": issues, "count": len(issues)}


@router.get("/reconciliation/issues/summary")
async def get_reconciliation_summary(
    connector_id: str | None = None,
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
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
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
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    svc = ReconciliationService()
    return await svc.resolve_issue(current_user.tenant_id, issue_id, req.resolution, current_user.id)


@router.post("/reconciliation/issues/{issue_id}/dismiss")
async def dismiss_issue(
    issue_id: str,
    req: DismissIssueRequest = Body(DismissIssueRequest()),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    svc = ReconciliationService()
    return await svc.dismiss_issue(current_user.tenant_id, issue_id, req.reason, current_user.id)


@router.post("/reconciliation/issues")
async def create_reconciliation_issue(
    req: CreateIssueRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
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


@router.get("/reconciliation/health/{connector_id}")
async def get_reconciliation_health(
    connector_id: str,
    current_user: User = Depends(get_current_user),
):
    svc = ReconciliationService()
    return await svc.get_health_score(current_user.tenant_id, connector_id)


# ─── Observability ────────────────────────────────────────────────

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
    connector_id: str | None = None,
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    from ...infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    logs = await repo.get_audit_logs(current_user.tenant_id, connector_id, limit)
    return {"logs": logs, "count": len(logs)}


# ─── Webhooks ────────────────────────────────────────────────────

@router.post("/webhooks/{provider}")
async def receive_webhook(
    provider: str,
    request: Request,
    connector_id: str | None = Query(None),
    x_webhook_signature: str | None = None,
    x_webhook_timestamp: str | None = None,
):
    body = await request.body()
    tenant_id = ""
    if connector_id:
        from core.database import db
        connector = await db.cm_connectors.find_one({"id": connector_id}, {"_id": 0, "tenant_id": 1})
        if connector:
            tenant_id = connector.get("tenant_id", "")
    if not tenant_id:
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
    svc = WebhookService()
    events = await svc.get_webhook_events(current_user.tenant_id, limit)
    return {"events": events, "count": len(events)}


# ─── Admin: Reconciliation Issues ────────────────────────────────

@router.get("/admin/reconciliation/issues")
async def admin_list_issues(
    connector_id: str | None = None,
    severity: str | None = None,
    issue_type: str | None = None,
    status: str = Query("open"),
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    svc = ReconciliationService()
    issues = await svc.get_issues(current_user.tenant_id, connector_id, status, limit)
    if severity:
        issues = [i for i in issues if i.get("severity") == severity]
    if issue_type:
        issues = [i for i in issues if i.get("issue_type") == issue_type]
    return {"issues": issues, "count": len(issues)}


@router.post("/admin/reconciliation/issues/{issue_id}/retry-sync")
async def admin_retry_sync_for_issue(
    issue_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
):
    svc = ReconciliationService()
    issue = await svc.get_issue_detail(current_user.tenant_id, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    sync_svc = InventorySyncService()
    try:
        result = await sync_svc.trigger_inventory_sync(
            tenant_id=current_user.tenant_id,
            connector_id=issue["connector_id"],
            date_start=datetime.now(UTC).strftime("%Y-%m-%d"),
            date_end=(datetime.now(UTC) + timedelta(days=7)).strftime("%Y-%m-%d"),
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
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
):
    svc = ReconciliationService()
    issue = await svc.get_issue_detail(current_user.tenant_id, issue_id)
    if not issue:
        raise HTTPException(status_code=404, detail="Issue not found")
    related_res = issue.get("related_reservation_ids", [])
    if related_res:
        from ...infrastructure.repository import ChannelManagerRepository
        repo = ChannelManagerRepository()
        for res_id in related_res:
            await repo.update_imported_reservation(current_user.tenant_id, res_id, {"ack_status": "ack_pending"})
    await svc.update_issue_status(current_user.tenant_id, issue_id, "retrying", current_user.id)
    return {"success": True, "retried_reservations": len(related_res)}


@router.post("/admin/reconciliation/issues/{issue_id}/revalidate-mapping")
async def admin_revalidate_mapping_for_issue(
    issue_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
):
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
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
):
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
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
):
    from ...infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    count = await repo.bulk_dismiss_issues(current_user.tenant_id, req.issue_ids, req.reason)
    return {"success": True, "dismissed_count": count}


# ─── Admin: Scheduler ────────────────────────────────────────────

@router.get("/admin/scheduler/status")
async def admin_scheduler_status(
    current_user: User = Depends(get_current_user),
):
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
    _perm=Depends(require_op("view_system_diagnostics")),  # v90 DW
):
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
    _perm=Depends(require_op("view_system_diagnostics")),  # v90 DW
):
    svc = SchedulerService()
    return await svc.run_all_connectors(current_user.tenant_id)


# ─── Admin: Credentials ──────────────────────────────────────────

@router.get("/admin/credentials")
async def admin_list_credentials(
    current_user: User = Depends(get_current_user),
):
    from ...infrastructure.repository import ChannelManagerRepository
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
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
):
    from ...infrastructure.repository import ChannelManagerRepository
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
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
):
    from ...infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    await enforce_credential_access(
        current_user, "connector_disable", connector_id, repo, require_write=True,
    )
    connector = await repo.get_connector(current_user.tenant_id, connector_id)
    if not connector:
        raise HTTPException(status_code=404, detail="Connector not found")
    connector["status"] = "disabled"
    connector["disabled_at"] = datetime.now(UTC).isoformat()
    connector["disabled_by"] = current_user.id
    await repo.upsert_connector(connector)

    from ...domain.models.audit import AuditAction, IntegrationAuditLog
    log = IntegrationAuditLog(
        tenant_id=current_user.tenant_id,
        connector_id=connector_id,
        action=AuditAction.ADMIN_CONNECTOR_DISABLED,
        actor_id=current_user.id,
    )
    await repo.create_audit_log(log.to_doc())
    return {"success": True, "message": "Connector disabled"}


# ─── Admin: Sync Health ──────────────────────────────────────────

@router.get("/admin/sync-health")
async def admin_sync_health_dashboard(
    current_user: User = Depends(get_current_user),
):
    from ...infrastructure.repository import ChannelManagerRepository
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
    from ...infrastructure.repository import ChannelManagerRepository
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


# ─── Admin: Error Queue ──────────────────────────────────────────

@router.get("/admin/error-queue")
async def admin_error_queue(
    connector_id: str | None = None,
    error_type: str | None = None,
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    svc = ErrorQueueService()
    return await svc.get_error_queue(current_user.tenant_id, connector_id, error_type, limit)


@router.get("/admin/error-queue/summary")
async def admin_error_queue_summary(
    connector_id: str | None = None,
    current_user: User = Depends(get_current_user),
):
    from ...infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    return await repo.get_error_queue_summary(current_user.tenant_id, connector_id)


@router.post("/admin/error-queue/retry")
async def admin_retry_error(
    req: ErrorQueueActionRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
):
    svc = ErrorQueueService()
    return await svc.retry_item(current_user.tenant_id, req.item_id, req.error_type, current_user.id)


@router.post("/admin/error-queue/dismiss")
async def admin_dismiss_error(
    req: ErrorQueueActionRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
):
    svc = ErrorQueueService()
    return await svc.dismiss_item(current_user.tenant_id, req.item_id, req.error_type, req.reason, current_user.id)


@router.post("/admin/error-queue/escalate")
async def admin_escalate_error(
    req: ErrorQueueActionRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
):
    svc = ErrorQueueService()
    return await svc.escalate_item(current_user.tenant_id, req.item_id, req.error_type, current_user.id)


@router.post("/admin/error-queue/bulk-retry")
async def admin_bulk_retry_errors(
    req: BulkRetryRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
):
    svc = ErrorQueueService()
    return await svc.bulk_retry(current_user.tenant_id, req.item_ids, req.error_type, current_user.id)


@router.post("/admin/error-queue/bulk-dismiss")
async def admin_bulk_dismiss_errors(
    req: BulkDismissRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
):
    svc = ErrorQueueService()
    return await svc.bulk_dismiss(current_user.tenant_id, req.item_ids, req.error_type, req.reason, current_user.id)


# ─── Admin: Observability Metrics ────────────────────────────────

@router.get("/admin/observability/metrics")
async def admin_observability_metrics(
    connector_id: str | None = None,
    current_user: User = Depends(get_current_user),
):
    from ...infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    connectors = await repo.get_connectors_by_tenant(current_user.tenant_id)
    if connector_id:
        connectors = [c for c in connectors if c.get("id") == connector_id]

    metrics_list = []
    for c in connectors:
        cid = c.get("id", "")
        sync_metrics = await repo.get_sync_metrics(current_user.tenant_id, cid)
        jobs = await repo.get_sync_jobs(current_user.tenant_id, cid, limit=100)

        total_jobs = len(jobs)
        succeeded_jobs = sum(1 for j in jobs if j.get("status") == "succeeded")
        failed_jobs = sum(1 for j in jobs if j.get("status") == "failed")
        retry_jobs = sum(1 for j in jobs if j.get("retry_count", 0) > 0)
        success_rate = round(succeeded_jobs / max(total_jobs, 1) * 100, 1)
        retry_rate = round(retry_jobs / max(total_jobs, 1) * 100, 1)

        from core.database import db
        total_imports = await db.cm_imported_reservations.count_documents({
            "tenant_id": current_user.tenant_id, "connector_id": cid,
        })
        ack_sent = await db.cm_imported_reservations.count_documents({
            "tenant_id": current_user.tenant_id, "connector_id": cid, "ack_status": "ack_sent",
        })
        ack_rate = round(ack_sent / max(total_imports, 1) * 100, 1)

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
    connector_id: str | None = None,
    action: str | None = None,
    limit: int = Query(100, le=500),
    current_user: User = Depends(get_current_user),
):
    from ...infrastructure.repository import ChannelManagerRepository
    repo = ChannelManagerRepository()
    logs = await repo.get_audit_logs(current_user.tenant_id, connector_id, limit)
    if action:
        logs = [log_entry for log_entry in logs if log_entry.get("action") == action]
    return {"logs": logs, "count": len(logs)}


# ─── Admin: Production Readiness ─────────────────────────────────

@router.post("/admin/production-readiness/{connector_id}")
async def admin_production_readiness(
    connector_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
):
    svc = ProductionReadinessService()
    return await svc.run_readiness_check(
        current_user.tenant_id, connector_id, current_user.id,
    )


@router.get("/admin/production-readiness/overview")
async def admin_production_readiness_overview(
    current_user: User = Depends(get_current_user),
):
    from ...infrastructure.repository import ChannelManagerRepository
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


# ─── Sandbox Validation ──────────────────────────────────────────

@router.post("/sandbox/validate/{connector_id}")
async def run_sandbox_validation(
    connector_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    svc = SandboxValidationService()
    try:
        return await svc.run_validation(
            current_user.tenant_id, connector_id, current_user.id,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/sandbox/validate/{connector_id}/full")
async def run_full_sandbox_validation(
    connector_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    svc = SandboxValidationService()
    try:
        report = await svc.run_validation(current_user.tenant_id, connector_id, current_user.id)
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
