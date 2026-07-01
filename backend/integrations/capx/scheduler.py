"""CapX availability scheduler — periodic snapshot push.

Pattern: Exely pull worker / HR push queue worker ile aynı.
Interval default 900s (15 dk). Aktif tenant için tüm room_type'ları tarar
ve önümüzdeki 30 günü CapX'e snapshot olarak gönderir.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from core.database import _raw_db
from core.transient_db_guard import TransientFailureTracker
from integrations.capx.client import CapXError, get_capx_client, get_capx_client_async

logger = logging.getLogger(__name__)

_transient_tracker = TransientFailureTracker("capx-availability")


class CapXAvailabilityScheduler:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self, *, interval_seconds: int = 900, lookahead_days: int = 30) -> None:
        if self._task and not self._task.done():
            logger.info("CapX availability scheduler zaten çalışıyor")
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._loop(interval_seconds, lookahead_days))
        logger.info("✅ CapX Availability Scheduler started (%ds, lookahead=%dd)", interval_seconds, lookahead_days)

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=5)
            except TimeoutError:
                self._task.cancel()

    async def _loop(self, interval: int, lookahead: int) -> None:
        # Pattern: `wait_for(stop.wait(), timeout=N)` interval süresi kadar
        # interruptible sleep. Timeout dolarsa TimeoutError → devam.
        # Event set edilirse (stop() çağrısı) normal döner → break ile çık.

        # İlk push'u 30sn sonra yap (cold-start trafiği bozmasın)
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=30)
            return  # stop() erken çağrıldı
        except TimeoutError:
            pass  # 30sn doldu, normal akış

        while not self._stop.is_set():
            try:
                await self._push_cycle(lookahead)
                _transient_tracker.reset(TransientFailureTracker.OUTER_LOOP_KEY)
            except Exception as e:
                _transient_tracker.log_exception(
                    logger,
                    e,
                    TransientFailureTracker.OUTER_LOOP_KEY,
                    context="availability cycle",
                    non_transient_msg="%s availability cycle error: %s",
                )
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
                break  # stop() çağrıldı → graceful exit
            except TimeoutError:
                continue  # interval doldu → sonraki cycle

    async def _push_cycle(self, lookahead_days: int) -> None:
        # Faz 3: env-default client'a bak; tenant'a özel client _per-tenant
        # döngüde çözülür (env config yoksa bile tenant-creds varsa çalışsın).
        env_client = get_capx_client(refresh=False)
        env_ok = env_client.configured

        # Aktif tenant'ları topla. env yapılandırılmamışsa SADECE
        # capx_tenant_credentials kaydı olan tenant'ları gez (gereksiz tarama
        # yok). env yapılandırılmışsa tüm aktif organizasyonlar.
        tenants: list[str] = []
        if env_ok:
            async for t in _raw_db.organizations.find(
                {"$or": [{"is_active": True}, {"is_active": {"$exists": False}}]},
                {"_id": 0, "id": 1},
            ):
                if t.get("id"):
                    tenants.append(t["id"])
        else:
            tenants = [tid for tid in await _raw_db["capx_tenant_credentials"].distinct("tenant_id") if tid]

        if not tenants:
            return

        today = datetime.now(UTC).date()
        end = today + timedelta(days=lookahead_days)
        pushed = 0
        errors = 0

        for tid in tenants:
            # Faz 3: tenant-aware client (tenant kayıtlı değilse env fallback).
            client = await get_capx_client_async(tenant_id=tid)
            if not client.configured:
                continue  # env de tenant da config yok — sessiz
            # room_types collection'dan tipleri çek
            room_types: list[str] = []
            async for rt in _raw_db.room_types.find({"tenant_id": tid}, {"_id": 0, "code": 1, "name": 1}):
                code = rt.get("code") or rt.get("name")
                if code:
                    room_types.append(code)

            if not room_types:
                continue

            for rtype in room_types:
                # Müsait oda sayısı: rooms - aktif booking
                total = await _raw_db.rooms.count_documents({"tenant_id": tid, "room_type": rtype, "is_active": True})
                if total == 0:
                    continue
                # Önümüzdeki dönemde booked
                booked = await _raw_db.bookings.count_documents(
                    {
                        "tenant_id": tid,
                        "status": {"$in": ["confirmed", "guaranteed", "checked_in"]},
                        "check_in": {"$lt": end.isoformat()},
                        "check_out": {"$gt": today.isoformat()},
                    }
                )
                available = max(0, total - booked)
                if available == 0:
                    continue

                # En düşük fiyat
                price_min = 0.0
                price_doc = await _raw_db.rate_plans.find_one(
                    {"tenant_id": tid, "room_type": rtype, "is_active": True},
                    {"_id": 0, "base_rate": 1, "price": 1},
                )
                if price_doc:
                    price_min = float(price_doc.get("base_rate") or price_doc.get("price") or 0)

                snapshot = {
                    "room_type": rtype,
                    "start_date": today.isoformat(),
                    "end_date": end.isoformat(),
                    "available_count": available,
                    "price_min": price_min,
                    "currency": "TRY",
                    "auto_publish": True,
                    "pms_external_ref": f"syroce-{tid[:8]}-{rtype}-{today.isoformat()}",
                }

                try:
                    await client.push_availability(snapshot)
                    pushed += 1
                except CapXError as exc:
                    errors += 1
                    logger.warning("CapX availability push failed (tenant=%s rtype=%s): %s", tid[:8], rtype, exc)

        if pushed or errors:
            logger.info("CapX availability cycle: pushed=%d errors=%d", pushed, errors)


availability_scheduler = CapXAvailabilityScheduler()
