"""
Security — Hardening Router
Production runtime APIs for audit status, rate limiting,
credential checks, tenant guard, and log sanitization status.
Thin router: delegates all business logic to SecurityRuntimeService.
"""
from fastapi import APIRouter, HTTPException, Depends, Query

from core.security import get_current_user
from models.schemas import User
from common.context import OperationContext
from security.security_runtime_service import security_runtime_service

router = APIRouter(prefix="/api/security", tags=["Security / Hardening"])


def _ctx(user: User) -> OperationContext:
    return OperationContext.from_user(user)


@router.get("/audit/status", summary="Audit trail status")
async def get_audit_status(
    hours: int = Query(24, ge=1, le=168),
    current_user: User = Depends(get_current_user),
):
    result = await security_runtime_service.get_audit_status(_ctx(current_user), hours=hours)
    return result.data


@router.get("/rate-limit/status", summary="Rate limiting status")
async def get_rate_limit_status(current_user: User = Depends(get_current_user)):
    result = await security_runtime_service.get_rate_limit_status(_ctx(current_user))
    return result.data


@router.post("/credentials/check", summary="Scan for weak credentials")
async def check_credentials(current_user: User = Depends(get_current_user)):
    result = await security_runtime_service.check_credentials(_ctx(current_user))
    if not result.ok:
        raise HTTPException(status_code=403, detail=result.error)
    return result.data


@router.get("/tenant-guard/status", summary="Tenant guard status")
async def get_tenant_guard_status(current_user: User = Depends(get_current_user)):
    result = await security_runtime_service.get_tenant_guard_status(_ctx(current_user))
    return result.data


@router.get("/log-sanitization/status", summary="Log sanitization status")
async def get_log_sanitization_status(current_user: User = Depends(get_current_user)):
    result = await security_runtime_service.get_log_sanitization_status(_ctx(current_user))
    return result.data


@router.post("/secret-leakage/check", summary="Check for secret leakage")
async def check_secret_leakage(
    text: str = Query(..., description="Text to check for leaked secrets"),
    current_user: User = Depends(get_current_user),
):
    result = await security_runtime_service.check_secret_leakage(_ctx(current_user), text)
    if not result.ok:
        raise HTTPException(status_code=403, detail=result.error)
    return result.data
