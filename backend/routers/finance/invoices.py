"""Auto-split from finance.py — section: invoices."""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: F401
    from openpyxl.utils import get_column_letter  # noqa: F401
except ImportError:
    Workbook = None

from core.database import db
from core.helpers import require_module
from core.sanitize import sanitize_plaintext
from core.security import get_current_user
from core.tenant_currency import get_tenant_currency
from models.schemas import (
    Invoice,
    InvoiceCreate,
    User,
)
from modules.folio.services.folio_balance_read_service import FolioBalanceReadService
from modules.folio.services.open_folio_service import OpenFolioService
from modules.pms_core.role_permission_service import require_op
from routers.finance.accounting import _validate_invoice_customer_name

try:
    from cache_manager import cached
except ImportError:
    def cached(ttl=300, key_prefix=""):
        def decorator(func):
            return func
        return decorator

router = APIRouter()
security = HTTPBearer()
folio_balance_read_service = FolioBalanceReadService()
open_folio_service = OpenFolioService()

@router.post("/invoices", response_model=Invoice)
async def create_invoice(
    invoice_data: InvoiceCreate,
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("invoices")),
):
    count = await db.invoices.count_documents({'tenant_id': current_user.tenant_id})
    invoice_number = f"INV-{count + 1:05d}"
    due_date_dt = datetime.fromisoformat(invoice_data.due_date.replace('Z', '+00:00'))
    # v95.5 — validate customer_name (anti-XML/HTML, min length) on this path too
    payload = {k: v for k, v in invoice_data.model_dump().items() if k != 'due_date'}
    if 'customer_name' in payload:
        payload['customer_name'] = _validate_invoice_customer_name(payload.get('customer_name'))
    invoice = Invoice(tenant_id=current_user.tenant_id, invoice_number=invoice_number, due_date=due_date_dt,
                     **payload)
    invoice_dict = invoice.model_dump()
    invoice_dict['issue_date'] = invoice_dict['issue_date'].isoformat()
    invoice_dict['due_date'] = invoice_dict['due_date'].isoformat()
    await db.invoices.insert_one(invoice_dict)
    return invoice


@router.get("/invoices", response_model=list[Invoice])
@cached(ttl=300, key_prefix="invoices_list")  # Cache for 5 min
async def get_invoices(
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("invoices")),
    _perm=Depends(require_op("view_finance_reports")),  # v70 Bug DG
):
    invoices = await db.invoices.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    # v95 — render-time scrub for legacy rows that contain XML/HTML fragments
    # (e.g. test seeds from earlier security probes). Persisted on next write.
    _SCRUB_FIELDS = ('billing_name', 'billing_tax_id', 'customer_name',
                     'customer_email', 'notes')
    for inv in invoices:
        for f in _SCRUB_FIELDS:
            if f in inv and isinstance(inv[f], str):
                inv[f] = sanitize_plaintext(inv[f], max_length=500)
    return invoices


@router.put("/invoices/{invoice_id}")
async def update_invoice(
    invoice_id: str,
    updates: dict[str, Any],
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("invoices")),
):
    # F8X (2026-05-24): tenant-scope both the update AND the read-back. Previously
    # the read-back used {'id': invoice_id} only, which returned (and exposed) the
    # invoice of another tenant when the update matched 0 docs. Fail-closed with
    # 404 when the invoice does not belong to the caller's tenant.
    tenant_filter = {'id': invoice_id, 'tenant_id': current_user.tenant_id}
    # Task #578 — fatura iptali kritik bir finansal mutasyon. before/after
    # snapshot alabilmek için güncelleme ÖNCESİ belgeyi oku.
    before_doc = await db.invoices.find_one(tenant_filter, {'_id': 0})
    result = await db.invoices.update_one(tenant_filter, {'$set': updates})
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Invoice not found")
    invoice_doc = await db.invoices.find_one(tenant_filter, {'_id': 0})
    if not invoice_doc:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # Task #578 — fatura durumu değişikliklerini (özellikle iptal/void)
    # tamper-evident audit trail'e before/after snapshot ile yaz. İptale
    # geçişlerde severity yükseltilir; diğer güncellemeler "info" kalır.
    try:
        old_status = (before_doc or {}).get('status')
        new_status = invoice_doc.get('status')
        is_cancellation = (
            old_status != new_status
            and isinstance(new_status, str)
            and new_status.lower() in {'cancelled', 'canceled', 'void', 'voided', 'iptal'}
        )
        from core.audit import log_audit_event
        await log_audit_event(
            tenant_id=current_user.tenant_id,
            user_id=current_user.id,
            action="invoice_cancelled" if is_cancellation else "invoice_updated",
            entity_type="invoice",
            entity_id=invoice_id,
            details=(
                f"Invoice {invoice_doc.get('invoice_number') or invoice_id} "
                f"status {old_status} -> {new_status}"
                if is_cancellation
                else f"Invoice {invoice_doc.get('invoice_number') or invoice_id} updated"
            ),
            before_value={"status": old_status, "total": (before_doc or {}).get('total')},
            after_value={"status": new_status, "changed_fields": sorted(updates.keys())},
            severity="warning" if is_cancellation else "info",
        )
    except Exception:
        import logging
        logging.getLogger(__name__).exception("audit log for update_invoice failed")

    return invoice_doc


@router.get("/invoices/stats")
@cached(ttl=120, key_prefix="invoices_stats")  # Cache for 2 min - faster refresh
async def get_invoice_stats(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),  # v70 Bug DG
):
    invoices = await db.invoices.find({'tenant_id': current_user.tenant_id}, {'_id': 0}).to_list(1000)
    total_revenue = sum(inv.get('total', 0) for inv in invoices if inv.get('status') == 'paid')
    pending_amount = sum(inv.get('total', 0) for inv in invoices if inv.get('status') in ['draft', 'sent'])
    overdue_amount = sum(inv.get('total', 0) for inv in invoices if inv.get('status') == 'overdue')
    currency_code, currency_symbol = await get_tenant_currency(current_user.tenant_id)
    return {
        'total_invoices': len(invoices),
        'total_revenue': total_revenue,
        'pending_amount': pending_amount,
        'overdue_amount': overdue_amount,
        'currency': currency_code,
        'currency_symbol': currency_symbol,
    }


