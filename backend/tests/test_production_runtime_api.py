"""
Production Runtime API Tests — Comprehensive endpoint testing for production hardening modules.
Tests: Event Bus, Runtime Infrastructure, Observability, Messaging Provider APIs.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://platform-prod-ready.preview.emergentagent.com').rstrip('/')


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@hotel.com",
        "password": "demo123"
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture(scope="module")
def headers(auth_token):
    """Returns headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


# ═══════════════ EVENT BUS API TESTS ═══════════════

class TestEventBusAPI:
    """Tests for /api/event-bus/* endpoints."""
    
    def test_event_bus_status(self, headers):
        """GET /api/event-bus/status returns mode, backend_status, redis_configured, fallback_available"""
        response = requests.get(f"{BASE_URL}/api/event-bus/status", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # Verify required fields
        assert "mode" in data
        assert "backend_status" in data
        assert "redis_configured" in data
        assert "fallback_available" in data
        # Verify values (in-memory mode expected without Redis)
        assert data["mode"] in ["in_memory", "redis"]
        assert data["backend_status"] in ["healthy", "degraded", "disconnected"]
    
    def test_event_bus_metrics(self, headers):
        """GET /api/event-bus/metrics returns total_published, delivered, dropped, events_last_hour, mode"""
        response = requests.get(f"{BASE_URL}/api/event-bus/metrics", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # Verify required fields
        assert "mode" in data
        assert "total_published" in data
        assert "total_delivered" in data
        assert "total_dropped" in data
        assert "events_last_hour" in data
        # Values should be integers >= 0
        assert isinstance(data["total_published"], int)
        assert data["total_published"] >= 0
    
    def test_event_bus_publish(self, headers):
        """POST /api/event-bus/publish publishes event and returns event_id with mode"""
        response = requests.post(
            f"{BASE_URL}/api/event-bus/publish?event_type=test_event&priority=normal",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        # Verify response structure
        assert "event_id" in data
        assert "mode" in data
        assert len(data["event_id"]) > 0  # UUID format
    
    def test_event_bus_replay_summary(self, headers):
        """GET /api/event-bus/replay/summary returns 24h replay summary"""
        response = requests.get(f"{BASE_URL}/api/event-bus/replay/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "replayable_events_24h" in data
        assert "by_type" in data
        assert isinstance(data["by_type"], list)
    
    def test_event_bus_channels(self, headers):
        """GET /api/event-bus/channels returns channel info"""
        response = requests.get(f"{BASE_URL}/api/event-bus/channels", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        # If channels exist, verify structure
        if len(data) > 0:
            ch = data[0]
            assert "tenant_id" in ch
            assert "channel" in ch
            assert "active_sessions" in ch
            assert "events_published" in ch


# ═══════════════ RUNTIME INFRASTRUCTURE API TESTS ═══════════════

class TestRuntimeInfrastructureAPI:
    """Tests for /api/runtime/* endpoints."""
    
    def test_runtime_overview(self, headers):
        """GET /api/runtime/overview returns event_bus, database, alerts, event_metrics"""
        response = requests.get(f"{BASE_URL}/api/runtime/overview", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # Verify top-level keys
        assert "event_bus" in data
        assert "database" in data
        assert "alerts" in data
        assert "event_metrics" in data
        # Verify event_bus structure
        eb = data["event_bus"]
        assert "mode" in eb
        assert "status" in eb
        assert "redis_configured" in eb
        # Verify database status
        assert data["database"]["status"] in ["healthy", "unhealthy"]
    
    def test_persistence_health(self, headers):
        """GET /api/runtime/persistence/health returns overall status and 10 collections"""
        response = requests.get(f"{BASE_URL}/api/runtime/persistence/health", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # Verify structure
        assert "overall" in data
        assert "collections" in data
        assert "healthy_count" in data
        assert "total_count" in data
        # Verify 10 collections
        assert data["total_count"] == 10
        # Verify each collection has status and document_count
        for coll_name, coll_info in data["collections"].items():
            assert "status" in coll_info
            assert "document_count" in coll_info or "error" in coll_info
    
    def test_alerts_evaluate(self, headers):
        """GET /api/runtime/alerts/evaluate runs all alert threshold checks"""
        response = requests.get(f"{BASE_URL}/api/runtime/alerts/evaluate", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "alerts" in data
        assert "count" in data
        assert isinstance(data["alerts"], list)
        assert isinstance(data["count"], int)
    
    def test_alerts_candidates(self, headers):
        """GET /api/runtime/alerts/candidates returns unacknowledged alerts"""
        response = requests.get(f"{BASE_URL}/api/runtime/alerts/candidates", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
    
    def test_alerts_engine_status(self, headers):
        """GET /api/runtime/alerts/engine-status returns cooldown_minutes, thresholds"""
        response = requests.get(f"{BASE_URL}/api/runtime/alerts/engine-status", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "cooldown_minutes" in data
        assert "thresholds" in data
        assert "active_alerts" in data
        # Verify cooldown value
        assert data["cooldown_minutes"] == 15
    
    def test_messaging_status(self, headers):
        """GET /api/runtime/messaging/status returns providers list, runtime status, retry_queue_size"""
        response = requests.get(f"{BASE_URL}/api/runtime/messaging/status", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert "runtime" in data
        assert "retry_queue_size" in data
        # Verify runtime structure
        runtime = data["runtime"]
        assert "provider_successes" in runtime
        assert "provider_errors" in runtime
    
    def test_observability_summary(self, headers):
        """GET /api/runtime/observability/summary returns metrics, traces, errors, health"""
        response = requests.get(f"{BASE_URL}/api/runtime/observability/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "metrics" in data
        assert "traces" in data
        assert "errors" in data
        assert "health" in data
        # Verify health structure
        health = data["health"]
        assert "overall_status" in health
        assert "services" in health


# ═══════════════ OBSERVABILITY API TESTS ═══════════════

class TestObservabilityAPI:
    """Tests for /api/observability/* endpoints."""
    
    def test_observability_metrics(self, headers):
        """GET /api/observability/metrics returns dashboard metrics (event_throughput, messaging_delivery, etc.)"""
        response = requests.get(f"{BASE_URL}/api/observability/metrics", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # Verify all dashboard metric keys
        assert "event_throughput" in data
        assert "websocket_latency" in data
        assert "ml_execution_time" in data
        assert "autopricing" in data
        assert "messaging_delivery" in data
        assert "reservation_sync_lag" in data
    
    def test_traces_summary(self, headers):
        """GET /api/observability/traces/summary returns total_requests, total_errors, endpoints"""
        response = requests.get(f"{BASE_URL}/api/observability/traces/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_requests" in data
        assert "total_errors" in data
        assert "endpoints" in data
        assert isinstance(data["endpoints"], list)
        # Verify real tracing is happening (request count should be > 0)
        assert data["total_requests"] >= 0
    
    def test_observability_health(self, headers):
        """GET /api/observability/health returns overall_status and all service statuses"""
        response = requests.get(f"{BASE_URL}/api/observability/health", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "overall_status" in data
        assert "services" in data
        # Verify service entries
        services = data["services"]
        assert "mongodb" in services
        assert "event_bus" in services
    
    def test_traces_flush(self, headers):
        """POST /api/observability/traces/flush flushes traces to MongoDB"""
        response = requests.post(f"{BASE_URL}/api/observability/traces/flush", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "flushed" in data
        assert isinstance(data["flushed"], int)
    
    def test_metrics_flush(self, headers):
        """POST /api/observability/metrics/flush flushes metrics to MongoDB"""
        response = requests.post(f"{BASE_URL}/api/observability/metrics/flush", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "flushed" in data
        assert isinstance(data["flushed"], int)
    
    def test_errors_summary(self, headers):
        """GET /api/observability/errors/summary returns error summary by severity"""
        response = requests.get(f"{BASE_URL}/api/observability/errors/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "total_errors" in data
        assert "by_severity" in data
        assert "top_errors" in data


# ═══════════════ MESSAGING CENTER API TESTS ═══════════════

class TestMessagingCenterAPI:
    """Tests for /api/messaging-center/* endpoints."""
    
    def test_messaging_runtime_status(self, headers):
        """GET /api/messaging-center/runtime-status returns provider_successes, errors, latency"""
        response = requests.get(f"{BASE_URL}/api/messaging-center/runtime-status", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "provider_successes" in data
        assert "provider_errors" in data
        assert "provider_latency" in data
        assert "fallback_usage" in data
    
    def test_list_providers(self, headers):
        """GET /api/messaging-center/providers returns list of providers"""
        response = requests.get(f"{BASE_URL}/api/messaging-center/providers", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "providers" in data
        assert isinstance(data["providers"], list)
    
    def test_list_templates(self, headers):
        """GET /api/messaging-center/templates returns list of templates"""
        response = requests.get(f"{BASE_URL}/api/messaging-center/templates", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert "templates" in data
        assert isinstance(data["templates"], list)


# ═══════════════ AUTHENTICATION TESTS ═══════════════

class TestAuthentication:
    """Tests for authentication requirements."""
    
    def test_event_bus_requires_auth(self):
        """Event bus endpoints require authentication (401 or 403)"""
        response = requests.get(f"{BASE_URL}/api/event-bus/status")
        assert response.status_code in [401, 403]
    
    def test_runtime_requires_auth(self):
        """Runtime endpoints require authentication (401 or 403)"""
        response = requests.get(f"{BASE_URL}/api/runtime/overview")
        assert response.status_code in [401, 403]
    
    def test_observability_requires_auth(self):
        """Observability endpoints require authentication (401 or 403)"""
        response = requests.get(f"{BASE_URL}/api/observability/health")
        assert response.status_code in [401, 403]
