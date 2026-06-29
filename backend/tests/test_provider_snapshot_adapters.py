import os
import json
import pytest
import httpx
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi import FastAPI
from fastapi.testclient import TestClient

from models.schemas import User
from domains.channel_manager.ari.router import router as ari_router
from domains.channel_manager.ari.provider_snapshot_contract import (
    ProviderSnapshotUnavailable,
    CredentialsMissing,
)
from domains.channel_manager.providers.hotelrunner.snapshot_adapter import HotelRunnerSnapshotAdapter
from domains.channel_manager.providers.exely.snapshot_adapter import ExelySnapshotAdapter
from domains.channel_manager.providers.hotelrunner.client import HttpResult

# Setup mock app for testing the router integration
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
        permissions=["manage_channel_connectors"],
    )


@pytest.fixture
def client(mock_user):
    from core.security import get_current_user

    app.dependency_overrides[get_current_user] = lambda: mock_user
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def load_fixture(filename, is_json=True):
    path = os.path.join(FIXTURES_DIR, filename)
    with open(path, "r", encoding="utf-8") as f:
        if is_json:
            return json.load(f)
        return f.read()


# ── HotelRunner Snapshot Adapter Tests ────────────────────────────────


@patch("domains.channel_manager.providers.hotelrunner.snapshot_adapter.HotelRunnerHttpClient")
@pytest.mark.asyncio
async def test_hotelrunner_snapshot_golden_path(mock_client_class):
    # Mock HttpResult response from HotelRunnerHttpClient.get
    mock_client = MagicMock()
    mock_client.get = AsyncMock()
    mock_client_class.return_value = mock_client
    mock_client.close = AsyncMock()

    avail_fixture = load_fixture("hr_avail_response.json")
    rates_fixture = load_fixture("hr_rates_response.json")

    mock_client.get.side_effect = [
        HttpResult(success=True, status_code=200, data=avail_fixture),
        HttpResult(success=True, status_code=200, data=rates_fixture),
    ]

    adapter = HotelRunnerSnapshotAdapter()
    creds = {"token": "valid_token", "hr_id": "valid_hr_id"}
    result = await adapter.fetch_snapshot(
        "tenant-1", "prop-1", creds, date_from="2026-06-29", date_to="2026-06-30"
    )

    assert len(result) == 2
    assert result[0]["room_type_code"] == "STD"
    assert result[0]["rate_plan_code"] == "BAR"
    assert result[0]["availability"] == 5
    assert result[0]["rate"] == 1500.0
    assert result[0]["restrictions"]["min_stay_through"] == 2
    assert result[0]["restrictions"]["stop_sell"] is False

    assert result[1]["room_type_code"] == "DLX"
    assert result[1]["rate_plan_code"] == "BAR"
    assert result[1]["availability"] == 3
    assert result[1]["rate"] == 2500.0
    assert result[1]["restrictions"]["min_stay_through"] == 1
    assert result[1]["restrictions"]["stop_sell"] is False


@pytest.mark.asyncio
async def test_hotelrunner_snapshot_credentials_missing():
    adapter = HotelRunnerSnapshotAdapter()
    with pytest.raises(CredentialsMissing):
        await adapter.fetch_snapshot(
            "tenant-1", "prop-1", {}, date_from="2026-06-29", date_to="2026-06-30"
        )


@patch("domains.channel_manager.providers.hotelrunner.snapshot_adapter.HotelRunnerHttpClient")
@pytest.mark.asyncio
async def test_hotelrunner_snapshot_api_error(mock_client_class):
    mock_client = MagicMock()
    mock_client.get = AsyncMock()
    mock_client_class.return_value = mock_client
    mock_client.close = AsyncMock()

    # Avail request succeeds but rates fails
    mock_client.get.side_effect = [
        HttpResult(success=True, status_code=200, data={"availability": []}),
        HttpResult(success=False, status_code=400, error="Invalid parameters"),
    ]

    adapter = HotelRunnerSnapshotAdapter()
    creds = {"token": "valid_token", "hr_id": "valid_hr_id"}
    with pytest.raises(ProviderSnapshotUnavailable) as exc:
        await adapter.fetch_snapshot(
            "tenant-1", "prop-1", creds, date_from="2026-06-29", date_to="2026-06-30"
        )
    assert "Invalid parameters" in str(exc.value)


@patch("domains.channel_manager.providers.hotelrunner.snapshot_adapter.HotelRunnerHttpClient")
@pytest.mark.asyncio
async def test_hotelrunner_snapshot_timeout(mock_client_class):
    mock_client = MagicMock()
    mock_client.get = AsyncMock()
    mock_client_class.return_value = mock_client
    mock_client.close = AsyncMock()

    mock_client.get.side_effect = httpx.TimeoutException("Read timed out")

    adapter = HotelRunnerSnapshotAdapter()
    creds = {"token": "valid_token", "hr_id": "valid_hr_id"}
    with pytest.raises(ProviderSnapshotUnavailable) as exc:
        await adapter.fetch_snapshot(
            "tenant-1", "prop-1", creds, date_from="2026-06-29", date_to="2026-06-30"
        )
    assert "connection failed" in str(exc.value)


# ── Exely Snapshot Adapter Tests ──────────────────────────────────────


@patch("domains.channel_manager.providers.exely.snapshot_adapter.ExelySoapTransport")
@pytest.mark.asyncio
async def test_exely_snapshot_golden_path(mock_transport_class):
    mock_transport = MagicMock()
    mock_transport_class.return_value = mock_transport

    exely_xml = load_fixture("exely_avail_rs.xml", is_json=False)
    mock_transport.send_soap = AsyncMock(return_value=exely_xml.encode("utf-8"))

    adapter = ExelySnapshotAdapter()
    creds = {
        "username": "exely_user",
        "password": "exely_password",
        "hotel_code": "exely_hotel_999",
        "api_url": "https://pmsconnect.prod.hopenapi.com/api/PMSConnect.svc",
    }
    result = await adapter.fetch_snapshot(
        "tenant-1", "prop-1", creds, date_from="2026-06-29", date_to="2026-06-30"
    )

    assert len(result) == 2
    assert result[0]["room_type_code"] == "STD"
    assert result[0]["rate_plan_code"] == "BAR"
    assert result[0]["date"] == "2026-06-29"
    assert result[0]["availability"] == 5
    assert result[0]["rate"] == 1500.0
    assert result[0]["restrictions"]["min_stay_through"] == 2
    assert result[0]["restrictions"]["stop_sell"] is False

    assert result[1]["room_type_code"] == "DLX"
    assert result[1]["rate_plan_code"] == "BAR"
    assert result[1]["date"] == "2026-06-29"
    assert result[1]["availability"] == 3
    assert result[1]["rate"] == 2500.0
    assert result[1]["restrictions"]["min_stay_through"] == 1
    assert result[1]["restrictions"]["stop_sell"] is False


@pytest.mark.asyncio
async def test_exely_snapshot_credentials_missing():
    adapter = ExelySnapshotAdapter()
    with pytest.raises(CredentialsMissing):
        await adapter.fetch_snapshot(
            "tenant-1", "prop-1", {}, date_from="2026-06-29", date_to="2026-06-30"
        )


@patch("domains.channel_manager.providers.exely.snapshot_adapter.ExelySoapTransport")
@pytest.mark.asyncio
async def test_exely_snapshot_soap_fault(mock_transport_class):
    mock_transport = MagicMock()
    mock_transport_class.return_value = mock_transport

    soap_fault_xml = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
      <soapenv:Body>
        <soapenv:Fault>
          <faultcode>soap:Server</faultcode>
          <faultstring>Internal Service Error</faultstring>
        </soapenv:Fault>
      </soapenv:Body>
    </soapenv:Envelope>"""
    mock_transport.send_soap = AsyncMock(return_value=soap_fault_xml.encode("utf-8"))

    adapter = ExelySnapshotAdapter()
    creds = {
        "username": "exely_user",
        "password": "exely_password",
        "hotel_code": "exely_hotel_999",
        "api_url": "https://pmsconnect.prod.hopenapi.com/api/PMSConnect.svc",
    }
    with pytest.raises(ProviderSnapshotUnavailable) as exc:
        await adapter.fetch_snapshot(
            "tenant-1", "prop-1", creds, date_from="2026-06-29", date_to="2026-06-30"
        )
    assert "SOAP Fault" in str(exc.value)


@patch("domains.channel_manager.providers.exely.snapshot_adapter.ExelySoapTransport")
@pytest.mark.asyncio
async def test_exely_snapshot_ota_errors(mock_transport_class):
    mock_transport = MagicMock()
    mock_transport_class.return_value = mock_transport

    ota_errors_xml = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
      <soapenv:Body>
        <OTA_HotelAvailRS xmlns="http://www.opentravel.org/OTA/2003/05" Version="1.0">
          <Errors>
            <Error Code="321">Hotel code not found</Error>
          </Errors>
        </OTA_HotelAvailRS>
      </soapenv:Body>
    </soapenv:Envelope>"""
    mock_transport.send_soap = AsyncMock(return_value=ota_errors_xml.encode("utf-8"))

    adapter = ExelySnapshotAdapter()
    creds = {
        "username": "exely_user",
        "password": "exely_password",
        "hotel_code": "exely_hotel_999",
        "api_url": "https://pmsconnect.prod.hopenapi.com/api/PMSConnect.svc",
    }
    with pytest.raises(ProviderSnapshotUnavailable) as exc:
        await adapter.fetch_snapshot(
            "tenant-1", "prop-1", creds, date_from="2026-06-29", date_to="2026-06-30"
        )
    assert "OTA Error [321]" in str(exc.value)


# ── Integration / Router Tests ────────────────────────────────────────


@patch("domains.channel_manager.ari.router.get_tenant_rollout_config", new_callable=AsyncMock)
@patch("domains.channel_manager.ari.router.get_decrypted_credentials")
@patch("domains.channel_manager.ari.router.repo")
@pytest.mark.asyncio
async def test_drift_check_router_credentials_missing(mock_repo, mock_creds, mock_rollout, client):
    mock_repo.upsert_drift_state = AsyncMock()
    mock_rollout.return_value = {"channel_ari_enabled": True}
    mock_creds.return_value = None  # Missing credentials triggers CredentialsMissing in router

    payload = {
        "tenant_id": "tenant-1",
        "property_id": "prop-1",
        "provider": "hotelrunner",
    }
    response = client.post("/api/channel-manager/ari/drift/check", json=payload)

    assert response.status_code == 409
    assert "No credentials configured" in response.json()["detail"]

    # Verify drift state is written with correct drift_type
    mock_repo.upsert_drift_state.assert_called_once()
    saved_state = mock_repo.upsert_drift_state.call_args[0][0]
    assert saved_state["drift_type"] == "credentials_missing"
    assert saved_state["room_type_code"] == "SYSTEM"


@patch("domains.channel_manager.ari.router.get_tenant_rollout_config", new_callable=AsyncMock)
@patch("domains.channel_manager.ari.router.get_decrypted_credentials")
@patch("domains.channel_manager.ari.router._get_snapshot_adapter")
@patch("domains.channel_manager.ari.router.build_pms_ari_snapshot")
@patch("domains.channel_manager.ari.router.repo")
@pytest.mark.asyncio
async def test_drift_check_router_provider_unavailable(
    mock_repo, mock_build, mock_get_adapter, mock_creds, mock_rollout, client
):
    mock_repo.upsert_drift_state = AsyncMock()
    mock_rollout.return_value = {"channel_ari_enabled": True}
    mock_creds.return_value = {"token": "t", "hr_id": "h"}
    mock_build.return_value = []

    # Mock the adapter to throw ProviderSnapshotUnavailable
    mock_adapter = AsyncMock()
    mock_adapter.fetch_snapshot.side_effect = ProviderSnapshotUnavailable("Service Down")
    mock_get_adapter.return_value = mock_adapter

    payload = {
        "tenant_id": "tenant-1",
        "property_id": "prop-1",
        "provider": "hotelrunner",
    }
    response = client.post("/api/channel-manager/ari/drift/check", json=payload)

    assert response.status_code == 502
    assert "Service Down" in response.json()["detail"]

    # Verify drift state is written with correct drift_type
    mock_repo.upsert_drift_state.assert_called_once()
    saved_state = mock_repo.upsert_drift_state.call_args[0][0]
    assert saved_state["drift_type"] == "provider_unavailable"
    assert saved_state["room_type_code"] == "SYSTEM"


# ── Sprint 2A.1 Hardening Tests ───────────────────────────────────────


@patch("domains.channel_manager.providers.hotelrunner.snapshot_adapter.HotelRunnerHttpClient")
@pytest.mark.asyncio
async def test_hotelrunner_malformed_quantity_raises_unavailable(mock_client_class):
    """qty='not-a-number' in availability response → ProviderSnapshotUnavailable."""
    mock_client = MagicMock()
    mock_client.get = AsyncMock()
    mock_client_class.return_value = mock_client
    mock_client.close = AsyncMock()

    mock_client.get.side_effect = [
        HttpResult(
            success=True,
            status_code=200,
            data={"availability": [{"room_code": "STD", "date": "2026-06-29", "quantity": "not-a-number"}]},
        ),
        HttpResult(
            success=True,
            status_code=200,
            data={"rates": [{"room_code": "STD", "date": "2026-06-29", "rate_code": "BAR", "price": 1500, "min_stay": 1, "stop_sell": False}]},
        ),
    ]

    adapter = HotelRunnerSnapshotAdapter()
    creds = {"token": "valid_token", "hr_id": "valid_hr_id"}
    with pytest.raises(ProviderSnapshotUnavailable) as exc:
        await adapter.fetch_snapshot("tenant-1", "prop-1", creds, date_from="2026-06-29", date_to="2026-06-30")
    assert "quantity" in str(exc.value)


@patch("domains.channel_manager.providers.hotelrunner.snapshot_adapter.HotelRunnerHttpClient")
@pytest.mark.asyncio
async def test_hotelrunner_malformed_price_raises_unavailable(mock_client_class):
    """price='bad_price' in rates response → ProviderSnapshotUnavailable."""
    mock_client = MagicMock()
    mock_client.get = AsyncMock()
    mock_client_class.return_value = mock_client
    mock_client.close = AsyncMock()

    mock_client.get.side_effect = [
        HttpResult(
            success=True,
            status_code=200,
            data={"availability": [{"room_code": "STD", "date": "2026-06-29", "quantity": 5}]},
        ),
        HttpResult(
            success=True,
            status_code=200,
            data={"rates": [{"room_code": "STD", "date": "2026-06-29", "rate_code": "BAR", "price": "bad_price", "min_stay": 1, "stop_sell": False}]},
        ),
    ]

    adapter = HotelRunnerSnapshotAdapter()
    creds = {"token": "valid_token", "hr_id": "valid_hr_id"}
    with pytest.raises(ProviderSnapshotUnavailable) as exc:
        await adapter.fetch_snapshot("tenant-1", "prop-1", creds, date_from="2026-06-29", date_to="2026-06-30")
    assert "price" in str(exc.value)


@patch("domains.channel_manager.providers.hotelrunner.snapshot_adapter.HotelRunnerHttpClient")
@pytest.mark.asyncio
async def test_hotelrunner_malformed_bool_stop_sell_raises_unavailable(mock_client_class):
    """stop_sell='garbage' (not bool-compatible string) → ProviderSnapshotUnavailable."""
    mock_client = MagicMock()
    mock_client.get = AsyncMock()
    mock_client_class.return_value = mock_client
    mock_client.close = AsyncMock()

    mock_client.get.side_effect = [
        HttpResult(
            success=True,
            status_code=200,
            data={"availability": [{"room_code": "STD", "date": "2026-06-29", "quantity": 5}]},
        ),
        HttpResult(
            success=True,
            status_code=200,
            data={"rates": [{"room_code": "STD", "date": "2026-06-29", "rate_code": "BAR", "price": 1500, "min_stay": 1, "stop_sell": "garbage"}]},
        ),
    ]

    adapter = HotelRunnerSnapshotAdapter()
    creds = {"token": "valid_token", "hr_id": "valid_hr_id"}
    with pytest.raises(ProviderSnapshotUnavailable) as exc:
        await adapter.fetch_snapshot("tenant-1", "prop-1", creds, date_from="2026-06-29", date_to="2026-06-30")
    assert "stop_sell" in str(exc.value)


@patch("domains.channel_manager.providers.hotelrunner.snapshot_adapter.HotelRunnerHttpClient")
@pytest.mark.asyncio
async def test_hotelrunner_string_false_stop_sell_parses_correctly(mock_client_class):
    """stop_sell='false' (string) must parse to False, not True (as naive bool() would)."""
    mock_client = MagicMock()
    mock_client.get = AsyncMock()
    mock_client_class.return_value = mock_client
    mock_client.close = AsyncMock()

    mock_client.get.side_effect = [
        HttpResult(
            success=True,
            status_code=200,
            data={"availability": [{"room_code": "STD", "date": "2026-06-29", "quantity": 5}]},
        ),
        HttpResult(
            success=True,
            status_code=200,
            data={"rates": [{"room_code": "STD", "date": "2026-06-29", "rate_code": "BAR", "price": 1500, "min_stay": 1, "stop_sell": "false"}]},
        ),
    ]

    adapter = HotelRunnerSnapshotAdapter()
    creds = {"token": "valid_token", "hr_id": "valid_hr_id"}
    result = await adapter.fetch_snapshot("tenant-1", "prop-1", creds, date_from="2026-06-29", date_to="2026-06-30")
    assert result[0]["restrictions"]["stop_sell"] is False


@patch("domains.channel_manager.providers.hotelrunner.snapshot_adapter.HotelRunnerHttpClient")
@pytest.mark.asyncio
async def test_hotelrunner_empty_snapshot_raises_unavailable(mock_client_class):
    """Valid HTTP response but no rates data → ProviderSnapshotUnavailable."""
    mock_client = MagicMock()
    mock_client.get = AsyncMock()
    mock_client_class.return_value = mock_client
    mock_client.close = AsyncMock()

    mock_client.get.side_effect = [
        HttpResult(success=True, status_code=200, data={"availability": []}),
        HttpResult(success=True, status_code=200, data={"rates": []}),
    ]

    adapter = HotelRunnerSnapshotAdapter()
    creds = {"token": "valid_token", "hr_id": "valid_hr_id"}
    with pytest.raises(ProviderSnapshotUnavailable) as exc:
        await adapter.fetch_snapshot("tenant-1", "prop-1", creds, date_from="2026-06-29", date_to="2026-06-30")
    assert "empty ARI snapshot" in str(exc.value)
    assert "refusing to clear drift state" in str(exc.value)


@pytest.mark.asyncio
async def test_exely_missing_api_url_raises_credentials_missing():
    """Exely credentials without api_url → CredentialsMissing (no test-endpoint fallback)."""
    adapter = ExelySnapshotAdapter()
    creds = {
        "username": "exely_user",
        "password": "exely_password",
        "hotel_code": "exely_hotel_999",
        # api_url intentionally absent
    }
    with pytest.raises(CredentialsMissing) as exc:
        await adapter.fetch_snapshot("tenant-1", "prop-1", creds, date_from="2026-06-29", date_to="2026-06-30")
    assert "api_url" in str(exc.value)


@patch("domains.channel_manager.providers.exely.snapshot_adapter.ExelySoapTransport")
@pytest.mark.asyncio
async def test_exely_empty_snapshot_raises_unavailable(mock_transport_class):
    """Exely response parses successfully but RoomStays contains no usable RoomRate → ProviderSnapshotUnavailable."""
    mock_transport = MagicMock()
    mock_transport_class.return_value = mock_transport

    empty_rs_xml = """<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
      <soapenv:Body>
        <OTA_HotelAvailRS xmlns="http://www.opentravel.org/OTA/2003/05" Version="1.0">
          <RoomStays/>
        </OTA_HotelAvailRS>
      </soapenv:Body>
    </soapenv:Envelope>"""
    mock_transport.send_soap = AsyncMock(return_value=empty_rs_xml.encode("utf-8"))

    adapter = ExelySnapshotAdapter()
    creds = {
        "username": "exely_user",
        "password": "exely_password",
        "hotel_code": "exely_hotel_999",
        "api_url": "https://pmsconnect.prod.hopenapi.com/api/PMSConnect.svc",
    }
    with pytest.raises(ProviderSnapshotUnavailable) as exc:
        await adapter.fetch_snapshot("tenant-1", "prop-1", creds, date_from="2026-06-29", date_to="2026-06-30")
    assert "empty ARI snapshot" in str(exc.value)
    assert "refusing to clear drift state" in str(exc.value)
