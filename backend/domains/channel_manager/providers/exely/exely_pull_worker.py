"""
Exely Reservation Pull Worker
Scheduled pull via OTA_ReadRQ → common ingest pipeline.
"""

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from core.database import db
from core.tenant_db import clear_tenant_context, set_tenant_context
from core.transient_db_guard import TransientFailureTracker, is_transient_db_error
from domains.channel_manager.providers.common_ingest import ingest_reservation, log_sync
from domains.channel_manager.providers.exely.auto_import import auto_import_pending
from domains.channel_manager.providers.exely.normalizer import normalize_reservation
from domains.channel_manager.providers.exely.production_safety import reservation_sync_block_reason
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.security import (
    exely_connection_projection,
    resolve_exely_credentials,
    safe_fingerprint,
)

logger = logging.getLogger(__name__)

PROVIDER = "exely"

# Demote transient Atlas hiccups (AutoReconnect / ServerSelectionTimeoutError
# "No primary available for writes" / SSL handshake timeouts) from per-tick
# ERROR (which floods Sentry with non-actionable alerts) to WARNING, while still
# escalating to ERROR once a streak shows a sustained outage. Keyed per tenant
# for the inner loop and by OUTER_LOOP_KEY for the scheduler tick.
_transient_tracker = TransientFailureTracker("EXELY-PULL")


def _record_scheduler_error(exc: BaseException, key: str, context: str) -> None:
    if is_transient_db_error(exc):
        _transient_tracker.log_exception(logger, exc, key, context=context)
        return
    logger.error("[EXELY-PULL] %s failed exception_class=%s", context, type(exc).__name__)


class ExelyPullScheduler:
    """
    Cursor-based scheduled reservation pull from Exely.
    Uses OTA_ReadRQ to fetch undelivered / updated reservations.
    """

    def __init__(self):
        self._running = False
        self._task = None

    async def start(self, interval_seconds: int = 60, safety_window_minutes: int = 5):
        if self._running:
            logger.warning("[EXELY-PULL] Scheduler already running")
            return True
        runtime_block = reservation_sync_block_reason()
        if runtime_block:
            logger.warning("[EXELY-PULL] Scheduler blocked reason=%s", runtime_block)
            return False
        self._running = True
        self._task = asyncio.create_task(self._run_loop(interval_seconds, safety_window_minutes))
        logger.info(f"[EXELY-PULL] Scheduler started: every {interval_seconds}s")
        return True

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("[EXELY-PULL] Scheduler stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    async def _run_loop(self, interval_seconds: int, safety_window_minutes: int):
        while self._running:
            try:
                await self._pull_all_tenants(safety_window_minutes)
            except asyncio.CancelledError:
                break
            except Exception as e:
                _record_scheduler_error(e, TransientFailureTracker.OUTER_LOOP_KEY, "loop_tick")
            else:
                _transient_tracker.reset(TransientFailureTracker.OUTER_LOOP_KEY)
            await asyncio.sleep(interval_seconds)

    async def _heartbeat(self, provider: ExelyProvider, tenant_id: str):
        """Send a room discovery request to keep the connection alive in Exely."""
        try:
            from datetime import datetime, timedelta

            tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
            week = (datetime.now(UTC) + timedelta(days=7)).strftime("%Y-%m-%d")
            result = await provider.discover_rooms(tomorrow, week)
            logger.info("[EXELY-PULL] operation=heartbeat success=%s", result.success)
        except Exception as exc:
            logger.warning("[EXELY-PULL] operation=heartbeat success=false exception_class=%s", type(exc).__name__)

    async def _pull_all_tenants(self, safety_window_minutes: int):
        runtime_block = reservation_sync_block_reason()
        if runtime_block:
            logger.warning("[EXELY-PULL] Tick blocked reason=%s", runtime_block)
            return

        connections = await db.exely_connections.find(
            {"is_active": True, "auto_sync_reservations": True},
            exely_connection_projection(),
        ).to_list(100)

        active_keys: list[str] = []
        for conn in connections:
            tenant_id = conn.get("tenant_id", "")
            key = safe_fingerprint(tenant_id)
            active_keys.append(key)
            try:
                set_tenant_context(tenant_id)
                creds = await resolve_exely_credentials(
                    tenant_id,
                    conn,
                    actor="exely_pull_worker",
                )
                if not creds:
                    logger.warning("[EXELY-PULL] credential_state=missing action=blocked")
                    # Not a transient DB failure — clear any prior streak so a
                    # later genuine hiccup doesn't escalate early off stale state.
                    _transient_tracker.reset(key)
                    continue

                await self.pull_for_tenant(
                    tenant_id=tenant_id,
                    username=creds["username"],
                    password=creds["password"],
                    hotel_code=creds["hotel_code"],
                    endpoint_url=creds["endpoint_url"],
                    safety_window_minutes=safety_window_minutes,
                )
            except Exception as e:
                # Preserve transient streak tracking without serializing exception details.
                _record_scheduler_error(e, key, "tenant_pull")
            else:
                _transient_tracker.reset(key)
            finally:
                clear_tenant_context()

        # Memory hygiene over long uptimes with tenant churn — drop streak
        # counters for connections no longer active (OUTER_LOOP_KEY preserved).
        _transient_tracker.prune(active_keys)

    async def pull_for_tenant(
        self,
        tenant_id: str,
        username: str,
        password: str,
        hotel_code: str,
        endpoint_url: str = "",
    ) -> dict[str, Any]:
        runtime_block = reservation_sync_block_reason()
        if runtime_block:
            return {
                "success": False,
                "error": runtime_block,
                "provider_read_count": 0,
                "provider_write_count": 0,
            }

        set_tenant_context(tenant_id)
        provider_kwargs = {
            "username": username,
            "password": password,
            "hotel_code": hotel_code,
            "tenant_id": tenant_id,
            "property_id": hotel_code,
            "connection_id": f"{tenant_id}:{hotel_code}",
        }
        if endpoint_url:
            provider_kwargs["endpoint_url"] = endpoint_url
        provider = ExelyProvider(**provider_kwargs)

        # Heartbeat: keep connection alive in Exely
        await self._heartbeat(provider, tenant_id)

        pull_start = datetime.now(UTC)

        result = await provider.pull_reservations()

        if not result.success:
            await log_sync(PROVIDER, tenant_id, "scheduled_pull", "failed", error=result.error_type)
            return {"success": False, "error": result.error_type}

        reservations = (result.data or {}).get("reservations", [])
        processed = 0

        for raw_res in reservations:
            raw_res = {**raw_res, "property_id": hotel_code}
            # Determine event type from status
            status = (raw_res.get("status") or "").lower()
            ext_id = raw_res.get("reservation_id", "")

            if status in ("cancel", "cancelled"):
                event_type = "cancellation"
            elif status in ("modify", "modified"):
                event_type = "modification"
            else:
                # Check if this reservation already exists — if so, detect changes
                # even when Exely reports status as "commit"/"confirmed"
                event_type = "reservation"
                if ext_id:
                    existing = await db.exely_reservations.find_one(
                        {"tenant_id": tenant_id, "external_id": ext_id, "pms_status": {"$in": ["imported", "confirmed"]}},
                        {"_id": 0, "provider_last_modified_at": 1, "guest_name": 1, "checkin_date": 1, "checkout_date": 1},
                    )
                    if existing:
                        # Compare last_modify timestamp or key fields
                        new_lm = raw_res.get("last_modify", "")
                        old_lm = existing.get("provider_last_modified_at", "")
                        new_name = raw_res.get("guest_name", "")
                        old_name = existing.get("guest_name", "")
                        new_ci = (raw_res.get("checkin_date", "") or "")[:10]
                        old_ci = (existing.get("checkin_date", "") or "")[:10]
                        new_co = (raw_res.get("checkout_date", "") or "")[:10]
                        old_co = (existing.get("checkout_date", "") or "")[:10]

                        if (
                            (new_lm and old_lm and new_lm != old_lm)
                            or (new_name and old_name and new_name != old_name)
                            or (new_ci and old_ci and new_ci != old_ci)
                            or (new_co and old_co and new_co != old_co)
                        ):
                            event_type = "modification"
                            logger.info("[EXELY-PULL] event=modification_detected")

            ingest_result = await ingest_reservation(
                provider=PROVIDER,
                tenant_id=tenant_id,
                raw_payload=raw_res,
                normalizer=normalize_reservation,
                event_type=event_type,
                source="scheduled_pull",
            )
            if ingest_result.get("success"):
                processed += 1

        # Update cursor
        await db.exely_pull_cursors.update_one(
            {"tenant_id": tenant_id},
            {
                "$set": {
                    "tenant_id": tenant_id,
                    "last_pull_at": pull_start.isoformat(),
                    "selection_type": "Undelivered",
                    "reservations_fetched": len(reservations),
                    "reservations_processed": processed,
                }
            },
            upsert=True,
        )

        duration_ms = int((datetime.now(UTC) - pull_start).total_seconds() * 1000)
        await log_sync(PROVIDER, tenant_id, "scheduled_pull", "success", duration_ms, processed)

        # Auto-import all pending reservations to PMS + process cancellations + modifications
        import_result = await auto_import_pending(tenant_id, provider=provider)
        logger.info(f"[EXELY-PULL] Auto-import: {import_result['imported']}/{import_result['total']} imported, {import_result.get('updated', 0)} updated")

        logger.info("[EXELY-PULL] fetched=%d processed=%d", len(reservations), processed)
        return {
            "success": True,
            "fetched": len(reservations),
            "processed": processed,
            "selection_type": "Undelivered",
            "imported": import_result.get("imported", 0),
            "updated": import_result.get("updated", 0),
            "cancelled": import_result.get("cancelled", 0),
        }


# Singleton
exely_pull_scheduler = ExelyPullScheduler()
