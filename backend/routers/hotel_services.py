"""
Hotel Services Router - Housekeeping Status, Wake-up Calls, Lost & Found,
Hotel Settings (logo/template), Group Folio Merging, PDF Invoice Generation
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

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
    notes: str | None = None
    priority: str | None = "normal"  # low, normal, high, urgent


@router.get("/housekeeping/rooms")
async def get_housekeeping_rooms(
    status_filter: str | None = None,
    floor: str | None = None,
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
        "housekeeping_updated_at": datetime.now(UTC).isoformat(),
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
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.housekeeping_log.insert_one(log_entry)
    log_entry.pop("_id", None)

    return {"success": True, "room_id": room_id, "new_status": data.status}


@router.put("/housekeeping/rooms/bulk-status")
async def bulk_update_room_status(
    room_ids: list[str] = [],
    status: str = "clean",
    current_user: User = Depends(get_current_user),
):
    """Bulk update housekeeping status for multiple rooms."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    now = datetime.now(UTC).isoformat()
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


@router.get("/wake-up-calls")
async def get_wake_up_calls(
    date: str | None = None,
    status: str | None = None,
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
    today = datetime.now(UTC).strftime("%Y-%m-%d")
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
        "created_at": datetime.now(UTC).isoformat(),
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
            updates["completed_at"] = datetime.now(UTC).isoformat()
            updates["completed_by"] = data.completed_by or current_user.name
    if data.notes is not None:
        updates["notes"] = data.notes
    if data.attempt_count is not None:
        updates["attempt_count"] = data.attempt_count
    if data.response:
        updates["response"] = data.response

    updates["updated_at"] = datetime.now(UTC).isoformat()

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


@router.get("/lost-found")
async def get_lost_found_items(
    status: str | None = None,
    category: str | None = None,
    search: str | None = None,
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
        "created_at": datetime.now(UTC).isoformat(),
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

    updates = {"updated_at": datetime.now(UTC).isoformat()}
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

    updates = {"updated_at": datetime.now(UTC).isoformat()}
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


@router.put("/hotel-settings")
async def update_hotel_settings(
    data: HotelSettingsUpdate,
    current_user: User = Depends(get_current_user),
):
    """Update hotel settings."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    updates = {"tenant_id": tid, "updated_at": datetime.now(UTC).isoformat()}
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
    invoice_number = f"INV-{datetime.now(UTC).strftime('%Y%m%d')}-{booking_id[:8].upper()}"

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
    Tarih: <strong>{datetime.now(UTC).strftime("%d.%m.%Y")}</strong>
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
    merge_booking_ids: list[str]
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
                "created_at": datetime.now(UTC).isoformat(),
                "merged_at": datetime.now(UTC).isoformat(),
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
                    "created_at": datetime.now(UTC).isoformat(),
                }
                await db.payments.insert_one(new_payment)
                new_payment.pop("_id", None)
                merged_payments.append(new_payment)

        # Mark source booking folio as merged
        await db.bookings.update_one(
            {"id": bid, "tenant_id": tid},
            {"$set": {"folio_merged_to": data.master_booking_id, "folio_merged_at": datetime.now(UTC).isoformat()}}
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
        "created_at": datetime.now(UTC).isoformat(),
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



# ═══════════════════════════════════════════════════
# 7. GROUP FOLIO - BOOKING DETAIL & GROUP PAYMENT
# ═══════════════════════════════════════════════════

@router.get("/group-folio/{group_id}/booking/{booking_id}")
async def get_group_booking_folio_detail(
    group_id: str,
    booking_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get detailed folio line items for a booking within a group."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    charges = []
    async for c in db.folio_charges.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}):
        charges.append(c)

    folios = []
    async for f in db.folios.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}):
        folios.append(f)

    payments = []
    async for p in db.payments.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}):
        payments.append(p)

    extra_charges = []
    async for ec in db.extra_charges.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}):
        extra_charges.append(ec)

    return {
        "booking_id": booking_id,
        "guest_name": booking.get("guest_name", "-"),
        "room_number": booking.get("room_number", "-"),
        "check_in": booking.get("check_in"),
        "check_out": booking.get("check_out"),
        "status": booking.get("status", "confirmed"),
        "total_amount": booking.get("total_amount", 0),
        "charges": charges,
        "folios": folios,
        "payments": payments,
        "extra_charges": extra_charges,
    }


class GroupPaymentRequest(BaseModel):
    group_id: str
    booking_id: str
    amount: float
    method: str = "cash"
    reference: str = ""


@router.post("/group-folio/payment")
async def record_group_payment(
    data: GroupPaymentRequest,
    current_user: User = Depends(get_current_user),
):
    """Record a payment for a booking within a group."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": data.booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    payment = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": data.booking_id,
        "amount": data.amount,
        "method": data.method,
        "payment_type": "group_payment",
        "reference": data.reference or f"Grup odeme - {data.group_id[:8]}",
        "recorded_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.payments.insert_one(payment)
    payment.pop("_id", None)

    return {"success": True, "payment": payment}



class GroupBulkPaymentRequest(BaseModel):
    group_id: str
    total_amount: float
    method: str = "cash"
    reference: str = ""
    distribution: str = "proportional"  # proportional | equal | balance_only


@router.post("/group-folio/bulk-payment")
async def record_group_bulk_payment(
    data: GroupBulkPaymentRequest,
    current_user: User = Depends(get_current_user),
):
    """Record a bulk payment distributed across all active bookings in a group."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    group = await db.group_bookings.find_one({"id": data.group_id, "tenant_id": tid}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadi")

    # Collect active (unmerged) bookings with positive balances
    active_bookings = []
    for bid in group.get("booking_ids", []):
        booking = await db.bookings.find_one({"id": bid, "tenant_id": tid}, {"_id": 0})
        if not booking or booking.get("folio_merged_to"):
            continue

        folio_total = 0
        async for f in db.folios.find({"booking_id": bid, "tenant_id": tid}, {"_id": 0}):
            if f.get("type") != "payment":
                folio_total += f.get("amount", 0)
        payment_total = 0
        async for p in db.payments.find({"booking_id": bid, "tenant_id": tid}, {"_id": 0}):
            payment_total += p.get("amount", 0)

        balance = booking.get("total_amount", 0) + folio_total - payment_total
        active_bookings.append({
            "booking_id": bid,
            "guest_name": booking.get("guest_name", "-"),
            "room_number": booking.get("room_number", "-"),
            "balance": balance,
        })

    if not active_bookings:
        raise HTTPException(status_code=400, detail="Aktif rezervasyon bulunamadi")

    # Calculate distribution
    total_positive_balance = sum(max(b["balance"], 0) for b in active_bookings)
    remaining = data.total_amount
    payments_created = []

    for i, ab in enumerate(active_bookings):
        if remaining <= 0:
            break

        if data.distribution == "equal":
            share = round(data.total_amount / len(active_bookings), 2)
        elif data.distribution == "balance_only":
            if ab["balance"] <= 0:
                continue
            share = min(ab["balance"], remaining)
        else:  # proportional
            if total_positive_balance > 0 and ab["balance"] > 0:
                share = round(data.total_amount * (ab["balance"] / total_positive_balance), 2)
            else:
                share = round(data.total_amount / len(active_bookings), 2)

        # Last booking gets the remainder to avoid rounding issues
        if i == len(active_bookings) - 1 and data.distribution != "balance_only":
            share = remaining

        share = min(share, remaining)
        if share <= 0:
            continue

        payment = {
            "id": str(uuid.uuid4()),
            "tenant_id": tid,
            "booking_id": ab["booking_id"],
            "amount": share,
            "method": data.method,
            "payment_type": "group_bulk_payment",
            "reference": data.reference or f"Toplu grup odeme - Oda {ab['room_number']}",
            "recorded_by": current_user.name,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db.payments.insert_one(payment)
        payment.pop("_id", None)
        payments_created.append({**payment, "guest_name": ab["guest_name"]})
        remaining = round(remaining - share, 2)

    return {
        "success": True,
        "total_distributed": round(data.total_amount - remaining, 2),
        "payments_count": len(payments_created),
        "payments": payments_created,
    }



@router.get("/group-folio-summary")
async def get_group_folio_summary(
    current_user: User = Depends(get_current_user),
):
    """Get summary statistics for all group folios."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    groups = []
    async for g in db.group_bookings.find({"tenant_id": tid}, {"_id": 0}):
        groups.append(g)

    total_groups = len(groups)
    total_bookings = sum(len(g.get("booking_ids", [])) for g in groups)
    active_groups = sum(1 for g in groups if g.get("status") == "active")

    total_balance = 0
    merged_count = 0
    for g in groups:
        for bid in g.get("booking_ids", []):
            booking = await db.bookings.find_one({"id": bid, "tenant_id": tid}, {"_id": 0})
            if not booking:
                continue
            if booking.get("folio_merged_to"):
                merged_count += 1

            folio_total = 0
            async for f in db.folios.find({"booking_id": bid, "tenant_id": tid}, {"_id": 0}):
                if f.get("type") != "payment":
                    folio_total += f.get("amount", 0)
            payment_total = 0
            async for p in db.payments.find({"booking_id": bid, "tenant_id": tid}, {"_id": 0}):
                payment_total += p.get("amount", 0)
            total_balance += booking.get("total_amount", 0) + folio_total - payment_total

    merge_log_count = await db.folio_merge_logs.count_documents({"tenant_id": tid})

    return {
        "total_groups": total_groups,
        "active_groups": active_groups,
        "total_bookings": total_bookings,
        "total_balance": total_balance,
        "merged_folios": merged_count,
        "merge_operations": merge_log_count,
    }



# ═══════════════════════════════════════════════════
# 10. RESERVATION CANCELLATION
# ═══════════════════════════════════════════════════

class CancelReservationRequest(BaseModel):
    reason: str
    cancel_type: str = "guest_request"
    apply_noshow: bool = False
    noshow_charge_type: str | None = None
    noshow_charge_amount: float | None = None


@router.post("/reservations/{booking_id}/cancel")
async def cancel_reservation(
    booking_id: str,
    body: CancelReservationRequest,
    current_user: User = Depends(get_current_user),
):
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    update_data = {
        "status": "no_show" if body.apply_noshow else "cancelled",
        "cancelled_at": datetime.now(UTC).isoformat(),
        "cancellation_reason": body.reason,
        "cancel_type": body.cancel_type,
    }

    if body.apply_noshow and body.noshow_charge_amount and body.noshow_charge_amount > 0:
        charge_id = str(uuid.uuid4())
        await db.folios.insert_one({
            "id": charge_id,
            "tenant_id": tid,
            "booking_id": booking_id,
            "type": "charge",
            "category": "no_show",
            "description": f"No-Show Ucreti ({body.noshow_charge_type or 'ozel'})",
            "amount": body.noshow_charge_amount,
            "created_at": datetime.now(UTC).isoformat(),
            "created_by": current_user.name,
        })
        update_data["noshow_charge"] = body.noshow_charge_amount

    await db.bookings.update_one({"id": booking_id, "tenant_id": tid}, {"$set": update_data})

    await db.reservation_history.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": booking_id,
        "action": "cancelled" if not body.apply_noshow else "marked_noshow",
        "actor": current_user.name,
        "details": {
            "reason": body.reason,
            "cancel_type": body.cancel_type,
            "noshow": body.apply_noshow,
            "noshow_charge": body.noshow_charge_amount if body.apply_noshow else None,
        },
        "created_at": datetime.now(UTC).isoformat(),
    })

    return {"success": True, "status": update_data["status"], "message": "Rezervasyon iptal edildi"}


# ═══════════════════════════════════════════════════
# 11. VOUCHER GENERATION
# ═══════════════════════════════════════════════════

@router.get("/reservations/{booking_id}/voucher")
async def generate_voucher(
    booking_id: str,
    current_user: User = Depends(get_current_user),
):
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    guest = None
    if booking.get("guest_id"):
        guest = await db.guests.find_one({"id": booking["guest_id"], "tenant_id": tid}, {"_id": 0})

    room = None
    if booking.get("room_id"):
        room = await db.rooms.find_one({"id": booking["room_id"], "tenant_id": tid}, {"_id": 0})

    settings = await db.hotel_settings.find_one({"tenant_id": tid}, {"_id": 0})
    if not settings:
        tenant = await db.tenants.find_one({"tenant_id": tid}, {"_id": 0})
        settings = {
            "hotel_name": tenant.get("property_name", "Hotel") if tenant else "Hotel",
            "hotel_address": tenant.get("address", "") if tenant else "",
            "hotel_phone": tenant.get("phone", "") if tenant else "",
            "hotel_email": tenant.get("email", "") if tenant else "",
        }

    guest_name = guest.get("name", booking.get("guest_name", "-")) if guest else booking.get("guest_name", "-")
    nights = max(1, (datetime.fromisoformat(str(booking.get("check_out", ""))[:10]) - datetime.fromisoformat(str(booking.get("check_in", ""))[:10])).days)

    voucher_no = f"V-{datetime.now(UTC).strftime('%Y%m%d')}-{booking_id[:8].upper()}"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; margin:0; padding:40px; color:#333; font-size:13px; }}
.voucher {{ border: 2px solid #1a56db; border-radius: 12px; padding: 32px; max-width: 700px; margin: 0 auto; }}
.header {{ text-align: center; border-bottom: 2px solid #1a56db; padding-bottom: 16px; margin-bottom: 24px; }}
.hotel-name {{ font-size: 24px; font-weight: 700; color: #1a56db; }}
.voucher-title {{ font-size: 20px; font-weight: 600; color: #1e293b; margin-top: 8px; }}
.voucher-no {{ font-size: 12px; color: #64748b; margin-top: 4px; }}
.info-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }}
.info-item {{ padding: 12px; background: #f8fafc; border-radius: 8px; }}
.info-label {{ font-size: 11px; color: #64748b; text-transform: uppercase; font-weight: 600; }}
.info-value {{ font-size: 14px; font-weight: 600; color: #1e293b; margin-top: 4px; }}
.footer {{ text-align: center; margin-top: 24px; padding-top: 16px; border-top: 1px solid #e2e8f0; color: #94a3b8; font-size: 11px; }}
</style></head><body>
<div class="voucher">
    <div class="header">
        <div class="hotel-name">{settings.get("hotel_name", "")}</div>
        <div style="font-size:12px;color:#64748b;">{settings.get("hotel_address", "")}</div>
        <div class="voucher-title">KONAKLAMA VOUCHER</div>
        <div class="voucher-no">Voucher No: {voucher_no}</div>
    </div>
    <div class="info-grid">
        <div class="info-item"><div class="info-label">Misafir</div><div class="info-value">{guest_name}</div></div>
        <div class="info-item"><div class="info-label">Rezervasyon No</div><div class="info-value">{booking.get("ota_confirmation", booking_id[:12])}</div></div>
        <div class="info-item"><div class="info-label">Giris Tarihi</div><div class="info-value">{str(booking.get("check_in",""))[:10]}</div></div>
        <div class="info-item"><div class="info-label">Cikis Tarihi</div><div class="info-value">{str(booking.get("check_out",""))[:10]}</div></div>
        <div class="info-item"><div class="info-label">Oda / Tip</div><div class="info-value">{booking.get("room_number", room.get("room_number","-") if room else "-")} / {room.get("room_type","") if room else booking.get("room_type","")}</div></div>
        <div class="info-item"><div class="info-label">Gece Sayisi</div><div class="info-value">{nights}</div></div>
        <div class="info-item"><div class="info-label">Yetiskin / Cocuk</div><div class="info-value">{booking.get("adults",1)} / {booking.get("children",0)}</div></div>
        <div class="info-item"><div class="info-label">Pansiyon</div><div class="info-value">{booking.get("rate_plan","Standart")}</div></div>
    </div>
    {f'<div style="padding:12px;background:#fffbeb;border-radius:8px;margin-bottom:16px;"><strong>Ozel Istekler:</strong> {booking.get("special_requests","")}</div>' if booking.get("special_requests") else ''}
    <div class="footer">
        <div>Bu voucher {settings.get("hotel_name","")} tarafindan duzenlenmistir.</div>
        <div>{settings.get("hotel_phone","")} | {settings.get("hotel_email","")}</div>
        <div style="margin-top:8px;">Tarih: {datetime.now(UTC).strftime("%d.%m.%Y %H:%M")}</div>
    </div>
</div>
</body></html>"""

    return {"success": True, "voucher_html": html, "voucher_no": voucher_no}


# ═══════════════════════════════════════════════════
# 12. ADVANCED INVOICE WITH ITEM SELECTION
# ═══════════════════════════════════════════════════

class InvoiceItemSelection(BaseModel):
    selected_charge_ids: list[str] = []
    billing_name: str | None = None
    billing_tax_id: str | None = None
    billing_tax_office: str | None = None
    billing_address: str | None = None
    billing_email: str | None = None
    invoice_note: str | None = None


@router.post("/reservations/{booking_id}/generate-invoice")
async def generate_custom_invoice(
    booking_id: str,
    body: InvoiceItemSelection,
    current_user: User = Depends(get_current_user),
):
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    guest = None
    if booking.get("guest_id"):
        guest = await db.guests.find_one({"id": booking["guest_id"], "tenant_id": tid}, {"_id": 0})

    settings = await db.hotel_settings.find_one({"tenant_id": tid}, {"_id": 0})
    if not settings:
        tenant = await db.tenants.find_one({"tenant_id": tid}, {"_id": 0})
        settings = {
            "hotel_name": tenant.get("property_name", "Hotel") if tenant else "Hotel",
            "hotel_address": tenant.get("address", "") if tenant else "",
            "hotel_phone": tenant.get("phone", "") if tenant else "",
            "hotel_email": tenant.get("email", "") if tenant else "",
            "tax_id": "", "tax_office": "", "currency_symbol": "₺", "invoice_footer": "",
        }

    all_charges = []
    if booking.get("total_amount", 0) > 0:
        all_charges.append({
            "id": "accommodation",
            "description": "Konaklama",
            "date": str(booking.get("check_in", ""))[:10],
            "amount": booking["total_amount"],
            "category": "room",
        })

    async for f in db.folios.find({"booking_id": booking_id, "tenant_id": tid, "type": {"$ne": "payment"}}, {"_id": 0}).sort("created_at", 1):
        all_charges.append({
            "id": f.get("id", ""),
            "description": f.get("description", f.get("category", "Masraf")),
            "date": str(f.get("created_at", ""))[:10],
            "amount": f.get("amount", 0),
            "category": f.get("category", "other"),
        })

    async for ec in db.extra_charges.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", 1):
        all_charges.append({
            "id": ec.get("id", ""),
            "description": ec.get("description", "Ekstra"),
            "date": str(ec.get("created_at", ""))[:10],
            "amount": ec.get("total", ec.get("amount", 0)),
            "category": ec.get("category", "other"),
        })

    if body.selected_charge_ids:
        selected = [c for c in all_charges if c["id"] in body.selected_charge_ids]
    else:
        selected = all_charges

    currency = settings.get("currency_symbol", "₺")
    grand_total = sum(c["amount"] for c in selected)
    invoice_number = f"INV-{datetime.now(UTC).strftime('%Y%m%d%H%M')}-{booking_id[:6].upper()}"

    guest_name = body.billing_name or (guest.get("name", booking.get("guest_name", "-")) if guest else booking.get("guest_name", "-"))

    charge_rows = ""
    for c in selected:
        charge_rows += f"""<tr>
            <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;">{c["description"]}</td>
            <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;text-align:center;">{c["date"]}</td>
            <td style="padding:10px 12px;border-bottom:1px solid #f1f5f9;text-align:right;font-weight:600;">{currency}{c["amount"]:,.2f}</td>
        </tr>"""

    logo_html = ""
    if settings.get("logo_data"):
        logo_html = f'<img src="{settings["logo_data"]}" style="max-height:70px;max-width:180px;" />'

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<style>
body {{ font-family: 'Segoe UI', Arial, sans-serif; margin:0; padding:0; color:#1e293b; font-size:13px; background:#fff; }}
.page {{ max-width:800px; margin:0 auto; padding:40px; }}
.header {{ display:flex; justify-content:space-between; align-items:flex-start; padding-bottom:24px; border-bottom:3px solid #1a56db; margin-bottom:28px; }}
.hotel-info {{ text-align:right; }}
.hotel-name {{ font-size:20px; font-weight:700; color:#1a56db; margin-bottom:4px; }}
.hotel-detail {{ font-size:11px; color:#64748b; line-height:1.6; }}
.invoice-badge {{ display:inline-block; background:linear-gradient(135deg,#1a56db,#3b82f6); color:#fff; padding:6px 16px; border-radius:6px; font-size:18px; font-weight:700; letter-spacing:1px; margin-bottom:12px; }}
.invoice-meta {{ color:#64748b; font-size:12px; line-height:1.8; }}
.invoice-meta strong {{ color:#1e293b; }}
.bill-grid {{ display:grid; grid-template-columns:1fr 1fr; gap:20px; margin-bottom:28px; }}
.bill-box {{ background:#f8fafc; border:1px solid #e2e8f0; border-radius:8px; padding:16px; }}
.bill-box h4 {{ margin:0 0 8px; font-size:11px; color:#64748b; text-transform:uppercase; letter-spacing:0.5px; font-weight:600; }}
.bill-box p {{ margin:2px 0; font-size:13px; }}
table {{ width:100%; border-collapse:collapse; margin-bottom:24px; }}
thead th {{ background:#f1f5f9; padding:10px 12px; text-align:left; font-weight:600; font-size:11px; color:#475569; text-transform:uppercase; letter-spacing:0.5px; }}
.total-section {{ background:#f0f9ff; border:2px solid #bfdbfe; border-radius:8px; padding:16px; text-align:right; }}
.total-section .grand {{ font-size:20px; font-weight:700; color:#1a56db; }}
.footer {{ margin-top:40px; padding-top:20px; border-top:2px solid #e2e8f0; text-align:center; color:#94a3b8; font-size:10px; line-height:1.8; }}
</style></head><body>
<div class="page">
    <div class="header">
        <div>{logo_html}<div class="invoice-badge">FATURA</div>
            <div class="invoice-meta">Fatura No: <strong>{invoice_number}</strong><br>Tarih: <strong>{datetime.now(UTC).strftime("%d.%m.%Y")}</strong></div>
        </div>
        <div class="hotel-info">
            <div class="hotel-name">{settings.get("hotel_name","")}</div>
            <div class="hotel-detail">
                {settings.get("hotel_address","")}<br>
                Tel: {settings.get("hotel_phone","")}<br>
                {settings.get("hotel_email","")}
                {f"<br>Vergi No: {settings.get('tax_id','')}" if settings.get("tax_id") else ""}
                {f"<br>V.D.: {settings.get('tax_office','')}" if settings.get("tax_office") else ""}
            </div>
        </div>
    </div>

    <div class="bill-grid">
        <div class="bill-box">
            <h4>Fatura Edilen</h4>
            <p><strong>{guest_name}</strong></p>
            {f"<p>Vergi No: {body.billing_tax_id}</p>" if body.billing_tax_id else ""}
            {f"<p>V.D.: {body.billing_tax_office}</p>" if body.billing_tax_office else ""}
            {f"<p>{body.billing_address}</p>" if body.billing_address else ""}
            {f"<p>{body.billing_email}</p>" if body.billing_email else ""}
        </div>
        <div class="bill-box">
            <h4>Konaklama Bilgileri</h4>
            <p>Oda: <strong>{booking.get("room_number","-")}</strong></p>
            <p>Giris: <strong>{str(booking.get("check_in",""))[:10]}</strong></p>
            <p>Cikis: <strong>{str(booking.get("check_out",""))[:10]}</strong></p>
            <p>Rez. No: <strong>{booking.get("ota_confirmation", booking_id[:12])}</strong></p>
        </div>
    </div>

    <table>
        <thead><tr><th>Aciklama</th><th style="text-align:center;">Tarih</th><th style="text-align:right;">Tutar</th></tr></thead>
        <tbody>{charge_rows}</tbody>
    </table>

    <div class="total-section">
        <div class="grand">TOPLAM: {currency}{grand_total:,.2f}</div>
    </div>

    {f'<div style="margin-top:16px;padding:12px;background:#fffbeb;border-radius:8px;font-size:12px;">{body.invoice_note}</div>' if body.invoice_note else ''}

    <div class="footer">
        {settings.get("invoice_footer", "") or "Bizi tercih ettiginiz icin tesekkur ederiz."}<br>
        {settings.get("hotel_name","")} | {settings.get("hotel_address","")} | {settings.get("hotel_phone","")}
    </div>
</div>
</body></html>"""

    await db.invoices.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": booking_id,
        "invoice_number": invoice_number,
        "billing_name": guest_name,
        "billing_tax_id": body.billing_tax_id,
        "total": grand_total,
        "item_count": len(selected),
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.name,
    })

    return {
        "success": True,
        "invoice_html": html,
        "invoice_number": invoice_number,
        "total": grand_total,
        "all_charges": all_charges,
    }


# ═══════════════════════════════════════════════════
# 13. GET INVOICE CHARGES (for frontend item selection)
# ═══════════════════════════════════════════════════

@router.get("/reservations/{booking_id}/invoice-charges")
async def get_invoice_charges(
    booking_id: str,
    current_user: User = Depends(get_current_user),
):
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    charges = []
    if booking.get("total_amount", 0) > 0:
        charges.append({
            "id": "accommodation",
            "description": "Konaklama",
            "category": "room",
            "amount": booking["total_amount"],
            "date": str(booking.get("check_in", ""))[:10],
        })

    async for f in db.folios.find({"booking_id": booking_id, "tenant_id": tid, "type": {"$ne": "payment"}}, {"_id": 0}).sort("created_at", 1):
        charges.append({
            "id": f.get("id", ""),
            "description": f.get("description", f.get("category", "Masraf")),
            "category": f.get("category", "other"),
            "amount": f.get("amount", 0),
            "date": str(f.get("created_at", ""))[:10],
        })

    async for ec in db.extra_charges.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", 1):
        charges.append({
            "id": ec.get("id", ""),
            "description": ec.get("description", "Ekstra"),
            "category": ec.get("category", "other"),
            "amount": ec.get("total", ec.get("amount", 0)),
            "date": str(ec.get("created_at", ""))[:10],
        })

    return {"charges": charges}


# ═══════════════════════════════════════════════════
# 14. ROOM CHANGE WITH ROOM TYPE FILTER AND PRICING
# ═══════════════════════════════════════════════════

@router.get("/available-rooms-by-type")
async def get_available_rooms_by_type(
    check_in: str,
    check_out: str,
    current_user: User = Depends(get_current_user),
):
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    all_rooms = []
    async for r in db.rooms.find({"tenant_id": tid, "is_active": True}, {"_id": 0}).sort("room_number", 1):
        all_rooms.append(r)

    conflicting_room_ids = set()
    async for b in db.bookings.find({
        "tenant_id": tid,
        "status": {"$nin": ["cancelled", "checked_out", "no_show"]},
        "check_in": {"$lt": check_out},
        "check_out": {"$gt": check_in},
    }, {"_id": 0, "room_id": 1}):
        if b.get("room_id"):
            conflicting_room_ids.add(b["room_id"])

    room_types = {}
    for r in all_rooms:
        rt = r.get("room_type", "Standard")
        if rt not in room_types:
            room_types[rt] = {"type": rt, "rooms": [], "base_price": r.get("base_price", 0)}
        is_available = r["id"] not in conflicting_room_ids
        room_types[rt]["rooms"].append({**r, "is_available": is_available})

    return {"room_types": list(room_types.values())}


# ═══════════════════════════════════════════════════
# 15. CREATE CARI ACCOUNT
# ═══════════════════════════════════════════════════

class CreateCariAccount(BaseModel):
    name: str
    account_type: str = "agency"
    tax_id: str | None = None
    tax_office: str | None = None
    address: str | None = None
    phone: str | None = None
    email: str | None = None


@router.post("/cari-accounts/create")
async def create_cari_account(
    body: CreateCariAccount,
    current_user: User = Depends(get_current_user),
):
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    account_id = str(uuid.uuid4())
    account = {
        "id": account_id,
        "tenant_id": tid,
        "name": body.name,
        "account_type": body.account_type,
        "tax_id": body.tax_id,
        "tax_office": body.tax_office,
        "address": body.address,
        "phone": body.phone,
        "email": body.email,
        "balance": 0,
        "is_active": True,
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.name,
    }
    await db.cari_accounts.insert_one(account)
    account.pop("_id", None)

    return {"success": True, "account": account}
