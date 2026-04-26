"""
KBS Queue SSE bridge — multi-worker safe Server-Sent Events fan-out
for the KBS notification queue.

Why this exists
---------------
The KBS desktop agent app subscribes to ``GET /api/kbs/queue/stream``
to receive ``job.available`` events the instant a notification is
enqueued (instead of polling ``GET /queue`` every few seconds). In a
multi-worker uvicorn deploy the SSE connection lands on whichever
worker the load balancer picks; the *enqueue* might happen on a
different worker. Without a cross-worker bridge, the agent on W1
would never see jobs created on W2.

Design
------
- Each worker keeps a per-process registry of local SSE subscribers
  (``asyncio.Queue`` per connection, scoped by ``tenant_id``).
- Every ``publish_*`` call:
    1) Pushes the event to local subscribers immediately.
    2) Best-effort publishes the event to a Redis channel so other
       workers can fan it out to *their* local subscribers.
- The Redis listener filters by ``source_instance`` to avoid
  duplicating events on the publishing worker (we already pushed
  locally in step 1).

Event shape (kept small — full job is fetched by the agent via the
existing ``GET /queue`` / ``POST /queue/{id}/claim`` endpoints):

    {
      "type": "job.available" | "job.completed" | "job.failed",
      "tenant_id": "<uuid>",
      "job_id": "<uuid>",
      "booking_id": "<uuid>",
      "action": "checkin" | "checkout",
      "ts": "<iso8601>",
      "instance": "<source_worker_id>"   # added by publisher
    }

Failure mode: a Redis outage degrades to "single-worker SSE", not
broken SSE. Local subscribers continue to receive events from
publishers on the same worker.
"""
import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

try:
    from redis.exceptions import TimeoutError as RedisTimeoutError
except Exception:  # pragma: no cover
    class RedisTimeoutError(Exception):
        """Shim used when redis.exceptions is unavailable."""


logger = logging.getLogger("infra.kbs_queue_pubsub")

CHANNEL = "kbs:queue:events"


class KBSQueuePubSub:
    """Singleton SSE event bridge for the KBS notification queue."""

    def __init__(self):
        self._redis = None
        self._pubsub = None
        self._instance_id = ""
        self._active = False
        self._listener_task: asyncio.Task | None = None
        self._reconnect_min_backoff: float = 1.0
        self._reconnect_max_backoff: float = 30.0
        # Per-tenant local subscriber registry. Each entry is a set of
        # ``asyncio.Queue`` objects owned by an active SSE connection.
        # Lookup is O(1) by tenant; we never iterate the global table.
        self._subscribers: dict[str, set[asyncio.Queue]] = {}
        self._sub_lock: asyncio.Lock | None = None
        self._metrics = {
            "events_published_local": 0,
            "events_published_redis": 0,
            "events_received_redis": 0,
            "events_delivered": 0,
            "publish_errors": 0,
            "listen_errors": 0,
            "reconnects": 0,
            "subscribers_total": 0,
            "last_publish_error": None,
            "last_publish_error_at": None,
            "last_listen_error": None,
            "last_listen_error_at": None,
        }
        # Throttle for Redis publish-error WARNINGs: log the first error
        # immediately, then at most one summary line every 30 s while the
        # condition persists. This keeps a chronic Redis outage visible
        # without flooding the log stream during high-throughput periods.
        self._last_publish_warn_at: datetime | None = None
        self._suppressed_publish_warns: int = 0
        self._publish_warn_interval_s: float = 30.0

    def _get_lock(self) -> asyncio.Lock:
        if self._sub_lock is None:
            self._sub_lock = asyncio.Lock()
        return self._sub_lock

    async def initialize(self, redis_client, instance_id: str) -> None:
        """Idempotent: tears down any prior listener / pubsub before
        re-binding (so re-init on Redis reconnect doesn't leak)."""
        self._instance_id = instance_id or "unknown"

        self._active = False
        prev_task = self._listener_task
        self._listener_task = None
        if prev_task is not None and not prev_task.done():
            prev_task.cancel()
            try:
                await prev_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._pubsub is not None:
            try:
                await self._pubsub.close()
            except Exception:
                pass
            self._pubsub = None

        if redis_client is None:
            self._redis = None
            logger.info(
                "KBS queue pub/sub: no Redis client, local-only mode"
            )
            return

        self._redis = redis_client
        try:
            self._pubsub = self._redis.pubsub()
            await self._pubsub.subscribe(CHANNEL)
            self._active = True
            self._listener_task = asyncio.create_task(self._listen())
            logger.info(
                f"KBS queue pub/sub initialized (instance={instance_id})"
            )
        except Exception as e:
            logger.warning(f"KBS queue pub/sub init failed: {e}")
            self._active = False

    # ── Local subscriber API (called by the SSE endpoint) ──────────

    async def add_subscriber(self, tenant_id: str) -> asyncio.Queue:
        """Register a local SSE connection for ``tenant_id`` and return
        the queue it should ``await`` on."""
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        async with self._get_lock():
            self._subscribers.setdefault(tenant_id, set()).add(q)
            self._metrics["subscribers_total"] = sum(
                len(s) for s in self._subscribers.values()
            )
        return q

    async def remove_subscriber(
        self, tenant_id: str, q: asyncio.Queue
    ) -> None:
        """Unregister a closed SSE connection."""
        async with self._get_lock():
            bucket = self._subscribers.get(tenant_id)
            if bucket is not None:
                bucket.discard(q)
                if not bucket:
                    self._subscribers.pop(tenant_id, None)
            self._metrics["subscribers_total"] = sum(
                len(s) for s in self._subscribers.values()
            )

    async def _fanout_local(self, tenant_id: str, event: dict) -> None:
        """Push ``event`` to every local subscriber for ``tenant_id``.

        Slow / disconnected consumers don't block the rest: a full
        queue (256 buffered events) drops the new event for that one
        client and increments a metric. The SSE endpoint also has its
        own 25 s heartbeat that closes truly dead sockets.
        """
        # Snapshot under the lock so concurrent (un)subscribe doesn't
        # race the iteration.
        async with self._get_lock():
            bucket = list(self._subscribers.get(tenant_id, ()))
        for q in bucket:
            try:
                q.put_nowait(event)
                self._metrics["events_delivered"] += 1
            except asyncio.QueueFull:
                # Drop on the floor — agent will pick up the missed
                # job on its next polling reconciliation. Logged so
                # ops can detect a chronically slow consumer.
                logger.warning(
                    "KBS SSE subscriber queue full for tenant %s — "
                    "dropping event",
                    tenant_id,
                )

    # ── Publisher API (called from queue mutation handlers) ────────

    async def publish(
        self,
        event_type: str,
        tenant_id: str,
        *,
        job_id: str,
        booking_id: str,
        action: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        """Emit a queue lifecycle event.

        Fans out to local subscribers first (so the publishing worker
        never depends on Redis loopback) then best-effort to Redis so
        other workers' subscribers also receive it.

        ``extra`` is merged into the published payload at the top
        level. Used for event-type-specific fields (e.g. the
        ``next_retry_at`` ISO timestamp on ``job.retry_scheduled``)
        without forcing every event to carry every optional field.
        Reserved keys (``type``, ``tenant_id``, ``job_id``,
        ``booking_id``, ``action``, ``ts``, ``instance``) cannot be
        overridden.
        """
        event = {
            "type": event_type,
            "tenant_id": tenant_id,
            "job_id": job_id,
            "booking_id": booking_id,
            "action": action,
            "ts": datetime.now(UTC).isoformat(),
            "instance": self._instance_id,
        }
        if extra:
            for k, v in extra.items():
                if k in event:
                    # Reserved field — don't allow caller to spoof
                    # core envelope fields.
                    continue
                event[k] = v
        # 1) Local fanout (synchronous, no I/O).
        try:
            await self._fanout_local(tenant_id, event)
            self._metrics["events_published_local"] += 1
        except Exception as e:
            logger.warning(f"KBS SSE local fanout error: {e}")

        # 2) Cross-worker fanout (best-effort).
        if self._active and self._redis is not None:
            try:
                await self._redis.publish(CHANNEL, json.dumps(event))
                self._metrics["events_published_redis"] += 1
            except Exception as e:
                self._metrics["publish_errors"] += 1
                self._metrics["last_publish_error"] = (
                    f"{type(e).__name__}: {str(e)[:200]}"
                )
                self._metrics["last_publish_error_at"] = (
                    datetime.now(UTC).isoformat()
                )
                # WARNING (not DEBUG) — a cross-worker publish failure
                # silently degrades the SSE bridge to single-worker
                # delivery and operators must see it. But we throttle
                # to "first error immediately, then ≤1 summary every
                # 30 s" so a Redis outage during high-throughput
                # publishing doesn't spam the log pipeline.
                #
                # Window semantics: ``suppressed`` counts errors
                # observed strictly between the previous warning line
                # and this one — it's accurate regardless of how long
                # the gap was. We say "since last warning" instead of
                # "in last 30s" to avoid mis-implying a fixed window.
                now = datetime.now(UTC)
                last = self._last_publish_warn_at
                interval_elapsed = (
                    last is None
                    or (now - last).total_seconds()
                    >= self._publish_warn_interval_s
                )
                if interval_elapsed:
                    suppressed = self._suppressed_publish_warns
                    suffix = (
                        f" (+{suppressed} similar suppressed since last warning)"
                        if suppressed
                        else ""
                    )
                    logger.warning(
                        f"KBS SSE Redis publish error "
                        f"(total={self._metrics['publish_errors']}): "
                        f"{e}{suffix}"
                    )
                    self._last_publish_warn_at = now
                    self._suppressed_publish_warns = 0
                else:
                    self._suppressed_publish_warns += 1

    # ── Background listener ────────────────────────────────────────

    async def _listen(self) -> None:
        backoff = self._reconnect_min_backoff
        while self._active:
            pubsub = self._pubsub
            if pubsub is not None:
                try:
                    async for message in pubsub.listen():
                        if message.get("type") != "message":
                            continue
                        await self._handle_message(message)
                    logger.warning(
                        "KBS SSE pubsub listener exited; reconnecting"
                    )
                except asyncio.CancelledError:
                    return
                except (TimeoutError, RedisTimeoutError) as e:
                    self._metrics["last_listen_error"] = (
                        f"IdleTimeout: {str(e)[:120]}"
                    )
                    self._metrics["last_listen_error_at"] = (
                        datetime.now(UTC).isoformat()
                    )
                    logger.debug(
                        "KBS SSE pubsub idle timeout; reconnecting"
                    )
                except Exception as e:
                    self._metrics["listen_errors"] += 1
                    self._metrics["last_listen_error"] = (
                        f"{type(e).__name__}: {str(e)[:200]}"
                    )
                    self._metrics["last_listen_error_at"] = (
                        datetime.now(UTC).isoformat()
                    )
                    logger.warning(
                        f"KBS SSE pubsub listener error: {e}; reconnecting"
                    )

            if not self._active or self._redis is None:
                return
            if await self._reconnect():
                backoff = self._reconnect_min_backoff
            else:
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    return
                backoff = min(backoff * 2, self._reconnect_max_backoff)

    async def _handle_message(self, message: dict[str, Any]) -> None:
        try:
            data = message.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="replace")
            event = json.loads(data) if isinstance(data, str) else {}
            # Loop guard: this worker already fanned out the event
            # locally during its own publish() call.
            if event.get("instance") == self._instance_id:
                return
            tenant_id = event.get("tenant_id")
            if not tenant_id:
                return
            self._metrics["events_received_redis"] += 1
            await self._fanout_local(tenant_id, event)
        except Exception as e:
            self._metrics["listen_errors"] += 1
            self._metrics["last_listen_error"] = (
                f"handle: {type(e).__name__}: {str(e)[:200]}"
            )
            self._metrics["last_listen_error_at"] = (
                datetime.now(UTC).isoformat()
            )
            logger.warning(f"KBS SSE handle error: {e}")

    async def _reconnect(self) -> bool:
        if self._redis is None:
            return False
        try:
            old = self._pubsub
            self._pubsub = None
            if old is not None:
                try:
                    await old.close()
                except Exception:
                    pass
            new_pubsub = self._redis.pubsub()
            await new_pubsub.subscribe(CHANNEL)
            self._pubsub = new_pubsub
            self._metrics["reconnects"] += 1
            logger.debug("KBS SSE pubsub reconnected")
            return True
        except Exception as e:
            logger.warning(f"KBS SSE pubsub reconnect failed: {e}")
            return False

    async def close(self) -> None:
        self._active = False
        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except (asyncio.CancelledError, Exception):
                pass
        self._listener_task = None
        if self._pubsub is not None:
            try:
                await self._pubsub.unsubscribe()
                await self._pubsub.close()
            except Exception:
                pass
            self._pubsub = None
        # Drop subscriber refs so connections can GC. The SSE
        # generators will see EOF on their queues' next get() once
        # the asyncio task is cancelled by the framework.
        self._subscribers.clear()

    def get_metrics(self) -> dict[str, Any]:
        return {
            **self._metrics,
            "active": self._active,
            "instance_id": self._instance_id,
            "tenants_with_subscribers": len(self._subscribers),
        }


# Singleton
kbs_queue_pubsub = KBSQueuePubSub()
