"""HotelRunner credential resolution with production fail-closed semantics.

Resolution priority (highest to lowest):

1. Pluggable secrets manager — queried first by hr_id, then by property_id.
   Preserves backwards compatibility with connections stored under either key.
   The existing security priority order is never altered.

2. Encrypted Provider Config credential vault — ``get_decrypted_credentials``
   from ``credential_vault``.  Only reached when the secrets manager returns
   nothing.  Production connections established via the Provider Config screen
   store their token here (AES-encrypted, decrypted at runtime). The vault is
   queried by ``property_id`` first, then by ``hr_id`` for legacy records.

3. Plaintext legacy fallback — connection document ``token`` field.
   Available only in development / test environments.
   Production always returns ``None`` at this stage (fail-closed).

The resolved dict always includes a ``_credential_source`` key whose value is
one of ``secrets_manager``, ``encrypted_vault``, ``legacy_dev_fallback``, or
``missing``.  Callers MUST NOT log this dict directly; the source key is safe
metadata but ``token`` is sensitive.
"""

from typing import Any

from core.secrets import get_secrets_manager
from infra.production_config import is_production_env


async def get_decrypted_credentials(
    tenant_id: str,
    provider: str,
    property_id: str,
) -> dict[str, str] | None:
    """Thin indirection over credential_vault.get_decrypted_credentials.

    Defined at module scope so tests can monkeypatch this symbol directly.
    """
    from domains.channel_manager.credential_vault import (
        get_decrypted_credentials as _vault_fn,
    )

    return await _vault_fn(tenant_id, provider, property_id)


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
    """Resolve HotelRunner credentials without using plaintext production fallbacks.

    Tries the following sources in order:

    1. Secrets manager keyed by ``hr_id``
    2. Secrets manager keyed by ``property_id``
    3. Encrypted credential vault keyed by ``property_id``, then ``hr_id``
    4. Plaintext connection token (development/test only — fail-closed in production)

    Returns a dict with ``token``, ``hr_id``, and ``_credential_source`` on
    success, or ``None`` when no credential can be resolved.

    Security guarantees:
    - ``token`` and any other secret values are NEVER logged.
    - ``_credential_source`` contains only class-level metadata.
    - Production returns ``None`` instead of a plaintext fallback.
    - No provider call is made unless a credential is returned.
    """
    hr_id = str(connection.get("hr_id") or "")
    property_id = str(connection.get("property_id") or connection.get("hr_id") or "default")

    sm = get_secrets_manager()

    # ── 1. Secrets manager: try hr_id key ──────────────────────────────
    if hr_id and hr_id != "default":
        creds = await sm.get_provider_credentials(
            tenant_id,
            "hotelrunner",
            hr_id,
            actor=actor,
        )
        if creds and creds.get("token"):
            resolved_hr_id = str(creds.get("hr_id") or hr_id)
            return {
                "token": str(creds["token"]),
                "hr_id": resolved_hr_id,
                "_credential_source": "secrets_manager",
            }

    # ── 2. Secrets manager: try property_id key ────────────────────────
    if property_id and property_id != hr_id:
        creds = await sm.get_provider_credentials(
            tenant_id,
            "hotelrunner",
            property_id,
            actor=actor,
        )
        if creds and creds.get("token"):
            resolved_hr_id = str(creds.get("hr_id") or hr_id or property_id)
            return {
                "token": str(creds["token"]),
                "hr_id": resolved_hr_id,
                "_credential_source": "secrets_manager",
            }

    # ── 3. Encrypted Provider Config credential vault ──────────────────
    vault_ids = list(dict.fromkeys(candidate for candidate in (property_id, hr_id) if candidate))
    for vault_id in vault_ids:
        try:
            vault_creds = await get_decrypted_credentials(tenant_id, "hotelrunner", vault_id)
        except Exception:
            # A vault failure must not expose credentials or enable plaintext in production.
            continue
        if vault_creds and vault_creds.get("token"):
            resolved_hr_id = str(vault_creds.get("hr_id") or hr_id or vault_id)
            return {
                "token": str(vault_creds["token"]),
                "hr_id": resolved_hr_id,
                "_credential_source": "encrypted_vault",
            }

    # ── 4. Plaintext legacy fallback (dev/test only) ───────────────────
    if is_production_env():
        return None

    legacy_token = connection.get("token")
    if legacy_token and hr_id:
        return {
            "token": str(legacy_token),
            "hr_id": hr_id,
            "_credential_source": "legacy_dev_fallback",
        }

    return None
