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
        self.path_params = {"secret": "synthetic-plaintext-callback-secret"}
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
        "domains.channel_manager.providers.hotelrunner.credentials.credential_vault.get_decrypted_credentials",
        AsyncMock(return_value=None),
    )

    result = await resolve_hotelrunner_credentials(
        "synthetic-tenant",
        {"hr_id": "synthetic-property", "token": "synthetic-plaintext-token"},
        actor="offline-test",
    )

    assert result is None
    assert manager.calls == 1


@pytest.mark.asyncio
async def test_production_provider_config_encrypted_credentials_are_resolved(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    manager = _EmptySecretsManager()
    encrypted_vault_read = AsyncMock(
        return_value={
            "token": "synthetic-encrypted-token",
            "hr_id": "synthetic-hotel-id",
        }
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.get_secrets_manager",
        lambda: manager,
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.credentials.credential_vault.get_decrypted_credentials",
        encrypted_vault_read,
    )

    result = await resolve_hotelrunner_credentials(
        "synthetic-tenant",
        {
            "property_id": "default",
            "hr_id": "synthetic-hotel-id",
        },
        actor="offline-test",
    )

    assert result == {
        "token": "synthetic-encrypted-token",
        "hr_id": "synthetic-hotel-id",
    }
    assert manager.calls == 2
    encrypted_vault_read.assert_awaited_once_with(
        "synthetic-tenant",
        "hotelrunner",
        "default",
    )


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
        "domains.channel_manager.providers.hotelrunner.credentials.credential_vault.get_decrypted_credentials",
        AsyncMock(return_value=None),
    )

    result = await resolve_hotelrunner_credentials(
        "synthetic-tenant",
        {"hr_id": "synthetic-property", "token": "synthetic-local-token"},
        actor="offline-test",
    )

    assert result == {
        "token": "synthetic-local-token",
        "hr_id": "synthetic-property",
    }


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
    message = (
        "GET /api/channel-manager/hotelrunner/callback/synthetic-path-secret"
        "?token=synthetic-query-token&hr_id=synthetic-property"
    )

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
