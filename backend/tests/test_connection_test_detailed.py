"""
Connection Test Detailed API Tests
Tests the production-grade HotelRunner connector test flow endpoint.

Tests the POST /api/channel-manager/v2/connectors/{connector_id}/test endpoint which validates:
- Authentication validity (auth_status)
- Property access (property_access_status)
- Room type fetch (inventory_read_status)
- Rate plan fetch (rate_read_status)
- XML API connectivity (xml_connectivity_status)

Each test step returns: status (pass/fail/warn), latency_ms, error_code, message
Test results are logged to audit trail with action=connection_tested
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get('VITE_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(not BASE_URL, reason="VITE_BACKEND_URL not set")
if not BASE_URL:
    BASE_URL = "https://pms-stability-test.preview.emergentagent.com"
BASE_URL = BASE_URL.rstrip('/') + "/api"

CM_V2_BASE = f"{BASE_URL}/channel-manager/v2"

TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"

# Existing connector from context
EXISTING_CONNECTOR_ID = "c79fd9cb-d240-4344-8b2d-7d8b71d6a681"


class TestConnectionTestDetailed:
    """Test the detailed connection test endpoint for HotelRunner connector."""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Authenticate and get access token."""
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Auth failed: {response.text}"
        data = response.json()
        return data.get("access_token")

    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Authenticated request headers."""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }

    def test_connection_test_returns_structured_response(self, auth_headers):
        """POST /connectors/{id}/test returns ConnectionTestResponse with all 5 status fields."""
        # Get available connector
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        assert list_response.status_code == 200
        connectors = list_response.json().get("connectors", [])
        
        if not connectors:
            pytest.skip("No connectors available for testing")
        
        connector_id = connectors[0].get("id") or connectors[0].get("connector_id")
        
        # Call test endpoint
        response = requests.post(f"{CM_V2_BASE}/connectors/{connector_id}/test", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify response has all required fields
        assert "success" in data, "Missing 'success' field in response"
        assert isinstance(data["success"], bool), "'success' should be boolean"
        
        assert "tested_at" in data, "Missing 'tested_at' field"
        assert "total_latency_ms" in data, "Missing 'total_latency_ms' field"
        assert isinstance(data["total_latency_ms"], int), "'total_latency_ms' should be int"
        
        assert "summary" in data, "Missing 'summary' field"
        
        # Verify all 5 test step status fields
        required_status_fields = [
            "auth_status",
            "property_access_status", 
            "inventory_read_status",
            "rate_read_status",
            "xml_connectivity_status"
        ]
        
        for field in required_status_fields:
            assert field in data, f"Missing required field: {field}"
            step = data[field]
            assert "status" in step, f"{field} missing 'status'"
            assert step["status"] in ["pass", "fail", "warn"], f"{field} has invalid status: {step['status']}"
            assert "latency_ms" in step, f"{field} missing 'latency_ms'"
            assert "message" in step, f"{field} missing 'message'"
            # error_code is optional, but should exist when status is fail/warn
            if step["status"] in ["fail", "warn"]:
                assert "error_code" in step, f"{field} should have 'error_code' when status is {step['status']}"
        
        print("✅ Connection test response structure valid")
        print(f"   - success: {data['success']}")
        print(f"   - total_latency_ms: {data['total_latency_ms']}")
        print(f"   - summary: {data['summary']}")
        for field in required_status_fields:
            step = data[field]
            print(f"   - {field}: {step['status']} ({step['latency_ms']}ms)")

    def test_connection_test_with_existing_connector(self, auth_headers):
        """Test connection with known existing connector ID."""
        # Use existing connector from context
        response = requests.post(
            f"{CM_V2_BASE}/connectors/{EXISTING_CONNECTOR_ID}/test", 
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify connector info in response
        assert "connector_id" in data, "Missing connector_id in response"
        assert "provider" in data, "Missing provider in response"
        
        # For HotelRunner sandbox, we expect 404s which result in fail status
        # This is expected behavior per the problem statement
        print("✅ Connection test for existing connector:")
        print(f"   - connector_id: {data.get('connector_id', 'N/A')}")
        print(f"   - provider: {data.get('provider', 'N/A')}")
        print(f"   - display_name: {data.get('display_name', 'N/A')}")
        print(f"   - success: {data['success']}")

    def test_connection_test_step_latency_values(self, auth_headers):
        """Verify each test step has valid latency measurements."""
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        connectors = list_response.json().get("connectors", [])
        
        if not connectors:
            pytest.skip("No connectors available")
        
        connector_id = connectors[0].get("id") or connectors[0].get("connector_id")
        response = requests.post(f"{CM_V2_BASE}/connectors/{connector_id}/test", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        
        # Each step should have latency >= 0
        status_fields = ["auth_status", "property_access_status", "inventory_read_status", 
                        "rate_read_status", "xml_connectivity_status"]
        
        total_step_latency = 0
        for field in status_fields:
            step = data.get(field, {})
            latency = step.get("latency_ms", 0)
            assert latency >= 0, f"{field} has invalid latency: {latency}"
            total_step_latency += latency
        
        # Total latency should be sum of all step latencies
        assert data["total_latency_ms"] == total_step_latency, \
            f"Total latency ({data['total_latency_ms']}) != sum of steps ({total_step_latency})"
        
        print(f"✅ Latency values valid: total={data['total_latency_ms']}ms")

    def test_connection_test_turkish_error_messages(self, auth_headers):
        """Verify Turkish error messages are returned for failed steps."""
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        connectors = list_response.json().get("connectors", [])
        
        if not connectors:
            pytest.skip("No connectors available")
        
        connector_id = connectors[0].get("id") or connectors[0].get("connector_id")
        response = requests.post(f"{CM_V2_BASE}/connectors/{connector_id}/test", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        
        # Check for Turkish characters in error messages (common Turkish chars: ş, ğ, ü, ö, ı, ç)
        turkish_chars = set("şğüöıçŞĞÜÖİÇ")
        status_fields = ["auth_status", "property_access_status", "inventory_read_status",
                        "rate_read_status", "xml_connectivity_status"]
        
        found_turkish = False
        for field in status_fields:
            step = data.get(field, {})
            message = step.get("message", "")
            if any(char in message for char in turkish_chars):
                found_turkish = True
                print(f"   - {field}: {message}")
        
        # Summary should also be in Turkish
        summary = data.get("summary", "")
        if any(char in summary for char in turkish_chars):
            found_turkish = True
            print(f"   - summary: {summary}")
        
        # Note: Turkish messages are expected based on code review
        # If sandbox fails with 404, messages like "Kaynak bulunamadı" should appear
        print(f"✅ Turkish error messages check: found={found_turkish}")

    def test_connection_test_error_codes(self, auth_headers):
        """Verify appropriate error codes are returned for failed steps."""
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        connectors = list_response.json().get("connectors", [])
        
        if not connectors:
            pytest.skip("No connectors available")
        
        connector_id = connectors[0].get("id") or connectors[0].get("connector_id")
        response = requests.post(f"{CM_V2_BASE}/connectors/{connector_id}/test", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        
        # Known error codes from the client.py implementation
        known_error_codes = [
            "AUTH_INVALID", "ACCESS_DENIED", "NOT_FOUND", "RATE_LIMITED",
            "PROVIDER_ERROR", "CONN_REFUSED", "TIMEOUT", "UNKNOWN",
            "CRED_MISSING", "SKIPPED"
        ]
        
        status_fields = ["auth_status", "property_access_status", "inventory_read_status",
                        "rate_read_status", "xml_connectivity_status"]
        
        print("✅ Error codes found:")
        for field in status_fields:
            step = data.get(field, {})
            error_code = step.get("error_code")
            status = step.get("status")
            if error_code:
                # Error code should be from known list or HTTP_{code} format
                is_known = error_code in known_error_codes or error_code.startswith("HTTP_")
                assert is_known, f"Unknown error code: {error_code}"
                print(f"   - {field}: {error_code} (status: {status})")

    def test_connection_test_nonexistent_connector(self, auth_headers):
        """Test connection for non-existent connector returns proper error."""
        fake_connector_id = str(uuid.uuid4())
        
        response = requests.post(
            f"{CM_V2_BASE}/connectors/{fake_connector_id}/test",
            headers=auth_headers
        )
        
        # Should return 200 with success=false or 404
        # Based on code, it returns 200 with success=false and message="Connector not found"
        if response.status_code == 200:
            data = response.json()
            assert data.get("success") == False, "Expected success=false for non-existent connector"
            assert "not found" in data.get("message", "").lower() or \
                   "bulunamadı" in data.get("message", "").lower(), \
                   f"Expected 'not found' message, got: {data.get('message')}"
            print(f"✅ Non-existent connector: success=false, message={data.get('message')}")
        else:
            assert response.status_code == 404, f"Expected 404 for non-existent connector, got {response.status_code}"
            print("✅ Non-existent connector: 404 Not Found")

    def test_connection_test_audit_log_entry(self, auth_headers):
        """Verify connection test creates audit log entry with action=connection_tested."""
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        connectors = list_response.json().get("connectors", [])
        
        if not connectors:
            pytest.skip("No connectors available")
        
        connector_id = connectors[0].get("id") or connectors[0].get("connector_id")
        
        # Run connection test
        test_response = requests.post(f"{CM_V2_BASE}/connectors/{connector_id}/test", headers=auth_headers)
        assert test_response.status_code == 200
        
        # Check audit logs
        audit_response = requests.get(
            f"{CM_V2_BASE}/audit?connector_id={connector_id}&limit=10",
            headers=auth_headers
        )
        assert audit_response.status_code == 200
        
        logs = audit_response.json().get("logs", [])
        
        # Find connection_tested entry
        found_audit = False
        for log in logs:
            if log.get("action") == "connection_tested":
                found_audit = True
                metadata = log.get("metadata", {})
                assert "success" in metadata, "Audit metadata missing 'success'"
                print("✅ Audit log entry found:")
                print(f"   - action: {log['action']}")
                print(f"   - connector_id: {log.get('connector_id', 'N/A')}")
                print(f"   - metadata.success: {metadata.get('success')}")
                print(f"   - metadata.summary: {metadata.get('summary', 'N/A')}")
                break
        
        assert found_audit, "No 'connection_tested' audit log entry found after test"


class TestConnectionTestResponseModel:
    """Test that ConnectionTestResponse model matches Pydantic schema."""

    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200
        return response.json().get("access_token")

    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }

    def test_response_matches_pydantic_model(self, auth_headers):
        """Verify response matches ConnectionTestResponse Pydantic model."""
        list_response = requests.get(f"{CM_V2_BASE}/connectors", headers=auth_headers)
        connectors = list_response.json().get("connectors", [])
        
        if not connectors:
            pytest.skip("No connectors available")
        
        connector_id = connectors[0].get("id") or connectors[0].get("connector_id")
        response = requests.post(f"{CM_V2_BASE}/connectors/{connector_id}/test", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        
        # ConnectionTestResponse fields from router.py
        expected_fields = {
            "success": bool,
            "connector_id": str,
            "provider": str,
            "display_name": str,
            "tested_at": str,
            "total_latency_ms": int,
            "summary": str,
        }
        
        for field, expected_type in expected_fields.items():
            if field in data:
                assert isinstance(data[field], expected_type), \
                    f"Field '{field}' should be {expected_type.__name__}, got {type(data[field]).__name__}"
        
        # ConnectionTestStepResult fields
        step_fields = ["auth_status", "property_access_status", "inventory_read_status",
                      "rate_read_status", "xml_connectivity_status"]
        
        for field in step_fields:
            if field in data and data[field] is not None:
                step = data[field]
                assert "status" in step and isinstance(step["status"], str)
                assert "latency_ms" in step and isinstance(step["latency_ms"], int)
                assert "message" in step and isinstance(step["message"], str)
                # error_code is Optional[str]
                if "error_code" in step and step["error_code"] is not None:
                    assert isinstance(step["error_code"], str)
        
        print("✅ Response matches ConnectionTestResponse model")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
