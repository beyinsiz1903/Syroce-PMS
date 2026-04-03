"""
HotelRunner Push Queue Worker
==============================
Background worker that retries failed HotelRunner pushes automatically.

When a push fails due to rate limiting (429), the task is queued in MongoDB.
This worker periodically checks the queue and retries pushes when the API recovers.

Rate limit cooldown: When 429 is received, a cooldown period (based on Retry-After)
is stored. The system waits for cooldown before retrying, and auto-retries when ready.
"""
import asyncio
import logging
import uuid
from datetime import UTC, datetime, timedelta

from core.database import db

logger = logging.getLogger(__name__)

QUEUE_CHECK_INTERVAL = 120  # seconds between queue checks
INTER_PUSH_DELAY = 13.0    # seconds between individual pushes (5 req/min limit → 12s min)
MAX_QUEUE_RETRIES = 10      # max retries before marking as permanently failed
DEFAULT_RATE_LIMIT_COOLDOWN = 65  # seconds — default cooldown when 429 hits (slightly > Retry-After)
MAX_AUTO_RETRIES = 5        # max consecutive auto-retries before stopping

# In-memory cooldown tracker per tenant
_tenant_cooldowns: dict[str, str] = {}  # tenant_id -> ISO datetime when cooldown expires
_auto_retry_tasks: dict[str, asyncio.Task] = {}  # tenant_id -> running auto-retry task
_auto_retry_counts: dict[str, int] = {}  # tenant_id -> consecutive auto-retry count
_batch_push_tasks: dict[str, asyncio.Task] = {}  # tenant_id -> running background batch push


def get_cooldown_remaining(tenant_id: str) -> int:
    """Returns seconds remaining in rate limit cooldown for tenant. 0 = no cooldown."""
    cooldown_until = _tenant_cooldowns.get(tenant_id)
    if not cooldown_until:
        return 0
    try:
        until_dt = datetime.fromisoformat(cooldown_until)
        remaining = (until_dt - datetime.now(UTC)).total_seconds()
        return max(0, int(remaining))
    except (ValueError, TypeError):
        return 0


def set_cooldown(tenant_id: str, seconds: int):
    """Set rate limit cooldown for a tenant."""
    until = datetime.now(UTC) + timedelta(seconds=seconds)
    _tenant_cooldowns[tenant_id] = until.isoformat()
    logger.info("[HR-QUEUE] Cooldown set for tenant %s: %ds (until %s)", tenant_id, seconds, until.isoformat())


def clear_cooldown(tenant_id: str):
    """Clear rate limit cooldown for a tenant (does NOT reset auto-retry counter)."""
    _tenant_cooldowns.pop(tenant_id, None)


def reset_auto_retry(tenant_id: str):
    """Reset auto-retry counter — call only after successful push."""
    _auto_retry_counts.pop(tenant_id, None)


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
    retry_after_seconds: int = DEFAULT_RATE_LIMIT_COOLDOWN,
) -> str:
    """Add a failed push task to the retry queue. Returns the queue item id."""
    now = datetime.now(UTC).isoformat()
    next_retry_at = (datetime.now(UTC) + timedelta(seconds=retry_after_seconds)).isoformat()

    # Set tenant-level cooldown
    set_cooldown(tenant_id, retry_after_seconds)

    # Check for existing pending task with same parameters — merge instead of duplicate
    existing = await db.hr_push_queue.find_one({
        "tenant_id": tenant_id,
        "room_type_code": room_type_code,
        "start_date": start_date,
        "end_date": end_date,
        "status": "pending",
    }, {"_id": 0, "id": 1})

    if existing:
        update_fields = {"updated_at": now, "next_retry_at": next_retry_at}
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
        "next_retry_at": next_retry_at,
        "created_at": now,
        "updated_at": now,
        "completed_at": None,
    }
    await db.hr_push_queue.insert_one(doc)
    logger.info("[HR-QUEUE] Enqueued push for %s (%s to %s) — id=%s, next_retry_at=%s", room_type_code, start_date, end_date, item_id, next_retry_at)
    return item_id


async def schedule_auto_retry(tenant_id: str, delay_seconds: int):
    """Schedule an automatic retry after the rate limit cooldown expires.
    Uses progressive backoff: delay doubles on each consecutive auto-retry.
    Stops after MAX_AUTO_RETRIES consecutive failures.
    """
    count = _auto_retry_counts.get(tenant_id, 0)
    if count >= MAX_AUTO_RETRIES:
        logger.warning("[HR-QUEUE] Max auto-retries (%d) reached for tenant %s — stopping auto-retry. Manual retry required.", MAX_AUTO_RETRIES, tenant_id)
        _auto_retry_counts[tenant_id] = 0
        return

    # Cancel existing auto-retry task for this tenant
    existing_task = _auto_retry_tasks.get(tenant_id)
    if existing_task and not existing_task.done():
        existing_task.cancel()

    # Progressive backoff: multiply delay by retry count (min 1x, max 4x)
    multiplier = min(1 + count, 4)
    actual_delay = delay_seconds * multiplier
    _auto_retry_counts[tenant_id] = count + 1

    # Update cooldown to match the actual delay
    set_cooldown(tenant_id, actual_delay)

    async def _delayed_retry():
        logger.info("[HR-QUEUE] Auto-retry #%d scheduled for tenant %s in %ds (base=%ds, multiplier=%dx)", count + 1, tenant_id, actual_delay, delay_seconds, multiplier)
        await asyncio.sleep(actual_delay)
        clear_cooldown(tenant_id)
        logger.info("[HR-QUEUE] Auto-retry #%d starting for tenant %s", count + 1, tenant_id)
        await push_queue_worker._process_tenant_queue(tenant_id)
        _auto_retry_tasks.pop(tenant_id, None)

    task = asyncio.create_task(_delayed_retry())
    _auto_retry_tasks[tenant_id] = task



async def start_background_batch_push(tenant_id: str):
    """Start background batch push for all pending queue items.

    Processes items one by one with 13-second delays to respect
    HotelRunner's 5 req/min rate limit. Runs as async background task.
    """
    # Cancel existing batch push for this tenant
    existing = _batch_push_tasks.get(tenant_id)
    if existing and not existing.done():
        logger.info("[HR-BATCH] Batch push already running for tenant %s — merging", tenant_id)
        return  # Let the existing batch handle it

    async def _batch_process():
        logger.info("[HR-BATCH] Background batch push starting for tenant %s", tenant_id)
        # Small delay to let the HTTP response return first
        await asyncio.sleep(1)
        await push_queue_worker._process_tenant_queue(tenant_id)
        _batch_push_tasks.pop(tenant_id, None)
        logger.info("[HR-BATCH] Background batch push completed for tenant %s", tenant_id)

    task = asyncio.create_task(_batch_process())
    _batch_push_tasks[tenant_id] = task


def is_batch_push_running(tenant_id: str) -> bool:
    """Check if a background batch push is currently running for a tenant."""
    task = _batch_push_tasks.get(tenant_id)
    return task is not None and not task.done()

async def get_queue_status(tenant_id: str) -> dict:
    """Get queue statistics for a tenant."""
    pending = await db.hr_push_queue.count_documents({"tenant_id": tenant_id, "status": "pending"})
    retrying = await db.hr_push_queue.count_documents({"tenant_id": tenant_id, "status": "retrying"})
    completed = await db.hr_push_queue.count_documents({"tenant_id": tenant_id, "status": "completed"})
    failed = await db.hr_push_queue.count_documents({"tenant_id": tenant_id, "status": "failed"})

    last_success = await db.hr_push_queue.find_one(
        {"tenant_id": tenant_id, "status": "completed"},
        {"_id": 0, "completed_at": 1},
        sort=[("completed_at", -1)],
    )

    pending_items = await db.hr_push_queue.find(
        {"tenant_id": tenant_id, "status": {"$in": ["pending", "retrying"]}},
        {"_id": 0},
    ).sort("created_at", 1).to_list(50)

    cooldown_remaining = get_cooldown_remaining(tenant_id)
    has_auto_retry = tenant_id in _auto_retry_tasks and not _auto_retry_tasks[tenant_id].done()

    return {
        "pending": pending,
        "retrying": retrying,
        "completed": completed,
        "failed": failed,
        "total_in_queue": pending + retrying,
        "last_success_at": last_success.get("completed_at") if last_success else None,
        "pending_items": pending_items,
        "cooldown_remaining": cooldown_remaining,
        "auto_retry_scheduled": has_auto_retry,
        "auto_retry_count": _auto_retry_counts.get(tenant_id, 0),
        "max_auto_retries": MAX_AUTO_RETRIES,
        "batch_push_active": is_batch_push_running(tenant_id),
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
        pipeline = [
            {"$match": {"status": {"$in": ["pending", "retrying"]}}},
            {"$group": {"_id": "$tenant_id"}},
        ]
        tenant_groups = await db.hr_push_queue.aggregate(pipeline).to_list(100)

        if not tenant_groups:
            return

        for tg in tenant_groups:
            tenant_id = tg["_id"]
            # Skip tenants still in cooldown
            cooldown = get_cooldown_remaining(tenant_id)
            if cooldown > 0:
                logger.info("[HR-QUEUE] Tenant %s still in cooldown (%ds remaining), skipping", tenant_id, cooldown)
                continue
            await self._process_tenant_queue(tenant_id)

    async def _process_tenant_queue(self, tenant_id: str):
        """Process pending queue items for a specific tenant."""
        from domains.channel_manager.hr_rate_manager_router import _get_hr_provider
        from domains.channel_manager.providers.hotelrunner.errors import HotelRunnerRateLimitError

        # Check cooldown before processing
        cooldown = get_cooldown_remaining(tenant_id)
        if cooldown > 0:
            logger.info("[HR-QUEUE] Tenant %s in cooldown (%ds), scheduling auto-retry", tenant_id, cooldown)
            await schedule_auto_retry(tenant_id, cooldown + 2)
            return

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

        success_count = 0
        for item in items:
            now = datetime.now(UTC).isoformat()

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
                    clear_cooldown(tenant_id)
                    reset_auto_retry(tenant_id)
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
                retry_count = item.get("retry_count", 0) + 1
                next_retry = (datetime.now(UTC) + timedelta(seconds=e.retry_after_seconds)).isoformat()
                await db.hr_push_queue.update_one(
                    {"id": item["id"]},
                    {"$set": {
                        "status": "pending",
                        "retry_count": retry_count,
                        "last_error": f"Rate limit: {e}",
                        "next_retry_at": next_retry,
                        "updated_at": now,
                    }},
                )
                self._consecutive_rate_limits += 1
                set_cooldown(tenant_id, e.retry_after_seconds + 5)
                logger.warning(
                    "[HR-QUEUE] Rate limited on %s — cooldown %ds, scheduling auto-retry (consecutive=%d)",
                    item["room_type_code"], e.retry_after_seconds, self._consecutive_rate_limits,
                )
                # Schedule auto-retry after cooldown
                await schedule_auto_retry(tenant_id, e.retry_after_seconds + 5)
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
