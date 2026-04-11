"""
Performance Optimization Endpoints
Enterprise-level optimizations for 550+ room properties
"""
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from advanced_cache import AdvancedCacheManager, CacheWarmer
from data_archival import DataArchivalManager
from materialized_views import MaterializedViewsManager

logger = logging.getLogger(__name__)

# Create router
optimization_router = APIRouter(prefix="/optimization", tags=["optimization"])

# Models
class ArchivalRequest(BaseModel):
    dry_run: bool = True
    threshold_days: int | None = None

class CacheInvalidation(BaseModel):
    pattern: str
    layer: str | None = None

class RefreshViewRequest(BaseModel):
    view_name: str | None = None  # If None, refresh all

# Initialize managers (will be set on app startup)
archival_manager = None
materialized_views_manager = None
cache_manager = None
cache_warmer = None

def init_optimization_managers(db, redis_client):
    """Initialize all optimization managers"""
    global archival_manager, materialized_views_manager, cache_manager, cache_warmer

    archival_manager = DataArchivalManager(db)
    materialized_views_manager = MaterializedViewsManager(db)
    cache_manager = AdvancedCacheManager(redis_client)
    cache_warmer = CacheWarmer(cache_manager)

    logger.info("✅ Optimization managers initialized")

# ============= DATA ARCHIVAL ENDPOINTS =============

@optimization_router.post("/archive/bookings")
async def archive_bookings(request: ArchivalRequest):
    """
    Archive old bookings to separate collection

    - **dry_run**: If true, only count records without moving them
    - **threshold_days**: Days threshold for archival (default: 365)
    """
    if not archival_manager:
        raise HTTPException(status_code=503, detail="Archival manager not initialized")

    if request.threshold_days:
        archival_manager.archive_threshold_days = request.threshold_days

    result = await archival_manager.archive_old_bookings(dry_run=request.dry_run)
    return result

@optimization_router.get("/archive/stats")
async def get_archive_stats():
    """Get statistics about data archival"""
    if not archival_manager:
        raise HTTPException(status_code=503, detail="Archival manager not initialized")

    return await archival_manager.get_archive_stats()

@optimization_router.post("/archive/setup")
async def setup_archive_indexes():
    """Setup indexes for archive collection"""
    if not archival_manager:
        raise HTTPException(status_code=503, detail="Archival manager not initialized")

    await archival_manager.setup_indexes()
    return {"message": "Archive indexes created successfully"}

# ============= MATERIALIZED VIEWS ENDPOINTS =============

@optimization_router.post("/views/refresh")
async def refresh_views(request: RefreshViewRequest = None):
    """
    Refresh materialized views

    - **view_name**: Specific view to refresh (default: all views)
    """
    if not materialized_views_manager:
        raise HTTPException(status_code=503, detail="Materialized views manager not initialized")

    if request and request.view_name:
        if request.view_name == "dashboard_metrics":
            result = await materialized_views_manager.refresh_dashboard_metrics()
        else:
            raise HTTPException(status_code=400, detail=f"Unknown view: {request.view_name}")
    else:
        result = await materialized_views_manager.refresh_all_views()

    return result

@optimization_router.get("/views/stats")
async def get_view_stats():
    """Get statistics about materialized views"""
    if not materialized_views_manager:
        raise HTTPException(status_code=503, detail="Materialized views manager not initialized")

    return await materialized_views_manager.get_view_stats()

@optimization_router.get("/views/{view_name}")
async def get_view(
    view_name: str,
    max_age_seconds: int = Query(300, description="Maximum age in seconds")
):
    """Get specific materialized view"""
    if not materialized_views_manager:
        raise HTTPException(status_code=503, detail="Materialized views manager not initialized")

    data = await materialized_views_manager.get_view(view_name, max_age_seconds)

    if data is None:
        raise HTTPException(status_code=404, detail="View not found or too old")

    return {
        "view_name": view_name,
        "data": data
    }

@optimization_router.post("/views/setup")
async def setup_view_indexes():
    """Setup indexes for materialized views"""
    if not materialized_views_manager:
        raise HTTPException(status_code=503, detail="Materialized views manager not initialized")

    await materialized_views_manager.setup_indexes()
    return {"message": "Materialized view indexes created successfully"}

# ============= CACHE ENDPOINTS =============

@optimization_router.get("/cache/stats")
async def get_cache_stats():
    """Get cache statistics"""
    if not cache_manager:
        raise HTTPException(status_code=503, detail="Cache manager not initialized")

    return await cache_manager.get_stats()

@optimization_router.post("/cache/invalidate")
async def invalidate_cache(request: CacheInvalidation):
    """
    Invalidate cache keys matching pattern

    - **pattern**: Pattern to match (e.g., "dashboard:*")
    - **layer**: Specific layer (optional)
    """
    if not cache_manager:
        raise HTTPException(status_code=503, detail="Cache manager not initialized")

    count = await cache_manager.invalidate_pattern(request.pattern)

    return {
        "invalidated_keys": count,
        "pattern": request.pattern
    }

@optimization_router.post("/cache/warm")
async def warm_cache(
    target: str = Query("dashboard", description="Target to warm: dashboard, pms, all")
):
    """
    Warm cache with frequently accessed data

    - **target**: What to warm (dashboard, pms, all)
    """
    if not cache_warmer or not materialized_views_manager:
        raise HTTPException(status_code=503, detail="Cache warmer not initialized")

    results = {}

    if target in ["dashboard", "all"]:
        results["dashboard"] = await cache_warmer.warm_dashboard_cache(materialized_views_manager)

    if target in ["pms", "all"]:
        # Get db from FastAPI app state
        # This would need to be injected properly
        results["pms"] = {"message": "PMS cache warming requires db injection"}

    return {
        "target": target,
        "results": results
    }

# ============= SYSTEM HEALTH ENDPOINTS =============

@optimization_router.get("/health")
async def optimization_health():
    """Check health of optimization systems"""
    health = {
        "archival": archival_manager is not None,
        "materialized_views": materialized_views_manager is not None,
        "cache": cache_manager is not None,
        "cache_warmer": cache_warmer is not None,
        "timestamp": datetime.utcnow().isoformat()
    }

    # Get detailed status if available
    if cache_manager:
        try:
            cache_stats = await cache_manager.get_stats()
            health["cache_details"] = {
                "total_keys": cache_stats.get("total_keys", 0),
                "memory_used": cache_stats.get("memory_used", "N/A")
            }
        except Exception as e:
            health["cache_details"] = {"error": str(e)}

    if materialized_views_manager:
        try:
            view_stats = await materialized_views_manager.get_view_stats()
            health["views_details"] = {
                "total_views": view_stats.get("total_views", 0)
            }
        except Exception as e:
            health["views_details"] = {"error": str(e)}

    return health

@optimization_router.post("/setup/all")
async def setup_all_optimizations():
    """Setup all optimization systems (indexes, etc.)"""
    results = {}

    if archival_manager:
        try:
            await archival_manager.setup_indexes()
            results["archival_indexes"] = "success"
        except Exception as e:
            results["archival_indexes"] = f"error: {e}"

    if materialized_views_manager:
        try:
            await materialized_views_manager.setup_indexes()
            results["view_indexes"] = "success"
        except Exception as e:
            results["view_indexes"] = f"error: {e}"

    # Initial cache warming
    if cache_warmer and materialized_views_manager:
        try:
            await cache_warmer.warm_dashboard_cache(materialized_views_manager)
            results["cache_warming"] = "success"
        except Exception as e:
            results["cache_warming"] = f"error: {e}"

    # Initial view refresh
    if materialized_views_manager:
        try:
            await materialized_views_manager.refresh_all_views()
            results["initial_refresh"] = "success"
        except Exception as e:
            results["initial_refresh"] = f"error: {e}"

    return {
        "message": "Optimization setup completed",
        "results": results,
        "timestamp": datetime.utcnow().isoformat()
    }
