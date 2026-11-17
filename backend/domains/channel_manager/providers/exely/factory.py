"""Resolve an active Exely provider without exposing credential material."""

from core.database import db

from .production_safety import provider_io_block_reason
from .provider import ExelyProvider
from .security import exely_connection_projection, resolve_exely_credentials


async def get_exely_provider(tenant_id: str, *, property_id: str | None = None, actor: str = "exely_ari_delivery"):
    runtime_block = provider_io_block_reason()
    if runtime_block:
        raise RuntimeError(runtime_block)

    connection = await db.exely_connections.find_one(
        {"tenant_id": tenant_id, "is_active": True, **({"hotel_code": property_id} if property_id else {})},
        exely_connection_projection(),
    )
    if not connection:
        raise RuntimeError("EXELY_CONNECTION_UNAVAILABLE")

    credentials = await resolve_exely_credentials(
        tenant_id,
        connection,
        actor=actor,
    )
    if not credentials:
        raise RuntimeError("EXELY_CREDENTIALS_UNAVAILABLE")

    hotel_code = credentials["hotel_code"]
    if property_id and hotel_code != property_id:
        raise RuntimeError("EXELY_PROPERTY_MISMATCH")
    provider = ExelyProvider(
        username=credentials["username"],
        password=credentials["password"],
        hotel_code=hotel_code,
        endpoint_url=credentials["endpoint_url"],
        connection_id=f"{tenant_id}:{hotel_code}",
        tenant_id=tenant_id,
        property_id=hotel_code,
        connection_mode=str(connection.get("mode") or ""),
        max_retries=0,
    )
    return provider, connection
