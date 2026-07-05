from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import uuid
from datetime import datetime

router = APIRouter(prefix="/gl", tags=["Genel Muhasebe"])

# --- Models ---
class GLAccountCreate(BaseModel):
    code: str
    name: str
    type: str # 'Asset', 'Liability', 'Equity', 'Revenue', 'Expense'

class JournalLine(BaseModel):
    account_code: str
    debit: float = 0.0
    credit: float = 0.0
    description: Optional[str] = None

class JournalEntryCreate(BaseModel):
    date: str
    type: str # 'Mahsup', 'Tahsilat', 'Tediye'
    description: str
    lines: List[JournalLine]

# --- Mock Database ---
# Seed standard TDHP accounts
mock_db = {
    "accounts": [
        {"code": "100", "name": "Kasa", "type": "Asset", "balance": 0.0},
        {"code": "102", "name": "Bankalar", "type": "Asset", "balance": 0.0},
        {"code": "108", "name": "Diğer Hazır Değerler (Kredi Kartı)", "type": "Asset", "balance": 0.0},
        {"code": "120", "name": "Alıcılar", "type": "Asset", "balance": 0.0},
        {"code": "153", "name": "Ticari Mallar", "type": "Asset", "balance": 0.0},
        {"code": "320", "name": "Satıcılar", "type": "Liability", "balance": 0.0},
        {"code": "336", "name": "Diğer Çeşitli Borçlar", "type": "Liability", "balance": 0.0},
        {"code": "391", "name": "Hesaplanan KDV", "type": "Liability", "balance": 0.0},
        {"code": "600", "name": "Yurtiçi Satışlar (Oda/F&B Geliri)", "type": "Revenue", "balance": 0.0},
        {"code": "740", "name": "Hizmet Üretim Maliyeti", "type": "Expense", "balance": 0.0},
        {"code": "770", "name": "Genel Yönetim Giderleri", "type": "Expense", "balance": 0.0},
    ],
    "journals": []
}

# --- Endpoints ---

@router.get("/accounts")
async def get_accounts():
    """List all TDHP Accounts with current calculated balances."""
    # Recalculate balances based on journals
    balances = {acc["code"]: 0.0 for acc in mock_db["accounts"]}
    for journal in mock_db["journals"]:
        for line in journal["lines"]:
            if line["account_code"] in balances:
                balances[line["account_code"]] += (line["debit"] - line["credit"])
                
    # Update mock_db balances
    for acc in mock_db["accounts"]:
        # Asset/Expense positive balance means debit > credit
        # Liability/Equity/Revenue positive balance means credit > debit
        # We will just return raw Balance (Debit - Credit) for Trial Balance
        acc["balance"] = balances.get(acc["code"], 0.0)
        
    return mock_db["accounts"]

@router.post("/accounts")
async def create_account(acc: GLAccountCreate):
    """Create a new TDHP Account (e.g. 120.01)"""
    for existing in mock_db["accounts"]:
        if existing["code"] == acc.code:
            raise HTTPException(status_code=400, detail="Bu hesap kodu zaten mevcut.")
            
    new_acc = acc.model_dump()
    new_acc["balance"] = 0.0
    mock_db["accounts"].append(new_acc)
    mock_db["accounts"].sort(key=lambda x: x["code"])
    return {"status": "success", "account": new_acc}

@router.get("/journals")
async def get_journals():
    """List all Journal Entries"""
    return sorted(mock_db["journals"], key=lambda x: x["date"], reverse=True)

@router.post("/journals")
async def create_journal(entry: JournalEntryCreate):
    """Create a Journal Entry (Yevmiye Fişi)"""
    total_debit = sum(line.debit for line in entry.lines)
    total_credit = sum(line.credit for line in entry.lines)
    
    # Check Double-Entry Accounting Rule
    if abs(total_debit - total_credit) > 0.01:
        raise HTTPException(
            status_code=400, 
            detail=f"Borç ({total_debit}) ve Alacak ({total_credit}) toplamları eşit olmak zorundadır!"
        )
        
    new_entry = entry.model_dump()
    new_entry["id"] = str(uuid.uuid4())
    new_entry["total"] = total_debit
    new_entry["timestamp"] = datetime.utcnow().isoformat()
    
    mock_db["journals"].append(new_entry)
    return {"status": "success", "journal_id": new_entry["id"]}

@router.get("/trial-balance")
async def get_trial_balance():
    """Trial Balance (Mizan)"""
    tb = {}
    for acc in mock_db["accounts"]:
        tb[acc["code"]] = {
            "code": acc["code"],
            "name": acc["name"],
            "total_debit": 0.0,
            "total_credit": 0.0,
            "balance": 0.0,
            "balance_type": "-"
        }
        
    for journal in mock_db["journals"]:
        for line in journal["lines"]:
            code = line["account_code"]
            if code in tb:
                tb[code]["total_debit"] += line["debit"]
                tb[code]["total_credit"] += line["credit"]
                
    # Calculate balances
    result = []
    for code, data in tb.items():
        if data["total_debit"] > 0 or data["total_credit"] > 0:
            diff = data["total_debit"] - data["total_credit"]
            data["balance"] = abs(diff)
            data["balance_type"] = "Borç" if diff > 0 else "Alacak" if diff < 0 else "-"
            result.append(data)
            
    # Add totals row
    total_debit = sum(x["total_debit"] for x in result)
    total_credit = sum(x["total_credit"] for x in result)
    
    return {
        "lines": sorted(result, key=lambda x: x["code"]),
        "totals": {
            "total_debit": total_debit,
            "total_credit": total_credit
        }
    }
