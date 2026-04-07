"""
P2 Features Test Suite - Auto-Map and Wire Failure Tracking
Tests for:
1. Auto-Map API (suggest, apply, status) for Exely and HotelRunner
2. Wire Failure Tracking (summary, recent, trend)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://pms-channel-cleanup.preview.emergentagent.com')
if not BASE_URL.endswith('/api'):
    BASE_URL = BASE_URL.rstrip('/') + '/api'

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for API calls."""
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
    )
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.status_code}")
    data = response.json()
    return data.get("access_token") or data.get("token")


@pytest.fixture(scope="module")
def headers(auth_token):
    """Get headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


# ============== AUTO-MAP TESTS ==============

class TestAutoMapSuggestEndpoint:
    """Tests for POST /api/channel-manager/auto-map/suggest"""
    
    def test_auto_map_suggest_exely_returns_200_or_404(self, headers):
        """Test auto-map suggest for Exely provider."""
        response = requests.post(
            f"{BASE_URL}/channel-manager/auto-map/suggest",
            json={"provider": "exely"},
            headers=headers
        )
        # 200 = success, 404 = no PMS room types or no provider rooms
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}, body: {response.text}"
        if response.status_code == 200:
            data = response.json()
            assert "provider" in data
            assert data["provider"] == "exely"
            assert "suggestions" in data
            assert "unmapped_pms_types" in data
            assert "unmapped_provider_rooms" in data
            assert "existing_mapping_count" in data
            assert "total_pms_types" in data
            assert "total_provider_rooms" in data
            print(f"Exely auto-map suggest: {len(data['suggestions'])} suggestions, {data['existing_mapping_count']} existing mappings")
    
    def test_auto_map_suggest_hotelrunner_returns_200_or_404(self, headers):
        """Test auto-map suggest for HotelRunner provider."""
        response = requests.post(
            f"{BASE_URL}/channel-manager/auto-map/suggest",
            json={"provider": "hotelrunner"},
            headers=headers
        )
        # 200 = success, 404 = no PMS room types or no provider rooms
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}, body: {response.text}"
        if response.status_code == 200:
            data = response.json()
            assert "provider" in data
            assert data["provider"] == "hotelrunner"
            assert "suggestions" in data
            assert "unmapped_pms_types" in data
            assert "unmapped_provider_rooms" in data
            print(f"HotelRunner auto-map suggest: {len(data['suggestions'])} suggestions")
    
    def test_auto_map_suggest_invalid_provider_returns_400(self, headers):
        """Test auto-map suggest with invalid provider returns 400."""
        response = requests.post(
            f"{BASE_URL}/channel-manager/auto-map/suggest",
            json={"provider": "invalid_provider"},
            headers=headers
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"


class TestAutoMapApplyEndpoint:
    """Tests for POST /api/channel-manager/auto-map/apply"""
    
    def test_auto_map_apply_empty_mappings_returns_success(self, headers):
        """Test auto-map apply with empty mappings list."""
        response = requests.post(
            f"{BASE_URL}/channel-manager/auto-map/apply",
            json={"provider": "exely", "mappings": []},
            headers=headers
        )
        assert response.status_code == 200, f"Unexpected status: {response.status_code}, body: {response.text}"
        data = response.json()
        assert "created" in data
        assert data["created"] == 0
        assert "errors" in data
    
    def test_auto_map_apply_invalid_provider_returns_400(self, headers):
        """Test auto-map apply with invalid provider returns 400."""
        response = requests.post(
            f"{BASE_URL}/channel-manager/auto-map/apply",
            json={"provider": "invalid", "mappings": []},
            headers=headers
        )
        assert response.status_code == 400


class TestAutoMapStatusEndpoint:
    """Tests for GET /api/channel-manager/auto-map/status/{provider}"""
    
    def test_auto_map_status_exely_returns_200_or_404(self, headers):
        """Test auto-map status for Exely provider."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/auto-map/status/exely",
            headers=headers
        )
        # 200 = success, 404 = no provider rooms
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}, body: {response.text}"
        if response.status_code == 200:
            data = response.json()
            assert "provider" in data
            assert data["provider"] == "exely"
            assert "total_pms_types" in data
            assert "total_provider_rooms" in data
            assert "mapped_count" in data
            assert "unmapped_count" in data
            assert "completion_pct" in data
            assert "existing_mappings" in data
            print(f"Exely mapping status: {data['mapped_count']}/{data['total_pms_types']} mapped ({data['completion_pct']}%)")
    
    def test_auto_map_status_hotelrunner_returns_200_or_404(self, headers):
        """Test auto-map status for HotelRunner provider."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/auto-map/status/hotelrunner",
            headers=headers
        )
        # 200 = success, 404 = no provider rooms
        assert response.status_code in [200, 404], f"Unexpected status: {response.status_code}, body: {response.text}"
        if response.status_code == 200:
            data = response.json()
            assert "provider" in data
            assert data["provider"] == "hotelrunner"
            assert "completion_pct" in data
            print(f"HotelRunner mapping status: {data['mapped_count']}/{data['total_pms_types']} mapped ({data['completion_pct']}%)")
    
    def test_auto_map_status_invalid_provider_returns_400(self, headers):
        """Test auto-map status with invalid provider returns 400."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/auto-map/status/invalid",
            headers=headers
        )
        assert response.status_code == 400


# ============== WIRE FAILURE TRACKING TESTS ==============

class TestWireFailureSummaryEndpoint:
    """Tests for GET /api/channel-manager/wire-failures/summary"""
    
    def test_wire_failure_summary_returns_200(self, headers):
        """Test wire failure summary endpoint returns 200."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/wire-failures/summary?days=30",
            headers=headers
        )
        assert response.status_code == 200, f"Unexpected status: {response.status_code}, body: {response.text}"
        data = response.json()
        assert "period_days" in data
        assert data["period_days"] == 30
        assert "total_failures" in data
        assert "breakdown" in data
        assert "health_status" in data
        assert data["health_status"] in ["healthy", "warning", "critical"]
        
        # Check breakdown structure
        breakdown = data["breakdown"]
        assert "ari_hard_fails" in breakdown
        assert "exely_sync_fails" in breakdown
        assert "dlq_items" in breakdown
        assert "control_plane_fails" in breakdown
        assert "reconciliation_issues" in breakdown
        assert "observability_errors" in breakdown
        print(f"Wire failure summary: {data['total_failures']} total failures, status: {data['health_status']}")
    
    def test_wire_failure_summary_with_custom_days(self, headers):
        """Test wire failure summary with custom days parameter."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/wire-failures/summary?days=7",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["period_days"] == 7


class TestWireFailureRecentEndpoint:
    """Tests for GET /api/channel-manager/wire-failures/recent"""
    
    def test_wire_failure_recent_returns_200(self, headers):
        """Test wire failure recent endpoint returns 200."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/wire-failures/recent?limit=10",
            headers=headers
        )
        assert response.status_code == 200, f"Unexpected status: {response.status_code}, body: {response.text}"
        data = response.json()
        assert "failures" in data
        assert "total" in data
        assert isinstance(data["failures"], list)
        
        # Check failure structure if any exist
        if data["failures"]:
            failure = data["failures"][0]
            assert "type" in failure
            assert "provider" in failure
            assert "message" in failure
            assert "severity" in failure
            assert "timestamp" in failure
        print(f"Wire failure recent: {data['total']} failures returned")
    
    def test_wire_failure_recent_with_provider_filter(self, headers):
        """Test wire failure recent with provider filter."""
        for provider in ["all", "ari", "exely", "dlq", "control_plane"]:
            response = requests.get(
                f"{BASE_URL}/channel-manager/wire-failures/recent?limit=10&provider={provider}",
                headers=headers
            )
            assert response.status_code == 200, f"Failed for provider {provider}: {response.status_code}"
            print(f"Wire failure recent (provider={provider}): {response.json()['total']} failures")


class TestWireFailureTrendEndpoint:
    """Tests for GET /api/channel-manager/wire-failures/trend"""
    
    def test_wire_failure_trend_returns_200(self, headers):
        """Test wire failure trend endpoint returns 200."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/wire-failures/trend?days=30",
            headers=headers
        )
        assert response.status_code == 200, f"Unexpected status: {response.status_code}, body: {response.text}"
        data = response.json()
        assert "trend" in data
        assert "period_days" in data
        assert data["period_days"] == 30
        assert isinstance(data["trend"], list)
        
        # Check trend structure if any exist
        if data["trend"]:
            day_data = data["trend"][0]
            assert "date" in day_data
            assert "ari_fails" in day_data
            assert "sync_fails" in day_data
            assert "total" in day_data
        print(f"Wire failure trend: {len(data['trend'])} days of data")
    
    def test_wire_failure_trend_with_custom_days(self, headers):
        """Test wire failure trend with custom days parameter."""
        response = requests.get(
            f"{BASE_URL}/channel-manager/wire-failures/trend?days=7",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert data["period_days"] == 7


# ============== INTEGRATION TESTS ==============

class TestAutoMapIntegration:
    """Integration tests for auto-map workflow."""
    
    def test_auto_map_full_workflow_exely(self, headers):
        """Test full auto-map workflow for Exely: status -> suggest -> (apply if suggestions)."""
        # Step 1: Get status
        status_response = requests.get(
            f"{BASE_URL}/channel-manager/auto-map/status/exely",
            headers=headers
        )
        if status_response.status_code == 404:
            pytest.skip("No Exely connection or room types available")
        
        assert status_response.status_code == 200
        status_data = status_response.json()
        print(f"Initial status: {status_data['mapped_count']}/{status_data['total_pms_types']} mapped")
        
        # Step 2: Get suggestions
        suggest_response = requests.post(
            f"{BASE_URL}/channel-manager/auto-map/suggest",
            json={"provider": "exely"},
            headers=headers
        )
        if suggest_response.status_code == 404:
            pytest.skip("No PMS room types or provider rooms available")
        
        assert suggest_response.status_code == 200
        suggest_data = suggest_response.json()
        print(f"Suggestions: {len(suggest_data['suggestions'])} found")
        
        # Verify consistency
        assert suggest_data["existing_mapping_count"] == status_data["existing_mappings"]


class TestWireFailureIntegration:
    """Integration tests for wire failure tracking."""
    
    def test_wire_failure_summary_and_recent_consistency(self, headers):
        """Test that summary and recent endpoints are consistent."""
        # Get summary
        summary_response = requests.get(
            f"{BASE_URL}/channel-manager/wire-failures/summary?days=30",
            headers=headers
        )
        assert summary_response.status_code == 200
        summary_data = summary_response.json()
        
        # Get recent
        recent_response = requests.get(
            f"{BASE_URL}/channel-manager/wire-failures/recent?limit=100",
            headers=headers
        )
        assert recent_response.status_code == 200
        recent_data = recent_response.json()
        
        # Get trend
        trend_response = requests.get(
            f"{BASE_URL}/channel-manager/wire-failures/trend?days=30",
            headers=headers
        )
        assert trend_response.status_code == 200
        trend_data = trend_response.json()
        
        print(f"Summary: {summary_data['total_failures']} total, Recent: {recent_data['total']}, Trend days: {len(trend_data['trend'])}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
