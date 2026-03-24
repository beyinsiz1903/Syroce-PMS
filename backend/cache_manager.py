"""
Redis Cache Manager for High-Performance Hotel PMS
Implements caching for frequently accessed data
"""

import hashlib
import json
import logging
import os
from datetime import date, datetime
from functools import wraps
from typing import Any, Callable, Optional

import redis

logger = logging.getLogger(__name__)


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
        try:
            self.client = redis.from_url(
                self.redis_url,
                decode_responses=True,
                max_connections=50,
                socket_connect_timeout=5,
                socket_timeout=5,
                retry_on_timeout=True
            )
            self.client.ping()
            self.enabled = True
            logger.info("Redis cache connected successfully")
        except Exception as e:
            logger.warning(f"Redis not available: {e}. Caching disabled.")
            self.enabled = False
            self.client = None

    def get(self, key: str) -> Optional[Any]:
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

    def delete_pattern(self, pattern: str):
        """Delete all keys matching pattern"""
        if not self.enabled:
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
        """Invalidate all cache for a tenant or specific entity type"""
        if entity_type:
            pattern = f"cache:{tenant_id}:{entity_type}:*"
        else:
            pattern = f"cache:{tenant_id}:*"

        return self.delete_pattern(pattern)

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
    """Extract tenant_id from function arguments, checking User objects first."""
    # Check kwargs for current_user or tenant_id
    for key in ('current_user', 'user'):
        obj = kwargs.get(key)
        if obj and hasattr(obj, 'tenant_id') and obj.tenant_id:
            return str(obj.tenant_id)

    if 'tenant_id' in kwargs and kwargs['tenant_id']:
        return str(kwargs['tenant_id'])

    # Check positional args for objects with tenant_id
    for arg in args:
        if hasattr(arg, 'tenant_id') and getattr(arg, 'tenant_id', None):
            return str(arg.tenant_id)

    return 'global'


def _build_cache_key(func: Callable, key_prefix: str, tenant_id: str, args, kwargs) -> str:
    """Build a stable, deterministic cache key."""
    # Collect key-relevant parts (exclude User objects which are not cache-relevant)
    key_parts = []
    for arg in args:
        if hasattr(arg, 'tenant_id'):
            continue  # Skip User objects
        key_parts.append(str(arg))

    for k, v in sorted(kwargs.items()):
        if k in ('current_user', 'user', 'request', 'response', 'db'):
            continue  # Skip non-cacheable params
        key_parts.append(f"{k}={v}")

    params_str = "|".join(key_parts)
    params_hash = hashlib.md5(params_str.encode()).hexdigest()[:12]

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
