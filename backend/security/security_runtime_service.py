"""
Security — Runtime Service
Orchestrates audit validation, rate limiting, credential scanning,
tenant guard, and log sanitization. No FastAPI dependencies.
"""
from typing import Dict, Any

from common.context import OperationContext
from common.result import ServiceResult
from common.errors import ForbiddenError


class SecurityRuntimeService:
    """Business logic for security runtime operations."""

    def __init__(self):
        from security.audit_validator import audit_validator
        from security.rate_limiter import tenant_rate_limiter
        from security.credential_guard import credential_guard
        from security.tenant_guard import tenant_guard
        from security.log_sanitizer import sanitize_string, detect_secret_leakage
        self._audit = audit_validator
        self._rate_limiter = tenant_rate_limiter
        self._credential_guard = credential_guard
        self._tenant_guard = tenant_guard
        self._sanitize = sanitize_string
        self._detect_leakage = detect_secret_leakage

    async def get_audit_status(self, ctx: OperationContext, hours: int = 24) -> ServiceResult:
        completeness = await self._audit.validate_completeness(ctx.tenant_id, hours=hours)
        summary = await self._audit.get_audit_summary(ctx.tenant_id, hours=hours)
        return ServiceResult.success({"completeness": completeness, "summary": summary})

    async def get_rate_limit_status(self, ctx: OperationContext) -> ServiceResult:
        stats = self._rate_limiter.get_stats(ctx.tenant_id)
        return ServiceResult.success({
            "tenant_id": ctx.tenant_id,
            "enforcement": "active",
            "stats": stats,
        })

    async def check_credentials(self, ctx: OperationContext) -> ServiceResult:
        if ctx.actor_role not in ("admin", "super_admin"):
            return ServiceResult.fail("Admin access required", "FORBIDDEN")
        result = await self._credential_guard.scan_weak_credentials(tenant_id=ctx.tenant_id)
        return ServiceResult.success(result)

    async def get_tenant_guard_status(self, ctx: OperationContext) -> ServiceResult:
        data = await self._tenant_guard.get_status(ctx.tenant_id)
        return ServiceResult.success(data)

    async def get_log_sanitization_status(self, ctx: OperationContext) -> ServiceResult:
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


security_runtime_service = SecurityRuntimeService()
