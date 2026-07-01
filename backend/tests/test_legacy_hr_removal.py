"""
Test suite for Legacy HotelRunner Connector Removal verification.
Verifies that:
1. Backend starts successfully after legacy code removal
2. All hotelrunner_v2 modules import correctly
3. Application services import correctly with updated paths
4. No remaining references to old connectors.hotelrunner package
5. Channel Manager v2 APIs work correctly
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for API tests."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}"}


class TestBackendHealth:
    """Verify backend starts and responds correctly."""

    def test_health_endpoint(self):
        """Backend health check should return healthy status."""
        response = requests.get(f"{BASE_URL}/api/health/")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "timestamp" in data

    def test_auth_login(self):
        """Authentication should work with demo credentials."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["user"]["email"] == TEST_EMAIL
        assert data["user"]["role"] == "super_admin"


class TestHotelRunnerV2ModuleImports:
    """Verify all hotelrunner_v2 modules import successfully."""

    def test_auth_module_import(self):
        """auth.py should import successfully."""
        from channel_manager.connectors.hotelrunner_v2.auth import HotelRunnerAuth
        assert HotelRunnerAuth is not None

    def test_hr_client_module_import(self):
        """hr_client.py (renamed from v1_client.py) should import."""
        from channel_manager.connectors.hotelrunner_v2.hr_client import HotelRunnerClient
        assert HotelRunnerClient is not None

    def test_v1_client_compat_alias(self):
        """v1_client.py compatibility alias should still work."""
        from channel_manager.connectors.hotelrunner_v2.v1_client import HotelRunnerClient
        assert HotelRunnerClient is not None

    def test_connector_errors_module_import(self):
        """connector_errors.py (renamed from v1_errors.py) should import."""
        from channel_manager.connectors.hotelrunner_v2.connector_errors import (
            ConnectorError,
            AuthenticationError,
            RateLimitError,
            XmlParseError,
        )
        assert ConnectorError is not None
        assert AuthenticationError is not None
        assert RateLimitError is not None
        assert XmlParseError is not None

    def test_v1_errors_compat_alias(self):
        """v1_errors.py compatibility alias should still work."""
        from channel_manager.connectors.hotelrunner_v2.v1_errors import ConnectorError
        assert ConnectorError is not None

    def test_reservation_mapper_module_import(self):
        """reservation_mapper.py (renamed from v1_mapper.py) should import."""
        from channel_manager.connectors.hotelrunner_v2.reservation_mapper import HotelRunnerMapper
        assert HotelRunnerMapper is not None

    def test_v1_mapper_compat_alias(self):
        """v1_mapper.py compatibility alias should still work."""
        from channel_manager.connectors.hotelrunner_v2.v1_mapper import HotelRunnerMapper
        assert HotelRunnerMapper is not None

    def test_environment_config_import(self):
        """environment_config.py should import successfully."""
        from channel_manager.connectors.hotelrunner_v2.environment_config import (
            EnvironmentConfig,
            get_environment_config,
            get_all_environments,
        )
        assert EnvironmentConfig is not None
        assert get_environment_config is not None
        assert get_all_environments is not None

    def test_xml_parser_import(self):
        """xml_parser.py should import successfully."""
        from channel_manager.connectors.hotelrunner_v2.xml_parser import (
            parse_response_status,
            parse_reservations_response,
        )
        assert parse_response_status is not None
        assert parse_reservations_response is not None

    def test_xml_builder_import(self):
        """xml_builder.py should import successfully."""
        from channel_manager.connectors.hotelrunner_v2.xml_builder import (
            build_availability_notif,
            build_rate_amount_notif,
            build_read_rq,
        )
        assert build_availability_notif is not None
        assert build_rate_amount_notif is not None
        assert build_read_rq is not None

    def test_service_module_import(self):
        """service.py should import successfully."""
        from channel_manager.connectors.hotelrunner_v2.service import HotelRunnerV2Service
        assert HotelRunnerV2Service is not None

    def test_router_module_import(self):
        """router.py should import successfully."""
        from channel_manager.connectors.hotelrunner_v2.router import router
        assert router is not None


class TestApplicationServiceImports:
    """Verify application services import correctly with updated paths."""

    def test_inventory_sync_service_import(self):
        """inventory_sync_service.py should import with updated hotelrunner_v2 paths."""
        from channel_manager.application.inventory_sync_service import InventorySyncService
        assert InventorySyncService is not None

    def test_reservation_import_service_import(self):
        """reservation_import_service.py should import with updated paths."""
        from channel_manager.application.reservation_import_service import ReservationImportService
        assert ReservationImportService is not None

    def test_connector_service_import(self):
        """connector_service.py should import with updated paths."""
        from channel_manager.application.connector_service import ConnectorService
        assert ConnectorService is not None

    def test_sandbox_validation_service_import(self):
        """sandbox_validation_service.py should import with updated paths."""
        from channel_manager.application.sandbox_validation_service import SandboxValidationService
        assert SandboxValidationService is not None


class TestNoLegacyReferences:
    """Verify no remaining references to old connectors.hotelrunner package."""

    def test_no_old_hotelrunner_directory(self):
        """Old connectors/hotelrunner directory should not exist."""
        import os
        old_path = "/app/backend/channel_manager/connectors/hotelrunner"
        assert not os.path.exists(old_path), f"Legacy directory still exists: {old_path}"

    def test_no_deprecated_v1_directory(self):
        """_deprecated_hotelrunner_v1 directory should not exist."""
        import os
        deprecated_path = "/app/backend/channel_manager/connectors/_deprecated_hotelrunner_v1"
        assert not os.path.exists(deprecated_path), f"Deprecated directory still exists: {deprecated_path}"

    def test_no_legacy_router_file(self):
        """router_legacy_DEPRECATED.py should not exist."""
        import os
        legacy_router = "/app/backend/channel_manager/interfaces/router_legacy_DEPRECATED.py"
        assert not os.path.exists(legacy_router), f"Legacy router still exists: {legacy_router}"

    def test_no_legacy_provider_file(self):
        """providers/hotelrunner_legacy.py should not exist."""
        import os
        legacy_provider = "/app/backend/channel_manager/providers/hotelrunner_legacy.py"
        assert not os.path.exists(legacy_provider), f"Legacy provider still exists: {legacy_provider}"


class TestChannelManagerV2APIs:
    """Verify Channel Manager v2 APIs work correctly after refactoring."""

    def test_connectors_list(self, auth_headers):
        """GET /api/channel-manager/v2/connectors should return connectors list."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/connectors",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "connectors" in data
        assert "count" in data
        assert isinstance(data["connectors"], list)
        assert data["count"] >= 0

    def test_mapping_wizard_suggest_rooms(self, auth_headers):
        """GET /api/channel-manager/v2/mapping-wizard/{connector_id}/suggest-rooms should work."""
        # Use known test connector ID
        connector_id = "27cc2aa6-68c8-4f62-95e0-076ef2c2f634"
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/mapping-wizard/{connector_id}/suggest-rooms",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "connector_id" in data
        assert "suggestions" in data
        assert "summary" in data

    def test_environments_endpoint(self, auth_headers):
        """GET /api/channel-manager/v2/environments should return environment configs."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/environments",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "environments" in data
        envs = data["environments"]
        assert "mock" in envs
        assert "sandbox" in envs
        assert "production" in envs
        # Verify environment config structure
        assert envs["sandbox"]["api_base_url"] == "https://sandbox.hotelrunner.com/api/v2"
        assert envs["production"]["api_base_url"] == "https://app.hotelrunner.com/api/v2"

    def test_import_jobs_list(self, auth_headers):
        """GET /api/channel-manager/v2/import-jobs should return jobs list."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/import-jobs",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "jobs" in data
        assert "count" in data

    def test_connector_polling_config(self, auth_headers):
        """GET /api/channel-manager/v2/connectors/{id}/polling-config should work."""
        connector_id = "27cc2aa6-68c8-4f62-95e0-076ef2c2f634"
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/connectors/{connector_id}/polling-config",
            headers=auth_headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert "connector_id" in data
        assert "environment" in data
        assert "reservation_polling_interval" in data


class TestHotelRunnerV2FunctionCalls:
    """Verify hotelrunner_v2 module functions work correctly."""

    def test_environment_config_get_all(self):
        """get_all_environments should return all 3 environments."""
        from channel_manager.connectors.hotelrunner_v2.environment_config import get_all_environments
        envs = get_all_environments()
        assert "mock" in envs
        assert "sandbox" in envs
        assert "production" in envs

    def test_environment_config_get_specific(self):
        """get_environment_config should return correct config for each env."""
        from channel_manager.connectors.hotelrunner_v2.environment_config import get_environment_config
        
        sandbox = get_environment_config("sandbox")
        assert sandbox.name == "sandbox"
        assert sandbox.sandbox is True
        
        prod = get_environment_config("production")
        assert prod.name == "production"
        assert prod.sandbox is False

    def test_xml_builder_availability_notif(self):
        """build_availability_notif should generate valid XML."""
        from channel_manager.connectors.hotelrunner_v2.xml_builder import build_availability_notif
        
        xml = build_availability_notif(
            hr_id="12345",
            updates=[{
                "room_type_code": "STD",
                "date_start": "2026-04-10",
                "date_end": "2026-04-11",
                "available": 5,
            }],
        )
        assert "OTA_HotelAvailNotifRQ" in xml
        assert "12345" in xml
        assert "STD" in xml

    def test_xml_parser_response_status(self):
        """parse_response_status should parse success/error responses."""
        from channel_manager.connectors.hotelrunner_v2.xml_parser import parse_response_status
        
        success_xml = """<?xml version="1.0"?>
        <OTA_HotelAvailNotifRS xmlns="http://www.opentravel.org/OTA/2003/05">
            <Success/>
        </OTA_HotelAvailNotifRS>"""
        
        result = parse_response_status(success_xml)
        assert result["success"] is True
        assert result["errors"] == []
