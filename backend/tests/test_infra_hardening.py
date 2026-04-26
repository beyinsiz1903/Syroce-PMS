"""
Infrastructure Hardening Test Suite.
Tests all new infrastructure components: Redis cluster, distributed locks,
worker queues, secrets manager, backup manager, cloud observability,
horizontal scaling, and WebSocket adapter.
"""
import pytest
import os
from datetime import datetime, timezone


# ── Redis Cluster Manager Tests ────────────────────────────────────

class TestRedisClusterManager:
    def test_init_defaults(self):
        from infra.redis_cluster import RedisClusterManager
        mgr = RedisClusterManager()
        assert mgr.mode == "standalone"
        assert mgr.connected is False

    @pytest.mark.asyncio
    async def test_connect_no_url(self):
        from infra.redis_cluster import RedisClusterManager
        mgr = RedisClusterManager()
        mgr._url = ""
        result = await mgr.connect()
        assert result is False
        assert mgr.connected is False

    @pytest.mark.asyncio
    async def test_health_check_disconnected(self):
        from infra.redis_cluster import RedisClusterManager
        mgr = RedisClusterManager()
        health = await mgr.health_check()
        assert health["status"] == "disconnected"
        assert health["mode"] == "standalone"

    def test_get_metrics(self):
        from infra.redis_cluster import RedisClusterManager
        mgr = RedisClusterManager()
        metrics = mgr.get_metrics()
        assert "mode" in metrics
        assert "connected" in metrics
        assert metrics["connections_created"] == 0

    def test_sentinel_host_parsing(self):
        from infra.redis_cluster import RedisClusterManager
        mgr = RedisClusterManager()
        mgr._url = "sentinel://host1:26379,host2:26379"
        hosts = mgr._parse_sentinel_hosts()
        assert len(hosts) == 2
        assert hosts[0] == ("host1", 26379)


# ── Distributed Lock Tests ─────────────────────────────────────────

class TestDistributedLockManager:
    def test_init(self):
        from infra.distributed_lock import DistributedLockManager
        mgr = DistributedLockManager()
        assert mgr._redis is None
        assert mgr.get_metrics()["locks_acquired"] == 0

    @pytest.mark.asyncio
    async def test_fallback_lock(self):
        from infra.distributed_lock import DistributedLockManager
        mgr = DistributedLockManager()
        # No Redis → should use fallback
        async with mgr.lock("test-lock"):
            metrics = mgr.get_metrics()
            assert metrics["fallback_used"] >= 1
            assert metrics["locks_acquired"] >= 1

    def test_metrics_structure(self):
        from infra.distributed_lock import DistributedLockManager
        mgr = DistributedLockManager()
        metrics = mgr.get_metrics()
        assert "locks_acquired" in metrics
        assert "locks_released" in metrics
        assert "locks_failed" in metrics
        assert "active_lock_names" in metrics


# ── Worker Queue Manager Tests ─────────────────────────────────────

class TestWorkerQueueManager:
    def test_queue_definitions(self):
        from infra.worker_queue import QUEUE_DEFINITIONS
        assert "default" in QUEUE_DEFINITIONS
        assert "ml" in QUEUE_DEFINITIONS
        assert "messaging" in QUEUE_DEFINITIONS
        assert "backup" in QUEUE_DEFINITIONS

    def test_task_routes(self):
        from infra.worker_queue import TASK_ROUTES
        assert "celery_tasks.ml_training_task" in TASK_ROUTES
        assert TASK_ROUTES["celery_tasks.ml_training_task"]["queue"] == "ml"

    def test_record_and_summary(self):
        from infra.worker_queue import WorkerQueueManager
        mgr = WorkerQueueManager()
        mgr.record_task_start("test_task", "id1", "default")
        mgr.record_task_complete("test_task", "id1", "default", 1.5)
        summary = mgr.get_worker_summary()
        assert summary["total_submitted"] >= 1
        assert summary["total_completed"] >= 1

    def test_failure_archive(self):
        from infra.worker_queue import WorkerQueueManager
        mgr = WorkerQueueManager()
        mgr.record_task_failure("fail_task", "id2", "ml", "some error", retries=2)
        failures = mgr.get_failure_archive()
        assert len(failures) >= 1
        assert failures[-1]["error"] == "some error"

    def test_stuck_candidates(self):
        from infra.worker_queue import WorkerQueueManager
        from datetime import timedelta
        mgr = WorkerQueueManager()
        mgr.record_task_start("stuck_task", "id3", "default")
        # Manually backdate the started_at
        for entry in mgr._task_history:
            if entry["task_id"] == "id3":
                old_time = datetime.now(timezone.utc) - timedelta(seconds=600)
                entry["started_at"] = old_time.isoformat()
        stuck = mgr.get_stuck_task_candidates(timeout_sec=300)
        assert len(stuck) >= 1


# ── Secrets Manager Tests ──────────────────────────────────────────

class TestSecretsManager:
    @pytest.mark.asyncio
    async def test_env_provider(self):
        from infra.secrets_manager import SecretsManager
        os.environ["TEST_SECRET_KEY"] = "test_value"
        mgr = SecretsManager()
        val = await mgr.get_secret("TEST_SECRET_KEY")
        assert val == "test_value"
        del os.environ["TEST_SECRET_KEY"]

    @pytest.mark.asyncio
    async def test_health_check_env(self):
        from infra.secrets_manager import SecretsManager
        mgr = SecretsManager()
        health = await mgr.health_check()
        assert health["provider"] == "env"
        assert health["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_access_logging(self):
        from infra.secrets_manager import SecretsManager
        mgr = SecretsManager()
        await mgr.get_secret("SOME_KEY", requester="test")
        log = mgr.get_access_log()
        assert len(log) >= 1
        assert "***" in log[-1]["key"]  # Masked

    def test_metrics(self):
        from infra.secrets_manager import SecretsManager
        mgr = SecretsManager()
        metrics = mgr.get_metrics()
        assert metrics["provider"] == "env"
        assert "total_requests" in metrics


# ── Backup Manager Tests ───────────────────────────────────────────

class TestBackupManager:
    def test_init(self):
        from infra.backup_manager import BackupManager
        mgr = BackupManager()
        assert mgr._enabled is False
        assert mgr._retention_days == 30

    def test_status(self):
        from infra.backup_manager import BackupManager
        mgr = BackupManager()
        status = mgr.get_status()
        assert "enabled" in status
        assert "rpo_target" in status
        assert "critical_collections" in status
        assert len(status["critical_collections"]) > 0

    def test_history_empty(self):
        from infra.backup_manager import BackupManager
        mgr = BackupManager()
        history = mgr.get_history()
        assert isinstance(history, list)

    @pytest.mark.asyncio
    async def test_create_backup_simulated(self):
        from infra.backup_manager import BackupManager
        mgr = BackupManager()
        mgr._mongo_url = "mongodb://localhost:27017/test"
        mgr._db_name = "test"
        result = await mgr.create_backup("test")
        assert result["backup_type"] == "test"
        # Either simulated (no mongodump) or completed
        assert result["status"] in ("simulated", "completed", "failed")


# ── Cloud Observability Tests ──────────────────────────────────────

class TestCloudObservability:
    def test_otel_status_disabled(self):
        from infra.cloud_observability import OTelTracer
        tracer = OTelTracer()
        status = tracer.get_status()
        assert status["active"] is False
        assert "not configured" in status["endpoint"]

    def test_noop_span(self):
        from infra.cloud_observability import OTelTracer
        tracer = OTelTracer()
        span = tracer.start_span("test")
        span.set_attribute("key", "value")
        span.end()
        assert tracer.get_status()["spans_created"] == 1

    def test_sentry_disabled(self):
        from infra.cloud_observability import SentryIntegration
        sentry = SentryIntegration()
        status = sentry.get_status()
        assert status["active"] is False
        assert status["dsn_configured"] is False

    def test_cloud_metrics(self):
        from infra.cloud_observability import CloudMetricsCollector
        metrics = CloudMetricsCollector()
        metrics.record_latency("api.test", 0.05)
        metrics.record_latency("api.test", 0.15)
        metrics.increment("requests")
        metrics.set_gauge("active_conns", 42)
        summary = metrics.get_summary()
        assert "api.test" in summary["latency"]
        assert summary["counters"]["requests"] == 1
        assert summary["gauges"]["active_conns"] == 42

    def test_percentile(self):
        from infra.cloud_observability import CloudMetricsCollector
        metrics = CloudMetricsCollector()
        for i in range(100):
            metrics.record_latency("perf", i * 0.01)
        p95 = metrics.get_percentile("perf", 0.95)
        assert p95 > 0


# ── Horizontal Scaling Tests ───────────────────────────────────────

class TestHorizontalScaling:
    def test_init(self):
        from infra.horizontal_scaling import HorizontalScalingManager
        mgr = HorizontalScalingManager()
        assert mgr.scaling_mode == "single"
        assert mgr.instance_id is not None

    def test_stateless_validation(self):
        from infra.horizontal_scaling import HorizontalScalingManager
        mgr = HorizontalScalingManager()
        result = mgr.stateless_validation()
        assert "ready_for_scaling" in result
        assert "checks" in result
        assert result["checks"]["env_based_config"] is True

    def test_readiness_check(self):
        from infra.horizontal_scaling import HorizontalScalingManager
        mgr = HorizontalScalingManager()
        result = mgr.readiness_check()
        assert result["ready"] is True
        assert "instance_id" in result

    @pytest.mark.asyncio
    async def test_get_active_instances_no_redis(self):
        from infra.horizontal_scaling import HorizontalScalingManager
        mgr = HorizontalScalingManager()
        instances = await mgr.get_active_instances()
        assert len(instances) == 1
        assert instances[0]["service_type"] == "backend"


# ── WebSocket Redis Adapter Tests ──────────────────────────────────

class TestWSRedisAdapter:
    def test_init(self):
        from infra.ws_redis_adapter import WebSocketRedisAdapter
        adapter = WebSocketRedisAdapter()
        assert adapter._active is False
        assert adapter.get_metrics()["messages_published"] == 0

    @pytest.mark.asyncio
    async def test_publish_local_fallback(self):
        from infra.ws_redis_adapter import WebSocketRedisAdapter
        adapter = WebSocketRedisAdapter()
        received = []
        async def handler(room, event, data):
            received.append((room, event, data))
        adapter._local_handler = handler
        await adapter.publish("dashboard", "update", {"test": True})
        assert len(received) == 1
        assert received[0][0] == "dashboard"

    def test_metrics_structure(self):
        from infra.ws_redis_adapter import WebSocketRedisAdapter
        adapter = WebSocketRedisAdapter()
        metrics = adapter.get_metrics()
        assert "messages_published" in metrics
        assert "messages_received" in metrics
        assert "active" in metrics

    @pytest.mark.asyncio
    async def test_publish_delivers_locally_when_redis_unavailable(self):
        """Regression: when Redis is not connected (single-instance mode),
        publish() must still fan out to local clients via the local
        handler — otherwise `broadcast_internal_message_read` and the
        `internal_typing` relay would silently no-op in fallback mode."""
        from infra.ws_redis_adapter import WebSocketRedisAdapter

        adapter = WebSocketRedisAdapter()
        # Mirror the startup path that hands the adapter no Redis client
        # but always wires the local handler.
        received = []

        async def handler(room, event, data):
            received.append((room, event, data))

        await adapter.initialize(None, "single-instance", local_handler=handler)
        assert adapter._active is False  # Redis disabled

        await adapter.publish("pms", "internal_message_read", {"reader_id": "u1"})
        await adapter.publish("pms", "internal_user_typing", {"from_user_id": "a"})

        assert received == [
            ("pms", "internal_message_read", {"reader_id": "u1"}),
            ("pms", "internal_user_typing", {"from_user_id": "a"}),
        ]
        # No publish errors because we never attempted Redis.
        assert adapter.get_metrics()["publish_errors"] == 0
        assert adapter.get_metrics()["messages_published"] == 0

    @pytest.mark.asyncio
    async def test_publish_delivers_locally_when_redis_active(self):
        """When Redis is active, the publishing instance must still
        deliver to its own clients (Redis loopback is suppressed by
        ``source_instance`` filtering on the listener side)."""
        from infra.ws_redis_adapter import WebSocketRedisAdapter

        published = []

        class _FakeRedis:
            async def publish(self, channel, message):
                published.append((channel, message))
                return 1

        adapter = WebSocketRedisAdapter()
        adapter._redis = _FakeRedis()
        adapter._active = True
        adapter._instance_id = "inst-A"

        received = []

        async def handler(room, event, data):
            received.append((room, event, data))

        adapter._local_handler = handler

        await adapter.publish("pms", "internal_user_typing", {"x": 1})

        # Local clients on the publishing instance got the event.
        assert received == [("pms", "internal_user_typing", {"x": 1})]
        # And it was bridged to other instances via Redis.
        assert len(published) == 1
        assert published[0][0] == "ws:broadcast:pms"
        assert adapter.get_metrics()["messages_published"] == 1

    @pytest.mark.asyncio
    async def test_cross_instance_bridge_via_listener(self):
        """An event published on instance A must reach clients on
        instance B once the pub/sub message is delivered to B's
        listener — and must NOT be re-delivered on A (loopback guard).
        """
        import asyncio
        from infra.ws_redis_adapter import WebSocketRedisAdapter

        # Shared in-memory bus mimicking Redis pub/sub between two instances.
        queues: dict[str, list[asyncio.Queue]] = {}

        class _FakePubSub:
            def __init__(self):
                self._queues: list[asyncio.Queue] = []

            async def subscribe(self, channel):
                q: asyncio.Queue = asyncio.Queue()
                queues.setdefault(channel, []).append(q)
                self._queues.append(q)

            async def listen(self):
                # Multiplex all subscribed queues.
                while True:
                    for q in list(self._queues):
                        try:
                            msg = q.get_nowait()
                        except asyncio.QueueEmpty:
                            continue
                        yield msg
                    await asyncio.sleep(0.01)

            async def unsubscribe(self):
                pass

            async def close(self):
                pass

        class _FakeRedis:
            def __init__(self, pubsub):
                self._pubsub = pubsub

            def pubsub(self):
                return self._pubsub

            async def publish(self, channel, message):
                # Deliver to every queue subscribed to that channel
                # on every instance — emulates Redis fan-out.
                for q in queues.get(channel, []):
                    await q.put({"type": "message", "data": message})
                return len(queues.get(channel, []))

        # Instance A
        ps_a = _FakePubSub()
        redis_a = _FakeRedis(ps_a)
        adapter_a = WebSocketRedisAdapter()
        received_a: list[tuple] = []

        async def handler_a(room, event, data):
            received_a.append((room, event, data))

        await adapter_a.initialize(redis_a, "inst-A", local_handler=handler_a)

        # Instance B
        ps_b = _FakePubSub()
        redis_b = _FakeRedis(ps_b)
        adapter_b = WebSocketRedisAdapter()
        received_b: list[tuple] = []

        async def handler_b(room, event, data):
            received_b.append((room, event, data))

        await adapter_b.initialize(redis_b, "inst-B", local_handler=handler_b)

        # Both instances subscribe to the 'pms' room.
        await adapter_a.subscribe("pms")
        await adapter_b.subscribe("pms")

        # Instance A publishes an event.
        await adapter_a.publish("pms", "internal_message_read", {"reader_id": "u1"})

        # Allow the listener tasks a few ticks to drain the queue.
        for _ in range(50):
            await asyncio.sleep(0.01)
            if received_b:
                break

        try:
            # Local delivery on the publisher fired exactly once.
            assert received_a == [("pms", "internal_message_read", {"reader_id": "u1"})]
            # Cross-instance delivery on B fired exactly once
            # (no double-delivery, source filter works).
            assert received_b == [("pms", "internal_message_read", {"reader_id": "u1"})]
            # Verify the loopback metric: B forwarded one message.
            assert adapter_b.get_metrics()["messages_forwarded"] == 1
        finally:
            await adapter_a.close()
            await adapter_b.close()

    @pytest.mark.asyncio
    async def test_subscribe_is_reference_counted(self):
        """Two callers subscribing to the same room should result in a
        single Redis SUBSCRIBE; the channel only goes away once both
        have unsubscribed. Mirrors the connect/disconnect bookkeeping
        for shared rooms (department, tenant broadcast)."""
        from infra.ws_redis_adapter import WebSocketRedisAdapter

        sub_calls: list[str] = []
        unsub_calls: list[str] = []

        class _FakePubSub:
            async def subscribe(self, channel):
                sub_calls.append(channel)

            async def unsubscribe(self, channel=None):
                unsub_calls.append(channel)

            async def listen(self):
                # Idle generator: tests don't exercise the listener path.
                if False:
                    yield None  # pragma: no cover

            async def close(self):
                pass

        class _FakeRedis:
            def pubsub(self):
                return _FakePubSub()

        adapter = WebSocketRedisAdapter()
        await adapter.initialize(_FakeRedis(), "inst-X", local_handler=None)

        room = "internal_chat:t1:dept:Reception"
        await adapter.subscribe(room)
        await adapter.subscribe(room)
        await adapter.subscribe(room)

        # Only one Redis SUBSCRIBE despite three local subscribers.
        assert sub_calls == [f"{adapter.CHANNEL_PREFIX}{room}"]
        assert adapter.get_metrics()["channels_active"] == 1

        await adapter.unsubscribe(room)
        await adapter.unsubscribe(room)
        # Still subscribed — one local subscriber remains.
        assert unsub_calls == []
        assert adapter.get_metrics()["channels_active"] == 1

        await adapter.unsubscribe(room)
        # Last subscriber gone → Redis UNSUBSCRIBE issued.
        assert unsub_calls == [f"{adapter.CHANNEL_PREFIX}{room}"]
        assert adapter.get_metrics()["channels_active"] == 0

        # Extra unsubscribe is a safe no-op (no negative refcounts).
        await adapter.unsubscribe(room)
        assert len(unsub_calls) == 1

    @pytest.mark.asyncio
    async def test_unsubscribe_noop_when_redis_inactive(self):
        """In single-instance mode (Redis unavailable), subscribe/unsubscribe
        must be safe no-ops so connect/disconnect bookkeeping in
        websocket_server doesn't blow up."""
        from infra.ws_redis_adapter import WebSocketRedisAdapter

        adapter = WebSocketRedisAdapter()
        await adapter.initialize(None, "single-instance", local_handler=None)
        assert adapter._active is False

        # Should not raise and should not affect channel count.
        await adapter.subscribe("internal_chat:t1:user:u1")
        await adapter.unsubscribe("internal_chat:t1:user:u1")
        assert adapter.get_metrics()["channels_active"] == 0

    @pytest.mark.asyncio
    async def test_connect_disconnect_subscribes_and_unsubscribes_rooms(self):
        """Authenticated socket connect/disconnect must subscribe and
        unsubscribe the adapter to all three tenant-scoped rooms (DM,
        broadcast, department) so cross-instance delivery works for the
        connection's full lifetime — and exactly that long."""
        from unittest.mock import AsyncMock, patch

        import websocket_server as ws

        sub_calls: list[str] = []
        unsub_calls: list[str] = []

        async def fake_subscribe(room):
            sub_calls.append(room)

        async def fake_unsubscribe(room):
            unsub_calls.append(room)

        async def fake_resolve(_auth):
            return {
                "user_id": "u1",
                "tenant_id": "t1",
                "role": "front_desk",
                "department": "Reception",
            }

        with patch.object(ws, "_resolve_user_identity", fake_resolve), \
             patch.object(ws.sio, "emit", AsyncMock()), \
             patch.object(ws.sio, "enter_room", AsyncMock()), \
             patch(
                 "infra.ws_redis_adapter.ws_redis_adapter.subscribe",
                 side_effect=fake_subscribe,
             ), \
             patch(
                 "infra.ws_redis_adapter.ws_redis_adapter.unsubscribe",
                 side_effect=fake_unsubscribe,
             ):
            await ws.connect("sid-test", {}, {"token": "x"})
            assert sorted(sub_calls) == sorted([
                "internal_chat:t1:user:u1",
                "internal_chat:t1:broadcast",
                "internal_chat:t1:dept:Reception",
            ])
            assert unsub_calls == []

            await ws.disconnect("sid-test")
            assert sorted(unsub_calls) == sorted(sub_calls)
            # Identity bookkeeping was cleared so a stale disconnect
            # cannot double-unsubscribe.
            assert "sid-test" not in ws.sid_identity

    @pytest.mark.asyncio
    async def test_listener_reconnects_and_resubscribes_after_pubsub_drop(self):
        """Regression for transient Redis drops: when the pub/sub
        connection dies (network blip, Redis restart, failover) the
        adapter must rebuild ``pubsub`` from the Redis client and
        re-subscribe to every channel in ``_subscribed_channels`` so the
        internal-chat bridge recovers without falling back to
        single-instance mode. Refcounts must be preserved (local
        users are still connected) and the loopback guard must still
        protect against double-delivery on the new connection.
        """
        import asyncio
        import json
        from infra.ws_redis_adapter import WebSocketRedisAdapter

        pubsubs: list = []

        class _FakePubSub:
            def __init__(self):
                self.queue: asyncio.Queue = asyncio.Queue()
                self.subscriptions: list[str] = []
                self.closed = False

            async def subscribe(self, channel):
                self.subscriptions.append(channel)

            async def unsubscribe(self, channel=None):
                pass

            async def listen(self):
                while True:
                    msg = await self.queue.get()
                    if msg is None:
                        # Sentinel: simulate a connection drop.
                        raise ConnectionError("pubsub connection dropped")
                    yield msg

            async def close(self):
                self.closed = True

        class _FakeRedis:
            def pubsub(self):
                ps = _FakePubSub()
                pubsubs.append(ps)
                return ps

            async def publish(self, channel, message):
                # Fan out only to live pubsubs subscribed to channel.
                count = 0
                for ps in pubsubs:
                    if not ps.closed and channel in ps.subscriptions:
                        await ps.queue.put({"type": "message", "data": message})
                        count += 1
                return count

        received: list[tuple] = []

        async def handler(room, event, data):
            received.append((room, event, data))

        adapter = WebSocketRedisAdapter()
        # Shorten backoff so the test reconnect path runs quickly even
        # when the first attempt would have to retry.
        adapter._reconnect_min_backoff = 0.01
        adapter._reconnect_max_backoff = 0.05

        await adapter.initialize(_FakeRedis(), "inst-X", local_handler=handler)

        room = "internal_chat:t1:user:u1"
        await adapter.subscribe(room)
        channel = f"{adapter.CHANNEL_PREFIX}{room}"

        # Sanity: a remote message reaches the handler over the original
        # pubsub.
        msg1 = json.dumps({
            "room": room,
            "event": "internal_message",
            "data": {"id": "m1"},
            "source_instance": "inst-A",
            "timestamp": "now",
        })
        await pubsubs[0].queue.put({"type": "message", "data": msg1})

        for _ in range(100):
            await asyncio.sleep(0.01)
            if received:
                break
        assert received == [(room, "internal_message", {"id": "m1"})]

        # Drop the connection: the listener will catch ConnectionError
        # and rebuild pubsub from _redis.pubsub().
        await pubsubs[0].queue.put(None)

        for _ in range(200):
            await asyncio.sleep(0.01)
            if (
                len(pubsubs) >= 2
                and channel in pubsubs[-1].subscriptions
                and adapter.get_metrics()["reconnects"] >= 1
            ):
                break

        try:
            assert len(pubsubs) >= 2, (
                "adapter did not create a new pubsub after drop"
            )
            # The new pubsub re-subscribed to the same room.
            assert channel in pubsubs[-1].subscriptions
            # Refcount preserved — the local subscriber never disconnected.
            assert adapter._channel_refcounts[channel] == 1
            assert channel in adapter._subscribed_channels
            assert adapter.get_metrics()["reconnects"] >= 1

            # A second remote message must reach the handler over the
            # NEW pubsub — proving the bridge recovered automatically.
            msg2 = json.dumps({
                "room": room,
                "event": "internal_message",
                "data": {"id": "m2"},
                "source_instance": "inst-A",
                "timestamp": "now",
            })
            # Publishing through the fake redis routes to live pubsubs only.
            await adapter._redis.publish(channel, msg2)

            for _ in range(100):
                await asyncio.sleep(0.01)
                if len(received) >= 2:
                    break

            # Exactly two messages — no double-delivery from the dropped
            # pubsub, and the loopback guard kept the bridge clean.
            assert received == [
                (room, "internal_message", {"id": "m1"}),
                (room, "internal_message", {"id": "m2"}),
            ]
        finally:
            await adapter.close()

    @pytest.mark.asyncio
    async def test_subscribe_during_reconnect_is_picked_up(self):
        """If a new room is subscribed while the adapter is mid-reconnect
        (pub/sub temporarily torn down), the channel must still be
        registered and end up subscribed once the reconnect succeeds.
        This guards against a race where ``subscribe()`` would otherwise
        no-op because ``self._pubsub`` is briefly ``None``.
        """
        import asyncio
        from infra.ws_redis_adapter import WebSocketRedisAdapter

        pubsubs: list = []

        class _FakePubSub:
            def __init__(self, idx: int):
                self.idx = idx
                self.queue: asyncio.Queue = asyncio.Queue()
                self.subscriptions: list[str] = []

            async def subscribe(self, channel):
                self.subscriptions.append(channel)

            async def unsubscribe(self, channel=None):
                pass

            async def listen(self):
                while True:
                    msg = await self.queue.get()
                    if msg is None:
                        raise ConnectionError("pubsub dropped")
                    yield msg

            async def close(self):
                pass

        class _FakeRedis:
            def __init__(self):
                self.fail_next_pubsub = False

            def pubsub(self):
                if self.fail_next_pubsub:
                    self.fail_next_pubsub = False
                    raise ConnectionError("redis still down")
                ps = _FakePubSub(len(pubsubs))
                pubsubs.append(ps)
                return ps

            async def publish(self, channel, message):
                return 0

        adapter = WebSocketRedisAdapter()
        # Long-ish backoff so the test has time to race a subscribe()
        # into the window where reconnect has failed once and is sleeping
        # (lock released, _pubsub is None).
        adapter._reconnect_min_backoff = 0.2
        adapter._reconnect_max_backoff = 0.2

        redis = _FakeRedis()
        await adapter.initialize(redis, "inst-X", local_handler=None)

        room_existing = "internal_chat:t1:user:u1"
        await adapter.subscribe(room_existing)
        existing_channel = f"{adapter.CHANNEL_PREFIX}{room_existing}"

        # Force the *next* reconnect attempt to fail so the listener
        # enters its backoff sleep with _pubsub still cleared.
        redis.fail_next_pubsub = True
        await pubsubs[0].queue.put(None)

        # Wait until reconnect has set _pubsub to None and is sleeping.
        for _ in range(50):
            await asyncio.sleep(0.005)
            if (
                adapter._pubsub is None
                and adapter.get_metrics()["reconnect_failures"] >= 1
            ):
                break
        assert adapter._pubsub is None, (
            "expected _pubsub to stay None during reconnect backoff sleep"
        )

        # NEW subscribe arrives mid-reconnect. With the race fix this
        # must record the channel even though _pubsub is None, so the
        # next successful reconnect picks it up automatically.
        room_new = "internal_chat:t1:dept:Reception"
        await adapter.subscribe(room_new)
        new_channel = f"{adapter.CHANNEL_PREFIX}{room_new}"
        assert new_channel in adapter._subscribed_channels
        assert adapter._channel_refcounts[new_channel] == 1

        # Let reconnect succeed on the next attempt.
        for _ in range(200):
            await asyncio.sleep(0.01)
            if (
                len(pubsubs) >= 2
                and new_channel in pubsubs[-1].subscriptions
                and existing_channel in pubsubs[-1].subscriptions
            ):
                break

        try:
            assert len(pubsubs) >= 2
            # The fresh pubsub must carry BOTH rooms — the pre-existing
            # one and the room subscribed during the reconnect window.
            assert existing_channel in pubsubs[-1].subscriptions
            assert new_channel in pubsubs[-1].subscriptions
            assert adapter.get_metrics()["reconnects"] >= 1
        finally:
            await adapter.close()

    @pytest.mark.asyncio
    async def test_internal_message_bridges_across_instances(self):
        """End-to-end: `broadcast_internal_message` published on instance A
        must reach a client connected to instance B that has subscribed to
        the same tenant-scoped room."""
        import asyncio
        from infra.ws_redis_adapter import WebSocketRedisAdapter

        queues: dict[str, list[asyncio.Queue]] = {}

        class _FakePubSub:
            def __init__(self):
                self._queues: list[asyncio.Queue] = []

            async def subscribe(self, channel):
                q: asyncio.Queue = asyncio.Queue()
                queues.setdefault(channel, []).append(q)
                self._queues.append(q)

            async def listen(self):
                while True:
                    for q in list(self._queues):
                        try:
                            msg = q.get_nowait()
                        except asyncio.QueueEmpty:
                            continue
                        yield msg
                    await asyncio.sleep(0.01)

            async def unsubscribe(self, channel=None):
                pass

            async def close(self):
                pass

        class _FakeRedis:
            def __init__(self, pubsub):
                self._pubsub = pubsub

            def pubsub(self):
                return self._pubsub

            async def publish(self, channel, message):
                for q in queues.get(channel, []):
                    await q.put({"type": "message", "data": message})
                return len(queues.get(channel, []))

        # Instance A — publisher (no local subscriber on the target room).
        ps_a = _FakePubSub()
        adapter_a = WebSocketRedisAdapter()
        received_a: list[tuple] = []

        async def handler_a(room, event, data):
            received_a.append((room, event, data))

        await adapter_a.initialize(_FakeRedis(ps_a), "inst-A", local_handler=handler_a)

        # Instance B — recipient subscribed to the same DM room.
        ps_b = _FakePubSub()
        adapter_b = WebSocketRedisAdapter()
        received_b: list[tuple] = []

        async def handler_b(room, event, data):
            received_b.append((room, event, data))

        await adapter_b.initialize(_FakeRedis(ps_b), "inst-B", local_handler=handler_b)

        room = "internal_chat:t1:user:u-recipient"
        await adapter_b.subscribe(room)

        # Publishing instance does NOT subscribe (sender has no local
        # client listening on the recipient's DM room) — exactly the
        # scenario this task fixes.
        envelope = {"message": {"id": "m1", "content": "hi"}, "tenant_id": "t1"}
        await adapter_a.publish(room, "internal_message", envelope)

        for _ in range(50):
            await asyncio.sleep(0.01)
            if received_b:
                break

        try:
            assert received_b == [(room, "internal_message", envelope)]
            # Publisher had no local subscriber on this room, but the
            # local handler still fired (publish always delivers locally).
            assert received_a == [(room, "internal_message", envelope)]
            assert adapter_b.get_metrics()["messages_forwarded"] == 1
        finally:
            await adapter_a.close()
            await adapter_b.close()
