"""
Production Readiness Validator — Comprehensive system health check
that aggregates all subsystem statuses into READY / DEGRADED / NOT_READY.
"""
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("infra.readiness_validator")


class ReadinessValidator:
    """Aggregates all subsystem health checks into a single readiness score."""

    def __init__(self):
        self._db = None

    def set_db(self, db):
        self._db = db

    @property
    def db(self):
        return self._db

    async def validate(self) -> dict[str, Any]:
        """Run all subsystem checks and produce readiness verdict."""
        checks = {}
        scores = []

        # 1. Redis connectivity
        try:
            from infra.redis_cluster import redis_cluster
            redis_health = await redis_cluster.health_check()
            redis_connected = redis_cluster.connected
            checks["redis"] = {
                "status": "healthy" if redis_connected else "disconnected",
                "mode": redis_cluster.mode,
                "connected": redis_connected,
                "health": redis_health,
            }
            scores.append(1.0 if redis_connected else 0.3)
        except Exception as e:
            checks["redis"] = {"status": "error", "error": str(e)}
            scores.append(0.0)

        # 2. MongoDB cluster health
        try:
            from core.database import db as mongo_db
            from infra.mongo_production import mongo_validator
            if mongo_validator._db is None:
                mongo_validator.set_db(mongo_db)
            pool = await mongo_validator.get_connection_pool_info()
            checks["mongodb"] = {
                "status": pool.get("status", "unknown"),
                "connections": pool.get("current_connections", 0),
                "version": pool.get("mongo_version", "unknown"),
            }
            scores.append(1.0 if pool.get("status") == "connected" else 0.0)
        except Exception as e:
            checks["mongodb"] = {"status": "error", "error": str(e)}
            scores.append(0.0)

        # 3. Worker availability
        try:
            from infra.worker_queue import worker_queue_manager
            worker_summary = worker_queue_manager.get_worker_summary()
            queue_count = len(worker_summary.get("queues", []))
            checks["workers"] = {
                "status": "active" if queue_count > 0 else "inactive",
                "total_queues": queue_count,
                "summary": worker_summary,
            }
            scores.append(1.0 if queue_count > 0 else 0.5)
        except Exception as e:
            checks["workers"] = {"status": "error", "error": str(e)}
            scores.append(0.0)

        # 4. Provider credentials
        try:
            from infra.provider_activation import provider_manager
            provider_status = provider_manager.get_all_provider_status()
            active = provider_status.get("active_providers", 0)
            total = provider_status.get("total_providers", 3)
            checks["providers"] = {
                "status": "configured" if active > 0 else "not_configured",
                "active": active,
                "total": total,
            }
            scores.append(min(1.0, active / max(total, 1)))
        except Exception as e:
            checks["providers"] = {"status": "error", "error": str(e)}
            scores.append(0.0)

        # 5. Backup readiness
        try:
            from infra.backup_manager import backup_manager
            backup_status = backup_manager.get_status()
            enabled = backup_status.get("enabled", False)
            checks["backup"] = {
                "status": "enabled" if enabled else "disabled",
                "details": backup_status,
            }
            scores.append(1.0 if enabled else 0.3)
        except Exception as e:
            checks["backup"] = {"status": "error", "error": str(e)}
            scores.append(0.0)

        # 6. Observability export
        try:
            from infra.cloud_observability import otel_tracer, sentry_integration
            otel_status = otel_tracer.get_status()
            sentry_status = sentry_integration.get_status()
            otel_active = otel_status.get("active", False)
            sentry_active = sentry_status.get("active", False)
            checks["observability"] = {
                "status": "active" if (otel_active or sentry_active) else "inactive",
                "otel_active": otel_active,
                "sentry_active": sentry_active,
            }
            scores.append(1.0 if (otel_active and sentry_active) else 0.5 if (otel_active or sentry_active) else 0.2)
        except Exception as e:
            checks["observability"] = {"status": "error", "error": str(e)}
            scores.append(0.0)

        # 7. Alert engine health
        try:
            from modules.observability.alerting_engine import alerting_engine
            alert_info = alerting_engine.get_summary() if hasattr(alerting_engine, "get_summary") else {"status": "available"}
            checks["alerting"] = {"status": "active", "details": alert_info}
            scores.append(1.0)
        except Exception as e:
            checks["alerting"] = {"status": "error", "error": str(e)}
            scores.append(0.3)

        # 8. Environment configuration
        try:
            from infra.production_config import production_config
            startup = production_config.startup_check()
            checks["configuration"] = {
                "status": startup.get("status", "unknown"),
                "missing_critical": startup.get("missing_critical", []),
            }
            scores.append(1.0 if startup.get("status") == "pass" else 0.0)
        except Exception as e:
            checks["configuration"] = {"status": "error", "error": str(e)}
            scores.append(0.0)

        # Calculate overall readiness
        avg_score = sum(scores) / len(scores) if scores else 0
        readiness_score = round(avg_score * 100)

        if readiness_score >= 80:
            readiness = "READY"
        elif readiness_score >= 50:
            readiness = "DEGRADED"
        else:
            readiness = "NOT_READY"

        return {
            "validated_at": datetime.now(UTC).isoformat(),
            "readiness": readiness,
            "readiness_score": readiness_score,
            "subsystem_count": len(checks),
            "checks": checks,
        }


readiness_validator = ReadinessValidator()
