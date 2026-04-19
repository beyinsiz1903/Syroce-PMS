"""Auto-split from finance.py — section: folio."""
import logging

logger = logging.getLogger(__name__)
import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side  # noqa: F401
    from openpyxl.utils import get_column_letter  # noqa: F401
except ImportError:
    Workbook = None

from core.database import db
from core.helpers import create_audit_log
from core.security import get_current_user
from core.utils import calculate_folio_balance, excel_response
from models.enums import ChargeCategory, FolioOperationType
from models.schemas import (
    ChargeCreate,
    Folio,
    FolioCharge,
    FolioCreate,
    FolioOperation,
    FolioOperationCreate,
    Payment,
    PaymentCreate,
    User,
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

@router.post("/folio/create", response_model=Folio)
async def create_folio(
    folio_data: FolioCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Create a new folio for a booking"""
    return await open_folio_service.create(folio_data, current_user, request)




@router.get("/folio/list")
async def list_folios(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user)
):
    """List all folios for the current tenant with optional status filter."""
    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status

    # Sprint 33: parallelize list + count, then BATCH-fetch bookings via $in
    # (was N+1 — one find_one per folio causing 6.6s on 50 rows).
    import asyncio as _asyncio
    folios_q = db.folios.find(query, {'_id': 0}).sort(
        'created_at', -1
    ).skip(offset).limit(limit).to_list(limit)
    total_q = db.folios.count_documents(query)
    folios, total = await _asyncio.gather(folios_q, total_q)

    booking_ids = [f.get('booking_id') for f in folios if f.get('booking_id')]
    booking_map = {}
    if booking_ids:
        bookings = await db.bookings.find(
            {'id': {'$in': booking_ids}, 'tenant_id': current_user.tenant_id},
            {'_id': 0, 'id': 1, 'guest_name': 1, 'room_number': 1,
             'room_id': 1, 'check_in': 1, 'check_out': 1}
        ).to_list(len(booking_ids))
        booking_map = {b['id']: b for b in bookings}

    for folio in folios:
        booking = booking_map.get(folio.get('booking_id'))
        if booking:
            folio['guest_name'] = booking.get('guest_name', '')
            folio['room_number'] = booking.get('room_number', '')
            folio['check_in'] = booking.get('check_in', '')
            folio['check_out'] = booking.get('check_out', '')

    return {
        'folios': folios,
        'total': total,
        'limit': limit,
        'offset': offset,
    }


@router.get("/folio/dashboard-stats")
@cached(ttl=300, key_prefix="folio_dashboard_stats")  # Cache for 5 minutes
async def get_folio_dashboard_stats(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get folio statistics for dashboard"""
    current_user = await get_current_user(credentials)

    try:
        # Get all open folios
        open_folios = await db.folios.find({
            'tenant_id': current_user.tenant_id,
            'status': 'open'
        }, {'_id': 0}).to_list(1000)

        # Calculate total outstanding balance from folio balance field
        total_outstanding = 0.0
        for folio in open_folios:
            # Use the balance field directly instead of calculating
            total_outstanding += folio.get('balance', 0)

        # Get recent charges (last 24 hours)
        yesterday = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        recent_charges = await db.folio_charges.count_documents({
            'tenant_id': current_user.tenant_id,
            'date': {'$gte': yesterday},
            'voided': False
        })

        # Get recent payments (last 24 hours)
        recent_payments = await db.payments.count_documents({
            'tenant_id': current_user.tenant_id,
            'date': {'$gte': yesterday}
        })

        return {
            'total_open_folios': len(open_folios),
            'total_outstanding_balance': round(total_outstanding, 2),
            'recent_charges_24h': recent_charges,
            'recent_payments_24h': recent_payments
        }
    except Exception as e:
        logger.info(f"Error in folio dashboard stats: {str(e)}")
        import traceback
        traceback.print_exc()
        # Return default values instead of raising
        return {
            'total_open_folios': 0,
            'total_outstanding_balance': 0.0,
            'recent_charges_24h': 0,
            'recent_payments_24h': 0
        }


@router.get("/folio/pending-ar")
@cached(ttl=600, key_prefix="folio_pending_ar")  # Cache for 10 min
async def get_pending_ar(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get pending accounts receivable (company folios with outstanding balances)"""
    current_user = await get_current_user(credentials)

    try:
        # Get all companies
        companies = await db.companies.find({
            'tenant_id': current_user.tenant_id
        }, {'_id': 0}).to_list(1000)

        ar_data = []

        for company in companies:
            # Get company's open folios with balance
            company_folios = await db.folios.find({
                'tenant_id': current_user.tenant_id,
                'company_id': company['id'],
                'status': 'open'
            }, {'_id': 0}).to_list(1000)

            # Use balance field directly
            folios_with_balance = [f for f in company_folios if f.get('balance', 0) > 0]
            total_outstanding = sum(f.get('balance', 0) for f in folios_with_balance)

            if total_outstanding > 0 and folios_with_balance:
                # Find oldest folio
                oldest_folio = min(folios_with_balance, key=lambda f: f.get('created_at', datetime.now(UTC).isoformat()))
                oldest_date = datetime.fromisoformat(oldest_folio['created_at'].replace('Z', '+00:00'))
                days_outstanding = (datetime.now(UTC) - oldest_date).days

                # Calculate aging
                aging = {'0-7': 0, '8-14': 0, '15-30': 0, '30+': 0}
                for folio in folios_with_balance:
                    days = (datetime.now(UTC) - datetime.fromisoformat(folio['created_at'].replace('Z', '+00:00'))).days
                    balance = folio.get('balance', 0)
                    if days <= 7:
                        aging['0-7'] += balance
                    elif days <= 14:
                        aging['8-14'] += balance
                    elif days <= 30:
                        aging['15-30'] += balance
                    else:
                        aging['30+'] += balance

                ar_data.append({
                    'company_id': company['id'],
                    'company_name': company.get('name', 'Unknown'),
                    'corporate_code': company.get('corporate_code', ''),
                    'contact_person': company.get('contact_person', ''),
                    'contact_email': company.get('contact_email', ''),
                    'contact_phone': company.get('contact_phone', ''),
                    'payment_terms': company.get('payment_terms', 'Net 30'),
                    'total_outstanding': round(total_outstanding, 2),
                    'open_folios_count': len(folios_with_balance),
                    'oldest_invoice_date': oldest_folio['created_at'],
                    'days_outstanding': days_outstanding,
                    'aging': aging
                })

        # Sort by days outstanding (oldest first)
        ar_data.sort(key=lambda x: x['days_outstanding'], reverse=True)

        return ar_data

    except Exception as e:
        logger.info(f"Error in get_pending_ar: {str(e)}")
        import traceback
        traceback.print_exc()
        return []


@router.get("/folio/booking/{booking_id}", response_model=list[Folio])
@cached(ttl=180, key_prefix="folio_by_booking")  # Cache for 3 min
async def get_booking_folios(booking_id: str, current_user: User = Depends(get_current_user)):
    """Get all folios for a booking"""
    folios = await db.folios.find({
        'booking_id': booking_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).to_list(1000)

    # Calculate current balance for each folio
    for folio in folios:
        folio['balance'] = await calculate_folio_balance(folio['id'], current_user.tenant_id)

    return folios


@router.get("/folio/{folio_id}", response_model=dict[str, Any])
@cached(ttl=180, key_prefix="folio_details")  # Cache for 3 min
async def get_folio_details(
    folio_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Get folio with charges and payments"""
    semantic_response = await folio_balance_read_service.get_folio_details(
        tenant_id=current_user.tenant_id,
        folio_id=folio_id,
    )
    asyncio.create_task(
        run_shadow_compare(
            endpoint="folio",
            tenant_id=current_user.tenant_id,
            property_id=request.headers.get("x-property-id"),
            correlation_id=request.headers.get("x-correlation-id"),
            semantic_payload=semantic_response,
            legacy_loader=lambda: _legacy_get_folio_details(
                tenant_id=current_user.tenant_id,
                folio_id=folio_id,
            ),
            comparator=compare_folio_payloads,
            entity_id=folio_id,
        )
    )
    return semantic_response


async def _legacy_get_folio_details(tenant_id: str, folio_id: str):
    folio = await db.folios.find_one({
        'id': folio_id,
        'tenant_id': tenant_id
    }, {'_id': 0})

    if not folio:
        raise HTTPException(status_code=404, detail="Folio not found")

    charges = await db.folio_charges.find({
        'folio_id': folio_id,
        'tenant_id': tenant_id
    }, {'_id': 0}).to_list(1000)

    payments = await db.payments.find({
        'folio_id': folio_id,
        'tenant_id': tenant_id
    }, {'_id': 0}).to_list(1000)

    balance = await calculate_folio_balance(folio_id, tenant_id)
    folio['balance'] = balance

    return {
        'folio': folio,
        'charges': charges,
        'payments': payments,
        'balance': balance
    }



@router.get("/folio/{folio_id}/excel")
@cached(ttl=600, key_prefix="folio_excel")  # Cache for 10 min
async def export_folio_excel(folio_id: str, current_user: User = Depends(get_current_user)):
    """Export Folio to Excel"""
    folio_data = await get_folio_details(folio_id, current_user)

    folio = folio_data['folio']
    charges = folio_data['charges']
    payments = folio_data['payments']
    balance = folio_data['balance']

    wb = Workbook()
    ws = wb.active
    ws.title = "Folio"

    # Folio header
    ws['A1'] = "GUEST FOLIO"
    ws['A1'].font = Font(size=16, bold=True)
    ws.merge_cells('A1:E1')

    ws['A3'] = "Folio Number:"
    ws['B3'] = folio.get('folio_number', 'N/A')
    ws['A4'] = "Type:"
    ws['B4'] = folio.get('folio_type', 'guest').title()
    ws['A5'] = "Status:"
    ws['B5'] = folio.get('status', 'open').upper()
    ws['A6'] = "Created:"
    ws['B6'] = folio.get('created_at', '')[:10]

    # Charges section
    ws['A9'] = "CHARGES"
    ws['A9'].font = Font(size=14, bold=True)

    charge_headers = ["Date", "Description", "Qty", "Amount", "Tax", "Total"]
    for col_num, header in enumerate(charge_headers, 1):
        cell = ws.cell(row=10, column=col_num)
        cell.value = header
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        cell.font = Font(bold=True, color="FFFFFF")

    row = 11
    total_charges = 0
    for charge in charges:
        if not charge.get('voided', False):
            ws.cell(row=row, column=1, value=charge.get('posted_at', '')[:10])
            ws.cell(row=row, column=2, value=charge.get('description', ''))
            ws.cell(row=row, column=3, value=charge.get('quantity', 1))
            ws.cell(row=row, column=4, value=f"${charge.get('amount', 0):,.2f}")
            ws.cell(row=row, column=5, value=f"${charge.get('tax_amount', 0):,.2f}")
            ws.cell(row=row, column=6, value=f"${charge.get('total', 0):,.2f}")
            total_charges += charge.get('total', 0)
            row += 1

    ws.cell(row=row, column=5, value="Total Charges:")
    ws.cell(row=row, column=5).font = Font(bold=True)
    ws.cell(row=row, column=6, value=f"${total_charges:,.2f}")
    ws.cell(row=row, column=6).font = Font(bold=True)

    # Payments section
    row += 2
    ws.cell(row=row, column=1, value="PAYMENTS")
    ws.cell(row=row, column=1).font = Font(size=14, bold=True)
    row += 1

    payment_headers = ["Date", "Method", "Type", "Amount"]
    for col_num, header in enumerate(payment_headers, 1):
        cell = ws.cell(row=row, column=col_num)
        cell.value = header
        cell.font = Font(bold=True)
        cell.fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        cell.font = Font(bold=True, color="FFFFFF")

    row += 1
    total_payments = 0
    for payment in payments:
        ws.cell(row=row, column=1, value=payment.get('processed_at', '')[:10])
        ws.cell(row=row, column=2, value=payment.get('payment_method', '').title())
        ws.cell(row=row, column=3, value=payment.get('payment_type', '').title())
        ws.cell(row=row, column=4, value=f"${payment.get('amount', 0):,.2f}")
        total_payments += payment.get('amount', 0)
        row += 1

    ws.cell(row=row, column=3, value="Total Payments:")
    ws.cell(row=row, column=3).font = Font(bold=True)
    ws.cell(row=row, column=4, value=f"${total_payments:,.2f}")
    ws.cell(row=row, column=4).font = Font(bold=True)

    # Balance
    row += 2
    ws.cell(row=row, column=5, value="BALANCE DUE:")
    ws.cell(row=row, column=5).font = Font(size=14, bold=True)
    ws.cell(row=row, column=6, value=f"${balance:,.2f}")
    ws.cell(row=row, column=6).font = Font(size=14, bold=True)
    ws.cell(row=row, column=6).fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")

    filename = f"folio_{folio.get('folio_number', folio_id)}.xlsx"
    return excel_response(wb, filename)



@router.post("/folio/{folio_id}/charge", response_model=FolioCharge)
async def post_charge_to_folio(
    folio_id: str,
    charge_data: ChargeCreate,
    current_user: User = Depends(get_current_user)
):
    """Post a charge to folio"""
    folio = await db.folios.find_one({
        'id': folio_id,
        'tenant_id': current_user.tenant_id,
        'status': 'open'
    })

    if not folio:
        raise HTTPException(status_code=404, detail="Folio not found or closed")

    # Calculate amounts with proper rounding
    amount = round(charge_data.amount * charge_data.quantity, 2)
    tax_amount = 0.0

    # Auto-calculate city tax if requested
    if charge_data.auto_calculate_tax and charge_data.charge_category == ChargeCategory.ROOM:
        # Get city tax rule
        tax_rule = await db.city_tax_rules.find_one({
            'tenant_id': current_user.tenant_id,
            'active': True
        })
        if tax_rule:
            if tax_rule.get('flat_amount'):
                tax_amount = round(tax_rule['flat_amount'], 2)
            else:
                tax_amount = round(amount * (tax_rule['tax_percentage'] / 100), 2)

    total = round(amount + tax_amount, 2)

    charge = FolioCharge(
        tenant_id=current_user.tenant_id,
        folio_id=folio_id,
        booking_id=folio['booking_id'],
        charge_category=charge_data.charge_category,
        description=charge_data.description,
        unit_price=charge_data.amount,
        quantity=charge_data.quantity,
        amount=amount,
        tax_amount=tax_amount,
        total=total,
        posted_by=current_user.id
    )

    charge_dict = charge.model_dump()
    charge_dict['date'] = charge_dict['date'].isoformat()
    await db.folio_charges.insert_one(charge_dict)

    # Update folio balance
    balance = await calculate_folio_balance(folio_id, current_user.tenant_id)
    await db.folios.update_one(
        {'id': folio_id},
        {'$set': {'balance': balance}}
    )

    # Audit log
    await create_audit_log(
        tenant_id=current_user.tenant_id,
        user=current_user,
        action="POST_CHARGE",
        entity_type="folio_charge",
        entity_id=charge.id,
        changes={'charge_category': charge_data.charge_category, 'amount': total, 'folio_id': folio_id}
    )

    return charge


@router.post("/folio/{folio_id}/payment", response_model=Payment)
async def post_payment_to_folio(
    folio_id: str,
    payment_data: PaymentCreate,
    current_user: User = Depends(get_current_user)
):
    """Post a payment to folio"""
    folio = await db.folios.find_one({
        'id': folio_id,
        'tenant_id': current_user.tenant_id
    })

    if not folio:
        raise HTTPException(status_code=404, detail="Folio not found")

    payment = Payment(
        tenant_id=current_user.tenant_id,
        folio_id=folio_id,
        booking_id=folio['booking_id'],
        processed_by=current_user.id,
        **payment_data.model_dump()
    )

    payment_dict = payment.model_dump()
    payment_dict['processed_at'] = payment_dict['processed_at'].isoformat()
    payment_dict['processed_by_name'] = current_user.name  # Add user name
    await db.payments.insert_one(payment_dict)

    # Update folio balance
    balance = await calculate_folio_balance(folio_id, current_user.tenant_id)
    await db.folios.update_one(
        {'id': folio_id},
        {'$set': {'balance': balance}}
    )

    return payment


@router.post("/folio/transfer", response_model=FolioOperation)
async def transfer_charges(
    operation_data: FolioOperationCreate,
    current_user: User = Depends(get_current_user)
):
    """Transfer charges from one folio to another"""
    if operation_data.operation_type != FolioOperationType.TRANSFER:
        raise HTTPException(status_code=400, detail="Invalid operation type")

    if not operation_data.to_folio_id:
        raise HTTPException(status_code=400, detail="Destination folio required for transfer")

    # Verify both folios exist
    from_folio = await db.folios.find_one({
        'id': operation_data.from_folio_id,
        'tenant_id': current_user.tenant_id
    })

    to_folio = await db.folios.find_one({
        'id': operation_data.to_folio_id,
        'tenant_id': current_user.tenant_id,
        'status': 'open'
    })

    if not from_folio or not to_folio:
        raise HTTPException(status_code=404, detail="Folio not found")

    # Transfer specified charges
    for charge_id in operation_data.charge_ids:
        await db.folio_charges.update_one(
            {'id': charge_id, 'folio_id': operation_data.from_folio_id},
            {'$set': {'folio_id': operation_data.to_folio_id}}
        )

    # Create operation record
    operation = FolioOperation(
        tenant_id=current_user.tenant_id,
        performed_by=current_user.id,
        **operation_data.model_dump()
    )

    operation_dict = operation.model_dump()
    operation_dict['performed_at'] = operation_dict['performed_at'].isoformat()
    await db.folio_operations.insert_one(operation_dict)

    # Update balances
    from_balance = await calculate_folio_balance(operation_data.from_folio_id, current_user.tenant_id)
    to_balance = await calculate_folio_balance(operation_data.to_folio_id, current_user.tenant_id)

    await db.folios.update_one(
        {'id': operation_data.from_folio_id},
        {'$set': {'balance': from_balance}}
    )
    await db.folios.update_one(
        {'id': operation_data.to_folio_id},
        {'$set': {'balance': to_balance}}
    )

    return operation


@router.post("/folio/{folio_id}/void-charge/{charge_id}")
async def void_charge(
    folio_id: str,
    charge_id: str,
    void_reason: str,
    current_user: User = Depends(get_current_user)
):
    """Void a charge"""
    charge = await db.folio_charges.find_one({
        'id': charge_id,
        'folio_id': folio_id,
        'tenant_id': current_user.tenant_id,
        'voided': False
    })

    if not charge:
        raise HTTPException(status_code=404, detail="Charge not found or already voided")

    await db.folio_charges.update_one(
        {'id': charge_id},
        {'$set': {
            'voided': True,
            'void_reason': void_reason,
            'voided_by': current_user.id,
            'voided_at': datetime.now(UTC).isoformat()
        }}
    )

    # Update folio balance
    balance = await calculate_folio_balance(folio_id, current_user.tenant_id)
    await db.folios.update_one(
        {'id': folio_id},
        {'$set': {'balance': balance}}
    )

    # Create operation record
    operation = FolioOperation(
        tenant_id=current_user.tenant_id,
        operation_type=FolioOperationType.VOID,
        from_folio_id=folio_id,
        charge_ids=[charge_id],
        amount=charge['total'],
        reason=void_reason,
        performed_by=current_user.id
    )

    operation_dict = operation.model_dump()
    operation_dict['performed_at'] = operation_dict['performed_at'].isoformat()
    await db.folio_operations.insert_one(operation_dict)

    return {"message": "Charge voided successfully"}


@router.post("/folio/{folio_id}/close")
async def close_folio(
    folio_id: str,
    current_user: User = Depends(get_current_user)
):
    """Close a folio"""
    folio = await db.folios.find_one({
        'id': folio_id,
        'tenant_id': current_user.tenant_id,
        'status': 'open'
    })

    if not folio:
        raise HTTPException(status_code=404, detail="Folio not found or already closed")

    # Check balance
    balance = await calculate_folio_balance(folio_id, current_user.tenant_id)

    if balance > 0.01:  # Allow small rounding differences
        raise HTTPException(
            status_code=400,
            detail=f"Cannot close folio with outstanding balance: {balance}"
        )

    await db.folios.update_one(
        {'id': folio_id},
        {'$set': {
            'status': 'closed',
            'balance': 0.0,
            'closed_at': datetime.now(UTC).isoformat()
        }}
    )

    return {"message": "Folio closed successfully"}


@router.get("/folio/{folio_id}/activity-log")
async def get_folio_activity_log(
    folio_id: str,
    current_user: User = Depends(get_current_user)
):
    """Get activity log for a folio"""
    folio = await db.folios.find_one({
        'id': folio_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0})

    if not folio:
        raise HTTPException(status_code=404, detail="Folio not found")

    # Get all activities
    activities = []

    # Charges
    charges = await db.folio_charges.find({
        'folio_id': folio_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).to_list(1000)

    for charge in charges:
        activities.append({
            'type': 'charge',
            'action': 'voided' if charge.get('voided') else 'added',
            'timestamp': charge.get('posted_at'),
            'description': charge.get('description'),
            'amount': charge.get('total', charge.get('amount', 0)),
            'user': charge.get('posted_by'),
            'details': charge
        })

    # Payments
    payments = await db.payments.find({
        'folio_id': folio_id,
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).to_list(1000)

    for payment in payments:
        activities.append({
            'type': 'payment',
            'action': 'voided' if payment.get('voided') else 'processed',
            'timestamp': payment.get('voided_at') if payment.get('voided') else payment.get('processed_at'),
            'description': f"{payment.get('method', 'Payment')} - {payment.get('payment_type', '')}",
            'amount': payment.get('amount', 0),
            'user': payment.get('voided_by') if payment.get('voided') else payment.get('processed_by'),
            'details': payment
        })

    # Operations (transfers, etc)
    operations = await db.folio_operations.find({
        '$or': [
            {'from_folio_id': folio_id},
            {'to_folio_id': folio_id}
        ],
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).to_list(1000)

    for op in operations:
        activities.append({
            'type': 'operation',
            'action': op.get('operation_type'),
            'timestamp': op.get('performed_at'),
            'description': f"Operation: {op.get('operation_type')}",
            'user': op.get('performed_by'),
            'details': op
        })

    # Sort by timestamp
    activities.sort(key=lambda x: x['timestamp'] if x['timestamp'] else '', reverse=True)

    return {
        'folio': folio,
        'activities': activities,
        'total_count': len(activities)
    }


