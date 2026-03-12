"""
WebSocket Redis Adapter — Distributed WebSocket broadcasting via Redis Pub/Sub.
Enables multi-instance WebSocket support. Falls back to local broadcast.
"""
import logging
import json
import asyncio
from typing import Optional, Dict, Any, Set
from datetime import datetime, timezone

logger = logging.getLogger("infra.ws_redis_adapter")


class WebSocketRedisAdapter:
    """Bridges WebSocket server with Redis Pub/Sub for multi-instance broadcast."""

    CHANNEL_PREFIX = "ws:broadcast:"

    def __init__(self):
        self._redis = None
        self._pubsub = None
        self._subscribed_channels: Set[str] = set()
        self._listener_task: Optional[asyncio.Task] = None
        self._local_handler = None
        self._active = False
        self._instance_id = ""
        self._metrics = {
            "messages_published": 0,
            "messages_received": 0,
            "messages_forwarded": 0,
            "publish_errors": 0,
            "channels_active": 0,
        }

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

    async def subscribe(self, room: str):
        """Subscribe to a room's broadcast channel."""
        channel = f"{self.CHANNEL_PREFIX}{room}"
        if not self._active or not self._pubsub:
            return
        if channel in self._subscribed_channels:
            return
        try:
            await self._pubsub.subscribe(channel)
            self._subscribed_channels.add(channel)
            self._metrics["channels_active"] = len(self._subscribed_channels)
            if not self._listener_task or self._listener_task.done():
                self._listener_task = asyncio.create_task(self._listen())
        except Exception as e:
            logger.error(f"WS subscribe error ({room}): {e}")

    async def publish(self, room: str, event: str, data: Dict[str, Any]):
        """Publish event to all instances via Redis."""
        message = json.dumps({
            "room": room,
            "event": event,
            "data": data,
            "source_instance": self._instance_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        if self._active and self._redis:
            try:
                channel = f"{self.CHANNEL_PREFIX}{room}"
                await self._redis.publish(channel, message)
                self._metrics["messages_published"] += 1
            except Exception as e:
                self._metrics["publish_errors"] += 1
                logger.error(f"WS publish error ({room}): {e}")
                # Fallback to local
                if self._local_handler:
                    await self._local_handler(room, event, data)
        else:
            # Local-only mode
            if self._local_handler:
                await self._local_handler(room, event, data)

    async def _listen(self):
        """Listen for messages from other instances."""
        if not self._pubsub:
            return
        try:
            async for message in self._pubsub.listen():
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
                    logger.error(f"WS message parse error: {e}")
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"WS listener error: {e}")

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
        self._active = False

    def get_metrics(self) -> Dict[str, Any]:
        return {
            **self._metrics,
            "active": self._active,
            "instance_id": self._instance_id,
            "subscribed_channels": list(self._subscribed_channels),
        }


# Singleton
ws_redis_adapter = WebSocketRedisAdapter()
