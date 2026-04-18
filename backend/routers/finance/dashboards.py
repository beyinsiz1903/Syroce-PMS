"""Auto-split from finance.py — section: dashboards."""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer

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

@router.get("/finance/expense-summary")
async def get_expense_summary(
    date: str | None = None,  # YYYY-MM-DD
    period: str = "today",  # today, week, month
    current_user: User = Depends(get_current_user)
):
    """
    Get expense summary with categories
    Categories: F&B costs, housekeeping, maintenance, staff, utilities, procurement
    """
    try:
        if date:
            target_date = datetime.fromisoformat(date).date()
        else:
            target_date = datetime.now(UTC).date()

        # Calculate date range
        if period == "today":
            start_date = target_date
            end_date = target_date
        elif period == "week":
            start_date = target_date - timedelta(days=7)
            end_date = target_date
        else:  # month
            start_date = target_date.replace(day=1)
            end_date = target_date

        # Sample expense data (in production, fetch from expenses collection)
        expenses = {
            'fnb_costs': {
                'amount': 15420.50,
                'category': 'F&B Maliyetleri',
                'breakdown': {
                    'food_purchases': 8500.00,
                    'beverages': 4200.50,
                    'supplies': 2720.00
                }
            },
            'housekeeping_expenses': {
                'amount': 8750.00,
                'category': 'Temizlik Giderleri',
                'breakdown': {
                    'cleaning_supplies': 3200.00,
                    'laundry': 4050.00,
                    'equipment': 1500.00
                }
            },
            'maintenance_costs': {
                'amount': 5600.00,
                'category': 'Teknik Maliyetler',
                'breakdown': {
                    'repairs': 3200.00,
                    'parts': 1800.00,
                    'preventive': 600.00
                }
            },
            'staff_costs': {
                'amount': 45800.00,
                'category': 'Personel Maliyetleri',
                'breakdown': {
                    'hourly_wages': 28500.00,
                    'overtime': 8200.00,
                    'benefits': 9100.00
                },
                'hourly_rate_avg': 85.50
            },
            'utilities': {
                'amount': 12300.00,
                'category': 'Enerji & Utilities',
                'breakdown': {
                    'electricity': 7200.00,
                    'water': 2800.00,
                    'gas': 2300.00
                }
            },
            'procurement': {
                'amount': 9850.00,
                'category': 'Satın Alma',
                'breakdown': {
                    'supplies': 5200.00,
                    'equipment': 3150.00,
                    'other': 1500.00
                }
            }
        }

        # Calculate totals
        total_expenses = sum(cat['amount'] for cat in expenses.values())

        # Calculate daily average for the period
        days_in_period = (end_date - start_date).days + 1
        daily_avg = total_expenses / days_in_period if days_in_period > 0 else 0

        return {
            'period': period,
            'start_date': start_date.isoformat(),
            'end_date': end_date.isoformat(),
            'total_expenses': round(total_expenses, 2),
            'daily_average': round(daily_avg, 2),
            'categories': expenses,
            'top_expense': max(expenses.items(), key=lambda x: x[1]['amount'])[1]['category']
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get expense summary: {str(e)}")



@router.get("/finance/cash-flow-dashboard")
async def get_cash_flow_dashboard(
    current_user: User = Depends(get_current_user)
):
    """
    Comprehensive cash flow dashboard for Finance Manager
    Shows: today's cash in/out, weekly plan, bank balances, risk alerts
    """
    try:
        today = datetime.now(UTC).date()
        today_str = today.isoformat()

        # Today's cash inflow (collections)
        today_checkins = await db.bookings.find({
            'check_in': today_str,
            'tenant_id': current_user.tenant_id
        }, {'_id': 0, 'total_amount': 1, 'paid_amount': 1}).to_list(200)

        today_collections = sum(b.get('paid_amount', 0) for b in today_checkins)

        # Today's cash outflow (expenses - sample data)
        today_expenses = {
            'staff_payments': 8500.00,
            'supplier_payments': 12300.00,
            'utility_bills': 3200.00,
            'other': 1500.00
        }
        today_outflow = sum(today_expenses.values())

        # Net cash flow
        net_cash_flow = today_collections - today_outflow

        # Weekly forecast (next 7 days)
        weekly_forecast = []
        for i in range(7):
            date = today + timedelta(days=i)
            date_str = date.isoformat()

            # Expected collections (check-ins + ongoing bookings)
            expected_checkins = await db.bookings.count_documents({
                'check_in': date_str,
                'tenant_id': current_user.tenant_id
            })

            expected_checkouts = await db.bookings.count_documents({
                'check_out': date_str,
                'tenant_id': current_user.tenant_id
            })

            # Simplified forecast
            expected_inflow = expected_checkins * 1500 + expected_checkouts * 500
            expected_outflow = 15000 if date.weekday() == 4 else 8000  # Friday = payroll

            weekly_forecast.append({
                'date': date_str,
                'day_name': date.strftime('%a'),
                'expected_inflow': round(expected_inflow, 2),
                'expected_outflow': round(expected_outflow, 2),
                'net': round(expected_inflow - expected_outflow, 2)
            })

        # Bank balances (sample - in production, integrate with bank API)
        bank_balances = [
            {'bank': 'Garanti BBVA', 'account': '****3421', 'balance': 285600.50, 'currency': 'TRY'},
            {'bank': 'İş Bankası', 'account': '****7832', 'balance': 142300.00, 'currency': 'TRY'},
            {'bank': 'Akbank', 'account': '****1259', 'balance': 95800.75, 'currency': 'TRY'}
        ]
        total_bank_balance = sum(b['balance'] for b in bank_balances)

        return {
            'today': {
                'date': today_str,
                'cash_inflow': round(today_collections, 2),
                'cash_outflow': round(today_outflow, 2),
                'net_cash_flow': round(net_cash_flow, 2),
                'outflow_breakdown': today_expenses
            },
            'weekly_forecast': weekly_forecast,
            'bank_balances': {
                'accounts': bank_balances,
                'total': round(total_bank_balance, 2)
            },
            'status': 'positive' if net_cash_flow > 0 else 'negative'
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get cash flow dashboard: {str(e)}")



@router.get("/finance/risk-alerts")
async def get_risk_alerts(
    current_user: User = Depends(get_current_user)
):
    """
    Financial risk monitoring: overdue accounts, credit limits, suspicious receivables
    """
    try:
        today = datetime.now(UTC).date()

        # Get all folios with outstanding balance
        folios = await db.folios.find({
            'tenant_id': current_user.tenant_id,
            'status': {'$in': ['open', 'closed']}
        }, {'_id': 0}).to_list(1000)

        overdue_accounts = []
        over_limit_accounts = []
        suspicious_accounts = []

        for folio in folios:
            outstanding = folio.get('total_amount', 0) - folio.get('paid_amount', 0)

            if outstanding > 0:
                # Get booking info
                booking = await db.bookings.find_one({'id': folio.get('booking_id')}, {'_id': 0})

                if booking:
                    # Calculate days overdue
                    checkout_date = datetime.fromisoformat(booking['check_out']).date()
                    days_overdue = (today - checkout_date).days

                    account_info = {
                        'folio_id': folio['id'],
                        'booking_id': booking['id'],
                        'guest_name': booking.get('guest_name'),
                        'room_number': booking.get('room_number'),
                        'outstanding_amount': round(outstanding, 2),
                        'checkout_date': booking['check_out'],
                        'days_overdue': days_overdue
                    }

                    # Risk Categories
                    if days_overdue > 7:
                        account_info['risk_level'] = 'high' if days_overdue > 30 else 'medium'
                        overdue_accounts.append(account_info)

                    # Credit limit check (sample: 10000 TL limit)
                    if outstanding > 10000:
                        account_info['risk_level'] = 'critical'
                        account_info['limit'] = 10000
                        over_limit_accounts.append(account_info)

                    # Suspicious accounts (multiple unpaid bookings or high amount)
                    if outstanding > 20000 or days_overdue > 60:
                        account_info['risk_level'] = 'critical'
                        account_info['reason'] = 'High amount' if outstanding > 20000 else 'Long overdue'
                        suspicious_accounts.append(account_info)

        # Sort by risk
        overdue_accounts.sort(key=lambda x: x['days_overdue'], reverse=True)
        over_limit_accounts.sort(key=lambda x: x['outstanding_amount'], reverse=True)
        suspicious_accounts.sort(key=lambda x: x['outstanding_amount'], reverse=True)

        # Calculate totals
        total_overdue_amount = sum(acc['outstanding_amount'] for acc in overdue_accounts)
        total_at_risk = sum(acc['outstanding_amount'] for acc in suspicious_accounts)

        # Create notifications for critical cases
        for acc in suspicious_accounts[:5]:  # Top 5 critical
            existing_notif = await db.notifications.find_one({
                'related_id': acc['folio_id'],
                'type': 'financial_risk',
                'tenant_id': current_user.tenant_id
            }, {'_id': 0})

            if not existing_notif:
                await db.notifications.insert_one({
                    'id': str(uuid.uuid4()),
                    'tenant_id': current_user.tenant_id,
                    'user_role': 'finance',
                    'title': f'🚨 Yüksek Riskli Hesap - {acc["guest_name"]}',
                    'message': f'₺{acc["outstanding_amount"]:,.2f} ödenmemiş bakiye',
                    'type': 'financial_risk',
                    'priority': 'urgent',
                    'related_id': acc['folio_id'],
                    'read': False,
                    'created_at': datetime.now(UTC).isoformat()
                })

        return {
            'overdue_accounts': overdue_accounts,
            'over_limit_accounts': over_limit_accounts,
            'suspicious_accounts': suspicious_accounts,
            'summary': {
                'total_overdue_count': len(overdue_accounts),
                'total_overdue_amount': round(total_overdue_amount, 2),
                'over_limit_count': len(over_limit_accounts),
                'suspicious_count': len(suspicious_accounts),
                'total_at_risk': round(total_at_risk, 2)
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get risk alerts: {str(e)}")



@router.get("/finance/folios-filtered")
@cached(ttl=300, key_prefix="finance_folios_filtered")  # Cache for 5 min
async def get_folios_filtered(
    customer_type: str | None = None,  # vip, corporate, individual
    room_number: str | None = None,
    status: str | None = None,  # open, closed, cancelled
    date_from: str | None = None,
    date_to: str | None = None,
    current_user: User = Depends(get_current_user)
):
    """
    Get filtered folios with customer type and room filters
    """
    try:
        filter_dict = {'tenant_id': current_user.tenant_id}

        if status:
            filter_dict['status'] = status

        folios = await db.folios.find(filter_dict, {'_id': 0}).sort('created_at', -1).limit(200).to_list(200)

        # Enrich with booking and guest data
        enriched_folios = []
        for folio in folios:
            if folio.get('booking_id'):
                booking = await db.bookings.find_one({'id': folio['booking_id']}, {'_id': 0})
                if booking:
                    folio['guest_name'] = booking.get('guest_name')
                    folio['room_number'] = booking.get('room_number')
                    folio['check_in'] = booking.get('check_in')
                    folio['check_out'] = booking.get('check_out')

                    # Get guest info for customer type
                    if booking.get('guest_id'):
                        guest = await db.guests.find_one({'id': booking['guest_id']}, {'_id': 0})
                        if guest:
                            folio['customer_type'] = guest.get('customer_type', 'individual')
                            folio['guest_email'] = guest.get('email')
                            folio['guest_phone'] = guest.get('phone')

            # Apply filters
            if customer_type and folio.get('customer_type') != customer_type:
                continue

            if room_number and folio.get('room_number') != room_number:
                continue

            if date_from and folio.get('check_in', '') < date_from:
                continue

            if date_to and folio.get('check_out', '') > date_to:
                continue

            enriched_folios.append(folio)

        return {
            'folios': enriched_folios,
            'count': len(enriched_folios),
            'filters': {
                'customer_type': customer_type,
                'room_number': room_number,
                'status': status,
                'date_from': date_from,
                'date_to': date_to
            }
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get filtered folios: {str(e)}")



@router.get("/finance/folio/{folio_id}/detail")
async def get_folio_detail(
    folio_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get complete folio details with all charges and payments
    """
    try:
        folio = await db.folios.find_one({
            'id': folio_id,
            'tenant_id': current_user.tenant_id
        }, {'_id': 0})

        if not folio:
            raise HTTPException(status_code=404, detail="Folio not found")

        # Get booking details
        if folio.get('booking_id'):
            booking = await db.bookings.find_one({'id': folio['booking_id']}, {'_id': 0})
            folio['booking'] = booking

        # Calculate outstanding
        folio['outstanding'] = folio.get('total_amount', 0) - folio.get('paid_amount', 0)

        return folio

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get folio detail: {str(e)}")



@router.post("/finance/mobile-payment")
async def process_mobile_payment(
    folio_id: str,
    amount: float,
    payment_method: str,  # cash, card, bank_transfer
    notes: str = "",
    current_user: User = Depends(get_current_user)
):
    """
    Process payment from mobile device
    """
    try:
        folio = await db.folios.find_one({
            'id': folio_id,
            'tenant_id': current_user.tenant_id
        }, {'_id': 0})

        if not folio:
            raise HTTPException(status_code=404, detail="Folio not found")

        # Create payment record
        payment_id = str(uuid.uuid4())
        payment = {
            'id': payment_id,
            'folio_id': folio_id,
            'amount': amount,
            'payment_method': payment_method,
            'notes': notes,
            'processed_by': current_user.id,
            'processed_by_name': current_user.name,
            'processed_at': datetime.now(UTC).isoformat(),
            'tenant_id': current_user.tenant_id
        }

        # Update folio
        new_paid_amount = folio.get('paid_amount', 0) + amount
        await db.folios.update_one(
            {'id': folio_id},
            {
                '$set': {
                    'paid_amount': new_paid_amount,
                    'updated_at': datetime.now(UTC).isoformat()
                },
                '$push': {'payments': payment}
            }
        )

        # Create audit log
        await db.audit_logs.insert_one({
            'id': str(uuid.uuid4()),
            'tenant_id': current_user.tenant_id,
            'user_id': current_user.id,
            'user_name': current_user.name,
            'user_role': current_user.role,
            'action': 'MOBILE_PAYMENT',
            'entity_type': 'folio',
            'entity_id': folio_id,
            'changes': {'amount': amount, 'method': payment_method},
            'timestamp': datetime.now(UTC).isoformat()
        })

        return {
            'message': 'Ödeme başarıyla işlendi',
            'payment_id': payment_id,
            'folio_id': folio_id,
            'amount': amount,
            'new_balance': round(folio.get('total_amount', 0) - new_paid_amount, 2)
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process payment: {str(e)}")





