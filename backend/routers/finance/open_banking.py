"""Tenant-scoped bank transaction reconciliation backed by the durable GL."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op
from shared_kernel.gl_posting import GLPostingError, post_journal_entry

router = APIRouter(prefix="/banking", tags=["Açık Bankacılık"])


class ReconcileRequest(BaseModel):
    transaction_id: str
    invoice_id: str


def _mask_account(value: str | None) -> str | None:
    compact = "".join((value or "").split())
    if not compact:
        return None
    if len(compact) <= 6:
        return "*" * len(compact)
    return f"{compact[:2]}{'*' * (len(compact) - 6)}{compact[-4:]}"


def _safe_transaction(transaction: dict) -> dict:
    return {
        "id": transaction.get("id"),
        "date": transaction.get("date"),
        "amount": transaction.get("amount", 0),
        "description": transaction.get("description", ""),
        "sender_name": transaction.get("sender_name", ""),
        "sender_account_masked": _mask_account(transaction.get("sender_iban")),
        "status": transaction.get("status", "unmatched"),
        "matched_with": transaction.get("matched_with"),
    }


@router.get("/transactions")
async def get_transactions(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
):
    """List the caller tenant's imported bank transactions without raw account data."""
    transactions = (
        await db.bank_transactions.find(
            {"tenant_id": current_user.tenant_id},
            {"_id": 0},
        )
        .sort("date", -1)
        .limit(1000)
        .to_list(1000)
    )
    return [_safe_transaction(transaction) for transaction in transactions]


@router.get("/open-invoices")
async def get_open_invoices(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
):
    """List durable tenant invoices that still have an outstanding balance."""
    invoices = (
        await db.invoices.find(
            {
                "tenant_id": current_user.tenant_id,
                "status": {"$nin": ["paid", "cancelled", "canceled", "void", "voided"]},
                "payment_status": {"$nin": ["paid"]},
            },
            {
                "_id": 0,
                "id": 1,
                "invoice_number": 1,
                "customer_name": 1,
                "billing_name": 1,
                "total": 1,
                "amount_paid": 1,
                "status": 1,
                "payment_status": 1,
            },
        )
        .sort("issue_date", -1)
        .limit(1000)
        .to_list(1000)
    )
    return [
        {
            "id": invoice.get("id"),
            "number": invoice.get("invoice_number") or "-",
            "client_name": invoice.get("customer_name") or invoice.get("billing_name") or "-",
            "amount": max(
                round(
                    float(invoice.get("total") or 0) - float(invoice.get("amount_paid") or 0),
                    2,
                ),
                0,
            ),
            "status": invoice.get("payment_status") or invoice.get("status") or "pending",
        }
        for invoice in invoices
    ]


@router.post("/sync")
async def sync_bank_transactions(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),
):
    """Fail closed until a real bank connector is configured for the tenant."""
    raise HTTPException(
        status_code=409,
        detail="Bu otel için gerçek banka bağlantısı yapılandırılmamış.",
    )


@router.post("/reconcile")
async def reconcile_transaction(
    request: ReconcileRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),
):
    """Match one durable bank transaction to one invoice and post one GL entry."""
    tenant_id = current_user.tenant_id
    transaction = await db.bank_transactions.find_one(
        {"id": request.transaction_id, "tenant_id": tenant_id},
        {"_id": 0},
    )
    if not transaction:
        raise HTTPException(status_code=404, detail="Banka işlemi bulunamadı.")

    invoice = await db.invoices.find_one(
        {"id": request.invoice_id, "tenant_id": tenant_id},
        {"_id": 0},
    )
    if not invoice:
        raise HTTPException(status_code=404, detail="Fatura bulunamadı.")

    if transaction.get("status") == "matched":
        if transaction.get("matched_invoice_id") == request.invoice_id and transaction.get("journal_entry_id"):
            return {"status": "success", "already_reconciled": True}
        raise HTTPException(status_code=409, detail="Bu işlem daha önce eşleştirilmiş.")
    if transaction.get("status") not in {None, "unmatched"}:
        raise HTTPException(status_code=409, detail="Bu işlem başka bir mutabakat tarafından işleniyor.")

    amount = round(float(transaction.get("amount") or 0), 2)
    if amount <= 0:
        raise HTTPException(status_code=400, detail="Banka işlem tutarı pozitif olmalıdır.")

    claim_id = f"bank-reconcile:{request.transaction_id}"
    claim = await db.bank_transactions.update_one(
        {
            "id": request.transaction_id,
            "tenant_id": tenant_id,
            "$or": [
                {"status": {"$in": [None, "unmatched"]}},
                {"status": "reconciling", "reconciliation_claim_id": claim_id},
            ],
        },
        {
            "$set": {
                "status": "reconciling",
                "reconciliation_claim_id": claim_id,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        },
    )
    if claim.matched_count != 1:
        raise HTTPException(status_code=409, detail="Bu işlem başka bir mutabakat tarafından alındı.")

    invoice_number = invoice.get("invoice_number") or "-"
    actor = getattr(current_user, "id", None) or getattr(current_user, "user_id", None) or "system"
    invoice_applied = request.transaction_id in (invoice.get("reconciled_bank_transaction_ids") or [])
    if not invoice_applied:
        invoice_claim = await db.invoices.update_one(
            {
                "id": request.invoice_id,
                "tenant_id": tenant_id,
                "reconciled_bank_transaction_ids": {"$ne": request.transaction_id},
                "$or": [
                    {"bank_reconciliation_claim_id": {"$exists": False}},
                    {"bank_reconciliation_claim_id": claim_id},
                ],
            },
            {"$set": {"bank_reconciliation_claim_id": claim_id}},
        )
        if invoice_claim.matched_count != 1:
            await db.bank_transactions.update_one(
                {"id": request.transaction_id, "tenant_id": tenant_id, "reconciliation_claim_id": claim_id},
                {"$set": {"status": "unmatched"}, "$unset": {"reconciliation_claim_id": ""}},
            )
            raise HTTPException(status_code=409, detail="Fatura başka bir mutabakat tarafından işleniyor.")
        invoice = await db.invoices.find_one(
            {"id": request.invoice_id, "tenant_id": tenant_id, "bank_reconciliation_claim_id": claim_id},
            {"_id": 0},
        )
        total = round(float((invoice or {}).get("total") or 0), 2)
        amount_paid_before = round(float((invoice or {}).get("amount_paid") or 0), 2)
        outstanding = round(total - amount_paid_before, 2)
        if total <= 0 or outstanding <= 0 or amount - outstanding > 0.005:
            await db.invoices.update_one(
                {"id": request.invoice_id, "tenant_id": tenant_id, "bank_reconciliation_claim_id": claim_id},
                {"$unset": {"bank_reconciliation_claim_id": ""}},
            )
            await db.bank_transactions.update_one(
                {"id": request.transaction_id, "tenant_id": tenant_id, "reconciliation_claim_id": claim_id},
                {"$set": {"status": "unmatched"}, "$unset": {"reconciliation_claim_id": ""}},
            )
            raise HTTPException(status_code=409, detail="Banka tutarı faturanın açık bakiyesini aşıyor.")
    try:
        journal = await post_journal_entry(
            db,
            tenant_id,
            date=transaction.get("date"),
            memo=f"Banka mutabakatı - {invoice_number}",
            lines=[
                {"account_code": "102", "debit": amount, "credit": 0},
                {"account_code": "120", "debit": 0, "credit": amount},
            ],
            source="bank_reconciliation",
            source_ref=request.transaction_id,
            actor=actor,
            idempotency_key=f"bank-reconcile:{request.transaction_id}",
        )

        total = round(float(invoice.get("total") or 0), 2)
        amount_paid = round(float(invoice.get("amount_paid") or 0) + amount, 2)
        payment_status = "paid" if total > 0 and amount_paid >= total else "partial"
        invoice_updates = {
            "payment_status": payment_status,
            "payment_date": datetime.now(UTC).isoformat(),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        if payment_status == "paid":
            invoice_updates["status"] = "paid"
        if not invoice_applied:
            invoice_result = await db.invoices.update_one(
                {
                    "id": request.invoice_id,
                    "tenant_id": tenant_id,
                    "bank_reconciliation_claim_id": claim_id,
                    "reconciled_bank_transaction_ids": {"$ne": request.transaction_id},
                },
                {
                    "$set": invoice_updates,
                    "$inc": {"amount_paid": amount},
                    "$addToSet": {"reconciled_bank_transaction_ids": request.transaction_id},
                    "$unset": {"bank_reconciliation_claim_id": ""},
                },
            )
        else:
            invoice_result = None
        if invoice_result is not None and invoice_result.matched_count != 1:
            applied = await db.invoices.find_one(
                {
                    "id": request.invoice_id,
                    "tenant_id": tenant_id,
                    "reconciled_bank_transaction_ids": request.transaction_id,
                },
                {"_id": 0, "id": 1},
            )
            if not applied:
                raise RuntimeError("invoice_update_failed")

        matched_at = datetime.now(UTC).isoformat()
        finalize = await db.bank_transactions.update_one(
            {
                "id": request.transaction_id,
                "tenant_id": tenant_id,
                "status": "reconciling",
                "reconciliation_claim_id": claim_id,
            },
            {
                "$set": {
                    "status": "matched",
                    "matched_invoice_id": request.invoice_id,
                    "matched_with": invoice_number,
                    "journal_entry_id": journal["id"],
                    "matched_at": matched_at,
                    "updated_at": matched_at,
                },
                "$unset": {"reconciliation_claim_id": ""},
            },
        )
        if finalize.modified_count != 1:
            finalized = await db.bank_transactions.find_one(
                {
                    "id": request.transaction_id,
                    "tenant_id": tenant_id,
                    "status": "matched",
                    "matched_invoice_id": request.invoice_id,
                    "journal_entry_id": journal["id"],
                },
                {"_id": 0, "id": 1},
            )
            if not finalized:
                raise RuntimeError("transaction_finalize_failed")
    except GLPostingError as exc:
        await db.invoices.update_one(
            {"id": request.invoice_id, "tenant_id": tenant_id, "bank_reconciliation_claim_id": claim_id},
            {"$unset": {"bank_reconciliation_claim_id": ""}},
        )
        await db.bank_transactions.update_one(
            {
                "id": request.transaction_id,
                "tenant_id": tenant_id,
                "reconciliation_claim_id": claim_id,
            },
            {"$set": {"status": "unmatched"}, "$unset": {"reconciliation_claim_id": ""}},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        await db.invoices.update_one(
            {"id": request.invoice_id, "tenant_id": tenant_id, "bank_reconciliation_claim_id": claim_id},
            {"$unset": {"bank_reconciliation_claim_id": ""}},
        )
        await db.bank_transactions.update_one(
            {
                "id": request.transaction_id,
                "tenant_id": tenant_id,
                "reconciliation_claim_id": claim_id,
            },
            {"$set": {"status": "unmatched"}, "$unset": {"reconciliation_claim_id": ""}},
        )
        raise HTTPException(
            status_code=503,
            detail="Mutabakat tamamlanamadı; kayıt eşleşmemiş durumda bırakıldı.",
        ) from exc

    return {"status": "success", "already_reconciled": False}
