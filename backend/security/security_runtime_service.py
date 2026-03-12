"""
Security — Runtime Service
Production-grade: aggregates real tenant guard violations, credential scan results,
audit completeness, rate limit metrics, log sanitization coverage, and security event history.
"""
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any

from common.context import OperationContext
from common.result import ServiceResult
from core.database import db

logger = logging.getLogger(__name__)


class SecurityRuntimeService:
    """Production security runtime operations with real DB queries."""

    def __init__(self):
        from security.audit_validator import audit_validator
        from security.rate_limiter import tenant_rate_limiter
        from security.credential_guard import credential_guard
        from security.tenant_guard import tenant_guard
        from security.property_guard import property_guard
        from security.log_sanitizer import sanitize_string, detect_secret_leakage
        self._audit = audit_validator
        self._rate_limiter = tenant_rate_limiter
        self._credential_guard = credential_guard
        self._tenant_guard = tenant_guard
        self._property_guard = property_guard
        self._sanitize = sanitize_string
        self._detect_leakage = detect_secret_leakage

    async def get_audit_status(self, ctx: OperationContext, hours: int = 24) -> ServiceResult:
        """Real audit completeness and gap analysis."""
        completeness = await self._audit.validate_completeness(ctx.tenant_id, hours=hours)
        summary = await self._audit.get_audit_summary(ctx.tenant_id, hours=hours)

        total_entries = completeness.get("total_audit_entries", 0)
        gaps = completeness.get("gaps_found", 0)
        bookings_modified = completeness.get("bookings_modified", 0)
        rooms_modified = completeness.get("rooms_modified", 0)

        # Completeness score (0-100)
        total_ops = bookings_modified + rooms_modified
        if total_ops > 0:
            covered = total_entries
            score = min(100, round((covered / max(total_ops, 1)) * 100))
        else:
            score = 100 if total_entries >= 0 else 0

        severity = "info"
        if gaps > 0:
            severity = "warning" if gaps <= 3 else "critical"

        return ServiceResult.success({
            "completeness": completeness,
            "summary": summary,
            "completeness_score": score,
            "severity": severity,
            "total_entries_period": total_entries,
            "gaps_found": gaps,
        })

    async def get_rate_limit_status(self, ctx: OperationContext) -> ServiceResult:
        """Real rate limit stats with burst detection."""
        stats = self._rate_limiter.get_stats(ctx.tenant_id)
        all_stats = self._rate_limiter.get_stats()

        allowed = stats.get("allowed", 0)
        rejected = stats.get("rejected", 0)
        total = allowed + rejected
        burst_detected = rejected > 10

        severity = "info"
        if rejected > 50:
            severity = "critical"
        elif rejected > 10:
            severity = "warning"

        return ServiceResult.success({
            "tenant_id": ctx.tenant_id,
            "enforcement": "active",
            "stats": stats,
            "burst_detected": burst_detected,
            "severity": severity,
            "total_requests": total,
            "rejection_rate": round((rejected / max(total, 1)) * 100, 1),
            "global_tenants_tracked": len(all_stats) if isinstance(all_stats, dict) else 0,
        })

    async def check_credentials(self, ctx: OperationContext) -> ServiceResult:
        if ctx.actor_role not in ("admin", "super_admin"):
            return ServiceResult.fail("Admin access required", "FORBIDDEN")
        result = await self._credential_guard.scan_weak_credentials(tenant_id=ctx.tenant_id)

        severity = "info"
        findings = result.get("findings", [])
        if any(f.get("severity") == "critical" for f in findings):
            severity = "critical"
        elif findings:
            severity = "warning"

        return ServiceResult.success({
            **result,
            "severity": severity,
            "remediation": [
                "Force password reset for flagged users",
                "Enable MFA for admin accounts",
                "Review password policy requirements",
            ] if findings else [],
        })

    async def get_tenant_guard_status(self, ctx: OperationContext) -> ServiceResult:
        """Real tenant guard violations from DB."""
        data = await self._tenant_guard.get_status(ctx.tenant_id)

        total_violations = data.get("total_violations", 0)
        recent_violations = data.get("violations_last_24h", 0)

        severity = "info"
        if total_violations > 10 or recent_violations > 3:
            severity = "critical"
        elif total_violations > 0:
            severity = "warning"

        return ServiceResult.success({
            **data,
            "severity": severity,
        })

    async def get_log_sanitization_status(self, ctx: OperationContext) -> ServiceResult:
        """Real log sanitization pattern check."""
        test_inputs = [
            "password=secret123",
            "api_key=sk-test123456",
            "user@example.com",
            "4111111111111111",
            "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.test",
        ]
        sanitized = [self._sanitize(t) for t in test_inputs]
        all_masked = all(t != s for t, s in zip(test_inputs, sanitized))
        labels = ["password", "api_key", "email", "card_number", "jwt_token"]

        return ServiceResult.success({
            "enforcement": "active",
            "patterns_active": len(test_inputs),
            "all_patterns_working": all_masked,
            "coverage_pct": round(sum(1 for t, s in zip(test_inputs, sanitized) if t != s) / len(test_inputs) * 100),
            "sample_results": [
                {"input_type": labels[i], "masked": test_inputs[i] != sanitized[i]}
                for i in range(len(test_inputs))
            ],
        })

    async def check_secret_leakage(self, ctx: OperationContext, text: str) -> ServiceResult:
        if ctx.actor_role not in ("admin", "super_admin"):
            return ServiceResult.fail("Admin access required", "FORBIDDEN")
        leaked = self._detect_leakage(text)
        return ServiceResult.success({
            "contains_secret": leaked,
            "action": "alert" if leaked else "safe",
        })

    async def get_comprehensive_status(self, ctx: OperationContext) -> ServiceResult:
        """Aggregated security health for dashboard consumption."""
        try:
            now = datetime.now(timezone.utc)

            # Tenant guard violations
            tg = await self._tenant_guard.get_status(ctx.tenant_id)
            tg_violations = tg.get("total_violations", 0)
            tg_recent = tg.get("violations_last_24h", 0)

            # Property guard (check if any denial exists)
            pg_denials = await db.get_collection("property_access_denials").count_documents(
                {"tenant_id": ctx.tenant_id}
            ) if "property_access_denials" in await db.list_collection_names() else 0

            # Audit completeness
            audit = await self._audit.validate_completeness(ctx.tenant_id, hours=24)
            audit_score = 100
            if audit.get("gaps_found", 0) > 0:
                total_ops = audit.get("bookings_modified", 0) + audit.get("rooms_modified", 0)
                if total_ops > 0:
                    audit_score = min(100, round((audit.get("total_audit_entries", 0) / max(total_ops, 1)) * 100))

            # Rate limit burst
            rl_stats = self._rate_limiter.get_stats(ctx.tenant_id)
            rl_rejected = rl_stats.get("rejected", 0)

            # Log sanitization
            test = self._sanitize("password=test123")
            sanitization_active = test != "password=test123"

            # Recent security events
            sec_events = await db.security_events.find(
                {"tenant_id": ctx.tenant_id, "timestamp": {"$gte": (now - timedelta(hours=24)).isoformat()}},
                {"_id": 0}
            ).sort("timestamp", -1).limit(10).to_list(10) if "security_events" in await db.list_collection_names() else []

            # Overall severity
            severity = "info"
            if tg_violations > 10 or rl_rejected > 50:
                severity = "critical"
            elif tg_recent > 0 or rl_rejected > 10 or audit.get("gaps_found", 0) > 0:
                severity = "warning"

            return ServiceResult.success({
                "severity": severity,
                "tenant_guard": {"violations": tg_violations, "recent_24h": tg_recent},
                "property_guard": {"denials": pg_denials},
                "audit": {"completeness_score": audit_score, "gaps": audit.get("gaps_found", 0)},
                "rate_limiting": {"rejected": rl_rejected, "burst_detected": rl_rejected > 10},
                "log_sanitization": {"active": sanitization_active},
                "recent_events": sec_events,
                "checked_at": now.isoformat(),
            })
        except Exception as e:
            logger.error(f"SecurityRuntimeService.get_comprehensive_status error: {e}")
            return ServiceResult.success({
                "severity": "warning",
                "error": str(e)[:100],
                "checked_at": datetime.now(timezone.utc).isoformat(),
            })


security_runtime_service = SecurityRuntimeService()
