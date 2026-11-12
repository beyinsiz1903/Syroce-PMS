"""Auto-split from hotel_services.py — backward-compatible sub-router."""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.schemas import User, _ensure_hotel_context
from modules.pms_core.role_permission_service import require_module_role, require_op

from ._common import (
    HotelSettingsUpdate,
    RoomStatusUpdate,
)

logger = logging.getLogger(__name__)
sub_router = APIRouter()

_HK_STATUSES = {"clean", "dirty", "cleaning", "inspected", "maintenance", "out_of_order"}
_VACANT_STATUSES = {"available", "clean", "dirty", "cleaning", "inspected"}


def _housekeeping_change(room, status, actor, now):
    if status not in _HK_STATUSES:
        raise HTTPException(422, "Geçersiz temizlik durumu.")
    updates = {"housekeeping_status": status, "hk_status": status, "updated_at": now,
               "housekeeping_updated_at": now, "housekeeping_updated_by": actor}
    # Readiness may follow cleaning only for an unoccupied, unblocked room.
    # Keep occupancy ownership and maintenance restrictions authoritative.
    if room.get("status") in _VACANT_STATUSES and not room.get("current_booking_id"):
        updates["status"] = "available" if status == "clean" else status
        updates["room_status"] = updates["status"]
    if status == "clean":
        updates.update(last_cleaned=now, last_cleaned_at=now)
    return updates


def _housekeeping_scope(room, tid):
    # A concurrent check-in, checkout or block must be reread, never undone by
    # a cleaning action prepared against the old occupancy state.
    return {"id": room["id"], "tenant_id": tid, "status": room.get("status"),
            "current_booking_id": room.get("current_booking_id")}


def _invalidate_housekeeping(tid):
    from routers.housekeeping import _invalidate_hk_caches

    _invalidate_hk_caches(tid)


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
    _perm=Depends(require_module_role("housekeeping")),  # v99 DW
):
    """Update housekeeping status of a room."""
    _ensure_hotel_context(current_user)
    tid = current_user.tenant_id

    room = await db.rooms.find_one({"id": room_id, "tenant_id": tid})
    if not room:
        raise HTTPException(status_code=404, detail="Oda bulunamadi")

    old_status = room.get("housekeeping_status", "clean")

    update_data = _housekeeping_change(room, data.status, current_user.name, datetime.now(UTC).isoformat())
    if data.notes:
        update_data["housekeeping_notes"] = data.notes

    result = await db.rooms.update_one(_housekeeping_scope(room, tid), {"$set": update_data})
    if result.matched_count != 1:
        raise HTTPException(409, "Odanın durumu değişti; yenileyip tekrar kontrol edin.")
    _invalidate_housekeeping(tid)

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
    if status not in _HK_STATUSES:
        raise HTTPException(422, "Geçersiz temizlik durumu.")
    rooms = await db.rooms.find({"id": {"$in": room_ids}, "tenant_id": tid}, {"_id": 0}).to_list(None)
    changed, conflicts = [], []
    for room in rooms:
        updates = _housekeeping_change(room, status, current_user.name, now)
        result = await db.rooms.update_one(_housekeeping_scope(room, tid), {"$set": updates})
        (changed if result.matched_count else conflicts).append(room["id"])
    _invalidate_housekeeping(tid)

    if changed:
        try:
            from websocket_server import broadcast_room_status_update
        except Exception as exc:
            broadcast_room_status_update = None
            logger.warning("[HK-WS] bulk room status yayini yuklenemedi: %s", exc)
        if broadcast_room_status_update:
            # Per-room try: tek odanin yayini patlasa da kalanlar yayinlanir.
            for rid in changed:
                try:
                    await broadcast_room_status_update(rid, status, tenant_id=tid)
                except Exception as exc:
                    logger.warning("[HK-WS] bulk room status yayini basarisiz room=%s: %s", rid, exc)

    return {"success": not conflicts, "updated_count": len(changed), "conflicted_room_ids": conflicts}


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
        tenant = await db.tenants.find_one({"id": tid}, {"_id": 0})
        if not tenant:
            tenant = await db.tenants.find_one({"tenant_id": tid}, {"_id": 0})
        settings = {
            "tenant_id": tid,
            "hotel_name": (tenant.get("property_name") or tenant.get("hotel_name") or tenant.get("name") or "") if tenant else "",
            "hotel_address": tenant.get("address", "") if tenant else "",
            "hotel_phone": tenant.get("phone", tenant.get("contact_phone", "")) if tenant else "",
            "hotel_email": tenant.get("email", tenant.get("contact_email", "")) if tenant else "",
            "tax_id": "",
            "tax_office": "",
            "logo_data": (tenant.get("logo_data") or tenant.get("logo_url")) if tenant else None,
            "invoice_header": "",
            "invoice_footer": "Konaklama hizmetlerinden memnun kaldiysa bizi tercih ettiginiz icin tesekkur ederiz.",
            "invoice_notes": "",
            "currency": "TRY",
            "currency_symbol": "₺",
            "default_accommodation_vat_rate": float(tenant.get("vat_rate", 10.0)) if tenant else 10.0,
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
