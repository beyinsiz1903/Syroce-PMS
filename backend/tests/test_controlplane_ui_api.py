"""
Control Plane UI API Tests
===========================
Tests for the Control Plane page backend APIs:
- Timeline API endpoints (Trace tab)
- Dashboard API endpoints (Health tab)
- Search API endpoints (Live Feed tab)

Test external_id: HR-VERIFY-1774179036 (has 4 timeline events from hotelrunner)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://test-shield-verified.preview.emergentagent.com')
if not BASE_URL.endswith('/api'):
    BASE_URL = BASE_URL.rstrip('/') + '/api'


class TestTimelineAPI:
    """Timeline API tests for Trace tab functionality"""
    
    def test_timeline_external_id_lookup(self):
        """GET /api/ops/timeline/external/{external_id} - Primary debug entry point"""
        response = requests.get(f"{BASE_URL}/ops/timeline/external/HR-VERIFY-1774179036")
        assert response.status_code == 200
        
        data = response.json()
        assert "timeline" in data
        assert "total_events" in data
        assert data["total_events"] == 4
        assert data["external_id"] == "HR-VERIFY-1774179036"
        assert data["entity_type"] == "reservation"
        
        # Verify timeline events
        timeline = data["timeline"]
        assert len(timeline) == 4
        
        # Check stages are in correct order
        stages = [e["stage"] for e in timeline]
        assert stages == ["webhook_received", "deduplicated", "normalized", "validated"]
        
        # Check all events have success status
        for event in timeline:
            assert event["status"] == "success"
            assert event["provider"] == "hotelrunner"
            
    def test_timeline_external_id_not_found(self):
        """GET /api/ops/timeline/external/{external_id} - Non-existent ID"""
        response = requests.get(f"{BASE_URL}/ops/timeline/external/NON-EXISTENT-ID-12345")
        assert response.status_code == 200
        
        data = response.json()
        assert data["total_events"] == 0
        assert "message" in data
        
    def test_timeline_search(self):
        """GET /api/ops/timeline/search - Search with filters"""
        response = requests.get(f"{BASE_URL}/ops/timeline/search", params={"limit": 50})
        assert response.status_code == 200
        
        data = response.json()
        assert "events" in data
        assert "total" in data
        assert "limit" in data
        assert data["limit"] == 50
        assert len(data["events"]) <= 50
        
    def test_timeline_search_by_provider(self):
        """GET /api/ops/timeline/search - Filter by provider"""
        response = requests.get(f"{BASE_URL}/ops/timeline/search", params={"provider": "hotelrunner", "limit": 10})
        assert response.status_code == 200
        
        data = response.json()
        for event in data["events"]:
            assert event["provider"] == "hotelrunner"
            
    def test_timeline_search_by_stage(self):
        """GET /api/ops/timeline/search - Filter by stage"""
        response = requests.get(f"{BASE_URL}/ops/timeline/search", params={"stage": "webhook_received", "limit": 10})
        assert response.status_code == 200
        
        data = response.json()
        for event in data["events"]:
            assert event["stage"] == "webhook_received"
            
    def test_timeline_gaps(self):
        """GET /api/ops/timeline/gaps - Stuck event detection"""
        response = requests.get(f"{BASE_URL}/ops/timeline/gaps", params={"max_age_minutes": 30, "limit": 50})
        assert response.status_code == 200
        
        data = response.json()
        assert "stuck_events" in data
        assert "total" in data
        assert "threshold_minutes" in data
        assert data["threshold_minutes"] == 30
        
    def test_timeline_correlation_lookup(self):
        """GET /api/ops/timeline/correlation/{correlation_id} - Full flow trace"""
        # First get a correlation_id from the test reservation
        timeline_response = requests.get(f"{BASE_URL}/ops/timeline/external/HR-VERIFY-1774179036")
        assert timeline_response.status_code == 200
        
        timeline_data = timeline_response.json()
        if timeline_data["total_events"] > 0:
            correlation_id = timeline_data["timeline"][0]["correlation_id"]
            
            response = requests.get(f"{BASE_URL}/ops/timeline/correlation/{correlation_id}")
            assert response.status_code == 200
            
            data = response.json()
            assert data["correlation_id"] == correlation_id
            assert "events" in data
            assert "total_events" in data
            assert data["total_events"] >= 1


class TestDashboardAPI:
    """Dashboard API tests for Health tab functionality"""
    
    def test_dashboard_full(self):
        """GET /api/ops/dashboard - Full system dashboard"""
        response = requests.get(f"{BASE_URL}/ops/dashboard")
        assert response.status_code == 200
        
        data = response.json()
        
        # Check health score and grade
        assert "health_score" in data
        assert "health_grade" in data
        assert data["health_grade"] in ["A", "B", "C", "D", "F"]
        assert 0 <= data["health_score"] <= 100
        
        # Check metrics
        assert "metrics" in data
        metrics = data["metrics"]
        assert "import_success_rate_24h" in metrics
        assert "sync_success_rate_24h" in metrics
        assert "outbox_pending" in metrics
        assert "failure_count_24h" in metrics
        
        # Check pipeline
        assert "pipeline" in data
        pipeline = data["pipeline"]
        assert "stages" in pipeline
        assert "total_in_flight" in pipeline
        
        # Check connector status
        assert "connector_status" in data
        
        # Check timestamp
        assert "timestamp" in data
        
    def test_dashboard_connectors(self):
        """GET /api/ops/dashboard/connectors - Connector health"""
        response = requests.get(f"{BASE_URL}/ops/dashboard/connectors")
        assert response.status_code == 200
        
        data = response.json()
        assert "connectors" in data
        
    def test_dashboard_pipeline(self):
        """GET /api/ops/dashboard/pipeline - Pipeline depth"""
        response = requests.get(f"{BASE_URL}/ops/dashboard/pipeline")
        assert response.status_code == 200
        
        data = response.json()
        assert "stages" in data
        assert "total_in_flight" in data
        
    def test_dashboard_trends(self):
        """GET /api/ops/dashboard/trends - Historical trends"""
        response = requests.get(f"{BASE_URL}/ops/dashboard/trends", params={"hours": 24})
        assert response.status_code == 200
        
        data = response.json()
        assert "hours" in data
        assert data["hours"] == 24
        assert "data_points" in data
        assert "timestamps" in data
        assert "health_scores" in data


class TestRawPayloadAPI:
    """Raw Payload API tests for webhook debugging"""
    
    def test_raw_payload_by_external_id(self):
        """GET /api/ops/timeline/raw-payloads/by-external/{external_id}"""
        response = requests.get(f"{BASE_URL}/ops/timeline/raw-payloads/by-external/HR-VERIFY-1774179036")
        assert response.status_code == 200
        
        data = response.json()
        assert "payloads" in data
        assert "count" in data
        assert "external_id" in data
        assert data["external_id"] == "HR-VERIFY-1774179036"
        
    def test_raw_payload_by_correlation_id(self):
        """GET /api/ops/timeline/raw-payload/{correlation_id}"""
        # First get a correlation_id from the test reservation
        timeline_response = requests.get(f"{BASE_URL}/ops/timeline/external/HR-VERIFY-1774179036")
        assert timeline_response.status_code == 200
        
        timeline_data = timeline_response.json()
        if timeline_data["total_events"] > 0:
            # Find webhook_received event which has raw_payload_id
            webhook_event = next((e for e in timeline_data["timeline"] if e["stage"] == "webhook_received"), None)
            if webhook_event:
                correlation_id = webhook_event["correlation_id"]
                
                response = requests.get(f"{BASE_URL}/ops/timeline/raw-payload/{correlation_id}")
                assert response.status_code == 200
                
                data = response.json()
                # Either we get the payload or an error message
                assert "raw_payload" in data or "error" in data


class TestLiveFeedAPI:
    """Live Feed API tests - uses search endpoint with default params"""
    
    def test_live_feed_default(self):
        """GET /api/ops/timeline/search - Default live feed (last 50 events)"""
        response = requests.get(f"{BASE_URL}/ops/timeline/search", params={"limit": 50})
        assert response.status_code == 200
        
        data = response.json()
        assert "events" in data
        assert "total" in data
        assert len(data["events"]) <= 50
        
        # Verify event structure for live feed display
        if data["events"]:
            event = data["events"][0]
            assert "timestamp" in event
            assert "stage" in event
            assert "external_id" in event or event.get("external_id") == ""
            assert "provider" in event
            assert "status" in event


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
