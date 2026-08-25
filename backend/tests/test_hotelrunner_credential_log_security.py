import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import HTTPException

import domains.channel_manager.providers.hotelrunner_security as hotelrunner_security
from domains.channel_manager import provider_config_router
from domains.channel_manager.ingest.pipeline import (
    _safe_normalized_timeline_metadata,
)
from domains.channel_manager.provider_config_router import SaveCredentialsRequest
from domains.channel_manager.providers.hotelrunner.client import HotelRunnerHttpClient
from domains.channel_manager.providers.hotelrunner.credentials import (
    hotelrunner_connection_projection,
    resolve_hotelrunner_credentials,
)
from domains.channel_manager.providers.hotelrunner.errors import (
    HotelRunnerParseError,
    HotelRunnerPayloadError,
)
from domains.channel_manager.providers.hotelrunner.observability import (
    persist_outbound_log,
)
from domains.channel_manager.providers.hotelrunner.parser import parse_reservations_response
from domains.channel_manager.providers.hotelrunner_shared import _store_raw_payload
from security.log_sanitizer import sanitize_string


class _FakeCollection:
    def __init__(self, existing=None):
        self.existing = existing
        self.inserted = []
        self.updated = []

    async def find_one(self, *args, **kwargs):
        return self.existing

    async def insert_one(self, doc):
        self.inserted.append(doc)

    async def update_one(self, query, update, **kwargs):
        self.updated.append((query, update, kwargs))

    async def update_many(self, query, update, **kwargs):
        self.updated.append((query, update, kwargs))


class _FakeDatabase:
    def __init__(self, collection):
        self.collection = collection
        self.webhook_raw_payloads = collection

    def __getitem__(self, name):
        return self.collection


class _EmptySecretsManager:
    def __init__(self):
        self.calls = 0

    async def get_provider_credentials(self, *args, **kwargs):
        self.calls += 1
        return None


class _QueryParams:
    def __init__(self, values):
        self.values = values

    def get(self, key, default=None):
        return self.values.get(key, default)


class _WebhookRequest:
    def __init__(self):
        self.headers = {"content-type": "application/json"}
        self.query_params = _QueryParams({"token": "synthetic-plaintext-token"})
        self.path_params = {}
        self.scope = {"type": "http", "req_id": "offline-security-test"}
        self.state = SimpleNamespace()
        self.client = SimpleNamespace(host="192.0.2.10")

    async def body(self):
        return b'{"hr_id":"synthetic-property"}'


@pytest.mark.asyncio
async def test_production_plaintext_connection_token_is_not_used(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    manager = _EmptySecretsManager()
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_secrets_manager",
        lambda: manager,
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_decrypted_credentials",
        AsyncMock(return_value=None),
        raising=False,
    )

    result = await resolve_hotelrunner_credentials(
        "synthetic-tenant",
        {"hr_id": "synthetic-property", "token": "synthetic-plaintext-token"},
        actor="offline-test",
    )

    assert result is None
    # hr_id path only (property_id == hr_id so deduped)
    assert manager.calls == 1


def test_production_connection_query_excludes_plaintext_fields(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")

    projection = hotelrunner_connection_projection()

    assert projection["token"] == 0
    assert projection["callback_secret"] == 0


@pytest.mark.asyncio
async def test_production_webhook_ignores_plaintext_connection_secrets(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("HOTELRUNNER_CALLBACK_SECRET", raising=False)

    async def lookup(_hr_id):
        return {
            "tenant_id": "synthetic-tenant",
            "hr_id": "synthetic-property",
            "token": "synthetic-plaintext-token",
            "callback_secret": "synthetic-plaintext-callback-secret",
        }

    monkeypatch.setattr(hotelrunner_security, "_lookup_signing_connection", lookup)
    monkeypatch.setattr(
        hotelrunner_security,
        "get_secrets_manager",
        lambda: _EmptySecretsManager(),
    )

    with pytest.raises(HTTPException) as exc_info:
        await hotelrunner_security._verify_hotelrunner_callback(_WebhookRequest())

    assert exc_info.value.status_code == 503


@pytest.mark.asyncio
async def test_development_plaintext_fallback_remains_local_only(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("NODE_ENV", raising=False)
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_secrets_manager",
        lambda: _EmptySecretsManager(),
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_decrypted_credentials",
        AsyncMock(return_value=None),
        raising=False,
    )

    result = await resolve_hotelrunner_credentials(
        "synthetic-tenant",
        {"hr_id": "synthetic-property", "token": "synthetic-local-token"},
        actor="offline-test",
    )

    assert result is not None
    assert result["token"] == "synthetic-local-token"
    assert result["hr_id"] == "synthetic-property"
    assert result["_credential_source"] == "legacy_dev_fallback"


@pytest.mark.asyncio
async def test_hotelrunner_config_create_persists_no_plaintext_credentials(monkeypatch):
    collection = _FakeCollection(existing=None)
    monkeypatch.setattr(provider_config_router, "db", _FakeDatabase(collection))
    monkeypatch.setattr(provider_config_router.vault, "store_secret", AsyncMock(return_value="synthetic-secret-ref"))
    upsert = AsyncMock()
    monkeypatch.setattr(provider_config_router.repo, "upsert_connection", upsert)

    await provider_config_router.save_credentials(
        "hotelrunner",
        SaveCredentialsRequest(
            credentials={
                "token": "synthetic-config-token",
                "hr_id": "synthetic-config-property",
            }
        ),
        SimpleNamespace(tenant_id="synthetic-tenant"),
        None,
    )

    persisted = upsert.await_args.args[0]
    assert persisted["credentials"] == {}
    assert persisted["hr_id"] == "synthetic-config-property"
    assert "synthetic-config-token" not in json.dumps(persisted)


@pytest.mark.asyncio
async def test_hotelrunner_config_update_unsets_legacy_plaintext_credentials(monkeypatch):
    collection = _FakeCollection(existing={"id": "existing"})
    monkeypatch.setattr(provider_config_router, "db", _FakeDatabase(collection))
    monkeypatch.setattr(provider_config_router.vault, "store_secret", AsyncMock(return_value="synthetic-secret-ref"))

    await provider_config_router.save_credentials(
        "hotelrunner",
        SaveCredentialsRequest(
            credentials={
                "token": "synthetic-rotated-token",
                "hr_id": "synthetic-config-property",
            }
        ),
        SimpleNamespace(tenant_id="synthetic-tenant"),
        None,
    )

    update = collection.updated[0][1]
    assert update["$unset"] == {"credentials": ""}
    assert "credentials" not in update["$set"]
    assert "synthetic-rotated-token" not in json.dumps(update)


def test_http_4xx_error_does_not_retain_provider_body():
    response = httpx.Response(
        400,
        text="guest@example.test token=synthetic-provider-token",
    )

    with pytest.raises(HotelRunnerPayloadError) as exc_info:
        HotelRunnerHttpClient._raise_for_status(response, 1, "synthetic-correlation")

    rendered = str(exc_info.value)
    assert "guest@example.test" not in rendered
    assert "synthetic-provider-token" not in rendered


def test_parse_error_keeps_only_response_hash_and_size():
    raw = "guest@example.test token=synthetic-provider-token"
    error = HotelRunnerParseError("Invalid JSON", raw_response=raw)

    assert error.raw_response == ""
    assert error.response_size_bytes == len(raw.encode())
    assert len(error.response_sha256) == 64
    assert "guest@example.test" not in str(error.__dict__)
    assert "synthetic-provider-token" not in str(error.__dict__)


def test_parser_log_does_not_include_reservation_or_guest_data(caplog):
    caplog.set_level(logging.WARNING, logger="hotelrunner.parser")
    payload = {
        "reservations": [
            {
                "hr_number": "synthetic-reservation-id",
                "firstname": "SyntheticGuest",
                "rooms": [{"total_adult": "not-an-integer"}],
            }
        ]
    }

    result = parse_reservations_response(payload)

    assert result.reservations == []
    assert "synthetic-reservation-id" not in caplog.text
    assert "SyntheticGuest" not in caplog.text
    assert "exception_class=ValueError" in caplog.text


@pytest.mark.asyncio
async def test_webhook_diagnostics_store_metadata_not_raw_payload(monkeypatch):
    collection = _FakeCollection()
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner_shared.db",
        _FakeDatabase(collection),
    )
    payload = {
        "hr_number": "synthetic-reservation-id",
        "guest": {"name": "SyntheticGuest"},
        "token": "synthetic-payload-token",
    }

    await _store_raw_payload(
        tenant_id="synthetic-tenant",
        correlation_id="synthetic-correlation",
        provider="hotelrunner",
        external_id="synthetic-reservation-id",
        event_type="reservation_create",
        payload=payload,
        source_ip="192.0.2.10",
    )

    persisted = collection.inserted[0]
    rendered = json.dumps(persisted)
    assert "raw_payload" not in persisted
    assert "external_id" not in persisted
    assert "source_ip" not in persisted
    assert persisted["payload_field_names"] == ["guest", "hr_number", "token"]
    assert "synthetic-reservation-id" not in rendered
    assert "SyntheticGuest" not in rendered
    assert "synthetic-payload-token" not in rendered
    assert "192.0.2.10" not in rendered


@pytest.mark.asyncio
async def test_outbound_audit_persists_payload_metadata_only():
    collection = _FakeCollection()
    payload = {
        "guest_name": "SyntheticGuest",
        "token": "synthetic-outbound-token",
    }

    await persist_outbound_log(
        _FakeDatabase(collection),
        connection_id="synthetic-tenant:synthetic-property",
        operation="inventory",
        path="/api/v2/apps/rooms/daily",
        method="PUT",
        request_payload=payload,
    )

    persisted = collection.inserted[0]
    rendered = json.dumps(persisted)
    assert "connection_id" not in persisted
    assert "request_payload_summary" not in persisted
    assert set(persisted["request_payload_metadata"]) == {
        "field_names",
        "sha256",
        "size_bytes",
    }
    assert "SyntheticGuest" not in rendered
    assert "synthetic-outbound-token" not in rendered
    assert "synthetic-tenant" not in rendered


def test_hotelrunner_query_and_path_secrets_are_redacted():
    message = "GET /api/channel-manager/hotelrunner/callback/synthetic-path-secret?token=synthetic-query-token&hr_id=synthetic-property"

    sanitized = sanitize_string(message)

    assert "synthetic-path-secret" not in sanitized
    assert "synthetic-query-token" not in sanitized
    assert "***REDACTED***" in sanitized


def test_normalized_timeline_metadata_omits_guest_and_amount():
    metadata = _safe_normalized_timeline_metadata(
        {
            "guest_name": "SyntheticGuest",
            "total_amount": 123.45,
            "check_in": "2026-08-01",
            "check_out": "2026-08-02",
            "room_type_code": "SYNTHETIC-ROOM",
            "rate_plan_code": "SYNTHETIC-RATE",
            "currency": "TRY",
            "status": "confirmed",
        }
    )

    assert "guest_name" not in metadata
    assert "total_amount" not in metadata
    assert "SyntheticGuest" not in json.dumps(metadata)


# ─────────────────────────────────────────────────────────────────────────────
# Credential Resolver: new dual-key + vault scenarios (PR #214 additions)
# ─────────────────────────────────────────────────────────────────────────────


class _SecretsManagerWithHrId:
    """Returns credentials when queried by hr_id key."""

    def __init__(self, hit_key: str, token: str, hr_id: str):
        self._hit_key = hit_key
        self._token = token
        self._hr_id = hr_id
        self.calls: list[str] = []

    async def get_provider_credentials(self, tenant_id, provider, property_id, *, actor):
        self.calls.append(property_id)
        if property_id == self._hit_key:
            return {"token": self._token, "hr_id": self._hr_id}
        return None


@pytest.mark.asyncio
async def test_production_secrets_manager_resolves_by_hr_id(monkeypatch):
    """Scenario 1: production + secrets manager + hr_id => PASS."""
    monkeypatch.setenv("APP_ENV", "production")
    manager = _SecretsManagerWithHrId(
        hit_key="synthetic-hr-id",
        token="synthetic-sm-token",
        hr_id="synthetic-hr-id",
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_secrets_manager",
        lambda: manager,
    )

    result = await resolve_hotelrunner_credentials(
        "synthetic-tenant",
        {"hr_id": "synthetic-hr-id", "property_id": "synthetic-prop-id"},
        actor="offline-test",
    )

    assert result is not None
    assert result["token"] == "synthetic-sm-token"
    assert result["hr_id"] == "synthetic-hr-id"
    assert result["_credential_source"] == "secrets_manager"
    # hr_id tried first — resolved immediately
    assert manager.calls[0] == "synthetic-hr-id"


@pytest.mark.asyncio
async def test_production_secrets_manager_resolves_by_property_id(monkeypatch):
    """Scenario 2: production + secrets manager + property_id => PASS."""
    monkeypatch.setenv("APP_ENV", "production")
    manager = _SecretsManagerWithHrId(
        hit_key="synthetic-prop-id",
        token="synthetic-prop-token",
        hr_id="synthetic-hr-id",
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_secrets_manager",
        lambda: manager,
    )

    # hr_id != property_id so both paths are attempted
    result = await resolve_hotelrunner_credentials(
        "synthetic-tenant",
        {"hr_id": "synthetic-hr-id", "property_id": "synthetic-prop-id"},
        actor="offline-test",
    )

    assert result is not None
    assert result["token"] == "synthetic-prop-token"
    assert result["_credential_source"] == "secrets_manager"
    # hr_id tried first, then property_id
    assert "synthetic-hr-id" in manager.calls
    assert "synthetic-prop-id" in manager.calls


@pytest.mark.asyncio
async def test_production_encrypted_vault_fallback(monkeypatch):
    """Scenario 3: production + encrypted Provider Config vault => PASS."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_secrets_manager",
        lambda: _EmptySecretsManager(),
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_decrypted_credentials",
        AsyncMock(return_value={"token": "synthetic-vault-token", "hr_id": "synthetic-hr-id"}),
        raising=False,
    )

    result = await resolve_hotelrunner_credentials(
        "synthetic-tenant",
        {"hr_id": "synthetic-hr-id"},
        actor="offline-test",
    )

    assert result is not None
    assert result["token"] == "synthetic-vault-token"
    assert result["hr_id"] == "synthetic-hr-id"
    assert result["_credential_source"] == "encrypted_vault"


@pytest.mark.asyncio
async def test_production_encrypted_vault_resolves_provider_config_property_id(monkeypatch):
    """Provider Config vault records are keyed by property_id, not HotelRunner ID."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_secrets_manager",
        lambda: _EmptySecretsManager(),
    )
    vault = AsyncMock(
        side_effect=lambda _tenant, _provider, key: (
            {"token": "synthetic-vault-token", "hr_id": "synthetic-hr-id"}
            if key == "synthetic-property-id"
            else None
        ),
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_decrypted_credentials",
        vault,
        raising=False,
    )

    result = await resolve_hotelrunner_credentials(
        "synthetic-tenant",
        {"hr_id": "synthetic-hr-id", "property_id": "synthetic-property-id"},
        actor="offline-test",
    )

    assert result is not None
    assert result["token"] == "synthetic-vault-token"
    assert result["hr_id"] == "synthetic-hr-id"
    assert result["_credential_source"] == "encrypted_vault"
    assert vault.await_count == 1
    assert vault.await_args.args[2] == "synthetic-property-id"


@pytest.mark.asyncio
async def test_encrypted_vault_falls_back_to_hr_id_without_duplicate_lookup(monkeypatch):
    """Legacy vault records remain resolvable and identical keys are queried once."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_secrets_manager",
        lambda: _EmptySecretsManager(),
    )
    vault = AsyncMock(return_value={"token": "synthetic-token", "hr_id": "synthetic-hr-id"})
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_decrypted_credentials",
        vault,
        raising=False,
    )

    result = await resolve_hotelrunner_credentials(
        "synthetic-tenant",
        {"hr_id": "synthetic-hr-id", "property_id": "synthetic-hr-id"},
        actor="offline-test",
    )

    assert result is not None
    assert result["_credential_source"] == "encrypted_vault"
    assert vault.await_count == 1


@pytest.mark.asyncio
async def test_production_only_plaintext_token_fails_closed(monkeypatch):
    """Scenario 4: production + only plaintext connection token => FAIL-CLOSED."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_secrets_manager",
        lambda: _EmptySecretsManager(),
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_decrypted_credentials",
        AsyncMock(return_value=None),
        raising=False,
    )

    result = await resolve_hotelrunner_credentials(
        "synthetic-tenant",
        {"hr_id": "synthetic-hr-id", "token": "synthetic-plaintext-token"},
        actor="offline-test",
    )

    assert result is None


@pytest.mark.asyncio
async def test_development_controlled_legacy_plaintext_fallback(monkeypatch):
    """Scenario 5: development + controlled legacy plaintext fallback => PASS."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("NODE_ENV", raising=False)
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_secrets_manager",
        lambda: _EmptySecretsManager(),
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_decrypted_credentials",
        AsyncMock(return_value=None),
        raising=False,
    )

    result = await resolve_hotelrunner_credentials(
        "synthetic-tenant",
        {"hr_id": "synthetic-hr-id", "token": "synthetic-dev-token"},
        actor="offline-test",
    )

    assert result is not None
    assert result["_credential_source"] == "legacy_dev_fallback"
    assert result["token"] == "synthetic-dev-token"


@pytest.mark.asyncio
async def test_credential_values_not_in_returned_credential_source_key(monkeypatch):
    """Scenario 8: credential values do not appear in _credential_source metadata."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("NODE_ENV", raising=False)
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_secrets_manager",
        lambda: _EmptySecretsManager(),
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_decrypted_credentials",
        AsyncMock(return_value=None),
        raising=False,
    )

    result = await resolve_hotelrunner_credentials(
        "synthetic-tenant",
        {"hr_id": "synthetic-hr-id", "token": "SHOULD-NOT-APPEAR-IN-SOURCE"},
        actor="offline-test",
    )

    assert result is not None
    assert "SHOULD-NOT-APPEAR-IN-SOURCE" not in result["_credential_source"]
    assert result["_credential_source"] in (
        "secrets_manager",
        "encrypted_vault",
        "legacy_dev_fallback",
    )


@pytest.mark.asyncio
async def test_no_credential_returns_none_no_exception(monkeypatch):
    """Scenario 7: credential not found => None returned, no provider write."""
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_secrets_manager",
        lambda: _EmptySecretsManager(),
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_decrypted_credentials",
        AsyncMock(return_value=None),
        raising=False,
    )

    result = await resolve_hotelrunner_credentials(
        "synthetic-tenant",
        {"hr_id": "synthetic-hr-id"},
        actor="offline-test",
    )

    assert result is None


@pytest.mark.asyncio
async def test_vault_exception_does_not_propagate(monkeypatch):
    """Vault failure must fall through to next source, not raise."""
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("NODE_ENV", raising=False)
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_secrets_manager",
        lambda: _EmptySecretsManager(),
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_decrypted_credentials",
        AsyncMock(side_effect=RuntimeError("vault unreachable")),
        raising=False,
    )

    # Should reach legacy fallback without raising
    result = await resolve_hotelrunner_credentials(
        "synthetic-tenant",
        {"hr_id": "synthetic-hr-id", "token": "synthetic-dev-token"},
        actor="offline-test",
    )

    assert result is not None
    assert result["_credential_source"] == "legacy_dev_fallback"


def test_credential_source_values_are_safe_class_metadata():
    """_credential_source must only be one of the four defined safe values."""
    import inspect

    from domains.channel_manager.providers.hotelrunner import credentials as creds_mod

    source = inspect.getsource(creds_mod)
    for assignment in (
        '"secrets_manager"',
        '"encrypted_vault"',
        '"legacy_dev_fallback"',
    ):
        assert assignment in source, f"Expected {assignment} in source"

    # Verify no raw secret value is assigned to _credential_source
    for forbidden in ("token", "password", "secret", "key"):
        # Only the key name 'token' appears in credential source assignment lines
        # — not its value
        lines = [ln for ln in source.splitlines() if "_credential_source" in ln and forbidden in ln]
        # allow mentions like checking creds.get("token") but not as value
        for ln in lines:
            assert "creds" not in ln or '= "' not in ln, f"Possible credential value leak in _credential_source assignment: {ln}"
