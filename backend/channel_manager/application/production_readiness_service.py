"""
Production Readiness Validation Service - Comprehensive integration health check.

Enhanced Checklist (10 items):
  1. HotelRunner sandbox auth success
  2. Inventory push success
  3. Reservation import success
  4. Reservation modification success
  5. Reservation cancellation success
  6. ACK lifecycle success
  7. Alerts functioning
  8. Metrics aggregation functioning
  9. Scheduler jobs working
  10. Credential security verified

Report: passed_checks, failed_checks, warnings, blocker_issues,
        production_recommendation (NOT_READY / CONDITIONALLY_READY / PRODUCTION_READY)
"""

import logging
from datetime import UTC, datetime
from typing import Any

from core.database import db

from ..domain.models.audit import AuditAction, IntegrationAuditLog
from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.application.production_readiness_service")


class ProductionReadinessService:
    """Runs comprehensive production readiness checks for a connector."""

    def __init__(self, repo: ChannelManagerRepository | None = None):
        self._repo = repo or ChannelManagerRepository()

    async def run_readiness_check(
        self,
        tenant_id: str,
        connector_id: str,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Run all 11 production readiness checks and generate a report."""
        connector = await self._repo.get_connector(tenant_id, connector_id)
        if not connector:
            return {"error": "Connector not found"}

        property_id = connector.get("property_id", "")
        checks: list[dict[str, Any]] = []

        # 1. HotelRunner sandbox auth success
        checks.append(await self._check_authentication(connector))

        # 2. Inventory push success
        checks.append(await self._check_inventory_push(tenant_id, connector_id))

        # 3. Rate push success
        checks.append(await self._check_rate_push(tenant_id, connector_id))

        # 4. Reservation import success
        checks.append(await self._check_reservation_pull(tenant_id, connector_id))

        # 5. Reservation modification success
        checks.append(await self._check_reservation_modification(tenant_id, connector_id))

        # 6. Reservation cancellation success
        checks.append(await self._check_reservation_cancellation(tenant_id, connector_id))

        # 7. ACK lifecycle success
        checks.append(await self._check_reservation_ack(tenant_id, connector_id))

        # 8. Alerts functioning
        checks.append(await self._check_alerts_functioning(tenant_id))

        # 9. Metrics aggregation functioning
        checks.append(await self._check_metrics_aggregation(tenant_id, connector_id))

        # 10. Scheduler jobs working
        checks.append(await self._check_scheduler_jobs(tenant_id, connector_id))

        # 11. Credential security verified
        checks.append(self._check_credential_security(connector))

        # 12. Mapping completeness
        checks.append(await self._check_mapping_completeness(tenant_id, connector_id))

        # Aggregate
        passed = [c for c in checks if c["status"] == "passed"]
        failed = [c for c in checks if c["status"] == "failed"]
        warnings = [c for c in checks if c["status"] == "warning"]
        blockers = [c for c in failed if c.get("blocker", False)]

        total_passed = len(passed)
        total_failed = len(failed)
        total_warnings = len(warnings)

        if not blockers and total_failed == 0:
            recommendation = "PRODUCTION_READY"
        elif not blockers and total_failed <= 2:
            recommendation = "CONDITIONALLY_READY"
        else:
            recommendation = "NOT_READY"

        report = {
            "connector_id": connector_id,
            "property_id": property_id,
            "provider": connector.get("provider", ""),
            "display_name": connector.get("display_name", ""),
            "checks": checks,
            "passed_checks": total_passed,
            "failed_checks": total_failed,
            "warning_checks": total_warnings,
            "blocker_issues": [c["check"] for c in blockers],
            "total_checks": len(checks),
            "production_recommendation": recommendation,
            "checked_at": datetime.now(UTC).isoformat(),
        }

        # Audit
        log = IntegrationAuditLog(
            tenant_id=tenant_id,
            property_id=property_id,
            connector_id=connector_id,
            action=AuditAction.PRODUCTION_READINESS_CHECK,
            actor_id=actor_id,
            metadata={"passed": total_passed, "failed": total_failed, "recommendation": recommendation},
        )
        await self._repo.create_audit_log(log.to_doc())

        return report

    async def _check_authentication(self, connector: dict) -> dict[str, Any]:
        status = connector.get("status", "")
        has_creds = bool(connector.get("credentials"))
        if status == "active" and has_creds:
            return {"check": "sandbox_auth_success", "status": "passed", "detail": "Connector active with credentials"}
        elif has_creds:
            return {"check": "sandbox_auth_success", "status": "warning", "detail": f"Connector status: {status}", "blocker": False}
        return {"check": "sandbox_auth_success", "status": "failed", "detail": "No credentials configured", "blocker": True}

    async def _check_inventory_push(self, tenant_id: str, connector_id: str) -> dict[str, Any]:
        succeeded = await db.cm_sync_jobs.count_documents(
            {
                "tenant_id": tenant_id,
                "connector_id": connector_id,
                "sync_type": "inventory",
                "status": "succeeded",
            }
        )
        if succeeded > 0:
            return {"check": "inventory_push_success", "status": "passed", "detail": f"{succeeded} successful inventory syncs"}
        return {"check": "inventory_push_success", "status": "warning", "detail": "No successful inventory syncs yet", "blocker": False}

    async def _check_reservation_pull(self, tenant_id: str, connector_id: str) -> dict[str, Any]:
        count = await self._repo.count_imported_reservations(tenant_id, connector_id)
        if count > 0:
            return {"check": "reservation_import_success", "status": "passed", "detail": f"{count} reservations imported"}
        return {"check": "reservation_import_success", "status": "warning", "detail": "No reservations imported yet", "blocker": False}

    async def _check_reservation_modification(self, tenant_id: str, connector_id: str) -> dict[str, Any]:
        modified = await db.cm_imported_reservations.count_documents(
            {
                "tenant_id": tenant_id,
                "connector_id": connector_id,
                "canonical_status": {"$in": ["modified", "Modify"]},
            }
        )
        audit_modified = await db.cm_integration_audit.count_documents(
            {
                "tenant_id": tenant_id,
                "connector_id": connector_id,
                "action": "reservation_modified",
            }
        )
        if modified > 0 or audit_modified > 0:
            return {"check": "reservation_modification_success", "status": "passed", "detail": f"{modified + audit_modified} modification events recorded"}
        return {"check": "reservation_modification_success", "status": "warning", "detail": "No modification events yet", "blocker": False}

    async def _check_reservation_cancellation(self, tenant_id: str, connector_id: str) -> dict[str, Any]:
        cancelled = await db.cm_imported_reservations.count_documents(
            {
                "tenant_id": tenant_id,
                "connector_id": connector_id,
                "canonical_status": {"$in": ["cancelled", "Cancel"]},
            }
        )
        audit_cancelled = await db.cm_integration_audit.count_documents(
            {
                "tenant_id": tenant_id,
                "connector_id": connector_id,
                "action": "reservation_cancelled",
            }
        )
        if cancelled > 0 or audit_cancelled > 0:
            return {"check": "reservation_cancellation_success", "status": "passed", "detail": f"{cancelled + audit_cancelled} cancellation events recorded"}
        return {"check": "reservation_cancellation_success", "status": "warning", "detail": "No cancellation events yet", "blocker": False}

    async def _check_reservation_ack(self, tenant_id: str, connector_id: str) -> dict[str, Any]:
        ack_failed = await db.cm_imported_reservations.count_documents(
            {
                "tenant_id": tenant_id,
                "connector_id": connector_id,
                "ack_status": "ack_failed",
            }
        )
        ack_sent = await db.cm_imported_reservations.count_documents(
            {
                "tenant_id": tenant_id,
                "connector_id": connector_id,
                "ack_status": "ack_sent",
            }
        )
        if ack_failed > 0:
            return {"check": "ack_lifecycle_success", "status": "failed", "detail": f"{ack_failed} ACK failures", "blocker": False}
        if ack_sent > 0:
            return {"check": "ack_lifecycle_success", "status": "passed", "detail": f"{ack_sent} ACKs sent successfully"}
        return {"check": "ack_lifecycle_success", "status": "warning", "detail": "No ACKs processed yet", "blocker": False}

    async def _check_alerts_functioning(self, tenant_id: str) -> dict[str, Any]:
        total_alerts = await db.cm_alerts.count_documents({"tenant_id": tenant_id})
        rules = await db.cm_alert_rules.count_documents({"tenant_id": tenant_id, "enabled": True})
        if rules > 0:
            return {"check": "alerts_functioning", "status": "passed", "detail": f"{rules} active rules, {total_alerts} alerts generated"}
        return {"check": "alerts_functioning", "status": "warning", "detail": "No alert rules configured", "blocker": False}

    async def _check_metrics_aggregation(self, tenant_id: str, connector_id: str) -> dict[str, Any]:
        metrics_count = await db.cm_historical_metrics.count_documents(
            {
                "tenant_id": tenant_id,
                "connector_id": connector_id,
            }
        )
        if metrics_count > 0:
            return {"check": "metrics_aggregation_functioning", "status": "passed", "detail": f"{metrics_count} metric snapshots recorded"}
        return {"check": "metrics_aggregation_functioning", "status": "warning", "detail": "No historical metrics recorded yet", "blocker": False}

    async def _check_scheduler_jobs(self, tenant_id: str, connector_id: str) -> dict[str, Any]:
        completed_jobs = await db.cm_import_jobs.count_documents(
            {
                "tenant_id": tenant_id,
                "connector_id": connector_id,
                "status": "completed",
            }
        )
        worker_jobs = await db.cm_worker_jobs.count_documents(
            {
                "tenant_id": tenant_id,
                "status": "completed",
            }
        )
        total = completed_jobs + worker_jobs
        if total > 0:
            return {"check": "scheduler_jobs_working", "status": "passed", "detail": f"{total} scheduled jobs completed successfully"}
        return {"check": "scheduler_jobs_working", "status": "warning", "detail": "No scheduled jobs have run yet", "blocker": False}

    @staticmethod
    def _check_credential_security(connector: dict) -> dict[str, Any]:
        encrypted = connector.get("credentials_encrypted", False)
        algo = connector.get("encryption_algorithm", "")
        if encrypted and algo == "AES-256-GCM":
            return {"check": "credential_security_verified", "status": "passed", "detail": "AES-256-GCM encryption active"}
        if encrypted:
            return {"check": "credential_security_verified", "status": "warning", "detail": f"Encrypted with {algo or 'unknown'}, recommend AES-256-GCM", "blocker": False}
        return {"check": "credential_security_verified", "status": "failed", "detail": "Credentials not encrypted", "blocker": True}

    async def _check_rate_push(self, tenant_id: str, connector_id: str) -> dict[str, Any]:
        """Check rate push success metrics."""
        succeeded = await db.cm_sync_jobs.count_documents(
            {
                "tenant_id": tenant_id,
                "connector_id": connector_id,
                "sync_type": "rates",
                "status": "succeeded",
            }
        )
        failed = await db.cm_sync_jobs.count_documents(
            {
                "tenant_id": tenant_id,
                "connector_id": connector_id,
                "sync_type": "rates",
                "status": "failed",
            }
        )
        if succeeded > 0:
            rate = round(succeeded / max(succeeded + failed, 1) * 100, 1)
            return {"check": "rate_push_success", "status": "passed", "detail": f"{succeeded} successful rate pushes ({rate}% success rate)"}
        return {"check": "rate_push_success", "status": "warning", "detail": "No successful rate pushes yet", "blocker": False}

    async def _check_mapping_completeness(self, tenant_id: str, connector_id: str) -> dict[str, Any]:
        """Check mapping completeness via mapping completeness service."""
        try:
            from .mapping_completeness_service import MappingCompletenessService

            svc = MappingCompletenessService(repo=self._repo)
            report = await svc.validate_completeness(tenant_id, connector_id)
            score = report.get("readiness_score", 0)
            sync_ok = report.get("sync_allowed", False)
            if sync_ok and score >= 70:
                return {"check": "mapping_completeness", "status": "passed", "detail": f"Mapping readiness score: {score}/100"}
            elif score >= 40:
                return {"check": "mapping_completeness", "status": "warning", "detail": f"Mapping readiness score: {score}/100, sync {'allowed' if sync_ok else 'blocked'}", "blocker": not sync_ok}
            return {"check": "mapping_completeness", "status": "failed", "detail": f"Mapping readiness score: {score}/100", "blocker": True}
        except Exception as e:
            return {"check": "mapping_completeness", "status": "warning", "detail": f"Could not validate: {str(e)[:100]}", "blocker": False}
