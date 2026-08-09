"""Offline production gates for Exely provider access."""

from unittest.mock import AsyncMock, patch

import pytest

from domains.channel_manager.providers.exely.ari_delivery import deliver_exely_ari
from domains.channel_manager.providers.exely.ari_publish import enqueue_exely_ari_update
from domains.channel_manager.providers.exely.exely_pull_worker import ExelyPullScheduler
from domains.channel_manager.providers.exely.production_safety import (
    EXELY_ARI_WRITE_KILL_SWITCH_ACTIVE,
    EXELY_PRODUCTION_DISABLED,
    EXELY_RESERVATION_SYNC_DISABLED,
    ari_write_block_reason,
    provider_io_block_reason,
    reservation_sync_block_reason,
    safe_runtime_state,
)
from domains.channel_manager.providers.exely.provider import ExelyProvider
from domains.channel_manager.providers.exely.security import EXELY_PRODUCTION_HOST

pytestmark = pytest.mark.exely_failure_stress

_ENV_KEYS = (
    "APP_ENV",
    "ENVIRONMENT",
    "NODE_ENV",
    "ENABLE_EXELY_PRODUCTION",
    "DISABLE_EXELY_RESERVATION_SYNC",
    "DISABLE_EXELY_ARI_WRITE",
)


@pytest.fixture(autouse=True)
def _clean_environment(monkeypatch):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def _update() -> dict:
    return {
        "property_id": "synthetic-property",
        "room_type_code": "synthetic-room",
        "rate_plan_code": "synthetic-rate",
        "start_date": "2030-01-01",
        "end_date": "2030-01-02",
        "value": 1,
        "currency": "USD",
    }


def _production_provider() -> ExelyProvider:
    return ExelyProvider(
        username="synthetic-user",
        password="synthetic-password",
        hotel_code="synthetic-property",
        endpoint_url=f"https://{EXELY_PRODUCTION_HOST}/api/PMSConnect.svc",
        tenant_id="synthetic-tenant",
        property_id="synthetic-property",
        quota_guard=AsyncMock(),
        max_retries=0,
    )


def test_production_is_default_off_and_safe_snapshot_has_booleans_only(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")

    assert provider_io_block_reason() == EXELY_PRODUCTION_DISABLED
    assert reservation_sync_block_reason() == EXELY_PRODUCTION_DISABLED
    assert ari_write_block_reason() == EXELY_PRODUCTION_DISABLED
    assert safe_runtime_state() == {
        "production_environment": True,
        "production_activation_enabled": False,
        "reservation_sync_allowed": False,
        "ari_write_allowed": False,
    }


def test_explicit_production_enable_keeps_independent_kill_switches(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ENABLE_EXELY_PRODUCTION", "true")
    monkeypatch.setenv("DISABLE_EXELY_RESERVATION_SYNC", "1")

    assert provider_io_block_reason() == ""
    assert reservation_sync_block_reason() == EXELY_RESERVATION_SYNC_DISABLED
    assert ari_write_block_reason() == ""

    monkeypatch.delenv("DISABLE_EXELY_RESERVATION_SYNC")
    monkeypatch.setenv("DISABLE_EXELY_ARI_WRITE", "yes")
    assert reservation_sync_block_reason() == ""
    assert ari_write_block_reason() == EXELY_ARI_WRITE_KILL_SWITCH_ACTIVE


def test_non_production_pilot_behavior_is_unchanged(monkeypatch):
    monkeypatch.setenv("APP_ENV", "test")

    assert provider_io_block_reason() == ""
    assert reservation_sync_block_reason() == ""
    assert ari_write_block_reason() == ""


@pytest.mark.asyncio
async def test_production_ari_delivery_blocks_before_db_and_provider(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    provider = AsyncMock()

    with patch(
        "domains.channel_manager.providers.exely.ari_delivery._prepare_delivery",
        new=AsyncMock(),
    ) as prepare:
        result = await deliver_exely_ari(
            "synthetic-tenant",
            "availability",
            _update(),
            provider=provider,
            write_enabled=True,
        )

    assert result.success is False
    assert result.error_code == EXELY_PRODUCTION_DISABLED
    assert result.provider_write_count == 0
    prepare.assert_not_awaited()
    provider.push_ari_operation.assert_not_awaited()


@pytest.mark.asyncio
async def test_ari_kill_switch_prevents_outbox_enqueue(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_EXELY_PRODUCTION", "true")
    monkeypatch.setenv("DISABLE_EXELY_ARI_WRITE", "true")

    with patch(
        "domains.channel_manager.providers.exely.ari_publish.publish_ari_event",
        new=AsyncMock(),
    ) as publish:
        result = await enqueue_exely_ari_update(
            "synthetic-tenant",
            "synthetic-property",
            "synthetic-room",
            "synthetic-rate",
            "2030-01-01",
            "2030-01-02",
            source_service="offline-test",
            availability=1,
        )

    assert result == {
        "accepted": False,
        "delivery_state": "blocked",
        "queued_operation_count": 0,
        "provider_write_count": 0,
        "error_code": EXELY_ARI_WRITE_KILL_SWITCH_ACTIVE,
    }
    publish.assert_not_awaited()


@pytest.mark.asyncio
async def test_low_level_provider_read_cannot_bypass_production_gate(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    provider = _production_provider()
    provider._transport.send_soap = AsyncMock()

    result = await provider.pull_reservations()

    assert result.success is False
    assert result.metadata["provider_write_count"] == 0
    provider._transport.send_soap.assert_not_awaited()


@pytest.mark.asyncio
async def test_low_level_provider_mutations_cannot_bypass_kill_switch(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_EXELY_PRODUCTION", "true")
    monkeypatch.setenv("DISABLE_EXELY_ARI_WRITE", "true")
    provider = _production_provider()
    provider._transport.send_soap = AsyncMock()

    result = await provider.push_ari_operation(
        operation="availability",
        room_type_code="synthetic-room",
        rate_plan_code="synthetic-rate",
        start_date="2030-01-01",
        end_date="2030-01-02",
        value=1,
        currency="USD",
    )

    assert result.success is False
    assert result.error_type == EXELY_ARI_WRITE_KILL_SWITCH_ACTIVE
    assert result.metadata["provider_write_count"] == 0
    provider._transport.send_soap.assert_not_awaited()


@pytest.mark.asyncio
async def test_low_level_ack_cannot_bypass_reservation_kill_switch(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("ENABLE_EXELY_PRODUCTION", "true")
    monkeypatch.setenv("DISABLE_EXELY_RESERVATION_SYNC", "true")
    provider = _production_provider()
    provider._transport.send_soap = AsyncMock()

    result = await provider.confirm_delivery(
        "synthetic-reservation",
        "synthetic-confirmation",
        create_datetime="2030-01-01T00:00:00Z",
        last_modify_datetime="2030-01-01T00:00:00Z",
    )

    assert result.success is False
    assert result.error_type == EXELY_RESERVATION_SYNC_DISABLED
    assert result.metadata["provider_write_count"] == 0
    provider._transport.send_soap.assert_not_awaited()


@pytest.mark.asyncio
async def test_reservation_scheduler_blocks_before_task_or_database(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    scheduler = ExelyPullScheduler()

    started = await scheduler.start()

    assert started is False
    assert scheduler.is_running is False
    assert scheduler._task is None


@pytest.mark.asyncio
async def test_direct_tenant_pull_blocks_before_provider_construction(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    scheduler = ExelyPullScheduler()

    with patch(
        "domains.channel_manager.providers.exely.exely_pull_worker.ExelyProvider",
    ) as provider_class:
        result = await scheduler.pull_for_tenant(
            tenant_id="synthetic-tenant",
            username="synthetic-user",
            password="synthetic-password",
            hotel_code="synthetic-property",
        )

    assert result == {
        "success": False,
        "error": EXELY_PRODUCTION_DISABLED,
        "provider_read_count": 0,
        "provider_write_count": 0,
    }
    provider_class.assert_not_called()


def test_feature_flag_registry_contains_all_exely_production_gates():
    from infra.feature_flags import KNOWN_FLAGS

    registry = {name: (kind, default) for name, kind, default in KNOWN_FLAGS}
    assert registry["ENABLE_EXELY_PRODUCTION"] == ("enable", False)
    assert registry["DISABLE_EXELY_RESERVATION_SYNC"] == ("disable", False)
    assert registry["DISABLE_EXELY_ARI_WRITE"] == ("disable", False)


def test_kill_switch_documentation_stays_in_lockstep():
    from pathlib import Path

    registry_doc = (Path(__file__).parents[2] / "docs/KILL_SWITCH_REGISTRY.md").read_text(
        encoding="utf-8",
    )
    for flag in (
        "ENABLE_EXELY_PRODUCTION",
        "DISABLE_EXELY_RESERVATION_SYNC",
        "DISABLE_EXELY_ARI_WRITE",
    ):
        assert flag in registry_doc
