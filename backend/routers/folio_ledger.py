"""
Folio Ledger API Router
========================
Immutable folio ledger endpoints: charge, payment, void, transfer, reconciliation.
"""

from datetime import UTC

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.folio_ledger_service import FolioLedgerService, ReconciliationEngine
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import (
    RolePermissionService,
    require_op,  # v94 DW
)

# Bug CQ fix — RBAC enforcement (paralel endpoint set'inde RBAC eksikti, hk yapabiliyordu)
_rps = RolePermissionService()


def _enforce_perm(role: str, op: str) -> None:
    _rps.enforce_permission(role, op)


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
    tax_breakdown: list[dict] | None = None
    idempotency_key: str | None = None
    business_date: str | None = None
    night_audit_run_id: str | None = None
    metadata: dict | None = None


class PaymentRequest(BaseModel):
    amount: float = Field(..., gt=0)
    payment_method: str = "cash"
    reference: str = ""
    booking_id: str = ""
    currency: str = "TRY"
    idempotency_key: str | None = None
    business_date: str | None = None
    metadata: dict | None = None


class VoidRequest(BaseModel):
    reason: str


class TransferRequest(BaseModel):
    to_folio_id: str
    amount: float = Field(..., gt=0)
    description: str = "Transfer"
    booking_id: str = ""
    idempotency_key: str | None = None


@router.post("/{folio_id}/charge")
async def post_charge(
    folio_id: str,
    body: ChargeRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v97 DW
):
    _enforce_perm(current_user.role, "post_charge")  # Bug CQ fix
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
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{folio_id}/payment")
async def post_payment(
    folio_id: str,
    body: PaymentRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v94 DW
):
    _enforce_perm(current_user.role, "post_payment")  # Bug CQ fix
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
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{folio_id}/void/{entry_id}")
async def void_entry(
    folio_id: str,
    entry_id: str,
    body: VoidRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_charge")),  # v97 DW
):
    _enforce_perm(current_user.role, "void_charge")  # Bug CQ fix
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
async def transfer(
    folio_id: str,
    body: TransferRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v97 DW
):
    _enforce_perm(current_user.role, "transfer_folio")  # Bug CQ fix
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
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{folio_id}/ledger")
async def get_ledger(folio_id: str, current_user: User = Depends(get_current_user)):
    _enforce_perm(current_user.role, "view_folio")  # Bug CQ fix
    try:
        return await ledger_service.get_ledger(current_user.tenant_id, folio_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{folio_id}/reconcile")
async def reconcile_folio(folio_id: str, current_user: User = Depends(get_current_user)):
    _enforce_perm(current_user.role, "view_folio")  # Bug CQ fix
    try:
        return await ledger_service.reconcile_folio(current_user.tenant_id, folio_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/reconciliation/run")
async def run_reconciliation(
    current_user: User = Depends(get_current_user),
    business_date: str | None = None,
    _perm=Depends(require_op("post_payment")),  # v97 DW
):
    # Bug CQ fix — reconciliation report contains tenant-wide financial drift data; finance/admin only
    _enforce_perm(current_user.role, "close_folio")
    from datetime import datetime

    bdate = business_date or datetime.now(UTC).strftime("%Y-%m-%d")
    result = await recon_engine.run_reconciliation(current_user.tenant_id, bdate)
    return result
