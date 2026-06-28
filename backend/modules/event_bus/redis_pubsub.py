"""
Redis Pub/Sub Backend for Event Bus — Production Mode.
Connection manager, health check, reconnect strategy, delivery metrics,
channel cardinality monitoring, backpressure safety, and observability hooks.
"""

import asyncio
import json
import logging
import os
import time
import uuid
from datetime import UTC, datetime
from typing import Callable

logger = logging.getLogger("event_bus.redis")


class RedisConnectionManager:
    """Manages Redis connection lifecycle with reconnect strategy."""

    def __init__(self, redis_url: str, max_retries: int = 10, base_backoff_sec: float = 1.0, max_backoff_sec: float = 30.0):
        self._redis_url = redis_url
        self._redis = None
        self._connected = False
        self._max_retries = max_retries
        self._base_backoff = base_backoff_sec
        self._max_backoff = max_backoff_sec
        self._reconnect_count = 0
        self._last_reconnect_at: str | None = None
        self._connect_lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def redis(self):
        return self._redis

    async def connect(self) -> bool:
        async with self._connect_lock:
            if self._connected and self._redis:
                try:
                    await self._redis.ping()
                    return True
                except Exception:
                    self._connected = False

            try:
                import redis.asyncio as aioredis

                self._redis = aioredis.from_url(
                    self._redis_url,
                    decode_responses=True,
                    socket_connect_timeout=3,
                    socket_timeout=5,
                    retry_on_timeout=True,
                    health_check_interval=30,
                )
                await self._redis.ping()
                self._connected = True
                self._last_reconnect_at = datetime.now(UTC).isoformat()
                logger.info(f"Redis connected: {self._redis_url}")
                return True
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}")
                self._connected = False
                return False

    async def reconnect_with_backoff(self) -> bool:
        for attempt in range(self._max_retries):
            backoff = min(self._base_backoff * (2**attempt), self._max_backoff)
            logger.info(f"Redis reconnect attempt {attempt + 1}/{self._max_retries} in {backoff}s")
            await asyncio.sleep(backoff)
            if await self.connect():
                self._reconnect_count += 1
                return True
        logger.error(f"Redis reconnect failed after {self._max_retries} attempts")
        return False

    async def disconnect(self):
        if self._redis:
            try:
                await self._redis.close()
            except Exception:
                pass
        self._connected = False
        self._redis = None

    def get_status(self) -> dict:
        return {
            "connected": self._connected,
            "reconnect_count": self._reconnect_count,
            "last_reconnect_at": self._last_reconnect_at,
            "redis_url_configured": bool(self._redis_url),
        }


class RedisPubSubBackend:
    """Redis-backed event bus backend for production multi-instance scaling."""

    def __init__(self, redis_url: str):
        self._conn_mgr = RedisConnectionManager(redis_url)
        self._pubsub = None
        self._subscriptions: dict[str, dict] = {}
        self._listener_task: asyncio.Task | None = None

        # Delivery metrics
        self._published = 0
        self._delivered = 0
        self._dropped = 0
        self._errors = 0
        self._publish_latencies: list[float] = []

        # Channel cardinality
        self._channel_message_counts: dict[str, int] = {}

        # Backpressure
        self._max_buffer_size = 10000
        self._buffer_size = 0

    @property
    def connected(self) -> bool:
        return self._conn_mgr.connected

    async def connect(self) -> bool:
        if await self._conn_mgr.connect():
            try:
                self._pubsub = self._conn_mgr.redis.pubsub()
                # Resubscribe to existing channels
                for sub_id, sub_info in self._subscriptions.items():
                    try:
                        await self._pubsub.subscribe(sub_info["channel"])
                    except Exception:
                        pass
                self._start_listener()
                return True
            except Exception as e:
                logger.error(f"PubSub setup failed: {e}")
                return False
        return False

    async def disconnect(self):
        if self._listener_task:
            self._listener_task.cancel()
            try:
                await self._listener_task
            except (asyncio.CancelledError, Exception):
                pass
        if self._pubsub:
            try:
                await self._pubsub.unsubscribe()
                await self._pubsub.close()
            except Exception:
                pass
        await self._conn_mgr.disconnect()

    async def publish(self, channel: str, event) -> bool:
        if not self._conn_mgr.connected or not self._conn_mgr.redis:
            self._dropped += 1
            return False

        # Backpressure check
        if self._buffer_size >= self._max_buffer_size:
            self._dropped += 1
            logger.warning(f"Backpressure: buffer full ({self._buffer_size}), dropping event")
            return False

        start = time.time()
        try:
            data = json.dumps(event.to_dict())
            receivers = await self._conn_mgr.redis.publish(channel, data)
            elapsed_ms = (time.time() - start) * 1000
            self._published += 1
            self._delivered += receivers
            self._publish_latencies.append(elapsed_ms)
            if len(self._publish_latencies) > 1000:
                self._publish_latencies = self._publish_latencies[-500:]
            self._channel_message_counts[channel] = self._channel_message_counts.get(channel, 0) + 1
            return True
        except Exception as e:
            self._errors += 1
            logger.error(f"Redis publish failed: {e}")
            # Trigger reconnect in background
            asyncio.create_task(self._handle_disconnect())
            return False

    async def subscribe(self, channel: str, callback: Callable) -> str:
        sub_id = str(uuid.uuid4())
        self._subscriptions[sub_id] = {"channel": channel, "callback": callback}
        if self._conn_mgr.connected and self._pubsub:
            try:
                await self._pubsub.subscribe(channel)
            except Exception as e:
                logger.error(f"Redis subscribe failed: {e}")
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> bool:
        sub = self._subscriptions.pop(subscription_id, None)
        if sub and self._conn_mgr.connected and self._pubsub:
            try:
                # Only unsubscribe if no other subs on same channel
                channel = sub["channel"]
                other_subs = [s for s in self._subscriptions.values() if s["channel"] == channel]
                if not other_subs:
                    await self._pubsub.unsubscribe(channel)
            except Exception:
                pass
        return sub is not None

    async def health_check(self) -> dict:
        conn_status = self._conn_mgr.get_status()
        base = {
            "backend": "redis",
            "subscriptions": len(self._subscriptions),
            "published": self._published,
            "delivered": self._delivered,
            "dropped": self._dropped,
            "errors": self._errors,
            "channels_active": len(self._channel_message_counts),
            "reconnect_count": conn_status["reconnect_count"],
            "last_reconnect_at": conn_status["last_reconnect_at"],
        }

        if not conn_status["connected"]:
            base["status"] = "disconnected"
            return base

        try:
            await self._conn_mgr.redis.ping()
            info = await self._conn_mgr.redis.info("clients")
            base.update(
                {
                    "status": "healthy",
                    "connected_clients": info.get("connected_clients", 0),
                    "avg_publish_latency_ms": round(sum(self._publish_latencies) / max(len(self._publish_latencies), 1), 2),
                }
            )
            return base
        except Exception as e:
            base["status"] = "error"
            base["error"] = str(e)[:200]
            return base

    def get_delivery_metrics(self) -> dict:
        return {
            "published": self._published,
            "delivered": self._delivered,
            "dropped": self._dropped,
            "errors": self._errors,
            "avg_publish_latency_ms": round(sum(self._publish_latencies) / max(len(self._publish_latencies), 1), 2),
            "channel_cardinality": len(self._channel_message_counts),
            "top_channels": dict(sorted(self._channel_message_counts.items(), key=lambda x: -x[1])[:10]),
        }

    def _start_listener(self):
        if self._listener_task and not self._listener_task.done():
            return
        self._listener_task = asyncio.create_task(self._listen_loop())

    async def _listen_loop(self):
        """Background listener for incoming Redis pub/sub messages."""
        _last_err = None
        try:
            while self._conn_mgr.connected and self._pubsub:
                # Hicbir abone yoksa pubsub connection acilmamistir; sessizce bekle.
                if not self._subscriptions:
                    await asyncio.sleep(5)
                    continue
                try:
                    message = await asyncio.wait_for(
                        self._pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0),
                        timeout=5.0,
                    )
                    if message and message["type"] == "message":
                        channel = message["channel"]
                        data = json.loads(message["data"])
                        for sub_info in self._subscriptions.values():
                            if sub_info["channel"] == channel:
                                try:
                                    from modules.event_bus.abstraction import EventEnvelope

                                    envelope = EventEnvelope.from_dict(data)
                                    await sub_info["callback"](envelope)
                                    self._delivered += 1
                                except Exception as e:
                                    logger.warning(f"Callback error: {e}")
                except TimeoutError:
                    continue
                except Exception as e:
                    msg = str(e)
                    if msg != _last_err:
                        logger.warning(f"Listener error: {e}")
                        _last_err = msg
                    await asyncio.sleep(5)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Listener loop died: {e}")

    async def _handle_disconnect(self):
        """Handle disconnect by attempting reconnect."""
        if not self._conn_mgr.connected:
            return
        self._conn_mgr._connected = False
        logger.warning("Redis disconnected, attempting reconnect...")
        success = await self._conn_mgr.reconnect_with_backoff()
        if success:
            # Re-init pubsub
            try:
                self._pubsub = self._conn_mgr.redis.pubsub()
                for sub_info in self._subscriptions.values():
                    await self._pubsub.subscribe(sub_info["channel"])
                self._start_listener()
                logger.info("Redis reconnected and resubscribed")
            except Exception as e:
                logger.error(f"Resubscribe after reconnect failed: {e}")
        else:
            logger.error("Redis reconnect exhausted, falling back to in-memory")


async def try_init_redis_backend(redis_url: str | None = None) -> RedisPubSubBackend | None:
    """Try to initialize Redis backend. Returns None if unavailable."""
    if not redis_url:
        redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        logger.info("REDIS_URL not configured, using in-memory event bus")
        return None

    backend = RedisPubSubBackend(redis_url)
    if await backend.connect():
        return backend
    logger.warning("Redis backend init failed, falling back to in-memory")
    return None
