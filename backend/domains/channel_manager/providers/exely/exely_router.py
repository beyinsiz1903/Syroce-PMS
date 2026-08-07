"""
Exely Integration Router
API endpoints for Exely connection management, room discovery, mapping, ARI push, and sync.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.database import db
from core.secrets import get_secrets_manager
from core.security import get_current_user
from domains.channel_manager.providers.common_ingest import ingest_reservation, log_sync
from domains.channel_manager.providers.exely.ari_publish import enqueue_exely_ari_update
from domains.channel_manager.providers.exely.errors import ExelyError
from domains.channel_manager.providers.exely.exely_pull_worker import exely_pull_scheduler
from domains.channel_manager.providers.exely.normalizer import normalize_reservation
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.security import (
    exely_connection_projection,
    resolve_exely_credentials,
)
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v93 DW

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channel-manager/exely", tags=["Exely Integration"])

PROVIDER = "exely"


# ── Request Models ───────────────────────────────────────────────────


class ExelyConnectionSetup(BaseModel):
    username: str
    password: str
    hotel_code: str
    endpoint_url: str | None = None
    property_name: str | None = None
    currency: str = "TRY"
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
    availability: int | None = None
    rate_amount: float | None = None
    currency: str = "TRY"
    stop_sell: bool | None = None
    min_stay: int | None = None
    min_los_arrival: int | None = None
    max_stay: int | None = None
    cta: bool | None = None
    ctd: bool | None = None


# ── Helpers ──────────────────────────────────────────────────────────


async def _get_client(tenant_id: str) -> tuple:
    conn = await db.exely_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True},
        exely_connection_projection(),
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely connection not found. Please set up a connection first.")

    creds = await resolve_exely_credentials(tenant_id, conn, actor="exely_router")
    if not creds:
        raise HTTPException(status_code=503, detail="Exely credentials are unavailable")
    kwargs = {
        "username": creds["username"],
        "password": creds["password"],
        "hotel_code": creds["hotel_code"],
        "endpoint_url": creds["endpoint_url"],
        "tenant_id": tenant_id,
        "property_id": creds["hotel_code"],
        "connection_id": f"{tenant_id}:{creds['hotel_code']}",
    }
    try:
        return ExelyProvider(**kwargs), conn
    except ExelyError as exc:
        raise HTTPException(status_code=502, detail=f"Exely connection rejected ({type(exc).__name__})")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Exely connection failed ({type(exc).__name__})")


# ── Connection Management ────────────────────────────────────────────


@router.post("/connect")
async def setup_connection(
    payload: ExelyConnectionSetup,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    """Setup Exely SOAP connection with credentials and test it."""
    kwargs = {
        "username": payload.username,
        "password": payload.password,
        "hotel_code": payload.hotel_code,
        "tenant_id": current_user.tenant_id,
        "property_id": payload.hotel_code,
        "connection_id": f"{current_user.tenant_id}:{payload.hotel_code}",
    }
    if payload.endpoint_url:
        kwargs["endpoint_url"] = payload.endpoint_url

    provider = ExelyProvider(**kwargs)
    provider_result = await provider.test_connection()
    test_data = provider_result.data or {}

    if not provider_result.success:
        raise HTTPException(status_code=400, detail="Exely connection test failed")

    # Store credentials in secrets manager (encrypted, audited)
    sm = get_secrets_manager()
    vault_payload = {
        "username": payload.username,
        "password": payload.password,
        "hotel_code": payload.hotel_code,
        "endpoint_url": payload.endpoint_url or "",
        "currency": payload.currency,
    }
    credentials_ref = await sm.store_provider_credentials(
        tenant_id=current_user.tenant_id,
        provider=PROVIDER,
        property_id=payload.hotel_code,
        credentials=vault_payload,
        actor=current_user.name,
    )

    connection = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "hotel_code": payload.hotel_code,
        "credentials_ref": credentials_ref,
        "endpoint_url": payload.endpoint_url or "",
        "property_name": payload.property_name or f"Exely Property ({payload.hotel_code})",
        "auto_sync_reservations": payload.auto_sync_reservations,
        "ari_write_enabled": False,
        "sync_interval_minutes": payload.sync_interval_minutes,
        "mode": "sandbox",
        "currency": payload.currency,
        "is_active": True,
        "room_types": test_data.get("room_types", []),
        "rate_plans": test_data.get("rate_plans", []),
        "connected_at": datetime.now(UTC).isoformat(),
        "last_sync_at": None,
        "created_by": current_user.name,
    }

    await db.exely_connections.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$set": connection},
        upsert=True,
    )

    await log_sync(PROVIDER, current_user.tenant_id, "connection", "success", duration_ms=provider_result.duration_ms, user_name=current_user.name)

    return {
        "message": "Exely connection established successfully",
        "connected": True,
        "room_types": test_data.get("room_types", []),
        "rate_plans": test_data.get("rate_plans", []),
        "connection_id": connection["id"],
    }


@router.get("/connection")
async def get_connection_status(current_user: User = Depends(get_current_user)):
    conn = await db.exely_connections.find_one(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0, "password": 0, "username": 0, "credentials_ref": 0, "endpoint_url": 0},
    )
    if not conn:
        return {"connected": False, "message": "Exely connection not configured"}
    return {"connected": conn.get("is_active", False), "connection": conn}


@router.post("/test")
async def test_connection(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    conn = await db.exely_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        exely_connection_projection(),
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely connection not found")
    if conn.get("mode") == "sandbox":
        return {
            "success": True,
            "connected": True,
            "message": "Sandbox mode — connection active and ready",
            "hotel_code": conn.get("hotel_code", ""),
            "property_name": conn.get("property_name", ""),
            "mode": "sandbox",
        }
    client, _conn = await _get_client(current_user.tenant_id)
    result = await client.test_connection()
    data = result.data or {}
    return {
        "success": result.success,
        "connected": bool(result.success and data.get("connected")),
        "room_types": data.get("room_types", []),
        "rate_plans": data.get("rate_plans", []),
        "duration_ms": result.duration_ms,
        "error_type": result.error_type if not result.success else None,
    }


@router.delete("/disconnect")
async def disconnect(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    result = await db.exely_connections.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$set": {"is_active": False, "disconnected_at": datetime.now(UTC).isoformat()}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Active connection not found")
    return {"message": "Exely connection disconnected"}


class CurrencyUpdateRequest(BaseModel):
    currency: str  # TRY, USD, EUR


@router.patch("/currency")
async def update_currency(
    payload: CurrencyUpdateRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    """Update the currency for the Exely connection."""
    allowed = {"TRY", "USD", "EUR", "GBP", "RUB"}
    if payload.currency not in allowed:
        raise HTTPException(status_code=400, detail=f"Unsupported currency. Supported: {', '.join(sorted(allowed))}")
    result = await db.exely_connections.update_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"$set": {"currency": payload.currency}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Active connection not found")
    return {"message": f"Currency updated to {payload.currency}", "currency": payload.currency}


# ── Room Discovery ───────────────────────────────────────────────────


@router.get("/rooms/discover")
async def discover_rooms(
    checkin: str | None = None,
    checkout: str | None = None,
    current_user: User = Depends(get_current_user),
):
    """Discover room types and rate plans from Exely via OTA_HotelAvailRQ."""
    client, conn = await _get_client(current_user.tenant_id)
    ci = checkin or datetime.now().strftime("%Y-%m-%d")
    co = checkout or (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    result = await client.discover_rooms(ci, co)
    if not result.success:
        raise HTTPException(status_code=502, detail=f"Exely room discovery error ({result.error_type})")
    data = result.data or {}

    # Cache discovered rooms/rates on connection
    await db.exely_connections.update_one(
        {"tenant_id": current_user.tenant_id},
        {
            "$set": {
                "room_types": data.get("room_types", []),
                "rate_plans": data.get("rate_plans", []),
                "rooms_fetched_at": datetime.now(UTC).isoformat(),
            }
        },
    )

    return {
        "room_types": data.get("room_types", []),
        "rate_plans": data.get("rate_plans", []),
    }


# ── Room Mapping ─────────────────────────────────────────────────────


@router.post("/room-mappings")
async def create_room_mapping(
    payload: ExelyRoomMapping,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
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
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.name,
    }
    await db.exely_room_mappings.insert_one(mapping)
    mapping.pop("_id", None)
    return {"message": "Oda eslesmesi olusturuldu", "mapping": mapping}


@router.get("/room-mappings")
async def get_room_mappings(current_user: User = Depends(get_current_user)):
    mappings = await db.exely_room_mappings.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0},
    ).to_list(100)
    return {"mappings": mappings, "count": len(mappings)}


@router.delete("/room-mappings/{mapping_id}")
async def delete_room_mapping(
    mapping_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    result = await db.exely_room_mappings.delete_one(
        {
            "id": mapping_id,
            "tenant_id": current_user.tenant_id,
        }
    )
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Esleme bulunamadi")
    return {"message": "Esleme silindi"}


# ── ARI Push ─────────────────────────────────────────────────────────


@router.post("/ari/push", status_code=202)
async def push_ari(
    payload: ExelyARIUpdate,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v100 DW
):
    """Durably queue an ARI update for the canonical Exely worker."""
    conn = await db.exely_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"_id": 0, "hotel_code": 1},
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely connection not found")
    result = await enqueue_exely_ari_update(
        current_user.tenant_id,
        str(conn.get("hotel_code") or ""),
        room_type_code=payload.room_type_code,
        rate_plan_code=payload.rate_plan_code,
        start_date=payload.start_date,
        end_date=payload.end_date,
        source_service="exely_router",
        availability=payload.availability,
        rate_amount=payload.rate_amount,
        currency=payload.currency,
        stop_sell=payload.stop_sell,
        min_los=payload.min_stay,
        min_los_arrival=payload.min_los_arrival,
        max_los=payload.max_stay,
        cta=payload.cta,
        ctd=payload.ctd,
        actor_id=current_user.id,
    )

    await log_sync(
        PROVIDER,
        current_user.tenant_id,
        "ari_queue",
        "queued" if result["accepted"] else "blocked",
        records=result["queued_operation_count"],
        user_name=current_user.name,
    )
    if not result["accepted"]:
        raise HTTPException(status_code=422, detail="No supported ARI mutation was supplied")
    return {"message": "ARI update queued", "result": result}


@router.post("/ari/bulk-push", status_code=202)
async def bulk_push_ari(
    updates: list[ExelyARIUpdate],
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),
):
    """Durably queue multiple ARI updates without direct provider writes."""
    conn = await db.exely_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"_id": 0, "hotel_code": 1},
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely connection not found")
    results = []
    for u in updates:
        r = await enqueue_exely_ari_update(
            current_user.tenant_id,
            str(conn.get("hotel_code") or ""),
            room_type_code=u.room_type_code,
            rate_plan_code=u.rate_plan_code,
            start_date=u.start_date,
            end_date=u.end_date,
            source_service="exely_router_bulk",
            availability=u.availability,
            rate_amount=u.rate_amount,
            currency=u.currency,
            stop_sell=u.stop_sell,
            min_los=u.min_stay,
            min_los_arrival=u.min_los_arrival,
            max_los=u.max_stay,
            cta=u.cta,
            ctd=u.ctd,
            actor_id=current_user.id,
        )
        results.append(r)

    accepted_count = sum(1 for r in results if r.get("accepted"))
    await log_sync(
        PROVIDER,
        current_user.tenant_id,
        "ari_bulk_queue",
        "queued" if accepted_count == len(results) else "partial",
        records=accepted_count,
        user_name=current_user.name,
    )

    return {
        "total": len(results),
        "queued": accepted_count,
        "blocked": len(results) - accepted_count,
        "provider_write_count": 0,
        "results": results,
    }


# ── Reservation Sync ─────────────────────────────────────────────────


@router.post("/sync/reservations/pull")
async def manual_pull(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),
):
    """Manually trigger a reservation pull from Exely."""
    conn = await db.exely_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        exely_connection_projection(),
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely connection not found")

    creds = await resolve_exely_credentials(current_user.tenant_id, conn, actor="exely_manual_pull")
    if not creds:
        raise HTTPException(status_code=503, detail="Exely credentials are unavailable")

    result = await exely_pull_scheduler.pull_for_tenant(
        tenant_id=current_user.tenant_id,
        username=creds["username"],
        password=creds["password"],
        hotel_code=creds["hotel_code"],
        endpoint_url=creds["endpoint_url"],
    )

    if not result["success"]:
        raise HTTPException(status_code=502, detail="Exely reservation pull failed")

    cancelled = result.get("cancelled", 0)
    updated = result.get("updated", 0)
    imported = result.get("imported", 0)
    msg_parts = [f"{result['processed']} rezervasyon cekildi"]
    if imported:
        msg_parts.append(f"{imported} PMS'e aktarildi")
    if updated:
        msg_parts.append(f"{updated} guncellendi")
    if cancelled:
        msg_parts.append(f"{cancelled} iptal edildi")
    return {
        "message": ", ".join(msg_parts),
        **result,
        "auto_imported": imported,
        "updated": updated,
        "cancelled": cancelled,
    }


@router.get("/reservations/local")
async def get_local_reservations(
    pms_status: str | None = None,
    current_user: User = Depends(get_current_user),
):
    query = {"tenant_id": current_user.tenant_id}
    if pms_status:
        query["pms_status"] = pms_status
    reservations = (
        await db.exely_reservations.find(
            query,
            {"_id": 0},
        )
        .sort("synced_at", -1)
        .to_list(100)
    )
    return {"reservations": reservations, "count": len(reservations)}


@router.post("/reservations/{reservation_id}/confirm")
async def confirm_reservation(
    reservation_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v97 DW
):
    """Confirm reservation delivery to Exely via OTA_NotifReportRQ."""
    client, conn = await _get_client(current_user.tenant_id)

    res = await db.exely_reservations.find_one(
        {
            "tenant_id": current_user.tenant_id,
            "external_id": reservation_id,
        }
    )
    if not res:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    from domains.channel_manager.providers.exely.lifecycle import acknowledge_durable_version

    result = await acknowledge_durable_version(client, res)
    if not result.get("success"):
        status_code = 502 if result.get("provider_write_count") else 409
        raise HTTPException(status_code=status_code, detail=f"Teslimat onayi tamamlanamadi ({result.get('reason')})")

    return {"message": "Rezervasyon teslimati onaylandi", "reservation_id": reservation_id}


@router.post("/reservations/confirm-all-imported")
async def confirm_all_imported_deliveries(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v97 DW
):
    """Confirm delivery for all imported but unconfirmed reservations."""
    tenant_id = current_user.tenant_id
    client, _conn = await _get_client(tenant_id)

    from domains.channel_manager.providers.exely.lifecycle import acknowledge_pending_versions

    result = await acknowledge_pending_versions(client, tenant_id, limit=200)

    return {
        "message": f"{result['acked']} teslimat onaylandi",
        "confirmed": result["acked"],
        "failed": result["failed"],
        "provider_write_count": result["provider_write_count"],
    }


@router.post("/reservations/{reservation_id}/import")
async def import_reservation_to_pms(
    reservation_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),
):
    """Manually import a channel reservation into PMS as a booking."""
    tenant_id = current_user.tenant_id

    # Find channel reservation
    res = await db.exely_reservations.find_one(
        {"tenant_id": tenant_id, "id": reservation_id},
        {"_id": 0},
    )
    if not res:
        res = await db.exely_reservations.find_one(
            {"tenant_id": tenant_id, "external_id": reservation_id},
            {"_id": 0},
        )
    if not res:
        raise HTTPException(status_code=404, detail="Rezervasyon bulunamadi")

    from domains.channel_manager.providers.exely.pms_lifecycle import process_single_and_ack

    client, _conn = await _get_client(tenant_id)
    result = await process_single_and_ack(tenant_id, res, provider=client)

    if not result.get("success"):
        acknowledgement = result.get("acknowledgement") or {}
        status_code = 502 if acknowledgement.get("provider_write_count") else 409
        raise HTTPException(status_code=status_code, detail=f"Import tamamlanamadi ({result.get('reason')})")

    return {
        "message": "Rezervasyon PMS'e basariyla aktarildi",
        **result,
    }


# ── Test Booking Verification ────────────────────────────────────────


class TestBookingVerifyRequest(BaseModel):
    reservation_id: str | None = None
    guest_name: str | None = None


@router.post("/test-booking/verify")
async def verify_test_booking(
    payload: TestBookingVerifyRequest,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    """
    Verify a test booking via OTA_ReadRQ.

    Flow:
    1. Snapshot current reservation count
    2. Trigger OTA_ReadRQ pull (optionally by reservation_id)
    3. Compare before/after
    4. Return verification report
    """
    tenant_id = current_user.tenant_id
    conn = await db.exely_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True},
        exely_connection_projection(),
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely bağlantısı bulunamadı")

    # Snapshot current state
    before_count = await db.exely_reservations.count_documents({"tenant_id": tenant_id})
    before_ids = set()
    existing = await db.exely_reservations.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "external_id": 1},
    ).to_list(500)
    before_ids = {r["external_id"] for r in existing if r.get("external_id")}

    creds = await resolve_exely_credentials(tenant_id, conn, actor="exely_test_booking_verify")
    if not creds:
        raise HTTPException(status_code=503, detail="Exely credentials are unavailable")
    username = creds["username"]
    password = creds["password"]
    hotel_code = creds["hotel_code"]
    endpoint_url = creds["endpoint_url"]

    verification = {
        "session_id": str(uuid.uuid4()),
        "before_count": before_count,
        "pull_result": None,
        "new_reservations": [],
        "verification_status": "pending",
        "errors": [],
    }

    try:
        # PMSConnect only supports SelectionType=Undelivered. A supplied ID is
        # filtered locally after the canonical undelivered read.
        if payload.reservation_id:
            provider_kwargs = {
                "username": username,
                "password": password,
                "hotel_code": hotel_code,
                "tenant_id": tenant_id,
                "property_id": hotel_code,
                "connection_id": f"{tenant_id}:{hotel_code}",
            }
            if endpoint_url:
                provider_kwargs["endpoint_url"] = endpoint_url
            provider = ExelyProvider(**provider_kwargs)
            pull = await provider.pull_reservations()
            pull_data = pull.data or {}
            matches = [item for item in pull_data.get("reservations", []) if str(item.get("reservation_id") or "") == payload.reservation_id]
            if pull.success and matches:
                for raw_res in matches:
                    raw_res = {**raw_res, "property_id": hotel_code}
                    ingest_result = await ingest_reservation(
                        provider=PROVIDER,
                        tenant_id=tenant_id,
                        raw_payload=raw_res,
                        normalizer=normalize_reservation,
                        event_type="new_booking",
                        source="test_booking_verify",
                    )
                    verification["new_reservations"].append(
                        {
                            "external_id": raw_res.get("reservation_id", ""),
                            "guest_name": raw_res.get("guest_name", ""),
                            "ingest_action": ingest_result.get("action", "unknown"),
                            "status": raw_res.get("status", ""),
                        }
                    )
            elif not pull.success:
                verification["errors"].append("OTA_ReadRQ: provider_read_failed")
        else:
            # Do a general pull for new undelivered reservations
            result = await exely_pull_scheduler.pull_for_tenant(
                tenant_id=tenant_id,
                username=username,
                password=password,
                hotel_code=hotel_code,
                endpoint_url=endpoint_url,
            )
            verification["pull_result"] = {
                "success": result.get("success", False),
                "processed": result.get("processed", 0),
                "error": result.get("error"),
            }

    except Exception as exc:
        verification["errors"].append(type(exc).__name__)

    # After state
    after_count = await db.exely_reservations.count_documents({"tenant_id": tenant_id})
    after_existing = await db.exely_reservations.find(
        {"tenant_id": tenant_id},
        {"_id": 0, "external_id": 1, "guest_name": 1, "state": 1, "synced_at": 1},
    ).to_list(500)
    after_ids = {r["external_id"] for r in after_existing if r.get("external_id")}
    new_ids = after_ids - before_ids

    # Get details for newly discovered reservations
    if new_ids and not verification["new_reservations"]:
        new_res = await db.exely_reservations.find(
            {"tenant_id": tenant_id, "external_id": {"$in": list(new_ids)}},
            {"_id": 0, "external_id": 1, "guest_name": 1, "state": 1, "checkin_date": 1, "checkout_date": 1},
        ).to_list(50)
        verification["new_reservations"] = [{"external_id": r.get("external_id"), "guest_name": r.get("guest_name"), "state": r.get("state")} for r in new_res]

    # Filter by guest name if provided
    if payload.guest_name and verification["new_reservations"]:
        search = payload.guest_name.lower()
        verification["new_reservations"] = [r for r in verification["new_reservations"] if search in (r.get("guest_name", "") or "").lower()]

    verification["after_count"] = after_count
    verification["new_count"] = len(new_ids)

    if verification["errors"]:
        verification["verification_status"] = "error"
    elif new_ids or verification["new_reservations"]:
        verification["verification_status"] = "found"
    else:
        verification["verification_status"] = "not_found"

    return verification


# ── Sync Status & Scheduler ─────────────────────────────────────────


@router.get("/sync/status")
async def get_sync_status(current_user: User = Depends(get_current_user)):
    cursor = await db.exely_pull_cursors.find_one(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0},
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
async def start_scheduler(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),
):
    conn = await db.exely_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"_id": 0, "sync_interval_seconds": 1},
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely connection not found")
    interval = conn.get("sync_interval_seconds", 60)
    await exely_pull_scheduler.start(interval_seconds=interval)
    return {"message": f"Scheduler baslatildi ({interval}s aralikla)", "interval_seconds": interval}


@router.post("/sync/scheduler/stop")
async def stop_scheduler(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),
):
    await exely_pull_scheduler.stop()
    return {"message": "Scheduler durduruldu"}


# ── Sync Logs ────────────────────────────────────────────────────────


@router.get("/sync-logs")
async def get_sync_logs(
    limit: int = 50,
    current_user: User = Depends(get_current_user),
):
    logs = (
        await db.exely_sync_logs.find(
            {"tenant_id": current_user.tenant_id},
            {"_id": 0},
        )
        .sort("timestamp", -1)
        .to_list(limit)
    )
    return {"logs": logs, "count": len(logs)}


# ── Raw Events / Debug ──────────────────────────────────────────────


@router.get("/logs/events")
async def get_raw_events(
    limit: int = 50,
    status: str | None = None,
    current_user: User = Depends(get_current_user),
):
    query = {"tenant_id": current_user.tenant_id}
    if status:
        query["status"] = status
    events = (
        await db.exely_raw_events.find(
            query,
            {"_id": 0, "payload": 0},
        )
        .sort("received_at", -1)
        .to_list(limit)
    )
    return {"events": events, "count": len(events)}
