"""Startup must not strand tenants that enable pull after deployment."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bootstrap.phases import g_channels
from domains.channel_manager.providers.exely import exely_pull_worker, production_safety


@pytest.fixture
def startup(monkeypatch):
    scheduler = SimpleNamespace(start=AsyncMock(return_value=True))
    connections = SimpleNamespace(find_one=AsyncMock(return_value=None))
    monkeypatch.setattr(g_channels, "_raw_db", SimpleNamespace(exely_connections=connections))
    monkeypatch.setattr(exely_pull_worker, "exely_pull_scheduler", scheduler)
    monkeypatch.setattr(production_safety, "reservation_sync_block_reason", lambda: "")
    monkeypatch.delenv("SYROCE_EXELY_PULL_INTERVAL", raising=False)
    app = SimpleNamespace(state=SimpleNamespace())
    return app, scheduler, connections


async def test_supervisor_starts_with_no_enabled_tenants_at_boot(startup):
    app, scheduler, connections = startup
    assert await g_channels._start_exely_pull_supervisor(app) is True
    scheduler.start.assert_awaited_once_with(interval_seconds=180)
    connections.find_one.assert_not_awaited()
    assert app.state.exely_pull_scheduler is scheduler


async def test_global_kill_switch_still_prevents_supervisor_start(startup, monkeypatch):
    app, scheduler, connections = startup
    monkeypatch.setattr(production_safety, "reservation_sync_block_reason", lambda: "EXELY_PRODUCTION_DISABLED")
    assert await g_channels._start_exely_pull_supervisor(app) is False
    scheduler.start.assert_not_awaited()
    connections.find_one.assert_not_awaited()
    assert not hasattr(app.state, "exely_pull_scheduler")


async def test_supervisor_respects_configured_tick_not_tenant_poll_interval(startup, monkeypatch):
    app, scheduler, _ = startup
    monkeypatch.setenv("SYROCE_EXELY_PULL_INTERVAL", "240")
    assert await g_channels._start_exely_pull_supervisor(app) is True
    scheduler.start.assert_awaited_once_with(interval_seconds=240)


async def test_failed_start_is_not_attached_as_running(startup):
    app, scheduler, _ = startup
    scheduler.start.return_value = False
    assert await g_channels._start_exely_pull_supervisor(app) is False
    assert not hasattr(app.state, "exely_pull_scheduler")
