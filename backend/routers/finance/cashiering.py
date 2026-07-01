"""Auto-split from finance.py — section: cashiering."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: F401
    from openpyxl.utils import get_column_letter  # noqa: F401
except ImportError:
    Workbook = None

from core.database import db
from core.security import get_current_user
from domains.pms.night_audit_module import CityLedgerAccount
from modules.pms_core.role_permission_service import RolePermissionService

_role_perm = RolePermissionService()


def _enforce(role: str, op: str):
    """Bug CT (v59) — Cashiering/AR endpoint'leri için RBAC zorunlu."""
    _role_perm.enforce_permission(role, op)


from models.schemas import (
    CityLedgerTransaction,
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


@router.post("/cashiering/city-ledger")
async def create_city_ledger_account(account_data: dict, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Create a new city ledger account for direct billing"""
    current_user = await get_current_user(credentials)
    _enforce(current_user.role, "manage_city_ledger")  # Bug CT

    account = CityLedgerAccount(
        tenant_id=current_user.tenant_id,
        account_name=account_data["account_name"],
        company_name=account_data["company_name"],
        contact_person=account_data.get("contact_person"),
        email=account_data.get("email"),
        phone=account_data.get("phone"),
        address=account_data.get("address"),
        credit_limit=account_data.get("credit_limit", 0.0),
        payment_terms=account_data.get("payment_terms", 30),
    )

    await db.city_ledger_accounts.insert_one(account.model_dump())

    return {"success": True, "account_id": account.id, "account_name": account.account_name, "credit_limit": account.credit_limit}


@router.get("/cashiering/city-ledger")
async def get_city_ledger_accounts(is_active: bool = True, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get all city ledger accounts"""
    current_user = await get_current_user(credentials)
    _enforce(current_user.role, "view_city_ledger")  # Bug CT

    query = {"tenant_id": current_user.tenant_id}
    if is_active is not None:
        query["is_active"] = is_active

    accounts = await db.city_ledger_accounts.find(query, {"_id": 0}).to_list(1000)

    return {"accounts": accounts, "total_count": len(accounts)}


@router.post("/cashiering/split-payment")
async def process_split_payment(booking_id: str, payments: list[dict], credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Process split payment (multiple payment methods for one bill)"""
    current_user = await get_current_user(credentials)
    _enforce(current_user.role, "post_payment")  # Bug CT

    # Get booking
    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": current_user.tenant_id})

    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Validate total matches booking amount
    total_payment = sum(p["amount"] for p in payments)

    if abs(total_payment - booking.get("total_amount", 0)) > 0.01:
        raise HTTPException(status_code=400, detail=f"Payment total ({total_payment}) doesn't match booking amount ({booking.get('total_amount', 0)})")

    # Process each payment
    payment_records = []
    for payment in payments:
        payment_record = {
            "id": str(uuid.uuid4()),
            "tenant_id": current_user.tenant_id,
            "booking_id": booking_id,
            "payment_method": payment["payment_method"],
            "amount": payment["amount"],
            "reference": payment.get("reference"),
            "processed_at": datetime.now(UTC).isoformat(),
            "processed_by": current_user.name,
        }
        await db.payments.insert_one(payment_record)
        payment_records.append(payment_record)

    # Update booking status (tenant-pinned defense-in-depth, v107 P0)
    await db.bookings.update_one({"id": booking_id, "tenant_id": current_user.tenant_id}, {"$set": {"payment_status": "paid", "paid_at": datetime.now(UTC).isoformat()}})

    return {"success": True, "booking_id": booking_id, "payments_processed": len(payment_records), "total_amount": total_payment, "payment_methods": [p["payment_method"] for p in payments]}


@router.get("/cashiering/ar-aging-report")
async def get_ar_aging_report(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get Accounts Receivable aging report (30/60/90 days)"""
    current_user = await get_current_user(credentials)
    _enforce(current_user.role, "view_ar_aging")  # Bug CT

    today = datetime.now(UTC)

    aging_buckets = {"current": [], "30_days": [], "60_days": [], "90_plus": []}

    # Get all city ledger accounts with balance
    accounts = await db.city_ledger_accounts.find({"tenant_id": current_user.tenant_id, "current_balance": {"$gt": 0}}, {"_id": 0}).to_list(1000)

    for account in accounts:
        # Get oldest transaction
        oldest_transaction = await db.city_ledger_transactions.find_one({"account_id": account["id"], "transaction_type": "charge"}, {"_id": 0}, sort=[("transaction_date", 1)])

        if oldest_transaction:
            # Parse transaction_date safely
            transaction_date = oldest_transaction["transaction_date"]
            if isinstance(transaction_date, str):
                transaction_date = datetime.fromisoformat(transaction_date.replace("Z", "+00:00"))
            elif not isinstance(transaction_date, datetime):
                continue  # Skip invalid data

            # Ensure timezone-aware
            if transaction_date.tzinfo is None:
                transaction_date = transaction_date.replace(tzinfo=UTC)

            days_old = (today - transaction_date).days

            aging_entry = {"account_id": account["id"], "account_name": account["account_name"], "balance": account["current_balance"], "days_old": days_old}

            if days_old <= 30:
                aging_buckets["current"].append(aging_entry)
            elif days_old <= 60:
                aging_buckets["30_days"].append(aging_entry)
            elif days_old <= 90:
                aging_buckets["60_days"].append(aging_entry)
            else:
                aging_buckets["90_plus"].append(aging_entry)

    # Calculate totals
    totals = {
        "current": sum(a["balance"] for a in aging_buckets["current"]),
        "30_days": sum(a["balance"] for a in aging_buckets["30_days"]),
        "60_days": sum(a["balance"] for a in aging_buckets["60_days"]),
        "90_plus": sum(a["balance"] for a in aging_buckets["90_plus"]),
    }

    totals["total"] = sum(totals.values())

    return {"aging_buckets": aging_buckets, "totals": totals, "generated_at": today.isoformat()}


@router.post("/cashiering/credit-limit")
async def set_credit_limit(account_id: str, credit_limit: float, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Set credit limit for city ledger account"""
    current_user = await get_current_user(credentials)
    _enforce(current_user.role, "manage_credit_limit")  # Bug CT

    result = await db.city_ledger_accounts.update_one({"id": account_id, "tenant_id": current_user.tenant_id}, {"$set": {"credit_limit": credit_limit}})

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Account not found")

    return {"success": True, "account_id": account_id, "credit_limit": credit_limit}


@router.get("/cashiering/credit-limit/{account_id}")
async def get_credit_limit(account_id: str, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get credit limit and current balance for account"""
    current_user = await get_current_user(credentials)
    _enforce(current_user.role, "view_credit_limit")  # Bug CT

    account = await db.city_ledger_accounts.find_one({"id": account_id, "tenant_id": current_user.tenant_id}, {"_id": 0})

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    available_credit = account["credit_limit"] - account["current_balance"]

    return {
        "account_id": account_id,
        "account_name": account["account_name"],
        "credit_limit": account["credit_limit"],
        "current_balance": account["current_balance"],
        "available_credit": available_credit,
        "credit_status": "ok" if available_credit > 0 else "exceeded",
    }


@router.post("/cashiering/direct-bill")
async def post_to_city_ledger(booking_id: str, account_id: str, amount: float, description: str, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Post charge to city ledger (direct billing)"""
    current_user = await get_current_user(credentials)
    _enforce(current_user.role, "post_direct_bill")  # Bug CT

    # Verify account
    account = await db.city_ledger_accounts.find_one({"id": account_id, "tenant_id": current_user.tenant_id})

    if not account:
        raise HTTPException(status_code=404, detail="City ledger account not found")

    # Check credit limit
    if account["current_balance"] + amount > account["credit_limit"]:
        raise HTTPException(status_code=400, detail=f"Credit limit exceeded. Available: {account['credit_limit'] - account['current_balance']}")

    # Create transaction
    transaction = CityLedgerTransaction(
        tenant_id=current_user.tenant_id, account_id=account_id, booking_id=booking_id, transaction_type="charge", amount=amount, description=description, posted_by=current_user.name
    )

    await db.city_ledger_transactions.insert_one(transaction.model_dump())

    # Update account balance
    await db.city_ledger_accounts.update_one({"id": account_id}, {"$inc": {"current_balance": amount}})

    return {"success": True, "transaction_id": transaction.id, "account_name": account["account_name"], "amount_posted": amount, "new_balance": account["current_balance"] + amount}


@router.get("/cashiering/outstanding-balance")
async def get_outstanding_balances(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get all city ledger accounts with outstanding balances"""
    current_user = await get_current_user(credentials)
    _enforce(current_user.role, "view_outstanding_balance")  # Bug CT

    accounts = await db.city_ledger_accounts.find({"tenant_id": current_user.tenant_id, "current_balance": {"$gt": 0}}, {"_id": 0}).sort("current_balance", -1).to_list(1000)

    total_outstanding = sum(a["current_balance"] for a in accounts)

    return {"accounts": accounts, "total_accounts": len(accounts), "total_outstanding": round(total_outstanding, 2)}


@router.post("/cashiering/city-ledger-payment")
async def post_city_ledger_payment(account_id: str, amount: float, payment_method: str, reference: str | None = None, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Post payment to city ledger account"""
    current_user = await get_current_user(credentials)
    _enforce(current_user.role, "post_city_ledger_payment")  # Bug CT

    account = await db.city_ledger_accounts.find_one({"id": account_id, "tenant_id": current_user.tenant_id})

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    transaction = CityLedgerTransaction(
        tenant_id=current_user.tenant_id,
        account_id=account_id,
        transaction_type="payment",
        amount=amount,
        description=f"Payment received via {payment_method}",
        reference_number=reference,
        posted_by=current_user.name,
    )

    await db.city_ledger_transactions.insert_one(transaction.model_dump())

    new_balance = account["current_balance"] - amount
    await db.city_ledger_accounts.update_one({"id": account_id}, {"$set": {"current_balance": max(0, new_balance)}})

    return {"success": True, "transaction_id": transaction.id, "account_name": account["account_name"], "amount_paid": amount, "new_balance": max(0, new_balance)}


@router.get("/cashiering/city-ledger/{account_id}/transactions")
async def get_city_ledger_transactions(account_id: str, limit: int = 100, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get transaction history for city ledger account"""
    current_user = await get_current_user(credentials)
    _enforce(current_user.role, "view_city_ledger_transactions")  # Bug CT

    transactions = await db.city_ledger_transactions.find({"account_id": account_id, "tenant_id": current_user.tenant_id}, {"_id": 0}).sort("transaction_date", -1).limit(limit).to_list(limit)

    charges = sum(t["amount"] for t in transactions if t["transaction_type"] == "charge")
    payments = sum(t["amount"] for t in transactions if t["transaction_type"] == "payment")

    return {
        "account_id": account_id,
        "transactions": transactions,
        "summary": {"total_charges": round(charges, 2), "total_payments": round(payments, 2), "current_balance": round(charges - payments, 2), "transaction_count": len(transactions)},
    }
