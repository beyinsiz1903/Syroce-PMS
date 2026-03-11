"""
Error Queue Service - Operational error queue for failed operations.

Provides a unified view of:
  - Failed sync jobs
  - Failed reservation imports
  - ACK failed reservations
  - Provider validation errors

Supports: retry, send_to_review, dismiss, escalate, bulk operations.
"""
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from ..domain.models.audit import IntegrationAuditLog, AuditAction
from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.error_queue_service")


class ErrorQueueService:
    """Unified error queue for all failed channel manager operations."""

    def __init__(self, repo: Optional[ChannelManagerRepository] = None):
        self._repo = repo or ChannelManagerRepository()

    async def get_error_queue(
        self,
        tenant_id: str,
        connector_id: Optional[str] = None,
        error_type: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        items = await self._repo.get_error_queue(tenant_id, connector_id, error_type, limit)
        summary = await self._repo.get_error_queue_summary(tenant_id, connector_id)
        return {
            "items": items,
            "count": len(items),
            "summary": summary,
        }

    async def retry_item(
        self, tenant_id: str, item_id: str, error_type: str,
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Retry a single error queue item."""
        if error_type == "sync_failed":
            await self._repo.update_sync_job(item_id, {
                "status": "pending",
                "last_error": None,
                "completed_at": None,
            })
        elif error_type == "import_failed":
            await self._repo.update_imported_reservation(tenant_id, item_id, {
                "import_status": "review",
            })
        elif error_type == "ack_failed":
            await self._repo.update_imported_reservation(tenant_id, item_id, {
                "ack_status": "ack_pending",
            })
        else:
            return {"success": False, "reason": f"Unknown error type: {error_type}"}

        await self._audit(tenant_id, "", "", AuditAction.MANUAL_RETRY, actor_id, {
            "item_id": item_id, "error_type": error_type,
        })
        return {"success": True, "item_id": item_id, "action": "retried"}

    async def dismiss_item(
        self, tenant_id: str, item_id: str, error_type: str,
        reason: str = "", actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Dismiss a single error queue item."""
        if error_type == "sync_failed":
            await self._repo.update_sync_job(item_id, {
                "status": "dismissed",
                "dismiss_reason": reason,
            })
        elif error_type in ("import_failed", "ack_failed"):
            await self._repo.update_imported_reservation(tenant_id, item_id, {
                "import_status": "dismissed",
                "dismiss_reason": reason,
            })
        await self._audit(tenant_id, "", "", AuditAction.MANUAL_REVIEW_DISMISSED, actor_id, {
            "item_id": item_id, "error_type": error_type, "reason": reason,
        })
        return {"success": True, "item_id": item_id, "action": "dismissed"}

    async def escalate_item(
        self, tenant_id: str, item_id: str, error_type: str,
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Escalate an error item by creating a reconciliation issue."""
        from ..application.reconciliation_service import ReconciliationService
        recon = ReconciliationService(self._repo)

        connector_id = ""
        description = f"Escalated {error_type} item: {item_id}"

        if error_type == "sync_failed":
            job = await self._repo.get_sync_job(item_id)
            if job:
                connector_id = job.get("connector_id", "")
                description = f"Escalated failed sync job: {job.get('last_error', '')[:200]}"
        elif error_type in ("import_failed", "ack_failed"):
            res = await self._repo.get_imported_reservation_by_id(tenant_id, item_id)
            if res:
                connector_id = res.get("connector_id", "")
                description = f"Escalated {error_type}: reservation {item_id}"

        connector = await self._repo.get_connector(tenant_id, connector_id) if connector_id else None
        property_id = connector.get("property_id", "") if connector else ""

        await recon.create_issue(
            tenant_id=tenant_id,
            property_id=property_id,
            connector_id=connector_id,
            issue_type="stale_sync" if error_type == "sync_failed" else "ack_failed",
            severity="high",
            description=description,
            suggested_actions=["retry_sync"],
        )

        await self._audit(tenant_id, property_id, connector_id, AuditAction.ERROR_ESCALATED, actor_id, {
            "item_id": item_id, "error_type": error_type,
        })
        return {"success": True, "item_id": item_id, "action": "escalated"}

    async def bulk_retry(
        self, tenant_id: str, item_ids: List[str], error_type: str,
        actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Bulk retry multiple error queue items."""
        if error_type == "sync_failed":
            count = await self._repo.bulk_retry_sync_jobs(tenant_id, item_ids)
        else:
            count = 0
            for item_id in item_ids:
                r = await self.retry_item(tenant_id, item_id, error_type, actor_id)
                if r.get("success"):
                    count += 1
        await self._audit(tenant_id, "", "", AuditAction.BULK_RETRY, actor_id, {
            "count": count, "error_type": error_type,
        })
        return {"success": True, "retried_count": count, "requested": len(item_ids)}

    async def bulk_dismiss(
        self, tenant_id: str, item_ids: List[str], error_type: str,
        reason: str = "", actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Bulk dismiss multiple error queue items."""
        count = 0
        for item_id in item_ids:
            r = await self.dismiss_item(tenant_id, item_id, error_type, reason, actor_id)
            if r.get("success"):
                count += 1
        await self._audit(tenant_id, "", "", AuditAction.BULK_DISMISS, actor_id, {
            "count": count, "error_type": error_type, "reason": reason,
        })
        return {"success": True, "dismissed_count": count, "requested": len(item_ids)}

    async def _audit(self, tenant_id, property_id, connector_id, action, actor_id=None, metadata=None):
        log = IntegrationAuditLog(
            tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
            action=action, actor_id=actor_id, metadata=metadata or {},
        )
        await self._repo.create_audit_log(log.to_doc())
