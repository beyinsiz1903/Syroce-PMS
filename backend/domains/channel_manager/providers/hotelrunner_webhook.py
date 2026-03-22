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
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks

from core.database import db
from core.security import get_current_user
from models.schemas import User
from domains.channel_manager import unified_repository as repo
from domains.channel_manager.data_model import (
    ConnectorProvider, RawChannelEvent, RawEventSource, ProcessingStatus,
)
from domains.channel_manager.ingest.normalizer import extract_hotelrunner_identity
from domains.channel_manager.ingest.pipeline import process_event

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
            "received_at": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.warning("Raw payload storage failed (non-blocking): %s", e)
    return payload_id

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/channel-manager/hotelrunner",
    tags=["HotelRunner Webhooks & Sync"],
)


# ── Webhook Raw Event Persistence ─────────────────────────────────────

async def _persist_and_process(
    tenant_id: str, property_id: str, payload: Dict[str, Any], event_type: str,
    source_ip: str = "system",
):
    """Persist raw event and process through the unified ingest pipeline.

    Timeline stages written:
      1. webhook_received — raw payload stored
      2. (normalized, deduplicated, validated — written by pipeline.process_event)
    """
    t_start = datetime.now(timezone.utc)
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
    t_received = datetime.now(timezone.utc)
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
    """Background task: process webhook reservations through ingest pipeline."""
    for res in reservations:
        try:
            await _persist_and_process(tenant_id, property_id, res, event_type, source_ip)
        except Exception as e:
            logger.error(f"[WEBHOOK] Error processing {event_type}: {e}")


def _resolve_property_id(body: Dict[str, Any]) -> str:
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
    status: Optional[str] = None,
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

    async def start(self, interval_minutes: int = 15, safety_window_minutes: int = 5):
        """Start the scheduled pull loop."""
        if self._running:
            logger.warning("[PULL] Scheduler already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(interval_minutes, safety_window_minutes))
        logger.info(f"[PULL] Scheduler started: every {interval_minutes}min, safety window {safety_window_minutes}min")

    async def stop(self):
        """Stop the scheduled pull loop."""
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("[PULL] Scheduler stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    async def _run_loop(self, interval_minutes: int, safety_window_minutes: int):
        while self._running:
            try:
                await self._pull_all_tenants(safety_window_minutes)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"[PULL] Loop error: {e}")

            await asyncio.sleep(interval_minutes * 60)

    async def _pull_all_tenants(self, safety_window_minutes: int):
        """Pull reservations for all active HotelRunner connections."""
        connections = await db.hotelrunner_connections.find(
            {"is_active": True, "auto_sync_reservations": True},
            {"_id": 0},
        ).to_list(100)

        for conn in connections:
            try:
                await self.pull_for_tenant(
                    tenant_id=conn["tenant_id"],
                    token=conn["token"],
                    hr_id=conn["hr_id"],
                    safety_window_minutes=safety_window_minutes,
                )
            except Exception as e:
                logger.error(f"[PULL] Error for tenant {conn['tenant_id']}: {e}")

    async def pull_for_tenant(
        self,
        tenant_id: str,
        token: str,
        hr_id: str,
        safety_window_minutes: int = 5,
    ) -> Dict[str, Any]:
        """Pull reservations for a specific tenant."""
        from domains.channel_manager.providers.hotelrunner import HotelRunnerProvider

        provider = HotelRunnerProvider(token=token, hr_id=hr_id)

        # Get cursor: last pull time - safety window
        cursor_doc = await db.hotelrunner_pull_cursors.find_one(
            {"tenant_id": tenant_id},
            {"_id": 0},
        )

        if cursor_doc and cursor_doc.get("last_pull_at"):
            last_pull = datetime.fromisoformat(cursor_doc["last_pull_at"])
            fetch_from = last_pull - timedelta(minutes=safety_window_minutes)
        else:
            fetch_from = datetime.now(timezone.utc) - timedelta(days=7)

        from_date = fetch_from.strftime("%Y-%m-%d")
        pull_start = datetime.now(timezone.utc)

        # Fetch from HotelRunner
        result = await provider.get_reservations(
            undelivered=False,
            from_date=from_date,
            per_page=10,
            page=1,
        )

        if not result["success"]:
            logger.error(f"[PULL] Failed for tenant {tenant_id}: {result.get('error')}")
            await _log_pull(tenant_id, "failed", 0, result.get("error"))
            return {"success": False, "error": result.get("error")}

        all_reservations = result["data"].get("reservations", [])
        total_pages = result["data"].get("pages", 1)

        # Fetch remaining pages
        for page in range(2, total_pages + 1):
            page_result = await provider.get_reservations(
                undelivered=False, from_date=from_date, per_page=10, page=page,
            )
            if page_result["success"]:
                all_reservations.extend(page_result["data"].get("reservations", []))

        # Process through unified ingest pipeline
        processed = 0
        for res in all_reservations:
            try:
                await _persist_and_process(
                    tenant_id, _resolve_property_id(res),
                    res, "reservation_pull",
                )
                processed += 1
            except Exception as e:
                logger.error(f"[PULL] Error processing reservation: {e}")

        # Update cursor
        await db.hotelrunner_pull_cursors.update_one(
            {"tenant_id": tenant_id},
            {"$set": {
                "tenant_id": tenant_id,
                "last_pull_at": pull_start.isoformat(),
                "last_fetch_from": from_date,
                "reservations_fetched": len(all_reservations),
                "reservations_processed": processed,
                "pages_fetched": total_pages,
            }},
            upsert=True,
        )

        duration_ms = int((datetime.now(timezone.utc) - pull_start).total_seconds() * 1000)
        await _log_pull(tenant_id, "success", processed, duration_ms=duration_ms)

        logger.info(f"[PULL] Tenant {tenant_id}: fetched {len(all_reservations)}, processed {processed}")
        return {
            "success": True,
            "fetched": len(all_reservations),
            "processed": processed,
            "pages": total_pages,
            "from_date": from_date,
        }


async def _log_pull(tenant_id: str, status: str, records: int, error: Optional[str] = None, duration_ms: int = 0):
    await db.hotelrunner_sync_logs.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
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

    result = await pull_scheduler.pull_for_tenant(
        tenant_id=current_user.tenant_id,
        token=conn["token"],
        hr_id=conn["hr_id"],
        safety_window_minutes=5,
    )

    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"Pull hatasi: {result.get('error')}")

    return {
        "message": f"{result['processed']} rezervasyon islendi ({result['fetched']} cekildi)",
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
