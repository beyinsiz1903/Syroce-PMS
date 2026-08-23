import asyncio
import logging

import pytest

from infra.horizontal_scaling import HorizontalScalingManager
from infra.redis_capacity import classify_redis_failure, redis_memory_capacity
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


@pytest.mark.asyncio
async def test_heartbeat_continuing_outage_escalates_only_once_until_recovery(monkeypatch, caplog):
    caplog.set_level(logging.INFO)
    manager = HorizontalScalingManager()
    manager._heartbeat_interval = 0

    class _RecoveringRedis:
        calls = 0

        async def hset(self, *args, **kwargs):
            self.calls += 1
            if self.calls <= 12 or self.calls >= 14:
                raise RuntimeError("unable to perform operation on <TCPTransport closed=True>")

    manager._redis = _RecoveringRedis()
    sleep_calls = 0

    async def _sleep(_delay):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls >= 17:
            raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", _sleep)

    await manager._heartbeat_loop()

    escalations = [
        record
        for record in caplog.records
        if record.levelname == "ERROR" and "Heartbeat failed repeatedly" in record.message
    ]
    assert len(escalations) == 2
    assert "Heartbeat recovered after 12 consecutive failures" in caplog.text
    assert "failure_class=REDIS_CONNECTION" in caplog.text


@pytest.mark.asyncio
async def test_maxmemory_heartbeat_fails_readiness_without_logging_raw_error(monkeypatch, caplog):
    manager = HorizontalScalingManager()
    manager._heartbeat_interval = 0

    class _FullRedis:
        async def hset(self, *args, **kwargs):
            raise RuntimeError("command not allowed when used memory > 'maxmemory'; private-marker")

        async def hgetall(self, *args, **kwargs):
            return {}

    manager._redis = _FullRedis()
    sleep_calls = 0

    async def _sleep(_delay):
        nonlocal sleep_calls
        sleep_calls += 1
        if sleep_calls >= 4:
            raise asyncio.CancelledError

    monkeypatch.setattr(asyncio, "sleep", _sleep)

    await manager._heartbeat_loop()

    assert manager.readiness_check()["ready"] is False
    assert manager.readiness_check()["heartbeat"]["failure_class"] == "REDIS_MAXMEMORY"
    assert "failure_class=REDIS_MAXMEMORY" in caplog.text
    assert "private-marker" not in caplog.text


@pytest.mark.asyncio
async def test_initial_registration_failure_keeps_recovery_loop_running():
    manager = HorizontalScalingManager()

    class _FullRedis:
        async def hset(self, *args, **kwargs):
            raise RuntimeError("OOM command not allowed when used memory > 'maxmemory'")

        async def hgetall(self, *args, **kwargs):
            return {}

    await manager.initialize(_FullRedis())

    try:
        assert manager._heartbeat_task is not None
        assert manager._heartbeat_task.done() is False
        assert manager._heartbeat_failures == 1
    finally:
        await manager.deregister()


@pytest.mark.asyncio
async def test_registry_prune_removes_stale_and_malformed_instances():
    manager = HorizontalScalingManager()

    class _Redis:
        deleted = []

        async def hgetall(self, *args, **kwargs):
            return {
                "stale": '{"last_heartbeat":"2000-01-01T00:00:00+00:00"}',
                "malformed": "not-json",
            }

        async def hdel(self, _key, *instance_ids):
            self.deleted.extend(instance_ids)

    manager._redis = _Redis()

    await manager._prune_stale_instances()

    assert set(manager._redis.deleted) == {"stale", "malformed"}


@pytest.mark.asyncio
async def test_redis_cluster_health_fails_when_write_capacity_is_exhausted():
    manager = RedisClusterManager()

    class _Redis:
        async def ping(self):
            return True

        async def info(self, *args):
            return {
                "used_memory": 256,
                "maxmemory": 256,
                "maxmemory_policy": "noeviction",
            }

    manager._redis = _Redis()
    manager._connected = True

    result = await manager.health_check()

    assert result["status"] == "unhealthy"
    assert result["memory_capacity"]["state"] == "exhausted"


def test_redis_capacity_and_failure_contracts():
    assert classify_redis_failure(RuntimeError("OOM command not allowed when used memory > 'maxmemory'")) == "REDIS_MAXMEMORY"
    assert classify_redis_failure(RuntimeError("unable to perform operation on <TCPTransport closed=True>")) == "REDIS_CONNECTION"
    assert classify_redis_failure(RuntimeError("command not allowed for this role")) == "REDIS_COMMAND_DENIED"
    assert redis_memory_capacity({"used_memory": 100, "maxmemory": 100, "maxmemory_policy": "noeviction"}) == {
        "state": "exhausted",
        "used_memory_bytes": 100,
        "maxmemory_bytes": 100,
        "usage_ratio": 1.0,
        "policy": "noeviction",
    }
