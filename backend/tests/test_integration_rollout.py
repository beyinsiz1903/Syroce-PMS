import pytest
from unittest.mock import patch, AsyncMock
from fastapi.testclient import TestClient

from fastapi import FastAPI
from routers.integration_rollout import router as rollout_router

app = FastAPI()
app.include_router(rollout_router)

@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client

@pytest.fixture
def override_deps():
    from core.security import get_current_user
    from models.schemas import User
    
    async def mock_user():
        return User(id="user-1", tenant_id="tenant-1", email="test@example.com", name="Test Admin", role="admin", roles=["admin"])
        
    app.dependency_overrides[get_current_user] = mock_user
    yield
    app.dependency_overrides = {}


@patch("routers.integration_rollout.get_tenant_rollout_config")
@patch("routers.integration_rollout.get_masked_credentials")
@patch("routers.integration_rollout.db")
@pytest.mark.asyncio
async def test_readiness_endpoint(mock_db, mock_creds, mock_config, override_deps, client):
    mock_config.return_value = {
        "finance_erp_enabled": False,
        "channel_ari_enabled": True,
        "drift_monitoring_enabled": True
    }
    
    # Mock credentials check: 
    # finance: loop logo, netsis (mock returns True for logo)
    # channel: hotelrunner, exely (mock returns False)
    async def mock_get_masked(tenant_id, provider, prop):
        if provider == "logo":
            return {"api_key": "***"}
        return None
        
    mock_creds.side_effect = mock_get_masked
    
    # Mock system drifts
    mock_cursor = AsyncMock()
    mock_cursor.to_list.return_value = []
    mock_db.__getitem__.return_value.find.return_value = mock_cursor
    
    response = client.get("/api/integration-rollout/readiness")
    assert response.status_code == 200
    data = response.json()
    
    assert data["config"]["channel_ari_enabled"] is True
    assert data["finance"]["status"] == "Ready"
    assert data["finance"]["configured"] is True
    assert data["channel"]["status"] == "Blocked"
    assert data["channel"]["configured"] is False


@patch("routers.integration_rollout.db")
@pytest.mark.asyncio
async def test_update_config_endpoint(mock_db, override_deps, client):
    mock_db.tenant_settings.update_one = AsyncMock()
    
    payload = {
        "finance_erp_enabled": True,
        "channel_ari_enabled": False,
        "drift_monitoring_enabled": False
    }
    response = client.post("/api/integration-rollout/config", json=payload)
    
    assert response.status_code == 200
    assert response.json()["success"] is True
    mock_db.tenant_settings.update_one.assert_called_once()
