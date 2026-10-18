"""Auto-split from finance.py — section: mobile."""

import re
import uuid
from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from modules.pms_core.role_permission_service import require_op  # v92 DW

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: F401
    from openpyxl.utils import get_column_letter  # noqa: F401
except ImportError:
    Workbook = None

from core.business_date_service import (
    ensure_business_date_initialized,
    stamp_open_business_date,
)
from core.database import db
from core.security import get_current_user
from modules.folio.services.folio_balance_read_service import FolioBalanceReadService
from modules.folio.services.open_folio_service import OpenFolioService
from modules.pms_core.receivable_reporting import folio_snapshots, iso_value, outstanding_invoice, receivable_rows, report_day, row_totals
from modules.pms_core.report_money import add_amount, currency_code, resolve_ledger_currencies, rounded_totals, single_amount
from modules.pms_core.reporting_financials import (
    NON_CASH_PAYMENT_METHODS,
    REPORTING_CURRENCY,
    deduplicate_report_payments,
    is_valid_payment,
    report_payment_day_match,
    report_payment_period_match,
    reporting_collection_amount,
    stamp_reporting_values,
)
from shared_kernel.idempotency import claim_short_window_dedup, release_idempotency

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


async def _receivables(tenant_id):
    from core.tenant_currency import get_tenant_currency

    state = await ensure_business_date_initialized(db, tenant_id)
    day = report_day(state["business_date"])
    currency, _ = await get_tenant_currency(tenant_id)
    return day, currency, await receivable_rows(db, tenant_id, day, fallback_currency=currency)


async def _enrich_receivable_guests(rows, tenant_id):
    ids = list({r["guest_id"] for r in rows if r.get("guest_id")})
    guests = {}
    if ids:
        from security.encrypted_lookup import decrypt_guest_doc

        async for guest in db.guests.find({"tenant_id": tenant_id, "id": {"$in": ids}}, {"_id": 0}):
            guests[guest["id"]] = decrypt_guest_doc(guest)
    for row in rows:
        guest = guests.get(row.get("guest_id"), {})
        row.update(guest_name=guest.get("name") or row["guest_name"], guest_email=guest.get("email"), guest_phone=guest.get("phone"))

_FX_RECEIPT_RE = re.compile(
    r"\[Döviz Çevirici\]\s*[\d.,]+\s+[A-Z]{2,3}\s*=\s*([\d.,]+)\s+([A-Z]{2,3})",
    re.IGNORECASE,
)


def _received_payment_amount(payment: dict) -> tuple[float, str]:
    if payment.get("received_amount") is not None and payment.get("received_currency"):
        try:
            return float(payment["received_amount"]), currency_code(payment["received_currency"])
        except (TypeError, ValueError):
            pass
    match = _FX_RECEIPT_RE.search(str(payment.get("notes") or ""))
    if match:
        try:
            return float(match.group(1).replace(",", ".")), match.group(2).upper()
        except ValueError:
            pass
    return float(payment.get("amount") or 0), currency_code(payment.get("currency"))


def _received_collection_amount(payment: dict) -> tuple[float, str]:
    """Return the received-currency amount with the standard refund sign."""
    amount, currency = _received_payment_amount(payment)
    if str(payment.get("payment_type") or "").strip().lower() == "refund" and amount > 0:
        amount = -amount
    return amount, currency


def _is_reportable_collection(payment: dict) -> bool:
    """Exclude voids and folio-only adjustments from cash collection reports."""
    method = str(payment.get("payment_method") or payment.get("method") or "").strip().lower()
    return is_valid_payment(payment) and method not in NON_CASH_PAYMENT_METHODS


async def _collection_rows(query: dict, tenant_id: str) -> list[dict]:
    rows = deduplicate_report_payments(await db.payments.find(query).to_list(None))
    return await resolve_ledger_currencies(rows, tenant_id, database=db, fallback_currency=REPORTING_CURRENCY)


def _month_bounds(year: int, month: int) -> tuple[datetime, datetime]:
    try:
        start = datetime(year, month, 1, tzinfo=UTC)
        end = datetime(year + 1, 1, 1, tzinfo=UTC) if month == 12 else datetime(year, month + 1, 1, tzinfo=UTC)
        return start, end
    except ValueError as exc:
        raise HTTPException(422, "Geçersiz yıl veya ay") from exc


class RecordPaymentRequest(BaseModel):
    folio_id: str
    amount: float = Field(gt=0, allow_inf_nan=False)
    payment_method: Literal["cash", "card", "transfer", "check"]
    currency: str | None = None
    notes: str | None = None


@router.get("/finance/mobile/daily-collections")
@cached(ttl=120, key_prefix="mobile_daily_collections")
async def get_daily_collections_mobile(
    date: str | None = None,
    current_user=Depends(get_current_user),  # tenant-aware cache key (Tur 2 fix)
    _perm=Depends(require_op("view_finance_reports")),  # v102 DW finance leak fix
    _nocache: bool = Query(False, alias="nocache"),
):
    """Get daily collections for finance mobile dashboard"""

    if date:
        target_date = datetime.fromisoformat(date)
    else:
        business_state = await ensure_business_date_initialized(db, current_user.tenant_id)
        target_date = datetime.fromisoformat(str(business_state["business_date"])[:10])

    # Get payments for the day
    total_collected = 0.0
    payment_count = 0
    payment_methods = {}
    totals_by_currency: dict[str, float] = {}
    methods_by_currency: dict[str, dict[str, float]] = {}
    method_counts: dict[str, int] = {}
    conversion_issue_count = 0

    business_day = target_date.date().isoformat()
    payment_query = {
        "tenant_id": current_user.tenant_id,
        **report_payment_day_match(business_day),
    }
    for payment in await _collection_rows(payment_query, current_user.tenant_id):
        if not _is_reportable_collection(payment):
            continue
        received_amount, currency = _received_collection_amount(payment)
        amount = reporting_collection_amount(payment)
        totals_by_currency[currency] = totals_by_currency.get(currency, 0) + received_amount
        if amount is None:
            conversion_issue_count += 1
            continue
        total_collected += amount
        payment_count += 1

        method = payment.get("payment_method") or payment.get("method") or "unknown"
        payment_methods[method] = payment_methods.get(method, 0) + amount
        method_totals = methods_by_currency.setdefault(method, {})
        method_totals[REPORTING_CURRENCY] = method_totals.get(REPORTING_CURRENCY, 0) + amount
        method_counts[method] = method_counts.get(method, 0) + 1

    return {
        "date": target_date.date().isoformat(),
        "total_collected": total_collected,
        "payment_count": payment_count,
        "payment_methods": payment_methods,
        "average_transaction": total_collected / payment_count if payment_count > 0 else 0,
        "reporting_currency": REPORTING_CURRENCY,
        "totals_by_currency": {REPORTING_CURRENCY: round(total_collected, 2)},
        "received_totals_by_currency": {key: round(value, 2) for key, value in totals_by_currency.items()},
        "conversion_issue_count": conversion_issue_count,
        "payment_methods_by_currency": {
            method: {key: round(value, 2) for key, value in totals.items()}
            for method, totals in methods_by_currency.items()
        },
        "payment_method_counts": method_counts,
    }


@router.get("/finance/mobile/monthly-collections")
@cached(ttl=300, key_prefix="mobile_monthly_collections")
async def get_monthly_collections_mobile(
    year: int | None = None,
    month: int | None = None,
    current_user=Depends(get_current_user),  # tenant-aware cache key (Tur 2 fix)
    _perm=Depends(require_op("view_finance_reports")),  # v102 DW finance leak fix
    _nocache: bool = Query(False, alias="nocache"),
):
    """Get monthly collections for finance mobile dashboard"""

    business_state = await ensure_business_date_initialized(db, current_user.tenant_id)
    today = datetime.fromisoformat(str(business_state["business_date"])[:10])
    target_year = year if year is not None else today.year
    target_month = month if month is not None else today.month
    start_of_month, end_of_month = _month_bounds(target_year, target_month)

    # Get payments for the month
    total_collected = 0.0
    payments_by_method = {}
    totals_by_currency: dict[str, float] = {}
    conversion_issue_count = 0

    last_business_day = (end_of_month - timedelta(days=1)).date().isoformat()
    payment_query = {
        "tenant_id": current_user.tenant_id,
        **report_payment_period_match(start_of_month.date().isoformat(), last_business_day),
    }
    for payment in await _collection_rows(payment_query, current_user.tenant_id):
        if not _is_reportable_collection(payment):
            continue
        received_amount, currency = _received_collection_amount(payment)
        amount = reporting_collection_amount(payment)
        totals_by_currency[currency] = totals_by_currency.get(currency, 0) + received_amount
        if amount is None:
            conversion_issue_count += 1
            continue
        total_collected += amount

        method = payment.get("payment_method") or payment.get("method") or "unknown"
        payments_by_method[method] = payments_by_method.get(method, 0) + amount

    return {"total_collected": round(total_collected, 2), "reporting_currency": REPORTING_CURRENCY, "conversion_issue_count": conversion_issue_count, "month": target_month, "year": target_year, "payments_by_method": {k: round(v, 2) for k, v in payments_by_method.items()}, "received_totals_by_currency": {k: round(v, 2) for k, v in totals_by_currency.items()}, "totals_by_currency": {REPORTING_CURRENCY: round(total_collected, 2)}}


@router.get("/finance/profit-loss")
async def get_profit_loss_report_v2(
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_finance_reports")),  # v102 DW finance leak fix
):
    """Get Profit & Loss (P&L) report"""
    current_user = await get_current_user(credentials)
    from routers.finance.accounting import get_profit_loss_report

    state = await ensure_business_date_initialized(db, current_user.tenant_id)
    day = datetime.fromisoformat(str(state["business_date"])[:10]).date()
    return await get_profit_loss_report(start_date or day.replace(day=1).isoformat(), end_date or day.isoformat(), current_user=current_user)


@router.get("/finance/cashier-shift-report")
async def get_cashier_shift_report(
    shift_date: str | None = None,
    cashier_name: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_finance_reports")),  # v102 DW finance leak fix
):
    """Get cashier shift report"""
    current_user = await get_current_user(credentials)

    if shift_date:
        target_date = datetime.fromisoformat(shift_date)
    else:
        # A cashier report without an explicit date belongs to the hotel's
        # currently open accounting day, not the server's UTC calendar day.
        business_state = await ensure_business_date_initialized(db, current_user.tenant_id)
        target_date = datetime.fromisoformat(str(business_state["business_date"])[:10])

    business_day = target_date.date().isoformat()
    query = {
        "tenant_id": current_user.tenant_id,
        **report_payment_day_match(business_day),
    }

    if cashier_name:
        query["created_by"] = cashier_name

    # Get all payments/transactions
    transaction_count = 0
    totals_by_currency: dict[str, float] = {}
    methods_by_currency: dict[str, dict[str, float]] = {}
    counts_by_currency = {}
    method_counts: dict[str, int] = {}

    for payment in await _collection_rows(query, current_user.tenant_id):
        if not _is_reportable_collection(payment):
            continue
        amount, currency = _received_collection_amount(payment)
        method = str(payment.get("payment_method") or payment.get("method") or "cash").strip().lower()
        method = {"bank_transfer": "transfer", "credit_card": "card"}.get(method, method)
        method = method if method in {"cash", "card", "transfer"} else "other"
        totals_by_currency[currency] = totals_by_currency.get(currency, 0) + amount
        method_totals = methods_by_currency.setdefault(method, {})
        method_totals[currency] = method_totals.get(currency, 0) + amount

        counts_by_currency[currency] = counts_by_currency.get(currency, 0) + 1
        method_counts[method] = method_counts.get(method, 0) + 1
        transaction_count += 1

    averages = {code: amount / counts_by_currency[code] for code, amount in totals_by_currency.items()}

    # Get opening and closing balance (if tracked)
    # This endpoint selects payments by day/name, not a counted cashier shift.
    # No opening count or physical closing evidence means UNKNOWN, not zero
    # and not a fabricated "balanced" reconciliation.

    return {
        "shift_date": target_date.date().isoformat(),
        "cashier_name": cashier_name or "All Cashiers",
        "opening_balance": None,
        "collections": {**{method: single_amount(methods_by_currency.get(method, {})) for method in ("cash", "card", "transfer", "other")}, "total": single_amount(totals_by_currency)},
        "expected_closing_balance": None, "total_paid_out": None,
        "variance": None, "balance_status": "physical_shift_count_not_available", "basis": "daily_payment_movements",
        "transaction_count": transaction_count,
        "payment_method_counts": method_counts,
        "average_transaction": single_amount(averages), "average_by_currency": rounded_totals(averages),
        "totals_by_currency": {key: round(value, 2) for key, value in totals_by_currency.items()},
        "payment_methods_by_currency": {
            method: {key: round(value, 2) for key, value in totals.items()}
            for method, totals in methods_by_currency.items()
        },
        "generated_at": datetime.now(UTC).isoformat(),
    }


@router.get("/finance/mobile/pending-receivables")
@cached(ttl=180, key_prefix="mobile_pending_receivables")
async def get_pending_receivables_mobile(
    current_user=Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
    _nocache: bool = Query(False, alias="nocache"),
):
    day, currency, rows = await _receivables(current_user.tenant_id)
    totals = row_totals(rows)
    overdue = row_totals([r for r in rows if r["is_overdue"]])
    return {"total_pending": single_amount(totals), "overdue_amount": single_amount(overdue),
            "totals_by_currency": totals, "overdue_by_currency": overdue, "as_of_date": day.isoformat(),
            "receivables_count": len(rows), "receivables": rows[:20], "returned_count": min(len(rows), 20),
            "truncated": len(rows) > 20, "currency": currency, "basis": "posted_folio_ledger", "order": "oldest_checkout_first"}


@router.get("/finance/mobile/monthly-costs")
async def get_monthly_costs_mobile(
    year: int | None = None,
    month: int | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_finance_reports")),  # v102 DW finance leak fix
):
    """Get monthly costs for finance mobile dashboard"""
    current_user = await get_current_user(credentials)

    state = await ensure_business_date_initialized(db, current_user.tenant_id)
    today = datetime.fromisoformat(str(state["business_date"])[:10])
    target_year = year if year is not None else today.year
    target_month = month if month is not None else today.month
    start_of_month, end_of_month = _month_bounds(target_year, target_month)

    from core.tenant_currency import get_tenant_currency

    currency, _ = await get_tenant_currency(current_user.tenant_id)

    # Get expenses for the month
    totals, categories = {}, {}

    last_day = (end_of_month - timedelta(days=1)).date().isoformat()
    expense_query = {
        "tenant_id": current_user.tenant_id,
        "voided": {"$ne": True},
        "status": {"$nin": ["cancelled", "canceled", "voided"]},
        **report_payment_period_match(
            start_of_month.date().isoformat(),
            last_day,
            date_fields=("date", "expense_date", "created_at"),
        ),
    }
    async for expense in db.expenses.find(expense_query):
        amount = expense.get("total_amount", expense.get("amount", 0))
        category = expense.get("category", "other")
        add_amount(totals, expense.get("currency") or currency, amount)
        add_amount(categories.setdefault(category, {}), expense.get("currency") or currency, amount)
    return {"year": target_year, "month": target_month, "total_costs": single_amount(totals),
        "totals_by_currency": rounded_totals(totals), "costs_by_category": {key: single_amount(value) for key, value in categories.items()},
        "categories_by_currency": {key: rounded_totals(value) for key, value in categories.items()}, "currency": next(iter(totals)) if len(totals) == 1 else currency,
        "mixed_currency": len(totals) > 1}


@router.post("/finance/mobile/record-payment")
async def record_payment_mobile(
    request: RecordPaymentRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("post_payment")),  # v92 DW
):
    """Record a payment from finance mobile"""
    current_user = await get_current_user(credentials)
    folio_id = request.folio_id
    amount = request.amount
    payment_method = request.payment_method
    notes = request.notes

    # Validate folio
    folio = await db.folios.find_one({"id": folio_id, "tenant_id": current_user.tenant_id})

    if not folio:
        raise HTTPException(status_code=404, detail="Folio not found")

    from core.tenant_currency import get_tenant_currency

    tenant_currency, _ = await get_tenant_currency(current_user.tenant_id)
    snapshot = (await folio_snapshots(db, current_user.tenant_id, [folio], fallback_currency=tenant_currency))[folio_id]
    ledger_currency = snapshot["currency"]
    if request.currency and currency_code(request.currency) != ledger_currency:
        raise HTTPException(409, "Tahsilat para birimi folyo para birimiyle aynı olmalıdır.")
    # The compact form has no FX quote/TRY counterpart. The cashier service
    # books its amount in TRY: passing a foreign nominal amount would invent
    # a 1:1 rate. Use the full folio payment workflow for foreign currencies.
    if ledger_currency != "TRY":
        raise HTTPException(409, "Döviz tahsilatını kur bilgisiyle ayrıntılı folyo ekranından kaydedin.")
    if any(code != ledger_currency and balance for code, balance in snapshot["balance_by_currency"].items()):
        raise HTTPException(409, "Birden fazla para birimi içeren folyoyu ayrıntılı folyo ekranından uzlaştırın.")
    if folio.get("status") != "open":
        raise HTTPException(409, "Yalnız açık folyoya tahsilat kaydedilebilir.")

    # Vardiya kontrolü: nakit ödemede aktif vardiya zorunlu
    from domains.pms.cashier_service import ensure_active_shift, record_cash_transaction

    await ensure_active_shift(current_user.tenant_id, payment_method)

    # This endpoint carries NO Idempotency-Key, so a double-tap (same folio +
    # amount + method, seconds apart) would post two payments. Server-side
    # short-window guard rejects the suspected duplicate (409) instead of
    # silently double-charging the guest.
    dedup = await claim_short_window_dedup(
        db,
        tenant_id=current_user.tenant_id,
        scope=f"auto_payment_dedup:folio:{folio_id}",
        fingerprint=f"{round(float(amount), 2)}|{payment_method}|final",
    )
    if dedup["status"] == "duplicate":
        raise HTTPException(
            status_code=409,
            detail="Olası çift ödeme: aynı tutar saniyeler içinde tekrar gönderildi",
        )
    auto_lock_id = dedup["lock_id"]

    # Create payment
    payment_id = str(uuid.uuid4())
    payment = {
        "id": payment_id,
        "tenant_id": current_user.tenant_id,
        "folio_id": folio_id,
        "booking_id": folio.get("booking_id"),
        "amount": amount,
        "currency": ledger_currency,
        "received_amount": amount,
        "received_currency": ledger_currency,
        "exchange_rate": 1,
        "payment_method": payment_method,
        "payment_type": "final",
        "notes": notes,
        "created_at": datetime.now(UTC),
        "created_by": current_user.username,
    }
    await stamp_open_business_date(db, current_user.tenant_id, payment)
    stamp_reporting_values(payment)

    try:
        await db.payments.insert_one(payment)
    except Exception:
        # Payment never became durable -> free the auto-dedup slot for a retry.
        await release_idempotency(db, lock_id=auto_lock_id)
        raise

    # Kasa hareketine yaz — cash için race-safe rollback
    is_cash = (payment_method or "").lower() == "cash"
    try:
        await record_cash_transaction(
            tenant_id=current_user.tenant_id,
            amount=amount,
            method=payment_method,
            direction="in",
            description=f"Mobil ödeme - Folio {folio_id[:8]}",
            txn_type="folio_payment",
            ref_type="payment",
            ref_id=payment_id,
            created_by=current_user.email,
            created_by_name=getattr(current_user, "name", None) or current_user.email,
            idempotency_key=f"payment:{payment_id}",
            require_open_shift=is_cash,
        )
    except HTTPException as he:
        if is_cash and he.status_code == 409:
            try:
                await db.payments.delete_one({"id": payment_id, "tenant_id": current_user.tenant_id})
                # Row removed -> free the auto-dedup slot for a real retry.
                await release_idempotency(db, lock_id=auto_lock_id)
            except Exception:
                import logging as _lg

                _lg.getLogger(__name__).exception("payment rollback failed after cashier 409")
        raise
    except Exception:
        import logging as _lg

        _lg.getLogger(__name__).exception("cashier txn record failed")

    # Update folio balance
    snapshot = (await folio_snapshots(db, current_user.tenant_id, [folio], fallback_currency=tenant_currency))[folio_id]
    new_balance = single_amount(snapshot["balance_by_currency"])
    updates = {"balance_by_currency": snapshot["balance_by_currency"]}
    if new_balance is not None:
        updates["balance"] = new_balance
    await db.folios.update_one({"id": folio_id, "tenant_id": current_user.tenant_id}, {"$set": updates})

    # Close folio if balance is zero
    if new_balance is not None and abs(new_balance) < 0.01:
        await db.folios.update_one({"id": folio_id, "tenant_id": current_user.tenant_id}, {"$set": {"status": "closed", "closed_at": datetime.now(UTC), "closed_by": current_user.username}})

    return {"message": "Payment recorded successfully", "payment_id": payment_id, "folio_id": folio_id, "amount": amount, "currency": ledger_currency,
            "new_balance": new_balance, "balance_by_currency": snapshot["balance_by_currency"], "folio_closed": new_balance is not None and abs(new_balance) < 0.01}


@router.get("/finance/mobile/cash-flow-summary")
@cached(ttl=180, key_prefix="mobile_cash_flow_summary")
async def get_cash_flow_summary_mobile(
    current_user=Depends(get_current_user),  # tenant-aware cache key (Tur 2 fix)
    _perm=Depends(require_op("view_finance_reports")),  # v102 DW finance leak fix
):
    """Get cash flow summary for finance mobile dashboard
    - Today's cash inflow (tahsilat)
    - Today's cash outflow (gider)
    - Weekly collection/payment plan
    - Bank balance summaries
    """
    business_state = await ensure_business_date_initialized(db, current_user.tenant_id)
    today = datetime.fromisoformat(str(business_state["business_date"])[:10]).date()
    from core.tenant_currency import get_tenant_currency

    tenant_currency, _ = await get_tenant_currency(current_user.tenant_id)

    # Today's cash inflow (payments received)
    inflow_count = 0
    inflow_by_currency: dict[str, float] = {}
    payment_query = {
        "tenant_id": current_user.tenant_id,
        **report_payment_day_match(today.isoformat()),
    }
    for payment in await _collection_rows(payment_query, current_user.tenant_id):
        if not _is_reportable_collection(payment):
            continue
        amount, currency = _received_collection_amount(payment)
        add_amount(inflow_by_currency, currency, amount)
        inflow_count += 1

    # Today's cash outflow (expenses)
    outflow_count = 0
    outflow_by_currency: dict[str, float] = {}
    expense_query = {
        "tenant_id": current_user.tenant_id,
        "transaction_type": "expense",
        **report_payment_day_match(today.isoformat()),
    }
    # Cash flow postings, not expense accruals or a synthetic paid flag.
    async for expense in db.cash_flow.find(expense_query):
        amount = expense.get("amount", 0)
        currency = str(expense.get("currency") or tenant_currency).upper()
        add_amount(outflow_by_currency, currency, amount)
        outflow_count += 1

    # Net cash flow today
    inflow_by_currency, outflow_by_currency = rounded_totals(inflow_by_currency), rounded_totals(outflow_by_currency)
    net_by_currency = {
        currency: round(inflow_by_currency.get(currency, 0) - outflow_by_currency.get(currency, 0), 2)
        for currency in set(inflow_by_currency) | set(outflow_by_currency)
    }

    # Weekly collection plan (Tur 3 perf fix: was 7×N+1 queries, now 3 bulk queries)
    weekly_dates = [(today + timedelta(days=d)).isoformat() for d in range(7)]
    bookings_by_date: dict[str, list[str]] = {d: [] for d in weekly_dates}
    async for booking in db.bookings.find(
        {"tenant_id": current_user.tenant_id, "$or": [
            {"check_out": {"$gte": weekly_dates[0], "$lt": (today + timedelta(days=7)).isoformat()}},
            {"check_out": {"$gte": datetime.combine(today, datetime.min.time(), UTC), "$lt": datetime.combine(today + timedelta(days=7), datetime.min.time(), UTC)}}],
            "status": {"$in": ["confirmed", "guaranteed", "checked_in", "in_house"]}}, {"_id": 0, "id": 1, "check_out": 1}
    ):
        co = str(booking.get("check_out") or "")[:10]
        if co in bookings_by_date and booking.get("id"):
            bookings_by_date[co].append(booking["id"])

    all_booking_ids = [bid for ids in bookings_by_date.values() for bid in ids]
    folios_by_booking = {}
    if all_booking_ids:
        async for folio in db.folios.find({"tenant_id": current_user.tenant_id, "booking_id": {"$in": all_booking_ids}, "status": "open"}, {"_id": 0, "booking_id": 1, "balance": 1, "currency": 1}):
            add_amount(folios_by_booking.setdefault(folio.get("booking_id"), {}), folio.get("currency") or tenant_currency, max(float(folio.get("balance") or 0), 0))

    invoices_by_due = {day: {} for day in weekly_dates}
    # Sales invoices are receivables, not supplier payments. The payment plan
    # uses unpaid expense obligations and deducts partial payments.
    async for invoice in db.expenses.find({"tenant_id": current_user.tenant_id,
        "$or": [{"due_date": {"$gte": weekly_dates[0], "$lt": (today + timedelta(days=7)).isoformat()}},
                {"due_date": {"$gte": datetime.combine(today, datetime.min.time(), UTC), "$lt": datetime.combine(today + timedelta(days=7), datetime.min.time(), UTC)}}],
        "payment_status": {"$in": ["pending", "partial"]}}, {"_id": 0}):
        d = str(invoice.get("due_date") or "")[:10]
        if d in invoices_by_due:
            amount = max(float(invoice.get("total_amount", invoice.get("amount", 0)) or 0) - float(invoice.get("amount_paid") or 0), 0)
            add_amount(invoices_by_due[d], invoice.get("currency") or tenant_currency, amount)

    weekly_plan = []
    for days_ahead in range(7):
        target_date = today + timedelta(days=days_ahead)
        d_iso = target_date.isoformat()
        ids = bookings_by_date.get(d_iso, [])
        expected_collections = {}
        for bid in ids:
            for code, value in folios_by_booking.get(bid, {}).items():
                add_amount(expected_collections, code, value)
        checkout_count = sum(1 for bid in ids if bid in folios_by_booking)
        weekly_plan.append(
            {"date": d_iso, "day_name": target_date.strftime("%A"), "expected_collections": single_amount(expected_collections),
             "collections_by_currency": rounded_totals(expected_collections), "payments_by_currency": rounded_totals(invoices_by_due[d_iso]),
             "expected_payments": single_amount(invoices_by_due[d_iso]), "checkout_count": checkout_count,
             "basis": "open_folio_balances_and_unpaid_expenses"}
        )

    # Bank balance summaries
    bank_balances = []
    async for bank in db.bank_accounts.find({"tenant_id": current_user.tenant_id, "is_active": True}):
        bank_balances.append(
            {
                "bank_name": bank.get("bank_name"),
                "account_number": str(bank.get("account_number") or "")[-4:],
                "currency": currency_code(bank.get("currency"), tenant_currency),
                "current_balance": bank.get("current_balance") if bank.get("current_balance") is not None else bank.get("balance", 0),
                "available_balance": bank.get("available_balance", 0),
                "last_sync": bank["last_sync"].isoformat() if isinstance(bank.get("last_sync"), datetime) else bank.get("last_sync"),
            }
        )

    total_bank_balance = sum(b["current_balance"] for b in bank_balances if b["currency"] == "TRY")

    return {
        "today": {"date": today.isoformat(), "cash_inflow": single_amount(inflow_by_currency), "cash_outflow": single_amount(outflow_by_currency),
            "net_flow": single_amount(net_by_currency), "inflow_count": inflow_count, "outflow_count": outflow_count, "currency": tenant_currency,
            "inflow_by_currency": inflow_by_currency, "outflow_by_currency": outflow_by_currency, "net_by_currency": net_by_currency},
        "weekly_plan": weekly_plan,
        "bank_balances": bank_balances,
        "total_bank_balance_try": total_bank_balance,
    }


@router.get("/finance/mobile/overdue-accounts")
@cached(ttl=180, key_prefix="mobile_overdue_accounts")  # Tur 3: was 11s, cache 3 min (tenant-aware key)
async def get_overdue_accounts_mobile(
    min_days: int = Query(7, ge=1),
    current_user=Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
    _nocache: bool = Query(False, alias="nocache"),
):
    day, currency, rows = await _receivables(current_user.tenant_id)
    accounts = [row for row in rows if row["days_overdue"] >= min_days]
    await _enrich_receivable_guests(accounts, current_user.tenant_id)
    for row in accounts:
        days = row["days_overdue"]
        level, color = ("suspicious", "black") if days >= 30 else ("critical", "red") if days >= 15 else ("warning", "yellow") if days >= 8 else ("normal", "green")
        row.update(risk_level=level, risk_color=color)
    totals = row_totals(accounts)
    return {"overdue_accounts": accounts, "as_of_date": day.isoformat(), "currency": currency,
            "basis": "posted_folio_ledger", "aging_basis": "days_since_checkout_not_contractual_due_date",
            "summary": {"total_count": len(accounts), "total_amount": single_amount(totals), "totals_by_currency": totals,
                        **{level + "_count": sum(r["risk_level"] == level for r in accounts) for level in ("suspicious", "critical", "warning")}}}


@router.get("/finance/mobile/credit-limit-violations")
@cached(ttl=300, key_prefix="mobile_credit_limit_violations")  # Tur 3: tenant-aware key
async def get_credit_limit_violations_mobile(
    current_user=Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
    _nocache: bool = Query(False, alias="nocache"),
):
    day, tenant_currency, rows = await _receivables(current_user.tenant_id)
    limits = await db.credit_limits.find({"tenant_id": current_user.tenant_id}, {"_id": 0}).to_list(None)
    ids = list({limit["company_id"] for limit in limits if limit.get("company_id")})
    companies = await db.companies.find({"tenant_id": current_user.tenant_id, "id": {"$in": ids}}, {"_id": 0}).to_list(None) if ids else []
    company_map = {row["id"]: row for row in companies}
    debt = {}
    for row in rows:
        if row.get("company_id"):
            bucket = debt.setdefault(row["company_id"], {})
            for code, amount in row["balance_by_currency"].items():
                add_amount(bucket, code, amount)
    violations, mismatches = [], []
    for limit in limits:
        company = company_map.get(limit.get("company_id"))
        if not company:
            continue
        code = currency_code(limit.get("credit_currency") or limit.get("currency"), tenant_currency)
        totals = rounded_totals(debt.get(limit["company_id"], {}))
        # Historical limits without a currency are denominated in the tenant
        # currency. Foreign debt is visible but never silently converted.
        if any(other != code and amount for other, amount in totals.items()):
            mismatches.append({"company_id": limit["company_id"], "company_name": company.get("name"),
                               "currency": code, "debt_by_currency": totals, "reason": "foreign_currency_debt_not_converted"})
        current = totals.get(code, 0)
        maximum = float(limit.get("credit_limit") or 0)
        utilization = current / maximum * 100 if maximum > 0 else None
        if current <= maximum and (utilization is None or utilization < 90):
            continue
        row = {"company_id": limit["company_id"], "company_name": company.get("name"), "currency": code,
               "credit_limit": maximum, "current_debt": current, "debt_by_currency": totals,
               "over_limit_amount": round(max(current - maximum, 0), 2), "available_credit": round(maximum - current, 2),
               "utilization_percentage": utilization, "payment_terms_days": limit.get("payment_terms_days", 30),
               **{key: company.get(key) for key in ("contact_person", "contact_email", "contact_phone")}}
        if current <= maximum:
            row["warning"] = "Near limit"
        violations.append(row)
    violations.sort(key=lambda row: (row["currency"], -(row["utilization_percentage"] or 0), row["company_id"]))
    return {"violations": violations, "currency_mismatches": mismatches, "as_of_date": day.isoformat(),
            "basis": "posted_folio_ledger", "summary": {"total_count": len(violations),
            "over_limit_count": sum(v["over_limit_amount"] > 0 for v in violations),
            "near_limit_count": sum(v.get("warning") == "Near limit" for v in violations),
            "currency_mismatch_count": len(mismatches)}}


@router.get("/finance/mobile/suspicious-receivables")
@cached(ttl=300, key_prefix="mobile_suspicious_receivables")  # Tur 3: was 10s, cache 5 min (tenant-aware key)
async def get_suspicious_receivables_mobile(
    current_user=Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
    _nocache: bool = Query(False, alias="nocache"),
):
    day, currency, rows = await _receivables(current_user.tenant_id)
    # Preserve the legacy TRY thresholds only in TRY. Thirty-day ageing is
    # meaningful in every currency, even a small EUR/USD nominal balance.
    accounts = [r for r in rows if r["days_overdue"] >= 30 or
                (r["days_overdue"] >= 15 and r["balance_by_currency"].get("TRY", 0) > 5000)]
    await _enrich_receivable_guests(accounts, current_user.tenant_id)
    for row in accounts:
        row["payment_history_count"] = row.pop("ledger_payment_count")
        row["reason"] = "30+ days overdue" if row["days_overdue"] >= 30 else "TRY balance > 5,000 and 15+ days overdue"
    totals = row_totals(accounts)
    return {"suspicious_receivables": accounts, "as_of_date": day.isoformat(), "currency": currency,
            "basis": "posted_folio_ledger", "summary": {"total_count": len(accounts), "total_amount": single_amount(totals),
            "totals_by_currency": totals, "average_days_overdue": sum(r["days_overdue"] for r in accounts) / len(accounts) if accounts else 0}}


@router.get("/finance/mobile/risk-alerts")
@cached(ttl=180, key_prefix="mobile_risk_alerts")  # Tur 3: was 11s, cache 3 min (tenant-aware key)
async def get_risk_alerts_mobile(
    current_user=Depends(get_current_user),
    _perm=Depends(require_op("view_finance_reports")),
    _nocache: bool = Query(False, alias="nocache"),
):
    alerts = []
    overdue = await get_overdue_accounts_mobile(min_days=7, current_user=current_user, _nocache=True)
    for level, severity, title in (("suspicious", "critical", "Şüpheli Alacaklar"), ("critical", "high", "Kritik Gecikmiş Ödemeler")):
        rows = [r for r in overdue["overdue_accounts"] if r["risk_level"] == level]
        if rows:
            totals = row_totals(rows)
            alerts.append({"id": "receivables-" + level, "type": level + "_receivables", "severity": severity, "title": title,
                           "message": f'{len(rows)} adet gecikmiş açık folyo', "amount": single_amount(totals),
                           "amounts_by_currency": totals, "action_required": True})
    limits = await get_credit_limit_violations_mobile(current_user=current_user, _nocache=True)
    for key, severity, title in (("over_limit_count", "critical", "Kredi Limiti Aşımı"), ("near_limit_count", "medium", "Limite Yaklaşan Firmalar"),
                                 ("currency_mismatch_count", "high", "Kredi para birimi kontrolü gerekli")):
        if limits["summary"][key]:
            alerts.append({"id": key, "type": key, "severity": severity, "title": title,
                           "message": f'{limits["summary"][key]} hesap için kontrol gerekli', "action_required": True})
    unpaid = []
    async for invoice in db.accounting_invoices.find({"tenant_id": current_user.tenant_id}, {"_id": 0}):
        # This is the existing 10,000 TRY rule, not a cross-currency threshold.
        if currency_code(invoice.get("currency"), overdue["currency"]) != "TRY":
            continue
        amount = outstanding_invoice(invoice)
        if amount > 10000:
            unpaid.append(amount)
    if unpaid:
        totals = {"TRY": round(sum(unpaid), 2)}
        alerts.append({"id": "large-unpaid-invoices", "type": "large_unpaid_invoices", "severity": "medium",
                       "title": "Büyük Ödenmemiş Faturalar", "message": f"{len(unpaid)} faturada kalan bakiye > 10.000 TRY",
                       "amount": totals["TRY"], "amounts_by_currency": totals, "action_required": False})
    alerts.sort(key=lambda row: {"critical": 0, "high": 1, "medium": 2}.get(row["severity"], 3))
    return {"alerts": alerts, "as_of_date": overdue["as_of_date"], "summary": {"total_alerts": len(alerts),
            "critical_count": sum(a["severity"] == "critical" for a in alerts), "high_count": sum(a["severity"] == "high" for a in alerts),
            "action_required_count": sum(a["action_required"] for a in alerts)}}


@router.get("/finance/mobile/daily-expenses")
async def get_daily_expenses_mobile(
    date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_finance_reports")),
):
    current_user = await get_current_user(credentials)
    from core.tenant_currency import get_tenant_currency

    if date is None:
        state = await ensure_business_date_initialized(db, current_user.tenant_id)
        date = str(state["business_date"])[:10]
    day = report_day(date)
    if day is None:
        raise HTTPException(422, "Geçersiz tarih")
    currency, _ = await get_tenant_currency(current_user.tenant_id)
    totals, categories, departments, count = {}, {}, {}, 0
    query = {"tenant_id": current_user.tenant_id, "voided": {"$ne": True}, "status": {"$nin": ["cancelled", "canceled", "voided"]},
             **report_payment_period_match(day.isoformat(), day.isoformat(), date_fields=("date", "expense_date", "created_at"))}
    async for expense in db.expenses.find(query):
        amount = expense.get("total_amount") if expense.get("total_amount") is not None else expense.get("amount", 0)
        code = currency_code(expense.get("currency"), currency)
        add_amount(totals, code, amount)
        add_amount(categories.setdefault(expense.get("category") or "other", {}), code, amount)
        add_amount(departments.setdefault(expense.get("department") or "other", {}), code, amount)
        count += 1
    return {"date": day.isoformat(), "currency": currency, "basis": "expense_accruals",
            "total_expenses": single_amount(totals), "totals_by_currency": rounded_totals(totals), "expense_count": count,
            "expenses_by_category": {k: single_amount(v) for k, v in categories.items()},
            "categories_by_currency": {k: rounded_totals(v) for k, v in categories.items()},
            "expenses_by_department": {k: single_amount(v) for k, v in departments.items()},
            "departments_by_currency": {k: rounded_totals(v) for k, v in departments.items()}}


@router.get("/finance/mobile/folio-full-extract/{folio_id}")
async def get_folio_full_extract_mobile(
    folio_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_finance_reports")),
):
    current_user = await get_current_user(credentials)
    from core.tenant_currency import get_tenant_currency

    folio = await db.folios.find_one({"id": folio_id, "tenant_id": current_user.tenant_id}, {"_id": 0})
    if not folio:
        raise HTTPException(404, "Folio not found")
    currency, _ = await get_tenant_currency(current_user.tenant_id)
    snap = (await folio_snapshots(db, current_user.tenant_id, [folio], fallback_currency=currency))[folio_id]
    booking = snap["booking"]
    guest = None
    if booking.get("guest_id"):
        from security.encrypted_lookup import decrypt_guest_doc

        guest = decrypt_guest_doc(await db.guests.find_one({"id": booking["guest_id"], "tenant_id": current_user.tenant_id}, {"_id": 0}))
    charges = [{**{key: row.get(key) for key in ("id", "category", "description", "amount", "tax_amount", "total", "currency")}, "date": iso_value(row.get("business_date") or row.get("created_at")),
                "quantity": row.get("quantity", 1), "unit_price": row.get("unit_price", row["total"]),
                "posted_by": row.get("posted_by")} for row in snap["charges"]]
    payments = [{**{key: row.get(key) for key in ("id", "amount", "currency", "payment_type", "notes")}, "date": iso_value(row.get("business_date") or row.get("payment_date") or row.get("date") or row.get("created_at")),
                 "payment_method": row.get("payment_method") or row.get("method"), "posted_by": row.get("created_by")} for row in snap["payments"]]
    charges.sort(key=lambda row: str(row["date"] or ""))
    payments.sort(key=lambda row: str(row["date"] or ""))
    return {"folio": {**{key: iso_value(folio.get(key)) for key in ("id", "folio_number", "folio_type", "status", "created_at", "closed_at")}, "currency": snap["currency"]},
            "booking": {key: iso_value(booking.get(key)) for key in ("id", "room_number", "check_in", "check_out")} if booking else None,
            "guest": {key: guest.get(key) for key in ("name", "email", "phone", "id_number")} if guest else ({"name": booking.get("guest_name")} if booking.get("guest_name") else None),
            "charges": charges, "payments": payments, "summary": {
                "total_charges": single_amount(snap["charges_by_currency"]), "total_payments": single_amount(snap["payments_by_currency"]),
                "current_balance": single_amount(snap["balance_by_currency"]), "charges_by_currency": snap["charges_by_currency"],
                "payments_by_currency": snap["payments_by_currency"], "balance_by_currency": snap["balance_by_currency"],
                "basis": "posted_folio_ledger", "charge_count": len(charges), "payment_count": len(payments)}}


@router.get("/finance/mobile/invoices")
async def get_invoices_mobile(
    start_date: str | None = None, end_date: str | None = None, unpaid_only: bool = False,
    department: str | None = None, credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_finance_reports")),
):
    current_user = await get_current_user(credentials)
    from core.tenant_currency import get_tenant_currency
    from routers.finance.accounting import _document_period

    query = {"tenant_id": current_user.tenant_id}
    if start_date or end_date:
        if not start_date or not end_date:
            raise HTTPException(422, "Başlangıç ve bitiş tarihi birlikte verilmelidir.")
        query.update(_document_period("created_at", start_date, end_date))
    raw = await db.accounting_invoices.find(query, {"_id": 0}).sort("created_at", -1).to_list(None)
    company_ids = list({i["company_id"] for i in raw if i.get("company_id")})
    companies = await db.companies.find({"tenant_id": current_user.tenant_id, "id": {"$in": company_ids}}, {"_id": 0}).to_list(None) if company_ids else []
    company_map = {c["id"]: c.get("name") for c in companies}
    currency, _ = await get_tenant_currency(current_user.tenant_id)
    invoices, totals, unpaid, paid = [], {}, {}, {}
    for invoice in raw:
        if str(invoice.get("status") or "").lower() in {"cancelled", "canceled", "void", "voided", "draft"} or invoice.get("voided"):
            continue
        remaining = outstanding_invoice(invoice)
        if unpaid_only and remaining <= 0:
            continue
        if department and not any(item.get("department") == department for item in invoice.get("items") or []):
            continue
        code = currency_code(invoice.get("currency"), currency)
        amount = float(invoice.get("total") or 0)
        add_amount(totals, code, amount)
        add_amount(unpaid, code, remaining)
        add_amount(paid, code, amount - remaining)
        invoices.append({**invoice, "created_at": iso_value(invoice.get("created_at")), "due_date": iso_value(invoice.get("due_date")),
                         "company_name": company_map.get(invoice.get("company_id")), "currency": code,
                         "outstanding_amount": remaining, "has_efatura": bool(invoice.get("efatura_uuid"))})
    return {"invoices": invoices, "currency": currency, "basis": "invoice_documents_not_cash_collections",
            "summary": {"total_count": len(invoices), "total_amount": single_amount(totals), "unpaid_amount": single_amount(unpaid),
                        "paid_amount": single_amount(paid), "totals_by_currency": rounded_totals(totals),
                        "unpaid_by_currency": rounded_totals(unpaid), "paid_by_currency": rounded_totals(paid)}}


@router.get("/finance/mobile/invoice-pdf/{invoice_id}")
async def get_invoice_pdf_mobile(
    invoice_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_finance_reports")),  # v102 DW finance leak fix
):
    """Generate and return invoice PDF (dynamic generation)"""
    current_user = await get_current_user(credentials)

    invoice = await db.accounting_invoices.find_one({"id": invoice_id, "tenant_id": current_user.tenant_id})

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # For MVP, return invoice data for frontend PDF generation
    # In production, use libraries like WeasyPrint or ReportLab for server-side PDF generation

    # Get company details if available
    company = None
    if invoice.get("company_id"):
        company = await db.companies.find_one({"id": invoice.get("company_id"), "tenant_id": current_user.tenant_id})

    # Get tenant details
    tenant = await db.tenants.find_one({"id": current_user.tenant_id})

    pdf_data = {
        "invoice": {
            "invoice_number": invoice.get("invoice_number"),
            "invoice_type": invoice.get("invoice_type"),
            "invoice_date": invoice.get("created_at").isoformat() if invoice.get("created_at") else None,
            "due_date": invoice.get("due_date"),
            "status": invoice.get("status"),
            "customer_name": invoice.get("customer_name"),
            "customer_tax_number": invoice.get("customer_tax_number"),
            "customer_address": invoice.get("customer_address"),
            "items": invoice.get("items", []),
            "subtotal": invoice.get("subtotal", 0),
            "vat": invoice.get("vat", 0),
            "vat_rate": invoice.get("vat_rate", 20),
            "total": invoice.get("total", 0),
            "currency": invoice.get("currency", "TRY"),
            "notes": invoice.get("notes"),
            "efatura_uuid": invoice.get("efatura_uuid"),
        },
        "company": {
            "name": company.get("name") if company else None,
            "tax_number": company.get("tax_number") if company else None,
            "billing_address": company.get("billing_address") if company else None,
        }
        if company
        else None,
        "hotel": {
            "name": tenant.get("hotel_name") if tenant else "Hotel PMS",
            "address": tenant.get("address") if tenant else "",
            "tax_number": tenant.get("tax_number") if tenant else "",
            "phone": tenant.get("phone") if tenant else "",
            "email": tenant.get("email") if tenant else "",
        },
        "generated_at": datetime.now(UTC).isoformat(),
        "pdf_ready": False,  # Flag for frontend to generate PDF
        "download_filename": f"Invoice_{invoice.get('invoice_number')}.pdf",
    }

    return pdf_data


@router.post("/finance/mobile/bank-balance-update")
async def update_bank_balance_mobile(
    bank_account_id: str,
    current_balance: float,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_finance_reports")),  # v92 DW
):
    """Manual bank balance update (for now, until API integration)"""
    current_user = await get_current_user(credentials)

    bank_account = await db.bank_accounts.find_one({"id": bank_account_id, "tenant_id": current_user.tenant_id})

    if not bank_account:
        raise HTTPException(status_code=404, detail="Bank account not found")

    await db.bank_accounts.update_one(
        {"id": bank_account_id, "tenant_id": current_user.tenant_id},
        {
            "$set": {
                "current_balance": current_balance,
                "available_balance": current_balance,  # Simplified for now
                "last_sync": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
            }
        },
    )

    return {"message": "Bank balance updated successfully", "bank_account_id": bank_account_id, "current_balance": current_balance}


@router.get("/finance/mobile/bank-balances")
async def get_bank_balances_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    _perm=Depends(require_op("view_finance_reports")),
):
    current_user = await get_current_user(credentials)
    from core.tenant_currency import get_tenant_currency

    currency, _ = await get_tenant_currency(current_user.tenant_id)
    accounts, totals = [], {}
    async for bank in db.bank_accounts.find({"tenant_id": current_user.tenant_id, "is_active": True}, {"_id": 0}):
        balance = bank.get("current_balance") if bank.get("current_balance") is not None else bank.get("balance")
        code = currency_code(bank.get("currency"), currency)
        if balance is not None:
            add_amount(totals, code, balance)
        accounts.append({**{key: bank.get(key) for key in ("id", "bank_name", "account_number", "iban", "account_type", "api_enabled")},
                         "currency": code, "current_balance": balance, "available_balance": bank.get("available_balance"),
                         "last_sync": iso_value(bank.get("last_sync"))})
    return {"bank_accounts": accounts, "total_balance_try": rounded_totals(totals).get("TRY", 0),
            "totals_by_currency": rounded_totals(totals), "account_count": len(accounts),
            "unavailable_balance_count": sum(a["current_balance"] is None for a in accounts), "basis": "stored_bank_snapshot_not_live_bank"}
