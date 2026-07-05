import random
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# Import mock_db from general_ledger to create journal entries directly
from .general_ledger import mock_db as gl_db

router = APIRouter(prefix="/banking", tags=["Açık Bankacılık"])

class BankTransaction(BaseModel):
    id: str
    date: str
    amount: float
    description: str
    sender_iban: str
    sender_name: str
    status: str # 'unmatched', 'matched'
    matched_with: str | None = None

class ReconcileRequest(BaseModel):
    transaction_id: str
    invoice_id: str
    invoice_number: str
    amount_paid: float
    client_name: str

# Mock Database for Bank Transactions
mock_banking_db = {
    "transactions": [
        {
            "id": str(uuid.uuid4()),
            "date": datetime.utcnow().strftime("%Y-%m-%d"),
            "amount": 15000.00,
            "description": "INV-2026-001 Nolu Fatura Odemesi",
            "sender_iban": "TR120006200000012345678901",
            "sender_name": "Booking.com B.V.",
            "status": "unmatched",
            "matched_with": None
        },
        {
            "id": str(uuid.uuid4()),
            "date": (datetime.utcnow() - timedelta(days=1)).strftime("%Y-%m-%d"),
            "amount": 2450.50,
            "description": "EFT - AHMET YILMAZ KONAKLAMA BEDELI",
            "sender_iban": "TR990004600000098765432109",
            "sender_name": "AHMET YILMAZ",
            "status": "unmatched",
            "matched_with": None
        }
    ]
}

@router.get("/transactions")
async def get_transactions():
    """Get all bank transactions."""
    return sorted(mock_banking_db["transactions"], key=lambda x: x["date"], reverse=True)

@router.post("/sync")
async def sync_bank_transactions():
    """Simulate fetching new transactions from bank API."""
    companies = ["Expedia Inc.", "Agoda LLC", "Mehmet Demir", "Jolly Tur"]
    desc = ["EFT Konaklama", "Havale Fatura Odemesi", "Acente Hakedis"]

    new_txn = {
        "id": str(uuid.uuid4()),
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "amount": round(random.uniform(1000.0, 50000.0), 2),
        "description": f"{random.choice(desc)} - {random.randint(1000, 9999)}",
        "sender_iban": f"TR{random.randint(10, 99)}000{random.randint(1000, 9999)}000000{random.randint(1000, 9999)}",
        "sender_name": random.choice(companies),
        "status": "unmatched",
        "matched_with": None
    }
    mock_banking_db["transactions"].append(new_txn)
    return {"status": "success", "transaction": new_txn}

@router.post("/reconcile")
async def reconcile_transaction(req: ReconcileRequest):
    """Reconcile a bank transaction with an invoice/folio."""
    txn = next((t for t in mock_banking_db["transactions"] if t["id"] == req.transaction_id), None)
    if not txn:
        raise HTTPException(status_code=404, detail="Banka işlemi bulunamadı.")

    if txn["status"] == "matched":
        raise HTTPException(status_code=400, detail="Bu işlem zaten eşleştirilmiş.")

    # Mark as matched
    txn["status"] = "matched"
    txn["matched_with"] = req.invoice_number

    # Create General Ledger Journal Entry (102 Bankalar -> Borç, 120 Alıcılar -> Alacak)
    journal_entry = {
        "id": str(uuid.uuid4()),
        "date": datetime.utcnow().strftime("%Y-%m-%d"),
        "type": "Tahsilat",
        "description": f"Banka Mutabakatı: {txn['sender_name']} - {req.invoice_number} Tahsilatı",
        "total": txn["amount"],
        "timestamp": datetime.utcnow().isoformat(),
        "lines": [
            {
                "account_code": "102",
                "debit": txn["amount"],
                "credit": 0.0,
                "description": f"Gelen Havale: {txn['description']}"
            },
            {
                "account_code": "120",
                "debit": 0.0,
                "credit": txn["amount"],
                "description": f"{req.client_name} - {req.invoice_number} Kapanış"
            }
        ]
    }

    # Add to general_ledger db
    gl_db["journals"].append(journal_entry)

    return {"status": "success", "message": "Mutabakat sağlandı ve Yevmiye Fişi kesildi."}
