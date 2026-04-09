"""
Re-encryption Worker — Background job for migrating data to new keys.

Handles:
  - Batch re-encryption of documents after key rotation
  - Progress tracking with checkpointing
  - Resume capability for interrupted jobs
  - Failure isolation (bad docs don't block others)
  - Audit trail for compliance

Usage:
  from security.reencryption_worker import get_reencryption_worker

  worker = get_reencryption_worker()
  job = await worker.start_job(key_id="...")
  status = await worker.get_job_status(job["job_id"])
"""
import asyncio
import logging
from datetime import UTC, datetime
from enum import Enum
from typing import Any

logger = logging.getLogger("security.reencryption_worker")

COLL_JOBS = "reencryption_jobs"
COLL_JOB_AUDIT = "reencryption_audit"


class JobState(str, Enum):
    """Re-encryption job states."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReencryptionWorker:
    """Background worker for re-encrypting data during key rotation."""

    def __init__(self):
        self._db = None
        self._running_jobs: dict[str, asyncio.Task] = {}

    def _get_db(self):
        if self._db is None:
            from core.tenant_db import get_system_db
            self._db = get_system_db()
        return self._db

    # ── Job Management ─────────────────────────────────────────────

    async def create_job(
        self,
        *,
        key_id: str,
        collections: list[str],
        actor: str,
        batch_size: int = 100,
        description: str = "",
    ) -> dict[str, Any]:
        """Create a new re-encryption job (does not start it)."""
        import uuid

        db = self._get_db()
        now = datetime.now(UTC)
        job_id = f"reenc-{uuid.uuid4().hex[:12]}"

        # Calculate scope
        scope = []
        for collection in collections:
            count = await db[collection].count_documents({})
            scope.append({"collection": collection, "total_documents": count})

        total_docs = sum(s["total_documents"] for s in scope)

        job_doc = {
            "job_id": job_id,
            "key_id": key_id,
            "state": JobState.PENDING.value,
            "description": description,
            "batch_size": batch_size,
            "scope": scope,
            "total_documents": total_docs,
            "processed_documents": 0,
            "failed_documents": 0,
            "current_collection": None,
            "current_offset": 0,
            "progress_percent": 0.0,
            "created_at": now.isoformat(),
            "created_by": actor,
            "started_at": None,
            "completed_at": None,
            "paused_at": None,
            "last_checkpoint_at": None,
            "error": None,
            "failed_doc_ids": [],
        }

        await db[COLL_JOBS].insert_one(job_doc)
        await self._audit(
            job_id=job_id,
            action="job_created",
            actor=actor,
            details={"key_id": key_id, "collections": collections, "total_documents": total_docs},
        )

        logger.info("Re-encryption job created: %s for key %s (%d docs)", job_id, key_id, total_docs)

        return {
            "job_id": job_id,
            "state": JobState.PENDING.value,
            "total_documents": total_docs,
            "scope": scope,
        }

    async def start_job(self, job_id: str, *, actor: str) -> dict[str, Any]:
        """Start or resume a re-encryption job."""
        db = self._get_db()

        job = await db[COLL_JOBS].find_one({"job_id": job_id}, {"_id": 0})
        if not job:
            return {"success": False, "error": "Job not found"}

        if job["state"] == JobState.RUNNING.value:
            return {"success": False, "error": "Job already running"}

        if job["state"] in (JobState.COMPLETED.value, JobState.CANCELLED.value):
            return {"success": False, "error": f"Cannot start job in state '{job['state']}'"}

        now = datetime.now(UTC)
        await db[COLL_JOBS].update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "state": JobState.RUNNING.value,
                    "started_at": now.isoformat() if job["state"] == JobState.PENDING.value else job["started_at"],
                    "paused_at": None,
                }
            },
        )

        await self._audit(
            job_id=job_id,
            action="job_started",
            actor=actor,
            details={"resumed": job["state"] != JobState.PENDING.value},
        )

        # Start background task
        task = asyncio.create_task(self._run_job(job_id))
        self._running_jobs[job_id] = task

        logger.info("Re-encryption job started: %s by %s", job_id, actor)

        return {"success": True, "job_id": job_id, "state": JobState.RUNNING.value}

    async def pause_job(self, job_id: str, *, actor: str) -> dict[str, Any]:
        """Pause a running job. Can be resumed later."""
        db = self._get_db()

        job = await db[COLL_JOBS].find_one({"job_id": job_id}, {"_id": 0})
        if not job:
            return {"success": False, "error": "Job not found"}

        if job["state"] != JobState.RUNNING.value:
            return {"success": False, "error": f"Cannot pause job in state '{job['state']}'"}

        now = datetime.now(UTC)
        await db[COLL_JOBS].update_one(
            {"job_id": job_id},
            {"$set": {"state": JobState.PAUSED.value, "paused_at": now.isoformat()}},
        )

        # Cancel background task
        if job_id in self._running_jobs:
            self._running_jobs[job_id].cancel()
            del self._running_jobs[job_id]

        await self._audit(
            job_id=job_id,
            action="job_paused",
            actor=actor,
            details={"progress_percent": job.get("progress_percent", 0)},
        )

        logger.info("Re-encryption job paused: %s by %s", job_id, actor)

        return {"success": True, "job_id": job_id, "state": JobState.PAUSED.value}

    async def cancel_job(self, job_id: str, *, actor: str, reason: str = "") -> dict[str, Any]:
        """Cancel a job. Cannot be resumed."""
        db = self._get_db()

        job = await db[COLL_JOBS].find_one({"job_id": job_id}, {"_id": 0})
        if not job:
            return {"success": False, "error": "Job not found"}

        if job["state"] in (JobState.COMPLETED.value, JobState.CANCELLED.value):
            return {"success": False, "error": f"Job already in terminal state '{job['state']}'"}

        now = datetime.now(UTC)
        await db[COLL_JOBS].update_one(
            {"job_id": job_id},
            {
                "$set": {
                    "state": JobState.CANCELLED.value,
                    "completed_at": now.isoformat(),
                    "error": f"Cancelled: {reason}" if reason else "Cancelled by operator",
                }
            },
        )

        # Cancel background task
        if job_id in self._running_jobs:
            self._running_jobs[job_id].cancel()
            del self._running_jobs[job_id]

        await self._audit(
            job_id=job_id,
            action="job_cancelled",
            actor=actor,
            details={"reason": reason, "progress_percent": job.get("progress_percent", 0)},
        )

        logger.info("Re-encryption job cancelled: %s by %s — %s", job_id, actor, reason)

        return {"success": True, "job_id": job_id, "state": JobState.CANCELLED.value}

    # ── Status / Progress ──────────────────────────────────────────

    async def get_job_status(self, job_id: str) -> dict[str, Any] | None:
        """Get current status of a job."""
        db = self._get_db()
        job = await db[COLL_JOBS].find_one({"job_id": job_id}, {"_id": 0})
        if not job:
            return None

        # Calculate ETA if running
        eta = None
        if job["state"] == JobState.RUNNING.value and job["processed_documents"] > 0:
            started = job.get("started_at")
            if started:
                try:
                    start_dt = datetime.fromisoformat(started.replace("Z", "+00:00"))
                    elapsed = (datetime.now(UTC) - start_dt).total_seconds()
                    rate = job["processed_documents"] / elapsed if elapsed > 0 else 0
                    remaining = job["total_documents"] - job["processed_documents"]
                    if rate > 0:
                        eta_seconds = remaining / rate
                        eta = (datetime.now(UTC).timestamp() + eta_seconds)
                except Exception:
                    pass

        return {
            **job,
            "is_running": job_id in self._running_jobs,
            "eta_timestamp": eta,
        }

    async def list_jobs(
        self,
        *,
        state: JobState | None = None,
        key_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """List re-encryption jobs."""
        db = self._get_db()
        query: dict[str, Any] = {}

        if state:
            query["state"] = state.value
        if key_id:
            query["key_id"] = key_id

        cursor = db[COLL_JOBS].find(query, {"_id": 0}).sort("created_at", -1).limit(limit)
        return await cursor.to_list(limit)

    async def get_dashboard(self) -> dict[str, Any]:
        """Re-encryption jobs dashboard."""
        db = self._get_db()

        all_jobs = await db[COLL_JOBS].find({}, {"_id": 0}).sort("created_at", -1).to_list(100)

        by_state = {s.value: [] for s in JobState}
        for job in all_jobs:
            state = job.get("state", JobState.PENDING.value)
            by_state.setdefault(state, []).append(job)

        running = [j for j in all_jobs if j["job_id"] in self._running_jobs]
        total_processed = sum(j.get("processed_documents", 0) for j in all_jobs)
        total_failed = sum(j.get("failed_documents", 0) for j in all_jobs)

        return {
            "summary": {
                "total_jobs": len(all_jobs),
                "pending": len(by_state.get(JobState.PENDING.value, [])),
                "running": len(running),
                "paused": len(by_state.get(JobState.PAUSED.value, [])),
                "completed": len(by_state.get(JobState.COMPLETED.value, [])),
                "failed": len(by_state.get(JobState.FAILED.value, [])),
                "cancelled": len(by_state.get(JobState.CANCELLED.value, [])),
                "total_documents_processed": total_processed,
                "total_documents_failed": total_failed,
            },
            "running_jobs": running,
            "recent_jobs": all_jobs[:20],
            "timestamp": datetime.now(UTC).isoformat(),
        }

    # ── Job Execution ──────────────────────────────────────────────

    async def _run_job(self, job_id: str) -> None:
        """Background task: execute re-encryption job."""
        db = self._get_db()

        try:
            job = await db[COLL_JOBS].find_one({"job_id": job_id}, {"_id": 0})
            if not job:
                return

            from security.field_encryption import get_field_encryption_service

            enc_svc = get_field_encryption_service()

            # Process each collection in scope
            for scope_item in job["scope"]:
                collection_name = scope_item["collection"]

                # Skip if already processed past this collection
                if job.get("current_collection") and job["current_collection"] != collection_name:
                    # Check if we should skip
                    scope_names = [s["collection"] for s in job["scope"]]
                    current_idx = scope_names.index(job["current_collection"]) if job["current_collection"] in scope_names else -1
                    this_idx = scope_names.index(collection_name)
                    if this_idx < current_idx:
                        continue

                await self._process_collection(
                    job_id=job_id,
                    job=job,
                    collection_name=collection_name,
                    enc_svc=enc_svc,
                    batch_size=job.get("batch_size", 100),
                )

                # Refresh job state (might have been paused)
                job = await db[COLL_JOBS].find_one({"job_id": job_id}, {"_id": 0})
                if not job or job["state"] != JobState.RUNNING.value:
                    return

            # Mark completed
            await db[COLL_JOBS].update_one(
                {"job_id": job_id},
                {
                    "$set": {
                        "state": JobState.COMPLETED.value,
                        "completed_at": datetime.now(UTC).isoformat(),
                        "progress_percent": 100.0,
                    }
                },
            )

            await self._audit(
                job_id=job_id,
                action="job_completed",
                actor="system",
                details={
                    "processed_documents": job.get("processed_documents", 0),
                    "failed_documents": job.get("failed_documents", 0),
                },
            )

            logger.info("Re-encryption job completed: %s", job_id)

        except asyncio.CancelledError:
            logger.info("Re-encryption job cancelled: %s", job_id)
            raise
        except Exception as e:
            logger.exception("Re-encryption job failed: %s", job_id)
            await db[COLL_JOBS].update_one(
                {"job_id": job_id},
                {
                    "$set": {
                        "state": JobState.FAILED.value,
                        "completed_at": datetime.now(UTC).isoformat(),
                        "error": str(e),
                    }
                },
            )
            await self._audit(
                job_id=job_id,
                action="job_failed",
                actor="system",
                details={"error": str(e)},
                severity="error",
            )
        finally:
            if job_id in self._running_jobs:
                del self._running_jobs[job_id]

    async def _process_collection(
        self,
        *,
        job_id: str,
        job: dict,
        collection_name: str,
        enc_svc,
        batch_size: int,
    ) -> None:
        """Process a single collection for re-encryption."""
        db = self._get_db()
        col = db[collection_name]

        # Update current collection
        await db[COLL_JOBS].update_one(
            {"job_id": job_id},
            {"$set": {"current_collection": collection_name, "current_offset": 0}},
        )

        # Resume from offset if applicable
        offset = 0
        if job.get("current_collection") == collection_name:
            offset = job.get("current_offset", 0)

        # Get all document IDs to process
        cursor = col.find(
            {"_enc_version": {"$exists": True}},  # Only already-encrypted docs
            {"_id": 1},
        ).skip(offset).batch_size(batch_size)

        doc_ids = [doc["_id"] async for doc in cursor]
        total_in_collection = len(doc_ids)

        processed = 0
        failed = 0
        failed_ids = []

        for i in range(0, len(doc_ids), batch_size):
            batch_ids = doc_ids[i:i + batch_size]

            for doc_id in batch_ids:
                try:
                    doc = await col.find_one({"_id": doc_id})
                    if not doc:
                        continue

                    # Decrypt and re-encrypt
                    decrypted = enc_svc.decrypt_document(doc, collection=collection_name)
                    reencrypted = enc_svc.encrypt_document(decrypted, collection=collection_name)

                    # Only update encrypted fields
                    update_fields = {}
                    for key in reencrypted:
                        if key.startswith("_") or key == "_id":
                            continue
                        if doc.get(key) != reencrypted.get(key):
                            update_fields[key] = reencrypted[key]

                    # Update encryption metadata
                    update_fields["_reencrypted_at"] = datetime.now(UTC).isoformat()
                    update_fields["_reencryption_job_id"] = job_id

                    if update_fields:
                        await col.update_one({"_id": doc_id}, {"$set": update_fields})

                    processed += 1

                except Exception as e:
                    failed += 1
                    failed_ids.append(str(doc_id))
                    logger.warning(
                        "Re-encryption failed: job=%s collection=%s doc=%s error=%s",
                        job_id, collection_name, doc_id, e,
                    )

            # Checkpoint progress
            total_processed = job.get("processed_documents", 0) + processed
            total_failed = job.get("failed_documents", 0) + failed
            progress = (total_processed / job["total_documents"] * 100) if job["total_documents"] > 0 else 100

            await db[COLL_JOBS].update_one(
                {"job_id": job_id},
                {
                    "$set": {
                        "processed_documents": total_processed,
                        "failed_documents": total_failed,
                        "current_offset": offset + processed + failed,
                        "progress_percent": round(progress, 2),
                        "last_checkpoint_at": datetime.now(UTC).isoformat(),
                    },
                    "$push": {"failed_doc_ids": {"$each": failed_ids[-10:]}},  # Keep last 10 failures
                },
            )

            failed_ids = []

            # Check if paused
            current_job = await db[COLL_JOBS].find_one({"job_id": job_id}, {"state": 1})
            if current_job and current_job.get("state") != JobState.RUNNING.value:
                return

            # Small delay to avoid overwhelming the database
            await asyncio.sleep(0.1)

        logger.info(
            "Re-encryption collection done: job=%s collection=%s processed=%d failed=%d",
            job_id, collection_name, processed, failed,
        )

    # ── Audit ──────────────────────────────────────────────────────

    async def get_audit_log(
        self,
        *,
        job_id: str | None = None,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Query re-encryption audit log."""
        db = self._get_db()
        query: dict[str, Any] = {}
        if job_id:
            query["job_id"] = job_id

        total = await db[COLL_JOB_AUDIT].count_documents(query)
        items = await db[COLL_JOB_AUDIT].find(
            query, {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(limit)

        return {"items": items, "total": total}

    async def _audit(
        self,
        *,
        job_id: str,
        action: str,
        actor: str,
        details: dict[str, Any] | None = None,
        severity: str = "info",
    ) -> None:
        """Write audit log entry."""
        db = self._get_db()
        try:
            await db[COLL_JOB_AUDIT].insert_one({
                "job_id": job_id,
                "action": action,
                "actor": actor,
                "details": details or {},
                "severity": severity,
                "timestamp": datetime.now(UTC).isoformat(),
            })
        except Exception:
            logger.exception("Failed to write re-encryption audit log")

    # ── Index Setup ────────────────────────────────────────────────

    async def ensure_indexes(self) -> None:
        """Create indexes for re-encryption collections."""
        db = self._get_db()

        jobs = db[COLL_JOBS]
        await jobs.create_index("job_id", unique=True)
        await jobs.create_index([("state", 1), ("created_at", -1)])
        await jobs.create_index("key_id")

        audit = db[COLL_JOB_AUDIT]
        await audit.create_index([("job_id", 1), ("timestamp", -1)])
        await audit.create_index("timestamp", expireAfterSeconds=180 * 86400)  # 6-month TTL


# ── Singleton ──────────────────────────────────────────────────────

_worker: ReencryptionWorker | None = None


def get_reencryption_worker() -> ReencryptionWorker:
    """Get or create the singleton ReencryptionWorker."""
    global _worker
    if _worker is None:
        _worker = ReencryptionWorker()
    return _worker
