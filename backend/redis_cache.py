"""
Redis-based Ultra-Fast Cache System
%100 Performance with Distributed Caching
"""
import redis
from typing import Any, Optional, Callable
from functools import wraps
import orjson

class RedisCache:
    """Redis-based cache for ultra-fast distributed caching"""
    
    def __init__(self, host='127.0.0.1', port=6379, db=0):
        self.redis_client = redis.Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=False,  # We'll handle encoding
            socket_connect_timeout=1,
            socket_timeout=1,
            max_connections=100
        )
        self._hits = 0
        self._misses = 0
    
    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate cache key"""
        key_parts = [prefix]
        
        # Add args
        for arg in args:
            if hasattr(arg, 'tenant_id'):
                key_parts.append(f"t:{arg.tenant_id}")
            elif hasattr(arg, 'id'):
                key_parts.append(f"u:{arg.id}")
        
        # Add kwargs
        for k, v in sorted(kwargs.items()):
            if isinstance(v, (str, int, float, bool)) and v is not None:
                key_parts.append(f"{k}:{v}")
        
        key_str = ":".join(str(k) for k in key_parts)
        return f"fastapi:{key_str}"
    
    def get(self, key: str) -> Optional[Any]:
        """Get from Redis cache"""
        try:
            data = self.redis_client.get(key)
            if data:
                self._hits += 1
                return orjson.loads(data)
            self._misses += 1
            return None
        except Exception as e:
            print(f"Redis get error: {e}")
            self._misses += 1
            return None
    
    def set(self, key: str, value: Any, ttl: int = 60):
        """Set in Redis cache with TTL"""
        try:
            serialized = orjson.dumps(value)
            self.redis_client.setex(key, ttl, serialized)
        except Exception as e:
            print(f"Redis set error: {e}")
    
    def delete(self, key: str):
        """Delete from cache"""
        try:
            self.redis_client.delete(key)
        except Exception as e:
            print(f"Redis delete error: {e}")
    
    def clear_pattern(self, pattern: str):
        """Clear all keys matching pattern"""
        try:
            keys = self.redis_client.keys(pattern)
            if keys:
                self.redis_client.delete(*keys)
        except Exception as e:
            print(f"Redis clear pattern error: {e}")
    
    def get_stats(self):
        """Get cache statistics"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        
        try:
            info = self.redis_client.info('memory')
            memory_used = info.get('used_memory_human', 'N/A')
        except:
            memory_used = 'N/A'
        
        return {
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': round(hit_rate, 2),
            'memory_used': memory_used,
            'connected': self.redis_client.ping()
        }

# Global Redis cache instance
redis_cache = None

def init_redis_cache():
    """Initialize Redis cache"""
    global redis_cache
    try:
        redis_cache = RedisCache()
        if redis_cache.redis_client.ping():
            print("✅ Redis cache initialized successfully")
            return redis_cache
    except Exception as e:
        print(f"⚠️ Redis initialization failed: {e}")
        redis_cache = None
    return redis_cache

def redis_cached(ttl: int = 30, key_prefix: str = ""):
    """Redis cache decorator for ultra-fast responses"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            if not redis_cache:
                # Fallback: no cache
                return await func(*args, **kwargs)
            
            # Generate cache key
            prefix = key_prefix or func.__name__
            cache_key = redis_cache._generate_key(prefix, *args, **kwargs)
            
            # Try cache
            cached = redis_cache.get(cache_key)
            if cached is not None:
                return cached
            
            # Cache miss - execute function
            result = await func(*args, **kwargs)
            
            # Store in cache
            redis_cache.set(cache_key, result, ttl)
            
            return result
        
        return wrapper
    return decorator
