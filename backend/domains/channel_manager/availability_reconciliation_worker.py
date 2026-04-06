"""
Availability Reconciliation Worker
===================================
Her 15 dakikada bir PMS'deki gerçek müsaitlik ile kanallardaki
müsaitliği karşılaştırıp farkları otomatik düzeltir.

Güvenlik ağı:
  - Ağ hatası nedeniyle başarısız olan push'ları telafi eder
  - Webhook ile gelen booking'lerin müsaitlik etkisini yakalar
  - Manuel DB değişikliklerini otomatik sync eder

Akış:
  15 dk → tüm tenant'lar → her room type → tarih aralığı (bugün + 60 gün) →
  gerçek availability hesapla → kanallara push et
"""
import asyncio
import logging
from datetime import datetime, timedelta, timezone

from core.database import db
from core.tenant_db import clear_tenant_context, set_tenant_context

logger = logging.getLogger("channel_manager.availability_reconciliation")

ACTIVE_STATUSES = ["pending", "confirmed", "guaranteed", "checked_in"]
RECONCILIATION_DAYS = 60  # Kaç günlük takvimi kontrol et


class AvailabilityReconciliationWorker:
    """Periyodik müsaitlik uzlaştırma worker'ı."""

    def __init__(self):
        self._running = False
        self._task = None

    async def start(self, interval_seconds: int = 900):
        """Worker'ı başlat (varsayılan: 15 dakika)."""
        if self._running:
            logger.warning("[AVAIL-RECON] Worker zaten çalışıyor")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(interval_seconds))
        logger.info("[AVAIL-RECON] Worker başlatıldı: %ds aralıkla", interval_seconds)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("[AVAIL-RECON] Worker durduruldu")

    @property
    def is_running(self) -> bool:
        return self._running

    async def _run_loop(self, interval_seconds: int):
        # İlk çalışmadan önce 60s bekle (startup yoğunluğunu azalt)
        await asyncio.sleep(60)
        while self._running:
            try:
                await self._reconcile_all_tenants()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[AVAIL-RECON] Loop hatası: %s", e)
            await asyncio.sleep(interval_seconds)

    async def _reconcile_all_tenants(self):
        """Tüm aktif tenant'lar için müsaitlik uzlaştırması yap."""
        # Exely veya HR bağlantısı olan tenant'ları bul
        tenant_ids = set()

        async for conn in db.exely_connections.find(
            {"is_active": True}, {"_id": 0, "tenant_id": 1}
        ):
            tenant_ids.add(conn["tenant_id"])

        async for conn in db.hotelrunner_connections.find(
            {"is_active": True}, {"_id": 0, "tenant_id": 1}
        ):
            tenant_ids.add(conn["tenant_id"])

        if not tenant_ids:
            return

        logger.info("[AVAIL-RECON] %d tenant için uzlaştırma başlıyor", len(tenant_ids))

        for tenant_id in tenant_ids:
            try:
                set_tenant_context(tenant_id)
                await self._reconcile_tenant(tenant_id)
            except Exception as e:
                logger.error("[AVAIL-RECON] Tenant %s hatası: %s", tenant_id[:8], e)
            finally:
                clear_tenant_context()

    async def _reconcile_tenant(self, tenant_id: str):
        """Tek bir tenant için müsaitlik uzlaştırması."""
        today = datetime.now(timezone.utc).date()
        end_date = today + timedelta(days=RECONCILIATION_DAYS)
        today_str = today.strftime("%Y-%m-%d")
        end_str = end_date.strftime("%Y-%m-%d")

        # Odaları room_type'a göre grupla
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

        # Aktif booking'leri çek
        active_bookings = await db.bookings.find(
            {
                "tenant_id": tenant_id,
                "status": {"$in": ACTIVE_STATUSES},
                "check_in": {"$lt": end_str},
                "check_out": {"$gt": today_str},
            },
            {"_id": 0, "room_id": 1, "check_in": 1, "check_out": 1},
        ).to_list(10000)

        # Her room type için tarih bazlı müsaitlik hesapla
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

        # Kanallara push et
        push_tasks = []
        push_tasks.append(
            _push_reconciliation_exely(tenant_id, availability_by_type)
        )
        push_tasks.append(
            _push_reconciliation_hr(tenant_id, availability_by_type)
        )
        results = await asyncio.gather(*push_tasks, return_exceptions=True)

        total_pushed = sum(r for r in results if isinstance(r, int))
        if total_pushed > 0:
            logger.info(
                "[AVAIL-RECON] Tenant %s: %d push tamamlandı",
                tenant_id[:8], total_pushed,
            )


async def _push_reconciliation_exely(
    tenant_id: str,
    availability_by_type: dict[str, dict[str, int]],
) -> int:
    """Exely'ye uzlaştırma push'ı."""
    push_count = 0
    try:
        conn = await db.exely_connections.find_one(
            {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
        )
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
        }
        if conn.get("endpoint_url"):
            provider_kwargs["endpoint_url"] = conn["endpoint_url"]

        provider = ExelyProvider(**provider_kwargs)

        rate_plans = conn.get("rate_plans", [])
        if not rate_plans:
            return 0

        # PMS room type → Exely room code mapping
        all_mappings = await db.exely_room_mappings.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(100)

        # Dedup by (pms_room_type, exely_room_code)
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

            # Tarihleri ardışık gruplara ayır
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
        logger.error("[AVAIL-RECON] Exely recon hatası: %s", e)

    return push_count


async def _push_reconciliation_hr(
    tenant_id: str,
    availability_by_type: dict[str, dict[str, int]],
) -> int:
    """HotelRunner'a uzlaştırma push'ı."""
    push_count = 0
    try:
        conn = await db.hotelrunner_connections.find_one(
            {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
        )
        if not conn:
            return 0

        # HR mappings
        all_mappings = await db.hotelrunner_room_mappings.find(
            {"tenant_id": tenant_id}, {"_id": 0}
        ).to_list(100)

        # Dedup by (pms_room_type, hr_inv_code)
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
            from domains.channel_manager.providers.hotelrunner_router import _get_provider
            provider, _ = await _get_provider(tenant_id)
        except Exception as e:
            logger.warning("[AVAIL-RECON] HR provider alınamadı: %s", e)
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
        logger.error("[AVAIL-RECON] HR recon hatası: %s", e)

    return push_count


# Singleton instance
availability_reconciliation_worker = AvailabilityReconciliationWorker()
