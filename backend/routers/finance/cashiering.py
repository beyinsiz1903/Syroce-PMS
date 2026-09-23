"""Auto-split from finance.py — section: cashiering."""

import math
import re
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: F401
    from openpyxl.utils import get_column_letter  # noqa: F401
except ImportError:
    Workbook = None

from core.business_date_service import stamp_open_business_date
from core.database import db
from core.security import get_current_user
from domains.pms.night_audit_module import CityLedgerAccount
from modules.pms_core.role_permission_service import RolePermissionService

_role_perm = RolePermissionService()


def _enforce(role: str, op: str):
    """Bug CT (v59) — Cashiering/AR endpoint'leri için RBAC zorunlu."""
    _role_perm.enforce_permission(getattr(role, "role", role), op, getattr(role, "granted_permissions", None))


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


class CityLedgerPaymentAllocation(BaseModel):
    """A payment amount explicitly settled against one reservation's AR item."""

    booking_id: str = Field(min_length=1, max_length=200)
    amount: float = Field(gt=0, le=1_000_000_000)


def _as_finite_money(value: object, *, default: float = 0.0) -> float:
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return default
    return amount if math.isfinite(amount) else default


def _city_ledger_booking_label(booking: dict | None, booking_id: str) -> dict:
    """Keep the city-ledger source item readable even for a deleted legacy booking."""
    booking = booking or {}
    room_number = booking.get("room_number") or booking.get("room_no") or "Atanmamış"
    guest_name = booking.get("guest_name") or booking.get("primary_guest_name") or "Misafir bilgisi yok"
    return {
        "booking_id": booking_id,
        "room_number": str(room_number),
        "guest_name": guest_name,
        "check_in": booking.get("check_in") or booking.get("check_in_date"),
        "check_out": booking.get("check_out") or booking.get("check_out_date"),
        "booking_status": booking.get("status"),
    }


async def _city_ledger_booking_items(tenant_id: str, account_id: str) -> tuple[list[dict], dict]:
    """Return room/reservation open items and clearly separate legacy unallocated money.

    A city-ledger charge created by ``transfer_to_cari`` or direct billing stores
    its ``booking_id``.  New payments may store a list of allocations.  Older
    generic payments intentionally remain visible as *unallocated* instead of
    being guessed against a room; guessing would silently settle the wrong room.
    """
    transactions = await db.city_ledger_transactions.find(
        {"tenant_id": tenant_id, "account_id": account_id},
        {"_id": 0},
    ).to_list(5000)

    items_by_booking: dict[str, dict] = {}
    allocated_payment_total = 0.0
    all_payment_total = 0.0
    adjustment_total = 0.0

    for transaction in transactions:
        if transaction.get("status") not in {None, "completed"}:
            continue
        transaction_type = transaction.get("transaction_type")
        amount = round(_as_finite_money(transaction.get("amount")), 2)
        if amount <= 0:
            continue

        if transaction_type == "charge" and transaction.get("booking_id"):
            booking_id = str(transaction["booking_id"])
            item = items_by_booking.setdefault(
                booking_id,
                {
                    "booking_id": booking_id,
                    "charged_amount": 0.0,
                    "allocated_payment_amount": 0.0,
                    "source_transactions": [],
                },
            )
            item["charged_amount"] += amount
            item["source_transactions"].append(
                {
                    "transaction_id": transaction.get("id"),
                    "date": transaction.get("transaction_date") or transaction.get("created_at"),
                    "description": transaction.get("description"),
                    "amount": amount,
                    "reference_number": transaction.get("reference_number"),
                }
            )
        elif transaction_type == "payment":
            all_payment_total += amount
            for allocation in transaction.get("allocations") or []:
                booking_id = str(allocation.get("booking_id") or "").strip()
                allocated_amount = round(_as_finite_money(allocation.get("amount")), 2)
                if not booking_id or allocated_amount <= 0:
                    continue
                item = items_by_booking.setdefault(
                    booking_id,
                    {
                        "booking_id": booking_id,
                        "charged_amount": 0.0,
                        "allocated_payment_amount": 0.0,
                        "source_transactions": [],
                    },
                )
                item["allocated_payment_amount"] += allocated_amount
                allocated_payment_total += allocated_amount
        elif transaction_type == "adjustment":
            adjustment_total += amount

    booking_ids = list(items_by_booking)
    bookings_by_id: dict[str, dict] = {}
    if booking_ids:
        bookings = await db.bookings.find(
            {"tenant_id": tenant_id, "id": {"$in": booking_ids}},
            {"_id": 0},
        ).to_list(len(booking_ids))
        bookings_by_id = {str(booking.get("id")): booking for booking in bookings if booking.get("id")}

    items: list[dict] = []
    for booking_id, item in items_by_booking.items():
        charged_amount = round(item["charged_amount"], 2)
        allocated_amount = round(item["allocated_payment_amount"], 2)
        open_amount = round(max(0.0, charged_amount - allocated_amount), 2)
        if charged_amount <= 0 and allocated_amount <= 0:
            continue
        items.append(
            {
                **_city_ledger_booking_label(bookings_by_id.get(booking_id), booking_id),
                "charged_amount": charged_amount,
                "allocated_payment_amount": allocated_amount,
                "open_amount": open_amount,
                "source_transactions": item["source_transactions"],
            }
        )

    items.sort(key=lambda item: (item.get("check_in") or "", item["booking_id"]), reverse=True)
    return items, {
        "room_open_total": round(sum(item["open_amount"] for item in items), 2),
        "allocated_payment_total": round(allocated_payment_total, 2),
        "unallocated_payment_total": round(max(0.0, all_payment_total - allocated_payment_total), 2),
        "adjustment_total": round(adjustment_total, 2),
    }


@router.post("/cashiering/city-ledger")
async def create_city_ledger_account(account_data: dict, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Create a new city ledger account for direct billing"""
    current_user = await get_current_user(credentials)
    _enforce(current_user, "manage_city_ledger")  # Bug CT

    account_name = str(account_data.get("account_name") or "").strip()
    company_name = str(account_data.get("company_name") or "").strip()
    if not account_name or not company_name:
        raise HTTPException(status_code=400, detail="Account name and company name are required")

    try:
        credit_limit = float(account_data.get("credit_limit", 0.0))
        payment_terms = int(account_data.get("payment_terms", 30))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid credit limit or payment terms") from exc
    if not math.isfinite(credit_limit) or credit_limit < 0:
        raise HTTPException(status_code=400, detail="Credit limit must be a finite non-negative amount")
    if payment_terms < 0 or payment_terms > 3650:
        raise HTTPException(status_code=400, detail="Payment terms must be between 0 and 3650 days")

    duplicate = await db.city_ledger_accounts.find_one(
        {
            "tenant_id": current_user.tenant_id,
            "account_name": {"$regex": f"^{re.escape(account_name)}$", "$options": "i"},
        },
        {"_id": 1},
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="City ledger account name already exists")

    account = CityLedgerAccount(
        tenant_id=current_user.tenant_id,
        account_name=account_name,
        company_name=company_name,
        contact_person=account_data.get("contact_person"),
        email=account_data.get("email"),
        phone=account_data.get("phone"),
        address=account_data.get("address"),
        credit_limit=credit_limit,
        payment_terms=payment_terms,
    )

    account_doc = account.model_dump()
    account_doc["_id"] = str(uuid.uuid5(uuid.NAMESPACE_URL, f"city-ledger:{current_user.tenant_id}:{account_name.casefold()}"))
    try:
        await db.city_ledger_accounts.insert_one(account_doc)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail="City ledger account name already exists") from exc

    return {"success": True, "account_id": account.id, "account_name": account.account_name, "credit_limit": account.credit_limit}


@router.get("/cashiering/city-ledger")
async def get_city_ledger_accounts(is_active: bool = True, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get all city ledger accounts"""
    current_user = await get_current_user(credentials)
    _enforce(current_user, "view_city_ledger")  # Bug CT

    query = {"tenant_id": current_user.tenant_id}
    if is_active is not None:
        query["is_active"] = is_active

    accounts = await db.city_ledger_accounts.find(query, {"_id": 0}).to_list(1000)

    return {"accounts": accounts, "total_count": len(accounts)}


@router.post("/cashiering/split-payment")
async def process_split_payment(booking_id: str, payments: list[dict], credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Process split payment (multiple payment methods for one bill)"""
    current_user = await get_current_user(credentials)
    _enforce(current_user, "post_payment")  # Bug CT

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
        await stamp_open_business_date(db, current_user.tenant_id, payment_record)
        await db.payments.insert_one(payment_record)
        payment_records.append(payment_record)

    # Update booking status (tenant-pinned defense-in-depth, v107 P0)
    await db.bookings.update_one({"id": booking_id, "tenant_id": current_user.tenant_id}, {"$set": {"payment_status": "paid", "paid_at": datetime.now(UTC).isoformat()}})

    return {"success": True, "booking_id": booking_id, "payments_processed": len(payment_records), "total_amount": total_payment, "payment_methods": [p["payment_method"] for p in payments]}


@router.get("/cashiering/ar-aging-report")
async def get_ar_aging_report(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get Accounts Receivable aging report (30/60/90 days)"""
    current_user = await get_current_user(credentials)
    _enforce(current_user, "view_ar_aging")  # Bug CT

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
    _enforce(current_user, "manage_credit_limit")  # Bug CT

    result = await db.city_ledger_accounts.update_one({"id": account_id, "tenant_id": current_user.tenant_id}, {"$set": {"credit_limit": credit_limit}})

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Account not found")

    return {"success": True, "account_id": account_id, "credit_limit": credit_limit}


@router.get("/cashiering/credit-limit/{account_id}")
async def get_credit_limit(account_id: str, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get credit limit and current balance for account"""
    current_user = await get_current_user(credentials)
    _enforce(current_user, "view_credit_limit")  # Bug CT

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
async def post_to_city_ledger(
    booking_id: str,
    account_id: str,
    amount: float,
    description: str,
    idempotency_key: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Post charge to city ledger (direct billing)"""
    current_user = await get_current_user(credentials)
    _enforce(current_user, "post_direct_bill")  # Bug CT

    if not math.isfinite(amount) or amount <= 0:
        raise HTTPException(status_code=400, detail="Direct bill amount must be a finite positive amount")

    description = str(description or "").strip()
    if not description or len(description) > 2000:
        raise HTTPException(status_code=400, detail="Direct bill description is required and must not exceed 2000 characters")

    request_key = str(idempotency_key or uuid.uuid4()).strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", request_key):
        raise HTTPException(status_code=400, detail="Invalid idempotency key")

    booking = await db.bookings.find_one(
        {"id": booking_id, "tenant_id": current_user.tenant_id},
        {"_id": 1},
    )
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    account = await db.city_ledger_accounts.find_one({"id": account_id, "tenant_id": current_user.tenant_id})

    if not account:
        raise HTTPException(status_code=404, detail="City ledger account not found")

    try:
        current_balance = float(account.get("current_balance", 0))
        credit_limit = float(account.get("credit_limit", 0))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="City ledger account balance is invalid") from exc
    if not math.isfinite(current_balance) or current_balance < 0 or not math.isfinite(credit_limit) or credit_limit < 0:
        raise HTTPException(status_code=409, detail="City ledger account balance is invalid")
    if current_balance + amount > credit_limit:
        raise HTTPException(status_code=409, detail="Credit limit exceeded")

    transaction_mongo_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"city-ledger-charge:{current_user.tenant_id}:{account_id}:{request_key}"))
    existing = await db.city_ledger_transactions.find_one(
        {"_id": transaction_mongo_id, "tenant_id": current_user.tenant_id},
    )
    if existing:
        if existing.get("status") == "completed":
            return {
                "success": True,
                "replayed": True,
                "transaction_id": existing["id"],
                "account_name": account["account_name"],
                "amount_posted": existing["amount"],
                "new_balance": existing["new_balance"],
            }
        raise HTTPException(status_code=409, detail="Direct bill is already being processed")

    # Create transaction
    transaction = CityLedgerTransaction(
        tenant_id=current_user.tenant_id,
        account_id=account_id,
        transaction_type="charge",
        amount=amount,
        description=description,
        posted_by=current_user.name,
    )
    transaction_doc = transaction.model_dump()
    transaction_doc.update(
        {
            "_id": transaction_mongo_id,
            "booking_id": booking_id,
            "idempotency_key": request_key,
            "status": "pending",
        }
    )
    try:
        await db.city_ledger_transactions.insert_one(transaction_doc)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail="Direct bill is already being processed") from exc

    new_balance = round(current_balance + amount, 2)
    balance_update = await db.city_ledger_accounts.update_one(
        {
            "id": account_id,
            "tenant_id": current_user.tenant_id,
            "current_balance": current_balance,
            "credit_limit": {"$gte": new_balance},
        },
        {"$inc": {"current_balance": amount}},
    )
    if balance_update.modified_count != 1:
        await db.city_ledger_transactions.delete_one({"_id": transaction_mongo_id, "status": "pending"})
        raise HTTPException(status_code=409, detail="City ledger balance changed; refresh and try again")

    try:
        transaction_update = await db.city_ledger_transactions.update_one(
            {"_id": transaction_mongo_id, "status": "pending"},
            {"$set": {"status": "completed", "new_balance": new_balance}},
        )
        if transaction_update.modified_count != 1:
            raise RuntimeError("City ledger transaction finalization failed")
    except Exception:
        rollback = await db.city_ledger_accounts.update_one(
            {
                "id": account_id,
                "tenant_id": current_user.tenant_id,
                "current_balance": new_balance,
            },
            {"$inc": {"current_balance": -amount}},
        )
        if rollback.modified_count == 1:
            await db.city_ledger_transactions.delete_one({"_id": transaction_mongo_id, "status": "pending"})
        raise

    return {
        "success": True,
        "replayed": False,
        "transaction_id": transaction.id,
        "account_name": account["account_name"],
        "amount_posted": amount,
        "new_balance": new_balance,
    }


@router.get("/cashiering/outstanding-balance")
async def get_outstanding_balances(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get all city ledger accounts with outstanding balances"""
    current_user = await get_current_user(credentials)
    _enforce(current_user, "view_outstanding_balance")  # Bug CT

    accounts = await db.city_ledger_accounts.find({"tenant_id": current_user.tenant_id, "current_balance": {"$gt": 0}}, {"_id": 0}).sort("current_balance", -1).to_list(1000)

    total_outstanding = sum(a["current_balance"] for a in accounts)

    return {"accounts": accounts, "total_accounts": len(accounts), "total_outstanding": round(total_outstanding, 2)}


@router.get("/cashiering/city-ledger/{account_id}/open-items")
async def get_city_ledger_open_items(
    account_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Show which reservation rooms make up an account's city-ledger balance.

    Only source transactions that are explicitly linked to a booking are shown
    as room items.  Legacy generic payments and write-offs are reported
    separately so an operator can reconcile them without falsely assigning
    them to a room.
    """
    current_user = await get_current_user(credentials)
    _enforce(current_user, "view_city_ledger_transactions")

    account = await db.city_ledger_accounts.find_one(
        {"id": account_id, "tenant_id": current_user.tenant_id},
        {"_id": 0},
    )
    if not account:
        raise HTTPException(status_code=404, detail="Cari hesap bulunamadı")

    items, totals = await _city_ledger_booking_items(current_user.tenant_id, account_id)
    account_balance = round(_as_finite_money(account.get("current_balance")), 2)
    tracked_balance = round(
        totals["room_open_total"] - totals["unallocated_payment_total"] - totals["adjustment_total"],
        2,
    )
    return {
        "account_id": account_id,
        "account_name": account.get("account_name"),
        "items": items,
        "summary": {
            **totals,
            "account_balance": account_balance,
            "tracked_balance": tracked_balance,
            "balance_difference": round(account_balance - tracked_balance, 2),
        },
    }


@router.post("/cashiering/city-ledger-payment")
async def post_city_ledger_payment(
    account_id: str,
    amount: float,
    payment_method: str,
    reference: str | None = None,
    idempotency_key: str | None = None,
    # ``embed=True`` keeps the HTTP contract explicit: {"allocations": [...]}.
    # The rest of this legacy endpoint remains query parameters for backwards
    # compatibility with existing payment clients.
    allocations: Annotated[list[CityLedgerPaymentAllocation] | None, Body(embed=True)] = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Post a general or reservation-allocated payment to a city ledger account."""
    current_user = await get_current_user(credentials)
    _enforce(current_user, "post_city_ledger_payment")  # Bug CT

    if not math.isfinite(amount) or amount <= 0:
        raise HTTPException(status_code=400, detail="Payment amount must be a finite positive amount")

    payment_method = str(payment_method or "").strip().lower()
    if payment_method not in {"bank_transfer", "credit_card", "cash", "check"}:
        raise HTTPException(status_code=400, detail="Unsupported payment method")

    request_key = str(idempotency_key or uuid.uuid4()).strip()
    if not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", request_key):
        raise HTTPException(status_code=400, detail="Invalid idempotency key")

    account = await db.city_ledger_accounts.find_one({"id": account_id, "tenant_id": current_user.tenant_id})

    if not account:
        raise HTTPException(status_code=404, detail="Account not found")

    try:
        current_balance = float(account.get("current_balance", 0))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail="Account balance is invalid") from exc
    if not math.isfinite(current_balance) or current_balance < 0:
        raise HTTPException(status_code=409, detail="Account balance is invalid")
    if amount > current_balance:
        raise HTTPException(status_code=409, detail="Payment amount exceeds outstanding balance")

    normalized_allocations: list[dict] = []
    if allocations:
        allocation_total = 0.0
        allocation_booking_ids: set[str] = set()
        for allocation in allocations:
            booking_id = allocation.booking_id.strip()
            allocation_amount = round(float(allocation.amount), 2)
            if booking_id in allocation_booking_ids:
                raise HTTPException(status_code=400, detail="Aynı rezervasyon ödeme dağıtımında birden fazla kez seçilemez")
            allocation_booking_ids.add(booking_id)
            allocation_total += allocation_amount
            normalized_allocations.append({"booking_id": booking_id, "amount": allocation_amount})

        if round(allocation_total, 2) != round(amount, 2):
            raise HTTPException(status_code=400, detail="Oda dağıtım toplamı ödeme tutarına eşit olmalıdır")

        items, _ = await _city_ledger_booking_items(current_user.tenant_id, account_id)
        open_by_booking = {item["booking_id"]: item["open_amount"] for item in items}
        for allocation in normalized_allocations:
            available = open_by_booking.get(allocation["booking_id"])
            if available is None:
                raise HTTPException(status_code=409, detail="Seçilen rezervasyon bu carinin açık oda bakiyesinde bulunamadı")
            if allocation["amount"] - available > 0.005:
                raise HTTPException(status_code=409, detail="Bir odaya ayrılan tahsilat o odanın açık bakiyesini aşamaz")

    transaction_mongo_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"city-ledger-payment:{current_user.tenant_id}:{account_id}:{request_key}"))
    existing = await db.city_ledger_transactions.find_one({"_id": transaction_mongo_id, "tenant_id": current_user.tenant_id})
    if existing:
        if existing.get("status") == "completed":
            return {
                "success": True,
                "replayed": True,
                "transaction_id": existing["id"],
                "account_name": account["account_name"],
                "amount_paid": existing["amount"],
                "new_balance": existing["new_balance"],
                "allocations": existing.get("allocations", []),
            }
        raise HTTPException(status_code=409, detail="Payment is already being processed")

    transaction = CityLedgerTransaction(
        tenant_id=current_user.tenant_id,
        account_id=account_id,
        transaction_type="payment",
        amount=amount,
        description=f"Payment received via {payment_method}",
        reference_number=reference,
        posted_by=current_user.name,
    )
    transaction_doc = transaction.model_dump()
    transaction_doc.update({"_id": transaction_mongo_id, "idempotency_key": request_key, "status": "pending"})
    if normalized_allocations:
        transaction_doc["allocations"] = normalized_allocations
        if len(normalized_allocations) == 1:
            transaction_doc["booking_id"] = normalized_allocations[0]["booking_id"]
    try:
        await db.city_ledger_transactions.insert_one(transaction_doc)
    except DuplicateKeyError as exc:
        raise HTTPException(status_code=409, detail="Payment is already being processed") from exc

    new_balance = round(current_balance - amount, 2)
    balance_update = await db.city_ledger_accounts.update_one(
        {
            "id": account_id,
            "tenant_id": current_user.tenant_id,
            "current_balance": {"$gte": amount},
        },
        {"$inc": {"current_balance": -amount}},
    )
    if balance_update.modified_count != 1:
        await db.city_ledger_transactions.delete_one({"_id": transaction_mongo_id, "status": "pending"})
        raise HTTPException(status_code=409, detail="Outstanding balance changed; refresh and try again")

    try:
        transaction_update = await db.city_ledger_transactions.update_one(
            {"_id": transaction_mongo_id, "status": "pending"},
            {"$set": {"status": "completed", "new_balance": new_balance}},
        )
        if transaction_update.modified_count != 1:
            raise RuntimeError("City ledger payment finalization failed")
    except Exception:
        await db.city_ledger_accounts.update_one(
            {"id": account_id, "tenant_id": current_user.tenant_id},
            {"$inc": {"current_balance": amount}},
        )
        await db.city_ledger_transactions.delete_one({"_id": transaction_mongo_id, "status": "pending"})
        raise

    return {
        "success": True,
        "replayed": False,
        "transaction_id": transaction.id,
        "account_name": account["account_name"],
        "amount_paid": amount,
        "new_balance": new_balance,
        "allocations": normalized_allocations,
    }


@router.get("/cashiering/city-ledger/{account_id}/transactions")
async def get_city_ledger_transactions(account_id: str, limit: int = 100, credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get transaction history for city ledger account"""
    current_user = await get_current_user(credentials)
    _enforce(current_user, "view_city_ledger_transactions")  # Bug CT

    transactions = await db.city_ledger_transactions.find({"account_id": account_id, "tenant_id": current_user.tenant_id}, {"_id": 0}).sort("transaction_date", -1).limit(limit).to_list(limit)

    charges = sum(t["amount"] for t in transactions if t["transaction_type"] == "charge")
    payments = sum(t["amount"] for t in transactions if t["transaction_type"] == "payment")

    return {
        "account_id": account_id,
        "transactions": transactions,
        "summary": {"total_charges": round(charges, 2), "total_payments": round(payments, 2), "current_balance": round(charges - payments, 2), "transaction_count": len(transactions)},
    }


@router.post("/cashiering/city-ledger-adjustment")
async def post_city_ledger_adjustment(
    account_id: str,
    amount: float,
    description: str,
    adjustment_type: str = "commission",
    idempotency_key: str = "",
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """Write off a commission/discount difference against a city ledger account balance.

    adjustment_type values:
      - commission   : acente komisyonu düşümü
      - discount     : indirim / promosyon
      - writeoff     : şüpheli alacak silme
      - other        : diğer
    """
    current_user = await get_current_user(credentials)
    _enforce(current_user, "post_city_ledger_payment")  # same permission as payment

    if amount <= 0:
        raise HTTPException(status_code=400, detail="Ayarlama tutarı sıfırdan büyük olmalıdır")

    valid_types = {"commission", "discount", "writeoff", "other"}
    if adjustment_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Geçersiz ayarlama tipi. Geçerli değerler: {valid_types}")

    account = await db.city_ledger_accounts.find_one({"id": account_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not account:
        raise HTTPException(status_code=404, detail="Cari hesap bulunamadı")

    current_balance = account.get("current_balance", 0.0)
    if current_balance <= 0:
        raise HTTPException(status_code=409, detail="Bu hesabın düşülecek bakiyesi bulunmuyor")
    if amount > current_balance + 0.005:
        raise HTTPException(status_code=409, detail="Ayarlama tutarı mevcut bakiyeyi aşamaz")

    request_key = idempotency_key or f"adj:{current_user.tenant_id}:{account_id}:{round(amount, 2)}"
    now = datetime.now(UTC).isoformat()

    transaction_doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "account_id": account_id,
        "transaction_type": "adjustment",
        "adjustment_type": adjustment_type,
        "amount": round(amount, 2),
        "description": description or f"{adjustment_type.capitalize()} ayarlaması",
        "posted_by": current_user.name,
        "transaction_date": now,
        "idempotency_key": request_key,
        "status": "completed",
    }

    try:
        await db.city_ledger_transactions.insert_one(transaction_doc)
    except Exception:
        raise HTTPException(status_code=409, detail="Bu ayarlama zaten kaydedilmiş")

    new_balance = round(current_balance - amount, 2)
    await db.city_ledger_accounts.update_one(
        {"id": account_id, "tenant_id": current_user.tenant_id},
        {"$set": {"current_balance": max(0.0, new_balance)}},
    )

    transaction_doc.pop("_id", None)
    return {
        "success": True,
        "adjustment": transaction_doc,
        "previous_balance": current_balance,
        "new_balance": max(0.0, new_balance),
    }
