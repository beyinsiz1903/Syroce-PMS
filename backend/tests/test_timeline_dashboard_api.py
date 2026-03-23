"""
Test Suite: Event Timeline & Dashboard API
============================================
Tests for the new "minimum battle loop" features:
1. Event Timeline system - trace reservations from OTA webhook to PMS booking
2. Dashboard aggregator - health score, failure counts, pipeline depth, connector status
3. Trends API - historical health data

Primary goal: "1 rezervasyonu 5 saniyede debug edebilmek" (trace a reservation in 5 seconds)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")

# Test data from simulated timeline events
TEST_EXTERNAL_ID_SUCCESS = "EXELY-TEST-98765"  # Full pipeline: received -> confirmed
TEST_EXTERNAL_ID_STUCK = "EXELY-STUCK-54321"  # Stuck at import_decided with failure
TEST_CORRELATION_ID = "393fde19-3d64-469e-bdad-d2117f05ec49"
TEST_ENTITY_ID = "4b5e1809-609c-4be6-97ba-1a1510c25f7d"
TEST_TENANT_ID = "044f122b-87b5-480a-88b4-b9534b0c8c90"


@pytest.fixture(scope="module")
def api_client():
    """Shared requests session."""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


# ═══════════════════════════════════════════════════════════════════════════════
# DASHBOARD API TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestDashboardAPI:
    """Tests for /api/ops/dashboard/* endpoints."""

    def test_dashboard_main(self, api_client):
        """GET /api/ops/dashboard - Full system dashboard."""
        response = api_client.get(f"{BASE_URL}/api/ops/dashboard")
        assert response.status_code == 200
        
        data = response.json()
        # Verify required fields
        assert "health_score" in data
        assert "health_grade" in data
        assert "metrics" in data
        assert "connector_status" in data
        assert "pipeline" in data
        assert "recent_failures" in data
        assert "timestamp" in data
        
        # Verify health score is valid
        assert 0 <= data["health_score"] <= 100
        assert data["health_grade"] in ["A", "B", "C", "D", "F"]
        
        # Verify metrics structure
        metrics = data["metrics"]
        assert "open_failures" in metrics
        assert "outbox_pending" in metrics
        assert "import_pending" in metrics
        assert "sync_success_rate_24h" in metrics
        
        # Verify pipeline structure
        pipeline = data["pipeline"]
        assert "stages" in pipeline
        assert "total_in_flight" in pipeline
        assert isinstance(pipeline["stages"], list)
        
        print(f"Dashboard health: {data['health_score']} ({data['health_grade']})")

    def test_dashboard_tenant_scoped(self, api_client):
        """GET /api/ops/dashboard/tenant/{tenant_id} - Tenant-scoped dashboard."""
        response = api_client.get(f"{BASE_URL}/api/ops/dashboard/tenant/{TEST_TENANT_ID}")
        assert response.status_code == 200
        
        data = response.json()
        assert "health_score" in data
        assert "health_grade" in data
        assert "metrics" in data
        
        print(f"Tenant dashboard health: {data['health_score']} ({data['health_grade']})")

    def test_dashboard_trends(self, api_client):
        """GET /api/ops/dashboard/trends?hours=24 - Historical trends."""
        response = api_client.get(f"{BASE_URL}/api/ops/dashboard/trends?hours=24")
        assert response.status_code == 200
        
        data = response.json()
        assert "hours" in data
        assert data["hours"] == 24
        assert "data_points" in data
        assert "timestamps" in data
        assert "health_scores" in data
        assert "failure_counts" in data
        assert "outbox_depths" in data
        
        # Verify arrays have same length
        assert len(data["timestamps"]) == len(data["health_scores"])
        assert len(data["timestamps"]) == len(data["failure_counts"])
        
        print(f"Trends: {data['data_points']} data points over {data['hours']} hours")

    def test_dashboard_connectors(self, api_client):
        """GET /api/ops/dashboard/connectors - Connector health."""
        response = api_client.get(f"{BASE_URL}/api/ops/dashboard/connectors")
        assert response.status_code == 200
        
        data = response.json()
        assert "connectors" in data
        assert isinstance(data["connectors"], list)
        
        # Verify connector structure if any exist
        if data["connectors"]:
            conn = data["connectors"][0]
            assert "provider" in conn
            assert "status" in conn
            print(f"Found {len(data['connectors'])} connectors")
        else:
            print("No connectors found")

    def test_dashboard_pipeline(self, api_client):
        """GET /api/ops/dashboard/pipeline - Pipeline depth."""
        response = api_client.get(f"{BASE_URL}/api/ops/dashboard/pipeline")
        assert response.status_code == 200
        
        data = response.json()
        assert "stages" in data
        assert "total_in_flight" in data
        
        # Verify stages structure
        for stage in data["stages"]:
            assert "name" in stage
            assert "count" in stage
        
        print(f"Pipeline: {data['total_in_flight']} total in flight")


# ═══════════════════════════════════════════════════════════════════════════════
# TIMELINE API TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestTimelineAPI:
    """Tests for /api/ops/timeline/* endpoints - the core debug feature."""

    def test_timeline_external_id_success(self, api_client):
        """GET /api/ops/timeline/external/{external_id} - Primary debug entry point.
        
        This is THE key feature: trace any OTA reservation in seconds.
        """
        response = api_client.get(f"{BASE_URL}/api/ops/timeline/external/{TEST_EXTERNAL_ID_SUCCESS}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["external_id"] == TEST_EXTERNAL_ID_SUCCESS
        assert "timeline" in data
        assert "total_events" in data
        assert "total_duration_ms" in data
        assert "current_stage" in data
        assert "gap_warnings" in data
        
        # Verify we have the full pipeline (9 events)
        assert data["total_events"] == 9
        assert data["current_stage"] == "confirmed"
        assert len(data["gap_warnings"]) == 0  # No gaps in successful flow
        
        # Verify timeline events are in order
        timeline = data["timeline"]
        stages = [e["stage"] for e in timeline]
        expected_stages = ["received", "validated", "normalized", "deduped", 
                         "import_decided", "stored", "queued", "dispatched", "confirmed"]
        assert stages == expected_stages
        
        print(f"Traced {TEST_EXTERNAL_ID_SUCCESS}: {data['total_events']} events, "
              f"{data['total_duration_ms']}ms total, stage={data['current_stage']}")

    def test_timeline_external_id_stuck(self, api_client):
        """GET /api/ops/timeline/external/{external_id} - Stuck reservation detection."""
        response = api_client.get(f"{BASE_URL}/api/ops/timeline/external/{TEST_EXTERNAL_ID_STUCK}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["external_id"] == TEST_EXTERNAL_ID_STUCK
        assert data["total_events"] == 4
        assert data["current_stage"] == "import_decided"
        
        # Should have gap warnings for missing stages
        assert len(data["gap_warnings"]) > 0
        
        # Verify the last event shows failure
        timeline = data["timeline"]
        last_event = timeline[-1]
        assert last_event["status"] == "failure"
        
        print(f"Stuck reservation {TEST_EXTERNAL_ID_STUCK}: stage={data['current_stage']}, "
              f"gaps={len(data['gap_warnings'])}")

    def test_timeline_external_id_not_found(self, api_client):
        """GET /api/ops/timeline/external/{external_id} - Non-existent ID."""
        response = api_client.get(f"{BASE_URL}/api/ops/timeline/external/NONEXISTENT-12345")
        assert response.status_code == 200
        
        data = response.json()
        assert data["total_events"] == 0
        assert "message" in data
        print("Non-existent external_id handled correctly")

    def test_timeline_correlation(self, api_client):
        """GET /api/ops/timeline/correlation/{correlation_id} - Full flow trace."""
        response = api_client.get(f"{BASE_URL}/api/ops/timeline/correlation/{TEST_CORRELATION_ID}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["correlation_id"] == TEST_CORRELATION_ID
        assert "events" in data
        assert "total_events" in data
        assert "entity_map" in data
        assert "total_duration_ms" in data
        
        # Verify entity map contains external_id
        assert "external_id" in data["entity_map"]
        assert data["entity_map"]["external_id"] == TEST_EXTERNAL_ID_SUCCESS
        
        print(f"Correlation trace: {data['total_events']} events, "
              f"entities={list(data['entity_map'].keys())}")

    def test_timeline_search(self, api_client):
        """GET /api/ops/timeline/search - Search with filters."""
        response = api_client.get(f"{BASE_URL}/api/ops/timeline/search?limit=5")
        assert response.status_code == 200
        
        data = response.json()
        assert "events" in data
        assert "total" in data
        assert "limit" in data
        assert "skip" in data
        
        assert data["limit"] == 5
        assert len(data["events"]) <= 5
        
        # Verify event structure
        if data["events"]:
            event = data["events"][0]
            assert "id" in event
            assert "stage" in event
            assert "status" in event
            assert "timestamp" in event
        
        print(f"Search: {len(data['events'])} events returned, {data['total']} total")

    def test_timeline_search_with_filters(self, api_client):
        """GET /api/ops/timeline/search - Search with provider filter."""
        response = api_client.get(f"{BASE_URL}/api/ops/timeline/search?provider=exely&limit=10")
        assert response.status_code == 200
        
        data = response.json()
        # All returned events should be from exely
        for event in data["events"]:
            assert event["provider"] == "exely"
        
        print(f"Filtered search (provider=exely): {len(data['events'])} events")

    def test_timeline_gaps(self, api_client):
        """GET /api/ops/timeline/gaps - Stuck event detection."""
        response = api_client.get(f"{BASE_URL}/api/ops/timeline/gaps")
        assert response.status_code == 200
        
        data = response.json()
        assert "stuck_events" in data
        assert "total" in data
        assert "threshold_minutes" in data
        
        print(f"Gap detection: {data['total']} stuck events (threshold={data['threshold_minutes']}min)")

    def test_timeline_entity(self, api_client):
        """GET /api/ops/timeline/{entity_type}/{entity_id} - Entity timeline."""
        response = api_client.get(f"{BASE_URL}/api/ops/timeline/reservation/{TEST_ENTITY_ID}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["entity_type"] == "reservation"
        assert data["entity_id"] == TEST_ENTITY_ID
        assert "timeline" in data
        assert "total_events" in data
        
        print(f"Entity timeline: {data['total_events']} events for {data['entity_type']}/{data['entity_id'][:8]}...")


# ═══════════════════════════════════════════════════════════════════════════════
# EXISTING OPS API TESTS (Regression)
# ═══════════════════════════════════════════════════════════════════════════════

class TestExistingOpsAPI:
    """Regression tests for existing /api/ops/* endpoints."""

    def test_ops_overview(self, api_client):
        """GET /api/ops/overview - System health overview."""
        response = api_client.get(f"{BASE_URL}/api/ops/overview")
        assert response.status_code == 200
        
        data = response.json()
        assert "open_failures" in data
        assert "stuck_outbox_count" in data
        assert "sync_success_rate" in data
        assert "timestamp" in data
        
        print(f"Overview: {data['open_failures']} open failures, "
              f"{data['stuck_outbox_count']} stuck outbox")

    def test_ops_failures(self, api_client):
        """GET /api/ops/failures - List failures."""
        response = api_client.get(f"{BASE_URL}/api/ops/failures")
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
        assert "total" in data
        
        print(f"Failures: {data['total']} total")

    def test_ops_outbox(self, api_client):
        """GET /api/ops/outbox - Outbox monitor."""
        response = api_client.get(f"{BASE_URL}/api/ops/outbox")
        assert response.status_code == 200
        
        data = response.json()
        assert "pending" in data
        assert "stuck" in data
        assert "failed" in data
        
        print(f"Outbox: {data['pending']} pending, {data['stuck']} stuck, {data['failed']} failed")

    def test_ops_imports(self, api_client):
        """GET /api/ops/imports - Import pipeline monitor."""
        response = api_client.get(f"{BASE_URL}/api/ops/imports")
        assert response.status_code == 200
        
        data = response.json()
        assert "pending" in data
        assert "failed" in data
        assert "imported_24h" in data
        
        print(f"Imports: {data['pending']} pending, {data['imported_24h']} imported (24h)")

    def test_ops_sync(self, api_client):
        """GET /api/ops/sync - Sync jobs monitor."""
        response = api_client.get(f"{BASE_URL}/api/ops/sync")
        assert response.status_code == 200
        
        data = response.json()
        assert "total_24h" in data
        assert "success_rate" in data
        
        print(f"Sync: {data['total_24h']} jobs (24h), {data['success_rate']}% success")


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION TESTS
# ═══════════════════════════════════════════════════════════════════════════════

class TestIntegration:
    """Integration tests verifying end-to-end flows."""

    def test_trace_reservation_under_5_seconds(self, api_client):
        """Verify the primary goal: trace a reservation in under 5 seconds.
        
        This test measures the actual response time for the debug workflow.
        """
        import time
        
        start = time.time()
        
        # Step 1: Lookup by external ID
        response = api_client.get(f"{BASE_URL}/api/ops/timeline/external/{TEST_EXTERNAL_ID_SUCCESS}")
        assert response.status_code == 200
        
        elapsed = time.time() - start
        
        # Verify we got the full trace
        data = response.json()
        assert data["total_events"] == 9
        assert data["current_stage"] == "confirmed"
        
        # The goal is < 5 seconds
        assert elapsed < 5.0, f"Trace took {elapsed:.2f}s, should be < 5s"
        
        print(f"✓ Traced reservation in {elapsed:.3f}s (goal: <5s)")

    def test_dashboard_and_timeline_consistency(self, api_client):
        """Verify dashboard metrics are consistent with timeline data."""
        # Get dashboard
        dash_response = api_client.get(f"{BASE_URL}/api/ops/dashboard")
        assert dash_response.status_code == 200
        dashboard = dash_response.json()
        
        # Get pipeline from dashboard
        pipeline_response = api_client.get(f"{BASE_URL}/api/ops/dashboard/pipeline")
        assert pipeline_response.status_code == 200
        pipeline = pipeline_response.json()
        
        # Verify pipeline data matches
        assert dashboard["pipeline"]["total_in_flight"] == pipeline["total_in_flight"]
        
        print("✓ Dashboard and pipeline data consistent")

    def test_tenant_isolation(self, api_client):
        """Verify tenant-scoped queries return filtered data."""
        # Get system-wide dashboard
        system_response = api_client.get(f"{BASE_URL}/api/ops/dashboard")
        assert system_response.status_code == 200
        system_data = system_response.json()
        
        # Get tenant-scoped dashboard
        tenant_response = api_client.get(f"{BASE_URL}/api/ops/dashboard/tenant/{TEST_TENANT_ID}")
        assert tenant_response.status_code == 200
        tenant_data = tenant_response.json()
        
        # Tenant data should be subset of system data
        assert tenant_data["pipeline"]["total_in_flight"] <= system_data["pipeline"]["total_in_flight"]
        
        print("✓ Tenant isolation working correctly")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
