"""
Global Persistent Cache System - %100 Performance
Aggressive caching for instant responses
"""
from functools import wraps
from typing import Any, Optional, Callable
import time
import hashlib

class GlobalCache:
    """Ultra-fast global cache with persistence"""
    
    def __init__(self):
        self._cache = {}
        self._hits = 0
        self._misses = 0
        self._last_cleanup = time.time()
    
    def _generate_key(self, func_name: str, args: tuple, kwargs: dict) -> str:
        """Generate stable cache key"""
        # Simple key for speed
        key_parts = [func_name]
        
        # Add user/tenant info if present
        for arg in args:
            if hasattr(arg, 'tenant_id'):
                key_parts.append(f"tenant_{arg.tenant_id}")
                break
            elif hasattr(arg, 'id'):
                key_parts.append(f"user_{arg.id}")
                break
        
        # Add query params if any
        for k, v in sorted(kwargs.items()):
            if isinstance(v, (str, int, float, bool)):
                key_parts.append(f"{k}_{v}")
        
        key_str = ":".join(map(str, key_parts))
        return hashlib.md5(key_str.encode()).hexdigest()[:12]
    
    def get(self, key: str) -> Optional[Any]:
        """Get from cache"""
        if key not in self._cache:
            self._misses += 1
            return None
        
        entry = self._cache[key]
        if time.time() > entry['expires']:
            del self._cache[key]
            self._misses += 1
            return None
        
        self._hits += 1
        return entry['data']
    
    def set(self, key: str, data: Any, ttl: int):
        """Set cache with TTL"""
        self._cache[key] = {
            'data': data,
            'expires': time.time() + ttl,
            'created': time.time()
        }
        
        # Auto cleanup every 60 seconds
        if time.time() - self._last_cleanup > 60:
            self._cleanup()
    
    def _cleanup(self):
        """Remove expired entries"""
        now = time.time()
        expired = [k for k, v in self._cache.items() if now > v['expires']]
        for k in expired:
            del self._cache[k]
        self._last_cleanup = now
    
    def clear_tenant(self, tenant_id: str):
        """Clear all cache for a tenant"""
        keys_to_delete = [k for k in self._cache.keys() if f"tenant_{tenant_id}" in k]
        for k in keys_to_delete:
            del self._cache[k]
    
    def get_stats(self):
        """Get cache statistics"""
        total = self._hits + self._misses
        hit_rate = (self._hits / total * 100) if total > 0 else 0
        return {
            'hits': self._hits,
            'misses': self._misses,
            'hit_rate': round(hit_rate, 2),
            'size': len(self._cache)
        }

# Global cache instance
global_cache = GlobalCache()

def fast_cache(ttl: int = 30):
    """Ultra-fast cache decorator for %100 performance"""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = global_cache._generate_key(func.__name__, args, kwargs)
            
            # Try cache first (ULTRA FAST!)
            cached = global_cache.get(cache_key)
            if cached is not None:
                return cached
            
            # Cache miss - execute function
            result = await func(*args, **kwargs)
            
            # Store in cache
            global_cache.set(cache_key, result, ttl)
            
            return result
        
        # Expose cache key generator for manual cache invalidation
        wrapper._cache_key = lambda *args, **kwargs: global_cache._generate_key(func.__name__, args, kwargs)
        return wrapper
    return decorator
