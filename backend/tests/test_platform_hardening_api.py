"""
Platform Hardening API Tests - Tests for all 4 new modules via HTTP endpoints:
- Data Pipeline: ML data pipeline, feature store, model registry, prediction service
- Event Bus: Redis pub/sub with in-memory fallback, event replay, routing
- Observability: Metrics collector, distributed tracing, error tracker, service health
- Security Hardening: Tenant scoped queries, property permissions, credential vault, data masking, audit completeness
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL not set")

class TestAuth:
    """Test authentication to get token for authenticated endpoints"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get auth token for the test session"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        # Token might be 'token' or 'access_token'
        token = data.get("access_token") or data.get("token")
        assert token, f"No token in response: {data}"
        return token
    
    @pytest.fixture(scope="class") 
    def headers(self, auth_token):
        """Headers with Bearer token"""
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


# ---- DATA PIPELINE API TESTS ----

class TestDataPipelineAPI(TestAuth):
    """Data Pipeline Module - ML data pipeline management API tests"""
    
    def test_health_endpoint(self, headers):
        """GET /api/data-pipeline/health - Pipeline health status"""
        response = requests.get(f"{BASE_URL}/api/data-pipeline/health", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # Verify response structure
        assert "feature_store" in data or "model_registry" in data or "stale_models" in data
        print(f"Pipeline health: {data.get('overall_status', 'retrieved')}")
    
    def test_feature_store_summary(self, headers):
        """GET /api/data-pipeline/feature-store/summary - Feature store summary"""
        response = requests.get(f"{BASE_URL}/api/data-pipeline/feature-store/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # Should return feature store info
        assert isinstance(data, dict)
        print("Feature store summary retrieved")
    
    def test_list_models(self, headers):
        """GET /api/data-pipeline/models - List registered models"""
        response = requests.get(f"{BASE_URL}/api/data-pipeline/models", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Models retrieved: {len(data)} models")
    
    def test_stale_models(self, headers):
        """GET /api/data-pipeline/models/stale - Get stale models"""
        response = requests.get(f"{BASE_URL}/api/data-pipeline/models/stale?stale_hours=24", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Stale models check: {len(data)} stale")
    
    def test_list_pipeline_runs(self, headers):
        """GET /api/data-pipeline/runs - List pipeline runs"""
        response = requests.get(f"{BASE_URL}/api/data-pipeline/runs?limit=10", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Pipeline runs: {len(data)} runs")
    
    def test_execute_pipeline_revenue_ml(self, headers):
        """POST /api/data-pipeline/runs/execute - Execute pipeline for revenue_ml"""
        response = requests.post(
            f"{BASE_URL}/api/data-pipeline/runs/execute?model_type=revenue_ml", 
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "run_id" in data or "status" in data or "model_type" in data
        print(f"Pipeline execution triggered: {data.get('run_id', data.get('status', 'ok'))}")
    
    def test_predictions_confidence(self, headers):
        """GET /api/data-pipeline/predictions/confidence - Confidence summary"""
        response = requests.get(f"{BASE_URL}/api/data-pipeline/predictions/confidence", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        print("Predictions confidence retrieved")
    
    def test_make_prediction_revenue_ml(self, headers):
        """POST /api/data-pipeline/predict - Make prediction"""
        response = requests.post(
            f"{BASE_URL}/api/data-pipeline/predict?model_type=revenue_ml",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        # Should have prediction result with confidence
        assert "confidence" in data or "prediction" in data or "recommended_rate" in data
        print(f"Prediction made: confidence={data.get('confidence', 'N/A')}")


# ---- EVENT BUS API TESTS ----

class TestEventBusAPI(TestAuth):
    """Event Bus Module - Redis Pub/Sub with in-memory fallback API tests"""
    
    def test_status_endpoint(self, headers):
        """GET /api/event-bus/status - Bus status"""
        response = requests.get(f"{BASE_URL}/api/event-bus/status", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # Should have mode and backend_details
        assert "mode" in data or "backend" in data or "status" in data
        print(f"Event bus mode: {data.get('mode', data.get('backend', 'ok'))}")
    
    def test_metrics_endpoint(self, headers):
        """GET /api/event-bus/metrics - Bus metrics"""
        response = requests.get(f"{BASE_URL}/api/event-bus/metrics", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        print(f"Event bus metrics: published={data.get('total_published', 0)}")
    
    def test_channels_endpoint(self, headers):
        """GET /api/event-bus/channels - List tenant channels"""
        response = requests.get(f"{BASE_URL}/api/event-bus/channels", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        print(f"Tenant channels: {len(data)}")
    
    def test_publish_event(self, headers):
        """POST /api/event-bus/publish - Publish test event"""
        response = requests.post(
            f"{BASE_URL}/api/event-bus/publish?event_type=test_event&priority=normal",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        assert "event_id" in data or "published" in data or "status" in data
        print(f"Event published: {data.get('event_id', 'ok')}")
    
    def test_replay_summary(self, headers):
        """GET /api/event-bus/replay/summary - Replay summary"""
        response = requests.get(f"{BASE_URL}/api/event-bus/replay/summary", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        print(f"Replay summary: {data.get('replayable_events_24h', 0)} events")


# ---- OBSERVABILITY API TESTS ----

class TestObservabilityAPI(TestAuth):
    """Observability Module - Metrics, tracing, errors, service health API tests"""
    
    def test_health_endpoint(self, headers):
        """GET /api/observability/health - Service health check"""
        response = requests.get(f"{BASE_URL}/api/observability/health", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # Should have overall_status and services
        assert "overall_status" in data or "services" in data or "healthy_count" in data
        print(f"Observability health: {data.get('overall_status', 'retrieved')}")
    
    def test_metrics_endpoint(self, headers):
        """GET /api/observability/metrics - Dashboard metrics"""
        response = requests.get(f"{BASE_URL}/api/observability/metrics", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        print("Dashboard metrics retrieved")
    
    def test_errors_summary(self, headers):
        """GET /api/observability/errors/summary - Error summary for 24 hours"""
        response = requests.get(f"{BASE_URL}/api/observability/errors/summary?hours=24", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # Should have error counts
        assert "total_errors" in data or "by_severity" in data
        print(f"Errors summary: {data.get('total_errors', 0)} total")
    
    def test_traces_summary(self, headers):
        """GET /api/observability/traces/summary - Trace summary for 1 hour"""
        response = requests.get(f"{BASE_URL}/api/observability/traces/summary?hours=1", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # Should have trace stats
        assert "total_requests" in data or "error_rate" in data
        print(f"Traces: {data.get('total_requests', 0)} requests")


# ---- SECURITY HARDENING API TESTS ----

class TestSecurityHardeningAPI(TestAuth):
    """Security Hardening Module - Multi-tenant security API tests"""
    
    def test_tenant_scope_check(self, headers):
        """GET /api/security-hardening/tenant-scope/check - Tenant isolation check"""
        response = requests.get(f"{BASE_URL}/api/security-hardening/tenant-scope/check", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # Should have isolation_score
        assert "isolation_score" in data or "collections_checked" in data
        print(f"Tenant isolation score: {data.get('isolation_score', 'N/A')}")
    
    def test_property_permissions(self, headers):
        """GET /api/security-hardening/property-permissions - Property permissions"""
        response = requests.get(f"{BASE_URL}/api/security-hardening/property-permissions", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, dict)
        print("Property permissions retrieved")
    
    def test_property_permissions_roles(self, headers):
        """GET /api/security-hardening/property-permissions/roles - Role permissions"""
        response = requests.get(f"{BASE_URL}/api/security-hardening/property-permissions/roles", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # Should have role definitions
        assert isinstance(data, dict)
        assert "admin" in data or "super_admin" in data or "front_desk" in data
        print(f"Role permissions: {len(data)} roles defined")
    
    def test_vault_status(self, headers):
        """GET /api/security-hardening/vault/status - Credential vault status"""
        response = requests.get(f"{BASE_URL}/api/security-hardening/vault/status", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # Should have vault health
        assert "vault_health" in data or "total_credentials" in data
        print(f"Vault status: {data.get('vault_health', 'retrieved')}")
    
    def test_audit_completeness(self, headers):
        """GET /api/security-hardening/audit-completeness - Audit completeness"""
        response = requests.get(f"{BASE_URL}/api/security-hardening/audit-completeness?hours=24", headers=headers)
        assert response.status_code == 200
        data = response.json()
        # Should have completeness_score
        assert "completeness_score" in data or "categories" in data
        print(f"Audit completeness: {data.get('completeness_score', 'N/A')}")
    
    def test_masking_preview(self, headers):
        """POST /api/security-hardening/masking-preview - Data masking preview"""
        test_data = {
            "password": "secret",
            "email": "test@test.com",
            "name": "John"
        }
        response = requests.post(
            f"{BASE_URL}/api/security-hardening/masking-preview",
            json=test_data,
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        # Response has masked_output field with masked data
        assert "masked_output" in data, f"Expected masked_output in response: {data}"
        masked = data["masked_output"]
        assert masked["password"] != "secret", "Password should be masked"
        assert masked["password"] == "****", f"Password should be fully masked, got: {masked['password']}"
        assert masked["name"] == "John", "Name should not be masked"
        print(f"Data masking: password='{masked['password']}', email='{masked['email']}', name='{masked['name']}'")


# ---- CROSS-TENANT SECURITY TESTS ----

class TestSecurityIsolation(TestAuth):
    """Cross-tenant security tests"""
    
    def test_rbac_role_check(self, headers):
        """Verify RBAC role permission definitions exist"""
        response = requests.get(f"{BASE_URL}/api/security-hardening/property-permissions/roles", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        # Verify expected roles exist
        expected_roles = ["super_admin", "admin", "front_desk"]
        for role in expected_roles:
            assert role in data, f"Missing role: {role}"
        
        # Verify super_admin has wildcard permission
        assert data.get("super_admin") == ["*"], "Super admin should have wildcard permissions"
        print(f"RBAC check passed: {len(data)} roles with proper permissions")
    
    def test_tenant_isolation_score(self, headers):
        """Verify tenant isolation is properly enforced"""
        response = requests.get(f"{BASE_URL}/api/security-hardening/tenant-scope/check", headers=headers)
        assert response.status_code == 200
        data = response.json()
        
        # Isolation score should be reasonably high (>0.5)
        score = data.get("isolation_score", 0)
        assert score >= 0.5, f"Isolation score too low: {score}"
        print(f"Tenant isolation score: {score * 100:.0f}%")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
