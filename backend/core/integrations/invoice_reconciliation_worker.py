"""
Invoice Reconciliation Worker — Background Worker for ambiguous dispatch reconciliation.
Polls invoice_sync for RECONCILIATION_REQUIRED records and attempts to verify
status via read-only channels.
"""

import asyncio
import logging
import os
import socket
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ReturnDocument

from core.integrations.invoice_reconciliation_service import InvoiceReconciliationService
from core.tenant_db import get_system_db, tenant_context
from core.transient_db_guard import TransientFailureTracker
from models.schemas.invoice_sync import InvoiceSyncState

logger = logging.getLogger("core.integrations.invoice_reconciliation_worker")

_transient_tracker = TransientFailureTracker("invoice-reconciliation-worker")


def _utc_now() -> datetime:
    return datetime.now(UTC)


class InvoiceReconciliationWorker:
    """
    Background worker for processing reconciliation for ambiguous dispatch attempts.
    Does NOT have POST access. Only read-only verification.
    """

    def __init__(
        self,
        *,
        poll_interval: float = 10.0,
        batch_size: int = 10,
        processing_timeout: int = 120,
        drain_pause: float = 0.5,
    ):
        self.poll_interval = poll_interval
        self.batch_size = batch_size
        self.processing_timeout = processing_timeout
        self.drain_pause = drain_pause
        self.worker_id = f"inv-recon-{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="invoice-reconciliation-worker")
        logger.info("Invoice Reconciliation Worker started: %s", self.worker_id)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=5.0)
            except TimeoutError:
                logger.warning("Worker drain timeout exceeded, cancelling task.")
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            finally:
                self._task = None
        logger.info("Invoice Reconciliation Worker stopped: %s", self.worker_id)

    async def _run(self) -> None:
        try:
            while not self._stop.is_set():
                try:
                    await self._recover_stuck()
                    count = await self._process_batch()
                    if count == 0:
                        await asyncio.sleep(self.poll_interval)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    _transient_tracker.log_exception(
                        logger,
                        exc,
                        TransientFailureTracker.OUTER_LOOP_KEY,
                        context="loop tick",
                        non_transient_msg="%s loop error: %s",
                    )
                    await asyncio.sleep(self.poll_interval)
                else:
                    _transient_tracker.reset(TransientFailureTracker.OUTER_LOOP_KEY)
        except asyncio.CancelledError:
            pass

    async def _recover_stuck(self) -> int:
        """Recover records stuck in lease during reconciliation."""
        now = _utc_now()
        sysdb = get_system_db()

        result = await sysdb.invoice_sync.update_many(
            {
                "state": InvoiceSyncState.RECONCILIATION_REQUIRED,
                "status_lease_expires_at": {"$lte": now},
            },
            {
                "$set": {
                    "updated_at": now,
                    "reconciliation_note": "lease expired — recovered by worker",
                    "status_lease_owner": None,
                    "status_lease_expires_at": None,
                },
            },
        )
        return result.modified_count

    async def _process_batch(self) -> int:
        processed = 0
        for _ in range(self.batch_size):
            if self._stop.is_set():
                break
            record = await self._claim_record()
            if not record:
                break
            await self._process_record(record)
            processed += 1
            if self.drain_pause > 0:
                await asyncio.sleep(self.drain_pause)
        return processed

    async def _claim_record(self) -> dict[str, Any] | None:
        """Atomically claim the next eligible invoice sync record for reconciliation."""
        now = _utc_now()
        sysdb = get_system_db()

        record = await sysdb.invoice_sync.find_one_and_update(
            {
                "state": InvoiceSyncState.RECONCILIATION_REQUIRED,
                "$and": [
                    {
                        "$or": [
                            {"next_reconciliation_at": None},
                            {"next_reconciliation_at": {"$exists": False}},
                            {"next_reconciliation_at": {"$lte": now}},
                        ]
                    },
                    {
                        "$or": [
                            {"status_lease_expires_at": None},
                            {"status_lease_expires_at": {"$exists": False}},
                            {"status_lease_expires_at": {"$lte": now}},
                        ]
                    }
                ]
            },
            {
                "$set": {
                    "status_lease_owner": self.worker_id,
                    "status_lease_expires_at": now + timedelta(seconds=self.processing_timeout),
                    "reconciliation_started_at": now,
                    "updated_at": now,
                },
                "$inc": {"version": 1},
            },
            sort=[("next_reconciliation_at", 1)],
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0, "id": 1, "tenant_id": 1, "version": 1},
        )
        # Cycle idempotency: Generate a new cycle ID upon successful claim
        if record:
            new_cycle = uuid.uuid4().hex
            sysdb.invoice_sync.update_one(
                {"id": record["id"], "tenant_id": record["tenant_id"]},
                {"$set": {"current_reconciliation_cycle_id": new_cycle}}
            )

        return record

    async def _process_record(self, record: dict[str, Any]) -> None:
        """Process a single invoice sync record within tenant context."""
        record_id = record.get("id")
        tenant_id = record.get("tenant_id")
        expected_version = record.get("version")

        if not record_id or not tenant_id or expected_version is None:
            logger.error("Invalid record claimed: %s", record)
            return

        with tenant_context(tenant_id):
            nilvera_cfg = await get_nilvera_tenant_config(tenant_id, decrypt_api_key=True)
            reader = None
            if nilvera_cfg.get("enabled") and nilvera_cfg.get("api_key"):
                from core.integrations.nilvera.client import NilveraHttpClient
                from core.integrations.nilvera.config import NilveraEndpoints
                class NilveraReadClient:
                    def __init__(self, api_key: str):
                        self.api_key = api_key
                    async def get_sale_status(self, uuid_str: str) -> dict:
                        async with NilveraHttpClient(api_key=self.api_key) as client:
                            endpoint = NilveraEndpoints.GET_SALE_INVOICE_STATUS.format(uuid=uuid_str)
                            return await client.get(endpoint, correlation_id=uuid_str, retryable=False)
                    async def get_sale_details(self, uuid_str: str) -> dict:
                        async with NilveraHttpClient(api_key=self.api_key) as client:
                            endpoint = NilveraEndpoints.GET_SALE_INVOICE_DETAIL.format(uuid=uuid_str)
                            return await client.get(endpoint, correlation_id=uuid_str, retryable=False)

                reader = NilveraReadClient(nilvera_cfg["api_key"])

            await InvoiceReconciliationService.execute_reconciliation(
                tenant_id,
                record_id,
                expected_version=expected_version,
                worker_id=self.worker_id,
                reader=reader
            )

            # Release lease always after processing
            sysdb = get_system_db()
            await sysdb.invoice_sync.update_one(
                {
                    "id": record_id,
                    "tenant_id": tenant_id,
                    "state": InvoiceSyncState.RECONCILIATION_REQUIRED.value,
                    "version": expected_version,
                    "status_lease_owner": self.worker_id,
                    "status_lease_expires_at": {"$gt": _utc_now()}
                },
                {"$set": {"status_lease_owner": None, "status_lease_expires_at": None}}
            )

invoice_reconciliation_worker = InvoiceReconciliationWorker()
