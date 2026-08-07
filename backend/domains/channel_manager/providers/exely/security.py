"""Security boundaries for Exely credentials, endpoints, and telemetry."""

from __future__ import annotations

import hashlib
import os
from typing import Any
from urllib.parse import parse_qsl, urlsplit

from core.secrets import get_secrets_manager
from infra.production_config import is_production_env

from .errors import ExelyValidationError

PROVIDER = "exely"
EXELY_TEST_ENDPOINT_URL = "https://pmsconnect.test.hopenapi.com/api/PMSConnect.svc"
EXELY_TEST_HOST = "pmsconnect.test.hopenapi.com"
EXELY_PRODUCTION_HOST = "pmsconnect.prod.hopenapi.com"
EXELY_ALLOWED_HOSTS = frozenset({EXELY_TEST_HOST, EXELY_PRODUCTION_HOST})
EXELY_ENDPOINT_PATH = "/api/pmsconnect.svc"
EXELY_ALLOWED_QUERY_FIELDS = frozenset({"hotelcode"})


def is_exely_production() -> bool:
    if is_production_env():
        return True
    return any(os.getenv(key, "").strip().lower() in {"prod", "live"} for key in ("APP_ENV", "ENVIRONMENT", "NODE_ENV"))


def safe_fingerprint(value: str, *, length: int = 12) -> str:
    """Return a non-reversible label suitable for logs and diagnostics."""
    if not value:
        return "-"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:length]


def exely_connection_projection() -> dict[str, int]:
    """Do not load legacy plaintext credentials into production processes."""
    if is_exely_production():
        return {"_id": 0, "username": 0, "password": 0}
    return {"_id": 0}


def validate_exely_endpoint(endpoint_url: str) -> str:
    """Validate an Exely endpoint without resolving or contacting the host."""
    try:
        parsed = urlsplit(str(endpoint_url or ""))
        port = parsed.port
    except ValueError as exc:
        raise ExelyValidationError("Exely endpoint is malformed", field="endpoint_url") from exc

    hostname = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https":
        raise ExelyValidationError("Exely endpoint must use HTTPS", field="endpoint_url")
    if parsed.username or parsed.password:
        raise ExelyValidationError("Exely endpoint must not contain credentials", field="endpoint_url")
    if port not in (None, 443):
        raise ExelyValidationError("Exely endpoint port is not allowed", field="endpoint_url")
    if hostname not in EXELY_ALLOWED_HOSTS:
        raise ExelyValidationError("Exely endpoint host is not allowed", field="endpoint_url")
    if is_exely_production() and hostname != EXELY_PRODUCTION_HOST:
        raise ExelyValidationError("Production requires the Exely production endpoint", field="endpoint_url")
    if (parsed.path or "").rstrip("/").lower() != EXELY_ENDPOINT_PATH:
        raise ExelyValidationError("Exely endpoint path is not allowed", field="endpoint_url")
    if parsed.fragment:
        raise ExelyValidationError("Exely endpoint fragment is not allowed", field="endpoint_url")

    query_fields = [key.lower() for key, _value in parse_qsl(parsed.query, keep_blank_values=True)]
    if len(query_fields) != len(set(query_fields)) or any(key not in EXELY_ALLOWED_QUERY_FIELDS for key in query_fields):
        raise ExelyValidationError("Exely endpoint query is not allowed", field="endpoint_url")
    return endpoint_url


async def get_decrypted_credentials(
    tenant_id: str,
    provider: str,
    property_id: str,
) -> dict[str, str] | None:
    """Indirection for the encrypted legacy provider vault."""
    from domains.channel_manager.credential_vault import (
        get_decrypted_credentials as _vault_get,
    )

    return await _vault_get(tenant_id, provider, property_id)


def _normalize_credentials(credentials: dict[str, Any], connection: dict[str, Any]) -> dict[str, str] | None:
    username = str(credentials.get("username") or "")
    password = str(credentials.get("password") or "")
    hotel_code = str(credentials.get("hotel_code") or connection.get("hotel_code") or "")
    endpoint_url = str(credentials.get("endpoint_url") or connection.get("endpoint_url") or EXELY_TEST_ENDPOINT_URL)
    if not username or not password or not hotel_code:
        return None
    validate_exely_endpoint(endpoint_url)
    return {
        "username": username,
        "password": password,
        "hotel_code": hotel_code,
        "endpoint_url": endpoint_url,
    }


async def resolve_exely_credentials(
    tenant_id: str,
    connection: dict[str, Any],
    *,
    actor: str,
) -> dict[str, str] | None:
    """Resolve Exely credentials; plaintext is never accepted in production."""
    property_id = str(connection.get("hotel_code") or "")
    if not property_id:
        return None

    try:
        credentials = await get_secrets_manager().get_provider_credentials(
            tenant_id,
            PROVIDER,
            property_id,
            actor=actor,
        )
    except Exception:
        credentials = None
    if credentials:
        normalized = _normalize_credentials(credentials, connection)
        if normalized:
            normalized["_credential_source"] = "secrets_manager"
            return normalized

    try:
        credentials = await get_decrypted_credentials(tenant_id, PROVIDER, property_id)
    except Exception:
        credentials = None
    if credentials:
        normalized = _normalize_credentials(credentials, connection)
        if normalized:
            normalized["_credential_source"] = "encrypted_vault"
            return normalized

    if is_exely_production():
        return None

    normalized = _normalize_credentials(connection, connection)
    if normalized:
        normalized["_credential_source"] = "legacy_dev_fallback"
        return normalized
    return None


def production_webhook_bypass_allowed() -> bool:
    """The single-flag compatibility bypass is never valid in production."""
    return os.getenv("ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK") == "1" and not is_exely_production()
