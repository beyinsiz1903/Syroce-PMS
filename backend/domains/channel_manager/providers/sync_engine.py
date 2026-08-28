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

from core.booking_realtime import publish_booking_change
from core.database import db
from domains.channel_manager.ingest.hotelrunner_pricing import (
    hotelrunner_guest_total,
    matches_legacy_before_tax_total,
)
from domains.channel_manager.providers.hotelrunner_shared import (
    _persist_and_process,
    _resolve_property_id,
    _timeline_append,
    explode_multi_room_reservation,
)

logger = logging.getLogger(__name__)

_PMS_DURABLE = "durable"
_PMS_PENDING = "pending"
_PMS_FAILED = "failed"


def _classify_provider_pull_failure(error: Any) -> str:
    """Return a bounded provider failure class without logging response details."""
    message = str(error or "").lower()
    if "429" in message or "rate limit" in message:
        return "RATE_LIMITED"
    if "timeout" in message or "timed out" in message:
        return "TIMEOUT"
    if any(marker in message for marker in ("401", "403", "unauthorized", "forbidden")):
        return "AUTH_REJECTED"
    if any(marker in message for marker in ("http 5", "status 5", "upstream 5")):
        return "UPSTREAM_5XX"
    return "PROVIDER_REJECTED"


async def run_phase_a(
    tenant_id: str,
    provider,
    safety_window_minutes: int,
    is_manual: bool = False,
) -> dict[str, Any]:
    all_reservations = []
    page = 1
    total_pages = 1

    try:
        while page <= total_pages:
            result = await provider.get_reservations(
                undelivered=True,
                per_page=50,
                page=page,
            )
            if not result.get("success"):
                failure_class = _classify_provider_pull_failure(result.get("error"))
                is_rate_limited = failure_class == "RATE_LIMITED"
                # A provider-declared failure is an expected upstream outcome. It
                # must remain visible operationally, but should not create an
                # application-error issue in Sentry. Invalid payloads and raised
                # exceptions below remain ERROR events.
                logger.warning(
                    "[PULL-A] Provider page fetch failed; no delivery ACKs sent: "
                    "failure_class=%s",
                    failure_class,
                )
                await log_pull(tenant_id, "failed", 0, "PROVIDER_PULL_FAILED")
                return {
                    "success": False,
                    "error": "PROVIDER_PULL_FAILED",
                    "rate_limited": is_rate_limited,
                    "fired": 0,
                }

            data = result.get("data")
            if not isinstance(data, dict):
                logger.error("[PULL-A] Provider response parse failed; no delivery ACKs sent")
                await log_pull(tenant_id, "failed", 0, "PROVIDER_RESPONSE_INVALID")
                return {"success": False, "error": "PROVIDER_RESPONSE_INVALID", "fired": 0}

            page_reservations = data.get("reservations", [])
            if not isinstance(page_reservations, list):
                logger.error("[PULL-A] Provider reservation list is invalid; no delivery ACKs sent")
                await log_pull(tenant_id, "failed", 0, "PROVIDER_RESPONSE_INVALID")
                return {"success": False, "error": "PROVIDER_RESPONSE_INVALID", "fired": 0}
            all_reservations.extend(page_reservations)
            total_pages = data.get("pages", 1)
            if not isinstance(total_pages, int) or total_pages < 1:
                logger.error("[PULL-A] Provider pagination is invalid; no delivery ACKs sent")
                await log_pull(tenant_id, "failed", 0, "PROVIDER_RESPONSE_INVALID")
                return {"success": False, "error": "PROVIDER_RESPONSE_INVALID", "fired": 0}
            page += 1
    except Exception as exc:
        logger.error(
            "[PULL-A] Provider page fetch raised %s; no delivery ACKs sent",
            type(exc).__name__,
        )
        await log_pull(tenant_id, "failed", 0, "PROVIDER_PULL_EXCEPTION")
        return {"success": False, "error": "PROVIDER_PULL_EXCEPTION", "fired": 0}

    processed = 0
    pending = 0
    failed = 0
    fire_items: list[tuple[str, str]] = []
    seen_uids: set[str] = set()

    for res in all_reservations:
        try:
            sub_reservations = explode_multi_room_reservation(res)
            reservation_durable = bool(sub_reservations)
            reservation_pms_number: str | None = None
            for sub_res in sub_reservations:
                try:
                    sub_state_a = (sub_res.get("state") or "").lower()
                    is_cancel_a = sub_state_a in ("cancelled", "canceled") or sub_res.get("_room_cancelled") or bool(sub_res.get("cancel_reason"))
                    evt_type_a = "reservation_cancel_pull" if is_cancel_a else "reservation_pull"
                    pipeline_result = await _persist_and_process(
                        tenant_id,
                        _resolve_property_id(sub_res),
                        sub_res,
                        evt_type_a,
                    )
                    durability = await _ensure_durable_pms_result(
                        tenant_id,
                        sub_res,
                        pipeline_result,
                        is_cancellation=bool(is_cancel_a),
                    )
                    if durability == _PMS_DURABLE:
                        pms_number = await _read_durable_pms_number(
                            tenant_id,
                            sub_res,
                        )
                        if not pms_number:
                            failed += 1
                            reservation_durable = False
                            logger.error("[PULL-A] Durable reservation has no PMS booking number; delivery ACK withheld")
                        else:
                            processed += 1
                            reservation_pms_number = reservation_pms_number or pms_number
                    elif durability == _PMS_PENDING:
                        pending += 1
                        reservation_durable = False
                    else:
                        failed += 1
                        reservation_durable = False
                except Exception as exc:
                    failed += 1
                    reservation_durable = False
                    logger.error(
                        "[PULL-A] PMS processing raised %s; delivery ACK withheld",
                        type(exc).__name__,
                    )

            msg_uid = res.get("message_uid") or res.get("ruid") or res.get("uid")
            if reservation_durable and reservation_pms_number and msg_uid and msg_uid not in seen_uids:
                seen_uids.add(msg_uid)
                fire_items.append((msg_uid, reservation_pms_number))
            elif reservation_durable and not msg_uid:
                failed += 1
                logger.error("[PULL-A] Durable reservation has no delivery UID; ACK withheld")
        except Exception as exc:
            failed += 1
            logger.error(
                "[PULL-A] Reservation processing raised %s; delivery ACK withheld",
                type(exc).__name__,
            )

    fired = 0
    for uid, pms_number in fire_items:
        try:
            fire_result = await provider.confirm_delivery(
                message_uid=uid,
                pms_number=pms_number,
            )
            if fire_result.success:
                fired += 1
            else:
                failed += 1
                logger.warning("[PULL-A] Delivery ACK rejected by provider")
        except Exception as exc:
            failed += 1
            logger.error("[PULL-A] Delivery ACK raised %s", type(exc).__name__)

    return {
        "success": failed == 0 and pending == 0 and fired == len(fire_items),
        "all_reservations": all_reservations,
        "processed": processed,
        "fired": fired,
        "pending": pending,
        "failed": failed,
        "pages": total_pages,
    }


async def _read_durable_pms_number(
    tenant_id: str,
    payload: dict[str, Any],
) -> str | None:
    """Read the tenant-scoped durable PMS identifier used in provider ACK history."""
    external_id = str(payload.get("hr_number") or "").strip()
    if not external_id:
        return None
    booking = await db.bookings.find_one(
        {
            "tenant_id": tenant_id,
            "external_reservation_id": external_id,
            "booking_source": {"$ne": "ota_unmatched_hold"},
        },
        {"_id": 0, "id": 1, "status": 1},
    )
    if not booking:
        return None
    pms_number = str(booking.get("id") or "").strip()
    return pms_number or None


async def _ensure_durable_pms_result(
    tenant_id: str,
    payload: dict[str, Any],
    pipeline_result,
    *,
    is_cancellation: bool,
) -> str:
    """Return durable only after the PMS booking state can be read back."""
    pipeline_status = getattr(pipeline_result, "status", "failed")
    if pipeline_status in {"pending", "retry_later"}:
        return _PMS_PENDING
    if pipeline_status == "failed":
        return _PMS_FAILED

    external_id = str(payload.get("hr_number") or "").strip()
    if not external_id:
        return _PMS_FAILED

    booking_query = {
        "tenant_id": tenant_id,
        "external_reservation_id": external_id,
        "booking_source": {"$ne": "ota_unmatched_hold"},
    }
    booking = await db.bookings.find_one(booking_query, {"_id": 0, "status": 1})

    if not booking and (getattr(pipeline_result, "status", "") == "duplicate" or getattr(pipeline_result, "decision", "") == "skip"):
        from core.import_bridge_service import replay_reviewed_mapping_import

        replay_result = await replay_reviewed_mapping_import(
            tenant_id=tenant_id,
            provider="hotelrunner",
            external_reservation_id=external_id,
        )
        if replay_result["status"] == "pending":
            return _PMS_PENDING
        if replay_result["status"] == "failed":
            return _PMS_FAILED
        booking = await db.bookings.find_one(booking_query, {"_id": 0, "status": 1})

    if booking:
        hr_state = "cancelled" if is_cancellation else (payload.get("state") or "confirmed")
        await sync_reservation_update(
            tenant_id,
            external_id,
            payload,
            hr_state,
            str(payload.get("updated_at") or ""),
        )
        if not is_cancellation:
            from domains.channel_manager.providers.unmatched_hold import (
                release_unmatched_reservation_hold,
            )

            release_result = await release_unmatched_reservation_hold(
                tenant_id=tenant_id,
                external_id=external_id,
                reason="mapping_resolved",
                delete_hold=True,
            )
            if release_result.get("booking_id") and not release_result.get("released"):
                return _PMS_FAILED
        booking = await db.bookings.find_one(booking_query, {"_id": 0, "status": 1})
        if not booking:
            return _PMS_FAILED
        if is_cancellation:
            return _PMS_DURABLE if booking.get("status") == "cancelled" else _PMS_FAILED
        return _PMS_FAILED if booking.get("status") == "cancelled" else _PMS_DURABLE

    import_record = await db.imported_reservations.find_one(
        {
            "tenant_id": tenant_id,
            "provider": "hotelrunner",
            "external_reservation_id": external_id,
        },
        {"_id": 0, "import_status": 1},
    )
    if import_record and import_record.get("import_status") in {
        "pending_auto_import",
        "processing",
        "retry",
    }:
        return _PMS_PENDING
    return _PMS_FAILED


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
                                    logger.info("[PULL-A5] Cancellation event processed")
                            except Exception as exc:
                                if "duplicate" not in str(exc).lower():
                                    logger.error(
                                        "[PULL-A5] Modified event failed exception_class=%s",
                                        type(exc).__name__,
                                    )
                    except Exception as exc:
                        logger.error(
                            "[PULL-A5] Reservation expansion failed exception_class=%s",
                            type(exc).__name__,
                        )
    except Exception as exc:
        logger.warning(
            "[PULL-A5] Modified reservation check failed exception_class=%s",
            type(exc).__name__,
        )

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
        except Exception as exc:
            if "not found" not in str(exc).lower():
                logger.warning(
                    "[PULL-A6] Sync failed exception_class=%s",
                    type(exc).__name__,
                )

    return updated


async def run_phase_b(tenant_id: str, provider) -> tuple[int, int]:
    from domains.channel_manager.providers.hotelrunner.mapping_bridge import backfill_hotelrunner_mappings

    await backfill_hotelrunner_mappings(tenant_id)
    catchup_imported = 0
    catchup_updated = 0

    # Mappings may have been completed after earlier reservations were parked
    # for review. Replay those local holds before comparing provider history.
    from core.import_bridge_service import replay_reviewed_mapping_import
    from core.import_decision import check_booking_source_exists

    review_rows = await db.imported_reservations.find(
        {
            "tenant_id": tenant_id,
            "provider": "hotelrunner",
            "import_status": "review_required",
            "review_reason": {"$in": ["unmapped_room_type", "unmapped_rate_plan"]},
        },
        {"_id": 0, "external_reservation_id": 1},
    ).to_list(500)
    for review in review_rows:
        external_id = review.get("external_reservation_id")
        if not external_id:
            continue
        was_durable = await check_booking_source_exists(
            tenant_id,
            "hotelrunner",
            external_id,
        )
        replay = await replay_reviewed_mapping_import(
            tenant_id=tenant_id,
            provider="hotelrunner",
            external_reservation_id=external_id,
        )
        if not was_durable and replay.get("status") == "durable":
            catchup_imported += 1

    all_page = 1
    all_total_pages = 1
    known_ext_ids = set()
    known_ext_updated = {}
    known_ext_status = {}
    known_ext_totals = {}

    async for doc in db.imported_reservations.find(
        {"tenant_id": tenant_id, "provider": "hotelrunner"},
        {"_id": 0, "external_reservation_id": 1, "provider_updated_at": 1, "created_at": 1},
    ):
        ext_id = doc.get("external_reservation_id", "")
        known_ext_ids.add(ext_id)
        known_ext_updated[ext_id] = doc.get("provider_updated_at") or doc.get("created_at", "")

    async for bdoc in db.bookings.find(
        {"tenant_id": tenant_id, "external_reservation_id": {"$exists": True, "$ne": ""}},
        {"_id": 0, "external_reservation_id": 1, "status": 1, "total_amount": 1},
    ):
        external_id = bdoc.get("external_reservation_id", "")
        known_ext_status[external_id] = bdoc.get("status", "confirmed")
        known_ext_totals[external_id] = bdoc.get("total_amount")

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
            hr_updated_at = res.get("updated_at", "")
            hr_state = res.get("state", "confirmed")
            hr_next_states = res.get("next_states") or []
            hr_cancel_reason = res.get("cancel_reason") or ""

            effective_state = hr_state
            if hr_state in ("cancelled", "canceled") or hr_cancel_reason:
                effective_state = "canceled"

            logger.info(
                "[PULL-PHASE-B] state=%s effective_state=%s next_state_count=%d has_cancel_reason=%s",
                hr_state,
                effective_state,
                len(hr_next_states),
                bool(hr_cancel_reason),
            )

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
                    except Exception as exc:
                        if "duplicate" not in str(exc).lower():
                            logger.error(
                                "[PULL-CATCHUP] Import failed exception_class=%s",
                                type(exc).__name__,
                            )
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
                        "[PULL-PHASE-B] sub_effective=%s room_cancelled=%s top_effective=%s ts_changed=%s new_partial=%s",
                        sub_effective_state,
                        sub_room_cancelled,
                        effective_state,
                        timestamp_changed,
                        has_new_room_cancels,
                    )

                    hr_status_check = {"canceled": "cancelled", "cancelled": "cancelled", "no_show": "no_show"}.get(sub_effective_state, sub_effective_state)
                    state_changed = hr_status_check != stored_status

                    if stored_status == "cancelled" and hr_status_check != "cancelled":
                        state_changed = False

                    # Provider timestamps do not change merely because Syroce's
                    # earlier importer selected rooms[].price instead of the
                    # authoritative guest-payable total.  A manual full
                    # reconciliation must therefore be allowed through this
                    # outer gate when the exact legacy before-tax signature is
                    # present; sync_reservation_update performs the same narrow
                    # check again before writing.
                    legacy_total_repair = matches_legacy_before_tax_total(
                        known_ext_totals.get(sub_ext),
                        sub_res,
                    )

                    if state_changed or timestamp_changed or legacy_total_repair:
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
                                logger.info(
                                    "[PULL-SYNC] state_changed=%s provider_state=%s stored_state=%s ts_changed=%s",
                                    state_changed,
                                    hr_status_check,
                                    stored_status,
                                    timestamp_changed,
                                )
                        except Exception as exc:
                            logger.error(
                                "[PULL-SYNC] Update failed exception_class=%s",
                                type(exc).__name__,
                            )

        all_page += 1

    if catchup_imported > 0:
        logger.info("[PULL-CATCHUP] Missing reservations imported count=%d", catchup_imported)
    if catchup_updated > 0:
        logger.info("[PULL-SYNC] Reservations updated count=%d", catchup_updated)

    return catchup_imported, catchup_updated


async def sync_reservation_update(
    tenant_id: str,
    ext_reservation_id: str,
    hr_payload: dict[str, Any],
    hr_state: str,
    hr_updated_at: str,
) -> bool:
    booking = await db.bookings.find_one(
        {
            "tenant_id": tenant_id,
            "external_reservation_id": ext_reservation_id,
            "booking_source": {"$ne": "ota_unmatched_hold"},
        },
        {"_id": 0},
    )
    if not booking:
        logger.warning("[PULL-SYNC] Durable PMS booking not found")
        return False

    total = hotelrunner_guest_total(hr_payload)
    existing_sync_ts = booking.get("last_synced_from_provider_at", "")
    provider_update_is_stale = bool(existing_sync_ts and hr_updated_at and hr_updated_at <= existing_sync_ts)
    legacy_total_repair = provider_update_is_stale and matches_legacy_before_tax_total(
        booking.get("total_amount"),
        hr_payload,
    )
    if provider_update_is_stale and not legacy_total_repair:
        logger.debug("[PULL-SYNC] Provider update already applied or superseded")
        return True

    rooms = hr_payload.get("rooms") or []
    room = rooms[0] if rooms else {}

    updates = {}
    guest_name_hr = f"{hr_payload.get('firstname', '')} {hr_payload.get('lastname', '')}".strip()
    if not guest_name_hr:
        guest_name_hr = hr_payload.get("guest", "")

    if not provider_update_is_stale and guest_name_hr and guest_name_hr != booking.get("guest_name", ""):
        updates["guest_name"] = guest_name_hr

    checkin = hr_payload.get("checkin_date") or (room.get("checkin_date") if room else "")
    checkout = hr_payload.get("checkout_date") or (room.get("checkout_date") if room else "")
    if not provider_update_is_stale and checkin and checkin != booking.get("check_in", ""):
        updates["check_in"] = checkin
    if not provider_update_is_stale and checkout and checkout != booking.get("check_out", ""):
        updates["check_out"] = checkout

    if room and not provider_update_is_stale:
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

    if total is not None and abs(total - float(booking.get("total_amount", 0))) > 0.01:
        updates["total_amount"] = total
        updates["provider_total_amount"] = total
        updates["pricing_tax_inclusive"] = True
        updates["pricing_source"] = "channel_manager"
        if legacy_total_repair:
            updates["hotelrunner_total_reconciled_from"] = float(booking.get("total_amount", 0))
            updates["hotelrunner_total_reconciled_at"] = datetime.now(UTC).isoformat()

    hr_status_map = {
        "confirmed": "confirmed",
        "modified": "confirmed",
        "canceled": "cancelled",
        "cancelled": "cancelled",
        "no_show": "no_show",
    }
    mapped_status = hr_status_map.get(hr_state, hr_state)
    if not provider_update_is_stale and mapped_status != booking.get("status", ""):
        updates["status"] = mapped_status
        if mapped_status == "cancelled":
            updates["cancelled_at"] = datetime.now(UTC).isoformat()
            cancel_reason = hr_payload.get("cancel_reason") or "Provider cancellation"
            updates["cancellation_reason"] = cancel_reason

    if not updates:
        if hr_updated_at:
            now = datetime.now(UTC).isoformat()
            result = await db.bookings.update_one(
                {
                    "tenant_id": tenant_id,
                    "external_reservation_id": ext_reservation_id,
                    "booking_source": {"$ne": "ota_unmatched_hold"},
                },
                {"$set": {"last_synced_from_provider_at": hr_updated_at, "updated_at": now}},
            )
            await db.imported_reservations.update_one(
                {"tenant_id": tenant_id, "external_reservation_id": ext_reservation_id},
                {"$set": {"provider_updated_at": hr_updated_at, "updated_at": now}},
            )
            return bool(getattr(result, "matched_count", 1))
        return True

    updates["updated_at"] = datetime.now(UTC).isoformat()
    if not provider_update_is_stale:
        updates["last_synced_from_provider_at"] = hr_updated_at

    booking_update = await db.bookings.update_one(
        {
            "tenant_id": tenant_id,
            "external_reservation_id": ext_reservation_id,
            "booking_source": {"$ne": "ota_unmatched_hold"},
        },
        {"$set": updates},
    )
    if not getattr(booking_update, "matched_count", 1):
        return False

    imported_update = {
        "updated_at": datetime.now(UTC).isoformat(),
        "guest_name": guest_name_hr if "guest_name" in updates else booking.get("guest_name", ""),
    }
    if not provider_update_is_stale:
        imported_update["provider_updated_at"] = hr_updated_at
    if "total_amount" in updates:
        imported_update["total_amount"] = updates["total_amount"]
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

    logger.info("[PULL-SYNC] Durable PMS update completed fields=%s", list(updates.keys()))

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
    except Exception as exc:
        logger.error("[PULL-SYNC] Notification creation raised %s", type(exc).__name__)

    await publish_booking_change(
        tenant_id=tenant_id,
        booking_id=booking.get("id", ""),
        event_type="cancel" if updates.get("status") == "cancelled" else "update",
        status=updates.get("status", booking.get("status")),
        source="hotelrunner_pull",
        external_reservation_id=ext_reservation_id,
    )

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
