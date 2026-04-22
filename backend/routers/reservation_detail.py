"""
Reservation Detail Router - Comprehensive reservation management endpoints
Provides full reservation detail view, folio operations, activity logging,
payment processing, cari transfers, room changes, and front office operations.
"""
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from core.database import db
from core.security import get_current_user
from models.schemas import User, _ensure_hotel_context
from models.schemas.bookings import BookingCreate
from modules.reservations.services.create_reservation_service import (
    CreateReservationService,
)

_create_reservation_service = CreateReservationService()


def _request_with_idempotency_key(req: Request, key: str) -> Request:
    """Aynı HTTP isteği içinde N alt-rezervasyon yaratırken her birine
    benzersiz Idempotency-Key enjekte eden ince sarmalayıcı."""
    headers = [
        (k, v) for k, v in req.scope["headers"]
        if k.lower() != b"idempotency-key"
    ]
    headers.append((b"idempotency-key", key.encode()))
    new_scope = {**req.scope, "headers": headers}
    return Request(new_scope, req.receive)

router = APIRouter(prefix="/api/pms", tags=["reservation-detail"])


# ── Request/Response Models ──

class PaymentRecord(BaseModel):
    amount: float
    method: str  # cash, card, bank_transfer, online
    payment_type: str = "interim"  # prepayment, deposit, interim, final
    reference: str | None = None
    notes: str | None = None


class CariTransfer(BaseModel):
    amount: float
    cari_account_id: str
    description: str | None = None


class AgencyPaymentRecord(BaseModel):
    amount: float
    agency_name: str | None = None
    reference: str | None = None
    notes: str | None = None


class ChargeSplit(BaseModel):
    charge_id: str
    target_folio_id: str | None = None
    target_booking_id: str | None = None
    split_amount: float
    reason: str | None = None


class NoteCreate(BaseModel):
    content: str
    note_type: str = "general"  # general, important, internal, guest_request


class RoomChangeRequest(BaseModel):
    new_room_id: str
    reason: str
    transfer_folio: bool = True


class EarlyCheckinRequest(BaseModel):
    checkin_time: str | None = None
    extra_charge: float = 0.0


class LateCheckoutRequest(BaseModel):
    checkout_time: str | None = None
    extra_charge: float = 0.0


class DepositRecord(BaseModel):
    amount: float
    method: str = "cash"
    reference: str | None = None


class DailyRateUpdate(BaseModel):
    rates: list[dict[str, Any]]  # [{date: "2026-03-18", rate: 450.0}, ...]


class CariAccountCreate(BaseModel):
    name: str
    account_type: str = "company"  # company, agency, individual
    company_id: str | None = None
    contact_person: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    credit_limit: float = 0.0
    payment_terms_days: int = 30


class ExtraChargeAdd(BaseModel):
    description: str
    category: str = "other"  # room, food, beverage, minibar, spa, laundry, other
    amount: float
    quantity: float = 1.0


class GuestUpdate(BaseModel):
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    id_number: str | None = None
    nationality: str | None = None
    vip_status: bool | None = None


class NewGroupBookingRow(BaseModel):
    """Grup oluştururken aynı anda yaratılacak yeni rezervasyon."""
    guest_name: str
    room_id: str
    check_in: str
    check_out: str
    total_amount: float
    adults: int = 1
    children: int = 0


class GroupBookingCreate(BaseModel):
    group_name: str
    booking_ids: list[str] = []
    # Yeni: aynı dialog'tan toplu rezervasyon yaratıp gruba bağlama
    new_bookings: list[NewGroupBookingRow] = []


class GroupBookingAddRoom(BaseModel):
    booking_id: str


class CommunicationLogCreate(BaseModel):
    channel: str = "email"  # email, sms, phone, whatsapp
    direction: str = "outbound"  # inbound, outbound
    subject: str | None = None
    content: str
    recipient: str | None = None


class DepositRefund(BaseModel):
    deposit_id: str
    refund_amount: float
    refund_method: str = "cash"
    reason: str | None = None


# ── Helper ──

def _clean_doc(doc):
    """Remove MongoDB _id from document."""
    if doc and "_id" in doc:
        del doc["_id"]
    return doc


def _clean_docs(docs):
    """Remove MongoDB _id from list of documents."""
    return [_clean_doc(d) for d in docs]


async def _log_activity(tenant_id: str, booking_id: str, action: str, actor: str, details: dict = None):
    """Log an activity for a reservation."""
    log_entry = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "booking_id": booking_id,
        "action": action,
        "actor": actor,
        "details": details or {},
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.reservation_activity_log.insert_one(log_entry)
    return log_entry


# ── Endpoints ──

@router.get("/reservations/{booking_id}/full-detail")
async def get_reservation_full_detail(
    booking_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get comprehensive reservation detail with all related data."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

    # Fetch related data in parallel-like fashion
    guest = None
    if booking.get("guest_id"):
        guest = await db.guests.find_one({"id": booking["guest_id"], "tenant_id": tid}, {"_id": 0})

    room = None
    if booking.get("room_id"):
        room = await db.rooms.find_one({"id": booking["room_id"], "tenant_id": tid}, {"_id": 0})

    # Folios
    folios = []
    async for f in db.folios.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}):
        folios.append(f)

    # Charges per folio
    charges = []
    async for c in db.folio_charges.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}):
        charges.append(c)

    # Payments per folio
    payments = []
    async for p in db.payments.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}):
        payments.append(p)

    # Extra charges
    extra_charges = []
    async for ec in db.extra_charges.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}):
        extra_charges.append(ec)

    # Notes
    notes = []
    async for n in db.reservation_notes.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", -1):
        notes.append(n)

    # Activity log / history
    history = []
    async for h in db.reservation_activity_log.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", -1):
        history.append(h)

    # Room move history
    room_moves = []
    async for rm in db.room_move_history.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("moved_at", -1):
        room_moves.append(rm)

    # Daily rates
    daily_rates = []
    async for dr in db.daily_rates.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("date", 1):
        daily_rates.append(dr)

    # If no daily rates exist, generate from booking
    if not daily_rates and booking.get("check_in") and booking.get("check_out"):
        ci = booking["check_in"]
        co = booking["check_out"]
        if isinstance(ci, str):
            ci = datetime.fromisoformat(ci.replace("Z", "+00:00")) if "T" in ci else datetime.strptime(ci[:10], "%Y-%m-%d")
        if isinstance(co, str):
            co = datetime.fromisoformat(co.replace("Z", "+00:00")) if "T" in co else datetime.strptime(co[:10], "%Y-%m-%d")
        nights = max((co - ci).days, 1)
        nightly_rate = round(booking.get("total_amount", 0) / nights, 2) if nights > 0 else 0
        current = ci
        for i in range(nights):
            daily_rates.append({
                "date": current.strftime("%Y-%m-%d") if hasattr(current, "strftime") else str(current)[:10],
                "rate": nightly_rate,
                "generated": True,
            })
            current = current + timedelta(days=1)

    # Guests associated with this booking
    guests_list = []
    if guest:
        guests_list.append(guest)
    # Also check for additional guests
    async for ag in db.booking_guests.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}):
        guests_list.append(ag)

    # Company info
    company = None
    if booking.get("company_id"):
        company = await db.companies.find_one({"id": booking["company_id"], "tenant_id": tid}, {"_id": 0})

    # Communication logs
    communication_logs = []
    async for cl in db.communication_logs.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", -1):
        communication_logs.append(cl)

    # Deposits
    deposits = []
    async for dep in db.deposits.find({"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}).sort("created_at", -1):
        deposits.append(dep)

    # Calculate totals
    total_charges = sum(c.get("total", c.get("amount", 0)) for c in charges if not c.get("voided"))
    total_payments = sum(p.get("amount", 0) for p in payments if not p.get("voided"))
    total_extra = sum(ec.get("charge_amount", ec.get("amount", 0)) for ec in extra_charges)
    total_deposits = sum(dep.get("amount", 0) for dep in deposits if dep.get("status") != "refunded")
    room_total = booking.get("total_amount", 0)
    balance = room_total + total_charges + total_extra - total_payments

    return {
        "booking": booking,
        "guest": guest,
        "room": room,
        "company": company,
        "folios": folios,
        "charges": charges,
        "payments": payments,
        "extra_charges": extra_charges,
        "notes": notes,
        "history": history,
        "room_moves": room_moves,
        "daily_rates": daily_rates,
        "guests": guests_list,
        "communication_logs": communication_logs,
        "deposits": deposits,
        "summary": {
            "total_amount": booking.get("total_amount", 0),
            "total_charges": round(total_charges, 2),
            "total_payments": round(total_payments, 2),
            "total_extra": round(total_extra, 2),
            "total_deposits": round(total_deposits, 2),
            "balance": round(balance, 2),
            "paid_amount": booking.get("paid_amount", 0),
        },
    }


@router.post("/reservations/{booking_id}/record-payment")
async def record_payment(
    booking_id: str,
    data: PaymentRecord,
    current_user: User = Depends(get_current_user),
):
    """Record a payment on the reservation's folio."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

    # Find or create folio
    folio = await db.folios.find_one({"booking_id": booking_id, "tenant_id": tid, "status": "open"}, {"_id": 0})
    if not folio:
        from core.utils import generate_folio_number
        folio_id = str(uuid.uuid4())
        folio = {
            "id": folio_id,
            "tenant_id": tid,
            "booking_id": booking_id,
            "folio_number": await generate_folio_number(tid),
            "folio_type": "guest",
            "status": "open",
            "guest_id": booking.get("guest_id"),
            "balance": 0.0,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db.folios.insert_one({**folio})

    payment = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "folio_id": folio["id"],
        "booking_id": booking_id,
        "amount": data.amount,
        "method": data.method,
        "payment_type": data.payment_type,
        "status": "paid",
        "reference": data.reference,
        "notes": data.notes,
        "processed_by": current_user.name,
        "processed_at": datetime.now(UTC).isoformat(),
        "voided": False,
    }
    await db.payments.insert_one({**payment})

    # Update booking paid_amount
    new_paid = (booking.get("paid_amount", 0) or 0) + data.amount
    await db.bookings.update_one(
        {"id": booking_id, "tenant_id": tid},
        {"$set": {"paid_amount": round(new_paid, 2)}},
    )

    await _log_activity(tid, booking_id, "payment_recorded", current_user.name, {
        "amount": data.amount, "method": data.method, "payment_type": data.payment_type,
    })

    payment.pop("_id", None)
    return {"success": True, "payment": payment}


@router.post("/reservations/{booking_id}/transfer-to-cari")
async def transfer_to_cari(
    booking_id: str,
    data: CariTransfer,
    current_user: User = Depends(get_current_user),
):
    """Transfer an amount from reservation folio to a cari (account receivable) account."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

    cari = await db.cari_accounts.find_one({"id": data.cari_account_id, "tenant_id": tid}, {"_id": 0})
    if not cari:
        raise HTTPException(status_code=404, detail="Cari hesap bulunamadı")

    # Create cari transaction
    transaction = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "cari_account_id": data.cari_account_id,
        "booking_id": booking_id,
        "transaction_type": "charge",
        "amount": data.amount,
        "description": data.description or f"Rezervasyon {booking_id} - Cariye aktarım",
        "posted_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.cari_transactions.insert_one({**transaction})

    # Update cari balance
    await db.cari_accounts.update_one(
        {"id": data.cari_account_id, "tenant_id": tid},
        {"$inc": {"current_balance": data.amount}},
    )

    # Mark as paid on the booking side (transferred to cari)
    new_paid = (booking.get("paid_amount", 0) or 0) + data.amount
    await db.bookings.update_one(
        {"id": booking_id, "tenant_id": tid},
        {"$set": {"paid_amount": round(new_paid, 2)}},
    )

    await _log_activity(tid, booking_id, "transferred_to_cari", current_user.name, {
        "amount": data.amount, "cari_account": cari.get("name"), "cari_account_id": data.cari_account_id,
    })

    transaction.pop("_id", None)
    return {"success": True, "transaction": transaction}


@router.post("/reservations/{booking_id}/record-agency-payment")
async def record_agency_payment(
    booking_id: str,
    data: AgencyPaymentRecord,
    current_user: User = Depends(get_current_user),
):
    """Record a payment made by an agency."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

    folio = await db.folios.find_one({"booking_id": booking_id, "tenant_id": tid, "status": "open"}, {"_id": 0})
    if not folio:
        from core.utils import generate_folio_number
        folio_id = str(uuid.uuid4())
        folio = {
            "id": folio_id,
            "tenant_id": tid,
            "booking_id": booking_id,
            "folio_number": await generate_folio_number(tid),
            "folio_type": "agency",
            "status": "open",
            "guest_id": booking.get("guest_id"),
            "balance": 0.0,
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db.folios.insert_one({**folio})

    payment = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "folio_id": folio["id"],
        "booking_id": booking_id,
        "amount": data.amount,
        "method": "agency",
        "payment_type": "agency_payment",
        "status": "paid",
        "reference": data.reference,
        "notes": data.notes,
        "agency_name": data.agency_name or booking.get("source_channel", ""),
        "processed_by": current_user.name,
        "processed_at": datetime.now(UTC).isoformat(),
        "voided": False,
    }
    await db.payments.insert_one({**payment})

    new_paid = (booking.get("paid_amount", 0) or 0) + data.amount
    await db.bookings.update_one(
        {"id": booking_id, "tenant_id": tid},
        {"$set": {"paid_amount": round(new_paid, 2)}},
    )

    await _log_activity(tid, booking_id, "agency_payment_recorded", current_user.name, {
        "amount": data.amount, "agency_name": data.agency_name,
    })

    payment.pop("_id", None)
    return {"success": True, "payment": payment}


@router.post("/reservations/{booking_id}/split-charge")
async def split_charge(
    booking_id: str,
    data: ChargeSplit,
    current_user: User = Depends(get_current_user),
):
    """Split a charge from one folio to another (e.g., transfer part of a meal to another room)."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    # Find the original charge
    charge = await db.folio_charges.find_one({"id": data.charge_id, "tenant_id": tid}, {"_id": 0})
    if not charge:
        # Also check extra_charges
        charge = await db.extra_charges.find_one({"id": data.charge_id, "tenant_id": tid}, {"_id": 0})
        if not charge:
            raise HTTPException(status_code=404, detail="Masraf bulunamadı")

    original_amount = charge.get("total", charge.get("amount", charge.get("charge_amount", 0)))
    if data.split_amount > original_amount:
        raise HTTPException(status_code=400, detail="Bölünecek tutar orijinal tutardan büyük olamaz")

    # Determine target
    target_booking_id = data.target_booking_id
    target_folio_id = data.target_folio_id

    if target_booking_id:
        target_booking = await db.bookings.find_one({"id": target_booking_id, "tenant_id": tid}, {"_id": 0})
        if not target_booking:
            raise HTTPException(status_code=404, detail="Hedef rezervasyon bulunamadı")

        target_folio = await db.folios.find_one({"booking_id": target_booking_id, "tenant_id": tid, "status": "open"}, {"_id": 0})
        if not target_folio:
            from core.utils import generate_folio_number
            target_folio = {
                "id": str(uuid.uuid4()),
                "tenant_id": tid,
                "booking_id": target_booking_id,
                "folio_number": await generate_folio_number(tid),
                "folio_type": "guest",
                "status": "open",
                "guest_id": target_booking.get("guest_id"),
                "balance": 0.0,
                "created_at": datetime.now(UTC).isoformat(),
            }
            await db.folios.insert_one({**target_folio})
        target_folio_id = target_folio["id"]

    # Create the split charge on target
    new_charge = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "folio_id": target_folio_id,
        "booking_id": target_booking_id or charge.get("booking_id"),
        "charge_category": charge.get("charge_category", charge.get("category", "other")),
        "description": f"[Aktarım] {charge.get('description', charge.get('charge_name', ''))}",
        "unit_price": data.split_amount,
        "quantity": 1.0,
        "amount": data.split_amount,
        "tax_amount": 0.0,
        "total": data.split_amount,
        "date": datetime.now(UTC).isoformat(),
        "posted_by": current_user.name,
        "voided": False,
        "split_from_charge_id": data.charge_id,
        "split_from_booking_id": booking_id,
    }
    await db.folio_charges.insert_one({**new_charge})

    # Update original charge amount
    new_original_amount = original_amount - data.split_amount
    collection = "folio_charges" if "folio_id" in charge else "extra_charges"
    amount_field = "total" if "total" in charge else ("amount" if "amount" in charge else "charge_amount")
    await getattr(db, collection).update_one(
        {"id": data.charge_id, "tenant_id": tid},
        {"$set": {amount_field: round(new_original_amount, 2)}},
    )

    # Log split operation
    split_log = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "operation_type": "split",
        "from_folio_id": charge.get("folio_id"),
        "to_folio_id": target_folio_id,
        "from_booking_id": booking_id,
        "to_booking_id": target_booking_id,
        "charge_ids": [data.charge_id],
        "amount": data.split_amount,
        "reason": data.reason or "Masraf bölme",
        "performed_by": current_user.name,
        "performed_at": datetime.now(UTC).isoformat(),
    }
    await db.folio_operations.insert_one({**split_log})

    await _log_activity(tid, booking_id, "charge_split", current_user.name, {
        "charge_id": data.charge_id, "split_amount": data.split_amount,
        "target_booking_id": target_booking_id, "reason": data.reason,
    })

    new_charge.pop("_id", None)
    return {"success": True, "new_charge": new_charge, "remaining_amount": round(new_original_amount, 2)}


@router.post("/reservations/{booking_id}/add-note")
async def add_reservation_note(
    booking_id: str,
    data: NoteCreate,
    current_user: User = Depends(get_current_user),
):
    """Add a note to a reservation."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    note = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": booking_id,
        "content": data.content,
        "note_type": data.note_type,
        "created_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.reservation_notes.insert_one({**note})

    await _log_activity(tid, booking_id, "note_added", current_user.name, {
        "note_type": data.note_type,
    })

    note.pop("_id", None)
    return {"success": True, "note": note}


@router.post("/reservations/{booking_id}/room-change")
async def room_change(
    booking_id: str,
    data: RoomChangeRequest,
    current_user: User = Depends(get_current_user),
):
    """Change the room for a reservation with full audit trail."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

    old_room_id = booking.get("room_id")
    old_room = await db.rooms.find_one({"id": old_room_id, "tenant_id": tid}, {"_id": 0})
    new_room = await db.rooms.find_one({"id": data.new_room_id, "tenant_id": tid}, {"_id": 0})

    if not new_room:
        raise HTTPException(status_code=404, detail="Yeni oda bulunamadı")

    # Update booking
    await db.bookings.update_one(
        {"id": booking_id, "tenant_id": tid},
        {"$set": {
            "room_id": data.new_room_id,
            "room_number": new_room.get("room_number"),
        }},
    )

    # Release old room
    if old_room_id:
        await db.rooms.update_one(
            {"id": old_room_id, "tenant_id": tid},
            {"$set": {"status": "dirty", "current_booking_id": None}},
        )

    # Assign new room
    await db.rooms.update_one(
        {"id": data.new_room_id, "tenant_id": tid},
        {"$set": {"status": "occupied", "current_booking_id": booking_id}},
    )

    # Record room move history
    move_record = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": booking_id,
        "from_room_id": old_room_id,
        "from_room_number": old_room.get("room_number") if old_room else None,
        "to_room_id": data.new_room_id,
        "to_room_number": new_room.get("room_number"),
        "reason": data.reason,
        "moved_by": current_user.name,
        "moved_at": datetime.now(UTC).isoformat(),
    }
    await db.room_move_history.insert_one({**move_record})

    await _log_activity(tid, booking_id, "room_changed", current_user.name, {
        "from_room": old_room.get("room_number") if old_room else None,
        "to_room": new_room.get("room_number"),
        "reason": data.reason,
    })

    move_record.pop("_id", None)
    return {"success": True, "move_record": move_record}


@router.post("/reservations/{booking_id}/early-checkin")
async def early_checkin(
    booking_id: str,
    data: EarlyCheckinRequest,
    current_user: User = Depends(get_current_user),
):
    """Process early check-in with optional extra charge — atomic transaction."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    from core.atomic_checkin_checkout import CheckInError, check_in_booking_atomic

    extra_fields = {"early_checkin": True}
    if data.checkin_time:
        extra_fields["checked_in_at"] = data.checkin_time

    try:
        result = await check_in_booking_atomic(
            booking_id=booking_id,
            tenant_id=tid,
            actor_id=current_user.id,
            actor_name=current_user.name,
            extra_fields=extra_fields,
        )
    except CheckInError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Add extra charge if any (outside transaction — non-critical)
    if data.extra_charge > 0:
        charge = {
            "id": str(uuid.uuid4()),
            "tenant_id": tid,
            "booking_id": booking_id,
            "charge_name": "Erken Giriş Ücreti",
            "charge_amount": data.extra_charge,
            "category": "room",
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db.extra_charges.insert_one({**charge})

    await _log_activity(tid, booking_id, "early_checkin", current_user.name, {
        "checkin_time": data.checkin_time or result.get("checked_in_at"),
        "extra_charge": data.extra_charge,
    })

    return {"success": True, "message": "Erken giriş yapıldı"}


@router.post("/reservations/{booking_id}/late-checkout")
async def late_checkout(
    booking_id: str,
    data: LateCheckoutRequest,
    current_user: User = Depends(get_current_user),
):
    """Process late check-out with optional extra charge."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

    updates = {"late_checkout": True}
    if data.checkout_time:
        updates["check_out_time"] = data.checkout_time

    await db.bookings.update_one({"id": booking_id, "tenant_id": tid}, {"$set": updates})

    if data.extra_charge > 0:
        charge = {
            "id": str(uuid.uuid4()),
            "tenant_id": tid,
            "booking_id": booking_id,
            "charge_name": "Geç Çıkış Ücreti",
            "charge_amount": data.extra_charge,
            "category": "room",
            "created_at": datetime.now(UTC).isoformat(),
        }
        await db.extra_charges.insert_one({**charge})

    await _log_activity(tid, booking_id, "late_checkout", current_user.name, {
        "checkout_time": data.checkout_time,
        "extra_charge": data.extra_charge,
    })

    return {"success": True, "message": "Geç çıkış kaydedildi"}


@router.post("/reservations/{booking_id}/mark-noshow")
async def mark_noshow(
    booking_id: str,
    current_user: User = Depends(get_current_user),
):
    """Mark a reservation as no-show."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

    await db.bookings.update_one(
        {"id": booking_id, "tenant_id": tid},
        {"$set": {"status": "no_show", "no_show_at": datetime.now(UTC).isoformat()}},
    )

    # Release the room
    if booking.get("room_id"):
        await db.rooms.update_one(
            {"id": booking["room_id"], "tenant_id": tid},
            {"$set": {"status": "available", "current_booking_id": None}},
        )

    await _log_activity(tid, booking_id, "marked_noshow", current_user.name, {})

    return {"success": True, "message": "No-show olarak işaretlendi"}


@router.put("/reservations/{booking_id}/vip-status")
async def update_vip_status(
    booking_id: str,
    vip: bool = True,
    current_user: User = Depends(get_current_user),
):
    """Toggle VIP status for the guest of a reservation."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

    if booking.get("guest_id"):
        await db.guests.update_one(
            {"id": booking["guest_id"], "tenant_id": tid},
            {"$set": {"vip_status": vip}},
        )

    await _log_activity(tid, booking_id, "vip_status_changed", current_user.name, {"vip": vip})

    return {"success": True, "vip_status": vip}


@router.post("/reservations/{booking_id}/record-deposit")
async def record_deposit(
    booking_id: str,
    data: DepositRecord,
    current_user: User = Depends(get_current_user),
):
    """Record a deposit payment."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

    deposit = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": booking_id,
        "amount": data.amount,
        "method": data.method,
        "reference": data.reference,
        "deposit_type": "deposit",
        "status": "received",
        "recorded_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.deposits.insert_one({**deposit})

    # Also record as payment
    payment = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "folio_id": "",
        "booking_id": booking_id,
        "amount": data.amount,
        "method": data.method,
        "payment_type": "deposit",
        "status": "paid",
        "reference": data.reference,
        "processed_by": current_user.name,
        "processed_at": datetime.now(UTC).isoformat(),
        "voided": False,
    }
    await db.payments.insert_one({**payment})

    new_paid = (booking.get("paid_amount", 0) or 0) + data.amount
    await db.bookings.update_one(
        {"id": booking_id, "tenant_id": tid},
        {"$set": {"paid_amount": round(new_paid, 2)}},
    )

    await _log_activity(tid, booking_id, "deposit_recorded", current_user.name, {
        "amount": data.amount, "method": data.method,
    })

    deposit.pop("_id", None)
    return {"success": True, "deposit": deposit}


@router.post("/reservations/{booking_id}/add-extra-charge")
async def add_extra_charge_detail(
    booking_id: str,
    data: ExtraChargeAdd,
    current_user: User = Depends(get_current_user),
):
    """Add an extra charge to a reservation."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

    total = round(data.amount * data.quantity, 2)
    charge = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": booking_id,
        "charge_name": data.description,
        "description": data.description,
        "category": data.category,
        "charge_category": data.category,
        "charge_amount": total,
        "amount": data.amount,
        "quantity": data.quantity,
        "total": total,
        "posted_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
        "voided": False,
    }
    await db.extra_charges.insert_one({**charge})

    await _log_activity(tid, booking_id, "extra_charge_added", current_user.name, {
        "description": data.description, "amount": total, "category": data.category,
    })

    charge.pop("_id", None)
    return {"success": True, "charge": charge}


@router.put("/reservations/{booking_id}/daily-rates")
async def update_daily_rates(
    booking_id: str,
    data: DailyRateUpdate,
    current_user: User = Depends(get_current_user),
):
    """Update daily rates for a reservation."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

    for rate_entry in data.rates:
        await db.daily_rates.update_one(
            {"booking_id": booking_id, "tenant_id": tid, "date": rate_entry["date"]},
            {"$set": {
                "rate": rate_entry["rate"],
                "updated_by": current_user.name,
                "updated_at": datetime.now(UTC).isoformat(),
            }},
            upsert=True,
        )

    # Recalculate total
    new_total = sum(r.get("rate", 0) for r in data.rates)
    if new_total > 0:
        await db.bookings.update_one(
            {"id": booking_id, "tenant_id": tid},
            {"$set": {"total_amount": round(new_total, 2)}},
        )

    await _log_activity(tid, booking_id, "daily_rates_updated", current_user.name, {
        "rates_count": len(data.rates),
    })

    return {"success": True, "new_total": round(new_total, 2)}


@router.put("/reservations/{booking_id}/update-guest")
async def update_reservation_guest(
    booking_id: str,
    data: GuestUpdate,
    current_user: User = Depends(get_current_user),
):
    """Update guest information for a reservation."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    booking = await db.bookings.find_one({"id": booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadı")

    if not booking.get("guest_id"):
        raise HTTPException(status_code=400, detail="Misafir bilgisi bulunamadı")

    updates = {k: v for k, v in data.model_dump().items() if v is not None}
    if updates:
        await db.guests.update_one({"id": booking["guest_id"], "tenant_id": tid}, {"$set": updates})

        if "name" in updates:
            await db.bookings.update_one(
                {"id": booking_id, "tenant_id": tid},
                {"$set": {"guest_name": updates["name"]}},
            )

    await _log_activity(tid, booking_id, "guest_updated", current_user.name, {"fields": list(updates.keys())})

    return {"success": True}


# ── Cari Account Endpoints ──

@router.get("/cari-accounts")
async def list_cari_accounts(current_user: User = Depends(get_current_user)):
    """List all cari (account receivable) accounts."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    accounts = []
    async for acc in db.cari_accounts.find({"tenant_id": tid}, {"_id": 0}).sort("name", 1):
        accounts.append(acc)

    return {"accounts": accounts}


@router.post("/cari-accounts")
async def create_cari_account(
    data: CariAccountCreate,
    current_user: User = Depends(get_current_user),
):
    """Create a new cari account."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    account = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "name": data.name,
        "account_type": data.account_type,
        "company_id": data.company_id,
        "contact_person": data.contact_person,
        "contact_email": data.contact_email,
        "contact_phone": data.contact_phone,
        "credit_limit": data.credit_limit,
        "payment_terms_days": data.payment_terms_days,
        "current_balance": 0.0,
        "status": "active",
        "created_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.cari_accounts.insert_one({**account})

    account.pop("_id", None)
    return {"success": True, "account": account}


@router.get("/cari-accounts/{account_id}/transactions")
async def get_cari_transactions(
    account_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get transactions for a cari account."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    transactions = []
    async for t in db.cari_transactions.find(
        {"cari_account_id": account_id, "tenant_id": tid}, {"_id": 0}
    ).sort("created_at", -1):
        transactions.append(t)

    return {"transactions": transactions}


class CariReconciliation(BaseModel):
    amount: float
    description: str | None = None


@router.post("/cari-accounts/{account_id}/reconcile")
async def reconcile_cari_account(
    account_id: str,
    data: CariReconciliation,
    current_user: User = Depends(get_current_user),
):
    """Reconcile (mahsuplaştır) a cari account - record a payment/offset."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    account = await db.cari_accounts.find_one({"id": account_id, "tenant_id": tid}, {"_id": 0})
    if not account:
        raise HTTPException(status_code=404, detail="Cari hesap bulunamadı")

    txn = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "cari_account_id": account_id,
        "booking_id": None,
        "transaction_type": "payment",
        "amount": data.amount,
        "description": data.description or "Mahsuplaştırma",
        "posted_by": current_user.name or current_user.email,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.cari_transactions.insert_one({**txn})
    txn.pop("_id", None)

    # Update account balance
    await db.cari_accounts.update_one(
        {"id": account_id, "tenant_id": tid},
        {"$inc": {"balance": -data.amount}},
    )

    return {"success": True, "transaction": txn}


@router.post("/cari-accounts/{account_id}/transfer-to-agency")
async def transfer_cari_to_agency(
    account_id: str,
    data: CariTransfer,
    current_user: User = Depends(get_current_user),
):
    """Transfer cari balance to an agency cari account."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    source = await db.cari_accounts.find_one({"id": account_id, "tenant_id": tid}, {"_id": 0})
    if not source:
        raise HTTPException(status_code=404, detail="Kaynak cari hesap bulunamadı")

    target = await db.cari_accounts.find_one({"id": data.cari_account_id, "tenant_id": tid}, {"_id": 0})
    if not target:
        raise HTTPException(status_code=404, detail="Hedef cari hesap bulunamadı")

    now = datetime.now(UTC).isoformat()
    actor = current_user.name or current_user.email

    # Debit from source
    debit_txn = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "cari_account_id": account_id,
        "booking_id": None,
        "transaction_type": "transfer_out",
        "amount": data.amount,
        "description": data.description or f"{target.get('name', '')} hesabina aktarim",
        "posted_by": actor,
        "created_at": now,
    }
    await db.cari_transactions.insert_one({**debit_txn})
    debit_txn.pop("_id", None)

    # Credit to target
    credit_txn = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "cari_account_id": data.cari_account_id,
        "booking_id": None,
        "transaction_type": "transfer_in",
        "amount": data.amount,
        "description": data.description or f"{source.get('name', '')} hesabindan aktarim",
        "posted_by": actor,
        "created_at": now,
    }
    await db.cari_transactions.insert_one({**credit_txn})
    credit_txn.pop("_id", None)

    # Update balances
    await db.cari_accounts.update_one({"id": account_id, "tenant_id": tid}, {"$inc": {"balance": -data.amount}})
    await db.cari_accounts.update_one({"id": data.cari_account_id, "tenant_id": tid}, {"$inc": {"balance": data.amount}})

    return {"success": True, "debit": debit_txn, "credit": credit_txn}



# ── Available Rooms Endpoint ──

@router.get("/available-rooms")
async def get_available_rooms(
    check_in: str = "",
    check_out: str = "",
    current_user: User = Depends(get_current_user),
):
    """Get available rooms for room change."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    all_rooms = []
    async for r in db.rooms.find({"tenant_id": tid}, {"_id": 0}).sort("room_number", 1):
        all_rooms.append(r)

    if not check_in or not check_out:
        return {"rooms": all_rooms}

    # Validate date format & ordering (her iki tarih varsa)
    try:
        from datetime import date as _date
        ci_d = _date.fromisoformat(check_in[:10])
        co_d = _date.fromisoformat(check_out[:10])
    except (ValueError, TypeError):
        raise HTTPException(status_code=422, detail="check_in ve check_out YYYY-MM-DD formatında olmalı")
    if co_d <= ci_d:
        raise HTTPException(status_code=422, detail="check_out tarihi check_in'den sonra olmalı")

    # Find bookings that overlap the date range
    occupied_room_ids = set()
    async for b in db.bookings.find({
        "tenant_id": tid,
        "status": {"$nin": ["cancelled", "no_show", "checked_out"]},
    }, {"_id": 0, "room_id": 1, "check_in": 1, "check_out": 1}):
        b_ci = str(b.get("check_in", ""))[:10]
        b_co = str(b.get("check_out", ""))[:10]
        if b_ci < check_out and b_co > check_in:
            if b.get("room_id"):
                occupied_room_ids.add(b["room_id"])

    available = [r for r in all_rooms if r.get("id") not in occupied_room_ids]
    return {"rooms": available, "all_rooms": all_rooms}


# ── Group Booking Endpoints ──

@router.post("/group-bookings")
async def create_group_booking(
    data: GroupBookingCreate,
    request: Request,
    current_user: User = Depends(get_current_user),
):
    """Create a new group booking.

    İki mod desteklenir (ikisi aynı çağrıda birleştirilebilir):
      1) `booking_ids`  — mevcut bireysel rezervasyonları seç ve grupla.
      2) `new_bookings` — grup adıyla aynı anda N adet yeni rezervasyon
         yarat ve gruba bağla. Her satır için (yoksa) misafir kaydı
         placeholder e-posta ile açılır, sonra standart rezervasyon
         servisi (`CreateReservationService`) çağrılır.
    """
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    if not data.group_name.strip():
        raise HTTPException(status_code=400, detail="Grup adı boş olamaz")

    # ── Aşama 1: TÜM girdileri yazma yapmadan önce doğrula ──
    # (Kısmi yazılmış grup oluşturmamak için).
    for idx, row in enumerate(data.new_bookings, start=1):
        if not row.guest_name.strip():
            raise HTTPException(status_code=400, detail=f"{idx}. satır: misafir adı zorunlu")
        if row.total_amount <= 0:
            raise HTTPException(status_code=400, detail=f"{idx}. satır ({row.guest_name}): geçerli bir tutar girin")
        try:
            ci_dt = datetime.fromisoformat(row.check_in.replace("Z", "+00:00"))
            co_dt = datetime.fromisoformat(row.check_out.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"{idx}. satır: tarih formatı geçersiz")
        if co_dt <= ci_dt:
            raise HTTPException(status_code=400, detail=f"{idx}. satır: çıkış tarihi giriş tarihinden sonra olmalı")

    # Tüm odaları toplu doğrula (tenant scope)
    requested_room_ids = list({r.room_id for r in data.new_bookings})
    if requested_room_ids:
        valid_room_ids = {
            r["id"] async for r in db.rooms.find(
                {"id": {"$in": requested_room_ids}, "tenant_id": tid}, {"id": 1}
            )
        }
        for idx, row in enumerate(data.new_bookings, start=1):
            if row.room_id not in valid_room_ids:
                raise HTTPException(status_code=404, detail=f"{idx}. satır: oda bulunamadı")

    # Mevcut booking_ids'i tenant kapsamında doğrula
    valid_existing_ids: list[str] = []
    if data.booking_ids:
        existing_docs = db.bookings.find(
            {"id": {"$in": list(set(data.booking_ids))}, "tenant_id": tid},
            {"id": 1},
        )
        valid_existing_ids = [d["id"] async for d in existing_docs]
        missing = set(data.booking_ids) - set(valid_existing_ids)
        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"Bu rezervasyonlar bulunamadı veya yetkiniz yok: {', '.join(list(missing)[:3])}",
            )

    if not data.new_bookings and not valid_existing_ids:
        raise HTTPException(status_code=400, detail="Grup için en az 1 rezervasyon gerekli")

    # ── Aşama 2: Yeni rezervasyonları yarat (failure'da geri al) ──
    created_guest_ids: list[str] = []
    new_booking_ids: list[str] = []
    try:
        for idx, row in enumerate(data.new_bookings, start=1):
            guest_id = str(uuid.uuid4())
            await db.guests.insert_one({
                "id": guest_id,
                "tenant_id": tid,
                "name": row.guest_name.strip(),
                "email": f"group-{guest_id[:8]}@placeholder.local",
                "phone": "",
                "id_number": "",
                "vip_status": False,
                "loyalty_points": 0,
                "total_stays": 0,
                "total_spend": 0.0,
                "created_at": datetime.now(UTC).isoformat(),
            })
            created_guest_ids.append(guest_id)

            booking_data = BookingCreate(
                guest_id=guest_id,
                room_id=row.room_id,
                check_in=row.check_in,
                check_out=row.check_out,
                adults=max(1, row.adults),
                children=max(0, row.children),
                guests_count=max(1, row.adults + row.children),
                total_amount=row.total_amount,
                channel="direct",
                source_channel="direct",
                origin="ui-group",
            )
            sub_request = _request_with_idempotency_key(request, str(uuid.uuid4()))
            result = await _create_reservation_service.create(
                booking_data, current_user, sub_request
            )
            bid = (
                result.get("booking_id")
                or result.get("id")
                or (result.get("booking") or {}).get("id")
            )
            if not bid:
                raise HTTPException(
                    status_code=500,
                    detail=f"{idx}. satır rezervasyon ID'si alınamadı",
                )
            new_booking_ids.append(bid)
    except Exception as exc:
        # Compensating: önceden yarattıklarını sil
        if new_booking_ids:
            await db.bookings.delete_many({"id": {"$in": new_booking_ids}, "tenant_id": tid})
        if created_guest_ids:
            await db.guests.delete_many({"id": {"$in": created_guest_ids}, "tenant_id": tid})
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(status_code=500, detail=f"Grup oluşturulurken hata: {exc}") from exc

    # Birleştir (tekrarlananları at, var olanları başa al)
    all_booking_ids = list(dict.fromkeys([*valid_existing_ids, *new_booking_ids]))

    # 3) Grubu oluştur
    group_id = str(uuid.uuid4())
    group = {
        "id": group_id,
        "tenant_id": tid,
        "group_name": data.group_name.strip(),
        "booking_ids": all_booking_ids,
        "status": "active",
        "total_rooms": len(all_booking_ids),
        "created_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.group_bookings.insert_one({**group})

    # 4) Her bookinge group_booking_id damgala
    for bid in all_booking_ids:
        await db.bookings.update_one(
            {"id": bid, "tenant_id": tid},
            {"$set": {"group_booking_id": group_id}},
        )

    group.pop("_id", None)
    return {
        "success": True,
        "group": group,
        "created_booking_ids": new_booking_ids,
    }


@router.get("/group-bookings")
async def list_group_bookings(current_user: User = Depends(get_current_user)):
    """List all group bookings."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    groups = []
    async for g in db.group_bookings.find({"tenant_id": tid}, {"_id": 0}).sort("created_at", -1):
        # Enrich with booking details
        group_bookings = []
        async for b in db.bookings.find(
            {"id": {"$in": g.get("booking_ids", [])}, "tenant_id": tid}, {"_id": 0}
        ):
            group_bookings.append(b)
        g["bookings"] = group_bookings
        g["total_amount"] = sum(b.get("total_amount", 0) for b in group_bookings)
        g["total_paid"] = sum(b.get("paid_amount", 0) for b in group_bookings)
        groups.append(g)

    return {"groups": groups}


@router.get("/group-bookings/{group_id}")
async def get_group_booking_detail(
    group_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get detailed group booking info."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    group = await db.group_bookings.find_one({"id": group_id, "tenant_id": tid}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Grup rezervasyon bulunamadi")

    bookings_list = []
    async for b in db.bookings.find(
        {"id": {"$in": group.get("booking_ids", [])}, "tenant_id": tid}, {"_id": 0}
    ):
        guest = None
        if b.get("guest_id"):
            guest = await db.guests.find_one({"id": b["guest_id"], "tenant_id": tid}, {"_id": 0})
        b["guest_detail"] = guest
        bookings_list.append(b)

    group["bookings"] = bookings_list
    group["total_amount"] = sum(b.get("total_amount", 0) for b in bookings_list)
    group["total_paid"] = sum(b.get("paid_amount", 0) for b in bookings_list)
    return group


@router.post("/group-bookings/{group_id}/add-room")
async def add_room_to_group(
    group_id: str,
    data: GroupBookingAddRoom,
    current_user: User = Depends(get_current_user),
):
    """Add a booking/room to a group."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    group = await db.group_bookings.find_one({"id": group_id, "tenant_id": tid}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadi")

    booking = await db.bookings.find_one({"id": data.booking_id, "tenant_id": tid}, {"_id": 0})
    if not booking:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    existing_ids = group.get("booking_ids", [])
    if data.booking_id not in existing_ids:
        existing_ids.append(data.booking_id)
        await db.group_bookings.update_one(
            {"id": group_id, "tenant_id": tid},
            {"$set": {"booking_ids": existing_ids, "total_rooms": len(existing_ids)}},
        )
        await db.bookings.update_one(
            {"id": data.booking_id, "tenant_id": tid},
            {"$set": {"group_booking_id": group_id}},
        )

    return {"success": True}


@router.post("/group-bookings/{group_id}/check-in-all")
async def group_check_in_all(
    group_id: str,
    current_user: User = Depends(get_current_user),
):
    """Check-in all reservations in a group — each via atomic transaction."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    group = await db.group_bookings.find_one({"id": group_id, "tenant_id": tid}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadi")

    from core.atomic_checkin_checkout import CheckInError, check_in_booking_atomic

    checked_in = 0
    errors = []
    for bid in group.get("booking_ids", []):
        try:
            await check_in_booking_atomic(
                booking_id=bid,
                tenant_id=tid,
                actor_id=current_user.id,
                actor_name=current_user.name,
            )
            checked_in += 1
        except CheckInError as e:
            errors.append({"booking_id": bid, "error": str(e)})

    return {"success": True, "checked_in_count": checked_in, "errors": errors}


@router.post("/group-bookings/{group_id}/check-out-all")
async def group_check_out_all(
    group_id: str,
    current_user: User = Depends(get_current_user),
):
    """Check-out all reservations in a group — each via atomic transaction."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    group = await db.group_bookings.find_one({"id": group_id, "tenant_id": tid}, {"_id": 0})
    if not group:
        raise HTTPException(status_code=404, detail="Grup bulunamadi")

    from core.atomic_checkin_checkout import CheckOutError, check_out_booking_atomic

    checked_out = 0
    errors = []
    for bid in group.get("booking_ids", []):
        try:
            await check_out_booking_atomic(
                booking_id=bid,
                tenant_id=tid,
                actor_id=current_user.id,
                actor_name=current_user.name,
                force=True,  # Group checkout forces past balance blockers
            )
            checked_out += 1
        except CheckOutError as e:
            errors.append({"booking_id": bid, "error": str(e)})

    return {"success": True, "checked_out_count": checked_out, "errors": errors}


# ── Communication Log Endpoints ──

@router.post("/reservations/{booking_id}/communication")
async def add_communication_log(
    booking_id: str,
    data: CommunicationLogCreate,
    current_user: User = Depends(get_current_user),
):
    """Add a communication log entry for a reservation."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    log_entry = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": booking_id,
        "channel": data.channel,
        "direction": data.direction,
        "subject": data.subject,
        "content": data.content,
        "recipient": data.recipient,
        "sent_by": current_user.name,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.communication_logs.insert_one({**log_entry})

    await _log_activity(tid, booking_id, "communication_logged", current_user.name, {
        "channel": data.channel, "direction": data.direction,
    })

    log_entry.pop("_id", None)
    return {"success": True, "log": log_entry}


@router.get("/reservations/{booking_id}/communication")
async def get_communication_logs(
    booking_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get communication log for a reservation."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    logs = []
    async for entry in db.communication_logs.find(
        {"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}
    ).sort("created_at", -1):
        logs.append(entry)

    return {"logs": logs}


# ── Deposit Management Endpoints ──

@router.get("/reservations/{booking_id}/deposits")
async def get_deposits(
    booking_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get deposits for a reservation."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    deposits = []
    async for d in db.deposits.find(
        {"booking_id": booking_id, "tenant_id": tid}, {"_id": 0}
    ).sort("created_at", -1):
        deposits.append(d)

    return {"deposits": deposits}


@router.post("/reservations/{booking_id}/refund-deposit")
async def refund_deposit(
    booking_id: str,
    data: DepositRefund,
    current_user: User = Depends(get_current_user),
):
    """Refund a deposit."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    deposit = await db.deposits.find_one(
        {"id": data.deposit_id, "tenant_id": tid}, {"_id": 0}
    )
    if not deposit:
        raise HTTPException(status_code=404, detail="Depozito bulunamadi")

    if data.refund_amount > deposit.get("amount", 0):
        raise HTTPException(status_code=400, detail="Iade tutari depozito tutarindan buyuk olamaz")

    refund = {
        "id": str(uuid.uuid4()),
        "tenant_id": tid,
        "booking_id": booking_id,
        "deposit_id": data.deposit_id,
        "refund_amount": data.refund_amount,
        "refund_method": data.refund_method,
        "reason": data.reason,
        "status": "refunded",
        "refunded_by": current_user.name,
        "refunded_at": datetime.now(UTC).isoformat(),
    }
    await db.deposit_refunds.insert_one({**refund})

    # Update deposit status
    remaining = deposit.get("amount", 0) - data.refund_amount
    new_status = "refunded" if remaining <= 0 else "partially_refunded"
    await db.deposits.update_one(
        {"id": data.deposit_id, "tenant_id": tid},
        {"$set": {"status": new_status, "refunded_amount": data.refund_amount}},
    )

    await _log_activity(tid, booking_id, "deposit_refunded", current_user.name, {
        "deposit_id": data.deposit_id, "refund_amount": data.refund_amount,
    })

    refund.pop("_id", None)
    return {"success": True, "refund": refund}


@router.get("/deposits/all")
async def list_all_deposits(current_user: User = Depends(get_current_user)):
    """List all deposits across all reservations."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    deposits = []
    async for d in db.deposits.find({"tenant_id": tid}, {"_id": 0}).sort("created_at", -1):
        # Enrich with booking info
        booking = await db.bookings.find_one({"id": d.get("booking_id"), "tenant_id": tid}, {"_id": 0, "guest_name": 1, "room_number": 1, "check_in": 1, "check_out": 1})
        if booking:
            d["guest_name"] = booking.get("guest_name")
            d["room_number"] = booking.get("room_number")
        deposits.append(d)

    return {"deposits": deposits}
