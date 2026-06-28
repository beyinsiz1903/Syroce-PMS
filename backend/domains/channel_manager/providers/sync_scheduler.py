"""
HotelRunner Reservation Pull Scheduler

Cursor-based background worker that manages scheduled pulling
of reservations for all active tenants.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from core.database import db
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

    async def start(self, interval_minutes: int = 15, safety_window_minutes: int = 5, interval_seconds: int | None = None):
        if self._running:
            logger.warning("[PULL] Scheduler already running")
            return
        self._running = True
        sleep_seconds = interval_seconds if interval_seconds is not None else interval_minutes * 60
        self._base_interval = sleep_seconds
        self._task = asyncio.create_task(self._run_loop(sleep_seconds, safety_window_minutes))
        logger.info(f"[PULL] Scheduler started: every {sleep_seconds}s, safety window {safety_window_minutes}min")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("[PULL] Scheduler stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    async def _run_loop(self, sleep_seconds: int, safety_window_minutes: int):
        while self._running:
            try:
                await self._pull_all_tenants(safety_window_minutes)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[PULL] Loop error: {e}")

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
        self._cycle_count += 1
        connections = await db.hotelrunner_connections.find(
            {"is_active": True, "auto_sync_reservations": True},
            {"_id": 0},
        ).to_list(100)

        for conn in connections:
            try:
                tenant_id = conn["tenant_id"]
                hr_id = conn.get("hr_id", conn.get("property_id", "default"))

                from core.secrets import get_secrets_manager

                sm = get_secrets_manager()
                creds = await sm.get_provider_credentials(tenant_id, "hotelrunner", hr_id)

                if not creds or not creds.get("token"):
                    if conn.get("token"):
                        creds = {"token": conn["token"], "hr_id": hr_id}
                    else:
                        logger.error(f"[PULL] No credentials for tenant {tenant_id} — skipping")
                        continue

                await self.pull_for_tenant(
                    tenant_id=tenant_id,
                    token=creds["token"],
                    hr_id=creds.get("hr_id", hr_id),
                    safety_window_minutes=safety_window_minutes,
                )
            except Exception as e:
                logger.error(f"[PULL] Error for tenant {conn.get('tenant_id', '?')}: {e}")

    async def pull_for_tenant(
        self,
        tenant_id: str,
        token: str,
        hr_id: str,
        safety_window_minutes: int = 5,
        is_manual: bool = False,
    ) -> dict[str, Any]:
        from core.tenant_db import set_tenant_context

        set_tenant_context(tenant_id)

        from domains.channel_manager.providers.hotelrunner import HotelRunnerProvider

        retries = 3 if is_manual else 2
        provider = HotelRunnerProvider(token=token, hr_id=hr_id, max_retries=retries)
        pull_start = datetime.now(UTC)

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
            except Exception as e:
                logger.warning(f"[PULL-A6] Modification sync error: {e}")

        catchup_imported = 0
        catchup_updated = 0
        if self._consecutive_rate_limits > 0:
            run_b = False
            logger.info("[PULL] Skipping Phase B — rate limit backoff active (consecutive: %d)", self._consecutive_rate_limits)
        else:
            run_b = self._cycle_count % 10 == 0
        if not run_b:
            logger.debug(f"[PULL] Skipping Phase B (cycle {self._cycle_count}, runs every 10th)")
        else:
            logger.info(f"[PULL] Running Phase B catch-up (cycle {self._cycle_count})")

        if run_b:
            try:
                catchup_imported, catchup_updated = await run_phase_b(tenant_id, provider)
            except Exception as e:
                logger.error(f"[PULL-CATCHUP] Error during catch-up pull: {e}")

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
