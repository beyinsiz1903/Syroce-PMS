"""
Distributed Lock Manager — Redis-based distributed locking.
Provides safe, tenant-aware distributed locks with timeout, retry, and metrics.
Falls back to asyncio.Lock when Redis is unavailable.
"""
import asyncio
import logging
import time
import uuid
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from contextlib import asynccontextmanager

logger = logging.getLogger("infra.distributed_lock")


class DistributedLock:
    """A single distributed lock instance."""

    def __init__(self, redis_client, name: str, timeout: float = 30.0,
                 retry_interval: float = 0.1, retry_count: int = 50):
        self._redis = redis_client
        self._name = f"lock:{name}"
        self._timeout = timeout
        self._retry_interval = retry_interval
        self._retry_count = retry_count
        self._token = str(uuid.uuid4())
        self._acquired = False

    async def acquire(self) -> bool:
        for _ in range(self._retry_count):
            result = await self._redis.set(
                self._name, self._token, nx=True, ex=int(self._timeout)
            )
            if result:
                self._acquired = True
                return True
            await asyncio.sleep(self._retry_interval)
        return False

    async def release(self) -> bool:
        if not self._acquired:
            return False
        # Lua script for atomic check-and-delete
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        try:
            result = await self._redis.eval(script, 1, self._name, self._token)
            self._acquired = False
            return result == 1
        except Exception as e:
            logger.error(f"Lock release failed for {self._name}: {e}")
            return False

    async def extend(self, additional_time: float) -> bool:
        script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("pexpire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        try:
            result = await self._redis.eval(
                script, 1, self._name, self._token, int(additional_time * 1000)
            )
            return result == 1
        except Exception:
            return False


class DistributedLockManager:
    """Manages distributed locks with metrics and fallback."""

    def __init__(self):
        self._redis = None
        self._fallback_locks: Dict[str, asyncio.Lock] = {}
        self._metrics = {
            "locks_acquired": 0,
            "locks_released": 0,
            "locks_failed": 0,
            "locks_timed_out": 0,
            "fallback_used": 0,
            "active_locks": 0,
            "contention_events": 0,
        }
        self._active_locks: Dict[str, Dict[str, Any]] = {}

    def set_redis(self, redis_client):
        self._redis = redis_client

    @asynccontextmanager
    async def lock(self, name: str, timeout: float = 30.0,
                   tenant_id: Optional[str] = None):
        """Acquire a distributed lock as async context manager."""
        lock_name = f"{tenant_id}:{name}" if tenant_id else name
        acquired = False
        start = time.time()

        try:
            if self._redis:
                dl = DistributedLock(self._redis, lock_name, timeout=timeout)
                acquired = await dl.acquire()
                if acquired:
                    self._metrics["locks_acquired"] += 1
                    self._metrics["active_locks"] += 1
                    self._active_locks[lock_name] = {
                        "acquired_at": datetime.now(timezone.utc).isoformat(),
                        "timeout": timeout,
                        "tenant_id": tenant_id,
                    }
                    try:
                        yield dl
                    finally:
                        await dl.release()
                        self._metrics["locks_released"] += 1
                        self._metrics["active_locks"] -= 1
                        self._active_locks.pop(lock_name, None)
                else:
                    self._metrics["locks_failed"] += 1
                    self._metrics["contention_events"] += 1
                    raise LockAcquisitionError(f"Failed to acquire lock: {lock_name}")
            else:
                # Fallback to in-process lock
                self._metrics["fallback_used"] += 1
                if lock_name not in self._fallback_locks:
                    self._fallback_locks[lock_name] = asyncio.Lock()
                async with self._fallback_locks[lock_name]:
                    self._metrics["locks_acquired"] += 1
                    self._metrics["active_locks"] += 1
                    try:
                        yield None
                    finally:
                        self._metrics["locks_released"] += 1
                        self._metrics["active_locks"] -= 1

        except LockAcquisitionError:
            raise
        except Exception as e:
            duration = time.time() - start
            if duration >= timeout:
                self._metrics["locks_timed_out"] += 1
            logger.error(f"Lock error for {lock_name}: {e}")
            raise

    def get_metrics(self) -> Dict[str, Any]:
        return {**self._metrics, "active_lock_names": list(self._active_locks.keys())}

    def get_active_locks(self) -> Dict[str, Any]:
        return dict(self._active_locks)


class LockAcquisitionError(Exception):
    pass


# Singleton
lock_manager = DistributedLockManager()
