"""
Exely Reservation Pull Worker
Scheduled pull via OTA_ReadRQ → common ingest pipeline.
"""
import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db
from core.secrets import get_secrets_manager
from core.tenant_db import clear_tenant_context, set_tenant_context
from domains.channel_manager.credential_vault import get_decrypted_credentials
from domains.channel_manager.providers.common_ingest import ingest_reservation, log_sync
from domains.channel_manager.providers.exely.auto_import import auto_import_pending
from domains.channel_manager.providers.exely.normalizer import normalize_reservation
from domains.channel_manager.providers.exely.provider import ExelyProvider

logger = logging.getLogger(__name__)

PROVIDER = "exely"


async def _resolve_exely_credentials(
    tenant_id: str, hotel_code: str, conn: dict[str, Any] | None = None
) -> dict[str, str] | None:
    """
    Resolve Exely credentials with a 3-tier fallback chain (mirrors HotelRunner).

    1) New SecretsManager (encrypted, AAD-bound) — written by /api/exely/connect
    2) Legacy credential vault (`provider_secrets` collection) — older deployments
    3) Plaintext on the connection document — seed data / pre-vault records
    """
    # Tier 1: New SecretsManager (preferred)
    try:
        sm = get_secrets_manager()
        creds = await sm.get_provider_credentials(tenant_id, PROVIDER, hotel_code)
        if creds and creds.get("username") and creds.get("password"):
            return {
                "username": creds["username"],
                "password": creds["password"],
                "endpoint_url": creds.get("endpoint_url", ""),
            }
    except Exception as e:
        logger.warning(f"[EXELY-CREDS] SecretsManager lookup failed for {tenant_id}/{hotel_code}: {e}")

    # Tier 2: Legacy credential vault
    try:
        legacy = await get_decrypted_credentials(tenant_id, PROVIDER, hotel_code)
        if legacy and legacy.get("username") and legacy.get("password"):
            return {
                "username": legacy["username"],
                "password": legacy["password"],
                "endpoint_url": legacy.get("endpoint_url", ""),
            }
    except Exception as e:
        logger.warning(f"[EXELY-CREDS] Legacy vault lookup failed for {tenant_id}/{hotel_code}: {e}")

    # Tier 3: Plaintext on connection doc (seed / pre-vault)
    if conn is None:
        conn = await db.exely_connections.find_one(
            {"tenant_id": tenant_id, "hotel_code": hotel_code}, {"_id": 0}
        )
    if conn and conn.get("username") and conn.get("password"):
        logger.warning(
            f"[EXELY-CREDS] Using legacy plaintext credentials for tenant {tenant_id}, "
            f"hotel {hotel_code}. Re-save via /api/exely/connect to migrate to vault."
        )
        return {
            "username": conn["username"],
            "password": conn["password"],
            "endpoint_url": conn.get("endpoint_url", ""),
        }

    return None


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
            tomorrow = (datetime.now(UTC) + timedelta(days=1)).strftime("%Y-%m-%d")
            week = (datetime.now(UTC) + timedelta(days=7)).strftime("%Y-%m-%d")
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
            tenant_id = conn.get("tenant_id", "")
            try:
                set_tenant_context(tenant_id)
                hotel_code = conn["hotel_code"]
                endpoint_url = conn.get("endpoint_url", "")

                creds = await _resolve_exely_credentials(tenant_id, hotel_code, conn)
                if not creds:
                    logger.warning(
                        f"[EXELY-PULL] No credentials available for tenant {tenant_id}, hotel {hotel_code}. "
                        f"Connect Exely from the UI (Channel Manager → Exely → Connect) to enable auto-pull."
                    )
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
                logger.error(f"[EXELY-PULL] Error for tenant {tenant_id or '?'}: {e}")
            finally:
                clear_tenant_context()

    async def pull_for_tenant(
        self,
        tenant_id: str,
        username: str,
        password: str,
        hotel_code: str,
        endpoint_url: str = "",
        safety_window_minutes: int = 5,
    ) -> dict[str, Any]:
        set_tenant_context(tenant_id)
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
            fetch_from = datetime.now(UTC) - timedelta(days=7)

        from_date = fetch_from.strftime("%Y-%m-%d")
        to_date = datetime.now(UTC).strftime("%Y-%m-%d")
        pull_start = datetime.now(UTC)

        result = await provider.legacy_pull_reservations(from_date=from_date, to_date=to_date)

        if not result["success"]:
            await log_sync(PROVIDER, tenant_id, "scheduled_pull", "failed", error=result.get("error"))
            return {"success": False, "error": result.get("error")}

        reservations = result.get("reservations", [])
        processed = 0

        for raw_res in reservations:
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
                        {"tenant_id": tenant_id, "external_id": ext_id,
                         "pms_status": {"$in": ["imported", "confirmed"]}},
                        {"_id": 0, "provider_last_modified_at": 1,
                         "guest_name": 1, "checkin_date": 1, "checkout_date": 1},
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

                        if ((new_lm and old_lm and new_lm != old_lm) or
                            (new_name and old_name and new_name != old_name) or
                            (new_ci and old_ci and new_ci != old_ci) or
                            (new_co and old_co and new_co != old_co)):
                            event_type = "modification"
                            logger.info(f"[EXELY-PULL] Detected modification for {ext_id} (status={status})")

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

        duration_ms = int((datetime.now(UTC) - pull_start).total_seconds() * 1000)
        await log_sync(PROVIDER, tenant_id, "scheduled_pull", "success", duration_ms, processed)

        # Auto-import all pending reservations to PMS + process cancellations + modifications
        import_result = await auto_import_pending(tenant_id, provider=provider)
        logger.info(f"[EXELY-PULL] Auto-import: {import_result['imported']}/{import_result['total']} imported, {import_result.get('updated', 0)} updated")

        # Auto-confirm delivery for all newly imported reservations
        await self._auto_confirm_deliveries(provider, tenant_id)

        # Individual check for cancellations and modifications that batch pull may miss
        try:
            cancel_detected = await self._check_individual_changes(provider, tenant_id)
            if cancel_detected.get("cancelled", 0) > 0 or cancel_detected.get("modified", 0) > 0:
                # Re-run auto_import to process any new changes
                import_result2 = await auto_import_pending(tenant_id, provider=provider)
                logger.info(f"[EXELY-PULL] Post-individual-check import: "
                            f"{import_result2.get('updated', 0)} updated, {import_result2.get('cancelled', 0)} cancelled")
        except Exception as e:
            logger.warning(f"[EXELY-PULL] Individual check error: {e}")

        logger.info(f"[EXELY-PULL] Tenant {tenant_id}: fetched {len(reservations)}, processed {processed}")
        return {
            "success": True,
            "fetched": len(reservations),
            "processed": processed,
            "from_date": from_date,
        }

    async def _check_individual_changes(self, provider: ExelyProvider, tenant_id: str) -> dict[str, int]:
        """Check individual imported reservations for cancellations and modifications.
        Only check reservations with check-in within the next 30 days for performance."""
        cutoff_date = (datetime.now(UTC) + timedelta(days=30)).strftime("%Y-%m-%d")
        imported = await db.exely_reservations.find(
            {"tenant_id": tenant_id,
             "state": {"$in": ["confirmed", "modified", "pending"]},
             "pms_status": "imported",
             "checkin_date": {"$lte": cutoff_date}},
            {"_id": 0, "external_id": 1, "provider_reservation_id": 1,
             "guest_name": 1, "checkin_date": 1, "checkout_date": 1,
             "rooms": 1, "provider_last_modified_at": 1},
        ).to_list(20)  # Reduced from 50 to 20 for speed

        if not imported:
            return {"cancelled": 0, "modified": 0}

        cancel_count = 0
        mod_count = 0

        for res in imported:
            ext_id = res.get("external_id", "")
            prov_res_id = res.get("provider_reservation_id", ext_id)
            try:
                pull_result = await provider.legacy_pull_reservations(reservation_id=prov_res_id)
                if not pull_result.get("success"):
                    continue
                reservations = pull_result.get("reservations", [])
                if not reservations:
                    continue
                raw_res = reservations[0]
                status = (raw_res.get("status") or "").lower()

                if status in ("cancel", "cancelled"):
                    ingest_result = await ingest_reservation(
                        provider=PROVIDER, tenant_id=tenant_id,
                        raw_payload=raw_res, normalizer=normalize_reservation,
                        event_type="cancellation", source="scheduled_cancel_check",
                    )
                    if ingest_result.get("action") == "cancelled":
                        cancel_count += 1
                    continue

                # Check for modifications
                changed = False
                new_last_modify = raw_res.get("last_modify", "")
                stored_last_modify = res.get("provider_last_modified_at", "")
                if new_last_modify and stored_last_modify and new_last_modify != stored_last_modify:
                    changed = True

                new_name = raw_res.get("guest_name", "")
                if new_name and new_name != res.get("guest_name", ""):
                    changed = True
                new_checkin = raw_res.get("checkin_date", "")
                if new_checkin and new_checkin[:10] != (res.get("checkin_date", "") or "")[:10]:
                    changed = True
                new_checkout = raw_res.get("checkout_date", "")
                if new_checkout and new_checkout[:10] != (res.get("checkout_date", "") or "")[:10]:
                    changed = True

                if changed:
                    ingest_result = await ingest_reservation(
                        provider=PROVIDER, tenant_id=tenant_id,
                        raw_payload=raw_res, normalizer=normalize_reservation,
                        event_type="modification", source="scheduled_mod_check",
                    )
                    if ingest_result.get("action") in ("updated", "created"):
                        mod_count += 1
                        logger.info(f"[EXELY-PULL] Modification detected for {ext_id}")
            except Exception as e:
                logger.warning(f"[EXELY-PULL] Individual check error for {ext_id}: {e}")

        return {"cancelled": cancel_count, "modified": mod_count}

    async def _auto_confirm_deliveries(self, provider: ExelyProvider, tenant_id: str):
        """Auto-confirm delivery for all imported but unconfirmed reservations."""
        try:
            unconfirmed = await db.exely_reservations.find(
                {
                    "tenant_id": tenant_id,
                    "delivery_confirmed": {"$ne": True},
                    "pms_status": {"$in": ["imported", "confirmed"]},
                    "state": {"$ne": "cancelled"},
                },
                {"_id": 0, "external_id": 1, "pms_booking_id": 1, "provider_last_modified_at": 1, "created_at": 1},
            ).to_list(50)

            if not unconfirmed:
                return

            confirmed = 0
            for res in unconfirmed:
                ext_id = res.get("external_id", "")
                pms_id = res.get("pms_booking_id", ext_id)
                create_dt = res.get("provider_last_modified_at") or res.get("created_at")
                modify_dt = res.get("provider_last_modified_at")
                try:
                    result = await provider.confirm_delivery(
                        ext_id, pms_id,
                        create_datetime=create_dt,
                        last_modify_datetime=modify_dt,
                        res_status="Reserved",
                    )
                    if result.success:
                        await db.exely_reservations.update_one(
                            {"tenant_id": tenant_id, "external_id": ext_id},
                            {"$set": {"delivery_confirmed": True, "delivery_confirmed_at": datetime.now(UTC).isoformat()}},
                        )
                        confirmed += 1
                    else:
                        logger.warning(f"[EXELY-PULL] Delivery confirm failed for {ext_id}: {result.error}")
                except Exception as e:
                    logger.warning(f"[EXELY-PULL] Delivery confirm error for {ext_id}: {e}")

            if confirmed:
                logger.info(f"[EXELY-PULL] Auto-confirmed {confirmed}/{len(unconfirmed)} deliveries for tenant {tenant_id}")
        except Exception as e:
            logger.warning(f"[EXELY-PULL] Auto-confirm error: {e}")


# Singleton
exely_pull_scheduler = ExelyPullScheduler()
