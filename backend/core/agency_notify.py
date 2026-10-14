"""Notifications between hotels and marketplace agencies.

Agencies keep notification preferences in their portal settings
(``marketplace_agencies.notification_preferences``). Every notice is stored in
``marketplace_agency_notices`` so the portal can list it, and is e-mailed to the
agency contact when the matching preference is on. Hotels are notified through
the tenant's bell-center ``notifications`` collection.

Notification helpers never raise: the business action that triggered them has
already been committed.
"""

from __future__ import annotations

import html
import logging
import uuid
from datetime import UTC, datetime

logger = logging.getLogger("core.agency_notify")

# Preference keys stored by the portal settings screen. A missing key means on.
PREF_NEW_RESERVATION = "new_reservation"
PREF_RESERVATION_CHANGE = "reservation_change"
PREF_CANCELLATION = "cancellation_request"
PREF_CONTRACT = "contract_updates"


def _now() -> str:
    return datetime.now(UTC).isoformat()


async def notify_agency(
    sysdb,
    *,
    agency_id: str,
    kind: str,
    title: str,
    message: str,
    preference: str,
    tenant_id: str | None = None,
    reference_id: str | None = None,
) -> None:
    """Store a portal notice for the agency and e-mail it if the preference allows."""
    try:
        notice = {
            "id": str(uuid.uuid4()),
            "agency_id": agency_id,
            "tenant_id": tenant_id,
            "kind": kind,
            "title": title,
            "message": message,
            "reference_id": reference_id,
            "read": False,
            "created_at": _now(),
        }
        await sysdb.marketplace_agency_notices.insert_one(notice)
        agency = await sysdb.marketplace_agencies.find_one(
            {"id": agency_id}, {"_id": 0, "contact_email": 1, "notification_preferences": 1}
        )
        prefs = (agency or {}).get("notification_preferences") or {}
        email = (agency or {}).get("contact_email")
        if not email or prefs.get(preference, True) is False:
            return
        from core.email import send_email

        body = f"<p><strong>{html.escape(title)}</strong></p><p>{html.escape(message)}</p>"
        await send_email(email, f"Syroce — {title}", body)
    except Exception as exc:  # noqa: BLE001 - notification must not undo the action
        logger.warning("Agency notice failed kind=%s agency=%s error=%s", kind, agency_id, type(exc).__name__)


async def notify_hotel(
    tenant_id: str,
    *,
    kind: str,
    title: str,
    message: str,
    action_url: str,
    metadata: dict | None = None,
) -> None:
    """Add a bell-center notification for the hotel's staff."""
    try:
        from core.database import db
        from core.tenant_db import tenant_context

        with tenant_context(tenant_id):
            await db.notifications.insert_one(
                {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tenant_id,
                    "user_id": None,
                    "type": kind,
                    "title": title,
                    "message": message,
                    "priority": "high",
                    "read": False,
                    "action_url": action_url,
                    "metadata": metadata or {},
                    "created_at": _now(),
                }
            )
    except Exception as exc:  # noqa: BLE001
        logger.warning("Hotel notice failed kind=%s tenant=%s error=%s", kind, tenant_id, type(exc).__name__)


async def on_pms_status_change(tenant_id: str, booking: dict, new_status: str, reason: str = "") -> None:
    """Hotel changed a marketplace booking in the PMS (cancel / no-show).

    Updates the agency ledger immediately and tells the agency, so the agency
    portal, reconciliation and credit view agree with the PMS.
    """
    agency_id = booking.get("agency_id")
    if not agency_id or not booking.get("id"):
        return
    try:
        from core.tenant_db import get_system_db

        sysdb = get_system_db()
        ledger = await sysdb.marketplace_bookings.find_one(
            {"id": booking["id"], "agency_id": agency_id}, {"_id": 0, "id": 1, "confirmation_code": 1}
        )
        if not ledger:
            return  # not a marketplace booking (hotel-bound legacy agency)
        await sysdb.marketplace_bookings.update_one(
            {"id": booking["id"], "agency_id": agency_id},
            {"$set": {"status": new_status, "pms_synced_at": _now()}},
        )
        code = ledger.get("confirmation_code") or booking.get("confirmation_code") or booking["id"]
        label = {"cancelled": "iptal edildi", "no_show": "no-show olarak işaretlendi"}.get(new_status, new_status)
        await notify_agency(
            sysdb,
            agency_id=agency_id,
            tenant_id=tenant_id,
            kind=f"hotel_{new_status}",
            title=f"Rezervasyon {code} otel tarafından {label}",
            message=(reason or "Otel PMS üzerinden işlem yaptı.")[:500],
            preference=PREF_CANCELLATION if new_status == "cancelled" else PREF_RESERVATION_CHANGE,
            reference_id=booking["id"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("PMS status sync failed booking=%s error=%s", booking.get("id"), type(exc).__name__)
