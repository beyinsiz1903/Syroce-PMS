"""
Redis Pub/Sub Backend for Event Bus.
Provides multi-instance WebSocket broadcasting via Redis.
Gracefully falls back to in-memory if Redis is unavailable.
"""
import logging
import json
import asyncio
from typing import Callable, Dict, Optional

logger = logging.getLogger("event_bus.redis")


class RedisPubSubBackend:
    """Redis-backed event bus backend for production multi-instance scaling."""

    def __init__(self, redis_url: Optional[str] = None):
        self._redis_url = redis_url
        self._redis = None
        self._pubsub = None
        self._subscriptions: Dict[str, dict] = {}
        self._published = 0
        self._delivered = 0
        self._connected = False
        self._listener_task = None

    async def connect(self) -> bool:
        if not self._redis_url:
            logger.info("No Redis URL configured, skipping Redis connection")
            return False
        try:
            import redis.asyncio as aioredis
            self._redis = aioredis.from_url(
                self._redis_url,
                decode_responses=True,
                socket_connect_timeout=3,
                socket_timeout=5,
                retry_on_timeout=True,
            )
            await self._redis.ping()
            self._pubsub = self._redis.pubsub()
            self._connected = True
            logger.info(f"Redis Pub/Sub connected: {self._redis_url}")
            return True
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}")
            self._connected = False
            return False

    async def disconnect(self):
        if self._listener_task:
            self._listener_task.cancel()
        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()
        self._connected = False

    async def publish(self, channel: str, event) -> bool:
        if not self._connected or not self._redis:
            return False
        try:
            data = json.dumps(event.to_dict())
            await self._redis.publish(channel, data)
            self._published += 1
            return True
        except Exception as e:
            logger.error(f"Redis publish failed: {e}")
            self._connected = False
            return False

    async def subscribe(self, channel: str, callback: Callable) -> str:
        import uuid
        sub_id = str(uuid.uuid4())
        self._subscriptions[sub_id] = {"channel": channel, "callback": callback}
        if self._connected and self._pubsub:
            try:
                await self._pubsub.subscribe(channel)
            except Exception as e:
                logger.error(f"Redis subscribe failed: {e}")
        return sub_id

    async def unsubscribe(self, subscription_id: str) -> bool:
        sub = self._subscriptions.pop(subscription_id, None)
        if sub and self._connected and self._pubsub:
            try:
                await self._pubsub.unsubscribe(sub["channel"])
            except Exception:
                pass
        return sub is not None

    async def health_check(self) -> dict:
        if not self._connected or not self._redis:
            return {
                "backend": "redis",
                "status": "disconnected",
                "subscriptions": len(self._subscriptions),
                "published": self._published,
                "delivered": self._delivered,
            }
        try:
            await self._redis.ping()
            info = await self._redis.info("clients")
            return {
                "backend": "redis",
                "status": "healthy",
                "connected_clients": info.get("connected_clients", 0),
                "subscriptions": len(self._subscriptions),
                "published": self._published,
                "delivered": self._delivered,
            }
        except Exception as e:
            return {
                "backend": "redis",
                "status": "error",
                "error": str(e),
            }


async def try_init_redis_backend(redis_url: Optional[str] = None) -> Optional[RedisPubSubBackend]:
    """Try to initialize Redis backend. Returns None if unavailable."""
    if not redis_url:
        import os
        redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        logger.info("REDIS_URL not configured, using in-memory event bus")
        return None

    backend = RedisPubSubBackend(redis_url)
    if await backend.connect():
        return backend
    return None
