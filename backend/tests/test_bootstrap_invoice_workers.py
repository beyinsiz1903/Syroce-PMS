from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bootstrap.phases.e_outbox import phase_e_outbox_and_eventbus
from bootstrap.phases.shutdown import shutdown_all


@pytest.fixture
def mock_app():
    app = MagicMock()
    app.state = MagicMock()
    return app


@pytest.fixture(autouse=True)
def enabled_nilvera_config(monkeypatch):
    monkeypatch.setenv("NILVERA_ENABLED", "true")
    import core.integrations.nilvera.config as nilvera_config

    nilvera_config._config = None
    yield
    nilvera_config._config = None

@pytest.fixture
def isolated_shutdown(monkeypatch):
    from unittest.mock import MagicMock
    mock_client = MagicMock()
    monkeypatch.setattr(
        "bootstrap.phases.shutdown.client",
        mock_client,
    )
    return mock_client

@pytest.fixture
def mock_workers():
    with (
        patch("core.integrations.invoice_dispatch_worker.invoice_dispatch_worker") as m_dispatch,
        patch("core.integrations.invoice_reconciliation_worker.invoice_reconciliation_worker") as m_recon,
        patch("core.integrations.invoice_status_worker.invoice_status_worker") as m_status,
        patch("core.integrations.invoice_lifecycle_worker.invoice_lifecycle_worker") as m_lifecycle,
        patch("core.integrations.incoming_invoice_sync_worker.incoming_invoice_sync_worker") as m_incoming,
    ):

        m_dispatch.start = AsyncMock()
        m_dispatch.stop = AsyncMock()

        m_recon.start = AsyncMock()
        m_recon.stop = AsyncMock()

        m_status.start = AsyncMock()
        m_status.stop = AsyncMock()

        m_lifecycle.start = AsyncMock()
        m_lifecycle.stop = AsyncMock()

        m_incoming.start = AsyncMock()
        m_incoming.stop = AsyncMock()

        yield m_dispatch, m_recon, m_status, m_lifecycle, m_incoming

@pytest.mark.asyncio
async def test_bootstrap_startup_starts_workers_once(mock_app, mock_workers):
    m_dispatch, m_recon, m_status, m_lifecycle, m_incoming = mock_workers
    await phase_e_outbox_and_eventbus(mock_app)

    m_dispatch.start.assert_called_once()
    m_recon.start.assert_called_once()
    m_status.start.assert_called_once()
    m_lifecycle.start.assert_called_once()
    m_incoming.start.assert_called_once()

    # Test duplicate task/calls
    assert m_dispatch.start.call_count == 1
    assert m_recon.start.call_count == 1
    assert m_status.start.call_count == 1
    assert m_lifecycle.start.call_count == 1
    assert m_incoming.start.call_count == 1

@pytest.mark.asyncio
async def test_bootstrap_shutdown_stops_workers_idempotently(mock_app, mock_workers, isolated_shutdown):
    m_dispatch, m_recon, m_status, m_lifecycle, m_incoming = mock_workers

    mock_app.state.invoice_dispatch_worker = m_dispatch
    mock_app.state.invoice_reconciliation_worker = m_recon
    mock_app.state.invoice_status_worker = m_status
    mock_app.state.invoice_lifecycle_worker = m_lifecycle
    mock_app.state.incoming_invoice_sync_worker = m_incoming

    await shutdown_all(mock_app)
    m_dispatch.stop.assert_called_once()
    m_recon.stop.assert_called_once()
    m_status.stop.assert_called_once()
    m_lifecycle.stop.assert_called_once()
    m_incoming.stop.assert_called_once()

    # idempotent
    await shutdown_all(mock_app)
    assert m_dispatch.stop.call_count == 2
    assert m_recon.stop.call_count == 2
    assert m_status.stop.call_count == 2
    assert m_lifecycle.stop.call_count == 2
    assert m_incoming.stop.call_count == 2

@pytest.mark.asyncio
async def test_bootstrap_reconciliation_start_error_reraised(mock_app, mock_workers):
    _, m_recon, _, _, _ = mock_workers

    m_recon.start.side_effect = RuntimeError("Simulated startup failure")

    with pytest.raises(RuntimeError, match="Simulated startup failure"):
        await phase_e_outbox_and_eventbus(mock_app)
