"""
Channel Manager — Provider Validation API Router
=================================================
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from core.security import get_current_user
from common.context import OperationContext
from common.response import from_service_result
from domains.channel_manager.provider_validation import provider_validation_service

router = APIRouter(prefix="/api/cm/validation", tags=["CM Provider Validation"])


class ValidateProviderRequest(BaseModel):
    provider_id: str


@router.post("/run")
async def run_validation(req: ValidateProviderRequest, user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await provider_validation_service.run_provider_validation(ctx, req.provider_id)
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)


@router.get("/sync-lag/{provider_id}")
async def get_sync_lag(
    provider_id: str,
    hours: int = Query(24, ge=1, le=168),
    user=Depends(get_current_user),
):
    ctx = OperationContext.from_user(user)
    result = await provider_validation_service.get_sync_lag_report(ctx, provider_id, hours)
    return from_service_result(result)


@router.get("/providers")
async def get_providers(user=Depends(get_current_user)):
    result = await provider_validation_service.get_provider_contracts()
    return from_service_result(result)
