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

        # 5. Backup readiness (Atlas-aware — see infra/atlas_backup_check.py).
        # When the cluster is on MongoDB Atlas M10+, continuous cloud backup
        # + PITR are managed by Atlas itself; the local backup_manager mongodump
        # path becomes a secondary defense layer. URI detection avoids any
        # network call here — the Atlas Admin API verification (when keys
        # are configured) lives in backend/scripts/verify_atlas_backup.py.
        try:
            from infra.atlas_backup_check import resolve_backup_check
            from infra.backup_manager import backup_manager
            backup_status = backup_manager.get_status()
            backup_check, backup_score = resolve_backup_check(backup_status)
            checks["backup"] = backup_check
            scores.append(backup_score)
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

        # 9. Exely webhook IP-allowlist (Pilot Readiness hard-blocker #1).
        # We re-use backend/scripts/verify_exely_whitelist.py as the single
        # source of truth so CLI, readiness API, and startup guardrail all
        # reach identical verdicts. The JSON exposed here is intentionally
        # IP-free: only verdict + counts. Raw IP/token values must NEVER
        # leave this process via readiness output (Sentry/CI/log sinks).
        try:
            import os as _os

            from scripts.verify_exely_whitelist import verify as _verify_exely
            _env_label = (
                _os.environ.get("ENVIRONMENT")
                or _os.environ.get("APP_ENV")
                or "development"
            )
            _findings = _verify_exely(
                dict(_os.environ), environment=_env_label, expect_ips=[]
            )
            _verdict = _findings.verdict
            _is_prod = _env_label.strip().lower() in ("production", "prod", "live")
            _configured_count = len(
                [t for t in (_os.environ.get("EXELY_IP_WHITELIST") or "").split(",") if t.strip()]
            )
            # NOTE: do NOT attach blocker/warning message strings — they
            # may include redacted IP previews, but readiness JSON should
            # stay metadata-only. Operators run the CLI for details.
            if _verdict == "FAIL":
                _status = "blocked" if _is_prod else "misconfigured"
            elif _verdict == "REVIEW":
                _status = "review"
            else:
                _status = "ok"
            checks["exely_whitelist"] = {
                "status": _status,
                "verdict": _verdict,
                "environment": _env_label,
                "blocker_count": len(_findings.blockers),
                "warning_count": len(_findings.warnings),
                "configured_count": _configured_count,
            }
            # Production scoring: FAIL is a hard zero (NOT_READY contributor),
            # REVIEW partially degrades, PASS is full credit. Non-prod missing
            # whitelist is informational only (0.7) — webhook is offline but
            # the rest of the PMS is healthy and the operator is staging.
            if _verdict == "FAIL" and _is_prod:
                scores.append(0.0)
            elif _verdict == "FAIL":
                scores.append(0.5)
            elif _verdict == "REVIEW":
                scores.append(0.7)
            else:
                scores.append(1.0)
        except Exception as e:
            # Fail-safe: never let the check itself crash readiness.
            # Log error type only, never IP/env contents.
            checks["exely_whitelist"] = {
                "status": "error",
                "error_type": type(e).__name__,
            }
            scores.append(0.0)

        # 10. CM outbox queue health — backlog + failed + age signals.
        # Reuses backend/infra/cm_observability_check.py so the readiness
        # API, the cron-driven alert script, and ad-hoc CLI all reach
        # identical verdicts. NEVER includes tenant_ids or event payloads.
        try:
            from core.database import db as mongo_db
            from infra.cm_observability_check import get_outbox_status
            outbox = await get_outbox_status(mongo_db)
            checks["cm_outbox"] = {
                "status": outbox.get("status", "unknown"),
                "backlog": outbox.get("backlog", 0),
                "failed": outbox.get("failed", 0),
                "oldest_seconds": outbox.get("oldest_seconds"),
                "last_processed_seconds": outbox.get("last_processed_seconds"),
                "reasons": outbox.get("reasons", []),
                "thresholds": outbox.get("thresholds", {}),
            }
            scores.append(outbox.get("score", 0.5))
        except Exception as e:
            checks["cm_outbox"] = {
                "status": "error",
                "error_type": type(e).__name__,
            }
            scores.append(0.5)

        # 11. CM provider circuit breakers — count by state, no per-
        # connection leakage. RBAC drill-down at
        # GET /api/channel-manager/unified-rate-manager/circuit-breakers.
        try:
            from infra.cm_observability_check import get_circuit_breaker_status
            cb = get_circuit_breaker_status()
            checks["cm_circuit_breakers"] = {
                "status": cb.get("status", "unknown"),
                "total": cb.get("total", 0),
                "open": cb.get("open", 0),
                "half_open": cb.get("half_open", 0),
                "closed": cb.get("closed", 0),
                "reasons": cb.get("reasons", []),
                "thresholds": cb.get("thresholds", {}),
            }
            scores.append(cb.get("score", 0.7))
        except Exception as e:
            checks["cm_circuit_breakers"] = {
                "status": "error",
                "error_type": type(e).__name__,
            }
            scores.append(0.7)

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
