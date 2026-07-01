"""
HotelRunner v2 — Dry-Run Write Path Tests
==========================================

Tests for the new dry-run write path implementation:
- POST /dry-run/ari-push — dry-run ARI push with payload, outbox entry, verification
- POST /dry-run/confirm-delivery — dry-run confirm delivery
- POST /dry-run/chain — create/modify/cancel chain test (3 steps)
- POST /dry-run/simulate-failure — timeout, validation_error, rate_limit simulation
- GET /dry-run/results — execution history
- GET /dry-run/stats — success rate, failure breakdown, chain stats
- GET /dry-run/write-criteria — write enable criteria check (6 criteria)
- GET /ops-dashboard includes dry_run and write_criteria fields
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")
TENANT_ID = "syroce_default"
PROPERTY_ID = "default"


class TestDryRunAriPush:
    """Tests for POST /dry-run/ari-push endpoint"""

    def test_dry_run_ari_push_success(self):
        """Test successful dry-run ARI push with valid payload"""
        response = requests.post(
            f"{BASE_URL}/api/channel/hotelrunner-v2/dry-run/ari-push",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID},
            json={
                "inv_code": "HR:TEST-DR-001",
                "start_date": "2026-04-01",
                "end_date": "2026-04-05",
                "availability": 10,
                "price": 200.0,
                "verify": True,
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert data.get("success") is True, f"Expected success=True, got {data}"
        assert data.get("operation") == "ari_push"
        assert data.get("mode") == "dry_run"
        assert "correlation_id" in data
        assert data["correlation_id"].startswith("dr-")
        assert "request_payload" in data
        assert "noop_response" in data
        assert data["noop_response"].get("success") is True
        assert "duration_ms" in data
        assert "created_at" in data
        
        # Verify payload was built correctly
        payload = data["request_payload"]
        assert payload.get("inv_code") == "HR:TEST-DR-001"
        assert payload.get("start_date") == "2026-04-01"
        assert payload.get("end_date") == "2026-04-05"
        
        # Verify consistency check
        assert "consistency_check" in data
        assert data["consistency_check"].get("pass") is True
        
        print(f"✓ Dry-run ARI push successful: correlation_id={data['correlation_id']}, duration={data['duration_ms']}ms")

    def test_dry_run_ari_push_with_all_fields(self):
        """Test dry-run ARI push with all optional fields"""
        response = requests.post(
            f"{BASE_URL}/api/channel/hotelrunner-v2/dry-run/ari-push",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID},
            json={
                "inv_code": "HR:TEST-DR-002",
                "start_date": "2026-04-10",
                "end_date": "2026-04-15",
                "availability": 5,
                "price": 250.0,
                "stop_sale": False,
                "min_stay": 2,
                "cta": True,
                "ctd": False,
                "days": [1, 2, 3, 4, 5],
                "channel_codes": ["BOOKING", "EXPEDIA"],
                "verify": True,
            },
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("success") is True
        # min_stay is converted to string by the mapper
        assert data["request_payload"].get("min_stay") in [2, "2"]
        print(f"✓ Dry-run ARI push with all fields: correlation_id={data['correlation_id']}")


class TestDryRunConfirmDelivery:
    """Tests for POST /dry-run/confirm-delivery endpoint"""

    def test_dry_run_confirm_delivery_success(self):
        """Test successful dry-run confirm delivery"""
        response = requests.post(
            f"{BASE_URL}/api/channel/hotelrunner-v2/dry-run/confirm-delivery",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID},
            json={
                "message_uid": "test-msg-uid-12345",
                "pms_number": "PMS-RES-001",
            },
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") is True
        assert data.get("operation") == "confirm_delivery"
        assert data.get("mode") == "dry_run"
        assert "correlation_id" in data
        assert data["request_payload"].get("message_uid") == "test-msg-uid-12345"
        assert data["request_payload"].get("pms_number") == "PMS-RES-001"
        
        print(f"✓ Dry-run confirm delivery successful: correlation_id={data['correlation_id']}")


class TestDryRunChain:
    """Tests for POST /dry-run/chain endpoint (create/modify/cancel sequence)"""

    def test_dry_run_chain_success(self):
        """Test successful dry-run chain (3 steps: create, modify, cancel)"""
        response = requests.post(
            f"{BASE_URL}/api/channel/hotelrunner-v2/dry-run/chain",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID},
            json={},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("operation") == "dry_run_chain"
        assert data.get("mode") == "dry_run"
        assert "correlation_id" in data
        assert data["correlation_id"].startswith("dr-chain-")
        
        # Verify 3 steps
        assert data.get("step_count") == 3
        assert "steps" in data
        assert len(data["steps"]) == 3
        
        # Verify step names
        step_names = [s.get("step") for s in data["steps"]]
        assert step_names == ["create", "modify", "cancel"]
        
        # Verify success counts
        assert data.get("success_count") == 3
        assert data.get("failure_count") == 0
        assert data.get("success") is True
        
        print(f"✓ Dry-run chain successful: {data['success_count']}/{data['step_count']} steps, correlation_id={data['correlation_id']}")

    def test_dry_run_chain_with_partial_failure(self):
        """Test dry-run chain with simulated failure on modify step"""
        response = requests.post(
            f"{BASE_URL}/api/channel/hotelrunner-v2/dry-run/chain",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID},
            json={
                "simulate_failures": {
                    "modify": "validation_error",
                },
            },
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("step_count") == 3
        assert data.get("success_count") == 2  # create and cancel succeed
        assert data.get("failure_count") == 1  # modify fails
        assert data.get("success") is False  # overall chain fails
        
        # Verify modify step failed
        modify_step = next((s for s in data["steps"] if s.get("step") == "modify"), None)
        assert modify_step is not None
        assert modify_step.get("success") is False
        
        print(f"✓ Dry-run chain with partial failure: {data['success_count']}/{data['step_count']} steps")


class TestDryRunSimulateFailure:
    """Tests for POST /dry-run/simulate-failure endpoint"""

    def test_simulate_timeout_failure(self):
        """Test timeout failure simulation"""
        response = requests.post(
            f"{BASE_URL}/api/channel/hotelrunner-v2/dry-run/simulate-failure",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID},
            json={"failure_type": "timeout"},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("success") is False
        assert data.get("failure_simulation") == "timeout"
        assert "noop_response" in data
        assert data["noop_response"].get("error_category") == "timeout"
        assert data["noop_response"].get("simulated") is True
        
        print(f"✓ Timeout simulation: correlation_id={data['correlation_id']}")

    def test_simulate_validation_error_failure(self):
        """Test validation_error failure simulation"""
        response = requests.post(
            f"{BASE_URL}/api/channel/hotelrunner-v2/dry-run/simulate-failure",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID},
            json={"failure_type": "validation_error"},
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("success") is False
        assert data.get("failure_simulation") == "validation_error"
        assert data["noop_response"].get("error_category") == "validation"
        
        print(f"✓ Validation error simulation: correlation_id={data['correlation_id']}")

    def test_simulate_rate_limit_failure(self):
        """Test rate_limit failure simulation"""
        response = requests.post(
            f"{BASE_URL}/api/channel/hotelrunner-v2/dry-run/simulate-failure",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID},
            json={"failure_type": "rate_limit"},
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("success") is False
        assert data.get("failure_simulation") == "rate_limit"
        assert data["noop_response"].get("error_category") == "rate_limit"
        
        print(f"✓ Rate limit simulation: correlation_id={data['correlation_id']}")


class TestDryRunResults:
    """Tests for GET /dry-run/results endpoint"""

    def test_get_dry_run_results(self):
        """Test getting dry-run execution history"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/dry-run/results",
            params={"tenant_id": TENANT_ID, "limit": 20},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "results" in data
        assert "count" in data
        assert isinstance(data["results"], list)
        
        # Verify results have expected fields
        if data["count"] > 0:
            result = data["results"][0]
            assert "id" in result
            assert "tenant_id" in result
            assert "operation" in result
            assert "mode" in result
            assert "success" in result
            assert "correlation_id" in result
            assert "created_at" in result
        
        print(f"✓ Dry-run results: {data['count']} entries")

    def test_get_dry_run_results_filtered_by_operation(self):
        """Test getting dry-run results filtered by operation type"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/dry-run/results",
            params={"tenant_id": TENANT_ID, "limit": 10, "operation": "ari_push"},
        )
        assert response.status_code == 200
        
        data = response.json()
        # All results should be ari_push operations
        for result in data["results"]:
            assert result.get("operation") == "ari_push"
        
        print(f"✓ Dry-run results filtered by ari_push: {data['count']} entries")


class TestDryRunStats:
    """Tests for GET /dry-run/stats endpoint"""

    def test_get_dry_run_stats(self):
        """Test getting dry-run statistics"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/dry-run/stats",
            params={"tenant_id": TENANT_ID},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert data.get("tenant_id") == TENANT_ID
        assert "calculated_at" in data
        assert "operations" in data
        assert "total_runs" in data
        assert "total_success" in data
        assert "total_failed" in data
        assert "overall_success_rate" in data
        assert "failure_breakdown" in data
        
        # Verify we have some runs from previous tests
        assert data["total_runs"] > 0, "Expected at least 1 dry-run from previous tests"
        
        # Verify failure breakdown exists (we ran failure simulations)
        assert isinstance(data["failure_breakdown"], dict)
        
        # Verify last_result exists
        assert "last_result" in data
        if data["last_result"]:
            assert "operation" in data["last_result"]
            assert "success" in data["last_result"]
            assert "correlation_id" in data["last_result"]
        
        print(f"✓ Dry-run stats: {data['total_runs']} runs, {data['overall_success_rate']}% success rate")
        print(f"  Failure breakdown: {data['failure_breakdown']}")


class TestWriteEnableCriteria:
    """Tests for GET /dry-run/write-criteria endpoint"""

    def test_get_write_criteria(self):
        """Test getting write enable criteria check"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/dry-run/write-criteria",
            params={"tenant_id": TENANT_ID},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify response structure
        assert data.get("tenant_id") == TENANT_ID
        assert "checked_at" in data
        assert "all_criteria_met" in data
        assert "met_count" in data
        assert "total_criteria" in data
        assert "write_ready" in data
        assert "criteria" in data
        
        # Verify 6 criteria
        assert data["total_criteria"] == 6, f"Expected 6 criteria, got {data['total_criteria']}"
        assert len(data["criteria"]) == 6
        
        # Verify criteria names
        criteria_names = [c["name"] for c in data["criteria"]]
        expected_names = ["readiness_score", "drift_low", "dry_run_success_rate", "dlq_empty", "retry_stable", "chain_success"]
        assert set(criteria_names) == set(expected_names), f"Expected criteria {expected_names}, got {criteria_names}"
        
        # Verify each criterion has required fields
        for criterion in data["criteria"]:
            assert "name" in criterion
            assert "label" in criterion
            assert "met" in criterion
            assert "current_value" in criterion
            assert "required_value" in criterion
        
        print(f"✓ Write criteria: {data['met_count']}/{data['total_criteria']} met, write_ready={data['write_ready']}")
        for c in data["criteria"]:
            status = "✓" if c["met"] else "✗"
            print(f"  {status} {c['label']}: {c['current_value']} (required: {c['required_value']})")


class TestOpsDashboardDryRunFields:
    """Tests for dry_run and write_criteria fields in ops-dashboard"""

    def test_ops_dashboard_includes_dry_run_fields(self):
        """Test that ops-dashboard includes dry_run and write_criteria fields"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/ops-dashboard",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # Verify dry_run field exists
        assert "dry_run" in data, "Expected 'dry_run' field in ops-dashboard response"
        dry_run = data["dry_run"]
        assert "total_runs" in dry_run
        assert "success_rate" in dry_run
        assert "total_success" in dry_run
        assert "total_failed" in dry_run
        assert "failure_breakdown" in dry_run
        assert "last_result" in dry_run
        assert "last_chain" in dry_run
        assert "operations" in dry_run
        
        # Verify write_criteria field exists
        assert "write_criteria" in data, "Expected 'write_criteria' field in ops-dashboard response"
        write_criteria = data["write_criteria"]
        assert "all_met" in write_criteria
        assert "met_count" in write_criteria
        assert "total_criteria" in write_criteria
        assert "criteria" in write_criteria
        assert write_criteria["total_criteria"] == 6
        
        print(f"✓ Ops dashboard includes dry_run: {dry_run['total_runs']} runs, {dry_run['success_rate']}% success")
        print(f"✓ Ops dashboard includes write_criteria: {write_criteria['met_count']}/{write_criteria['total_criteria']} met")


class TestFeatureFlagsDryRunMode:
    """Tests for dry_run_mode feature flag"""

    def test_feature_flags_include_dry_run_mode(self):
        """Test that feature flags include dry_run_mode"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/flags",
            params={"tenant_id": TENANT_ID},
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "dry_run_mode" in data, "Expected 'dry_run_mode' in feature flags"
        
        print(f"✓ Feature flags include dry_run_mode: {data['dry_run_mode']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
