import ast
import inspect
import json
import logging
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from domains.channel_manager.providers import common_ingest
from domains.channel_manager.providers.exely import exely_webhook_router
from domains.channel_manager.providers.exely.client import ExelySoapTransport
from domains.channel_manager.providers.exely.errors import ExelyParseError, ExelyPayloadError, ExelyValidationError
from domains.channel_manager.providers.exely.observability import persist_outbound_log
from domains.channel_manager.providers.exely.response_parser import parse_read_rs
from domains.channel_manager.providers.exely.security import (
    EXELY_PRODUCTION_HOST,
    EXELY_TEST_ENDPOINT_URL,
    exely_connection_projection,
    production_webhook_bypass_allowed,
    resolve_exely_credentials,
    validate_exely_endpoint,
)
from security.log_sanitizer import sanitize_string


class _Collection:
    def __init__(self):
        self.inserted = []
        self.updated = []

    async def insert_one(self, document):
        self.inserted.append(document)

    async def update_one(self, query, update, **kwargs):
        self.updated.append((query, update, kwargs))


class _Database:
    def __init__(self, collection):
        self.collection = collection
        self.webhook_raw_payloads = collection

    def __getitem__(self, _name):
        return self.collection


class _EmptySecretsManager:
    async def get_provider_credentials(self, *args, **kwargs):
        return None


class _SecretsManager:
    async def get_provider_credentials(self, *args, **kwargs):
        return {
            "username": "synthetic-vault-user",
            "password": "synthetic-vault-password",
            "hotel_code": "synthetic-property",
            "endpoint_url": EXELY_TEST_ENDPOINT_URL,
        }


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    for key in ("APP_ENV", "ENVIRONMENT", "NODE_ENV", "ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK"):
        monkeypatch.delenv(key, raising=False)


def test_official_test_endpoint_is_allowed_offline():
    assert validate_exely_endpoint(EXELY_TEST_ENDPOINT_URL) == EXELY_TEST_ENDPOINT_URL


def test_legacy_direct_http_client_is_removed():
    legacy_path = Path(__file__).parents[1] / "domains/channel_manager/providers/exely/exely_client_legacy.py"
    assert not legacy_path.exists()


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://pmsconnect.test.hopenapi.com/api/PMSConnect.svc",
        "https://attacker.example/api/PMSConnect.svc",
        "https://synthetic-user:synthetic-password@pmsconnect.test.hopenapi.com/api/PMSConnect.svc",
        "https://pmsconnect.test.hopenapi.com/other",
        "https://pmsconnect.test.hopenapi.com/api/PMSConnect.svc?token=synthetic-query-secret",
    ],
)
def test_untrusted_endpoint_shapes_fail_closed(endpoint):
    with pytest.raises(ExelyValidationError):
        validate_exely_endpoint(endpoint)


def test_production_rejects_test_endpoint_and_accepts_allowlisted_production_host(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")

    with pytest.raises(ExelyValidationError):
        validate_exely_endpoint(EXELY_TEST_ENDPOINT_URL)

    production_url = f"https://{EXELY_PRODUCTION_HOST}/api/PMSConnect.svc"
    assert validate_exely_endpoint(production_url) == production_url


@pytest.mark.asyncio
async def test_production_plaintext_credentials_are_never_resolved(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setattr(
        "domains.channel_manager.providers.exely.security.get_secrets_manager",
        lambda: _EmptySecretsManager(),
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.exely.security.get_decrypted_credentials",
        AsyncMock(return_value=None),
    )

    result = await resolve_exely_credentials(
        "synthetic-tenant",
        {
            "hotel_code": "synthetic-property",
            "username": "synthetic-plaintext-user",
            "password": "synthetic-plaintext-password",
            "endpoint_url": f"https://{EXELY_PRODUCTION_HOST}/api/PMSConnect.svc",
        },
        actor="offline-test",
    )

    assert result is None
    assert exely_connection_projection() == {"_id": 0, "username": 0, "password": 0}


@pytest.mark.asyncio
async def test_secrets_manager_credentials_are_resolved_without_plaintext_fallback(monkeypatch):
    monkeypatch.setattr(
        "domains.channel_manager.providers.exely.security.get_secrets_manager",
        lambda: _SecretsManager(),
    )
    vault_lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "domains.channel_manager.providers.exely.security.get_decrypted_credentials",
        vault_lookup,
    )

    result = await resolve_exely_credentials(
        "synthetic-tenant",
        {"hotel_code": "synthetic-property"},
        actor="offline-test",
    )

    assert result is not None
    assert result["_credential_source"] == "secrets_manager"
    vault_lookup.assert_not_awaited()


def test_http_error_does_not_retain_provider_body():
    response = httpx.Response(400, text="guest@example.test Password=synthetic-provider-password")

    with pytest.raises(ExelyPayloadError) as exc_info:
        ExelySoapTransport._raise_for_http_status(response, 1, "synthetic-correlation")

    rendered = str(exc_info.value)
    assert "guest@example.test" not in rendered
    assert "synthetic-provider-password" not in rendered


@pytest.mark.asyncio
async def test_transport_logs_metadata_not_soap_payload(monkeypatch, caplog):
    async def _safe_post(*args, **kwargs):
        return httpx.Response(200, content=b"<synthetic-response/>")

    monkeypatch.setattr("integrations.xchange.safety.safe_post_async", _safe_post)
    caplog.set_level(logging.DEBUG, logger="exely.client")
    transport = ExelySoapTransport(EXELY_TEST_ENDPOINT_URL)
    xml = '<Security Username="synthetic-user" Password="synthetic-password"/><Guest>guest@example.test</Guest>'

    response = await transport.send_soap(
        xml,
        "https://www.hopenapi.com/Api/PMSConnect/HotelReadReservationRQ",
        correlation_id="synthetic-correlation",
    )

    assert response == b"<synthetic-response/>"
    assert "synthetic-user" not in caplog.text
    assert "synthetic-password" not in caplog.text
    assert "guest@example.test" not in caplog.text
    assert "status_class=2xx" in caplog.text


def test_parse_error_keeps_only_response_hash_and_size():
    raw = "guest@example.test Password=synthetic-provider-password"
    error = ExelyParseError("Invalid XML", raw_response=raw)

    assert error.raw_response == ""
    assert error.response_size_bytes == len(raw.encode())
    assert len(error.response_sha256) == 64
    assert "guest@example.test" not in json.dumps(error.__dict__)
    assert "synthetic-provider-password" not in json.dumps(error.__dict__)


def test_provider_error_description_is_not_exposed_or_logged(caplog):
    caplog.set_level(logging.WARNING, logger="exely.response_parser")
    xml = b"""<soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">
    <soap:Body><OTA_ResRetrieveRS xmlns="http://www.opentravel.org/OTA/2003/05">
    <Errors><Error Code="SYNTHETIC_CODE">guest@example.test Password=synthetic-secret</Error></Errors>
    </OTA_ResRetrieveRS></soap:Body></soap:Envelope>"""

    result = parse_read_rs(xml)
    rendered = json.dumps(result)

    assert result["success"] is False
    assert result["provider_codes"] == ["SYNTHETIC_CODE"]
    assert "guest@example.test" not in rendered + caplog.text
    assert "synthetic-secret" not in rendered + caplog.text


@pytest.mark.asyncio
async def test_webhook_diagnostics_store_metadata_not_raw_payload(monkeypatch):
    collection = _Collection()
    monkeypatch.setattr(exely_webhook_router, "db", _Database(collection))
    payload = b'<Guest email="guest@example.test" Password="synthetic-secret"/>'

    await exely_webhook_router._store_raw_payload(
        tenant_id="synthetic-tenant",
        correlation_id="synthetic-correlation",
        provider="exely",
        external_id="synthetic-reservation-id",
        event_type="reservation_webhook",
        raw_body=payload,
        content_type="text/xml",
    )

    persisted = collection.inserted[0]
    rendered = json.dumps(persisted)
    assert "raw_payload" not in persisted
    assert "external_id" not in persisted
    assert "source_ip" not in persisted
    assert persisted["payload_size_bytes"] == len(payload)
    assert "guest@example.test" not in rendered
    assert "synthetic-secret" not in rendered
    assert "synthetic-reservation-id" not in rendered


@pytest.mark.asyncio
async def test_raw_event_store_minimizes_provider_payload(monkeypatch):
    collection = _Collection()
    monkeypatch.setattr(common_ingest, "db", _Database(collection))
    payload = {
        "reservation_id": "synthetic-reservation-id",
        "guest_name": "Synthetic Guest",
        "guest_email": "guest@example.test",
    }

    await common_ingest.store_raw_event(
        "exely",
        "synthetic-tenant",
        "reservation",
        "synthetic-reservation-id",
        "direct",
        payload,
    )

    persisted = collection.inserted[0]
    rendered = json.dumps(persisted)
    assert "payload" not in persisted
    assert persisted["external_id"] == "synthetic-reservation-id"
    assert persisted["payload_metadata"]["field_names"] == sorted(payload)
    assert "Synthetic Guest" not in rendered
    assert "guest@example.test" not in rendered


@pytest.mark.asyncio
async def test_exely_minimization_does_not_change_other_provider_replay_payload(monkeypatch):
    collection = _Collection()
    monkeypatch.setattr(common_ingest, "db", _Database(collection))
    payload = {"reservation_id": "synthetic-reservation-id"}

    await common_ingest.store_raw_event(
        "hotelrunner",
        "synthetic-tenant",
        "reservation",
        "synthetic-reservation-id",
        "direct",
        payload,
    )

    assert collection.inserted[0]["payload"] == payload


@pytest.mark.asyncio
async def test_outbound_audit_persists_payload_metadata_only():
    collection = _Collection()
    payload = '<Security Username="synthetic-user" Password="synthetic-password"/>'

    await persist_outbound_log(
        _Database(collection),
        connection_id="synthetic-tenant:synthetic-property",
        operation="availability",
        soap_action="OTA_HotelAvailNotifRQ",
        request_payload=payload,
    )

    persisted = collection.inserted[0]
    rendered = json.dumps(persisted)
    assert "connection_id" not in persisted
    assert "request_payload_summary" not in persisted
    assert set(persisted["request_payload_metadata"]) == {"sha256", "size_bytes"}
    assert "synthetic-user" not in rendered
    assert "synthetic-password" not in rendered
    assert "synthetic-tenant" not in rendered


def test_production_unauthenticated_webhook_bypass_is_ignored(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK", "1")

    assert production_webhook_bypass_allowed() is False


def test_production_wins_over_conflicting_test_webhook_environment(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("EXELY_TEST_WEBHOOK_AUTH_MODE", "open_for_testing")
    monkeypatch.setenv("E2E_EXTERNAL_DRY_RUN", "true")
    monkeypatch.setenv("E2E_ALLOW_DESTRUCTIVE_STRESS", "true")
    monkeypatch.setenv("E2E_STRESS_TENANT_ID", "synthetic-stress-tenant")

    assert exely_webhook_router._exely_test_auth_open() is False


def test_exely_query_credentials_are_redacted():
    message = "GET /api/PMSConnect.svc?username=synthetic-user&password=synthetic-password"

    sanitized = sanitize_string(message)

    assert "synthetic-user" not in sanitized
    assert "synthetic-password" not in sanitized
    assert "***REDACTED***" in sanitized


def test_mutation_routes_require_connector_management_permission():
    mutation_functions = (
        "bulk_push_ari",
        "manual_pull",
        "import_reservation_to_pms",
        "start_scheduler",
        "stop_scheduler",
    )
    router_path = Path(__file__).parents[1] / "domains/channel_manager/providers/exely/exely_router.py"
    router_source = router_path.read_text(encoding="utf-8")
    tree = ast.parse(router_source)
    functions = {node.name: ast.get_source_segment(router_source, node) or "" for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    sources = "\n".join(functions[name] for name in mutation_functions)
    assert sources.count('require_op("manage_channel_connectors")') == len(mutation_functions)
    assert 'require_op("view_system_diagnostics")' not in sources
    assert '"raw_payload":' not in inspect.getsource(exely_webhook_router._store_raw_payload)
