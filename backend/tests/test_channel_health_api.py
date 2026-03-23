"""
Channel Health Dashboard API Tests
Tests for GET /api/ops/dashboard/channel-health endpoint
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")


class TestChannelHealthAPI:
    """Tests for Channel Health Dashboard endpoint"""

    def test_channel_health_endpoint_returns_200(self):
        """Test that channel-health endpoint returns 200 OK"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Channel health endpoint returns 200")

    def test_channel_health_response_structure(self):
        """Test that response contains all required fields"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health")
        assert response.status_code == 200
        data = response.json()

        # Check all required top-level fields
        required_fields = [
            "push_latency",
            "sync_metrics",
            "failure_breakdown",
            "reconciliation_drift",
            "retry_metrics",
            "provider_summary",
            "provider_sla",
            "period_hours",
            "calculated_at",
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        print(f"PASS: All {len(required_fields)} required fields present")

    def test_push_latency_structure(self):
        """Test push_latency field structure"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health")
        data = response.json()
        
        push_latency = data.get("push_latency", {})
        assert "overall" in push_latency, "Missing push_latency.overall"
        assert "by_provider" in push_latency, "Missing push_latency.by_provider"
        
        overall = push_latency["overall"]
        for key in ["p50", "p95", "p99", "count", "avg"]:
            assert key in overall, f"Missing push_latency.overall.{key}"
        print("PASS: push_latency structure is correct")

    def test_sync_metrics_structure(self):
        """Test sync_metrics field structure"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health")
        data = response.json()
        
        sync_metrics = data.get("sync_metrics", {})
        assert "overall" in sync_metrics, "Missing sync_metrics.overall"
        assert "by_provider" in sync_metrics, "Missing sync_metrics.by_provider"
        
        overall = sync_metrics["overall"]
        for key in ["total", "completed", "success_rate"]:
            assert key in overall, f"Missing sync_metrics.overall.{key}"
        print("PASS: sync_metrics structure is correct")

    def test_reconciliation_drift_structure(self):
        """Test reconciliation_drift field structure"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health")
        data = response.json()
        
        drift = data.get("reconciliation_drift", {})
        assert "by_provider" in drift, "Missing reconciliation_drift.by_provider"
        assert "total_open" in drift, "Missing reconciliation_drift.total_open"
        
        # Verify total_open is a number
        assert isinstance(drift["total_open"], int), "total_open should be an integer"
        print(f"PASS: reconciliation_drift structure correct, total_open={drift['total_open']}")

    def test_provider_sla_structure(self):
        """Test provider_sla field structure"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health")
        data = response.json()
        
        provider_sla = data.get("provider_sla", {})
        
        # Check if hotelrunner provider exists (based on real data)
        if "hotelrunner" in provider_sla:
            sla = provider_sla["hotelrunner"]
            required_sla_fields = [
                "push_latency_p95_ms",
                "push_latency_target_ms",
                "push_latency_ok",
                "sync_success_rate",
                "sync_target",
                "sync_ok",
                "retry_success_rate",
                "retry_target",
                "retry_ok",
                "overall",
            ]
            for field in required_sla_fields:
                assert field in sla, f"Missing provider_sla.hotelrunner.{field}"
            
            # Verify overall is one of expected values
            assert sla["overall"] in ["compliant", "warning", "breached"], \
                f"Invalid SLA overall status: {sla['overall']}"
            print(f"PASS: provider_sla.hotelrunner structure correct, overall={sla['overall']}")
        else:
            print("INFO: No hotelrunner provider in SLA data")

    def test_hours_query_parameter(self):
        """Test that hours query parameter is accepted"""
        # Test with different hour values
        for hours in [1, 24, 48, 168]:
            response = requests.get(
                f"{BASE_URL}/api/ops/dashboard/channel-health",
                params={"hours": hours}
            )
            assert response.status_code == 200, f"Failed for hours={hours}"
            data = response.json()
            assert data["period_hours"] == hours, f"Expected period_hours={hours}, got {data['period_hours']}"
        print("PASS: hours query parameter works correctly")

    def test_hours_parameter_validation(self):
        """Test hours parameter validation (1-168 range)"""
        # Test invalid hours (0 should fail)
        response = requests.get(
            f"{BASE_URL}/api/ops/dashboard/channel-health",
            params={"hours": 0}
        )
        assert response.status_code == 422, "Expected 422 for hours=0"
        
        # Test invalid hours (>168 should fail)
        response = requests.get(
            f"{BASE_URL}/api/ops/dashboard/channel-health",
            params={"hours": 200}
        )
        assert response.status_code == 422, "Expected 422 for hours=200"
        print("PASS: hours parameter validation works")

    def test_retry_metrics_structure(self):
        """Test retry_metrics field structure"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health")
        data = response.json()
        
        retry_metrics = data.get("retry_metrics", {})
        assert "overall" in retry_metrics, "Missing retry_metrics.overall"
        assert "by_provider" in retry_metrics, "Missing retry_metrics.by_provider"
        
        overall = retry_metrics["overall"]
        for key in ["total_retried", "retried_success", "retry_success_rate"]:
            assert key in overall, f"Missing retry_metrics.overall.{key}"
        print("PASS: retry_metrics structure is correct")

    def test_failure_breakdown_structure(self):
        """Test failure_breakdown field structure"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health")
        data = response.json()
        
        failures = data.get("failure_breakdown", {})
        assert "overall" in failures, "Missing failure_breakdown.overall"
        assert "by_provider" in failures, "Missing failure_breakdown.by_provider"
        assert "total_failures" in failures, "Missing failure_breakdown.total_failures"
        print("PASS: failure_breakdown structure is correct")

    def test_provider_summary_structure(self):
        """Test provider_summary field structure"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health")
        data = response.json()
        
        provider_summary = data.get("provider_summary", {})
        
        # Check if hotelrunner exists
        if "hotelrunner" in provider_summary:
            summary = provider_summary["hotelrunner"]
            for key in ["total", "active", "inactive"]:
                assert key in summary, f"Missing provider_summary.hotelrunner.{key}"
            print(f"PASS: provider_summary.hotelrunner correct - {summary['active']} active connectors")
        else:
            print("INFO: No hotelrunner in provider_summary")

    def test_calculated_at_is_valid_timestamp(self):
        """Test that calculated_at is a valid ISO timestamp"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health")
        data = response.json()
        
        calculated_at = data.get("calculated_at")
        assert calculated_at is not None, "Missing calculated_at"
        
        # Should be ISO format with timezone
        from datetime import datetime
        try:
            # Try parsing ISO format
            datetime.fromisoformat(calculated_at.replace("Z", "+00:00"))
            print(f"PASS: calculated_at is valid ISO timestamp: {calculated_at}")
        except ValueError as e:
            pytest.fail(f"Invalid timestamp format: {calculated_at}, error: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
