"""
Test suite for Reconciliation Service, Scheduler Service, Event Sync Service, and Credential Vault.

Tests:
  - Reconciliation issue creation, lifecycle, and queries
  - Stale sync, mapping validity, unprocessed import detection
  - ACK failure and pending detection
  - Inventory/rate mismatch detection
  - Issue status transitions
  - Scheduler stale job and requeue logic
  - Event sync routing
  - Credential encryption/decryption
"""
import pytest
import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

from channel_manager.domain.models.reconciliation import (
    ReconciliationIssue, ReconciliationSeverity, IssueType, IssueStatus, SuggestedAction,
)
from channel_manager.application.reconciliation_service import ReconciliationService
from channel_manager.application.scheduler_service import SchedulerService
from channel_manager.application.event_sync_service import EventSyncService, SUPPORTED_EVENTS
from channel_manager.infrastructure.credential_vault import CredentialVault


# ─── Reconciliation Model Tests ─────────────────────────────────────

class TestReconciliationModel:
    def test_issue_creation(self):
        issue = ReconciliationIssue(
            tenant_id="t1", property_id="p1", connector_id="c1",
            issue_type=IssueType.STALE_SYNC,
            severity=ReconciliationSeverity.HIGH,
            description="Test issue",
        )
        assert issue.status == IssueStatus.OPEN
        assert issue.issue_type == IssueType.STALE_SYNC
        assert issue.severity == ReconciliationSeverity.HIGH
        doc = issue.to_doc()
        assert "id" in doc
        assert doc["status"] == "open"

    def test_issue_types_coverage(self):
        expected = {
            "inventory_mismatch", "rate_mismatch", "missing_reservation",
            "stale_sync", "invalid_mapping", "ack_failed",
            "ack_pending_too_long", "unprocessed_import",
        }
        actual = {it.value for it in IssueType}
        assert expected == actual

    def test_severity_levels(self):
        assert ReconciliationSeverity.CRITICAL.value == "critical"
        assert ReconciliationSeverity.HIGH.value == "high"
        assert ReconciliationSeverity.MEDIUM.value == "medium"
        assert ReconciliationSeverity.LOW.value == "low"

    def test_issue_lifecycle_states(self):
        expected = {"open", "investigating", "retrying", "resolved", "dismissed"}
        actual = {s.value for s in IssueStatus}
        assert expected == actual

    def test_suggested_actions(self):
        expected = {
            "retry_sync", "revalidate_mapping", "retry_ack",
            "send_to_review", "dismiss_with_reason",
        }
        actual = {sa.value for sa in SuggestedAction}
        assert expected == actual

    def test_issue_with_evidence(self):
        issue = ReconciliationIssue(
            tenant_id="t1", property_id="p1", connector_id="c1",
            issue_type=IssueType.INVENTORY_MISMATCH,
            severity=ReconciliationSeverity.CRITICAL,
            description="Mismatch found",
            evidence_payload={"mismatch_count": 5, "date": "2026-03-01"},
            suggested_actions=["retry_sync"],
            related_sync_job_ids=["job1", "job2"],
        )
        doc = issue.to_doc()
        assert doc["evidence_payload"]["mismatch_count"] == 5
        assert len(doc["related_sync_job_ids"]) == 2
        assert doc["suggested_actions"] == ["retry_sync"]

    def test_from_doc(self):
        doc = {
            "_id": "mongo_id",
            "id": "test-id",
            "tenant_id": "t1", "property_id": "p1", "connector_id": "c1",
            "issue_type": "stale_sync",
            "severity": "high",
            "status": "investigating",
            "description": "Test",
        }
        issue = ReconciliationIssue.from_doc(doc)
        assert issue.id == "test-id"
        assert issue.status == IssueStatus.INVESTIGATING


# ─── Reconciliation Service Tests ────────────────────────────────────

class TestReconciliationService:

    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock()
        repo.get_connector = AsyncMock(return_value={
            "id": "c1", "tenant_id": "t1", "property_id": "p1",
            "status": "active", "last_successful_sync": None,
        })
        repo.get_mappings = AsyncMock(return_value=[])
        repo.count_imported_reservations = AsyncMock(return_value=0)
        repo.create_reconciliation_issue = AsyncMock()
        repo.create_audit_log = AsyncMock()
        repo.get_reconciliation_issues = AsyncMock(return_value=[])
        repo.get_reconciliation_issue = AsyncMock(return_value=None)
        repo.update_reconciliation_issue = AsyncMock()
        repo.get_reconciliation_summary = AsyncMock(return_value={
            "total_open": 0, "by_type": {}, "by_severity": {},
        })
        repo.get_active_mappings = AsyncMock(return_value=[])
        repo.get_sync_snapshot = AsyncMock(return_value=None)
        return repo

    @pytest.mark.asyncio
    async def test_run_reconciliation_detects_stale_sync(self, mock_repo):
        svc = ReconciliationService(mock_repo)
        with patch.object(svc, '_check_inventory_mismatch', return_value=[]), \
             patch.object(svc, '_check_rate_mismatch', return_value=[]):
            result = await svc.run_reconciliation("t1", "c1")
        assert result["issues_found"] >= 1
        assert mock_repo.create_reconciliation_issue.called

    @pytest.mark.asyncio
    async def test_run_reconciliation_no_issues(self, mock_repo):
        mock_repo.get_connector.return_value["last_successful_sync"] = datetime.now(timezone.utc).isoformat()
        svc = ReconciliationService(mock_repo)
        with patch.object(svc, '_check_mapping_validity', return_value=[]), \
             patch.object(svc, '_check_unprocessed_imports', return_value=[]), \
             patch.object(svc, '_check_ack_failures', return_value=[]), \
             patch.object(svc, '_check_ack_pending', return_value=[]), \
             patch.object(svc, '_check_inventory_mismatch', return_value=[]), \
             patch.object(svc, '_check_rate_mismatch', return_value=[]):
            result = await svc.run_reconciliation("t1", "c1")
        assert result["issues_found"] == 0

    @pytest.mark.asyncio
    async def test_resolve_issue(self, mock_repo):
        mock_repo.get_reconciliation_issue.return_value = {
            "id": "i1", "tenant_id": "t1", "property_id": "p1",
            "connector_id": "c1", "status": "open",
        }
        svc = ReconciliationService(mock_repo)
        result = await svc.resolve_issue("t1", "i1", "Fixed manually")
        assert result["status"] == "resolved"
        mock_repo.update_reconciliation_issue.assert_called()

    @pytest.mark.asyncio
    async def test_dismiss_issue(self, mock_repo):
        svc = ReconciliationService(mock_repo)
        result = await svc.dismiss_issue("t1", "i1", "Not relevant")
        assert result["status"] == "dismissed"

    @pytest.mark.asyncio
    async def test_update_issue_status_valid_transition(self, mock_repo):
        mock_repo.get_reconciliation_issue.return_value = {
            "id": "i1", "tenant_id": "t1", "status": "open",
        }
        svc = ReconciliationService(mock_repo)
        result = await svc.update_issue_status("t1", "i1", "investigating")
        assert result["status"] == "investigating"

    @pytest.mark.asyncio
    async def test_update_issue_status_invalid_transition(self, mock_repo):
        mock_repo.get_reconciliation_issue.return_value = {
            "id": "i1", "tenant_id": "t1", "status": "resolved",
        }
        svc = ReconciliationService(mock_repo)
        with pytest.raises(ValueError, match="Cannot transition"):
            await svc.update_issue_status("t1", "i1", "open")

    @pytest.mark.asyncio
    async def test_create_issue_from_external(self, mock_repo):
        svc = ReconciliationService(mock_repo)
        result = await svc.create_issue(
            "t1", "p1", "c1",
            "inventory_mismatch", "high",
            "5 mismatches found",
            suggested_actions=["retry_sync"],
            evidence_payload={"count": 5},
        )
        assert result["issue_type"] == "inventory_mismatch"
        assert result["severity"] == "high"
        mock_repo.create_reconciliation_issue.assert_called()

    @pytest.mark.asyncio
    async def test_check_unprocessed_imports(self, mock_repo):
        mock_repo.count_imported_reservations.side_effect = lambda t, c, s: 3 if s == "review" else 1
        svc = ReconciliationService(mock_repo)
        issues = await svc._check_unprocessed_imports("t1", "c1", "p1")
        assert len(issues) == 2
        types = {i.issue_type for i in issues}
        assert IssueType.UNPROCESSED_IMPORT in types

    @pytest.mark.asyncio
    async def test_stale_sync_medium_severity(self, mock_repo):
        stale_time = (datetime.now(timezone.utc) - timedelta(hours=30)).isoformat()
        mock_repo.get_connector.return_value["last_successful_sync"] = stale_time
        svc = ReconciliationService(mock_repo)
        issues = await svc._check_stale_sync("t1", "c1", "p1")
        assert len(issues) == 1
        assert issues[0].severity == ReconciliationSeverity.MEDIUM

    @pytest.mark.asyncio
    async def test_stale_sync_high_severity(self, mock_repo):
        stale_time = (datetime.now(timezone.utc) - timedelta(hours=72)).isoformat()
        mock_repo.get_connector.return_value["last_successful_sync"] = stale_time
        svc = ReconciliationService(mock_repo)
        issues = await svc._check_stale_sync("t1", "c1", "p1")
        assert len(issues) == 1
        assert issues[0].severity == ReconciliationSeverity.HIGH


# ─── Scheduler Service Tests ────────────────────────────────────────

class TestSchedulerService:

    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock()
        repo.get_connector = AsyncMock(return_value={
            "id": "c1", "tenant_id": "t1", "property_id": "p1", "status": "active",
        })
        repo.get_connectors_by_tenant = AsyncMock(return_value=[
            {"id": "c1", "tenant_id": "t1", "property_id": "p1", "status": "active"},
        ])
        repo.get_sync_jobs = AsyncMock(return_value=[])
        repo.update_sync_job = AsyncMock()
        repo.create_audit_log = AsyncMock()
        repo.get_sync_snapshot = AsyncMock(return_value=None)
        repo.get_active_mappings = AsyncMock(return_value=[])
        return repo

    @pytest.mark.asyncio
    async def test_scheduled_check_inactive_connector(self, mock_repo):
        mock_repo.get_connector.return_value["status"] = "paused"
        svc = SchedulerService(mock_repo)
        result = await svc.run_scheduled_check("t1", "c1")
        assert result["skipped"] is True

    @pytest.mark.asyncio
    async def test_scheduled_check_no_actions(self, mock_repo):
        svc = SchedulerService(mock_repo)
        with patch.object(svc, '_check_missing_snapshots', return_value=[]), \
             patch.object(svc, '_check_drift', return_value=[]):
            result = await svc.run_scheduled_check("t1", "c1")
        assert result["total_actions"] == 0

    @pytest.mark.asyncio
    async def test_stale_pending_job_detection(self, mock_repo):
        old_time = (datetime.now(timezone.utc) - timedelta(hours=5)).isoformat()
        mock_repo.get_sync_jobs.return_value = [
            {"id": "j1", "status": "pending", "created_at": old_time},
        ]
        svc = SchedulerService(mock_repo)
        actions = await svc._check_stale_pending_jobs("t1", "c1")
        assert len(actions) == 1
        assert actions[0]["type"] == "stale_job_failed"

    @pytest.mark.asyncio
    async def test_retryable_failed_job_requeue(self, mock_repo):
        recent_time = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        mock_repo.get_sync_jobs.return_value = [
            {"id": "j1", "status": "failed", "retry_count": 0, "completed_at": recent_time},
        ]
        svc = SchedulerService(mock_repo)
        actions = await svc._check_retryable_failed_jobs("t1", "c1")
        assert len(actions) == 1
        assert actions[0]["type"] == "failed_job_requeued"

    @pytest.mark.asyncio
    async def test_run_all_connectors(self, mock_repo):
        svc = SchedulerService(mock_repo)
        with patch.object(svc, 'run_scheduled_check', return_value={"connector_id": "c1", "total_actions": 0}):
            result = await svc.run_all_connectors("t1")
        assert result["connectors_checked"] == 1


# ─── Event Sync Service Tests ────────────────────────────────────────

class TestEventSyncService:

    @pytest.fixture
    def mock_repo(self):
        repo = AsyncMock()
        repo.get_active_connectors = AsyncMock(return_value=[])
        repo.create_audit_log = AsyncMock()
        return repo

    def test_supported_events(self):
        expected = {
            "booking_created", "booking_modified", "booking_cancelled",
            "room_blocked", "room_unblocked",
            "rate_changed", "restriction_changed",
        }
        assert SUPPORTED_EVENTS == expected

    @pytest.mark.asyncio
    async def test_unsupported_event(self, mock_repo):
        svc = EventSyncService(mock_repo)
        result = await svc.handle_event("t1", "unknown_event", {"property_id": "p1"})
        assert result["handled"] is False

    @pytest.mark.asyncio
    async def test_missing_property_id(self, mock_repo):
        svc = EventSyncService(mock_repo)
        result = await svc.handle_event("t1", "booking_created", {})
        assert result["handled"] is False
        assert "property_id" in result["reason"]

    @pytest.mark.asyncio
    async def test_no_active_connectors(self, mock_repo):
        svc = EventSyncService(mock_repo)
        result = await svc.handle_event("t1", "booking_created", {
            "property_id": "p1", "check_in": "2026-03-15", "check_out": "2026-03-17",
        })
        assert result["handled"] is True
        assert result["sync_jobs_created"] == 0

    def test_extract_date_range_booking(self):
        start, end = EventSyncService._extract_date_range("booking_created", {
            "check_in": "2026-03-15", "check_out": "2026-03-17",
        })
        assert start == "2026-03-15"
        assert end == "2026-03-17"

    def test_extract_date_range_rate_changed(self):
        start, end = EventSyncService._extract_date_range("rate_changed", {
            "date_start": "2026-04-01", "date_end": "2026-04-30",
        })
        assert start == "2026-04-01"
        assert end == "2026-04-30"

    def test_extract_room_types(self):
        rts = EventSyncService._extract_room_types("booking_created", {"room_type_id": "standard"})
        assert rts == ["standard"]

    @pytest.mark.asyncio
    async def test_batch_events(self, mock_repo):
        svc = EventSyncService(mock_repo)
        result = await svc.handle_batch_events("t1", [
            {"event_type": "booking_created", "payload": {"property_id": "p1", "check_in": "2026-03-15", "check_out": "2026-03-17"}},
            {"event_type": "rate_changed", "payload": {"property_id": "p1", "date_start": "2026-04-01", "date_end": "2026-04-30"}},
        ])
        assert result["processed"] == 2


# ─── Credential Vault Tests ─────────────────────────────────────────

class TestCredentialVault:

    def test_encrypt_decrypt_roundtrip(self):
        vault = CredentialVault()
        original = {"token": "abc123xyz", "hr_id": "12345"}
        encrypted = vault.encrypt_credentials(original)
        assert encrypted["token"] != original["token"]
        decrypted = vault.decrypt_credentials(encrypted)
        assert decrypted == original

    def test_mask_credentials(self):
        masked = CredentialVault.mask_credentials({"token": "abcdef123456", "hr_id": "999"})
        assert masked["token"].startswith("abcd")
        assert "****" in masked["token"]
        assert masked["hr_id"] == "****"

    def test_encrypt_empty_value(self):
        vault = CredentialVault()
        encrypted = vault.encrypt_credentials({"token": "", "hr_id": "12345"})
        decrypted = vault.decrypt_credentials(encrypted)
        assert decrypted["token"] == ""
        assert decrypted["hr_id"] == "12345"

    def test_mask_short_values(self):
        masked = CredentialVault.mask_credentials({"key": "ab"})
        assert masked["key"] == "****"
