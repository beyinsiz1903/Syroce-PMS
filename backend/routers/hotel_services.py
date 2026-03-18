"""
Hotel Services Router - Housekeeping Status, Wake-up Calls, Lost & Found,
Hotel Settings (logo/template), Group Folio Merging, PDF Invoice Generation
"""
import uuid
import base64
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import Response
from pydantic import BaseModel, Field

from core.database import db
from core.security import get_current_user
from models.schemas import User, _ensure_hotel_context

router = APIRouter(prefix="/api/pms", tags=["hotel-services"])


# ── Helper ──
def _clean_doc(doc):
    if doc and "_id" in doc:
        del doc["_id"]
    return doc


# ═══════════════════════════════════════════════════
# 1. HOUSEKEEPING STATUS MANAGEMENT (within rooms)
# ═══════════════════════════════════════════════════

class RoomStatusUpdate(BaseModel):
    status: str  # clean, dirty, inspected, maintenance, out_of_order
    notes: Optional[str] = None
    priority: Optional[str] = "normal"  # low, normal, high, urgent


@router.get("/housekeeping/rooms")
async def get_housekeeping_rooms(
    status_filter: Optional[str] = None,
    floor: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """Get all rooms with housekeeping status."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    query = {"tenant_id": tid}
    if status_filter:
        query["housekeeping_status"] = status_filter
    if floor:
        query["floor"] = floor

    rooms = []
    async for r in db.rooms.find(query, {"_id": 0}).sort("room_number", 1):
        # Check if room has active booking
        booking = await db.bookings.find_one(
            {"room_id": r.get("id"), "tenant_id": tid, "status": {"$in": ["checked_in", "confirmed"]}},
            {"_id": 0, "guest_name": 1, "check_out": 1, "status": 1}
        )
        r["current_booking"] = booking
        r["housekeeping_status"] = r.get("housekeeping_status", "clean")
        rooms.append(r)

    # Summary counts
    statuses = {}
    for r in rooms:
        s = r.get("housekeeping_status", "clean")
        statuses[s] = statuses.get(s, 0) + 1

    return {"rooms": rooms, "summary": statuses, "total": len(rooms)}


@router.put("/housekeeping/rooms/{room_id}/status")
async def update_room_housekeeping_status(
    room_id: str,
    data: RoomStatusUpdate,
    current_user: User = Depends(get_current_user),
):
    """Update housekeeping status of a room."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    room = await db.rooms.find_one({"id": room_id, "tenant_id": tid})
    if not room:
        raise HTTPException(status_code=404, detail="Oda bulunamadi")

    old_status = room.get("housekeeping_status", "clean")

    update_data = {
        "housekeeping_status": data.status,
        "housekeeping_updated_at": datetime.now(timezone.utc).isoformat(),
        "housekeeping_updated_by": current_user.name,
    }
    if data.notes:
        update_data["housekeeping_notes"] = data.notes

    await db.rooms.update_one(
        {"id": room_id, "tenant_id": tid},
        {"$set": update_data}
    )

    # Log the change
    log_entry = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "room_id": room_id,
        "room_number": room.get("room_number"),
        "old_status": old_status,
        "new_status": data.status,
        "notes": data.notes,
        "changed_by": current_user.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.housekeeping_log.insert_one(log_entry)
    log_entry.pop("_id", None)

    return {"success": True, "room_id": room_id, "new_status": data.status}


@router.put("/housekeeping/rooms/bulk-status")
async def bulk_update_room_status(
    room_ids: List[str] = [],
    status: str = "clean",
    current_user: User = Depends(get_current_user),
):
    """Bulk update housekeeping status for multiple rooms."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    now = datetime.now(timezone.utc).isoformat()
    result = await db.rooms.update_many(
        {"id": {"$in": room_ids}, "tenant_id": tid},
        {"$set": {
            "housekeeping_status": status,
            "housekeeping_updated_at": now,
            "housekeeping_updated_by": current_user.name,
        }}
    )

    return {"success": True, "updated_count": result.modified_count}


# ═══════════════════════════════════════════════════
# 2. WAKE-UP CALL MANAGEMENT
# ═══════════════════════════════════════════════════

class WakeUpCallCreate(BaseModel):
    room_number: str
    guest_name: Optional[str] = None
    booking_id: Optional[str] = None
    wake_time: str  # HH:MM format
    wake_date: str  # YYYY-MM-DD
    recurring: bool = False
    recurrence_end_date: Optional[str] = None
    notes: Optional[str] = None
    method: str = "phone"  # phone, system, both


class WakeUpCallUpdate(BaseModel):
    wake_time: Optional[str] = None
    wake_date: Optional[str] = None
    status: Optional[str] = None  # pending, completed, missed, cancelled
    notes: Optional[str] = None
    completed_by: Optional[str] = None
    attempt_count: Optional[int] = None
    response: Optional[str] = None  # answered, no_answer, busy


@router.get("/wake-up-calls")
async def get_wake_up_calls(
    date: Optional[str] = None,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """Get wake-up calls, optionally filtered by date and status."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    query = {"tenant_id": tid}
    if date:
        query["wake_date"] = date
    if status:
        query["status"] = status

    calls = []
    async for c in db.wake_up_calls.find(query, {"_id": 0}).sort([("wake_date", 1), ("wake_time", 1)]):
        calls.append(c)

    # Stats
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_calls = [c for c in calls if c.get("wake_date") == today]
    pending = len([c for c in today_calls if c.get("status") == "pending"])
    completed = len([c for c in today_calls if c.get("status") == "completed"])
    missed = len([c for c in today_calls if c.get("status") == "missed"])

    return {
        "calls": calls,
        "stats": {
            "total_today": len(today_calls),
            "pending": pending,
            "completed": completed,
            "missed": missed,
        }
    }


@router.post("/wake-up-calls")
async def create_wake_up_call(
    data: WakeUpCallCreate,
    current_user: User = Depends(get_current_user),
):
    """Create a new wake-up call."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    call = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "room_number": data.room_number,
        "guest_name": data.guest_name,
        "booking_id": data.booking_id,
        "wake_time": data.wake_time,
        "wake_date": data.wake_date,
        "recurring": data.recurring,
        "recurrence_end_date": data.recurrence_end_date,
        "notes": data.notes,
        "method": data.method,
        "status": "pending",
        "attempt_count": 0,
        "created_by": current_user.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.wake_up_calls.insert_one(call)
    call.pop("_id", None)

    return {"success": True, "call": call}


@router.put("/wake-up-calls/{call_id}")
async def update_wake_up_call(
    call_id: str,
    data: WakeUpCallUpdate,
    current_user: User = Depends(get_current_user),
):
    """Update a wake-up call status."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    updates = {}
    if data.wake_time:
        updates["wake_time"] = data.wake_time
    if data.wake_date:
        updates["wake_date"] = data.wake_date
    if data.status:
        updates["status"] = data.status
        if data.status == "completed":
            updates["completed_at"] = datetime.now(timezone.utc).isoformat()
            updates["completed_by"] = data.completed_by or current_user.name
    if data.notes is not None:
        updates["notes"] = data.notes
    if data.attempt_count is not None:
        updates["attempt_count"] = data.attempt_count
    if data.response:
        updates["response"] = data.response

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()

    result = await db.wake_up_calls.update_one(
        {"id": call_id, "tenant_id": tid},
        {"$set": updates}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Wake-up call bulunamadi")

    updated = await db.wake_up_calls.find_one({"id": call_id}, {"_id": 0})
    return {"success": True, "call": updated}


@router.delete("/wake-up-calls/{call_id}")
async def delete_wake_up_call(
    call_id: str,
    current_user: User = Depends(get_current_user),
):
    """Delete a wake-up call."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    result = await db.wake_up_calls.delete_one({"id": call_id, "tenant_id": tid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Wake-up call bulunamadi")

    return {"success": True}


# ═══════════════════════════════════════════════════
# 3. LOST & FOUND MODULE
# ═══════════════════════════════════════════════════

class LostFoundCreate(BaseModel):
    item_name: str
    description: Optional[str] = None
    category: str = "other"  # electronics, clothing, jewelry, documents, bags, other
    found_location: str
    found_date: str
    found_by: Optional[str] = None
    room_number: Optional[str] = None
    guest_name: Optional[str] = None
    guest_contact: Optional[str] = None
    booking_id: Optional[str] = None
    storage_location: Optional[str] = None
    photo_data: Optional[str] = None  # base64


class LostFoundUpdate(BaseModel):
    status: Optional[str] = None  # found, claimed, returned, disposed, stored
    claimed_by: Optional[str] = None
    claimed_date: Optional[str] = None
    return_method: Optional[str] = None  # in_person, shipping, courier
    tracking_number: Optional[str] = None
    notes: Optional[str] = None
    guest_name: Optional[str] = None
    guest_contact: Optional[str] = None


@router.get("/lost-found")
async def get_lost_found_items(
    status: Optional[str] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """Get lost & found items."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    query = {"tenant_id": tid}
    if status:
        query["status"] = status
    if category:
        query["category"] = category

    items = []
    async for item in db.lost_found.find(query, {"_id": 0}).sort("created_at", -1):
        if search:
            search_lower = search.lower()
            if (search_lower not in (item.get("item_name", "").lower()) and
                search_lower not in (item.get("description", "") or "").lower() and
                search_lower not in (item.get("guest_name", "") or "").lower()):
                continue
        items.append(item)

    stats = {
        "total": len(items),
        "found": len([i for i in items if i.get("status") == "found"]),
        "claimed": len([i for i in items if i.get("status") == "claimed"]),
        "returned": len([i for i in items if i.get("status") == "returned"]),
        "stored": len([i for i in items if i.get("status") == "stored"]),
    }

    return {"items": items, "stats": stats}


@router.post("/lost-found")
async def create_lost_found_item(
    data: LostFoundCreate,
    current_user: User = Depends(get_current_user),
):
    """Register a new lost & found item."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    item = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "item_name": data.item_name,
        "description": data.description,
        "category": data.category,
        "found_location": data.found_location,
        "found_date": data.found_date,
        "found_by": data.found_by or current_user.name,
        "room_number": data.room_number,
        "guest_name": data.guest_name,
        "guest_contact": data.guest_contact,
        "booking_id": data.booking_id,
        "storage_location": data.storage_location,
        "photo_data": data.photo_data,
        "status": "found",
        "created_by": current_user.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.lost_found.insert_one(item)
    item.pop("_id", None)

    return {"success": True, "item": item}


@router.put("/lost-found/{item_id}")
async def update_lost_found_item(
    item_id: str,
    data: LostFoundUpdate,
    current_user: User = Depends(get_current_user),
):
    """Update a lost & found item."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if data.status:
        updates["status"] = data.status
    if data.claimed_by:
        updates["claimed_by"] = data.claimed_by
    if data.claimed_date:
        updates["claimed_date"] = data.claimed_date
    if data.return_method:
        updates["return_method"] = data.return_method
    if data.tracking_number:
        updates["tracking_number"] = data.tracking_number
    if data.notes is not None:
        updates["notes"] = data.notes
    if data.guest_name:
        updates["guest_name"] = data.guest_name
    if data.guest_contact:
        updates["guest_contact"] = data.guest_contact

    result = await db.lost_found.update_one(
        {"id": item_id, "tenant_id": tid},
        {"$set": updates}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Kayit bulunamadi")

    updated = await db.lost_found.find_one({"id": item_id}, {"_id": 0})
    return {"success": True, "item": updated}


@router.delete("/lost-found/{item_id}")
async def delete_lost_found_item(
    item_id: str,
    current_user: User = Depends(get_current_user),
):
    """Delete a lost & found item."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    result = await db.lost_found.delete_one({"id": item_id, "tenant_id": tid})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Kayit bulunamadi")

    return {"success": True}


@router.post("/lost-found/{item_id}/match-guest")
async def match_guest_to_item(
    item_id: str,
    guest_name: str = "",
    guest_contact: str = "",
    booking_id: str = "",
    current_user: User = Depends(get_current_user),
):
    """Match a guest to a lost & found item."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
    if guest_name:
        updates["guest_name"] = guest_name
    if guest_contact:
        updates["guest_contact"] = guest_contact
    if booking_id:
        updates["booking_id"] = booking_id
        # Try to get guest info from booking
        booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
        if booking:
            updates["guest_name"] = booking.get("guest_name", guest_name)
            updates["room_number"] = booking.get("room_number")

    result = await db.lost_found.update_one(
        {"id": item_id, "tenant_id": tid},
        {"$set": updates}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Kayit bulunamadi")

    updated = await db.lost_found.find_one({"id": item_id}, {"_id": 0})
    return {"success": True, "item": updated}


# ═══════════════════════════════════════════════════
# 4. HOTEL SETTINGS - Logo & Invoice Template
# ═══════════════════════════════════════════════════

@router.get("/hotel-settings")
async def get_hotel_settings(
    current_user: User = Depends(get_current_user),
):
    """Get hotel settings including logo and invoice template."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    settings = await db.hotel_settings.find_one({"tenant_id": tid}, {"_id": 0})
    if not settings:
        # Return defaults
        tenant = await db.tenants.find_one({"tenant_id": tid}, {"_id": 0})
        settings = {
            "tenant_id": tid,
            "hotel_name": tenant.get("property_name", "") if tenant else "",
            "hotel_address": tenant.get("address", "") if tenant else "",
            "hotel_phone": tenant.get("phone", tenant.get("contact_phone", "")) if tenant else "",
            "hotel_email": tenant.get("email", tenant.get("contact_email", "")) if tenant else "",
            "tax_id": "",
            "tax_office": "",
            "logo_data": None,
            "invoice_header": "",
            "invoice_footer": "Konaklama hizmetlerinden memnun kaldiysa bizi tercih ettiginiz icin tesekkur ederiz.",
            "invoice_notes": "",
            "currency": "TRY",
            "currency_symbol": "₺",
        }

    return settings


class HotelSettingsUpdate(BaseModel):
    hotel_name: Optional[str] = None
    hotel_address: Optional[str] = None
    hotel_phone: Optional[str] = None
    hotel_email: Optional[str] = None
    tax_id: Optional[str] = None
    tax_office: Optional[str] = None
    logo_data: Optional[str] = None  # base64 encoded image
    invoice_header: Optional[str] = None
    invoice_footer: Optional[str] = None
    invoice_notes: Optional[str] = None
    currency: Optional[str] = None
    currency_symbol: Optional[str] = None


@router.put("/hotel-settings")
async def update_hotel_settings(
    data: HotelSettingsUpdate,
    current_user: User = Depends(get_current_user),
):
    """Update hotel settings."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    updates = {"tenant_id": tid, "updated_at": datetime.now(timezone.utc).isoformat()}
    for field in data.model_fields:
        val = getattr(data, field)
        if val is not None:
            updates[field] = val

    await db.hotel_settings.update_one(
        {"tenant_id": tid},
        {"$set": updates},
        upsert=True,
    )

    settings = await db.hotel_settings.find_one({"tenant_id": tid}, {"_id": 0})
    return {"success": True, "settings": settings}


# ═══════════════════════════════════════════════════
# 5. PDF INVOICE GENERATION FROM FOLIO
# ═══════════════════════════════════════════════════

@router.get("/reservations/{booking_id}/invoice-pdf")
async def generate_invoice_pdf(
    booking_id: str,
    current_user: User = Depends(get_current_user),
):
    """Generate a PDF invoice from reservation folio."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    # Get booking
    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    # Get folio entries
    folios = []
    async for f in db.folios.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", 1):
        folios.append(f)

    # Get payments
    payments = []
    async for p in db.payments.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", 1):
        payments.append(p)

    # Get hotel settings
    settings = await db.hotel_settings.find_one({"tenant_id": tid}, {"_id": 0})
    if not settings:
        tenant = await db.tenants.find_one({"tenant_id": tid}, {"_id": 0})
        settings = {
            "hotel_name": tenant.get("property_name", "Hotel") if tenant else "Hotel",
            "hotel_address": tenant.get("address", "") if tenant else "",
            "hotel_phone": tenant.get("phone", "") if tenant else "",
            "hotel_email": tenant.get("email", "") if tenant else "",
            "tax_id": "",
            "tax_office": "",
            "logo_data": None,
            "invoice_footer": "",
            "currency_symbol": "₺",
        }

    # Get guest info
    guest = None
    if booking.get("guest_id"):
        guest = await db.guests.find_one({"id": booking["guest_id"], "tenant_id": tid}, {"_id": 0})

    # Build invoice data
    invoice_number = f"INV-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{booking_id[:8].upper()}"

    # Calculate totals
    total_payments = sum(p.get("amount", 0) for p in payments)

    # Also include accommodation total
    accommodation_total = booking.get("total_amount", 0)

    # Generate HTML for PDF
    currency = settings.get("currency_symbol", "₺")

    logo_html = ""
    if settings.get("logo_data"):
        logo_html = f'<img src="{settings["logo_data"]}" style="max-height:80px;max-width:200px;" />'

    folio_rows = ""
    if accommodation_total > 0:
        folio_rows += f"""<tr>
            <td style="padding:8px;border-bottom:1px solid #eee;">Konaklama</td>
            <td style="padding:8px;border-bottom:1px solid #eee;">{booking.get("check_in","")[:10]} - {booking.get("check_out","")[:10]}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;text-align:right;">{currency}{accommodation_total:,.2f}</td>
        </tr>"""

    for f in folios:
        if f.get("type") == "payment":
            continue
        folio_rows += f"""<tr>
            <td style="padding:8px;border-bottom:1px solid #eee;">{f.get("description", f.get("category", "Masraf"))}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;">{(f.get("created_at",""))[:10]}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;text-align:right;">{currency}{f.get("amount",0):,.2f}</td>
        </tr>"""

    payment_rows = ""
    for p in payments:
        method_label = {"cash": "Nakit", "card": "Kredi Karti", "bank_transfer": "Havale/EFT", "online": "Online"}.get(p.get("method", ""), p.get("method", ""))
        payment_rows += f"""<tr>
            <td style="padding:8px;border-bottom:1px solid #eee;">{method_label}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;">{(p.get("created_at",""))[:10]}</td>
            <td style="padding:8px;border-bottom:1px solid #eee;text-align:right;">{currency}{p.get("amount",0):,.2f}</td>
        </tr>"""

    grand_total = accommodation_total + sum(f.get("amount", 0) for f in folios if f.get("type") != "payment")
    balance = grand_total - total_payments

    guest_name = guest.get("name", booking.get("guest_name", "-")) if guest else booking.get("guest_name", "-")
    guest_email = guest.get("email", "") if guest else ""
    guest_phone = guest.get("phone", "") if guest else ""

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; margin:0; padding:40px; color:#333; font-size:13px; }}
.header {{ display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:30px; border-bottom:3px solid #1a56db; padding-bottom:20px; }}
.hotel-info {{ text-align:right; }}
.hotel-name {{ font-size:22px; font-weight:700; color:#1a56db; }}
.invoice-title {{ font-size:28px; font-weight:700; color:#1a56db; margin:20px 0 10px; }}
.info-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:25px; }}
.info-box {{ background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:16px; }}
.info-box h3 {{ margin:0 0 8px; font-size:13px; color:#64748b; text-transform:uppercase; letter-spacing:0.5px; }}
table {{ width:100%; border-collapse:collapse; margin-bottom:20px; }}
th {{ background:#f1f5f9; padding:10px 8px; text-align:left; font-weight:600; font-size:12px; color:#475569; text-transform:uppercase; }}
.total-row {{ font-weight:700; background:#f0f9ff; }}
.balance-row {{ font-weight:700; font-size:16px; background:#eff6ff; color:#1a56db; }}
.footer {{ margin-top:40px; padding-top:20px; border-top:2px solid #e2e8f0; text-align:center; color:#94a3b8; font-size:11px; }}
</style></head><body>

<div class="header">
    <div>{logo_html}</div>
    <div class="hotel-info">
        <div class="hotel-name">{settings.get("hotel_name","")}</div>
        <div>{settings.get("hotel_address","")}</div>
        <div>{settings.get("hotel_phone","")}</div>
        <div>{settings.get("hotel_email","")}</div>
        {f'<div>Vergi No: {settings.get("tax_id","")}</div>' if settings.get("tax_id") else ''}
        {f'<div>Vergi Dairesi: {settings.get("tax_office","")}</div>' if settings.get("tax_office") else ''}
    </div>
</div>

<div class="invoice-title">FATURA</div>
<div style="margin-bottom:20px;color:#64748b;">
    Fatura No: <strong>{invoice_number}</strong><br>
    Tarih: <strong>{datetime.now(timezone.utc).strftime("%d.%m.%Y")}</strong>
</div>

<div class="info-grid">
    <div class="info-box">
        <h3>Misafir Bilgileri</h3>
        <div><strong>{guest_name}</strong></div>
        {f'<div>{guest_email}</div>' if guest_email else ''}
        {f'<div>{guest_phone}</div>' if guest_phone else ''}
    </div>
    <div class="info-box">
        <h3>Rezervasyon Bilgileri</h3>
        <div>Oda: <strong>{booking.get("room_number","-")}</strong></div>
        <div>Giris: <strong>{(booking.get("check_in",""))[:10]}</strong></div>
        <div>Cikis: <strong>{(booking.get("check_out",""))[:10]}</strong></div>
    </div>
</div>

<h3 style="color:#1a56db;margin-bottom:8px;">Masraflar</h3>
<table>
    <thead><tr>
        <th>Aciklama</th>
        <th>Tarih</th>
        <th style="text-align:right;">Tutar</th>
    </tr></thead>
    <tbody>
        {folio_rows}
        <tr class="total-row">
            <td colspan="2" style="padding:10px 8px;">TOPLAM MASRAF</td>
            <td style="padding:10px 8px;text-align:right;">{currency}{grand_total:,.2f}</td>
        </tr>
    </tbody>
</table>

<h3 style="color:#1a56db;margin-bottom:8px;">Odemeler</h3>
<table>
    <thead><tr>
        <th>Odeme Yontemi</th>
        <th>Tarih</th>
        <th style="text-align:right;">Tutar</th>
    </tr></thead>
    <tbody>
        {payment_rows if payment_rows else '<tr><td colspan="3" style="padding:8px;text-align:center;color:#94a3b8;">Henuz odeme yok</td></tr>'}
        <tr class="total-row">
            <td colspan="2" style="padding:10px 8px;">TOPLAM ODEME</td>
            <td style="padding:10px 8px;text-align:right;">{currency}{total_payments:,.2f}</td>
        </tr>
    </tbody>
</table>

<table>
    <tr class="balance-row">
        <td colspan="2" style="padding:12px 8px;font-size:16px;">KALAN BAKIYE</td>
        <td style="padding:12px 8px;text-align:right;font-size:16px;">{currency}{balance:,.2f}</td>
    </tr>
</table>

<div class="footer">
    {settings.get("invoice_footer", "") or "Bizi tercih ettiginiz icin tesekkur ederiz."}
    <br><br>
    {settings.get("hotel_name","")} | {settings.get("hotel_address","")} | {settings.get("hotel_phone","")}
</div>

</body></html>"""

    return {
        "success": True,
        "invoice_html": html,
        "invoice_number": invoice_number,
        "booking_id": booking_id,
        "guest_name": guest_name,
        "total_charges": grand_total,
        "total_payments": total_payments,
        "balance": balance,
    }


# ═══════════════════════════════════════════════════
# 6. GROUP FOLIO MERGING
# ═══════════════════════════════════════════════════

class GroupFolioMerge(BaseModel):
    group_id: str
    master_booking_id: str
    merge_booking_ids: List[str]
    merge_payments: bool = True


@router.post("/group-folio/merge")
async def merge_group_folios(
    data: GroupFolioMerge,
    current_user: User = Depends(get_current_user),
):
    """Merge multiple folios from a group into a master folio."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    # Verify master booking exists
    master = await db.bookings.find_one({"id": data.master_booking_id, "tenant_id": tid}, {"_id": 0})
    if not master:
        raise HTTPException(status_code=404, detail="Ana rezervasyon bulunamadi")

    merged_entries = []
    merged_payments = []
    total_transferred = 0

    for bid in data.merge_booking_ids:
        if bid == data.master_booking_id:
            continue

        source_booking = await db.bookings.find_one({"id": bid, "tenant_id": tid}, {"_id": 0})
        if not source_booking:
            continue

        # Transfer folio entries
        async for folio in db.folios.find({"booking_id": bid, "tenant_id": tid}, {"_id": 0}):
            new_entry = {
                "id": str(uuid.uuid4()),
                "tenant_id": tid,
                "booking_id": data.master_booking_id,
                "original_booking_id": bid,
                "description": f"[Oda {source_booking.get('room_number', '?')}] {folio.get('description', '')}",
                "category": folio.get("category", "transfer"),
                "amount": folio.get("amount", 0),
                "type": folio.get("type", "charge"),
                "merged_from": bid,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "merged_at": datetime.now(timezone.utc).isoformat(),
            }
            await db.folios.insert_one(new_entry)
            new_entry.pop("_id", None)
            merged_entries.append(new_entry)
            total_transferred += folio.get("amount", 0)

        # Transfer payments if requested
        if data.merge_payments:
            async for payment in db.payments.find({"booking_id": bid, "tenant_id": tid}, {"_id": 0}):
                new_payment = {
                    "id": str(uuid.uuid4()),
                    "tenant_id": tid,
                    "booking_id": data.master_booking_id,
                    "original_booking_id": bid,
                    "amount": payment.get("amount", 0),
                    "method": payment.get("method", "transfer"),
                    "payment_type": "transfer",
                    "reference": f"Grup birlestirme - Oda {source_booking.get('room_number', '?')}",
                    "merged_from": bid,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
                await db.payments.insert_one(new_payment)
                new_payment.pop("_id", None)
                merged_payments.append(new_payment)

        # Mark source booking folio as merged
        await db.bookings.update_one(
            {"id": bid, "tenant_id": tid},
            {"$set": {"folio_merged_to": data.master_booking_id, "folio_merged_at": datetime.now(timezone.utc).isoformat()}}
        )

    # Log the merge
    merge_log = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "group_id": data.group_id,
        "master_booking_id": data.master_booking_id,
        "merged_booking_ids": data.merge_booking_ids,
        "total_entries_merged": len(merged_entries),
        "total_payments_merged": len(merged_payments),
        "total_amount_transferred": total_transferred,
        "merged_by": current_user.name,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.folio_merge_logs.insert_one(merge_log)
    merge_log.pop("_id", None)

    return {
        "success": True,
        "merge_log": merge_log,
        "merged_entries_count": len(merged_entries),
        "merged_payments_count": len(merged_payments),
    }


@router.get("/group-folio/{group_id}")
async def get_group_folio_status(
    group_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get folio status for a group booking."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    # Get group
    group = await db.group_bookings.find_one({"id": group_id, "tenant_id": tid}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadi")

    booking_ids = group.get("booking_ids", [])
    bookings_data = []

    for bid in booking_ids:
        booking = await db.bookings.find_one({"id": bid, "tenant_id": tid}, {"_id": 0})
        if not booking:
            continue

        # Get folio summary
        folio_total = 0
        async for f in db.folios.find({"booking_id": bid, "tenant_id": tid}, {"_id": 0}):
            if f.get("type") != "payment":
                folio_total += f.get("amount", 0)

        payment_total = 0
        async for p in db.payments.find({"booking_id": bid, "tenant_id": tid}, {"_id": 0}):
            payment_total += p.get("amount", 0)

        bookings_data.append({
            "booking_id": bid,
            "guest_name": booking.get("guest_name", "-"),
            "room_number": booking.get("room_number", "-"),
            "accommodation_total": booking.get("total_amount", 0),
            "folio_charges": folio_total,
            "payments": payment_total,
            "balance": booking.get("total_amount", 0) + folio_total - payment_total,
            "folio_merged_to": booking.get("folio_merged_to"),
        })

    # Check merge logs
    merge_logs = []
    async for log in db.folio_merge_logs.find({"group_id": group_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", -1):
        merge_logs.append(log)

    return {
        "group": group,
        "bookings": bookings_data,
        "merge_logs": merge_logs,
    }
