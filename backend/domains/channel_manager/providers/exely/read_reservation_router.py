"""Tenant/property-bound setup and reconciliation for the read-only REST API."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, SecretStr

from core.database import db
from core.secrets import get_secrets_manager
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op

from .demographics import reconcile_one, stable_reconciliation_plan
from .read_reservation import (
    VAULT_PROVIDER,
    ReadReservationError,
    origin_for,
    read_client,
    require_read_allowed,
    saved_read_credentials,
    test_read_scope,
)
from .security import exely_connection_projection

router = APIRouter(prefix="/read-reservation", tags=["Exely Read Reservation"])


class ReadSetup(BaseModel):
    client_id: SecretStr
    client_secret: SecretStr
    reservation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,160}$")
    confirmation: str
    test_read_only_consent: str = ""


class ReconcileRequest(BaseModel):
    reservation_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,160}$")


async def active_connection(user: User) -> dict:
    connection = await db.exely_connections.find_one({"tenant_id": user.tenant_id, "is_active": True}, exely_connection_projection())
    if not connection:
        raise HTTPException(404, "EXELY_CONNECTION_NOT_FOUND")
    try:
        origin_for(connection)
    except ReadReservationError as exc:
        raise HTTPException(409, str(exc)) from None
    return connection


@router.post("/connect")
async def connect_read_reservation(payload: ReadSetup, current_user: User = Depends(get_current_user), _perm=Depends(require_op("manage_channel_connectors"))):
    connection = await active_connection(current_user)
    property_id = str(connection["hotel_code"])
    if payload.confirmation != f"ENABLE_READ_RESERVATION:{property_id}":
        raise HTTPException(400, "EXELY_READ_CONFIRMATION_REQUIRED")
    scope = ""
    if payload.test_read_only_consent:
        scope = test_read_scope(connection)
        if not scope or payload.test_read_only_consent != "ALLOW_TEST_READ:501694":
            raise HTTPException(400, "EXELY_READ_TEST_CONSENT_INVALID")
        connection = {**connection, "read_reservation_test_read_scope": scope}
    credentials = {"client_id": payload.client_id.get_secret_value(), "client_secret": payload.client_secret.get_secret_value()}
    # Validate here, not in Pydantic errors which can echo invalid raw inputs.
    if any(not value.strip() or len(value) > 4096 for value in credentials.values()):
        raise HTTPException(400, "EXELY_READ_CREDENTIALS_INVALID")
    reservation = await db.exely_reservations.find_one({
        "tenant_id": current_user.tenant_id, "property_id": property_id, "external_id": payload.reservation_id,
    }, {"_id": 0})
    if not reservation:
        raise HTTPException(404, "EXELY_READ_LOCAL_RESERVATION_NOT_FOUND")
    try:
        require_read_allowed(connection)
        async with read_client(connection, credentials) as client:
            plans = await stable_reconciliation_plan(current_user.tenant_id, connection, reservation, client)
        await get_secrets_manager().store_provider_credentials(
            tenant_id=current_user.tenant_id, provider=VAULT_PROVIDER, property_id=property_id,
            credentials={**credentials, "property_id": property_id, "connection_id": str(connection["id"]), "mode": connection["mode"]},
            actor=current_user.name,
        )
        result = await db.exely_connections.update_one({
            "tenant_id": current_user.tenant_id, "id": connection["id"], "hotel_code": connection["hotel_code"],
            "mode": connection["mode"], "is_active": True,
        }, {"$set": {"read_reservation_enabled": True, "read_reservation_test_read_scope": scope}})
        if result.matched_count != 1:
            raise HTTPException(409, "EXELY_READ_CONNECTION_CHANGED")
    except ReadReservationError as exc:
        raise HTTPException(409, str(exc)) from None
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(503, "EXELY_READ_SETUP_UNAVAILABLE") from None
    return {"success": True, "property_id": property_id, "enabled": True, "applied": False,
            "rooms": [{"adults": plan["proof"]["adults"], "children_ages": plan["proof"]["children_ages"]} for plan in plans],
            "provider_write_count": 0}


@router.post("/pause")
async def pause_read_reservation(current_user: User = Depends(get_current_user), _perm=Depends(require_op("manage_channel_connectors"))):
    connection = await active_connection(current_user)
    result = await db.exely_connections.update_one({
        "tenant_id": current_user.tenant_id, "id": connection["id"], "hotel_code": connection["hotel_code"], "is_active": True,
    }, {"$set": {"read_reservation_enabled": False, "read_reservation_test_read_scope": ""}})
    if result.matched_count != 1:
        raise HTTPException(409, "EXELY_READ_CONNECTION_CHANGED")
    return {"success": True, "enabled": False}


@router.post("/reconcile")
async def reconcile_read_reservation(payload: ReconcileRequest, current_user: User = Depends(get_current_user), _perm=Depends(require_op("manage_channel_connectors"))):
    connection = await active_connection(current_user)
    try:
        require_read_allowed(connection)
        credentials = await saved_read_credentials(current_user.tenant_id, connection)
        if not credentials:
            raise ReadReservationError("EXELY_READ_NOT_CONFIGURED")
        async with read_client(connection, credentials) as client:
            return await reconcile_one(current_user.tenant_id, connection, payload.reservation_id, client)
    except ReadReservationError as exc:
        raise HTTPException(409, str(exc)) from None
    except Exception:
        raise HTTPException(503, "EXELY_READ_RECONCILIATION_UNAVAILABLE") from None
