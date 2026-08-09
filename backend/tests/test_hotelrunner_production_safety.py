"""Offline production gates for HotelRunner provider access."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from channel_manager.connectors.hotelrunner_v2.auth import HotelRunnerAuth
from channel_manager.connectors.hotelrunner_v2.client import HRv2Client
from channel_manager.connectors.hotelrunner_v2.connector_errors import ConnectorError
from channel_manager.connectors.hotelrunner_v2.errors import (
    HRv2Error,
    HRv2ValidationError,
)
from channel_manager.connectors.hotelrunner_v2.hr_client import HotelRunnerClient
from channel_manager.connectors.hotelrunner_v2.service import HotelRunnerV2Service
from domains.channel_manager.hr_push_queue_worker import HRPushQueueWorker
from domains.channel_manager.providers.hotelrunner.ari_delivery import (
    STATE_BLOCKED,
    deliver_hotelrunner_ari,
)
from domains.channel_manager.providers.hotelrunner.factory import get_provider
from domains.channel_manager.providers.hotelrunner.production_safety import (
    HOTELRUNNER_ARI_WRITE_KILL_SWITCH_ACTIVE,
    HOTELRUNNER_PRODUCTION_DISABLED,
    HOTELRUNNER_RESERVATION_SYNC_DISABLED,
    ari_write_block_reason,
    provider_io_block_reason,
    provider_operation_block_reason,
    reservation_sync_block_reason,
    safe_runtime_state,
)
from domains.channel_manager.providers.hotelrunner.provider import HotelRunnerProvider
from domains.channel_manager.providers.sync_scheduler import ReservationPullScheduler

_ENV_KEYS = (
    "APP_ENV",
    "ENVIRONMENT",
    "NODE_ENV",
    "ENABLE_HOTELRUNNER_PRODUCTION",
    "DISABLE_HOTELRUNNER_RESERVATION_SYNC",
    "DISABLE_HOTELRUNNER_ARI_WRITE",
)


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _provider_without_credentials() -> HotelRunnerProvider:
    provider = object.__new__(HotelRunnerProvider)
    provider._client = SimpleNamespace(get=AsyncMock(), put=AsyncMock())
    provider._connection_id = "synthetic-connection"
    return provider


def _ari_update() -> dict:
    return {
        "inv_code": "synthetic-room",
        "start_date": "2030-01-01",
        "end_date": "2030-01-02",
        "availability": 1,
    }


def test_production_is_default_off_and_snapshot_is_boolean_only(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")

    assert provider_io_block_reason() == HOTELRUNNER_PRODUCTION_DISABLED
    assert reservation_sync_block_reason() == HOTELRUNNER_PRODUCTION_DISABLED
    assert ari_write_block_reason() == HOTELRUNNER_PRODUCTION_DISABLED
    assert safe_runtime_state() == {
        "production_environment": True,
        "production_activation_enabled": False,
        "reservation_sync_allowed": False,
        "ari_write_allowed": False,
    }


def test_explicit_master_keeps_independent_stop_switches(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ENABLE_HOTELRUNNER_PRODUCTION", "true")
    monkeypatch.setenv("DISABLE_HOTELRUNNER_RESERVATION_SYNC", "1")

    assert provider_io_block_reason() == ""
    assert reservation_sync_block_reason() == HOTELRUNNER_RESERVATION_SYNC_DISABLED
    assert ari_write_block_reason() == ""

    monkeypatch.delenv("DISABLE_HOTELRUNNER_RESERVATION_SYNC")
    monkeypatch.setenv("DISABLE_HOTELRUNNER_ARI_WRITE", "yes")
    assert reservation_sync_block_reason() == ""
    assert ari_write_block_reason() == HOTELRUNNER_ARI_WRITE_KILL_SWITCH_ACTIVE


def test_non_production_behavior_is_unchanged(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")

    assert provider_io_block_reason() == ""
    assert reservation_sync_block_reason() == ""
    assert ari_write_block_reason() == ""


def test_operation_classifier_applies_independent_stops(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_HOTELRUNNER_PRODUCTION", "true")
    monkeypatch.setenv("DISABLE_HOTELRUNNER_RESERVATION_SYNC", "true")
    monkeypatch.setenv("DISABLE_HOTELRUNNER_ARI_WRITE", "true")

    assert provider_operation_block_reason("GET", "/api/v2/apps/reservations") == HOTELRUNNER_RESERVATION_SYNC_DISABLED
    assert provider_operation_block_reason("PUT", "/api/v2/apps/reservations/fire") == HOTELRUNNER_RESERVATION_SYNC_DISABLED
    assert provider_operation_block_reason("GET", "/api/v2/apps/rooms") == ""
    assert provider_operation_block_reason("PUT", "/api/v2/apps/rooms/~") == HOTELRUNNER_ARI_WRITE_KILL_SWITCH_ACTIVE


@pytest.mark.asyncio
async def test_v2_compat_client_cannot_bypass_production_gate(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    client = HRv2Client(
        token="synthetic-token",
        hr_id="synthetic-property",
        base_url="https://example.invalid",
    )

    with patch(
        "channel_manager.connectors.hotelrunner_v2.client.httpx.AsyncClient",
    ) as http_client:
        with pytest.raises(HRv2ValidationError) as exc_info:
            await client.get("/api/v2/apps/rooms")

    assert str(exc_info.value) == HOTELRUNNER_PRODUCTION_DISABLED
    http_client.assert_not_called()


@pytest.mark.asyncio
async def test_legacy_compat_client_cannot_bypass_separate_stops(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_HOTELRUNNER_PRODUCTION", "true")
    monkeypatch.setenv("DISABLE_HOTELRUNNER_RESERVATION_SYNC", "true")
    monkeypatch.setenv("DISABLE_HOTELRUNNER_ARI_WRITE", "true")
    client = object.__new__(HotelRunnerClient)
    client._auth = HotelRunnerAuth("synthetic-token", "synthetic-property")
    client._client = SimpleNamespace(get=AsyncMock(), put=AsyncMock(), post=AsyncMock())

    with pytest.raises(ConnectorError) as reservation_error:
        await client._request_json("GET", "/apps/reservations")
    with pytest.raises(ConnectorError) as ari_error:
        await client._request("POST", "/ari/availability")

    assert str(reservation_error.value) == HOTELRUNNER_RESERVATION_SYNC_DISABLED
    assert str(ari_error.value) == HOTELRUNNER_ARI_WRITE_KILL_SWITCH_ACTIVE
    client._client.get.assert_not_awaited()
    client._client.put.assert_not_awaited()
    client._client.post.assert_not_awaited()


@pytest.mark.asyncio
async def test_v2_service_factory_blocks_before_secret_resolution(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")

    with patch("core.secrets.get_secrets_manager") as secrets_manager:
        with pytest.raises(HRv2Error) as exc_info:
            await HotelRunnerV2Service.create("synthetic-tenant", "synthetic-property")

    assert str(exc_info.value) == HOTELRUNNER_PRODUCTION_DISABLED
    secrets_manager.assert_not_called()


@pytest.mark.asyncio
async def test_low_level_read_blocks_before_client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    provider = _provider_without_credentials()

    result = await provider.fetch_rooms()

    assert result.success is False
    assert result.error_type == HOTELRUNNER_PRODUCTION_DISABLED
    assert result.metadata["provider_read_count"] == 0
    provider._client.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_reservation_read_and_ack_block_before_client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_HOTELRUNNER_PRODUCTION", "true")
    monkeypatch.setenv("DISABLE_HOTELRUNNER_RESERVATION_SYNC", "true")
    provider = _provider_without_credentials()

    pull_result = await provider.fetch_reservations()
    ack_result = await provider.confirm_delivery("synthetic-message")

    assert pull_result.error_type == HOTELRUNNER_RESERVATION_SYNC_DISABLED
    assert ack_result.error_type == HOTELRUNNER_RESERVATION_SYNC_DISABLED
    assert ack_result.metadata["provider_write_count"] == 0
    provider._client.get.assert_not_awaited()
    provider._client.put.assert_not_awaited()


@pytest.mark.asyncio
async def test_low_level_ari_write_blocks_before_client(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_HOTELRUNNER_PRODUCTION", "true")
    monkeypatch.setenv("DISABLE_HOTELRUNNER_ARI_WRITE", "true")
    provider = _provider_without_credentials()

    result = await provider.update_room(**_ari_update())

    assert result["success"] is False
    assert result["error_type"] == HOTELRUNNER_ARI_WRITE_KILL_SWITCH_ACTIVE
    assert result["provider_write_count"] == 0
    provider._client.put.assert_not_awaited()


@pytest.mark.asyncio
async def test_ari_delivery_blocks_before_database_and_provider(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    provider = SimpleNamespace(update_room=AsyncMock())

    with patch(
        "domains.channel_manager.providers.hotelrunner.ari_delivery._live_write_enabled",
        new=AsyncMock(),
    ) as live_write_enabled:
        result = await deliver_hotelrunner_ari(
            "synthetic-tenant",
            _ari_update(),
            provider=provider,
        )

    assert result.success is False
    assert result.state == STATE_BLOCKED
    assert result.error_code == HOTELRUNNER_PRODUCTION_DISABLED
    assert result.provider_write_count == 0
    live_write_enabled.assert_not_awaited()
    provider.update_room.assert_not_awaited()


@pytest.mark.asyncio
async def test_factory_blocks_before_database(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")

    with patch(
        "domains.channel_manager.providers.hotelrunner.factory.db.hotelrunner_connections.find_one",
        new=AsyncMock(),
    ) as find_one:
        with pytest.raises(HTTPException) as exc_info:
            await get_provider("synthetic-tenant")

    assert exc_info.value.status_code == 503
    assert exc_info.value.detail == HOTELRUNNER_PRODUCTION_DISABLED
    find_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_reservation_scheduler_blocks_before_task_and_provider(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    scheduler = ReservationPullScheduler()

    started = await scheduler.start()
    result = await scheduler.pull_for_tenant(
        "synthetic-tenant",
        "synthetic-token",
        "synthetic-property",
    )

    assert started is False
    assert scheduler.is_running is False
    assert scheduler._task is None
    assert result == {
        "success": False,
        "error": HOTELRUNNER_PRODUCTION_DISABLED,
        "provider_read_count": 0,
        "provider_write_count": 0,
    }


@pytest.mark.asyncio
async def test_push_worker_blocks_before_task_and_database(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    worker = HRPushQueueWorker()

    with patch(
        "domains.channel_manager.hr_push_queue_worker.db.hr_push_queue.aggregate",
    ) as aggregate:
        started = await worker.start()
        await worker._process_queue()

    assert started is False
    assert worker.is_running is False
    assert worker._task is None
    aggregate.assert_not_called()


def test_feature_flag_registry_contains_hotelrunner_gates():
    from infra.feature_flags import KNOWN_FLAGS

    registry = {name: (kind, default) for name, kind, default in KNOWN_FLAGS}
    assert registry["ENABLE_HOTELRUNNER_PRODUCTION"] == ("enable", False)
    assert registry["DISABLE_HOTELRUNNER_RESERVATION_SYNC"] == ("disable", False)
    assert registry["DISABLE_HOTELRUNNER_ARI_WRITE"] == ("disable", False)


def test_kill_switch_documentation_stays_in_lockstep():
    from pathlib import Path

    registry_doc = (Path(__file__).parents[2] / "docs/KILL_SWITCH_REGISTRY.md").read_text(
        encoding="utf-8",
    )
    for flag in (
        "ENABLE_HOTELRUNNER_PRODUCTION",
        "DISABLE_HOTELRUNNER_RESERVATION_SYNC",
        "DISABLE_HOTELRUNNER_ARI_WRITE",
    ):
        assert flag in registry_doc
