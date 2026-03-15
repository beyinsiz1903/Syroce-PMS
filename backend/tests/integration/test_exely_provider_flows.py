"""
Exely Provider — Integration Tests
=====================================

Tests the full integration flow:
- Provider facade end-to-end with mocked SOAP transport
- Legacy interface backward compatibility
- Error propagation through the full stack
- Call site wiring verification
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from domains.channel_manager.providers.exely import ExelyProvider, ProviderResult
from domains.channel_manager.providers.exely.errors import (
    ExelyError,
    ExelyAuthError,
    ExelyTemporaryError,
    ExelyRateLimitError,
    ExelyPayloadError,
)
from domains.channel_manager.providers.exely.retry import ExelyRetryPolicy
from domains.channel_manager.providers.exely import observability as obs


# Sample SOAP responses
_AVAIL_RS = b"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ota="http://www.opentravel.org/OTA/2003/05">
  <soapenv:Body>
    <ota:OTA_HotelAvailRS>
      <ota:RoomStay>
        <ota:RoomType RoomTypeCode="DBL" RoomDescription="Double Room" NumberOfUnits="5"/>
        <ota:RatePlan RatePlanCode="BAR" RatePlanName="Best Available Rate"/>
      </ota:RoomStay>
    </ota:OTA_HotelAvailRS>
  </soapenv:Body>
</soapenv:Envelope>"""

_READ_RS = b"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ota="http://www.opentravel.org/OTA/2003/05">
  <soapenv:Body>
    <ota:OTA_ResRetrieveRS>
      <ota:HotelReservation ResStatus="Commit" CreateDateTime="2025-06-01T10:00:00">
        <ota:UniqueID Type="14" ID="RES001"/>
        <ota:ResGuest>
          <ota:Profiles>
            <ota:Profile>
              <ota:Customer>
                <ota:PersonName>
                  <ota:GivenName>Ali</ota:GivenName>
                  <ota:Surname>Yilmaz</ota:Surname>
                </ota:PersonName>
              </ota:Customer>
            </ota:Profile>
          </ota:Profiles>
        </ota:ResGuest>
        <ota:RoomStay>
          <ota:RoomType RoomTypeCode="DBL"/>
          <ota:RatePlan RatePlanCode="BAR"/>
          <ota:GuestCount AgeQualifyingCode="10" Count="2"/>
          <ota:TimeSpan Start="2025-06-15" End="2025-06-20"/>
          <ota:Total AmountAfterTax="1500.00" CurrencyCode="TRY"/>
        </ota:RoomStay>
        <ota:ResGlobalInfo>
          <ota:Total AmountAfterTax="1500.00" CurrencyCode="TRY"/>
        </ota:ResGlobalInfo>
      </ota:HotelReservation>
    </ota:OTA_ResRetrieveRS>
  </soapenv:Body>
</soapenv:Envelope>"""

_SUCCESS_RS = b"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ota="http://www.opentravel.org/OTA/2003/05">
  <soapenv:Body>
    <ota:OTA_NotifReportRS>
      <ota:Success/>
    </ota:OTA_NotifReportRS>
  </soapenv:Body>
</soapenv:Envelope>"""


class TestProviderFacadeIntegration:
    """Full flow tests through the provider facade."""

    @pytest.mark.asyncio
    async def test_full_connection_flow(self):
        """Test connection → discover rooms → pull reservations."""
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")

        with patch.object(provider._transport, "send_soap", new_callable=AsyncMock) as mock:
            # Step 1: Test connection
            mock.return_value = _AVAIL_RS
            conn_result = await provider.test_connection()
            assert conn_result.success is True
            assert conn_result.data["connected"] is True

            # Step 2: Discover rooms
            rooms_result = await provider.discover_rooms("2025-06-01", "2025-06-02")
            assert rooms_result.success is True
            assert len(rooms_result.data["room_types"]) == 1

            # Step 3: Pull reservations
            mock.return_value = _READ_RS
            pull_result = await provider.pull_reservations(from_date="2025-06-01", to_date="2025-06-15")
            assert pull_result.success is True
            assert pull_result.data["count"] == 1
            assert pull_result.data["reservations"][0]["reservation_id"] == "RES001"

    @pytest.mark.asyncio
    async def test_full_ari_push_flow(self):
        """Test ARI push with validation → build → send → parse."""
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")

        with patch.object(provider._transport, "send_soap", new_callable=AsyncMock) as mock:
            mock.return_value = _SUCCESS_RS
            result = await provider.push_ari(
                room_type_code="DBL",
                rate_plan_code="BAR",
                start_date="2025-07-01",
                end_date="2025-07-10",
                availability=5,
                rate_amount=200.0,
                min_stay=2,
            )
            assert result.success is True
            # Verify the SOAP envelope was built correctly
            call_args = mock.call_args
            xml_body = call_args[0][0]
            assert "OTA_HotelAvailNotifRQ" in xml_body
            assert "DBL" in xml_body
            assert "BAR" in xml_body


class TestLegacyCompatibility:
    """Verify legacy dict interface still works for all call sites."""

    @pytest.mark.asyncio
    async def test_legacy_test_connection_dict_format(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        with patch.object(provider._transport, "send_soap", new_callable=AsyncMock) as mock:
            mock.return_value = _AVAIL_RS
            result = await provider.legacy_test_connection()
            assert isinstance(result, dict)
            assert result["connected"] is True
            assert "room_types" in result
            assert "rate_plans" in result
            assert "duration_ms" in result

    @pytest.mark.asyncio
    async def test_legacy_pull_reservations_dict_format(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        with patch.object(provider._transport, "send_soap", new_callable=AsyncMock) as mock:
            mock.return_value = _READ_RS
            result = await provider.legacy_pull_reservations(from_date="2025-06-01", to_date="2025-06-15")
            assert isinstance(result, dict)
            assert result["success"] is True
            assert isinstance(result["reservations"], list)
            assert "count" in result
            assert "duration_ms" in result

    @pytest.mark.asyncio
    async def test_legacy_discover_rooms_dict_format(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        with patch.object(provider._transport, "send_soap", new_callable=AsyncMock) as mock:
            mock.return_value = _AVAIL_RS
            result = await provider.legacy_discover_rooms("2025-06-01", "2025-06-02")
            assert isinstance(result, dict)
            assert result["success"] is True
            assert isinstance(result["room_types"], list)
            assert isinstance(result["rate_plans"], list)

    @pytest.mark.asyncio
    async def test_legacy_push_ari_dict_format(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        with patch.object(provider._transport, "send_soap", new_callable=AsyncMock) as mock:
            mock.return_value = _SUCCESS_RS
            result = await provider.legacy_push_ari(
                room_type_code="DBL", rate_plan_code="BAR",
                start_date="2025-07-01", end_date="2025-07-10",
            )
            assert isinstance(result, dict)
            assert result["success"] is True

    @pytest.mark.asyncio
    async def test_legacy_confirm_delivery_dict_format(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        with patch.object(provider._transport, "send_soap", new_callable=AsyncMock) as mock:
            mock.return_value = _SUCCESS_RS
            result = await provider.legacy_confirm_delivery("RES001", "CONF001")
            assert isinstance(result, dict)
            assert result["success"] is True


class TestErrorPropagation:
    """Test that errors propagate correctly through the full stack."""

    @pytest.mark.asyncio
    async def test_auth_error_no_retry(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        provider._retry = ExelyRetryPolicy(max_retries=3, base_delay=0.01)
        call_count = 0

        async def auth_fail(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            raise ExelyAuthError("WSSE failed")

        with patch.object(provider._transport, "send_soap", side_effect=auth_fail):
            result = await provider.test_connection()
            assert result.success is False
            assert result.error_type == "ExelyAuthError"
            assert call_count == 1  # No retry for auth errors

    @pytest.mark.asyncio
    async def test_temporary_error_retries(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        provider._retry = ExelyRetryPolicy(max_retries=2, base_delay=0.01)
        call_count = 0

        async def flaky(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ExelyTemporaryError("server error")
            return _AVAIL_RS

        with patch.object(provider._transport, "send_soap", side_effect=flaky):
            result = await provider.test_connection()
            assert result.success is True
            assert call_count == 3

    @pytest.mark.asyncio
    async def test_rate_limit_error_retries(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        provider._retry = ExelyRetryPolicy(max_retries=1, base_delay=0.01)
        call_count = 0

        async def rate_limited(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ExelyRateLimitError(retry_after_seconds=0)
            return _AVAIL_RS

        with patch.object(provider._transport, "send_soap", side_effect=rate_limited):
            result = await provider.test_connection()
            assert result.success is True
            assert call_count == 2


class TestObservabilityIntegration:
    """Verify observability records are created during provider operations."""

    def setup_method(self):
        obs.reset_metrics()

    @pytest.mark.asyncio
    async def test_success_recorded(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        with patch.object(provider._transport, "send_soap", new_callable=AsyncMock) as mock:
            mock.return_value = _AVAIL_RS
            await provider.test_connection()
            health = obs.get_provider_health()
            assert health["success_count"] >= 1
            assert health["call_count"] >= 1

    @pytest.mark.asyncio
    async def test_failure_recorded(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        with patch.object(provider._transport, "send_soap", new_callable=AsyncMock) as mock:
            mock.side_effect = ExelyAuthError("fail")
            await provider.test_connection()
            health = obs.get_provider_health()
            assert health["error_count"] >= 1


class TestCredentialsIntegration:
    """Test credentials dict initialization (used by provider_config_router)."""

    def test_init_from_config_router_format(self):
        """Credentials format from provider_config_router."""
        creds = {
            "username": "test_user",
            "password": "test_pass",
            "hotel_code": "H001",
            "endpoint_url": "https://custom.exely.com/ota/OTA",
        }
        provider = ExelyProvider(credentials=creds)
        assert provider._username == "test_user"

    def test_init_from_snapshot_collector_format(self):
        """Credentials format from snapshot_collectors."""
        creds = {
            "username": "snap_user",
            "password": "snap_pass",
            "hotel_id": "H002",  # Note: hotel_id not hotel_code
            "soap_url": "https://alt.exely.com/ota/OTA",
        }
        provider = ExelyProvider(credentials=creds)
        assert provider._hotel_code == "H002"
