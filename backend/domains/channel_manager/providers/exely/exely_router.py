"""
Exely Integration Router
API endpoints for Exely connection management, room discovery, mapping, ARI push, and sync.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

from core.database import db
from core.secrets import get_secrets_manager
from core.security import get_current_user
from domains.channel_manager.providers.common_ingest import ingest_reservation, log_sync
from domains.channel_manager.providers.exely.ari_delivery import preview_exely_ari
from domains.channel_manager.providers.exely.ari_publish import enqueue_exely_ari_update
from domains.channel_manager.providers.exely.errors import ExelyError
from domains.channel_manager.providers.exely.exely_pull_worker import exely_pull_scheduler
from domains.channel_manager.providers.exely.normalizer import normalize_reservation
from domains.channel_manager.providers.exely.production_safety import (
    ari_write_block_reason,
    provider_io_block_reason,
    reservation_sync_block_reason,
    safe_runtime_state,
)
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.read_reservation_router import router as read_reservation_router
from domains.channel_manager.providers.exely.scheduling import connection_pull_interval_seconds
from domains.channel_manager.providers.exely.security import (
    EXELY_PRODUCTION_ENDPOINT_URL,
    EXELY_TEST_ENDPOINT_URL,
    exely_connection_projection,
    is_exely_production,
    resolve_exely_credentials,
)
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v93 DW

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/channel-manager/exely", tags=["Exely Integration"])
router.include_router(read_reservation_router)

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
    sync_interval_minutes: int = Field(default=15, ge=3, le=60, strict=True)
    mode: Literal["sandbox", "production"] = "production"


class ExelyRoomMapping(BaseModel):
    pms_room_type: str
    exely_room_code: str
    exely_rate_plan_code: str
    exely_room_name: str
    pms_api_room_code: str = ""
    pms_api_rate_plan_code: str = ""
    sync_availability: bool = True
    sync_price: bool = True
    sync_restrictions: bool = True


class ExelyARIUpdate(BaseModel):
    room_type_code: str = Field(min_length=1, max_length=160)
    rate_plan_code: str = Field(min_length=1, max_length=160)
    start_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    end_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    availability: int | None = Field(default=None, ge=0, strict=True)
    rate_amount: float | None = Field(default=None, ge=0, allow_inf_nan=False, strict=True)
    currency: str = Field(default="TRY", pattern=r"^[A-Z]{3}$")
    stop_sell: bool | None = Field(default=None, strict=True)
    min_stay: int | None = Field(default=None, ge=1, strict=True)
    min_los_arrival: int | None = Field(default=None, ge=1, strict=True)
    max_stay: int | None = Field(default=None, ge=1, strict=True)
    cta: bool | None = Field(default=None, strict=True)
    ctd: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def validate_mutations(self):
        operations = {
            "availability": self.availability, "rate": self.rate_amount,
            "stop_sell": self.stop_sell, "min_los": self.min_stay,
            "min_los_arrival": self.min_los_arrival, "max_los": self.max_stay,
            "cta": self.cta, "ctd": self.ctd,
        }
        if all(value is None for value in operations.values()):
            raise ValueError("EXELY_ARI_MUTATION_REQUIRED")
        for operation, value in operations.items():
            if value is None:
                continue
            result = preview_exely_ari(operation, {
                "tenant_id": "validation", "property_id": "validation",
                "room_type_code": self.room_type_code, "rate_plan_code": self.rate_plan_code,
                "start_date": self.start_date, "end_date": self.end_date,
                "value": value, "currency": self.currency,
            })
            if result.error_code:
                raise ValueError(result.error_code)
        return self


class ExelySyncSettings(BaseModel):
    sync_interval_minutes: int = Field(ge=3, le=60, strict=True)


class ExelyARIWriteActivation(BaseModel):
    enabled: bool
    confirmation: str


# ── Helpers ──────────────────────────────────────────────────────────


def _connection_endpoint(mode: str, endpoint_url: str | None) -> str:
    if endpoint_url:
        return endpoint_url
    if mode == "sandbox":
        return EXELY_TEST_ENDPOINT_URL
    return EXELY_PRODUCTION_ENDPOINT_URL


async def _get_client(tenant_id: str) -> tuple:
    runtime_block = provider_io_block_reason()
    if runtime_block:
        raise HTTPException(status_code=503, detail=runtime_block)

    conn = await db.exely_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True},
        exely_connection_projection(),
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely connection not found. Please set up a connection first.")

    try:
        creds = await resolve_exely_credentials(tenant_id, conn, actor="exely_router")
    except ExelyError as exc:
        raise HTTPException(status_code=502, detail=f"Exely credentials rejected ({type(exc).__name__})")
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Exely credentials failed ({type(exc).__name__})")
    if not creds:
        raise HTTPException(status_code=503, detail="Exely credentials are unavailable")
    kwargs = {
        "username": creds["username"],
        "password": creds["password"],
        "hotel_code": creds["hotel_code"],
        "endpoint_url": creds["endpoint_url"],
        "tenant_id": tenant_id,
        "property_id": creds["hotel_code"],
        "connection_mode": str(conn.get("mode") or ""),
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
    runtime_block = provider_io_block_reason()
    if runtime_block:
        raise HTTPException(status_code=503, detail=runtime_block)

    endpoint_url = _connection_endpoint(payload.mode, payload.endpoint_url)
    kwargs = {
        "username": payload.username,
        "password": payload.password,
        "hotel_code": payload.hotel_code,
        "tenant_id": current_user.tenant_id,
        "property_id": payload.hotel_code,
        "connection_id": f"{current_user.tenant_id}:{payload.hotel_code}",
        "connection_mode": payload.mode,
        "endpoint_url": endpoint_url,
    }

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
        "endpoint_url": endpoint_url,
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
        "endpoint_url": endpoint_url,
        "property_name": payload.property_name or f"Exely Property ({payload.hotel_code})",
        "auto_sync_reservations": payload.auto_sync_reservations,
        "ari_write_enabled": False,
        "sync_interval_minutes": payload.sync_interval_minutes,
        "mode": payload.mode,
        "currency": payload.currency,
        "is_active": True,
        "read_reservation_enabled": False,
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
    if conn.get("mode") == "sandbox" and not is_exely_production():
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
    tested_at = datetime.now(UTC).isoformat()
    health_status = "healthy" if result.success and data.get("connected") else "failed"
    safe_error_code = str(result.error_type or "EXELY_CONNECTION_TEST_FAILED") if health_status == "failed" else None
    await db.exely_connections.update_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {
            "$set": {
                "last_connection_test_at": tested_at,
                "last_connection_test_status": health_status,
                "last_connection_test_error": safe_error_code,
                **({"last_connection_success_at": tested_at} if health_status == "healthy" else {}),
            }
        },
    )
    return {
        "success": result.success,
        "connected": bool(result.success and data.get("connected")),
        "room_types": data.get("room_types", []),
        "rate_plans": data.get("rate_plans", []),
        "duration_ms": result.duration_ms,
        "error_type": safe_error_code,
        "tested_at": tested_at,
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
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Active connection not found")
    return {"message": f"Currency updated to {payload.currency}", "currency": payload.currency}


@router.post("/ari-write")
async def update_ari_write_state(
    payload: ExelyARIWriteActivation,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),
):
    """Enable or stop provider writes for exactly one tenant connection.

    The global production gate remains controlled by the protected cutover
    workflow.  Enabling here is deliberately tenant-scoped and requires a
    healthy connection plus at least one complete availability mapping.
    """
    expected = "ENABLE_EXELY_ARI_WRITE" if payload.enabled else "DISABLE_EXELY_ARI_WRITE"
    if payload.confirmation != expected:
        raise HTTPException(status_code=400, detail="EXELY_ARI_WRITE_CONFIRMATION_REQUIRED")

    conn = await db.exely_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"_id": 0},
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely connection not found")

    if payload.enabled:
        runtime_block = ari_write_block_reason()
        if runtime_block:
            raise HTTPException(status_code=503, detail=runtime_block)

        mapping = await db.exely_room_mappings.find_one(
            {
                "tenant_id": current_user.tenant_id,
                "sync_availability": True,
                "exely_room_code": {"$nin": [None, ""]},
                "exely_rate_plan_code": {"$nin": [None, ""]},
            },
            {"_id": 1},
        )
        if not mapping:
            raise HTTPException(status_code=409, detail="EXELY_ARI_MAPPING_REQUIRED")

        client, _connection = await _get_client(current_user.tenant_id)
        probe = await client.test_connection()
        if not probe.success:
            raise HTTPException(status_code=409, detail="EXELY_CONNECTION_PROBE_FAILED")

    await db.exely_connections.update_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {
            "$set": {
                "ari_write_enabled": payload.enabled,
                "ari_write_updated_at": datetime.now(UTC).isoformat(),
                "ari_write_updated_by": current_user.name,
            }
        },
    )
    await log_sync(
        PROVIDER,
        current_user.tenant_id,
        "ari_write_activation",
        "enabled" if payload.enabled else "disabled",
        user_name=current_user.name,
    )
    return {
        "ari_write_enabled": payload.enabled,
        "message": "Exely ARI gonderimi acildi" if payload.enabled else "Exely ARI gonderimi durduruldu",
    }


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
                "services": data.get('services', []),
            }
        },
    )

    return {
        "room_types": data.get("room_types", []),
        "rate_plans": data.get("rate_plans", []),
        "services": data.get('services', []),
    }


# ── Room Mapping ─────────────────────────────────────────────────────


@router.post("/room-mappings")
async def create_room_mapping(
    payload: ExelyRoomMapping,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    duplicate = await db.exely_room_mappings.find_one(
        {
            "tenant_id": current_user.tenant_id,
            "pms_room_type": payload.pms_room_type,
            "exely_room_code": payload.exely_room_code,
            "exely_rate_plan_code": payload.exely_rate_plan_code,
        },
        {"_id": 1},
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Bu oda ve fiyat plani eslemesi zaten mevcut")
    if payload.sync_availability:
        other_inventory_mapping = await db.exely_room_mappings.find_one(
            {"tenant_id": current_user.tenant_id, "pms_room_type": payload.pms_room_type, "sync_availability": True},
            {"_id": 1},
        )
        if other_inventory_mapping:
            raise HTTPException(status_code=409, detail="Bu PMS oda tipinde başka bir müsaitlik eşlemesi açık")
    mapping = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "pms_room_type": payload.pms_room_type,
        "exely_room_code": payload.exely_room_code,
        "exely_rate_plan_code": payload.exely_rate_plan_code,
        "exely_room_name": payload.exely_room_name,
        "pms_api_room_code": payload.pms_api_room_code.strip(),
        "pms_api_rate_plan_code": payload.pms_api_rate_plan_code.strip(),
        "sync_availability": payload.sync_availability,
        "sync_price": payload.sync_price,
        "sync_restrictions": payload.sync_restrictions,
        "created_at": datetime.now(UTC).isoformat(),
        "created_by": current_user.name,
    }
    await db.exely_room_mappings.insert_one(mapping)
    mapping.pop("_id", None)
    return {"message": "Oda eslesmesi olusturuldu", "mapping": mapping}


@router.patch("/room-mappings/{mapping_id}")
async def update_room_mapping(
    mapping_id: str,
    payload: ExelyRoomMapping,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),
):
    """Edit one mapping without deleting its reservation aliases or audit identity."""
    selector = {"id": mapping_id, "tenant_id": current_user.tenant_id}
    existing = await db.exely_room_mappings.find_one(selector, {"_id": 0})
    if not existing:
        raise HTTPException(status_code=404, detail="Esleme bulunamadi")
    room_code = payload.exely_room_code.strip()
    rate_code = payload.exely_rate_plan_code.strip()
    pms_type = payload.pms_room_type.strip()
    if not all((room_code, rate_code, pms_type)):
        raise HTTPException(status_code=422, detail="Oda tipi ve fiyat planı kodları zorunludur")
    duplicate = await db.exely_room_mappings.find_one(
        {"tenant_id": current_user.tenant_id, "id": {"$ne": mapping_id}, "pms_room_type": pms_type, "exely_room_code": room_code, "exely_rate_plan_code": rate_code},
        {"_id": 1},
    )
    if duplicate:
        raise HTTPException(status_code=409, detail="Bu oda ve fiyat planı eşlemesi zaten mevcut")
    if payload.sync_availability:
        other_inventory_mapping = await db.exely_room_mappings.find_one(
            {"tenant_id": current_user.tenant_id, "id": {"$ne": mapping_id}, "pms_room_type": pms_type, "sync_availability": True},
            {"_id": 1},
        )
        if other_inventory_mapping:
            raise HTTPException(status_code=409, detail="Bu PMS oda tipinde başka bir müsaitlik eşlemesi açık")
    fields = {
        "pms_room_type": pms_type,
        "exely_room_code": room_code,
        "exely_rate_plan_code": rate_code,
        "exely_room_name": payload.exely_room_name.strip(),
        "pms_api_room_code": payload.pms_api_room_code.strip() or existing.get("pms_api_room_code") or (existing.get("exely_room_code", "") if existing.get("exely_room_code") != room_code else ""),
        "pms_api_rate_plan_code": payload.pms_api_rate_plan_code.strip()
        or existing.get("pms_api_rate_plan_code")
        or (existing.get("exely_rate_plan_code", "") if existing.get("exely_rate_plan_code") != rate_code else ""),
        "sync_availability": payload.sync_availability,
        "sync_price": payload.sync_price,
        "sync_restrictions": payload.sync_restrictions,
        "updated_at": datetime.now(UTC).isoformat(),
        "updated_by": current_user.name,
    }
    await db.exely_room_mappings.update_one(selector, {"$set": fields})
    return {"message": "Eşleme güncellendi", "mapping": {**existing, **fields}}


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
    runtime_block = ari_write_block_reason()
    if runtime_block:
        raise HTTPException(status_code=503, detail=runtime_block)

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
    updates: Annotated[list[ExelyARIUpdate], Field(min_length=1, max_length=200)],
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),
):
    """Durably queue multiple ARI updates without direct provider writes."""
    runtime_block = ari_write_block_reason()
    if runtime_block:
        raise HTTPException(status_code=503, detail=runtime_block)

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
    try:
        runtime_block = reservation_sync_block_reason()
        if runtime_block:
            raise HTTPException(status_code=503, detail=runtime_block)

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
            connection_mode=str(conn.get("mode") or ""),
            **({"read_reservation_enabled": True} if conn.get("read_reservation_enabled") else {}),
        )
        if not result["success"]:
            error_code = str(result.get("error") or "EXELY_PROVIDER_READ_FAILED")
            # A provider-side read rejection is an expected operational result,
            # not an application crash. Returning it as a structured 200 keeps
            # reverse proxies from replacing the response body with a generic
            # 502 page, so the operator can see the exact safe error class.
            return {
                "success": False,
                "error": error_code,
                "message": f"EXELY_RESERVATION_PULL_FAILED:{error_code}",
                "provider_read_count": result.get("provider_read_count", 0),
                "provider_write_count": result.get("provider_write_count", 0),
            }

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
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[EXELY] manual reservation pull failed")
        return {
            "success": False,
            "error": type(exc).__name__,
            "message": f"EXELY_RESERVATION_PULL_FAILED:{type(exc).__name__} - {str(exc)}",
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
    runtime_block = reservation_sync_block_reason()
    if runtime_block:
        raise HTTPException(status_code=503, detail=runtime_block)

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
    runtime_block = reservation_sync_block_reason()
    if runtime_block:
        raise HTTPException(status_code=503, detail=runtime_block)

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
    try:
        runtime_block = reservation_sync_block_reason()
        if runtime_block:
            raise HTTPException(status_code=503, detail=runtime_block)

        tenant_id = current_user.tenant_id
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
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("[EXELY] manual reservation import failed")
        # Import failures are operational outcomes. Keep a safe class visible
        # to the UI instead of letting a reverse proxy replace the response
        # with a generic error page.
        return {
            "success": False,
            "error": type(exc).__name__,
            "message": f"EXELY_RESERVATION_IMPORT_FAILED:{type(exc).__name__}",
            "provider_write_count": 0,
        }

    if not result.get("success"):
        acknowledgement = result.get("acknowledgement") or {}
        reason = str(result.get("reason") or "PMS_IMPORT_FAILED")
        return {
            "success": False,
            "error": reason,
            "message": f"EXELY_RESERVATION_IMPORT_FAILED:{reason}",
            "provider_write_count": int(acknowledgement.get("provider_write_count") or 0),
        }

    return {
        "message": "Rezervasyon PMS'e basariyla aktarildi",
        **result,
    }


# ── Test Booking Verification ────────────────────────────────────────


class TestBookingVerifyRequest(BaseModel):
    reservation_id: str | None = None
    guest_name: str | None = None
    expected_adults: int | None = Field(default=None, ge=0, le=1000, strict=True)
    expected_children_ages: list[Annotated[int, Field(ge=0, le=17, strict=True)]] | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_demographic_expectations(self):
        if self.expected_adults is not None or self.expected_children_ages is not None:
            if not (self.reservation_id or "").strip():
                raise ValueError("A reservation ID is required for demographic comparison")
            if self.expected_adults is None or self.expected_children_ages is None:
                raise ValueError("Supply both expected adults and child ages")
        return self


def _test_booking_summary(reservation: dict, payload: TestBookingVerifyRequest, *, demographic_rooms: list | None = None) -> dict:
    """An imported record is not evidence of provider demographic acceptance.

    PMSConnect bed counts can hide children. Compare expectations with the
    stored counts, but never infer ages from comments or certify REST data we
    have not read. This is read-only and does not rewrite provider versions.
    """
    rooms = demographic_rooms if demographic_rooms is not None else reservation.get("rooms") or []
    checks = {
        "pms_import": "passed" if reservation.get("pms_status") == "imported" else "pending",
        "provider_ack": "passed" if reservation.get("delivery_confirmed") is True else "pending",
        "guest_demographics": "passed" if demographic_rooms is not None else "not_verified",
    }
    row = {
        "external_id": reservation.get("external_id") or reservation.get("reservation_id"),
        "guest_name": reservation.get("guest_name", ""),
        "state": reservation.get("state") or reservation.get("status", ""),
        "checks": checks,
        "acceptance_status": "not_verified",
    }
    if payload.expected_adults is not None:
        # The form describes a single-room test. A multi-room total is not a
        # safe room-stay match, even if its aggregate counts happen to agree.
        room = rooms[0] if len(rooms) == 1 else {}
        ages = room.get("children_ages")
        expected = payload.expected_children_ages
        counts_match = bool(room) and room.get("adults") == payload.expected_adults and room.get("children") == len(expected)
        ages_match = (
            isinstance(ages, list)
            and all(type(age) is int and 0 <= age <= 17 for age in ages)
            and sorted(ages) == sorted(expected)
        ) if expected else room.get("children", None) == 0
        checks["expected_guest_counts"] = ("matches_verified_counts" if demographic_rooms is not None else "matches_reported_counts") if counts_match and ages_match else "mismatch"
        if not counts_match or not ages_match:
            row["acceptance_status"] = "mismatch"
    return row


async def _stored_test_booking_summary(tenant_id: str, conn: dict, reservation: dict, payload: TestBookingVerifyRequest) -> dict:
    """Do not certify from an old audit row: inspect the current PMS documents."""
    if conn.get("read_reservation_enabled"):
        from .demographics import verified_booking

        ids = reservation.get("pms_booking_ids") or [reservation.get("pms_booking_id")]
        ids = [booking_id for booking_id in ids if booking_id]
        if ids and len(ids) == len(reservation.get("rooms") or []):
            bookings = await db.bookings.find({
                "tenant_id": tenant_id, "property_id": str(conn.get("hotel_code") or ""),
                "id": {"$in": ids}, "provider_group_reservation_id": reservation.get("external_id"),
                "provider_version_key": reservation.get("provider_version_key"), "booking_source": "exely",
            }, {"_id": 0}).to_list(len(ids))
            if len(bookings) == len(ids) and all(verified_booking(booking) for booking in bookings):
                return _test_booking_summary(reservation, payload, demographic_rooms=[{
                    "adults": booking["adults"], "children": booking["children"], "children_ages": booking["children_ages"],
                } for booking in bookings])
    return _test_booking_summary(reservation, payload)


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
    runtime_block = reservation_sync_block_reason()
    if runtime_block:
        raise HTTPException(status_code=503, detail=runtime_block)

    tenant_id = current_user.tenant_id
    conn = await db.exely_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True},
        exely_connection_projection(),
    )
    if not conn:
        raise HTTPException(status_code=404, detail="Exely bağlantısı bulunamadı")

    # Every lookup belongs to this active property, not merely this tenant.
    scope = {"tenant_id": tenant_id, "property_id": str(conn.get("hotel_code") or "")}
    if payload.reservation_id:
        scope["external_id"] = payload.reservation_id
    before_count = await db.exely_reservations.count_documents(scope)
    before_ids = set()
    existing = await db.exely_reservations.find(
        scope,
        {"_id": 0, "external_id": 1},
    ).to_list(None)
    before_ids = {r["external_id"] for r in existing if r.get("external_id")}

    stored = await db.exely_reservations.find_one(scope, {"_id": 0}) if payload.reservation_id else None

    verification = {
        "session_id": str(uuid.uuid4()),
        "before_count": before_count,
        "pull_result": None,
        "new_reservations": [],
        "verification_status": "pending",
        "acceptance_status": "not_verified",
        "lookup_source": "stored" if stored else "undelivered_pull",
        "warnings": ["Rezervasyonun bulunması tam kabul değildir. Yetişkin/çocuk ayrımı ve yaşlar sağlayıcının yapılandırılmış verisiyle ayrıca doğrulanmalıdır."],
        "errors": [],
    }

    try:
        if not stored:
            creds = await resolve_exely_credentials(tenant_id, conn, actor="exely_test_booking_verify")
            if not creds:
                raise HTTPException(status_code=503, detail="Exely credentials are unavailable")
            username = creds["username"]
            password = creds["password"]
            hotel_code = creds["hotel_code"]
            endpoint_url = creds["endpoint_url"]
        # PMSConnect only supports SelectionType=Undelivered. A supplied ID is
        # filtered locally after the canonical undelivered read.
        if stored:
            # ACKed reservations are no longer in Undelivered. Finding the
            # scoped stored record does NOT claim a fresh provider read.
            verification["new_reservations"] = [await _stored_test_booking_summary(tenant_id, conn, stored, payload)]
        elif payload.reservation_id:
            provider_kwargs = {
                "username": username,
                "password": password,
                "hotel_code": hotel_code,
                "tenant_id": tenant_id,
                "property_id": hotel_code,
                "connection_id": f"{tenant_id}:{hotel_code}",
                "connection_mode": str(conn.get("mode") or ""),
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
                    if ingest_result.get("success") is False or ingest_result.get("action") in {"error", "failed"}:
                        verification["errors"].append("PMS_IMPORT_FAILED")
                    row = _test_booking_summary(raw_res, payload)
                    row["ingest_action"] = ingest_result.get("action", "unknown")
                    verification["new_reservations"].append(row)
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
                connection_mode=str(conn.get("mode") or ""),
            )
            verification["pull_result"] = {
                "success": result.get("success", False),
                "processed": result.get("processed", 0),
                "error": result.get("error"),
            }
            if not result.get("success"):
                verification["errors"].append("OTA_ReadRQ: provider_read_failed")

    except Exception as exc:
        verification["errors"].append(type(exc).__name__)

    # After state
    after_count = await db.exely_reservations.count_documents(scope)
    after_existing = await db.exely_reservations.find(
        scope,
        {"_id": 0, "external_id": 1, "guest_name": 1, "state": 1, "synced_at": 1},
    ).to_list(None)
    after_ids = {r["external_id"] for r in after_existing if r.get("external_id")}
    new_ids = after_ids - before_ids

    # Get details for newly discovered reservations
    if new_ids and not verification["new_reservations"]:
        new_res = await db.exely_reservations.find(
            {**scope, "external_id": {"$in": list(new_ids)}},
            {"_id": 0},
        ).to_list(50)
        verification["new_reservations"] = [await _stored_test_booking_summary(tenant_id, conn, r, payload) for r in new_res]

    # Filter by guest name if provided
    if payload.guest_name and verification["new_reservations"]:
        search = payload.guest_name.lower()
        verification["new_reservations"] = [r for r in verification["new_reservations"] if search in (r.get("guest_name", "") or "").lower()]

    verification["after_count"] = after_count
    verification["new_count"] = len(new_ids)

    if verification["errors"]:
        verification["verification_status"] = "error"
    elif verification["new_reservations"]:
        verification["verification_status"] = "found"
    else:
        verification["verification_status"] = "not_found"

    if any(row.get("acceptance_status") == "mismatch" for row in verification["new_reservations"]):
        verification["acceptance_status"] = "mismatch"

    return verification


# ── Sync Status & Scheduler ─────────────────────────────────────────


@router.get("/sync/status")
async def get_sync_status(current_user: User = Depends(get_current_user)):
    conn = await db.exely_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"_id": 0, "auto_sync_reservations": 1, "sync_interval_minutes": 1, "sync_interval_seconds": 1},
    )
    cursor = await db.exely_pull_cursors.find_one(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0},
    )
    pending_events = await db.exely_raw_events.count_documents(
        {"tenant_id": current_user.tenant_id, "status": "pending"},
    )
    error_cutoff = (datetime.now(UTC) - timedelta(hours=24)).isoformat()
    error_events = await db.exely_raw_events.count_documents(
        {
            "tenant_id": current_user.tenant_id,
            "status": "error",
            "received_at": {"$gte": error_cutoff},
        },
    )
    historical_error_events = await db.exely_raw_events.count_documents(
        {"tenant_id": current_user.tenant_id, "status": "error"},
    )
    total_reservations = await db.exely_reservations.count_documents(
        {"tenant_id": current_user.tenant_id},
    )
    return {
        "scheduler_running": exely_pull_scheduler.is_running,
        "reservation_sync_enabled": bool(conn and conn.get("auto_sync_reservations")),
        "sync_interval_seconds": connection_pull_interval_seconds(conn) if conn else None,
        "production_safety": safe_runtime_state(),
        "last_pull": cursor,
        "pending_events": pending_events,
        "error_events": error_events,
        "historical_error_events": historical_error_events,
        "error_window_hours": 24,
        "total_reservations": total_reservations,
    }


@router.post("/sync/scheduler/start")
async def start_scheduler(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),
):
    runtime_block = reservation_sync_block_reason()
    if runtime_block:
        raise HTTPException(status_code=503, detail=runtime_block)

    result = await db.exely_connections.update_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"$set": {"auto_sync_reservations": True, "sync_settings_updated_at": datetime.now(UTC).isoformat(), "sync_settings_updated_by": current_user.name}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Exely connection not found")
    await log_sync(PROVIDER, current_user.tenant_id, "reservation_sync_settings", "enabled", user_name=current_user.name)
    return {"message": "Bu tesis için otomatik rezervasyon çekimi açıldı; ortak çalışan değiştirilmedi.", "reservation_sync_enabled": True}


@router.post("/sync/scheduler/stop")
async def stop_scheduler(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),
):
    result = await db.exely_connections.update_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"$set": {"auto_sync_reservations": False, "sync_settings_updated_at": datetime.now(UTC).isoformat(), "sync_settings_updated_by": current_user.name}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Exely connection not found")
    await log_sync(PROVIDER, current_user.tenant_id, "reservation_sync_settings", "disabled", user_name=current_user.name)
    return {"message": "Bu tesis için otomatik rezervasyon çekimi durduruldu. Başlamış işlem güvenle tamamlanabilir; diğer tesisler etkilenmez.", "reservation_sync_enabled": False}


@router.patch("/sync/settings")
async def update_sync_settings(
    payload: ExelySyncSettings,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),
):
    result = await db.exely_connections.update_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"$set": {"sync_interval_minutes": payload.sync_interval_minutes, "sync_settings_updated_at": datetime.now(UTC).isoformat(), "sync_settings_updated_by": current_user.name}},
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Exely connection not found")
    await log_sync(PROVIDER, current_user.tenant_id, "reservation_sync_settings", "interval_updated", user_name=current_user.name)
    return {"message": "Tesisin çekim aralığı kaydedildi; mevcut kota/işlem kilidi dolduğunda uygulanır.", "sync_interval_minutes": payload.sync_interval_minutes}


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
