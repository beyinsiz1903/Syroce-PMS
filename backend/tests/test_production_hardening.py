"""
Comprehensive Production Hardening Test Suite.

Covers:
  - Provider contract hardening (XML parser resilience)
  - Alert delivery channels
  - Background worker service
  - Connector health service
  - Enhanced production readiness
  - Contract test scenarios
"""
import pytest

# ══════════════════════════════════════════════════════════════════
# 1. XML Parser Contract Hardening Tests
# ══════════════════════════════════════════════════════════════════

class TestXmlParserContractHardening:
    """Tests for XML parser resilience against real-world provider variations."""

    def test_parse_valid_response(self):
        from channel_manager.connectors.hotelrunner_v2.xml_parser import parse_response_status
        xml = '<?xml version="1.0"?><OTA_HotelAvailNotifRS><Success/></OTA_HotelAvailNotifRS>'
        result = parse_response_status(xml)
        assert result["success"] is True
        assert result["errors"] == []

    def test_parse_error_response(self):
        from channel_manager.connectors.hotelrunner_v2.xml_parser import parse_response_status
        xml = '<?xml version="1.0"?><OTA_HotelAvailNotifRS><Errors><Error Code="42" Type="3">Invalid hotel code</Error></Errors></OTA_HotelAvailNotifRS>'
        result = parse_response_status(xml)
        assert result["success"] is False
        assert len(result["errors"]) == 1
        assert result["errors"][0]["code"] == "42"

    def test_parse_empty_xml_raises(self):
        from channel_manager.connectors.hotelrunner_v2.xml_parser import parse_response_status
        from channel_manager.connectors.hotelrunner_v2.contract_errors import InvalidXmlError
        with pytest.raises(InvalidXmlError):
            parse_response_status("")

    def test_parse_malformed_xml_raises(self):
        from channel_manager.connectors.hotelrunner_v2.xml_parser import parse_response_status
        from channel_manager.connectors.hotelrunner_v2.contract_errors import InvalidXmlError
        with pytest.raises(InvalidXmlError):
            parse_response_status("<not-valid-xml><<<")

    def test_unknown_fields_ignored(self):
        """Unknown XML elements should be silently ignored."""
        from channel_manager.connectors.hotelrunner_v2.xml_parser import parse_reservations_response
        xml = '''<?xml version="1.0"?>
        <OTA_ResRetrieveRS>
            <HotelReservation ResStatus="Commit">
                <UniqueID Type="14" ID="TEST-001"/>
                <UnknownField>Should be ignored</UnknownField>
                <AnotherUnknown attr="value"/>
                <RoomStays>
                    <RoomStay>
                        <TimeSpan Start="2026-03-01" End="2026-03-03"/>
                        <RoomTypes><RoomType RoomTypeCode="STD"/></RoomTypes>
                        <RatePlans><RatePlan RatePlanCode="BAR"/></RatePlans>
                        <Total AmountAfterTax="250.00" CurrencyCode="TRY"/>
                    </RoomStay>
                </RoomStays>
            </HotelReservation>
        </OTA_ResRetrieveRS>'''
        result = parse_reservations_response(xml)
        assert len(result) == 1
        assert result[0]["external_id"] == "TEST-001"

    def test_missing_optional_fields_tolerated(self):
        """Missing optional fields should default gracefully."""
        from channel_manager.connectors.hotelrunner_v2.xml_parser import parse_reservations_response
        xml = '''<?xml version="1.0"?>
        <OTA_ResRetrieveRS>
            <HotelReservation ResStatus="Commit">
                <UniqueID Type="14" ID="TEST-002"/>
            </HotelReservation>
        </OTA_ResRetrieveRS>'''
        result = parse_reservations_response(xml)
        assert len(result) == 1
        r = result[0]
        assert r["guest"]["first_name"] == ""
        assert r["guest"]["email"] == ""
        assert r["total_amount"] == 0.0
        assert r["adult_count"] == 1

    def test_unexpected_enum_values_fallback(self):
        """Unexpected enum values should be handled gracefully."""
        from channel_manager.connectors.hotelrunner_v2.xml_parser import _enum_fallback
        assert _enum_fallback("Commit", {"Commit", "Cancel"}) == "Commit"
        assert _enum_fallback("UnknownStatus", {"Commit", "Cancel"}) == "UnknownStatus"
        assert _enum_fallback("", {"Commit", "Cancel"}, "Commit") == "Commit"

    def test_malformed_amount_defaults_to_zero(self):
        """Malformed numeric values should default to 0."""
        from channel_manager.connectors.hotelrunner_v2.xml_parser import _safe_float, _safe_int
        assert _safe_float("not_a_number") == 0.0
        assert _safe_float("") == 0.0
        assert _safe_float("250.50") == 250.50
        assert _safe_int("abc") == 0
        assert _safe_int("") == 0
        assert _safe_int("42") == 42

    def test_sensitive_data_masking(self):
        """Sensitive card data should be masked in audit payloads."""
        from channel_manager.connectors.hotelrunner_v2.xml_parser import mask_sensitive_xml
        xml = '<Payment><CardNumber>4111111111111111</CardNumber><CVV>123</CVV></Payment>'
        masked = mask_sensitive_xml(xml)
        assert "4111111111111111" not in masked
        assert "123" not in masked
        assert "****" in masked

    def test_payload_truncation(self):
        """Large payloads should be truncated."""
        from channel_manager.connectors.hotelrunner_v2.xml_parser import truncate_payload
        short = "short payload"
        assert truncate_payload(short) == short
        long_payload = "x" * 10000
        truncated = truncate_payload(long_payload, max_len=100)
        assert len(truncated) < 200
        assert "truncated" in truncated

    def test_audit_record_creation(self):
        """Audit records should contain correlation_id and hashes."""
        from channel_manager.connectors.hotelrunner_v2.xml_parser import build_audit_record
        record = build_audit_record("push_availability", "<request/>", "<response/>", "corr-123")
        assert record["correlation_id"] == "corr-123"
        assert record["request_hash"] != ""
        assert record["response_hash"] != ""

    def test_provider_error_parsing(self):
        """Provider error responses should be parsed into typed errors."""
        from channel_manager.connectors.hotelrunner_v2.xml_parser import parse_provider_error
        from channel_manager.connectors.hotelrunner_v2.contract_errors import ProviderErrorResponseError
        xml = '<?xml version="1.0"?><OTA_RS><Errors><Error Code="501" Type="3">Room not found</Error></Errors></OTA_RS>'
        with pytest.raises(ProviderErrorResponseError) as exc_info:
            parse_provider_error(xml)
        assert "501" in str(exc_info.value)


# ══════════════════════════════════════════════════════════════════
# 2. Contract Error Classes Tests
# ══════════════════════════════════════════════════════════════════

class TestContractErrors:
    def test_invalid_xml_error(self):
        from channel_manager.connectors.hotelrunner_v2.contract_errors import InvalidXmlError
        err = InvalidXmlError("Bad XML", raw_xml="<bad>", parse_error="syntax")
        d = err.to_dict()
        assert d["error_type"] == "invalid_xml"
        assert "raw_xml_snippet" in d["details"]

    def test_missing_required_field_error(self):
        from channel_manager.connectors.hotelrunner_v2.contract_errors import MissingRequiredFieldError
        err = MissingRequiredFieldError("room_type_code", "reservation", "RES-001")
        d = err.to_dict()
        assert d["error_type"] == "missing_required_field"
        assert d["details"]["field_name"] == "room_type_code"

    def test_schema_mismatch_error(self):
        from channel_manager.connectors.hotelrunner_v2.contract_errors import SchemaMismatchError
        err = SchemaMismatchError("Wrong schema", expected="OTA_RS", actual="CustomRS")
        d = err.to_dict()
        assert d["error_type"] == "schema_mismatch"

    def test_provider_error_response(self):
        from channel_manager.connectors.hotelrunner_v2.contract_errors import ProviderErrorResponseError
        err = ProviderErrorResponseError("hotelrunner", "501", "Not found", "<raw/>")
        d = err.to_dict()
        assert d["error_type"] == "provider_error_response"
        assert d["details"]["error_code"] == "501"

    def test_unknown_response_format(self):
        from channel_manager.connectors.hotelrunner_v2.contract_errors import UnknownResponseFormatError
        err = UnknownResponseFormatError("text/html", "<html>Error</html>")
        d = err.to_dict()
        assert d["error_type"] == "unknown_response_format"


# ══════════════════════════════════════════════════════════════════
# 3. Alert Delivery Service Tests
# ══════════════════════════════════════════════════════════════════

class TestAlertDeliveryService:
    def test_fingerprint_generation(self):
        from channel_manager.application.alert_delivery_service import AlertDeliveryService
        svc = AlertDeliveryService()
        fp1 = svc._make_fingerprint("t1", "ch1", "trigger1", "conn1")
        fp2 = svc._make_fingerprint("t1", "ch1", "trigger1", "conn1")
        fp3 = svc._make_fingerprint("t1", "ch2", "trigger1", "conn1")
        assert fp1 == fp2  # Same inputs = same fingerprint
        assert fp1 != fp3  # Different channel = different fingerprint

    def test_email_body_formatting(self):
        from channel_manager.application.alert_delivery_service import AlertDeliveryService
        svc = AlertDeliveryService()
        alert = {
            "severity": "critical",
            "trigger": "health_score_drop",
            "connector_id": "test-conn",
            "description": "Health score below threshold",
            "created_at": "2026-03-01T00:00:00Z",
        }
        body = svc._format_email_body(alert)
        assert "CRITICAL" in body
        assert "test-conn" in body

    @pytest.mark.asyncio
    async def test_webhook_delivery(self):
        from channel_manager.application.alert_delivery_service import AlertDeliveryService
        svc = AlertDeliveryService()
        channel = {"config": {"url": ""}, "id": "ch1"}
        alert = {"id": "a1", "severity": "info", "trigger": "test"}
        # Empty URL should return False
        result = await svc._deliver_webhook(channel, alert)
        assert result is False

    @pytest.mark.asyncio
    async def test_slack_delivery_no_url(self):
        from channel_manager.application.alert_delivery_service import AlertDeliveryService
        svc = AlertDeliveryService()
        channel = {"config": {}, "id": "ch1"}
        alert = {"id": "a1", "severity": "info", "trigger": "test"}
        result = await svc._deliver_slack(channel, alert)
        assert result is False

    @pytest.mark.asyncio
    async def test_teams_delivery_no_url(self):
        from channel_manager.application.alert_delivery_service import AlertDeliveryService
        svc = AlertDeliveryService()
        channel = {"config": {}, "id": "ch1"}
        alert = {"id": "a1", "severity": "info", "trigger": "test"}
        result = await svc._deliver_teams(channel, alert)
        assert result is False


# ══════════════════════════════════════════════════════════════════
# 4. Background Worker Service Tests
# ══════════════════════════════════════════════════════════════════

class TestBackgroundWorkerService:
    def test_worker_job_creation(self):
        from channel_manager.application.background_worker_service import WorkerJob
        job = WorkerJob("reservation_import", "tenant-1", "conn-1")
        assert job.status == "pending"
        assert job.job_type == "reservation_import"
        doc = job.to_doc()
        assert "id" in doc
        assert doc["tenant_id"] == "tenant-1"

    def test_default_intervals(self):
        from channel_manager.application.background_worker_service import DEFAULT_INTERVALS
        assert DEFAULT_INTERVALS["reservation_import"] == 300
        assert DEFAULT_INTERVALS["inventory_safety_sync"] == 1800
        assert DEFAULT_INTERVALS["connector_health_check"] == 900
        assert DEFAULT_INTERVALS["metrics_aggregation"] == 1800


# ══════════════════════════════════════════════════════════════════
# 5. Connector Health Service Tests
# ══════════════════════════════════════════════════════════════════

class TestConnectorHealthService:
    def test_health_score_calculation(self):
        from channel_manager.application.connector_health_service import ConnectorHealthService
        # Perfect score
        score = ConnectorHealthService._calc_health_score(100, 100, 100, 0, 0, 0, 100, rate_push_success_rate=100)
        assert score == 100.0

        # Zero everything (rate_push defaults to 100, so pass 0 explicitly)
        score_zero = ConnectorHealthService._calc_health_score(0, 0, 0, 10, 5, 100, 100, rate_push_success_rate=0)
        assert score_zero == 0.0

    def test_classification(self):
        from channel_manager.application.connector_health_service import ConnectorHealthService
        assert ConnectorHealthService._classify(90) == "HEALTHY"
        assert ConnectorHealthService._classify(70) == "DEGRADED"
        assert ConnectorHealthService._classify(50) == "CRITICAL"

    def test_uptime_calculation(self):
        from channel_manager.application.connector_health_service import ConnectorHealthService
        # No jobs, active connector
        assert ConnectorHealthService._calc_uptime({"status": "active"}, []) == 100.0
        # No jobs, inactive connector
        assert ConnectorHealthService._calc_uptime({"status": "error"}, []) == 0.0
        # Some failed jobs
        jobs = [{"status": "succeeded"}, {"status": "succeeded"}, {"status": "failed"}]
        assert ConnectorHealthService._calc_uptime({}, jobs) == 66.7


# ══════════════════════════════════════════════════════════════════
# 6. Contract Test Scenarios
# ══════════════════════════════════════════════════════════════════

class TestContractScenarios:
    """End-to-end contract test scenarios for provider variations."""

    def test_duplicate_reservation_detection(self):
        """Same external_id parsed from two identical payloads should produce same result."""
        from channel_manager.connectors.hotelrunner_v2.xml_parser import parse_reservations_response
        xml = '''<?xml version="1.0"?>
        <OTA_ResRetrieveRS>
            <HotelReservation ResStatus="Commit">
                <UniqueID Type="14" ID="DUP-001"/>
                <RoomStays><RoomStay>
                    <TimeSpan Start="2026-04-01" End="2026-04-03"/>
                </RoomStay></RoomStays>
            </HotelReservation>
        </OTA_ResRetrieveRS>'''
        r1 = parse_reservations_response(xml)
        r2 = parse_reservations_response(xml)
        assert r1[0]["external_id"] == r2[0]["external_id"]

    def test_cancellation_status_parsing(self):
        """Cancel status should be correctly parsed."""
        from channel_manager.connectors.hotelrunner_v2.xml_parser import parse_reservations_response
        xml = '''<?xml version="1.0"?>
        <OTA_ResRetrieveRS>
            <HotelReservation ResStatus="Cancel">
                <UniqueID Type="14" ID="CANCEL-001"/>
            </HotelReservation>
        </OTA_ResRetrieveRS>'''
        result = parse_reservations_response(xml)
        assert result[0]["res_status"] == "Cancel"

    def test_modification_status_parsing(self):
        """Modify status should be correctly parsed."""
        from channel_manager.connectors.hotelrunner_v2.xml_parser import parse_reservations_response
        xml = '''<?xml version="1.0"?>
        <OTA_ResRetrieveRS>
            <HotelReservation ResStatus="Modify">
                <UniqueID Type="14" ID="MOD-001"/>
            </HotelReservation>
        </OTA_ResRetrieveRS>'''
        result = parse_reservations_response(xml)
        assert result[0]["res_status"] == "Modify"

    def test_unknown_status_handled(self):
        """Unknown reservation status should not crash."""
        from channel_manager.connectors.hotelrunner_v2.xml_parser import parse_reservations_response
        xml = '''<?xml version="1.0"?>
        <OTA_ResRetrieveRS>
            <HotelReservation ResStatus="WeirdStatus">
                <UniqueID Type="14" ID="WEIRD-001"/>
            </HotelReservation>
        </OTA_ResRetrieveRS>'''
        result = parse_reservations_response(xml)
        assert result[0]["res_status"] == "WeirdStatus"

    def test_payload_with_source_channel(self):
        """Source channel info should be extracted if present."""
        from channel_manager.connectors.hotelrunner_v2.xml_parser import parse_reservations_response
        xml = '''<?xml version="1.0"?>
        <OTA_ResRetrieveRS>
            <HotelReservation ResStatus="Commit">
                <UniqueID Type="14" ID="SRC-001"/>
                <POS><Source ChannelCode="BOOKING_COM"/></POS>
            </HotelReservation>
        </OTA_ResRetrieveRS>'''
        result = parse_reservations_response(xml)
        assert result[0]["source_channel"] == "BOOKING_COM"

    def test_multiple_error_codes_parsing(self):
        """Multiple OTA errors should all be captured."""
        from channel_manager.connectors.hotelrunner_v2.xml_parser import parse_response_status
        xml = '''<?xml version="1.0"?><OTA_RS>
            <Errors>
                <Error Code="100" Type="1">First error</Error>
                <Error Code="200" Type="2">Second error</Error>
            </Errors>
        </OTA_RS>'''
        result = parse_response_status(xml)
        assert result["success"] is False
        assert len(result["errors"]) == 2

    def test_warning_parsing(self):
        """Warnings should be captured alongside success."""
        from channel_manager.connectors.hotelrunner_v2.xml_parser import parse_response_status
        xml = '''<?xml version="1.0"?><OTA_RS>
            <Success/>
            <Warnings>
                <Warning>Rate might be outdated</Warning>
            </Warnings>
        </OTA_RS>'''
        result = parse_response_status(xml)
        assert result["success"] is True
        assert len(result["warnings"]) == 1


# ══════════════════════════════════════════════════════════════════
# 7. Environment Config Tests
# ══════════════════════════════════════════════════════════════════

class TestEnvironmentConfig:
    def test_sandbox_config(self):
        from channel_manager.connectors.hotelrunner_v2.environment_config import get_environment_config
        cfg = get_environment_config("sandbox")
        assert cfg.name == "sandbox"
        assert "sandbox" in cfg.api_base_url
        assert cfg.sandbox is True

    def test_production_config(self):
        from channel_manager.connectors.hotelrunner_v2.environment_config import get_environment_config
        cfg = get_environment_config("production")
        assert cfg.sandbox is False
        assert cfg.retry_max == 5

    def test_mock_config(self):
        from channel_manager.connectors.hotelrunner_v2.environment_config import get_environment_config
        cfg = get_environment_config("mock")
        assert "localhost" in cfg.api_base_url
        assert cfg.credential_encryption_required is False

    def test_all_environments(self):
        from channel_manager.connectors.hotelrunner_v2.environment_config import get_all_environments
        envs = get_all_environments()
        assert "mock" in envs
        assert "sandbox" in envs
        assert "production" in envs

    def test_default_fallback(self):
        from channel_manager.connectors.hotelrunner_v2.environment_config import get_environment_config
        cfg = get_environment_config("nonexistent")
        assert cfg.name == "sandbox"  # defaults to sandbox


# ══════════════════════════════════════════════════════════════════
# 8. XML Builder Tests
# ══════════════════════════════════════════════════════════════════

class TestXmlBuilder:
    def test_build_availability_notif(self):
        from channel_manager.connectors.hotelrunner_v2.xml_builder import build_availability_notif
        updates = [{"room_type_code": "STD", "date_start": "2026-03-01", "date_end": "2026-03-02", "available": 5}]
        xml = build_availability_notif("HR123", updates)
        assert "OTA_HotelAvailNotifRQ" in xml
        assert "STD" in xml
        assert "BookingLimit" in xml

    def test_build_rate_amount_notif(self):
        from channel_manager.connectors.hotelrunner_v2.xml_builder import build_rate_amount_notif
        updates = [{"room_type_code": "STD", "rate_plan_code": "BAR", "date_start": "2026-03-01", "date_end": "2026-03-02", "amount_after_tax": 150.0, "currency": "TRY"}]
        xml = build_rate_amount_notif("HR123", updates)
        assert "OTA_HotelRateAmountNotifRQ" in xml
        assert "150.00" in xml

    def test_build_notif_report(self):
        from channel_manager.connectors.hotelrunner_v2.xml_builder import build_notif_report_rq
        xml = build_notif_report_rq("HR123", ["RES-001", "RES-002"])
        assert "OTA_NotifReportRQ" in xml
        assert "RES-001" in xml
        assert "RES-002" in xml
