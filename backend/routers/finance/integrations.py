"""Auto-split from finance.py — section: integrations."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
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

from domains.channel_manager.credential_vault import get_decrypted_credentials
from routers.finance.erp_connectors.base import ERPConnectionError, ERPSyncRejected, ERPSyncTimeout
from routers.finance.erp_connectors.logo import LogoHttpConnector
from routers.finance.erp_connectors.netsis import NetsisHttpConnector

ERP_CREDENTIAL_PROPERTY_ID = "finance"





async def _gather_invoices(tenant_id: str, since=None):
    query = {"tenant_id": tenant_id}
    if since:
        query["created_at"] = {"$gte": since}
    return await db.finance_invoices.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)


async def _gather_payments(tenant_id: str, since=None):
    query = {"tenant_id": tenant_id}
    if since:
        query["created_at"] = {"$gte": since}
    return await db.finance_payments.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)


async def _log_accounting_sync(tenant_id: str, payload: dict):
    record = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        **payload,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.accounting_sync_logs.insert_one(record)
    return record


@router.post("/finance/logo-integration/sync")
async def sync_with_logo(
    sync_data: dict = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v94 DW
):
    """Sync finance data with Logo ERP."""
    tenant_id = current_user.tenant_id

    # 1. Fetch data
    invoices = await _gather_invoices(tenant_id)
    payments = await _gather_payments(tenant_id)

    if len(invoices) == 0 and len(payments) == 0:
        log_entry = await _log_accounting_sync(
            tenant_id,
            {
                "provider": "logo",
                "synced_invoices": 0,
                "synced_payments": 0,
                "synced_at": datetime.now(UTC).isoformat(),
                "status": "noop",
                "details": "No invoices or payments to sync.",
            },
        )
        return {
            "success": True,
            "status": "noop",
            "synced_invoices": 0,
            "synced_payments": 0,
            "log_id": log_entry["id"],
            "message": "No data to sync.",
        }

    # 2. Build ERP payloads (Logo Schema)
    logo_payloads = []
    for inv in invoices:
        logo_payloads.append(
            {
                "FicheNo": inv.get("invoice_number", ""),
                "Date": inv.get("issue_date", ""),
                "ARPA_Code": inv.get("guest_id", ""),  # AR/AP code mapping
                "Total": inv.get("total_amount", 0.0),
                "Lines": [
                    {"ItemCode": line.get("item_id", "GENERIC"), "Quantity": line.get("quantity", 1), "Price": line.get("unit_price", 0.0), "VatRate": line.get("tax_rate", 0)}
                    for line in inv.get("items", [])
                ],
            }
        )

    logo_payment_payloads = []
    for p in payments:
        logo_payment_payloads.append(
            {
                "ReceiptNo": p.get("receipt_number", p.get("id", "")),
                "Date": p.get("created_at", ""),
                "ARPA_Code": p.get("guest_id", ""),
                "Amount": p.get("amount", 0.0),
                "PaymentMethod": p.get("method", "CASH"),
            }
        )

    credentials = await get_decrypted_credentials(tenant_id, "logo", ERP_CREDENTIAL_PROPERTY_ID)
    if not credentials:
        raise HTTPException(status_code=409, detail="No credentials configured for Logo ERP")

    api_url = credentials.get("api_url")
    if not api_url:
        raise HTTPException(status_code=409, detail="API URL missing in credentials")

    sync_id = str(uuid.uuid4())
    connector = LogoHttpConnector()

    try:
        synced_invoices_count = 0
        synced_payments_count = 0
        response_statuses = {}

        if logo_payloads:
            res_inv = await connector.send_payload(api_url, "invoices", logo_payloads, credentials, sync_id)
            synced_invoices_count = len(invoices)
            response_statuses["invoices"] = res_inv.get("status_code")

        if logo_payment_payloads:
            res_pay = await connector.send_payload(api_url, "payments", logo_payment_payloads, credentials, sync_id)
            synced_payments_count = len(payments)
            response_statuses["payments"] = res_pay.get("status_code")

        log_entry = await _log_accounting_sync(
            tenant_id,
            {
                "provider": "logo",
                "synced_invoices": synced_invoices_count,
                "synced_payments": synced_payments_count,
                "synced_at": datetime.now(UTC).isoformat(),
                "status": "success",
                "provider_response_status": response_statuses,
                "details": "Payloads synced to Logo ERP successfully",
            },
        )

        return {
            "success": True,
            "data_available": True,
            "synced_invoices": synced_invoices_count,
            "synced_payments": synced_payments_count,
            "log_id": log_entry["id"],
            "message": "Logo ERP senkronizasyonu tamamlandi.",
        }
    except ERPConnectionError as e:
        await _log_accounting_sync(tenant_id, {
            "provider": "logo",
            "status": "failed",
            "error_type": "connection_error",
            "synced_at": datetime.now(UTC).isoformat(),
        })
        raise HTTPException(status_code=502, detail=str(e))
    except ERPSyncTimeout as e:
        await _log_accounting_sync(tenant_id, {
            "provider": "logo",
            "status": "failed",
            "error_type": "timeout",
            "synced_at": datetime.now(UTC).isoformat(),
        })
        raise HTTPException(status_code=504, detail=str(e))
    except ERPSyncRejected as e:
        await _log_accounting_sync(tenant_id, {
            "provider": "logo",
            "status": "failed",
            "error_type": "provider_rejected",
            "provider_response_status": e.status_code,
            "synced_at": datetime.now(UTC).isoformat(),
        })
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/finance/netsis-integration/sync")
async def sync_with_netsis(
    sync_data: dict = None,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v94 DW
):
    """Sync finance data with Netsis ERP."""
    tenant_id = current_user.tenant_id

    invoices = await _gather_invoices(tenant_id)
    payments = await _gather_payments(tenant_id)

    if len(invoices) == 0 and len(payments) == 0:
        log_entry = await _log_accounting_sync(
            tenant_id,
            {
                "provider": "netsis",
                "synced_invoices": 0,
                "synced_payments": 0,
                "synced_at": datetime.now(UTC).isoformat(),
                "status": "noop",
                "details": "No invoices or payments to sync.",
            },
        )
        return {
            "success": True,
            "status": "noop",
            "synced_invoices": 0,
            "synced_payments": 0,
            "log_id": log_entry["id"],
            "message": "No data to sync.",
        }

    # 2. Build ERP payloads (Netsis Schema)
    netsis_payloads = []
    for inv in invoices:
        netsis_payloads.append(
            {
                "FATIRS_NO": inv.get("invoice_number", ""),
                "TARIH": inv.get("issue_date", ""),
                "CARI_KODU": inv.get("guest_id", ""),
                "GENELTOPLAM": inv.get("total_amount", 0.0),
                "Kalemler": [
                    {"STOK_KODU": line.get("item_id", "GENERIC"), "MIKTAR": line.get("quantity", 1), "FIYAT": line.get("unit_price", 0.0), "KDV_ORANI": line.get("tax_rate", 0)}
                    for line in inv.get("items", [])
                ],
            }
        )

    netsis_payment_payloads = []
    for p in payments:
        netsis_payment_payloads.append(
            {
                "MAKBUZ_NO": p.get("receipt_number", p.get("id", "")),
                "TARIH": p.get("created_at", ""),
                "CARI_KODU": p.get("guest_id", ""),
                "TUTAR": p.get("amount", 0.0),
                "TIP": p.get("method", "CASH"),
            }
        )

    credentials = await get_decrypted_credentials(tenant_id, "netsis", ERP_CREDENTIAL_PROPERTY_ID)
    if not credentials:
        raise HTTPException(status_code=409, detail="No credentials configured for Netsis ERP")

    api_url = credentials.get("api_url")
    if not api_url:
        raise HTTPException(status_code=409, detail="API URL missing in credentials")

    sync_id = str(uuid.uuid4())
    connector = NetsisHttpConnector()

    try:
        synced_invoices_count = 0
        synced_payments_count = 0
        response_statuses = {}

        if netsis_payloads:
            res_inv = await connector.send_payload(api_url, "invoices", netsis_payloads, credentials, sync_id)
            synced_invoices_count = len(invoices)
            response_statuses["invoices"] = res_inv.get("status_code")

        if netsis_payment_payloads:
            res_pay = await connector.send_payload(api_url, "payments", netsis_payment_payloads, credentials, sync_id)
            synced_payments_count = len(payments)
            response_statuses["payments"] = res_pay.get("status_code")

        log_entry = await _log_accounting_sync(
            tenant_id,
            {
                "provider": "netsis",
                "synced_invoices": synced_invoices_count,
                "synced_payments": synced_payments_count,
                "synced_at": datetime.now(UTC).isoformat(),
                "status": "success",
                "provider_response_status": response_statuses,
                "details": "Payloads synced to Netsis ERP successfully",
            },
        )

        return {
            "success": True,
            "data_available": True,
            "synced_invoices": synced_invoices_count,
            "synced_payments": synced_payments_count,
            "log_id": log_entry["id"],
            "message": "Netsis ERP senkronizasyonu tamamlandi.",
        }
    except ERPConnectionError as e:
        await _log_accounting_sync(tenant_id, {
            "provider": "netsis",
            "status": "failed",
            "error_type": "connection_error",
            "synced_at": datetime.now(UTC).isoformat(),
        })
        raise HTTPException(status_code=502, detail=str(e))
    except ERPSyncTimeout as e:
        await _log_accounting_sync(tenant_id, {
            "provider": "netsis",
            "status": "failed",
            "error_type": "timeout",
            "synced_at": datetime.now(UTC).isoformat(),
        })
        raise HTTPException(status_code=504, detail=str(e))
    except ERPSyncRejected as e:
        await _log_accounting_sync(tenant_id, {
            "provider": "netsis",
            "status": "failed",
            "error_type": "provider_rejected",
            "provider_response_status": e.status_code,
            "synced_at": datetime.now(UTC).isoformat(),
        })
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/finance/integration/logs")
async def get_integration_logs(limit: int = 20, current_user: User = Depends(get_current_user)):
    logs = await db.accounting_sync_logs.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"logs": logs, "count": len(logs)}


@router.get("/finance/budget-vs-actual")
async def budget_vs_actual(
    month: str | None = None,
    current_user: User = Depends(get_current_user),
):
    # Tur 3: default — current month YYYY-MM when omitted
    if not month:
        from datetime import date as _d

        month = _d.today().strftime("%Y-%m")
    # Kategori bazli (rooms/fnb/other) gercek butce kaynagi yok (db.budgets yalnizca
    # revenue/expense toplami tutar). Uydurma sabit butce/gerceklesen uretmek yerine
    # fail-closed don; FE anahtarlari (budget/actual/variance/variance_pct) korunur.
    zero = {"rooms": 0, "fnb": 0, "other": 0, "total": 0}
    return {
        "month": month,
        "budget": dict(zero),
        "actual": dict(zero),
        "variance": dict(zero),
        "variance_pct": dict(zero),
        "data_available": False,
        "message": "Kategori bazli butce verisi tanimlanmamis.",
    }
