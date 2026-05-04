"""Auto-split from misc_router.py — backward-compatible sub-router."""
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

from ._common import (
    calculate_folio_balance,
)

logger = logging.getLogger(__name__)

sub_router = APIRouter()

@sub_router.post("/payments/intent")
async def payment_intent(payment_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v94 DW
):
    intent = {'id': str(uuid.uuid4()), 'amount': payment_data['amount'], 'status': 'pending'}
    await db.payment_intents.insert_one(intent)
    return {'success': True, 'intent_id': intent['id']}



# NOT: /payments/installment ucu kaldırıldı (sadece silinen PaymentGateway
# sayfası kullanıyordu). Frontdesk taksitlendirme için folio_ledger kullanılır.


@sub_router.post("/payments/create-intent")
async def create_payment_intent(payment_data: dict, current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v94 DW
):
    intent = {
        'id': str(uuid.uuid4()), 'amount': payment_data['amount'],
        'status': 'pending', 'stripe_id': f'pi_mock_{str(uuid.uuid4())[:8]}'
    }
    await db.payment_intents.insert_one(intent)


# NOT: GDS (Amadeus/Sabre/Galileo) entegrasyon stub'ları kaldırıldı.
# Gerçek bir GDS bağlantısı eklendiğinde, OTA Channel Manager paterniyle
# (backend/domains/channel_manager) ayrı bir adapter olarak kurulmalı.


# ============= MOBILE APP BACKEND =============




# ============= FOLIO & BILLING ENGINE =============



@sub_router.post("/payment/{payment_id}/void")
async def void_payment(
    payment_id: str,
    void_reason: str = "Voided by staff",
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("post_payment")),  # v94 DW
):
    """Void a payment"""
    payment = await db.payments.find_one({
        'id': payment_id,
        'tenant_id': current_user.tenant_id
    })

    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")

    if payment.get('voided'):
        raise HTTPException(status_code=400, detail="Payment already voided")

    # Update payment
    await db.payments.update_one(
        {'id': payment_id},
        {'$set': {
            'voided': True,
            'voided_by': current_user.id,
            'voided_at': datetime.now(UTC).isoformat(),
            'void_reason': void_reason
        }}
    )

    # Recalculate folio balance
    folio_id = payment['folio_id']
    balance = await calculate_folio_balance(folio_id, current_user.tenant_id)
    await db.folios.update_one(
        {'id': folio_id},
        {'$set': {'balance': balance}}
    )

    return {"message": "Payment voided successfully"}

# ── Folio by Booking ID (used by ReservationCalendar sidebar) ──

@sub_router.get("/folio/booking/{booking_id}")
async def get_folios_by_booking(booking_id: str, current_user: User = Depends(get_current_user)):
    folios = await db.folios.find(
        {"booking_id": booking_id, "tenant_id": current_user.tenant_id},
        {"_id": 0},
    ).to_list(20)
    return folios

