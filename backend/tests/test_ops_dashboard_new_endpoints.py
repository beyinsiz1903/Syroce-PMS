"""
Test: Ops Dashboard New Endpoints — Inventory Alignment, DORA Metrics, DORA Correlation
========================================================================================
Tests the 3 new endpoints added for Unified Ops View:
1. GET /api/ops/dashboard/inventory-alignment
2. GET /api/ops/dashboard/dora-metrics
3. GET /api/ops/dashboard/dora-correlation

Also verifies existing endpoints still work:
4. GET /api/ops/dashboard/deploy-stats
5. GET /api/ops/dashboard/deploy-trend
"""
import pytest
import requests
import os

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://pms-messaging-hub.preview.emergentagent.com")


class TestInventoryAlignmentEndpoint:
    """Test GET /api/ops/dashboard/inventory-alignment"""

    def test_inventory_alignment_returns_200(self):
        """Endpoint should return 200 OK"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/inventory-alignment")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    def test_inventory_alignment_has_required_fields(self):
        """Response must include alignment_status, freshness, drift_count, drift_nights, provider_breakdown, connectors_checked"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/inventory-alignment")
        data = response.json()

        required_fields = [
            "alignment_status",
            "freshness",
            "drift_count",
            "drift_nights",
            "provider_breakdown",
            "connectors_checked",
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"

    def test_inventory_alignment_status_valid(self):
        """alignment_status must be one of: aligned, drift_detected, stale, no_data, reconcile_running"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/inventory-alignment")
        data = response.json()

        valid_statuses = {"aligned", "drift_detected", "stale", "no_data", "reconcile_running"}
        assert data["alignment_status"] in valid_statuses, (
            f"Invalid alignment_status: {data['alignment_status']}"
        )

    def test_inventory_alignment_freshness_valid(self):
        """freshness must be one of: fresh, recent, stale, empty"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/inventory-alignment")
        data = response.json()

        valid_freshness = {"fresh", "recent", "stale", "empty"}
        assert data["freshness"] in valid_freshness, (
            f"Invalid freshness: {data['freshness']}"
        )

    def test_inventory_alignment_provider_breakdown_is_list(self):
        """provider_breakdown must be a list"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/inventory-alignment")
        data = response.json()

        assert isinstance(data["provider_breakdown"], list), (
            f"provider_breakdown should be list, got {type(data['provider_breakdown'])}"
        )

    def test_inventory_alignment_with_days_ahead_param(self):
        """Endpoint should accept days_ahead parameter"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/inventory-alignment?days_ahead=7")
        assert response.status_code == 200
        data = response.json()
        assert "date_range" in data


class TestDoraMetricsEndpoint:
    """Test GET /api/ops/dashboard/dora-metrics"""

    def test_dora_metrics_returns_200(self):
        """Endpoint should return 200 OK"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/dora-metrics")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    def test_dora_metrics_has_metrics_object(self):
        """Response must include metrics object"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/dora-metrics")
        data = response.json()

        assert "metrics" in data, "Missing 'metrics' object"
        assert isinstance(data["metrics"], dict), "metrics should be a dict"

    def test_dora_metrics_has_four_metrics(self):
        """metrics object must have deployment_frequency, change_failure_rate, mttr, lead_time"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/dora-metrics")
        data = response.json()

        required_metrics = ["deployment_frequency", "change_failure_rate", "mttr", "lead_time"]
        for metric in required_metrics:
            assert metric in data["metrics"], f"Missing DORA metric: {metric}"

    def test_dora_metrics_each_has_value_and_rating(self):
        """Each metric must have value and rating fields"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/dora-metrics")
        data = response.json()

        for metric_name, metric_data in data["metrics"].items():
            assert "value" in metric_data, f"{metric_name} missing 'value'"
            assert "rating" in metric_data, f"{metric_name} missing 'rating'"

    def test_dora_metrics_rating_valid(self):
        """rating must be one of: elite, high, medium, low, no_data"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/dora-metrics")
        data = response.json()

        valid_ratings = {"elite", "high", "medium", "low", "no_data"}
        for metric_name, metric_data in data["metrics"].items():
            assert metric_data["rating"] in valid_ratings, (
                f"{metric_name} has invalid rating: {metric_data['rating']}"
            )

    def test_dora_metrics_with_days_param(self):
        """Endpoint should accept days parameter"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/dora-metrics?days=14")
        assert response.status_code == 200
        data = response.json()
        assert data["period_days"] == 14


class TestDoraCorrelationEndpoint:
    """Test GET /api/ops/dashboard/dora-correlation"""

    def test_dora_correlation_returns_200(self):
        """Endpoint should return 200 OK"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/dora-correlation")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    def test_dora_correlation_has_correlations_array(self):
        """Response must include correlations array"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/dora-correlation")
        data = response.json()

        assert "correlations" in data, "Missing 'correlations' array"
        assert isinstance(data["correlations"], list), "correlations should be a list"

    def test_dora_correlation_items_have_inference(self):
        """Each correlation item must have inference field"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/dora-correlation")
        data = response.json()

        for corr in data["correlations"]:
            assert "inference" in corr, f"Correlation missing 'inference': {corr.get('name', 'unknown')}"

    def test_dora_correlation_inference_valid(self):
        """inference must be one of valid values"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/dora-correlation")
        data = response.json()

        valid_inferences = {
            "positive_correlation", "inverse_correlation", "co_declining",
            "insufficient_data", "no_correlation", "improving", "stable", "degrading"
        }
        for corr in data["correlations"]:
            assert corr["inference"] in valid_inferences, (
                f"Invalid inference: {corr['inference']}"
            )


class TestExistingEndpointsStillWork:
    """Verify existing endpoints still work after new additions"""

    def test_deploy_stats_returns_200(self):
        """GET /api/ops/dashboard/deploy-stats should still work"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploy-stats")
        assert response.status_code == 200

    def test_deploy_trend_returns_200(self):
        """GET /api/ops/dashboard/deploy-trend should still work"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/deploy-trend")
        assert response.status_code == 200
        data = response.json()
        assert "trend" in data
        assert "days" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
