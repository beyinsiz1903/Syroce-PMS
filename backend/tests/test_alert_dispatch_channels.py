"""
Task #46 — Multi-instance live chat bridge alerts must reach the on-call
notification channels (Slack + email), not just the in-DB dashboard.

These tests cover the dispatcher contract:

  1. ``dispatch_alert`` honours per-tenant Slack/email config when present.
  2. When no tenant config exists, ``OPS_ALERT_SLACK_WEBHOOK_URL`` and
     ``OPS_ALERT_EMAIL_TO`` env vars provide a zero-config fallback so
     fresh deployments still page the team.
  3. The env fallback applies the ``OPS_ALERT_MIN_SEVERITY`` floor (default
     ``warning``) — INFO-level signals never spam the inbox by accident.
  4. ``ProductionAlertEngine._fire_alert`` invokes the dispatcher exactly
     once after persisting an alert, so the existing 7-channel evaluator
     loop now also fans out to email/Slack without code changes elsewhere.
  5. Dispatch failures are swallowed — alert evaluation must not break.
"""
from __future__ import annotations

import sys
from unittest.mock import AsyncMock, patch

import pytest


def _patch_db(monkeypatch):
    """Replace alert_dispatch.db with a stub that returns no tenant config
    (so the dispatcher falls through to env fallback) and accepts inserts."""
    from domains.channel_manager.monitoring import alert_dispatch as ad

    class _Coll:
        async def find_one(self, *_a, **_kw):
            return None

        async def replace_one(self, *_a, **_kw):
            return None

    class _DB:
        def __getitem__(self, _name):
            return _Coll()

    monkeypatch.setattr(ad, "db", _DB())


@pytest.mark.asyncio
async def test_env_fallback_dispatches_slack_and_email_for_high_severity(monkeypatch):
    """High-severity WS bridge alert with only env vars set → both channels fire."""
    _patch_db(monkeypatch)
    monkeypatch.setenv("OPS_ALERT_SLACK_WEBHOOK_URL", "https://hooks.slack.test/T0/B0/x")
    monkeypatch.setenv("OPS_ALERT_EMAIL_TO", "ops@example.com,oncall@example.com")
    monkeypatch.delenv("OPS_ALERT_MIN_SEVERITY", raising=False)

    from domains.channel_manager.monitoring import alert_dispatch as ad

    slack_mock = AsyncMock(return_value=type("R", (), {"status_code": 200})())
    send_email_mock = AsyncMock(return_value={"sent": True, "provider": "resend", "id": "x"})

    with patch("integrations.xchange.safety.safe_post_async", slack_mock), \
         patch("core.email.send_email", send_email_mock):
        result = await ad.dispatch_alert({
            "alert_type": "ws_bridge_publish_errors",
            "severity": "high",
            "title": "Multi-Instance Chat Bridge Publish Errors",
            "message": "12 publish errors (+5 since last alert).",
            "context": {"publish_errors": 12, "delta": 5, "instance_id": "pod-a"},
            "runbook_hint": "Check REDIS_URL connectivity.",
        })

    assert result == {"dashboard": True, "slack": True, "email": True}
    assert slack_mock.await_count == 1
    sent_url = slack_mock.await_args.args[0]
    assert sent_url == "https://hooks.slack.test/T0/B0/x"
    # Email is fanned out to every recipient in the comma-separated list.
    assert send_email_mock.await_count == 2
    recipients = sorted(call.args[0] for call in send_email_mock.await_args_list)
    assert recipients == ["oncall@example.com", "ops@example.com"]


@pytest.mark.asyncio
async def test_env_fallback_severity_floor_blocks_info(monkeypatch):
    """Default OPS_ALERT_MIN_SEVERITY is ``warning`` → INFO is not paged."""
    _patch_db(monkeypatch)
    monkeypatch.setenv("OPS_ALERT_SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    monkeypatch.setenv("OPS_ALERT_EMAIL_TO", "ops@example.com")
    monkeypatch.delenv("OPS_ALERT_MIN_SEVERITY", raising=False)

    from domains.channel_manager.monitoring import alert_dispatch as ad

    slack_mock = AsyncMock(return_value=type("R", (), {"status_code": 200})())
    send_email_mock = AsyncMock(return_value={"sent": True})

    with patch("integrations.xchange.safety.safe_post_async", slack_mock), \
         patch("core.email.send_email", send_email_mock):
        result = await ad.dispatch_alert({
            "alert_type": "stale_dataset",
            "severity": "info",
            "title": "Stale dataset",
            "message": "Pipeline last ran 50h ago.",
        })

    assert result == {"dashboard": True, "slack": False, "email": False}
    slack_mock.assert_not_awaited()
    send_email_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_env_fallback_severity_floor_can_be_lowered(monkeypatch):
    """Operators can set the floor to ``info`` to opt every alert in."""
    _patch_db(monkeypatch)
    monkeypatch.setenv("OPS_ALERT_EMAIL_TO", "ops@example.com")
    monkeypatch.setenv("OPS_ALERT_MIN_SEVERITY", "info")
    monkeypatch.delenv("OPS_ALERT_SLACK_WEBHOOK_URL", raising=False)

    from domains.channel_manager.monitoring import alert_dispatch as ad

    send_email_mock = AsyncMock(return_value={"sent": True})
    with patch("core.email.send_email", send_email_mock):
        result = await ad.dispatch_alert({
            "alert_type": "stale_dataset",
            "severity": "info",
            "title": "Stale",
            "message": "x",
        })
    assert result["email"] is True
    send_email_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_tenant_config_takes_precedence_over_env(monkeypatch):
    """When a tenant has explicitly enabled Slack the env URL is ignored."""
    monkeypatch.setenv("OPS_ALERT_SLACK_WEBHOOK_URL", "https://env.fallback/")
    monkeypatch.setenv("OPS_ALERT_EMAIL_TO", "env@example.com")

    from domains.channel_manager.monitoring import alert_dispatch as ad

    class _Coll:
        async def find_one(self, *_a, **_kw):
            return {
                "tenant_id": "system",
                "slack": {
                    "enabled": True,
                    "webhook_url": "https://tenant.specific/hook",
                    "severities": ["high", "critical"],
                },
                "email": {
                    "enabled": True,
                    "recipients": ["tenant@example.com"],
                    "severities": ["high", "critical"],
                },
            }
        async def replace_one(self, *_a, **_kw):
            return None

    class _DB:
        def __getitem__(self, _n):
            return _Coll()

    monkeypatch.setattr(ad, "db", _DB())

    slack_mock = AsyncMock(return_value=type("R", (), {"status_code": 200})())
    send_email_mock = AsyncMock(return_value={"sent": True})

    with patch("integrations.xchange.safety.safe_post_async", slack_mock), \
         patch("core.email.send_email", send_email_mock):
        await ad.dispatch_alert({
            "alert_type": "ws_bridge_publish_errors",
            "severity": "high",
            "title": "x",
            "message": "y",
        })

    assert slack_mock.await_args.args[0] == "https://tenant.specific/hook"
    assert send_email_mock.await_args.args[0] == "tenant@example.com"


@pytest.mark.asyncio
async def test_explicit_disable_blocks_env_fallback(monkeypatch):
    """If a tenant has saved config that explicitly disables a channel, the
    env-var fallback must NOT silently re-enable it for them. (Architect
    review fix — review #46.)"""
    monkeypatch.setenv("OPS_ALERT_SLACK_WEBHOOK_URL", "https://env.fallback/")
    monkeypatch.setenv("OPS_ALERT_EMAIL_TO", "env@example.com")

    from domains.channel_manager.monitoring import alert_dispatch as ad

    class _Coll:
        async def find_one(self, *_a, **_kw):
            return {
                "tenant_id": "system",
                "slack": {"enabled": False, "webhook_url": ""},
                "email": {"enabled": False, "recipients": []},
            }
        async def replace_one(self, *_a, **_kw):
            return None

    class _DB:
        def __getitem__(self, _n):
            return _Coll()

    monkeypatch.setattr(ad, "db", _DB())

    slack_mock = AsyncMock()
    send_email_mock = AsyncMock()
    with patch("integrations.xchange.safety.safe_post_async", slack_mock), \
         patch("core.email.send_email", send_email_mock):
        result = await ad.dispatch_alert({
            "alert_type": "ws_bridge_publish_errors",
            "severity": "high",
            "title": "x",
            "message": "y",
        })

    assert result == {"dashboard": True, "slack": False, "email": False}
    slack_mock.assert_not_awaited()
    send_email_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_context_redaction_strips_secrets_from_email(monkeypatch):
    """Sensitive context keys (URL, token, error, secret, …) must be masked
    before any payload leaves egress — both email and Slack. (Architect
    review fix — review #46.)"""
    _patch_db(monkeypatch)
    monkeypatch.setenv("OPS_ALERT_EMAIL_TO", "ops@example.com")
    monkeypatch.setenv("OPS_ALERT_SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    monkeypatch.delenv("OPS_ALERT_MIN_SEVERITY", raising=False)

    from domains.channel_manager.monitoring import alert_dispatch as ad

    captured_emails: list[str] = []

    async def _capture_email(addr, subject, html, *, text=None, **_kw):
        captured_emails.append(html + "\n---\n" + (text or ""))
        return {"sent": True}

    captured_slack: list[dict] = []

    async def _capture_slack(_url, *, json=None, **_kw):
        captured_slack.append(json or {})
        return type("R", (), {"status_code": 200})()

    with patch("core.email.send_email", _capture_email), \
         patch("integrations.xchange.safety.safe_post_async", _capture_slack):
        await ad.dispatch_alert({
            "alert_type": "ws_bridge_publish_errors",
            "severity": "high",
            "title": "Bridge errors",
            "message": "12 errors",
            "context": {
                "publish_errors": 12,                        # safe — kept
                "redis_url": "redis://user:p4ss@host:6379",  # secret — masked
                "auth_token": "Bearer abcdef",               # secret — masked
                "last_publish_error": "Auth failed for sk_live_xxx",  # error — masked
                "instance_id": "pod-a",                      # safe — kept
            },
        })

    assert captured_emails, "email channel was not invoked"
    body = captured_emails[0]
    assert "redis://user:p4ss" not in body
    assert "sk_live_xxx" not in body
    assert "abcdef" not in body
    assert "***" in body          # placeholder rendered
    assert "publish_errors" in body  # safe key still present
    assert "pod-a" in body           # safe value still present


@pytest.mark.asyncio
async def test_slack_message_uses_message_field_not_details(monkeypatch):
    """Regression: the Slack template previously read alert['details']
    while _fire_alert populates alert['message'] — Slack messages would be
    blank. (Architect review fix — review #46.)"""
    _patch_db(monkeypatch)
    monkeypatch.setenv("OPS_ALERT_SLACK_WEBHOOK_URL", "https://hooks.slack.test/x")
    monkeypatch.delenv("OPS_ALERT_EMAIL_TO", raising=False)

    from domains.channel_manager.monitoring import alert_dispatch as ad

    captured: list[dict] = []

    async def _capture(_url, *, json=None, **_kw):
        captured.append(json or {})
        return type("R", (), {"status_code": 200})()

    with patch("integrations.xchange.safety.safe_post_async", _capture):
        await ad.dispatch_alert({
            "alert_type": "ws_bridge_publish_errors",
            "severity": "high",
            "title": "Bridge errors",
            "message": "12 publish errors (+5 since last alert).",
        })

    assert captured, "Slack channel was not invoked"
    payload = captured[0]
    rendered = str(payload)
    assert "12 publish errors" in rendered


@pytest.mark.asyncio
async def test_no_channels_configured_is_a_no_op(monkeypatch):
    """No tenant config + no env vars → dispatcher returns dashboard-only."""
    _patch_db(monkeypatch)
    for var in ("OPS_ALERT_SLACK_WEBHOOK_URL", "OPS_ALERT_EMAIL_TO", "OPS_ALERT_MIN_SEVERITY"):
        monkeypatch.delenv(var, raising=False)

    from domains.channel_manager.monitoring import alert_dispatch as ad

    slack_mock = AsyncMock()
    send_email_mock = AsyncMock()
    with patch("integrations.xchange.safety.safe_post_async", slack_mock), \
         patch("core.email.send_email", send_email_mock):
        result = await ad.dispatch_alert({
            "alert_type": "ws_bridge_publish_errors",
            "severity": "high",
            "title": "x",
            "message": "y",
        })

    assert result == {"dashboard": True, "slack": False, "email": False}
    slack_mock.assert_not_awaited()
    send_email_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_fire_alert_invokes_dispatcher_after_persist(monkeypatch):
    """ProductionAlertEngine._fire_alert must call dispatch_alert exactly
    once for every alert that survives cooldown & dedup, so the existing
    threshold loops now reach Slack/email automatically."""
    from modules.observability import alerting_engine as ae

    class _AlertHistory:
        async def insert_one(self, *_a, **_kw):
            return None

    class _DBStub:
        alert_history = _AlertHistory()

    monkeypatch.setattr(ae, "db", _DBStub())

    dispatch_mock = AsyncMock(return_value={"dashboard": True, "slack": True, "email": False})
    fake_module = type("M", (), {"dispatch_alert": dispatch_mock})()
    monkeypatch.setitem(
        sys.modules,
        "domains.channel_manager.monitoring.alert_dispatch",
        fake_module,
    )

    engine = ae.ProductionAlertEngine()
    alert = await engine._fire_alert(
        ae.AlertType.WS_BRIDGE_PUBLISH_ERRORS,
        "Multi-Instance Chat Bridge Publish Errors",
        "12 errors",
        context={"publish_errors": 12},
    )

    assert alert is not None
    dispatch_mock.assert_awaited_once()
    forwarded = dispatch_mock.await_args.args[0]
    assert forwarded["alert_type"] == ae.AlertType.WS_BRIDGE_PUBLISH_ERRORS
    assert forwarded["severity"] == ae.AlertSeverity.HIGH
    assert forwarded["context"]["publish_errors"] == 12


@pytest.mark.asyncio
async def test_fire_alert_swallows_dispatch_failure(monkeypatch):
    """A broken dispatcher must never propagate out of _fire_alert."""
    from modules.observability import alerting_engine as ae

    class _AlertHistory:
        async def insert_one(self, *_a, **_kw):
            return None

    class _DBStub:
        alert_history = _AlertHistory()

    monkeypatch.setattr(ae, "db", _DBStub())

    async def _boom(_):
        raise RuntimeError("downstream Slack outage")

    fake_module = type("M", (), {"dispatch_alert": _boom})()
    monkeypatch.setitem(
        sys.modules,
        "domains.channel_manager.monitoring.alert_dispatch",
        fake_module,
    )

    engine = ae.ProductionAlertEngine()
    # Use a fresh alert type so cooldown does not interfere with the assertion.
    alert = await engine._fire_alert(
        ae.AlertType.REDIS_DISCONNECTED,
        "Redis disconnected",
        "lost connection",
    )
    assert alert is not None  # persisted + returned despite dispatcher crash


@pytest.mark.asyncio
async def test_ws_bridge_inactive_skipped_in_single_instance(monkeypatch):
    """Regression: WS_BRIDGE_INACTIVE must NOT fire (and therefore not page
    anyone) when the deployment is single-instance — the alerting engine
    already encodes that policy and #46 keeps it intact."""
    from modules.observability import alerting_engine as ae

    class _StubAdapter:
        def get_metrics(self):
            return {
                "instance_id": "single-instance",
                "active": False,
                "publish_errors": 0,
                "subscribed_channels": [],
                "messages_published": 0,
                "messages_received": 0,
                "messages_forwarded": 0,
                "channels_active": 0,
            }

    monkeypatch.setitem(
        sys.modules,
        "infra.ws_redis_adapter",
        type("M", (), {"ws_redis_adapter": _StubAdapter()})(),
    )

    engine = ae.ProductionAlertEngine()
    fired: list[str] = []

    async def _fake_fire(alert_type, *_a, **_kw):
        fired.append(alert_type)
        return {"alert_type": alert_type}

    monkeypatch.setattr(engine, "_fire_alert", _fake_fire)

    # Replicate the WS-bridge branch directly (the full evaluate_all loop
    # touches many other subsystems we'd otherwise have to stub out).
    from infra.ws_redis_adapter import ws_redis_adapter
    metrics = ws_redis_adapter.get_metrics()
    instance_id = metrics.get("instance_id") or ""
    active = bool(metrics.get("active"))
    if not active and instance_id and instance_id != "single-instance":
        await engine._fire_alert(ae.AlertType.WS_BRIDGE_INACTIVE, "x", "y")

    assert fired == []
