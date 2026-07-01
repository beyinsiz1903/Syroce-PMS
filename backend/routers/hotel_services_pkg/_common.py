"""Shared helpers + Pydantic models for hotel_services sub-modules.
All inline models from the original 1900-line monolith collected here for
reuse across the 5 sub-routers.
"""

import html as _html
import re as _re
from datetime import UTC, datetime, timedelta

from pydantic import BaseModel


def _e(value) -> str:
    return _html.escape("" if value is None else str(value), quote=True)


def _safe_logo_src(logo_data) -> str:
    if not logo_data:
        return ""
    s = str(logo_data).strip()
    if _re.match(r"^data:image/(png|jpeg|jpg|gif|webp|svg\+xml);base64,[A-Za-z0-9+/=\s]+$", s, _re.IGNORECASE):
        return s
    if _re.match(r"^https?://[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+$", s):
        return s
    return ""


def _clean_doc(doc):
    if doc and "_id" in doc:
        del doc["_id"]
    return doc


# ═══════════════════════════════════════════════════
# 1. HOUSEKEEPING STATUS MANAGEMENT (within rooms)
# ═══════════════════════════════════════════════════


class RoomStatusUpdate(BaseModel):
    status: str  # clean, dirty, inspected, maintenance, out_of_order
    notes: str | None = None
    priority: str | None = "normal"  # low, normal, high, urgent


class WakeUpCallCreate(BaseModel):
    room_number: str
    guest_name: str | None = None
    booking_id: str | None = None
    wake_time: str  # HH:MM format
    wake_date: str  # YYYY-MM-DD
    recurring: bool = False
    recurrence_end_date: str | None = None
    notes: str | None = None
    method: str = "phone"  # phone, system, both


class WakeUpCallUpdate(BaseModel):
    wake_time: str | None = None
    wake_date: str | None = None
    status: str | None = None  # pending, completed, missed, cancelled
    notes: str | None = None
    completed_by: str | None = None
    attempt_count: int | None = None
    response: str | None = None  # answered, no_answer, busy


async def _fire_due_wake_up_alerts(tenant_id: str, calls: list[dict]) -> None:
    """For each pending wake-up call whose scheduled time has arrived,
    create a notification (idempotent — gated by `alert_fired_at`) so it
    appears in the bell menu. Marks the call doc to prevent duplicates.
    Mutates the call dicts in-place so the GET response carries the new
    `alert_fired_at` value to the frontend immediately.
    """
    try:
        from zoneinfo import ZoneInfo

        now_local = datetime.now(ZoneInfo("Europe/Istanbul"))
    except Exception:
        now_local = datetime.now(UTC) + timedelta(hours=3)
    today_str = now_local.strftime("%Y-%m-%d")
    time_str = now_local.strftime("%H:%M")
    now_iso = datetime.now(UTC).isoformat()

    for call in calls:
        if call.get("status") != "pending":
            continue
        if call.get("alert_fired_at"):
            continue
        wd = call.get("wake_date") or ""
        wt = (call.get("wake_time") or "")[:5]  # ensure HH:MM
        is_due = (wd < today_str) or (wd == today_str and wt <= time_str)
        if not is_due:
            continue

        # 1) Insert bell-center notification FIRST (idempotent on source_id).
        # Only after a successful write do we mark the call as alerted, so
        # a transient DB hiccup leaves the call un-fired and the next poll
        # will retry. Without this ordering, a failed notification write
        # would silently lose the bell entry forever.
        try:
            await db.notifications.update_one(
                {
                    "tenant_id": tenant_id,
                    "source_type": "wake_up_call",
                    "source_id": call["id"],
                },
                {
                    "$setOnInsert": {
                        "id": str(uuid.uuid4()),
                        "tenant_id": tenant_id,
                        "source_type": "wake_up_call",
                        "source_id": call["id"],
                        "type": "alert",
                        "severity": "warning",
                        "title": f"Uyandırma: Oda {call.get('room_number', '')}",
                        "message": (f"Oda {call.get('room_number', '')}" + (f" — {call['guest_name']}" if call.get("guest_name") else "") + f" — saat {wt} uyandırma çağrısı zamanı geldi."),
                        "link": "/app/pms/wake-up-calls",
                        "icon": "alarm-clock",
                        "read": False,
                        "created_at": now_iso,
                    }
                },
                upsert=True,
            )
        except Exception:
            # Skip marking; next poll will retry the whole flow.
            continue

        # 2) Mark call as alerted (atomic; only one request wins under load).
        await db.wake_up_calls.update_one(
            {"id": call["id"], "tenant_id": tenant_id, "alert_fired_at": {"$exists": False}},
            {"$set": {"alert_fired_at": now_iso}},
        )
        call["alert_fired_at"] = now_iso


def _annotate_due(calls: list[dict]) -> None:
    try:
        from zoneinfo import ZoneInfo

        now_local = datetime.now(ZoneInfo("Europe/Istanbul"))
    except Exception:
        now_local = datetime.now(UTC) + timedelta(hours=3)
    today_str = now_local.strftime("%Y-%m-%d")
    time_str = now_local.strftime("%H:%M")
    for c in calls:
        wd = c.get("wake_date") or ""
        wt = (c.get("wake_time") or "")[:5]
        c["is_due"] = bool(c.get("status") == "pending" and ((wd < today_str) or (wd == today_str and wt <= time_str)))


class LostFoundCreate(BaseModel):
    item_name: str
    description: str | None = None
    category: str = "other"  # electronics, clothing, jewelry, documents, bags, other
    found_location: str
    found_date: str
    found_by: str | None = None
    room_number: str | None = None
    guest_name: str | None = None
    guest_contact: str | None = None
    booking_id: str | None = None
    storage_location: str | None = None
    photo_data: str | None = None  # base64


class LostFoundUpdate(BaseModel):
    status: str | None = None  # found, claimed, returned, disposed, stored
    claimed_by: str | None = None
    claimed_date: str | None = None
    return_method: str | None = None  # in_person, shipping, courier
    tracking_number: str | None = None
    notes: str | None = None
    guest_name: str | None = None
    guest_contact: str | None = None


class HotelSettingsUpdate(BaseModel):
    hotel_name: str | None = None
    hotel_address: str | None = None
    hotel_phone: str | None = None
    hotel_email: str | None = None
    tax_id: str | None = None
    tax_office: str | None = None
    logo_data: str | None = None  # base64 encoded image
    invoice_header: str | None = None
    invoice_footer: str | None = None
    invoice_notes: str | None = None
    currency: str | None = None
    currency_symbol: str | None = None


class GroupFolioMerge(BaseModel):
    group_id: str
    master_booking_id: str
    merge_booking_ids: list[str]
    merge_payments: bool = True


class GroupPaymentRequest(BaseModel):
    group_id: str
    booking_id: str
    amount: float
    method: str = "cash"
    reference: str = ""


class GroupBulkPaymentRequest(BaseModel):
    group_id: str
    total_amount: float
    method: str = "cash"
    reference: str = ""
    distribution: str = "proportional"  # proportional | equal | balance_only


class CancelReservationRequest(BaseModel):
    reason: str
    cancel_type: str = "guest_request"
    apply_noshow: bool = False
    noshow_charge_type: str | None = None
    noshow_charge_amount: float | None = None


class InvoiceItemSelection(BaseModel):
    selected_charge_ids: list[str] = []
    billing_name: str | None = None
    billing_tax_id: str | None = None
    billing_tax_office: str | None = None
    billing_address: str | None = None
    billing_email: str | None = None
    invoice_note: str | None = None


class CreateCariAccount(BaseModel):
    name: str
    account_type: str = "agency"
    tax_id: str | None = None
    tax_office: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None
