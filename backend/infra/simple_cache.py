"""
Simple In-Memory Cache System
Ultra-fast caching without Redis dependency
"""
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Dict, Optional


class SimpleCache:
    """Thread-safe in-memory cache"""
    
    def __init__(self):
        self._cache: Dict[str, Dict[str, Any]] = {}
    
    def set(self, key: str, value: Any, ttl: int = 60):
        """Set cache with TTL in seconds"""
        expires_at = datetime.utcnow() + timedelta(seconds=ttl)
        self._cache[key] = {
            'value': value,
            'expires_at': expires_at
        }
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired"""
        if key not in self._cache:
            return None
        
        cache_entry = self._cache[key]
        if datetime.utcnow() > cache_entry['expires_at']:
            # Expired, remove it
            del self._cache[key]
            return None
        
        return cache_entry['value']
    
    def delete(self, key: str):
        """Delete cache entry"""
        if key in self._cache:
            del self._cache[key]
    
    def clear(self):
        """Clear all cache"""
        self._cache.clear()
    
    def cleanup_expired(self):
        """Remove expired entries"""
        now = datetime.utcnow()
        expired_keys = [
            key for key, entry in self._cache.items()
            if now > entry['expires_at']
        ]
        for key in expired_keys:
            del self._cache[key]

# Global cache instance
simple_cache = SimpleCache()

def simple_cached(ttl: int = 60, key_prefix: str = ""):
    """Decorator for simple caching"""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Generate cache key from function name and args
            cache_key = f"{key_prefix}:{func.__name__}"
            
            # Try to get from cache
            cached_value = simple_cache.get(cache_key)
            if cached_value is not None:
                return cached_value
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Store in cache
            simple_cache.set(cache_key, result, ttl)
            
            return result
        return wrapper
    return decorator
