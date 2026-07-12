import asyncio
import os
import sys
from unittest.mock import AsyncMock

from domains.channel_manager.providers.sync_scheduler import ReservationPullScheduler
from infra.distributed_lock import lock_manager


class MockRedis:
    def __init__(self):
        self._store = {}
        self._lock = asyncio.Lock()
        self.eval_calls = []

    async def set(self, name, value, nx=False, ex=None):
        async with self._lock:
            if nx and name in self._store:
                return False
            self._store[name] = value
            return True

    async def eval(self, script, numkeys, *args):
        self.eval_calls.append((script, args))
        key = args[0]
        token = args[1]
        async with self._lock:
            if "pexpire" in script:
                if self._store.get(key) == token:
                    return 1
                return 0
            elif "del" in script:
                if self._store.get(key) == token:
                    del self._store[key]
                    return 1
                return 0
        return 0

async def test_scheduler_concurrency_only_one_worker_runs():
    print("Running test_scheduler_concurrency_only_one_worker_runs...")
    redis = MockRedis()
    lock_manager.set_redis(redis)
    os.environ["ENV"] = "test"

    scheduler1 = ReservationPullScheduler()
    scheduler2 = ReservationPullScheduler()
    pull_calls = []

    async def mock_pull(*args, **kwargs):
        pull_calls.append(1)
        await asyncio.sleep(0.5)

    scheduler1._pull_all_tenants = AsyncMock(side_effect=mock_pull)
    scheduler2._pull_all_tenants = AsyncMock(side_effect=mock_pull)

    scheduler1._running = True
    scheduler2._running = True

    async def cancel_after(delay):
        await asyncio.sleep(delay)
        scheduler1._running = False
        scheduler2._running = False

    t1 = asyncio.create_task(scheduler1._run_loop(sleep_seconds=1, safety_window_minutes=5))
    t2 = asyncio.create_task(scheduler2._run_loop(sleep_seconds=1, safety_window_minutes=5))

    await cancel_after(0.8)

    t1.cancel()
    t2.cancel()

    assert len(pull_calls) == 1, f"Expected 1 pull call, got {len(pull_calls)}"
    print("test_scheduler_concurrency_only_one_worker_runs PASSED")

async def test_scheduler_concurrency_redis_unavailable():
    print("Running test_scheduler_concurrency_redis_unavailable...")
    lock_manager.set_redis(None)
    os.environ["ENV"] = "test"
    scheduler = ReservationPullScheduler()
    pull_calls = []

    async def mock_pull(*args, **kwargs):
        pull_calls.append(1)

    scheduler._pull_all_tenants = AsyncMock(side_effect=mock_pull)
    scheduler._running = True

    async def cancel_after(delay):
        await asyncio.sleep(delay)
        scheduler._running = False

    t1 = asyncio.create_task(scheduler._run_loop(sleep_seconds=1, safety_window_minutes=5))
    await cancel_after(0.1)
    t1.cancel()

    assert len(pull_calls) == 0, "Worker should skip cycle when Redis is unavailable"
    print("test_scheduler_concurrency_redis_unavailable PASSED")

async def test_scheduler_concurrency_long_cycle():
    print("Running test_scheduler_concurrency_long_cycle...")
    redis = MockRedis()
    lock_manager.set_redis(redis)
    os.environ["ENV"] = "test"

    scheduler1 = ReservationPullScheduler()
    scheduler2 = ReservationPullScheduler()
    pull_calls = []

    async def mock_pull_long(*args, **kwargs):
        pull_calls.append(1)
        await asyncio.sleep(1.5)

    scheduler1._pull_all_tenants = AsyncMock(side_effect=mock_pull_long)
    scheduler2._pull_all_tenants = AsyncMock(side_effect=mock_pull_long)

    scheduler1._running = True
    scheduler2._running = True

    t1 = asyncio.create_task(scheduler1._run_loop(sleep_seconds=1, safety_window_minutes=5))
    await asyncio.sleep(0.1)

    t2 = asyncio.create_task(scheduler2._run_loop(sleep_seconds=1, safety_window_minutes=5))
    await asyncio.sleep(0.5)

    scheduler1._running = False
    scheduler2._running = False

    t1.cancel()
    t2.cancel()

    assert len(pull_calls) == 1, "Scheduler 2 should not pull while Scheduler 1 is running"
    print("test_scheduler_concurrency_long_cycle PASSED")

async def test_scheduler_concurrency_lock_release(mock_redis):
    from infra.distributed_lock import DistributedLock, lock_manager
    print("Running test_scheduler_concurrency_lock_release...")
    lock_manager.set_redis(mock_redis)
    os.environ["ENV"] = "test"
    scheduler = ReservationPullScheduler()

    async def mock_pull_short(*args, **kwargs):
        await asyncio.sleep(0.1)

    scheduler._pull_all_tenants = AsyncMock(side_effect=mock_pull_short)
    scheduler._running = True

    redis = lock_manager.get_redis()
    lock_name = "test:hotelrunner:pull-cycle"
    dl = DistributedLock(redis, lock_name, timeout=600.0, retry_count=1)

    acquired = await dl.acquire()
    assert acquired is True, "Should acquire lock"

    actual_key = f"lock:{lock_name}"
    assert actual_key in mock_redis._store, "Lock should be in redis"

    try:
        await scheduler._pull_all_tenants(5)
    finally:
        await dl.release()

    assert actual_key not in mock_redis._store, "Lock should be removed after finally block"
    print("test_scheduler_concurrency_lock_release PASSED")

async def test_scheduler_heartbeat_extends_lock():
    from infra.distributed_lock import DistributedLock, lock_manager
    print("Running test_scheduler_heartbeat_extends_lock...")
    redis = MockRedis()
    lock_manager.set_redis(redis)
    os.environ["ENV"] = "test"



    async def mock_pull_long(*args, **kwargs):
        pass

    # Direct test of heartbeat mechanism
    dl = DistributedLock(redis, "test-hb", timeout=600.0)
    await dl.acquire()
    extended = await dl.extend(600.0)
    assert extended is True, "Should be able to extend lock"

    # Let's check if pexpire was in the eval calls
    has_pexpire = any("pexpire" in call[0] for call in redis.eval_calls)
    assert has_pexpire, "pexpire should be called"
    print("test_scheduler_heartbeat_extends_lock PASSED")

async def test_scheduler_different_hostnames_same_key():
    print("Running test_scheduler_different_hostnames_same_key...")
    # Simulate two different HOSTNAME environments but SAME DEPLOYMENT_ENV
    os.environ["DEPLOYMENT_ENV"] = "production"

    # 1. First worker
    os.environ["HOSTNAME"] = "backend-worker-A"
    scheduler1 = ReservationPullScheduler()
    # Mock pull to just hold the lock
    async def mock_pull_A(*args, **kwargs):
        await asyncio.sleep(0.5)
    scheduler1._pull_all_tenants = AsyncMock(side_effect=mock_pull_A)

    # 2. Second worker
    os.environ["HOSTNAME"] = "backend-worker-B"
    scheduler2 = ReservationPullScheduler()
    pull_calls_B = []
    async def mock_pull_B(*args, **kwargs):
        pull_calls_B.append(1)
        await asyncio.sleep(0.1)
    scheduler2._pull_all_tenants = AsyncMock(side_effect=mock_pull_B)

    scheduler1._running = True
    scheduler2._running = True

    redis = MockRedis()
    lock_manager.set_redis(redis)

    t1 = asyncio.create_task(scheduler1._run_loop(sleep_seconds=1, safety_window_minutes=5))
    await asyncio.sleep(0.1) # let worker A acquire lock
    t2 = asyncio.create_task(scheduler2._run_loop(sleep_seconds=1, safety_window_minutes=5))
    await asyncio.sleep(0.2)

    scheduler1._running = False
    scheduler2._running = False
    t1.cancel()
    t2.cancel()

    assert len(pull_calls_B) == 0, "Worker B should not pull because Worker A holds the lock, even though HOSTNAME differs."
    print("test_scheduler_different_hostnames_same_key PASSED")


async def test_scheduler_heartbeat_loss_aborts_cycle():
    print("Running test_scheduler_heartbeat_loss_aborts_cycle...")
    redis = MockRedis()
    lock_manager.set_redis(redis)
    os.environ["DEPLOYMENT_ENV"] = "test"

    scheduler = ReservationPullScheduler()

    pull_started = asyncio.Event()
    pull_aborted = False

    async def mock_pull_long(*args, **kwargs):
        nonlocal pull_aborted
        pull_started.set()
        try:
            await asyncio.sleep(10.0)
        except asyncio.CancelledError:
            pull_aborted = True
            raise

    scheduler._pull_all_tenants = AsyncMock(side_effect=mock_pull_long)
    scheduler._running = True

    # Patch DistributedLock.extend to return False and sleep to return immediately
    from infra.distributed_lock import DistributedLock
    original_extend = DistributedLock.extend
    original_sleep = asyncio.sleep

    extend_called = asyncio.Event()

    async def mock_extend(self, additional_time):
        extend_called.set()
        return False

    async def mock_sleep(delay, *args, **kwargs):
        if delay == 300:
            return
        return await original_sleep(delay, *args, **kwargs)

    DistributedLock.extend = mock_extend
    asyncio.sleep = mock_sleep

    try:
        t1 = asyncio.create_task(scheduler._run_loop(sleep_seconds=1, safety_window_minutes=5))
        await pull_started.wait()
        await extend_called.wait()

        # Give run_loop time to abort
        await asyncio.sleep(0.1)

        assert pull_aborted is True, "Pull task should be cancelled when heartbeat fails"
    finally:
        DistributedLock.extend = original_extend
        asyncio.sleep = original_sleep
        scheduler._running = False
        t1.cancel()

    print("test_scheduler_heartbeat_loss_aborts_cycle PASSED")

async def test_scheduler_heartbeat_exception_aborts_cycle():
    print("Running test_scheduler_heartbeat_exception_aborts_cycle...")
    redis = MockRedis()
    lock_manager.set_redis(redis)
    os.environ["DEPLOYMENT_ENV"] = "test"

    scheduler = ReservationPullScheduler()

    pull_started = asyncio.Event()
    pull_aborted = False

    async def mock_pull_long(*args, **kwargs):
        nonlocal pull_aborted
        pull_started.set()
        try:
            await asyncio.sleep(10.0)
        except asyncio.CancelledError:
            pull_aborted = True
            raise

    scheduler._pull_all_tenants = AsyncMock(side_effect=mock_pull_long)
    scheduler._running = True

    from infra.distributed_lock import DistributedLock
    original_extend = DistributedLock.extend
    original_sleep = asyncio.sleep

    extend_called = asyncio.Event()

    async def mock_extend(self, additional_time):
        extend_called.set()
        raise Exception("Redis connection lost")

    async def mock_sleep(delay, *args, **kwargs):
        if delay == 300:
            return
        return await original_sleep(delay, *args, **kwargs)

    DistributedLock.extend = mock_extend
    asyncio.sleep = mock_sleep

    try:
        t1 = asyncio.create_task(scheduler._run_loop(sleep_seconds=1, safety_window_minutes=5))
        await pull_started.wait()
        await extend_called.wait()

        await asyncio.sleep(0.1)

        assert pull_aborted is True, "Pull task should be cancelled when heartbeat throws exception"
    finally:
        DistributedLock.extend = original_extend
        asyncio.sleep = original_sleep
        scheduler._running = False
        t1.cancel()

    print("test_scheduler_heartbeat_exception_aborts_cycle PASSED")

async def test_scheduler_shutdown_cancels_pull_task():
    print("Running test_scheduler_shutdown_cancels_pull_task...")
    redis = MockRedis()
    lock_manager.set_redis(redis)
    os.environ["DEPLOYMENT_ENV"] = "test"

    scheduler = ReservationPullScheduler()

    pull_started = asyncio.Event()
    pull_aborted = False

    async def mock_pull_long(*args, **kwargs):
        nonlocal pull_aborted
        pull_started.set()
        try:
            await asyncio.sleep(10.0)
        except asyncio.CancelledError:
            pull_aborted = True
            raise

    scheduler._pull_all_tenants = AsyncMock(side_effect=mock_pull_long)
    scheduler._running = True

    t1 = asyncio.create_task(scheduler._run_loop(sleep_seconds=1, safety_window_minutes=5))
    await pull_started.wait()

    # Cancel the scheduler itself
    t1.cancel()

    try:
        await t1
    except asyncio.CancelledError:
        pass

    assert pull_aborted is True, "Pull task should be cancelled when scheduler shuts down"
    print("test_scheduler_shutdown_cancels_pull_task PASSED")

async def test_scheduler_acquire_exception_skips_cycle():
    print("Running test_scheduler_acquire_exception_skips_cycle...")
    redis = MockRedis()
    lock_manager.set_redis(redis)
    os.environ["DEPLOYMENT_ENV"] = "test"

    scheduler = ReservationPullScheduler()
    pull_calls = []

    async def mock_pull(*args, **kwargs):
        pull_calls.append(1)

    scheduler._pull_all_tenants = AsyncMock(side_effect=mock_pull)
    scheduler._running = True

    # Patch DistributedLock.acquire to throw an exception
    from infra.distributed_lock import DistributedLock
    original_acquire = DistributedLock.acquire

    async def mock_acquire(self):
        raise Exception("Connection reset by peer during SET")

    DistributedLock.acquire = mock_acquire

    try:
        t1 = asyncio.create_task(scheduler._run_loop(sleep_seconds=1, safety_window_minutes=5))
        # Wait slightly to let loop run the try/except logic
        await asyncio.sleep(0.1)

        assert len(pull_calls) == 0, "Provider should not be called if lock acquisition throws an exception"
        assert not t1.done(), "Scheduler task should not crash and should still be running"
    finally:
        DistributedLock.acquire = original_acquire
        scheduler._running = False
        t1.cancel()

    print("test_scheduler_acquire_exception_skips_cycle PASSED")

async def main():
    try:
        await test_scheduler_concurrency_only_one_worker_runs()
        await test_scheduler_concurrency_redis_unavailable()
        await test_scheduler_concurrency_long_cycle()
        await test_scheduler_concurrency_lock_release(MockRedis())
        await test_scheduler_heartbeat_extends_lock()
        await test_scheduler_different_hostnames_same_key()
        await test_scheduler_heartbeat_loss_aborts_cycle()
        await test_scheduler_heartbeat_exception_aborts_cycle()
        await test_scheduler_shutdown_cancels_pull_task()
        await test_scheduler_acquire_exception_skips_cycle()
        print("All tests PASSED!")
    except AssertionError as e:
        print(f"TEST FAILED: {e}")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
