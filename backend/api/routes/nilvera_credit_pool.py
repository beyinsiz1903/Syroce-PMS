"""Nilvera credit-pool APIs.

All mutations are local Syroce ledger mutations only. No endpoint in this module
calls Nilvera or performs provider writes.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from core.helpers import require_admin, require_super_admin_guard
from core.integrations.nilvera.credit_pool import (
    NilveraCreditPoolError,
    allocate_to_tenant,
    consume_tenant_credits,
    get_pool_summary,
    get_tenant_balance,
    list_events,
    record_purchase,
    set_low_balance_threshold,
)
from models.schemas import User

router = APIRouter(prefix="/api/integrations/nilvera/credits", tags=["Integrations", "Nilvera Credits"])


class PurchaseRequest(BaseModel):
    credits: int = Field(ge=100_000)
    purchased_at: datetime | None = None
    reference: str | None = Field(default=None, max_length=200)


class AllocationRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    credits: int = Field(ge=100)
    reference: str | None = Field(default=None, max_length=200)


class ConsumptionRequest(BaseModel):
    tenant_id: str = Field(min_length=1, max_length=128)
    credits: int = Field(default=1, ge=1)
    reference: str | None = Field(default=None, max_length=200)


class ThresholdRequest(BaseModel):
    low_balance_threshold: int = Field(ge=0)


def _translate(exc: NilveraCreditPoolError) -> HTTPException:
    detail = str(exc)
    if "insufficient" in detail:
        return HTTPException(status_code=409, detail=detail)
    return HTTPException(status_code=422, detail=detail)


@router.get("/me")
async def tenant_credit_balance(user: User = Depends(require_admin)) -> dict:
    return await get_tenant_balance(user.tenant_id)


@router.get("/admin/summary")
async def credit_pool_summary(user: User = Depends(require_super_admin_guard(not_found=False))) -> dict:
    return await get_pool_summary()


@router.post("/admin/purchases")
async def add_credit_purchase(payload: PurchaseRequest, user: User = Depends(require_super_admin_guard(not_found=False))) -> dict:
    try:
        return await record_purchase(
            credits=payload.credits,
            purchased_at=payload.purchased_at,
            reference=payload.reference,
            actor_id=str(user.id),
        )
    except NilveraCreditPoolError as exc:
        raise _translate(exc) from None


@router.post("/admin/allocations")
async def allocate_credit(payload: AllocationRequest, user: User = Depends(require_super_admin_guard(not_found=False))) -> dict:
    try:
        return await allocate_to_tenant(
            tenant_id=payload.tenant_id,
            credits=payload.credits,
            actor_id=str(user.id),
            reference=payload.reference,
        )
    except NilveraCreditPoolError as exc:
        raise _translate(exc) from None


@router.post("/admin/consumption")
async def consume_credit(payload: ConsumptionRequest, user: User = Depends(require_super_admin_guard(not_found=False))) -> dict:
    """Local/manual ledger consumption; does not call Nilvera."""
    try:
        return await consume_tenant_credits(
            tenant_id=payload.tenant_id,
            credits=payload.credits,
            actor_id=str(user.id),
            reference=payload.reference,
        )
    except NilveraCreditPoolError as exc:
        raise _translate(exc) from None


@router.patch("/admin/settings")
async def update_credit_pool_settings(payload: ThresholdRequest, user: User = Depends(require_super_admin_guard(not_found=False))) -> dict:
    try:
        return await set_low_balance_threshold(payload.low_balance_threshold, actor_id=str(user.id))
    except NilveraCreditPoolError as exc:
        raise _translate(exc) from None


@router.get("/admin/events")
async def credit_events(
    tenant_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    user: User = Depends(require_super_admin_guard(not_found=False)),
) -> list[dict]:
    return await list_events(tenant_id=tenant_id, limit=limit)
