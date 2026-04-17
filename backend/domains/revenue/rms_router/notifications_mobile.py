"""
Domain Router: RMS Revenue

Revenue management system, comp-set, yield management, Faz 2 sales/revenue features.
"""
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel

from core.cache import cached
from core.database import db
from core.security import get_current_user, security
from models.schemas import (
    AddCompetitorRequest,
    AutoPricingRequest,
    DemandForecastRequest,
    ScrapePricesRequest,
    User,
)

router = APIRouter(prefix="/api", tags=["rms-revenue"])

# ========================================


# ─── Endpoints (split: notifications_mobile) ───


@router.get("/notifications/mobile/finance")
async def get_finance_notifications_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get notifications for finance mobile dashboard"""
    current_user = await get_current_user(credentials)

    notifications = []
    today = datetime.now(UTC)

    # Overdue receivables
    overdue_count = 0
    overdue_amount = 0.0

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
                # Convert string date to datetime for comparison
                try:
                    if isinstance(checkout, str):
                        checkout_date = datetime.fromisoformat(checkout).replace(tzinfo=UTC)
                    else:
                        checkout_date = checkout if checkout.tzinfo else checkout.replace(tzinfo=UTC)

                    if checkout_date < today - timedelta(days=7):
                        overdue_count += 1
                        overdue_amount += folio.get('balance', 0)
                except (ValueError, AttributeError):
                    pass  # Skip invalid dates

    if overdue_count > 0:
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'overdue_receivables',
            'title': 'Overdue Receivables',
            'message': f"{overdue_count} overdue receivable(s) - Total: ₺{overdue_amount:.2f}",
            'priority': 'high',
            'created_at': today.isoformat()
        })

    # Large payment approvals needed (> 10000 TL)
    async for payment in db.payment_approvals.find({
        'tenant_id': current_user.tenant_id,
        'status': 'pending',
        'amount': {'$gt': 10000}
    }):
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'large_payment_approval',
            'title': 'Large Payment Approval',
            'message': f"Payment of ₺{payment.get('amount', 0):.2f} awaiting approval",
            'priority': 'medium',
            'created_at': payment.get('created_at').isoformat()
        })

    return {
        'notifications': notifications,
        'unread_count': len(notifications)
    }


# --------------------------------------------------------------------------
# Finance Mobile - New Enhancements (Cash Flow, Risk Management, Expenses)
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# Security/IT Mobile Dashboard Endpoints (NEW)
# --------------------------------------------------------------------------



@router.get("/notifications/mobile/security")
async def get_security_notifications_mobile(
    credentials: HTTPAuthorizationCredentials = Depends(security)
):
    """Get notifications for security/IT mobile dashboard"""
    current_user = await get_current_user(credentials)

    notifications = []

    # System errors in last hour
    error_count = await db.system_logs.count_documents({
        'tenant_id': current_user.tenant_id,
        'log_level': 'error',
        'created_at': {'$gte': datetime.now(UTC) - timedelta(hours=1)}
    })

    if error_count > 0:
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'system_error',
            'title': 'System Errors',
            'message': f"{error_count} system error(s) recorded in the last hour",
            'priority': 'high',
            'created_at': datetime.now(UTC).isoformat()
        })

    # Connection failures
    async for error in db.system_logs.find({
        'tenant_id': current_user.tenant_id,
        'log_type': {'$in': ['pos_error', 'cm_sync_error']},
        'created_at': {'$gte': datetime.now(UTC) - timedelta(hours=1)}
    }).limit(5):
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'connection_failure',
            'title': 'Connection Error',
            'message': error.get('message', 'Connection issue detected'),
            'priority': 'medium',
            'created_at': error.get('created_at').isoformat()
        })

    # Security alerts
    failed_logins = await db.auth_logs.count_documents({
        'tenant_id': current_user.tenant_id,
        'action': 'login_failed',
        'timestamp': {'$gte': datetime.now(UTC) - timedelta(hours=1)}
    })

    if failed_logins > 5:
        notifications.append({
            'id': str(uuid.uuid4()),
            'type': 'security_alert',
            'title': 'Security Alert',
            'message': f"Multiple failed login attempts ({failed_logins})",
            'priority': 'urgent',
            'created_at': datetime.now(UTC).isoformat()
        })

    return {
        'notifications': notifications,
        'unread_count': len(notifications)
    }




# ============================================================================
# NEW RMS: Internal-Data-Driven Dashboard, Yield Rules, Seasonal Calendar
# ============================================================================

