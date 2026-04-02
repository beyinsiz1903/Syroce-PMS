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

        # ── Phase B: Catch-up — fetch ALL reservations, import missing ─
        catchup_imported = 0
        try:
            all_page = 1
            all_total_pages = 1
            known_ext_ids = set()

            # Gather already-imported external_reservation_ids
            async for doc in db.imported_reservations.find(
                {"tenant_id": tenant_id, "provider": "hotelrunner"},
                {"_id": 0, "external_reservation_id": 1},
            ):
                known_ext_ids.add(doc.get("external_reservation_id", ""))

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
                    rooms = res.get("rooms") or []
                    # Check if ANY sub-reservation from this parent is missing
                    if len(rooms) <= 1:
                        if hr_number not in known_ext_ids:
                            sub_reservations = explode_multi_room_reservation(res)
                            for sub_res in sub_reservations:
                                try:
                                    await _persist_and_process(
                                        tenant_id, _resolve_property_id(sub_res),
                                        sub_res, "reservation_catchup",
                                    )
                                    catchup_imported += 1
                                except Exception as e:
                                    if "duplicate" not in str(e).lower():
                                        logger.error(f"[PULL-CATCHUP] Error: {e}")
                    else:
                        # Multi-room: check each suffix
                        any_missing = False
                        for idx in range(len(rooms)):
                            suffix_id = f"{hr_number}-{idx}" if idx > 0 else hr_number
                            if suffix_id not in known_ext_ids:
                                any_missing = True
                                break

                        if any_missing:
                            sub_reservations = explode_multi_room_reservation(res)
                            for sub_res in sub_reservations:
                                sub_ext = sub_res.get("hr_number", "")
                                if sub_ext not in known_ext_ids:
                                    try:
                                        await _persist_and_process(
                                            tenant_id, _resolve_property_id(sub_res),
                                            sub_res, "reservation_catchup",
                                        )
                                        catchup_imported += 1
                                    except Exception as e:
                                        if "duplicate" not in str(e).lower():
                                            logger.error(f"[PULL-CATCHUP] Error: {e}")

                all_page += 1

            if catchup_imported > 0:
                logger.info(f"[PULL-CATCHUP] Tenant {tenant_id}: {catchup_imported} missing reservations imported")
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
                "pages_fetched": total_pages,
            }},
            upsert=True,
        )

        duration_ms = int((datetime.now(UTC) - pull_start).total_seconds() * 1000)
        await _log_pull(tenant_id, "success", processed + catchup_imported, duration_ms=duration_ms)

        logger.info(f"[PULL] Tenant {tenant_id}: fetched {len(all_reservations)}, processed {processed}, fired {fired}, catchup {catchup_imported}")
        return {
            "success": True,
            "fetched": len(all_reservations),
            "processed": processed,
            "fired": fired,
            "catchup_imported": catchup_imported,
            "pages": total_pages,
        }


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
