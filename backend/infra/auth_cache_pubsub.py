"""
Auth Cache Pub/Sub — cross-instance invalidation for the in-process
user / tenant document caches in ``core.security`` and ``core.helpers``.

Without this adapter the auth caches are correct only on the worker
that processed the mutation: a parallel worker keeps serving the stale
user role / tenant module flags until its own 30 s / 60 s TTL expires.
With it, every ``invalidate_user_doc_cache`` / ``invalidate_tenant_doc_cache``
call publishes a small JSON message on a Redis channel and every other
worker drops the matching entry from its local cache within milliseconds.

Loop-safety:
  - The publishing path emits a ``source_instance`` field.
  - The listener skips messages whose ``source_instance`` matches its
    own instance id, so a worker never reacts to its own broadcast.
  - The listener evicts via the *internal* ``_local_evict_*`` helpers
    (NOT the public ``invalidate_*`` API) so receiving an event never
    re-publishes — that would be an infinite loop.

Failure mode:
  - All Redis I/O is best-effort: any network / encoding error is
    logged and swallowed. The local cache is always evicted before
    publishing, so a Redis outage degrades to "single-worker correct"
    rather than "stale forever".

Reconnect:
  - Same auto-reconnect + idle-timeout-debug pattern as
    ``infra.ws_redis_adapter`` — we stay subscribed across Redis
    restarts and treat the routine 30 s socket idle timeout as DEBUG,
    not WARNING.
"""
import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

try:
    from redis.exceptions import TimeoutError as RedisTimeoutError
except Exception:  # pragma: no cover — defensive
    class RedisTimeoutError(Exception):
        """Shim used when redis.exceptions is unavailable."""


logger = logging.getLogger("infra.auth_cache_pubsub")

CHANNEL_USER = "auth:invalidate:user"
CHANNEL_TENANT = "auth:invalidate:tenant"


class AuthCachePubSub:
    """Singleton bridge between local auth caches and Redis pub/sub."""

    def __init__(self):
        self._redis = None
        self._pubsub = None
        self._instance_id = ""
        self._active = False
        self._listener_task: asyncio.Task | None = None
        self._reconnect_min_backoff: float = 1.0
        self._reconnect_max_backoff: float = 30.0
        self._metrics = {
            "user_published": 0,
            "tenant_published": 0,
            "user_received": 0,
            "tenant_received": 0,
            "publish_errors": 0,
            "listen_errors": 0,
            "reconnects": 0,
            # Counts the rare case where ``schedule_publish_*`` is
            # called from a thread / sync context with no running event
            # loop. Local eviction has already happened so this worker
            # is correct; the counter just helps detect unexpected
            # call paths during ops review.
            "publish_skipped_no_loop": 0,
            "last_publish_error": None,
            "last_publish_error_at": None,
            "last_listen_error": None,
            "last_listen_error_at": None,
        }

    async def initialize(self, redis_client, instance_id: str) -> None:
        """Wire up the Redis client and start the listener.

        Fully idempotent: any in-flight listener task and pubsub object
        from a previous initialize call are torn down first — including
        when ``redis_client`` is None (local-only / disable mode), so
        re-init never leaks file descriptors or background tasks.
        """
        self._instance_id = instance_id or "unknown"

        # Stop any prior listener and pubsub before re-binding. Marking
        # ``_active=False`` first stops the listener loop from chasing
        # reconnects against the old client; only then do we cancel the
        # task and close the old pubsub.
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
            logger.info("Auth cache pub/sub: no Redis client, local-only mode")
            return

        self._redis = redis_client
        try:
            self._pubsub = self._redis.pubsub()
            await self._pubsub.subscribe(CHANNEL_USER, CHANNEL_TENANT)
            self._active = True
            self._listener_task = asyncio.create_task(self._listen())
            logger.info(
                f"Auth cache pub/sub initialized (instance={instance_id})"
            )
        except Exception as e:
            logger.warning(f"Auth cache pub/sub init failed: {e}")
            self._active = False

    async def publish_user(self, user_id: str | None) -> None:
        """Broadcast a user-cache eviction. Empty / None id → full flush."""
        if not self._active or self._redis is None:
            return
        try:
            payload = json.dumps({
                "id": user_id or "",
                "instance": self._instance_id,
                "ts": datetime.now(UTC).isoformat(),
            })
            await self._redis.publish(CHANNEL_USER, payload)
            self._metrics["user_published"] += 1
        except Exception as e:
            self._metrics["publish_errors"] += 1
            self._metrics["last_publish_error"] = (
                f"{type(e).__name__}: {str(e)[:200]}"
            )
            self._metrics["last_publish_error_at"] = (
                datetime.now(UTC).isoformat()
            )
            logger.debug(f"Auth cache pub/sub publish_user error: {e}")

    async def publish_tenant(self, tenant_id: str | None) -> None:
        """Broadcast a tenant-cache eviction. Empty / None id → full flush."""
        if not self._active or self._redis is None:
            return
        try:
            payload = json.dumps({
                "id": tenant_id or "",
                "instance": self._instance_id,
                "ts": datetime.now(UTC).isoformat(),
            })
            await self._redis.publish(CHANNEL_TENANT, payload)
            self._metrics["tenant_published"] += 1
        except Exception as e:
            self._metrics["publish_errors"] += 1
            self._metrics["last_publish_error"] = (
                f"{type(e).__name__}: {str(e)[:200]}"
            )
            self._metrics["last_publish_error_at"] = (
                datetime.now(UTC).isoformat()
            )
            logger.debug(f"Auth cache pub/sub publish_tenant error: {e}")

    def schedule_publish_user(self, user_id: str | None) -> None:
        """Fire-and-forget publish from a sync caller.

        ``invalidate_user_doc_cache`` is sync (called from sync helpers
        inside ``core.security``), so we cannot ``await`` here. We schedule
        the publish on the running event loop if one exists; otherwise we
        silently drop the broadcast (single-worker correctness is
        preserved by the local evict that already ran).
        """
        if not self._active:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._metrics["publish_skipped_no_loop"] += 1
            return
        loop.create_task(self.publish_user(user_id))

    def schedule_publish_tenant(self, tenant_id: str | None) -> None:
        if not self._active:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            self._metrics["publish_skipped_no_loop"] += 1
            return
        loop.create_task(self.publish_tenant(tenant_id))

    async def _listen(self) -> None:
        """Background listener with auto-reconnect.

        Mirrors ``infra.ws_redis_adapter._listen`` so we get the same
        idle-timeout-is-DEBUG behaviour and exponential backoff on real
        connection failures.
        """
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
                        "Auth cache pubsub listener exited; reconnecting"
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
                    logger.debug("Auth cache pubsub idle timeout; reconnecting")
                except Exception as e:
                    self._metrics["listen_errors"] += 1
                    self._metrics["last_listen_error"] = (
                        f"{type(e).__name__}: {str(e)[:200]}"
                    )
                    self._metrics["last_listen_error_at"] = (
                        datetime.now(UTC).isoformat()
                    )
                    logger.warning(
                        f"Auth cache pubsub listener error: {e}; reconnecting"
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
        """Apply a remote eviction to the local cache, *without* re-publishing."""
        try:
            channel = message.get("channel")
            if isinstance(channel, bytes):
                channel = channel.decode("utf-8", errors="replace")
            data = message.get("data")
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="replace")
            payload = json.loads(data) if isinstance(data, str) else {}

            # Loop guard: skip our own broadcasts.
            if payload.get("instance") == self._instance_id:
                return

            target_id = payload.get("id") or None  # "" → None → full flush
            # Lazy import: core.security / core.helpers must NOT import
            # this module at top-level (circular: startup imports both).
            if channel == CHANNEL_USER:
                from core.security import _local_evict_user_doc
                _local_evict_user_doc(target_id)
                self._metrics["user_received"] += 1
            elif channel == CHANNEL_TENANT:
                from core.helpers import _local_evict_tenant_doc
                _local_evict_tenant_doc(target_id)
                self._metrics["tenant_received"] += 1
        except Exception as e:
            self._metrics["listen_errors"] += 1
            self._metrics["last_listen_error"] = (
                f"handle: {type(e).__name__}: {str(e)[:200]}"
            )
            self._metrics["last_listen_error_at"] = (
                datetime.now(UTC).isoformat()
            )
            logger.warning(f"Auth cache pubsub handle error: {e}")

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
            await new_pubsub.subscribe(CHANNEL_USER, CHANNEL_TENANT)
            self._pubsub = new_pubsub
            self._metrics["reconnects"] += 1
            logger.debug("Auth cache pubsub reconnected")
            return True
        except Exception as e:
            logger.warning(f"Auth cache pubsub reconnect failed: {e}")
            return False

    async def close(self) -> None:
        if self._listener_task:
            self._listener_task.cancel()
            self._listener_task = None
        if self._pubsub is not None:
            try:
                await self._pubsub.unsubscribe()
                await self._pubsub.close()
            except Exception:
                pass
            self._pubsub = None
        self._active = False

    def get_metrics(self) -> dict[str, Any]:
        return {
            **self._metrics,
            "active": self._active,
            "instance_id": self._instance_id,
        }


# Singleton
auth_cache_pubsub = AuthCachePubSub()
