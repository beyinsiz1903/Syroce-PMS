"""
HotelRunner Scheduled Pull Job & Reservation Sync

Cursor-based scheduled reservation pull from HotelRunner.
Two-phase strategy:
  Phase A — fetch undelivered reservations -> process -> fire (confirm delivery)
  Phase B — fetch ALL reservations -> diff against DB -> import missing + sync updates
"""
import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from domains.channel_manager.providers.hotelrunner_shared import (
    _persist_and_process,
    _resolve_property_id,
    _timeline_append,
    explode_multi_room_reservation,
)
from models.schemas import User

logger = logging.getLogger(__name__)

sync_router = APIRouter(
    prefix="/api/channel-manager/hotelrunner",
    tags=["HotelRunner Sync"],
)


# ── Scheduled Pull Scheduler ─────────────────────────────────────────

class ReservationPullScheduler:
    """
    Cursor-based scheduled reservation pull from HotelRunner.
    Runs every N minutes, fetches reservations updated since last cursor - safety window.
    Backs off automatically when rate-limited (429).
    """

    def __init__(self):
        self._running = False
        self._task = None
        self._cycle_count = 0
        self._consecutive_rate_limits = 0
        self._base_interval = 30  # default seconds — match Exely speed

    async def start(self, interval_minutes: int = 15, safety_window_minutes: int = 5, interval_seconds: int | None = None):
        """Start the scheduled pull loop. interval_seconds overrides interval_minutes if provided."""
        if self._running:
            logger.warning("[PULL] Scheduler already running")
            return
        self._running = True
        sleep_seconds = interval_seconds if interval_seconds is not None else interval_minutes * 60
        self._base_interval = sleep_seconds
        self._task = asyncio.create_task(self._run_loop(sleep_seconds, safety_window_minutes))
        logger.info(f"[PULL] Scheduler started: every {sleep_seconds}s, safety window {safety_window_minutes}min")

    async def stop(self):
        """Stop the scheduled pull loop."""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("[PULL] Scheduler stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    async def _run_loop(self, sleep_seconds: int, safety_window_minutes: int):
        while self._running:
            try:
                await self._pull_all_tenants(safety_window_minutes)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[PULL] Loop error: {e}")

            # Adaptive backoff: if rate-limited, wait progressively longer
            if self._consecutive_rate_limits > 0:
                backoff_multiplier = min(2 ** self._consecutive_rate_limits, 16)  # max 16x
                actual_sleep = self._base_interval * backoff_multiplier
                logger.warning(
                    "[PULL] Rate-limit backoff active: sleeping %ds (base=%ds, consecutive_429=%d)",
                    actual_sleep, self._base_interval, self._consecutive_rate_limits,
                )
                await asyncio.sleep(actual_sleep)
            else:
                await asyncio.sleep(sleep_seconds)

    async def _pull_all_tenants(self, safety_window_minutes: int):
        """Pull reservations for all active HotelRunner connections."""
        self._cycle_count += 1
        connections = await db.hotelrunner_connections.find(
            {"is_active": True, "auto_sync_reservations": True},
            {"_id": 0},
        ).to_list(100)

        for conn in connections:
            try:
                tenant_id = conn["tenant_id"]
                hr_id = conn.get("hr_id", conn.get("property_id", "default"))

                from core.secrets import get_secrets_manager
                sm = get_secrets_manager()
                creds = await sm.get_provider_credentials(tenant_id, "hotelrunner", hr_id)

                if not creds or not creds.get("token"):
                    if conn.get("token"):
                        creds = {"token": conn["token"], "hr_id": hr_id}
                    else:
                        logger.error(f"[PULL] No credentials for tenant {tenant_id} — skipping")
                        continue

                await self.pull_for_tenant(
                    tenant_id=tenant_id,
                    token=creds["token"],
                    hr_id=creds.get("hr_id", hr_id),
                    safety_window_minutes=safety_window_minutes,
                )
            except Exception as e:
                logger.error(f"[PULL] Error for tenant {conn.get('tenant_id', '?')}: {e}")

    async def pull_for_tenant(
        self,
        tenant_id: str,
        token: str,
        hr_id: str,
        safety_window_minutes: int = 5,
        is_manual: bool = False,
    ) -> dict[str, Any]:
        """Pull reservations for a specific tenant.

        Two-phase strategy:
          Phase A — fetch undelivered reservations -> process -> fire (confirm delivery)
          Phase B — fetch ALL reservations -> diff against DB -> import missing ones
        """
        from core.tenant_db import set_tenant_context
        set_tenant_context(tenant_id)

        from domains.channel_manager.providers.hotelrunner import HotelRunnerProvider

        # Scheduled polling: fail fast (0 retries) to let adaptive backoff handle recovery
        # Manual pull: normal retries (3) since user is waiting
        retries = 3 if is_manual else 0
        provider = HotelRunnerProvider(token=token, hr_id=hr_id, max_retries=retries)
        pull_start = datetime.now(UTC)

        # ── Phase A: Fetch UNDELIVERED reservations ──────────────
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
                # Track rate limit hits for adaptive backoff
                if "429" in str(error_msg) or "rate limit" in str(error_msg).lower():
                    self._consecutive_rate_limits += 1
                    logger.warning(
                        "[PULL] Rate limit detected (consecutive: %d) — will back off on next cycle",
                        self._consecutive_rate_limits,
                    )
                if page == 1:
                    await _log_pull(tenant_id, "failed", 0, error_msg)
                    return {"success": False, "error": error_msg}
                break

            page_reservations = result["data"].get("reservations", [])
            all_reservations.extend(page_reservations)
            total_pages = result["data"].get("pages", 1)
            page += 1

        # Reset rate limit counter on successful fetch
        if all_reservations or page > 1:
            self._consecutive_rate_limits = 0

        # Process undelivered + fire
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
                    logger.info(
                        f"[PULL] Multi-room reservation {res.get('hr_number')}: "
                        f"{rooms_count} rooms -> {len(sub_reservations)} sub-reservations"
                    )

                for sub_res in sub_reservations:
                    try:
                        # Detect cancellation state for correct event_type
                        sub_state_a = (sub_res.get("state") or "").lower()
                        is_cancel_a = (
                            sub_state_a in ("cancelled", "canceled")
                            or sub_res.get("_room_cancelled")
                            or bool(sub_res.get("cancel_reason"))
                        )
                        evt_type_a = "reservation_cancel_pull" if is_cancel_a else "reservation_pull"
                        await _persist_and_process(
                            tenant_id, _resolve_property_id(sub_res),
                            sub_res, evt_type_a,
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

        # Fire (confirm delivery) for undelivered reservations
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

        # ── Phase A.5: Fetch recently MODIFIED reservations ─────────
        # This is the KEY optimization — catches name changes, date changes, etc.
        # within seconds instead of waiting for Phase B (catch-up)
        mod_processed = 0
        try:
            cursor_doc = await db.hotelrunner_pull_cursors.find_one(
                {"tenant_id": tenant_id}, {"_id": 0, "last_pull_at": 1},
            )
            if cursor_doc and cursor_doc.get("last_pull_at"):
                from datetime import timedelta
                last_pull_dt = datetime.fromisoformat(cursor_doc["last_pull_at"])
                # Fetch modifications since last pull minus safety window
                mod_since = (last_pull_dt - timedelta(minutes=safety_window_minutes)).strftime("%Y-%m-%d")

                # Paginate through ALL modified reservations (not just page 1)
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
                                    # Detect cancellation from state — use different event_type
                                    # so provider_event_id is unique and not deduped with
                                    # the previous modification event
                                    sub_state = (sub_res.get("state") or "").lower()
                                    is_cancelled = (
                                        sub_state in ("cancelled", "canceled")
                                        or sub_res.get("_room_cancelled")
                                        or bool(sub_res.get("cancel_reason"))
                                    )
                                    evt_type = "reservation_cancel_pull" if is_cancelled else "reservation_modified_pull"
                                    await _persist_and_process(
                                        tenant_id, _resolve_property_id(sub_res),
                                        sub_res, evt_type,
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

        # ── Phase A.6: Sync detected modifications to PMS bookings ──────
        # Instead of making additional API calls, compare Phase A.5 results
        # with existing booking data and apply updates directly
        individual_updated = 0
        if mod_processed > 0:
            try:
                individual_updated = await _sync_modified_reservations_to_pms(tenant_id)
            except Exception as e:
                logger.warning(f"[PULL-A6] Modification sync error: {e}")

        # ── Phase B: Catch-up — fetch ALL reservations, import missing + sync updates ─
        catchup_imported = 0
        catchup_updated = 0
        # Skip Phase B if rate-limited recently to reduce API pressure
        if self._consecutive_rate_limits > 0:
            run_phase_b = False
            logger.info("[PULL] Skipping Phase B — rate limit backoff active (consecutive: %d)", self._consecutive_rate_limits)
        else:
            # Phase B runs every 10th cycle (~5 min at 30s interval) since
            # Phase A.5 now handles modifications in real-time
            run_phase_b = (self._cycle_count % 10 == 0)
        if not run_phase_b:
            logger.debug(f"[PULL] Skipping Phase B (cycle {self._cycle_count}, runs every 10th)")
        else:
            logger.info(f"[PULL] Running Phase B catch-up (cycle {self._cycle_count})")

        if run_phase_b:
            try:
                catchup_imported, catchup_updated = await _run_phase_b(
                    tenant_id, provider,
                )
            except Exception as e:
                logger.error(f"[PULL-CATCHUP] Error during catch-up pull: {e}")

        # ── Update cursor ──────────────────────────────────────
        await db.hotelrunner_pull_cursors.update_one(
            {"tenant_id": tenant_id},
            {"$set": {
                "tenant_id": tenant_id,
                "last_pull_at": pull_start.isoformat(),
                "reservations_fetched": len(all_reservations),
                "reservations_processed": processed,
                "reservations_fired": fired,
                "mod_processed": mod_processed,
                "individual_updated": individual_updated,
                "catchup_imported": catchup_imported,
                "catchup_updated": catchup_updated,
                "pages_fetched": total_pages,
            }},
            upsert=True,
        )

        duration_ms = int((datetime.now(UTC) - pull_start).total_seconds() * 1000)
        total_processed = processed + mod_processed + individual_updated + catchup_imported
        await _log_pull(tenant_id, "success", total_processed, duration_ms=duration_ms)

        logger.info(
            f"[PULL] Tenant {tenant_id}: fetched {len(all_reservations)}, "
            f"processed {processed}, fired {fired}, "
            f"mod_a5 {mod_processed}, individual_a6 {individual_updated}, "
            f"catchup {catchup_imported}, updated {catchup_updated}"
        )
        return {
            "success": True,
            "fetched": len(all_reservations),
            "processed": processed,
            "fired": fired,
            "mod_processed": mod_processed,
            "individual_updated": individual_updated,
            "catchup_imported": catchup_imported,
            "catchup_updated": catchup_updated,
            "pages": total_pages,
        }


# ── Sync Modified Reservations to PMS (Phase A.6) ───────────────────

async def _sync_modified_reservations_to_pms(tenant_id: str) -> int:
    """After Phase A.5 persists modified reservations as raw events,
    compare the latest raw event data with existing PMS bookings
    and apply any detected changes (guest name, dates, status, etc.).

    This runs without additional API calls — uses only local DB data.
    Returns count of updated reservations.
    """
    # Find recently processed raw events from Phase A.5 (last 2 minutes)
    from datetime import timedelta
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
            was_updated = await _sync_reservation_update(
                tenant_id, ext_id, payload, hr_state, hr_updated_at,
            )
            if was_updated:
                updated += 1
        except Exception as e:
            if "not found" not in str(e).lower():
                logger.warning(f"[PULL-A6] Sync error for {ext_id}: {e}")

    return updated


# ── Phase B: Catch-up Pull ───────────────────────────────────────────

async def _run_phase_b(tenant_id: str, provider) -> tuple[int, int]:
    """Run Phase B catch-up: fetch ALL reservations, diff against DB, import missing + sync updates.

    Returns (catchup_imported, catchup_updated).
    """
    catchup_imported = 0
    catchup_updated = 0

    all_page = 1
    all_total_pages = 1
    known_ext_ids = set()
    known_ext_updated = {}
    known_ext_status = {}

    # Gather already-imported external_reservation_ids with their last known update time and status
    async for doc in db.imported_reservations.find(
        {"tenant_id": tenant_id, "provider": "hotelrunner"},
        {"_id": 0, "external_reservation_id": 1, "provider_updated_at": 1, "created_at": 1},
    ):
        ext_id = doc.get("external_reservation_id", "")
        known_ext_ids.add(ext_id)
        known_ext_updated[ext_id] = doc.get("provider_updated_at") or doc.get("created_at", "")

    # Also gather current booking statuses for state-change detection
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
            # Only use explicit state or cancel_reason for cancellation detection.
            # next_states=['cancel'] means "cancel is an available ACTION", NOT that
            # the reservation IS cancelled. HR sends this for ALL confirmed reservations.
            if hr_state in ("cancelled", "canceled") or hr_cancel_reason:
                effective_state = "canceled"

            logger.info(
                f"[PULL-PHASE-B] {hr_number}: state={hr_state}, effective={effective_state}, "
                f"next_states={hr_next_states}, cancel_reason={hr_cancel_reason}, "
                f"updated_at={hr_updated_at}"
            )

            sub_reservations = explode_multi_room_reservation(res)

            # Detect NEW room-level cancellations
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
                    # New reservation: import
                    if sub_room_cancelled:
                        sub_res["state"] = "cancelled"
                    elif not is_exploded and effective_state == "canceled":
                        # Single-room reservation — top-level state is reliable
                        sub_res["state"] = "cancelled"
                        sub_res["_room_cancelled"] = True
                    # For multi-room (is_exploded): trust exploder's per-room state

                    try:
                        # Use correct event_type for cancellations
                        catchup_evt = "reservation_cancel_catchup" if sub_room_cancelled or effective_state == "canceled" else "reservation_catchup"
                        await _persist_and_process(
                            tenant_id, _resolve_property_id(sub_res),
                            sub_res, catchup_evt,
                        )
                        catchup_imported += 1
                    except Exception as e:
                        if "duplicate" not in str(e).lower():
                            logger.error(f"[PULL-CATCHUP] Error importing {sub_ext}: {e}")
                else:
                    # Existing reservation: check for modifications/cancellations
                    stored_updated = known_ext_updated.get(sub_ext, "")
                    stored_status = known_ext_status.get(sub_ext, "confirmed")
                    timestamp_changed = hr_updated_at and hr_updated_at > stored_updated

                    # Per-room effective state — three-tier logic
                    if sub_room_cancelled:
                        sub_effective_state = "canceled"
                    elif is_exploded and effective_state == "canceled":
                        if has_new_room_cancels:
                            # Other rooms stay active when new partial cancellation detected
                            sub_effective_state = "confirmed"
                        else:
                            # Room is NOT _room_cancelled — keep stored status.
                            # Don't cascade top-level cancel to active rooms just because
                            # timestamp changed (e.g. name/date modification).
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

                    # SAFETY: Never auto-un-cancel a reservation.
                    # HR returns state=confirmed for both active AND cancelled reservations,
                    # so we can't reliably detect un-cancellation. Keep cancelled status.
                    if stored_status == "cancelled" and hr_status_check != "cancelled":
                        state_changed = False

                    if state_changed or timestamp_changed:
                        try:
                            updated = await _sync_reservation_update(
                                tenant_id, sub_ext, sub_res, sub_effective_state, hr_updated_at,
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


# ── Reservation Update Sync ──────────────────────────────────────────

async def _sync_reservation_update(
    tenant_id: str,
    ext_reservation_id: str,
    hr_payload: dict[str, Any],
    hr_state: str,
    hr_updated_at: str,
) -> bool:
    """
    Sync modifications/cancellations from HotelRunner to PMS bookings.

    Compares HR payload with stored booking and updates:
    - Guest name changes
    - Date changes
    - Amount changes
    - Status changes (cancelled, modified)
    - Guest record updates

    Returns True if booking was updated.
    """
    booking = await db.bookings.find_one(
        {"tenant_id": tenant_id, "external_reservation_id": ext_reservation_id},
        {"_id": 0},
    )
    if not booking:
        logger.warning(f"[PULL-SYNC] Booking not found for {ext_reservation_id}")
        return False

    rooms = hr_payload.get("rooms") or []
    room = rooms[0] if rooms else {}

    updates = {}
    guest_name_hr = f"{hr_payload.get('firstname', '')} {hr_payload.get('lastname', '')}".strip()
    if not guest_name_hr:
        guest_name_hr = hr_payload.get("guest", "")

    # Guest name change
    if guest_name_hr and guest_name_hr != booking.get("guest_name", ""):
        updates["guest_name"] = guest_name_hr
        logger.info(f"[PULL-SYNC] {ext_reservation_id}: guest name '{booking.get('guest_name')}' -> '{guest_name_hr}'")

    # Date changes
    checkin = hr_payload.get("checkin_date") or (room.get("checkin_date") if room else "")
    checkout = hr_payload.get("checkout_date") or (room.get("checkout_date") if room else "")
    if checkin and checkin != booking.get("check_in", ""):
        updates["check_in"] = checkin
    if checkout and checkout != booking.get("check_out", ""):
        updates["check_out"] = checkout

    # Room type change
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

    # Amount change
    total = float(hr_payload.get("total", 0) or 0)
    if room:
        total = float(room.get("total", room.get("price", 0)) or 0)
    if total > 0 and abs(total - float(booking.get("total_amount", 0))) > 0.01:
        updates["total_amount"] = total

    # Status change (cancellation)
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

    # Apply updates
    updates["updated_at"] = datetime.now(UTC).isoformat()
    updates["last_synced_from_provider_at"] = hr_updated_at

    await db.bookings.update_one(
        {"tenant_id": tenant_id, "external_reservation_id": ext_reservation_id},
        {"$set": updates},
    )

    # Update imported_reservations record with new provider timestamp
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

    # Update guest record if name changed
    if "guest_name" in updates and booking.get("guest_id"):
        guest_parts = guest_name_hr.split(" ", 1)
        guest_first = guest_parts[0]
        guest_last = guest_parts[1] if len(guest_parts) > 1 else ""
        await db.guests.update_one(
            {"tenant_id": tenant_id, "id": booking["guest_id"]},
            {"$set": {
                "first_name": guest_first,
                "last_name": guest_last,
                "updated_at": datetime.now(UTC).isoformat(),
            }},
        )

    # Timeline: sync update
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

    # Create notifications for important changes
    try:
        notification_messages = []
        if "status" in updates and updates["status"] == "cancelled":
            notification_messages.append(
                f"Rezervasyon Iptali: {guest_name_hr or booking.get('guest_name', '')}, "
                f"{ext_reservation_id}, "
                f"Giris: {booking.get('check_in', '')}, Cikis: {booking.get('check_out', '')}"
            )
        if "guest_name" in updates:
            notification_messages.append(
                f"Misafir Adi Degisikligi: {booking.get('guest_name', '')} -> {updates['guest_name']}, "
                f"{ext_reservation_id}"
            )
        if "check_in" in updates or "check_out" in updates:
            notification_messages.append(
                f"Tarih Degisikligi: {ext_reservation_id}, "
                f"Giris: {updates.get('check_in', booking.get('check_in', ''))}, "
                f"Cikis: {updates.get('check_out', booking.get('check_out', ''))}"
            )

        for msg in notification_messages:
            await db.notifications.insert_one({
                "id": str(uuid.uuid4()),
                "tenant_id": tenant_id,
                "type": "reservation_update",
                "message": msg,
                "booking_id": booking.get("id", ""),
                "external_reservation_id": ext_reservation_id,
                "is_read": False,
                "created_at": datetime.now(UTC).isoformat(),
            })
    except Exception as e:
        logger.error(f"[PULL-SYNC] Notification creation error for {ext_reservation_id}: {e}")

    return True


# ── Pull Log Helper ──────────────────────────────────────────────────

async def _log_pull(tenant_id: str, status: str, records: int, error: str | None = None, duration_ms: int = 0):
    await db.hotelrunner_sync_logs.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "sync_type": "scheduled_pull",
        "status": status,
        "duration_ms": duration_ms,
        "records_synced": records,
        "error_message": error,
        "initiator": "system",
    })


# ── Singleton ─────────────────────────────────────────────────────────
pull_scheduler = ReservationPullScheduler()


# ── Manual Pull/Sync Endpoints ───────────────────────────────────────

@sync_router.post("/sync/reservations/pull")
async def manual_pull(
    current_user: User = Depends(get_current_user),
):
    """Manually trigger a reservation pull from HotelRunner."""
    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"_id": 0},
    )
    if not conn:
        raise HTTPException(status_code=404, detail="HotelRunner baglantisi bulunamadi")

    hr_id = conn.get("hr_id", conn.get("property_id", "default"))
    from core.secrets import get_secrets_manager
    sm = get_secrets_manager()
    creds = await sm.get_provider_credentials(current_user.tenant_id, "hotelrunner", hr_id)

    if not creds or not creds.get("token"):
        fallback = await db.hotelrunner_connections.find_one(
            {"tenant_id": current_user.tenant_id, "is_active": True},
            {"_id": 0, "token": 1, "hr_id": 1},
        )
        if fallback and fallback.get("token"):
            creds = {"token": fallback["token"], "hr_id": fallback.get("hr_id", hr_id)}
        else:
            raise HTTPException(status_code=502, detail="HotelRunner kimlik bilgileri bulunamadi")

    result = await pull_scheduler.pull_for_tenant(
        tenant_id=current_user.tenant_id,
        token=creds["token"],
        hr_id=creds.get("hr_id", hr_id),
        safety_window_minutes=5,
        is_manual=True,
    )

    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"Pull hatasi: {result.get('error')}")

    return {
        "message": f"{result['processed']} rezervasyon islendi ({result['fetched']} cekildi, {result.get('fired', 0)} onaylandi)",
        **result,
    }


@sync_router.get("/sync/status")
async def get_sync_status(current_user: User = Depends(get_current_user)):
    """Get current sync status including scheduler and cursor info."""
    cursor = await db.hotelrunner_pull_cursors.find_one(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0},
    )

    pending_events = await db.hotelrunner_raw_events.count_documents(
        {"tenant_id": current_user.tenant_id, "status": "pending"},
    )
    error_events = await db.hotelrunner_raw_events.count_documents(
        {"tenant_id": current_user.tenant_id, "status": "error"},
    )
    total_reservations = await db.hotelrunner_reservations.count_documents(
        {"tenant_id": current_user.tenant_id},
    )

    return {
        "scheduler_running": pull_scheduler.is_running,
        "auto_polling_disabled": not pull_scheduler.is_running,
        "polling_interval_seconds": pull_scheduler._base_interval,
        "cycle_count": pull_scheduler._cycle_count,
        "last_pull": cursor,
        "pending_events": pending_events,
        "error_events": error_events,
        "total_reservations": total_reservations,
        "optimization_notes": {
            "phase_a": "Yeni rezervasyonlar (undelivered) - her döngüde",
            "phase_a5": "Modifikasyon tespiti (from_last_update_date) - her döngüde",
            "phase_a6": "Bireysel rezervasyon kontrolü - her döngüde",
            "phase_b": "Tam catch-up (tüm rezervasyonlar) - her 10. döngüde",
        },
    }


@sync_router.post("/sync/scheduler/start")
async def start_scheduler(current_user: User = Depends(get_current_user)):
    """Start the scheduled pull job."""
    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"_id": 0},
    )
    if not conn:
        raise HTTPException(status_code=404, detail="HotelRunner baglantisi bulunamadi")

    interval = conn.get("sync_interval_minutes", 15)
    await pull_scheduler.start(interval_minutes=interval)
    return {"message": f"Scheduler baslatildi ({interval} dk aralikla)", "interval": interval}


@sync_router.post("/sync/scheduler/stop")
async def stop_scheduler(current_user: User = Depends(get_current_user)):
    """Stop the scheduled pull job."""
    await pull_scheduler.stop()
    return {"message": "Scheduler durduruldu"}


@sync_router.post("/sync/reservations/full-resync")
async def full_resync(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """Full resync: fetch ALL reservations (including already delivered) and re-import.
    Multi-room reservations are properly exploded into per-room bookings.
    Deduplication prevents double imports of already-imported reservations.
    """
    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"_id": 0},
    )
    if not conn:
        raise HTTPException(status_code=404, detail="HotelRunner baglantisi bulunamadi")

    hr_id = conn.get("hr_id", conn.get("property_id", "default"))
    from core.secrets import get_secrets_manager
    sm = get_secrets_manager()
    creds = await sm.get_provider_credentials(current_user.tenant_id, "hotelrunner", hr_id)

    if not creds or not creds.get("token"):
        fallback = await db.hotelrunner_connections.find_one(
            {"tenant_id": current_user.tenant_id, "is_active": True},
            {"_id": 0, "token": 1, "hr_id": 1},
        )
        if fallback and fallback.get("token"):
            creds = {"token": fallback["token"], "hr_id": fallback.get("hr_id", hr_id)}
        else:
            raise HTTPException(status_code=502, detail="HotelRunner kimlik bilgileri bulunamadi")

    from core.tenant_db import set_tenant_context
    set_tenant_context(current_user.tenant_id)
    from domains.channel_manager.providers.hotelrunner import HotelRunnerProvider
    provider = HotelRunnerProvider(token=creds["token"], hr_id=creds.get("hr_id", hr_id))

    # Fetch ALL reservations (not just undelivered)
    all_reservations = []
    page = 1
    total_pages = 1
    while page <= total_pages:
        result = await provider.get_reservations(
            undelivered=False, per_page=50, page=page,
        )
        if not result["success"]:
            raise HTTPException(status_code=502, detail=f"Rezervasyon cekme hatasi: {result.get('error')}")
        page_reservations = result["data"].get("reservations", [])
        all_reservations.extend(page_reservations)
        total_pages = result["data"].get("pages", 1)
        page += 1

    # Explode multi-room and process
    processed = 0
    skipped = 0
    errors = 0
    for res in all_reservations:
        sub_reservations = explode_multi_room_reservation(res)
        for sub_res in sub_reservations:
            try:
                await _persist_and_process(
                    current_user.tenant_id, _resolve_property_id(sub_res),
                    sub_res, "reservation_pull",
                )
                processed += 1
            except Exception as e:
                err_msg = str(e)
                if "duplicate" in err_msg.lower() or "already" in err_msg.lower():
                    skipped += 1
                else:
                    errors += 1
                    logger.error(f"[RESYNC] Error: {e}")

    return {
        "message": f"Full resync tamamlandi: {processed} islendi, {skipped} atlandi (zaten var), {errors} hata",
        "success": True,
        "fetched": len(all_reservations),
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
    }
