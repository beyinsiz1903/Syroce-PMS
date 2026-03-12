"""
Tenant Isolation — Validation API Router
=========================================
"""
from fastapi import APIRouter, Depends, Query
from typing import Optional

from core.security import get_current_user
from common.context import OperationContext
from common.response import from_service_result
from security.tenant_isolation_service import tenant_isolation_service

router = APIRouter(prefix="/api/tenant-isolation/v2", tags=["Tenant Isolation v2"])


@router.get("/validate")
async def run_isolation_validation(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await tenant_isolation_service.run_isolation_validation(ctx)
    return from_service_result(result)


@router.get("/noisy-tenants")
async def detect_noisy_tenants(
    window_minutes: int = Query(60, ge=5, le=1440),
    user=Depends(get_current_user),
):
    ctx = OperationContext.from_user(user)
    result = await tenant_isolation_service.detect_noisy_tenants(ctx, window_minutes)
    return from_service_result(result)


@router.get("/resource-fairness")
async def get_resource_fairness(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await tenant_isolation_service.get_resource_fairness(ctx)
    return from_service_result(result)
