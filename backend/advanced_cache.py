"""
Advanced Multi-Layer Caching System
L1: 1 minute (critical real-time data)
L2: 5 minutes (standard data)
L3: 1 hour (reports and analytics)
"""
import redis
import json
import logging
from typing import Any, Optional, Callable
from functools import wraps
import hashlib

logger = logging.getLogger(__name__)

class CacheLayer:
    L1_CRITICAL = "L1"  # 1 minute - Real-time critical data
    L2_STANDARD = "L2"  # 5 minutes - Standard data
    L3_REPORTS = "L3"   # 1 hour - Reports and analytics
    
    TTL_MAP = {
        L1_CRITICAL: 60,        # 1 minute
        L2_STANDARD: 300,       # 5 minutes
        L3_REPORTS: 3600        # 1 hour
    }

class AdvancedCacheManager:
    def __init__(self, redis_client: redis.Redis):
        self.redis = redis_client
        self.namespace = "pms:cache"
        
    def _make_key(self, layer: str, key: str) -> str:
        """Generate cache key with namespace and layer"""
        return f"{self.namespace}:{layer}:{key}"
    
    def _serialize(self, value: Any) -> str:
        """Serialize value for cache storage"""
        try:
            return json.dumps(value, default=str)
        except Exception as e:
            logger.error(f"Serialization error: {e}")
            return None
    
    def _deserialize(self, value: str) -> Any:
        """Deserialize value from cache"""
        try:
            return json.loads(value) if value else None
        except Exception as e:
            logger.error(f"Deserialization error: {e}")
            return None
    
    async def get(self, key: str, layer: str = CacheLayer.L2_STANDARD) -> Optional[Any]:
        """
        Get value from cache
        
        Args:
            key: Cache key
            layer: Cache layer (L1, L2, or L3)
            
        Returns:
            Cached value or None
        """
        try:
            cache_key = self._make_key(layer, key)
            value = self.redis.get(cache_key)
            
            if value:
                logger.debug(f"Cache HIT: {cache_key}")
                return self._deserialize(value)
            else:
                logger.debug(f"Cache MISS: {cache_key}")
                return None
                
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    async def set(
        self,
        key: str,
        value: Any,
        layer: str = CacheLayer.L2_STANDARD,
        ttl: Optional[int] = None
    ) -> bool:
        """
        Set value in cache
        
        Args:
            key: Cache key
            value: Value to cache
            layer: Cache layer
            ttl: Custom TTL (overrides layer default)
            
        Returns:
            Success status
        """
        try:
            cache_key = self._make_key(layer, key)
            serialized = self._serialize(value)
            
            if serialized is None:
                return False
            
            ttl_seconds = ttl if ttl is not None else CacheLayer.TTL_MAP.get(layer, 300)
            
            self.redis.setex(cache_key, ttl_seconds, serialized)
            logger.debug(f"Cache SET: {cache_key} (TTL: {ttl_seconds}s)")
            return True
            
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
    
    async def delete(self, key: str, layer: str = CacheLayer.L2_STANDARD) -> bool:
        """Delete key from cache"""
        try:
            cache_key = self._make_key(layer, key)
            self.redis.delete(cache_key)
            logger.debug(f"Cache DELETE: {cache_key}")
            return True
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """
        Invalidate all keys matching pattern
        
        Args:
            pattern: Key pattern (e.g., "dashboard:*")
            
        Returns:
            Number of keys deleted
        """
        try:
            full_pattern = f"{self.namespace}:*:{pattern}"
            keys = self.redis.keys(full_pattern)
            
            if keys:
                count = self.redis.delete(*keys)
                logger.info(f"Invalidated {count} keys matching {pattern}")
                return count
            return 0
            
        except Exception as e:
            logger.error(f"Cache invalidation error: {e}")
            return 0
    
    async def get_stats(self) -> dict:
        """Get cache statistics"""
        try:
            # Get all cache keys
            all_keys = self.redis.keys(f"{self.namespace}:*")
            
            # Count by layer
            layer_stats = {
                CacheLayer.L1_CRITICAL: 0,
                CacheLayer.L2_STANDARD: 0,
                CacheLayer.L3_REPORTS: 0
            }
            
            for key in all_keys:
                key_str = key.decode() if isinstance(key, bytes) else key
                for layer in layer_stats.keys():
                    if f":{layer}:" in key_str:
                        layer_stats[layer] += 1
                        break
            
            # Redis info
            info = self.redis.info()
            
            return {
                "total_keys": len(all_keys),
                "layer_distribution": layer_stats,
                "memory_used": info.get("used_memory_human"),
                "connected_clients": info.get("connected_clients"),
                "hit_rate": "N/A",  # Would need tracking
                "layers": {
                    "L1": {"ttl": CacheLayer.TTL_MAP[CacheLayer.L1_CRITICAL], "description": "Critical real-time"},
                    "L2": {"ttl": CacheLayer.TTL_MAP[CacheLayer.L2_STANDARD], "description": "Standard data"},
                    "L3": {"ttl": CacheLayer.TTL_MAP[CacheLayer.L3_REPORTS], "description": "Reports & analytics"}
                }
            }
            
        except Exception as e:
            logger.error(f"Failed to get cache stats: {e}")
            return {"error": str(e)}


def cache_with_layer(
    layer: str = CacheLayer.L2_STANDARD,
    key_prefix: str = "",
    ttl: Optional[int] = None
):
    """
    Decorator for caching function results with specific layer
    
    Usage:
        @cache_with_layer(layer=CacheLayer.L1_CRITICAL, key_prefix="dashboard")
        async def get_dashboard_data():
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key from function name and arguments
            key_parts = [key_prefix or func.__name__]
            
            # Add args to key (skip first arg if it's 'self')
            func_args = args[1:] if args and hasattr(args[0], '__class__') else args
            if func_args:
                key_parts.append(str(func_args))
            if kwargs:
                key_parts.append(str(sorted(kwargs.items())))
            
            cache_key = hashlib.md5(":".join(key_parts).encode()).hexdigest()
            
            # Try to get from cache
            cache_manager = kwargs.get('cache_manager')
            if cache_manager:
                cached = await cache_manager.get(cache_key, layer)
                if cached is not None:
                    logger.debug(f"Returning cached result for {func.__name__}")
                    return cached
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Cache result
            if cache_manager and result is not None:
                await cache_manager.set(cache_key, result, layer, ttl)
            
            return result
        
        return wrapper
    return decorator


class CacheWarmer:
    """Proactive cache warming for frequently accessed data"""
    
    def __init__(self, cache_manager: AdvancedCacheManager):
        self.cache = cache_manager
        
    async def warm_dashboard_cache(self, materialized_views_manager):
        """Pre-warm dashboard caches"""
        try:
            logger.info("Warming dashboard cache...")
            
            # Get materialized views
            metrics = await materialized_views_manager.get_view("dashboard_metrics")
            
            if metrics:
                # Cache in L1 for immediate access
                await self.cache.set(
                    "dashboard:metrics",
                    metrics,
                    CacheLayer.L1_CRITICAL
                )
                logger.info("Dashboard cache warmed successfully")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Cache warming failed: {e}")
            return False
    
    async def warm_pms_cache(self, db):
        """Pre-warm PMS module caches"""
        try:
            logger.info("Warming PMS cache...")
            
            # Cache room statuses
            rooms = await db.rooms.find({"status": {"$ne": "out_of_order"}}).to_list(None)
            await self.cache.set(
                "pms:rooms:active",
                rooms,
                CacheLayer.L2_STANDARD
            )
            
            # Cache today's arrivals
            from datetime import datetime, timedelta
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            arrivals = await db.bookings.find({
                "check_in": {
                    "$gte": today,
                    "$lt": today + timedelta(days=1)
                }
            }).to_list(100)
            
            await self.cache.set(
                "pms:arrivals:today",
                arrivals,
                CacheLayer.L1_CRITICAL
            )
            
            logger.info("PMS cache warmed successfully")
            return True
            
        except Exception as e:
            logger.error(f"PMS cache warming failed: {e}")
            return False
