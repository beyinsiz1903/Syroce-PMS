"""
Security — Hardening Router
Production runtime APIs for audit status, rate limiting,
credential checks, tenant guard, and log sanitization status.
"""
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional

from core.security import get_current_user
from models.schemas import User
from security.audit_validator import audit_validator
from security.rate_limiter import tenant_rate_limiter
from security.credential_guard import credential_guard
from security.tenant_guard import tenant_guard
from security.log_sanitizer import sanitize_string, detect_secret_leakage

router = APIRouter(prefix="/api/security", tags=["Security / Hardening"])


@router.get("/audit/status", summary="Audit trail status")
async def get_audit_status(
    hours: int = Query(24, ge=1, le=168),
    current_user: User = Depends(get_current_user),
):
    """Validate audit trail completeness for the tenant."""
    completeness = await audit_validator.validate_completeness(
        current_user.tenant_id, hours=hours,
    )
    summary = await audit_validator.get_audit_summary(
        current_user.tenant_id, hours=hours,
    )
    return {
        "completeness": completeness,
        "summary": summary,
    }


@router.get("/rate-limit/status", summary="Rate limiting status")
async def get_rate_limit_status(
    current_user: User = Depends(get_current_user),
):
    """Get rate limiting statistics for the current tenant."""
    stats = tenant_rate_limiter.get_stats(current_user.tenant_id)
    return {
        "tenant_id": current_user.tenant_id,
        "enforcement": "active",
        "stats": stats,
    }


@router.post("/credentials/check", summary="Scan for weak credentials")
async def check_credentials(
    current_user: User = Depends(get_current_user),
):
    """Scan tenant users for weak/default credentials. Admin only."""
    if current_user.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    result = await credential_guard.scan_weak_credentials(tenant_id=current_user.tenant_id)
    return result


@router.get("/tenant-guard/status", summary="Tenant guard status")
async def get_tenant_guard_status(
    current_user: User = Depends(get_current_user),
):
    """Get tenant isolation guard enforcement status and violations."""
    return await tenant_guard.get_status(current_user.tenant_id)


@router.get("/log-sanitization/status", summary="Log sanitization status")
async def get_log_sanitization_status(
    current_user: User = Depends(get_current_user),
):
    """Check log sanitization enforcement status."""
    # Run a sample check
    test_inputs = [
        "password=secret123",
        "api_key=sk-test123456",
        "user@example.com",
        "4111111111111111",
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.test",
    ]
    sanitized = [sanitize_string(t) for t in test_inputs]
    all_masked = all(
        t != s for t, s in zip(test_inputs, sanitized)
    )

    return {
        "enforcement": "active",
        "patterns_active": len(test_inputs),
        "all_patterns_working": all_masked,
        "sample_results": [
            {"input_type": "password", "masked": test_inputs[0] != sanitized[0]},
            {"input_type": "api_key", "masked": test_inputs[1] != sanitized[1]},
            {"input_type": "email", "masked": test_inputs[2] != sanitized[2]},
            {"input_type": "card_number", "masked": test_inputs[3] != sanitized[3]},
            {"input_type": "jwt_token", "masked": test_inputs[4] != sanitized[4]},
        ],
    }


@router.post("/secret-leakage/check", summary="Check for secret leakage")
async def check_secret_leakage(
    text: str = Query(..., description="Text to check for leaked secrets"),
    current_user: User = Depends(get_current_user),
):
    """Check if a string contains leaked API keys or secrets."""
    if current_user.role not in ("admin", "super_admin"):
        raise HTTPException(status_code=403, detail="Admin access required")
    leaked = detect_secret_leakage(text)
    return {
        "contains_secret": leaked,
        "action": "alert" if leaked else "safe",
    }
