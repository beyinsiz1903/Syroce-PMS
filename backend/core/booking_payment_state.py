"""One definition of what has been paid on a reservation.

``bookings.paid_amount`` is an incrementing counter that every payment path
bumps, including a transfer to the city ledger where no money is received,
and ``bookings.balance`` / ``payment_status`` were left stale by the folio
payment endpoints. Both are derived here from the reservation's payments and
the same balance the reservation detail shows, so the PMS, the agency portal,
the agency ledger and the credit check agree.
"""

from __future__ import annotations

import logging

from modules.pms_core.reporting_financials import INSTRUMENT_SETTLEMENT_METHODS, INVALID_PAYMENT_STATUSES, NON_CASH_PAYMENT_METHODS

logger = logging.getLogger(__name__)

# A city-ledger transfer moves the debt to an account; no money is received.
NON_COLLECTION_METHODS = frozenset({"city_ledger"})
NON_COLLECTION_TYPES = frozenset({"city_ledger_transfer"})
# A payment row in one of these states moved no money (declined card,
# cancelled or rejected entry, not yet confirmed).
INVALID_STATUSES = INVALID_PAYMENT_STATUSES


def is_effective(payment: dict) -> bool:
    """The one filter every payment sum uses: not voided, not failed."""
    return payment.get("voided") is not True and str(payment.get("status") or "").lower() not in INVALID_STATUSES


def _is_transfer(payment: dict) -> bool:
    return payment.get("method") in NON_COLLECTION_METHODS or payment.get("payment_type") in NON_COLLECTION_TYPES


def _signed_amount(payment: dict) -> float:
    try:
        amount = float(payment.get("amount") or 0)
    except (TypeError, ValueError):
        return 0.0
    if payment.get("payment_type") == "refund" or payment.get("status") == "refunded":
        return -abs(amount)
    return amount


def collected_amount(payments: list[dict]) -> float:
    """Money actually received on a reservation, net of refunds."""
    total = sum(_signed_amount(p) for p in payments
                if is_effective(p) and not _is_transfer(p) and str(p.get("method") or "").lower() not in NON_CASH_PAYMENT_METHODS)
    return round(max(0.0, total), 2)


def transferred_amount(payments: list[dict]) -> float:
    """Amount moved to the city ledger (settled on account, not collected)."""
    total = sum(_signed_amount(p) for p in payments if is_effective(p) and _is_transfer(p))
    return round(max(0.0, total), 2)


def refunded_amount(payments: list[dict]) -> float:
    return round(sum(abs(_signed_amount(p)) for p in payments
                     if is_effective(p) and _signed_amount(p) < 0), 2)


def payment_state(*, balance: float, payments: list[dict]) -> str:
    """Reservation payment status from its payments and outstanding balance."""
    collected = collected_amount(payments)
    transferred = transferred_amount(payments)
    applied_security = sum(_signed_amount(p) for p in payments if is_effective(p) and p.get("method") == "security_deposit_application")
    non_cash_settled = sum(_signed_amount(p) for p in payments if is_effective(p) and p.get("method") in INSTRUMENT_SETTLEMENT_METHODS)
    if balance <= 0.01 and (collected > 0 or transferred > 0 or applied_security > 0 or non_cash_settled > 0):
        return "paid" if transferred <= 0.01 else "transferred"
    if collected > 0 or transferred > 0 or applied_security > 0 or non_cash_settled > 0:
        return "partial"
    if refunded_amount(payments) > 0:
        return "refunded"
    return "pending"


PAYMENT_FIELDS = {"_id": 0, "amount": 1, "method": 1, "payment_type": 1, "status": 1, "voided": 1}


async def compute_booking_payment_state(database, tenant_id: str, booking: dict, payments: list[dict] | None = None) -> dict:
    """Balance, status and collected money of one reservation, from its live
    payments; also used on read so records older than this module are right."""
    from routers.reservation_detail import _reservation_outstanding_balance

    balance = round(float(await _reservation_outstanding_balance(tenant_id, booking)), 2)
    if payments is None:
        payments = await database.payments.find(
            {"tenant_id": tenant_id, "booking_id": booking["id"]}, PAYMENT_FIELDS).to_list(None)
    return {"balance": max(0.0, balance), "payment_status": payment_state(balance=balance, payments=payments),
            "collected_amount": collected_amount(payments)}


async def refresh_booking_payment_state(database, tenant_id: str, booking_id: str) -> dict | None:
    """Recompute ``balance`` and ``payment_status`` after a payment change.

    Never raises: a payment that was recorded must not look failed because
    the cached fields could not be refreshed (the next refresh repairs them).
    """
    try:
        booking = await database.bookings.find_one({"id": booking_id, "tenant_id": tenant_id}, {"_id": 0})
        if not booking:
            return None
        state = await compute_booking_payment_state(database, tenant_id, booking)
        await database.bookings.update_one({"id": booking_id, "tenant_id": tenant_id}, {"$set": state})
        return state
    except Exception as exc:  # noqa: BLE001 - see docstring
        logger.warning("Booking payment state refresh failed booking=%s error=%s", booking_id, type(exc).__name__)
        return None
