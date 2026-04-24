"""
Exely Integration Router
API endpoints for Exely connection management, room discovery, mapping, ARI push, and sync.
"""
import logging
from modules.pms_core.role_permission_service import require_op  # v93 DW
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.database import db
from core.secrets import get_secrets_manager
from core.security import get_current_user
from domains.channel_manager.providers.common_ingest import ingest_reservation, log_sync
from domains.channel_manager.providers.exely.errors import ExelyError
from domains.channel_manager.providers.exely.exely_pull_worker import exely_pull_scheduler
from domains.channel_manager.providers.exely.normalizer import normalize_reservation
from domains.channel_manager.providers.exely.provider import ExelyProvider
from models.schemas import User

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


# ── Helpers ──────────────────────────────────────────────────────────

async def _get_client(tenant_id: str) -> tuple:
    conn = await db.exely_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0},
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely connection not found. Please set up a connection first.")

    # Resolve credentials via secrets manager (with legacy fallback)
    sm = get_secrets_manager()
    hotel_code = conn.get("hotel_code", "")
    creds = await sm.get_provider_credentials(tenant_id, PROVIDER, hotel_code)

    if creds:
        kwargs = {
            "username": creds.get("username", ""),
            "password": creds.get("password", ""),
            "hotel_code": creds.get("hotel_code", hotel_code),
        }
        if creds.get("endpoint_url"):
            kwargs["endpoint_url"] = creds["endpoint_url"]
    else:
        # Final fallback: read from connection doc (pre-migration data)
        kwargs = {
            "username": conn.get("username", ""),
            "password": conn.get("password", ""),
            "hotel_code": conn.get("hotel_code", ""),
        }
        if conn.get("endpoint_url"):
            kwargs["endpoint_url"] = conn["endpoint_url"]
        if kwargs.get("username"):
            logger.warning("Using legacy connection doc credentials for Exely tenant=%s — migrate ASAP", tenant_id)
    try:
        return ExelyProvider(**kwargs), conn
    except ExelyError as exc:
        raise HTTPException(status_code=502, detail=f"Exely credentials invalid or missing: {exc.message}")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Exely connection error: {exc}")


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
    }
    if payload.endpoint_url:
        kwargs["endpoint_url"] = payload.endpoint_url

    provider = ExelyProvider(**kwargs)
    test_result = await provider.legacy_test_connection()

    if not test_result["connected"]:
        raise HTTPException(status_code=400, detail=f"Exely connection error: {test_result['error']}")

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
        "sync_interval_minutes": payload.sync_interval_minutes,
        "mode": "sandbox",
        "currency": payload.currency,
        "is_active": True,
        "room_types": test_result.get("room_types", []),
        "rate_plans": test_result.get("rate_plans", []),
        "connected_at": datetime.now(UTC).isoformat(),
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
        "message": "Exely connection established successfully",
        "connected": True,
        "room_types": test_result.get("room_types", []),
        "rate_plans": test_result.get("rate_plans", []),
        "connection_id": connection["id"],
    }


@router.get("/connection")
async def get_connection_status(current_user: User = Depends(get_current_user)):
    conn = await db.exely_connections.find_one(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0, "password": 0, "username": 0, "credentials_ref": 0},
    )
    if not conn:
        return {"connected": False, "message": "Exely connection not configured"}
    return {"connected": conn.get("is_active", False), "connection": conn}


@router.post("/test")
async def test_connection(current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    conn = await db.exely_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True}, {"_id": 0},
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
    result = await client.legacy_test_connection()
    if isinstance(result, dict) and "connected" not in result:
        result["connected"] = result.get("success", False)
    if isinstance(result, dict) and "success" not in result:
        result["success"] = result.get("connected", False)
    return result


@router.delete("/disconnect")
async def disconnect(current_user: User = Depends(get_current_user),
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

    result = await client.legacy_discover_rooms(ci, co)
    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"Exely room discovery error: {result['error']}")

    # Cache discovered rooms/rates on connection
    await db.exely_connections.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$set": {
            "room_types": result["room_types"],
            "rate_plans": result["rate_plans"],
            "rooms_fetched_at": datetime.now(UTC).isoformat(),
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
        {"tenant_id": current_user.tenant_id}, {"_id": 0},
    ).to_list(100)
    return {"mappings": mappings, "count": len(mappings)}


@router.delete("/room-mappings/{mapping_id}")
async def delete_room_mapping(
    mapping_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
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
    _perm=Depends(require_op("manage_channel_connectors")),  # v100 DW
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
    updates: list[ExelyARIUpdate],
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v96 DW
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
async def manual_pull(current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v96 DW
):
    """Manually trigger a reservation pull from Exely."""
    conn = await db.exely_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True}, {"_id": 0},
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely connection not found")

    # Get credentials from secrets manager
    sm = get_secrets_manager()
    creds = await sm.get_provider_credentials(current_user.tenant_id, PROVIDER, conn.get("hotel_code", ""))
    if creds:
        username = creds.get("username", "")
        password = creds.get("password", "")
        hotel_code = creds.get("hotel_code", "")
        endpoint_url = creds.get("endpoint_url", "")
    else:
        username = conn.get("username", "")
        password = conn.get("password", "")
        hotel_code = conn.get("hotel_code", "")
        endpoint_url = conn.get("endpoint_url", "")

    result = await exely_pull_scheduler.pull_for_tenant(
        tenant_id=current_user.tenant_id,
        username=username,
        password=password,
        hotel_code=hotel_code,
        endpoint_url=endpoint_url,
    )

    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"Pull hatasi: {result.get('error')}")

    # Also check individual imported reservations for cancellation status changes.
    # The batch "Undelivered" pull may not return cancellations immediately.
    cancel_detected = await _check_individual_cancellations(
        current_user.tenant_id, username, password, hotel_code, endpoint_url,
    )

    # Also check for modifications (name, date, room type changes)
    mod_detected = await _check_individual_modifications(
        current_user.tenant_id, username, password, hotel_code, endpoint_url,
    )

    # Auto-import is already triggered inside pull_for_tenant
    # Also import any previously pending ones (including modifications)
    from domains.channel_manager.providers.exely.auto_import import auto_import_pending
    from domains.channel_manager.providers.exely.provider import ExelyProvider
    provider_kwargs = {"username": username, "password": password, "hotel_code": hotel_code}
    if endpoint_url:
        provider_kwargs["endpoint_url"] = endpoint_url
    confirm_provider = ExelyProvider(**provider_kwargs)
    import_result = await auto_import_pending(current_user.tenant_id, provider=confirm_provider)

    cancelled = import_result.get("cancelled", 0) + cancel_detected
    updated = import_result.get("updated", 0) + mod_detected
    msg_parts = [f"{result['processed']} rezervasyon cekildi"]
    if import_result["imported"]:
        msg_parts.append(f"{import_result['imported']} PMS'e aktarildi")
    if updated:
        msg_parts.append(f"{updated} guncellendi")
    if cancelled:
        msg_parts.append(f"{cancelled} iptal edildi")
    return {
        "message": ", ".join(msg_parts),
        **result,
        "auto_imported": import_result["imported"],
        "updated": updated,
        "cancelled": cancelled,
    }


async def _check_individual_cancellations(
    tenant_id: str, username: str, password: str, hotel_code: str, endpoint_url: str,
) -> int:
    """
    Check each imported (non-cancelled) exely_reservation individually via Exely SOAP
    to detect cancellations that the batch 'Undelivered' pull may miss.
    """

    imported_reservations = await db.exely_reservations.find(
        {"tenant_id": tenant_id, "state": {"$in": ["confirmed", "pending"]}, "pms_status": "imported"},
        {"_id": 0, "external_id": 1, "provider_reservation_id": 1},
    ).to_list(50)

    if not imported_reservations:
        return 0

    provider_kwargs = {"username": username, "password": password, "hotel_code": hotel_code}
    if endpoint_url:
        provider_kwargs["endpoint_url"] = endpoint_url
    provider = ExelyProvider(**provider_kwargs)

    cancel_count = 0
    for res in imported_reservations:
        ext_id = res.get("external_id", "")
        prov_res_id = res.get("provider_reservation_id", ext_id)
        try:
            pull_result = await provider.legacy_pull_reservations(reservation_id=prov_res_id)
            if not pull_result.get("success"):
                continue
            reservations = pull_result.get("reservations", [])
            if not reservations:
                continue
            raw_res = reservations[0]
            status = (raw_res.get("status") or "").lower()
            if status in ("cancel", "cancelled"):
                ingest_result = await ingest_reservation(
                    provider=PROVIDER,
                    tenant_id=tenant_id,
                    raw_payload=raw_res,
                    normalizer=normalize_reservation,
                    event_type="cancellation",
                    source="manual_cancel_check",
                )
                if ingest_result.get("action") == "cancelled":
                    cancel_count += 1
                    logger.info(f"[EXELY-CANCEL-CHECK] Detected cancellation for {ext_id}")
        except Exception as e:
            logger.warning(f"[EXELY-CANCEL-CHECK] Error checking {ext_id}: {e}")

    return cancel_count


async def _check_individual_modifications(
    tenant_id: str, username: str, password: str, hotel_code: str, endpoint_url: str,
) -> int:
    """
    Check each imported exely_reservation individually via Exely SOAP
    to detect modifications (name changes, date changes, room type changes)
    that the batch 'Undelivered' pull may miss.
    """

    imported_reservations = await db.exely_reservations.find(
        {"tenant_id": tenant_id, "state": {"$in": ["confirmed", "modified"]}, "pms_status": "imported"},
        {"_id": 0, "external_id": 1, "provider_reservation_id": 1,
         "guest_name": 1, "checkin_date": 1, "checkout_date": 1, "rooms": 1,
         "provider_last_modified_at": 1},
    ).to_list(50)

    if not imported_reservations:
        return 0

    provider_kwargs = {"username": username, "password": password, "hotel_code": hotel_code}
    if endpoint_url:
        provider_kwargs["endpoint_url"] = endpoint_url
    provider = ExelyProvider(**provider_kwargs)

    mod_count = 0
    for res in imported_reservations:
        ext_id = res.get("external_id", "")
        prov_res_id = res.get("provider_reservation_id", ext_id)
        try:
            pull_result = await provider.legacy_pull_reservations(reservation_id=prov_res_id)
            if not pull_result.get("success"):
                continue
            reservations = pull_result.get("reservations", [])
            if not reservations:
                continue
            raw_res = reservations[0]
            status = (raw_res.get("status") or "").lower()

            # Skip cancelled (handled by cancellation check)
            if status in ("cancel", "cancelled"):
                continue

            # Detect changes by comparing with stored data
            changed = False
            new_name = raw_res.get("guest_name", "")
            new_checkin = raw_res.get("checkin_date", "")
            new_checkout = raw_res.get("checkout_date", "")
            new_rooms = raw_res.get("rooms", [])
            new_room_code = new_rooms[0].get("room_type_code", "") if new_rooms else ""

            stored_name = res.get("guest_name", "")
            stored_checkin = res.get("checkin_date", "")
            stored_checkout = res.get("checkout_date", "")
            stored_rooms = res.get("rooms", [])
            stored_room_code = stored_rooms[0].get("room_type_code", "") if stored_rooms else ""

            # Compare last_modify timestamp
            new_last_modify = raw_res.get("last_modify", "")
            stored_last_modify = res.get("provider_last_modified_at", "")
            if new_last_modify and stored_last_modify and new_last_modify != stored_last_modify:
                changed = True

            # Also compare individual fields
            if new_name and new_name != stored_name:
                changed = True
            if new_checkin and new_checkin[:10] != (stored_checkin or "")[:10]:
                changed = True
            if new_checkout and new_checkout[:10] != (stored_checkout or "")[:10]:
                changed = True
            if new_room_code and new_room_code != stored_room_code:
                changed = True

            if changed:
                ingest_result = await ingest_reservation(
                    provider=PROVIDER,
                    tenant_id=tenant_id,
                    raw_payload=raw_res,
                    normalizer=normalize_reservation,
                    event_type="modification",
                    source="individual_mod_check",
                )
                if ingest_result.get("action") in ("updated", "created"):
                    mod_count += 1
                    logger.info(f"[EXELY-MOD-CHECK] Detected modification for {ext_id}: "
                                f"name={new_name != stored_name}, dates={new_checkin[:10] != (stored_checkin or '')[:10]}, "
                                f"room={new_room_code != stored_room_code}")
        except Exception as e:
            logger.warning(f"[EXELY-MOD-CHECK] Error checking {ext_id}: {e}")

    return mod_count


@router.get("/reservations/local")
async def get_local_reservations(
    pms_status: str | None = None,
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
    _perm=Depends(require_op("manage_channel_connectors")),  # v97 DW
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
        {"$set": {"delivery_confirmed": True, "confirmed_at": datetime.now(UTC).isoformat()}},
    )

    return {"message": "Rezervasyon teslimati onaylandi", "reservation_id": reservation_id}


@router.post("/reservations/confirm-all-imported")
async def confirm_all_imported_deliveries(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v97 DW
):
    """Confirm delivery for all imported but unconfirmed reservations."""
    tenant_id = current_user.tenant_id
    client, conn = await _get_client(tenant_id)

    # Find imported reservations that haven't been confirmed to Exely
    unconfirmed = await db.exely_reservations.find(
        {
            "tenant_id": tenant_id,
            "pms_status": "imported",
            "pms_booking_id": {"$ne": None},
            "delivery_confirmed": {"$ne": True},
        },
        {"_id": 0, "external_id": 1, "pms_booking_id": 1, "provider_last_modified_at": 1, "created_at": 1},
    ).to_list(200)

    confirmed = 0
    errors = []
    for res in unconfirmed:
        try:
            create_dt = res.get("provider_last_modified_at") or res.get("created_at")
            result = await client.legacy_confirm_delivery(
                res["external_id"], res["pms_booking_id"],
                create_datetime=create_dt,
                res_status="Book",
            )
            if result.get("success"):
                await db.exely_reservations.update_one(
                    {"tenant_id": tenant_id, "external_id": res["external_id"]},
                    {"$set": {"delivery_confirmed": True, "confirmed_at": datetime.now(UTC).isoformat()}},
                )
                confirmed += 1
                logger.info(f"[EXELY] Bulk confirm: {res['external_id']} -> OK")
            else:
                errors.append({"external_id": res["external_id"], "error": result.get("error", "unknown")})
        except Exception as e:
            errors.append({"external_id": res["external_id"], "error": str(e)})

    return {
        "message": f"{confirmed}/{len(unconfirmed)} teslimat onaylandi",
        "confirmed": confirmed,
        "total": len(unconfirmed),
        "errors": errors,
    }



@router.post("/reservations/{reservation_id}/import")
async def import_reservation_to_pms(
    reservation_id: str,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v96 DW
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

    if res.get("pms_status") == "imported" and res.get("pms_booking_id"):
        return {"message": "Rezervasyon zaten PMS'e aktarilmis", "pms_booking_id": res["pms_booking_id"]}

    from domains.channel_manager.providers.exely.auto_import import auto_import_reservation
    result = await auto_import_reservation(tenant_id, res)

    if not result.get("success"):
        raise HTTPException(status_code=400, detail=f"Import hatasi: {result.get('reason')}")

    # Confirm delivery to Exely
    if result.get("pms_booking_id"):
        try:
            client, conn = await _get_client(tenant_id)
            external_id = res.get("external_id", reservation_id)
            confirm = await client.legacy_confirm_delivery(external_id, result["pms_booking_id"])
            if confirm.get("success"):
                logger.info(f"[EXELY] Delivery confirmed for {external_id}")
        except Exception as e:
            logger.warning(f"[EXELY] Delivery confirm error: {e}")

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
        {"tenant_id": tenant_id, "is_active": True}, {"_id": 0},
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely bağlantısı bulunamadı")

    # Snapshot current state
    before_count = await db.exely_reservations.count_documents({"tenant_id": tenant_id})
    before_ids = set()
    existing = await db.exely_reservations.find(
        {"tenant_id": tenant_id}, {"_id": 0, "external_id": 1},
    ).to_list(500)
    before_ids = {r["external_id"] for r in existing if r.get("external_id")}

    # Get credentials from secrets manager
    sm = get_secrets_manager()
    creds = await sm.get_provider_credentials(tenant_id, PROVIDER, conn.get("hotel_code", ""))
    if creds:
        username = creds.get("username", "")
        password = creds.get("password", "")
        hotel_code = creds.get("hotel_code", "")
        endpoint_url = creds.get("endpoint_url", "")
    else:
        username = conn.get("username", "")
        password = conn.get("password", "")
        hotel_code = conn.get("hotel_code", "")
        endpoint_url = conn.get("endpoint_url", "")

    verification = {
        "session_id": str(uuid.uuid4()),
        "before_count": before_count,
        "pull_result": None,
        "new_reservations": [],
        "verification_status": "pending",
        "errors": [],
    }

    try:
        # If specific reservation_id provided, do targeted pull
        if payload.reservation_id:
            provider_kwargs = {"username": username, "password": password, "hotel_code": hotel_code}
            if endpoint_url:
                provider_kwargs["endpoint_url"] = endpoint_url
            provider = ExelyProvider(**provider_kwargs)
            pull = await provider.legacy_pull_reservations(reservation_id=payload.reservation_id)
            if pull.get("success") and pull.get("reservations"):
                for raw_res in pull["reservations"]:
                    ingest_result = await ingest_reservation(
                        provider=PROVIDER,
                        tenant_id=tenant_id,
                        raw_payload=raw_res,
                        normalizer=normalize_reservation,
                        event_type="new_booking",
                        source="test_booking_verify",
                    )
                    verification["new_reservations"].append({
                        "external_id": raw_res.get("reservation_id", ""),
                        "guest_name": raw_res.get("guest_name", ""),
                        "ingest_action": ingest_result.get("action", "unknown"),
                        "status": raw_res.get("status", ""),
                    })
            else:
                verification["errors"].append(f"OTA_ReadRQ: {pull.get('error', 'unknown')}")
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

    except Exception as e:
        verification["errors"].append(str(e))

    # After state
    after_count = await db.exely_reservations.count_documents({"tenant_id": tenant_id})
    after_existing = await db.exely_reservations.find(
        {"tenant_id": tenant_id}, {"_id": 0, "external_id": 1, "guest_name": 1, "state": 1, "synced_at": 1},
    ).to_list(500)
    after_ids = {r["external_id"] for r in after_existing if r.get("external_id")}
    new_ids = after_ids - before_ids

    # Get details for newly discovered reservations
    if new_ids and not verification["new_reservations"]:
        new_res = await db.exely_reservations.find(
            {"tenant_id": tenant_id, "external_id": {"$in": list(new_ids)}},
            {"_id": 0, "external_id": 1, "guest_name": 1, "state": 1, "checkin_date": 1, "checkout_date": 1},
        ).to_list(50)
        verification["new_reservations"] = [
            {"external_id": r.get("external_id"), "guest_name": r.get("guest_name"), "state": r.get("state")}
            for r in new_res
        ]

    # Filter by guest name if provided
    if payload.guest_name and verification["new_reservations"]:
        search = payload.guest_name.lower()
        verification["new_reservations"] = [
            r for r in verification["new_reservations"]
            if search in (r.get("guest_name", "") or "").lower()
        ]

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
async def start_scheduler(current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
):
    conn = await db.exely_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True}, {"_id": 0},
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely connection not found")
    interval = conn.get("sync_interval_seconds", 60)
    await exely_pull_scheduler.start(interval_seconds=interval)
    return {"message": f"Scheduler baslatildi ({interval}s aralikla)", "interval_seconds": interval}


@router.post("/sync/scheduler/stop")
async def stop_scheduler(current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("view_system_diagnostics")),  # v93 DW
):
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
    status: str | None = None,
    current_user: User = Depends(get_current_user),
):
    query = {"tenant_id": current_user.tenant_id}
    if status:
        query["status"] = status
    events = await db.exely_raw_events.find(
        query, {"_id": 0, "payload": 0},
    ).sort("received_at", -1).to_list(limit)
    return {"events": events, "count": len(events)}
