"""
HotelRunner Webhook Receiver & Scheduled Pull Job

Webhook: Lightweight receiver → raw store → async process
Pull Job: Cursor-based fetch every N minutes → diff check → ingest
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any

from fastapi import APIRouter, Request, HTTPException, Depends, BackgroundTasks

from core.database import db
from core.security import get_current_user
from models.schemas import User
from domains.channel_manager.providers.hotelrunner_ingest import (
    ingest_reservation,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/channel-manager/hotelrunner",
    tags=["HotelRunner Webhooks & Sync"],
)


# ── Webhook Receiver ─────────────────────────────────────────────────
# Lightweight: receive, store raw, ack fast, process in background

async def _process_webhook_batch(tenant_id: str, reservations: list, event_type: str):
    """Background task: process webhook reservations through ingest pipeline."""
    results = []
    for res in reservations:
        result = await ingest_reservation(
            tenant_id=tenant_id,
            raw_payload=res,
            event_type=event_type,
            source="webhook",
        )
        results.append(result)
    logger.info(f"[WEBHOOK] Processed {len(results)} reservations for tenant {tenant_id}")


@router.post("/webhooks/reservations")
async def webhook_reservations(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook endpoint for new reservations from HotelRunner.
    Stores raw payload immediately and processes asynchronously.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    # Extract tenant from header or query param
    tenant_id = request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id")
    if not tenant_id:
        # Try to find tenant from hr_id in payload
        hr_id = body.get("hr_id") or request.query_params.get("hr_id")
        if hr_id:
            conn = await db.hotelrunner_connections.find_one({"hr_id": hr_id}, {"_id": 0, "tenant_id": 1})
            if conn:
                tenant_id = conn["tenant_id"]

    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required (header X-Tenant-ID or query param)")

    # Handle both single reservation and batch
    reservations = body.get("reservations", [body] if "hr_number" in body else [])

    # Process in background (don't block the ack)
    background_tasks.add_task(_process_webhook_batch, tenant_id, reservations, "reservation")

    return {
        "status": "accepted",
        "count": len(reservations),
        "message": f"{len(reservations)} rezervasyon alindi, islenmeye baslandi",
    }


@router.post("/webhooks/modifications")
async def webhook_modifications(request: Request, background_tasks: BackgroundTasks):
    """Webhook for reservation modifications."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    tenant_id = request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id")
    hr_id = body.get("hr_id") or request.query_params.get("hr_id")
    if not tenant_id and hr_id:
        conn = await db.hotelrunner_connections.find_one({"hr_id": hr_id}, {"_id": 0, "tenant_id": 1})
        if conn:
            tenant_id = conn["tenant_id"]

    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")

    reservations = body.get("reservations", [body] if "hr_number" in body else [])

    background_tasks.add_task(_process_webhook_batch, tenant_id, reservations, "modification")
    return {"status": "accepted", "count": len(reservations)}


@router.post("/webhooks/cancellations")
async def webhook_cancellations(request: Request, background_tasks: BackgroundTasks):
    """Webhook for reservation cancellations."""
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    tenant_id = request.headers.get("X-Tenant-ID") or request.query_params.get("tenant_id")
    hr_id = body.get("hr_id") or request.query_params.get("hr_id")
    if not tenant_id and hr_id:
        conn = await db.hotelrunner_connections.find_one({"hr_id": hr_id}, {"_id": 0, "tenant_id": 1})
        if conn:
            tenant_id = conn["tenant_id"]

    if not tenant_id:
        raise HTTPException(status_code=400, detail="tenant_id required")

    reservations = body.get("reservations", [body] if "hr_number" in body else [])

    background_tasks.add_task(_process_webhook_batch, tenant_id, reservations, "cancellation")
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

        # Process through ingest pipeline
        processed = 0
        for res in all_reservations:
            ingest_result = await ingest_reservation(
                tenant_id=tenant_id,
                raw_payload=res,
                event_type="reservation",
                source="scheduled_pull",
            )
            if ingest_result.get("success"):
                processed += 1

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
