import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

import pymongo.errors
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core.integrations.incoming_invoice_sync_service import IncomingInvoiceSyncService
from core.integrations.nilvera.errors import NilveraApiError
from core.integrations.nilvera.worker_health import NilveraWorkerHealthMixin
from core.tenant_db import get_db_for_tenant, get_system_db
from models.schemas.invoice_sync import InvoiceProvider
from models.schemas.nilvera_worker_health import NilveraWorkerErrorCode

logger = logging.getLogger(__name__)


class IncomingInvoiceSyncWorker(NilveraWorkerHealthMixin):
    def __init__(
        self,
        *,
        poll_interval_sec: float = 300.0,
        batch_size: int = 20,
        lease_seconds: int = 1800,
        initial_lookback_days: int = 31,
        overlap_hours: int = 48,
    ):
        super().__init__(worker_name="incoming-invoice-sync-worker")
        if poll_interval_sec <= 0 or batch_size <= 0 or lease_seconds <= 0:
            raise ValueError("Incoming invoice sync worker timing must be positive")
        if not 1 <= initial_lookback_days <= 31:
            raise ValueError("Incoming invoice sync lookback must be between 1 and 31 days")
        if overlap_hours < 0:
            raise ValueError("Incoming invoice sync overlap cannot be negative")
        self._poll_interval_sec = poll_interval_sec
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds
        self._initial_lookback_days = initial_lookback_days
        self._overlap_hours = overlap_hours
        self._worker_id = f"incoming-sync-{uuid.uuid4().hex}"
        self._task: asyncio.Task | None = None
        self._stop_event = asyncio.Event()

    async def start(self) -> None:
        if not self.health.enabled:
            return
        if self._task and not self._task.done():
            return

        self._stop_event.clear()
        self._mark_starting()
        self._task = asyncio.create_task(self._run_loop(), name="incoming-invoice-sync-worker")
        await asyncio.sleep(0)
        if self._task.done():
            self._record_loop_error(NilveraWorkerErrorCode.STARTUP_TASK_FAILED)
            self._mark_failed("STARTUP_TASK_FAILED")
            raise RuntimeError("NILVERA_WORKER_STARTUP_FAILED") from None
        self._mark_running()
        logger.info("Incoming invoice sync worker started")

    async def stop(self) -> None:
        self._stop_event.set()
        if self._task:
            self._mark_stopping()
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=10.0)
            except TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            except asyncio.CancelledError:
                pass
            finally:
                self._task = None
                self._mark_stopped()
        logger.info("Incoming invoice sync worker stopped")

    async def _run_loop(self) -> None:
        try:
            while not self._stop_event.is_set():
                try:
                    self._record_heartbeat()
                    processed = await self._process_batch()
                    if processed == 0:
                        await self._wait_for_next_tick()
                except asyncio.CancelledError:
                    raise
                except (TimeoutError, pymongo.errors.PyMongoError) as exc:
                    self._record_job_error(NilveraWorkerErrorCode.TRANSIENT_DEPENDENCY_ERROR)
                    logger.warning(
                        "Incoming invoice sync loop dependency failure error_type=%s",
                        type(exc).__name__,
                    )
                    await self._wait_for_next_tick()
                except Exception:
                    raise
        except asyncio.CancelledError:
            pass
        except Exception:
            logger.error(
                "NILVERA_WORKER_FATAL_ERROR worker=%s error_code=FATAL_LOOP_ERROR",
                self.worker_name,
            )
            self._record_loop_error(NilveraWorkerErrorCode.FATAL_LOOP_ERROR)
            self._mark_failed("Worker loop crashed")

    async def _wait_for_next_tick(self) -> None:
        try:
            await asyncio.wait_for(self._stop_event.wait(), timeout=self._poll_interval_sec)
        except TimeoutError:
            pass

    async def _process_batch(self) -> int:
        sysdb = get_system_db()
        tenants = sysdb.tenant_settings.find(
            {
                "nilvera.enabled": True,
                "nilvera.api_key_enc": {"$exists": True, "$type": "string", "$ne": ""},
            },
            {"_id": 0, "tenant_id": 1},
        )

        processed = 0
        async for tenant in tenants:
            if self._stop_event.is_set():
                break
            tenant_id = tenant.get("tenant_id")
            if not isinstance(tenant_id, str) or not tenant_id:
                continue
            state = await self._claim_due_sync(tenant_id)
            if state is None:
                continue
            await self._process_tenant(tenant_id, state)
            processed += 1
            if processed >= self._batch_size:
                break
        return processed

    async def _claim_due_sync(self, tenant_id: str) -> dict | None:
        db = get_db_for_tenant(tenant_id)
        now = datetime.now(UTC)
        try:
            await db.incoming_invoice_sync_state.update_one(
                {"tenant_id": tenant_id, "provider": InvoiceProvider.NILVERA.value},
                {
                    "$setOnInsert": {
                        "tenant_id": tenant_id,
                        "provider": InvoiceProvider.NILVERA.value,
                        "next_sync_at": now,
                        "last_successful_end_at": None,
                        "lease_owner": None,
                        "lease_expires_at": None,
                        "last_error_code": None,
                        "version": 1,
                        "created_at": now,
                        "updated_at": now,
                    }
                },
                upsert=True,
            )
        except DuplicateKeyError:
            pass
        return await db.incoming_invoice_sync_state.find_one_and_update(
            {
                "tenant_id": tenant_id,
                "provider": InvoiceProvider.NILVERA.value,
                "next_sync_at": {"$lte": now},
                "$or": [
                    {"lease_expires_at": None},
                    {"lease_expires_at": {"$exists": False}},
                    {"lease_expires_at": {"$lte": now}},
                ],
            },
            {
                "$set": {
                    "lease_owner": self._worker_id,
                    "lease_expires_at": now + timedelta(seconds=self._lease_seconds),
                    "updated_at": now,
                },
                "$inc": {"version": 1},
            },
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0, "last_successful_end_at": 1, "version": 1},
        )

    async def _process_tenant(self, tenant_id: str, state: dict) -> None:
        end_date = datetime.now(UTC)
        minimum_start = end_date - timedelta(days=self._initial_lookback_days)
        last_end = state.get("last_successful_end_at")
        start_date = minimum_start
        if isinstance(last_end, datetime):
            if last_end.tzinfo is None:
                last_end = last_end.replace(tzinfo=UTC)
            start_date = max(minimum_start, last_end - timedelta(hours=self._overlap_hours))

        try:
            result = await IncomingInvoiceSyncService.sync_tenant(
                tenant_id,
                start_date,
                end_date,
            )
        except Exception as exc:
            safe_code = exc.safe_code if isinstance(exc, NilveraApiError) else "INCOMING_SYNC_FAILED"
            await self._complete_failure(tenant_id, safe_code)
            self._record_job_error(NilveraWorkerErrorCode.INCOMING_SYNC_FAILED)
            logger.warning("Incoming invoice sync failed error_code=%s", safe_code)
            return

        completed = await self._complete_success(tenant_id, end_date, result.invoices_seen)
        if not completed:
            self._record_job_error(NilveraWorkerErrorCode.INCOMING_SYNC_FAILED)
            logger.warning("Incoming invoice sync lease was lost before completion")
            return
        self._record_success(1)

    async def _complete_success(
        self,
        tenant_id: str,
        end_date: datetime,
        invoices_seen: int,
    ) -> bool:
        now = datetime.now(UTC)
        db = get_db_for_tenant(tenant_id)
        update_result = await db.incoming_invoice_sync_state.update_one(
            {
                "tenant_id": tenant_id,
                "provider": InvoiceProvider.NILVERA.value,
                "lease_owner": self._worker_id,
            },
            {
                "$set": {
                    "last_successful_end_at": end_date,
                    "last_successful_invoice_count": invoices_seen,
                    "next_sync_at": now + timedelta(seconds=self._poll_interval_sec),
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "last_error_code": None,
                    "updated_at": now,
                },
                "$inc": {"version": 1},
            },
        )
        return update_result.modified_count == 1

    async def _complete_failure(self, tenant_id: str, safe_code: str) -> None:
        now = datetime.now(UTC)
        db = get_db_for_tenant(tenant_id)
        await db.incoming_invoice_sync_state.update_one(
            {
                "tenant_id": tenant_id,
                "provider": InvoiceProvider.NILVERA.value,
                "lease_owner": self._worker_id,
            },
            {
                "$set": {
                    "next_sync_at": now + timedelta(seconds=self._poll_interval_sec),
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "last_error_code": safe_code,
                    "updated_at": now,
                },
                "$inc": {"version": 1},
            },
        )


incoming_invoice_sync_worker = IncomingInvoiceSyncWorker()
