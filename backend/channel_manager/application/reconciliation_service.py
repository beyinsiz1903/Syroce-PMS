"""
Reconciliation Service - Detects data drift between PMS and external providers.

Issue Types:
  - inventory_mismatch: PMS availability != last pushed availability
  - rate_mismatch: PMS rate != last pushed rate
  - missing_reservation: In provider but not in PMS
  - stale_sync: Last sync too old
  - invalid_mapping: Mapping validation failed
  - ack_failed: Reservation acknowledgement failed
  - ack_pending_too_long: ACK pending > threshold
  - unprocessed_import: Reservations stuck in review/failed

Severity: critical > high > medium > low
Lifecycle: open -> investigating -> retrying -> resolved | dismissed
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional, List

from ..domain.models.reconciliation import (
    ReconciliationIssue, ReconciliationSeverity, IssueType,
    IssueStatus, SuggestedAction,
)
from ..domain.models.audit import IntegrationAuditLog, AuditAction
from ..infrastructure.repository import ChannelManagerRepository

from core.database import db

logger = logging.getLogger("channel_manager.application.reconciliation_service")

# Thresholds
STALE_SYNC_HOURS_MEDIUM = 24
STALE_SYNC_HOURS_HIGH = 48
ACK_PENDING_HOURS = 4
REVIEW_QUEUE_HIGH = 5
FAILED_IMPORT_CRITICAL = 3


class ReconciliationService:
    """Detects and tracks data drift between PMS and external providers."""

    def __init__(self, repo: Optional[ChannelManagerRepository] = None):
        self._repo = repo or ChannelManagerRepository()

    # ------------------------------------------------------------------ #
    #  Run Full Reconciliation                                             #
    # ------------------------------------------------------------------ #

    async def run_reconciliation(
        self, tenant_id: str, connector_id: str, actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run a full reconciliation check for a connector."""
        connector = await self._repo.get_connector(tenant_id, connector_id)
        if not connector:
            raise ValueError("Connector not found")

        property_id = connector.get("property_id", "")
        issues_found: List[ReconciliationIssue] = []

        # Run all checks
        issues_found.extend(await self._check_stale_sync(tenant_id, connector_id, property_id))
        issues_found.extend(await self._check_mapping_validity(tenant_id, connector_id, property_id))
        issues_found.extend(await self._check_unprocessed_imports(tenant_id, connector_id, property_id))
        issues_found.extend(await self._check_ack_failures(tenant_id, connector_id, property_id))
        issues_found.extend(await self._check_ack_pending(tenant_id, connector_id, property_id))
        issues_found.extend(await self._check_inventory_mismatch(tenant_id, connector_id, property_id))
        issues_found.extend(await self._check_rate_mismatch(tenant_id, connector_id, property_id))

        # Persist issues
        for issue in issues_found:
            await self._repo.create_reconciliation_issue(issue.to_doc())

        # Audit
        await self._audit(
            tenant_id, property_id, connector_id,
            AuditAction.RECONCILIATION_RUN, actor_id,
            {"issues_found": len(issues_found)},
        )

        severity_counts = {
            "critical": sum(1 for i in issues_found if i.severity == ReconciliationSeverity.CRITICAL),
            "high": sum(1 for i in issues_found if i.severity == ReconciliationSeverity.HIGH),
            "medium": sum(1 for i in issues_found if i.severity == ReconciliationSeverity.MEDIUM),
            "low": sum(1 for i in issues_found if i.severity == ReconciliationSeverity.LOW),
        }

        return {
            "connector_id": connector_id,
            "property_id": property_id,
            "issues_found": len(issues_found),
            "severity_breakdown": severity_counts,
            "issue_types": list({i.issue_type.value for i in issues_found}),
            "run_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------ #
    #  Issue CRUD                                                          #
    # ------------------------------------------------------------------ #

    async def get_issues(
        self, tenant_id: str, connector_id: Optional[str] = None,
        status: str = "open", limit: int = 100,
    ) -> List[Dict[str, Any]]:
        return await self._repo.get_reconciliation_issues(tenant_id, connector_id, status, limit)

    async def get_issue_detail(self, tenant_id: str, issue_id: str) -> Optional[Dict[str, Any]]:
        return await self._repo.get_reconciliation_issue(tenant_id, issue_id)

    async def update_issue_status(
        self, tenant_id: str, issue_id: str,
        new_status: str, actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Transition issue status (investigating, retrying)."""
        issue = await self._repo.get_reconciliation_issue(tenant_id, issue_id)
        if not issue:
            raise ValueError("Issue not found")

        valid_transitions = {
            "open": ["investigating", "retrying", "resolved", "dismissed"],
            "investigating": ["retrying", "resolved", "dismissed"],
            "retrying": ["resolved", "dismissed", "open"],
        }
        current = issue.get("status", "open")
        if new_status not in valid_transitions.get(current, []):
            raise ValueError(f"Cannot transition from '{current}' to '{new_status}'")

        updates = {
            "status": new_status,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        await self._repo.update_reconciliation_issue(issue_id, updates)
        return {"issue_id": issue_id, "status": new_status}

    async def resolve_issue(
        self, tenant_id: str, issue_id: str,
        resolution: str, actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        await self._repo.update_reconciliation_issue(issue_id, {
            "status": IssueStatus.RESOLVED.value,
            "resolution": resolution,
            "resolved_by": actor_id,
            "resolved_at": now,
            "updated_at": now,
        })
        issue = await self._repo.get_reconciliation_issue(tenant_id, issue_id)
        if issue:
            await self._audit(
                tenant_id, issue.get("property_id", ""), issue.get("connector_id", ""),
                AuditAction.RECONCILIATION_RESOLVED, actor_id,
                {"issue_id": issue_id, "resolution": resolution},
            )
        return {"issue_id": issue_id, "status": "resolved"}

    async def dismiss_issue(
        self, tenant_id: str, issue_id: str,
        reason: str = "", actor_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        now = datetime.now(timezone.utc).isoformat()
        await self._repo.update_reconciliation_issue(issue_id, {
            "status": IssueStatus.DISMISSED.value,
            "dismiss_reason": reason,
            "resolved_by": actor_id,
            "resolved_at": now,
            "updated_at": now,
        })
        return {"issue_id": issue_id, "status": "dismissed"}

    # ------------------------------------------------------------------ #
    #  Issue Summary / Dashboard                                           #
    # ------------------------------------------------------------------ #

    async def get_issue_summary(
        self, tenant_id: str, connector_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Aggregate issue counts by type and severity for dashboard."""
        return await self._repo.get_reconciliation_summary(tenant_id, connector_id)

    async def get_health_score(
        self, tenant_id: str, connector_id: str,
    ) -> Dict[str, Any]:
        """
        Compute an operational health score (0-100) for a connector.

        Factors:
          - Open critical/high issues (heavy penalty)
          - Stale sync age
          - Failed sync ratio
          - Unprocessed imports
        """
        summary = await self._repo.get_reconciliation_summary(tenant_id, connector_id)
        connector = await self._repo.get_connector(tenant_id, connector_id)

        score = 100
        details = {}

        # Penalty for open issues by severity
        by_severity = summary.get("by_severity", {})
        critical_count = by_severity.get("critical", 0)
        high_count = by_severity.get("high", 0)
        medium_count = by_severity.get("medium", 0)
        low_count = by_severity.get("low", 0)

        issue_penalty = critical_count * 20 + high_count * 10 + medium_count * 3 + low_count * 1
        score -= min(issue_penalty, 60)
        details["issue_penalty"] = issue_penalty

        # Penalty for stale sync
        if connector:
            last_sync = connector.get("last_successful_sync")
            if not last_sync:
                score -= 20
                details["sync_staleness"] = "no_successful_sync"
            else:
                try:
                    last_dt = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
                    age_hours = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
                    if age_hours > 48:
                        score -= 15
                        details["sync_staleness"] = f"{age_hours:.0f}h"
                    elif age_hours > 24:
                        score -= 5
                        details["sync_staleness"] = f"{age_hours:.0f}h"
                    else:
                        details["sync_staleness"] = "healthy"
                except (ValueError, TypeError):
                    pass

            # Penalty for consecutive failures
            consecutive = connector.get("consecutive_failures", 0)
            if consecutive >= 5:
                score -= 15
            elif consecutive >= 3:
                score -= 8
            elif consecutive >= 1:
                score -= 3
            details["consecutive_failures"] = consecutive

        score = max(0, min(100, score))

        if score >= 80:
            status = "healthy"
        elif score >= 50:
            status = "degraded"
        else:
            status = "critical"

        return {
            "connector_id": connector_id,
            "health_score": score,
            "status": status,
            "open_issues": summary.get("total_open", 0),
            "by_severity": by_severity,
            "by_type": summary.get("by_type", {}),
            "details": details,
            "calculated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ------------------------------------------------------------------ #
    #  Check: Stale Sync                                                   #
    # ------------------------------------------------------------------ #

    async def _check_stale_sync(
        self, tenant_id: str, connector_id: str, property_id: str,
    ) -> List[ReconciliationIssue]:
        issues = []
        connector = await self._repo.get_connector(tenant_id, connector_id)
        last_sync = connector.get("last_successful_sync") if connector else None

        if not last_sync:
            issues.append(ReconciliationIssue(
                tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
                issue_type=IssueType.STALE_SYNC,
                severity=ReconciliationSeverity.HIGH,
                description="Bu connector icin basarili senkronizasyon kaydi yok",
                suggested_actions=[SuggestedAction.RETRY_SYNC.value],
                evidence_payload={"last_sync": None},
            ))
        else:
            try:
                last_dt = datetime.fromisoformat(last_sync.replace("Z", "+00:00"))
                age_hours = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
                if age_hours > STALE_SYNC_HOURS_HIGH:
                    issues.append(ReconciliationIssue(
                        tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
                        issue_type=IssueType.STALE_SYNC,
                        severity=ReconciliationSeverity.HIGH,
                        description=f"Son basarili senkronizasyon {age_hours:.0f} saat once",
                        suggested_actions=[SuggestedAction.RETRY_SYNC.value],
                        evidence_payload={"last_sync": last_sync, "age_hours": round(age_hours, 1)},
                    ))
                elif age_hours > STALE_SYNC_HOURS_MEDIUM:
                    issues.append(ReconciliationIssue(
                        tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
                        issue_type=IssueType.STALE_SYNC,
                        severity=ReconciliationSeverity.MEDIUM,
                        description=f"Son basarili senkronizasyon {age_hours:.0f} saat once",
                        suggested_actions=[SuggestedAction.RETRY_SYNC.value],
                        evidence_payload={"last_sync": last_sync, "age_hours": round(age_hours, 1)},
                    ))
            except (ValueError, TypeError):
                pass

        return issues

    # ------------------------------------------------------------------ #
    #  Check: Mapping Validity                                             #
    # ------------------------------------------------------------------ #

    async def _check_mapping_validity(
        self, tenant_id: str, connector_id: str, property_id: str,
    ) -> List[ReconciliationIssue]:
        issues = []
        mappings = await self._repo.get_mappings(tenant_id, connector_id)

        # Invalid mappings
        invalid_mappings = [m for m in mappings if m.get("validation_status") == "invalid"]
        for m in invalid_mappings:
            issues.append(ReconciliationIssue(
                tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
                issue_type=IssueType.INVALID_MAPPING,
                severity=ReconciliationSeverity.HIGH,
                entity_type=m.get("entity_type", ""),
                entity_id=m.get("id", ""),
                description=m.get("invalid_reason", f"Gecersiz mapping: {m.get('entity_type')} ({m.get('id', '')[:8]}...)"),
                related_mapping_ids=[m.get("id", "")],
                suggested_actions=[SuggestedAction.REVALIDATE_MAPPING.value],
                evidence_payload={
                    "mapping_id": m.get("id"),
                    "entity_type": m.get("entity_type"),
                    "pms_entity_id": m.get("pms_entity_id"),
                    "external_entity_id": m.get("external_entity_id"),
                    "invalid_reason": m.get("invalid_reason"),
                },
            ))

        # Unmapped room types
        room_mappings = [m for m in mappings if m.get("entity_type") == "room_type" and m.get("status") == "active"]
        mapped_pms_ids = {m.get("pms_entity_id") for m in room_mappings}
        pms_rooms = await db.rooms.find(
            {"tenant_id": tenant_id, "property_id": property_id, "status": {"$ne": "out_of_service"}},
            {"_id": 0, "room_type": 1},
        ).to_list(1000)
        all_types = {r.get("room_type") for r in pms_rooms if r.get("room_type")}
        unmapped = all_types - mapped_pms_ids
        if unmapped:
            issues.append(ReconciliationIssue(
                tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
                issue_type=IssueType.INVALID_MAPPING,
                severity=ReconciliationSeverity.MEDIUM,
                description=f"Eslestirilmemis oda tipleri: {', '.join(unmapped)}",
                suggested_actions=[SuggestedAction.REVALIDATE_MAPPING.value],
                evidence_payload={"unmapped_room_types": list(unmapped)},
            ))

        return issues

    # ------------------------------------------------------------------ #
    #  Check: Unprocessed Imports                                          #
    # ------------------------------------------------------------------ #

    async def _check_unprocessed_imports(
        self, tenant_id: str, connector_id: str, property_id: str,
    ) -> List[ReconciliationIssue]:
        issues = []
        review_count = await self._repo.count_imported_reservations(tenant_id, connector_id, "review")
        failed_count = await self._repo.count_imported_reservations(tenant_id, connector_id, "failed")

        if review_count > 0:
            severity = ReconciliationSeverity.HIGH if review_count > REVIEW_QUEUE_HIGH else ReconciliationSeverity.MEDIUM
            issues.append(ReconciliationIssue(
                tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
                issue_type=IssueType.UNPROCESSED_IMPORT,
                severity=severity,
                description=f"{review_count} rezervasyon manuel inceleme bekliyor",
                suggested_actions=[SuggestedAction.SEND_TO_REVIEW.value],
                evidence_payload={"review_count": review_count},
            ))

        if failed_count > 0:
            severity = ReconciliationSeverity.CRITICAL if failed_count > FAILED_IMPORT_CRITICAL else ReconciliationSeverity.HIGH
            issues.append(ReconciliationIssue(
                tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
                issue_type=IssueType.UNPROCESSED_IMPORT,
                severity=severity,
                description=f"{failed_count} rezervasyon import'u basarisiz",
                suggested_actions=[SuggestedAction.RETRY_SYNC.value, SuggestedAction.SEND_TO_REVIEW.value],
                evidence_payload={"failed_count": failed_count},
            ))

        return issues

    # ------------------------------------------------------------------ #
    #  Check: ACK Failures                                                 #
    # ------------------------------------------------------------------ #

    async def _check_ack_failures(
        self, tenant_id: str, connector_id: str, property_id: str,
    ) -> List[ReconciliationIssue]:
        issues = []
        ack_failed = await db.cm_imported_reservations.count_documents({
            "tenant_id": tenant_id,
            "connector_id": connector_id,
            "ack_status": "ack_failed",
        })
        if ack_failed > 0:
            issues.append(ReconciliationIssue(
                tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
                issue_type=IssueType.ACK_FAILED,
                severity=ReconciliationSeverity.HIGH,
                description=f"{ack_failed} rezervasyon onay gonderilemedi (ACK failed)",
                suggested_actions=[SuggestedAction.RETRY_ACK.value],
                evidence_payload={"ack_failed_count": ack_failed},
            ))
        return issues

    # ------------------------------------------------------------------ #
    #  Check: ACK Pending Too Long                                         #
    # ------------------------------------------------------------------ #

    async def _check_ack_pending(
        self, tenant_id: str, connector_id: str, property_id: str,
    ) -> List[ReconciliationIssue]:
        issues = []
        threshold = (datetime.now(timezone.utc) - timedelta(hours=ACK_PENDING_HOURS)).isoformat()
        ack_pending_old = await db.cm_imported_reservations.count_documents({
            "tenant_id": tenant_id,
            "connector_id": connector_id,
            "ack_status": "ack_pending",
            "created_at": {"$lt": threshold},
        })
        if ack_pending_old > 0:
            issues.append(ReconciliationIssue(
                tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
                issue_type=IssueType.ACK_PENDING_TOO_LONG,
                severity=ReconciliationSeverity.MEDIUM,
                description=f"{ack_pending_old} rezervasyon {ACK_PENDING_HOURS} saatten fazla onay bekliyor",
                suggested_actions=[SuggestedAction.RETRY_ACK.value],
                evidence_payload={"ack_pending_count": ack_pending_old, "threshold_hours": ACK_PENDING_HOURS},
            ))
        return issues

    # ------------------------------------------------------------------ #
    #  Check: Inventory Mismatch                                           #
    # ------------------------------------------------------------------ #

    async def _check_inventory_mismatch(
        self, tenant_id: str, connector_id: str, property_id: str,
    ) -> List[ReconciliationIssue]:
        """Compare PMS availability with last synced snapshot for today + 7 days."""
        issues = []
        from ..application.mapping_service import MappingService
        mapping_svc = MappingService(self._repo)
        room_lookup = await mapping_svc.get_mapping_lookup(tenant_id, connector_id, "room_type")
        if not room_lookup:
            return issues

        today = datetime.now(timezone.utc).date()
        rooms = await db.rooms.find(
            {"tenant_id": tenant_id, "property_id": property_id, "status": {"$ne": "out_of_service"}},
            {"_id": 0, "room_type": 1},
        ).to_list(1000)
        room_type_counts: Dict[str, int] = {}
        for r in rooms:
            rt = r.get("room_type", "")
            if rt and rt in room_lookup:
                room_type_counts[rt] = room_type_counts.get(rt, 0) + 1

        mismatches = 0
        for day_offset in range(7):
            check_date = (today + timedelta(days=day_offset)).isoformat()
            bookings = await db.bookings.find({
                "tenant_id": tenant_id,
                "check_in": {"$lte": check_date},
                "check_out": {"$gt": check_date},
                "status": {"$nin": ["cancelled", "no_show"]},
            }, {"_id": 0, "room_type": 1}).to_list(5000)

            for rt, total in room_type_counts.items():
                occupied = sum(1 for b in bookings if b.get("room_type") == rt)
                pms_available = max(0, total - occupied)

                snapshot = await self._repo.get_sync_snapshot(tenant_id, connector_id, rt, check_date)
                if snapshot and snapshot.get("available") is not None:
                    synced_available = snapshot["available"]
                    if pms_available != synced_available:
                        mismatches += 1

        if mismatches > 0:
            severity = ReconciliationSeverity.CRITICAL if mismatches > 10 else ReconciliationSeverity.HIGH
            issues.append(ReconciliationIssue(
                tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
                issue_type=IssueType.INVENTORY_MISMATCH,
                severity=severity,
                description=f"Sonraki 7 gun icinde {mismatches} envanter uyumsuzlugu tespit edildi",
                suggested_actions=[SuggestedAction.RETRY_SYNC.value],
                evidence_payload={"mismatch_count": mismatches, "check_range_days": 7},
            ))
        return issues

    # ------------------------------------------------------------------ #
    #  Check: Rate Mismatch                                                #
    # ------------------------------------------------------------------ #

    async def _check_rate_mismatch(
        self, tenant_id: str, connector_id: str, property_id: str,
    ) -> List[ReconciliationIssue]:
        """Compare PMS rates with last synced snapshot for today + 7 days."""
        issues = []
        from ..application.mapping_service import MappingService
        mapping_svc = MappingService(self._repo)
        room_lookup = await mapping_svc.get_mapping_lookup(tenant_id, connector_id, "room_type")
        rate_lookup = await mapping_svc.get_mapping_lookup(tenant_id, connector_id, "rate_plan")
        if not room_lookup or not rate_lookup:
            return issues

        today = datetime.now(timezone.utc).date()
        end_date = (today + timedelta(days=7)).isoformat()

        rates = await db.rate_overrides.find({
            "tenant_id": tenant_id,
            "date": {"$gte": today.isoformat(), "$lte": end_date},
        }, {"_id": 0}).to_list(5000)

        mismatches = 0
        for r in rates:
            rt_id = r.get("room_type_id", "")
            rp_id = r.get("rate_plan_id", "")
            if rt_id not in room_lookup or rp_id not in rate_lookup:
                continue
            date = r.get("date", "")
            current_rate = r.get("sell_rate", 0.0)
            snapshot = await self._repo.get_sync_snapshot(tenant_id, connector_id, rt_id, date)
            if snapshot and snapshot.get("sell_rate") is not None:
                if abs(current_rate - snapshot["sell_rate"]) > 0.01:
                    mismatches += 1

        if mismatches > 0:
            severity = ReconciliationSeverity.HIGH if mismatches > 5 else ReconciliationSeverity.MEDIUM
            issues.append(ReconciliationIssue(
                tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
                issue_type=IssueType.RATE_MISMATCH,
                severity=severity,
                description=f"Sonraki 7 gun icinde {mismatches} fiyat uyumsuzlugu tespit edildi",
                suggested_actions=[SuggestedAction.RETRY_SYNC.value],
                evidence_payload={"mismatch_count": mismatches, "check_range_days": 7},
            ))
        return issues

    # ------------------------------------------------------------------ #
    #  Create Issue (from external callers, e.g., push failures)           #
    # ------------------------------------------------------------------ #

    async def create_issue(
        self,
        tenant_id: str,
        property_id: str,
        connector_id: str,
        issue_type: str,
        severity: str,
        description: str,
        suggested_actions: Optional[List[str]] = None,
        evidence_payload: Optional[Dict[str, Any]] = None,
        related_sync_job_ids: Optional[List[str]] = None,
        related_mapping_ids: Optional[List[str]] = None,
        related_reservation_ids: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Create a reconciliation issue from external callers (e.g., push failure)."""
        issue = ReconciliationIssue(
            tenant_id=tenant_id,
            property_id=property_id,
            connector_id=connector_id,
            issue_type=IssueType(issue_type),
            severity=ReconciliationSeverity(severity),
            description=description,
            suggested_actions=suggested_actions or [],
            evidence_payload=evidence_payload,
            related_sync_job_ids=related_sync_job_ids or [],
            related_mapping_ids=related_mapping_ids or [],
            related_reservation_ids=related_reservation_ids or [],
        )
        await self._repo.create_reconciliation_issue(issue.to_doc())
        return issue.to_doc()

    # ------------------------------------------------------------------ #
    #  Audit                                                               #
    # ------------------------------------------------------------------ #

    async def _audit(self, tenant_id, property_id, connector_id, action, actor_id=None, metadata=None):
        log = IntegrationAuditLog(
            tenant_id=tenant_id, property_id=property_id, connector_id=connector_id,
            action=action, actor_id=actor_id, metadata=metadata or {},
        )
        await self._repo.create_audit_log(log.to_doc())
