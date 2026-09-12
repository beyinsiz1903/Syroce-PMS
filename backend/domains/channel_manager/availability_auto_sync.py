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
from datetime import date, datetime, timedelta

from core.database import db
from core.room_type_inventory_service import (
    get_room_type_inventory,
    reconcile_date_range,
)
from core.tenant_db import clear_tenant_context, set_tenant_context

logger = logging.getLogger("channel_manager.availability_auto_sync")



async def _load_authoritative_availability(
    tenant_id: str,
    room_type: str,
    start_date: date,
    end_date: date,
) -> dict[str, int]:
    """Read sellable inventory from the canonical room-night-lock projection.

    Channel availability must use the same source as the PMS calendar.  Counting
    bookings here is unsafe: holds, out-of-order rooms and a recently reassigned
    reservation are represented by room-night locks before (and sometimes
    independently of) the booking document.  A raw booking count can therefore
    overwrite a correct channel value with an incorrect one.
    """
    last_stay_date = end_date - timedelta(days=1)
    if last_stay_date < start_date:
        return {}

    await reconcile_date_range(
        tenant_id,
        start_date.isoformat(),
        last_stay_date.isoformat(),
    )

    availability: dict[str, int] = {}
    current_date = start_date
    while current_date < end_date:
        date_string = current_date.isoformat()
        inventory = await get_room_type_inventory(tenant_id, date_string, room_type)
        item = next((row for row in inventory if row.get("room_type") == room_type), None)
        if item is None or not isinstance(item.get("sellable"), int):
            raise RuntimeError(
                "Canonical inventory is unavailable for "
                f"room_type={room_type!r}, date={date_string!r}"
            )
        availability[date_string] = max(item["sellable"], 0)
        current_date += timedelta(days=1)

    return availability


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
            "[AVAIL-AUTO-SYNC] Sync failed: %s",
            type(e).__name__,
        )
    finally:
        clear_tenant_context()


async def sync_availability_from_durable_event(
    tenant_id: str,
    room_id: str,
    check_in: str,
    check_out: str,
) -> dict:
    """Run booking availability sync from the durable outbox worker.

    Unlike the request-scoped helper above, this path does not sleep and does
    not hide delivery results. The dispatcher uses the result to avoid marking
    a configured provider's event as processed when no work was accepted.
    """
    set_tenant_context(tenant_id)
    try:
        result = await _do_sync(tenant_id, room_id, check_in, check_out)
        return result or {"configured_providers": 0, "queued_operations": 0, "errors": []}
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
        logger.warning("[AVAIL-AUTO-SYNC] Room not found")
        return {"configured_providers": 0, "queued_operations": 0, "errors": ["room_not_found"]}
    pms_room_type = room.get("room_type", "")
    if not pms_room_type:
        logger.warning("[AVAIL-AUTO-SYNC] Room type missing")
        return {"configured_providers": 0, "queued_operations": 0, "errors": ["room_type_missing"]}

    # 2. Tarih aralığını belirle
    ci_str = check_in[:10]
    co_str = check_out[:10]
    start_date = datetime.strptime(ci_str, "%Y-%m-%d").date()
    end_date = datetime.strptime(co_str, "%Y-%m-%d").date()

    # check_out günü dahil değil (checkout günü oda boş)
    if end_date <= start_date:
        return {"configured_providers": 0, "queued_operations": 0, "errors": ["invalid_date_range"]}

    # 3. Calendar and every OTA push must read exactly the same, canonical
    # room-night-lock inventory.  Do not fall back to a booking count here:
    # a fallback can reopen a room that the calendar has correctly closed.
    date_availability = await _load_authoritative_availability(
        tenant_id,
        pms_room_type,
        start_date,
        end_date,
    )

    if not date_availability:
        return {"configured_providers": 0, "queued_operations": 0, "errors": ["empty_inventory_range"]}

    logger.info(
        "[AVAIL-AUTO-SYNC] Availability calculated: date_count=%d",
        len(date_availability),
    )

    # 4. Kanallara push et (arka planda paralel)
    results = await asyncio.gather(
        _push_to_exely(tenant_id, pms_room_type, date_availability),
        _push_to_hotelrunner(tenant_id, pms_room_type, date_availability),
        return_exceptions=True,
    )
    summary = {"configured_providers": 0, "queued_operations": 0, "errors": []}
    for result in results:
        if isinstance(result, Exception):
            summary["errors"].append(type(result).__name__)
            continue
        if not isinstance(result, dict):
            continue
        summary["configured_providers"] += int(bool(result.get("configured")))
        summary["queued_operations"] += int(result.get("queued_operations", 0))
        summary["errors"].extend(result.get("errors", []))
    return summary


async def _push_to_exely(
    tenant_id: str,
    pms_room_type: str,
    date_availability: dict[str, int],
):
    """Exely'ye müsaitlik push et."""
    try:
        # Exely bağlantısını bul
        conn = await db.exely_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0})
        if not conn:
            logger.debug("[AVAIL-AUTO-SYNC] No Exely connection for tenant=%s", tenant_id)
            return {"configured": False, "queued_operations": 0, "errors": []}

        # PMS room type → Exely room code mapping
        mappings = await db.exely_room_mappings.find(
            {
                "tenant_id": tenant_id,
                "pms_room_type": pms_room_type,
                "sync_availability": {"$ne": False},
            },
            {"_id": 0},
        ).to_list(10)
        if not mappings:
            logger.debug("[AVAIL-AUTO-SYNC] No Exely mapping for pms_type=%s", pms_room_type)
            return {"configured": True, "queued_operations": 0, "errors": ["exely_room_mapping_missing"]}

        hotel_code = conn.get("hotel_code", "")
        if not hotel_code:
            logger.warning("[AVAIL-AUTO-SYNC] Exely property mapping missing")
            return {"configured": True, "queued_operations": 0, "errors": ["exely_property_mapping_missing"]}
        from domains.channel_manager.providers.exely.ari_publish import enqueue_exely_ari_update

        # Tarihleri ardışık gruplara ayır
        sorted_dates = sorted(date_availability.keys())
        date_groups = _group_consecutive_dates_with_same_avail(sorted_dates, date_availability)

        # Inventory is room-type-wide. Sending the same inventory via multiple
        # rate plans can duplicate a booking decrement (and violates Exely's
        # certification request for one availability mapping per room type).
        seen_pairs = set()
        unique_mappings = []
        for mapping in mappings:
            rc = mapping.get("exely_room_code", "")
            rp_code = mapping.get("exely_rate_plan_code", "")
            pair = (rc, rp_code)
            if rc and rp_code and pair not in seen_pairs:
                seen_pairs.add(pair)
                unique_mappings.append(mapping)
        if len(unique_mappings) > 1:
            logger.error("[AVAIL-AUTO-SYNC] Exely multiple availability mappings for room_type=%s", pms_room_type)
            return {"configured": True, "queued_operations": 0, "errors": ["exely_multiple_availability_mappings"]}

        # Her mapping ve rate plan için push et
        push_count = 0
        errors = []
        for mapping in unique_mappings:
            exely_room_code = mapping.get("exely_room_code", "")
            rp_code = mapping.get("exely_rate_plan_code", "")
            if not exely_room_code or not rp_code:
                continue

            for group_start, group_end, avail in date_groups:
                try:
                    result = await enqueue_exely_ari_update(
                        tenant_id,
                        hotel_code,
                        room_type_code=exely_room_code,
                        rate_plan_code=rp_code,
                        start_date=group_start,
                        end_date=group_end,
                        source_service="availability_auto_sync",
                        availability=avail,
                    )
                    if result["accepted"]:
                        push_count += 1
                        logger.info(
                            "[AVAIL-AUTO-SYNC] Exely delivery_state=queued operation=availability",
                        )
                    else:
                        errors.append(str(result.get("error_code") or "exely_write_blocked"))
                        logger.warning(
                            "[AVAIL-AUTO-SYNC] Exely delivery_state=blocked operation=availability",
                        )
                except Exception as e:
                    errors.append(type(e).__name__)
                    logger.error("[AVAIL-AUTO-SYNC] Exely queue failed: %s", type(e).__name__)

        logger.info("[AVAIL-AUTO-SYNC] Exely queued operations=%d", push_count)
        return {"configured": True, "queued_operations": push_count, "errors": errors}

    except Exception as e:
        logger.error("[AVAIL-AUTO-SYNC] Exely sync error: %s", e)
        return {"configured": True, "queued_operations": 0, "errors": [type(e).__name__]}


async def _push_to_hotelrunner(
    tenant_id: str,
    pms_room_type: str,
    date_availability: dict[str, int],
):
    """HotelRunner'a müsaitlik push et."""
    try:
        conn = await db.hotelrunner_connections.find_one({"tenant_id": tenant_id, "is_active": True}, {"_id": 0})
        if not conn:
            logger.debug("[AVAIL-AUTO-SYNC] No active HR connection")
            return {"configured": False, "queued_operations": 0, "errors": []}

        # PMS room type → HR inv_code mapping
        mappings = await db.hotelrunner_room_mappings.find(
            {"tenant_id": tenant_id, "pms_room_type": pms_room_type},
            {"_id": 0},
        ).to_list(10)
        if not mappings:
            logger.debug("[AVAIL-AUTO-SYNC] No HR room mapping")
            return {"configured": True, "queued_operations": 0, "errors": ["hotelrunner_room_mapping_missing"]}

        from domains.channel_manager.providers.hotelrunner.ari_delivery import (
            deliver_hotelrunner_ari,
        )

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
        errors = []
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
                    delivery = await deliver_hotelrunner_ari(tenant_id, update_data)
                    if delivery.success:
                        push_count += 1
                        logger.info("[AVAIL-AUTO-SYNC] HR transaction confirmed")
                    else:
                        logger.warning(
                            "[AVAIL-AUTO-SYNC] HR transaction not confirmed: %s",
                            delivery.provider_status_class,
                        )
                        errors.append(delivery.provider_status_class or "hotelrunner_delivery_failed")
                        return {"configured": True, "queued_operations": push_count, "errors": errors}
                except Exception as e:
                    logger.error("[AVAIL-AUTO-SYNC] HR delivery error: %s", type(e).__name__)
                    errors.append(type(e).__name__)
                    return {"configured": True, "queued_operations": push_count, "errors": errors}

        logger.info("[AVAIL-AUTO-SYNC] HR total %d pushes completed", push_count)
        return {"configured": True, "queued_operations": push_count, "errors": errors}

    except Exception as e:
        logger.error("[AVAIL-AUTO-SYNC] HR sync error: %s", type(e).__name__)
        return {"configured": True, "queued_operations": 0, "errors": [type(e).__name__]}


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
