"""Auto-split from finance.py — section: invoices."""
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: F401
    from openpyxl.utils import get_column_letter  # noqa: F401
except ImportError:
    Workbook = None

from core.database import db
from core.helpers import require_module
from core.security import get_current_user
from models.schemas import (
    Invoice,
    InvoiceCreate,
    User,
)
from modules.folio.services.folio_balance_read_service import FolioBalanceReadService
from modules.folio.services.open_folio_service import OpenFolioService
from modules.pms_core.role_permission_service import require_op

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
    invoice = Invoice(tenant_id=current_user.tenant_id, invoice_number=invoice_number, due_date=due_date_dt,
                     **{k: v for k, v in invoice_data.model_dump().items() if k != 'due_date'})
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
    return invoices


@router.put("/invoices/{invoice_id}")
async def update_invoice(
    invoice_id: str,
    updates: dict[str, Any],
    current_user: User = Depends(get_current_user),
    _: None = Depends(require_module("invoices")),
):
    await db.invoices.update_one({'id': invoice_id, 'tenant_id': current_user.tenant_id}, {'$set': updates})
    invoice_doc = await db.invoices.find_one({'id': invoice_id}, {'_id': 0})
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
    return {'total_invoices': len(invoices), 'total_revenue': total_revenue, 'pending_amount': pending_amount, 'overdue_amount': overdue_amount}


