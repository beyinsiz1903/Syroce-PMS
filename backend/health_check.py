"""
Comprehensive Health Check System
Kubernetes/Docker ready health endpoints
"""
from fastapi import APIRouter, Response, status, Request
from datetime import datetime
import psutil
import redis
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

health_router = APIRouter(prefix="/health", tags=["health"])

async def check_mongodb(db) -> Dict[str, Any]:
    """Check MongoDB connectivity and performance"""
    try:
        start_time = datetime.utcnow()
        
        # Ping database
        await db.command('ping')
        
        # Get server status
        server_status = await db.command('serverStatus')
        
        response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        return {
            "status": "healthy",
            "response_time_ms": round(response_time, 2),
            "connections": server_status.get("connections", {}).get("current", 0),
            "uptime_seconds": server_status.get("uptime", 0)
        }
    except Exception as e:
        logger.error(f"MongoDB health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

async def check_redis(redis_client: redis.Redis) -> Dict[str, Any]:
    """Check Redis connectivity and performance"""
    try:
        start_time = datetime.utcnow()
        
        # Ping Redis
        redis_client.ping()
        
        # Get info
        info = redis_client.info()
        
        response_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        return {
            "status": "healthy",
            "response_time_ms": round(response_time, 2),
            "connected_clients": info.get("connected_clients", 0),
            "used_memory": info.get("used_memory_human", "N/A"),
            "uptime_seconds": info.get("uptime_in_seconds", 0)
        }
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

def check_system_resources() -> Dict[str, Any]:
    """Check system resources"""
    try:
        cpu_percent = psutil.cpu_percent(interval=0)  # Instant reading, no wait
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "status": "healthy",
            "cpu": {
                "usage_percent": cpu_percent,
                "status": "ok" if cpu_percent < 80 else "warning" if cpu_percent < 95 else "critical"
            },
            "memory": {
                "total_gb": round(memory.total / (1024**3), 2),
                "used_gb": round(memory.used / (1024**3), 2),
                "usage_percent": memory.percent,
                "status": "ok" if memory.percent < 80 else "warning" if memory.percent < 95 else "critical"
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 2),
                "used_gb": round(disk.used / (1024**3), 2),
                "usage_percent": disk.percent,
                "status": "ok" if disk.percent < 80 else "warning" if disk.percent < 95 else "critical"
            }
        }
    except Exception as e:
        logger.error(f"System resource check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e)
        }

@health_router.get("/")
async def health_check_simple():
    """
    Simple health check endpoint
    Returns 200 if service is up
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "service": "hotel_pms"
    }

@health_router.get("/liveness")
async def liveness_probe():
    """
    Kubernetes liveness probe
    Checks if application is running
    """
    return Response(
        content="OK",
        status_code=status.HTTP_200_OK,
        media_type="text/plain"
    )

@health_router.get("/readiness")
async def readiness_probe(db=None, redis_client=None):
    """
    Kubernetes readiness probe
    Checks if application is ready to serve traffic
    """
    checks = {}
    all_healthy = True
    
    # Check MongoDB
    if db:
        mongo_health = await check_mongodb(db)
        checks["mongodb"] = mongo_health
        if mongo_health["status"] != "healthy":
            all_healthy = False
    
    # Check Redis
    if redis_client:
        redis_health = await check_redis(redis_client)
        checks["redis"] = redis_health
        if redis_health["status"] != "healthy":
            all_healthy = False
    
    # Check system resources
    system_health = check_system_resources()
    checks["system"] = system_health
    if system_health["status"] != "healthy":
        all_healthy = False
    
    status_code = status.HTTP_200_OK if all_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return Response(
        content="OK" if all_healthy else "NOT_READY",
        status_code=status_code,
        media_type="text/plain"
    )

@health_router.get("/detailed")
async def detailed_health_check(db=None, redis_client=None):
    """
    Detailed health check with all components
    """
    checks = {}
    overall_status = "healthy"
    
    # MongoDB check
    if db:
        mongo_health = await check_mongodb(db)
        checks["mongodb"] = mongo_health
        if mongo_health["status"] != "healthy":
            overall_status = "degraded"
    else:
        checks["mongodb"] = {"status": "not_configured"}
    
    # Redis check
    if redis_client:
        redis_health = await check_redis(redis_client)
        checks["redis"] = redis_health
        if redis_health["status"] != "healthy":
            overall_status = "degraded"
    else:
        checks["redis"] = {"status": "not_configured"}
    
    # System resources
    checks["system"] = check_system_resources()
    if checks["system"]["status"] != "healthy":
        overall_status = "degraded"
    
    # Check optimization systems
    try:
        from optimization_endpoints import archival_manager, materialized_views_manager, cache_manager
        
        checks["optimization"] = {
            "data_archival": archival_manager is not None,
            "materialized_views": materialized_views_manager is not None,
            "cache_manager": cache_manager is not None
        }
    except Exception:
        checks["optimization"] = {"status": "not_available"}
    
    response = {
        "status": overall_status,
        "timestamp": datetime.utcnow().isoformat(),
        "service": "hotel_pms",
        "version": "1.0.0",
        "checks": checks
    }
    
    status_code = status.HTTP_200_OK if overall_status == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return Response(
        content=str(response),
        status_code=status_code,
        media_type="application/json"
    )


@health_router.get("/db", include_in_schema=False)
@health_router.get("/db/", include_in_schema=False)
async def health_db_check(request: Request):
    """DB connectivity check.
    - No auth/guards
    - Fast fail
    - Useful for narrowing down 520 root cause
    """
    import time
    from fastapi.responses import ORJSONResponse

    t0 = time.time()
    try:
        db = request.app.state.db
        await db.command("ping")
        ms = int((time.time() - t0) * 1000)
        return ORJSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ok", "db": "ok", "latency_ms": ms},
        )
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        return ORJSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "degraded",
                "db": "down",
                "latency_ms": ms,
                "error": str(e),
            },
        )


@health_router.get("/startup")
async def startup_probe():
    """
    Kubernetes startup probe
    Checks if application has started successfully
    """
    # Simple check - if this endpoint responds, app has started
    return Response(
        content="STARTED",
        status_code=status.HTTP_200_OK,
        media_type="text/plain"
    )
