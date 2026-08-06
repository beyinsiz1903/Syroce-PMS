"""HotelRunner credential resolution with production fail-closed semantics."""

from typing import Any

from core.secrets import get_secrets_manager
from domains.channel_manager import credential_vault
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
    hr_id = str(connection.get("hr_id") or "")
    configured_property_id = connection.get("property_id")
    property_id = str(configured_property_id or "default")

    sm = get_secrets_manager()
    # The native HotelRunner connection flow stores secrets under ``hr_id``;
    # the generic provider-config flow stores them under ``property_id``.  Try
    # both identities so either supported setup path produces a usable
    # connection (and preserve hr_id-first compatibility with existing data).
    secret_ids = list(
        dict.fromkeys(
            value
            for value in (hr_id, str(configured_property_id or ""))
            if value
        )
    )
    for secret_id in secret_ids:
        creds = await sm.get_provider_credentials(
            tenant_id,
            "hotelrunner",
            secret_id,
            actor=actor,
        )
        if creds and creds.get("token"):
            resolved_hr_id = str(creds.get("hr_id") or hr_id)
            if resolved_hr_id:
                return {"token": str(creds["token"]), "hr_id": resolved_hr_id}

    # Provider Config uses the encrypted database vault rather than the
    # pluggable secrets manager.  This is still an encrypted-at-rest source,
    # unlike the legacy plaintext connection fields rejected below.
    vault_ids = list(dict.fromkeys((property_id, "default", "")))
    for vault_id in vault_ids:
        creds = await credential_vault.get_decrypted_credentials(
            tenant_id,
            "hotelrunner",
            vault_id,
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
