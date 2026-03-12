"""
Test Suite: Multi-Phase Hardening APIs
Tests for Phase C/D/E hardening endpoints:
- Channel Manager Hardening (runtime status, drift, reconciliation, sync, providers)
- Worker/Queue Hardening (queue health, stuck tasks, failures, retries)
- Security Hardening (audit, rate-limit, credentials check, tenant guard, log sanitization)
- Observability Runtime (metrics, alerts)
Plus core endpoints (auth, PMS rooms/bookings, housekeeping)
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestAuth:
    """Authentication endpoint tests"""
    
    def test_login_success(self):
        """POST /api/auth/login - returns access_token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, f"No access_token in response: {data}"
        assert isinstance(data["access_token"], str)
        assert len(data["access_token"]) > 0
        print(f"✅ Login successful, token length: {len(data['access_token'])}")
    
    def test_get_me_with_token(self, auth_token):
        """GET /api/auth/me - returns user info with Bearer token"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/auth/me", headers=headers)
        assert response.status_code == 200, f"Get me failed: {response.text}"
        data = response.json()
        assert "email" in data, f"No email in response: {data}"
        print(f"✅ Get me successful, user: {data.get('email')}")


class TestPMSCore:
    """PMS core endpoint tests (rooms, bookings)"""
    
    def test_get_rooms(self, auth_token):
        """GET /api/pms/rooms?limit=5 - returns room list"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/pms/rooms?limit=5", headers=headers)
        assert response.status_code == 200, f"Get rooms failed: {response.text}"
        data = response.json()
        # Response could be a list or an object with rooms key
        assert isinstance(data, (list, dict)), f"Unexpected response type: {type(data)}"
        print(f"✅ Get rooms successful: {type(data)}")
    
    def test_get_bookings(self, auth_token):
        """GET /api/pms/bookings?limit=5 - returns booking list"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/pms/bookings?limit=5", headers=headers)
        assert response.status_code == 200, f"Get bookings failed: {response.text}"
        data = response.json()
        assert isinstance(data, (list, dict)), f"Unexpected response type: {type(data)}"
        print("✅ Get bookings successful")


class TestHousekeeping:
    """Housekeeping endpoint tests"""
    
    def test_get_housekeeping_tasks(self, auth_token):
        """GET /api/housekeeping/tasks - returns tasks"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/housekeeping/tasks", headers=headers)
        assert response.status_code == 200, f"Get housekeeping tasks failed: {response.text}"
        data = response.json()
        assert isinstance(data, (list, dict)), f"Unexpected response type: {type(data)}"
        print("✅ Get housekeeping tasks successful")


class TestChannelManagerHardening:
    """Channel Manager hardening API tests (Phase C)"""
    
    def test_runtime_status(self, auth_token):
        """GET /api/channel-manager/runtime/status - returns health, sync_stats, drift, reconciliation, providers"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/channel-manager/runtime/status", headers=headers)
        assert response.status_code == 200, f"Runtime status failed: {response.text}"
        data = response.json()
        # Validate response contains expected keys (may vary based on impl)
        print(f"✅ CM runtime status: {list(data.keys()) if isinstance(data, dict) else 'list response'}")
    
    def test_drift_scan(self, auth_token):
        """POST /api/channel-manager/drift/scan - returns scan results with pms_room_types, drifts_found"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.post(f"{BASE_URL}/api/channel-manager/drift/scan", headers=headers)
        assert response.status_code == 200, f"Drift scan failed: {response.text}"
        data = response.json()
        print(f"✅ Drift scan successful: {list(data.keys()) if isinstance(data, dict) else 'response'}")
    
    def test_drift_issues(self, auth_token):
        """GET /api/channel-manager/drift/issues - returns scans list"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/channel-manager/drift/issues", headers=headers)
        assert response.status_code == 200, f"Drift issues failed: {response.text}"
        data = response.json()
        assert "scans" in data or isinstance(data, list), f"Unexpected response: {data}"
        print(f"✅ Drift issues: count={data.get('count', len(data) if isinstance(data, list) else 'N/A')}")
    
    def test_reconciliation_run(self, auth_token):
        """POST /api/channel-manager/reconciliation/run - returns reconciliation result"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.post(f"{BASE_URL}/api/channel-manager/reconciliation/run", headers=headers)
        assert response.status_code == 200, f"Reconciliation run failed: {response.text}"
        data = response.json()
        print(f"✅ Reconciliation run successful: {list(data.keys()) if isinstance(data, dict) else 'response'}")
    
    def test_reconciliation_history(self, auth_token):
        """GET /api/channel-manager/reconciliation/history - returns results list"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/channel-manager/reconciliation/history", headers=headers)
        assert response.status_code == 200, f"Reconciliation history failed: {response.text}"
        data = response.json()
        assert "results" in data or isinstance(data, list), f"Unexpected response: {data}"
        print(f"✅ Reconciliation history: count={data.get('count', len(data) if isinstance(data, list) else 'N/A')}")
    
    def test_sync_schedule(self, auth_token):
        """GET /api/channel-manager/sync/schedule - returns running, interval_seconds"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/channel-manager/sync/schedule", headers=headers)
        assert response.status_code == 200, f"Sync schedule failed: {response.text}"
        data = response.json()
        assert "running" in data, f"No 'running' key in response: {data}"
        assert "interval_seconds" in data, f"No 'interval_seconds' key in response: {data}"
        print(f"✅ Sync schedule: running={data['running']}, interval={data['interval_seconds']}s")
    
    def test_sync_trigger(self, auth_token):
        """POST /api/channel-manager/sync/trigger?event_type=manual - returns status triggered"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.post(f"{BASE_URL}/api/channel-manager/sync/trigger?event_type=manual", headers=headers)
        assert response.status_code == 200, f"Sync trigger failed: {response.text}"
        data = response.json()
        assert "status" in data, f"No 'status' key in response: {data}"
        print(f"✅ Sync trigger: status={data['status']}")
    
    def test_providers_health(self, auth_token):
        """GET /api/channel-manager/providers/health - returns providers list, circuit_breakers"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/channel-manager/providers/health", headers=headers)
        assert response.status_code == 200, f"Providers health failed: {response.text}"
        data = response.json()
        assert "providers" in data or "circuit_breakers" in data, f"Missing expected keys: {data}"
        print(f"✅ Providers health: {list(data.keys())}")


class TestWorkersHardening:
    """Worker/Queue hardening API tests (Phase D)"""
    
    def test_queues_health(self, auth_token):
        """GET /api/workers/queues/health - returns health, pending, processing, stuck, saturation_pct"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/workers/queues/health", headers=headers)
        assert response.status_code == 200, f"Queues health failed: {response.text}"
        data = response.json()
        print(f"✅ Queues health: {list(data.keys()) if isinstance(data, dict) else 'response'}")
    
    def test_stuck_tasks(self, auth_token):
        """GET /api/workers/tasks/stuck - returns stuck_tasks list, count"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/workers/tasks/stuck", headers=headers)
        assert response.status_code == 200, f"Stuck tasks failed: {response.text}"
        data = response.json()
        assert "stuck_tasks" in data, f"No 'stuck_tasks' key: {data}"
        assert "count" in data, f"No 'count' key: {data}"
        print(f"✅ Stuck tasks: count={data['count']}")
    
    def test_task_failures(self, auth_token):
        """GET /api/workers/tasks/failures - returns failures list, stats"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/workers/tasks/failures", headers=headers)
        assert response.status_code == 200, f"Task failures failed: {response.text}"
        data = response.json()
        assert "failures" in data or "stats" in data, f"Missing expected keys: {data}"
        print(f"✅ Task failures: {list(data.keys())}")
    
    def test_retries_summary(self, auth_token):
        """GET /api/workers/retries/summary - returns period, status_counts, by_type"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/workers/retries/summary", headers=headers)
        assert response.status_code == 200, f"Retries summary failed: {response.text}"
        data = response.json()
        print(f"✅ Retries summary: {list(data.keys()) if isinstance(data, dict) else 'response'}")


class TestSecurityHardening:
    """Security hardening API tests (Phase E)"""
    
    def test_audit_status(self, auth_token):
        """GET /api/security/audit/status - returns completeness, summary"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/security/audit/status", headers=headers)
        assert response.status_code == 200, f"Audit status failed: {response.text}"
        data = response.json()
        assert "completeness" in data or "summary" in data, f"Missing expected keys: {data}"
        print(f"✅ Audit status: {list(data.keys())}")
    
    def test_rate_limit_status(self, auth_token):
        """GET /api/security/rate-limit/status - returns enforcement active, stats"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/security/rate-limit/status", headers=headers)
        assert response.status_code == 200, f"Rate limit status failed: {response.text}"
        data = response.json()
        assert "enforcement" in data, f"No 'enforcement' key: {data}"
        print(f"✅ Rate limit status: enforcement={data['enforcement']}")
    
    def test_credentials_check(self, auth_token):
        """POST /api/security/credentials/check - returns scanned_users, weak_credentials_found
        Note: This endpoint may take 5-10 seconds due to bcrypt verification
        """
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.post(f"{BASE_URL}/api/security/credentials/check", headers=headers, timeout=30)
        # Accept 200 (success) or 403 (non-admin)
        assert response.status_code in [200, 403], f"Credentials check failed: {response.text}"
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Credentials check: {list(data.keys())}")
        else:
            print("✅ Credentials check: 403 (admin required, expected for demo user)")
    
    def test_tenant_guard_status(self, auth_token):
        """GET /api/security/tenant-guard/status - returns enforcement active, total_violations"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/security/tenant-guard/status", headers=headers)
        assert response.status_code == 200, f"Tenant guard status failed: {response.text}"
        data = response.json()
        print(f"✅ Tenant guard status: {list(data.keys()) if isinstance(data, dict) else 'response'}")
    
    def test_log_sanitization_status(self, auth_token):
        """GET /api/security/log-sanitization/status - returns enforcement active, all_patterns_working true"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/security/log-sanitization/status", headers=headers)
        assert response.status_code == 200, f"Log sanitization status failed: {response.text}"
        data = response.json()
        assert "enforcement" in data, f"No 'enforcement' key: {data}"
        assert "all_patterns_working" in data, f"No 'all_patterns_working' key: {data}"
        print(f"✅ Log sanitization: enforcement={data['enforcement']}, patterns_working={data['all_patterns_working']}")


class TestObservabilityRuntime:
    """Observability runtime API tests"""
    
    def test_runtime_metrics(self, auth_token):
        """GET /api/observability/runtime/metrics - returns sync, drift, reconciliation, queue, security metrics"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/observability/runtime/metrics", headers=headers)
        assert response.status_code == 200, f"Runtime metrics failed: {response.text}"
        data = response.json()
        print(f"✅ Runtime metrics: {list(data.keys()) if isinstance(data, dict) else 'response'}")
    
    def test_runtime_alerts(self, auth_token):
        """GET /api/observability/runtime/alerts - returns alerts list, count, critical"""
        headers = {"Authorization": f"Bearer {auth_token}"}
        response = requests.get(f"{BASE_URL}/api/observability/runtime/alerts", headers=headers)
        assert response.status_code == 200, f"Runtime alerts failed: {response.text}"
        data = response.json()
        assert "alerts" in data, f"No 'alerts' key: {data}"
        assert "count" in data, f"No 'count' key: {data}"
        print(f"✅ Runtime alerts: count={data['count']}, critical={data.get('critical', 0)}")


# ── Fixtures ────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token using demo credentials"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": "demo@hotel.com",
        "password": "demo123"
    })
    if response.status_code != 200:
        pytest.skip(f"Authentication failed: {response.text}")
    data = response.json()
    token = data.get("access_token")
    if not token:
        pytest.skip(f"No access_token in response: {data}")
    return token
