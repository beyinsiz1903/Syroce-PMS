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
