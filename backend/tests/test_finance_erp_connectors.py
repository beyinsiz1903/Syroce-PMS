import pytest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
import httpx

from models.schemas import User
from routers.finance.integrations import router as finance_router

app = FastAPI()
app.include_router(finance_router)

@pytest.fixture
def mock_user():
    return User(
        id="test-admin",
        tenant_id="tenant-1",
        email="admin@test.com",
        name="Test Admin",
        role="super_admin",
        permissions=["view_system_diagnostics"]
    )

@pytest.fixture
def client(mock_user):
    from core.security import get_current_user
    app.dependency_overrides[get_current_user] = lambda: mock_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@patch("routers.finance.integrations._gather_invoices", new_callable=AsyncMock)
@patch("routers.finance.integrations._gather_payments", new_callable=AsyncMock)
@patch("routers.finance.integrations._log_accounting_sync", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_logo_sync_no_data(mock_log, mock_payments, mock_invoices, client):
    # Setup no data
    mock_invoices.return_value = []
    mock_payments.return_value = []
    
    response = client.post("/finance/logo-integration/sync")
    
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "noop"
    assert data["success"] is True
    assert data["synced_invoices"] == 0
    
    mock_log.assert_called_once()
    log_arg = mock_log.call_args[0][1]
    assert log_arg["status"] == "noop"
    assert log_arg["synced_invoices"] == 0


@patch("routers.finance.integrations.get_decrypted_credentials", new_callable=AsyncMock)
@patch("routers.finance.integrations._gather_invoices", new_callable=AsyncMock)
@patch("routers.finance.integrations._gather_payments", new_callable=AsyncMock)
@patch("routers.finance.integrations._log_accounting_sync", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_logo_sync_missing_credentials(mock_log, mock_payments, mock_invoices, mock_creds, client):
    # Setup some data
    mock_invoices.return_value = [{"invoice_number": "INV-1"}]
    mock_payments.return_value = []
    
    # Missing credentials
    mock_creds.return_value = None
    
    response = client.post("/finance/logo-integration/sync")
    
    assert response.status_code == 409
    assert "No credentials configured" in response.json()["detail"]
    mock_log.assert_not_called()


@patch("httpx.AsyncClient.post", new_callable=AsyncMock)
@patch("routers.finance.integrations.get_decrypted_credentials", new_callable=AsyncMock)
@patch("routers.finance.integrations._gather_invoices", new_callable=AsyncMock)
@patch("routers.finance.integrations._gather_payments", new_callable=AsyncMock)
@patch("routers.finance.integrations._log_accounting_sync", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_logo_sync_connection_error(mock_log, mock_payments, mock_invoices, mock_creds, mock_post, client):
    mock_invoices.return_value = [{"invoice_number": "INV-1"}]
    mock_payments.return_value = []
    mock_creds.return_value = {"api_url": "https://logo.example", "api_key": "secret"}
    
    # Simulate connection error
    mock_post.side_effect = httpx.RequestError("Connection failed")
    
    response = client.post("/finance/logo-integration/sync")
    
    assert response.status_code == 502
    assert "Connection error" in response.json()["detail"]
    
    mock_log.assert_called_once()
    log_arg = mock_log.call_args[0][1]
    assert log_arg["status"] == "failed"
    assert log_arg["error_type"] == "connection_error"


@patch("httpx.AsyncClient.post", new_callable=AsyncMock)
@patch("routers.finance.integrations.get_decrypted_credentials", new_callable=AsyncMock)
@patch("routers.finance.integrations._gather_invoices", new_callable=AsyncMock)
@patch("routers.finance.integrations._gather_payments", new_callable=AsyncMock)
@patch("routers.finance.integrations._log_accounting_sync", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_netsis_sync_timeout(mock_log, mock_payments, mock_invoices, mock_creds, mock_post, client):
    mock_invoices.return_value = [{"invoice_number": "INV-1"}]
    mock_payments.return_value = []
    mock_creds.return_value = {"api_url": "https://netsis.example", "api_key": "secret"}
    
    # Simulate timeout
    mock_post.side_effect = httpx.TimeoutException("Read timeout")
    
    response = client.post("/finance/netsis-integration/sync")
    
    assert response.status_code == 504
    assert "Timeout while syncing" in response.json()["detail"]
    
    mock_log.assert_called_once()
    log_arg = mock_log.call_args[0][1]
    assert log_arg["status"] == "failed"
    assert log_arg["error_type"] == "timeout"


@patch("httpx.AsyncClient.post", new_callable=AsyncMock)
@patch("routers.finance.integrations.get_decrypted_credentials", new_callable=AsyncMock)
@patch("routers.finance.integrations._gather_invoices", new_callable=AsyncMock)
@patch("routers.finance.integrations._gather_payments", new_callable=AsyncMock)
@patch("routers.finance.integrations._log_accounting_sync", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_logo_sync_success(mock_log, mock_payments, mock_invoices, mock_creds, mock_post, client):
    mock_invoices.return_value = [{"invoice_number": "INV-1"}]
    mock_payments.return_value = []
    mock_creds.return_value = {"api_url": "https://logo.example", "api_key": "secret"}
    
    # Simulate 200 OK
    mock_response = httpx.Response(status_code=200, text="OK")
    mock_post.return_value = mock_response
    
    # Mock log response needs an ID
    mock_log.return_value = {"id": "log-123"}
    
    response = client.post("/finance/logo-integration/sync")
    
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["synced_invoices"] == 1
    
    mock_log.assert_called_once()
    log_arg = mock_log.call_args[0][1]
    assert log_arg["status"] == "success"
    assert log_arg["provider_response_status"] == 200
    
    # Ensure X-Syroce-Sync-Id is sent
    mock_post.assert_called_once()
    headers = mock_post.call_args[1].get("headers", {})
    assert "X-Syroce-Sync-Id" in headers
