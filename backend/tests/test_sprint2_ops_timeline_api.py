"""
Sprint 2 Ops Timeline & Auto-Remediation API Tests
===================================================

Tests for:
- GET /api/ops-events/timeline/{correlation_id} - Correlation timeline endpoint
- GET /api/ops-events/incident/{event_id}/summary - Incident summary endpoint
- GET /api/ops-events/incidents/prioritized - Prioritized incident feed
- GET /api/ops-events/connectors/health - Unified connector health contract
- GET /api/ops-events/impact-analysis - Impact analysis endpoint
- GET /api/ops-events/remediation/status - Auto-remediation engine status
- POST /api/ops-events/remediation/start - Start remediation engine
- POST /api/ops-events/remediation/stop - Stop remediation engine
- POST /api/ops-events/connectors/{id}/recover - Manual connector recover
- POST /api/ops-events/connectors/{id}/degrade - Manual connector degrade
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = os.environ.get("VITE_BACKEND_URL", "https://correlation-trace.preview.emergentagent.com").rstrip("/")

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for tests."""
    resp = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
    )
    if resp.status_code != 200:
        pytest.skip(f"Authentication failed: {resp.status_code} - {resp.text}")
    data = resp.json()
    # Token field is 'access_token' per test_credentials.md
    token = data.get("access_token") or data.get("token")
    if not token:
        pytest.skip("No token in auth response")
    return token


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get auth headers for API calls."""
    return {"Authorization": f"Bearer {auth_token}"}


class TestOpsEventsBasicEndpoints:
    """Test basic ops events endpoints that should work without data."""

    def test_list_ops_events(self, auth_headers):
        """Test GET /api/ops-events/list - should return events list."""
        resp = requests.get(
            f"{BASE_URL}/api/ops-events/list",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "events" in data
        assert "count" in data
        assert "severity_counts_24h" in data
        print(f"✓ list_ops_events: {data['count']} events, severity_counts: {data['severity_counts_24h']}")

    def test_webhook_deliveries(self, auth_headers):
        """Test GET /api/ops-events/webhook-deliveries - should return deliveries list."""
        resp = requests.get(
            f"{BASE_URL}/api/ops-events/webhook-deliveries",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "deliveries" in data
        assert "count" in data
        assert "summary" in data
        print(f"✓ webhook_deliveries: {data['count']} deliveries, summary: {data['summary']}")

    def test_webhook_dlq(self, auth_headers):
        """Test GET /api/ops-events/webhook-dlq - should return DLQ items."""
        resp = requests.get(
            f"{BASE_URL}/api/ops-events/webhook-dlq",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "items" in data
        assert "count" in data
        assert "pending_count" in data
        print(f"✓ webhook_dlq: {data['count']} items, pending: {data['pending_count']}")

    def test_rate_limit_status(self, auth_headers):
        """Test GET /api/ops-events/rate-limit-status - should return rate limit info."""
        resp = requests.get(
            f"{BASE_URL}/api/ops-events/rate-limit-status",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "provider" in data
        assert "is_throttled" in data
        print(f"✓ rate_limit_status: provider={data['provider']}, throttled={data['is_throttled']}")

    def test_channel_health(self, auth_headers):
        """Test GET /api/ops-events/channel-health - should return channel health."""
        resp = requests.get(
            f"{BASE_URL}/api/ops-events/channel-health",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "channels" in data
        assert "total_channels" in data
        print(f"✓ channel_health: {data['total_channels']} channels")

    def test_dashboard_summary(self, auth_headers):
        """Test GET /api/ops-events/dashboard-summary - should return full dashboard data."""
        resp = requests.get(
            f"{BASE_URL}/api/ops-events/dashboard-summary",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        # Verify all expected sections
        assert "webhook_delivery" in data
        assert "rate_limit" in data
        assert "channels" in data
        assert "recent_events" in data
        assert "generated_at" in data
        print(f"✓ dashboard_summary: webhook_delivery={data['webhook_delivery']}, rate_limit={data['rate_limit']}")


class TestSprint2PrioritizedIncidents:
    """Test Sprint 2 P1: Prioritized incident feed."""

    def test_prioritized_incidents_basic(self, auth_headers):
        """Test GET /api/ops-events/incidents/prioritized - basic call."""
        resp = requests.get(
            f"{BASE_URL}/api/ops-events/incidents/prioritized",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "incidents" in data
        assert "counts" in data
        # Verify counts structure
        counts = data["counts"]
        assert "dlq_pending" in counts
        assert "throttle_active" in counts
        assert "terminal_failures" in counts
        assert "warnings" in counts
        assert "total" in counts
        print(f"✓ prioritized_incidents: {data['counts']['total']} total, counts={counts}")

    def test_prioritized_incidents_with_resolved(self, auth_headers):
        """Test GET /api/ops-events/incidents/prioritized with include_resolved=true."""
        resp = requests.get(
            f"{BASE_URL}/api/ops-events/incidents/prioritized?include_resolved=true",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "incidents" in data
        assert "counts" in data
        assert "resolved" in data["counts"]
        print(f"✓ prioritized_incidents (with resolved): resolved={data['counts']['resolved']}")

    def test_prioritized_incidents_with_limit(self, auth_headers):
        """Test GET /api/ops-events/incidents/prioritized with custom limit."""
        resp = requests.get(
            f"{BASE_URL}/api/ops-events/incidents/prioritized?limit=10",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert len(data["incidents"]) <= 10
        print(f"✓ prioritized_incidents (limit=10): {len(data['incidents'])} incidents returned")


class TestSprint2ConnectorHealth:
    """Test Sprint 2 P1: Unified connector health contract."""

    def test_connectors_health_basic(self, auth_headers):
        """Test GET /api/ops-events/connectors/health - basic call."""
        resp = requests.get(
            f"{BASE_URL}/api/ops-events/connectors/health",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "connectors" in data
        assert "summary" in data
        assert "generated_at" in data
        
        # Verify summary structure
        summary = data["summary"]
        assert "total" in summary
        assert "healthy" in summary
        assert "degraded" in summary
        assert "critical" in summary
        assert "overall_health" in summary
        print(f"✓ connectors_health: {summary['total']} connectors, overall={summary['overall_health']}")

    def test_connectors_health_contract_fields(self, auth_headers):
        """Test that connector health follows unified contract schema."""
        resp = requests.get(
            f"{BASE_URL}/api/ops-events/connectors/health",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        
        # If there are connectors, verify the contract fields
        if data["connectors"]:
            conn = data["connectors"][0]
            # Required fields per unified contract
            required_fields = [
                "connector_id", "provider", "status", "health_score",
                "last_success_at", "last_failure_at", "failure_rate_1h",
                "retry_backlog", "dlq_count", "throttle_active", "metrics_1h"
            ]
            for field in required_fields:
                assert field in conn, f"Missing required field: {field}"
            
            # Verify health_score is 0-100
            assert 0 <= conn["health_score"] <= 100
            
            # Verify status is one of expected values
            assert conn["status"] in ["healthy", "degraded", "critical"]
            
            print(f"✓ connector health contract verified for {conn['provider']}: score={conn['health_score']}, status={conn['status']}")
        else:
            print("✓ connectors_health contract: no connectors to verify (empty list is valid)")


class TestSprint2ImpactAnalysis:
    """Test Sprint 2: Impact analysis endpoint."""

    def test_impact_analysis_basic(self, auth_headers):
        """Test GET /api/ops-events/impact-analysis - basic call."""
        resp = requests.get(
            f"{BASE_URL}/api/ops-events/impact-analysis",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "analysis_period_hours" in data
        assert "impacted_channels" in data
        assert "total_channels_impacted" in data
        assert "total_critical_events" in data
        assert "total_warning_events" in data
        print(f"✓ impact_analysis: {data['total_channels_impacted']} channels impacted, critical={data['total_critical_events']}, warning={data['total_warning_events']}")

    def test_impact_analysis_custom_period(self, auth_headers):
        """Test GET /api/ops-events/impact-analysis with custom since_hours."""
        resp = requests.get(
            f"{BASE_URL}/api/ops-events/impact-analysis?since_hours=48",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data["analysis_period_hours"] == 48
        print(f"✓ impact_analysis (48h): {data['total_channels_impacted']} channels impacted")


class TestSprint2AutoRemediation:
    """Test Sprint 2 P1.5: Auto-remediation engine endpoints."""

    def test_remediation_status(self, auth_headers):
        """Test GET /api/ops-events/remediation/status - should return engine status."""
        resp = requests.get(
            f"{BASE_URL}/api/ops-events/remediation/status",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert "engine_running" in data
        assert "rules" in data
        assert "cooldowns_active" in data
        
        # Verify rules structure
        rules = data["rules"]
        expected_rules = ["connector_degradation", "alert_escalation", "rate_limit_queueing", "recovery_drain", "dlq_auto_resolve"]
        for rule in expected_rules:
            assert rule in rules, f"Missing rule: {rule}"
        
        print(f"✓ remediation_status: running={data['engine_running']}, cooldowns={data['cooldowns_active']}")

    def test_remediation_start(self, auth_headers):
        """Test POST /api/ops-events/remediation/start - should start engine."""
        resp = requests.post(
            f"{BASE_URL}/api/ops-events/remediation/start",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") == True
        assert "message" in data
        print(f"✓ remediation_start: {data['message']}")

    def test_remediation_stop(self, auth_headers):
        """Test POST /api/ops-events/remediation/stop - should stop engine."""
        resp = requests.post(
            f"{BASE_URL}/api/ops-events/remediation/stop",
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        data = resp.json()
        assert data.get("ok") == True
        assert "message" in data
        print(f"✓ remediation_stop: {data['message']}")


class TestSprint2CorrelationTimeline:
    """Test Sprint 2 P0: Correlation timeline endpoint."""

    def test_timeline_not_found(self, auth_headers):
        """Test GET /api/ops-events/timeline/{correlation_id} with non-existent ID."""
        resp = requests.get(
            f"{BASE_URL}/api/ops-events/timeline/nonexistent-correlation-id-12345",
            headers=auth_headers,
        )
        # Should return 404 for non-existent correlation_id
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        print("✓ timeline (not found): correctly returns 404 for non-existent correlation_id")


class TestSprint2IncidentSummary:
    """Test Sprint 2 P0: Incident summary endpoint."""

    def test_incident_summary_not_found(self, auth_headers):
        """Test GET /api/ops-events/incident/{event_id}/summary with non-existent ID."""
        resp = requests.get(
            f"{BASE_URL}/api/ops-events/incident/nonexistent-event-id-12345/summary",
            headers=auth_headers,
        )
        # Should return 404 for non-existent event_id
        assert resp.status_code == 404, f"Expected 404, got {resp.status_code}: {resp.text}"
        print("✓ incident_summary (not found): correctly returns 404 for non-existent event_id")


class TestSprint2ManualConnectorActions:
    """Test Sprint 2: Manual connector recover/degrade endpoints."""

    def test_connector_recover_not_found(self, auth_headers):
        """Test POST /api/ops-events/connectors/{id}/recover with non-existent ID."""
        resp = requests.post(
            f"{BASE_URL}/api/ops-events/connectors/nonexistent-connector-id/recover",
            headers=auth_headers,
        )
        # Should return 400 for non-existent or already active connector
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        print("✓ connector_recover (not found): correctly returns 400 for non-existent connector")

    def test_connector_degrade_not_found(self, auth_headers):
        """Test POST /api/ops-events/connectors/{id}/degrade with non-existent ID."""
        resp = requests.post(
            f"{BASE_URL}/api/ops-events/connectors/nonexistent-connector-id/degrade?reason=test",
            headers=auth_headers,
        )
        # Should return 400 for non-existent or already degraded connector
        assert resp.status_code == 400, f"Expected 400, got {resp.status_code}: {resp.text}"
        print("✓ connector_degrade (not found): correctly returns 400 for non-existent connector")


class TestAuthenticationRequired:
    """Test that all endpoints require authentication."""

    def test_endpoints_require_auth(self):
        """Test that endpoints return 401/403 without auth."""
        endpoints = [
            ("GET", "/api/ops-events/list"),
            ("GET", "/api/ops-events/webhook-deliveries"),
            ("GET", "/api/ops-events/webhook-dlq"),
            ("GET", "/api/ops-events/rate-limit-status"),
            ("GET", "/api/ops-events/channel-health"),
            ("GET", "/api/ops-events/dashboard-summary"),
            ("GET", "/api/ops-events/incidents/prioritized"),
            ("GET", "/api/ops-events/connectors/health"),
            ("GET", "/api/ops-events/impact-analysis"),
            ("GET", "/api/ops-events/remediation/status"),
            ("POST", "/api/ops-events/remediation/start"),
            ("POST", "/api/ops-events/remediation/stop"),
            ("GET", "/api/ops-events/timeline/test-id"),
            ("GET", "/api/ops-events/incident/test-id/summary"),
        ]
        
        for method, endpoint in endpoints:
            if method == "GET":
                resp = requests.get(f"{BASE_URL}{endpoint}")
            else:
                resp = requests.post(f"{BASE_URL}{endpoint}")
            
            assert resp.status_code in [401, 403], f"{method} {endpoint} should require auth, got {resp.status_code}"
        
        print(f"✓ All {len(endpoints)} endpoints correctly require authentication")
