from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bootstrap.phases.e_outbox import phase_e_outbox_and_eventbus
from bootstrap.phases.shutdown import shutdown_all


@pytest.fixture
def mock_app():
    app = MagicMock()
    app.state = MagicMock()
    return app

@pytest.fixture
def mock_workers():
    with patch("core.integrations.invoice_dispatch_worker.invoice_dispatch_worker") as m_dispatch, \
         patch("core.integrations.invoice_reconciliation_worker.invoice_reconciliation_worker") as m_recon:

        m_dispatch.start = AsyncMock()
        m_dispatch.stop = AsyncMock()

        m_recon.start = AsyncMock()
        m_recon.stop = AsyncMock()

        yield m_dispatch, m_recon, m_dispatch, m_recon

@pytest.mark.asyncio
async def test_bootstrap_startup_starts_workers_once(mock_app, mock_workers):
    m_dispatch, m_recon, m_dispatch_sd, m_recon_sd = mock_workers
    await phase_e_outbox_and_eventbus(mock_app)

    m_dispatch.start.assert_called_once()
    m_recon.start.assert_called_once()

    # Test duplicate task/calls
    assert m_dispatch.start.call_count == 1
    assert m_recon.start.call_count == 1

@pytest.mark.asyncio
async def test_bootstrap_shutdown_stops_workers_idempotently(mock_app, mock_workers):
    m_dispatch, m_recon, m_dispatch_sd, m_recon_sd = mock_workers

    mock_app.state.invoice_dispatch_worker = m_dispatch_sd
    mock_app.state.invoice_reconciliation_worker = m_recon_sd

    await shutdown_all(mock_app)
    m_dispatch_sd.stop.assert_called_once()
    m_recon_sd.stop.assert_called_once()

    # idempotent
    await shutdown_all(mock_app)
    assert m_dispatch_sd.stop.call_count == 2
    assert m_recon_sd.stop.call_count == 2

@pytest.mark.asyncio
async def test_bootstrap_reconciliation_start_error_reraised(mock_app, mock_workers):
    m_dispatch, m_recon, m_dispatch_sd, m_recon_sd = mock_workers

    m_recon.start.side_effect = RuntimeError("Simulated startup failure")

    with pytest.raises(RuntimeError, match="Simulated startup failure"):
        await phase_e_outbox_and_eventbus(mock_app)
