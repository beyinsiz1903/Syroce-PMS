"""Auto-split from hotel_services.py — backward-compatible sub-router."""
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.schemas import User, _ensure_hotel_context
from modules.pms_core.role_permission_service import require_module as require_module_v99
from modules.pms_core.role_permission_service import require_op

from ._common import (
    HotelSettingsUpdate,
    RoomStatusUpdate,
)

logger = logging.getLogger(__name__)
sub_router = APIRouter()

@sub_router.get("/housekeeping/rooms")
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

    rooms = await db.rooms.find(query, {"_id": 0}).sort("room_number", 1).to_list(length=None)
    room_ids = [r.get("id") for r in rooms if r.get("id")]

    bookings_by_room: dict = {}
    if room_ids:
        async for b in db.bookings.find(
            {"room_id": {"$in": room_ids}, "tenant_id": tid, "status": {"$in": ["checked_in", "confirmed"]}},
            {"_id": 0, "room_id": 1, "guest_name": 1, "check_out": 1, "status": 1},
        ):
            rid = b.get("room_id")
            if rid and rid not in bookings_by_room:
                bookings_by_room[rid] = {k: v for k, v in b.items() if k != "room_id"}

    for r in rooms:
        r["current_booking"] = bookings_by_room.get(r.get("id"))
        r["housekeeping_status"] = r.get("housekeeping_status", "clean")

    # Summary counts
    statuses = {}
    for r in rooms:
        s = r.get("housekeeping_status", "clean")
        statuses[s] = statuses.get(s, 0) + 1

    return {"rooms": rooms, "summary": statuses, "total": len(rooms)}


@sub_router.put("/housekeeping/rooms/{room_id}/status")
async def update_room_housekeeping_status(
    room_id: str,
    data: RoomStatusUpdate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_module_v99("housekeeping")),  # v99 DW
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

    try:
        from websocket_server import broadcast_room_status_update
        await broadcast_room_status_update(room_id, data.status, tenant_id=tid)
    except Exception as exc:
        logger.warning("[HK-WS] room status yayini basarisiz room=%s: %s", room_id, exc)

    return {"success": True, "room_id": room_id, "new_status": data.status}


@sub_router.put("/housekeeping/rooms/bulk-status")
async def bulk_update_room_status(
    room_ids: list[str] = [],
    status: str = "clean",
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v96 DW
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

    if result.modified_count:
        try:
            from websocket_server import broadcast_room_status_update
        except Exception as exc:
            broadcast_room_status_update = None
            logger.warning("[HK-WS] bulk room status yayini yuklenemedi: %s", exc)
        if broadcast_room_status_update:
            # Per-room try: tek odanin yayini patlasa da kalanlar yayinlanir.
            for rid in room_ids:
                try:
                    await broadcast_room_status_update(rid, status, tenant_id=tid)
                except Exception as exc:
                    logger.warning("[HK-WS] bulk room status yayini basarisiz room=%s: %s", rid, exc)

    return {"success": True, "updated_count": result.modified_count}


# ═══════════════════════════════════════════════════
# 2. WAKE-UP CALL MANAGEMENT
# ═══════════════════════════════════════════════════


@sub_router.get("/hotel-settings")
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



@sub_router.put("/hotel-settings")
async def update_hotel_settings(
    data: HotelSettingsUpdate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_users")),  # v90 DW
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

    # Invalidate cached tenant currency so the next dashboard request reflects the new selection.
    try:
        from core.tenant_currency import invalidate_tenant_currency
        invalidate_tenant_currency(tid)
    except Exception:
        pass

    settings = await db.hotel_settings.find_one({"tenant_id": tid}, {"_id": 0})
    return {"success": True, "settings": settings}


# ═══════════════════════════════════════════════════
# 5. PDF INVOICE GENERATION FROM FOLIO
# ═══════════════════════════════════════════════════

