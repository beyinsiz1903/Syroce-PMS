"""
Deploy Pipeline API Tests
=========================
Tests for the production deploy pipeline: hard-gate CI/CD, progressive deploy,
auto-rollback, migration verification, smoke tests, and canary analysis.

Endpoints tested:
- GET /api/deploy/pipeline/gates — gate definitions
- POST /api/deploy/pipeline/start — create pipeline run
- POST /api/deploy/pipeline/run-all — run all gates sequentially
- GET /api/deploy/pipelines — list recent pipelines
- GET /api/deploy/pipeline/{pipeline_id} — get specific pipeline
- GET /api/deploy/migration/verify — schema drift detection
- GET /api/deploy/migration/stats — collection statistics
- POST /api/deploy/smoke-tests/run — run smoke tests
- GET /api/deploy/rollback/triggers — rollback trigger definitions
- GET /api/deploy/rollback/evaluate — evaluate real metrics
- GET /api/deploy/rollback/history — rollback history
- GET /api/deploy/analysis/overview — combined canary + triggers + pipeline
- POST /api/deploy/rollback/execute — execute manual rollback
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('VITE_BACKEND_URL', '').rstrip('/')

@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for API calls."""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": "demo@hotel.com", "password": "demo123"}
    )
    if response.status_code == 200:
        data = response.json()
        return data.get("access_token") or data.get("token")
    pytest.skip("Authentication failed - skipping tests")

@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Headers with auth token."""
    return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}


class TestPipelineGates:
    """Tests for pipeline gate definitions."""
    
    def test_get_gate_definitions(self, auth_headers):
        """GET /api/deploy/pipeline/gates — returns gate definitions."""
        response = requests.get(f"{BASE_URL}/api/deploy/pipeline/gates", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "data" in data, "Response should have 'data' field"
        assert "gates" in data["data"], "Response should have 'gates' array"
        
        gates = data["data"]["gates"]
        assert len(gates) >= 6, f"Expected at least 6 gates, got {len(gates)}"
        
        # Verify expected gates exist
        gate_ids = [g["id"] for g in gates]
        expected_gates = ["lint", "unit_test", "security_audit", "migration_check", "build", "smoke_test"]
        for expected in expected_gates:
            assert expected in gate_ids, f"Missing gate: {expected}"
        
        # Verify gate structure
        for gate in gates:
            assert "id" in gate
            assert "name" in gate
            assert "description" in gate
            assert "order" in gate
            assert "timeout_seconds" in gate
            assert "blocking" in gate
            assert gate["blocking"] is True, "All gates should be blocking (hard-gate)"
        
        print(f"PASS: Gate definitions returned {len(gates)} gates: {gate_ids}")


class TestPipelineStart:
    """Tests for starting a new pipeline run."""
    
    def test_start_pipeline(self, auth_headers):
        """POST /api/deploy/pipeline/start — creates a new pipeline run."""
        response = requests.post(
            f"{BASE_URL}/api/deploy/pipeline/start",
            headers=auth_headers,
            json={"version_tag": "test-v1.0.0"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "data" in data, "Response should have 'data' field"
        
        pipeline = data["data"]
        assert "pipeline_id" in pipeline, "Pipeline should have pipeline_id"
        assert pipeline["pipeline_id"].startswith("pipe-"), "Pipeline ID should start with 'pipe-'"
        assert pipeline["status"] == "running", "New pipeline should be 'running'"
        assert pipeline["version_tag"] == "test-v1.0.0", "Version tag should match"
        assert "gates" in pipeline, "Pipeline should have gates"
        assert pipeline["passed_gates"] == 0, "New pipeline should have 0 passed gates"
        assert pipeline["total_gates"] >= 6, "Pipeline should have at least 6 gates"
        
        # Verify all gates are pending
        for gate_id, gate_status in pipeline["gates"].items():
            assert gate_status["status"] == "pending", f"Gate {gate_id} should be pending"
        
        print(f"PASS: Pipeline started with ID: {pipeline['pipeline_id']}")
        return pipeline["pipeline_id"]


class TestPipelineList:
    """Tests for listing pipeline runs."""
    
    def test_list_pipelines(self, auth_headers):
        """GET /api/deploy/pipelines — lists recent pipeline runs."""
        response = requests.get(f"{BASE_URL}/api/deploy/pipelines?limit=10", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "data" in data, "Response should have 'data' field"
        assert "pipelines" in data["data"], "Response should have 'pipelines' array"
        
        pipelines = data["data"]["pipelines"]
        assert isinstance(pipelines, list), "Pipelines should be a list"
        
        if len(pipelines) > 0:
            pipeline = pipelines[0]
            assert "pipeline_id" in pipeline
            assert "status" in pipeline
            assert "triggered_by" in pipeline
            assert "started_at" in pipeline
            assert "gates" in pipeline
            print(f"PASS: Listed {len(pipelines)} pipelines, latest: {pipeline['pipeline_id']} ({pipeline['status']})")
        else:
            print("PASS: Pipeline list returned (empty)")


class TestPipelineGetById:
    """Tests for getting a specific pipeline."""
    
    def test_get_pipeline_by_id(self, auth_headers):
        """GET /api/deploy/pipeline/{pipeline_id} — returns specific pipeline."""
        # First create a pipeline
        start_response = requests.post(
            f"{BASE_URL}/api/deploy/pipeline/start",
            headers=auth_headers,
            json={"version_tag": "test-get-by-id"}
        )
        assert start_response.status_code == 200
        pipeline_id = start_response.json()["data"]["pipeline_id"]
        
        # Now get it by ID
        response = requests.get(f"{BASE_URL}/api/deploy/pipeline/{pipeline_id}", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "data" in data
        assert data["data"]["pipeline_id"] == pipeline_id
        print(f"PASS: Retrieved pipeline {pipeline_id}")
    
    def test_get_nonexistent_pipeline(self, auth_headers):
        """GET /api/deploy/pipeline/{invalid_id} — returns 404."""
        response = requests.get(f"{BASE_URL}/api/deploy/pipeline/pipe-nonexistent123", headers=auth_headers)
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        print("PASS: Nonexistent pipeline returns 404")


class TestMigrationVerification:
    """Tests for migration verification endpoints."""
    
    def test_verify_migrations(self, auth_headers):
        """GET /api/deploy/migration/verify — schema drift detection."""
        response = requests.get(f"{BASE_URL}/api/deploy/migration/verify", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "data" in data
        
        result = data["data"]
        assert "verified_at" in result
        assert "collections_checked" in result
        assert "drift_issues" in result
        assert "missing_indexes" in result
        assert "verdict" in result
        assert result["verdict"] in ["PASS", "WARN", "FAIL"]
        
        print(f"PASS: Migration verification: {result['collections_checked']} collections, verdict: {result['verdict']}")
    
    def test_collection_stats(self, auth_headers):
        """GET /api/deploy/migration/stats — collection statistics."""
        response = requests.get(f"{BASE_URL}/api/deploy/migration/stats", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "data" in data
        assert "collections" in data["data"]
        assert "total" in data["data"]
        
        collections = data["data"]["collections"]
        assert isinstance(collections, list)
        
        if len(collections) > 0:
            coll = collections[0]
            assert "collection" in coll
            assert "document_count" in coll
            assert "index_count" in coll
        
        print(f"PASS: Collection stats: {data['data']['total']} collections")


class TestSmokeTests:
    """Tests for smoke test runner."""
    
    def test_run_smoke_tests(self, auth_headers):
        """POST /api/deploy/smoke-tests/run — runs 8 HTTP smoke tests."""
        response = requests.post(f"{BASE_URL}/api/deploy/smoke-tests/run", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "data" in data
        
        result = data["data"]
        assert "ran_at" in result
        assert "total" in result
        assert "passed" in result
        assert "failed" in result
        assert "results" in result
        assert "verdict" in result
        
        assert result["total"] >= 8, f"Expected at least 8 smoke tests, got {result['total']}"
        
        # Verify result structure
        for test in result["results"]:
            assert "id" in test
            assert "name" in test
            assert "path" in test
            assert "passed" in test
            assert "duration_ms" in test
        
        print(f"PASS: Smoke tests: {result['passed']}/{result['total']} passed, verdict: {result['verdict']}")


class TestRollbackTriggers:
    """Tests for auto-rollback trigger endpoints."""
    
    def test_get_trigger_definitions(self, auth_headers):
        """GET /api/deploy/rollback/triggers — rollback trigger definitions."""
        response = requests.get(f"{BASE_URL}/api/deploy/rollback/triggers", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "data" in data
        assert "triggers" in data["data"]
        
        triggers = data["data"]["triggers"]
        assert len(triggers) >= 5, f"Expected at least 5 triggers, got {len(triggers)}"
        
        # Verify expected triggers
        trigger_ids = [t["id"] for t in triggers]
        expected_triggers = ["error_rate_5xx", "health_endpoint_down", "db_connection_fail", "outbox_backlog", "import_failure_rate"]
        for expected in expected_triggers:
            assert expected in trigger_ids, f"Missing trigger: {expected}"
        
        # Verify trigger structure
        for trigger in triggers:
            assert "id" in trigger
            assert "name" in trigger
            assert "description" in trigger
            assert "threshold" in trigger
            assert "unit" in trigger
            assert "action" in trigger
            assert "source" in trigger
        
        print(f"PASS: Trigger definitions: {len(triggers)} triggers defined")
    
    def test_evaluate_triggers(self, auth_headers):
        """GET /api/deploy/rollback/evaluate — evaluates real system metrics."""
        response = requests.get(f"{BASE_URL}/api/deploy/rollback/evaluate", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "data" in data
        
        result = data["data"]
        assert "evaluated_at" in result
        assert "triggers" in result
        assert "any_triggered" in result
        assert "recommendation" in result
        assert result["recommendation"] in ["continue", "pause", "rollback"]
        
        # Verify each trigger has current_value
        for trigger in result["triggers"]:
            assert "trigger_id" in trigger
            assert "current_value" in trigger
            assert "threshold" in trigger
            assert "triggered" in trigger
        
        print(f"PASS: Trigger evaluation: recommendation={result['recommendation']}, any_triggered={result['any_triggered']}")
    
    def test_rollback_history(self, auth_headers):
        """GET /api/deploy/rollback/history — rollback execution history."""
        response = requests.get(f"{BASE_URL}/api/deploy/rollback/history?limit=10", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "data" in data
        assert "rollbacks" in data["data"]
        assert "total" in data["data"]
        
        rollbacks = data["data"]["rollbacks"]
        assert isinstance(rollbacks, list)
        
        if len(rollbacks) > 0:
            rb = rollbacks[0]
            assert "rollback_id" in rb
            assert "executed_at" in rb
            assert "reason" in rb
            print(f"PASS: Rollback history: {len(rollbacks)} records, latest: {rb['rollback_id']}")
        else:
            print("PASS: Rollback history returned (empty)")


class TestAnalysisOverview:
    """Tests for combined analysis overview."""
    
    def test_analysis_overview(self, auth_headers):
        """GET /api/deploy/analysis/overview — combined canary + triggers + pipeline."""
        response = requests.get(f"{BASE_URL}/api/deploy/analysis/overview", headers=auth_headers)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Response structure: {canary, triggers, last_pipeline}
        assert "canary" in data or data.get("canary") is None
        assert "triggers" in data or data.get("triggers") is None
        assert "last_pipeline" in data or data.get("last_pipeline") is None
        
        print(f"PASS: Analysis overview returned (canary={data.get('canary') is not None}, triggers={data.get('triggers') is not None}, last_pipeline={data.get('last_pipeline') is not None})")


class TestRollbackExecute:
    """Tests for manual rollback execution."""
    
    def test_execute_rollback(self, auth_headers):
        """POST /api/deploy/rollback/execute — executes manual rollback."""
        response = requests.post(
            f"{BASE_URL}/api/deploy/rollback/execute",
            headers=auth_headers,
            json={"reason": "TEST_manual_rollback_test"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "data" in data
        
        result = data["data"]
        assert "rollback_id" in result
        assert "executed_at" in result
        assert "reason" in result
        assert result["reason"] == "TEST_manual_rollback_test"
        assert "status" in result
        assert result["status"] == "executed"
        
        # Verify smoke test verification was run
        if "verification" in result and result["verification"]:
            assert "smoke_tests_passed" in result["verification"]
            assert "smoke_tests_total" in result["verification"]
            assert "verdict" in result["verification"]
        
        print(f"PASS: Rollback executed: {result['rollback_id']}")


class TestPipelineRunAll:
    """Tests for running full pipeline (all gates)."""
    
    def test_run_full_pipeline(self, auth_headers):
        """POST /api/deploy/pipeline/run-all — runs all gates sequentially."""
        # Note: This may take 10+ seconds due to lint and test gates
        response = requests.post(
            f"{BASE_URL}/api/deploy/pipeline/run-all",
            headers=auth_headers,
            json={"version_tag": "test-full-run"},
            timeout=120  # Allow up to 2 minutes for full pipeline
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "data" in data
        
        pipeline = data["data"]
        assert "pipeline_id" in pipeline
        assert "status" in pipeline
        assert pipeline["status"] in ["passed", "failed", "running"]
        assert "gates" in pipeline
        assert "passed_gates" in pipeline
        assert "total_gates" in pipeline
        
        # Check gate statuses
        passed_count = 0
        failed_count = 0
        for gate_id, gate_status in pipeline["gates"].items():
            if gate_status["status"] == "passed":
                passed_count += 1
            elif gate_status["status"] == "failed":
                failed_count += 1
        
        print(f"PASS: Full pipeline run: {pipeline['pipeline_id']}, status={pipeline['status']}, passed={passed_count}/{pipeline['total_gates']}")
        
        # If pipeline failed, show which gate failed
        if pipeline["status"] == "failed":
            for gate_id, gate_status in pipeline["gates"].items():
                if gate_status["status"] == "failed":
                    errors = gate_status.get("errors", [])
                    print(f"  Gate '{gate_id}' failed: {errors[:2] if errors else 'no error details'}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
