"""
HotelRunner Webhook Receiver & Scheduled Pull Job

Webhook: Lightweight receiver → raw_channel_events → async process via ingest pipeline
Pull Job: Cursor-based fetch every N minutes → diff check → ingest

UPDATED: Now feeds into the unified 9-collection ingest pipeline.
TIMELINE: Every webhook writes received → normalized → deduplicated stages.
"""
import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request

from core.database import db
from core.security import get_current_user
from domains.channel_manager import unified_repository as repo
from domains.channel_manager.data_model import (
    ConnectorProvider,
    ProcessingStatus,
    RawChannelEvent,
    RawEventSource,
)
from domains.channel_manager.ingest.normalizer import extract_hotelrunner_identity
from domains.channel_manager.ingest.pipeline import process_event
from models.schemas import User

logger = logging.getLogger(__name__)


def _timeline_append(**kwargs):
    """Fire-and-forget timeline write. Returns a coroutine."""
    try:
        from controlplane.timeline_writer import get_timeline_writer
        return get_timeline_writer().append(**kwargs)
    except Exception:
        async def _noop():
            return None
        return _noop()


async def _store_raw_payload(
    tenant_id: str, correlation_id: str, provider: str,
    external_id: str, event_type: str, payload: dict,
    source_ip: str,
) -> str:
    """Store raw webhook JSON payload for debugging. Returns payload_id."""
    payload_id = str(uuid.uuid4())
    try:
        raw_str = json.dumps(payload, default=str, ensure_ascii=False)
        await db.webhook_raw_payloads.insert_one({
            "id": payload_id,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "provider": provider,
            "external_id": external_id,
            "event_type": event_type,
            "content_type": "application/json",
            "raw_payload": raw_str,
            "payload_size_bytes": len(raw_str.encode("utf-8")),
            "source_ip": source_ip,
            "received_at": datetime.now(UTC).isoformat(),
        })
    except Exception as e:
        logger.warning("Raw payload storage failed (non-blocking): %s", e)
    return payload_id

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/channel-manager/hotelrunner",
    tags=["HotelRunner Webhooks & Sync"],
)


# ── Multi-room Reservation Exploder ───────────────────────────────────

def explode_multi_room_reservation(raw_reservation: dict[str, Any]) -> list[dict[str, Any]]:
    """Explode a HotelRunner reservation with multiple rooms into per-room payloads.

    HotelRunner sends multi-room bookings as one reservation object with a `rooms` array.
    Each room becomes a separate PMS booking. Sub-reservation numbering follows HR convention:
      rooms[0] → hr_number (original)
      rooms[1] → hr_number-1
      rooms[2] → hr_number-2
      ...

    Per-room state: Each room may have its own cancellation status.
    The room-level state overrides the top-level state for that specific sub-reservation.

    If the reservation has 0 or 1 rooms, returns it as-is (list of 1).
    """
    rooms = raw_reservation.get("rooms", [])
    if not rooms or not isinstance(rooms, list) or len(rooms) <= 1:
        return [raw_reservation]

    hr_number = str(raw_reservation.get("hr_number", ""))
    exploded = []

    for idx, room in enumerate(rooms):
        if not isinstance(room, dict):
            continue

        sub_hr = hr_number if idx == 0 else f"{hr_number}-{idx}"

        sub_payload = {
            **raw_reservation,
            "hr_number": sub_hr,
            "rooms": [room],
            "total": float(room.get("price", 0) or 0),
            "_exploded_from": hr_number,
            "_room_index": idx,
        }

        # Use room-level dates if available, fallback to reservation-level
        if room.get("checkin_date"):
            sub_payload["checkin_date"] = room["checkin_date"]
        if room.get("checkout_date"):
            sub_payload["checkout_date"] = room["checkout_date"]

        # Per-room state override: if the room has its own state, use it
        # This is critical for multi-room reservations where only some rooms are cancelled
        room_state = (room.get("state") or "").lower()
        room_status = (room.get("status") or "").lower()
        room_cancel_reason = room.get("cancel_reason") or ""
        room_next_states = room.get("next_states") or []

        if room_state in ("cancelled", "canceled"):
            sub_payload["state"] = "cancelled"
            sub_payload["_room_cancelled"] = True
        elif room_status in ("cancelled", "canceled"):
            sub_payload["state"] = "cancelled"
            sub_payload["_room_cancelled"] = True
        elif room_cancel_reason or "cancel" in room_next_states:
            sub_payload["state"] = "cancelled"
            sub_payload["_room_cancelled"] = True
            if room_cancel_reason:
                sub_payload["cancel_reason"] = room_cancel_reason
        else:
            # Room is NOT cancelled — ensure top-level cancel markers don't leak
            sub_payload["_room_cancelled"] = False

        exploded.append(sub_payload)

    return exploded if exploded else [raw_reservation]


# ── Webhook Raw Event Persistence ─────────────────────────────────────

async def _persist_and_process(
    tenant_id: str, property_id: str, payload: dict[str, Any], event_type: str,
    source_ip: str = "system",
):
    """Persist raw event and process through the unified ingest pipeline.

    Timeline stages written:
      1. webhook_received — raw payload stored
      2. (normalized, deduplicated, validated — written by pipeline.process_event)
    """
    from core.tenant_db import set_tenant_context
    set_tenant_context(tenant_id)

    t_start = datetime.now(UTC)
    correlation_id = str(uuid.uuid4())
    identity = extract_hotelrunner_identity(payload)
    hr_number = identity.get("external_reservation_id", "")
    last_mod = identity.get("provider_last_modified_at", "")
    identity["provider_event_id"] = f"{hr_number}_{event_type}_{last_mod}"

    # ── Store raw payload ─────────────────────────────────────────
    raw_payload_id = await _store_raw_payload(
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        provider="hotelrunner",
        external_id=hr_number,
        event_type=event_type,
        payload=payload,
        source_ip=source_ip,
    )

    # ── Timeline: webhook_received ────────────────────────────────
    t_received = datetime.now(UTC)
    recv_duration_ms = int((t_received - t_start).total_seconds() * 1000)
    await _timeline_append(
        tenant_id=tenant_id,
        correlation_id=correlation_id,
        entity_type="reservation",
        external_id=hr_number,
        stage="webhook_received",
        status="success",
        source="hotelrunner_webhook",
        provider="hotelrunner",
        duration_ms=recv_duration_ms,
        metadata={
            "raw_payload_id": raw_payload_id,
            "event_type": event_type,
            "hr_number": hr_number,
            "source_ip": source_ip,
            "content_type": "application/json",
        },
    )

    payload_hash = RawChannelEvent.compute_payload_hash(payload)

    event = RawChannelEvent(
        tenant_id=tenant_id,
        property_id=property_id,
        provider=ConnectorProvider.HOTELRUNNER,
        event_type=event_type,
        provider_event_id=identity["provider_event_id"],
        external_reservation_id=identity["external_reservation_id"],
        provider_version=identity["provider_version"],
        provider_last_modified_at=identity["provider_last_modified_at"],
        raw_payload=payload,
        payload_hash=payload_hash,
        received_via=RawEventSource.WEBHOOK,
        processing_status=ProcessingStatus.PENDING,
        correlation_id=correlation_id,
    )
    event_doc = event.to_doc()
    event_id = await repo.insert_raw_event(event_doc)
    event_doc["id"] = event_id

    # Process through pipeline (pipeline writes normalized/deduplicated/validated stages)
    result = await process_event(event_doc)
    logger.info(f"[WEBHOOK] {event_type}: {event_id} → {result.decision} ({result.reason})")
    return result


async def _process_webhook_batch(
    tenant_id: str, property_id: str, reservations: list, event_type: str,
    source_ip: str = "system",
):
    """Background task: process webhook reservations through ingest pipeline.
    Multi-room reservations are exploded into per-room pipeline events.
    """
    for res in reservations:
        try:
            sub_reservations = explode_multi_room_reservation(res)
            for sub_res in sub_reservations:
                try:
                    await _persist_and_process(tenant_id, property_id, sub_res, event_type, source_ip)
                except Exception as e:
                    logger.error(f"[WEBHOOK] Error processing sub-reservation {sub_res.get('hr_number')}: {e}")
        except Exception as e:
            logger.error(f"[WEBHOOK] Error processing {event_type}: {e}")


def _resolve_property_id(body: dict[str, Any]) -> str:
    """Extract property_id from payload."""
    return body.get("property_id", "prop-001")


@router.post("/webhooks/reservations")
async def webhook_reservations(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook endpoint for new reservations from HotelRunner.
    Persists as raw_channel_event and processes via unified ingest pipeline.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    tenant_id = request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id")
    if not tenant_id:
        tenant_id = body.get("tenant_id", "")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required (header X-Tenant-ID or query param)")

    property_id = _resolve_property_id(body)
    reservations = body.get("reservations", [body] if "hr_number" in body else [])
    source_ip = request.client.host if request.client else "unknown"

    background_tasks.add_task(
        _process_webhook_batch, tenant_id, property_id, reservations, "reservation_create", source_ip,
    )

    return {
        "status": "accepted",
        "count": len(reservations),
        "message": f"{len(reservations)} rezervasyon alindi, islenmeye baslandi",
    }


@router.post("/webhooks/modifications")
async def webhook_modifications(request: Request, background_tasks: BackgroundTasks):
    """Webhook for reservation modifications → unified ingest pipeline."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    tenant_id = request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id")
    if not tenant_id:
        tenant_id = body.get("tenant_id", "")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")

    property_id = _resolve_property_id(body)
    reservations = body.get("reservations", [body] if "hr_number" in body else [])
    source_ip = request.client.host if request.client else "unknown"

    background_tasks.add_task(
        _process_webhook_batch, tenant_id, property_id, reservations, "reservation_modify", source_ip,
    )
    return {"status": "accepted", "count": len(reservations)}


@router.post("/webhooks/cancellations")
async def webhook_cancellations(request: Request, background_tasks: BackgroundTasks):
    """Webhook for reservation cancellations → unified ingest pipeline."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    tenant_id = request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id")
    if not tenant_id:
        tenant_id = body.get("tenant_id", "")
    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")

    property_id = _resolve_property_id(body)
    reservations = body.get("reservations", [body] if "hr_number" in body else [])
    source_ip = request.client.host if request.client else "unknown"

    # Set status to cancelled for the decision engine
    for res in reservations:
        if "status" not in res:
            res["status"] = "cancelled"

    background_tasks.add_task(
        _process_webhook_batch, tenant_id, property_id, reservations, "reservation_cancel", source_ip,
    )
    return {"status": "accepted", "count": len(reservations)}


# ── Raw Events API ───────────────────────────────────────────────────

@router.get("/logs/events")
async def get_raw_events(
    limit: int = 50,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Get raw ingest events for debugging and audit."""
    query = {"tenant_id": current_user.tenant_id}
    if status:
        query["status"] = status

    events = await db.hotelrunner_raw_events.find(
        query, {"_id": 0, "payload": 0}
    ).sort("received_at", -1).to_list(limit)
    return {"events": events, "count": len(events)}


@router.get("/logs/errors")
async def get_error_events(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
):
    """Get failed ingest events."""
    events = await db.hotelrunner_raw_events.find(
        {"tenant_id": current_user.tenant_id, "status": "error"},
        {"_id": 0},
    ).sort("received_at", -1).to_list(limit)
    return {"events": events, "count": len(events)}


@router.post("/sync/reservations/replay/{event_id}")
async def replay_event(
    event_id: str,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    """Replay a raw event through the ingest pipeline."""
    event = await db.hotelrunner_raw_events.find_one(
        {"id": event_id, "tenant_id": current_user.tenant_id},
    )
    if not event:
        raise HTTPException(status_code=404, detail="Event bulunamadi")

    # Reset event status
    await db.hotelrunner_raw_events.update_one(
        {"id": event_id},
        {"$set": {"status": "pending", "processed_at": None, "error_message": None, "retry_count": (event.get("retry_count", 0) + 1)}},
    )

    background_tasks.add_task(
        _process_webhook_batch,
        current_user.tenant_id,
        [event["payload"]],
        event["event_type"],
    )
    return {"message": "Event replay baslatildi", "event_id": event_id}


# ── Scheduled Pull Job ───────────────────────────────────────────────

class ReservationPullScheduler:
    """
    Cursor-based scheduled reservation pull from HotelRunner.
    Runs every N minutes, fetches reservations updated since last cursor - safety window.
    """

    def __init__(self):
        self._running = False
        self._task = None
        self._cycle_count = 0  # Track cycles for Phase B scheduling

    async def start(self, interval_minutes: int = 15, safety_window_minutes: int = 5, interval_seconds: int | None = None):
        """Start the scheduled pull loop. interval_seconds overrides interval_minutes if provided."""
        if self._running:
            logger.warning("[PULL] Scheduler already running")
            return
        self._running = True
        sleep_seconds = interval_seconds if interval_seconds is not None else interval_minutes * 60
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

                # Resolve credentials via secrets manager (same as _get_provider)
                from core.secrets import get_secrets_manager
                sm = get_secrets_manager()
                creds = await sm.get_provider_credentials(tenant_id, "hotelrunner", hr_id)

                if not creds or not creds.get("token"):
                    # Fallback: legacy plaintext token in connection doc
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
    ) -> dict[str, Any]:
        """Pull reservations for a specific tenant.

        Two-phase strategy:
          Phase A — fetch undelivered reservations → process → fire (confirm delivery)
          Phase B — fetch ALL reservations → diff against DB → import missing ones
                    (catches push-failed reservations that HR no longer marks undelivered)
        """
        from core.tenant_db import set_tenant_context
        set_tenant_context(tenant_id)

        from domains.channel_manager.providers.hotelrunner import HotelRunnerProvider

        provider = HotelRunnerProvider(token=token, hr_id=hr_id)

        pull_start = datetime.now(UTC)

        # ── Phase A: Fetch UNDELIVERED reservations ──────────────────
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
                logger.error(f"[PULL] Failed for tenant {tenant_id} page {page}: {result.get('error')}")
                if page == 1:
                    await _log_pull(tenant_id, "failed", 0, result.get("error"))
                    return {"success": False, "error": result.get("error")}
                break

            page_reservations = result["data"].get("reservations", [])
            all_reservations.extend(page_reservations)
            total_pages = result["data"].get("pages", 1)
            page += 1

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
                        f"{rooms_count} rooms → {len(sub_reservations)} sub-reservations"
                    )

                for sub_res in sub_reservations:
                    try:
                        await _persist_and_process(
                            tenant_id, _resolve_property_id(sub_res),
                            sub_res, "reservation_pull",
                        )
                        processed += 1
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

        # ── Phase B: Catch-up — fetch ALL reservations, import missing + sync updates ─
        # Run Phase B every 3rd cycle to avoid rate-limiting (Phase A+B = 2 calls per cycle)
        catchup_imported = 0
        catchup_updated = 0
        run_phase_b = (pull_scheduler._cycle_count % 3 == 0)
        if not run_phase_b:
            logger.debug(f"[PULL] Skipping Phase B (cycle {pull_scheduler._cycle_count}, runs every 3rd)")
        else:
            # Wait 10 seconds between Phase A and Phase B to avoid rate limiting
            await asyncio.sleep(10)
            logger.info(f"[PULL] Running Phase B catch-up (cycle {pull_scheduler._cycle_count})")

        if run_phase_b:
            try:
                all_page = 1
                all_total_pages = 1
                known_ext_ids = set()
                known_ext_updated = {}  # ext_id → provider_updated_at stored in DB

                # Gather already-imported external_reservation_ids with their last known update time and status
                known_ext_status = {}  # ext_id → booking status stored in DB
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

                        # Derive effective state: if next_states contains 'cancel' or cancel_reason exists,
                        # treat as cancellation even if state is still 'confirmed'
                        effective_state = hr_state
                        if "cancel" in hr_next_states or hr_cancel_reason:
                            effective_state = "canceled"

                        logger.info(
                            f"[PULL-PHASE-B] {hr_number}: state={hr_state}, effective={effective_state}, "
                            f"next_states={hr_next_states}, cancel_reason={hr_cancel_reason}, "
                            f"updated_at={hr_updated_at}"
                        )

                        sub_reservations = explode_multi_room_reservation(res)

                        # ── Detect NEW room-level cancellations ──
                        # If HR explicitly marks NEW rooms as cancelled (rooms that our DB
                        # still has as confirmed), this is a PARTIAL cancel → only cancel
                        # those specific rooms.
                        # If NO new room-level cancels exist but top-level is cancelled,
                        # this is a GLOBAL cancel → cancel ALL rooms.
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
                                # ── New reservation: import ──
                                # For new imports, use top-level effective state when no room-level cancel
                                if sub_room_cancelled:
                                    sub_res["state"] = "cancelled"
                                elif effective_state == "canceled" and not has_new_room_cancels:
                                    sub_res["state"] = "cancelled"
                                    sub_res["_room_cancelled"] = True

                                try:
                                    await _persist_and_process(
                                        tenant_id, _resolve_property_id(sub_res),
                                        sub_res, "reservation_catchup",
                                    )
                                    catchup_imported += 1
                                except Exception as e:
                                    if "duplicate" not in str(e).lower():
                                        logger.error(f"[PULL-CATCHUP] Error importing {sub_ext}: {e}")
                            else:
                                # ── Existing reservation: check for modifications/cancellations ──
                                stored_updated = known_ext_updated.get(sub_ext, "")
                                stored_status = known_ext_status.get(sub_ext, "confirmed")
                                timestamp_changed = hr_updated_at and hr_updated_at > stored_updated

                                # Per-room effective state — three-tier logic:
                                # 1. Explicit room-level cancel → always cancelled
                                # 2. Exploded room in cancelled reservation:
                                #    a. New partial cancel detected → only cancel marked rooms
                                #    b. No new room cancels + timestamp changed → global cancel
                                #    c. No new room cancels + timestamp same → keep stored status
                                # 3. Single-room / non-cancelled → use top-level state
                                if sub_room_cancelled:
                                    sub_effective_state = "canceled"
                                elif is_exploded and effective_state == "canceled":
                                    if has_new_room_cancels:
                                        # Partial cancel: HR marked specific rooms as cancelled
                                        # This room is NOT explicitly marked → keep confirmed
                                        sub_effective_state = "confirmed"
                                    elif timestamp_changed:
                                        # Global cancel: no new room-level cancels but
                                        # timestamp changed → all remaining rooms cancelled
                                        sub_effective_state = "canceled"
                                    else:
                                        # No new changes → keep stored status
                                        sub_effective_state = {"cancelled": "canceled"}.get(stored_status, stored_status)
                                else:
                                    sub_effective_state = effective_state

                                logger.info(
                                    f"[PULL-PHASE-B] {sub_ext}: sub_effective={sub_effective_state}, "
                                    f"room_cancelled={sub_room_cancelled}, top_effective={effective_state}, "
                                    f"ts_changed={timestamp_changed}, new_partial={has_new_room_cancels}"
                                )

                                # Map HR effective state to PMS status for comparison
                                hr_status_check = {"canceled": "cancelled", "cancelled": "cancelled", "no_show": "no_show"}.get(sub_effective_state, sub_effective_state)
                                state_changed = hr_status_check != stored_status

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
            except Exception as e:
                logger.error(f"[PULL-CATCHUP] Error during catch-up pull: {e}")

        # ── Update cursor ──────────────────────────────────────────
        await db.hotelrunner_pull_cursors.update_one(
            {"tenant_id": tenant_id},
            {"$set": {
                "tenant_id": tenant_id,
                "last_pull_at": pull_start.isoformat(),
                "reservations_fetched": len(all_reservations),
                "reservations_processed": processed,
                "reservations_fired": fired,
                "catchup_imported": catchup_imported,
                "catchup_updated": catchup_updated,
                "pages_fetched": total_pages,
            }},
            upsert=True,
        )

        duration_ms = int((datetime.now(UTC) - pull_start).total_seconds() * 1000)
        await _log_pull(tenant_id, "success", processed + catchup_imported, duration_ms=duration_ms)

        logger.info(f"[PULL] Tenant {tenant_id}: fetched {len(all_reservations)}, processed {processed}, fired {fired}, catchup {catchup_imported}, updated {catchup_updated}")
        return {
            "success": True,
            "fetched": len(all_reservations),
            "processed": processed,
            "fired": fired,
            "catchup_imported": catchup_imported,
            "catchup_updated": catchup_updated,
            "pages": total_pages,
        }


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
    # Find the booking by external_reservation_id
    booking = await db.bookings.find_one(
        {"tenant_id": tenant_id, "external_reservation_id": ext_reservation_id},
        {"_id": 0},
    )
    if not booking:
        logger.warning(f"[PULL-SYNC] Booking not found for {ext_reservation_id}")
        return False

    # Extract normalized data from HR payload
    rooms = hr_payload.get("rooms") or []
    room = rooms[0] if rooms else {}

    # Build update fields
    updates = {}
    guest_name_hr = f"{hr_payload.get('firstname', '')} {hr_payload.get('lastname', '')}".strip()
    if not guest_name_hr:
        guest_name_hr = hr_payload.get("guest", "")

    # Guest name change
    if guest_name_hr and guest_name_hr != booking.get("guest_name", ""):
        updates["guest_name"] = guest_name_hr
        logger.info(f"[PULL-SYNC] {ext_reservation_id}: guest name '{booking.get('guest_name')}' → '{guest_name_hr}'")

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
        # Also check via room_mappings to resolve PMS room type name
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
                logger.info(f"[PULL-SYNC] {ext_reservation_id}: room type '{booking.get('room_type')}' → '{new_room_type}'")

    # Amount change
    total = float(hr_payload.get("total", 0) or 0)
    if room:
        total = float(room.get("total", room.get("price", 0)) or 0)
    if total > 0 and abs(total - float(booking.get("total_amount", 0))) > 0.01:
        updates["total_amount"] = total

    # Status change (cancellation)
    hr_status_map = {
        "confirmed": "confirmed",
        "modified": "confirmed",  # Modified but still confirmed
        "canceled": "cancelled",
        "cancelled": "cancelled",
        "no_show": "no_show",
    }
    mapped_status = hr_status_map.get(hr_state, hr_state)
    if mapped_status != booking.get("status", ""):
        updates["status"] = mapped_status
        logger.info(f"[PULL-SYNC] {ext_reservation_id}: status '{booking.get('status')}' → '{mapped_status}'")
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
                f"Rezervasyon İptali: {guest_name_hr or booking.get('guest_name', '')}, "
                f"{ext_reservation_id}, "
                f"Giriş: {booking.get('check_in', '')}, Çıkış: {booking.get('check_out', '')}"
            )
        if "guest_name" in updates:
            notification_messages.append(
                f"Misafir Adı Değişikliği: {booking.get('guest_name', '')} → {updates['guest_name']}, "
                f"{ext_reservation_id}"
            )
        if "check_in" in updates or "check_out" in updates:
            notification_messages.append(
                f"Tarih Değişikliği: {ext_reservation_id}, "
                f"Giriş: {updates.get('check_in', booking.get('check_in', ''))}, "
                f"Çıkış: {updates.get('check_out', booking.get('check_out', ''))}"
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


# Singleton
pull_scheduler = ReservationPullScheduler()


# ── Manual Pull/Sync Endpoints ───────────────────────────────────────

@router.post("/sync/reservations/pull")
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

    # Resolve credentials via secrets manager
    hr_id = conn.get("hr_id", conn.get("property_id", "default"))
    from core.secrets import get_secrets_manager
    sm = get_secrets_manager()
    creds = await sm.get_provider_credentials(current_user.tenant_id, "hotelrunner", hr_id)

    if not creds or not creds.get("token"):
        # Fallback: legacy plaintext token in connection doc
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
    )

    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"Pull hatasi: {result.get('error')}")

    return {
        "message": f"{result['processed']} rezervasyon islendi ({result['fetched']} cekildi, {result.get('fired', 0)} onaylandi)",
        **result,
    }


@router.get("/sync/status")
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
        "last_pull": cursor,
        "pending_events": pending_events,
        "error_events": error_events,
        "total_reservations": total_reservations,
    }


@router.post("/sync/scheduler/start")
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


@router.post("/sync/scheduler/stop")
async def stop_scheduler(current_user: User = Depends(get_current_user)):
    """Stop the scheduled pull job."""
    await pull_scheduler.stop()
    return {"message": "Scheduler durduruldu"}



@router.post("/sync/reservations/full-resync")
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
        "message": f"Full resync tamamlandi: {processed} islendi, {skipped} atlandı (zaten var), {errors} hata",
        "success": True,
        "fetched": len(all_reservations),
        "processed": processed,
        "skipped": skipped,
        "errors": errors,
    }
