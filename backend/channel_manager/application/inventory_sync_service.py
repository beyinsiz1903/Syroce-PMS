"""
Inventory Sync Engine - Production-grade delta sync from PMS to external providers.

Architecture:
  PMS state → delta detection → change records → coalescing → batching → rate-limited dispatch → audit

SyncJob Lifecycle: pending → batched → dispatched → succeeded | retrying → failed → manual_review

Supported change types:
  - availability_changed
  - stop_sell_changed
  - closed_to_arrival_changed
  - closed_to_departure_changed
  - minimum_stay_changed
  - rate_changed
"""
import logging
import time
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db

from ..connectors.hotelrunner.auth import HotelRunnerAuth
from ..connectors.hotelrunner.client import HotelRunnerClient
from ..connectors.hotelrunner.errors import (
    AuthenticationError,
    ConnectorError,
    ProviderUnavailableError,
    RateLimitError,
    ValidationError,
    XmlParseError,
)
from ..domain.models.audit import AuditAction, IntegrationAuditLog
from ..domain.models.connector_account import ConnectorAccount, ConnectorProvider
from ..domain.models.sync import (
    ChangeType,
    PushReceipt,
    SyncDirection,
    SyncEvent,
    SyncJob,
    SyncJobStatus,
    SyncType,
)
from ..infrastructure.repository import ChannelManagerRepository

logger = logging.getLogger("channel_manager.inventory_sync_engine")

# Non-retryable error types
NON_RETRYABLE_ERRORS = (AuthenticationError, ValidationError, XmlParseError)
RETRYABLE_ERRORS = (RateLimitError, ProviderUnavailableError)

BATCH_SIZE = 50
MAX_RETRIES = 3


class InventorySyncService:
    """Production-grade inventory/rate/restriction delta sync engine."""

    def __init__(self, repo: ChannelManagerRepository | None = None):
        self._repo = repo or ChannelManagerRepository()

    # ─── Main Entry Points ──────────────────────────────────────────────

    async def trigger_inventory_sync(
        self,
        tenant_id: str,
        connector_id: str,
        date_start: str,
        date_end: str,
        room_type_ids: list[str] | None = None,
        triggered_by: str = "system",
        trigger_reason: str = "",
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Trigger a delta inventory+restriction sync to the external provider."""
        connector = await self._load_connector(tenant_id, connector_id)
        job = await self._create_job(
            tenant_id, connector.property_id, connector_id,
            SyncType.INVENTORY, date_start, date_end,
            room_type_ids=room_type_ids,
            triggered_by=triggered_by, trigger_reason=trigger_reason,
        )
        await self._audit_job(job, AuditAction.SYNC_JOB_STARTED, actor_id)

        try:
            return await self._execute_inventory_pipeline(job, connector, date_start, date_end, room_type_ids)
        except Exception as e:
            return await self._handle_job_failure(job, e)

    async def trigger_rate_sync(
        self,
        tenant_id: str,
        connector_id: str,
        date_start: str,
        date_end: str,
        rate_plan_ids: list[str] | None = None,
        triggered_by: str = "system",
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Trigger a delta rate sync to the external provider."""
        connector = await self._load_connector(tenant_id, connector_id)
        job = await self._create_job(
            tenant_id, connector.property_id, connector_id,
            SyncType.RATES, date_start, date_end,
            rate_plan_ids=rate_plan_ids,
            triggered_by=triggered_by, trigger_reason="Rate sync",
        )
        await self._audit_job(job, AuditAction.SYNC_JOB_STARTED, actor_id)

        try:
            return await self._execute_rate_pipeline(job, connector, date_start, date_end, rate_plan_ids)
        except Exception as e:
            return await self._handle_job_failure(job, e)

    async def retry_failed_job(
        self,
        tenant_id: str,
        job_id: str,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Retry a failed/manual_review job's failed events."""
        job_doc = await self._repo.get_sync_job(job_id)
        if not job_doc:
            raise ValueError("Sync job not found")
        if job_doc["tenant_id"] != tenant_id:
            raise ValueError("Unauthorized")
        if job_doc["status"] not in ("failed", "manual_review"):
            raise ValueError(f"Job status '{job_doc['status']}' is not retryable")

        connector = await self._load_connector(tenant_id, job_doc["connector_id"])
        failed_events = await self._repo.get_failed_events_for_job(job_id)

        if not failed_events:
            return {"job_id": job_id, "status": "succeeded", "message": "No failed events to retry"}

        # Update job status to retrying
        await self._repo.update_sync_job(job_id, {
            "status": SyncJobStatus.RETRYING.value,
            "retry_count": job_doc.get("retry_count", 0) + 1,
        })
        await self._audit_job_by_id(
            tenant_id, job_doc.get("property_id", ""), job_doc["connector_id"],
            job_id, AuditAction.MANUAL_RETRY, actor_id,
            {"failed_event_count": len(failed_events)},
        )

        # Re-dispatch failed events
        succeeded = 0
        still_failed = 0
        for evt_doc in failed_events:
            event = SyncEvent.from_doc(evt_doc)
            result = await self._dispatch_single_event(connector, event)
            if result["success"]:
                succeeded += 1
            else:
                still_failed += 1

        # Determine final status
        total_completed = job_doc.get("completed_events", 0) + succeeded
        total_failed = still_failed
        if total_failed == 0:
            final_status = SyncJobStatus.SUCCEEDED
        elif total_failed > 0 and job_doc.get("retry_count", 0) + 1 >= MAX_RETRIES:
            final_status = SyncJobStatus.MANUAL_REVIEW
        else:
            final_status = SyncJobStatus.FAILED

        await self._repo.update_sync_job(job_id, {
            "status": final_status.value,
            "completed_events": total_completed,
            "failed_events": total_failed,
            "completed_at": datetime.now(UTC).isoformat(),
        })

        return {
            "job_id": job_id,
            "status": final_status.value,
            "retried": len(failed_events),
            "succeeded": succeeded,
            "still_failed": still_failed,
        }

    async def dismiss_manual_review(
        self,
        tenant_id: str,
        job_id: str,
        actor_id: str | None = None,
    ) -> dict[str, Any]:
        """Dismiss a manual review job (acknowledge the failure)."""
        job_doc = await self._repo.get_sync_job(job_id)
        if not job_doc or job_doc["tenant_id"] != tenant_id:
            raise ValueError("Sync job not found")
        if job_doc["status"] != "manual_review":
            raise ValueError("Job is not in manual_review status")

        await self._repo.update_sync_job(job_id, {
            "status": SyncJobStatus.FAILED.value,
            "completed_at": datetime.now(UTC).isoformat(),
            "last_error": "Dismissed by user",
        })
        await self._audit_job_by_id(
            tenant_id, job_doc.get("property_id", ""), job_doc["connector_id"],
            job_id, AuditAction.MANUAL_REVIEW_DISMISSED, actor_id,
        )
        return {"job_id": job_id, "status": "failed", "message": "Manual review dismissed"}

    async def get_manual_review_queue(
        self, tenant_id: str, connector_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Get all jobs awaiting manual review."""
        return await self._repo.get_manual_review_jobs(tenant_id, connector_id)

    # ─── Pipeline: Inventory + Restrictions ─────────────────────────────

    async def _execute_inventory_pipeline(
        self, job: SyncJob, connector: ConnectorAccount,
        date_start: str, date_end: str, room_type_ids: list[str] | None,
    ) -> dict[str, Any]:
        """Full pipeline: detect → coalesce → batch → dispatch → finalize."""
        pipeline_start = time.monotonic()

        # 1. Get room type mappings
        from ..application.mapping_service import MappingService
        mapping_svc = MappingService(self._repo)
        room_lookup = await mapping_svc.get_mapping_lookup(
            job.tenant_id, job.connector_id, "room_type",
        )
        if not room_lookup:
            await self._transition_job(job, SyncJobStatus.FAILED, error="No active room type mappings found")
            return self._job_response(job)

        # 2. Detect delta changes
        changes = await self._detect_inventory_deltas(
            job.tenant_id, job.property_id, job.connector_id,
            date_start, date_end, room_type_ids, room_lookup,
        )

        if not changes:
            await self._transition_job(job, SyncJobStatus.SUCCEEDED)
            await self._repo.update_sync_job(job.id, {
                "total_changes_detected": 0,
                "total_changes_after_coalescing": 0,
                "completed_at": datetime.now(UTC).isoformat(),
                "duration_ms": int((time.monotonic() - pipeline_start) * 1000),
            })
            return {**self._job_response(job), "message": "No inventory changes to push"}

        await self._repo.update_sync_job(job.id, {
            "total_changes_detected": len(changes),
            "change_types": list({c["change_type"] for c in changes}),
        })

        # 3. Coalesce changes
        coalesced = self._coalesce_changes(changes)
        await self._transition_job(job, SyncJobStatus.BATCHED)
        await self._repo.update_sync_job(job.id, {
            "total_changes_after_coalescing": len(coalesced),
            "batched_at": datetime.now(UTC).isoformat(),
        })
        await self._audit_job(job, AuditAction.SYNC_JOB_BATCHED, metadata={
            "total_changes": len(changes),
            "after_coalescing": len(coalesced),
        })

        # 4. Split into inventory updates vs restriction updates
        inv_updates = [c for c in coalesced if c["change_type"] == ChangeType.AVAILABILITY_CHANGED.value]
        restriction_updates = [c for c in coalesced if c["change_type"] != ChangeType.AVAILABILITY_CHANGED.value
                               and c["change_type"] != ChangeType.RATE_CHANGED.value]

        # 5. Create sync events (batched)
        events = []
        for batch_idx, batch in enumerate(self._batch_updates(inv_updates)):
            event = SyncEvent(
                job_id=job.id, tenant_id=job.tenant_id, connector_id=job.connector_id,
                direction=SyncDirection.PUSH, sync_type=SyncType.INVENTORY,
                status=SyncJobStatus.PENDING, change_type="availability_changed",
                batch_index=batch_idx, batch_size=len(batch),
                coalesced_count=sum(c.get("coalesced_count", 1) for c in batch),
                request_payload={"updates": batch},
            )
            events.append(event)

        for batch_idx, batch in enumerate(self._batch_updates(restriction_updates)):
            event = SyncEvent(
                job_id=job.id, tenant_id=job.tenant_id, connector_id=job.connector_id,
                direction=SyncDirection.PUSH, sync_type=SyncType.RESTRICTIONS,
                status=SyncJobStatus.PENDING,
                change_type=batch[0]["change_type"] if batch else "restriction",
                batch_index=batch_idx + len(inv_updates), batch_size=len(batch),
                coalesced_count=sum(c.get("coalesced_count", 1) for c in batch),
                request_payload={"updates": batch},
            )
            events.append(event)

        if not events:
            await self._transition_job(job, SyncJobStatus.SUCCEEDED)
            return {**self._job_response(job), "message": "No changes after coalescing"}

        # Persist events
        await self._repo.create_sync_events_batch([e.to_doc() for e in events])
        await self._repo.update_sync_job(job.id, {"total_events": len(events)})

        # 6. Dispatch events (rate-limit aware)
        await self._transition_job(job, SyncJobStatus.DISPATCHED)
        await self._repo.update_sync_job(job.id, {"dispatched_at": datetime.now(UTC).isoformat()})
        await self._audit_job(job, AuditAction.SYNC_JOB_DISPATCHED, metadata={
            "total_events": len(events),
        })

        completed, failed, retried = await self._dispatch_events(connector, events)

        # 7. Update snapshots for succeeded items
        if completed > 0:
            await self._update_snapshots(job.tenant_id, job.connector_id, coalesced)

        # 8. Finalize job
        duration_ms = int((time.monotonic() - pipeline_start) * 1000)
        final_status = self._determine_final_status(completed, failed, retried, job.retry_count)

        await self._repo.update_sync_job(job.id, {
            "status": final_status.value,
            "completed_events": completed,
            "failed_events": failed,
            "retried_events": retried,
            "completed_at": datetime.now(UTC).isoformat(),
            "duration_ms": duration_ms,
        })
        job.status = final_status

        # Update connector health
        await self._update_connector_health(connector, final_status, failed)

        # Audit completion
        if final_status == SyncJobStatus.SUCCEEDED:
            await self._audit_job(job, AuditAction.SYNC_JOB_COMPLETED, metadata={
                "completed": completed, "duration_ms": duration_ms,
            })
        elif final_status == SyncJobStatus.MANUAL_REVIEW:
            await self._audit_job(job, AuditAction.SYNC_JOB_MANUAL_REVIEW, metadata={
                "completed": completed, "failed": failed, "duration_ms": duration_ms,
            })
        else:
            await self._audit_job(job, AuditAction.SYNC_JOB_FAILED, metadata={
                "completed": completed, "failed": failed, "duration_ms": duration_ms,
            })

        # Emit WebSocket event for inventory sync
        try:
            from .realtime_service import RealtimeEventService
            await RealtimeEventService.emit_sync_job_update(
                job.tenant_id, self._job_response(job, duration_ms=duration_ms, completed=completed, failed=failed),
            )
        except Exception:
            pass

        return self._job_response(job, duration_ms=duration_ms, completed=completed, failed=failed)

    # ─── Pipeline: Rate Sync ────────────────────────────────────────────

    async def _execute_rate_pipeline(
        self, job: SyncJob, connector: ConnectorAccount,
        date_start: str, date_end: str, rate_plan_ids: list[str] | None,
    ) -> dict[str, Any]:
        pipeline_start = time.monotonic()

        from ..application.mapping_service import MappingService
        mapping_svc = MappingService(self._repo)
        room_lookup = await mapping_svc.get_mapping_lookup(job.tenant_id, job.connector_id, "room_type")
        rate_lookup = await mapping_svc.get_mapping_lookup(job.tenant_id, job.connector_id, "rate_plan")

        # Detect rate deltas
        changes = await self._detect_rate_deltas(
            job.tenant_id, job.property_id, job.connector_id,
            date_start, date_end, room_lookup, rate_lookup,
        )

        if not changes:
            await self._transition_job(job, SyncJobStatus.SUCCEEDED)
            return {**self._job_response(job), "message": "No rate changes to push"}

        await self._repo.update_sync_job(job.id, {
            "total_changes_detected": len(changes),
            "change_types": [ChangeType.RATE_CHANGED.value],
        })

        coalesced = self._coalesce_changes(changes)
        await self._transition_job(job, SyncJobStatus.BATCHED)
        await self._repo.update_sync_job(job.id, {
            "total_changes_after_coalescing": len(coalesced),
            "batched_at": datetime.now(UTC).isoformat(),
        })

        events = []
        for batch_idx, batch in enumerate(self._batch_updates(coalesced)):
            event = SyncEvent(
                job_id=job.id, tenant_id=job.tenant_id, connector_id=job.connector_id,
                direction=SyncDirection.PUSH, sync_type=SyncType.RATES,
                status=SyncJobStatus.PENDING, change_type="rate_changed",
                batch_index=batch_idx, batch_size=len(batch),
                coalesced_count=sum(c.get("coalesced_count", 1) for c in batch),
                request_payload={"updates": batch},
            )
            events.append(event)

        if not events:
            await self._transition_job(job, SyncJobStatus.SUCCEEDED)
            return {**self._job_response(job), "message": "No rate events to dispatch"}

        await self._repo.create_sync_events_batch([e.to_doc() for e in events])
        await self._repo.update_sync_job(job.id, {"total_events": len(events)})

        await self._transition_job(job, SyncJobStatus.DISPATCHED)
        await self._repo.update_sync_job(job.id, {"dispatched_at": datetime.now(UTC).isoformat()})

        completed, failed, retried = await self._dispatch_events(connector, events, is_rate=True)

        duration_ms = int((time.monotonic() - pipeline_start) * 1000)
        final_status = self._determine_final_status(completed, failed, retried, job.retry_count)

        await self._repo.update_sync_job(job.id, {
            "status": final_status.value,
            "completed_events": completed,
            "failed_events": failed,
            "retried_events": retried,
            "completed_at": datetime.now(UTC).isoformat(),
            "duration_ms": duration_ms,
        })
        job.status = final_status
        await self._update_connector_health(connector, final_status, failed)

        audit_action = AuditAction.SYNC_JOB_COMPLETED if final_status == SyncJobStatus.SUCCEEDED else AuditAction.SYNC_JOB_FAILED
        await self._audit_job(job, audit_action, metadata={
            "completed": completed, "failed": failed, "duration_ms": duration_ms,
        })

        # Record rate push metrics
        try:
            from .rate_push_tracking_service import RatePushTrackingService
            rpt = RatePushTrackingService(repo=self._repo)
            await rpt.record_rate_push(
                tenant_id=job.tenant_id, connector_id=job.connector_id,
                success=final_status == SyncJobStatus.SUCCEEDED,
                latency_ms=duration_ms,
                error_type=type(Exception).__name__ if failed > 0 else "",
                update_count=len(coalesced),
                retry_count=retried,
            )
        except Exception:
            pass

        # Emit WebSocket event
        try:
            from .realtime_service import RealtimeEventService
            await RealtimeEventService.emit_sync_job_update(
                job.tenant_id, self._job_response(job, duration_ms=duration_ms, completed=completed, failed=failed),
            )
        except Exception:
            pass

        return self._job_response(job, duration_ms=duration_ms, completed=completed, failed=failed)

    # ─── Delta Detection ────────────────────────────────────────────────

    async def _check_inventory_freshness(
        self, tenant_id: str, date: str, stale_threshold_minutes: int = 15,
    ) -> str:
        """Check freshness of room_type_inventory materialized view.

        Returns: 'fresh' | 'recent' | 'stale' | 'empty'
        No fallback — stale means reconcile, not ignore.
        """
        latest = await db.room_type_inventory.find_one(
            {"tenant_id": tenant_id, "date": date},
            {"_id": 0, "last_computed_at": 1},
            sort=[("last_computed_at", -1)],
        )
        if not latest or not latest.get("last_computed_at"):
            return "empty"

        try:
            last_dt = datetime.fromisoformat(latest["last_computed_at"])
            age_minutes = (datetime.now(UTC) - last_dt).total_seconds() / 60
            if age_minutes < 5:
                return "fresh"
            elif age_minutes < stale_threshold_minutes:
                return "recent"
            else:
                return "stale"
        except (ValueError, TypeError):
            return "stale"

    async def _detect_inventory_deltas(
        self, tenant_id: str, property_id: str, connector_id: str,
        date_start: str, date_end: str,
        room_type_ids: list[str] | None, room_lookup: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Detect inventory changes using room_type_inventory as authoritative truth.

        Authoritative source: room_type_inventory materialized view (from room_night_locks).
        Accounts for booking + hold + OOO + OOS locks — NOT raw booking counts.
        NO fallback to booking-based computation. If view is stale, reconcile first.
        """
        from core.room_type_inventory_service import (
            get_room_type_inventory,
            reconcile_date_range,
        )

        changes: list[dict[str, Any]] = []

        # Step 1: Freshness check — stale view = reconcile, NOT fallback
        freshness = await self._check_inventory_freshness(tenant_id, date_start)
        if freshness in ("stale", "empty"):
            logger.warning(
                "Inventory view %s for tenant %s — reconciling before sync",
                freshness, tenant_id,
            )
            recon_result = await reconcile_date_range(tenant_id, date_start, date_end)
            if recon_result.get("drift_detected", 0) > 0:
                logger.warning(
                    "Pre-sync reconciliation found %d drifts for tenant %s",
                    recon_result["drift_detected"], tenant_id,
                )

        # Step 2: Get restriction data from PMS (unchanged — restrictions have no alt source)
        restrictions = await db.inventory_restrictions.find({
            "tenant_id": tenant_id,
            "date": {"$gte": date_start, "$lte": date_end},
        }, {"_id": 0}).to_list(5000)
        restriction_map: dict[str, dict] = {}
        for r in restrictions:
            key = f"{r.get('room_type_id', '')}_{r.get('date', '')}"
            restriction_map[key] = r

        # Step 3: Iterate date range, read from AUTHORITATIVE view
        start = datetime.strptime(date_start, "%Y-%m-%d").date()
        end = datetime.strptime(date_end, "%Y-%m-%d").date()
        current_date = start

        while current_date <= end:
            date_str = current_date.isoformat()

            # Read from room_type_inventory — the SINGLE source of truth
            inventory_items = await get_room_type_inventory(tenant_id, date_str)

            for item in inventory_items:
                rt = item.get("room_type", "")
                if not rt:
                    continue
                if room_type_ids and rt not in room_type_ids:
                    continue
                ext_code = room_lookup.get(rt)
                if not ext_code:
                    continue

                # Authoritative sellable count from room_night_locks
                current_available = item.get("sellable", 0)

                # Restriction state
                restriction_key = f"{rt}_{date_str}"
                restriction = restriction_map.get(restriction_key, {})

                # Last synced snapshot (what the channel currently has)
                snapshot = await self._repo.get_sync_snapshot(
                    tenant_id, connector_id, rt, date_str,
                )
                last_available = snapshot.get("available") if snapshot else None
                last_stop_sell = snapshot.get("stop_sell", False) if snapshot else None
                last_cta = snapshot.get("closed_to_arrival", False) if snapshot else None
                last_ctd = snapshot.get("closed_to_departure", False) if snapshot else None
                last_min_stay = snapshot.get("minimum_stay") if snapshot else None

                current_stop_sell = restriction.get("stop_sell", False)
                current_cta = restriction.get("closed_to_arrival", False)
                current_ctd = restriction.get("closed_to_departure", False)
                current_min_stay = restriction.get("minimum_stay")

                base_change = {
                    "room_type_id": rt,
                    "room_type_code": ext_code,
                    "date_start": date_str,
                    "date_end": date_str,
                }

                # Availability delta (from authoritative view)
                if last_available is None or current_available != last_available:
                    changes.append({
                        **base_change,
                        "change_type": ChangeType.AVAILABILITY_CHANGED.value,
                        "old_value": last_available,
                        "new_value": current_available,
                        "available": current_available,
                        "source": "room_type_inventory",
                    })

                # Stop sell delta
                if last_stop_sell is None or current_stop_sell != last_stop_sell:
                    if current_stop_sell or last_stop_sell:
                        changes.append({
                            **base_change,
                            "change_type": ChangeType.STOP_SELL_CHANGED.value,
                            "old_value": last_stop_sell,
                            "new_value": current_stop_sell,
                            "restriction_status": "Close" if current_stop_sell else "Open",
                        })

                # Closed to arrival delta
                if last_cta is None or current_cta != last_cta:
                    if current_cta or last_cta:
                        changes.append({
                            **base_change,
                            "change_type": ChangeType.CLOSED_TO_ARRIVAL_CHANGED.value,
                            "old_value": last_cta,
                            "new_value": current_cta,
                            "closed_to_arrival": current_cta,
                        })

                # Closed to departure delta
                if last_ctd is None or current_ctd != last_ctd:
                    if current_ctd or last_ctd:
                        changes.append({
                            **base_change,
                            "change_type": ChangeType.CLOSED_TO_DEPARTURE_CHANGED.value,
                            "old_value": last_ctd,
                            "new_value": current_ctd,
                            "closed_to_departure": current_ctd,
                        })

                # Minimum stay delta
                if last_min_stay != current_min_stay:
                    if current_min_stay is not None or last_min_stay is not None:
                        changes.append({
                            **base_change,
                            "change_type": ChangeType.MINIMUM_STAY_CHANGED.value,
                            "old_value": last_min_stay,
                            "new_value": current_min_stay,
                            "min_stay": current_min_stay,
                        })

            current_date += timedelta(days=1)

        return changes

    async def _detect_rate_deltas(
        self, tenant_id: str, property_id: str, connector_id: str,
        date_start: str, date_end: str,
        room_lookup: dict[str, str], rate_lookup: dict[str, str],
    ) -> list[dict[str, Any]]:
        """Detect rate changes by comparing PMS state with last synced snapshot."""
        changes: list[dict[str, Any]] = []

        rates = await db.rate_overrides.find({
            "tenant_id": tenant_id,
            "date": {"$gte": date_start, "$lte": date_end},
        }, {"_id": 0}).to_list(5000)

        for r in rates:
            room_type_id = r.get("room_type_id", "")
            rate_plan_id = r.get("rate_plan_id", "")
            ext_room = room_lookup.get(room_type_id)
            ext_rate = rate_lookup.get(rate_plan_id)
            if not ext_room or not ext_rate:
                continue

            date = r.get("date", "")
            current_rate = r.get("sell_rate", 0.0)

            snapshot = await self._repo.get_sync_snapshot(tenant_id, connector_id, room_type_id, date)
            last_rate = snapshot.get("sell_rate") if snapshot else None

            if last_rate is None or abs(current_rate - (last_rate or 0)) > 0.01:
                changes.append({
                    "change_type": ChangeType.RATE_CHANGED.value,
                    "room_type_id": room_type_id,
                    "room_type_code": ext_room,
                    "rate_plan_id": rate_plan_id,
                    "rate_plan_code": ext_rate,
                    "date_start": date,
                    "date_end": date,
                    "old_value": last_rate,
                    "new_value": current_rate,
                    "amount_after_tax": current_rate,
                    "currency": r.get("currency", "TRY"),
                })

        return changes

    # ─── Coalescing ─────────────────────────────────────────────────────

    def _coalesce_changes(self, changes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Merge consecutive changes for the same property/room_type/rate_plan/change_type.
        Adjacent dates with same values are merged into a single date range.
        """
        if not changes:
            return []

        # Group by (room_type_code, rate_plan_code, change_type)
        groups: dict[str, list[dict]] = defaultdict(list)
        for c in changes:
            key = f"{c.get('room_type_code', '')}|{c.get('rate_plan_code', c.get('rate_plan_id', ''))}|{c['change_type']}"
            groups[key].append(c)

        coalesced = []
        for key, group in groups.items():
            # Sort by date
            group.sort(key=lambda x: x["date_start"])

            # Merge adjacent dates with same new_value
            merged = group[0].copy()
            merged["coalesced_count"] = 1

            for i in range(1, len(group)):
                curr = group[i]
                prev_end = datetime.strptime(merged["date_end"], "%Y-%m-%d").date()
                curr_start = datetime.strptime(curr["date_start"], "%Y-%m-%d").date()

                # Can merge if adjacent date and same new value
                if (curr_start - prev_end).days <= 1 and curr.get("new_value") == merged.get("new_value"):
                    merged["date_end"] = curr["date_end"]
                    merged["coalesced_count"] += 1
                else:
                    coalesced.append(merged)
                    merged = curr.copy()
                    merged["coalesced_count"] = 1

            coalesced.append(merged)

        return coalesced

    # ─── Batching ───────────────────────────────────────────────────────

    def _batch_updates(self, updates: list[dict], batch_size: int = BATCH_SIZE) -> list[list[dict]]:
        """Split updates into batches for efficient API calls."""
        if not updates:
            return []
        return [updates[i:i+batch_size] for i in range(0, len(updates), batch_size)]

    # ─── Dispatch (Rate-Limit Aware) ────────────────────────────────────

    async def _dispatch_events(
        self, connector: ConnectorAccount, events: list[SyncEvent], is_rate: bool = False,
    ) -> tuple[int, int, int]:
        """Dispatch all events with rate limiting and retry logic."""
        completed = 0
        failed = 0
        retried = 0

        for event in events:
            result = await self._dispatch_single_event(connector, event, is_rate)
            if result["success"]:
                completed += 1
            elif result.get("retried", False):
                retried += 1
                if result.get("eventually_succeeded"):
                    completed += 1
                else:
                    failed += 1
            else:
                failed += 1

        return completed, failed, retried

    async def _dispatch_single_event(
        self, connector: ConnectorAccount, event: SyncEvent, is_rate: bool = False,
    ) -> dict[str, Any]:
        """Dispatch a single sync event to the provider with retry logic."""
        event_start = time.monotonic()

        # Update event to dispatched
        await self._repo.update_sync_event(event.id, {
            "status": SyncJobStatus.DISPATCHED.value,
            "started_at": datetime.now(UTC).isoformat(),
        })

        updates = (event.request_payload or {}).get("updates", [])
        if not updates:
            await self._repo.update_sync_event(event.id, {
                "status": SyncJobStatus.SUCCEEDED.value,
                "completed_at": datetime.now(UTC).isoformat(),
                "duration_ms": 0,
            })
            return {"success": True}

        last_error = None
        attempt = 0
        max_retries = event.max_retries

        while attempt <= max_retries:
            try:
                if connector.provider == ConnectorProvider.HOTELRUNNER:
                    auth = HotelRunnerAuth.from_credentials(connector.credentials)
                    client = HotelRunnerClient(auth=auth, sandbox=True)
                    try:
                        if is_rate or event.sync_type == SyncType.RATES:
                            result = await client.push_rates(updates)
                        elif event.sync_type == SyncType.RESTRICTIONS:
                            result = await client.push_availability(updates)
                        else:
                            result = await client.push_availability(updates)
                    finally:
                        await client.close()
                else:
                    raise ValueError(f"Unsupported provider: {connector.provider}")

                latency_ms = int((time.monotonic() - event_start) * 1000)

                # Success
                await self._repo.update_sync_event(event.id, {
                    "status": SyncJobStatus.SUCCEEDED.value,
                    "response_payload": result,
                    "completed_at": datetime.now(UTC).isoformat(),
                    "duration_ms": latency_ms,
                    "latency_ms": latency_ms,
                    "retry_count": attempt,
                })

                # Create push receipt
                receipt = PushReceipt(
                    tenant_id=connector.tenant_id, connector_id=connector.id,
                    sync_event_id=event.id, job_id=event.job_id,
                    provider_status="success", provider_response=result,
                    acknowledged=True, latency_ms=latency_ms,
                    acknowledged_at=datetime.now(UTC).isoformat(),
                )
                await self._repo.create_push_receipt(receipt.to_doc())

                # Audit
                await self._audit_event(event, AuditAction.SYNC_EVENT_SUCCEEDED, {
                    "latency_ms": latency_ms, "attempt": attempt + 1,
                })

                return {"success": True, "latency_ms": latency_ms, "retried": attempt > 0}

            except NON_RETRYABLE_ERRORS as e:
                # Non-retryable: fail immediately
                latency_ms = int((time.monotonic() - event_start) * 1000)
                error_msg = getattr(e, "message", str(e))
                await self._repo.update_sync_event(event.id, {
                    "status": SyncJobStatus.FAILED.value,
                    "error_message": error_msg,
                    "error_code": type(e).__name__,
                    "is_retryable": False,
                    "completed_at": datetime.now(UTC).isoformat(),
                    "duration_ms": latency_ms,
                    "latency_ms": latency_ms,
                    "retry_count": attempt,
                })
                await self._audit_event(event, AuditAction.SYNC_EVENT_FAILED, {
                    "error": error_msg, "error_code": type(e).__name__,
                    "retryable": False, "latency_ms": latency_ms,
                })
                return {"success": False, "error": error_msg, "retryable": False}

            except RETRYABLE_ERRORS as e:
                last_error = e
                attempt += 1
                if attempt > max_retries:
                    break

                # Update event as retrying
                await self._repo.update_sync_event(event.id, {
                    "status": SyncJobStatus.RETRYING.value,
                    "retry_count": attempt,
                    "error_message": getattr(e, "message", str(e)),
                })

                # Backoff delay
                delay = min(2.0 * (2 ** (attempt - 1)), 30.0)
                if isinstance(e, RateLimitError):
                    delay = min(e.retry_after_seconds, 60)

                logger.warning("Event %s retry %d/%d after %.1fs: %s",
                               event.id[:8], attempt, max_retries, delay, str(e))
                import asyncio
                await asyncio.sleep(delay)

            except ConnectorError as e:
                last_error = e
                if e.recoverable:
                    attempt += 1
                    if attempt > max_retries:
                        break
                    await self._repo.update_sync_event(event.id, {
                        "status": SyncJobStatus.RETRYING.value,
                        "retry_count": attempt,
                    })
                    import asyncio
                    await asyncio.sleep(2.0 * (2 ** (attempt - 1)))
                else:
                    break

        # Exhausted retries or non-recoverable ConnectorError
        latency_ms = int((time.monotonic() - event_start) * 1000)
        error_msg = getattr(last_error, "message", str(last_error)) if last_error else "Unknown error"
        await self._repo.update_sync_event(event.id, {
            "status": SyncJobStatus.FAILED.value,
            "error_message": error_msg,
            "error_code": type(last_error).__name__ if last_error else "UNKNOWN",
            "is_retryable": getattr(last_error, "recoverable", False) if last_error else False,
            "completed_at": datetime.now(UTC).isoformat(),
            "duration_ms": latency_ms,
            "latency_ms": latency_ms,
            "retry_count": attempt,
        })
        await self._audit_event(event, AuditAction.SYNC_EVENT_FAILED, {
            "error": error_msg, "retries_exhausted": attempt,
            "latency_ms": latency_ms,
        })
        return {"success": False, "error": error_msg, "retried": attempt > 0}

    # ─── Snapshot Management ────────────────────────────────────────────

    async def _update_snapshots(
        self, tenant_id: str, connector_id: str, coalesced: list[dict[str, Any]],
    ) -> None:
        """Update sync snapshots after successful dispatch."""
        for change in coalesced:
            room_type_id = change.get("room_type_id", "")
            start = datetime.strptime(change["date_start"], "%Y-%m-%d").date()
            end = datetime.strptime(change["date_end"], "%Y-%m-%d").date()
            current = start

            while current <= end:
                date_str = current.isoformat()
                snapshot = {
                    "tenant_id": tenant_id,
                    "connector_id": connector_id,
                    "room_type_id": room_type_id,
                    "date": date_str,
                    "updated_at": datetime.now(UTC).isoformat(),
                }

                ct = change.get("change_type", "")
                if ct == ChangeType.AVAILABILITY_CHANGED.value:
                    snapshot["available"] = change.get("new_value")
                elif ct == ChangeType.STOP_SELL_CHANGED.value:
                    snapshot["stop_sell"] = change.get("new_value")
                elif ct == ChangeType.CLOSED_TO_ARRIVAL_CHANGED.value:
                    snapshot["closed_to_arrival"] = change.get("new_value")
                elif ct == ChangeType.CLOSED_TO_DEPARTURE_CHANGED.value:
                    snapshot["closed_to_departure"] = change.get("new_value")
                elif ct == ChangeType.MINIMUM_STAY_CHANGED.value:
                    snapshot["minimum_stay"] = change.get("new_value")
                elif ct == ChangeType.RATE_CHANGED.value:
                    snapshot["sell_rate"] = change.get("new_value")

                await self._repo.upsert_sync_snapshot(snapshot)
                current += timedelta(days=1)

    # ─── Helper Methods ─────────────────────────────────────────────────

    async def _load_connector(self, tenant_id: str, connector_id: str) -> ConnectorAccount:
        doc = await self._repo.get_connector(tenant_id, connector_id)
        if not doc:
            raise ValueError("Connector not found")
        if doc.get("status") != "active":
            raise ValueError(f"Connector is not active (status: {doc.get('status')})")
        return ConnectorAccount.from_doc(doc)

    async def _create_job(
        self, tenant_id: str, property_id: str, connector_id: str,
        sync_type: SyncType, date_start: str, date_end: str,
        room_type_ids: list[str] | None = None,
        rate_plan_ids: list[str] | None = None,
        triggered_by: str = "system", trigger_reason: str = "",
    ) -> SyncJob:
        job = SyncJob(
            tenant_id=tenant_id,
            property_id=property_id,
            connector_id=connector_id,
            direction=SyncDirection.PUSH,
            sync_type=sync_type,
            date_range_start=date_start,
            date_range_end=date_end,
            room_type_ids=room_type_ids or [],
            rate_plan_ids=rate_plan_ids or [],
            triggered_by=triggered_by,
            trigger_reason=trigger_reason,
            status=SyncJobStatus.PENDING,
            started_at=datetime.now(UTC).isoformat(),
        )
        await self._repo.create_sync_job(job.to_doc())
        return job

    async def _transition_job(self, job: SyncJob, status: SyncJobStatus, error: str | None = None) -> None:
        updates: dict[str, Any] = {"status": status.value}
        if error:
            updates["last_error"] = error
        if status in (SyncJobStatus.SUCCEEDED, SyncJobStatus.FAILED, SyncJobStatus.MANUAL_REVIEW):
            updates["completed_at"] = datetime.now(UTC).isoformat()
        await self._repo.update_sync_job(job.id, updates)
        job.status = status

    async def _handle_job_failure(self, job: SyncJob, error: Exception) -> dict[str, Any]:
        error_msg = str(error)[:500]
        await self._repo.update_sync_job(job.id, {
            "status": SyncJobStatus.FAILED.value,
            "last_error": error_msg,
            "completed_at": datetime.now(UTC).isoformat(),
        })
        job.status = SyncJobStatus.FAILED
        await self._audit_job(job, AuditAction.SYNC_JOB_FAILED, metadata={"error": error_msg})
        return self._job_response(job, error=error_msg)

    def _determine_final_status(
        self, completed: int, failed: int, retried: int, job_retry_count: int,
    ) -> SyncJobStatus:
        if failed == 0:
            return SyncJobStatus.SUCCEEDED
        if completed > 0 and failed > 0 and job_retry_count < MAX_RETRIES:
            return SyncJobStatus.FAILED
        if failed > 0 and job_retry_count >= MAX_RETRIES:
            return SyncJobStatus.MANUAL_REVIEW
        return SyncJobStatus.FAILED

    async def _update_connector_health(
        self, connector: ConnectorAccount, status: SyncJobStatus, failed: int,
    ) -> None:
        doc = await self._repo.get_connector(connector.tenant_id, connector.id)
        if not doc:
            return
        if status == SyncJobStatus.SUCCEEDED:
            doc["last_successful_sync"] = datetime.now(UTC).isoformat()
            doc["consecutive_failures"] = 0
        else:
            doc["consecutive_failures"] = doc.get("consecutive_failures", 0) + 1
            doc["last_error"] = f"{failed} events failed"
            doc["last_error_at"] = datetime.now(UTC).isoformat()
        doc["total_syncs"] = doc.get("total_syncs", 0) + 1
        await self._repo.upsert_connector(doc)

    def _job_response(
        self, job: SyncJob, duration_ms: int = 0, completed: int = 0,
        failed: int = 0, error: str | None = None,
    ) -> dict[str, Any]:
        resp = {
            "job_id": job.id,
            "status": job.status.value,
            "sync_type": job.sync_type.value,
            "direction": job.direction.value,
            "date_range_start": job.date_range_start,
            "date_range_end": job.date_range_end,
            "total_changes_detected": job.total_changes_detected,
            "total_changes_after_coalescing": job.total_changes_after_coalescing,
            "change_types": job.change_types,
            "total_events": job.total_events,
            "completed_events": completed,
            "failed_events": failed,
            "duration_ms": duration_ms,
            "triggered_by": job.triggered_by,
            "created_at": job.created_at,
        }
        if error:
            resp["error"] = error
        return resp

    # ─── Audit Helpers ──────────────────────────────────────────────────

    async def _audit_job(
        self, job: SyncJob, action: AuditAction,
        actor_id: str | None = None, metadata: dict | None = None,
    ) -> None:
        log = IntegrationAuditLog(
            tenant_id=job.tenant_id,
            property_id=job.property_id,
            connector_id=job.connector_id,
            action=action,
            entity_type="sync_job",
            entity_id=job.id,
            actor_id=actor_id,
            metadata=metadata or {},
        )
        await self._repo.create_audit_log(log.to_doc())

    async def _audit_job_by_id(
        self, tenant_id: str, property_id: str, connector_id: str,
        job_id: str, action: AuditAction,
        actor_id: str | None = None, metadata: dict | None = None,
    ) -> None:
        log = IntegrationAuditLog(
            tenant_id=tenant_id, property_id=property_id,
            connector_id=connector_id, action=action,
            entity_type="sync_job", entity_id=job_id,
            actor_id=actor_id, metadata=metadata or {},
        )
        await self._repo.create_audit_log(log.to_doc())

    async def _audit_event(
        self, event: SyncEvent, action: AuditAction, metadata: dict | None = None,
    ) -> None:
        log = IntegrationAuditLog(
            tenant_id=event.tenant_id,
            connector_id=event.connector_id,
            action=action,
            entity_type="sync_event",
            entity_id=event.id,
            metadata=metadata or {},
        )
        await self._repo.create_audit_log(log.to_doc())
