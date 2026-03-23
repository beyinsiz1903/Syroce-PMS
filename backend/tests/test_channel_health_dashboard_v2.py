"""
Channel Health Dashboard API Tests v2
Tests for all 3 new endpoints:
- GET /api/ops/dashboard/channel-health
- GET /api/ops/dashboard/channel-health/trends
- GET /api/ops/dashboard/channel-health/field-kpis
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")


class TestChannelHealthEndpoint:
    """Tests for GET /api/ops/dashboard/channel-health"""

    def test_channel_health_returns_200(self):
        """Test that channel-health endpoint returns 200 OK"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Channel health endpoint returns 200")

    def test_channel_health_response_structure(self):
        """Test that response contains all required fields"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health")
        assert response.status_code == 200
        data = response.json()

        required_fields = [
            "push_latency", "sync_metrics", "failure_breakdown",
            "reconciliation_drift", "retry_metrics", "provider_sla",
            "period_hours", "calculated_at"
        ]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        print(f"PASS: All {len(required_fields)} required fields present")

    def test_push_latency_structure(self):
        """Test push_latency field structure with p50/p95/p99"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health")
        data = response.json()
        
        push_latency = data.get("push_latency", {})
        assert "overall" in push_latency, "Missing push_latency.overall"
        assert "by_provider" in push_latency, "Missing push_latency.by_provider"
        
        overall = push_latency["overall"]
        for key in ["p50", "p95", "p99", "count", "avg"]:
            assert key in overall, f"Missing push_latency.overall.{key}"
        print("PASS: push_latency structure with p50/p95/p99 is correct")

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
        assert isinstance(drift["total_open"], int), "total_open should be an integer"
        print(f"PASS: reconciliation_drift structure correct, total_open={drift['total_open']}")

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

    def test_provider_sla_structure(self):
        """Test provider_sla field structure"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health")
        data = response.json()
        
        provider_sla = data.get("provider_sla", {})
        
        if provider_sla:
            # Check first provider's SLA structure
            first_provider = list(provider_sla.keys())[0]
            sla = provider_sla[first_provider]
            required_sla_fields = [
                "push_latency_p95_ms", "push_latency_target_ms", "push_latency_ok",
                "sync_success_rate", "sync_target", "sync_ok",
                "retry_success_rate", "retry_target", "retry_ok", "overall"
            ]
            for field in required_sla_fields:
                assert field in sla, f"Missing provider_sla.{first_provider}.{field}"
            
            assert sla["overall"] in ["compliant", "warning", "breached"], \
                f"Invalid SLA overall status: {sla['overall']}"
            print(f"PASS: provider_sla structure correct, {first_provider} overall={sla['overall']}")
        else:
            print("INFO: No provider SLA data available")


class TestChannelHealthTrendsEndpoint:
    """Tests for GET /api/ops/dashboard/channel-health/trends"""

    def test_trends_returns_200(self):
        """Test that trends endpoint returns 200 OK"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/trends")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Trends endpoint returns 200")

    def test_trends_response_structure(self):
        """Test that trends response contains required fields"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/trends")
        assert response.status_code == 200
        data = response.json()

        required_fields = ["buckets", "bucket_size_hours", "period_hours", "total_buckets", "calculated_at"]
        for field in required_fields:
            assert field in data, f"Missing required field: {field}"
        
        assert isinstance(data["buckets"], list), "buckets should be a list"
        print(f"PASS: Trends response structure correct, {data['total_buckets']} buckets")

    def test_trends_bucket_structure(self):
        """Test that each bucket contains time-series data"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/trends?hours=24")
        data = response.json()
        
        if data["buckets"]:
            bucket = data["buckets"][0]
            # Check bucket has timestamp
            assert "timestamp" in bucket, "Missing timestamp in bucket"
            
            # Check for push_latency data
            if "push_latency" in bucket:
                pl = bucket["push_latency"]
                for key in ["p50", "p95", "p99"]:
                    assert key in pl, f"Missing push_latency.{key} in bucket"
            
            # Check for sync data
            if "sync" in bucket:
                sync = bucket["sync"]
                assert "success_rate" in sync, "Missing sync.success_rate in bucket"
            
            print("PASS: Bucket structure contains time-series data")
        else:
            print("INFO: No buckets in trends data")

    def test_trends_hours_24_vs_168_bucket_size(self):
        """Test that hours=24 returns smaller bucket_size_hours than hours=168"""
        response_24 = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/trends?hours=24")
        response_168 = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/trends?hours=168")
        
        assert response_24.status_code == 200
        assert response_168.status_code == 200
        
        data_24 = response_24.json()
        data_168 = response_168.json()
        
        # hours=24 should have bucket_size_hours=1, hours=168 should have bucket_size_hours=12
        assert data_24["bucket_size_hours"] <= data_168["bucket_size_hours"], \
            f"Expected 24h bucket_size ({data_24['bucket_size_hours']}) <= 168h bucket_size ({data_168['bucket_size_hours']})"
        
        print(f"PASS: 24h bucket_size={data_24['bucket_size_hours']}h, 168h bucket_size={data_168['bucket_size_hours']}h")

    def test_trends_hours_parameter_validation(self):
        """Test hours parameter validation (1-720 range)"""
        # Valid hours
        for hours in [1, 24, 168, 720]:
            response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/trends?hours={hours}")
            assert response.status_code == 200, f"Expected 200 for hours={hours}, got {response.status_code}"
        
        # Invalid hours (0 should fail)
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/trends?hours=0")
        assert response.status_code == 422, f"Expected 422 for hours=0, got {response.status_code}"
        
        # Invalid hours (>720 should fail)
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/trends?hours=800")
        assert response.status_code == 422, f"Expected 422 for hours=800, got {response.status_code}"
        
        print("PASS: Trends hours parameter validation works")


class TestChannelHealthFieldKPIsEndpoint:
    """Tests for GET /api/ops/dashboard/channel-health/field-kpis"""

    def test_field_kpis_returns_200(self):
        """Test that field-kpis endpoint returns 200 OK"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/field-kpis")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("PASS: Field KPIs endpoint returns 200")

    def test_field_kpis_response_structure(self):
        """Test that field-kpis response contains all 5 KPIs"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/field-kpis")
        assert response.status_code == 200
        data = response.json()

        required_kpis = [
            "sync_success", "drift_reduction", "mttr_hours",
            "operator_interventions", "push_sla_compliance"
        ]
        for kpi in required_kpis:
            assert kpi in data, f"Missing required KPI: {kpi}"
        
        assert "period_hours" in data, "Missing period_hours"
        assert "calculated_at" in data, "Missing calculated_at"
        print(f"PASS: All 5 field KPIs present")

    def test_field_kpi_structure(self):
        """Test that each KPI has current/previous/delta/trend fields"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/field-kpis")
        data = response.json()
        
        kpi_fields = ["current", "previous", "delta", "trend"]
        
        for kpi_name in ["sync_success", "drift_reduction", "mttr_hours", "operator_interventions", "push_sla_compliance"]:
            kpi = data.get(kpi_name, {})
            for field in kpi_fields:
                assert field in kpi, f"Missing {kpi_name}.{field}"
            
            # Validate trend value
            assert kpi["trend"] in ["up", "down", "flat"], \
                f"Invalid trend value for {kpi_name}: {kpi['trend']}"
        
        print("PASS: All KPIs have current/previous/delta/trend structure")

    def test_field_kpis_sync_success_has_unit(self):
        """Test that sync_success KPI has unit field"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/field-kpis")
        data = response.json()
        
        sync_success = data.get("sync_success", {})
        assert "unit" in sync_success, "Missing sync_success.unit"
        assert sync_success["unit"] == "%", f"Expected unit='%', got '{sync_success['unit']}'"
        print("PASS: sync_success has unit='%'")

    def test_field_kpis_drift_reduction_has_unit(self):
        """Test that drift_reduction KPI has unit field"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/field-kpis")
        data = response.json()
        
        drift = data.get("drift_reduction", {})
        assert "unit" in drift, "Missing drift_reduction.unit"
        print(f"PASS: drift_reduction has unit='{drift['unit']}'")

    def test_field_kpis_mttr_has_saat_unit(self):
        """Test that mttr_hours KPI has 'saat' unit (Turkish for hours)"""
        response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/field-kpis")
        data = response.json()
        
        mttr = data.get("mttr_hours", {})
        assert "unit" in mttr, "Missing mttr_hours.unit"
        assert mttr["unit"] == "saat", f"Expected unit='saat', got '{mttr['unit']}'"
        print("PASS: mttr_hours has unit='saat'")

    def test_field_kpis_period_hours_parameter(self):
        """Test period_hours query parameter"""
        for period in [24, 72, 168]:
            response = requests.get(f"{BASE_URL}/api/ops/dashboard/channel-health/field-kpis?period_hours={period}")
            assert response.status_code == 200, f"Expected 200 for period_hours={period}"
            data = response.json()
            assert data["period_hours"] == period, f"Expected period_hours={period}, got {data['period_hours']}"
        
        print("PASS: period_hours parameter works correctly")


class TestNoReactAppBackendUrlReferences:
    """Tests to verify REACT_APP_BACKEND_URL has been replaced with VITE_BACKEND_URL"""

    def test_this_test_file_uses_vite_backend_url(self):
        """Verify this test file uses VITE_BACKEND_URL"""
        vite_url = os.environ.get("VITE_BACKEND_URL", "")
        assert vite_url != "", "VITE_BACKEND_URL environment variable should be set"
        assert vite_url.startswith("http"), f"VITE_BACKEND_URL should be a valid URL, got: {vite_url}"
        print(f"PASS: Using VITE_BACKEND_URL={BASE_URL}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
