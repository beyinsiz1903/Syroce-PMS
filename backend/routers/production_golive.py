"""
Production Go-Live Router — All endpoints for production readiness validation,
environment configuration, MongoDB health, worker runtime, provider activation,
observability go-live, backup DR validation, security checklist, and readiness score.
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional
from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/production-golive", tags=["production-golive"])


# ── Production Readiness (Top-Level) ──────────────────────────────

@router.get("/readiness")
async def get_readiness(current_user: User = Depends(get_current_user)):
    """Full production readiness validation — returns READY / DEGRADED / NOT_READY."""
    from infra.readiness_validator import readiness_validator
    return await readiness_validator.validate()


@router.get("/summary")
async def get_golive_summary(current_user: User = Depends(get_current_user)):
    """Complete production go-live dashboard data — aggregates all subsystems."""
    from infra.readiness_validator import readiness_validator
    from infra.production_config import production_config
    from infra.mongo_production import mongo_validator
    from infra.provider_activation import provider_manager
    from infra.security_checklist import security_checklist

    readiness = await readiness_validator.validate()
    config_validation = production_config.validate_all()
    mongo_report = await mongo_validator.get_full_report()
    provider_status = provider_manager.get_all_provider_status()
    security_result = await security_checklist.run_full_checklist()

    # Worker summary
    from infra.worker_queue import worker_queue_manager
    worker_data = worker_queue_manager.get_worker_summary()

    # Backup status
    from infra.backup_manager import backup_manager
    backup_data = backup_manager.get_status()

    # Observability
    from infra.cloud_observability import otel_tracer, sentry_integration, cloud_metrics
    observability_data = {
        "otel": otel_tracer.get_status(),
        "sentry": sentry_integration.get_status(),
        "metrics": cloud_metrics.get_summary(),
    }

    # Redis
    from infra.redis_cluster import redis_cluster
    redis_data = {
        "mode": redis_cluster.mode,
        "connected": redis_cluster.connected,
        "health": await redis_cluster.health_check(),
        "metrics": redis_cluster.get_metrics(),
    }

    return {
        "readiness": readiness,
        "configuration": config_validation,
        "redis": redis_data,
        "mongodb": mongo_report,
        "workers": worker_data,
        "providers": provider_status,
        "backup": backup_data,
        "observability": observability_data,
        "security": security_result,
    }


# ── Environment Configuration ─────────────────────────────────────

@router.get("/config/validate")
async def validate_config(current_user: User = Depends(get_current_user)):
    """Full environment variable validation."""
    from infra.production_config import production_config
    return production_config.validate_all()


@router.get("/config/inspect")
async def inspect_config(current_user: User = Depends(get_current_user)):
    """Masked configuration inspection."""
    from infra.production_config import production_config
    return production_config.get_masked_config()


@router.get("/config/startup-check")
async def startup_check(current_user: User = Depends(get_current_user)):
    """Startup configuration check — critical variables only."""
    from infra.production_config import production_config
    return production_config.startup_check()


@router.get("/config/leak-scan")
async def leak_scan(current_user: User = Depends(get_current_user)):
    """Scan for potential secret leakage."""
    from infra.production_config import production_config
    return production_config.detect_leaked_secrets()


# ── Redis Production ──────────────────────────────────────────────

@router.get("/redis/cluster-validation")
async def redis_cluster_validation(current_user: User = Depends(get_current_user)):
    """Redis cluster connection validation with detailed metrics."""
    from infra.redis_cluster import redis_cluster
    from infra.distributed_lock import lock_manager
    health = await redis_cluster.health_check()
    return {
        "mode": redis_cluster.mode,
        "connected": redis_cluster.connected,
        "health": health,
        "metrics": redis_cluster.get_metrics(),
        "lock_metrics": lock_manager.get_metrics(),
        "pool_config": {
            "max_connections": int(redis_cluster._max_connections),
        },
    }


@router.get("/redis/pubsub-health")
async def redis_pubsub_health(current_user: User = Depends(get_current_user)):
    """Redis pub/sub health monitoring."""
    from infra.redis_cluster import redis_cluster
    metrics = redis_cluster.get_metrics()
    return {
        "connected": redis_cluster.connected,
        "pubsub_messages": metrics.get("pubsub_messages", 0),
        "mode": redis_cluster.mode,
        "status": "active" if redis_cluster.connected else "inactive",
    }


@router.get("/redis/lock-safety")
async def redis_lock_safety(current_user: User = Depends(get_current_user)):
    """Distributed lock safety check."""
    from infra.distributed_lock import lock_manager
    return {
        "metrics": lock_manager.get_metrics(),
        "active_locks": lock_manager.get_active_locks(),
        "safety_status": "operational",
    }


# ── MongoDB Production ────────────────────────────────────────────

@router.get("/mongo/health")
async def mongo_health(current_user: User = Depends(get_current_user)):
    """Comprehensive MongoDB production health report."""
    from infra.mongo_production import mongo_validator
    return await mongo_validator.get_full_report()


@router.get("/mongo/pool")
async def mongo_pool(current_user: User = Depends(get_current_user)):
    """MongoDB connection pool information."""
    from infra.mongo_production import mongo_validator
    return await mongo_validator.get_connection_pool_info()


@router.get("/mongo/replica-set")
async def mongo_replica_set(current_user: User = Depends(get_current_user)):
    """Replica set detection and health."""
    from infra.mongo_production import mongo_validator
    return await mongo_validator.detect_replica_set()


@router.get("/mongo/indexes")
async def mongo_indexes(current_user: User = Depends(get_current_user)):
    """Index validation for critical collections."""
    from infra.mongo_production import mongo_validator
    return await mongo_validator.validate_indexes()


@router.get("/mongo/slow-queries")
async def mongo_slow_queries(
    threshold_ms: int = Query(100, ge=10, le=5000),
    current_user: User = Depends(get_current_user),
):
    """Slow query metrics."""
    from infra.mongo_production import mongo_validator
    return await mongo_validator.get_slow_query_metrics(threshold_ms)


@router.get("/mongo/schema-drift")
async def mongo_schema_drift(current_user: User = Depends(get_current_user)):
    """Schema drift detection for critical collections."""
    from infra.mongo_production import mongo_validator
    return await mongo_validator.detect_schema_drift()


@router.get("/mongo/collections")
async def mongo_collections(current_user: User = Depends(get_current_user)):
    """Collection health summary."""
    from infra.mongo_production import mongo_validator
    return await mongo_validator.get_collection_health()


# ── Worker Runtime ────────────────────────────────────────────────

@router.get("/workers/validation")
async def worker_validation(current_user: User = Depends(get_current_user)):
    """Worker runtime validation — heartbeat, queue backlog, stuck tasks."""
    from infra.worker_queue import worker_queue_manager
    return {
        "summary": worker_queue_manager.get_worker_summary(),
        "queues": worker_queue_manager.get_queue_status(),
        "stuck_tasks": worker_queue_manager.get_stuck_task_candidates(),
        "failure_archive": worker_queue_manager.get_failure_archive(10),
        "status": "operational",
    }


@router.get("/workers/scaling-readiness")
async def worker_scaling_readiness(current_user: User = Depends(get_current_user)):
    """Worker scaling readiness check."""
    from infra.worker_queue import worker_queue_manager
    summary = worker_queue_manager.get_worker_summary()
    return {
        "total_queues": summary.get("total_queues", 0),
        "queue_definitions": summary.get("queues", {}),
        "scaling_ready": summary.get("total_queues", 0) > 0,
        "recommendation": "Scale workers per queue based on load",
    }


# ── Provider Activation ──────────────────────────────────────────

@router.get("/providers/status")
async def provider_status(current_user: User = Depends(get_current_user)):
    """All messaging provider status with delivery metrics."""
    from infra.provider_activation import provider_manager
    return provider_manager.get_all_provider_status()


@router.get("/providers/validate")
async def provider_validate(current_user: User = Depends(get_current_user)):
    """Validate all provider credentials."""
    from infra.provider_activation import provider_manager
    return await provider_manager.get_full_report()


@router.get("/providers/delivery-metrics")
async def provider_delivery_metrics(current_user: User = Depends(get_current_user)):
    """Delivery success rates and latency metrics."""
    from infra.provider_activation import provider_manager
    return provider_manager.get_delivery_metrics()


# ── Observability Go-Live ────────────────────────────────────────

@router.get("/observability/validation")
async def observability_validation(current_user: User = Depends(get_current_user)):
    """Observability stack validation — OTel, Sentry, Prometheus, Grafana."""
    from infra.cloud_observability import otel_tracer, sentry_integration, cloud_metrics

    return {
        "otel": {
            **otel_tracer.get_status(),
            "export_validation": "active" if otel_tracer.get_status().get("active") else "inactive",
        },
        "sentry": {
            **sentry_integration.get_status(),
            "tracking_validation": "active" if sentry_integration.get_status().get("active") else "inactive",
        },
        "prometheus_metrics": cloud_metrics.get_summary(),
        "grafana_dashboard": {
            "template_available": True,
            "path": "/ops/grafana/dashboard.json",
        },
        "overall_status": "active" if (
            otel_tracer.get_status().get("active") or sentry_integration.get_status().get("active")
        ) else "inactive",
    }


@router.get("/observability/key-metrics")
async def observability_key_metrics(current_user: User = Depends(get_current_user)):
    """Key production metrics — API latency, event throughput, queue lag."""
    from infra.cloud_observability import cloud_metrics
    summary = cloud_metrics.get_summary()
    return {
        "api_latency": summary.get("api_latency", {}),
        "event_throughput": summary.get("event_throughput", {}),
        "worker_queue_lag": summary.get("worker_queue_lag", {}),
        "messaging_delivery_rate": summary.get("messaging_delivery_rate", {}),
        "collected_at": summary.get("collected_at", None),
    }


# ── Backup & DR Validation ───────────────────────────────────────

@router.get("/backup/validation")
async def backup_validation(current_user: User = Depends(get_current_user)):
    """Backup system validation — scheduled success, retention, restore simulation."""
    from infra.backup_manager import backup_manager
    status = backup_manager.get_status()
    history = backup_manager.get_history(5)

    last_backup = history[0] if history else None
    return {
        "enabled": status.get("enabled", False),
        "status": status,
        "history": history,
        "last_backup": last_backup,
        "rpo_target": "24h",
        "rto_target": "4h",
        "retention_policy": {
            "days": status.get("retention_days", 30),
        },
        "restore_test_available": True,
        "overall_status": "operational" if status.get("enabled") else "disabled",
    }


# ── Security Checklist ───────────────────────────────────────────

@router.get("/security/checklist")
async def security_full_checklist(current_user: User = Depends(get_current_user)):
    """Complete security go-live checklist."""
    from infra.security_checklist import security_checklist
    return await security_checklist.run_full_checklist()


@router.get("/security/tenant-isolation")
async def security_tenant_isolation(current_user: User = Depends(get_current_user)):
    """Tenant isolation validation."""
    from infra.security_checklist import security_checklist
    return await security_checklist.check_tenant_isolation()


@router.get("/security/rbac")
async def security_rbac(current_user: User = Depends(get_current_user)):
    """RBAC validation."""
    from infra.security_checklist import security_checklist
    return await security_checklist.check_rbac()
