"""
Ultra-Fast Caching System for API Responses
In-memory caching without Redis dependency
"""
from functools import wraps
from typing import Any, Dict, Optional
import time
import hashlib

class UltraCache:
    """Ultra-fast in-memory cache with automatic cleanup"""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._last_cleanup = time.time()
    
    def _generate_key(self, prefix: str, *args, **kwargs) -> str:
        """Generate cache key from function args"""
        # Create a stable hash from args and kwargs
        key_data = f"{prefix}:{str(args)}:{str(sorted(kwargs.items()))}"
        return hashlib.md5(key_data.encode()).hexdigest()[:16]
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if key not in self._cache:
            return None
        
        entry = self._cache[key]
        if time.time() > entry['expires']:
            del self._cache[key]
            return None
        
        return entry['value']
    
    def set(self, key: str, value: Any, ttl: int):
        """Set value in cache with TTL"""
        self._cache[key] = {
            'value': value,
            'expires': time.time() + ttl
        }
        
        # Auto cleanup every 5 minutes
        if time.time() - self._last_cleanup > 300:
            self._cleanup()
    
    def _cleanup(self):
        """Remove expired entries"""
        now = time.time()
        expired = [k for k, v in self._cache.items() if now > v['expires']]
        for k in expired:
            del self._cache[k]
        self._last_cleanup = now
    
    def clear(self):
        """Clear all cache"""
        self._cache.clear()

# Global cache instance
ultra_cache = UltraCache()

def ultra_cached(ttl: int = 30):
    """Ultra-fast cache decorator"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key
            cache_key = ultra_cache._generate_key(func.__name__, *args, **kwargs)
            
            # Try cache
            cached = ultra_cache.get(cache_key)
            if cached is not None:
                return cached
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Cache result
            ultra_cache.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator
