"""
Core: Cache utilities shared across domain routers.
"""
try:
    from cache_manager import BookingCache, DashboardCache, RoomCache, cache, cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator
    cache = None
    DashboardCache = None
    RoomCache = None
    BookingCache = None
