"""
WebSocket Redis Adapter — Distributed WebSocket broadcasting via Redis Pub/Sub.
Enables multi-instance WebSocket support. Falls back to local broadcast.
"""
import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

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
                self._channel_refcounts[channel] = (
                    self._channel_refcounts.get(channel, 0) + 1
                )
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
        if self._active and self._redis:
            try:
                channel = f"{self.CHANNEL_PREFIX}{room}"
                message = json.dumps({
                    "room": room,
                    "event": event,
                    "data": data,
                    "source_instance": self._instance_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                })
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
        while self._active:
            pubsub = self._pubsub
            if pubsub is not None:
                try:
                    async for message in pubsub.listen():
                        if message["type"] != "message":
                            continue
                        try:
                            payload = json.loads(message["data"])
                            # Skip own messages
                            if payload.get("source_instance") == self._instance_id:
                                continue
                            self._metrics["messages_received"] += 1
                            # Forward to local websocket clients
                            if self._local_handler:
                                await self._local_handler(
                                    payload["room"], payload["event"], payload["data"]
                                )
                                self._metrics["messages_forwarded"] += 1
                        except Exception as e:
                            self._metrics["last_listen_error"] = (
                                f"{type(e).__name__}: {str(e)[:200]}"
                            )
                            self._metrics["last_listen_error_at"] = (
                                datetime.now(UTC).isoformat()
                            )
                            logger.error(f"WS message parse error: {e}")
                    # listen() returned without raising → server closed
                    # the subscription cleanly. Treat as a transient
                    # drop and rebuild so bridged events keep flowing.
                    logger.warning(
                        "WS pubsub listener exited; attempting reconnect"
                    )
                except asyncio.CancelledError:
                    return
                except Exception as e:
                    self._metrics["last_listen_error"] = (
                        f"{type(e).__name__}: {str(e)[:200]}"
                    )
                    self._metrics["last_listen_error_at"] = (
                        datetime.now(UTC).isoformat()
                    )
                    logger.warning(
                        f"WS pubsub listener error: {e}; attempting reconnect"
                    )
            # else: previous reconnect attempt cleared _pubsub but
            # failed to rebuild it — fall through and keep retrying so
            # we don't permanently drop into local-only mode.

            if not self._active or self._redis is None:
                return

            if await self._reconnect_pubsub():
                backoff = self._reconnect_min_backoff
            else:
                self._metrics["reconnect_failures"] += 1
                try:
                    await asyncio.sleep(backoff)
                except asyncio.CancelledError:
                    return
                backoff = min(backoff * 2, self._reconnect_max_backoff)

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
                logger.info(
                    "WS pubsub reconnected; re-subscribed to "
                    f"{len(channels)} channel(s)"
                )
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

    def get_metrics(self) -> dict[str, Any]:
        return {
            **self._metrics,
            "active": self._active,
            "instance_id": self._instance_id,
            "subscribed_channels": list(self._subscribed_channels),
        }


# Singleton
ws_redis_adapter = WebSocketRedisAdapter()
