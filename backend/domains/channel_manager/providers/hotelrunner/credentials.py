"""HotelRunner credential resolution with production fail-closed semantics."""

from typing import Any

from core.secrets import get_secrets_manager
from infra.production_config import is_production_env


def hotelrunner_connection_projection() -> dict[str, int]:
    """Avoid loading legacy plaintext fields into production processes."""
    if is_production_env():
        return {"_id": 0, "token": 0, "callback_secret": 0}
    return {"_id": 0}


async def resolve_hotelrunner_credentials(
    tenant_id: str,
    connection: dict[str, Any],
    *,
    actor: str,
) -> dict[str, str] | None:
    """Resolve credentials without using plaintext production fallbacks.

    Production accepts only the configured secrets backend. The connection
    document fallback remains available in test/development so offline and
    local compatibility workflows can migrate independently.
    """
    property_id = str(connection.get("property_id") or connection.get("hr_id") or "default")
    hr_id = str(connection.get("hr_id") or "")

    sm = get_secrets_manager()
    creds = await sm.get_provider_credentials(
        tenant_id,
        "hotelrunner",
        property_id,
        actor=actor,
    )
    if creds and creds.get("token"):
        resolved_hr_id = str(creds.get("hr_id") or hr_id)
        if resolved_hr_id:
            return {"token": str(creds["token"]), "hr_id": resolved_hr_id}

    if is_production_env():
        return None

    legacy_token = connection.get("token")
    if legacy_token and hr_id:
        return {"token": str(legacy_token), "hr_id": hr_id}
    return None
