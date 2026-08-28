"""
HotelRunner Reservation Pull Scheduler

Cursor-based background worker that manages scheduled pulling
of reservations for all active tenants.
"""

import asyncio
import logging
import time
from datetime import UTC, datetime
from typing import Any

from core.database import db
from domains.channel_manager.providers.hotelrunner.credentials import (
    hotelrunner_connection_projection,
    resolve_hotelrunner_credentials,
)
from domains.channel_manager.providers.hotelrunner.production_safety import (
    reservation_sync_block_reason,
)
from domains.channel_manager.providers.sync_engine import (
    log_pull,
    run_phase_a,
    run_phase_a5,
    run_phase_a6,
    run_phase_b,
)

logger = logging.getLogger(__name__)


class ReservationPullScheduler:
    def __init__(self):
        self._running = False
        self._task = None
        self._cycle_count = 0
        self._consecutive_rate_limits = 0
        self._base_interval = 30
        self._lock_error_log_interval = 900.0
        self._last_lock_error_log_at: float | None = None
        self._suppressed_lock_errors = 0

    def _record_lock_acquisition_failure(self, error: Exception) -> None:
        now = time.monotonic()
        if self._last_lock_error_log_at is None or now - self._last_lock_error_log_at >= self._lock_error_log_interval:
            logger.error(
                "[PULL] Distributed lock acquisition failed; skipping cycle to prevent split-brain exception_class=%s suppressed=%d",
                type(error).__name__,
                self._suppressed_lock_errors,
            )
            self._last_lock_error_log_at = now
            self._suppressed_lock_errors = 0
            return
        self._suppressed_lock_errors += 1
        logger.debug(
            "[PULL] Distributed lock acquisition failure suppressed exception_class=%s",
            type(error).__name__,
        )

    def _reset_lock_acquisition_failures(self) -> None:
        self._last_lock_error_log_at = None
        self._suppressed_lock_errors = 0

    def _should_run_phase_b(self, *, is_manual: bool, has_prior_cursor: bool) -> bool:
        """Run a full reconciliation promptly after each process start.

        The normal ten-cycle cadence remains in place, but the first safe
        cycle of a newly deployed process must also reconcile provider
        history.  Otherwise corrections to already-imported reservations can
        remain invisible for hours unless an operator finds and uses the
        manual HotelRunner sync action.
        """
        return is_manual or self._cycle_count == 1 or not has_prior_cursor or self._cycle_count % 10 == 0

    async def start(self, interval_minutes: int = 15, safety_window_minutes: int = 5, interval_seconds: int | None = None):
        runtime_block = reservation_sync_block_reason()
        if runtime_block:
            logger.warning("[PULL] Scheduler blocked reason=%s", runtime_block)
            return False
        if self._running:
            logger.warning("[PULL] Scheduler already running")
            return False
        self._running = True
        sleep_seconds = interval_seconds if interval_seconds is not None else interval_minutes * 60
        self._base_interval = sleep_seconds
        self._task = asyncio.create_task(self._run_loop(sleep_seconds, safety_window_minutes))
        logger.info(f"[PULL] Scheduler started: every {sleep_seconds}s, safety window {safety_window_minutes}min")
        return True

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("[PULL] Scheduler stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    async def _run_loop(self, sleep_seconds: int, safety_window_minutes: int):
        import os

        from infra.distributed_lock import DistributedLock, lock_manager

        while self._running:
            runtime_block = reservation_sync_block_reason()
            if runtime_block:
                logger.warning("[PULL] Cycle blocked reason=%s", runtime_block)
                await asyncio.sleep(sleep_seconds)
                continue
            # Enforce same deployment key across replicas (do not fallback to hostnames)
            env = os.environ.get("DEPLOYMENT_ENV") or os.environ.get("APP_ENV") or os.environ.get("ENVIRONMENT") or "production"
            redis = lock_manager.get_redis()
            expected_sleep = sleep_seconds

            if self._consecutive_rate_limits > 0:
                expected_sleep = self._base_interval * min(2**self._consecutive_rate_limits, 16)

            if redis is None:
                logger.warning("[PULL] distributed_lock_unavailable — skipping cycle to prevent split-brain")
                await asyncio.sleep(expected_sleep)
                continue

            lock_name = f"syroce:{env}:hotelrunner:pull-cycle"
            # 600 seconds (10 minutes) TTL to safely cover 3x 60s retries + API overhead
            dl = DistributedLock(redis, lock_name, timeout=600.0, retry_count=1)

            try:
                acquired = await dl.acquire()
            except Exception as lock_err:
                self._record_lock_acquisition_failure(lock_err)
                await asyncio.sleep(expected_sleep)
                continue
            self._reset_lock_acquisition_failures()

            if not acquired:
                logger.debug("[PULL] Cycle owned by another worker; skipping")
                await asyncio.sleep(expected_sleep)
                continue

            lock_lost = asyncio.Event()

            # Start a heartbeat to extend the lock if it approaches the 600s TTL
            async def lock_heartbeat():
                while True:
                    await asyncio.sleep(300)  # extend every 5 minutes
                    try:
                        extended = await dl.extend(600.0)
                        if extended:
                            logger.debug("[PULL] Lock extended by 600s via heartbeat")
                        else:
                            logger.warning("[PULL] Failed to extend lock (token mismatch/expired)")
                            lock_lost.set()
                            return
                    except Exception as hb_err:
                        logger.error(
                            "[PULL] Heartbeat error exception_class=%s",
                            type(hb_err).__name__,
                        )
                        lock_lost.set()
                        return

            heartbeat_task = asyncio.create_task(lock_heartbeat())
            pull_task = asyncio.create_task(self._pull_all_tenants(safety_window_minutes))
            lost_task = asyncio.create_task(lock_lost.wait())

            try:
                done, _ = await asyncio.wait(
                    {pull_task, lost_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                if lost_task in done and lock_lost.is_set():
                    pull_task.cancel()
                    await asyncio.gather(pull_task, return_exceptions=True)
                    logger.error("[PULL] Distributed lock lost; cycle aborted")
                else:
                    # pull_task finished successfully or with an exception before lock was lost
                    await pull_task

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(
                    "[PULL] Loop error exception_class=%s",
                    type(exc).__name__,
                )
            finally:
                if not heartbeat_task.done():
                    heartbeat_task.cancel()
                    await asyncio.gather(heartbeat_task, return_exceptions=True)

                if not pull_task.done():
                    pull_task.cancel()
                    await asyncio.gather(pull_task, return_exceptions=True)

                if not lost_task.done():
                    lost_task.cancel()
                    await asyncio.gather(lost_task, return_exceptions=True)

                await dl.release()

            if self._consecutive_rate_limits > 0:
                backoff_multiplier = min(2**self._consecutive_rate_limits, 16)
                actual_sleep = self._base_interval * backoff_multiplier
                logger.warning(
                    "[PULL] Rate-limit backoff active: sleeping %ds (base=%ds, consecutive_429=%d)",
                    actual_sleep,
                    self._base_interval,
                    self._consecutive_rate_limits,
                )
                await asyncio.sleep(actual_sleep)
            else:
                await asyncio.sleep(sleep_seconds)

    async def _pull_all_tenants(self, safety_window_minutes: int):
        runtime_block = reservation_sync_block_reason()
        if runtime_block:
            logger.warning("[PULL] Tenant scan blocked reason=%s", runtime_block)
            return
        self._cycle_count += 1
        connections = await db.hotelrunner_connections.find(
            {"is_active": True, "auto_sync_reservations": True},
            hotelrunner_connection_projection(),
        ).to_list(100)

        for conn in connections:
            try:
                tenant_id = conn["tenant_id"]
                hr_id = conn.get("hr_id", conn.get("property_id", "default"))

                creds = await resolve_hotelrunner_credentials(
                    tenant_id,
                    conn,
                    actor="hotelrunner.scheduler",
                )
                if not creds:
                    logger.error("[PULL] Credentials unavailable; tenant skipped")
                    continue

                await self.pull_for_tenant(
                    tenant_id=tenant_id,
                    token=creds["token"],
                    hr_id=creds.get("hr_id", hr_id),
                    safety_window_minutes=safety_window_minutes,
                )
            except Exception as e:
                logger.error("[PULL] Tenant pull failed exception_class=%s", type(e).__name__)

    async def pull_for_tenant(
        self,
        tenant_id: str,
        token: str,
        hr_id: str,
        safety_window_minutes: int = 5,
        is_manual: bool = False,
    ) -> dict[str, Any]:
        runtime_block = reservation_sync_block_reason()
        if runtime_block:
            return {
                "success": False,
                "error": runtime_block,
                "provider_read_count": 0,
                "provider_write_count": 0,
            }

        from core.tenant_db import set_tenant_context

        set_tenant_context(tenant_id)

        from domains.channel_manager.providers.hotelrunner import HotelRunnerProvider

        retries = 3 if is_manual else 2
        provider = HotelRunnerProvider(token=token, hr_id=hr_id, max_retries=retries)
        pull_start = datetime.now(UTC)

        # Mapping UI and durable import historically used separate collections.
        # Backfill locally before processing any reservation; no provider write.
        from domains.channel_manager.providers.hotelrunner.mapping_bridge import backfill_hotelrunner_mappings

        await backfill_hotelrunner_mappings(tenant_id)
        prior_cursor = await db.hotelrunner_pull_cursors.find_one(
            {"tenant_id": tenant_id}, {"_id": 0, "last_pull_at": 1}
        )

        phase_a_result = await run_phase_a(tenant_id, provider, safety_window_minutes, is_manual)
        if not phase_a_result["success"]:
            if phase_a_result.get("rate_limited"):
                self._consecutive_rate_limits += 1
                logger.warning(
                    "[PULL] Rate limit detected (consecutive: %d) — will back off on next cycle",
                    self._consecutive_rate_limits,
                )
            return {"success": False, "error": phase_a_result.get("error", "")}

        all_reservations = phase_a_result["all_reservations"]
        processed = phase_a_result["processed"]
        fired = phase_a_result["fired"]
        total_pages = phase_a_result["pages"]

        if all_reservations or total_pages > 1:
            self._consecutive_rate_limits = 0

        mod_processed = await run_phase_a5(tenant_id, provider, safety_window_minutes)

        individual_updated = 0
        if mod_processed > 0:
            try:
                individual_updated = await run_phase_a6(tenant_id)
            except Exception as exc:
                logger.warning(
                    "[PULL-A6] Modification sync error exception_class=%s",
                    type(exc).__name__,
                )

        catchup_imported = 0
        catchup_updated = 0
        if self._consecutive_rate_limits > 0:
            run_b = False
            logger.info("[PULL] Skipping Phase B — rate limit backoff active (consecutive: %d)", self._consecutive_rate_limits)
        else:
            run_b = self._should_run_phase_b(
                is_manual=is_manual,
                has_prior_cursor=bool(prior_cursor),
            )
        if not run_b:
            logger.debug(f"[PULL] Skipping Phase B (cycle {self._cycle_count}, runs every 10th)")
        else:
            logger.info(f"[PULL] Running Phase B catch-up (cycle {self._cycle_count})")

        if run_b:
            try:
                catchup_imported, catchup_updated = await run_phase_b(tenant_id, provider)
            except Exception as exc:
                logger.error(
                    "[PULL-CATCHUP] Error during catch-up pull exception_class=%s",
                    type(exc).__name__,
                )

        await db.hotelrunner_pull_cursors.update_one(
            {"tenant_id": tenant_id},
            {
                "$set": {
                    "tenant_id": tenant_id,
                    "last_pull_at": pull_start.isoformat(),
                    "reservations_fetched": len(all_reservations),
                    "reservations_processed": processed,
                    "reservations_fired": fired,
                    "mod_processed": mod_processed,
                    "individual_updated": individual_updated,
                    "catchup_imported": catchup_imported,
                    "catchup_updated": catchup_updated,
                    "pages_fetched": total_pages,
                }
            },
            upsert=True,
        )

        duration_ms = int((datetime.now(UTC) - pull_start).total_seconds() * 1000)
        total_processed = processed + mod_processed + individual_updated + catchup_imported
        await log_pull(tenant_id, "success", total_processed, duration_ms=duration_ms)

        logger.info(
            f"[PULL] Tenant {tenant_id}: fetched {len(all_reservations)}, "
            f"processed {processed}, fired {fired}, "
            f"mod_a5 {mod_processed}, individual_a6 {individual_updated}, "
            f"catchup {catchup_imported}, updated {catchup_updated}"
        )
        return {
            "success": True,
            "fetched": len(all_reservations),
            "processed": processed,
            "fired": fired,
            "mod_processed": mod_processed,
            "individual_updated": individual_updated,
            "catchup_imported": catchup_imported,
            "catchup_updated": catchup_updated,
            "pages": total_pages,
        }


pull_scheduler = ReservationPullScheduler()
