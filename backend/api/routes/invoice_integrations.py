"""API routes for Invoice Integrations and Reconciliation."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel

from core.integrations.invoice_status_repository import InvoiceStatusRepository
from core.integrations.invoice_sync_repository import InvoiceSyncRepository
from core.tenant_db import get_db_for_tenant
from models.schemas.invoice_sync import InvoiceSyncState
from modules.event_bus.abstraction import event_bus

router = APIRouter(prefix="/api/integrations/invoices", tags=["Integrations", "Reconciliation"])


class ReconcileInvoiceStatusRequest(BaseModel):
    resolution: Literal[
        "KEEP_SUBMITTED",
        "MARK_ACCEPTED",
        "MARK_REJECTED",
        "MARK_CANCELLED",
    ]
    note: str


from core.security import get_current_user
from models.schemas import User


@router.get("/reconciliation")
async def list_reconciliation_records(
    user: User = Depends(get_current_user)
):
    """
    List records that require manual reconciliation.
    """
    db = get_db_for_tenant(user.tenant_id)
    cursor = db.invoice_sync.find({"reconciliation_required": True}).limit(100)
    docs = await cursor.to_list(length=100)
    # We should normally return a paginated model. For now returning dicts.
    return {"data": list(docs)}


@router.get("/{dispatch_id}/status")
async def get_invoice_status(
    dispatch_id: str = Path(...),
    user: User = Depends(get_current_user)
):
    """
    Get the sync status of an invoice.
    """
    record = await InvoiceSyncRepository.get_by_id(user.tenant_id, dispatch_id)
    if not record:
        raise HTTPException(status_code=404, detail="Dispatch record not found")
    return record


@router.post("/{dispatch_id}/reconcile")
async def reconcile_invoice_status(
    req: ReconcileInvoiceStatusRequest,
    dispatch_id: str = Path(...),
    user: User = Depends(get_current_user)
):
    """
    Manually reconcile a dispatch record stuck in UNKNOWN or inconsistent state.
    """
    if not req.note or not req.note.strip():
        raise HTTPException(status_code=400, detail="Note is required for reconciliation")

    record = await InvoiceSyncRepository.get_by_id(user.tenant_id, dispatch_id)
    if not record:
        raise HTTPException(status_code=404, detail="Dispatch record not found")

    if not record.reconciliation_required:
        raise HTTPException(status_code=400, detail="Record does not require reconciliation")

    target_state_map = {
        "KEEP_SUBMITTED": InvoiceSyncState.SUBMITTED,
        "MARK_ACCEPTED": InvoiceSyncState.ACCEPTED,
        "MARK_REJECTED": InvoiceSyncState.REJECTED,
        "MARK_CANCELLED": InvoiceSyncState.CANCELLED,
    }

    target_state = target_state_map[req.resolution]

    success = await InvoiceStatusRepository.reconcile_status(
        tenant_id=user.tenant_id,
        dispatch_id=dispatch_id,
        target_state=target_state,
        note=req.note,
        actor=str(user.id)
    )

    if not success:
        raise HTTPException(status_code=409, detail="Failed to reconcile record. It may have been updated concurrently.")

    await event_bus.publish("invoice_status.reconciled", {
        "dispatch_id": dispatch_id,
        "tenant_id": user.tenant_id,
        "actor": str(user.id),
        "previous_state": record.state.value,
        "new_state": target_state.value,
        "reason": record.reconciliation_reason
    })

    return {"status": "success", "dispatch_id": dispatch_id, "new_state": target_state.value}


@router.post("/{dispatch_id}/retry-status")
async def retry_invoice_status(
    dispatch_id: str = Path(...),
    user: User = Depends(get_current_user)
):
    """
    Force a status poll for a SUBMITTED invoice. Does not re-trigger POST /einvoice/Send/Model.
    """
    record = await InvoiceSyncRepository.get_by_id(user.tenant_id, dispatch_id)
    if not record:
        raise HTTPException(status_code=404, detail="Dispatch record not found")

    if record.state != InvoiceSyncState.SUBMITTED:
        raise HTTPException(status_code=400, detail="Only SUBMITTED records can be status-retried")

    from datetime import UTC, datetime
    now = datetime.now(UTC)

    # Update the record to be picked up immediately by the worker
    db = get_db_for_tenant(user.tenant_id)
    await db.invoice_sync.update_one(
        {"id": dispatch_id, "tenant_id": user.tenant_id},
        {"$set": {"next_status_check_at": now, "reconciliation_required": False, "updated_at": now}}
    )

    return {"status": "success", "message": "Status poll enqueued"}
