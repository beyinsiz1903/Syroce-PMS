"""
Infrastructure Hardening Router — API endpoints for all infrastructure
hardening components: containers, Redis cluster, workers, secrets,
backups, observability, scaling, and unified dashboard data.
"""
from fastapi import APIRouter, Depends, Query, BackgroundTasks
from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/infra", tags=["infrastructure-hardening"])


# ── Unified Dashboard Summary ──────────────────────────────────────

@router.get("/summary")
async def get_infrastructure_summary(current_user: User = Depends(get_current_user)):
    """Complete infrastructure hardening dashboard data."""
    from infra.redis_cluster import redis_cluster
    from infra.worker_queue import worker_queue_manager
    from infra.secrets_manager import secrets_manager
    from infra.backup_manager import backup_manager
    from infra.cloud_observability import otel_tracer, sentry_integration, cloud_metrics
    from infra.horizontal_scaling import scaling_manager
    from infra.distributed_lock import lock_manager

    redis_health = await redis_cluster.health_check()
    secrets_health = await secrets_manager.health_check()
    scaling_summary = await scaling_manager.get_scaling_summary()

    return {
        "redis_cluster": {
            "mode": redis_cluster.mode,
            "connected": redis_cluster.connected,
            "health": redis_health,
            "metrics": redis_cluster.get_metrics(),
        },
        "distributed_locks": lock_manager.get_metrics(),
        "worker_queues": worker_queue_manager.get_worker_summary(),
        "secrets": secrets_health,
        "backup": backup_manager.get_status(),
        "observability": {
            "otel": otel_tracer.get_status(),
            "sentry": sentry_integration.get_status(),
            "cloud_metrics": cloud_metrics.get_summary(),
        },
        "scaling": scaling_summary,
        "container": _get_container_info(),
    }


# ── Redis Cluster ──────────────────────────────────────────────────

@router.get("/redis/health")
async def redis_health(current_user: User = Depends(get_current_user)):
    from infra.redis_cluster import redis_cluster
    return await redis_cluster.health_check()


@router.get("/redis/metrics")
async def redis_metrics(current_user: User = Depends(get_current_user)):
    from infra.redis_cluster import redis_cluster
    return redis_cluster.get_metrics()


@router.get("/redis/locks")
async def redis_locks(current_user: User = Depends(get_current_user)):
    from infra.distributed_lock import lock_manager
    return {
        "metrics": lock_manager.get_metrics(),
        "active_locks": lock_manager.get_active_locks(),
    }


# ── Worker Queues ──────────────────────────────────────────────────

@router.get("/workers/summary")
async def worker_summary(current_user: User = Depends(get_current_user)):
    from infra.worker_queue import worker_queue_manager
    return worker_queue_manager.get_worker_summary()


@router.get("/workers/queues")
async def worker_queues(current_user: User = Depends(get_current_user)):
    from infra.worker_queue import worker_queue_manager
    return worker_queue_manager.get_queue_status()


@router.get("/workers/failures")
async def worker_failures(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    from infra.worker_queue import worker_queue_manager
    return worker_queue_manager.get_failure_archive(limit)


@router.get("/workers/stuck")
async def worker_stuck_tasks(current_user: User = Depends(get_current_user)):
    from infra.worker_queue import worker_queue_manager
    return worker_queue_manager.get_stuck_task_candidates()


# ── Secrets Management ─────────────────────────────────────────────

@router.get("/secrets/health")
async def secrets_health(current_user: User = Depends(get_current_user)):
    from infra.secrets_manager import secrets_manager
    return await secrets_manager.health_check()


@router.get("/secrets/audit")
async def secrets_audit(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    from infra.secrets_manager import secrets_manager
    return {
        "access_log": secrets_manager.get_access_log(limit),
        "metrics": secrets_manager.get_metrics(),
    }


# ── Backup & DR ────────────────────────────────────────────────────

@router.get("/backup/status")
async def backup_status(current_user: User = Depends(get_current_user)):
    from infra.backup_manager import backup_manager
    return backup_manager.get_status()


@router.get("/backup/history")
async def backup_history(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    from infra.backup_manager import backup_manager
    return backup_manager.get_history(limit)


@router.post("/backup/trigger")
async def trigger_backup(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
):
    from infra.backup_manager import backup_manager
    background_tasks.add_task(backup_manager.create_backup, "manual")
    return {"status": "backup_triggered", "message": "Backup started in background"}


@router.post("/backup/test-restore/{backup_id}")
async def test_restore(
    backup_id: str,
    current_user: User = Depends(get_current_user),
):
    from infra.backup_manager import backup_manager
    return await backup_manager.test_restore(backup_id)


@router.post("/backup/cleanup")
async def cleanup_backups(current_user: User = Depends(get_current_user)):
    from infra.backup_manager import backup_manager
    return await backup_manager.cleanup_old_backups()


# ── Cloud Observability ────────────────────────────────────────────

@router.get("/observability/status")
async def observability_status(current_user: User = Depends(get_current_user)):
    from infra.cloud_observability import otel_tracer, sentry_integration, cloud_metrics
    return {
        "otel": otel_tracer.get_status(),
        "sentry": sentry_integration.get_status(),
        "metrics_summary": cloud_metrics.get_summary(),
    }


@router.get("/observability/metrics")
async def observability_cloud_metrics(current_user: User = Depends(get_current_user)):
    from infra.cloud_observability import cloud_metrics
    return cloud_metrics.get_summary()


# ── Horizontal Scaling ─────────────────────────────────────────────

@router.get("/scaling/summary")
async def scaling_summary(current_user: User = Depends(get_current_user)):
    from infra.horizontal_scaling import scaling_manager
    return await scaling_manager.get_scaling_summary()


@router.get("/scaling/instances")
async def scaling_instances(current_user: User = Depends(get_current_user)):
    from infra.horizontal_scaling import scaling_manager
    return await scaling_manager.get_active_instances()


@router.get("/scaling/stateless-check")
async def stateless_check(current_user: User = Depends(get_current_user)):
    from infra.horizontal_scaling import scaling_manager
    return scaling_manager.stateless_validation()


@router.get("/scaling/readiness")
async def scaling_readiness():
    """Load balancer readiness probe (no auth required)."""
    from infra.horizontal_scaling import scaling_manager
    return scaling_manager.readiness_check()


# ── Container Info ─────────────────────────────────────────────────

@router.get("/container/info")
async def container_info(current_user: User = Depends(get_current_user)):
    return _get_container_info()


def _get_container_info() -> dict:
    """Detect container environment information."""
    import os
    import platform

    is_docker = os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv")
    is_k8s = bool(os.environ.get("KUBERNETES_SERVICE_HOST"))

    return {
        "is_containerized": is_docker or is_k8s,
        "is_kubernetes": is_k8s,
        "hostname": platform.node(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "instance_id": os.environ.get("INSTANCE_ID", "unknown"),
        "environment_vars_present": {
            "MONGO_URL": bool(os.environ.get("MONGO_URL")),
            "REDIS_URL": bool(os.environ.get("REDIS_URL")),
            "SENTRY_DSN": bool(os.environ.get("SENTRY_DSN")),
            "OTEL_EXPORTER_ENDPOINT": bool(os.environ.get("OTEL_EXPORTER_ENDPOINT")),
            "SECRETS_PROVIDER": os.environ.get("SECRETS_PROVIDER", "env"),
            "BACKUP_ENABLED": os.environ.get("BACKUP_ENABLED", "false"),
        },
    }
