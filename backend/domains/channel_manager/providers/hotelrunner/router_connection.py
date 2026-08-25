"""
HotelRunner Router — Connection / Settings Endpoints
======================================================

Connection lifecycle (connect, status, test, disconnect) plus channel
discovery and transaction lookup. These endpoints DO call the provider
client over HTTP for the live `test_connection`, `get_channels`,
`get_connected_channels`, and `get_transaction_details` operations.

Mounted under the main `/api/channel-manager/hotelrunner` prefix by the
parent router.
"""

import logging
import os
import secrets
import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException

from core.database import db
from core.secrets import get_secrets_manager
from core.security import get_current_user
from models.schemas import User
from modules.pms_core.role_permission_service import require_op  # v101 DW

from .credentials import hotelrunner_connection_projection
from .factory import get_provider
from .router_schemas import HRConnectionSetup
from .sync_log import log_sync

logger = logging.getLogger(__name__)

router = APIRouter()


# ── Connection Management ────────────────────────────────────────────


@router.post("/connect")
async def setup_connection(
    payload: HRConnectionSetup,
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    """Setup HotelRunner connection with credentials and test it."""
    from domains.channel_manager.providers.hotelrunner import HotelRunnerProvider

    logger.info("[HR-CONNECT] connection test started env=%s", payload.environment)

    provider = HotelRunnerProvider(
        token=payload.token,
        hr_id=payload.hr_id,
        environment=payload.environment,
    )

    logger.info("[HR-CONNECT] target_url=%s", provider._base_url)

    test_result = await provider.test_connection()

    if not test_result.success:
        logger.error(
            "[HR-CONNECT] FAILED error_type=%s env=%s",
            test_result.error_type or "ProviderRejected",
            payload.environment,
        )
        raise HTTPException(
            status_code=400,
            detail=f"HotelRunner baglanti hatasi ({test_result.error_type or 'ProviderRejected'})",
        )

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

    await log_sync(current_user.tenant_id, "connection", "success", duration_ms=test_result.duration_ms, user_name=current_user.name)

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
        {
            "_id": 0,
            "token": 0,
            "callback_secret": 0,
            "credentials_ref": 0,
        },
    )
    if not conn:
        return {"connected": False, "message": "HotelRunner baglantisi kurulmamis"}

    return {"connected": conn.get("is_active", False), "connection": conn}


@router.get("/callback-readiness")
async def get_callback_readiness(current_user: User = Depends(get_current_user)):
    """Return a secret-safe readiness view for HotelRunner real-time push.

    HotelRunner's official callback authenticates with ``token`` and ``hr_id``.
    We never return either value.  Legacy path-secret presence is reported only
    as a boolean so operators can identify old URLs without exposing secrets.
    This endpoint is read-only and performs no provider call.
    """
    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"_id": 0, "hr_id": 1},
    )
    if not conn or not conn.get("hr_id"):
        return {
            "ready": False,
            "official_auth": "token_plus_hr_id",
            "callback_url": None,
            "credentials_configured": False,
            "legacy_path_secret_configured": False,
            "legacy_path_secret_blocks_official_url": False,
            "registration_requires_provider_confirmation": True,
            "blockers": ["HOTELRUNNER_CONNECTION_MISSING"],
        }

    hr_id = str(conn["hr_id"])
    try:
        credentials = await get_secrets_manager().get_provider_credentials(
            current_user.tenant_id,
            "hotelrunner",
            hr_id,
            actor=current_user.name,
        )
    except Exception:
        logger.exception("HotelRunner callback readiness credential lookup failed")
        raise HTTPException(status_code=503, detail="HotelRunner credential service unavailable")

    credentials = credentials or {}
    stored_hr_id = str(credentials.get("hr_id") or "")
    credentials_configured = bool(credentials.get("token")) and stored_hr_id == hr_id
    legacy_path_secret_configured = bool(
        credentials.get("callback_secret")
        or os.environ.get("HOTELRUNNER_CALLBACK_SECRET")
    )
    callback_path = "/api/channel-manager/hotelrunner/callback"
    public_base = (os.environ.get("PUBLIC_APP_URL") or "").strip().rstrip("/")
    callback_url = f"{public_base}{callback_path}" if public_base else callback_path
    blockers = [] if credentials_configured else ["HOTELRUNNER_ENCRYPTED_CREDENTIALS_MISSING"]

    return {
        "ready": credentials_configured,
        "official_auth": "token_plus_hr_id",
        "callback_url": callback_url,
        "credentials_configured": credentials_configured,
        "legacy_path_secret_configured": legacy_path_secret_configured,
        "legacy_path_secret_blocks_official_url": False,
        "registration_requires_provider_confirmation": True,
        "blockers": blockers,
    }


@router.post("/test")
async def test_connection(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    """Test existing HotelRunner connection."""
    tid = current_user.tenant_id
    hr_conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": tid, "is_active": True},
        hotelrunner_connection_projection(),
    )
    if not hr_conn:
        hr_conn = await db.provider_connections.find_one(
            {"tenant_id": tid, "provider": "hotelrunner", "status": "active"},
            {"_id": 0, "environment": 1, "mode": 1},
        )
    if not hr_conn:
        raise HTTPException(status_code=404, detail="HotelRunner baglantisi bulunamadi. Lutfen once baglanti kurun.")

    env = hr_conn.get("environment") or hr_conn.get("mode")
    if env in ("sandbox", "mock"):
        return {"success": True, "connected": True, "mode": env, "message": "Sandbox/mock test basarili"}

    provider, conn = await get_provider(tid)
    result = await provider.test_connection()
    result_data = result.data if isinstance(result.data, dict) else {}
    connected = bool(result.success and result_data.get("connected", True))
    safe_error_type = result.error_type or "ProviderConnectionError"
    return {
        "success": bool(result.success),
        "connected": connected,
        "duration_ms": result.duration_ms,
        "error": "" if connected else safe_error_type,
        "error_type": "" if connected else safe_error_type,
    }


@router.delete("/disconnect")
async def disconnect(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),  # v101 DW
):
    """Disconnect HotelRunner integration."""
    result = await db.hotelrunner_connections.update_one(
        {"tenant_id": current_user.tenant_id},
        {"$set": {"is_active": False, "disconnected_at": datetime.now(UTC).isoformat()}},
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Aktif baglanti bulunamadi")

    return {"message": "HotelRunner baglantisi kesildi"}


# ── Custom HMAC Signing Secret (non-HotelRunner senders only) ────────


@router.get("/webhook-secret")
async def get_webhook_secret_status(current_user: User = Depends(get_current_user)):
    """Return whether the optional Syroce custom-HMAC secret is configured.

    HotelRunner's official callback does not use this secret.  The secret value
    is never returned here — only its configured state and rotation timestamp.
    """
    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0, "webhook_secret_set": 1, "webhook_secret_rotated_at": 1},
    )
    if not conn:
        return {"configured": False, "rotated_at": None}
    return {
        "configured": bool(conn.get("webhook_secret_set")),
        "rotated_at": conn.get("webhook_secret_rotated_at"),
    }


@router.post("/webhook-secret/rotate")
async def rotate_webhook_secret(
    current_user: User = Depends(get_current_user),
    _perm=Depends(require_op("manage_channel_connectors")),
):
    """Generate or rotate the optional Syroce custom-HMAC signing secret.

    The new secret is generated server-side, stored encrypted in the
    SecretsManager (never written to the connection document), and returned in
    plaintext exactly once. HotelRunner's official real-time push does not use
    this endpoint or this secret.
    """
    conn = await db.hotelrunner_connections.find_one(
        {"tenant_id": current_user.tenant_id, "is_active": True},
        {"_id": 0, "hr_id": 1},
    )
    if not conn or not conn.get("hr_id"):
        raise HTTPException(
            status_code=404,
            detail="HotelRunner baglantisi bulunamadi. Lutfen once baglanti kurun.",
        )

    new_secret = secrets.token_hex(32)
    sm = get_secrets_manager()
    await sm.store_webhook_secret(
        tenant_id=current_user.tenant_id,
        provider="hotelrunner",
        property_id=str(conn["hr_id"]),
        secret=new_secret,
        actor=current_user.name,
    )

    now = datetime.now(UTC).isoformat()
    await db.hotelrunner_connections.update_one(
        {"tenant_id": current_user.tenant_id},
        {
            "$set": {
                "webhook_secret_set": True,
                "webhook_secret_rotated_at": now,
                "webhook_secret_rotated_by": current_user.name,
            }
        },
    )

    from core.masking import fingerprint_id

    logger.info(
        "[HR-WEBHOOK-SECRET] rotated tenant_fp=%s property_fp=%s",
        fingerprint_id(current_user.tenant_id),
        fingerprint_id(str(conn["hr_id"])),
    )

    return {
        "message": ("Yalnizca ozel HMAC gondericileri icin imza secret'i olusturuldu. Resmi HotelRunner callback akisi bu degeri kullanmaz."),
        "mode": "custom_hmac_only",
        "hotelrunner_official": False,
        "webhook_secret": new_secret,
        "rotated_at": now,
    }


# ── Channel Operations ───────────────────────────────────────────────


@router.get("/channels")
async def get_channels(current_user: User = Depends(get_current_user)):
    """Get all available HotelRunner channels."""
    provider, conn = await get_provider(current_user.tenant_id)
    result = await provider.get_channels()
    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"Kanal listesi hatasi: {result['error']}")
    return result["data"]


@router.get("/channels/connected")
async def get_connected_channels(current_user: User = Depends(get_current_user)):
    """Get connected channels with process stats."""
    provider, conn = await get_provider(current_user.tenant_id)
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
    provider, conn = await get_provider(current_user.tenant_id)
    result = await provider.get_transaction_details(transaction_id)
    if not result["success"]:
        raise HTTPException(status_code=502, detail=f"Islem detay hatasi: {result['error']}")
    return result["data"]
