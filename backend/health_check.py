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


@health_router.get("/deep")
async def deep_health_check(request: Request):
    """
    OBS-001: Deep Health Check — production readiness probe.
    Returns status of MongoDB, Redis, outbox queue, and background workers.
    """
    import time
    from fastapi.responses import ORJSONResponse

    result = {
        "timestamp": datetime.utcnow().isoformat(),
        "service": "hotel_pms",
    }
    overall_ok = True

    # ── MongoDB ──
    t0 = time.time()
    try:
        db_inst = request.app.state.db
        await db_inst.command("ping")
        rs_status = await db_inst.client.admin.command("replSetGetStatus")
        members = rs_status.get("members", [])
        primary_ok = any(m.get("stateStr") == "PRIMARY" for m in members)
        result["mongo"] = {
            "status": "ok" if primary_ok else "degraded",
            "latency_ms": int((time.time() - t0) * 1000),
            "replica_set": rs_status.get("set", "unknown"),
            "primary": primary_ok,
        }
        if not primary_ok:
            overall_ok = False
    except Exception as e:
        result["mongo"] = {"status": "fail", "error": str(e)}
        overall_ok = False

    # ── Redis ──
    try:
        r = redis.Redis(host="localhost", port=6379, socket_timeout=2)
        r.ping()
        info = r.info("memory")
        result["redis"] = {
            "status": "ok",
            "used_memory": info.get("used_memory_human", "?"),
        }
    except Exception as e:
        result["redis"] = {"status": "fail", "error": str(e)}
        overall_ok = False

    # ── Outbox queue depth (OTA-002 enhanced) ──
    try:
        db_inst = request.app.state.db
        pending = await db_inst.outbox_events.count_documents({"status": "pending"})
        processing = await db_inst.outbox_events.count_documents({"status": "processing"})
        retry = await db_inst.outbox_events.count_documents({"status": "retry"})
        failed = await db_inst.outbox_events.count_documents({"status": "failed"})

        cutoff_24h = (datetime.utcnow() - __import__("datetime").timedelta(hours=24)).isoformat()
        processed_24h = await db_inst.outbox_events.count_documents({
            "status": "processed",
            "processed_at": {"$gte": cutoff_24h},
        })

        oldest_pending = await db_inst.outbox_events.find_one(
            {"status": {"$in": ["pending", "retry"]}},
            {"_id": 0, "created_at": 1},
            sort=[("created_at", 1)],
        )
        oldest_seconds = None
        if oldest_pending and oldest_pending.get("created_at"):
            try:
                from datetime import timezone as _tz
                created = datetime.fromisoformat(oldest_pending["created_at"])
                if created.tzinfo is None:
                    created = created.replace(tzinfo=_tz.utc)
                oldest_seconds = round((datetime.now(_tz.utc) - created).total_seconds(), 1)
            except Exception:
                pass

        last_processed = await db_inst.outbox_events.find_one(
            {"status": "processed"},
            {"_id": 0, "processed_at": 1},
            sort=[("processed_at", -1)],
        )

        # Provider failure breakdown
        pipeline = [
            {"$match": {"status": "failed"}},
            {"$group": {"_id": "$provider", "count": {"$sum": 1}}},
        ]
        provider_failures = {}
        async for doc in db_inst.outbox_events.aggregate(pipeline):
            provider_failures[doc["_id"] or "fan-out"] = doc["count"]

        outbox_status = "ok"
        if failed >= 100:
            outbox_status = "critical"
            overall_ok = False
        elif failed >= 10 or (oldest_seconds and oldest_seconds > 600):
            outbox_status = "degraded"

        result["outbox"] = {
            "status": outbox_status,
            "pending": pending,
            "processing": processing,
            "retry": retry,
            "failed": failed,
            "processed_24h": processed_24h,
            "oldest_pending_seconds": oldest_seconds,
            "last_processed_at": last_processed.get("processed_at") if last_processed else None,
            "provider_failures": provider_failures,
        }
    except Exception as e:
        result["outbox"] = {"status": "unknown", "error": str(e)}

    # ── Night audit ──
    try:
        db_inst = request.app.state.db
        last_audit = await db_inst.night_audit_logs.find_one(
            {}, {"_id": 0, "business_date": 1, "completed_at": 1},
            sort=[("completed_at", -1)],
        )
        result["night_audit"] = {
            "last_run": last_audit.get("completed_at") if last_audit else None,
            "last_date": last_audit.get("business_date") if last_audit else None,
        }
    except Exception:
        result["night_audit"] = {"last_run": None}

    # ── DATA-001: Import bridge metrics ──
    try:
        db_inst = request.app.state.db
        imp_coll = db_inst.imported_reservations
        imp_pending = await imp_coll.count_documents({"import_status": "pending_auto_import"})
        imp_processing = await imp_coll.count_documents({"import_status": "processing"})
        imp_retry = await imp_coll.count_documents({"import_status": "retry"})
        imp_review = await imp_coll.count_documents({"import_status": "review_required"})
        imp_failed = await imp_coll.count_documents({"import_status": "failed"})

        imp_oldest = await imp_coll.find_one(
            {"import_status": {"$in": ["pending_auto_import", "retry"]}},
            {"_id": 0, "created_at": 1},
            sort=[("created_at", 1)],
        )
        imp_oldest_seconds = None
        if imp_oldest and imp_oldest.get("created_at"):
            try:
                from datetime import timezone as _tz2
                cr = datetime.fromisoformat(imp_oldest["created_at"])
                if cr.tzinfo is None:
                    cr = cr.replace(tzinfo=_tz2.utc)
                imp_oldest_seconds = round((datetime.now(_tz2.utc) - cr).total_seconds(), 1)
            except Exception:
                pass

        imp_last = await imp_coll.find_one(
            {"import_status": "imported"},
            {"_id": 0, "imported_at": 1},
            sort=[("imported_at", -1)],
        )

        imp_pipeline = [
            {"$match": {"import_status": {"$in": ["failed", "review_required"]}}},
            {"$group": {"_id": "$provider", "count": {"$sum": 1}}},
        ]
        imp_provider_failures = {}
        async for doc in imp_coll.aggregate(imp_pipeline):
            imp_provider_failures[doc["_id"] or "unknown"] = doc["count"]

        imp_status = "ok"
        if imp_failed >= 50:
            imp_status = "critical"
            overall_ok = False
        elif imp_failed >= 5 or imp_review >= 20 or (imp_oldest_seconds and imp_oldest_seconds > 600):
            imp_status = "degraded"

        result["import_bridge"] = {
            "status": imp_status,
            "pending_auto_import": imp_pending,
            "processing": imp_processing,
            "retry": imp_retry,
            "review_required": imp_review,
            "failed": imp_failed,
            "oldest_pending_seconds": imp_oldest_seconds,
            "last_imported_at": imp_last.get("imported_at") if imp_last else None,
            "provider_failures": imp_provider_failures,
        }
    except Exception as e:
        result["import_bridge"] = {"status": "unknown", "error": str(e)}

    result["overall"] = "ok" if overall_ok else "degraded"
    sc = status.HTTP_200_OK if overall_ok else status.HTTP_503_SERVICE_UNAVAILABLE
    return ORJSONResponse(status_code=sc, content=result)
