"""Fiscal-document guards: refuse cutting an invoice / e-Fatura against a
reservation that has been cancelled.

A cancelled reservation represents a stay that never happened; issuing a sales
invoice or e-Fatura against it produces a fiscal document that would later need
a credit note (iptal faturasi) to unwind. We therefore block fiscal-document
creation at every last-second XML / invoice-creation point.

Deliberately ALLOWED (NOT blocked):
- ``no_show``    -> the no-show penalty / first-night charge is legitimate
                    revenue and is routinely invoiced,
- ``checked_out``-> the normal invoicing case,
- ``booking_id`` None / booking not found -> manual or legacy invoices are
                    legal; we only block when we can POSITIVELY confirm a
                    cancelled booking.

The guard always re-reads the booking status from the database at the moment of
the cut (a true last-second check) instead of trusting any cached/earlier
snapshot.
"""
from typing import Any

from fastapi import HTTPException

# Only a positively-cancelled reservation is non-invoiceable. ``canceled``
# (US spelling) is included defensively for any legacy rows.
NON_INVOICEABLE_STATUSES = {"cancelled", "canceled"}


def is_status_invoiceable(status: Any) -> bool:
    """True unless the status is a positively-cancelled state."""
    normalized = status.lower() if isinstance(status, str) else (status or "")
    return normalized not in NON_INVOICEABLE_STATUSES


async def resolve_booking_status(
    db_handle, tenant_id: str, booking_id: str | None
) -> str | None:
    """Last-second fetch of a booking's current status (tenant-scoped).

    Returns ``None`` when there is no booking_id or the booking cannot be
    resolved, so callers treat those as invoiceable (manual / legacy invoices).
    """
    if not booking_id:
        return None
    booking = await db_handle.bookings.find_one(
        {"id": booking_id, "tenant_id": tenant_id},
        {"_id": 0, "status": 1},
    )
    if not booking:
        return None
    status = booking.get("status")
    return status.lower() if isinstance(status, str) else None


async def ensure_booking_invoiceable(
    db_handle, tenant_id: str, booking_id: str | None
) -> None:
    """Raise HTTP 409 when the booking is positively cancelled; no-op otherwise.

    Used at HTTP invoice / e-Fatura creation endpoints. The Celery sweep uses
    :func:`resolve_booking_status` + :func:`is_status_invoiceable` directly so it
    can terminal-fail the invoice instead of raising.
    """
    status = await resolve_booking_status(db_handle, tenant_id, booking_id)
    if not is_status_invoiceable(status):
        raise HTTPException(
            status_code=409,
            detail="Rezervasyon iptal edilmiş; fatura/e-Fatura kesilemez",
        )
