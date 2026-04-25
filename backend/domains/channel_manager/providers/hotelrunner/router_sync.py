"""
HotelRunner Router — CRITICAL Push/Pull Sync Endpoints
========================================================

Live HotelRunner integration endpoints. These do real HTTP egress to the
HotelRunner API via the provider client (with its retry, rate-limit, and
observability machinery). Handler bodies are byte-for-byte equivalent to
the original implementations in `hotelrunner_router.py` — only the helper
import names changed (`_get_provider` → `get_provider`, `_log_sync` →
`log_sync`).

Mounted under the main `/api/channel-manager/hotelrunner` prefix by the
parent router.
"""
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v96 DW

from .factory import get_provider
from .router_schemas import HRARIUpdate
from .sync_log import log_sync

router = APIRouter()


# ── Room / Inventory Operations ──────────────────────────────────────

@router.get("/rooms")
async def get_rooms(current_user: User = Depends(get_current_user)):
    """Fetch all rooms/rates from HotelRunner."""
    provider, conn = await get_provider(current_user.tenant_id)
    result = await provider.get_rooms()

    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"HotelRunner API hatasi: {result['error']}")

    rooms = result["data"].get("rooms", [])

    await db.hotelrunner_connections.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$set": {"cached_rooms": rooms, "rooms_fetched_at": datetime.now(UTC).isoformat()}},
    )

    return {"rooms": rooms, "count": len(rooms)}


@router.put("/rooms/update")
async def update_room_ari(
    payload: HRARIUpdate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    """Push ARI update to HotelRunner."""
    provider, conn = await get_provider(current_user.tenant_id)

    update_data = payload.model_dump(exclude_none=True)
    result = await provider.update_room(**update_data)

    status = "success" if result["success"] else "failed"
    await log_sync(current_user.tenant_id, "ari_push", status,
                   duration_ms=result.get("duration_ms", 0), records=1,
                   error=result.get("error"), user_name=current_user.name)

    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"ARI guncelleme hatasi: {result['error']}")

    return {
        "message": "ARI guncelleme basarili",
        "transaction_id": result["data"].get("transaction_id"),
        "status": result["data"].get("status"),
    }


@router.post("/rooms/bulk-update")
async def bulk_update_ari(
    updates: list[HRARIUpdate],
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v96 DW
):
    """Push multiple ARI updates to HotelRunner."""
    provider, conn = await get_provider(current_user.tenant_id)

    update_dicts = [u.model_dump(exclude_none=True) for u in updates]
    results = await provider.push_ari_bulk(update_dicts)

    success_count = sum(1 for r in results if r.get("success"))
    fail_count = len(results) - success_count

    await log_sync(current_user.tenant_id, "ari_bulk_push", "success" if fail_count == 0 else "partial",
                   records=success_count, user_name=current_user.name)

    return {
        "total": len(results),
        "success": success_count,
        "failed": fail_count,
        "results": results,
    }


# ── Reservation Operations ───────────────────────────────────────────

@router.get("/reservations")
async def get_reservations(
    undelivered: bool = True,
    from_date: str | None = None,
    per_page: int = 10,
    page: int = 1,
    current_user: User = Depends(get_current_user),
):
    """Fetch reservations from HotelRunner."""
    provider, conn = await get_provider(current_user.tenant_id)

    result = await provider.get_reservations(
        undelivered=undelivered,
        from_date=from_date,
        per_page=per_page,
        page=page,
    )

    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"Rezervasyon cekme hatasi: {result['error']}")

    data = result["data"]
    return {
        "reservations": data.get("reservations", []),
        "count": data.get("count", 0),
        "current_page": data.get("current_page", 1),
        "pages": data.get("pages", 1),
    }


@router.post("/reservations/sync")
async def sync_reservations(current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v96 DW
):
    """Pull all undelivered reservations and store them for PMS import."""
    provider, conn = await get_provider(current_user.tenant_id)

    result = await provider.sync_reservations()
    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"Senkronizasyon hatasi: {result['error']}")

    imported = 0
    for res in result["reservations"]:
        hr_number = res.get("hr_number", "")
        existing = await db.hotelrunner_reservations.find_one({
            "tenant_id": current_user.tenant_id,
            "hr_number": hr_number,
        })

        reservation_doc = {
            "tenant_id": current_user.tenant_id,
            "hr_number": hr_number,
            "hr_reservation_id": res.get("reservation_id"),
            "channel": res.get("channel"),
            "channel_display": res.get("channel_display"),
            "state": res.get("state"),
            "guest_name": res.get("guest"),
            "guest_firstname": res.get("firstname"),
            "guest_lastname": res.get("lastname"),
            "guest_email": res.get("address", {}).get("email"),
            "guest_phone": res.get("address", {}).get("phone"),
            "guest_country": res.get("country"),
            "checkin_date": res.get("checkin_date"),
            "checkout_date": res.get("checkout_date"),
            "total": res.get("total"),
            "currency": res.get("currency"),
            "payment_method": res.get("payment"),
            "total_rooms": res.get("total_rooms"),
            "total_guests": res.get("total_guests"),
            "rooms": res.get("rooms", []),
            "note": res.get("note"),
            "message_uid": res.get("message_uid"),
            "raw_data": res,
            "pms_status": "pending",
            "pms_booking_id": None,
            "synced_at": datetime.now(UTC).isoformat(),
        }

        if existing:
            await db.hotelrunner_reservations.update_one(
                {"_id": existing["_id"]},
                {"$set": reservation_doc},
            )
        else:
            reservation_doc["id"] = str(uuid.uuid4())
            reservation_doc["created_at"] = datetime.now(UTC).isoformat()
            await db.hotelrunner_reservations.insert_one(reservation_doc)
            imported += 1

    await db.hotelrunner_connections.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$set": {"last_sync_at": datetime.now(UTC).isoformat()}},
    )

    await log_sync(current_user.tenant_id, "reservation_sync", "success",
                   records=imported, user_name=current_user.name)

    return {
        "message": f"{imported} yeni rezervasyon senkronize edildi",
        "total_fetched": result["count"],
        "new_imported": imported,
    }


@router.post("/reservations/{hr_number}/confirm")
async def confirm_reservation_delivery(
    hr_number: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v97 DW
):
    """Confirm reservation delivery to HotelRunner."""
    provider, conn = await get_provider(current_user.tenant_id)

    res = await db.hotelrunner_reservations.find_one({
        "tenant_id": current_user.tenant_id,
        "hr_number": hr_number,
    })
    if not res:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    message_uid = res.get("message_uid")
    if not message_uid:
        raise HTTPException(status_code=400, detail="message_uid bulunamadi")

    result = await provider.confirm_delivery(
        message_uid=message_uid,
        pms_number=res.get("pms_booking_id"),
    )

    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"Teslimat onay hatasi: {result['error']}")

    await db.hotelrunner_reservations.update_one(
        {"tenant_id": current_user.tenant_id, "hr_number": hr_number},
        {"$set": {"delivery_confirmed": True, "confirmed_at": datetime.now(UTC).isoformat()}},
    )

    return {"message": "Rezervasyon teslimati onaylandi", "hr_number": hr_number}
