"""Fail-closed contracts for HotelRunner reservation mutations."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import HTTPException

from domains.channel_manager.providers.hotelrunner import provider as provider_module
from domains.channel_manager.providers.hotelrunner import router_sync
from domains.channel_manager.providers.hotelrunner.client import HttpResult
from domains.channel_manager.providers.hotelrunner.errors import (
    HotelRunnerParseError,
    HotelRunnerPayloadError,
    HotelRunnerTemporaryError,
)
from domains.channel_manager.providers.hotelrunner.provider import HotelRunnerProvider
from domains.channel_manager.providers.hotelrunner.schemas import ProviderResult


def _provider(result=None, error: Exception | None = None) -> HotelRunnerProvider:
    provider = object.__new__(HotelRunnerProvider)
    provider._connection_id = "synthetic-connection"
    provider._client = SimpleNamespace(
        put=AsyncMock(return_value=result, side_effect=error),
    )
    provider._retry = SimpleNamespace(execute=AsyncMock())
    return provider


@pytest.mark.asyncio
async def test_ack_success_is_single_attempt_with_valid_telemetry(monkeypatch):
    provider = _provider(HttpResult(success=True, status_code=200, data={"status": "ok"}))
    record = Mock()
    monkeypatch.setattr(provider_module.obs, "record_provider_call", record)

    result = await provider.confirm_delivery("synthetic-message")

    assert result.success is True
    assert result.metadata == {
        "provider_write_count": 1,
        "retry_count": 0,
        "provider_status_class": "SUCCESS",
        "delivery_state": "CONFIRMED",
        "http_status": 200,
        "retryable": False,
    }
    provider._client.put.assert_awaited_once()
    provider._retry.execute.assert_not_awaited()
    assert record.call_args.kwargs["connection_id"] == "synthetic-connection"
    assert "tenant_id" not in record.call_args.kwargs


@pytest.mark.asyncio
async def test_telemetry_failure_does_not_flip_confirmed_provider_result(monkeypatch):
    provider = _provider(HttpResult(success=True, status_code=200, data={"status": "ok"}))
    monkeypatch.setattr(
        provider_module.obs,
        "record_provider_call",
        Mock(side_effect=TypeError("synthetic telemetry failure")),
    )

    result = await provider.confirm_delivery("synthetic-message")

    assert result.success is True
    assert result.metadata["delivery_state"] == "CONFIRMED"
    assert provider._client.put.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "error",
    [
        HotelRunnerTemporaryError("synthetic timeout"),
        HotelRunnerParseError("synthetic parse failure", raw_response="sensitive-provider-body"),
    ],
    ids=["timeout-or-5xx", "parse-failure"],
)
async def test_ambiguous_ack_failure_is_never_retried(monkeypatch, caplog, error):
    provider = _provider(error=error)
    monkeypatch.setattr(provider_module.obs, "record_provider_failure", Mock())

    result = await provider.confirm_delivery("synthetic-message")

    assert result.success is False
    assert result.error == "HOTELRUNNER_WRITE_OUTCOME_UNKNOWN"
    assert result.metadata["provider_status_class"] == "WRITE_OUTCOME_UNKNOWN"
    assert result.metadata["delivery_state"] == "AMBIGUOUS"
    assert result.metadata["provider_write_count"] == 1
    assert result.metadata["retry_count"] == 0
    assert result.metadata["retryable"] is False
    assert provider._client.put.await_count == 1
    provider._retry.execute.assert_not_awaited()
    assert "sensitive-provider-body" not in caplog.text


@pytest.mark.asyncio
async def test_definitive_ack_rejection_is_not_ambiguous_or_retried(monkeypatch):
    provider = _provider(error=HotelRunnerPayloadError("synthetic validation"))
    monkeypatch.setattr(provider_module.obs, "record_provider_failure", Mock())

    result = await provider.confirm_delivery("synthetic-message")

    assert result.success is False
    assert result.error == "HOTELRUNNER_WRITE_REJECTED"
    assert result.metadata["provider_status_class"] == "REJECTED"
    assert result.metadata["delivery_state"] == "REJECTED"
    assert result.metadata["provider_write_count"] == 1
    assert provider._client.put.await_count == 1
    provider._retry.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_state_mutation_is_single_attempt(monkeypatch):
    provider = _provider(HttpResult(success=True, status_code=200, data={"status": "ok"}))
    monkeypatch.setattr(provider_module.obs, "record_provider_call", Mock())

    result = await provider.update_reservation_state(
        "synthetic-message",
        "cancel",
        "customer",
    )

    assert result.success is True
    assert result.metadata["provider_write_count"] == 1
    assert result.metadata["retry_count"] == 0
    assert provider._client.put.await_count == 1
    assert provider._client.put.await_args.kwargs["params"] == {
        "message_uid": "synthetic-message",
        "event": "cancel",
        "cancel_reason": "customer",
    }
    provider._retry.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_compat_ack_failure_returns_safe_502_without_durable_confirmation(monkeypatch):
    provider = SimpleNamespace(
        confirm_delivery=AsyncMock(
            return_value=ProviderResult(
                success=False,
                error="sensitive-provider-message",
                error_type="HotelRunnerTemporaryError",
                metadata={"delivery_state": "AMBIGUOUS"},
            )
        )
    )
    database = SimpleNamespace(
        hotelrunner_reservations=SimpleNamespace(
            find_one=AsyncMock(return_value={"message_uid": "synthetic-message"}),
            update_one=AsyncMock(),
        )
    )
    monkeypatch.setattr(router_sync, "get_provider", AsyncMock(return_value=(provider, {})))
    monkeypatch.setattr(router_sync, "db", database)

    with pytest.raises(HTTPException) as exc_info:
        await router_sync.confirm_reservation_delivery(
            "synthetic-reservation",
            current_user=SimpleNamespace(tenant_id="synthetic-tenant"),
            _perm=None,
        )

    assert exc_info.value.status_code == 502
    assert exc_info.value.detail == {
        "code": "HOTELRUNNER_ACK_FAILED",
        "error_type": "HotelRunnerTemporaryError",
        "delivery_state": "AMBIGUOUS",
    }
    assert "sensitive-provider-message" not in str(exc_info.value.detail)
    provider.confirm_delivery.assert_awaited_once()
    database.hotelrunner_reservations.update_one.assert_not_awaited()
