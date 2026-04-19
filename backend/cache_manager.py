"""
Redis Cache Manager for High-Performance Hotel PMS
Implements caching for frequently accessed data
"""

import fnmatch
import hashlib
import json
import logging
import os
import threading
import time
from datetime import date, datetime
from functools import wraps
from typing import Any, Callable

import redis

logger = logging.getLogger(__name__)


class _InMemoryTTLStore:
    """Thread-safe in-memory TTL cache used when Redis is unavailable.

    Bounded to ~5000 entries via simple FIFO eviction to prevent unbounded growth.
    Suitable as a single-process fallback; multi-worker setups should use Redis.
    """

    MAX_ENTRIES = 5000

    def __init__(self):
        self._data: dict[str, tuple[float, str]] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> str | None:
        with self._lock:
            entry = self._data.get(key)
            if not entry:
                return None
            expires_at, value = entry
            if expires_at < time.time():
                self._data.pop(key, None)
                return None
            return value

    def setex(self, key: str, ttl: int, value: str):
        with self._lock:
            if len(self._data) >= self.MAX_ENTRIES and key not in self._data:
                # Evict oldest 10% to keep latency predictable
                drop = max(1, self.MAX_ENTRIES // 10)
                for k in list(self._data.keys())[:drop]:
                    self._data.pop(k, None)
            self._data[key] = (time.time() + ttl, value)

    def delete(self, *keys: str) -> int:
        n = 0
        with self._lock:
            for k in keys:
                if self._data.pop(k, None) is not None:
                    n += 1
        return n

    def keys(self, pattern: str) -> list[str]:
        with self._lock:
            return [k for k in self._data.keys() if fnmatch.fnmatchcase(k, pattern)]

    def dbsize(self) -> int:
        with self._lock:
            return len(self._data)

    def info(self) -> dict:
        return {"connected_clients": 1, "used_memory_human": "in-memory"}

    def ping(self):
        return True


def _json_serializer(obj):
    """Custom JSON serializer that handles Pydantic models, datetime, etc."""
    if hasattr(obj, 'model_dump'):
        return obj.model_dump()
    if hasattr(obj, 'dict'):
        return obj.dict()
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if hasattr(obj, 'value'):
        return obj.value
    return str(obj)


def _make_serializable(value: Any) -> Any:
    """Recursively convert Pydantic models and other non-serializable types to dicts/primitives."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if hasattr(value, 'model_dump'):
        return value.model_dump()
    if hasattr(value, 'dict') and not isinstance(value, dict):
        return value.dict()
    if isinstance(value, dict):
        return {k: _make_serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_make_serializable(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if hasattr(value, 'value'):
        return value.value
    return value


class CacheManager:
    """Redis-based cache manager with async support"""

    def __init__(self):
        self.redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        self.backend = "none"
        try:
            self.client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                max_connections=50,
                socket_connect_timeout=2,
                socket_timeout=2,
                retry_on_timeout=True
            )
            self.client.ping()
            self.enabled = True
            self.backend = "redis"
            logger.info("Redis cache connected successfully")
        except Exception as e:
            # Fallback to in-memory TTL cache so @cached() decorators stay effective.
            logger.warning(f"Redis not available: {e}. Falling back to in-memory cache.")
            self.client = _InMemoryTTLStore()
            self.enabled = True
            self.backend = "memory"

    def get(self, key: str) -> Any | None:
        """Get value from cache"""
        if not self.enabled:
            return None

        try:
            value = self.client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Cache get error for key {key}: {e}")
            return None

    def set(self, key: str, value: Any, ttl: int = 300):
        """Set value in cache with TTL (default 5 minutes)"""
        if not self.enabled:
            return False

        try:
            serializable = _make_serializable(value)
            self.client.setex(
                key,
                ttl,
                json.dumps(serializable, default=_json_serializer)
            )
            return True
        except Exception as e:
            logger.error(f"Cache set error for key {key}: {e}")
            return False

    def delete(self, key: str):
        """Delete key from cache"""
        if not self.enabled:
            return False

        try:
            self.client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Cache delete error for key {key}: {e}")
            return False

    # Strict shape for tenant-scoped invalidation patterns:
    #   cache:<tenant_id>:<entity>[:<sub>...]:*
    # tenant: ASCII safe-set; entity/sub: same set (no glob meta);
    # only the trailing `*` is allowed (and only as the final segment).
    _SAFE_PATTERN_RE = __import__("re").compile(
        r"^cache:[A-Za-z0-9._\-]{1,128}"
        r"(?::[A-Za-z0-9._\-]+){1,8}"
        r"(?::\*)?$"
    )

    def delete_pattern(self, pattern: str):
        """Delete all keys matching pattern.
        Sprint 32: central guard — any pattern starting with `cache:`
        must conform to the strict tenant-scoped shape, otherwise it is
        rejected. This protects legacy helpers (DashboardCache.invalidate,
        etc.) from a future caller passing an untrusted tenant_id with
        glob meta or `:`-skew payloads (e.g. `a:b*c`). Non-`cache:`
        patterns (custom prefixes outside tenant namespace) pass through."""
        if not self.enabled:
            return False
        if pattern.startswith("cache:"):
            if not self._SAFE_PATTERN_RE.match(pattern):
                logger.warning(
                    "cache.delete_pattern REJECTED malformed/unsafe "
                    "pattern=%r", pattern)
                return False
        try:
            keys = self.client.keys(pattern)
            if keys:
                self.client.delete(*keys)
            return True
        except Exception as e:
            logger.error(f"Cache delete pattern error for {pattern}: {e}")
            return False

    def invalidate_tenant_cache(self, tenant_id: str, entity_type: str = None):
        """Invalidate all cache for a tenant or specific entity type.
        Tenant_id is validated up-front to prevent any glob meta from
        leaking into the pattern (defense-in-depth alongside the
        delete_pattern central guard)."""
        if not self._is_safe_tenant_id(tenant_id):
            logger.warning(
                "cache.invalidate_tenant_cache REJECTED unsafe tenant_id "
                "(entity=%s, tenant_repr=%r)", entity_type, tenant_id)
            return False
        if entity_type and any(c in entity_type for c in "*?[]\\:"):
            logger.warning(
                "cache.invalidate_tenant_cache REJECTED unsafe entity=%r",
                entity_type)
            return False
        if entity_type:
            pattern = f"cache:{tenant_id}:{entity_type}:*"
        else:
            pattern = f"cache:{tenant_id}:*"

        return self.delete_pattern(pattern)

    # ── Sprint 32: hardened invalidation ────────────────────────────
    # Counters are bumped on every safe_invalidate path; protected by a
    # threading.Lock so concurrent FastAPI workers (thread-pool) don't
    # lose increments. Counters are per-process; if SLO alerts are wired,
    # aggregate across replicas at the metrics layer.
    invalidation_failures: dict = {}
    invalidation_success: dict = {}
    _invalidation_metrics_lock = threading.Lock()

    # Strict ASCII whitelist — `str.isalnum()` would also accept Unicode
    # alphanumerics (e.g. Cyrillic, fullwidth digits) which could collide
    # with key namespaces or evade ops review.
    _SAFE_TENANT_RE = __import__("re").compile(r"^[A-Za-z0-9._\-]{1,128}$")

    @classmethod
    def _is_safe_tenant_id(cls, tenant_id: str) -> bool:
        """Tenant id must be ASCII [A-Za-z0-9._-], length 1..128.
        Blocks Redis KEYS glob metacharacters (*, ?, [, ], \\) which could
        otherwise broaden a delete_pattern scope across tenants, plus any
        non-ASCII alphanumeric forms."""
        if not tenant_id or not isinstance(tenant_id, str):
            return False
        return bool(cls._SAFE_TENANT_RE.match(tenant_id))

    def _bump(self, bucket: dict, key: str) -> None:
        with self._invalidation_metrics_lock:
            bucket[key] = bucket.get(key, 0) + 1

    def safe_invalidate(self, tenant_id: str, entity_prefix: str) -> bool:
        """Tenant-scoped, glob-safe invalidation with metrics + warning logs.
        Returns True on success, False on validation/backend failure."""
        key = f"{entity_prefix}"
        if not self._is_safe_tenant_id(tenant_id):
            self._bump(self.invalidation_failures, key)
            logger.warning(
                "cache.safe_invalidate REJECTED unsafe tenant_id "
                "(prefix=%s, tenant_repr=%r)", entity_prefix, tenant_id)
            return False
        if not entity_prefix or any(
                c in entity_prefix for c in "*?[]\\:"):
            self._bump(self.invalidation_failures, key)
            logger.warning(
                "cache.safe_invalidate REJECTED unsafe entity_prefix=%r",
                entity_prefix)
            return False
        pattern = f"cache:{tenant_id}:{entity_prefix}:*"
        ok = self.delete_pattern(pattern)
        if ok:
            self._bump(self.invalidation_success, key)
        else:
            self._bump(self.invalidation_failures, key)
            logger.warning(
                "cache.safe_invalidate FAILED pattern=%s", pattern)
        return bool(ok)

    def health_check(self) -> dict:
        """Check cache health"""
        if not self.enabled:
            return {
                'status': 'disabled',
                'message': 'Redis not available'
            }

        try:
            info = self.client.info()
            return {
                'status': 'healthy',
                'connected_clients': info.get('connected_clients', 0),
                'used_memory_human': info.get('used_memory_human', 'N/A'),
                'total_keys': self.client.dbsize()
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e)
            }

# Global cache instance
cache = CacheManager()

def _extract_tenant_id(args, kwargs) -> str:
    """Extract tenant_id from function arguments, checking User/Tenant context first."""
    # Check kwargs for any common tenant-bearing dependency
    for key in ('current_user', 'user', 'tenant', 'tenant_ctx', 'ctx'):
        obj = kwargs.get(key)
        if obj and hasattr(obj, 'tenant_id') and getattr(obj, 'tenant_id', None):
            return str(obj.tenant_id)

    if 'tenant_id' in kwargs and kwargs['tenant_id']:
        return str(kwargs['tenant_id'])

    # Check positional args for objects with tenant_id
    for arg in args:
        if hasattr(arg, 'tenant_id') and getattr(arg, 'tenant_id', None):
            return str(arg.tenant_id)

    return 'global'


def _stable_str(value: Any) -> str:
    """Render a value into a stable string for cache-key hashing.
    Avoids object reprs that include memory addresses (e.g. <Obj at 0x...>).
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return str(value)
    if hasattr(value, 'tenant_id') and getattr(value, 'tenant_id', None):
        return f"tenant:{value.tenant_id}"
    if hasattr(value, 'model_dump'):
        try:
            return json.dumps(value.model_dump(), sort_keys=True, default=str)
        except Exception:
            return type(value).__name__
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_stable_str(v) for v in value) + "]"
    if isinstance(value, dict):
        return "{" + ",".join(f"{k}:{_stable_str(v)}" for k, v in sorted(value.items())) + "}"
    return type(value).__name__


def _build_cache_key(func: Callable, key_prefix: str, tenant_id: str, args, kwargs) -> str:
    """Build a stable, deterministic cache key."""
    # Collect key-relevant parts (exclude User/tenant objects, already in tenant_id prefix)
    skip_keys = {'current_user', 'user', 'request', 'response', 'db', 'tenant', 'tenant_ctx', 'ctx'}
    key_parts = []
    for arg in args:
        if hasattr(arg, 'tenant_id'):
            continue
        key_parts.append(_stable_str(arg))

    for k, v in sorted(kwargs.items()):
        if k in skip_keys:
            continue
        key_parts.append(f"{k}={_stable_str(v)}")

    params_str = "|".join(key_parts)
    params_hash = hashlib.sha256(params_str.encode()).hexdigest()[:16]

    return f"cache:{tenant_id}:{key_prefix or func.__name__}:{params_hash}"


def cached(
    ttl: int = 300,
    key_prefix: str = "",
    invalidate_on: list = None
):
    """
    Decorator for caching function results.
    Properly serializes Pydantic models and uses stable cache keys.

    Args:
        ttl: Time to live in seconds (default 5 minutes)
        key_prefix: Prefix for cache key
        invalidate_on: List of entity types that should invalidate this cache
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not cache.enabled:
                return await func(*args, **kwargs)

            tenant_id = _extract_tenant_id(args, kwargs)
            cache_key = _build_cache_key(func, key_prefix, tenant_id, args, kwargs)

            # Try to get from cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached_value

            # Cache miss - call function
            logger.debug(f"Cache miss: {cache_key}")
            result = await func(*args, **kwargs)

            # Store in cache (Pydantic models are auto-serialized)
            cache.set(cache_key, result, ttl=ttl)

            return result

        return wrapper
    return decorator


# Specific cache helpers for common patterns

class DashboardCache:
    """Cache helpers for dashboard data"""

    @staticmethod
    def get_stats_key(tenant_id: str, date: str = None) -> str:
        """Get cache key for dashboard stats"""
        date_str = date or "today"
        return f"cache:{tenant_id}:dashboard:stats:{date_str}"

    @staticmethod
    def get_occupancy_key(tenant_id: str, date_range: str) -> str:
        """Get cache key for occupancy data"""
        return f"cache:{tenant_id}:dashboard:occupancy:{date_range}"

    @staticmethod
    def invalidate(tenant_id: str):
        """Invalidate all dashboard cache for tenant"""
        cache.delete_pattern(f"cache:{tenant_id}:dashboard:*")


class RoomCache:
    """Cache helpers for room data"""

    @staticmethod
    def get_status_key(tenant_id: str) -> str:
        """Get cache key for room status board"""
        return f"cache:{tenant_id}:rooms:status_board"

    @staticmethod
    def get_available_key(tenant_id: str, date: str) -> str:
        """Get cache key for available rooms on date"""
        return f"cache:{tenant_id}:rooms:available:{date}"

    @staticmethod
    def invalidate(tenant_id: str, room_id: str = None):
        """Invalidate room cache"""
        if room_id:
            cache.delete(f"cache:{tenant_id}:rooms:{room_id}")
        else:
            cache.delete_pattern(f"cache:{tenant_id}:rooms:*")


class BookingCache:
    """Cache helpers for booking data"""

    @staticmethod
    def invalidate(tenant_id: str, booking_id: str = None):
        """Invalidate booking cache and related caches"""
        if booking_id:
            cache.delete(f"cache:{tenant_id}:bookings:{booking_id}")
        else:
            cache.delete_pattern(f"cache:{tenant_id}:bookings:*")

        # Also invalidate related caches
        DashboardCache.invalidate(tenant_id)
        RoomCache.invalidate(tenant_id)


class GuestCache:
    """Cache helpers for guest data"""

    @staticmethod
    def get_profile_key(tenant_id: str, guest_id: str) -> str:
        """Get cache key for guest profile"""
        return f"cache:{tenant_id}:guests:profile:{guest_id}"

    @staticmethod
    def get_history_key(tenant_id: str, guest_id: str) -> str:
        """Get cache key for guest stay history"""
        return f"cache:{tenant_id}:guests:history:{guest_id}"

    @staticmethod
    def invalidate(tenant_id: str, guest_id: str = None):
        """Invalidate guest cache"""
        if guest_id:
            cache.delete_pattern(f"cache:{tenant_id}:guests:*:{guest_id}")
        else:
            cache.delete_pattern(f"cache:{tenant_id}:guests:*")


class ReportCache:
    """Cache helpers for reports"""

    @staticmethod
    def get_key(tenant_id: str, report_type: str, params: dict) -> str:
        """Get cache key for report"""
        params_str = str(sorted(params.items()))
        params_hash = hashlib.md5(params_str.encode()).hexdigest()[:12]
        return f"cache:{tenant_id}:reports:{report_type}:{params_hash}"

    @staticmethod
    def invalidate_all(tenant_id: str):
        """Invalidate all reports cache"""
        cache.delete_pattern(f"cache:{tenant_id}:reports:*")


# Cache warming functions (pre-populate cache)

async def warm_dashboard_cache(tenant_id: str, db):
    """Pre-populate dashboard cache with frequently accessed data"""
    try:
        # Room status counts
        rooms = await db.rooms.find({'tenant_id': tenant_id}, {'_id': 0, 'status': 1}).to_list(1000)
        status_counts = {}
        for room in rooms:
            status = room.get('status', 'available')
            status_counts[status] = status_counts.get(status, 0) + 1

        key = DashboardCache.get_stats_key(tenant_id)
        cache.set(key, {'room_status_counts': status_counts}, ttl=300)

        logger.info(f"✅ Warmed dashboard cache for tenant {tenant_id}")
    except Exception as e:
        logger.error(f"Error warming dashboard cache: {e}")


async def warm_room_cache(tenant_id: str, db):
    """Pre-populate room cache"""
    try:
        rooms = await db.rooms.find(
            {'tenant_id': tenant_id},
            {'_id': 0}
        ).to_list(1000)

        key = RoomCache.get_status_key(tenant_id)
        cache.set(key, rooms, ttl=60)  # Short TTL for real-time data

        logger.info(f"✅ Warmed room cache for tenant {tenant_id}")
    except Exception as e:
        logger.error(f"Error warming room cache: {e}")
