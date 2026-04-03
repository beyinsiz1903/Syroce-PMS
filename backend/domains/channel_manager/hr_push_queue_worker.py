"""
HotelRunner Push Queue Worker
==============================
Background worker that retries failed HotelRunner pushes automatically.

When a push fails due to rate limiting (429), the task is queued in MongoDB.
This worker periodically checks the queue and retries pushes when the API recovers.
"""
import asyncio
import logging
from datetime import UTC, datetime

from core.database import db

logger = logging.getLogger(__name__)

QUEUE_CHECK_INTERVAL = 120  # seconds between queue checks
INTER_PUSH_DELAY = 3.0     # seconds between individual pushes
MAX_QUEUE_RETRIES = 10      # max retries before marking as permanently failed


async def enqueue_failed_push(
    tenant_id: str,
    room_type_code: str,
    start_date: str,
    end_date: str,
    *,
    rate=None,
    avail=None,
    stop=None,
    minstay=None,
    error: str = "",
) -> str:
    """Add a failed push task to the retry queue. Returns the queue item id."""
    now = datetime.now(UTC).isoformat()

    # Check for existing pending task with same parameters — merge instead of duplicate
    existing = await db.hr_push_queue.find_one({
        "tenant_id": tenant_id,
        "room_type_code": room_type_code,
        "start_date": start_date,
        "end_date": end_date,
        "status": "pending",
    }, {"_id": 0, "id": 1})

    if existing:
        # Update values on the existing queued task
        update_fields = {"updated_at": now}
        if rate is not None:
            update_fields["rate"] = rate
        if avail is not None:
            update_fields["avail"] = avail
        if stop is not None:
            update_fields["stop"] = stop
        if minstay is not None:
            update_fields["minstay"] = minstay
        await db.hr_push_queue.update_one(
            {"id": existing["id"]},
            {"$set": update_fields},
        )
        logger.info("[HR-QUEUE] Merged into existing queue item %s for %s", existing["id"], room_type_code)
        return existing["id"]

    import uuid
    item_id = str(uuid.uuid4())[:12]
    doc = {
        "id": item_id,
        "tenant_id": tenant_id,
        "room_type_code": room_type_code,
        "start_date": start_date,
        "end_date": end_date,
        "rate": rate,
        "avail": avail,
        "stop": stop,
        "minstay": minstay,
        "status": "pending",
        "retry_count": 0,
        "last_error": error,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
    }
    await db.hr_push_queue.insert_one(doc)
    logger.info("[HR-QUEUE] Enqueued push for %s (%s to %s) — id=%s", room_type_code, start_date, end_date, item_id)
    return item_id


async def get_queue_status(tenant_id: str) -> dict:
    """Get queue statistics for a tenant."""
    pending = await db.hr_push_queue.count_documents({"tenant_id": tenant_id, "status": "pending"})
    retrying = await db.hr_push_queue.count_documents({"tenant_id": tenant_id, "status": "retrying"})
    completed = await db.hr_push_queue.count_documents({"tenant_id": tenant_id, "status": "completed"})
    failed = await db.hr_push_queue.count_documents({"tenant_id": tenant_id, "status": "failed"})

    # Get last successful push time
    last_success = await db.hr_push_queue.find_one(
        {"tenant_id": tenant_id, "status": "completed"},
        {"_id": 0, "completed_at": 1},
        sort=[("completed_at", -1)],
    )

    # Get pending items details
    pending_items = await db.hr_push_queue.find(
        {"tenant_id": tenant_id, "status": {"$in": ["pending", "retrying"]}},
        {"_id": 0},
    ).sort("created_at", 1).to_list(50)

    return {
        "pending": pending,
        "retrying": retrying,
        "completed": completed,
        "failed": failed,
        "total_in_queue": pending + retrying,
        "last_success_at": last_success.get("completed_at") if last_success else None,
        "pending_items": pending_items,
    }


async def clear_completed(tenant_id: str) -> int:
    """Remove completed items from queue."""
    result = await db.hr_push_queue.delete_many({"tenant_id": tenant_id, "status": "completed"})
    return result.deleted_count


class HRPushQueueWorker:
    """Background worker that processes the push retry queue."""

    def __init__(self):
        self._running = False
        self._task = None
        self._consecutive_rate_limits = 0

    async def start(self, interval_seconds: int = QUEUE_CHECK_INTERVAL):
        if self._running:
            logger.warning("[HR-QUEUE] Worker already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._run_loop(interval_seconds))
        logger.info("[HR-QUEUE] Worker started (check every %ds)", interval_seconds)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
        logger.info("[HR-QUEUE] Worker stopped")

    @property
    def is_running(self) -> bool:
        return self._running

    async def _run_loop(self, interval_seconds: int):
        while self._running:
            try:
                await self._process_queue()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error("[HR-QUEUE] Loop error: %s", e)

            # Adaptive backoff when rate-limited
            if self._consecutive_rate_limits > 0:
                multiplier = min(2 ** self._consecutive_rate_limits, 8)
                wait = interval_seconds * multiplier
                logger.info("[HR-QUEUE] Rate-limit backoff: sleeping %ds (consecutive=%d)", wait, self._consecutive_rate_limits)
                await asyncio.sleep(wait)
            else:
                await asyncio.sleep(interval_seconds)

    async def _process_queue(self):
        """Process all pending items across all tenants."""
        # Find distinct tenants with pending items
        pipeline = [
            {"$match": {"status": {"$in": ["pending", "retrying"]}}},
            {"$group": {"_id": "$tenant_id"}},
        ]
        tenant_groups = await db.hr_push_queue.aggregate(pipeline).to_list(100)

        if not tenant_groups:
            return

        for tg in tenant_groups:
            tenant_id = tg["_id"]
            await self._process_tenant_queue(tenant_id)

    async def _process_tenant_queue(self, tenant_id: str):
        """Process pending queue items for a specific tenant."""
        from domains.channel_manager.hr_rate_manager_router import _get_hr_provider
        from domains.channel_manager.providers.hotelrunner.errors import HotelRunnerRateLimitError

        provider, _ = await _get_hr_provider(tenant_id)
        if not provider:
            logger.warning("[HR-QUEUE] No provider for tenant %s — skipping", tenant_id)
            return

        items = await db.hr_push_queue.find(
            {"tenant_id": tenant_id, "status": {"$in": ["pending", "retrying"]}},
            {"_id": 0},
        ).sort("created_at", 1).to_list(20)

        if not items:
            return

        logger.info("[HR-QUEUE] Processing %d items for tenant %s", len(items), tenant_id)

        # Test connectivity with first item before processing all
        success_count = 0
        for item in items:
            now = datetime.now(UTC).isoformat()

            # Mark as retrying
            await db.hr_push_queue.update_one(
                {"id": item["id"]},
                {"$set": {"status": "retrying", "updated_at": now}},
            )

            update_data = {
                "inv_code": item["room_type_code"],
                "start_date": item["start_date"],
                "end_date": item["end_date"],
            }
            if item.get("avail") is not None:
                update_data["availability"] = int(item["avail"])
            if item.get("rate") is not None:
                update_data["price"] = float(item["rate"])
            if item.get("stop") is not None:
                update_data["stop_sale"] = 1 if item["stop"] else 0
            if item.get("minstay") is not None:
                update_data["min_stay"] = int(item["minstay"])

            try:
                result = await provider.update_room(**update_data)
                if result.get("success"):
                    await db.hr_push_queue.update_one(
                        {"id": item["id"]},
                        {"$set": {
                            "status": "completed",
                            "completed_at": now,
                            "updated_at": now,
                        }},
                    )
                    success_count += 1
                    self._consecutive_rate_limits = 0
                    logger.info("[HR-QUEUE] Push OK: %s (%s ~ %s)", item["room_type_code"], item["start_date"], item["end_date"])
                else:
                    retry_count = item.get("retry_count", 0) + 1
                    new_status = "failed" if retry_count >= MAX_QUEUE_RETRIES else "pending"
                    await db.hr_push_queue.update_one(
                        {"id": item["id"]},
                        {"$set": {
                            "status": new_status,
                            "retry_count": retry_count,
                            "last_error": result.get("error", "Unknown error"),
                            "updated_at": now,
                        }},
                    )
                    logger.warning("[HR-QUEUE] Push FAILED: %s — %s (retry %d)", item["room_type_code"], result.get("error"), retry_count)

            except HotelRunnerRateLimitError as e:
                # Rate limited — put back to pending and stop processing this tenant
                retry_count = item.get("retry_count", 0) + 1
                await db.hr_push_queue.update_one(
                    {"id": item["id"]},
                    {"$set": {
                        "status": "pending",
                        "retry_count": retry_count,
                        "last_error": f"Rate limit: {e}",
                        "updated_at": now,
                    }},
                )
                self._consecutive_rate_limits += 1
                logger.warning(
                    "[HR-QUEUE] Rate limited on %s — stopping queue processing, will retry later (consecutive=%d)",
                    item["room_type_code"], self._consecutive_rate_limits,
                )
                break  # Stop processing — API is rate-limited

            except Exception as e:
                retry_count = item.get("retry_count", 0) + 1
                new_status = "failed" if retry_count >= MAX_QUEUE_RETRIES else "pending"
                await db.hr_push_queue.update_one(
                    {"id": item["id"]},
                    {"$set": {
                        "status": new_status,
                        "retry_count": retry_count,
                        "last_error": str(e),
                        "updated_at": now,
                    }},
                )
                logger.error("[HR-QUEUE] Error pushing %s: %s", item["room_type_code"], e)

            # Delay between pushes
            await asyncio.sleep(INTER_PUSH_DELAY)

        if success_count > 0:
            logger.info("[HR-QUEUE] Tenant %s: %d/%d pushes successful", tenant_id, success_count, len(items))


# Singleton
push_queue_worker = HRPushQueueWorker()
