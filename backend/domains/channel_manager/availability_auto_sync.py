"""
Availability Auto-Sync Service
==============================
Manuel rezervasyon oluşturulduğunda / güncellendiğinde / iptal edildiğinde
gerçek müsaitliği (toplam oda - aktif rezervasyon) hesaplayıp
Exely ve HotelRunner kanallarına otomatik push eder.

Akış:
  booking event → room_type tespit → tarih aralığı belirleme →
  her gün için aktif booking sayısı hesaplama → gerçek availability →
  Exely push (SOAP) + HotelRunner push (REST) arka planda
"""
import asyncio
import logging
from datetime import datetime, timedelta

from core.database import db
from core.tenant_db import clear_tenant_context, set_tenant_context

logger = logging.getLogger("channel_manager.availability_auto_sync")

ACTIVE_STATUSES = ["pending", "confirmed", "guaranteed", "checked_in"]


async def sync_availability_after_booking(
    tenant_id: str,
    room_id: str,
    check_in: str,
    check_out: str,
):
    """
    Bir booking olayından sonra etkilenen tarihler için
    gerçek müsaitliği hesapla ve kanallara push et.
    Arka planda çalışır, hata fırlatmaz.
    """
    try:
        # Booking'in DB'ye tamamen commit olmasını garantile
        await asyncio.sleep(1)
        set_tenant_context(tenant_id)
        await _do_sync(tenant_id, room_id, check_in, check_out)
    except Exception as e:
        logger.error(
            "[AVAIL-AUTO-SYNC] Hata tenant=%s room=%s: %s",
            tenant_id, room_id, e,
        )
    finally:
        clear_tenant_context()


async def _do_sync(tenant_id: str, room_id: str, check_in: str, check_out: str):
    """Core sync logic."""
    # 1. Odanın room_type'ını bul
    room = await db.rooms.find_one(
        {"id": room_id, "tenant_id": tenant_id},
        {"_id": 0, "room_type": 1},
    )
    if not room:
        logger.warning("[AVAIL-AUTO-SYNC] Oda bulunamadı: %s", room_id)
        return
    pms_room_type = room.get("room_type", "")
    if not pms_room_type:
        logger.warning("[AVAIL-AUTO-SYNC] Oda tipi boş: %s", room_id)
        return

    # 2. Bu oda tipindeki toplam oda sayısını ve oda ID'lerini bul
    rooms_of_type = await db.rooms.find(
        {"tenant_id": tenant_id, "room_type": pms_room_type},
        {"_id": 0, "id": 1},
    ).to_list(500)
    total_rooms = len(rooms_of_type)
    room_ids = {r["id"] for r in rooms_of_type}

    if total_rooms == 0:
        return

    # 3. Tarih aralığını belirle
    ci_str = check_in[:10]
    co_str = check_out[:10]
    start_date = datetime.strptime(ci_str, "%Y-%m-%d").date()
    end_date = datetime.strptime(co_str, "%Y-%m-%d").date()

    # check_out günü dahil değil (checkout günü oda boş)
    if end_date <= start_date:
        return

    # 4. Bu tarih aralığında aktif booking'leri çek
    active_bookings = await db.bookings.find(
        {
            "tenant_id": tenant_id,
            "status": {"$in": ACTIVE_STATUSES},
            "check_in": {"$lt": co_str},
            "check_out": {"$gt": ci_str},
        },
        {"_id": 0, "room_id": 1, "check_in": 1, "check_out": 1},
    ).to_list(10000)

    # 5. Her gün için sold count hesapla
    date_availability = {}
    d = start_date
    while d < end_date:
        ds = d.strftime("%Y-%m-%d")
        sold = 0
        for b in active_bookings:
            if b.get("room_id") not in room_ids:
                continue
            b_ci = (b.get("check_in") or "")[:10]
            b_co = (b.get("check_out") or "")[:10]
            if b_ci <= ds < b_co:
                sold += 1
        real_avail = max(total_rooms - sold, 0)
        date_availability[ds] = real_avail
        d += timedelta(days=1)

    if not date_availability:
        return

    logger.info(
        "[AVAIL-AUTO-SYNC] tenant=%s room_type=%s tarih=%s→%s avail=%s",
        tenant_id, pms_room_type, ci_str, co_str,
        dict(list(date_availability.items())[:5]),
    )

    # 6. Kanallara push et (arka planda paralel)
    tasks = []
    tasks.append(_push_to_exely(tenant_id, pms_room_type, date_availability))
    tasks.append(_push_to_hotelrunner(tenant_id, pms_room_type, date_availability))
    await asyncio.gather(*tasks, return_exceptions=True)


async def _push_to_exely(
    tenant_id: str,
    pms_room_type: str,
    date_availability: dict[str, int],
):
    """Exely'ye müsaitlik push et."""
    try:
        # Exely bağlantısını bul
        conn = await db.exely_connections.find_one(
            {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
        )
        if not conn:
            logger.debug("[AVAIL-AUTO-SYNC] Exely bağlantısı yok tenant=%s", tenant_id)
            return

        # PMS room type → Exely room code mapping
        mappings = await db.exely_room_mappings.find(
            {"tenant_id": tenant_id, "pms_room_type": pms_room_type},
            {"_id": 0},
        ).to_list(10)
        if not mappings:
            logger.debug("[AVAIL-AUTO-SYNC] Exely mapping yok pms_type=%s", pms_room_type)
            return

        # Credential'ları al ve provider oluştur
        from domains.channel_manager.credential_vault import get_decrypted_credentials

        hotel_code = conn.get("hotel_code", "")
        creds = await get_decrypted_credentials(tenant_id, "exely", hotel_code)
        if not creds:
            logger.warning("[AVAIL-AUTO-SYNC] Exely credential bulunamadı tenant=%s", tenant_id)
            return

        from domains.channel_manager.providers.exely.provider import ExelyProvider

        provider_kwargs = {
            "username": creds.get("username", ""),
            "password": creds.get("password", ""),
            "hotel_code": hotel_code,
        }
        if conn.get("endpoint_url"):
            provider_kwargs["endpoint_url"] = conn["endpoint_url"]

        provider = ExelyProvider(**provider_kwargs)

        # Rate plan'ları al
        rate_plans = conn.get("rate_plans", [])
        if not rate_plans:
            logger.debug("[AVAIL-AUTO-SYNC] Exely rate_plans boş")
            return

        # Tarihleri ardışık gruplara ayır
        sorted_dates = sorted(date_availability.keys())
        date_groups = _group_consecutive_dates_with_same_avail(sorted_dates, date_availability)

        # Duplicate exely_room_code'ları filtrele
        seen_room_codes = set()
        unique_mappings = []
        for mapping in mappings:
            rc = mapping.get("exely_room_code", "")
            if rc and rc not in seen_room_codes:
                seen_room_codes.add(rc)
                unique_mappings.append(mapping)

        # Her mapping ve rate plan için push et
        push_count = 0
        for mapping in unique_mappings:
            exely_room_code = mapping.get("exely_room_code", "")
            if not exely_room_code:
                continue

            for rp in rate_plans:
                rp_code = rp.get("code", "")
                if not rp_code:
                    continue

                for group_start, group_end, avail in date_groups:
                    try:
                        result = await provider.push_ari(
                            room_type_code=exely_room_code,
                            rate_plan_code=rp_code,
                            start_date=group_start,
                            end_date=group_end,
                            availability=avail,
                        )
                        if result.success:
                            push_count += 1
                            logger.info(
                                "[AVAIL-AUTO-SYNC] Exely push OK: room=%s rp=%s %s→%s avail=%d",
                                exely_room_code, rp_code, group_start, group_end, avail,
                            )
                        else:
                            logger.warning(
                                "[AVAIL-AUTO-SYNC] Exely push FAIL: room=%s rp=%s err=%s",
                                exely_room_code, rp_code, result.error,
                            )
                    except Exception as e:
                        logger.error("[AVAIL-AUTO-SYNC] Exely push error: %s", e)

        logger.info("[AVAIL-AUTO-SYNC] Exely toplam %d push tamamlandı", push_count)

    except Exception as e:
        logger.error("[AVAIL-AUTO-SYNC] Exely sync hatası: %s", e)


async def _push_to_hotelrunner(
    tenant_id: str,
    pms_room_type: str,
    date_availability: dict[str, int],
):
    """HotelRunner'a müsaitlik push et."""
    try:
        conn = await db.hotelrunner_connections.find_one(
            {"tenant_id": tenant_id, "is_active": True}, {"_id": 0}
        )
        if not conn:
            logger.debug("[AVAIL-AUTO-SYNC] HR bağlantısı yok tenant=%s", tenant_id)
            return

        # PMS room type → HR inv_code mapping
        mappings = await db.hotelrunner_room_mappings.find(
            {"tenant_id": tenant_id, "pms_room_type": pms_room_type},
            {"_id": 0},
        ).to_list(10)
        if not mappings:
            logger.debug("[AVAIL-AUTO-SYNC] HR mapping yok pms_type=%s", pms_room_type)
            return

        # HR provider'ı al
        try:
            from domains.channel_manager.providers.hotelrunner_router import _get_provider
            provider, _ = await _get_provider(tenant_id)
        except Exception as e:
            logger.warning("[AVAIL-AUTO-SYNC] HR provider alınamadı: %s", e)
            return

        # Tarihleri ardışık gruplara ayır
        sorted_dates = sorted(date_availability.keys())
        date_groups = _group_consecutive_dates_with_same_avail(sorted_dates, date_availability)

        # Duplicate hr_inv_code'ları filtrele
        seen_inv_codes = set()
        unique_mappings = []
        for mapping in mappings:
            ic = mapping.get("hr_inv_code", "")
            if ic and ic not in seen_inv_codes:
                seen_inv_codes.add(ic)
                unique_mappings.append(mapping)

        push_count = 0
        for mapping in unique_mappings:
            hr_inv_code = mapping.get("hr_inv_code", "")
            if not hr_inv_code:
                continue

            for group_start, group_end, avail in date_groups:
                try:
                    update_data = {
                        "inv_code": hr_inv_code,
                        "start_date": group_start,
                        "end_date": group_end,
                        "availability": int(avail),
                    }
                    result = await provider.update_room(**update_data)
                    if result.get("success"):
                        push_count += 1
                        logger.info(
                            "[AVAIL-AUTO-SYNC] HR push OK: inv=%s %s→%s avail=%d",
                            hr_inv_code, group_start, group_end, avail,
                        )
                    else:
                        logger.warning(
                            "[AVAIL-AUTO-SYNC] HR push FAIL: inv=%s err=%s",
                            hr_inv_code, result.get("error"),
                        )
                except Exception as e:
                    logger.error("[AVAIL-AUTO-SYNC] HR push error: %s", e)

        logger.info("[AVAIL-AUTO-SYNC] HR toplam %d push tamamlandı", push_count)

    except Exception as e:
        logger.error("[AVAIL-AUTO-SYNC] HR sync hatası: %s", e)


def _group_consecutive_dates_with_same_avail(
    sorted_dates: list[str],
    date_availability: dict[str, int],
) -> list[tuple[str, str, int]]:
    """
    Ardışık günleri ve aynı availability değerini grupla.
    Dönüş: [(start_date, end_date, availability), ...]
    """
    if not sorted_dates:
        return []

    groups = []
    group_start = sorted_dates[0]
    prev_date = datetime.strptime(sorted_dates[0], "%Y-%m-%d").date()
    prev_avail = date_availability[sorted_dates[0]]

    for ds in sorted_dates[1:]:
        curr_date = datetime.strptime(ds, "%Y-%m-%d").date()
        curr_avail = date_availability[ds]

        if (curr_date - prev_date).days == 1 and curr_avail == prev_avail:
            prev_date = curr_date
        else:
            groups.append((group_start, prev_date.strftime("%Y-%m-%d"), prev_avail))
            group_start = ds
            prev_date = curr_date
            prev_avail = curr_avail

    groups.append((group_start, prev_date.strftime("%Y-%m-%d"), prev_avail))
    return groups
