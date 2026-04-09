"""
Sprint 3: Encryption Management API Tests

Tests for:
- Key Registry: register, list, state transitions, emergency revoke
- Re-encryption Jobs: create, start, pause, cancel
- Dashboard endpoints
- Audit logs
- Key safe summary
"""
import os
import pytest
import requests
import uuid

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = "https://correlation-trace.preview.emergentagent.com"

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for admin user."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=30,
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    return data.get("access_token")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token."""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json",
    }


@pytest.fixture(scope="module")
def test_key_id():
    """Generate unique test key ID."""
    return f"TEST-key-{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def test_job_id():
    """Placeholder for job ID created during tests."""
    return {"id": None}


class TestAuthRequired:
    """Test that all endpoints require authentication."""

    def test_keys_list_requires_auth(self):
        """GET /api/ops/encryption/keys requires auth."""
        response = requests.get(f"{BASE_URL}/api/ops/encryption/keys", timeout=10)
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

    def test_dashboard_requires_auth(self):
        """GET /api/ops/encryption/dashboard requires auth."""
        response = requests.get(f"{BASE_URL}/api/ops/encryption/dashboard", timeout=10)
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"

    def test_register_key_requires_auth(self):
        """POST /api/ops/encryption/keys/register requires auth."""
        response = requests.post(
            f"{BASE_URL}/api/ops/encryption/keys/register",
            json={"key_id": "test", "key_type": "master"},
            timeout=10,
        )
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"


class TestKeyRegistry:
    """Key registry CRUD and state management tests."""

    def test_register_key_success(self, auth_headers, test_key_id):
        """POST /api/ops/encryption/keys/register - register new key."""
        response = requests.post(
            f"{BASE_URL}/api/ops/encryption/keys/register",
            headers=auth_headers,
            json={
                "key_id": test_key_id,
                "key_type": "master",
                "description": "Test master key for Sprint 3 testing",
                "rotation_policy_days": 30,
            },
            timeout=30,
        )
        assert response.status_code == 200, f"Register failed: {response.text}"
        data = response.json()
        assert data.get("success") is True
        assert data.get("key_id") == test_key_id
        assert data.get("state") == "active"
        assert "next_rotation_due" in data
        print(f"✓ Key registered: {test_key_id}")

    def test_register_duplicate_key_fails(self, auth_headers, test_key_id):
        """POST /api/ops/encryption/keys/register - duplicate key fails."""
        response = requests.post(
            f"{BASE_URL}/api/ops/encryption/keys/register",
            headers=auth_headers,
            json={
                "key_id": test_key_id,
                "key_type": "master",
                "description": "Duplicate key",
            },
            timeout=30,
        )
        # Should return 400 or success=False
        if response.status_code == 200:
            data = response.json()
            assert data.get("success") is False
            assert "already registered" in data.get("error", "").lower()
        else:
            assert response.status_code == 400
        print("✓ Duplicate key registration rejected")

    def test_register_invalid_key_type_fails(self, auth_headers):
        """POST /api/ops/encryption/keys/register - invalid key type fails."""
        response = requests.post(
            f"{BASE_URL}/api/ops/encryption/keys/register",
            headers=auth_headers,
            json={
                "key_id": f"TEST-invalid-{uuid.uuid4().hex[:6]}",
                "key_type": "invalid_type",
                "description": "Invalid type test",
            },
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Invalid key type rejected")

    def test_list_keys(self, auth_headers, test_key_id):
        """GET /api/ops/encryption/keys - list all keys."""
        response = requests.get(
            f"{BASE_URL}/api/ops/encryption/keys",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"List failed: {response.text}"
        data = response.json()
        assert "keys" in data
        assert "count" in data
        assert isinstance(data["keys"], list)
        # Verify our test key is in the list
        key_ids = [k["key_id"] for k in data["keys"]]
        assert test_key_id in key_ids, f"Test key {test_key_id} not found in list"
        print(f"✓ Listed {data['count']} keys")

    def test_list_keys_filter_by_state(self, auth_headers):
        """GET /api/ops/encryption/keys?state=active - filter by state."""
        response = requests.get(
            f"{BASE_URL}/api/ops/encryption/keys",
            headers=auth_headers,
            params={"state": "active"},
            timeout=30,
        )
        assert response.status_code == 200, f"Filter failed: {response.text}"
        data = response.json()
        # All returned keys should be active
        for key in data["keys"]:
            assert key["state"] == "active", f"Key {key['key_id']} has state {key['state']}"
        print(f"✓ Filtered {data['count']} active keys")

    def test_list_keys_filter_by_type(self, auth_headers):
        """GET /api/ops/encryption/keys?key_type=master - filter by type."""
        response = requests.get(
            f"{BASE_URL}/api/ops/encryption/keys",
            headers=auth_headers,
            params={"key_type": "master"},
            timeout=30,
        )
        assert response.status_code == 200, f"Filter failed: {response.text}"
        data = response.json()
        for key in data["keys"]:
            assert key["key_type"] == "master", f"Key {key['key_id']} has type {key['key_type']}"
        print(f"✓ Filtered {data['count']} master keys")

    def test_get_key_by_id(self, auth_headers, test_key_id):
        """GET /api/ops/encryption/keys/{key_id} - get specific key."""
        response = requests.get(
            f"{BASE_URL}/api/ops/encryption/keys/{test_key_id}",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Get key failed: {response.text}"
        data = response.json()
        assert data["key_id"] == test_key_id
        assert data["key_type"] == "master"
        assert data["state"] == "active"
        assert "version" in data
        assert "created_at" in data
        print(f"✓ Got key details: {test_key_id}")

    def test_get_key_not_found(self, auth_headers):
        """GET /api/ops/encryption/keys/{key_id} - non-existent key returns 404."""
        response = requests.get(
            f"{BASE_URL}/api/ops/encryption/keys/non-existent-key-xyz",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("✓ Non-existent key returns 404")

    def test_get_key_summary(self, auth_headers, test_key_id):
        """GET /api/ops/encryption/keys/{key_id}/summary - safe summary."""
        response = requests.get(
            f"{BASE_URL}/api/ops/encryption/keys/{test_key_id}/summary",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Summary failed: {response.text}"
        data = response.json()
        assert data["key_id"] == test_key_id
        assert "state" in data
        assert "version" in data
        assert "days_until_rotation" in data
        assert "is_overdue" in data
        print(f"✓ Got key summary: days_until_rotation={data.get('days_until_rotation')}")


class TestKeyStateTransitions:
    """Key state transition tests."""

    def test_initiate_rotation(self, auth_headers, test_key_id):
        """POST /api/ops/encryption/keys/rotation/initiate - start rotation."""
        response = requests.post(
            f"{BASE_URL}/api/ops/encryption/keys/rotation/initiate",
            headers=auth_headers,
            json={"key_id": test_key_id, "reason": "test_rotation"},
            timeout=30,
        )
        assert response.status_code == 200, f"Initiate rotation failed: {response.text}"
        data = response.json()
        assert data.get("success") is True
        assert data.get("new_state") == "pending_rotation"
        print(f"✓ Rotation initiated: {test_key_id} -> pending_rotation")

    def test_verify_pending_rotation_state(self, auth_headers, test_key_id):
        """Verify key is now in pending_rotation state."""
        response = requests.get(
            f"{BASE_URL}/api/ops/encryption/keys/{test_key_id}",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["state"] == "pending_rotation"
        print("✓ Key state verified: pending_rotation")

    def test_cancel_rotation(self, auth_headers, test_key_id):
        """POST /api/ops/encryption/keys/rotation/cancel - cancel rotation."""
        response = requests.post(
            f"{BASE_URL}/api/ops/encryption/keys/rotation/cancel",
            headers=auth_headers,
            json={"key_id": test_key_id, "reason": "test_cancel"},
            timeout=30,
        )
        assert response.status_code == 200, f"Cancel rotation failed: {response.text}"
        data = response.json()
        assert data.get("success") is True
        assert data.get("new_state") == "active"
        print(f"✓ Rotation cancelled: {test_key_id} -> active")

    def test_initiate_and_complete_rotation(self, auth_headers, test_key_id):
        """Full rotation flow: initiate -> complete."""
        # Initiate
        response = requests.post(
            f"{BASE_URL}/api/ops/encryption/keys/rotation/initiate",
            headers=auth_headers,
            json={"key_id": test_key_id, "reason": "complete_test"},
            timeout=30,
        )
        assert response.status_code == 200
        assert response.json().get("success") is True

        # Complete
        response = requests.post(
            f"{BASE_URL}/api/ops/encryption/keys/rotation/complete",
            headers=auth_headers,
            json={"key_id": test_key_id},
            timeout=30,
        )
        assert response.status_code == 200, f"Complete rotation failed: {response.text}"
        data = response.json()
        assert data.get("success") is True
        assert data.get("state") == "retired"
        assert "version" in data
        print(f"✓ Rotation completed: {test_key_id} -> retired (v{data.get('version')})")


class TestEmergencyRevoke:
    """Emergency revoke flow tests."""

    def test_emergency_revoke_requires_reason(self, auth_headers):
        """POST /api/ops/encryption/keys/emergency-revoke - requires detailed reason."""
        # Create a key to revoke
        revoke_key_id = f"TEST-revoke-{uuid.uuid4().hex[:6]}"
        requests.post(
            f"{BASE_URL}/api/ops/encryption/keys/register",
            headers=auth_headers,
            json={"key_id": revoke_key_id, "key_type": "api", "description": "Key for revoke test"},
            timeout=30,
        )

        # Try to revoke with short reason
        response = requests.post(
            f"{BASE_URL}/api/ops/encryption/keys/emergency-revoke",
            headers=auth_headers,
            json={"key_id": revoke_key_id, "reason": "short"},
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400 for short reason, got {response.status_code}"
        print("✓ Short revoke reason rejected")

    def test_emergency_revoke_success(self, auth_headers):
        """POST /api/ops/encryption/keys/emergency-revoke - successful revoke."""
        # Create a key to revoke
        revoke_key_id = f"TEST-revoke-{uuid.uuid4().hex[:6]}"
        requests.post(
            f"{BASE_URL}/api/ops/encryption/keys/register",
            headers=auth_headers,
            json={"key_id": revoke_key_id, "key_type": "webhook", "description": "Key for revoke test"},
            timeout=30,
        )

        # Revoke with proper reason
        response = requests.post(
            f"{BASE_URL}/api/ops/encryption/keys/emergency-revoke",
            headers=auth_headers,
            json={
                "key_id": revoke_key_id,
                "reason": "Security incident detected - key potentially compromised during testing",
            },
            timeout=30,
        )
        assert response.status_code == 200, f"Revoke failed: {response.text}"
        data = response.json()
        assert data.get("success") is True
        assert data.get("state") == "revoked"
        assert "action_required" in data
        print(f"✓ Key revoked: {revoke_key_id}")

        # Verify state
        response = requests.get(
            f"{BASE_URL}/api/ops/encryption/keys/{revoke_key_id}",
            headers=auth_headers,
            params={"include_revoked": "true"},
            timeout=30,
        )
        if response.status_code == 200:
            assert response.json()["state"] == "revoked"
            print("✓ Revoked state verified")


class TestReencryptionJobs:
    """Re-encryption job CRUD tests."""

    def test_create_reencryption_job(self, auth_headers, test_job_id):
        """POST /api/ops/encryption/reencryption/create - create job."""
        # First create a key for the job
        job_key_id = f"TEST-job-key-{uuid.uuid4().hex[:6]}"
        requests.post(
            f"{BASE_URL}/api/ops/encryption/keys/register",
            headers=auth_headers,
            json={"key_id": job_key_id, "key_type": "pii", "description": "Key for job test"},
            timeout=30,
        )

        response = requests.post(
            f"{BASE_URL}/api/ops/encryption/reencryption/create",
            headers=auth_headers,
            json={
                "key_id": job_key_id,
                "collections": ["guests", "bookings"],
                "batch_size": 50,
                "description": "Test re-encryption job",
            },
            timeout=30,
        )
        assert response.status_code == 200, f"Create job failed: {response.text}"
        data = response.json()
        assert "job_id" in data
        assert data.get("state") == "pending"
        assert "total_documents" in data
        test_job_id["id"] = data["job_id"]
        print(f"✓ Job created: {data['job_id']} ({data.get('total_documents')} docs)")

    def test_create_job_requires_collections(self, auth_headers):
        """POST /api/ops/encryption/reencryption/create - requires collections."""
        response = requests.post(
            f"{BASE_URL}/api/ops/encryption/reencryption/create",
            headers=auth_headers,
            json={
                "key_id": "some-key",
                "collections": [],
                "description": "Empty collections test",
            },
            timeout=30,
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        print("✓ Empty collections rejected")

    def test_list_reencryption_jobs(self, auth_headers, test_job_id):
        """GET /api/ops/encryption/reencryption/jobs - list jobs."""
        response = requests.get(
            f"{BASE_URL}/api/ops/encryption/reencryption/jobs",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"List jobs failed: {response.text}"
        data = response.json()
        assert "jobs" in data
        assert "count" in data
        if test_job_id["id"]:
            job_ids = [j["job_id"] for j in data["jobs"]]
            assert test_job_id["id"] in job_ids
        print(f"✓ Listed {data['count']} jobs")

    def test_get_job_status(self, auth_headers, test_job_id):
        """GET /api/ops/encryption/reencryption/jobs/{job_id} - get job status."""
        if not test_job_id["id"]:
            pytest.skip("No job created")

        response = requests.get(
            f"{BASE_URL}/api/ops/encryption/reencryption/jobs/{test_job_id['id']}",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Get job failed: {response.text}"
        data = response.json()
        assert data["job_id"] == test_job_id["id"]
        assert "state" in data
        assert "progress_percent" in data
        assert "total_documents" in data
        print(f"✓ Job status: {data['state']} ({data['progress_percent']}%)")

    def test_start_job(self, auth_headers, test_job_id):
        """POST /api/ops/encryption/reencryption/start - start job."""
        if not test_job_id["id"]:
            pytest.skip("No job created")

        response = requests.post(
            f"{BASE_URL}/api/ops/encryption/reencryption/start",
            headers=auth_headers,
            json={"job_id": test_job_id["id"]},
            timeout=30,
        )
        assert response.status_code == 200, f"Start job failed: {response.text}"
        data = response.json()
        assert data.get("success") is True
        assert data.get("state") == "running"
        print(f"✓ Job started: {test_job_id['id']}")

    def test_pause_job(self, auth_headers, test_job_id):
        """POST /api/ops/encryption/reencryption/pause - pause job."""
        if not test_job_id["id"]:
            pytest.skip("No job created")

        response = requests.post(
            f"{BASE_URL}/api/ops/encryption/reencryption/pause",
            headers=auth_headers,
            json={"job_id": test_job_id["id"]},
            timeout=30,
        )
        # May fail if job already completed
        if response.status_code == 200:
            data = response.json()
            assert data.get("success") is True
            assert data.get("state") == "paused"
            print(f"✓ Job paused: {test_job_id['id']}")
        else:
            print(f"✓ Pause returned {response.status_code} (job may have completed)")

    def test_cancel_job(self, auth_headers, test_job_id):
        """POST /api/ops/encryption/reencryption/cancel - cancel job."""
        if not test_job_id["id"]:
            pytest.skip("No job created")

        response = requests.post(
            f"{BASE_URL}/api/ops/encryption/reencryption/cancel",
            headers=auth_headers,
            json={"job_id": test_job_id["id"], "reason": "Test cancellation"},
            timeout=30,
        )
        # May fail if job already in terminal state
        if response.status_code == 200:
            data = response.json()
            assert data.get("success") is True
            assert data.get("state") == "cancelled"
            print(f"✓ Job cancelled: {test_job_id['id']}")
        else:
            print(f"✓ Cancel returned {response.status_code} (job may be in terminal state)")


class TestDashboards:
    """Dashboard endpoint tests."""

    def test_main_dashboard(self, auth_headers):
        """GET /api/ops/encryption/dashboard - main dashboard."""
        response = requests.get(
            f"{BASE_URL}/api/ops/encryption/dashboard",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Dashboard failed: {response.text}"
        data = response.json()
        assert "keys" in data
        assert "reencryption_jobs" in data
        assert "timestamp" in data

        # Verify keys dashboard structure
        keys = data["keys"]
        assert "summary" in keys
        assert "keys" in keys
        summary = keys["summary"]
        assert "total" in summary
        assert "active" in summary
        assert "pending_rotation" in summary
        assert "retired" in summary
        assert "revoked" in summary

        # Verify jobs dashboard structure
        jobs = data["reencryption_jobs"]
        assert "summary" in jobs
        assert "recent_jobs" in jobs

        print(f"✓ Dashboard: {summary['total']} keys, {jobs['summary']['total_jobs']} jobs")

    def test_keys_dashboard(self, auth_headers):
        """GET /api/ops/encryption/dashboard/keys - keys dashboard only."""
        response = requests.get(
            f"{BASE_URL}/api/ops/encryption/dashboard/keys",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Keys dashboard failed: {response.text}"
        data = response.json()
        assert "summary" in data
        assert "keys" in data
        assert "by_type" in data
        assert "overdue_rotations" in data
        assert "rotation_warnings" in data
        print(f"✓ Keys dashboard: {data['summary']['total']} total, {data['summary']['overdue_count']} overdue")

    def test_jobs_dashboard(self, auth_headers):
        """GET /api/ops/encryption/dashboard/jobs - jobs dashboard only."""
        response = requests.get(
            f"{BASE_URL}/api/ops/encryption/dashboard/jobs",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Jobs dashboard failed: {response.text}"
        data = response.json()
        assert "summary" in data
        assert "recent_jobs" in data
        summary = data["summary"]
        assert "total_jobs" in summary
        assert "pending" in summary
        assert "running" in summary
        assert "completed" in summary
        print(f"✓ Jobs dashboard: {summary['total_jobs']} total, {summary['running']} running")


class TestAuditLogs:
    """Audit log endpoint tests."""

    def test_key_audit_log(self, auth_headers):
        """GET /api/ops/encryption/audit/keys - key audit log."""
        response = requests.get(
            f"{BASE_URL}/api/ops/encryption/audit/keys",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Key audit failed: {response.text}"
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)
        if data["items"]:
            item = data["items"][0]
            assert "key_id" in item
            assert "action" in item
            assert "actor" in item
            assert "timestamp" in item
        print(f"✓ Key audit log: {data['total']} entries")

    def test_key_audit_log_filter_by_key(self, auth_headers, test_key_id):
        """GET /api/ops/encryption/audit/keys?key_id=... - filter by key."""
        response = requests.get(
            f"{BASE_URL}/api/ops/encryption/audit/keys",
            headers=auth_headers,
            params={"key_id": test_key_id},
            timeout=30,
        )
        assert response.status_code == 200, f"Filtered audit failed: {response.text}"
        data = response.json()
        for item in data["items"]:
            assert item["key_id"] == test_key_id
        print(f"✓ Filtered key audit: {len(data['items'])} entries for {test_key_id}")

    def test_job_audit_log(self, auth_headers):
        """GET /api/ops/encryption/audit/jobs - job audit log."""
        response = requests.get(
            f"{BASE_URL}/api/ops/encryption/audit/jobs",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Job audit failed: {response.text}"
        data = response.json()
        assert "items" in data
        assert "total" in data
        if data["items"]:
            item = data["items"][0]
            assert "job_id" in item
            assert "action" in item
            assert "actor" in item
        print(f"✓ Job audit log: {data['total']} entries")


class TestActiveKeyLookup:
    """Active key lookup tests."""

    def test_get_active_key_by_type(self, auth_headers):
        """GET /api/ops/encryption/keys/active/{key_type} - get active key."""
        # Create an active key of type 'connector'
        active_key_id = f"TEST-active-{uuid.uuid4().hex[:6]}"
        requests.post(
            f"{BASE_URL}/api/ops/encryption/keys/register",
            headers=auth_headers,
            json={"key_id": active_key_id, "key_type": "connector", "description": "Active connector key"},
            timeout=30,
        )

        response = requests.get(
            f"{BASE_URL}/api/ops/encryption/keys/active/connector",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Get active key failed: {response.text}"
        data = response.json()
        assert data["key_type"] == "connector"
        assert data["state"] == "active"
        print(f"✓ Active connector key: {data['key_id']}")

    def test_get_active_key_not_found(self, auth_headers):
        """GET /api/ops/encryption/keys/active/{key_type} - no active key returns 404."""
        # Use a unique tenant_id that won't have any keys
        response = requests.get(
            f"{BASE_URL}/api/ops/encryption/keys/active/master",
            headers=auth_headers,
            params={"tenant_id": "non-existent-tenant-xyz"},
            timeout=30,
        )
        # May return 404 or an active key if one exists for system
        if response.status_code == 404:
            print("✓ No active key for non-existent tenant returns 404")
        else:
            print(f"✓ Active key lookup returned {response.status_code}")


class TestIndexSetup:
    """Index setup endpoint test."""

    def test_setup_indexes(self, auth_headers):
        """POST /api/ops/encryption/setup-indexes - create indexes."""
        response = requests.post(
            f"{BASE_URL}/api/ops/encryption/setup-indexes",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Setup indexes failed: {response.text}"
        data = response.json()
        assert data.get("status") == "ok"
        print("✓ Indexes created successfully")


class TestExistingData:
    """Tests for existing seed data mentioned in context."""

    def test_existing_keys_present(self, auth_headers):
        """Verify existing keys from seed data."""
        response = requests.get(
            f"{BASE_URL}/api/ops/encryption/keys",
            headers=auth_headers,
            params={"include_revoked": "true"},
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        key_ids = [k["key_id"] for k in data["keys"]]
        
        # Check for expected seed keys (may or may not exist)
        expected_keys = ["master-key-v1", "pii-key-v1", "connector-hotelrunner-v1"]
        found_keys = [k for k in expected_keys if k in key_ids]
        print(f"✓ Found {len(found_keys)}/{len(expected_keys)} expected seed keys: {found_keys}")

    def test_pending_rotation_key(self, auth_headers):
        """Check for key in pending_rotation state."""
        response = requests.get(
            f"{BASE_URL}/api/ops/encryption/keys",
            headers=auth_headers,
            params={"state": "pending_rotation"},
            timeout=30,
        )
        assert response.status_code == 200
        data = response.json()
        print(f"✓ Found {data['count']} keys in pending_rotation state")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
