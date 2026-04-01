"""
HotelRunner v2 Ops Dashboard API Tests
======================================
Tests for the /api/channel/hotelrunner-v2/ops-dashboard endpoint
and related operational endpoints.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://pms-channel-mgr.preview.emergentagent.com')
if not BASE_URL.endswith('/api'):
    BASE_URL = BASE_URL.rstrip('/') + '/api'

TENANT_ID = "syroce_default"
PROPERTY_ID = "default"


class TestHRv2OpsDashboard:
    """Tests for the HotelRunner v2 Ops Dashboard API"""
    
    def test_ops_dashboard_returns_200(self):
        """Test that ops-dashboard endpoint returns 200 OK"""
        response = requests.get(
            f"{BASE_URL}/channel/hotelrunner-v2/ops-dashboard",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify required top-level fields
        assert "generated_at" in data
        assert "tenant_id" in data
        assert data["tenant_id"] == TENANT_ID
        assert "property_id" in data
        assert data["property_id"] == PROPERTY_ID
    
    def test_ops_dashboard_provider_health(self):
        """Test provider_health section in ops-dashboard response"""
        response = requests.get(
            f"{BASE_URL}/channel/hotelrunner-v2/ops-dashboard",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify provider_health structure
        assert "provider_health" in data
        ph = data["provider_health"]
        
        assert "provider" in ph
        assert ph["provider"] == "HotelRunner"
        assert "connector_version" in ph
        assert ph["connector_version"] == "v2"
        assert "auth_status" in ph
        assert "reservations_api" in ph
        assert "shadow_mode" in ph
        assert "write_path" in ph
        assert "connector_enabled" in ph
    
    def test_ops_dashboard_feature_flags(self):
        """Test feature_flags section in ops-dashboard response"""
        response = requests.get(
            f"{BASE_URL}/channel/hotelrunner-v2/ops-dashboard",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify feature_flags structure
        assert "feature_flags" in data
        flags = data["feature_flags"]
        
        assert "connector_enabled" in flags
        assert "shadow_mode" in flags
        assert "write_enabled" in flags
        assert "reconciliation_enabled" in flags
        assert "auto_fix_enabled" in flags
        
        # Verify types
        assert isinstance(flags["connector_enabled"], bool)
        assert isinstance(flags["shadow_mode"], bool)
        assert isinstance(flags["write_enabled"], bool)
    
    def test_ops_dashboard_sync_overview(self):
        """Test sync_overview section in ops-dashboard response"""
        response = requests.get(
            f"{BASE_URL}/channel/hotelrunner-v2/ops-dashboard",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify sync_overview structure
        assert "sync_overview" in data
        sync = data["sync_overview"]
        
        assert "drift_count" in sync
        assert "last_reconciliation" in sync
        
        # Verify last_reconciliation structure
        recon = sync["last_reconciliation"]
        assert "run_id" in recon
        assert "timestamp" in recon
        assert "mismatch_count" in recon
        assert "duration_ms" in recon
    
    def test_ops_dashboard_metrics_24h(self):
        """Test metrics_24h section in ops-dashboard response"""
        response = requests.get(
            f"{BASE_URL}/channel/hotelrunner-v2/ops-dashboard",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify metrics_24h structure
        assert "metrics_24h" in data
        m24 = data["metrics_24h"]
        
        assert "tenant_id" in m24
        assert "period_hours" in m24
        assert m24["period_hours"] == 24
        assert "operations" in m24
        assert "total_operations" in m24
        assert "overall_success_rate" in m24
    
    def test_ops_dashboard_dlq(self):
        """Test dlq section in ops-dashboard response"""
        response = requests.get(
            f"{BASE_URL}/channel/hotelrunner-v2/ops-dashboard",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify dlq structure
        assert "dlq" in data
        dlq = data["dlq"]
        
        assert "count" in dlq
        assert "recent_entries" in dlq
        assert isinstance(dlq["count"], int)
        assert isinstance(dlq["recent_entries"], list)
    
    def test_ops_dashboard_recent_events(self):
        """Test recent_events section in ops-dashboard response"""
        response = requests.get(
            f"{BASE_URL}/channel/hotelrunner-v2/ops-dashboard",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify recent_events structure
        assert "recent_events" in data
        events = data["recent_events"]
        
        assert isinstance(events, list)
        
        # If there are events, verify structure
        if len(events) > 0:
            event = events[0]
            assert "operation" in event
            assert "success" in event
            assert "duration_ms" in event
            assert "recorded_at" in event
    
    def test_ops_dashboard_recent_drifts(self):
        """Test recent_drifts section in ops-dashboard response"""
        response = requests.get(
            f"{BASE_URL}/channel/hotelrunner-v2/ops-dashboard",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID}
        )
        assert response.status_code == 200
        data = response.json()
        
        # Verify recent_drifts structure
        assert "recent_drifts" in data
        drifts = data["recent_drifts"]
        
        assert isinstance(drifts, list)


class TestHRv2TestConnection:
    """Tests for the test-connection endpoint"""
    
    def test_test_connection_returns_success(self):
        """Test that test-connection endpoint works"""
        response = requests.post(
            f"{BASE_URL}/channel/hotelrunner-v2/test-connection",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "success" in data
        assert "steps" in data
        assert "total_latency_ms" in data
        
        # Verify steps structure
        steps = data["steps"]
        assert isinstance(steps, list)
        assert len(steps) > 0
        
        for step in steps:
            assert "step" in step
            assert "status" in step
            assert "latency_ms" in step


class TestHRv2Reconciliation:
    """Tests for the reconciliation endpoint"""
    
    def test_reconcile_returns_success(self):
        """Test that reconcile endpoint works"""
        response = requests.post(
            f"{BASE_URL}/channel/hotelrunner-v2/reconcile",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID, "since_hours": 24}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "success" in data
        assert "run_id" in data
        assert "hr_count" in data
        assert "pms_count" in data
        assert "mismatch_count" in data
        assert "duration_ms" in data


class TestHRv2FeatureFlags:
    """Tests for the feature flags endpoint"""
    
    def test_get_flags_returns_200(self):
        """Test that flags endpoint returns 200 OK"""
        response = requests.get(
            f"{BASE_URL}/channel/hotelrunner-v2/flags",
            params={"tenant_id": TENANT_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify required flags
        assert "connector_enabled" in data
        assert "shadow_mode" in data
        assert "write_enabled" in data
        assert "reconciliation_enabled" in data
        assert "auto_fix_enabled" in data


class TestHRv2Metrics:
    """Tests for the metrics endpoint"""
    
    def test_get_metrics_returns_200(self):
        """Test that metrics endpoint returns 200 OK"""
        response = requests.get(
            f"{BASE_URL}/channel/hotelrunner-v2/metrics",
            params={"tenant_id": TENANT_ID, "hours": 24}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "tenant_id" in data
        assert "period_hours" in data
        assert "operations" in data
        assert "total_operations" in data
        assert "overall_success_rate" in data


class TestHRv2Status:
    """Tests for the status endpoint"""
    
    def test_get_status_returns_200(self):
        """Test that status endpoint returns 200 OK"""
        response = requests.get(
            f"{BASE_URL}/channel/hotelrunner-v2/status",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        data = response.json()
        
        # Verify response structure
        assert "tenant_id" in data
        assert "property_id" in data
        assert "provider" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
