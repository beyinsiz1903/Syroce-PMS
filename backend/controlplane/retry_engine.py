"""
Retry Engine — Idempotent Retry and Replay for Control Plane
=============================================================
Handles retry/replay of failed operations with:
- Idempotency guarantees (no duplicate reservations)
- Dry-run mode for safe operator verification
- Retry logging and failure tracking integration
- Operation-specific dispatch

Every retry MUST be safe to call multiple times.
"""
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from .failure_model import FailureStatus, FailureType, OperationType

logger = logging.getLogger("controlplane.retry_engine")

COLL_FAILURES = "cp_failures"
COLL_RETRY_LOG = "cp_retry_log"


class RetryEngine:
    """Idempotent retry/replay engine.

    Guarantees:
    - Retrying a reservation ingest does NOT create duplicates
    - Retrying ARI push does NOT corrupt state
    - Every retry attempt is logged
    - Dry-run mode available for operator safety
    """

    def __init__(self):
        self._db = None

    def _get_db(self):
        if self._db is None:
            from core.database import db
            self._db = db
        return self._db

    async def retry(
        self,
        failure_id: str,
        *,
        dry_run: bool = False,
        initiated_by: str = "operator",
    ) -> dict[str, Any]:
        """Retry a failed operation.

        Args:
            failure_id: The cp_failures document ID.
            dry_run: If True, validate the retry would work but don't execute.
            initiated_by: Who initiated the retry (for audit).

        Returns:
            Retry result with status and details.
        """
        db = self._get_db()

        # 1. Load the failure
        failure = await db[COLL_FAILURES].find_one(
            {"id": failure_id}, {"_id": 0}
        )
        if not failure:
            return {"success": False, "error": "failure_not_found", "failure_id": failure_id}

        # 2. Check retryable
        if failure["status"] not in (FailureStatus.OPEN.value, FailureStatus.RETRYING.value):
            return {
                "success": False,
                "error": "not_retryable",
                "reason": f"Failure status is '{failure['status']}', must be 'open' or 'retrying'",
                "failure_id": failure_id,
            }

        if failure["failure_type"] == FailureType.PERMANENT.value:
            return {
                "success": False,
                "error": "permanent_failure",
                "reason": "Permanent failures cannot be retried. Resolve the root cause first.",
                "failure_id": failure_id,
            }

        # 3. Dry-run mode
        if dry_run:
            return {
                "success": True,
                "dry_run": True,
                "failure_id": failure_id,
                "operation_type": failure["operation_type"],
                "would_retry": True,
                "current_retry_count": failure.get("retry_count", 0),
                "message": "Dry run: retry would be attempted. No changes made.",
            }

        # 4. Mark as retrying
        now = datetime.now(UTC).isoformat()
        await db[COLL_FAILURES].update_one(
            {"id": failure_id},
            {"$set": {
                "status": FailureStatus.RETRYING.value,
                "updated_at": now,
            },
            "$inc": {"retry_count": 1}},
        )

        # 5. Log the retry attempt
        retry_log = {
            "id": str(uuid.uuid4()),
            "failure_id": failure_id,
            "tenant_id": failure["tenant_id"],
            "provider": failure["provider"],
            "operation_type": failure["operation_type"],
            "initiated_by": initiated_by,
            "dry_run": False,
            "started_at": now,
            "status": "pending",
        }
        await db[COLL_RETRY_LOG].insert_one(retry_log)

        # 6. Dispatch retry based on operation type
        try:
            result = await self._dispatch_retry(failure)

            # 7. Update failure + log on success
            await db[COLL_FAILURES].update_one(
                {"id": failure_id},
                {"$set": {
                    "status": FailureStatus.RESOLVED.value,
                    "resolved_at": datetime.now(UTC).isoformat(),
                    "resolved_by": f"retry:{initiated_by}",
                    "updated_at": datetime.now(UTC).isoformat(),
                }},
            )
            await db[COLL_RETRY_LOG].update_one(
                {"id": retry_log["id"]},
                {"$set": {
                    "status": "success",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "result": result,
                }},
            )

            logger.info(
                "Retry succeeded: failure=%s op=%s tenant=%s",
                failure_id, failure["operation_type"], failure["tenant_id"],
            )
            return {
                "success": True,
                "failure_id": failure_id,
                "operation_type": failure["operation_type"],
                "retry_result": result,
                "message": "Retry completed successfully.",
            }

        except Exception as e:
            # 8. Reopen failure on retry error
            error_msg = str(e)
            await db[COLL_FAILURES].update_one(
                {"id": failure_id},
                {"$set": {
                    "status": FailureStatus.OPEN.value,
                    "last_seen_at": datetime.now(UTC).isoformat(),
                    "error_message": error_msg[:1000],
                    "updated_at": datetime.now(UTC).isoformat(),
                }},
            )
            await db[COLL_RETRY_LOG].update_one(
                {"id": retry_log["id"]},
                {"$set": {
                    "status": "failed",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "error": error_msg[:1000],
                }},
            )

            logger.warning(
                "Retry failed: failure=%s op=%s error=%s",
                failure_id, failure["operation_type"], error_msg,
            )
            return {
                "success": False,
                "failure_id": failure_id,
                "error": "retry_failed",
                "reason": error_msg[:500],
            }

    async def _dispatch_retry(self, failure: dict[str, Any]) -> dict[str, Any]:
        """Route retry to the appropriate handler based on operation_type."""
        op = failure.get("operation_type", "")
        context = failure.get("context", {})
        tenant_id = failure["tenant_id"]
        provider = failure["provider"]

        if op == OperationType.RESERVATION_IMPORT.value:
            return await self._retry_reservation_import(tenant_id, provider, context)
        elif op == OperationType.OUTBOX_DISPATCH.value:
            return await self._retry_outbox_event(tenant_id, provider, context)
        elif op == OperationType.ARI_PUSH.value:
            return await self._retry_ari_push(tenant_id, provider, context)
        elif op == OperationType.SYNC_JOB.value:
            return await self._retry_sync_job(tenant_id, provider, context)
        else:
            return {"status": "no_handler", "operation_type": op,
                    "message": f"No automatic retry handler for '{op}'. Manual intervention required."}

    async def _retry_reservation_import(
        self, tenant_id: str, provider: str, context: dict[str, Any],
    ) -> dict[str, Any]:
        """Retry a failed reservation import. Duplicate-safe via import bridge."""
        import_id = context.get("import_id", "")
        if not import_id:
            return {"status": "skipped", "reason": "No import_id in failure context"}

        db = self._get_db()
        # Check if already imported (idempotency)
        doc = await db.imported_reservations.find_one(
            {"id": import_id}, {"_id": 0, "import_status": 1}
        )
        if doc and doc.get("import_status") == "imported":
            return {"status": "already_imported", "import_id": import_id}

        # Re-trigger import via bridge
        try:
            from core.import_bridge_service import auto_import_reservation_to_pms
            result = await auto_import_reservation_to_pms(import_id)
            return {"status": "retried", "import_id": import_id, "result": str(result)}
        except Exception as e:
            raise RuntimeError(f"Reservation import retry failed: {e}")

    async def _retry_outbox_event(
        self, tenant_id: str, provider: str, context: dict[str, Any],
    ) -> dict[str, Any]:
        """Retry a failed outbox event by resetting it to pending."""
        event_id = context.get("event_id", "")
        if not event_id:
            return {"status": "skipped", "reason": "No event_id in failure context"}

        db = self._get_db()
        now = datetime.now(UTC).isoformat()
        result = await db.outbox_events.update_one(
            {"event_id": event_id, "status": {"$in": ["failed", "parked"]}},
            {"$set": {"status": "pending", "updated_at": now},
             "$unset": {"failed_at": "", "parked_at": "", "parked_reason": ""}},
        )
        if result.modified_count == 1:
            return {"status": "requeued", "event_id": event_id}
        return {"status": "not_modified", "event_id": event_id,
                "reason": "Event not in failed/parked state or not found"}

    async def _retry_ari_push(
        self, tenant_id: str, provider: str, context: dict[str, Any],
    ) -> dict[str, Any]:
        """Retry an ARI push by re-enqueuing the outbox event."""
        # ARI push failures map to outbox events
        event_id = context.get("event_id", "")
        if event_id:
            return await self._retry_outbox_event(tenant_id, provider, context)
        return {"status": "skipped", "reason": "No event_id for ARI retry"}

    async def _retry_sync_job(
        self, tenant_id: str, provider: str, context: dict[str, Any],
    ) -> dict[str, Any]:
        """Retry a failed sync job."""
        job_id = context.get("job_id", "")
        if not job_id:
            return {"status": "skipped", "reason": "No job_id in failure context"}
        # Mark sync job for re-execution
        db = self._get_db()
        now = datetime.now(UTC).isoformat()
        result = await db.cp_sync_jobs.update_one(
            {"id": job_id, "status": {"$in": ["failed", "stalled"]}},
            {"$set": {"status": "pending", "updated_at": now, "retry_requested_at": now}},
        )
        if result.modified_count == 1:
            return {"status": "requeued", "job_id": job_id}
        return {"status": "not_modified", "job_id": job_id}


# ── Singleton ──────────────────────────────────────────────────────
_engine: RetryEngine | None = None


def get_retry_engine() -> RetryEngine:
    global _engine
    if _engine is None:
        _engine = RetryEngine()
    return _engine
