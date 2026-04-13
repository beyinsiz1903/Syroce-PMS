"""
HotelRunner Integration Router
API endpoints for HotelRunner connection management, testing, and operations.
"""
import logging
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.database import db
from core.secrets import get_secrets_manager
from core.security import get_current_user
from models.schemas import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channel-manager/hotelrunner", tags=["HotelRunner Integration"])


# ── Request/Response Models ──────────────────────────────────────────

class HRCredentials(BaseModel):
    token: str
    hr_id: str


class HRConnectionSetup(BaseModel):
    token: str
    hr_id: str
    property_name: str | None = None
    environment: str = "production"  # production | sandbox | mock
    auto_sync_reservations: bool = True
    auto_confirm_delivery: bool = False
    sync_interval_minutes: int = 15


class HRARIUpdate(BaseModel):
    inv_code: str
    start_date: str
    end_date: str
    availability: int | None = None
    price: float | None = None
    stop_sale: int | None = None
    min_stay: int | None = None
    cta: int | None = None
    ctd: int | None = None
    days: list[int] | None = None
    channel_codes: list[str] | None = None


class HRReservationFilter(BaseModel):
    undelivered: bool = True
    from_date: str | None = None
    per_page: int = 10
    page: int = 1
    modified: bool = False
    booked: bool = False


# ── Helper: Get provider instance ────────────────────────────────────

async def _get_provider(tenant_id: str):
    """Get HotelRunner provider instance for a tenant via secrets manager."""
    from domains.channel_manager.providers.hotelrunner import HotelRunnerProvider

    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True},
        {"_id": 0, "token": 0},
    )
    if not conn:
        pc = await db.provider_connections.find_one(
            {"tenant_id": tenant_id, "provider": "hotelrunner", "status": "active"},
        )
        if pc:
            pc_creds = pc.get("credentials", {})
            legacy = await db.hotelrunner_connections.find_one(
                {"tenant_id": tenant_id}, {"_id": 0, "cached_rooms": 1}
            )
            conn = {
                "tenant_id": tenant_id,
                "hr_id": pc_creds.get("hr_id", ""),
                "token": pc_creds.get("token", pc_creds.get("hr_token", "")),
                "property_name": pc.get("display_name", ""),
                "environment": pc.get("environment", "live"),
                "is_active": True,
                "channels": [],
                "cached_rooms": (legacy or {}).get("cached_rooms", []),
            }
        else:
            raise HTTPException(status_code=404, detail="HotelRunner baglantisi bulunamadi. Lutfen once baglanti kurun.")

    # Resolve environment
    environment = conn.get("environment", "mock")

    # Resolve credentials via secrets manager (with legacy fallback)
    sm = get_secrets_manager()
    property_id = conn.get("hr_id", conn.get("property_id", "default"))
    creds = await sm.get_provider_credentials(tenant_id, "hotelrunner", property_id)

    if not creds or not creds.get("token"):
        # Final fallback: read from connection doc (pre-migration data)
        fallback_conn = await db.hotelrunner_connections.find_one(
            {"tenant_id": tenant_id, "is_active": True},
            {"_id": 0, "token": 1, "hr_id": 1},
        )
        if fallback_conn and fallback_conn.get("token"):
            creds = {"token": fallback_conn["token"], "hr_id": fallback_conn.get("hr_id", "")}
            logger.warning("Using legacy plaintext credentials for HotelRunner tenant=%s — migrate ASAP", tenant_id)
        else:
            raise HTTPException(status_code=502, detail="HotelRunner kimlik bilgileri bulunamadi")

    try:
        return HotelRunnerProvider(
            token=creds["token"],
            hr_id=creds.get("hr_id", ""),
            environment=environment,
        ), conn
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"HotelRunner kimlik bilgileri gecersiz: {exc}")


async def _log_sync(tenant_id: str, sync_type: str, status: str, duration_ms: int = 0,
                     records: int = 0, error: str | None = None, user_name: str = "system"):
    """Log a sync event."""
    await db.hotelrunner_sync_logs.insert_one({
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "timestamp": datetime.now(UTC).isoformat(),
        "sync_type": sync_type,
        "status": status,
        "duration_ms": duration_ms,
        "records_synced": records,
        "error_message": error,
        "initiator": user_name,
    })


# ── Connection Management ────────────────────────────────────────────

@router.post("/connect")
async def setup_connection(
    payload: HRConnectionSetup,
    current_user: User = Depends(get_current_user),
):
    """Setup HotelRunner connection with credentials and test it."""
    from domains.channel_manager.providers.hotelrunner import HotelRunnerProvider

    logger.info(
        "[HR-CONNECT] env=%s hr_id=%s token=%s...%s",
        payload.environment, payload.hr_id,
        payload.token[:4] if len(payload.token) > 8 else "****",
        payload.token[-4:] if len(payload.token) > 8 else "****",
    )

    provider = HotelRunnerProvider(
        token=payload.token,
        hr_id=payload.hr_id,
        environment=payload.environment,
    )

    logger.info("[HR-CONNECT] target_url=%s", provider._base_url)

    test_result = await provider.test_connection()

    if not test_result.success:
        logger.error("[HR-CONNECT] FAILED: %s (env=%s, url=%s)", test_result.error, payload.environment, provider._base_url)
        raise HTTPException(status_code=400, detail=f"HotelRunner baglanti hatasi: {test_result.error}")

    result_data = test_result.data or {}

    # Store credentials in secrets manager (encrypted, never in connection doc)
    sm = get_secrets_manager()
    await sm.store_provider_credentials(
        tenant_id=current_user.tenant_id,
        provider="hotelrunner",
        property_id=payload.hr_id,
        credentials={"token": payload.token, "hr_id": payload.hr_id},
        actor=current_user.name,
    )

    connection = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "hr_id": payload.hr_id,
        "credentials_ref": f"secrets_manager::hotelrunner::{payload.hr_id}",
        "environment": payload.environment,
        "property_name": payload.property_name or "HotelRunner Property",
        "auto_sync_reservations": payload.auto_sync_reservations,
        "auto_confirm_delivery": payload.auto_confirm_delivery,
        "sync_interval_minutes": payload.sync_interval_minutes,
        "is_active": True,
        "channels": result_data.get("channels", []),
        "connected_at": datetime.now(UTC).isoformat(),
        "last_sync_at": None,
        "created_by": current_user.name,
    }

    await db.hotelrunner_connections.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$set": connection},
        upsert=True,
    )

    # Remove any legacy plaintext token from the connection doc
    await db.hotelrunner_connections.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$unset": {"token": ""}},
    )

    await _log_sync(current_user.tenant_id, "connection", "success",
                     duration_ms=test_result.duration_ms, user_name=current_user.name)

    channels = (test_result.data or {}).get("channels", [])
    return {
        "message": "HotelRunner baglantisi basariyla kuruldu",
        "connected": True,
        "channels": channels,
        "connection_id": connection["id"],
    }


@router.get("/connection")
async def get_connection_status(current_user: User = Depends(get_current_user)):
    """Get current HotelRunner connection status."""
    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0, "token": 0, "credentials_ref": 0},
    )
    if not conn:
        return {"connected": False, "message": "HotelRunner baglantisi kurulmamis"}

    return {"connected": conn.get("is_active", False), "connection": conn}


@router.post("/test")
async def test_connection(current_user: User = Depends(get_current_user)):
    """Test existing HotelRunner connection."""
    tid = current_user.tenant_id
    hr_conn = await db.hotelrunner_connections.find_one({"tenant_id": tid, "is_active": True})
    if not hr_conn:
        hr_conn = await db.provider_connections.find_one(
            {"tenant_id": tid, "provider": "hotelrunner", "status": "active"}
        )
    if not hr_conn:
        raise HTTPException(status_code=404, detail="HotelRunner baglantisi bulunamadi. Lutfen once baglanti kurun.")

    env = hr_conn.get("environment") or hr_conn.get("mode")
    if env in ("sandbox", "mock"):
        return {"success": True, "connected": True, "mode": env, "message": "Sandbox/mock test basarili"}

    provider, conn = await _get_provider(tid)
    result = await provider.test_connection()
    return result


@router.delete("/disconnect")
async def disconnect(current_user: User = Depends(get_current_user)):
    """Disconnect HotelRunner integration."""
    result = await db.hotelrunner_connections.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$set": {"is_active": False, "disconnected_at": datetime.now(UTC).isoformat()}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Aktif baglanti bulunamadi")

    return {"message": "HotelRunner baglantisi kesildi"}


# ── Room / Inventory Operations ──────────────────────────────────────

@router.get("/rooms")
async def get_rooms(current_user: User = Depends(get_current_user)):
    """Fetch all rooms/rates from HotelRunner."""
    provider, conn = await _get_provider(current_user.tenant_id)
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
):
    """Push ARI update to HotelRunner."""
    provider, conn = await _get_provider(current_user.tenant_id)

    update_data = payload.model_dump(exclude_none=True)
    result = await provider.update_room(**update_data)

    status = "success" if result["success"] else "failed"
    await _log_sync(current_user.tenant_id, "ari_push", status,
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
):
    """Push multiple ARI updates to HotelRunner."""
    provider, conn = await _get_provider(current_user.tenant_id)

    update_dicts = [u.model_dump(exclude_none=True) for u in updates]
    results = await provider.push_ari_bulk(update_dicts)

    success_count = sum(1 for r in results if r.get("success"))
    fail_count = len(results) - success_count

    await _log_sync(current_user.tenant_id, "ari_bulk_push", "success" if fail_count == 0 else "partial",
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
    provider, conn = await _get_provider(current_user.tenant_id)

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
async def sync_reservations(current_user: User = Depends(get_current_user)):
    """Pull all undelivered reservations and store them for PMS import."""
    provider, conn = await _get_provider(current_user.tenant_id)

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

    await _log_sync(current_user.tenant_id, "reservation_sync", "success",
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
):
    """Confirm reservation delivery to HotelRunner."""
    provider, conn = await _get_provider(current_user.tenant_id)

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


@router.get("/reservations/local")
async def get_local_reservations(
    pms_status: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Get locally stored HotelRunner reservations."""
    query = {"tenant_id": current_user.tenant_id}
    if pms_status:
        query["pms_status"] = pms_status

    reservations = await db.hotelrunner_reservations.find(
        query, {"_id": 0, "raw_data": 0}
    ).sort("synced_at", -1).to_list(100)

    return {"reservations": reservations, "count": len(reservations)}


# ── Channel Operations ───────────────────────────────────────────────

@router.get("/channels")
async def get_channels(current_user: User = Depends(get_current_user)):
    """Get all available HotelRunner channels."""
    provider, conn = await _get_provider(current_user.tenant_id)
    result = await provider.get_channels()
    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"Kanal listesi hatasi: {result['error']}")
    return result["data"]


@router.get("/channels/connected")
async def get_connected_channels(current_user: User = Depends(get_current_user)):
    """Get connected channels with process stats."""
    provider, conn = await _get_provider(current_user.tenant_id)
    result = await provider.get_connected_channels()
    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"Bagli kanal listesi hatasi: {result['error']}")
    return result["data"]


# ── Transaction Tracking ─────────────────────────────────────────────

@router.get("/transactions/{transaction_id}")
async def get_transaction_details(
    transaction_id: str,
    current_user: User = Depends(get_current_user),
):
    """Get transaction status details."""
    provider, conn = await _get_provider(current_user.tenant_id)
    result = await provider.get_transaction_details(transaction_id)
    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"Islem detay hatasi: {result['error']}")
    return result["data"]


# ── Room Mapping ─────────────────────────────────────────────────────

class HRRoomMapping(BaseModel):
    pms_room_type: str
    hr_inv_code: str
    hr_rate_code: str
    hr_room_name: str
    sync_availability: bool = True
    sync_price: bool = True
    sync_restrictions: bool = True


@router.get("/pms-room-types")
async def get_pms_room_types(current_user: User = Depends(get_current_user)):
    """Get distinct PMS room types for mapping dropdown."""
    types = await db.rooms.distinct("room_type", {"tenant_id": current_user.tenant_id})
    return {"room_types": [t for t in types if t]}


@router.get("/cached-rooms")
async def get_cached_hr_rooms(current_user: User = Depends(get_current_user)):
    """Get cached HotelRunner rooms from last fetch."""
    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"_id": 0, "cached_rooms": 1, "rooms_fetched_at": 1},
    )
    if not conn:
        return {"rooms": [], "fetched_at": None}
    return {
        "rooms": conn.get("cached_rooms", []),
        "fetched_at": conn.get("rooms_fetched_at"),
    }


@router.post("/room-mappings")
async def create_room_mapping(
    payload: HRRoomMapping,
    current_user: User = Depends(get_current_user),
):
    """Create a PMS <> HotelRunner room mapping."""
    existing = await db.hotelrunner_room_mappings.find_one({
        "tenant_id": current_user.tenant_id,
        "hr_inv_code": payload.hr_inv_code,
        "hr_rate_code": payload.hr_rate_code,
    })
    if existing:
        await db.hotelrunner_room_mappings.update_one(
            {"_id": existing["_id"]},
            {"$set": {
                "pms_room_type": payload.pms_room_type,
                "hr_room_name": payload.hr_room_name,
                "sync_availability": payload.sync_availability,
                "sync_price": payload.sync_price,
                "sync_restrictions": payload.sync_restrictions,
                "updated_at": datetime.now(UTC).isoformat(),
                "updated_by": current_user.name,
            }},
        )
        return {"message": "Oda eslemesi guncellendi", "mapping_id": existing.get("id")}

    mapping = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "pms_room_type": payload.pms_room_type,
        "hr_inv_code": payload.hr_inv_code,
        "hr_rate_code": payload.hr_rate_code,
        "hr_room_name": payload.hr_room_name,
        "sync_availability": payload.sync_availability,
        "sync_price": payload.sync_price,
        "sync_restrictions": payload.sync_restrictions,
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.name,
    }

    await db.hotelrunner_room_mappings.insert_one(mapping)
    mapping.pop("_id", None)
    return {"message": "Oda eslemesi olusturuldu", "mapping": mapping}


@router.post("/room-mappings/bulk")
async def bulk_create_room_mappings(
    mappings_data: list[HRRoomMapping],
    current_user: User = Depends(get_current_user),
):
    """Create or update multiple room mappings at once."""
    created = 0
    updated = 0
    for m in mappings_data:
        existing = await db.hotelrunner_room_mappings.find_one({
            "tenant_id": current_user.tenant_id,
            "hr_inv_code": m.hr_inv_code,
            "hr_rate_code": m.hr_rate_code,
        })
        if existing:
            await db.hotelrunner_room_mappings.update_one(
                {"_id": existing["_id"]},
                {"$set": {
                    "pms_room_type": m.pms_room_type,
                    "hr_room_name": m.hr_room_name,
                    "sync_availability": m.sync_availability,
                    "sync_price": m.sync_price,
                    "sync_restrictions": m.sync_restrictions,
                    "updated_at": datetime.now(UTC).isoformat(),
                    "updated_by": current_user.name,
                }},
            )
            updated += 1
        else:
            doc = {
                "id": str(uuid.uuid4()),
                "tenant_id": current_user.tenant_id,
                "pms_room_type": m.pms_room_type,
                "hr_inv_code": m.hr_inv_code,
                "hr_rate_code": m.hr_rate_code,
                "hr_room_name": m.hr_room_name,
                "sync_availability": m.sync_availability,
                "sync_price": m.sync_price,
                "sync_restrictions": m.sync_restrictions,
                "created_at": datetime.now(UTC).isoformat(),
                "created_by": current_user.name,
            }
            await db.hotelrunner_room_mappings.insert_one(doc)
            created += 1

    return {"message": f"{created} yeni, {updated} guncellenen esleme", "created": created, "updated": updated}


@router.get("/room-mappings")
async def get_room_mappings(current_user: User = Depends(get_current_user)):
    """Get all PMS <> HotelRunner room mappings."""
    mappings = await db.hotelrunner_room_mappings.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0},
    ).to_list(100)
    return {"mappings": mappings, "count": len(mappings)}


@router.delete("/room-mappings/{mapping_id}")
async def delete_room_mapping(
    mapping_id: str,
    current_user: User = Depends(get_current_user),
):
    """Delete a room mapping."""
    result = await db.hotelrunner_room_mappings.delete_one({
        "id": mapping_id,
        "tenant_id": current_user.tenant_id,
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Esleme bulunamadi")
    return {"message": "Esleme silindi"}


# ── Sync Logs ────────────────────────────────────────────────────────

@router.get("/sync-logs")
async def get_sync_logs(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
):
    """Get HotelRunner sync logs."""
    logs = await db.hotelrunner_sync_logs.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0},
    ).sort("timestamp", -1).to_list(limit)
    return {"logs": logs, "count": len(logs)}


# ── API Usage Stats ──────────────────────────────────────────────────

@router.get("/usage")
async def get_api_usage(current_user: User = Depends(get_current_user)):
    """Get HotelRunner API usage statistics."""
    provider, conn = await _get_provider(current_user.tenant_id)
    stats = provider.get_usage_stats()
    stats["last_sync_at"] = conn.get("last_sync_at")
    stats["connected_at"] = conn.get("connected_at")
    return stats
