"""
Exely Integration Router
API endpoints for Exely connection management, room discovery, mapping, ARI push, and sync.
"""
import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from pydantic import BaseModel

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks

from core.database import db
from core.security import get_current_user
from models.schemas import User
from domains.channel_manager.providers.common_ingest import ingest_reservation, log_sync
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.normalizer import normalize_reservation
from domains.channel_manager.providers.exely.exely_pull_worker import exely_pull_scheduler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channel-manager/exely", tags=["Exely Integration"])

PROVIDER = "exely"


# ── Request Models ───────────────────────────────────────────────────

class ExelyConnectionSetup(BaseModel):
    username: str
    password: str
    hotel_code: str
    endpoint_url: Optional[str] = None
    property_name: Optional[str] = None
    auto_sync_reservations: bool = True
    sync_interval_minutes: int = 15


class ExelyRoomMapping(BaseModel):
    pms_room_type: str
    exely_room_code: str
    exely_rate_plan_code: str
    exely_room_name: str
    sync_availability: bool = True
    sync_price: bool = True
    sync_restrictions: bool = True


class ExelyARIUpdate(BaseModel):
    room_type_code: str
    rate_plan_code: str
    start_date: str
    end_date: str
    availability: Optional[int] = None
    rate_amount: Optional[float] = None
    currency: str = "TRY"
    stop_sell: Optional[bool] = None
    min_stay: Optional[int] = None


# ── Helpers ──────────────────────────────────────────────────────────

async def _get_client(tenant_id: str) -> tuple:
    conn = await db.exely_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0},
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely baglantisi bulunamadi. Lutfen once baglanti kurun.")
    kwargs = {
        "username": conn["username"],
        "password": conn["password"],
        "hotel_code": conn["hotel_code"],
    }
    if conn.get("endpoint_url"):
        kwargs["endpoint_url"] = conn["endpoint_url"]
    return ExelyProvider(**kwargs), conn


# ── Connection Management ────────────────────────────────────────────

@router.post("/connect")
async def setup_connection(
    payload: ExelyConnectionSetup,
    current_user: User = Depends(get_current_user),
):
    """Setup Exely SOAP connection with credentials and test it."""
    kwargs = {
        "username": payload.username,
        "password": payload.password,
        "hotel_code": payload.hotel_code,
    }
    if payload.endpoint_url:
        kwargs["endpoint_url"] = payload.endpoint_url

    provider = ExelyProvider(**kwargs)
    test_result = await provider.legacy_test_connection()

    if not test_result["connected"]:
        raise HTTPException(status_code=400, detail=f"Exely baglanti hatasi: {test_result['error']}")

    connection = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "username": payload.username,
        "password": payload.password,
        "hotel_code": payload.hotel_code,
        "endpoint_url": payload.endpoint_url or "",
        "property_name": payload.property_name or f"Exely Property ({payload.hotel_code})",
        "auto_sync_reservations": payload.auto_sync_reservations,
        "sync_interval_minutes": payload.sync_interval_minutes,
        "is_active": True,
        "room_types": test_result.get("room_types", []),
        "rate_plans": test_result.get("rate_plans", []),
        "connected_at": datetime.now(timezone.utc).isoformat(),
        "last_sync_at": None,
        "created_by": current_user.name,
    }

    await db.exely_connections.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$set": connection},
        upsert=True,
    )

    await log_sync(PROVIDER, current_user.tenant_id, "connection", "success",
                    duration_ms=test_result.get("duration_ms", 0), user_name=current_user.name)

    return {
        "message": "Exely baglantisi basariyla kuruldu",
        "connected": True,
        "room_types": test_result.get("room_types", []),
        "rate_plans": test_result.get("rate_plans", []),
        "connection_id": connection["id"],
    }


@router.get("/connection")
async def get_connection_status(current_user: User = Depends(get_current_user)):
    conn = await db.exely_connections.find_one(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0, "password": 0},
    )
    if not conn:
        return {"connected": False, "message": "Exely baglantisi kurulmamis"}
    return {"connected": conn.get("is_active", False), "connection": conn}


@router.post("/test")
async def test_connection(current_user: User = Depends(get_current_user)):
    client, conn = await _get_client(current_user.tenant_id)
    result = await client.legacy_test_connection()
    return result


@router.delete("/disconnect")
async def disconnect(current_user: User = Depends(get_current_user)):
    result = await db.exely_connections.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$set": {"is_active": False, "disconnected_at": datetime.now(timezone.utc).isoformat()}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Aktif baglanti bulunamadi")
    return {"message": "Exely baglantisi kesildi"}


# ── Room Discovery ───────────────────────────────────────────────────

@router.get("/rooms/discover")
async def discover_rooms(
    checkin: Optional[str] = None,
    checkout: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    """Discover room types and rate plans from Exely via OTA_HotelAvailRQ."""
    client, conn = await _get_client(current_user.tenant_id)
    ci = checkin or datetime.now().strftime("%Y-%m-%d")
    co = checkout or (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    result = await client.legacy_discover_rooms(ci, co)
    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"Exely oda kesfetme hatasi: {result['error']}")

    # Cache discovered rooms/rates on connection
    await db.exely_connections.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$set": {
            "room_types": result["room_types"],
            "rate_plans": result["rate_plans"],
            "rooms_fetched_at": datetime.now(timezone.utc).isoformat(),
        }},
    )

    return {
        "room_types": result["room_types"],
        "rate_plans": result["rate_plans"],
    }


# ── Room Mapping ─────────────────────────────────────────────────────

@router.post("/room-mappings")
async def create_room_mapping(
    payload: ExelyRoomMapping,
    current_user: User = Depends(get_current_user),
):
    mapping = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "pms_room_type": payload.pms_room_type,
        "exely_room_code": payload.exely_room_code,
        "exely_rate_plan_code": payload.exely_rate_plan_code,
        "exely_room_name": payload.exely_room_name,
        "sync_availability": payload.sync_availability,
        "sync_price": payload.sync_price,
        "sync_restrictions": payload.sync_restrictions,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "created_by": current_user.name,
    }
    await db.exely_room_mappings.insert_one(mapping)
    mapping.pop("_id", None)
    return {"message": "Oda eslesmesi olusturuldu", "mapping": mapping}


@router.get("/room-mappings")
async def get_room_mappings(current_user: User = Depends(get_current_user)):
    mappings = await db.exely_room_mappings.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0},
    ).to_list(100)
    return {"mappings": mappings, "count": len(mappings)}


@router.delete("/room-mappings/{mapping_id}")
async def delete_room_mapping(
    mapping_id: str,
    current_user: User = Depends(get_current_user),
):
    result = await db.exely_room_mappings.delete_one({
        "id": mapping_id, "tenant_id": current_user.tenant_id,
    })
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Esleme bulunamadi")
    return {"message": "Esleme silindi"}


# ── ARI Push ─────────────────────────────────────────────────────────

@router.post("/ari/push")
async def push_ari(
    payload: ExelyARIUpdate,
    current_user: User = Depends(get_current_user),
):
    """Push a delta ARI update to Exely."""
    client, conn = await _get_client(current_user.tenant_id)
    result = await client.legacy_push_ari(
        room_type_code=payload.room_type_code,
        rate_plan_code=payload.rate_plan_code,
        start_date=payload.start_date,
        end_date=payload.end_date,
        availability=payload.availability,
        rate_amount=payload.rate_amount,
        currency=payload.currency,
        stop_sell=payload.stop_sell,
        min_stay=payload.min_stay,
    )

    status = "success" if result["success"] else "failed"
    await log_sync(PROVIDER, current_user.tenant_id, "ari_push", status,
                    duration_ms=result.get("duration_ms", 0), records=1,
                    error=result.get("error"), user_name=current_user.name)

    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"ARI push hatasi: {result['error']}")

    return {"message": "ARI guncelleme Exely'ye gonderildi", "result": result}


@router.post("/ari/bulk-push")
async def bulk_push_ari(
    updates: List[ExelyARIUpdate],
    current_user: User = Depends(get_current_user),
):
    """Push multiple ARI updates."""
    client, conn = await _get_client(current_user.tenant_id)
    results = []
    for u in updates:
        r = await client.push_ari(
            room_type_code=u.room_type_code,
            rate_plan_code=u.rate_plan_code,
            start_date=u.start_date,
            end_date=u.end_date,
            availability=u.availability,
            rate_amount=u.rate_amount,
            currency=u.currency,
            stop_sell=u.stop_sell,
            min_stay=u.min_stay,
        )
        results.append(r)

    success_count = sum(1 for r in results if r.get("success"))
    await log_sync(PROVIDER, current_user.tenant_id, "ari_bulk_push",
                    "success" if success_count == len(results) else "partial",
                    records=success_count, user_name=current_user.name)

    return {"total": len(results), "success": success_count, "failed": len(results) - success_count, "results": results}


# ── Reservation Sync ─────────────────────────────────────────────────

@router.post("/sync/reservations/pull")
async def manual_pull(current_user: User = Depends(get_current_user)):
    """Manually trigger a reservation pull from Exely."""
    conn = await db.exely_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True}, {"_id": 0},
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely baglantisi bulunamadi")

    result = await exely_pull_scheduler.pull_for_tenant(
        tenant_id=current_user.tenant_id,
        username=conn["username"],
        password=conn["password"],
        hotel_code=conn["hotel_code"],
        endpoint_url=conn.get("endpoint_url", ""),
    )

    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"Pull hatasi: {result.get('error')}")

    return {
        "message": f"{result['processed']} rezervasyon islendi ({result['fetched']} cekildi)",
        **result,
    }


@router.get("/reservations/local")
async def get_local_reservations(
    pms_status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    query = {"tenant_id": current_user.tenant_id}
    if pms_status:
        query["pms_status"] = pms_status
    reservations = await db.exely_reservations.find(
        query, {"_id": 0},
    ).sort("synced_at", -1).to_list(100)
    return {"reservations": reservations, "count": len(reservations)}


@router.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: str,
    current_user: User = Depends(get_current_user),
):
    """Confirm reservation delivery to Exely via OTA_NotifReportRQ."""
    client, conn = await _get_client(current_user.tenant_id)

    res = await db.exely_reservations.find_one({
        "tenant_id": current_user.tenant_id,
        "external_id": reservation_id,
    })
    if not res:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    pms_booking_id = res.get("pms_booking_id") or reservation_id
    result = await client.legacy_confirm_delivery(reservation_id, pms_booking_id)

    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"Teslimat onay hatasi: {result['error']}")

    await db.exely_reservations.update_one(
        {"tenant_id": current_user.tenant_id, "external_id": reservation_id},
        {"$set": {"delivery_confirmed": True, "confirmed_at": datetime.now(timezone.utc).isoformat()}},
    )

    return {"message": "Rezervasyon teslimati onaylandi", "reservation_id": reservation_id}


# ── Sync Status & Scheduler ─────────────────────────────────────────

@router.get("/sync/status")
async def get_sync_status(current_user: User = Depends(get_current_user)):
    cursor = await db.exely_pull_cursors.find_one(
        {"tenant_id": current_user.tenant_id}, {"_id": 0},
    )
    pending_events = await db.exely_raw_events.count_documents(
        {"tenant_id": current_user.tenant_id, "status": "pending"},
    )
    error_events = await db.exely_raw_events.count_documents(
        {"tenant_id": current_user.tenant_id, "status": "error"},
    )
    total_reservations = await db.exely_reservations.count_documents(
        {"tenant_id": current_user.tenant_id},
    )
    return {
        "scheduler_running": exely_pull_scheduler.is_running,
        "last_pull": cursor,
        "pending_events": pending_events,
        "error_events": error_events,
        "total_reservations": total_reservations,
    }


@router.post("/sync/scheduler/start")
async def start_scheduler(current_user: User = Depends(get_current_user)):
    conn = await db.exely_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True}, {"_id": 0},
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely baglantisi bulunamadi")
    interval = conn.get("sync_interval_minutes", 15)
    await exely_pull_scheduler.start(interval_minutes=interval)
    return {"message": f"Scheduler baslatildi ({interval} dk aralikla)", "interval": interval}


@router.post("/sync/scheduler/stop")
async def stop_scheduler(current_user: User = Depends(get_current_user)):
    await exely_pull_scheduler.stop()
    return {"message": "Scheduler durduruldu"}


# ── Sync Logs ────────────────────────────────────────────────────────

@router.get("/sync-logs")
async def get_sync_logs(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
):
    logs = await db.exely_sync_logs.find(
        {"tenant_id": current_user.tenant_id}, {"_id": 0},
    ).sort("timestamp", -1).to_list(limit)
    return {"logs": logs, "count": len(logs)}


# ── Raw Events / Debug ──────────────────────────────────────────────

@router.get("/logs/events")
async def get_raw_events(
    limit: int = 50,
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user),
):
    query = {"tenant_id": current_user.tenant_id}
    if status:
        query["status"] = status
    events = await db.exely_raw_events.find(
        query, {"_id": 0, "payload": 0},
    ).sort("received_at", -1).to_list(limit)
    return {"events": events, "count": len(events)}
