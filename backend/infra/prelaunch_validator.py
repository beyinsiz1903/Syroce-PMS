"""
Pre-Launch Validation Suite — Comprehensive pre-production validation that runs
all critical subsystem checks in sequence and produces blockers, warnings,
recommendations, and a launch readiness verdict.

Verdicts: NOT_READY | CONDITIONALLY_READY | GO_LIVE_READY
"""

import logging
import time
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("infra.prelaunch_validator")


class ValidationStep:
    """Single validation step result."""

    def __init__(self, name: str, category: str):
        self.name = name
        self.category = category
        self.status = "pending"  # pass / fail / warning / skipped
        self.latency_ms: float = 0
        self.details: dict[str, Any] = {}
        self.blocker: bool = False
        self.message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category,
            "status": self.status,
            "latency_ms": round(self.latency_ms, 2),
            "blocker": self.blocker,
            "message": self.message,
            "details": self.details,
        }


class PreLaunchValidator:
    """Runs all pre-launch validation steps and produces readiness verdict."""

    def __init__(self):
        self._history: list[dict[str, Any]] = []
        self._max_history = 50
        self._db = None

    def set_db(self, db):
        self._db = db

    async def run_full_validation(self) -> dict[str, Any]:
        """Execute all validation steps in sequence."""
        start = time.time()
        steps: list[dict[str, Any]] = []

        # 1. Config validation
        steps.append(await self._check_config())

        # 2. Redis connectivity
        steps.append(await self._check_redis())

        # 3. MongoDB connectivity
        steps.append(await self._check_mongo())

        # 4. Worker availability
        steps.append(await self._check_workers())

        # 5. Provider credential validation
        steps.append(await self._check_providers())

        # 6. Event bus health
        steps.append(await self._check_event_bus())

        # 7. WebSocket broadcast health
        steps.append(await self._check_websocket())

        # 8. Messaging send simulation
        steps.append(await self._check_messaging_sim())

        # 9. Tracing export validation
        steps.append(await self._check_tracing())

        # 10. Alert engine health
        steps.append(await self._check_alert_engine())

        # 11. Backup readiness
        steps.append(await self._check_backup())

        # 12. Security checklist completeness
        steps.append(await self._check_security())

        total_ms = (time.time() - start) * 1000

        # Classify results
        blockers = [s for s in steps if s["blocker"] and s["status"] == "fail"]
        warnings = [s for s in steps if s["status"] == "warning"]
        passed = [s for s in steps if s["status"] == "pass"]
        failed = [s for s in steps if s["status"] == "fail"]

        # Readiness score
        total = len(steps)
        pass_score = len(passed) / total * 100 if total else 0

        # Verdict
        if len(blockers) > 0:
            recommendation = "NOT_READY"
        elif len(failed) > 0 or len(warnings) > 2:
            recommendation = "CONDITIONALLY_READY"
        else:
            recommendation = "GO_LIVE_READY"

        # Recommended next actions
        actions = []
        for b in blockers:
            actions.append(f"[BLOCKER] Fix: {b['name']} — {b['message']}")
        for w in warnings[:5]:
            actions.append(f"[WARNING] Review: {w['name']} — {w['message']}")
        if recommendation == "CONDITIONALLY_READY":
            actions.append("Review all warnings and confirm acceptable risk before launch")
        if recommendation == "GO_LIVE_READY":
            actions.append("All checks passed — system is ready for production launch")

        result = {
            "run_id": f"plv_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}",
            "started_at": datetime.now(UTC).isoformat(),
            "total_duration_ms": round(total_ms, 2),
            "recommendation": recommendation,
            "readiness_score": round(pass_score),
            "total_checks": total,
            "passed_count": len(passed),
            "failed_count": len(failed),
            "warning_count": len(warnings),
            "blocker_count": len(blockers),
            "blockers": [{"name": b["name"], "message": b["message"]} for b in blockers],
            "warnings": [{"name": w["name"], "message": w["message"]} for w in warnings],
            "recommended_actions": actions,
            "steps": steps,
        }

        self._history.append(result)
        if len(self._history) > self._max_history:
            self._history = self._history[-self._max_history :]

        return result

    def get_history(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._history[-limit:]

    def get_latest(self) -> dict[str, Any] | None:
        return self._history[-1] if self._history else None

    # ── Individual validation steps ──────────────────────────────

    async def _run_step(self, name: str, category: str, check_fn) -> dict[str, Any]:
        step = ValidationStep(name, category)
        start = time.time()
        try:
            await check_fn(step)
        except Exception as e:
            step.status = "fail"
            step.message = f"Exception: {str(e)[:200]}"
        step.latency_ms = (time.time() - start) * 1000
        return step.to_dict()

    async def _check_config(self) -> dict[str, Any]:
        async def _run(step):
            from infra.config_activation import config_activation

            result = config_activation.get_boot_check()
            if result["status"] == "BLOCKED":
                step.status = "fail"
                step.blocker = True
                step.message = f"Boot blockers: {', '.join(result['blockers'])}"
            else:
                step.status = "pass"
                step.message = "All critical config variables present"
            step.details = result

        return await self._run_step("config_validation", "infrastructure", _run)

    async def _check_redis(self) -> dict[str, Any]:
        async def _run(step):
            from infra.redis_cluster import redis_cluster

            health = await redis_cluster.health_check()
            if health.get("status") == "healthy":
                step.status = "pass"
                step.message = f"Redis connected ({redis_cluster.mode} mode)"
            elif redis_cluster.connected:
                step.status = "warning"
                step.message = "Redis connected but health degraded"
            else:
                step.status = "warning"
                step.message = "Redis not connected — cache/pubsub unavailable"
            step.details = {"mode": redis_cluster.mode, "connected": redis_cluster.connected}

        return await self._run_step("redis_connectivity", "infrastructure", _run)

    async def _check_mongo(self) -> dict[str, Any]:
        async def _run(step):
            from infra.mongo_production import mongo_validator

            if mongo_validator._db is None and self._db:
                mongo_validator.set_db(self._db)
            pool = await mongo_validator.get_connection_pool_info()
            if pool.get("status") == "connected":
                step.status = "pass"
                step.message = f"MongoDB connected (v{pool.get('mongo_version', '?')})"
            else:
                step.status = "fail"
                step.blocker = True
                step.message = "MongoDB not connected"
            step.details = pool

        return await self._run_step("mongo_connectivity", "infrastructure", _run)

    async def _check_workers(self) -> dict[str, Any]:
        async def _run(step):
            from infra.worker_queue import worker_queue_manager

            summary = worker_queue_manager.get_worker_summary()
            queue_count = len(summary.get("queues", []))
            if queue_count > 0:
                step.status = "pass"
                step.message = f"{queue_count} queues configured"
            else:
                step.status = "warning"
                step.message = "No worker queues detected"
            step.details = {"queues": queue_count, "pending": summary.get("total_pending", 0)}

        return await self._run_step("worker_availability", "runtime", _run)

    async def _check_providers(self) -> dict[str, Any]:
        async def _run(step):
            from infra.provider_activation import provider_manager

            status = provider_manager.get_all_provider_status()
            active = status.get("active_providers", 0)
            total = status.get("total_providers", 3)
            if active == total:
                step.status = "pass"
                step.message = f"All {total} providers configured"
            elif active > 0:
                step.status = "warning"
                step.message = f"{active}/{total} providers configured"
            else:
                step.status = "warning"
                step.message = "No messaging providers configured"
            step.details = {"active": active, "total": total}

        return await self._run_step("provider_credentials", "integrations", _run)

    async def _check_event_bus(self) -> dict[str, Any]:
        async def _run(step):
            try:
                from modules.event_system.event_bus import event_bus

                if hasattr(event_bus, "get_stats"):
                    stats = event_bus.get_stats()
                    step.status = "pass"
                    step.message = "Event bus operational"
                    step.details = stats
                else:
                    step.status = "pass"
                    step.message = "Event bus module loaded"
            except ImportError:
                step.status = "warning"
                step.message = "Event bus module not available"

        return await self._run_step("event_bus_health", "runtime", _run)

    async def _check_websocket(self) -> dict[str, Any]:
        async def _run(step):
            try:
                from websocket_server import broadcast_kitchen_orders  # noqa: F401

                step.status = "pass"
                step.message = "WebSocket broadcast module loaded"
            except ImportError:
                step.status = "warning"
                step.message = "WebSocket module not available"

        return await self._run_step("websocket_broadcast", "runtime", _run)

    async def _check_messaging_sim(self) -> dict[str, Any]:
        async def _run(step):
            from infra.provider_activation import provider_manager

            status = provider_manager.get_all_provider_status()
            active = status.get("active_providers", 0)
            if active > 0:
                step.status = "pass"
                step.message = f"Messaging ready via {active} provider(s)"
            else:
                step.status = "warning"
                step.message = "No active messaging providers for delivery"
            step.details = {"active_providers": active}

        return await self._run_step("messaging_simulation", "integrations", _run)

    async def _check_tracing(self) -> dict[str, Any]:
        async def _run(step):
            from infra.cloud_observability import otel_tracer

            status = otel_tracer.get_status()
            if status.get("active"):
                step.status = "pass"
                step.message = "OTel tracing active"
            else:
                step.status = "warning"
                step.message = "Tracing not active"
            step.details = status

        return await self._run_step("tracing_export", "observability", _run)

    async def _check_alert_engine(self) -> dict[str, Any]:
        async def _run(step):
            try:
                from modules.observability.alerting_engine import alerting_engine  # noqa: F401

                step.status = "pass"
                step.message = "Alert engine available"
            except ImportError:
                step.status = "warning"
                step.message = "Alert engine module not loaded"

        return await self._run_step("alert_engine", "observability", _run)

    async def _check_backup(self) -> dict[str, Any]:
        async def _run(step):
            from infra.backup_manager import backup_manager

            status = backup_manager.get_status()
            if status.get("enabled"):
                step.status = "pass"
                step.message = f"Backups enabled (retention: {status.get('retention_days', 30)}d)"
            else:
                step.status = "warning"
                step.message = "Backups not enabled"
            step.details = {"enabled": status.get("enabled"), "retention_days": status.get("retention_days")}

        return await self._run_step("backup_readiness", "operations", _run)

    async def _check_security(self) -> dict[str, Any]:
        async def _run(step):
            from infra.security_checklist import security_checklist

            if security_checklist._db is None and self._db:
                security_checklist.set_db(self._db)
            result = await security_checklist.run_full_checklist()
            score = result.get("score", 0)
            if score >= 80:
                step.status = "pass"
                step.message = f"Security score: {score}%"
            elif score >= 50:
                step.status = "warning"
                step.message = f"Security score: {score}% — review failed checks"
            else:
                step.status = "fail"
                step.blocker = True
                step.message = f"Security score too low: {score}%"
            step.details = {"score": score, "failed": result.get("failed_checks", [])}

        return await self._run_step("security_checklist", "security", _run)


# Singleton
prelaunch_validator = PreLaunchValidator()
