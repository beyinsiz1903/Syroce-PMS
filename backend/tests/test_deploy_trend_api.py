"""
Deploy Trend API Tests — CI/CD → Control Plane Integration
============================================================
Tests for the new deploy-trend endpoint and related deploy tracker features.

Features tested:
- GET /api/ops/dashboard/deploy-trend — Daily deploy activity trend
- POST /api/ops/deploys — Record deploy event
- GET /api/ops/dashboard/deploys — Deploy history
- GET /api/ops/dashboard/deploy-stats — Deploy statistics
- booking_adapter.py import fix verification
"""
import os
import pytest
import requests
import importlib

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")


class TestDeployTrendAPI:
    """Tests for the new deploy-trend endpoint."""

    def test_deploy_trend_endpoint_returns_200(self):
        """GET /api/ops/dashboard/deploy-trend returns 200."""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploy-trend?days=14")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("✅ deploy-trend endpoint returns 200")

    def test_deploy_trend_response_structure(self):
        """deploy-trend response has correct structure."""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploy-trend?days=14")
        data = response.json()
        
        assert "trend" in data, "Response missing 'trend' field"
        assert "days" in data, "Response missing 'days' field"
        assert isinstance(data["trend"], list), "'trend' should be a list"
        assert data["days"] == 14, f"Expected days=14, got {data['days']}"
        print(f"✅ deploy-trend structure valid: {len(data['trend'])} data points")

    def test_deploy_trend_data_fields(self):
        """Each trend item has required fields."""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploy-trend?days=14")
        data = response.json()
        
        if len(data["trend"]) > 0:
            item = data["trend"][0]
            required_fields = ["date", "total", "success", "failure", "rollbacks"]
            for field in required_fields:
                assert field in item, f"Trend item missing '{field}' field"
            print(f"✅ Trend item has all required fields: {required_fields}")
        else:
            print("⚠️ No trend data available (empty list)")

    def test_deploy_trend_custom_days_parameter(self):
        """deploy-trend accepts custom days parameter."""
        for days in [7, 30, 60]:
            response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploy-trend?days={days}")
            assert response.status_code == 200, f"Failed for days={days}"
            data = response.json()
            assert data["days"] == days, f"Expected days={days}, got {data['days']}"
        print("✅ deploy-trend accepts custom days parameter (7, 30, 60)")


class TestDeployHistoryAPI:
    """Tests for deploy history endpoint."""

    def test_deploy_history_returns_200(self):
        """GET /api/ops/dashboard/deploys returns 200."""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploys")
        assert response.status_code == 200
        print("✅ deploy history endpoint returns 200")

    def test_deploy_history_response_structure(self):
        """Deploy history has correct structure."""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploys")
        data = response.json()
        
        assert "deploys" in data, "Response missing 'deploys' field"
        assert "count" in data, "Response missing 'count' field"
        assert isinstance(data["deploys"], list), "'deploys' should be a list"
        print(f"✅ Deploy history structure valid: {data['count']} deploys")

    def test_deploy_history_item_fields(self):
        """Each deploy item has required fields."""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploys")
        data = response.json()
        
        if len(data["deploys"]) > 0:
            deploy = data["deploys"][0]
            required_fields = ["sha", "short_sha", "environment", "status", "actor", "branch", "smoke_test", "rollback", "recorded_at"]
            for field in required_fields:
                assert field in deploy, f"Deploy item missing '{field}' field"
            print(f"✅ Deploy item has all required fields")
        else:
            print("⚠️ No deploy data available")

    def test_deploy_history_smoke_test_badge_data(self):
        """Deploy items with smoke_test have endpoints array."""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploys")
        data = response.json()
        
        deploys_with_smoke = [d for d in data["deploys"] if d.get("smoke_test", {}).get("endpoints")]
        if deploys_with_smoke:
            smoke = deploys_with_smoke[0]["smoke_test"]
            assert "endpoints" in smoke, "smoke_test missing 'endpoints'"
            assert isinstance(smoke["endpoints"], list), "'endpoints' should be a list"
            if smoke["endpoints"]:
                ep = smoke["endpoints"][0]
                assert "path" in ep or "name" in ep, "Endpoint missing path/name"
                assert "status" in ep, "Endpoint missing status"
                assert "result" in ep, "Endpoint missing result"
            print(f"✅ Smoke test badge data valid: {len(smoke['endpoints'])} endpoints")
        else:
            print("⚠️ No deploys with smoke test data")


class TestDeployStatsAPI:
    """Tests for deploy statistics endpoint."""

    def test_deploy_stats_returns_200(self):
        """GET /api/ops/dashboard/deploy-stats returns 200."""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploy-stats")
        assert response.status_code == 200
        print("✅ deploy-stats endpoint returns 200")

    def test_deploy_stats_response_structure(self):
        """Deploy stats has correct structure."""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploy-stats")
        data = response.json()
        
        assert "by_environment" in data, "Response missing 'by_environment'"
        assert "overall" in data, "Response missing 'overall'"
        assert isinstance(data["by_environment"], list), "'by_environment' should be a list"
        print(f"✅ Deploy stats structure valid: {len(data['by_environment'])} environments")

    def test_deploy_stats_overall_fields(self):
        """Overall stats has required fields."""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploy-stats")
        data = response.json()
        
        overall = data["overall"]
        required_fields = ["total_deploys", "total_success", "total_failure", "total_rollbacks", "overall_success_rate"]
        for field in required_fields:
            assert field in overall, f"Overall stats missing '{field}'"
        print(f"✅ Overall stats: {overall['total_deploys']} deploys, {overall['overall_success_rate']}% success rate")


class TestRecordDeployAPI:
    """Tests for recording deploy events."""

    def test_record_deploy_returns_200(self):
        """POST /api/ops/deploys records a deploy event."""
        payload = {
            "sha": "test-trend-abc123def456",
            "environment": "test-trend-env",
            "status": "success",
            "actor": "pytest-trend-runner",
            "branch": "test-trend-branch",
            "smoke_test": {
                "endpoints": [
                    {"name": "Health", "path": "/api/health", "status": 200, "latency_ms": 50, "result": "OK"}
                ]
            },
            "rollback": False
        }
        response = requests.post(f"{BASE_URL}/api/ops/deploys", json=payload)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data.get("recorded") == True, "Deploy not recorded"
        assert data.get("environment") == "test-trend-env"
        print(f"✅ Deploy event recorded: {data.get('sha')} → {data.get('environment')}")


class TestBookingAdapterImportFix:
    """Tests for booking_adapter.py import fix."""

    def test_booking_adapter_import_no_error(self):
        """booking_adapter.py imports without ModuleNotFoundError."""
        import sys
        sys.path.insert(0, "/app/backend")
        
        try:
            # This should not raise ModuleNotFoundError
            from domains.pms.booking_adapter import BookingAdapter
            print("✅ booking_adapter imports successfully")
        except ModuleNotFoundError as e:
            pytest.fail(f"ModuleNotFoundError: {e}")
        except ImportError as e:
            pytest.fail(f"ImportError: {e}")

    def test_booking_adapter_class_exists(self):
        """BookingAdapter class is importable and has expected methods."""
        import sys
        sys.path.insert(0, "/app/backend")
        
        from booking_adapter import BookingAdapter
        
        adapter = BookingAdapter({})
        assert hasattr(adapter, "normalize_rate_update"), "Missing normalize_rate_update method"
        assert hasattr(adapter, "push_rates"), "Missing push_rates method"
        assert hasattr(adapter, "push_availability"), "Missing push_availability method"
        print("✅ BookingAdapter class has expected methods")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
