import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from core.integrations.nilvera.client import NilveraHttpClient
from core.integrations.nilvera.config import (
    NilveraEndpoints,
    is_nilvera_create_return_enabled,
)
from core.integrations.nilvera.errors import (
    NilveraMalformedResponseError,
    NilveraTimeoutError,
)
from core.integrations.nilvera.return_adapter import NilveraReturnAdapter


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        ("false", False),
        ("invalid", False),
        (" true ", True),
    ],
)
def test_create_return_feature_gate_is_fail_closed(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("NILVERA_CREATE_RETURN_ENABLED", raising=False)
    else:
        monkeypatch.setenv("NILVERA_CREATE_RETURN_ENABLED", value)

    assert is_nilvera_create_return_enabled() is expected


@pytest.mark.asyncio
async def test_create_return_disabled_does_not_access_provider(monkeypatch):
    monkeypatch.delenv("NILVERA_CREATE_RETURN_ENABLED", raising=False)
    client = SimpleNamespace(post=AsyncMock(), last_http_status=None)

    with pytest.raises(RuntimeError, match="NILVERA_CREATE_RETURN_DISABLED"):
        await NilveraReturnAdapter(client).create_return(str(uuid.uuid4()))

    client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_return_rejects_invalid_uuid_before_provider_access(monkeypatch):
    monkeypatch.setenv("NILVERA_CREATE_RETURN_ENABLED", "true")
    client = SimpleNamespace(post=AsyncMock(), last_http_status=None)

    with pytest.raises(ValueError, match="INVALID_SOURCE_PROVIDER_UUID"):
        await NilveraReturnAdapter(client).create_return("not-an-identifier")

    client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_return_posts_once_without_a_body_or_retry(monkeypatch):
    monkeypatch.setenv("NILVERA_CREATE_RETURN_ENABLED", "true")
    source_uuid = str(uuid.uuid4())
    created_uuid = str(uuid.uuid4())
    client = SimpleNamespace(
        post=AsyncMock(return_value={"UUID": created_uuid, "InvoiceNumber": "SAFE-CONTRACT-VALUE"}),
        last_http_status=200,
    )

    response = await NilveraReturnAdapter(client).create_return(
        source_uuid,
        correlation_id="safe-correlation",
    )

    assert str(response.provider_uuid) == created_uuid
    client.post.assert_awaited_once_with(
        NilveraEndpoints.CREATE_PURCHASE_RETURN.format(uuid=source_uuid),
        correlation_id="safe-correlation",
        retryable=False,
        stage="CREATE_RETURN",
    )
    assert "json" not in client.post.await_args.kwargs


@pytest.mark.asyncio
async def test_create_return_timeout_is_not_retried(monkeypatch):
    monkeypatch.setenv("NILVERA_CREATE_RETURN_ENABLED", "true")
    client = SimpleNamespace(
        post=AsyncMock(side_effect=NilveraTimeoutError("safe timeout")),
        last_http_status=None,
    )

    with pytest.raises(NilveraTimeoutError):
        await NilveraReturnAdapter(client).create_return(str(uuid.uuid4()))

    assert client.post.await_count == 1


@pytest.mark.asyncio
async def test_create_return_response_requires_provider_uuid(monkeypatch):
    monkeypatch.setenv("NILVERA_CREATE_RETURN_ENABLED", "true")
    client = SimpleNamespace(
        post=AsyncMock(return_value={"InvoiceNumber": "SAFE-CONTRACT-VALUE"}),
        last_http_status=200,
    )

    with pytest.raises(NilveraMalformedResponseError):
        await NilveraReturnAdapter(client).create_return(str(uuid.uuid4()))

    assert client.post.await_count == 1


@pytest.mark.asyncio
async def test_http_client_omits_body_and_content_type_for_bodyless_post(monkeypatch):
    monkeypatch.setenv("NILVERA_ENABLED", "true")
    monkeypatch.setenv("NILVERA_ENV", "test")
    import core.integrations.nilvera.config

    core.integrations.nilvera.config._config = None
    observed: dict[str, object] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        observed["content"] = request.content
        observed["content_type"] = request.headers.get("Content-Type")
        return httpx.Response(
            200,
            json={"UUID": str(uuid.uuid4())},
            request=request,
        )

    async with httpx.AsyncClient(
        base_url="https://apitest.nilvera.com",
        transport=httpx.MockTransport(handler),
    ) as raw_client:
        client = NilveraHttpClient("sandbox-key", client=raw_client)
        await client.post("/bodyless")

    assert observed == {"content": b"", "content_type": None}


def test_create_return_discovery_does_not_emit_raw_identifiers_or_payloads():
    sandbox_test = (Path(__file__).parents[1] / "integration/test_nilvera_sandbox_e2e.py").read_text()
    start = sandbox_test.index("async def test_sandbox_create_return_contract_discovery")
    end = sandbox_test.index("async def test_sandbox_incoming_commercial_invoice_answer_contract")
    discovery = sandbox_test[start:end]

    assert 'record_property("source_provider_uuid"' not in discovery
    assert 'record_property("created_uuid"' not in discovery
    assert 'record_property("invoice_number"' not in discovery
    assert "str(exc)" not in discovery
    assert "print(" not in discovery
