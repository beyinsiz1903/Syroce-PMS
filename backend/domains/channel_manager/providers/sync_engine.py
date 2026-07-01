"""
HotelRunner Sync Engine — Core sync phases and reservation update logic.

Phase A   — Undelivered reservations
Phase A.5 — Modified reservations (from_last_update_date)
Phase A.6 — PMS booking diff + update
Phase B   — Full catch-up reconciliation
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from core.database import db
from domains.channel_manager.providers.hotelrunner_shared import (
    _persist_and_process,
    _resolve_property_id,
    _timeline_append,
    explode_multi_room_reservation,
)

logger = logging.getLogger(__name__)


async def run_phase_a(
    tenant_id: str,
    provider,
    safety_window_minutes: int,
    is_manual: bool = False,
) -> dict[str, Any]:
    all_reservations = []
    page = 1
    total_pages = 1

    while page <= total_pages:
        result = await provider.get_reservations(
            undelivered=True,
            per_page=50,
            page=page,
        )
        if not result["success"]:
            error_msg = result.get("error", "")
            logger.error(f"[PULL] Failed for tenant {tenant_id} page {page}: {error_msg}")
            is_rate_limited = "429" in str(error_msg) or "rate limit" in str(error_msg).lower()
            if page == 1:
                await log_pull(tenant_id, "failed", 0, error_msg)
                return {"success": False, "error": error_msg, "rate_limited": is_rate_limited}
            break

        page_reservations = result["data"].get("reservations", [])
        all_reservations.extend(page_reservations)
        total_pages = result["data"].get("pages", 1)
        page += 1

    processed = 0
    fire_uids = []

    for res in all_reservations:
        try:
            hr_state_phase_a = res.get("state", "unknown")
            hr_number_phase_a = res.get("hr_number", "?")
            logger.info(f"[PULL-PHASE-A] Processing {hr_number_phase_a}: state={hr_state_phase_a}")

            sub_reservations = explode_multi_room_reservation(res)
            rooms_count = len(res.get("rooms", []) or [])
            if rooms_count > 1:
                logger.info(f"[PULL] Multi-room reservation {res.get('hr_number')}: {rooms_count} rooms -> {len(sub_reservations)} sub-reservations")

            for sub_res in sub_reservations:
                try:
                    sub_state_a = (sub_res.get("state") or "").lower()
                    is_cancel_a = sub_state_a in ("cancelled", "canceled") or sub_res.get("_room_cancelled") or bool(sub_res.get("cancel_reason"))
                    evt_type_a = "reservation_cancel_pull" if is_cancel_a else "reservation_pull"
                    await _persist_and_process(
                        tenant_id,
                        _resolve_property_id(sub_res),
                        sub_res,
                        evt_type_a,
                    )
                    processed += 1
                    if is_cancel_a:
                        logger.info(f"[PULL-A] Cancellation in undelivered: {sub_res.get('hr_number')}")
                except Exception as e:
                    logger.error(f"[PULL] Error processing sub-reservation {sub_res.get('hr_number')}: {e}")

            msg_uid = res.get("message_uid") or res.get("ruid") or res.get("uid")
            if msg_uid:
                fire_uids.append(msg_uid)
        except Exception as e:
            logger.error(f"[PULL] Error processing reservation: {e}")

    fired = 0
    for uid in fire_uids:
        try:
            fire_result = await provider.confirm_delivery(message_uid=uid)
            if fire_result.success:
                fired += 1
                logger.info(f"[PULL] Fired reservation uid={uid}")
            else:
                logger.warning(f"[PULL] Fire failed for uid={uid}: {fire_result.error}")
        except Exception as e:
            logger.error(f"[PULL] Fire error for uid={uid}: {e}")

    return {
        "success": True,
        "all_reservations": all_reservations,
        "processed": processed,
        "fired": fired,
        "pages": total_pages,
    }


async def run_phase_a5(
    tenant_id: str,
    provider,
    safety_window_minutes: int,
) -> int:
    mod_processed = 0
    try:
        cursor_doc = await db.hotelrunner_pull_cursors.find_one(
            {"tenant_id": tenant_id},
            {"_id": 0, "last_pull_at": 1},
        )
        if cursor_doc and cursor_doc.get("last_pull_at"):
            last_pull_dt = datetime.fromisoformat(cursor_doc["last_pull_at"])
            mod_since = (last_pull_dt - timedelta(minutes=safety_window_minutes)).strftime("%Y-%m-%d")

            mod_page = 1
            mod_total_pages = 1
            all_mod_reservations = []
            while mod_page <= mod_total_pages:
                mod_result = await provider.get_reservations(
                    undelivered=False,
                    from_last_update_date=mod_since,
                    per_page=50,
                    page=mod_page,
                )
                if not mod_result["success"]:
                    break
                page_mods = mod_result["data"].get("reservations", [])
                all_mod_reservations.extend(page_mods)
                mod_total_pages = mod_result["data"].get("pages", 1)
                mod_page += 1

            if all_mod_reservations:
                logger.info(f"[PULL-A5] Found {len(all_mod_reservations)} recently modified reservations (pages: {mod_total_pages})")
                for mod_res in all_mod_reservations:
                    try:
                        sub_reservations = explode_multi_room_reservation(mod_res)
                        for sub_res in sub_reservations:
                            try:
                                sub_state = (sub_res.get("state") or "").lower()
                                is_cancelled = sub_state in ("cancelled", "canceled") or sub_res.get("_room_cancelled") or bool(sub_res.get("cancel_reason"))
                                evt_type = "reservation_cancel_pull" if is_cancelled else "reservation_modified_pull"
                                await _persist_and_process(
                                    tenant_id,
                                    _resolve_property_id(sub_res),
                                    sub_res,
                                    evt_type,
                                )
                                mod_processed += 1
                                if is_cancelled:
                                    logger.info(f"[PULL-A5] Cancellation detected: {sub_res.get('hr_number')}")
                            except Exception as e:
                                if "duplicate" not in str(e).lower():
                                    logger.error(f"[PULL-A5] Error processing modified {sub_res.get('hr_number')}: {e}")
                    except Exception as e:
                        logger.error(f"[PULL-A5] Error: {e}")
    except Exception as e:
        logger.warning(f"[PULL-A5] Modified reservation check error: {e}")

    return mod_processed


async def run_phase_a6(tenant_id: str) -> int:
    cutoff = (datetime.now(UTC) - timedelta(minutes=2)).isoformat()

    recent_events = await db.raw_channel_events.find(
        {
            "tenant_id": tenant_id,
            "provider": "hotelrunner",
            "event_type": {"$in": ["reservation_modified_pull", "reservation_cancel_pull"]},
            "received_at": {"$gte": cutoff},
        },
        {"_id": 0, "external_reservation_id": 1, "raw_payload": 1, "event_type": 1},
    ).to_list(50)

    if not recent_events:
        return 0

    updated = 0
    for event in recent_events:
        ext_id = event.get("external_reservation_id", "")
        payload = event.get("raw_payload", {})
        if not ext_id or not payload:
            continue

        hr_updated_at = payload.get("updated_at", "")
        hr_state = payload.get("state", "confirmed")

        try:
            was_updated = await sync_reservation_update(
                tenant_id,
                ext_id,
                payload,
                hr_state,
                hr_updated_at,
            )
            if was_updated:
                updated += 1
        except Exception as e:
            if "not found" not in str(e).lower():
                logger.warning(f"[PULL-A6] Sync error for {ext_id}: {e}")

    return updated


async def run_phase_b(tenant_id: str, provider) -> tuple[int, int]:
    catchup_imported = 0
    catchup_updated = 0

    all_page = 1
    all_total_pages = 1
    known_ext_ids = set()
    known_ext_updated = {}
    known_ext_status = {}

    async for doc in db.imported_reservations.find(
        {"tenant_id": tenant_id, "provider": "hotelrunner"},
        {"_id": 0, "external_reservation_id": 1, "provider_updated_at": 1, "created_at": 1},
    ):
        ext_id = doc.get("external_reservation_id", "")
        known_ext_ids.add(ext_id)
        known_ext_updated[ext_id] = doc.get("provider_updated_at") or doc.get("created_at", "")

    async for bdoc in db.bookings.find(
        {"tenant_id": tenant_id, "external_reservation_id": {"$exists": True, "$ne": ""}},
        {"_id": 0, "external_reservation_id": 1, "status": 1},
    ):
        known_ext_status[bdoc.get("external_reservation_id", "")] = bdoc.get("status", "confirmed")

    while all_page <= all_total_pages:
        result = await provider.get_reservations(
            undelivered=False,
            per_page=50,
            page=all_page,
        )
        if not result["success"]:
            break

        page_reservations = result["data"].get("reservations", [])
        all_total_pages = result["data"].get("pages", 1)

        for res in page_reservations:
            hr_number = res.get("hr_number", "")
            hr_updated_at = res.get("updated_at", "")
            hr_state = res.get("state", "confirmed")
            hr_next_states = res.get("next_states") or []
            hr_cancel_reason = res.get("cancel_reason") or ""

            effective_state = hr_state
            if hr_state in ("cancelled", "canceled") or hr_cancel_reason:
                effective_state = "canceled"

            logger.info(f"[PULL-PHASE-B] {hr_number}: state={hr_state}, effective={effective_state}, next_states={hr_next_states}, cancel_reason={hr_cancel_reason}, updated_at={hr_updated_at}")

            sub_reservations = explode_multi_room_reservation(res)

            newly_room_cancelled = set()
            for _sr in sub_reservations:
                _sr_ext = _sr.get("hr_number", "")
                if _sr.get("_room_cancelled") and known_ext_status.get(_sr_ext, "confirmed") != "cancelled":
                    newly_room_cancelled.add(_sr_ext)
            has_new_room_cancels = len(newly_room_cancelled) > 0

            for sub_res in sub_reservations:
                sub_ext = sub_res.get("hr_number", "")
                sub_room_cancelled = sub_res.get("_room_cancelled", False)
                is_exploded = bool(sub_res.get("_exploded_from"))

                if sub_ext not in known_ext_ids:
                    if sub_room_cancelled:
                        sub_res["state"] = "cancelled"
                    elif not is_exploded and effective_state == "canceled":
                        sub_res["state"] = "cancelled"
                        sub_res["_room_cancelled"] = True

                    try:
                        catchup_evt = "reservation_cancel_catchup" if sub_room_cancelled or effective_state == "canceled" else "reservation_catchup"
                        await _persist_and_process(
                            tenant_id,
                            _resolve_property_id(sub_res),
                            sub_res,
                            catchup_evt,
                        )
                        catchup_imported += 1
                    except Exception as e:
                        if "duplicate" not in str(e).lower():
                            logger.error(f"[PULL-CATCHUP] Error importing {sub_ext}: {e}")
                else:
                    stored_updated = known_ext_updated.get(sub_ext, "")
                    stored_status = known_ext_status.get(sub_ext, "confirmed")
                    timestamp_changed = hr_updated_at and hr_updated_at > stored_updated

                    if sub_room_cancelled:
                        sub_effective_state = "canceled"
                    elif is_exploded and effective_state == "canceled":
                        if has_new_room_cancels:
                            sub_effective_state = "confirmed"
                        else:
                            sub_effective_state = stored_status
                    else:
                        sub_effective_state = effective_state

                    logger.info(
                        f"[PULL-PHASE-B] {sub_ext}: sub_effective={sub_effective_state}, "
                        f"room_cancelled={sub_room_cancelled}, top_effective={effective_state}, "
                        f"ts_changed={timestamp_changed}, new_partial={has_new_room_cancels}"
                    )

                    hr_status_check = {"canceled": "cancelled", "cancelled": "cancelled", "no_show": "no_show"}.get(sub_effective_state, sub_effective_state)
                    state_changed = hr_status_check != stored_status

                    if stored_status == "cancelled" and hr_status_check != "cancelled":
                        state_changed = False

                    if state_changed or timestamp_changed:
                        try:
                            updated = await sync_reservation_update(
                                tenant_id,
                                sub_ext,
                                sub_res,
                                sub_effective_state,
                                hr_updated_at,
                            )
                            if updated:
                                catchup_updated += 1
                                logger.info(f"[PULL-SYNC] {sub_ext}: state_changed={state_changed} (hr={hr_status_check}, stored={stored_status}), ts_changed={timestamp_changed}")
                        except Exception as e:
                            logger.error(f"[PULL-SYNC] Error updating {sub_ext}: {e}")

        all_page += 1

    if catchup_imported > 0:
        logger.info(f"[PULL-CATCHUP] Tenant {tenant_id}: {catchup_imported} missing reservations imported")
    if catchup_updated > 0:
        logger.info(f"[PULL-SYNC] Tenant {tenant_id}: {catchup_updated} reservations updated")

    return catchup_imported, catchup_updated


async def sync_reservation_update(
    tenant_id: str,
    ext_reservation_id: str,
    hr_payload: dict[str, Any],
    hr_state: str,
    hr_updated_at: str,
) -> bool:
    booking = await db.bookings.find_one(
        {"tenant_id": tenant_id, "external_reservation_id": ext_reservation_id},
        {"_id": 0},
    )
    if not booking:
        logger.warning(f"[PULL-SYNC] Booking not found for {ext_reservation_id}")
        return False

    existing_sync_ts = booking.get("last_synced_from_provider_at", "")
    if existing_sync_ts and hr_updated_at and hr_updated_at <= existing_sync_ts:
        logger.debug(f"[PULL-SYNC] {ext_reservation_id}: skipping stale update (hr={hr_updated_at} <= existing={existing_sync_ts})")
        return False

    rooms = hr_payload.get("rooms") or []
    room = rooms[0] if rooms else {}

    updates = {}
    guest_name_hr = f"{hr_payload.get('firstname', '')} {hr_payload.get('lastname', '')}".strip()
    if not guest_name_hr:
        guest_name_hr = hr_payload.get("guest", "")

    if guest_name_hr and guest_name_hr != booking.get("guest_name", ""):
        updates["guest_name"] = guest_name_hr
        logger.info(f"[PULL-SYNC] {ext_reservation_id}: guest name '{booking.get('guest_name')}' -> '{guest_name_hr}'")

    checkin = hr_payload.get("checkin_date") or (room.get("checkin_date") if room else "")
    checkout = hr_payload.get("checkout_date") or (room.get("checkout_date") if room else "")
    if checkin and checkin != booking.get("check_in", ""):
        updates["check_in"] = checkin
    if checkout and checkout != booking.get("check_out", ""):
        updates["check_out"] = checkout

    if room:
        hr_room_code = room.get("inv_code") or room.get("code") or ""
        if hr_room_code:
            room_mapping = await db.room_mappings.find_one(
                {
                    "tenant_id": tenant_id,
                    "provider": "hotelrunner",
                    "provider_room_code": hr_room_code,
                    "is_active": True,
                },
                {"_id": 0, "pms_room_type_id": 1, "pms_room_type_name": 1},
            )
            new_room_type = (room_mapping or {}).get("pms_room_type_name") or (room_mapping or {}).get("pms_room_type_id") or hr_room_code
            new_room_type_id = (room_mapping or {}).get("pms_room_type_id") or hr_room_code

            if new_room_type != booking.get("room_type", ""):
                updates["room_type"] = new_room_type
                updates["room_type_id"] = new_room_type_id
                logger.info(f"[PULL-SYNC] {ext_reservation_id}: room type '{booking.get('room_type')}' -> '{new_room_type}'")

    total = float(hr_payload.get("total", 0) or 0)
    if room:
        total = float(room.get("total", room.get("price", 0)) or 0)
    if total > 0 and abs(total - float(booking.get("total_amount", 0))) > 0.01:
        updates["total_amount"] = total

    hr_status_map = {
        "confirmed": "confirmed",
        "modified": "confirmed",
        "canceled": "cancelled",
        "cancelled": "cancelled",
        "no_show": "no_show",
    }
    mapped_status = hr_status_map.get(hr_state, hr_state)
    if mapped_status != booking.get("status", ""):
        updates["status"] = mapped_status
        logger.info(f"[PULL-SYNC] {ext_reservation_id}: status '{booking.get('status')}' -> '{mapped_status}'")
        if mapped_status == "cancelled":
            updates["cancelled_at"] = datetime.now(UTC).isoformat()
            cancel_reason = hr_payload.get("cancel_reason") or "Provider cancellation"
            updates["cancellation_reason"] = cancel_reason
            logger.info(f"[PULL-SYNC] {ext_reservation_id}: cancellation_reason='{cancel_reason}'")

    if not updates:
        return False

    updates["updated_at"] = datetime.now(UTC).isoformat()
    updates["last_synced_from_provider_at"] = hr_updated_at

    await db.bookings.update_one(
        {"tenant_id": tenant_id, "external_reservation_id": ext_reservation_id},
        {"$set": updates},
    )

    imported_update = {
        "provider_updated_at": hr_updated_at,
        "updated_at": datetime.now(UTC).isoformat(),
        "guest_name": guest_name_hr if "guest_name" in updates else booking.get("guest_name", ""),
    }
    if "status" in updates:
        imported_update["status"] = updates["status"]
    await db.imported_reservations.update_one(
        {"tenant_id": tenant_id, "external_reservation_id": ext_reservation_id},
        {"$set": imported_update},
    )

    if "guest_name" in updates and booking.get("guest_id"):
        guest_parts = guest_name_hr.split(" ", 1)
        guest_first = guest_parts[0]
        guest_last = guest_parts[1] if len(guest_parts) > 1 else ""
        await db.guests.update_one(
            {"tenant_id": tenant_id, "id": booking["guest_id"]},
            {
                "$set": {
                    "first_name": guest_first,
                    "last_name": guest_last,
                    "updated_at": datetime.now(UTC).isoformat(),
                }
            },
        )

    await _timeline_append(
        tenant_id=tenant_id,
        correlation_id=str(uuid.uuid4()),
        entity_type="reservation",
        external_id=ext_reservation_id,
        stage="provider_sync_update",
        status="success",
        source="hotelrunner_pull",
        provider="hotelrunner",
        metadata={
            "updated_fields": list(updates.keys()),
            "hr_state": hr_state,
            "hr_updated_at": hr_updated_at,
        },
    )

    logger.info(f"[PULL-SYNC] {ext_reservation_id}: updated fields={list(updates.keys())}")

    try:
        notifications_to_create = []
        if "status" in updates and updates["status"] == "cancelled":
            notifications_to_create.append(
                {
                    "title": f"Rezervasyon Iptali - {guest_name_hr or booking.get('guest_name', '')}",
                    "message": (
                        f"{guest_name_hr or booking.get('guest_name', '')} adli misafirin {booking.get('check_in', '')[:10]} - {booking.get('check_out', '')[:10]} tarihli rezervasyonu iptal edildi."
                    ),
                    "type": "reservation_cancelled",
                    "priority": "high",
                    "category": "reservation",
                    "dedup_key": f"cancel_{ext_reservation_id}",
                }
            )
        if "guest_name" in updates:
            notifications_to_create.append(
                {
                    "title": f"Misafir Adi Degisikligi - {ext_reservation_id}",
                    "message": (f"Misafir adi degistirildi: {booking.get('guest_name', '')} -> {updates['guest_name']}"),
                    "type": "reservation_modified",
                    "priority": "normal",
                    "category": "reservation",
                    "dedup_key": f"name_{ext_reservation_id}_{updates['guest_name']}",
                }
            )
        if "check_in" in updates or "check_out" in updates:
            notifications_to_create.append(
                {
                    "title": f"Tarih Degisikligi - {ext_reservation_id}",
                    "message": (f"Tarih degistirildi: Giris: {updates.get('check_in', booking.get('check_in', ''))[:10]}, Cikis: {updates.get('check_out', booking.get('check_out', ''))[:10]}"),
                    "type": "reservation_modified",
                    "priority": "normal",
                    "category": "reservation",
                    "dedup_key": f"date_{ext_reservation_id}_{updates.get('check_in', '')}_{updates.get('check_out', '')}",
                }
            )

        for notif_data in notifications_to_create:
            dedup_key = notif_data.pop("dedup_key")
            existing = await db.notifications.find_one(
                {
                    "tenant_id": tenant_id,
                    "external_reservation_id": ext_reservation_id,
                    "dedup_key": dedup_key,
                }
            )
            if existing:
                continue
            await db.notifications.insert_one(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "booking_id": booking.get("id", ""),
                    "external_reservation_id": ext_reservation_id,
                    "read": False,
                    "created_at": datetime.now(UTC).isoformat(),
                    "dedup_key": dedup_key,
                    **notif_data,
                }
            )
    except Exception as e:
        logger.error(f"[PULL-SYNC] Notification creation error for {ext_reservation_id}: {e}")

    return True


async def log_pull(tenant_id: str, status: str, records: int, error: str | None = None, duration_ms: int = 0):
    await db.hotelrunner_sync_logs.insert_one(
        {
            "id": str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "timestamp": datetime.now(UTC).isoformat(),
            "sync_type": "scheduled_pull",
            "status": status,
            "duration_ms": duration_ms,
            "records_synced": records,
            "error_message": error,
            "initiator": "system",
        }
    )
