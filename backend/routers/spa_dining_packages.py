"""SPA & Restaurant Dining Cross-Departmental Package Scheduler.

Manages spa + dining joint packages, schedules linked resource bookings,
performs cross-departmental conflict checking, and handles room folio posting.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from pymongo.errors import DuplicateKeyError

from core.security import get_current_user
from core.tenant_db import get_system_db
from domains.spa.router import _check_conflict as _check_spa_conflict
from models.schemas import User
from modules.pms_core.role_permission_service import require_op
from shared_kernel.pos_idem import ensure_compound_unique

router = APIRouter(prefix="/api/spa-dining", tags=["SPA & Dining Scheduler"])

DEFAULT_PACKAGES = [
    {
        "id": "pkg_zen_dine",
        "name": "Zen & Dine Paketi",
        "spa_service_id": "massage_swedish",
        "spa_service_name": "İsveç Masajı 60dk",
        "spa_duration_minutes": 60,
        "dining_duration_minutes": 120,
        "gap_minutes": 30,
        "price": 3200.0,
        "description": "60 dakikalık İsveç masajı ve ardından restoranımızda gurme akşam yemeği.",
    },
    {
        "id": "pkg_royal_treatment",
        "name": "Royal Treatment Paketi",
        "spa_service_id": "massage_deep_tissue",
        "spa_service_name": "Derin Doku Masajı 90dk",
        "spa_duration_minutes": 90,
        "dining_duration_minutes": 120,
        "gap_minutes": 30,
        "price": 4000.0,
        "description": "90 dakikalık derin doku masajı ve ardından restoranımızda gurme akşam yemeği.",
    },
]


class PackageBookingRequest(BaseModel):
    package_id: str = Field(..., min_length=1, max_length=100)
    spa_therapist_id: str = Field(..., min_length=1, max_length=100)
    spa_room_id: str = Field(..., min_length=1, max_length=100)
    dining_outlet_id: str = Field(..., min_length=1, max_length=100)
    dining_table_number: str = Field(..., min_length=1, max_length=50)
    starts_at: str = Field(..., min_length=1, max_length=50)  # ISO 8601
    guest_name: str = Field(..., min_length=1, max_length=200)
    guest_phone: str | None = Field(None, max_length=50)
    reservation_id: str | None = Field(None, max_length=100)  # hotel booking reference
    charge_to_room: bool = False


async def _check_dining_conflict(tenant_id: str, outlet_id: str, table_number: str, start: datetime, end: datetime) -> str | None:
    db = get_system_db()
    table = await db.table_layouts.find_one({"table_number": table_number, "outlet_id": outlet_id, "tenant_id": tenant_id})
    if not table:
        return "Masa bulunamadı"

    async for res in db.table_reservations.find({"tenant_id": tenant_id, "outlet_id": outlet_id, "table_number": table_number, "status": "confirmed"}):
        try:
            res_time = datetime.fromisoformat(res["reservation_time"].replace("Z", "+00:00"))
            res_end = res_time + timedelta(hours=2)  # Assume 2 hours dining reservation hold
            if res_time < end and res_end > start:
                return f"Masa çakışması: {res.get('guest_name')} (Saat: {res.get('reservation_time')})"
        except Exception:
            if res["reservation_time"] == start.isoformat():
                return "Masa çakışması (birebir eşleşme)"
    return None


async def _post_package_to_folio(tenant_id: str, booking: dict) -> None:
    db = get_system_db()
    await ensure_compound_unique(
        db.folio_postings,
        [("tenant_id", 1), ("dedup_key", 1)],
        partial_filter={"dedup_key": {"$type": "string"}},
        name="uniq_folio_postings_dedup",
    )
    posting = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "reservation_id": booking.get("reservation_id"),
        "folio_id": booking.get("reservation_id"),
        "transaction_code": "PKG",
        "description": f"Paket: {booking.get('package_name')}",
        "amount": float(booking.get("total_price", 0)),
        "currency": "TRY",
        "posting_type": "CHARGE",
        "posted_at": datetime.now(UTC).isoformat(),
        "source": "spa_dining_package_module",
        "reference": booking.get("id"),
        "dedup_key": f"spa_dining_package:{booking.get('id')}",
    }
    try:
        await db.folio_postings.insert_one(posting)
    except DuplicateKeyError:
        return

    # Best-effort Xchange publish
    try:
        from integrations.xchange.bus import bus
        from integrations.xchange.schemas import MessageType

        await bus.publish(
            tenant_id=tenant_id,
            message_type=MessageType.POSTING_CHARGE,
            payload={
                "posting_id": posting["id"],
                "reservation_id": posting["reservation_id"],
                "folio_id": posting["folio_id"],
                "posting_type": "CHARGE",
                "transaction_code": "PKG",
                "description": posting["description"],
                "amount": posting["amount"],
                "currency": posting["currency"],
                "posted_at": posting["posted_at"],
            },
        )
    except Exception:
        pass


@router.get("/packages")
async def list_packages(current_user: User = Depends(get_current_user)) -> dict:
    """Returns available SPA & Dining packages."""
    return {"packages": DEFAULT_PACKAGES}


@router.get("/bookings")
async def list_package_bookings(
    guest_name: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_security")),
) -> dict:
    """List cross-departmental spa/dining bookings."""
    db = get_system_db()
    q = {"tenant_id": current_user.tenant_id}
    if guest_name:
        q["guest_name"] = guest_name

    bookings = await db.spa_dining_package_bookings.find(q, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"bookings": bookings}


@router.post("/bookings")
async def create_package_booking(
    payload: PackageBookingRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_sales")),
):
    """Atomic cross-booking for SPA & Restoran table package."""
    db = get_system_db()
    tenant_id = current_user.tenant_id

    # 1. Resolve package
    pkg = next((p for p in DEFAULT_PACKAGES if p["id"] == payload.package_id), None)
    if not pkg:
        raise HTTPException(status_code=404, detail="Paket bulunamadı")

    # 2. Parse times
    try:
        spa_start = datetime.fromisoformat(payload.starts_at.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail="Geçersiz başlangıç zamanı formatı (ISO 8601 gerekli)")

    spa_end = spa_start + timedelta(minutes=pkg["spa_duration_minutes"])
    dining_start = spa_end + timedelta(minutes=pkg["gap_minutes"])
    dining_end = dining_start + timedelta(minutes=pkg["dining_duration_minutes"])

    # 3. Conflict Checks
    # a) SPA room/therapist conflict
    spa_err = await _check_spa_conflict(tenant_id=tenant_id, therapist_id=payload.spa_therapist_id, room_id=payload.spa_room_id, start=spa_start, end=spa_end)
    if spa_err:
        raise HTTPException(status_code=409, detail=f"SPA Kaynak Çakışması: {spa_err}")

    # b) Dining table conflict
    dining_err = await _check_dining_conflict(tenant_id=tenant_id, outlet_id=payload.dining_outlet_id, table_number=payload.dining_table_number, start=dining_start, end=dining_end)
    if dining_err:
        raise HTTPException(status_code=409, detail=f"Restoran Masa Çakışması: {dining_err}")

    # 4. Atomic Insertions
    booking_id = str(uuid.uuid4())
    spa_appt_id = str(uuid.uuid4())
    dining_res_id = str(uuid.uuid4())

    # Create Spa Appointment
    spa_appt = {
        "id": spa_appt_id,
        "tenant_id": tenant_id,
        "service_id": pkg["spa_service_id"],
        "service_name": pkg["spa_service_name"],
        "therapist_id": payload.spa_therapist_id,
        "room_id": payload.spa_room_id,
        "guest_name": payload.guest_name,
        "guest_phone": payload.guest_phone,
        "starts_at": spa_start.isoformat(),
        "ends_at": spa_end.isoformat(),
        "price": float(pkg["price"] * 0.6),  # Attribution 60%
        "currency": "TRY",
        "status": "scheduled",
        "reservation_id": payload.reservation_id,
        "charge_to_room": payload.charge_to_room,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.spa_appointments.insert_one(spa_appt)

    # Create Dining Reservation
    dining_res = {
        "id": dining_res_id,
        "tenant_id": tenant_id,
        "outlet_id": payload.dining_outlet_id,
        "table_number": payload.dining_table_number,
        "guest_name": payload.guest_name,
        "party_size": 2,
        "reservation_time": dining_start.isoformat(),
        "status": "confirmed",
        "created_by": current_user.id,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.table_reservations.insert_one(dining_res)

    # Set table layout status to reserved
    await db.table_layouts.update_one(
        {"table_number": payload.dining_table_number, "outlet_id": payload.dining_outlet_id, "tenant_id": tenant_id}, {"$set": {"status": "reserved", "reserved_for": payload.guest_name}}
    )

    # Create linked Cross-Booking
    cross_booking = {
        "id": booking_id,
        "tenant_id": tenant_id,
        "package_id": payload.package_id,
        "package_name": pkg["name"],
        "spa_appointment_id": spa_appt_id,
        "dining_reservation_id": dining_res_id,
        "total_price": pkg["price"],
        "guest_name": payload.guest_name,
        "guest_phone": payload.guest_phone,
        "reservation_id": payload.reservation_id,
        "charge_to_room": payload.charge_to_room,
        "created_at": datetime.now(UTC).isoformat(),
    }
    await db.spa_dining_package_bookings.insert_one(cross_booking)

    # 5. Folio Posting
    if payload.charge_to_room and payload.reservation_id:
        booking = await db.bookings.find_one({"id": payload.reservation_id, "tenant_id": tenant_id})
        if not booking:
            # Rollback creations to remain fail-closed
            await db.spa_appointments.delete_one({"id": spa_appt_id})
            await db.table_reservations.delete_one({"id": dining_res_id})
            await db.spa_dining_package_bookings.delete_one({"id": booking_id})
            raise HTTPException(status_code=400, detail="Oda rezervasyonu bulunamadı, folioya yansıtılamıyor")
        await _post_package_to_folio(tenant_id, cross_booking)

    return {
        "success": True,
        "booking_id": booking_id,
        "spa_appointment_id": spa_appt_id,
        "dining_reservation_id": dining_res_id,
        "spa_time": f"{spa_start.isoformat()} -> {spa_end.isoformat()}",
        "dining_time": f"{dining_start.isoformat()} -> {dining_end.isoformat()}",
    }
