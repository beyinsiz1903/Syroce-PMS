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


@pytest.mark.asyncio
async def test_ari_drift_unsupported_provider(client):
    payload = {
        "tenant_id": "tenant-1",
        "property_id": "prop-1",
        "provider": "unknown_provider"
    }
    response = client.post("/api/channel-manager/ari/drift/check", json=payload)
    assert response.status_code == 400
    assert "Unknown provider" in response.json()["detail"]


@patch("domains.channel_manager.ari.router.build_pms_ari_snapshot")
@pytest.mark.asyncio
async def test_ari_drift_provider_unavailable(mock_build, client):
    # build_pms_ari_snapshot doesn't throw
    mock_build.return_value = [{"room_type_code": "R1", "rate_plan_code": "RP1", "date": "2024-01-01", "availability": 5}]
    
    # But HotelRunner adapter will raise ProviderSnapshotUnavailable
    payload = {
        "tenant_id": "tenant-1",
        "property_id": "prop-1",
        "provider": "hotelrunner"
    }
    
    with patch("domains.channel_manager.ari.drift_worker.repo.upsert_drift_state", new_callable=AsyncMock) as mock_upsert:
        response = client.post("/api/channel-manager/ari/drift/check", json=payload)
        
        # Must fail-closed with 502
        assert response.status_code == 502
        assert "not yet implemented" in response.json()["detail"]
        
        # Must NOT have written any drift states (no fake "drift false" or "matched")
        mock_upsert.assert_not_called()


@patch("domains.channel_manager.ari.router._get_snapshot_adapter")
@patch("domains.channel_manager.ari.router.build_pms_ari_snapshot")
@pytest.mark.asyncio
async def test_ari_drift_credentials_missing(mock_build, mock_get_adapter, client):
    mock_build.return_value = []
    
    mock_adapter = AsyncMock()
    mock_adapter.fetch_snapshot.side_effect = CredentialsMissing("No credentials configured for tenant")
    mock_get_adapter.return_value = mock_adapter
    
    payload = {
        "tenant_id": "tenant-1",
        "property_id": "prop-1",
        "provider": "hotelrunner"
    }
    
    response = client.post("/api/channel-manager/ari/drift/check", json=payload)
    assert response.status_code == 409
    assert "No credentials" in response.json()["detail"]


@patch("domains.channel_manager.ari.router._get_snapshot_adapter")
@patch("domains.channel_manager.ari.router.build_pms_ari_snapshot")
@pytest.mark.asyncio
async def test_ari_drift_successful_reconciliation_no_drift(mock_build, mock_get_adapter, client):
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
    
    with patch("domains.channel_manager.ari.drift_worker.repo.upsert_drift_state", new_callable=AsyncMock) as mock_upsert:
        response = client.post("/api/channel-manager/ari/drift/check", json=payload)
        
        assert response.status_code == 200
        data = response.json()
        assert data["matched"] == 1
        assert data["drifts_found"] == 0
        
        # It should record the matched state
        mock_upsert.assert_called()
        call_args = mock_upsert.call_args[0][0]
        assert call_args["drift_detected"] is False


@patch("domains.channel_manager.ari.router._get_snapshot_adapter")
@patch("domains.channel_manager.ari.router.build_pms_ari_snapshot")
@pytest.mark.asyncio
async def test_ari_drift_successful_reconciliation_with_drift(mock_build, mock_get_adapter, client):
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
    
    with patch("domains.channel_manager.ari.drift_worker.repo.upsert_drift_state", new_callable=AsyncMock) as mock_upsert:
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
