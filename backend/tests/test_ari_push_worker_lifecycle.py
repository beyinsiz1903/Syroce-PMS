import asyncio
import os

import pytest

os.environ.setdefault("JWT_SECRET", "test-secret-at-least-32-characters-long")

from workers import ari_push_worker


@pytest.fixture(autouse=True)
async def reset_worker_task():
    await ari_push_worker.stop_push_worker()
    yield
    await ari_push_worker.stop_push_worker()


@pytest.mark.asyncio
async def test_start_is_idempotent_and_stop_cancels_worker(monkeypatch):
    started = asyncio.Event()

    async def fake_worker_loop():
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(ari_push_worker, "ari_push_worker_loop", fake_worker_loop)

    first_task = await ari_push_worker.start_push_worker()
    second_task = await ari_push_worker.start_push_worker()
    await started.wait()

    assert first_task is second_task
    assert first_task.get_name() == "ari-push-worker"
    assert await ari_push_worker.stop_push_worker() is True
    assert first_task.cancelled()
    assert await ari_push_worker.stop_push_worker() is False


@pytest.mark.asyncio
async def test_stopped_worker_cannot_run_another_database_tick(monkeypatch):
    ticked = asyncio.Event()
    release_tick = asyncio.Event()
    tick_count = 0

    async def fake_worker_loop():
        nonlocal tick_count
        while True:
            tick_count += 1
            ticked.set()
            await release_tick.wait()
            release_tick.clear()

    monkeypatch.setattr(ari_push_worker, "ari_push_worker_loop", fake_worker_loop)

    task = await ari_push_worker.start_push_worker()
    await ticked.wait()
    assert tick_count == 1

    assert await ari_push_worker.stop_push_worker() is True
    release_tick.set()
    await asyncio.sleep(0)

    assert task.cancelled()
    assert tick_count == 1
