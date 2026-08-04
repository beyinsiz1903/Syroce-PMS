import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bootstrap.phases.e_outbox import phase_e_outbox_and_eventbus
from core.integrations.invoice_dispatch_worker import InvoiceDispatchWorker
from core.integrations.invoice_lifecycle_worker import InvoiceLifecycleWorker
from core.integrations.invoice_reconciliation_worker import InvoiceReconciliationWorker
from core.integrations.invoice_status_worker import InvoiceStatusWorker
from models.schemas.nilvera_worker_health import NilveraWorkerStatus


class MockApp:
    def __init__(self):
        self.state = MagicMock()


@pytest.fixture
def mock_workers():
    dispatch = InvoiceDispatchWorker()
    status = InvoiceStatusWorker()
    recon = InvoiceReconciliationWorker()
    lifecycle = InvoiceLifecycleWorker()

    # Configure all to enabled by default for tests
    dispatch.configure(enabled=True)
    status.configure(enabled=True)
    recon.configure(enabled=True)
    lifecycle.configure(enabled=True)

    yield [dispatch, status, recon, lifecycle]

    # Cleanup tasks
    for w in [dispatch, status, recon, lifecycle]:
        w._stop_event.set()
        if w._task:
            w._task.cancel()


@pytest.mark.asyncio
async def test_1_initial_state_check(mock_workers):
    for w in mock_workers:
        # Before configure(), enabled=True, status=STOPPED
        assert w.health.status == NilveraWorkerStatus.STOPPED
        assert w.health.enabled is True
        assert w.health.task_alive is False
        assert w.health.processed_total == 0


@pytest.mark.asyncio
async def test_2_successful_start(mock_workers):
    for w in mock_workers:
        with patch.object(w, "_run_loop", new_callable=AsyncMock) if hasattr(w, "_run_loop") else patch.object(w, "_run", new_callable=AsyncMock):
            await w.start()
            assert w.health.status == NilveraWorkerStatus.RUNNING
            assert w.health.task_alive is True
            assert w.health.started_at is not None


@pytest.mark.asyncio
async def test_3_duplicate_start_prevention(mock_workers):
    for w in mock_workers:
        with patch.object(w, "_run_loop", new_callable=AsyncMock) if hasattr(w, "_run_loop") else patch.object(w, "_run", new_callable=AsyncMock) as mock_run:
            await w.start()
            task_ref = w._task
            await w.start()
            assert w._task is task_ref  # Same task, not recreated
            assert mock_run.call_count == 1


@pytest.mark.asyncio
async def test_4_heartbeat_progresses(mock_workers):
    w = mock_workers[0]
    w._record_heartbeat()
    hb1 = w.health.last_heartbeat_at
    await asyncio.sleep(0.01)
    w._record_heartbeat()
    hb2 = w.health.last_heartbeat_at
    assert hb2 > hb1
    assert w.health.task_alive is True


@pytest.mark.asyncio
async def test_5_last_success_at_updates(mock_workers):
    w = mock_workers[0]
    assert w.health.processed_total == 0
    w._record_success(2)
    assert w.health.processed_total == 2
    assert w.health.last_success_at is not None


@pytest.mark.asyncio
async def test_6_sanitized_health_after_error(mock_workers):
    w = mock_workers[0]
    w._record_job_error("MOCK_ERROR_CODE", fatal=False)
    assert w.health.job_failed_total == 1
    assert w.health.last_error_code == "MOCK_ERROR_CODE"
    assert w.health.status != NilveraWorkerStatus.FAILED  # Not a fatal loop error

    w._record_loop_error("FATAL_CRASH")
    w._mark_failed("Crash")
    assert w.health.loop_error_total == 1
    assert w.health.status == NilveraWorkerStatus.FAILED
    assert w.health.degraded_reason == "Crash"


@pytest.mark.asyncio
async def test_7_no_secret_leaks_in_health(mock_workers):
    w = mock_workers[0]
    w._record_job_error("MY_SECRET_KEY", fatal=False)
    # The developer shouldn't pass raw secrets, but ensure DTO dump is controlled
    dump = w.health.model_dump(mode="json")
    assert "api_key" not in dump
    assert "credential" not in dump
    rep = repr(w)
    assert "api_key" not in rep


@pytest.mark.asyncio
async def test_8_fatal_startup_when_enabled(monkeypatch):
    monkeypatch.setenv("NILVERA_ENABLED", "true")

    import core.integrations.nilvera.config as nilvera_cfg
    nilvera_cfg._config = None  # Force reload

    app = MockApp()

    # Mock one of the workers to fail during start
    with patch("core.integrations.invoice_dispatch_worker.invoice_dispatch_worker.start", side_effect=RuntimeError("Mock Start Fail")):
        with pytest.raises(RuntimeError, match="Mock Start Fail"):
            await phase_e_outbox_and_eventbus(app)


@pytest.mark.asyncio
async def test_9_disabled_state_when_configured_false(monkeypatch):
    monkeypatch.setenv("NILVERA_ENABLED", "false")
    import core.integrations.nilvera.config as nilvera_cfg
    nilvera_cfg._config = None

    app = MockApp()

    with patch("core.integrations.invoice_dispatch_worker.invoice_dispatch_worker.start") as mock_start:
        await phase_e_outbox_and_eventbus(app)
        assert mock_start.call_count == 0

    from core.integrations.invoice_dispatch_worker import invoice_dispatch_worker
    assert invoice_dispatch_worker.health.status == NilveraWorkerStatus.DISABLED
    assert invoice_dispatch_worker.health.enabled is False


@pytest.mark.asyncio
async def test_10_idempotent_shutdown(mock_workers):
    for w in mock_workers:
        with patch.object(w, "_run_loop", new_callable=AsyncMock) if hasattr(w, "_run_loop") else patch.object(w, "_run", new_callable=AsyncMock):
            await w.start()
            await w.stop()
            assert w.health.status == NilveraWorkerStatus.STOPPED
            assert w._task is None

            # Second stop should not raise
            await w.stop()
            assert w.health.status == NilveraWorkerStatus.STOPPED


@pytest.mark.asyncio
async def test_11_lifecycle_async_start(mock_workers):
    # Verify the lifecycle worker specifically has an async start
    w = mock_workers[3]
    assert asyncio.iscoroutinefunction(w.start)


@pytest.mark.asyncio
async def test_12_status_failure_no_dispatch_retry(mock_workers):
    # Status worker failures are just _record_job_error, and don't affect dispatch
    status_w = mock_workers[1]
    status_w._record_job_error("STATUS_ERR", fatal=False)
    assert status_w.health.job_failed_total == 1
    # Dispatch state is completely independent
    assert mock_workers[0].health.job_failed_total == 0


@pytest.mark.asyncio
async def test_13_reconciliation_no_post_calls():
    # Tested manually in code structure, but we can verify the service executes without POST
    # Since we can't easily mock the entire service here without duplicating its tests,
    # we assert the worker uses NilveraReadClient and not the main write client.
    import inspect

    from core.integrations.invoice_reconciliation_worker import InvoiceReconciliationWorker
    source = inspect.getsource(InvoiceReconciliationWorker._process_record)
    assert "NilveraReadClient" in source
    assert "client.post" not in source


@pytest.mark.asyncio
async def test_15_nilvera_enabled_missing(monkeypatch):
    monkeypatch.delenv("NILVERA_ENABLED", raising=False)
    import core.integrations.nilvera.config as nilvera_cfg
    nilvera_cfg._config = None

    app = MockApp()
    with pytest.raises(ValueError, match="NILVERA_ENABLED_MISSING"):
        await phase_e_outbox_and_eventbus(app)


@pytest.mark.asyncio
async def test_16_nilvera_enabled_invalid(monkeypatch, caplog):
    monkeypatch.setenv("NILVERA_ENABLED", "invalid_value")
    import core.integrations.nilvera.config as nilvera_cfg
    nilvera_cfg._config = None

    app = MockApp()
    with pytest.raises(ValueError, match="NILVERA_ENABLED_INVALID"):
        await phase_e_outbox_and_eventbus(app)

    # Assert raw value is not leaked in exception string or logs
    assert "invalid_value" not in caplog.text


@pytest.mark.asyncio
async def test_17_atomic_startup_rollback(monkeypatch):
    monkeypatch.setenv("NILVERA_ENABLED", "true")
    import core.integrations.nilvera.config as nilvera_cfg
    nilvera_cfg._config = None

    from core.integrations.invoice_dispatch_worker import invoice_dispatch_worker
    from core.integrations.invoice_lifecycle_worker import invoice_lifecycle_worker
    from core.integrations.invoice_reconciliation_worker import invoice_reconciliation_worker
    from core.integrations.invoice_status_worker import invoice_status_worker

    app = MockApp()

    # Make status worker fail to start.
    # Dispatch should be stopped.
    with patch.object(invoice_dispatch_worker, "start", new_callable=AsyncMock) as mock_disp_start, \
         patch.object(invoice_dispatch_worker, "stop", new_callable=AsyncMock) as mock_disp_stop, \
         patch.object(invoice_status_worker, "start", side_effect=RuntimeError("Status Start Fail")), \
         patch.object(invoice_status_worker, "stop", new_callable=AsyncMock) as mock_stat_stop, \
         patch.object(invoice_reconciliation_worker, "start", new_callable=AsyncMock) as mock_recon_start, \
         patch.object(invoice_lifecycle_worker, "start", new_callable=AsyncMock) as mock_life_start:

        with pytest.raises(RuntimeError, match="Status Start Fail"):
            await phase_e_outbox_and_eventbus(app)

        mock_disp_start.assert_called_once()
        mock_disp_stop.assert_called_once()
        mock_stat_stop.assert_not_called()
        mock_recon_start.assert_not_called()
        mock_life_start.assert_not_called()
