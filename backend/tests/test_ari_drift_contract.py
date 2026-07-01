import pytest
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from models.schemas import User

from domains.channel_manager.ari.router import router as ari_router
from domains.channel_manager.ari.provider_snapshot_contract import (
    ProviderSnapshotUnavailable,
    CredentialsMissing,
    UnsupportedProvider,
)

app = FastAPI()
app.include_router(ari_router)


@pytest.fixture
def mock_user():
    return User(
        id="test-admin",
        tenant_id="tenant-1",
        email="admin@test.com",
        name="Test Admin",
        role="super_admin",
        permissions=["manage_channel_connectors"]
    )


@pytest.fixture
def client(mock_user):
    from core.security import get_current_user
    app.dependency_overrides[get_current_user] = lambda: mock_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@patch("domains.channel_manager.ari.router.get_tenant_rollout_config", new_callable=AsyncMock)
@pytest.mark.asyncio
async def test_ari_drift_unsupported_provider(mock_rollout, client):
    mock_rollout.return_value = {"channel_ari_enabled": True}
    payload = {
        "tenant_id": "tenant-1",
        "property_id": "prop-1",
        "provider": "unknown_provider"
    }
    response = client.post("/api/channel-manager/ari/drift/check", json=payload)
    assert response.status_code == 400
    assert "Unknown provider" in response.json()["detail"]


@patch("domains.channel_manager.ari.router.get_tenant_rollout_config", new_callable=AsyncMock)
@patch("domains.channel_manager.ari.router.get_decrypted_credentials")
@patch("domains.channel_manager.ari.router._get_snapshot_adapter")
@patch("domains.channel_manager.ari.router.build_pms_ari_snapshot")
@pytest.mark.asyncio
async def test_ari_drift_provider_unavailable(mock_build, mock_get_adapter, mock_creds, mock_rollout, client):
    mock_rollout.return_value = {"channel_ari_enabled": True}
    mock_creds.return_value = {"api_key": "fake"}
    # build_pms_ari_snapshot doesn't throw
    mock_build.return_value = [{"room_type_code": "R1", "rate_plan_code": "RP1", "date": "2024-01-01", "availability": 5}]
    
    # But HotelRunner adapter will raise ProviderSnapshotUnavailable
    mock_adapter = AsyncMock()
    mock_adapter.fetch_snapshot.side_effect = ProviderSnapshotUnavailable("not yet implemented")
    mock_get_adapter.return_value = mock_adapter

    payload = {
        "tenant_id": "tenant-1",
        "property_id": "prop-1",
        "provider": "hotelrunner"
    }
    
    with patch("domains.channel_manager.ari.router.repo.upsert_drift_state", new_callable=AsyncMock) as mock_upsert:
        response = client.post("/api/channel-manager/ari/drift/check", json=payload)
        
        # Must fail-closed with 502
        assert response.status_code == 502
        assert "not yet implemented" in response.json()["detail"]
        
        # Should have written SYSTEM error drift state
        mock_upsert.assert_called_once()
        args = mock_upsert.call_args[0][0]
        assert args["drift_type"] == "provider_unavailable"
        assert args["room_type_code"] == "SYSTEM"


@patch("domains.channel_manager.ari.router.get_tenant_rollout_config", new_callable=AsyncMock)
@patch("domains.channel_manager.ari.router.get_decrypted_credentials")
@pytest.mark.asyncio
async def test_ari_drift_credentials_missing(mock_creds, mock_rollout, client):
    mock_rollout.return_value = {"channel_ari_enabled": True}
    
    # Simulate missing credentials
    mock_creds.side_effect = CredentialsMissing("No active default credentials found for provider.")
    
    payload = {
        "tenant_id": "tenant-1",
        "property_id": "prop-1",
        "provider": "hotelrunner"
    }
    
    with patch("domains.channel_manager.ari.router.repo.upsert_drift_state", new_callable=AsyncMock) as mock_upsert:
        response = client.post("/api/channel-manager/ari/drift/check", json=payload)
        
    assert response.status_code == 409
    assert "No active default" in response.json()["detail"]
    mock_upsert.assert_called_once()
    assert mock_upsert.call_args[0][0]["drift_type"] == "credentials_missing"


@patch("domains.channel_manager.ari.router.get_tenant_rollout_config", new_callable=AsyncMock)
@patch("domains.channel_manager.ari.router.get_decrypted_credentials")
@patch("domains.channel_manager.ari.router._get_snapshot_adapter")
@patch("domains.channel_manager.ari.router.build_pms_ari_snapshot")
@pytest.mark.asyncio
async def test_ari_drift_successful_reconciliation_no_drift(mock_build, mock_get_adapter, mock_creds, mock_rollout, client):
    mock_rollout.return_value = {"channel_ari_enabled": True}
    mock_creds.return_value = {"api_key": "fake"}
    # Both PMS and Provider return exact same snapshot
    snapshot = [
        {
            "room_type_code": "STD",
            "rate_plan_code": "BB",
            "date": "2024-01-01",
            "availability": 5,
            "rate": 100.0,
            "restrictions": {}
        }
    ]
    mock_build.return_value = snapshot
    
    mock_adapter = AsyncMock()
    mock_adapter.fetch_snapshot.return_value = snapshot
    mock_get_adapter.return_value = mock_adapter
    
    payload = {
        "tenant_id": "tenant-1",
        "property_id": "prop-1",
        "provider": "exely"
    }
    
    with patch("domains.channel_manager.ari.drift_worker.repo.upsert_drift_state", new_callable=AsyncMock) as mock_upsert, \
         patch("domains.channel_manager.ari.router.repo.clear_system_drift_state", new_callable=AsyncMock) as mock_clear:
        response = client.post("/api/channel-manager/ari/drift/check", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["matched"] == 1
        assert data["drifts_found"] == 0
        
        # It should record the matched state
        mock_upsert.assert_called()
        call_args = mock_upsert.call_args[0][0]
        assert call_args["drift_detected"] is False


@patch("domains.channel_manager.ari.router.get_tenant_rollout_config", new_callable=AsyncMock)
@patch("domains.channel_manager.ari.router.get_decrypted_credentials")
@patch("domains.channel_manager.ari.router._get_snapshot_adapter")
@patch("domains.channel_manager.ari.router.build_pms_ari_snapshot")
@pytest.mark.asyncio
async def test_ari_drift_successful_reconciliation_with_drift(mock_build, mock_get_adapter, mock_creds, mock_rollout, client):
    mock_rollout.return_value = {"channel_ari_enabled": True}
    mock_creds.return_value = {"api_key": "fake"}
    # PMS has 5 available, Provider has 3 (drift!)
    pms_snapshot = [
        {
            "room_type_code": "STD",
            "rate_plan_code": "BB",
            "date": "2024-01-01",
            "availability": 5,
            "rate": 100.0,
            "restrictions": {}
        }
    ]
    provider_snapshot = [
        {
            "room_type_code": "STD",
            "rate_plan_code": "BB",
            "date": "2024-01-01",
            "availability": 3,
            "rate": 100.0,
            "restrictions": {}
        }
    ]
    
    mock_build.return_value = pms_snapshot
    
    mock_adapter = AsyncMock()
    mock_adapter.fetch_snapshot.return_value = provider_snapshot
    mock_get_adapter.return_value = mock_adapter
    
    payload = {
        "tenant_id": "tenant-1",
        "property_id": "prop-1",
        "provider": "hotelrunner"
    }
    
    with patch("domains.channel_manager.ari.drift_worker.repo.upsert_drift_state", new_callable=AsyncMock) as mock_upsert, \
         patch("domains.channel_manager.ari.router.repo.clear_system_drift_state", new_callable=AsyncMock) as mock_clear:
        response = client.post("/api/channel-manager/ari/drift/check", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["matched"] == 0
        assert data["drifts_found"] == 1
        assert data["drifts"][0]["drift_fields"] == ["availability"]
        
        # It should record the drift state
        mock_upsert.assert_called()
        call_args = mock_upsert.call_args[0][0]
        assert call_args["drift_detected"] is True
