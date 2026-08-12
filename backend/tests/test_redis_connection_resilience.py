import asyncio

import pytest

from infra.horizontal_scaling import HorizontalScalingManager
from infra.redis_cluster import RedisClusterManager


def test_managed_redis_client_kwargs_enable_keepalive_health_checks_and_timeout_retry():
    kwargs = RedisClusterManager._client_kwargs(socket_timeout=30, max_connections=42)

    assert kwargs["decode_responses"] is True
    assert kwargs["socket_connect_timeout"] == 5
    assert kwargs["socket_timeout"] == 30
    assert kwargs["retry_on_timeout"] is True
    assert kwargs["health_check_interval"] == 15
    assert kwargs["socket_keepalive"] is True
    assert kwargs["max_connections"] == 42


@pytest.mark.asyncio
async def test_heartbeat_transient_disconnects_warn_before_escalating(monkeypatch, caplog):
    manager = HorizontalScalingManager()
    manager._heartbeat_interval = 0

    class _FlakyRedis:
        async def hset(self, *args, **kwargs):
            raise ConnectionError("connection closed by server")

    manager._redis = _FlakyRedis()

    sleep_calls = 0

    async def _sleep(_delay):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls >= 3:
            raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", _sleep)

    await manager._heartbeat_loop()

    assert manager._heartbeat_failures == 2
    assert "Heartbeat transient failure (1/3)" in caplog.text
    assert "Heartbeat transient failure (2/3)" in caplog.text
    assert "Heartbeat failed repeatedly" not in caplog.text


@pytest.mark.asyncio
async def test_heartbeat_persistent_disconnect_escalates_after_threshold(monkeypatch, caplog):
    manager = HorizontalScalingManager()
    manager._heartbeat_interval = 0

    class _BrokenRedis:
        async def hset(self, *args, **kwargs):
            raise ConnectionError("connection closed by server")

    manager._redis = _BrokenRedis()

    sleep_calls = 0

    async def _sleep(_delay):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls >= 4:
            raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", _sleep)

    await manager._heartbeat_loop()

    assert manager._heartbeat_failures == 3
    assert "Heartbeat failed repeatedly (3 consecutive)" in caplog.text
