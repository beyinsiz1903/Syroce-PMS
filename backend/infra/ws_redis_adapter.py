"""
WebSocket Redis Adapter — Distributed WebSocket broadcasting via Redis Pub/Sub.
Enables multi-instance WebSocket support. Falls back to local broadcast.
"""

import asyncio
import json
import logging
from collections import deque
from datetime import UTC, datetime
from typing import Any

# ``redis.exceptions.TimeoutError`` does NOT inherit from the built-in
# ``TimeoutError`` (its MRO is ``[TimeoutError(redis), RedisError, Exception]``
# where the leftmost ``TimeoutError`` is redis's own class, not Python's).
# We import it explicitly so the idle-pubsub timeout path can catch it
# and downgrade the log level. ImportError is tolerated because some
# minimal redis builds may not expose this submodule.
try:
    from redis.exceptions import TimeoutError as RedisTimeoutError
except Exception:  # pragma: no cover — defensive

    class RedisTimeoutError(Exception):
        """Shim used when redis.exceptions is unavailable."""


logger = logging.getLogger("infra.ws_redis_adapter")


class WebSocketRedisAdapter:
    """Bridges WebSocket server with Redis Pub/Sub for multi-instance broadcast."""

    CHANNEL_PREFIX = "ws:broadcast:"

    def __init__(self):
        self._redis = None
        self._pubsub = None
        self._subscribed_channels: set[str] = set()
        # Reference counts per channel so that dynamic, per-user/per-tenant
        # rooms (e.g. ``internal_chat:{tenant}:user:{id}``) only unsubscribe
        # from Redis when the *last* local subscriber leaves.
        self._channel_refcounts: dict[str, int] = {}
        self._sub_lock: asyncio.Lock | None = None
        self._listener_task: asyncio.Task | None = None
        self._local_handler = None
        self._active = False
        self._instance_id = ""
        self._metrics = {
            "messages_published": 0,
            "messages_received": 0,
            "messages_forwarded": 0,
            "publish_errors": 0,
            "channels_active": 0,
            "last_publish_error": None,
            "last_publish_error_at": None,
            "last_listen_error": None,
            "last_listen_error_at": None,
            "reconnects": 0,
            "reconnect_failures": 0,
        }
        # Backoff bounds (seconds) for pub/sub reconnect attempts. Kept as
        # instance attributes so tests can shrink them and so an operator
        # could tune them without touching the loop.
        self._reconnect_min_backoff: float = 1.0
        self._reconnect_max_backoff: float = 30.0
        # ── Circuit-breaker tunables (see _listen). When the listener
        # exits in <1s ``_breaker_threshold`` times in a row we stop
        # logging WARNINGs and force a ``_breaker_cooldown_s`` sleep
        # before the next reconnect attempt. The breaker auto-resets
        # after ``_breaker_window_s`` so a transient storm cannot
        # permanently silence real outages. Tests can shrink these.
        self._breaker_threshold: int = 5
        self._breaker_cooldown_s: float = 30.0
        self._breaker_window_s: float = 300.0
        # ── Task #47: rolling per-minute snapshots so the System Health
        # dashboard can render a 1-hour trend / sparkline for the bridge.
        # We keep the last ``_snapshot_max`` samples (default 60 → ~1h at
        # 60s cadence) and only record a new sample when at least
        # ``_snapshot_interval_s`` have elapsed since the previous one.
        # The bookkeeping is lazy: every read of ``get_metrics()`` calls
        # ``_record_snapshot_if_due()`` so we don't need a background
        # task. This keeps the adapter dependency-free and makes the
        # behavior trivially testable by patching ``_now``.
        self._snapshot_interval_s: float = 60.0
        self._snapshot_max: int = 60
        self._snapshots: deque[dict[str, Any]] = deque(maxlen=self._snapshot_max)
        self._last_snapshot_at: float | None = None

    async def initialize(self, redis_client, instance_id: str, local_handler=None):
        """Initialize with Redis client and local broadcast handler."""
        self._redis = redis_client
        self._instance_id = instance_id
        self._local_handler = local_handler

        if self._redis:
            try:
                self._pubsub = self._redis.pubsub()
                self._active = True
                logger.info(f"WS Redis adapter initialized (instance={instance_id})")
            except Exception as e:
                logger.warning(f"WS Redis adapter init failed: {e}")
                self._active = False
        else:
            logger.info("WS Redis adapter: no Redis, using local-only mode")

    def _get_lock(self) -> asyncio.Lock:
        """Lazily create the subscription lock on the running event loop.

        The adapter is a module-level singleton instantiated at import time
        (no loop yet). Creating the lock on first use binds it to the loop
        actually running the server.
        """
        if self._sub_lock is None:
            self._sub_lock = asyncio.Lock()
        return self._sub_lock

    async def subscribe(self, room: str):
        """Subscribe to a room's broadcast channel.

        Reference-counted: subsequent ``subscribe`` calls for the same room
        only bump the local refcount; the underlying Redis ``SUBSCRIBE`` is
        issued exactly once per channel until the matching number of
        :meth:`unsubscribe` calls have been made. This makes the API safe
        to call from per-connection enrolment for dynamic rooms like
        ``internal_chat:{tenant}:user:{id}``.

        The channel is recorded in ``_subscribed_channels`` *before* the
        Redis call so that a concurrent pub/sub reconnect (which briefly
        clears ``self._pubsub``) cannot lose the new subscription — the
        reconnect snapshot will simply include it on the next attempt.
        """
        channel = f"{self.CHANNEL_PREFIX}{room}"
        if not self._active:
            return
        async with self._get_lock():
            if channel in self._subscribed_channels:
                self._channel_refcounts[channel] = self._channel_refcounts.get(channel, 0) + 1
                return
            # Record first; reconnect uses _subscribed_channels as the
            # source of truth when rebuilding the pub/sub connection.
            self._subscribed_channels.add(channel)
            self._channel_refcounts[channel] = 1
            self._metrics["channels_active"] = len(self._subscribed_channels)
            if self._pubsub is not None:
                try:
                    await self._pubsub.subscribe(channel)
                except Exception as e:
                    # Connection probably dropping; leave the channel
                    # tracked so the next successful reconnect picks it up.
                    logger.error(f"WS subscribe error ({room}): {e}")
            if not self._listener_task or self._listener_task.done():
                self._listener_task = asyncio.create_task(self._listen())

    async def unsubscribe(self, room: str):
        """Decrement the local refcount for ``room`` and, when it reaches
        zero, issue ``UNSUBSCRIBE`` to Redis.

        No-op when Redis is not active or the room was never subscribed.
        Local bookkeeping always runs under the lock so it stays
        consistent with any concurrent pub/sub reconnect.
        """
        channel = f"{self.CHANNEL_PREFIX}{room}"
        if not self._active:
            return
        async with self._get_lock():
            count = self._channel_refcounts.get(channel, 0)
            if count <= 0:
                return
            count -= 1
            if count > 0:
                self._channel_refcounts[channel] = count
                return
            # Last subscriber gone — drop the Redis subscription.
            self._channel_refcounts.pop(channel, None)
            self._subscribed_channels.discard(channel)
            self._metrics["channels_active"] = len(self._subscribed_channels)
            if self._pubsub is not None:
                try:
                    await self._pubsub.unsubscribe(channel)
                except Exception as e:
                    logger.error(f"WS unsubscribe error ({room}): {e}")

    async def publish(self, room: str, event: str, data: dict[str, Any]):
        """Publish event to all instances via Redis.

        Always delivers to this instance's local clients first (so the
        publishing instance never depends on Redis loopback), then bridges
        the same event to other instances through Redis pub/sub. The
        listener on the receiving side filters by ``source_instance`` to
        avoid double-delivery on the publishing instance.
        """
        # 1) Local fan-out for clients connected to this instance.
        if self._local_handler:
            try:
                await self._local_handler(room, event, data)
            except Exception as e:
                logger.error(f"WS local handler error ({room}): {e}")

        # 2) Cross-instance fan-out via Redis pub/sub (best-effort).
        await self.publish_remote_only(room, event, data)

    async def publish_remote_only(self, room: str, event: str, data: dict[str, Any]) -> None:
        """Publish ONLY to other instances via Redis pub/sub — skip the
        local-handler invocation that :meth:`publish` performs.

        Useful for callers that have already done their own local
        fan-out and only need cross-instance delivery (e.g. the
        room-service order stream which broadcasts directly to its own
        FastAPI WebSockets so it can return an accurate per-socket
        delivery count). Best-effort: when Redis is inactive this is a
        no-op, exactly mirroring the cross-instance branch of
        :meth:`publish`.
        """
        if not (self._active and self._redis):
            return
        try:
            channel = f"{self.CHANNEL_PREFIX}{room}"
            message = json.dumps(
                {
                    "room": room,
                    "event": event,
                    "data": data,
                    "source_instance": self._instance_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                }
            )
            await self._redis.publish(channel, message)
            self._metrics["messages_published"] += 1
        except Exception as e:
            self._metrics["publish_errors"] += 1
            self._metrics["last_publish_error"] = f"{type(e).__name__}: {str(e)[:200]}"
            self._metrics["last_publish_error_at"] = datetime.now(UTC).isoformat()
            logger.error(f"WS publish error ({room}): {e}")

    async def _listen(self):
        """Listen for messages from other instances.

        Auto-reconnects: if the Redis pub/sub connection drops (network
        blip, Redis restart, failover) the listener rebuilds ``pubsub``
        from the underlying Redis client and re-issues ``SUBSCRIBE`` for
        every channel still tracked in ``_subscribed_channels`` — local
        refcounts are preserved so currently connected users stay
        enrolled. Failed reconnect attempts use exponential backoff.

        The same loopback guard (``source_instance`` check) applies to
        messages received after reconnect, so a transient drop cannot
        cause double-delivery.
        """
        backoff = self._reconnect_min_backoff
        # ── Circuit breaker: prevent log/CPU spam when listen() returns
        # immediately in a tight loop (e.g. no channels subscribed yet,
        # or the broker keeps closing the subscription cleanly). After
        # ``_breaker_threshold`` consecutive fast exits we suppress
        # WARNINGs (logger.debug instead) and force a longer cool-down
        # sleep until either a real message arrives or _breaker_window_s
        # elapses, then reset the counter.
        breaker_count = 0
        breaker_suppressed_logged = False
        loop = asyncio.get_event_loop()
        last_reset = loop.time()
        while self._active:
            cycle_start = loop.time()
            pubsub = self._pubsub
            saw_message = False
            exit_reason = "clean"  # clean | idle | error
            if pubsub is not None:
                try:
                    async for message in pubsub.listen():
                        if message["type"] != "message":
                            continue
                        saw_message = True
                        try:
                            payload = json.loads(message["data"])
                            # Skip own messages
                            if payload.get("source_instance") == self._instance_id:
                                continue
                            self._metrics["messages_received"] += 1
                            # Forward to local websocket clients
                            if self._local_handler:
                                await self._local_handler(payload["room"], payload["event"], payload["data"])
                                self._metrics["messages_forwarded"] += 1
                        except Exception as e:
                            self._metrics["last_listen_error"] = f"{type(e).__name__}: {str(e)[:200]}"
                            self._metrics["last_listen_error_at"] = datetime.now(UTC).isoformat()
                            logger.error(f"WS message parse error: {e}")
                    # listen() returned without raising → server closed
                    # the subscription cleanly. Treat as a transient
                    # drop and rebuild so bridged events keep flowing.
                    if breaker_count < self._breaker_threshold:
                        logger.warning("WS pubsub listener exited; attempting reconnect")
                except asyncio.CancelledError:
                    return
                except (TimeoutError, RedisTimeoutError) as e:
                    # Pub/sub idle socket timeout (default redis socket_timeout
                    # ~30s). No message arrived in the read window — this is
                    # normal for low-traffic channels, NOT an error. Quiet
                    # reconnect keeps the listener alive without log spam.
                    self._metrics["last_listen_error"] = f"IdleTimeout: {str(e)[:120]}"
                    self._metrics["last_listen_error_at"] = datetime.now(UTC).isoformat()
                    logger.debug("WS pubsub idle timeout; reconnecting")
                    exit_reason = "idle"
                except Exception as e:
                    self._metrics["last_listen_error"] = f"{type(e).__name__}: {str(e)[:200]}"
                    self._metrics["last_listen_error_at"] = datetime.now(UTC).isoformat()
                    exit_reason = "error"
                    # Genuine connection failure (network blip, Redis restart)
                    # — WARNING the first few times, then suppress to debug
                    # so a stuck remote endpoint cannot flood the log.
                    if breaker_count < self._breaker_threshold:
                        logger.warning(f"WS pubsub listener error: {e}; attempting reconnect")
                    else:
                        logger.debug(f"WS pubsub listener error (suppressed): {e}")
            # else: previous reconnect attempt cleared _pubsub but
            # failed to rebuild it — fall through and keep retrying so
            # we don't permanently drop into local-only mode.

            if not self._active or self._redis is None:
                return

            # Circuit-breaker bookkeeping. A "fast exit" is any cycle that
            # finished in < 1s without forwarding a real message — that's
            # what creates the log/CPU spam. Real traffic or genuine idle
            # (>=1s) resets the counter.
            now = loop.time()
            cycle_dur = now - cycle_start
            if saw_message or cycle_dur >= 1.0:
                breaker_count = 0
                breaker_suppressed_logged = False
                last_reset = now
            else:
                breaker_count += 1
                if breaker_count == self._breaker_threshold and not breaker_suppressed_logged:
                    logger.warning(
                        f"WS pubsub: {breaker_count} fast reconnects in a row "
                        f"(reason={exit_reason}); suppressing further warnings "
                        f"and applying {self._breaker_cooldown_s:.0f}s cool-down. "
                        f"Check Redis connectivity if this persists."
                    )
                    breaker_suppressed_logged = True
                # Auto-reset the breaker after a window so a transient
                # storm doesn't permanently silence real outages.
                if (now - last_reset) >= self._breaker_window_s:
                    breaker_count = 0
                    breaker_suppressed_logged = False
                    last_reset = now

            if await self._reconnect_pubsub():
                backoff = self._reconnect_min_backoff
            else:
                self._metrics["reconnect_failures"] += 1
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    return
                backoff = min(backoff * 2, self._reconnect_max_backoff)

            # When tripped, force a long cool-down regardless of
            # reconnect outcome so we cannot busy-loop.
            if breaker_count >= self._breaker_threshold:
                try:
                    await asyncio.sleep(self._breaker_cooldown_s)
                except asyncio.CancelledError:
                    return

    async def _reconnect_pubsub(self) -> bool:
        """Rebuild the pub/sub connection and re-subscribe to every
        channel currently tracked in ``_subscribed_channels``.

        Local subscriber refcounts (``_channel_refcounts``) are
        intentionally preserved — connected users never went away, only
        the upstream Redis link did. Returns ``True`` on success.
        """
        if self._redis is None:
            return False
        try:
            async with self._get_lock():
                old = self._pubsub
                self._pubsub = None
                if old is not None:
                    try:
                        await old.close()
                    except Exception:
                        pass

                new_pubsub = self._redis.pubsub()
                # Snapshot channels under lock so concurrent
                # subscribe/unsubscribe calls can't race the rebuild.
                channels = list(self._subscribed_channels)
                for channel in channels:
                    await new_pubsub.subscribe(channel)
                self._pubsub = new_pubsub
                self._metrics["reconnects"] += 1
                # Idle-timeout reconnects are routine (every ~socket_timeout
                # seconds for low-traffic channels). Surface them at DEBUG
                # to avoid log spam; operators can still see them via
                # ``get_metrics()['reconnects']``.
                logger.debug(f"WS pubsub reconnected; re-subscribed to {len(channels)} channel(s)")
                return True
        except Exception as e:
            logger.warning(f"WS pubsub reconnect failed: {e}")
            return False

    async def close(self):
        """Close adapter and cleanup."""
        if self._listener_task:
            self._listener_task.cancel()
        if self._pubsub:
            try:
                await self._pubsub.unsubscribe()
                await self._pubsub.close()
            except Exception:
                pass
        self._subscribed_channels.clear()
        self._channel_refcounts.clear()
        self._metrics["channels_active"] = 0
        self._active = False

    def _now(self) -> datetime:
        """Indirection seam so tests can freeze time deterministically."""
        return datetime.now(UTC)

    def _record_snapshot_if_due(self) -> None:
        """Append a new rolling snapshot when the cadence has elapsed.

        Called lazily from ``get_metrics``/``get_metrics_history`` so we
        don't need a background task. Callers that read metrics very
        rarely will simply have a sparser series — that's an acceptable
        trade-off because the dashboard endpoint polls these values on a
        regular interval anyway.
        """
        now = self._now()
        now_ts = now.timestamp()
        if self._last_snapshot_at is not None and (now_ts - self._last_snapshot_at) < self._snapshot_interval_s:
            return
        self._last_snapshot_at = now_ts
        self._snapshots.append(
            {
                "at": now.isoformat(),
                "publish_errors": int(self._metrics.get("publish_errors") or 0),
                "messages_published": int(self._metrics.get("messages_published") or 0),
                "messages_received": int(self._metrics.get("messages_received") or 0),
                "messages_forwarded": int(self._metrics.get("messages_forwarded") or 0),
                "reconnects": int(self._metrics.get("reconnects") or 0),
            }
        )

    def get_metrics_history(self) -> list[dict[str, Any]]:
        """Return a copy of the rolling snapshot buffer (oldest → newest).

        Each entry contains the cumulative counter values at the sample
        time. The dashboard converts adjacent samples to per-interval
        deltas to render the trend.
        """
        self._record_snapshot_if_due()
        return list(self._snapshots)

    def get_metrics(self) -> dict[str, Any]:
        # Always advance the rolling buffer on read so the dashboard sees
        # an up-to-date series even before the first dedicated history
        # call lands.
        self._record_snapshot_if_due()
        return {
            **self._metrics,
            "active": self._active,
            "instance_id": self._instance_id,
            "subscribed_channels": list(self._subscribed_channels),
        }


# Singleton
ws_redis_adapter = WebSocketRedisAdapter()
