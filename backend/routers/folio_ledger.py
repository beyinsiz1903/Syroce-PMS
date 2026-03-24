"""
Folio Ledger API Router
========================
Immutable folio ledger endpoints: charge, payment, void, transfer, reconciliation.
"""
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.folio_ledger_service import FolioLedgerService, ReconciliationEngine
from core.security import get_current_user
from models.schemas import User

router = APIRouter(prefix="/api/folio-ledger", tags=["Folio Ledger"])

ledger_service = FolioLedgerService()
recon_engine = ReconciliationEngine()


class ChargeRequest(BaseModel):
    amount: float = Field(..., gt=0)
    description: str
    charge_code: str = "ROOM"
    booking_id: str = ""
    currency: str = "TRY"
    tax_amount: float = 0.0
    tax_breakdown: Optional[List[Dict]] = None
    idempotency_key: Optional[str] = None
    business_date: Optional[str] = None
    night_audit_run_id: Optional[str] = None
    metadata: Optional[Dict] = None


class PaymentRequest(BaseModel):
    amount: float = Field(..., gt=0)
    payment_method: str = "cash"
    reference: str = ""
    booking_id: str = ""
    currency: str = "TRY"
    idempotency_key: Optional[str] = None
    business_date: Optional[str] = None
    metadata: Optional[Dict] = None


class VoidRequest(BaseModel):
    reason: str


class TransferRequest(BaseModel):
    to_folio_id: str
    amount: float = Field(..., gt=0)
    description: str = "Transfer"
    booking_id: str = ""
    idempotency_key: Optional[str] = None


@router.post("/{folio_id}/charge")
async def post_charge(folio_id: str, body: ChargeRequest, current_user: User = Depends(get_current_user)):
    try:
        result = await ledger_service.post_charge(
            tenant_id=current_user.tenant_id,
            folio_id=folio_id,
            booking_id=body.booking_id,
            amount=body.amount,
            description=body.description,
            charge_code=body.charge_code,
            currency=body.currency,
            tax_amount=body.tax_amount,
            tax_breakdown=body.tax_breakdown,
            idempotency_key=body.idempotency_key,
            posted_by=current_user.id,
            business_date=body.business_date,
            night_audit_run_id=body.night_audit_run_id,
            metadata=body.metadata,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{folio_id}/payment")
async def post_payment(folio_id: str, body: PaymentRequest, current_user: User = Depends(get_current_user)):
    try:
        result = await ledger_service.post_payment(
            tenant_id=current_user.tenant_id,
            folio_id=folio_id,
            booking_id=body.booking_id,
            amount=body.amount,
            payment_method=body.payment_method,
            reference=body.reference,
            currency=body.currency,
            idempotency_key=body.idempotency_key,
            posted_by=current_user.id,
            business_date=body.business_date,
            metadata=body.metadata,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{folio_id}/void/{entry_id}")
async def void_entry(folio_id: str, entry_id: str, body: VoidRequest, current_user: User = Depends(get_current_user)):
    try:
        result = await ledger_service.void_entry(
            tenant_id=current_user.tenant_id,
            folio_id=folio_id,
            entry_id=entry_id,
            reason=body.reason,
            posted_by=current_user.id,
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{folio_id}/transfer")
async def transfer(folio_id: str, body: TransferRequest, current_user: User = Depends(get_current_user)):
    try:
        result = await ledger_service.transfer(
            tenant_id=current_user.tenant_id,
            from_folio_id=folio_id,
            to_folio_id=body.to_folio_id,
            amount=body.amount,
            description=body.description,
            booking_id=body.booking_id,
            idempotency_key=body.idempotency_key,
            posted_by=current_user.id,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{folio_id}/ledger")
async def get_ledger(folio_id: str, current_user: User = Depends(get_current_user)):
    return await ledger_service.get_ledger(current_user.tenant_id, folio_id)


@router.get("/{folio_id}/reconcile")
async def reconcile_folio(folio_id: str, current_user: User = Depends(get_current_user)):
    return await ledger_service.reconcile_folio(current_user.tenant_id, folio_id)


@router.post("/reconciliation/run")
async def run_reconciliation(current_user: User = Depends(get_current_user), business_date: Optional[str] = None):
    from datetime import datetime, timezone
    bdate = business_date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    result = await recon_engine.run_reconciliation(current_user.tenant_id, bdate)
    return result
