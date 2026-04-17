"""Auto-split from finance.py — section: mobile."""
import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from enum import Enum
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, EmailStr, Field

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: F401
    from openpyxl.utils import get_column_letter  # noqa: F401
except ImportError:
    Workbook = None

from core.database import db
from core.helpers import create_audit_log, require_module
from core.security import get_current_user
from core.utils import calculate_folio_balance, excel_response
from models.enums import ChargeCategory, FolioOperationType, PaymentStatus
from models.schemas import (
    CashFlow, ChargeCreate, CityLedgerTransaction, ConvertCurrencyRequest,
    CreateCurrencyRateRequest, CreateMultiCurrencyInvoiceRequest, Folio,
    FolioCharge, FolioCreate, FolioOperation, FolioOperationCreate,
    GenerateInvoiceFromFolioRequest, Invoice, InvoiceCreate, Payment,
    PaymentCreate, User,
)
from modules.folio.services.folio_balance_read_service import FolioBalanceReadService
from modules.folio.services.open_folio_service import OpenFolioService
from shared_kernel.shadow_metrics import compare_folio_payloads, run_shadow_compare

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

class RecordPaymentRequest(BaseModel):
    folio_id: str
    amount: float
    payment_method: str
    notes: str | None = None


@router.get("/finance/mobile/daily-collections")
async def get_daily_collections_mobile(
    date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get daily collections for finance mobile dashboard"""
    current_user = await get_current_user(credentials)

    if date:
        target_date = datetime.fromisoformat(date)
    else:
        target_date = datetime.now(UTC)

    start_of_day = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)

    # Get payments for the day
    total_collected = 0.0
    payment_count = 0
    payment_methods = {}

    async for payment in db.payments.find({
        'tenant_id': current_user.tenant_id,
        'created_at': {
            '$gte': start_of_day,
            '$lte': end_of_day
        }
    }):
        amount = payment.get('amount', 0)
        total_collected += amount
        payment_count += 1

        method = payment.get('payment_method', 'unknown')
        payment_methods[method] = payment_methods.get(method, 0) + amount

    return {
        'date': target_date.date().isoformat(),
        'total_collected': total_collected,
        'payment_count': payment_count,
        'payment_methods': payment_methods,
        'average_transaction': total_collected / payment_count if payment_count > 0 else 0
    }



@router.get("/finance/mobile/monthly-collections")
async def get_monthly_collections_mobile(
    year: int | None = None,
    month: int | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get monthly collections for finance mobile dashboard"""
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC)
    target_year = year or today.year
    target_month = month or today.month

    # First day of month
    start_of_month = datetime(target_year, target_month, 1, tzinfo=UTC)

    # First day of next month
    if target_month == 12:
        end_of_month = datetime(target_year + 1, 1, 1, tzinfo=UTC)
    else:
        end_of_month = datetime(target_year, target_month + 1, 1, tzinfo=UTC)

    # Get payments for the month
    total_collected = 0.0
    payments_by_method = {}

    async for payment in db.payments.find({
        'tenant_id': current_user.tenant_id,
        'created_at': {'$gte': start_of_month.isoformat(), '$lt': end_of_month.isoformat()}
    }):
        amount = payment.get('amount', 0)
        total_collected += amount

        method = payment.get('payment_method', 'unknown')
        payments_by_method[method] = payments_by_method.get(method, 0) + amount

    return {
        'total_collected': round(total_collected, 2),
        'month': target_month,
        'year': target_year,
        'payments_by_method': {k: round(v, 2) for k, v in payments_by_method.items()},
        'currency': 'TRY'
    }



@router.get("/finance/profit-loss")
async def get_profit_loss_report_v2(
    start_date: str | None = None,
    end_date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get Profit & Loss (P&L) report"""
    await get_current_user(credentials)

    if not start_date:
        # Default to current month
        start_date = datetime.now(UTC).replace(day=1, hour=0, minute=0, second=0)
    else:
        start_date = datetime.fromisoformat(start_date)

    if not end_date:
        # End of current month
        if start_date.month == 12:
            end_date = datetime(start_date.year + 1, 1, 1, tzinfo=UTC) - timedelta(days=1)
        else:
            end_date = datetime(start_date.year, start_date.month + 1, 1, tzinfo=UTC) - timedelta(days=1)
    else:
        end_date = datetime.fromisoformat(end_date)

    # REVENUE
    # Room Revenue



@router.get("/finance/cashier-shift-report")
async def get_cashier_shift_report(
    shift_date: str | None = None,
    cashier_name: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get cashier shift report"""
    current_user = await get_current_user(credentials)

    if shift_date:
        target_date = datetime.fromisoformat(shift_date)
    else:
        target_date = datetime.now(UTC)

    start_of_day = target_date.replace(hour=0, minute=0, second=0)
    end_of_day = target_date.replace(hour=23, minute=59, second=59)

    query = {
        'tenant_id': current_user.tenant_id,
        'created_at': {'$gte': start_of_day, '$lte': end_of_day}
    }

    if cashier_name:
        query['created_by'] = cashier_name

    # Get all payments/transactions
    total_cash = 0
    total_card = 0
    total_transfer = 0
    total_other = 0
    transaction_count = 0

    async for payment in db.payments.find(query):
        amount = payment.get('amount', 0)
        method = payment.get('payment_method', 'cash')

        if method == 'cash':
            total_cash += amount
        elif method == 'card':
            total_card += amount
        elif method == 'transfer':
            total_transfer += amount
        else:
            total_other += amount

        transaction_count += 1

    total_collected = total_cash + total_card + total_transfer + total_other

    # Get opening and closing balance (if tracked)
    opening_balance = 0  # Should be from shift start record
    expected_closing = opening_balance + total_cash

    # Calculate variances
    variance = 0  # Would be: actual_closing - expected_closing

    return {
        'shift_date': target_date.date().isoformat(),
        'cashier_name': cashier_name or 'All Cashiers',
        'opening_balance': opening_balance,
        'collections': {
            'cash': total_cash,
            'card': total_card,
            'transfer': total_transfer,
            'other': total_other,
            'total': total_collected
        },
        'expected_closing_balance': expected_closing,
        'variance': variance,
        'transaction_count': transaction_count,
        'average_transaction': total_collected / transaction_count if transaction_count > 0 else 0,
        'generated_at': datetime.now(UTC).isoformat()
    }

    payment_count = 0

    async for payment in db.payments.find({
        'tenant_id': current_user.tenant_id,
        'created_at': {
            '$gte': start_of_month,
            '$lt': end_of_month
        }
    }):
        total_collected += payment.get('amount', 0)
        payment_count += 1

    # Calculate collection rate (collected vs expected)
    total_expected = 0.0
    async for booking in db.bookings.find({
        'tenant_id': current_user.tenant_id,
        'check_in': {
            '$gte': start_of_month,
            '$lt': end_of_month
        }
    }):
        total_expected += booking.get('total_amount', 0)

    collection_rate = (total_collected / total_expected * 100) if total_expected > 0 else 0

    return {
        'year': target_year,
        'month': target_month,
        'total_collected': total_collected,
        'payment_count': payment_count,
        'total_expected': total_expected,
        'collection_rate': collection_rate,
        'outstanding': total_expected - total_collected
    }



@router.get("/finance/mobile/pending-receivables")
async def get_pending_receivables_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get pending receivables for finance mobile dashboard"""
    current_user = await get_current_user(credentials)

    # Get all open folios with balance
    total_pending = 0.0
    overdue_amount = 0.0
    receivables = []

    today = datetime.now(UTC)

    open_folios = await db.folios.find({
        'tenant_id': current_user.tenant_id,
        'status': 'open',
        'balance': {'$gt': 0}
    }).to_list(length=None)

    # Batch-fetch all related bookings in one query
    booking_ids = [f.get('booking_id') for f in open_folios if f.get('booking_id')]
    bookings_by_id: dict = {}
    if booking_ids:
        async for b in db.bookings.find(
            {'id': {'$in': booking_ids}, 'tenant_id': current_user.tenant_id},
            {'_id': 0, 'id': 1, 'check_out': 1, 'guest_name': 1, 'room_number': 1},
        ):
            bookings_by_id[b['id']] = b

    for folio in open_folios:
        balance = folio.get('balance', 0)
        total_pending += balance

        # Get booking info from batch lookup
        booking = bookings_by_id.get(folio.get('booking_id'))

        is_overdue = False
        checkout_date_str = None

        if booking:
            checkout = booking.get('check_out')
            if checkout:
                try:
                    # Convert string to datetime for comparison
                    if isinstance(checkout, str):
                        checkout_dt = datetime.fromisoformat(checkout).replace(tzinfo=UTC)
                        checkout_date_str = checkout
                    else:
                        checkout_dt = checkout if checkout.tzinfo else checkout.replace(tzinfo=UTC)
                        checkout_date_str = checkout.isoformat()

                    if checkout_dt < today:
                        is_overdue = True
                        overdue_amount += balance
                except (ValueError, AttributeError):
                    pass

        receivables.append({
            'folio_id': folio.get('id'),
            'folio_number': folio.get('folio_number'),
            'guest_name': booking.get('guest_name') if booking else 'Unknown',
            'balance': balance,
            'is_overdue': is_overdue,
            'checkout_date': checkout_date_str,
            'created_at': folio.get('created_at').isoformat() if isinstance(folio.get('created_at'), datetime) else folio.get('created_at')
        })

    # Sort by amount (highest first)
    receivables.sort(key=lambda x: x['balance'], reverse=True)

    return {
        'total_pending': total_pending,
        'overdue_amount': overdue_amount,
        'receivables_count': len(receivables),
        'receivables': receivables[:20]  # Top 20
    }



@router.get("/finance/mobile/monthly-costs")
async def get_monthly_costs_mobile(
    year: int | None = None,
    month: int | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get monthly costs for finance mobile dashboard"""
    current_user = await get_current_user(credentials)

    today = datetime.now(UTC)
    target_year = year or today.year
    target_month = month or today.month

    # First day of month
    start_of_month = datetime(target_year, target_month, 1, tzinfo=UTC)

    # First day of next month
    if target_month == 12:
        end_of_month = datetime(target_year + 1, 1, 1, tzinfo=UTC)
    else:
        end_of_month = datetime(target_year, target_month + 1, 1, tzinfo=UTC)

    # Get expenses for the month
    total_costs = 0.0
    costs_by_category = {}

    async for expense in db.expenses.find({
        'tenant_id': current_user.tenant_id,
        'expense_date': {
            '$gte': start_of_month,
            '$lt': end_of_month
        }
    }):
        amount = expense.get('amount', 0)
        total_costs += amount

        category = expense.get('category', 'other')
        costs_by_category[category] = costs_by_category.get(category, 0) + amount

    return {
        'year': target_year,
        'month': target_month,
        'total_costs': total_costs,
        'costs_by_category': costs_by_category
    }



@router.post("/finance/mobile/record-payment")
async def record_payment_mobile(
    request: RecordPaymentRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Record a payment from finance mobile"""
    current_user = await get_current_user(credentials)
    folio_id = request.folio_id
    amount = request.amount
    payment_method = request.payment_method
    notes = request.notes

    # Validate folio
    folio = await db.folios.find_one({
        'id': folio_id,
        'tenant_id': current_user.tenant_id
    })

    if not folio:
        raise HTTPException(status_code=404, detail="Folio not found")

    # Create payment
    payment_id = str(uuid.uuid4())
    payment = {
        'id': payment_id,
        'tenant_id': current_user.tenant_id,
        'folio_id': folio_id,
        'booking_id': folio.get('booking_id'),
        'amount': amount,
        'payment_method': payment_method,
        'payment_type': 'final',
        'notes': notes,
        'created_at': datetime.now(UTC),
        'created_by': current_user.username
    }

    await db.payments.insert_one(payment)

    # Update folio balance
    new_balance = folio.get('balance', 0) - amount
    await db.folios.update_one(
        {'id': folio_id, 'tenant_id': current_user.tenant_id},
        {'$set': {'balance': new_balance}}
    )

    # Close folio if balance is zero
    if abs(new_balance) < 0.01:
        await db.folios.update_one(
            {'id': folio_id, 'tenant_id': current_user.tenant_id},
            {
                '$set': {
                    'status': 'closed',
                    'closed_at': datetime.now(UTC),
                    'closed_by': current_user.username
                }
            }
        )

    return {
        'message': 'Payment recorded successfully',
        'payment_id': payment_id,
        'folio_id': folio_id,
        'amount': amount,
        'new_balance': new_balance,
        'folio_closed': abs(new_balance) < 0.01
    }



@router.get("/finance/mobile/cash-flow-summary")
async def get_cash_flow_summary_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get cash flow summary for finance mobile dashboard
    - Today's cash inflow (tahsilat)
    - Today's cash outflow (gider)
    - Weekly collection/payment plan
    - Bank balance summaries
    """
    current_user = await get_current_user(credentials)
    today = datetime.now(UTC).date()
    start_of_day = datetime.combine(today, datetime.min.time()).replace(tzinfo=UTC)
    end_of_day = datetime.combine(today, datetime.max.time()).replace(tzinfo=UTC)

    # Today's cash inflow (payments received)
    today_inflow = 0.0
    inflow_count = 0
    async for payment in db.payments.find({
        'tenant_id': current_user.tenant_id,
        'created_at': {'$gte': start_of_day, '$lte': end_of_day}
    }):
        today_inflow += payment.get('amount', 0)
        inflow_count += 1

    # Today's cash outflow (expenses)
    today_outflow = 0.0
    outflow_count = 0
    async for expense in db.expenses.find({
        'tenant_id': current_user.tenant_id,
        'date': {'$gte': start_of_day, '$lte': end_of_day},
        'paid': True
    }):
        today_outflow += expense.get('amount', 0)
        outflow_count += 1

    # Net cash flow today
    net_flow = today_inflow - today_outflow

    # Weekly collection plan (next 7 days expected collections)
    weekly_plan = []
    for days_ahead in range(7):
        target_date = today + timedelta(days=days_ahead)

        # Expected checkouts (potential collections)
        expected_collections = 0.0
        checkout_count = 0
        async for booking in db.bookings.find({
            'tenant_id': current_user.tenant_id,
            'check_out': target_date.isoformat(),
            'status': {'$in': ['confirmed', 'guaranteed', 'checked_in']}
        }):
            # Get folio balance for this booking
            folio = await db.folios.find_one({
                'tenant_id': current_user.tenant_id,
                'booking_id': booking.get('id'),
                'status': 'open'
            })
            if folio:
                expected_collections += folio.get('balance', 0)
                checkout_count += 1

        # Expected payments from companies (due date)
        expected_payments = 0.0
        async for invoice in db.accounting_invoices.find({
            'tenant_id': current_user.tenant_id,
            'due_date': target_date.isoformat(),
            'status': 'pending'
        }):
            expected_payments += invoice.get('total', 0)

        weekly_plan.append({
            'date': target_date.isoformat(),
            'day_name': target_date.strftime('%A'),
            'expected_collections': expected_collections,
            'expected_payments': expected_payments,
            'checkout_count': checkout_count
        })

    # Bank balance summaries
    bank_balances = []
    async for bank in db.bank_accounts.find({
        'tenant_id': current_user.tenant_id,
        'is_active': True
    }):
        bank_balances.append({
            'bank_name': bank.get('bank_name'),
            'account_number': bank.get('account_number')[-4:],  # Last 4 digits
            'currency': bank.get('currency', 'TRY'),
            'current_balance': bank.get('current_balance', 0),
            'available_balance': bank.get('available_balance', 0),
            'last_sync': bank.get('last_sync').isoformat() if bank.get('last_sync') else None
        })

    total_bank_balance = sum(b['current_balance'] for b in bank_balances if b['currency'] == 'TRY')

    return {
        'today': {
            'date': today.isoformat(),
            'cash_inflow': today_inflow,
            'cash_outflow': today_outflow,
            'net_flow': net_flow,
            'inflow_count': inflow_count,
            'outflow_count': outflow_count
        },
        'weekly_plan': weekly_plan,
        'bank_balances': bank_balances,
        'total_bank_balance_try': total_bank_balance
    }



@router.get("/finance/mobile/overdue-accounts")
async def get_overdue_accounts_mobile(
    min_days: int = 7,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get accounts overdue by more than specified days (default 7)
    Returns with risk level classification:
    - Normal: 0-7 days
    - Warning: 8-14 days (Yellow)
    - Critical: 15-30 days (Red)
    - Suspicious: 30+ days (Black)
    """
    current_user = await get_current_user(credentials)
    today = datetime.now(UTC)

    overdue_accounts = []

    async for folio in db.folios.find({
        'tenant_id': current_user.tenant_id,
        'status': 'open',
        'balance': {'$gt': 0}
    }):
        booking = await db.bookings.find_one({
            'id': folio.get('booking_id'),
            'tenant_id': current_user.tenant_id
        })

        if booking:
            checkout = booking.get('check_out')
            if checkout:
                try:
                    if isinstance(checkout, str):
                        checkout_date = datetime.fromisoformat(checkout).replace(tzinfo=UTC)
                    else:
                        checkout_date = checkout if checkout.tzinfo else checkout.replace(tzinfo=UTC)

                    days_overdue = (today - checkout_date).days

                    if days_overdue >= min_days:
                        # Determine risk level
                        if days_overdue >= 30:
                            risk_level = RiskLevel.SUSPICIOUS
                            risk_color = "black"
                        elif days_overdue >= 15:
                            risk_level = RiskLevel.CRITICAL
                            risk_color = "red"
                        elif days_overdue >= 8:
                            risk_level = RiskLevel.WARNING
                            risk_color = "yellow"
                        else:
                            risk_level = RiskLevel.NORMAL
                            risk_color = "green"

                        guest = await db.guests.find_one({
                            'id': booking.get('guest_id'),
                            'tenant_id': current_user.tenant_id
                        })

                        overdue_accounts.append({
                            'folio_id': folio.get('id'),
                            'folio_number': folio.get('folio_number'),
                            'booking_id': booking.get('id'),
                            'guest_name': guest.get('name') if guest else 'Unknown',
                            'guest_email': guest.get('email') if guest else None,
                            'guest_phone': guest.get('phone') if guest else None,
                            'room_number': booking.get('room_number'),
                            'checkout_date': checkout_date.date().isoformat(),
                            'balance': folio.get('balance', 0),
                            'days_overdue': days_overdue,
                            'risk_level': risk_level.value,
                            'risk_color': risk_color
                        })
                except (ValueError, AttributeError):
                    pass

    # Sort by days overdue (most critical first)
    overdue_accounts.sort(key=lambda x: x['days_overdue'], reverse=True)

    # Summary statistics
    total_overdue = sum(acc['balance'] for acc in overdue_accounts)
    suspicious_count = len([a for a in overdue_accounts if a['risk_level'] == 'suspicious'])
    critical_count = len([a for a in overdue_accounts if a['risk_level'] == 'critical'])
    warning_count = len([a for a in overdue_accounts if a['risk_level'] == 'warning'])

    return {
        'overdue_accounts': overdue_accounts,
        'summary': {
            'total_count': len(overdue_accounts),
            'total_amount': total_overdue,
            'suspicious_count': suspicious_count,  # 30+ days
            'critical_count': critical_count,  # 15-30 days
            'warning_count': warning_count  # 8-14 days
        }
    }



@router.get("/finance/mobile/credit-limit-violations")
async def get_credit_limit_violations_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get companies exceeding their credit limits"""
    current_user = await get_current_user(credentials)

    violations = []

    async for credit_limit in db.credit_limits.find({
        'tenant_id': current_user.tenant_id
    }):
        company = await db.companies.find_one({
            'id': credit_limit.get('company_id'),
            'tenant_id': current_user.tenant_id
        })

        if not company:
            continue

        # Calculate current debt from open folios
        current_debt = 0.0
        async for folio in db.folios.find({
            'tenant_id': current_user.tenant_id,
            'company_id': credit_limit.get('company_id'),
            'status': 'open',
            'balance': {'$gt': 0}
        }):
            current_debt += folio.get('balance', 0)

        credit_limit_amount = credit_limit.get('credit_limit', 0)
        available_credit = credit_limit_amount - current_debt
        utilization_pct = (current_debt / credit_limit_amount * 100) if credit_limit_amount > 0 else 0

        # Check if exceeding limit
        if current_debt > credit_limit_amount:
            violations.append({
                'company_id': credit_limit.get('company_id'),
                'company_name': company.get('name'),
                'credit_limit': credit_limit_amount,
                'current_debt': current_debt,
                'over_limit_amount': current_debt - credit_limit_amount,
                'available_credit': available_credit,
                'utilization_percentage': utilization_pct,
                'payment_terms_days': credit_limit.get('payment_terms_days', 30),
                'contact_person': company.get('contact_person'),
                'contact_email': company.get('contact_email'),
                'contact_phone': company.get('contact_phone')
            })
        # Also include companies near limit (90%+)
        elif utilization_pct >= 90:
            violations.append({
                'company_id': credit_limit.get('company_id'),
                'company_name': company.get('name'),
                'credit_limit': credit_limit_amount,
                'current_debt': current_debt,
                'over_limit_amount': 0,
                'available_credit': available_credit,
                'utilization_percentage': utilization_pct,
                'payment_terms_days': credit_limit.get('payment_terms_days', 30),
                'contact_person': company.get('contact_person'),
                'contact_email': company.get('contact_email'),
                'contact_phone': company.get('contact_phone'),
                'warning': 'Near limit'
            })

    # Sort by over limit amount
    violations.sort(key=lambda x: x.get('over_limit_amount', 0), reverse=True)

    return {
        'violations': violations,
        'summary': {
            'total_count': len(violations),
            'over_limit_count': len([v for v in violations if v.get('over_limit_amount', 0) > 0]),
            'near_limit_count': len([v for v in violations if v.get('warning') == 'Near limit'])
        }
    }



@router.get("/finance/mobile/suspicious-receivables")
async def get_suspicious_receivables_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get suspicious receivables list (30+ days overdue + high amounts)"""
    current_user = await get_current_user(credentials)
    today = datetime.now(UTC)

    suspicious_list = []

    async for folio in db.folios.find({
        'tenant_id': current_user.tenant_id,
        'status': 'open',
        'balance': {'$gt': 1000}  # Only significant amounts
    }):
        booking = await db.bookings.find_one({
            'id': folio.get('booking_id'),
            'tenant_id': current_user.tenant_id
        })

        if booking:
            checkout = booking.get('check_out')
            if checkout:
                try:
                    if isinstance(checkout, str):
                        checkout_date = datetime.fromisoformat(checkout).replace(tzinfo=UTC)
                    else:
                        checkout_date = checkout if checkout.tzinfo else checkout.replace(tzinfo=UTC)

                    days_overdue = (today - checkout_date).days

                    # Suspicious criteria: 30+ days OR high amount with 15+ days
                    balance = folio.get('balance', 0)
                    is_suspicious = (days_overdue >= 30) or (days_overdue >= 15 and balance > 5000)

                    if is_suspicious:
                        guest = await db.guests.find_one({
                            'id': booking.get('guest_id'),
                            'tenant_id': current_user.tenant_id
                        })

                        # Get payment history
                        payment_count = await db.payments.count_documents({
                            'tenant_id': current_user.tenant_id,
                            'folio_id': folio.get('id')
                        })

                        suspicious_list.append({
                            'folio_id': folio.get('id'),
                            'folio_number': folio.get('folio_number'),
                            'guest_name': guest.get('name') if guest else 'Unknown',
                            'guest_email': guest.get('email') if guest else None,
                            'guest_phone': guest.get('phone') if guest else None,
                            'company_id': folio.get('company_id'),
                            'balance': balance,
                            'checkout_date': checkout_date.date().isoformat(),
                            'days_overdue': days_overdue,
                            'payment_history_count': payment_count,
                            'reason': '30+ days overdue' if days_overdue >= 30 else 'High amount + 15+ days overdue'
                        })
                except (ValueError, AttributeError):
                    pass

    # Sort by balance (highest first)
    suspicious_list.sort(key=lambda x: x['balance'], reverse=True)

    total_suspicious_amount = sum(s['balance'] for s in suspicious_list)

    return {
        'suspicious_receivables': suspicious_list,
        'summary': {
            'total_count': len(suspicious_list),
            'total_amount': total_suspicious_amount,
            'average_days_overdue': sum(s['days_overdue'] for s in suspicious_list) / len(suspicious_list) if suspicious_list else 0
        }
    }



@router.get("/finance/mobile/risk-alerts")
async def get_risk_alerts_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get comprehensive risk alerts for finance dashboard"""
    current_user = await get_current_user(credentials)

    alerts = []

    # Get overdue accounts (7+ days)
    overdue_response = await get_overdue_accounts_mobile(min_days=7, credentials=credentials)
    overdue_summary = overdue_response['summary']

    if overdue_summary['suspicious_count'] > 0:
        alerts.append({
            'id': str(uuid.uuid4()),
            'type': 'suspicious_receivables',
            'severity': 'critical',
            'title': 'Şüpheli Alacaklar',
            'message': f"{overdue_summary['suspicious_count']} adet 30+ gün gecikmiş alacak",
            'amount': sum(a['balance'] for a in overdue_response['overdue_accounts'] if a['risk_level'] == 'suspicious'),
            'action_required': True
        })

    if overdue_summary['critical_count'] > 0:
        alerts.append({
            'id': str(uuid.uuid4()),
            'type': 'critical_overdue',
            'severity': 'high',
            'title': 'Kritik Gecikmiş Ödemeler',
            'message': f"{overdue_summary['critical_count']} adet 15+ gün gecikmiş ödeme",
            'amount': sum(a['balance'] for a in overdue_response['overdue_accounts'] if a['risk_level'] == 'critical'),
            'action_required': True
        })

    # Get credit limit violations
    violations_response = await get_credit_limit_violations_mobile(credentials=credentials)
    violations_summary = violations_response['summary']

    if violations_summary['over_limit_count'] > 0:
        alerts.append({
            'id': str(uuid.uuid4()),
            'type': 'credit_limit_violation',
            'severity': 'critical',
            'title': 'Kredi Limiti Aşımı',
            'message': f"{violations_summary['over_limit_count']} firma limiti aştı",
            'action_required': True
        })

    if violations_summary['near_limit_count'] > 0:
        alerts.append({
            'id': str(uuid.uuid4()),
            'type': 'near_credit_limit',
            'severity': 'medium',
            'title': 'Limite Yaklaşan Firmalar',
            'message': f"{violations_summary['near_limit_count']} firma limitin %90'ına ulaştı",
            'action_required': False
        })

    # Check for large unpaid invoices
    large_unpaid = 0
    large_unpaid_amount = 0.0
    async for invoice in db.accounting_invoices.find({
        'tenant_id': current_user.tenant_id,
        'status': 'pending',
        'total': {'$gt': 10000}
    }):
        large_unpaid += 1
        large_unpaid_amount += invoice.get('total', 0)

    if large_unpaid > 0:
        alerts.append({
            'id': str(uuid.uuid4()),
            'type': 'large_unpaid_invoices',
            'severity': 'medium',
            'title': 'Büyük Ödenmemiş Faturalar',
            'message': f"{large_unpaid} adet büyük fatura ödenmedi (>₺10,000)",
            'amount': large_unpaid_amount,
            'action_required': False
        })

    # Sort by severity
    severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}
    alerts.sort(key=lambda x: severity_order.get(x['severity'], 999))

    return {
        'alerts': alerts,
        'summary': {
            'total_alerts': len(alerts),
            'critical_count': len([a for a in alerts if a['severity'] == 'critical']),
            'high_count': len([a for a in alerts if a['severity'] == 'high']),
            'action_required_count': len([a for a in alerts if a.get('action_required')])
        }
    }



@router.get("/finance/mobile/daily-expenses")
async def get_daily_expenses_mobile(
    date: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get daily expense/cost summary"""
    current_user = await get_current_user(credentials)

    if date:
        target_date = datetime.fromisoformat(date).date()
    else:
        target_date = datetime.now(UTC).date()

    start_of_day = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=UTC)
    end_of_day = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=UTC)

    # Get expenses by category
    expenses_by_category = {}
    expenses_by_department = {}
    total_expenses = 0.0
    expense_count = 0

    async for expense in db.expenses.find({
        'tenant_id': current_user.tenant_id,
        'date': {'$gte': start_of_day, '$lte': end_of_day}
    }):
        amount = expense.get('amount', 0)
        category = expense.get('category', 'Other')
        department = expense.get('department', 'other')

        total_expenses += amount
        expense_count += 1

        expenses_by_category[category] = expenses_by_category.get(category, 0) + amount
        expenses_by_department[department] = expenses_by_department.get(department, 0) + amount

    return {
        'date': target_date.isoformat(),
        'total_expenses': total_expenses,
        'expense_count': expense_count,
        'expenses_by_category': expenses_by_category,
        'expenses_by_department': expenses_by_department
    }



@router.get("/finance/mobile/folio-full-extract/{folio_id}")
async def get_folio_full_extract_mobile(
    folio_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get full folio extract with all charges and payments"""
    current_user = await get_current_user(credentials)

    folio = await db.folios.find_one({
        'id': folio_id,
        'tenant_id': current_user.tenant_id
    })

    if not folio:
        raise HTTPException(status_code=404, detail="Folio not found")

    # Get booking details
    booking = await db.bookings.find_one({
        'id': folio.get('booking_id'),
        'tenant_id': current_user.tenant_id
    })

    # Get guest details
    guest = None
    if booking:
        guest = await db.guests.find_one({
            'id': booking.get('guest_id'),
            'tenant_id': current_user.tenant_id
        })

    # Get all charges
    charges = []
    total_charges = 0.0
    async for charge in db.folio_charges.find({
        'folio_id': folio_id,
        'tenant_id': current_user.tenant_id,
        'voided': {'$ne': True}
    }).sort('created_at', 1):
        charge_amount = charge.get('total', 0)
        total_charges += charge_amount
        charges.append({
            'id': charge.get('id'),
            'date': charge.get('created_at').isoformat() if charge.get('created_at') else None,
            'category': charge.get('category'),
            'description': charge.get('description'),
            'quantity': charge.get('quantity', 1),
            'unit_price': charge.get('unit_price', 0),
            'amount': charge.get('amount', 0),
            'tax_amount': charge.get('tax_amount', 0),
            'total': charge_amount,
            'posted_by': charge.get('posted_by')
        })

    # Get all payments
    payments = []
    total_payments = 0.0
    async for payment in db.payments.find({
        'folio_id': folio_id,
        'tenant_id': current_user.tenant_id
    }).sort('created_at', 1):
        payment_amount = payment.get('amount', 0)
        total_payments += payment_amount
        payments.append({
            'id': payment.get('id'),
            'date': payment.get('created_at').isoformat() if payment.get('created_at') else None,
            'amount': payment_amount,
            'payment_method': payment.get('payment_method'),
            'payment_type': payment.get('payment_type'),
            'notes': payment.get('notes'),
            'posted_by': payment.get('created_by')
        })

    current_balance = total_charges - total_payments

    return {
        'folio': {
            'id': folio.get('id'),
            'folio_number': folio.get('folio_number'),
            'folio_type': folio.get('folio_type'),
            'status': folio.get('status'),
            'created_at': folio.get('created_at').isoformat() if folio.get('created_at') else None,
            'closed_at': folio.get('closed_at').isoformat() if folio.get('closed_at') else None
        },
        'guest': {
            'name': guest.get('name') if guest else 'Unknown',
            'email': guest.get('email') if guest else None,
            'phone': guest.get('phone') if guest else None,
            'id_number': guest.get('id_number') if guest else None
        } if guest else None,
        'booking': {
            'id': booking.get('id') if booking else None,
            'room_number': booking.get('room_number') if booking else None,
            'check_in': booking.get('check_in') if booking else None,
            'check_out': booking.get('check_out') if booking else None
        } if booking else None,
        'charges': charges,
        'payments': payments,
        'summary': {
            'total_charges': total_charges,
            'total_payments': total_payments,
            'current_balance': current_balance,
            'charge_count': len(charges),
            'payment_count': len(payments)
        }
    }



@router.get("/finance/mobile/invoices")
async def get_invoices_mobile(
    start_date: str | None = None,
    end_date: str | None = None,
    unpaid_only: bool = False,
    department: str | None = None,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get invoices with advanced filtering (date, unpaid, department)"""
    current_user = await get_current_user(credentials)

    query = {'tenant_id': current_user.tenant_id}

    # Date filter
    if start_date or end_date:
        date_filter = {}
        if start_date:
            date_filter['$gte'] = datetime.fromisoformat(start_date)
        if end_date:
            date_filter['$lte'] = datetime.fromisoformat(end_date)
        query['created_at'] = date_filter

    # Unpaid filter
    if unpaid_only:
        query['status'] = 'pending'

    # Department filter - will need to check items
    invoices = []
    total_amount = 0.0
    unpaid_amount = 0.0

    async for invoice in db.accounting_invoices.find(query).sort('created_at', -1).limit(100):
        # If department filter is specified, check invoice items
        if department:
            items = invoice.get('items', [])
            has_department = any(item.get('department') == department for item in items)
            if not has_department:
                continue

        invoice_total = invoice.get('total', 0)
        total_amount += invoice_total

        if invoice.get('status') == 'pending':
            unpaid_amount += invoice_total

        # Get company details if available
        company_name = None
        if invoice.get('company_id'):
            company = await db.companies.find_one({
                'id': invoice.get('company_id'),
                'tenant_id': current_user.tenant_id
            })
            if company:
                company_name = company.get('name')

        invoices.append({
            'id': invoice.get('id'),
            'invoice_number': invoice.get('invoice_number'),
            'invoice_type': invoice.get('invoice_type'),
            'status': invoice.get('status'),
            'customer_name': invoice.get('customer_name'),
            'company_name': company_name,
            'created_at': invoice.get('created_at').isoformat() if invoice.get('created_at') else None,
            'due_date': invoice.get('due_date'),
            'subtotal': invoice.get('subtotal', 0),
            'vat': invoice.get('vat', 0),
            'total': invoice_total,
            'currency': invoice.get('currency', 'TRY'),
            'has_efatura': invoice.get('efatura_uuid') is not None
        })

    return {
        'invoices': invoices,
        'summary': {
            'total_count': len(invoices),
            'total_amount': total_amount,
            'unpaid_amount': unpaid_amount,
            'paid_amount': total_amount - unpaid_amount
        }
    }



@router.get("/finance/mobile/invoice-pdf/{invoice_id}")
async def get_invoice_pdf_mobile(
    invoice_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Generate and return invoice PDF (dynamic generation)"""
    current_user = await get_current_user(credentials)

    invoice = await db.accounting_invoices.find_one({
        'id': invoice_id,
        'tenant_id': current_user.tenant_id
    })

    if not invoice:
        raise HTTPException(status_code=404, detail="Invoice not found")

    # For MVP, return invoice data for frontend PDF generation
    # In production, use libraries like WeasyPrint or ReportLab for server-side PDF generation

    # Get company details if available
    company = None
    if invoice.get('company_id'):
        company = await db.companies.find_one({
            'id': invoice.get('company_id'),
            'tenant_id': current_user.tenant_id
        })

    # Get tenant details
    tenant = await db.tenants.find_one({'id': current_user.tenant_id})

    pdf_data = {
        'invoice': {
            'invoice_number': invoice.get('invoice_number'),
            'invoice_type': invoice.get('invoice_type'),
            'invoice_date': invoice.get('created_at').isoformat() if invoice.get('created_at') else None,
            'due_date': invoice.get('due_date'),
            'status': invoice.get('status'),
            'customer_name': invoice.get('customer_name'),
            'customer_tax_number': invoice.get('customer_tax_number'),
            'customer_address': invoice.get('customer_address'),
            'items': invoice.get('items', []),
            'subtotal': invoice.get('subtotal', 0),
            'vat': invoice.get('vat', 0),
            'vat_rate': invoice.get('vat_rate', 20),
            'total': invoice.get('total', 0),
            'currency': invoice.get('currency', 'TRY'),
            'notes': invoice.get('notes'),
            'efatura_uuid': invoice.get('efatura_uuid')
        },
        'company': {
            'name': company.get('name') if company else None,
            'tax_number': company.get('tax_number') if company else None,
            'billing_address': company.get('billing_address') if company else None
        } if company else None,
        'hotel': {
            'name': tenant.get('hotel_name') if tenant else 'Hotel PMS',
            'address': tenant.get('address') if tenant else '',
            'tax_number': tenant.get('tax_number') if tenant else '',
            'phone': tenant.get('phone') if tenant else '',
            'email': tenant.get('email') if tenant else ''
        },
        'generated_at': datetime.now(UTC).isoformat(),
        'pdf_ready': False,  # Flag for frontend to generate PDF
        'download_filename': f"Invoice_{invoice.get('invoice_number')}.pdf"
    }

    return pdf_data



@router.post("/finance/mobile/bank-balance-update")
async def update_bank_balance_mobile(
    bank_account_id: str,
    current_balance: float,
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Manual bank balance update (for now, until API integration)"""
    current_user = await get_current_user(credentials)

    bank_account = await db.bank_accounts.find_one({
        'id': bank_account_id,
        'tenant_id': current_user.tenant_id
    })

    if not bank_account:
        raise HTTPException(status_code=404, detail="Bank account not found")

    await db.bank_accounts.update_one(
        {'id': bank_account_id, 'tenant_id': current_user.tenant_id},
        {
            '$set': {
                'current_balance': current_balance,
                'available_balance': current_balance,  # Simplified for now
                'last_sync': datetime.now(UTC),
                'updated_at': datetime.now(UTC)
            }
        }
    )

    return {
        'message': 'Bank balance updated successfully',
        'bank_account_id': bank_account_id,
        'current_balance': current_balance
    }



@router.get("/finance/mobile/bank-balances")
async def get_bank_balances_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get all bank account balances"""
    current_user = await get_current_user(credentials)

    bank_accounts = []
    total_balance_try = 0.0

    async for bank in db.bank_accounts.find({
        'tenant_id': current_user.tenant_id,
        'is_active': True
    }):
        balance = bank.get('current_balance', 0)
        bank_accounts.append({
            'id': bank.get('id'),
            'bank_name': bank.get('bank_name'),
            'account_number': bank.get('account_number'),
            'iban': bank.get('iban'),
            'currency': bank.get('currency', 'TRY'),
            'current_balance': balance,
            'available_balance': bank.get('available_balance', 0),
            'account_type': bank.get('account_type', 'checking'),
            'api_enabled': bank.get('api_enabled', False),
            'last_sync': bank.get('last_sync').isoformat() if bank.get('last_sync') else None
        })

        if bank.get('currency') == 'TRY':
            total_balance_try += balance

    return {
        'bank_accounts': bank_accounts,
        'total_balance_try': total_balance_try,
        'account_count': len(bank_accounts)
    }







