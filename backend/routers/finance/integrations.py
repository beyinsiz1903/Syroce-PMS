"""Auto-split from finance.py — section: integrations."""
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
        # Gercek Logo ERP HTTP entegrasyonu uygulanmadi; sahte 'synced' donmek
        # yerine cagrildiginda hata ver (gelecekte yanlislikla fabrikasyon
        # basari uretilmesini engeller).
        raise NotImplementedError("Logo ERP send_invoice not implemented")

    async def send_payment(self, payment):
        raise NotImplementedError("Logo ERP send_payment not implemented")


class NetsisConnector:
    """Netsis connector (entegrasyon henuz uygulanmadi)."""
    def __init__(self):
        import os
        self.base_url = os.environ.get('NETSIS_API_URL', 'https://netsis.example/api')

    async def send_invoice(self, invoice):
        raise NotImplementedError("Netsis ERP send_invoice not implemented")


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
    """Sync finance data with Logo ERP."""
    # Gercek Logo ERP HTTP entegrasyonu uygulanmadi (connector sahte "synced"
    # donuyordu). Sahte basari raporlamak yerine fail-closed don; veri aktarilmaz.
    log_entry = await _log_accounting_sync(current_user.tenant_id, {
        'provider': 'logo',
        'synced_invoices': 0,
        'synced_payments': 0,
        'synced_at': datetime.now(UTC).isoformat(),
        'status': 'not_implemented'
    })

    return {
        'success': False,
        'data_available': False,
        'synced_invoices': 0,
        'synced_payments': 0,
        'log_id': log_entry['id'],
        'message': 'Logo ERP entegrasyonu henuz uygulanmadi; veri aktarilmadi.'
    }



@router.post("/finance/netsis-integration/sync")
async def sync_with_netsis(sync_data: dict = None, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v94 DW
):
    # Gercek Netsis ERP HTTP entegrasyonu uygulanmadi (connector sahte "synced"
    # donuyordu). Sahte basari raporlamak yerine fail-closed don; veri aktarilmaz.
    log_entry = await _log_accounting_sync(current_user.tenant_id, {
        'provider': 'netsis',
        'synced_invoices': 0,
        'synced_payments': 0,
        'synced_at': datetime.now(UTC).isoformat(),
        'status': 'not_implemented'
    })

    return {
        'success': False,
        'data_available': False,
        'synced_invoices': 0,
        'log_id': log_entry['id'],
        'message': 'Netsis ERP entegrasyonu henuz uygulanmadi; veri aktarilmadi.'
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
    # Kategori bazli (rooms/fnb/other) gercek butce kaynagi yok (db.budgets yalnizca
    # revenue/expense toplami tutar). Uydurma sabit butce/gerceklesen uretmek yerine
    # fail-closed don; FE anahtarlari (budget/actual/variance/variance_pct) korunur.
    zero = {'rooms': 0, 'fnb': 0, 'other': 0, 'total': 0}
    return {
        'month': month,
        'budget': dict(zero),
        'actual': dict(zero),
        'variance': dict(zero),
        'variance_pct': dict(zero),
        'data_available': False,
        'message': 'Kategori bazli butce verisi tanimlanmamis.',
    }



