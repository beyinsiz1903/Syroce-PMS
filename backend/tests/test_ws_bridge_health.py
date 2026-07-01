"""
Tests for the multi-instance live chat bridge (ws_redis_adapter)
health surface — adapter metrics, normalized health endpoint logic,
and alerting engine threshold check.
"""
import sys

import pytest


# ── Helpers ──────────────────────────────────────────────────────


def _stub_dependencies(monkeypatch, *, ws_metrics):
    """Patch every external dependency the alerting engine touches
    except the WS bridge so each test can isolate that branch."""
    from modules.observability import alerting_engine as ae

    fake_eb = type("EB", (), {})()

    async def _eb_status():
        return {"mode": "memory", "backend_status": "healthy"}

    async def _eb_metrics():
        return {"total_dropped": 0, "total_errors": 0}

    fake_eb.get_status = _eb_status
    fake_eb.get_metrics = _eb_metrics
    monkeypatch.setitem(
        sys.modules,
        "modules.event_bus.abstraction",
        type("M", (), {"event_bus": fake_eb})(),
    )

    fake_obs = type("OBS", (), {})()
    fake_obs.get_all_metrics = lambda: {"histograms": {}}
    monkeypatch.setitem(
        sys.modules,
        "modules.observability.metrics_collector",
        type("M", (), {"metrics": fake_obs})(),
    )

    class _StubAdapter:
        def get_metrics(self):
            return ws_metrics

    monkeypatch.setitem(
        sys.modules,
        "infra.ws_redis_adapter",
        type("M", (), {"ws_redis_adapter": _StubAdapter()})(),
    )

    class _CountStub:
        async def count_documents(self, *a, **kw):
            return 0

    class _DBStub:
        messaging_delivery_logs = _CountStub()
        observability_errors = _CountStub()

        async def command(self, *a, **kw):
            return {"ok": 1}

    monkeypatch.setattr(ae, "db", _DBStub())


def _make_engine_capturing_alerts():
    from modules.observability import alerting_engine as ae

    engine = ae.ProductionAlertEngine()
    fired: list[dict] = []

    async def _fake_fire(alert_type, title, message, context=None):
        rec = {
            "alert_type": alert_type,
            "title": title,
            "message": message,
            "context": context or {},
        }
        fired.append(rec)
        return rec

    engine._fire_alert = _fake_fire  # type: ignore[assignment]
    return engine, fired


# ── ws_redis_adapter metrics ──────────────────────────────────────


@pytest.mark.asyncio
async def test_publish_error_records_last_error_metric():
    """Failed Redis publish must populate publish_errors counter
    plus last_publish_error / last_publish_error_at."""
    from infra.ws_redis_adapter import WebSocketRedisAdapter

    class _BrokenRedis:
        async def publish(self, channel, message):
            raise RuntimeError("redis down")

    adapter = WebSocketRedisAdapter()
    adapter._redis = _BrokenRedis()
    adapter._active = True
    adapter._instance_id = "inst-test"

    await adapter.publish("pms", "internal_message_read", {"reader_id": "u1"})

    metrics = adapter.get_metrics()
    assert metrics["publish_errors"] == 1
    assert "RuntimeError" in metrics["last_publish_error"]
    assert "redis down" in metrics["last_publish_error"]
    assert metrics["last_publish_error_at"] is not None
    assert metrics["messages_published"] == 0


def test_metrics_default_includes_last_error_fields():
    from infra.ws_redis_adapter import WebSocketRedisAdapter

    metrics = WebSocketRedisAdapter().get_metrics()
    for key in (
        "messages_published",
        "messages_received",
        "messages_forwarded",
        "publish_errors",
        "channels_active",
        "last_publish_error",
        "last_publish_error_at",
        "last_listen_error",
        "last_listen_error_at",
        "active",
        "instance_id",
        "subscribed_channels",
    ):
        assert key in metrics, f"missing metric key: {key}"


# ── Alerting engine: WS bridge thresholds ────────────────────────


@pytest.mark.asyncio
async def test_ws_bridge_publish_errors_alert_fires_above_threshold(monkeypatch):
    """Once cumulative publish_errors crosses the threshold, the engine
    must fire WS_BRIDGE_PUBLISH_ERRORS with last error + counters in
    the alert context, and advance the baseline."""
    from modules.observability import alerting_engine as ae

    engine, fired = _make_engine_capturing_alerts()
    threshold = ae.DEFAULT_THRESHOLDS[ae.AlertType.WS_BRIDGE_PUBLISH_ERRORS]["count"]

    _stub_dependencies(
        monkeypatch,
        ws_metrics={
            "messages_published": 100,
            "messages_received": 50,
            "messages_forwarded": 50,
            "publish_errors": threshold + 1,
            "channels_active": 2,
            "active": True,
            "instance_id": "inst-A",
            "subscribed_channels": ["ws:broadcast:pms"],
            "last_publish_error": "ConnectionError: redis down",
            "last_publish_error_at": "2026-04-26T12:00:00+00:00",
            "last_listen_error": None,
            "last_listen_error_at": None,
        },
    )

    await engine.evaluate_all()
    bridge_alerts = [
        a for a in fired if a["alert_type"] == ae.AlertType.WS_BRIDGE_PUBLISH_ERRORS
    ]
    assert bridge_alerts, "expected WS bridge alert to fire"

    ctx = bridge_alerts[0]["context"]
    assert ctx["publish_errors"] == threshold + 1
    assert ctx["delta"] == threshold + 1
    assert ctx["last_publish_error"].startswith("ConnectionError")
    assert ctx["instance_id"] == "inst-A"
    assert engine._baselines["ws_bridge_publish_errors"] == threshold + 1


@pytest.mark.asyncio
async def test_ws_bridge_publish_errors_alert_silent_below_threshold(monkeypatch):
    """A handful of publish errors below the threshold must NOT fire."""
    from modules.observability import alerting_engine as ae

    engine, fired = _make_engine_capturing_alerts()
    threshold = ae.DEFAULT_THRESHOLDS[ae.AlertType.WS_BRIDGE_PUBLISH_ERRORS]["count"]

    _stub_dependencies(
        monkeypatch,
        ws_metrics={
            "messages_published": 10,
            "messages_received": 0,
            "messages_forwarded": 0,
            "publish_errors": max(threshold - 1, 0),
            "channels_active": 1,
            "active": True,
            "instance_id": "inst-B",
            "subscribed_channels": ["ws:broadcast:pms"],
            "last_publish_error": None,
            "last_publish_error_at": None,
            "last_listen_error": None,
            "last_listen_error_at": None,
        },
    )

    await engine.evaluate_all()
    assert not [
        a for a in fired if a["alert_type"] == ae.AlertType.WS_BRIDGE_PUBLISH_ERRORS
    ]


@pytest.mark.asyncio
async def test_ws_bridge_alert_baseline_resets_when_counter_drops(monkeypatch):
    """If ws_redis_adapter restarts and its in-memory counter drops below
    the engine's stored baseline, the engine must reset the baseline so
    the next threshold crossing fires immediately — otherwise alerts
    would be silently delayed until the new counter climbs past the
    old high-water mark."""
    from modules.observability import alerting_engine as ae

    engine, fired = _make_engine_capturing_alerts()
    threshold = ae.DEFAULT_THRESHOLDS[ae.AlertType.WS_BRIDGE_PUBLISH_ERRORS]["count"]

    # Simulate a previously-high baseline (e.g. last fire was at 30 errors).
    engine._baselines["ws_bridge_publish_errors"] = 30

    # Adapter restarted: counter is now well below the stored baseline,
    # but already past the absolute threshold again on the new process.
    _stub_dependencies(
        monkeypatch,
        ws_metrics={
            "messages_published": 5,
            "messages_received": 0,
            "messages_forwarded": 0,
            "publish_errors": threshold + 2,
            "channels_active": 1,
            "active": True,
            "instance_id": "inst-restarted",
            "subscribed_channels": ["ws:broadcast:pms"],
            "last_publish_error": "TimeoutError: redis timeout",
            "last_publish_error_at": "2026-04-26T13:00:00+00:00",
            "last_listen_error": None,
            "last_listen_error_at": None,
        },
    )

    await engine.evaluate_all()

    bridge_alerts = [
        a for a in fired if a["alert_type"] == ae.AlertType.WS_BRIDGE_PUBLISH_ERRORS
    ]
    assert bridge_alerts, "expected re-fire after counter reset"
    # Baseline must have been reset to 0 first, then advanced to current.
    assert engine._baselines["ws_bridge_publish_errors"] == threshold + 2


# ── Normalized health endpoint logic ─────────────────────────────


@pytest.mark.asyncio
async def test_normalized_ws_bridge_endpoint_reports_critical_on_burst(monkeypatch):
    """publish_errors past the critical multiplier (5x threshold) must
    produce status=critical with a degraded_reason and expose the last
    error for operators."""
    from routers import system_health_normalized as shn
    from modules.observability import alerting_engine as ae

    threshold = ae.DEFAULT_THRESHOLDS[ae.AlertType.WS_BRIDGE_PUBLISH_ERRORS]["count"]

    class _StubAdapter:
        def get_metrics(self):
            return {
                "messages_published": 10,
                "messages_received": 0,
                "messages_forwarded": 0,
                "publish_errors": threshold * 5 + 1,
                "channels_active": 3,
                "active": True,
                "instance_id": "inst-A",
                "subscribed_channels": [
                    "ws:broadcast:pms",
                    "ws:broadcast:dashboard",
                    "ws:broadcast:reservations",
                ],
                "last_publish_error": "RedisConnectionError: connection refused",
                "last_publish_error_at": "2026-04-26T12:00:00+00:00",
                "last_listen_error": None,
                "last_listen_error_at": None,
            }

    monkeypatch.setitem(
        sys.modules,
        "infra.ws_redis_adapter",
        type("M", (), {"ws_redis_adapter": _StubAdapter()})(),
    )

    class _U:
        tenant_id = "t1"

    result = await shn.normalized_ws_bridge(_U())  # type: ignore[arg-type]

    assert result["status"] == "critical"
    assert result["severity"] == "critical"
    assert result["scope_id"] == "ws-bridge"
    assert result["degraded_reason"]
    assert result["critical_blockers"]
    detail = result["detail"]
    assert detail["publish_errors"] == threshold * 5 + 1
    assert detail["publish_error_threshold"] == threshold
    assert detail["publish_error_critical_threshold"] == threshold * 5
    assert detail["last_publish_error"].startswith("RedisConnectionError")
    assert detail["channels_active"] == 3
    assert detail["active"] is True


@pytest.mark.asyncio
async def test_normalized_ws_bridge_single_instance_is_healthy(monkeypatch):
    """Local-only mode (no Redis) is the documented dev fallback and
    must surface as healthy/info — not as a warning."""
    from routers import system_health_normalized as shn

    class _StubAdapter:
        def get_metrics(self):
            return {
                "messages_published": 0,
                "messages_received": 0,
                "messages_forwarded": 0,
                "publish_errors": 0,
                "channels_active": 0,
                "active": False,
                "instance_id": "single-instance",
                "subscribed_channels": [],
                "last_publish_error": None,
                "last_publish_error_at": None,
                "last_listen_error": None,
                "last_listen_error_at": None,
            }

    monkeypatch.setitem(
        sys.modules,
        "infra.ws_redis_adapter",
        type("M", (), {"ws_redis_adapter": _StubAdapter()})(),
    )

    class _U:
        tenant_id = "t1"

    result = await shn.normalized_ws_bridge(_U())  # type: ignore[arg-type]
    assert result["status"] == "healthy"
    assert result["severity"] == "info"
    assert result["detail"]["single_instance_mode"] is True
    assert result["degraded_reason"] is None


@pytest.mark.asyncio
async def test_normalized_ws_bridge_inactive_with_real_instance_is_degraded(monkeypatch):
    """Multi-instance pod with Redis bridge inactive must report
    degraded — that is the silent-bridge bug the task is preventing."""
    from routers import system_health_normalized as shn

    class _StubAdapter:
        def get_metrics(self):
            return {
                "messages_published": 5,
                "messages_received": 0,
                "messages_forwarded": 0,
                "publish_errors": 0,
                "channels_active": 0,
                "active": False,
                "instance_id": "pod-7af3",
                "subscribed_channels": [],
                "last_publish_error": None,
                "last_publish_error_at": None,
                "last_listen_error": None,
                "last_listen_error_at": None,
            }

    monkeypatch.setitem(
        sys.modules,
        "infra.ws_redis_adapter",
        type("M", (), {"ws_redis_adapter": _StubAdapter()})(),
    )

    class _U:
        tenant_id = "t1"

    result = await shn.normalized_ws_bridge(_U())  # type: ignore[arg-type]
    assert result["status"] == "degraded"
    assert result["severity"] == "warning"
    assert result["detail"]["single_instance_mode"] is False
    assert result["degraded_reason"]


def test_alerting_engine_exports_ws_bridge_alert_types():
    from modules.observability import alerting_engine as ae

    assert hasattr(ae.AlertType, "WS_BRIDGE_PUBLISH_ERRORS")
    assert hasattr(ae.AlertType, "WS_BRIDGE_INACTIVE")
    assert ae.AlertType.WS_BRIDGE_PUBLISH_ERRORS in ae.SEVERITY_MAP
    assert ae.AlertType.WS_BRIDGE_PUBLISH_ERRORS in ae.RUNBOOK_HINTS
    assert ae.AlertType.WS_BRIDGE_INACTIVE in ae.SEVERITY_MAP
    assert ae.AlertType.WS_BRIDGE_INACTIVE in ae.RUNBOOK_HINTS
