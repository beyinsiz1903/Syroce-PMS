"""
Production Go-Live Module API Tests
Tests all 27 endpoints in the production-golive router for the enterprise hotel PMS.
Includes: readiness validation, config inspection, Redis validation, MongoDB health,
worker validation, provider activation, observability, backup DR, and security checklist.
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

pytestmark = pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL not set")

# Test user credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


class TestAuthSetup:
    """Verify authentication works for all tests."""
    
    @pytest.fixture(scope="class")
    def token(self):
        """Get authentication token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, f"No access_token in response: {data}"
        return data["access_token"]
    
    @pytest.fixture(scope="class")
    def auth_headers(self, token):
        """Get headers with auth token."""
        return {"Authorization": f"Bearer {token}"}


class TestReadinessEndpoints(TestAuthSetup):
    """Tests for top-level production readiness endpoints."""
    
    def test_readiness_returns_status_and_score(self, auth_headers):
        """GET /api/production-golive/readiness - returns READY/DEGRADED/NOT_READY"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/readiness",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate readiness structure
        assert "readiness" in data, "Missing 'readiness' field"
        assert data["readiness"] in ["READY", "DEGRADED", "NOT_READY"], f"Invalid readiness: {data['readiness']}"
        assert "readiness_score" in data, "Missing 'readiness_score' field"
        assert isinstance(data["readiness_score"], int), "readiness_score should be int"
        assert 0 <= data["readiness_score"] <= 100, "readiness_score should be 0-100"
        assert "checks" in data, "Missing 'checks' field"
        assert "validated_at" in data, "Missing 'validated_at' field"
        print(f"Readiness: {data['readiness']} ({data['readiness_score']}%)")
    
    def test_summary_returns_all_subsystems(self, auth_headers):
        """GET /api/production-golive/summary - comprehensive dashboard data"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/summary",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Validate all subsystem sections present
        required_keys = ["readiness", "configuration", "redis", "mongodb", "workers", 
                        "providers", "backup", "observability", "security"]
        for key in required_keys:
            assert key in data, f"Missing subsystem: {key}"
        print(f"Summary contains {len(data)} subsystems")


class TestConfigEndpoints(TestAuthSetup):
    """Tests for environment configuration validation endpoints."""
    
    def test_config_validate_returns_all_categories(self, auth_headers):
        """GET /api/production-golive/config/validate - full env validation"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/config/validate",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "categories" in data, "Missing 'categories'"
        assert "overall_status" in data, "Missing 'overall_status'"
        assert "total_configured" in data, "Missing 'total_configured'"
        assert "total_required" in data, "Missing 'total_required'"
        assert data["overall_status"] in ["READY", "DEGRADED", "NOT_READY"]
        print(f"Config: {data['total_configured']}/{data['total_required']} configured")
    
    def test_config_inspect_returns_masked_values(self, auth_headers):
        """GET /api/production-golive/config/inspect - masked config inspection"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/config/inspect",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "config" in data, "Missing 'config'"
        assert "inspected_at" in data, "Missing 'inspected_at'"
        # Verify config entries have expected structure
        for var_name, var_data in data["config"].items():
            assert "configured" in var_data, f"Missing 'configured' for {var_name}"
            assert "category" in var_data, f"Missing 'category' for {var_name}"
        print(f"Inspected {len(data['config'])} configuration variables")
    
    def test_startup_check_returns_critical_vars(self, auth_headers):
        """GET /api/production-golive/config/startup-check - startup critical vars"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/config/startup-check",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "status" in data, "Missing 'status'"
        assert data["status"] in ["pass", "fail"], f"Invalid status: {data['status']}"
        assert "missing_critical" in data, "Missing 'missing_critical'"
        assert "checked_at" in data, "Missing 'checked_at'"
        print(f"Startup check: {data['status']}")
    
    def test_leak_scan_returns_suspicious_count(self, auth_headers):
        """GET /api/production-golive/config/leak-scan - secret leakage scan"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/config/leak-scan",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "status" in data, "Missing 'status'"
        assert data["status"] in ["clean", "review_needed"], f"Invalid status: {data['status']}"
        assert "suspicious_count" in data, "Missing 'suspicious_count'"
        assert "scanned_at" in data, "Missing 'scanned_at'"
        print(f"Leak scan: {data['status']} ({data['suspicious_count']} suspicious)")


class TestRedisEndpoints(TestAuthSetup):
    """Tests for Redis production validation endpoints."""
    
    def test_redis_cluster_validation(self, auth_headers):
        """GET /api/production-golive/redis/cluster-validation - cluster details"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/redis/cluster-validation",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "mode" in data, "Missing 'mode'"
        assert "connected" in data, "Missing 'connected'"
        assert "health" in data, "Missing 'health'"
        assert "metrics" in data, "Missing 'metrics'"
        assert "lock_metrics" in data, "Missing 'lock_metrics'"
        print(f"Redis: mode={data['mode']}, connected={data['connected']}")
    
    def test_redis_pubsub_health(self, auth_headers):
        """GET /api/production-golive/redis/pubsub-health - pub/sub health"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/redis/pubsub-health",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "connected" in data, "Missing 'connected'"
        assert "mode" in data, "Missing 'mode'"
        assert "status" in data, "Missing 'status'"
        print(f"PubSub: status={data['status']}")
    
    def test_redis_lock_safety(self, auth_headers):
        """GET /api/production-golive/redis/lock-safety - distributed lock check"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/redis/lock-safety",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "metrics" in data, "Missing 'metrics'"
        assert "active_locks" in data, "Missing 'active_locks'"
        assert "safety_status" in data, "Missing 'safety_status'"
        print(f"Lock safety: {data['safety_status']}")


class TestMongoEndpoints(TestAuthSetup):
    """Tests for MongoDB production validation endpoints."""
    
    def test_mongo_health(self, auth_headers):
        """GET /api/production-golive/mongo/health - full health report"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/mongo/health",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "overall_status" in data, "Missing 'overall_status'"
        assert "connection_pool" in data, "Missing 'connection_pool'"
        assert "replica_set" in data, "Missing 'replica_set'"
        assert "index_validation" in data, "Missing 'index_validation'"
        print(f"MongoDB health: {data['overall_status']}")
    
    def test_mongo_pool(self, auth_headers):
        """GET /api/production-golive/mongo/pool - connection pool info"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/mongo/pool",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "status" in data, "Missing 'status'"
        print(f"Mongo pool: status={data['status']}")
    
    def test_mongo_indexes(self, auth_headers):
        """GET /api/production-golive/mongo/indexes - index validation"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/mongo/indexes",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "status" in data, "Missing 'status'"
        assert "validated_at" in data, "Missing 'validated_at'"
        print(f"Index validation: status={data['status']}")
    
    def test_mongo_collections(self, auth_headers):
        """GET /api/production-golive/mongo/collections - collection health"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/mongo/collections",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "health" in data, "Missing 'health'"
        assert "total_documents" in data, "Missing 'total_documents'"
        print(f"Collections: {data['total_documents']} total documents")
    
    def test_mongo_schema_drift(self, auth_headers):
        """GET /api/production-golive/mongo/schema-drift - schema drift detection"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/mongo/schema-drift",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "scanned_at" in data, "Missing 'scanned_at'"
        assert "collections_scanned" in data, "Missing 'collections_scanned'"
        print(f"Schema drift: scanned {data['collections_scanned']} collections")
    
    def test_mongo_slow_queries(self, auth_headers):
        """GET /api/production-golive/mongo/slow-queries - slow query metrics"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/mongo/slow-queries",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "status" in data, "Missing 'status'"
        print(f"Slow queries: status={data['status']}")
    
    def test_mongo_replica_set(self, auth_headers):
        """GET /api/production-golive/mongo/replica-set - replica set detection"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/mongo/replica-set",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "is_replica_set" in data or "status" in data, "Missing expected fields"
        print(f"Replica set: {data.get('is_replica_set', data.get('status'))}")


class TestWorkerEndpoints(TestAuthSetup):
    """Tests for worker runtime validation endpoints."""
    
    def test_workers_validation(self, auth_headers):
        """GET /api/production-golive/workers/validation - worker runtime"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/workers/validation",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "summary" in data, "Missing 'summary'"
        assert "queues" in data, "Missing 'queues'"
        assert "status" in data, "Missing 'status'"
        print(f"Workers: status={data['status']}")
    
    def test_workers_scaling_readiness(self, auth_headers):
        """GET /api/production-golive/workers/scaling-readiness - scaling readiness"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/workers/scaling-readiness",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "total_queues" in data, "Missing 'total_queues'"
        assert "scaling_ready" in data, "Missing 'scaling_ready'"
        print(f"Scaling: {data['total_queues']} queues, ready={data['scaling_ready']}")


class TestProviderEndpoints(TestAuthSetup):
    """Tests for provider integration activation endpoints."""
    
    def test_providers_status(self, auth_headers):
        """GET /api/production-golive/providers/status - messaging provider status"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/providers/status",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "providers" in data, "Missing 'providers'"
        assert "active_providers" in data, "Missing 'active_providers'"
        assert "total_providers" in data, "Missing 'total_providers'"
        assert "fallback_chain" in data, "Missing 'fallback_chain'"
        print(f"Providers: {data['active_providers']}/{data['total_providers']} active")
    
    def test_providers_validate(self, auth_headers):
        """GET /api/production-golive/providers/validate - credential validation"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/providers/validate",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "providers" in data, "Missing 'providers'"
        assert "validated_at" in data, "Missing 'validated_at'"
        print(f"Provider validation: {data.get('production_ready_count', 0)} ready")
    
    def test_providers_delivery_metrics(self, auth_headers):
        """GET /api/production-golive/providers/delivery-metrics - delivery metrics"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/providers/delivery-metrics",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        # Delivery metrics may be empty if no deliveries made
        assert isinstance(data, dict), "Expected dict response"
        print(f"Delivery metrics: {len(data)} providers tracked")


class TestObservabilityEndpoints(TestAuthSetup):
    """Tests for observability go-live endpoints."""
    
    def test_observability_validation(self, auth_headers):
        """GET /api/production-golive/observability/validation - stack validation"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/observability/validation",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "otel" in data, "Missing 'otel'"
        assert "sentry" in data, "Missing 'sentry'"
        assert "overall_status" in data, "Missing 'overall_status'"
        print(f"Observability: {data['overall_status']}")
    
    def test_observability_key_metrics(self, auth_headers):
        """GET /api/production-golive/observability/key-metrics - key metrics"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/observability/key-metrics",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        # Key metrics should have various performance indicators
        assert isinstance(data, dict), "Expected dict response"
        print(f"Key metrics: {len(data)} metric categories")


class TestBackupEndpoints(TestAuthSetup):
    """Tests for backup DR validation endpoints."""
    
    def test_backup_validation(self, auth_headers):
        """GET /api/production-golive/backup/validation - backup system validation"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/backup/validation",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "enabled" in data, "Missing 'enabled'"
        assert "overall_status" in data, "Missing 'overall_status'"
        assert "rpo_target" in data, "Missing 'rpo_target'"
        assert "rto_target" in data, "Missing 'rto_target'"
        print(f"Backup: enabled={data['enabled']}, status={data['overall_status']}")


class TestSecurityEndpoints(TestAuthSetup):
    """Tests for security checklist endpoints."""
    
    def test_security_checklist(self, auth_headers):
        """GET /api/production-golive/security/checklist - full security checklist"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/security/checklist",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "overall_status" in data, "Missing 'overall_status'"
        assert data["overall_status"] in ["PASS", "PARTIAL", "FAIL"]
        assert "passed" in data, "Missing 'passed'"
        assert "total" in data, "Missing 'total'"
        assert "score" in data, "Missing 'score'"
        assert "checks" in data, "Missing 'checks'"
        print(f"Security: {data['overall_status']} ({data['passed']}/{data['total']})")
    
    def test_security_tenant_isolation(self, auth_headers):
        """GET /api/production-golive/security/tenant-isolation - tenant isolation"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/security/tenant-isolation",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "check" in data or "pass" in data, "Missing expected fields"
        print(f"Tenant isolation: pass={data.get('pass', 'unknown')}")
    
    def test_security_rbac(self, auth_headers):
        """GET /api/production-golive/security/rbac - RBAC validation"""
        response = requests.get(
            f"{BASE_URL}/api/production-golive/security/rbac",
            headers=auth_headers
        )
        assert response.status_code == 200, f"Failed: {response.text}"
        data = response.json()
        
        assert "check" in data or "pass" in data, "Missing expected fields"
        print(f"RBAC: pass={data.get('pass', 'unknown')}")


class TestAuthRequired(TestAuthSetup):
    """Tests to verify auth is required for all endpoints."""
    
    @pytest.mark.parametrize("endpoint", [
        "/api/production-golive/readiness",
        "/api/production-golive/summary",
        "/api/production-golive/config/validate",
        "/api/production-golive/config/inspect",
        "/api/production-golive/config/startup-check",
        "/api/production-golive/config/leak-scan",
        "/api/production-golive/redis/cluster-validation",
        "/api/production-golive/redis/pubsub-health",
        "/api/production-golive/redis/lock-safety",
        "/api/production-golive/mongo/health",
        "/api/production-golive/mongo/pool",
        "/api/production-golive/mongo/indexes",
        "/api/production-golive/mongo/collections",
        "/api/production-golive/mongo/schema-drift",
        "/api/production-golive/mongo/slow-queries",
        "/api/production-golive/mongo/replica-set",
        "/api/production-golive/workers/validation",
        "/api/production-golive/workers/scaling-readiness",
        "/api/production-golive/providers/status",
        "/api/production-golive/providers/validate",
        "/api/production-golive/providers/delivery-metrics",
        "/api/production-golive/observability/validation",
        "/api/production-golive/observability/key-metrics",
        "/api/production-golive/backup/validation",
        "/api/production-golive/security/checklist",
        "/api/production-golive/security/tenant-isolation",
        "/api/production-golive/security/rbac",
    ])
    def test_endpoints_return_401_or_403_without_token(self, endpoint):
        """All production-golive endpoints require authentication."""
        response = requests.get(f"{BASE_URL}{endpoint}")
        assert response.status_code in [401, 403], \
            f"{endpoint} should require auth, got {response.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
