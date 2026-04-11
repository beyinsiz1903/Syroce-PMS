"""
Pilot Hotel Readiness — API Router
====================================
"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from common.context import OperationContext
from common.response import from_service_result
from core.security import get_current_user
from ops.pilot_readiness import pilot_readiness_service

router = APIRouter(prefix="/api/pilot", tags=["Pilot Readiness"])


class SignOffRequest(BaseModel):
    check_id: str
    notes: str = ""

class FeatureToggleRequest(BaseModel):
    feature: str
    enabled: bool


@router.get("/readiness")
async def run_readiness_check(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await pilot_readiness_service.run_readiness_check(ctx)
    return from_service_result(result)


@router.post("/sign-off")
async def sign_off_check(req: SignOffRequest, user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await pilot_readiness_service.sign_off_check(ctx, req.check_id, req.notes)
    if not result.ok:
        raise HTTPException(status_code=400, detail=from_service_result(result))
    return from_service_result(result)


@router.get("/feature-toggles")
async def get_feature_toggles(user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await pilot_readiness_service.get_feature_toggles(ctx)
    return from_service_result(result)


@router.post("/feature-toggles")
async def set_feature_toggle(req: FeatureToggleRequest, user=Depends(get_current_user)):
    ctx = OperationContext.from_user(user)
    result = await pilot_readiness_service.set_feature_toggle(ctx, req.feature, req.enabled)
    if not result.ok:
        code = 403 if result.code == "FORBIDDEN" else 400
        raise HTTPException(status_code=code, detail=from_service_result(result))
    return from_service_result(result)
