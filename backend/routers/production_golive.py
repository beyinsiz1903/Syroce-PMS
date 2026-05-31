"""
Production Go-Live Router — All endpoints for production readiness validation,
provider test connections, config activation, pre-launch validation suite,
live ops alerts, and full dashboard data.
"""

from fastapi import APIRouter, Body, Depends, Query

from core.cache import cached
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v82 DR

router = APIRouter(prefix="/api/production-golive", tags=["production-golive"])


# ── Production Readiness (Top-Level) ──────────────────────────────

@router.get("/readiness")
async def get_readiness(current_user: User = Depends(get_current_user)):
    """Full production readiness validation — returns READY / DEGRADED / NOT_READY."""
    from infra.readiness_validator import readiness_validator
    return await readiness_validator.validate()


@router.get("/uniqueness-backstops")
async def get_uniqueness_backstops(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),
):
    """Report which duplicate-prevention unique-index backstops are active.

    Task #231: the "no duplicate supplier/contract" safeguards are enforced by
    unique indexes that are built best-effort. If legacy duplicate rows exist
    (the index is global across tenants) a build is *deferred* and the safeguard
    is silently OFF for everyone until the residue is cleaned. This surfaces each
    backstop's status (active / deferred / unknown) so ops can see at a glance
    whether the duplicate-prevention safeguards are enforced.
    """
    from shared_kernel import index_backstops

    # Touch the lazy index builders so a not-yet-attempted backstop is attempted
    # (and self-heals) when an operator checks, rather than reporting "unknown".
    try:
        from routers.mice import _ensure_indexes as _mice_ensure_indexes
        await _mice_ensure_indexes()
    except Exception:  # noqa: BLE001
        pass
    try:
        from domains.revenue.rms_router.sales import _ensure_contract_indexes
        await _ensure_contract_indexes()
    except Exception:  # noqa: BLE001
        pass

    backstops = index_backstops.list_status()
    deferred = [b for b in backstops if b.get("status") == "deferred"]
    return {
        "all_active": index_backstops.all_active(),
        "any_deferred": index_backstops.any_deferred(),
        "deferred_count": len(deferred),
        "backstops": backstops,
    }


@router.get("/summary")
@cached(ttl=60, key_prefix="golive_summary")
async def get_golive_summary(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v87 DR-FOLLOWUP-1: ops/devops diagnostics
):
    """Complete production go-live dashboard data — aggregates all subsystems."""
    from infra.mongo_production import mongo_validator
    from infra.production_config import production_config
    from infra.provider_activation import provider_manager
    from infra.readiness_validator import readiness_validator
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
    from infra.cloud_observability import cloud_metrics, otel_tracer, sentry_integration
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

    # Provider test status
    from infra.provider_test_connection import provider_test_service
    provider_test_status = provider_test_service.get_status()

    # Config activation
    from infra.config_activation import config_activation
    config_activation_data = config_activation.validate_all()

    # Pre-launch latest
    from infra.prelaunch_validator import prelaunch_validator
    prelaunch_latest = prelaunch_validator.get_latest()

    # Alerts summary
    from infra.live_ops_alerts import live_ops_alerts
    alerts_summary = live_ops_alerts.get_alert_summary()

    return {
        "readiness": readiness,
        "configuration": config_validation,
        "config_activation": config_activation_data,
        "redis": redis_data,
        "mongodb": mongo_report,
        "workers": worker_data,
        "providers": provider_status,
        "provider_tests": provider_test_status,
        "backup": backup_data,
        "observability": observability_data,
        "security": security_result,
        "prelaunch_latest": prelaunch_latest,
        "alerts_summary": alerts_summary,
    }


# ── Environment Configuration ─────────────────────────────────────

@router.get("/config/validate")
async def validate_config(current_user: User = Depends(get_current_user)):
    from infra.production_config import production_config
    return production_config.validate_all()


@router.get("/config/inspect")
async def inspect_config(current_user: User = Depends(get_current_user)):
    from infra.production_config import production_config
    return production_config.get_masked_config()


@router.get("/config/startup-check")
async def startup_check(current_user: User = Depends(get_current_user)):
    from infra.production_config import production_config
    return production_config.startup_check()


@router.get("/config/leak-scan")
async def leak_scan(current_user: User = Depends(get_current_user)):
    from infra.production_config import production_config
    return production_config.detect_leaked_secrets()


# ── Config Activation Workflow ────────────────────────────────────

@router.get("/config-activation/validate")
async def config_activation_validate(current_user: User = Depends(get_current_user)):
    """Full config activation validation with blocker/warning classification."""
    from infra.config_activation import config_activation
    return config_activation.validate_all()


@router.get("/config-activation/boot-check")
async def config_activation_boot_check(current_user: User = Depends(get_current_user)):
    """Boot blocker check."""
    from infra.config_activation import config_activation
    return config_activation.get_boot_check()


@router.get("/config-activation/category/{category}")
async def config_activation_category(category: str, current_user: User = Depends(get_current_user)):
    """Config status for a specific category."""
    from infra.config_activation import config_activation
    return config_activation.get_category_status(category)


# ── Provider Test Connection ──────────────────────────────────────

@router.post("/providers/{provider}/test")
async def test_provider_connection(provider: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """Live test connection for a specific provider."""
    from infra.provider_test_connection import provider_test_service
    return await provider_test_service.test_provider(provider, user_id=current_user.id)


@router.post("/providers/test-all")
async def test_all_providers(current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """Test all provider connections."""
    from infra.provider_test_connection import provider_test_service
    return await provider_test_service.test_all_providers(user_id=current_user.id)


@router.get("/providers/status")
async def provider_status(current_user: User = Depends(get_current_user)):
    """All messaging provider status with delivery metrics."""
    from infra.provider_activation import provider_manager
    from infra.provider_test_connection import provider_test_service
    base_status = provider_manager.get_all_provider_status()
    test_status = provider_test_service.get_status()
    return {**base_status, "test_results": test_status}


@router.get("/providers/test-audit")
async def provider_test_audit(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    """Provider test audit log."""
    from infra.provider_test_connection import provider_test_service
    return {"audit_log": provider_test_service.get_audit_log(limit)}


@router.get("/providers/validate")
async def provider_validate(current_user: User = Depends(get_current_user)):
    from infra.provider_activation import provider_manager
    return await provider_manager.get_full_report()


@router.get("/providers/delivery-metrics")
async def provider_delivery_metrics(current_user: User = Depends(get_current_user)):
    from infra.provider_activation import provider_manager
    return provider_manager.get_delivery_metrics()


# ── Redis Production ──────────────────────────────────────────────

@router.get("/redis/cluster-validation")
async def redis_cluster_validation(current_user: User = Depends(get_current_user)):
    from infra.distributed_lock import lock_manager
    from infra.redis_cluster import redis_cluster
    health = await redis_cluster.health_check()
    return {
        "mode": redis_cluster.mode,
        "connected": redis_cluster.connected,
        "health": health,
        "metrics": redis_cluster.get_metrics(),
        "lock_metrics": lock_manager.get_metrics(),
        "pool_config": {"max_connections": int(redis_cluster._max_connections)},
    }


@router.get("/redis/pubsub-health")
async def redis_pubsub_health(current_user: User = Depends(get_current_user)):
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
    from infra.distributed_lock import lock_manager
    return {
        "metrics": lock_manager.get_metrics(),
        "active_locks": lock_manager.get_active_locks(),
        "safety_status": "operational",
    }


# ── MongoDB Production ────────────────────────────────────────────

@router.get("/mongo/health")
async def mongo_health(current_user: User = Depends(get_current_user)):
    from infra.mongo_production import mongo_validator
    return await mongo_validator.get_full_report()


@router.get("/mongo/pool")
async def mongo_pool(current_user: User = Depends(get_current_user)):
    from infra.mongo_production import mongo_validator
    return await mongo_validator.get_connection_pool_info()


@router.get("/mongo/replica-set")
async def mongo_replica_set(current_user: User = Depends(get_current_user)):
    from infra.mongo_production import mongo_validator
    return await mongo_validator.detect_replica_set()


@router.get("/mongo/indexes")
async def mongo_indexes(current_user: User = Depends(get_current_user)):
    from infra.mongo_production import mongo_validator
    return await mongo_validator.validate_indexes()


@router.get("/mongo/slow-queries")
async def mongo_slow_queries(
    threshold_ms: int = Query(100, ge=10, le=5000),
    current_user: User = Depends(get_current_user),
):
    from infra.mongo_production import mongo_validator
    return await mongo_validator.get_slow_query_metrics(threshold_ms)


@router.get("/mongo/schema-drift")
async def mongo_schema_drift(current_user: User = Depends(get_current_user)):
    from infra.mongo_production import mongo_validator
    return await mongo_validator.detect_schema_drift()


@router.get("/mongo/collections")
async def mongo_collections(current_user: User = Depends(get_current_user)):
    from infra.mongo_production import mongo_validator
    return await mongo_validator.get_collection_health()


# ── Worker Runtime ────────────────────────────────────────────────

@router.get("/workers/validation")
async def worker_validation(current_user: User = Depends(get_current_user)):
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
    from infra.worker_queue import worker_queue_manager
    summary = worker_queue_manager.get_worker_summary()
    return {
        "total_queues": summary.get("total_queues", 0),
        "queue_definitions": summary.get("queues", {}),
        "scaling_ready": len(summary.get("queues", [])) > 0,
        "recommendation": "Scale workers per queue based on load",
    }


# ── Pre-Launch Validation Suite ───────────────────────────────────

@router.post("/validate/run")
async def run_prelaunch_validation(current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v101 DW
):
    """Run full pre-launch validation suite."""
    from core.database import db
    from infra.prelaunch_validator import prelaunch_validator
    prelaunch_validator.set_db(db)
    result = await prelaunch_validator.run_full_validation()

    # Auto-fire alert if NOT_READY
    if result.get("recommendation") == "NOT_READY":
        from infra.live_ops_alerts import live_ops_alerts
        await live_ops_alerts.fire_alert("prelaunch_validation_failed", {
            "readiness_score": result.get("readiness_score"),
            "blocker_count": result.get("blocker_count"),
        }, user_id=current_user.id)

    return result


@router.get("/validate/history")
async def prelaunch_validation_history(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """Get pre-launch validation history."""
    from infra.prelaunch_validator import prelaunch_validator
    return {"history": prelaunch_validator.get_history(limit)}


@router.get("/validate/latest")
async def prelaunch_validation_latest(current_user: User = Depends(get_current_user)):
    """Get latest pre-launch validation result."""
    from infra.prelaunch_validator import prelaunch_validator
    latest = prelaunch_validator.get_latest()
    return latest or {"status": "no_validation_run", "message": "Run validation first"}


# ── Live Ops Alerts ───────────────────────────────────────────────

@router.post("/alerts/fire")
async def fire_alert(
    alert_type: str = Body(...),
    context: dict = Body(default={}),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v100 DW
):
    """Manually fire a production alert."""
    from infra.live_ops_alerts import live_ops_alerts
    return await live_ops_alerts.fire_alert(alert_type, context, user_id=current_user.id)


@router.get("/alerts/history")
async def alert_history(
    limit: int = Query(50, ge=1, le=200),
    severity: str | None = Query(None),
    current_user: User = Depends(get_current_user),
):
    """Get alert history with optional severity filter."""
    from infra.live_ops_alerts import live_ops_alerts
    return {"alerts": live_ops_alerts.get_alert_history(limit, severity)}


@router.get("/alerts/summary")
async def alert_summary(current_user: User = Depends(get_current_user)):
    """Alert summary — counts by severity and type."""
    from infra.live_ops_alerts import live_ops_alerts
    return live_ops_alerts.get_alert_summary()


@router.get("/alerts/definitions")
async def alert_definitions(current_user: User = Depends(get_current_user)):
    """All alert type definitions with runbooks."""
    from infra.live_ops_alerts import live_ops_alerts
    return {"definitions": live_ops_alerts.get_definitions()}


@router.get("/alerts/delivery-log")
async def alert_delivery_log(
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    """Webhook delivery log."""
    from infra.live_ops_alerts import live_ops_alerts
    return {"delivery_log": live_ops_alerts.get_delivery_log(limit)}


# ── Observability Go-Live ────────────────────────────────────────

@router.get("/observability/validation")
async def observability_validation(current_user: User = Depends(get_current_user)):
    from infra.cloud_observability import cloud_metrics, otel_tracer, sentry_integration
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
        "grafana_dashboard": {"template_available": True, "path": "/ops/grafana/dashboard.json"},
        "overall_status": "active" if (
            otel_tracer.get_status().get("active") or sentry_integration.get_status().get("active")
        ) else "inactive",
    }


@router.get("/observability/key-metrics")
async def observability_key_metrics(current_user: User = Depends(get_current_user)):
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
        "retention_policy": {"days": status.get("retention_days", 30)},
        "restore_test_available": True,
        "overall_status": "operational" if status.get("enabled") else "disabled",
    }


# ── Security Checklist ───────────────────────────────────────────

@router.get("/security/checklist")
async def security_full_checklist(current_user: User = Depends(get_current_user)):
    from infra.security_checklist import security_checklist
    return await security_checklist.run_full_checklist()


@router.get("/security/tenant-isolation")
async def security_tenant_isolation(current_user: User = Depends(get_current_user)):
    from infra.security_checklist import security_checklist
    return await security_checklist.check_tenant_isolation()


@router.get("/security/rbac")
async def security_rbac(current_user: User = Depends(get_current_user)):
    from infra.security_checklist import security_checklist
    return await security_checklist.check_rbac()


# ── Deployment Orchestration ──────────────────────────────────────

@router.get("/deployment/risk-assessment")
async def deployment_risk_assessment(current_user: User = Depends(get_current_user)):
    """Full deployment risk assessment with safety score and mitigations."""
    from infra.deployment_orchestrator import deployment_orchestrator
    return deployment_orchestrator.assess_risk()


@router.get("/deployment/strategy")
async def deployment_strategy(current_user: User = Depends(get_current_user)):
    """Recommended deployment strategy based on current risk profile."""
    from infra.deployment_orchestrator import deployment_orchestrator
    return deployment_orchestrator.get_deployment_strategy()


@router.get("/deployment/infrastructure")
async def deployment_infrastructure(current_user: User = Depends(get_current_user)):
    """Infrastructure topology and config file inventory."""
    from infra.deployment_orchestrator import deployment_orchestrator
    return deployment_orchestrator.get_infra_summary()


@router.get("/deployment/first-batch")
async def deployment_first_batch(current_user: User = Depends(get_current_user)):
    """First deployment batch — ordered component startup sequence."""
    from infra.deployment_orchestrator import deployment_orchestrator
    strategy = deployment_orchestrator.get_deployment_strategy()
    return {
        "strategy": strategy["strategy"],
        "first_5_components": strategy["deployment_batches"][:5],
        "pre_deployment_checks": strategy["pre_deployment_checks"],
        "rollback_plan": strategy["rollback_plan"],
    }


# ── Secrets Manager ───────────────────────────────────────────────

@router.get("/secrets/health")
async def secrets_health(current_user: User = Depends(get_current_user)):
    """Secrets manager health and provider status."""
    from infra.secrets_manager import secrets_manager
    return await secrets_manager.health_check()


@router.get("/secrets/access-log")
async def secrets_access_log(
    limit: int = Query(30, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """Recent secrets access log (masked)."""
    from infra.secrets_manager import secrets_manager
    return {"access_log": secrets_manager.get_access_log(limit)}


@router.get("/secrets/metrics")
async def secrets_metrics(current_user: User = Depends(get_current_user)):
    """Secrets manager usage metrics."""
    from infra.secrets_manager import secrets_manager
    return secrets_manager.get_metrics()


# ── Backup Trigger & Restore Test ─────────────────────────────────

@router.post("/backup/trigger")
async def trigger_backup(current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v90 DW
):
    """Manually trigger a MongoDB backup."""
    from infra.backup_manager import backup_manager
    return await backup_manager.create_backup("manual")


@router.post("/backup/restore-test/{backup_id}")
async def test_restore(backup_id: str, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v90 DW
):
    """Test restore integrity for a specific backup."""
    from infra.backup_manager import backup_manager
    return await backup_manager.test_restore(backup_id)


@router.post("/backup/cleanup")
async def cleanup_backups(current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v90 DW
):
    """Remove backups older than retention period."""
    from infra.backup_manager import backup_manager
    return await backup_manager.cleanup_old_backups()


@router.get("/backup/history")
async def backup_history(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
):
    """Backup history."""
    from infra.backup_manager import backup_manager
    return {"history": backup_manager.get_history(limit)}


# ── Horizontal Scaling ────────────────────────────────────────────

@router.get("/scaling/summary")
async def scaling_summary(current_user: User = Depends(get_current_user)):
    """Instance scaling status and health."""
    from infra.horizontal_scaling import scaling_manager
    return await scaling_manager.get_scaling_summary()


@router.get("/scaling/stateless-check")
async def stateless_check(current_user: User = Depends(get_current_user)):
    """Statelessness validation for horizontal scaling."""
    from infra.horizontal_scaling import scaling_manager
    return scaling_manager.stateless_validation()
