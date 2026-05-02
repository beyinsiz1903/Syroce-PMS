"""
HotelRunner Router — Provider Factory
======================================

Resolves the active HotelRunner connection for a tenant and constructs a
`HotelRunnerProvider` instance with credentials from the secrets manager
(falling back to legacy plaintext storage when present).
"""
import logging

from fastapi import HTTPException

from core.database import db
from core.secrets import get_secrets_manager

logger = logging.getLogger(__name__)


async def get_provider(tenant_id: str):
    """Get HotelRunner provider instance for a tenant via secrets manager.

    Returns:
        Tuple of (HotelRunnerProvider, connection_dict).
    Raises:
        HTTPException 404 if no connection found.
        HTTPException 502 if credentials missing or invalid.
    """
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
            # v95 — Auto-migrate ONLY when vault is empty (create-if-absent guard).
            # Never overwrite an existing vault secret with plaintext.
            try:
                existing = None
                try:
                    existing = await sm.get_provider_credentials(
                        tenant_id, "hotelrunner", property_id
                    )
                except Exception:
                    existing = None
                if existing and existing.get("token"):
                    logger.warning(
                        "[HR-CREDS] Vault has token for tenant=%s property=%s but Tier-1 missed; "
                        "using plaintext fallback transiently (no overwrite).",
                        tenant_id, property_id,
                    )
                else:
                    await sm.store_provider_credentials(
                        tenant_id=tenant_id,
                        provider="hotelrunner",
                        property_id=property_id,
                        credentials={"token": creds["token"], "hr_id": creds["hr_id"]},
                        actor="hotelrunner.factory.auto_migrate",
                    )
                    logger.info(
                        "[HR-CREDS] Auto-migrated plaintext token → vault for tenant=%s property=%s",
                        tenant_id, property_id,
                    )
            except Exception as me:
                logger.warning(
                    "Using legacy plaintext credentials for HotelRunner tenant=%s — auto-migrate guard failed: %s",
                    tenant_id, me,
                )
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
