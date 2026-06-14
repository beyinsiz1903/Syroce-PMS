"""Regression guard for the cold-boot "Internal Server Error" window.

register_routers() imports ~189 router modules synchronously (~17-34s). On the
single-worker combined deployment, running that inside the deferred startup
callback blocked the event loop for the whole window, so uvicorn could not serve
even the cheap `/` health probe → the platform health check timed out
("context deadline exceeded") → the edge proxy showed a plain
"Internal Server Error" on every cold boot.

register_routers_async() drives the same work as a generator and releases the
loop between routers. These tests pin that behavior:

  1. the generator yields exactly once per manifest entry (so the async driver
     gets a release point after every router),
  2. the synchronous register_routers() still mounts every router (parity),
  3. the async variant does NOT monopolize the loop — a concurrent task makes
     progress while a (simulated-blocking) registration runs.
"""
import asyncio
import time

from bootstrap import router_registry


class _StubApp:
    def __init__(self):
        self.included = []

    def include_router(self, router, **kwargs):
        self.included.append(router)


def _expected_count():
    return len(router_registry._EXTRACTED_ROUTERS) + len(router_registry._OPTIONAL_ROUTERS)


def test_iter_register_yields_once_per_router(monkeypatch):
    monkeypatch.setattr(router_registry, "_safe_import", lambda m, a: object())
    app = _StubApp()
    steps = list(router_registry._iter_register(app, None))
    assert len(steps) == _expected_count()
    assert len(app.included) == _expected_count()


def test_register_routers_sync_parity(monkeypatch):
    monkeypatch.setattr(router_registry, "_safe_import", lambda m, a: object())
    app = _StubApp()
    router_registry.register_routers(app, None)
    assert len(app.included) == _expected_count()


def test_register_routers_async_releases_event_loop(monkeypatch):
    n_routers = 30
    block_per_router = 0.005  # simulate synchronous per-router import cost

    def _fake_iter(app, api_router, require_super_admin_dep=None):
        for _ in range(n_routers):
            time.sleep(block_per_router)  # blocking, like a real module import
            yield

    monkeypatch.setattr(router_registry, "_iter_register", _fake_iter)

    async def _run():
        state = {"hb": 0, "stop": False}

        async def _heartbeat():
            # Stand-in for uvicorn serving the `/` probe between routers.
            while not state["stop"]:
                state["hb"] += 1
                await asyncio.sleep(0)

        task = asyncio.create_task(_heartbeat())
        await asyncio.sleep(0)  # let the heartbeat start
        await router_registry.register_routers_async(app=object(), api_router=None)
        state["stop"] = True
        await task
        return state["hb"]

    heartbeats = asyncio.run(_run())
    # If the async variant blocked the loop (the bug), the heartbeat could not
    # advance during registration. Cooperative yielding lets it tick repeatedly.
    assert heartbeats >= n_routers // 2
