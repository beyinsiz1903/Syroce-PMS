"""
Phase 7 — Production Environment Preparation Service
======================================================
Validates infrastructure, security, data safety, and observability
readiness for production rollout.
"""

import logging
from datetime import UTC, datetime, timedelta

from common.context import OperationContext
from common.result import ServiceResult

logger = logging.getLogger(__name__)


class ProductionEnvService:
    """Validates production environment readiness across 4 categories."""

    def __init__(self):
        from core.database import db

        self._db = db

    @staticmethod
    def _not_verified(name: str, issues: list[str], message: str) -> dict:
        """Record an operational claim as unknown until real evidence exists."""
        issues.append(message)
        return {"name": name, "status": "not_verified"}

    async def run_full_validation(self, ctx: OperationContext) -> ServiceResult:
        """Run all 4 category validations and produce overall readiness."""
        now = datetime.now(UTC)
        categories = {
            "infrastructure": await self._validate_infrastructure(ctx),
            "security": await self._validate_security(ctx),
            "data_safety": await self._validate_data_safety(ctx),
            "observability": await self._validate_observability(ctx),
        }

        total_checks = sum(c["total"] for c in categories.values())
        passed_checks = sum(c["passed"] for c in categories.values())
        overall_score = round(passed_checks / max(total_checks, 1) * 100, 1)
        all_issues = []
        for cat_name, cat_data in categories.items():
            for issue in cat_data.get("issues", []):
                all_issues.append({"category": cat_name, "issue": issue})

        result = {
            "overall_score": overall_score,
            "ready": overall_score >= 80 and not any(c.get("critical_fail") for c in categories.values()),
            "categories": categories,
            "total_checks": total_checks,
            "passed_checks": passed_checks,
            "issues": all_issues,
            "validated_at": now.isoformat(),
        }

        await self._db.production_env_validations.insert_one(
            {
                "tenant_id": ctx.tenant_id,
                "result": result,
                "validated_at": now.isoformat(),
            }
        )

        return ServiceResult.success(result)

    async def _validate_infrastructure(self, ctx: OperationContext) -> dict:
        checks = []
        issues = []
        critical = False

        # Database connectivity is the only infrastructure check that this
        # process can verify directly.
        try:
            await self._db.command("ping")
            checks.append({"name": "mongodb_connection", "status": "pass"})
        except Exception:
            checks.append({"name": "mongodb_connection", "status": "fail"})
            issues.append("MongoDB connection unavailable")
            critical = True

        # Worker readiness
        worker_tasks = await self._db.celery_task_log.count_documents({"created_at": {"$gte": (datetime.now(UTC) - timedelta(hours=1)).isoformat()}})
        if worker_tasks > 0:
            checks.append({"name": "worker_autoscaling_readiness", "status": "pass"})
        else:
            checks.append(self._not_verified("worker_autoscaling_readiness", issues, "No worker activity evidence in the last hour"))

        checks.append(self._not_verified("load_balancer_health", issues, "Load balancer health is not connected to this validation"))
        checks.append(self._not_verified("redis_cluster_health", issues, "Redis health is not connected to this validation"))
        checks.append(self._not_verified("mongo_replication_health", issues, "MongoDB replication health is not connected to this validation"))

        passed = sum(1 for c in checks if c["status"] == "pass")
        return {
            "checks": checks,
            "total": len(checks),
            "passed": passed,
            "issues": issues,
            "critical_fail": critical,
        }

    async def _validate_security(self, ctx: OperationContext) -> dict:
        checks = []
        issues = []
        critical = False

        checks.append(self._not_verified("secrets_rotation_verified", issues, "Secrets rotation evidence is not connected to this validation"))
        checks.append(self._not_verified("tls_termination_verified", issues, "TLS termination evidence is not connected to this validation"))
        checks.append(self._not_verified("rate_limiting_active", issues, "Rate-limit runtime evidence is not connected to this validation"))
        checks.append(self._not_verified("waf_policies_active", issues, "WAF policy evidence is not connected to this validation"))

        # JWT security
        import os

        jwt_secret = os.environ.get("JWT_SECRET", "")
        if jwt_secret and len(jwt_secret) >= 16:
            checks.append({"name": "jwt_secret_strength", "status": "pass"})
        else:
            checks.append({"name": "jwt_secret_strength", "status": "warn"})
            issues.append("JWT secret may need strengthening for production")

        passed = sum(1 for c in checks if c["status"] == "pass")
        return {
            "checks": checks,
            "total": len(checks),
            "passed": passed,
            "issues": issues,
            "critical_fail": critical,
        }

    async def _validate_data_safety(self, ctx: OperationContext) -> dict:
        checks = []
        issues = []

        checks.append(self._not_verified("backup_schedule_active", issues, "Backup schedule evidence is not connected to this validation"))
        checks.append(self._not_verified("restore_test_verified", issues, "Restore-test evidence is not connected to this validation"))

        # Audit log persistence
        audit_count = await self._db.audit_logs.count_documents({"tenant_id": ctx.tenant_id})
        if audit_count > 0:
            checks.append({"name": "audit_log_persistence", "status": "pass"})
        else:
            checks.append({"name": "audit_log_persistence", "status": "warn"})
            issues.append("No audit logs found for tenant — persistence unverified")

        checks.append(self._not_verified("data_retention_policy", issues, "Data retention evidence is not connected to this validation"))

        passed = sum(1 for c in checks if c["status"] == "pass")
        return {
            "checks": checks,
            "total": len(checks),
            "passed": passed,
            "issues": issues,
            "critical_fail": False,
        }

    async def _validate_observability(self, ctx: OperationContext) -> dict:
        checks = []
        issues = []

        checks.append(self._not_verified("metrics_collection_active", issues, "Metrics delivery evidence is not connected to this validation"))
        checks.append(self._not_verified("log_aggregation_active", issues, "Log aggregation evidence is not connected to this validation"))
        checks.append(self._not_verified("tracing_pipeline_active", issues, "Tracing delivery evidence is not connected to this validation"))

        # Alert routing
        from modules.observability.alert_enrichment import ALERT_RULES

        if len(ALERT_RULES) >= 10:
            checks.append({"name": "alert_routing_active", "status": "pass"})
        else:
            checks.append({"name": "alert_routing_active", "status": "warn"})
            issues.append(f"Only {len(ALERT_RULES)} alert rules configured (need >= 10)")

        checks.append(self._not_verified("health_dashboard_active", issues, "Health dashboard evidence is not connected to this validation"))

        passed = sum(1 for c in checks if c["status"] == "pass")
        return {
            "checks": checks,
            "total": len(checks),
            "passed": passed,
            "issues": issues,
            "critical_fail": False,
        }


production_env_service = ProductionEnvService()
