"""
Cached Endpoints Wrapper
Adds caching to frequently accessed endpoints
"""
from fastapi import APIRouter, HTTPException
from typing import Optional
from datetime import datetime, timedelta
import redis
from advanced_cache import AdvancedCacheManager, CacheLayer

# Initialize cache manager
redis_client = redis.Redis(
    host='127.0.0.1',
    port=6379,
    db=0,
    decode_responses=False
)

cache_manager = AdvancedCacheManager(redis_client)

cached_router = APIRouter(prefix="/api/cached", tags=["cached"])


async def get_with_cache(
    key: str,
    fetch_func,
    layer: str = CacheLayer.L2_STANDARD,
    ttl: Optional[int] = None
):
    """
    Generic cache wrapper for data fetching
    
    Args:
        key: Cache key
        fetch_func: Async function to fetch data if not in cache
        layer: Cache layer (L1, L2, or L3)
        ttl: Custom TTL (optional)
        
    Returns:
        Cached or fresh data
    """
    # Try to get from cache
    cached_data = await cache_manager.get(key, layer)
    
    if cached_data is not None:
        return cached_data
    
    # Fetch fresh data
    fresh_data = await fetch_func()
    
    # Store in cache
    await cache_manager.set(key, fresh_data, layer, ttl)
    
    return fresh_data


# ============= CACHED DASHBOARD ENDPOINTS =============

@cached_router.get("/dashboard/metrics")
async def get_dashboard_metrics_cached(db):
    """
    Cached dashboard metrics
    Uses materialized views with L1 cache (1 minute)
    """
    from materialized_views import MaterializedViewsManager
    
    async def fetch():
        views_manager = MaterializedViewsManager(db)
        return await views_manager.get_view("dashboard_metrics", max_age_seconds=60)
    
    return await get_with_cache(
        key="dashboard:metrics",
        fetch_func=fetch,
        layer=CacheLayer.L1_CRITICAL,
        ttl=60  # 1 minute
    )


@cached_router.get("/dashboard/occupancy")
async def get_occupancy_cached(db):
    """
    Cached occupancy data
    L1 cache (1 minute) for real-time feel
    """
    async def fetch():
        total_rooms = await db.rooms.count_documents({"status": {"$ne": "out_of_order"}})
        occupied_rooms = await db.bookings.count_documents({
            "status": "checked_in",
            "check_in": {"$lte": datetime.utcnow()},
            "check_out": {"$gte": datetime.utcnow()}
        })
        
        return {
            "total_rooms": total_rooms,
            "occupied_rooms": occupied_rooms,
            "available_rooms": total_rooms - occupied_rooms,
            "occupancy_rate": (occupied_rooms / total_rooms * 100) if total_rooms > 0 else 0
        }
    
    return await get_with_cache(
        key="dashboard:occupancy",
        fetch_func=fetch,
        layer=CacheLayer.L1_CRITICAL,
        ttl=60
    )


# ============= CACHED PMS ENDPOINTS =============

@cached_router.get("/pms/rooms")
async def get_rooms_cached(db, status: Optional[str] = None):
    """
    Cached rooms list
    L2 cache (5 minutes)
    """
    cache_key = f"pms:rooms:{status or 'all'}"
    
    async def fetch():
        query = {"status": status} if status else {}
        rooms = await db.rooms.find(query).to_list(None)
        return rooms
    
    return await get_with_cache(
        key=cache_key,
        fetch_func=fetch,
        layer=CacheLayer.L2_STANDARD,
        ttl=300  # 5 minutes
    )


@cached_router.get("/pms/rooms/available")
async def get_available_rooms_cached(db, check_in: str, check_out: str):
    """
    Cached available rooms
    L2 cache (2 minutes)
    """
    cache_key = f"pms:rooms:available:{check_in}:{check_out}"
    
    async def fetch():
        # Find rooms that are not booked for the given dates
        check_in_date = datetime.fromisoformat(check_in)
        check_out_date = datetime.fromisoformat(check_out)
        
        # Get all rooms
        all_rooms = await db.rooms.find({"status": {"$ne": "out_of_order"}}).to_list(None)
        
        # Get booked rooms for the period
        booked_bookings = await db.bookings.find({
            "status": {"$in": ["confirmed", "checked_in"]},
            "$or": [
                {
                    "check_in": {"$lte": check_out_date},
                    "check_out": {"$gte": check_in_date}
                }
            ]
        }).to_list(None)
        
        booked_room_ids = {b["room_id"] for b in booked_bookings}
        
        available_rooms = [r for r in all_rooms if str(r["_id"]) not in booked_room_ids]
        
        return available_rooms
    
    return await get_with_cache(
        key=cache_key,
        fetch_func=fetch,
        layer=CacheLayer.L2_STANDARD,
        ttl=120  # 2 minutes
    )


@cached_router.get("/pms/guests/frequent")
async def get_frequent_guests_cached(db, limit: int = 50):
    """
    Cached frequent guests
    L3 cache (1 hour) - changes infrequently
    """
    cache_key = f"pms:guests:frequent:{limit}"
    
    async def fetch():
        # Aggregate bookings by guest
        pipeline = [
            {
                "$group": {
                    "_id": "$guest_id",
                    "booking_count": {"$sum": 1},
                    "total_spent": {"$sum": "$total_amount"}
                }
            },
            {
                "$sort": {"booking_count": -1}
            },
            {
                "$limit": limit
            }
        ]
        
        frequent_guests = await db.bookings.aggregate(pipeline).to_list(limit)
        
        # Enrich with guest details
        for guest_stat in frequent_guests:
            guest = await db.guests.find_one({"_id": guest_stat["_id"]})
            if guest:
                guest_stat["guest_name"] = guest.get("name")
                guest_stat["guest_email"] = guest.get("email")
        
        return frequent_guests
    
    return await get_with_cache(
        key=cache_key,
        fetch_func=fetch,
        layer=CacheLayer.L3_REPORTS,
        ttl=3600  # 1 hour
    )


# ============= CACHED REPORTS =============

@cached_router.get("/reports/monthly-summary")
async def get_monthly_summary_cached(db, year: int, month: int):
    """
    Cached monthly summary
    L3 cache (1 hour)
    """
    cache_key = f"reports:monthly:{year}:{month}"
    
    async def fetch():
        import calendar
        
        # Calculate date range
        start_date = datetime(year, month, 1)
        last_day = calendar.monthrange(year, month)[1]
        end_date = datetime(year, month, last_day, 23, 59, 59)
        
        # Aggregate data
        bookings = await db.bookings.count_documents({
            "created_at": {"$gte": start_date, "$lte": end_date}
        })
        
        revenue_pipeline = [
            {
                "$match": {
                    "created_at": {"$gte": start_date, "$lte": end_date}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "total_revenue": {"$sum": "$total_amount"}
                }
            }
        ]
        
        revenue_result = await db.bookings.aggregate(revenue_pipeline).to_list(1)
        revenue = revenue_result[0]["total_revenue"] if revenue_result else 0
        
        return {
            "year": year,
            "month": month,
            "bookings_count": bookings,
            "total_revenue": revenue,
            "average_booking_value": revenue / bookings if bookings > 0 else 0
        }
    
    return await get_with_cache(
        key=cache_key,
        fetch_func=fetch,
        layer=CacheLayer.L3_REPORTS,
        ttl=3600  # 1 hour
    )


@cached_router.get("/reports/revenue-by-channel")
async def get_revenue_by_channel_cached(db, days: int = 30):
    """
    Cached revenue by channel report
    L3 cache (30 minutes)
    """
    cache_key = f"reports:revenue:channel:{days}"
    
    async def fetch():
        cutoff_date = datetime.utcnow() - timedelta(days=days)
        
        pipeline = [
            {
                "$match": {
                    "created_at": {"$gte": cutoff_date}
                }
            },
            {
                "$group": {
                    "_id": "$channel",
                    "bookings_count": {"$sum": 1},
                    "total_revenue": {"$sum": "$total_amount"}
                }
            },
            {
                "$sort": {"total_revenue": -1}
            }
        ]
        
        results = await db.bookings.aggregate(pipeline).to_list(None)
        
        return {
            "period_days": days,
            "channels": results
        }
    
    return await get_with_cache(
        key=cache_key,
        fetch_func=fetch,
        layer=CacheLayer.L3_REPORTS,
        ttl=1800  # 30 minutes
    )


# ============= CACHE MANAGEMENT ENDPOINTS =============

@cached_router.post("/cache/invalidate/{pattern}")
async def invalidate_cache_pattern(pattern: str):
    """
    Invalidate cache keys matching pattern
    
    Examples:
        - /cache/invalidate/dashboard:*
        - /cache/invalidate/pms:rooms:*
    """
    count = await cache_manager.invalidate_pattern(pattern)
    
    return {
        "success": True,
        "pattern": pattern,
        "invalidated_keys": count,
        "timestamp": datetime.utcnow().isoformat()
    }


@cached_router.post("/cache/invalidate/all")
async def invalidate_all_cache():
    """Invalidate all cache (use with caution!)"""
    count = await cache_manager.invalidate_pattern("*")
    
    return {
        "success": True,
        "invalidated_keys": count,
        "message": "All cache cleared",
        "timestamp": datetime.utcnow().isoformat()
    }


@cached_router.get("/cache/keys")
async def list_cache_keys(pattern: str = "*"):
    """List all cache keys matching pattern"""
    try:
        keys = redis_client.keys(f"pms:cache:*:{pattern}")
        
        key_list = []
        for key in keys:
            key_str = key.decode() if isinstance(key, bytes) else key
            ttl = redis_client.ttl(key)
            
            key_list.append({
                "key": key_str,
                "ttl": ttl,
                "expires_in": f"{ttl}s" if ttl > 0 else "expired"
            })
        
        return {
            "total_keys": len(key_list),
            "keys": key_list
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============= CACHE WARMING ENDPOINTS =============

@cached_router.post("/cache/warm/dashboard")
async def warm_dashboard_cache(db):
    """Warm dashboard cache proactively"""
    from materialized_views import MaterializedViewsManager
    from advanced_cache import CacheWarmer
    
    views_manager = MaterializedViewsManager(db)
    cache_warmer = CacheWarmer(cache_manager)
    
    result = await cache_warmer.warm_dashboard_cache(views_manager)
    
    return {
        "success": result,
        "message": "Dashboard cache warmed",
        "timestamp": datetime.utcnow().isoformat()
    }


@cached_router.post("/cache/warm/pms")
async def warm_pms_cache(db):
    """Warm PMS cache proactively"""
    from advanced_cache import CacheWarmer
    
    cache_warmer = CacheWarmer(cache_manager)
    result = await cache_warmer.warm_pms_cache(db)
    
    return {
        "success": result,
        "message": "PMS cache warmed",
        "timestamp": datetime.utcnow().isoformat()
    }


@cached_router.post("/cache/warm/all")
async def warm_all_cache(db):
    """Warm all caches"""
    results = {
        "dashboard": await warm_dashboard_cache(db),
        "pms": await warm_pms_cache(db)
    }
    
    return {
        "success": True,
        "results": results,
        "timestamp": datetime.utcnow().isoformat()
    }
