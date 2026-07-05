import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

# In a real app we'd use core dependencies (auth, tenant_id).
# We'll use mock dependencies or ignore them for this sandbox.
# Assuming a basic router structure.
router = APIRouter(prefix="/einvoice", tags=["e-Fatura Entegrasyonu"])

# Mock database for settings and invoice statuses
mock_db = {
    "settings": {},
    "invoices": {}
}

class EInvoiceSettings(BaseModel):
    integrator: str
    username: str
    password: str
    environment: str # 'test' or 'live'
    alias: str | None = None

class EInvoiceSendRequest(BaseModel):
    invoice_id: str

@router.post("/settings")
async def save_settings(settings: EInvoiceSettings):
    """
    Saves the API credentials for the e-Invoice integrator.
    """
    mock_db["settings"] = settings.model_dump()
    return {"status": "success", "message": "e-Fatura ayarları başarıyla kaydedildi."}

@router.get("/settings")
async def get_settings():
    """
    Retrieves the saved API credentials.
    """
    return mock_db.get("settings", {})

async def mock_send_to_gib(invoice_id: str):
    """
    Simulates sending an invoice to GİB via a private integrator.
    """
    await asyncio.sleep(2) # Simulate network delay
    mock_db["invoices"][invoice_id] = {
        "status": "APPROVED",
        "ettn": str(uuid.uuid4()),
        "envelope_id": f"GIB2026{str(uuid.uuid4().int)[:9]}",
        "timestamp": datetime.utcnow().isoformat(),
        "message": "Fatura başarıyla resmileştirildi."
    }

@router.post("/send/{invoice_id}")
async def send_einvoice(invoice_id: str, background_tasks: BackgroundTasks):
    """
    Initiates sending an invoice to the e-Invoice integrator.
    """
    settings = mock_db.get("settings")
    if not settings:
        raise HTTPException(status_code=400, detail="Lütfen önce e-Fatura Ayarlarını yapılandırın.")

    # Mark as queued
    mock_db["invoices"][invoice_id] = {
        "status": "QUEUED",
        "message": "Kuyruğa eklendi, entegratöre iletiliyor..."
    }

    # Process in background (simulation)
    background_tasks.add_task(mock_send_to_gib, invoice_id)

    return {
        "status": "success",
        "message": "Fatura kuyruğa alındı.",
        "invoice_id": invoice_id
    }

@router.get("/status/{invoice_id}")
async def get_einvoice_status(invoice_id: str):
    """
    Returns the status of an e-invoice.
    """
    data = mock_db["invoices"].get(invoice_id)
    if not data:
        return {"status": "NOT_SENT", "message": "Fatura henüz resmileştirilmedi."}

    return data
