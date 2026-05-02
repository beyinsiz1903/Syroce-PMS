"""Auto-split from finance.py — section: integrations."""
import asyncio
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends
from fastapi.security import HTTPBearer

from modules.pms_core.role_permission_service import require_op  # v94 DW

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: F401
    from openpyxl.utils import get_column_letter  # noqa: F401
except ImportError:
    Workbook = None

from core.database import db
from core.security import get_current_user
from models.schemas import (
    User,
)
from modules.folio.services.folio_balance_read_service import FolioBalanceReadService
from modules.folio.services.open_folio_service import OpenFolioService

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

class LogoConnector:
    """Mock Logo/Netsis connector for ERP sync"""
    def __init__(self):
        import os
        self.base_url = os.environ.get('LOGO_API_URL', 'https://logo.example/api')

    async def send_invoice(self, invoice):
        await asyncio.sleep(0.1)
        return {'external_id': f"LOGO-{invoice['id'][:8]}", 'status': 'synced', 'message': 'Invoice pushed to Logo'}

    async def send_payment(self, payment):
        await asyncio.sleep(0.1)
        return {'external_id': f"LOGO-PAY-{payment['id'][:8]}", 'status': 'synced', 'message': 'Payment pushed to Logo'}


class NetsisConnector:
    """Mock Netsis connector"""
    def __init__(self):
        import os
        self.base_url = os.environ.get('NETSIS_API_URL', 'https://netsis.example/api')

    async def send_invoice(self, invoice):
        await asyncio.sleep(0.1)
        return {'external_id': f"NETSIS-{invoice['id'][:8]}", 'status': 'synced', 'message': 'Invoice pushed to Netsis'}


async def _gather_invoices(tenant_id: str, since=None):
    query = {'tenant_id': tenant_id}
    if since:
        query['created_at'] = {'$gte': since}
    return await db.finance_invoices.find(query, {'_id': 0}).sort('created_at', -1).to_list(500)


async def _gather_payments(tenant_id: str, since=None):
    query = {'tenant_id': tenant_id}
    if since:
        query['created_at'] = {'$gte': since}
    return await db.finance_payments.find(query, {'_id': 0}).sort('created_at', -1).to_list(500)


async def _log_accounting_sync(tenant_id: str, payload: dict):
    record = {
        'id': str(uuid.uuid4()),
        'tenant_id': tenant_id,
        **payload,
        'created_at': datetime.now(UTC).isoformat(),
    }
    await db.accounting_sync_logs.insert_one(record)
    return record


@router.post("/finance/logo-integration/sync")
async def sync_with_logo(sync_data: dict = None, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v94 DW
):
    """Sync finance data with Logo ERP"""
    connector = LogoConnector()
    since = sync_data.get('since') if sync_data else None
    invoices = await _gather_invoices(current_user.tenant_id, since)
    payments = await _gather_payments(current_user.tenant_id, since)

    synced_invoices = []
    for invoice in invoices:
        result = await connector.send_invoice(invoice)
        synced_invoices.append({**invoice, **result})

    synced_payments = []
    for payment in payments:
        result = await connector.send_payment(payment)
        synced_payments.append({**payment, **result})

    log_entry = await _log_accounting_sync(current_user.tenant_id, {
        'provider': 'logo',
        'synced_invoices': len(synced_invoices),
        'synced_payments': len(synced_payments),
        'synced_at': datetime.now(UTC).isoformat(),
        'status': 'success'
    })

    return {
        'success': True,
        'synced_invoices': len(synced_invoices),
        'synced_payments': len(synced_payments),
        'log_id': log_entry['id']
    }



@router.post("/finance/netsis-integration/sync")
async def sync_with_netsis(sync_data: dict = None, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v94 DW
):
    connector = NetsisConnector()
    since = sync_data.get('since') if sync_data else None
    invoices = await _gather_invoices(current_user.tenant_id, since)

    synced = []
    for invoice in invoices:
        result = await connector.send_invoice(invoice)
        synced.append({**invoice, **result})

    log_entry = await _log_accounting_sync(current_user.tenant_id, {
        'provider': 'netsis',
        'synced_invoices': len(synced),
        'synced_payments': 0,
        'synced_at': datetime.now(UTC).isoformat(),
        'status': 'success'
    })

    return {
        'success': True,
        'synced_invoices': len(synced),
        'log_id': log_entry['id']
    }



@router.get("/finance/integration/logs")
async def get_integration_logs(limit: int = 20, current_user: User = Depends(get_current_user)):
    logs = await db.accounting_sync_logs.find(
        {'tenant_id': current_user.tenant_id},
        {'_id': 0}
    ).sort('created_at', -1).limit(limit).to_list(limit)
    return {'logs': logs, 'count': len(logs)}


@router.get("/finance/budget-vs-actual")
async def budget_vs_actual(
    month: str | None = None,
    current_user: User = Depends(get_current_user),
):
    # Tur 3: default — current month YYYY-MM when omitted
    if not month:
        from datetime import date as _d
        month = _d.today().strftime('%Y-%m')
    # Simulated budget data
    budget = {'rooms': 150000, 'fnb': 50000, 'other': 20000, 'total': 220000}
    actual = {'rooms': 165000, 'fnb': 48000, 'other': 22000, 'total': 235000}
    variance = {k: actual[k] - budget[k] for k in budget}
    variance_pct = {k: round((variance[k] / budget[k] * 100), 1) if budget[k] > 0 else 0 for k in budget}
    return {
        'month': month, 'budget': budget, 'actual': actual,
        'variance': variance, 'variance_pct': variance_pct
    }



