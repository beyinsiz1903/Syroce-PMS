"""
Availability Reconciliation Worker
===================================
Compares real PMS availability with channel availability every 15 minutes
and automatically corrects discrepancies.

Safety net:
  - Compensates for failed pushes due to network errors
  - Captures availability impact of bookings received via webhook
  - Auto-syncs manual DB changes

Flow:
  15 min -> all tenants -> each room type -> date range (today + 60 days) ->
  calculate real availability -> push to channels
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from core.database import db
from core.tenant_db import clear_tenant_context, set_tenant_context

logger = logging.getLogger("channel_manager.availability_reconciliation")

ACTIVE_STATUSES = ["pending", "confirmed", "guaranteed", "checked_in"]
RECONCILIATION_DAYS = 60


class AvailabilityReconciliationWorker:
    """Periodic availability reconciliation worker."""

    def __init__(self):
        self._running = False
        self._task = None

    async def start(self, interval_seconds: int = 900):
        """Start the worker (default: 15 minutes)."""
        if self._running:
            logger.warning("[AVAIL-RECON] Worker already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(interval_seconds))
        logger.info("[AVAIL-RECON] Worker started: %ds interval", interval_seconds)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("[AVAIL-RECON] Worker stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    async def _run_loop(self, interval_seconds: int):
        await asyncio.sleep(60)
        while self._running:
            try:
                await self._reconcile_all_tenants()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[AVAIL-RECON] Loop error: %s", e)
            await asyncio.sleep(interval_seconds)

    async def _reconcile_all_tenants(self):
        """Reconcile availability for all active tenants."""
        tenant_ids = set()

        async for conn in db.exely_connections.find({"is_active": True}, {"_id": 0, "tenant_id": 1}):
            tenant_ids.add(conn["tenant_id"])

        async for conn in db.hotelrunner_connections.find({"is_active": True}, {"_id": 0, "tenant_id": 1}):
            tenant_ids.add(conn["tenant_id"])

        if not tenant_ids:
            return

        logger.info("[AVAIL-RECON] Starting reconciliation for %d tenants", len(tenant_ids))

        for tenant_id in tenant_ids:
            try:
                set_tenant_context(tenant_id)
                await self._reconcile_tenant(tenant_id)
            except Exception as e:
                logger.error("[AVAIL-RECON] Tenant %s error: %s", tenant_id[:8], e)
            finally:
                clear_tenant_context()

    async def _reconcile_tenant(self, tenant_id: str):
        """Reconcile availability for a single tenant."""
        today = datetime.now(UTC).date()
        end_date = today + timedelta(days=RECONCILIATION_DAYS)
        today_str = today.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        rooms = await db.rooms.find(
            {"tenant_id": tenant_id},
            {"_id": 0, "id": 1, "room_type": 1},
        ).to_list(500)

        room_ids_by_type: dict[str, set[str]] = {}
        total_by_type: dict[str, int] = {}
        for r in rooms:
            rt = r.get("room_type", "")
            if not rt:
                continue
            room_ids_by_type.setdefault(rt, set()).add(r["id"])
            total_by_type[rt] = total_by_type.get(rt, 0) + 1

        if not room_ids_by_type:
            return

        active_bookings = await db.bookings.find(
            {
                "tenant_id": tenant_id,
                "status": {"$in": ACTIVE_STATUSES},
                "check_in": {"$lt": end_str},
                "check_out": {"$gt": today_str},
            },
            {"_id": 0, "room_id": 1, "check_in": 1, "check_out": 1},
        ).to_list(10000)

        availability_by_type: dict[str, dict[str, int]] = {}

        for pms_type, type_room_ids in room_ids_by_type.items():
            total = total_by_type[pms_type]
            date_avail = {}
            d = today
            while d < end_date:
                ds = d.strftime("%Y-%m-%d")
                sold = 0
                for b in active_bookings:
                    if b.get("room_id") not in type_room_ids:
                        continue
                    b_ci = (b.get("check_in") or "")[:10]
                    b_co = (b.get("check_out") or "")[:10]
                    if b_ci <= ds < b_co:
                        sold += 1
                date_avail[ds] = max(total - sold, 0)
                d += timedelta(days=1)
            availability_by_type[pms_type] = date_avail

        push_tasks = []
        push_tasks.append(_push_reconciliation_exely(tenant_id, availability_by_type))
        push_tasks.append(_push_reconciliation_hr(tenant_id, availability_by_type))
        results = await asyncio.gather(*push_tasks, return_exceptions=True)

        total_pushed = sum(r for r in results if isinstance(r, int))
        if total_pushed > 0:
            logger.info(
                "[AVAIL-RECON] Tenant %s: %d pushes completed",
                tenant_id[:8],
                total_pushed,
            )


async def _push_reconciliation_exely(
    tenant_id: str,
    availability_by_type: dict[str, dict[str, int]],
) -> int:
    """Push reconciliation data to Exely."""
    push_count = 0
    try:
        conn = await db.exely_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0})
        if not conn:
            return 0

        from domains.channel_manager.credential_vault import get_decrypted_credentials

        hotel_code = conn.get("hotel_code", "")
        creds = await get_decrypted_credentials(tenant_id, "exely", hotel_code)
        if not creds:
            return 0

        from domains.channel_manager.providers.exely.provider import ExelyProvider

        provider_kwargs = {
            "username": creds.get("username", ""),
            "password": creds.get("password", ""),
            "hotel_code": hotel_code,
            "connection_id": f"{tenant_id}:{hotel_code}",
        }
        if conn.get("endpoint_url"):
            provider_kwargs["endpoint_url"] = conn["endpoint_url"]

        provider = ExelyProvider(**provider_kwargs)

        rate_plans = conn.get("rate_plans", [])
        if not rate_plans:
            return 0

        all_mappings = await db.exely_room_mappings.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(100)

        seen = set()
        unique_mappings = []
        for m in all_mappings:
            key = (m.get("pms_room_type", ""), m.get("exely_room_code", ""))
            if key[0] and key[1] and key not in seen:
                seen.add(key)
                unique_mappings.append(m)

        for mapping in unique_mappings:
            pms_type = mapping.get("pms_room_type", "")
            exely_code = mapping.get("exely_room_code", "")

            date_avail = availability_by_type.get(pms_type)
            if not date_avail:
                continue

            from domains.channel_manager.availability_auto_sync import (
                _group_consecutive_dates_with_same_avail,
            )

            sorted_dates = sorted(date_avail.keys())
            groups = _group_consecutive_dates_with_same_avail(sorted_dates, date_avail)

            for rp in rate_plans:
                rp_code = rp.get("code", "")
                if not rp_code:
                    continue

                for group_start, group_end, avail in groups:
                    try:
                        result = await provider.push_ari(
                            room_type_code=exely_code,
                            rate_plan_code=rp_code,
                            start_date=group_start,
                            end_date=group_end,
                            availability=avail,
                        )
                        if result.success:
                            push_count += 1
                    except Exception as e:
                        logger.error("[AVAIL-RECON] Exely push error: %s", e)

        if push_count > 0:
            logger.info("[AVAIL-RECON] Exely: %d push OK (tenant=%s)", push_count, tenant_id[:8])

    except Exception as e:
        logger.error("[AVAIL-RECON] Exely recon error: %s", e)

    return push_count


async def _push_reconciliation_hr(
    tenant_id: str,
    availability_by_type: dict[str, dict[str, int]],
) -> int:
    """Push reconciliation data to HotelRunner."""
    push_count = 0
    try:
        conn = await db.hotelrunner_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0})
        if not conn:
            return 0

        all_mappings = await db.hotelrunner_room_mappings.find({"tenant_id": tenant_id}, {"_id": 0}).to_list(100)

        seen = set()
        unique_mappings = []
        for m in all_mappings:
            key = (m.get("pms_room_type", ""), m.get("hr_inv_code", ""))
            if key[0] and key[1] and key not in seen:
                seen.add(key)
                unique_mappings.append(m)

        if not unique_mappings:
            return 0

        try:
            from domains.channel_manager.providers.hotelrunner.factory import get_provider as _get_provider

            provider, _ = await _get_provider(tenant_id)
        except Exception as e:
            logger.warning("[AVAIL-RECON] Cannot get HR provider: %s", e)
            return 0

        from domains.channel_manager.availability_auto_sync import (
            _group_consecutive_dates_with_same_avail,
        )

        for mapping in unique_mappings:
            pms_type = mapping.get("pms_room_type", "")
            hr_inv = mapping.get("hr_inv_code", "")

            date_avail = availability_by_type.get(pms_type)
            if not date_avail:
                continue

            sorted_dates = sorted(date_avail.keys())
            groups = _group_consecutive_dates_with_same_avail(sorted_dates, date_avail)

            for group_start, group_end, avail in groups:
                try:
                    result = await provider.update_room(
                        inv_code=hr_inv,
                        start_date=group_start,
                        end_date=group_end,
                        availability=int(avail),
                    )
                    if result.get("success"):
                        push_count += 1
                except Exception as e:
                    logger.error("[AVAIL-RECON] HR push error: %s", e)

        if push_count > 0:
            logger.info("[AVAIL-RECON] HR: %d push OK (tenant=%s)", push_count, tenant_id[:8])

    except Exception as e:
        logger.error("[AVAIL-RECON] HR recon error: %s", e)

    return push_count


availability_reconciliation_worker = AvailabilityReconciliationWorker()
