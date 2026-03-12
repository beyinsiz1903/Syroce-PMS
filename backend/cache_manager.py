"""
Redis Cache Manager for High-Performance Hotel PMS
Implements caching for frequently accessed data
"""

import redis
import json
import os
from typing import Optional, Any, Callable
from functools import wraps
import logging

logger = logging.getLogger(__name__)

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
            # Test connection
            self.client.ping()
            self.enabled = True
            logger.info("✅ Redis cache connected successfully")
        except Exception as e:
            logger.warning(f"⚠️ Redis not available: {e}. Caching disabled.")
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
            self.client.setex(
                key,
                ttl,
                json.dumps(value, default=str)
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

def cached(
    ttl: int = 300,
    key_prefix: str = "",
    invalidate_on: list = None
):
    """
    Decorator for caching function results
    
    Args:
        ttl: Time to live in seconds (default 5 minutes)
        key_prefix: Prefix for cache key
        invalidate_on: List of entity types that should invalidate this cache
    
    Usage:
        @cached(ttl=600, key_prefix="dashboard")
        async def get_dashboard_data(tenant_id: str):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not cache.enabled:
                # If cache disabled, call function directly
                return await func(*args, **kwargs)
            
            # Build cache key from function name and arguments
            # Extract tenant_id if present
            tenant_id = kwargs.get('tenant_id') or (args[0] if args else 'global')
            
            # Create unique cache key
            cache_key_parts = [
                'cache',
                str(tenant_id),
                key_prefix or func.__name__,
                str(hash(str(args) + str(sorted(kwargs.items()))))[:16]
            ]
            cache_key = ":".join(cache_key_parts)
            
            # Try to get from cache
            cached_value = cache.get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit: {cache_key}")
                return cached_value
            
            # Cache miss - call function
            logger.debug(f"Cache miss: {cache_key}")
            result = await func(*args, **kwargs)
            
            # Store in cache
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
        params_hash = str(hash(str(sorted(params.items()))))[:16]
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
