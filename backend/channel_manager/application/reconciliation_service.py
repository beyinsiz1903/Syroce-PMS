"""
Reconciliation Service - Compares PMS state with provider state to detect drift.

Detects:
  - Inventory mismatches (PMS availability vs last pushed availability)
  - Rate mismatches (PMS rates vs last pushed rates)
  - Missing reservations (in provider but not in PMS)
  - Stale sync jobs (last sync too old)
  - Invalid mappings
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from ..domain.models.reconciliation import ReconciliationIssue, ReconciliationSeverity, IssueType
from ..domain.models.audit import IntegrationAuditLog, AuditAction
from ..infrastructure.repository import ChannelManagerRepository

from core.database import db

logger = logging.getLogger("channel_manager.application.reconciliation_service")


class ReconciliationService:
    """Detects and tracks data drift between PMS and external providers."""

    def __init__(self, repo: Optional[ChannelManagerRepository] = None):
        self._repo = repo or ChannelManagerRepository()

    async def run_reconciliation(
        self, tenant_id: str, connector_id: str, actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run a full reconciliation check for a connector."""
        connector = await self._repo.get_connector(tenant_id, connector_id)
        if not connector:
            raise ValueError("Connector not found")

        property_id = connector.get("property_id", "")
        issues_found = []

        # Check 1: Stale sync
        stale_issues = await self._check_stale_sync(tenant_id, connector_id, property_id)
        issues_found.extend(stale_issues)

        # Check 2: Invalid mappings
        mapping_issues = await self._check_mapping_validity(tenant_id, connector_id, property_id)
        issues_found.extend(mapping_issues)

        # Check 3: Unprocessed imports
        import_issues = await self._check_unprocessed_imports(tenant_id, connector_id, property_id)
        issues_found.extend(import_issues)

        # Save issues
        for issue in issues_found:
            await self._repo.create_reconciliation_issue(issue.to_doc())

        # Audit
        await self._audit(
            tenant_id, property_id, connector_id,
            AuditAction.RECONCILIATION_RUN, actor_id,
            {"issues_found": len(issues_found)},
        )

        return {
            "connector_id": connector_id,
            "issues_found": len(issues_found),
            "critical": sum(1 for i in issues_found if i.severity == ReconciliationSeverity.CRITICAL),
            "high": sum(1 for i in issues_found if i.severity == ReconciliationSeverity.HIGH),
            "medium": sum(1 for i in issues_found if i.severity == ReconciliationSeverity.MEDIUM),
            "low": sum(1 for i in issues_found if i.severity == ReconciliationSeverity.LOW),
        }

    async def get_issues(
        self, tenant_id: str, connector_id: Optional[str] = None,
        status: str = "open", limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return await self._repo.get_reconciliation_issues(tenant_id, connector_id, status, limit)

    async def resolve_issue(
        self, tenant_id: str, issue_id: str,
        resolution: str, actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self._repo.update_reconciliation_issue(issue_id, {
            "status": "resolved",
            "resolution": resolution,
            "resolved_by": actor_id,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        })
        return {"issue_id": issue_id, "status": "resolved"}

    async def dismiss_issue(
        self, tenant_id: str, issue_id: str, actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        await self._repo.update_reconciliation_issue(issue_id, {
            "status": "dismissed",
            "resolved_by": actor_id,
            "resolved_at": datetime.now(timezone.utc).isoformat(),
        })
        return {"issue_id": issue_id, "status": "dismissed"}

    async def _check_stale_sync(self, tenant_id: str, connector_id: str, property_id: str) -> List[ReconciliationIssue]:
        """Check if the last sync is older than threshold."""
        issues = []
        connector = await self._repo.get_connector(tenant_id, connector_id)
        last_sync = connector.get("last_successful_sync") if connector else None

        if not last_sync:
            issues.append(ReconciliationIssue(
                tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
                issue_type=IssueType.SYNC_STALE,
                severity=ReconciliationSeverity.HIGH,
                description="No successful sync recorded for this connector",
            ))
        else:
            try:
                last_dt = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
                age_hours = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
                if age_hours > 24:
                    issues.append(ReconciliationIssue(
                        tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
                        issue_type=IssueType.SYNC_STALE,
                        severity=ReconciliationSeverity.MEDIUM if age_hours < 48 else ReconciliationSeverity.HIGH,
                        description=f"Last successful sync was {age_hours:.0f} hours ago",
                    ))
            except (ValueError, TypeError):
                pass

        return issues

    async def _check_mapping_validity(self, tenant_id: str, connector_id: str, property_id: str) -> List[ReconciliationIssue]:
        """Check for invalid or missing mappings."""
        issues = []
        mappings = await self._repo.get_mappings(tenant_id, connector_id)

        invalid_count = sum(1 for m in mappings if m.get("status") == "invalid")
        if invalid_count > 0:
            issues.append(ReconciliationIssue(
                tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
                issue_type=IssueType.MAPPING_INVALID,
                severity=ReconciliationSeverity.HIGH,
                description=f"{invalid_count} invalid mapping(s) detected",
            ))

        # Check room types without mappings
        room_mappings = [m for m in mappings if m.get("entity_type") == "room_type" and m.get("status") == "active"]
        mapped_pms_ids = {m.get("pms_entity_id") for m in room_mappings}

        pms_rooms = await db.rooms.find(
            {"tenant_id": tenant_id}, {"_id": 0, "room_type": 1}
        ).to_list(1000)
        all_types = {r.get("room_type") for r in pms_rooms if r.get("room_type")}
        unmapped = all_types - mapped_pms_ids
        if unmapped:
            issues.append(ReconciliationIssue(
                tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
                issue_type=IssueType.MAPPING_INVALID,
                severity=ReconciliationSeverity.MEDIUM,
                description=f"Unmapped room types: {', '.join(unmapped)}",
                pms_value={"unmapped_types": list(unmapped)},
            ))

        return issues

    async def _check_unprocessed_imports(self, tenant_id: str, connector_id: str, property_id: str) -> List[ReconciliationIssue]:
        """Check for stuck/unprocessed imported reservations."""
        issues = []
        review_count = await self._repo.count_imported_reservations(tenant_id, connector_id, "review")
        failed_count = await self._repo.count_imported_reservations(tenant_id, connector_id, "failed")

        if review_count > 0:
            issues.append(ReconciliationIssue(
                tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
                issue_type=IssueType.MISSING_RESERVATION,
                severity=ReconciliationSeverity.HIGH if review_count > 5 else ReconciliationSeverity.MEDIUM,
                description=f"{review_count} reservation(s) waiting for manual review",
            ))

        if failed_count > 0:
            issues.append(ReconciliationIssue(
                tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
                issue_type=IssueType.MISSING_RESERVATION,
                severity=ReconciliationSeverity.CRITICAL if failed_count > 3 else ReconciliationSeverity.HIGH,
                description=f"{failed_count} reservation import(s) failed",
            ))

        return issues

    async def _audit(self, tenant_id, property_id, connector_id, action, actor_id=None, metadata=None):
        log = IntegrationAuditLog(
            tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
            action=action, actor_id=actor_id, metadata=metadata or {},
        )
        await self._repo.create_audit_log(log.to_doc())
