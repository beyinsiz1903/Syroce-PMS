"""Resolve an active Exely provider without exposing credential material."""

from core.database import db

from .provider import ExelyProvider
from .security import exely_connection_projection, resolve_exely_credentials


async def get_exely_provider(tenant_id: str):
    connection = await db.exely_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True},
        exely_connection_projection(),
    )
    if not connection:
        raise RuntimeError("EXELY_CONNECTION_UNAVAILABLE")

    credentials = await resolve_exely_credentials(
        tenant_id,
        connection,
        actor="exely_ari_delivery",
    )
    if not credentials:
        raise RuntimeError("EXELY_CREDENTIALS_UNAVAILABLE")

    hotel_code = credentials["hotel_code"]
    provider = ExelyProvider(
        username=credentials["username"],
        password=credentials["password"],
        hotel_code=hotel_code,
        endpoint_url=credentials["endpoint_url"],
        connection_id=f"{tenant_id}:{hotel_code}",
        tenant_id=tenant_id,
        property_id=hotel_code,
        max_retries=0,
    )
    return provider, connection
