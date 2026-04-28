"""
Regression tests for normalized_overview() aggregation semantics.

After the asyncio.gather refactor, ensure:
  1) Subsystem exception is converted into an in-band degraded entry,
     overall response shape (top-level keys + subsystem keys) is unchanged,
     and overall_status is at least "degraded".
  2) Non-Exception BaseException (e.g. asyncio.CancelledError) is NOT
     swallowed by _coerce — cooperative cancellation must propagate.
  3) Coerced fallback uses the caller's tenant_id when available
     (scope_type=tenant), matching the contract used by healthy entries.
"""
import asyncio
import pytest

from routers import system_health_normalized as mod


class _FakeUser:
    def __init__(self, tenant_id="tenant-aggregation-test"):
        self.tenant_id = tenant_id
        self.id = "user-1"
        self.role = "admin"


@pytest.mark.asyncio
async def test_subsystem_exception_becomes_degraded_entry(monkeypatch):
    user = _FakeUser()

    async def boom(_u):
        raise RuntimeError("simulated subsystem failure")

    async def healthy(_u):
        return mod._health_response(
            status="healthy", severity="info",
            scope_type="tenant", scope_id=user.tenant_id,
            detail={"ok": True},
        )

    monkeypatch.setattr(mod, "normalized_channel_manager", boom)
    monkeypatch.setattr(mod, "normalized_workers", healthy)
    monkeypatch.setattr(mod, "normalized_security", healthy)
    monkeypatch.setattr(mod, "normalized_observability", healthy)
    monkeypatch.setattr(mod, "normalized_alerts", healthy)
    monkeypatch.setattr(mod, "normalized_ws_bridge", healthy)

    out = await mod.normalized_overview(user)

    # Top-level shape unchanged
    assert set(out.keys()) >= {
        "overall_status", "overall_severity", "last_updated_at",
        "live_capable", "data_freshness", "subsystems",
    }
    # All six subsystems present
    assert set(out["subsystems"].keys()) == {
        "channel_manager", "workers", "security",
        "observability", "alerts", "ws_bridge",
    }
    # The failing subsystem is now degraded with tenant scope and error detail
    cm = out["subsystems"]["channel_manager"]
    assert cm["status"] == "degraded"
    assert cm["severity"] == "warning"
    assert cm["scope_type"] == "tenant"
    assert cm["scope_id"] == user.tenant_id
    assert "RuntimeError" in (cm.get("degraded_reason") or "")
    assert cm["detail"].get("subsystem") == "channel-manager"
    # Overall is at least degraded (a warning subsystem present)
    assert out["overall_status"] in ("degraded", "critical")
    assert out["overall_severity"] in ("warning", "critical")


@pytest.mark.asyncio
async def test_cancelled_error_is_not_swallowed(monkeypatch):
    user = _FakeUser()

    async def cancelled(_u):
        raise asyncio.CancelledError()

    async def healthy(_u):
        return mod._health_response(
            status="healthy", severity="info",
            scope_type="tenant", scope_id=user.tenant_id,
            detail={"ok": True},
        )

    monkeypatch.setattr(mod, "normalized_channel_manager", cancelled)
    monkeypatch.setattr(mod, "normalized_workers", healthy)
    monkeypatch.setattr(mod, "normalized_security", healthy)
    monkeypatch.setattr(mod, "normalized_observability", healthy)
    monkeypatch.setattr(mod, "normalized_alerts", healthy)
    monkeypatch.setattr(mod, "normalized_ws_bridge", healthy)

    with pytest.raises((asyncio.CancelledError, BaseException)) as excinfo:
        await mod.normalized_overview(user)
    # Make sure it really is CancelledError, not a generic Exception
    assert isinstance(excinfo.value, asyncio.CancelledError)


@pytest.mark.asyncio
async def test_overview_runs_concurrently(monkeypatch):
    """Sleeping subsystems should run in parallel under gather."""
    user = _FakeUser()

    async def slow(_u, delay=0.2):
        await asyncio.sleep(delay)
        return mod._health_response(
            status="healthy", severity="info",
            scope_type="tenant", scope_id=user.tenant_id,
            detail={"slept_ms": int(delay * 1000)},
        )

    monkeypatch.setattr(mod, "normalized_channel_manager", slow)
    monkeypatch.setattr(mod, "normalized_workers", slow)
    monkeypatch.setattr(mod, "normalized_security", slow)
    monkeypatch.setattr(mod, "normalized_observability", slow)
    monkeypatch.setattr(mod, "normalized_alerts", slow)
    monkeypatch.setattr(mod, "normalized_ws_bridge", slow)

    loop = asyncio.get_event_loop()
    t0 = loop.time()
    out = await mod.normalized_overview(user)
    elapsed = loop.time() - t0

    # Sequential would be ~1.2s (6 * 0.2). Parallel should be well under 0.5s.
    assert elapsed < 0.5, f"overview not concurrent: took {elapsed:.3f}s"
    assert out["overall_status"] == "healthy"
