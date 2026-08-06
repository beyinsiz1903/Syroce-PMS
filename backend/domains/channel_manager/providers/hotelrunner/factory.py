"""
HotelRunner Router — Provider Factory
======================================

Resolves the active HotelRunner connection for a tenant and constructs a
`HotelRunnerProvider` instance with credentials from the secrets manager.
"""

from fastapi import HTTPException

from core.database import db

from .credentials import (
    hotelrunner_connection_projection,
    resolve_hotelrunner_credentials,
)


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
        hotelrunner_connection_projection(),
    )
    if not conn:
        pc = await db.provider_connections.find_one(
            {"tenant_id": tenant_id, "provider": "hotelrunner", "status": "active"},
            {
                "_id": 0,
                "credentials.hr_id": 1,
                "display_name": 1,
                "environment": 1,
                "property_id": 1,
                "hr_id": 1,
                "sync_reservations": 1,
            },
        )
        if pc:
            pc_creds = pc.get("credentials", {})
            legacy = await db.hotelrunner_connections.find_one({"tenant_id": tenant_id}, {"_id": 0, "cached_rooms": 1})
            conn = {
                "tenant_id": tenant_id,
                "property_id": pc.get("property_id", "default"),
                "hr_id": pc.get("hr_id") or pc_creds.get("hr_id", ""),
                "property_name": pc.get("display_name", ""),
                "environment": pc.get("environment", "live"),
                "is_active": True,
                "auto_sync_reservations": pc.get("sync_reservations", False),
                "channels": [],
                "cached_rooms": (legacy or {}).get("cached_rooms", []),
            }
        else:
            raise HTTPException(status_code=404, detail="HotelRunner baglantisi bulunamadi. Lutfen once baglanti kurun.")

    # Resolve environment
    environment = conn.get("environment", "mock")

    property_id = str(conn.get("property_id") or conn.get("hr_id") or "default")
    creds = await resolve_hotelrunner_credentials(
        tenant_id,
        conn,
        actor="hotelrunner.factory",
    )
    if not creds:
        raise HTTPException(status_code=502, detail="HotelRunner kimlik bilgileri bulunamadi")

    try:
        return HotelRunnerProvider(
            token=creds["token"],
            hr_id=creds.get("hr_id", ""),
            environment=environment,
            connection_id=f"{tenant_id}:{property_id}",
        ), conn
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"HotelRunner kimlik bilgileri gecersiz ({type(exc).__name__})",
        )
