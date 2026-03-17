"""
Exely Provider — Unit Tests
==============================

Tests the production-grade Exely SOAP provider adapter.
Covers: errors, retry, validators, observability, client, provider facade.
"""
import asyncio
import pytest
import time
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

# ── Error Hierarchy ──────────────────────────────────────────────────

from domains.channel_manager.providers.exely.errors import (
    ExelyError,
    ExelyAuthError,
    ExelySOAPFaultError,
    ExelyTemporaryError,
    ExelyRateLimitError,
    ExelyPayloadError,
    ExelyParseError,
    ExelyMappingError,
    ExelyValidationError,
)


class TestExelyErrors:
    def test_base_error(self):
        e = ExelyError("test", recoverable=True)
        assert str(e) == "test"
        assert e.recoverable is True

    def test_auth_error_not_recoverable(self):
        e = ExelyAuthError()
        assert e.recoverable is False
        assert "authentication" in str(e).lower()

    def test_soap_fault_error(self):
        e = ExelySOAPFaultError(fault_code="Server", fault_string="Internal error")
        assert "Server" in str(e)
        assert "Internal error" in str(e)
        assert e.recoverable is False

    def test_soap_fault_recoverable(self):
        e = ExelySOAPFaultError(fault_code="Server", fault_string="Temporary", recoverable=True)
        assert e.recoverable is True

    def test_temporary_error_is_recoverable(self):
        e = ExelyTemporaryError("server error")
        assert e.recoverable is True

    def test_rate_limit_error(self):
        e = ExelyRateLimitError(retry_after_seconds=30)
        assert e.retry_after_seconds == 30
        assert e.recoverable is True

    def test_payload_error(self):
        e = ExelyPayloadError("bad request", details={"field": "x"})
        assert e.details == {"field": "x"}
        assert e.recoverable is False

    def test_parse_error_truncates(self):
        e = ExelyParseError("parse fail", raw_response="x" * 5000)
        assert len(e.raw_response) == 2000
        assert e.recoverable is False

    def test_mapping_error(self):
        e = ExelyMappingError("not found", entity_type="room", entity_id="R1")
        assert e.entity_type == "room"
        assert e.entity_id == "R1"

    def test_validation_error(self):
        e = ExelyValidationError("required", field="username")
        assert e.field == "username"
        assert e.recoverable is False

    def test_error_inheritance(self):
        """All errors inherit from ExelyError."""
        for cls in [
            ExelyAuthError, ExelySOAPFaultError, ExelyTemporaryError,
            ExelyRateLimitError, ExelyPayloadError, ExelyParseError,
            ExelyMappingError, ExelyValidationError,
        ]:
            assert issubclass(cls, ExelyError)
            assert issubclass(cls, Exception)


# ── Retry Policy ─────────────────────────────────────────────────────

from domains.channel_manager.providers.exely.retry import ExelyRetryPolicy


class TestExelyRetry:
    def test_non_retryable_errors(self):
        policy = ExelyRetryPolicy()
        assert policy.should_retry(ExelyAuthError(), 1) is False
        assert policy.should_retry(ExelyPayloadError(), 1) is False
        assert policy.should_retry(ExelyParseError(), 1) is False
        assert policy.should_retry(ExelyMappingError(), 1) is False
        assert policy.should_retry(ExelyValidationError(), 1) is False

    def test_retryable_errors(self):
        policy = ExelyRetryPolicy()
        assert policy.should_retry(ExelyTemporaryError(), 1) is True
        assert policy.should_retry(ExelyRateLimitError(), 1) is True

    def test_max_retries_respected(self):
        policy = ExelyRetryPolicy(max_retries=2)
        assert policy.should_retry(ExelyTemporaryError(), 2) is True
        assert policy.should_retry(ExelyTemporaryError(), 3) is False

    def test_backoff_increases(self):
        policy = ExelyRetryPolicy(base_delay=1.0, jitter=0.0)
        d0 = policy.get_backoff_seconds(0)
        d1 = policy.get_backoff_seconds(1)
        d2 = policy.get_backoff_seconds(2)
        assert d1 > d0
        assert d2 > d1

    def test_rate_limit_uses_retry_after(self):
        policy = ExelyRetryPolicy()
        e = ExelyRateLimitError(retry_after_seconds=45)
        delay = policy.get_backoff_seconds(0, e)
        assert delay == 45.0

    def test_max_delay_cap(self):
        policy = ExelyRetryPolicy(base_delay=100.0, max_delay=120.0, jitter=0.0)
        delay = policy.get_backoff_seconds(10)
        assert delay <= 120.0

    @pytest.mark.asyncio
    async def test_execute_success_no_retry(self):
        policy = ExelyRetryPolicy()
        call_count = 0

        async def ok():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await policy.execute(ok)
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_execute_retries_on_temporary(self):
        policy = ExelyRetryPolicy(max_retries=2, base_delay=0.01)
        call_count = 0

        async def flaky():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ExelyTemporaryError("transient")
            return "ok"

        result = await policy.execute(flaky)
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_execute_raises_on_non_retryable(self):
        policy = ExelyRetryPolicy(max_retries=3, base_delay=0.01)
        call_count = 0

        async def auth_fail():
            nonlocal call_count
            call_count += 1
            raise ExelyAuthError("bad creds")

        with pytest.raises(ExelyAuthError):
            await policy.execute(auth_fail)
        assert call_count == 1  # No retry


# ── Validators ───────────────────────────────────────────────────────

from domains.channel_manager.providers.exely.validators import (
    validate_credentials,
    extract_credentials,
    validate_ari_payload,
    validate_date_range,
)


class TestExelyValidators:
    def test_validate_credentials_ok(self):
        validate_credentials("user", "pass", "H123")

    def test_validate_credentials_missing_username(self):
        with pytest.raises(ExelyValidationError, match="Username"):
            validate_credentials("", "pass", "H123")

    def test_validate_credentials_missing_password(self):
        with pytest.raises(ExelyValidationError, match="Password"):
            validate_credentials("user", "", "H123")

    def test_validate_credentials_missing_hotel_code(self):
        with pytest.raises(ExelyValidationError, match="Hotel code"):
            validate_credentials("user", "pass", "")

    def test_extract_credentials(self):
        creds = {"username": "u", "password": "p", "hotel_code": "H1"}
        u, p, h = extract_credentials(creds)
        assert u == "u"
        assert p == "p"
        assert h == "H1"

    def test_extract_credentials_fallback_hotel_id(self):
        creds = {"username": "u", "password": "p", "hotel_id": "H2"}
        _, _, h = extract_credentials(creds)
        assert h == "H2"

    def test_validate_ari_payload_ok(self):
        validate_ari_payload("RT1", "RP1", "2025-01-01", "2025-01-10")

    def test_validate_ari_missing_room_type(self):
        with pytest.raises(ExelyValidationError, match="room_type_code"):
            validate_ari_payload("", "RP1", "2025-01-01", "2025-01-10")

    def test_validate_ari_date_range_invalid(self):
        with pytest.raises(ExelyValidationError, match="end_date"):
            validate_ari_payload("RT1", "RP1", "2025-01-10", "2025-01-01")

    def test_validate_date_range_ok(self):
        validate_date_range("2025-01-01", "2025-01-10")
        validate_date_range(None, None)

    def test_validate_date_range_invalid(self):
        with pytest.raises(ExelyValidationError, match="to_date"):
            validate_date_range("2025-01-10", "2025-01-01")


# ── Observability ────────────────────────────────────────────────────

from domains.channel_manager.providers.exely import observability as obs


class TestExelyObservability:
    def setup_method(self):
        obs.reset_metrics()

    def test_record_success(self):
        obs.record_provider_call(
            soap_action="OTA_ReadRQ", duration_ms=100,
            success=True, connection_id="c1",
        )
        health = obs.get_provider_health()
        assert health["call_count"] == 1
        assert health["success_count"] == 1
        assert health["error_count"] == 0
        assert health["avg_latency_ms"] == 100
        assert health["success_rate_pct"] == 100.0

    def test_record_error(self):
        obs.record_provider_call(
            soap_action="OTA_ReadRQ", duration_ms=50,
            success=False, connection_id="c1", error_type="ExelyTemporaryError",
        )
        health = obs.get_provider_health()
        assert health["error_count"] == 1
        assert health["success_rate_pct"] == 0.0

    def test_record_failure_auth(self):
        obs.record_provider_failure(
            error_type="ExelyAuthError", message="bad",
            connection_id="c1", soap_action="OTA_HotelAvailRQ",
        )
        health = obs.get_provider_health()
        assert health["auth_failure_count"] == 1

    def test_record_failure_soap_fault(self):
        obs.record_provider_failure(
            error_type="ExelySOAPFaultError", message="fault",
            connection_id="c1", soap_action="OTA_ReadRQ",
        )
        health = obs.get_provider_health()
        assert health["soap_fault_count"] == 1

    def test_reset_metrics(self):
        obs.record_provider_call(soap_action="test", duration_ms=10, success=True)
        obs.reset_metrics()
        health = obs.get_provider_health()
        assert health["call_count"] == 0
        assert health["success_count"] == 0

    def test_health_provider_name(self):
        health = obs.get_provider_health()
        assert health["provider"] == "exely"


# ── SOAP Builder ─────────────────────────────────────────────────────

from domains.channel_manager.providers.exely.soap_builder import (
    build_read_rq,
    build_hotel_avail_rq,
    build_notif_report_rq,
    build_ari_update_rq,
)


class TestSoapBuilder:
    def test_build_read_rq_by_date(self):
        xml = build_read_rq("u", "p", "H1", "2025-01-01", "2025-01-10")
        assert "OTA_ReadRQ" in xml
        assert "H1" in xml
        assert "2025-01-01" in xml
        assert 'Username="u"' in xml

    def test_build_read_rq_by_id(self):
        xml = build_read_rq("u", "p", "H1", reservation_id="RES123")
        assert "RES123" in xml
        assert "UniqueID" in xml

    def test_build_hotel_avail_rq(self):
        xml = build_hotel_avail_rq("u", "p", "H1", "2025-06-01", "2025-06-02")
        assert "OTA_HotelAvailRQ" in xml
        assert "2025-06-01" in xml
        assert "HotelRef" in xml

    def test_build_notif_report_rq(self):
        xml = build_notif_report_rq("u", "p", "H1", "RES1", "CONF1")
        assert "OTA_NotifReportRQ" in xml
        assert "RES1" in xml
        assert "CONF1" in xml

    def test_build_ari_update_with_availability(self):
        xml = build_ari_update_rq("u", "p", "H1", "DBL", "BAR", "2025-07-01", "2025-07-10", availability=5)
        assert "OTA_HotelAvailNotifRQ" in xml
        assert "BookingLimit" in xml

    def test_build_ari_update_with_rate(self):
        xml = build_ari_update_rq("u", "p", "H1", "DBL", "BAR", "2025-07-01", "2025-07-10", rate_amount=150.50)
        assert "150.50" in xml
        assert "BaseByGuestAmt" in xml

    def test_build_ari_update_with_stop_sell(self):
        xml = build_ari_update_rq("u", "p", "H1", "DBL", "BAR", "2025-07-01", "2025-07-10", stop_sell=True)
        assert 'Status="Close"' in xml

    def test_build_ari_update_with_min_stay(self):
        xml = build_ari_update_rq("u", "p", "H1", "DBL", "BAR", "2025-07-01", "2025-07-10", min_stay=2)
        assert "LengthOfStay" in xml
        assert 'Time="2"' in xml

    def test_security_header(self):
        xml = build_read_rq("user1", "pass1", "H1")
        assert "Security" in xml
        assert 'Username="user1"' in xml
        assert 'Password="pass1"' in xml
        assert "hopenapi.com" in xml


# ── Response Parser ──────────────────────────────────────────────────

from domains.channel_manager.providers.exely.response_parser import (
    parse_soap_response,
    parse_read_rs,
    parse_hotel_avail_rs,
    parse_notif_report_rs,
    parse_ari_update_rs,
)

# Sample SOAP response XMLs for testing
_SOAP_AVAIL_RS = b"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ota="http://www.opentravel.org/OTA/2003/05">
  <soapenv:Body>
    <ota:OTA_HotelAvailRS>
      <ota:RoomStay>
        <ota:RoomType RoomTypeCode="DBL" RoomDescription="Double Room" NumberOfUnits="5"/>
        <ota:RatePlan RatePlanCode="BAR" RatePlanName="Best Available Rate"/>
      </ota:RoomStay>
      <ota:RoomStay>
        <ota:RoomType RoomTypeCode="SGL" RoomDescription="Single Room" NumberOfUnits="3"/>
        <ota:RatePlan RatePlanCode="NR" RatePlanName="Non-Refundable"/>
      </ota:RoomStay>
    </ota:OTA_HotelAvailRS>
  </soapenv:Body>
</soapenv:Envelope>"""

_SOAP_READ_RS = b"""<?xml version="1.0" encoding="UTF-8"?>
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
                  <ota:GivenName>John</ota:GivenName>
                  <ota:Surname>Doe</ota:Surname>
                </ota:PersonName>
                <ota:Email>john@test.com</ota:Email>
              </ota:Customer>
            </ota:Profile>
          </ota:Profiles>
        </ota:ResGuest>
        <ota:RoomStay>
          <ota:RoomType RoomTypeCode="DBL"/>
          <ota:RatePlan RatePlanCode="BAR"/>
          <ota:GuestCount AgeQualifyingCode="10" Count="2"/>
          <ota:TimeSpan Start="2025-06-15" End="2025-06-20"/>
          <ota:Total AmountAfterTax="500.00" CurrencyCode="TRY"/>
        </ota:RoomStay>
        <ota:ResGlobalInfo>
          <ota:Total AmountAfterTax="500.00" CurrencyCode="TRY"/>
        </ota:ResGlobalInfo>
      </ota:HotelReservation>
    </ota:OTA_ResRetrieveRS>
  </soapenv:Body>
</soapenv:Envelope>"""

_SOAP_FAULT = b"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/">
  <soapenv:Body>
    <soapenv:Fault>
      <faultcode>Server</faultcode>
      <faultstring>Authentication failed</faultstring>
    </soapenv:Fault>
  </soapenv:Body>
</soapenv:Envelope>"""

_SOAP_SUCCESS_RS = b"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ota="http://www.opentravel.org/OTA/2003/05">
  <soapenv:Body>
    <ota:OTA_NotifReportRS>
      <ota:Success/>
    </ota:OTA_NotifReportRS>
  </soapenv:Body>
</soapenv:Envelope>"""

_SOAP_ERROR_RS = b"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns:ota="http://www.opentravel.org/OTA/2003/05">
  <soapenv:Body>
    <ota:OTA_HotelAvailNotifRS>
      <ota:Errors>
        <ota:Error ShortText="Invalid room type code"/>
      </ota:Errors>
    </ota:OTA_HotelAvailNotifRS>
  </soapenv:Body>
</soapenv:Envelope>"""


class TestResponseParser:
    def test_parse_soap_fault(self):
        result = parse_soap_response(_SOAP_FAULT)
        assert result["success"] is False
        assert "Authentication failed" in result["error"]

    def test_parse_invalid_xml(self):
        result = parse_soap_response(b"<broken>")
        assert result["success"] is False

    def test_parse_hotel_avail_rs(self):
        result = parse_hotel_avail_rs(_SOAP_AVAIL_RS)
        assert result["success"] is True
        assert len(result["room_types"]) == 2
        assert len(result["rate_plans"]) == 2
        assert result["room_types"][0]["code"] == "DBL"
        assert result["rate_plans"][0]["code"] == "BAR"

    def test_parse_read_rs(self):
        result = parse_read_rs(_SOAP_READ_RS)
        assert result["success"] is True
        assert result["count"] == 1
        res = result["reservations"][0]
        assert res["reservation_id"] == "RES001"
        assert res["guest_firstname"] == "John"
        assert res["guest_lastname"] == "Doe"
        assert res["status"] == "Commit"
        assert len(res["rooms"]) == 1
        assert res["rooms"][0]["room_type_code"] == "DBL"

    def test_parse_notif_report_success(self):
        result = parse_notif_report_rs(_SOAP_SUCCESS_RS)
        assert result["success"] is True

    def test_parse_ari_update_error(self):
        result = parse_ari_update_rs(_SOAP_ERROR_RS)
        assert result["success"] is False
        assert "Invalid room type" in result["error"]


# ── Normalizer ───────────────────────────────────────────────────────

from domains.channel_manager.providers.exely.normalizer import normalize_reservation


class TestExelyNormalizer:
    def test_normalize_basic(self):
        raw = {
            "reservation_id": "RES001",
            "status": "Commit",
            "guest_name": "John Doe",
            "guest_firstname": "John",
            "guest_lastname": "Doe",
            "guest_email": "john@test.com",
            "checkin_date": "2025-06-15",
            "checkout_date": "2025-06-20",
            "total": 500.0,
            "currency": "TRY",
            "rooms": [
                {"room_type_code": "DBL", "rate_plan_code": "BAR", "adults": 2, "children": 0, "amount": 500.0},
            ],
        }
        canonical = normalize_reservation(raw)
        assert canonical["external_id"] == "RES001"
        assert canonical["status"] == "confirmed"
        assert canonical["guest"]["name"] == "John Doe"
        assert canonical["stay"]["check_in"] == "2025-06-15"
        assert canonical["stay"]["nights"] == 5
        assert canonical["financial"]["total_amount"] == 500.0
        assert canonical["source_system"] == "EXELY"

    def test_normalize_cancelled(self):
        raw = {"reservation_id": "R2", "status": "Cancel", "rooms": []}
        canonical = normalize_reservation(raw)
        assert canonical["status"] == "cancelled"

    def test_normalize_modified(self):
        raw = {"reservation_id": "R3", "status": "Modify", "rooms": []}
        canonical = normalize_reservation(raw)
        assert canonical["status"] == "modified"


# ── Provider Facade ──────────────────────────────────────────────────

from domains.channel_manager.providers.exely.provider import ExelyProvider


class TestExelyProvider:
    def test_init_with_direct_credentials(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        assert provider._username == "u"

    def test_init_with_credentials_dict(self):
        provider = ExelyProvider(credentials={"username": "u", "password": "p", "hotel_code": "H1"})
        assert provider._username == "u"

    def test_init_validation_error(self):
        with pytest.raises(ExelyValidationError):
            ExelyProvider(username="", password="p", hotel_code="H1")

    @pytest.mark.asyncio
    async def test_test_connection_success(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        with patch.object(provider._transport, "send_soap", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = _SOAP_AVAIL_RS
            result = await provider.test_connection()
            assert result.success is True
            assert result.data["connected"] is True
            assert len(result.data["room_types"]) == 2
            assert result.duration_ms >= 0

    @pytest.mark.asyncio
    async def test_test_connection_auth_failure(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        with patch.object(provider._transport, "send_soap", new_callable=AsyncMock) as mock_send:
            mock_send.side_effect = ExelyAuthError("bad creds")
            result = await provider.test_connection()
            assert result.success is False
            assert "bad creds" in result.error
            assert result.error_type == "ExelyAuthError"

    @pytest.mark.asyncio
    async def test_discover_rooms_success(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        with patch.object(provider._transport, "send_soap", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = _SOAP_AVAIL_RS
            result = await provider.discover_rooms("2025-06-01", "2025-06-02")
            assert result.success is True
            assert len(result.data["room_types"]) == 2

    @pytest.mark.asyncio
    async def test_pull_reservations_success(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        with patch.object(provider._transport, "send_soap", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = _SOAP_READ_RS
            result = await provider.pull_reservations(from_date="2025-06-01", to_date="2025-06-15")
            assert result.success is True
            assert result.data["count"] == 1
            assert result.data["reservations"][0]["reservation_id"] == "RES001"

    @pytest.mark.asyncio
    async def test_push_ari_success(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        with patch.object(provider._transport, "send_soap", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = _SOAP_SUCCESS_RS
            result = await provider.push_ari(
                room_type_code="DBL", rate_plan_code="BAR",
                start_date="2025-07-01", end_date="2025-07-10",
                availability=5,
            )
            assert result.success is True

    @pytest.mark.asyncio
    async def test_push_ari_validation_error(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        result = await provider.push_ari(
            room_type_code="", rate_plan_code="BAR",
            start_date="2025-07-01", end_date="2025-07-10",
        )
        assert result.success is False
        assert "room_type_code" in result.error

    @pytest.mark.asyncio
    async def test_confirm_delivery_success(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        with patch.object(provider._transport, "send_soap", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = _SOAP_SUCCESS_RS
            result = await provider.confirm_delivery("RES001", "CONF001")
            assert result.success is True

    @pytest.mark.asyncio
    async def test_confirm_delivery_soap_error(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        with patch.object(provider._transport, "send_soap", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = _SOAP_ERROR_RS
            result = await provider.confirm_delivery("RES001", "CONF001")
            # NotifReportRS with Errors should fail
            # Actually parse_notif_report_rs checks for Errors element
            # _SOAP_ERROR_RS has ota:Errors so it should fail
            assert result.success is False

    @pytest.mark.asyncio
    async def test_legacy_test_connection(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        with patch.object(provider._transport, "send_soap", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = _SOAP_AVAIL_RS
            result = await provider.legacy_test_connection()
            assert isinstance(result, dict)
            assert result["connected"] is True
            assert "room_types" in result

    @pytest.mark.asyncio
    async def test_legacy_pull_reservations(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        with patch.object(provider._transport, "send_soap", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = _SOAP_READ_RS
            result = await provider.legacy_pull_reservations(from_date="2025-06-01", to_date="2025-06-15")
            assert isinstance(result, dict)
            assert result["success"] is True
            assert len(result["reservations"]) == 1

    @pytest.mark.asyncio
    async def test_legacy_discover_rooms(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        with patch.object(provider._transport, "send_soap", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = _SOAP_AVAIL_RS
            result = await provider.legacy_discover_rooms("2025-06-01", "2025-06-02")
            assert isinstance(result, dict)
            assert result["success"] is True
            assert len(result["room_types"]) == 2

    @pytest.mark.asyncio
    async def test_temporary_error_triggers_retry(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1", max_retries=2)
        call_count = 0

        async def flaky_send(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ExelyTemporaryError("server error")
            return _SOAP_AVAIL_RS

        with patch.object(provider._transport, "send_soap", side_effect=flaky_send):
            # Also need to patch retry delay
            provider._retry = ExelyRetryPolicy(max_retries=2, base_delay=0.01)
            result = await provider.test_connection()
            assert result.success is True
            assert call_count == 3

    def test_normalize_to_canonical(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        raw = {
            "reservation_id": "R1", "status": "Commit",
            "guest_name": "Test", "checkin_date": "2025-01-01",
            "checkout_date": "2025-01-05", "total": 200, "rooms": [],
        }
        canonical = provider.normalize_to_canonical(raw)
        assert canonical["external_id"] == "R1"
        assert canonical["source_system"] == "EXELY"

    def test_usage_stats(self):
        provider = ExelyProvider(username="u", password="p", hotel_code="H1")
        obs.reset_metrics()
        stats = provider.get_usage_stats()
        assert "requests_today" in stats
        assert "success_rate_pct" in stats


# ── Client (Transport) ──────────────────────────────────────────────

from domains.channel_manager.providers.exely.client import ExelySoapTransport
import httpx


class TestExelySoapTransport:
    @pytest.mark.asyncio
    async def test_raise_for_401(self):
        transport = ExelySoapTransport("https://example.com")
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        with pytest.raises(ExelyAuthError):
            transport._raise_for_http_status(mock_resp, 100, "test")

    @pytest.mark.asyncio
    async def test_raise_for_429(self):
        transport = ExelySoapTransport("https://example.com")
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.headers = {"Retry-After": "30"}
        with pytest.raises(ExelyRateLimitError) as exc_info:
            transport._raise_for_http_status(mock_resp, 100, "test")
        assert exc_info.value.retry_after_seconds == 30

    @pytest.mark.asyncio
    async def test_raise_for_500(self):
        transport = ExelySoapTransport("https://example.com")
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        with pytest.raises(ExelyTemporaryError):
            transport._raise_for_http_status(mock_resp, 100, "test")

    @pytest.mark.asyncio
    async def test_raise_for_400(self):
        transport = ExelySoapTransport("https://example.com")
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "bad request"
        with pytest.raises(ExelyPayloadError):
            transport._raise_for_http_status(mock_resp, 100, "test")

    @pytest.mark.asyncio
    async def test_200_no_raise(self):
        transport = ExelySoapTransport("https://example.com")
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        # Should not raise
        transport._raise_for_http_status(mock_resp, 100, "test")
