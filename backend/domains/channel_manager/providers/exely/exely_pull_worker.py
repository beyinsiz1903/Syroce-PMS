"""
Exely Reservation Pull Worker
Scheduled pull via OTA_ReadRQ → common ingest pipeline.
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional

from core.database import db
from domains.channel_manager.providers.common_ingest import ingest_reservation, log_sync
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.normalizer import normalize_reservation
from domains.channel_manager.providers.exely.auto_import import auto_import_pending
from domains.channel_manager.credential_vault import get_decrypted_credentials

logger = logging.getLogger(__name__)

PROVIDER = "exely"


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
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(interval_seconds, safety_window_minutes))
        logger.info(f"[EXELY-PULL] Scheduler started: every {interval_seconds}s")

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
                logger.error(f"[EXELY-PULL] Loop error: {e}")
            await asyncio.sleep(interval_seconds)

    async def _heartbeat(self, provider: ExelyProvider, tenant_id: str):
        """Send a room discovery request to keep the connection alive in Exely."""
        try:
            from datetime import datetime, timedelta
            tomorrow = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
            week = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d")
            result = await provider.discover_rooms(tomorrow, week)
            logger.info(f"[EXELY-PULL] Heartbeat for {tenant_id}: success={result.success}")
        except Exception as e:
            logger.warning(f"[EXELY-PULL] Heartbeat failed for {tenant_id}: {e}")

    async def _pull_all_tenants(self, safety_window_minutes: int):
        connections = await db.exely_connections.find(
            {"is_active": True, "auto_sync_reservations": True},
            {"_id": 0},
        ).to_list(100)

        for conn in connections:
            try:
                tenant_id = conn["tenant_id"]
                hotel_code = conn["hotel_code"]
                endpoint_url = conn.get("endpoint_url", "")

                # Get credentials from vault
                creds = await get_decrypted_credentials(tenant_id, "exely", hotel_code)
                if not creds:
                    logger.error(f"[EXELY-PULL] No vault credentials for tenant {tenant_id}, hotel {hotel_code}")
                    continue

                await self.pull_for_tenant(
                    tenant_id=tenant_id,
                    username=creds["username"],
                    password=creds["password"],
                    hotel_code=hotel_code,
                    endpoint_url=endpoint_url or creds.get("endpoint_url", ""),
                    safety_window_minutes=safety_window_minutes,
                )
            except Exception as e:
                logger.error(f"[EXELY-PULL] Error for tenant {conn.get('tenant_id', '?')}: {e}")

    async def pull_for_tenant(
        self,
        tenant_id: str,
        username: str,
        password: str,
        hotel_code: str,
        endpoint_url: str = "",
        safety_window_minutes: int = 5,
    ) -> Dict[str, Any]:
        provider_kwargs = {"username": username, "password": password, "hotel_code": hotel_code}
        if endpoint_url:
            provider_kwargs["endpoint_url"] = endpoint_url
        provider = ExelyProvider(**provider_kwargs)

        # Heartbeat: keep connection alive in Exely
        await self._heartbeat(provider, tenant_id)

        # Cursor: last pull time - safety window
        cursor_doc = await db.exely_pull_cursors.find_one(
            {"tenant_id": tenant_id}, {"_id": 0},
        )

        if cursor_doc and cursor_doc.get("last_pull_at"):
            last_pull = datetime.fromisoformat(cursor_doc["last_pull_at"])
            fetch_from = last_pull - timedelta(minutes=safety_window_minutes)
        else:
            fetch_from = datetime.now(timezone.utc) - timedelta(days=7)

        from_date = fetch_from.strftime("%Y-%m-%d")
        to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        pull_start = datetime.now(timezone.utc)

        result = await provider.legacy_pull_reservations(from_date=from_date, to_date=to_date)

        if not result["success"]:
            await log_sync(PROVIDER, tenant_id, "scheduled_pull", "failed", error=result.get("error"))
            return {"success": False, "error": result.get("error")}

        reservations = result.get("reservations", [])
        processed = 0

        for raw_res in reservations:
            # Determine event type from status
            status = (raw_res.get("status") or "").lower()
            if status in ("cancel", "cancelled"):
                event_type = "cancellation"
            elif status in ("modify", "modified"):
                event_type = "modification"
            else:
                event_type = "reservation"

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
            {"$set": {
                "tenant_id": tenant_id,
                "last_pull_at": pull_start.isoformat(),
                "last_fetch_from": from_date,
                "reservations_fetched": len(reservations),
                "reservations_processed": processed,
            }},
            upsert=True,
        )

        duration_ms = int((datetime.now(timezone.utc) - pull_start).total_seconds() * 1000)
        await log_sync(PROVIDER, tenant_id, "scheduled_pull", "success", duration_ms, processed)

        # Auto-import all pending reservations to PMS
        if processed > 0:
            import_result = await auto_import_pending(tenant_id)
            logger.info(f"[EXELY-PULL] Auto-import: {import_result['imported']}/{import_result['total']} imported")

        logger.info(f"[EXELY-PULL] Tenant {tenant_id}: fetched {len(reservations)}, processed {processed}")
        return {
            "success": True,
            "fetched": len(reservations),
            "processed": processed,
            "from_date": from_date,
        }


# Singleton
exely_pull_scheduler = ExelyPullScheduler()
