"""
Production Readiness Validator — Comprehensive system health check
that aggregates all subsystem statuses into READY / DEGRADED / NOT_READY.
"""
import asyncio
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

    # ── Subsystem checks ────────────────────────────────────────
    # Her check (key, check_dict, score) tuple döner. İstisnalar
    # asyncio.gather(return_exceptions=True) ile yakalanır ve
    # validate() içinde "error" entry'sine düşürülür.
    # Senkron alt sistemler asyncio.to_thread ile event loop'u
    # bloklamadan paralel çalışır.

    async def _check_redis(self):
        from infra.redis_cluster import redis_cluster
        redis_health = await redis_cluster.health_check()
        redis_connected = redis_cluster.connected
        return ("redis", {
            "status": "healthy" if redis_connected else "disconnected",
            "mode": redis_cluster.mode,
            "connected": redis_connected,
            "health": redis_health,
        }, 1.0 if redis_connected else 0.3)

    async def _check_mongodb(self):
        from core.database import db as mongo_db
        from infra.mongo_production import mongo_validator
        if mongo_validator._db is None:
            mongo_validator.set_db(mongo_db)
        pool = await mongo_validator.get_connection_pool_info()
        return ("mongodb", {
            "status": pool.get("status", "unknown"),
            "connections": pool.get("current_connections", 0),
            "version": pool.get("mongo_version", "unknown"),
        }, 1.0 if pool.get("status") == "connected" else 0.0)

    async def _check_workers(self):
        from infra.worker_queue import worker_queue_manager
        worker_summary = await asyncio.to_thread(worker_queue_manager.get_worker_summary)
        queue_count = len(worker_summary.get("queues", []))
        return ("workers", {
            "status": "active" if queue_count > 0 else "inactive",
            "total_queues": queue_count,
            "summary": worker_summary,
        }, 1.0 if queue_count > 0 else 0.5)

    async def _check_providers(self):
        from infra.provider_activation import provider_manager
        provider_status = await asyncio.to_thread(provider_manager.get_all_provider_status)
        active = provider_status.get("active_providers", 0)
        total = provider_status.get("total_providers", 3)
        return ("providers", {
            "status": "configured" if active > 0 else "not_configured",
            "active": active,
            "total": total,
        }, min(1.0, active / max(total, 1)))

    async def _check_backup(self):
        # Atlas-aware — see infra/atlas_backup_check.py. URI detection avoids
        # any network call here. Sync internals → to_thread.
        from infra.atlas_backup_check import resolve_backup_check
        from infra.backup_manager import backup_manager

        def _run():
            backup_status = backup_manager.get_status()
            return resolve_backup_check(backup_status)

        backup_check, backup_score = await asyncio.to_thread(_run)
        return ("backup", backup_check, backup_score)

    async def _check_observability(self):
        from infra.cloud_observability import otel_tracer, sentry_integration
        otel_status = await asyncio.to_thread(otel_tracer.get_status)
        sentry_status = await asyncio.to_thread(sentry_integration.get_status)
        otel_active = otel_status.get("active", False)
        sentry_active = sentry_status.get("active", False)
        return ("observability", {
            "status": "active" if (otel_active or sentry_active) else "inactive",
            "otel_active": otel_active,
            "sentry_active": sentry_active,
        }, 1.0 if (otel_active and sentry_active) else 0.5 if (otel_active or sentry_active) else 0.2)

    async def _check_alerting(self):
        from modules.observability.alerting_engine import alerting_engine
        alert_info = await asyncio.to_thread(
            alerting_engine.get_summary
        ) if hasattr(alerting_engine, "get_summary") else {"status": "available"}
        return ("alerting", {"status": "active", "details": alert_info}, 1.0)

    async def _check_configuration(self):
        from infra.production_config import production_config
        startup = await asyncio.to_thread(production_config.startup_check)
        return ("configuration", {
            "status": startup.get("status", "unknown"),
            "missing_critical": startup.get("missing_critical", []),
        }, 1.0 if startup.get("status") == "pass" else 0.0)

    async def _check_exely_whitelist(self):
        # Re-uses backend/scripts/verify_exely_whitelist.py as single source
        # of truth so CLI, readiness API, and startup guardrail all reach
        # identical verdicts. JSON exposed is IP-free: verdict + counts only.
        import os as _os

        from scripts.verify_exely_whitelist import verify as _verify_exely

        def _run():
            env_label = (
                _os.environ.get("ENVIRONMENT")
                or _os.environ.get("APP_ENV")
                or "development"
            )
            findings = _verify_exely(
                dict(_os.environ), environment=env_label, expect_ips=[]
            )
            verdict = findings.verdict
            is_prod = env_label.strip().lower() in ("production", "prod", "live")
            configured_count = len(
                [t for t in (_os.environ.get("EXELY_IP_WHITELIST") or "").split(",") if t.strip()]
            )
            if verdict == "FAIL":
                status = "blocked" if is_prod else "misconfigured"
            elif verdict == "REVIEW":
                status = "review"
            else:
                status = "ok"
            # Production scoring: FAIL hard zero in prod; REVIEW partial.
            if verdict == "FAIL" and is_prod:
                score = 0.0
            elif verdict == "FAIL":
                score = 0.5
            elif verdict == "REVIEW":
                score = 0.7
            else:
                score = 1.0
            return ({
                "status": status,
                "verdict": verdict,
                "environment": env_label,
                "blocker_count": len(findings.blockers),
                "warning_count": len(findings.warnings),
                "configured_count": configured_count,
            }, score)

        check, score = await asyncio.to_thread(_run)
        return ("exely_whitelist", check, score)

    async def _check_cm_outbox(self):
        # Reuses backend/infra/cm_observability_check.py so readiness API,
        # cron alert script, and CLI all reach identical verdicts.
        # NEVER includes tenant_ids or event payloads.
        from core.database import db as mongo_db
        from infra.cm_observability_check import get_outbox_status
        outbox = await get_outbox_status(mongo_db)
        return ("cm_outbox", {
            "status": outbox.get("status", "unknown"),
            "backlog": outbox.get("backlog", 0),
            "failed": outbox.get("failed", 0),
            "oldest_seconds": outbox.get("oldest_seconds"),
            "last_processed_seconds": outbox.get("last_processed_seconds"),
            "reasons": outbox.get("reasons", []),
            "thresholds": outbox.get("thresholds", {}),
        }, outbox.get("score", 0.5))

    async def _check_cm_circuit_breakers(self):
        # Count by state, no per-connection leakage. RBAC drill-down at
        # GET /api/channel-manager/unified-rate-manager/circuit-breakers.
        from infra.cm_observability_check import get_circuit_breaker_status
        cb = await asyncio.to_thread(get_circuit_breaker_status)
        return ("cm_circuit_breakers", {
            "status": cb.get("status", "unknown"),
            "total": cb.get("total", 0),
            "open": cb.get("open", 0),
            "half_open": cb.get("half_open", 0),
            "closed": cb.get("closed", 0),
            "reasons": cb.get("reasons", []),
            "thresholds": cb.get("thresholds", {}),
        }, cb.get("score", 0.7))

    # Error fallback per check key — preserves the per-check error
    # contract from the legacy serial implementation.
    _ERROR_FALLBACKS = {
        "redis": ({"status": "error"}, 0.0),
        "mongodb": ({"status": "error"}, 0.0),
        "workers": ({"status": "error"}, 0.0),
        "providers": ({"status": "error"}, 0.0),
        "backup": ({"status": "error"}, 0.0),
        "observability": ({"status": "error"}, 0.0),
        "alerting": ({"status": "error"}, 0.3),
        "configuration": ({"status": "error"}, 0.0),
        "exely_whitelist": ({"status": "error"}, 0.0),
        "cm_outbox": ({"status": "error"}, 0.5),
        "cm_circuit_breakers": ({"status": "error"}, 0.7),
    }

    async def validate(self) -> dict[str, Any]:
        """Run all subsystem checks in parallel and produce readiness verdict.

        Perf: önceden 11 alt sistem sıralı (3 async + 8 sync) çalışıyordu;
        asyncio.gather ile tüm checkler paralel — async DB/Redis kontrolleri
        eşzamanlı, sync olanlar asyncio.to_thread ile event loop'u bloklamaz.
        Toplam latency artık en yavaş kontrole eşit.
        """
        # Sıra önemli: legacy JSON'da checks key sırası bu listeydi.
        # (Dict order korunur — Python 3.7+ insertion-ordered.)
        check_specs = [
            ("redis", self._check_redis),
            ("mongodb", self._check_mongodb),
            ("workers", self._check_workers),
            ("providers", self._check_providers),
            ("backup", self._check_backup),
            ("observability", self._check_observability),
            ("alerting", self._check_alerting),
            ("configuration", self._check_configuration),
            ("exely_whitelist", self._check_exely_whitelist),
            ("cm_outbox", self._check_cm_outbox),
            ("cm_circuit_breakers", self._check_cm_circuit_breakers),
        ]

        raw = await asyncio.gather(
            *(fn() for _, fn in check_specs),
            return_exceptions=True,
        )

        checks: dict[str, Any] = {}
        scores: list[float] = []
        for (key, _fn), result in zip(check_specs, raw):
            if isinstance(result, BaseException) and not isinstance(result, Exception):
                # CancelledError / SystemExit / KeyboardInterrupt — yutma.
                raise result
            if isinstance(result, Exception):
                fallback_check, fallback_score = self._ERROR_FALLBACKS[key]
                checks[key] = {**fallback_check, "error": str(result)} if "error" not in fallback_check else {
                    **fallback_check, "error_type": type(result).__name__,
                }
                # exely_whitelist / cm_* legacy davranışı: error_type yalın,
                # error mesajı gizli — payload sızdırma riski.
                if key in ("exely_whitelist", "cm_outbox", "cm_circuit_breakers"):
                    checks[key] = {"status": "error", "error_type": type(result).__name__}
                scores.append(fallback_score)
                continue
            _, check_dict, score = result
            checks[key] = check_dict
            scores.append(score)

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
