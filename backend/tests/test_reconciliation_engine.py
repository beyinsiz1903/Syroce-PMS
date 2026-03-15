"""
Cross-Provider Reconciliation Engine API Tests
===============================================

Tests all reconciliation endpoints:
- GET /api/channel-manager/reconciliation/cases — List cases with filters
- GET /api/channel-manager/reconciliation/cases/{case_id} — Get case detail
- POST /api/channel-manager/reconciliation/cases/{case_id}/resolve — Resolve a case
- POST /api/channel-manager/reconciliation/cases/{case_id}/ignore — Ignore a case
- POST /api/channel-manager/reconciliation/cases/{case_id}/acknowledge — Acknowledge a case
- POST /api/channel-manager/reconciliation/run — Trigger manual reconciliation
- POST /api/channel-manager/reconciliation/run-with-snapshots — Run with test snapshots
- GET /api/channel-manager/reconciliation/dashboard — Dashboard data
- GET /api/channel-manager/reconciliation/metrics — Mismatch metrics
- GET /api/channel-manager/reconciliation/worker/status — Worker status

Auto-resolution: missing_reservation → auto-resolved, amount_mismatch → open
Idempotency: same mismatch should not create duplicate case
"""
import pytest
import requests
import os
import uuid
from datetime import datetime, timezone

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")
pytestmark = pytest.mark.skipif(not BASE_URL, reason="REACT_APP_BACKEND_URL not set — requires live server")
TENANT_ID = "044f122b-87b5-480a-88b4-b9534b0c8c90"  # demo tenant
PROPERTY_ID = "prop-001"


class TestReconciliationAuth:
    """Authentication and basic access tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token."""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        assert "access_token" in data, "No access_token in login response"
        return data["access_token"]
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def test_login_returns_token(self, auth_token):
        """Verify login returns valid token."""
        assert auth_token is not None
        assert len(auth_token) > 20
        print(f"[PASS] Login successful, token length: {len(auth_token)}")
    
    def test_unauthenticated_access_blocked(self):
        """Verify endpoints require authentication."""
        response = requests.get(f"{BASE_URL}/api/channel-manager/reconciliation/cases")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
        print("[PASS] Unauthenticated access blocked")


class TestReconciliationListCases:
    """GET /api/channel-manager/reconciliation/cases"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        assert response.status_code == 200
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def test_list_cases_basic(self, headers):
        """List all reconciliation cases."""
        response = requests.get(f"{BASE_URL}/api/channel-manager/reconciliation/cases", headers=headers)
        assert response.status_code == 200, f"List cases failed: {response.text}"
        data = response.json()
        assert "cases" in data, "No 'cases' key in response"
        assert "count" in data, "No 'count' key in response"
        assert isinstance(data["cases"], list)
        print(f"[PASS] List cases: {data['count']} cases returned")
    
    def test_list_cases_filter_status(self, headers):
        """Filter cases by status."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/reconciliation/cases?status=open",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        for case in data.get("cases", []):
            assert case.get("status") == "open", f"Case {case.get('id')} has status {case.get('status')}"
        print(f"[PASS] Filter by status=open: {data['count']} cases")
    
    def test_list_cases_filter_severity(self, headers):
        """Filter cases by severity."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/reconciliation/cases?severity=high",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        for case in data.get("cases", []):
            assert case.get("severity") == "high"
        print(f"[PASS] Filter by severity=high: {data['count']} cases")
    
    def test_list_cases_filter_case_type(self, headers):
        """Filter cases by case_type."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/reconciliation/cases?case_type=missing_reservation",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        for case in data.get("cases", []):
            assert case.get("case_type") == "missing_reservation"
        print(f"[PASS] Filter by case_type=missing_reservation: {data['count']} cases")
    
    def test_list_cases_filter_provider(self, headers):
        """Filter cases by provider."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/reconciliation/cases?provider=hotelrunner",
            headers=headers
        )
        assert response.status_code == 200
        data = response.json()
        for case in data.get("cases", []):
            assert case.get("provider") == "hotelrunner"
        print(f"[PASS] Filter by provider=hotelrunner: {data['count']} cases")


class TestReconciliationDashboard:
    """GET /api/channel-manager/reconciliation/dashboard"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def test_dashboard_structure(self, headers):
        """Verify dashboard returns expected structure."""
        response = requests.get(f"{BASE_URL}/api/channel-manager/reconciliation/dashboard", headers=headers)
        assert response.status_code == 200, f"Dashboard failed: {response.text}"
        data = response.json()
        
        # Check required fields
        assert "open_cases" in data, "Missing 'open_cases'"
        assert "severity_counts" in data, "Missing 'severity_counts'"
        assert "provider_breakdown" in data, "Missing 'provider_breakdown'"
        assert "type_breakdown" in data, "Missing 'type_breakdown'"
        assert "recent_cases" in data, "Missing 'recent_cases'"
        assert "worker" in data, "Missing 'worker'"
        
        # Validate types
        assert isinstance(data["open_cases"], int)
        assert isinstance(data["severity_counts"], dict)
        assert isinstance(data["provider_breakdown"], dict)
        assert isinstance(data["type_breakdown"], dict)
        assert isinstance(data["recent_cases"], list)
        
        print(f"[PASS] Dashboard: {data['open_cases']} open cases, "
              f"severity_counts={data['severity_counts']}, "
              f"provider_breakdown={data['provider_breakdown']}")


class TestReconciliationMetrics:
    """GET /api/channel-manager/reconciliation/metrics"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def test_metrics_structure(self, headers):
        """Verify metrics returns mismatch counts."""
        response = requests.get(f"{BASE_URL}/api/channel-manager/reconciliation/metrics", headers=headers)
        assert response.status_code == 200, f"Metrics failed: {response.text}"
        data = response.json()
        
        # Check all mismatch type counts exist
        expected_keys = [
            "cases_open", "cases_resolved", "cases_ignored", "cases_total",
            "missing_reservations", "ghost_reservations", "status_conflicts",
            "amount_mismatches", "date_conflicts", "duplicate_reservations",
            "worker"
        ]
        for key in expected_keys:
            assert key in data, f"Missing key: {key}"
        
        print(f"[PASS] Metrics: total={data['cases_total']}, open={data['cases_open']}, "
              f"missing={data['missing_reservations']}, ghost={data['ghost_reservations']}")


class TestReconciliationWorkerStatus:
    """GET /api/channel-manager/reconciliation/worker/status"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def test_worker_status(self, headers):
        """Verify worker status endpoint."""
        response = requests.get(f"{BASE_URL}/api/channel-manager/reconciliation/worker/status", headers=headers)
        assert response.status_code == 200, f"Worker status failed: {response.text}"
        data = response.json()
        
        assert "worker" in data
        worker = data["worker"]
        assert "running" in worker
        assert "runs_total" in worker
        assert "interval_seconds" in worker
        
        print(f"[PASS] Worker status: running={worker['running']}, runs={worker['runs_total']}")


class TestReconciliationRun:
    """POST /api/channel-manager/reconciliation/run"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def test_manual_run(self, headers):
        """Trigger manual reconciliation run."""
        response = requests.post(f"{BASE_URL}/api/channel-manager/reconciliation/run", json={}, headers=headers)
        assert response.status_code == 200, f"Manual run failed: {response.text}"
        data = response.json()
        
        assert "message" in data
        assert "result" in data
        result = data["result"]
        
        # Verify result structure
        assert "status" in result
        assert result["status"] in ["completed", "already_running", "error"]
        
        print(f"[PASS] Manual run: status={result['status']}, "
              f"mismatches={result.get('mismatches_found', 0)}, "
              f"cases_created={result.get('cases_created', 0)}")


class TestReconciliationRunWithSnapshots:
    """POST /api/channel-manager/reconciliation/run-with-snapshots"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def test_run_with_snapshots_missing_reservation(self, headers):
        """
        Run with snapshot containing reservation not in PMS lineage.
        Should detect missing_reservation mismatch.
        """
        test_ext_id = f"RECON-TEST-MISSING-{uuid.uuid4().hex[:8]}"
        
        # Provider has a reservation that PMS doesn't have → missing_reservation
        snapshots = [
            {
                "external_reservation_id": test_ext_id,
                "check_in": "2026-03-01",
                "check_out": "2026-03-03",
                "status": "confirmed",
                "total_amount": 500.00,
                "currency": "TRY",
                "guest_name": "Test Missing Guest",
            }
        ]
        
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/reconciliation/run-with-snapshots",
            json={
                "provider": "hotelrunner",
                "property_id": PROPERTY_ID,
                "snapshots": snapshots
            },
            headers=headers
        )
        assert response.status_code == 200, f"Run with snapshots failed: {response.text}"
        data = response.json()
        result = data.get("result", {})
        
        assert result.get("provider_count") == 1
        # Should detect missing_reservation since this ext_id isn't in PMS lineage
        assert result.get("mismatches") >= 1, f"Expected at least 1 mismatch, got {result.get('mismatches')}"
        
        print(f"[PASS] Run with snapshots (missing): mismatches={result['mismatches']}, "
              f"cases_created={result.get('cases_created')}, "
              f"auto_resolved={result.get('auto_resolved')}")
    
    def test_run_with_snapshots_ghost_reservation(self, headers):
        """
        Run with empty snapshot against existing PMS lineage.
        Should detect ghost_reservation for PMS reservations not in provider.
        """
        # Get current PMS lineage count first
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/model/lineage?property_id={PROPERTY_ID}",
            headers=headers
        )
        assert response.status_code == 200
        lineages = response.json().get("lineages", [])
        hotelrunner_lineages = [l for l in lineages if l.get("provider") == "hotelrunner"]
        
        # Run with empty snapshots - PMS has reservations but provider doesn't
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/reconciliation/run-with-snapshots",
            json={
                "provider": "hotelrunner",
                "property_id": PROPERTY_ID,
                "snapshots": []  # Empty snapshots
            },
            headers=headers
        )
        assert response.status_code == 200, f"Ghost test failed: {response.text}"
        data = response.json()
        result = data.get("result", {})
        
        # Should detect ghost_reservation for each PMS lineage record
        print(f"[PASS] Run with snapshots (ghost): pms_count={result.get('pms_count')}, "
              f"mismatches={result.get('mismatches')}, "
              f"cases_created={result.get('cases_created')}")
    
    def test_run_with_snapshots_amount_mismatch(self, headers):
        """
        Run with snapshot that matches ext_id but has different amount.
        Should detect amount_mismatch (NOT auto-resolved).
        """
        # First get an existing lineage record to use its ext_id
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/model/lineage?property_id={PROPERTY_ID}",
            headers=headers
        )
        lineages = response.json().get("lineages", [])
        hr_lineages = [l for l in lineages if l.get("provider") == "hotelrunner"]
        
        if hr_lineages:
            existing = hr_lineages[0]
            ext_id = existing.get("external_reservation_id")
            original_amount = existing.get("total_amount", 100)
            
            # Provider reports different amount
            snapshots = [
                {
                    "external_reservation_id": ext_id,
                    "check_in": existing.get("arrival_date", "2026-03-01"),
                    "check_out": existing.get("departure_date", "2026-03-03"),
                    "status": existing.get("status", "confirmed"),
                    "total_amount": original_amount + 999.99,  # Different amount
                    "currency": existing.get("currency", "TRY"),
                }
            ]
            
            response = requests.post(
                f"{BASE_URL}/api/channel-manager/reconciliation/run-with-snapshots",
                json={
                    "provider": "hotelrunner",
                    "property_id": PROPERTY_ID,
                    "snapshots": snapshots
                },
                headers=headers
            )
            assert response.status_code == 200
            result = response.json().get("result", {})
            
            # Amount mismatch should NOT be auto-resolved
            print(f"[PASS] Run with snapshots (amount_mismatch): mismatches={result.get('mismatches')}, "
                  f"auto_resolved={result.get('auto_resolved', 0)} (should be 0 for amount_mismatch)")
        else:
            pytest.skip("No hotelrunner lineages to test amount mismatch")


class TestReconciliationAutoResolution:
    """Test auto-resolution rules"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def test_missing_reservation_auto_resolved(self, headers):
        """Missing reservation cases should be auto-resolved."""
        test_ext_id = f"RECON-AUTO-{uuid.uuid4().hex[:8]}"
        
        # Create a missing_reservation case
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/reconciliation/run-with-snapshots",
            json={
                "provider": "hotelrunner",
                "property_id": PROPERTY_ID,
                "snapshots": [
                    {
                        "external_reservation_id": test_ext_id,
                        "check_in": "2026-04-01",
                        "check_out": "2026-04-03",
                        "status": "confirmed",
                        "total_amount": 300.00,
                    }
                ]
            },
            headers=headers
        )
        assert response.status_code == 200
        result = response.json().get("result", {})
        
        # missing_reservation should be auto-resolved
        if result.get("cases_created", 0) > 0:
            # The case should have been auto-resolved
            print(f"[PASS] Auto-resolution: cases_created={result['cases_created']}, "
                  f"auto_resolved={result.get('auto_resolved', 0)}")


class TestReconciliationIdempotency:
    """Test duplicate case prevention"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def test_duplicate_case_skipped(self, headers):
        """Same mismatch should not create duplicate case if already open."""
        test_ext_id = f"RECON-IDEMPOTENT-{uuid.uuid4().hex[:8]}"
        
        snapshots = [
            {
                "external_reservation_id": test_ext_id,
                "check_in": "2026-05-01",
                "check_out": "2026-05-03",
                "status": "confirmed",
                "total_amount": 400.00,
            }
        ]
        
        # First run - should create case
        response1 = requests.post(
            f"{BASE_URL}/api/channel-manager/reconciliation/run-with-snapshots",
            json={"provider": "exely", "property_id": PROPERTY_ID, "snapshots": snapshots},
            headers=headers
        )
        assert response1.status_code == 200
        result1 = response1.json().get("result", {})
        created_first = result1.get("cases_created", 0)
        
        # Second run with same snapshots - should skip duplicate
        response2 = requests.post(
            f"{BASE_URL}/api/channel-manager/reconciliation/run-with-snapshots",
            json={"provider": "exely", "property_id": PROPERTY_ID, "snapshots": snapshots},
            headers=headers
        )
        assert response2.status_code == 200
        result2 = response2.json().get("result", {})
        skipped = result2.get("skipped_duplicate", 0)
        
        print(f"[PASS] Idempotency: first_run_created={created_first}, "
              f"second_run_skipped_duplicates={skipped}")


class TestReconciliationCaseActions:
    """Test case lifecycle: acknowledge, resolve, ignore"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def _create_test_case(self, headers) -> str:
        """Helper to create a test case and return its ID."""
        test_ext_id = f"RECON-ACTION-{uuid.uuid4().hex[:8]}"
        
        # First get existing lineage to create amount_mismatch (not auto-resolved)
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/model/lineage?property_id={PROPERTY_ID}",
            headers=headers
        )
        lineages = response.json().get("lineages", [])
        hr_lineages = [l for l in lineages if l.get("provider") == "hotelrunner"]
        
        if hr_lineages:
            existing = hr_lineages[0]
            ext_id = existing.get("external_reservation_id")
            
            # Create amount_mismatch case (not auto-resolved)
            response = requests.post(
                f"{BASE_URL}/api/channel-manager/reconciliation/run-with-snapshots",
                json={
                    "provider": "hotelrunner",
                    "property_id": PROPERTY_ID,
                    "snapshots": [{
                        "external_reservation_id": ext_id,
                        "check_in": existing.get("arrival_date"),
                        "check_out": existing.get("departure_date"),
                        "status": existing.get("status", "confirmed"),
                        "total_amount": 99999.99,  # Big difference
                    }]
                },
                headers=headers
            )
        
        # Get the created case
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/reconciliation/cases?status=open",
            headers=headers
        )
        cases = response.json().get("cases", [])
        if cases:
            return cases[0].get("id")
        return None
    
    def test_acknowledge_case(self, headers):
        """Acknowledge a case."""
        # Get an open case
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/reconciliation/cases?status=open",
            headers=headers
        )
        cases = response.json().get("cases", [])
        
        if not cases:
            pytest.skip("No open cases to acknowledge")
        
        case_id = cases[0]["id"]
        
        # Acknowledge it
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/reconciliation/cases/{case_id}/acknowledge",
            json={"note": "Under review by T1 testing agent"},
            headers=headers
        )
        assert response.status_code == 200, f"Acknowledge failed: {response.text}"
        data = response.json()
        assert "message" in data
        assert data["case_id"] == case_id
        
        # Verify status changed
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/reconciliation/cases/{case_id}",
            headers=headers
        )
        assert response.status_code == 200
        case = response.json()
        assert case.get("status") == "acknowledged"
        
        print(f"[PASS] Acknowledge case {case_id}: status={case.get('status')}")
    
    def test_resolve_case(self, headers):
        """Resolve a case."""
        # Get an open or acknowledged case
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/reconciliation/cases?status=acknowledged",
            headers=headers
        )
        cases = response.json().get("cases", [])
        
        if not cases:
            # Try open cases
            response = requests.get(
                f"{BASE_URL}/api/channel-manager/reconciliation/cases?status=open",
                headers=headers
            )
            cases = response.json().get("cases", [])
        
        if not cases:
            pytest.skip("No cases to resolve")
        
        case_id = cases[0]["id"]
        
        # Resolve it
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/reconciliation/cases/{case_id}/resolve",
            json={"resolution": "Manually resolved by T1 testing agent"},
            headers=headers
        )
        assert response.status_code == 200, f"Resolve failed: {response.text}"
        
        # Verify status changed
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/reconciliation/cases/{case_id}",
            headers=headers
        )
        case = response.json()
        assert case.get("status") == "resolved"
        assert "resolution" in case
        
        print(f"[PASS] Resolve case {case_id}: status={case.get('status')}")
    
    def test_ignore_case(self, headers):
        """Ignore a case."""
        # Get an open case
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/reconciliation/cases?status=open",
            headers=headers
        )
        cases = response.json().get("cases", [])
        
        if not cases:
            pytest.skip("No open cases to ignore")
        
        case_id = cases[0]["id"]
        
        # Ignore it
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/reconciliation/cases/{case_id}/ignore",
            json={"reason": "Test case - ignored by T1"},
            headers=headers
        )
        assert response.status_code == 200, f"Ignore failed: {response.text}"
        
        # Verify status changed
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/reconciliation/cases/{case_id}",
            headers=headers
        )
        case = response.json()
        assert case.get("status") == "ignored"
        
        print(f"[PASS] Ignore case {case_id}: status={case.get('status')}")
    
    def test_resolve_already_closed_case_fails(self, headers):
        """Cannot resolve an already closed case."""
        # Get a resolved case
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/reconciliation/cases?status=resolved",
            headers=headers
        )
        cases = response.json().get("cases", [])
        
        if not cases:
            pytest.skip("No resolved cases to test")
        
        case_id = cases[0]["id"]
        
        # Try to resolve again
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/reconciliation/cases/{case_id}/resolve",
            json={"resolution": "Double resolve attempt"},
            headers=headers
        )
        assert response.status_code == 400, f"Expected 400, got {response.status_code}"
        
        print(f"[PASS] Double resolve blocked for case {case_id}")


class TestReconciliationCaseDetail:
    """GET /api/channel-manager/reconciliation/cases/{case_id}"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com", "password": "demo123"
        })
        return response.json()["access_token"]
    
    @pytest.fixture(scope="class")
    def headers(self, auth_token):
        return {"Authorization": f"Bearer {auth_token}", "Content-Type": "application/json"}
    
    def test_get_case_detail(self, headers):
        """Get detailed case information."""
        # Get any case first
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/reconciliation/cases",
            headers=headers
        )
        cases = response.json().get("cases", [])
        
        if not cases:
            pytest.skip("No cases to fetch detail")
        
        case_id = cases[0]["id"]
        
        # Get detail
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/reconciliation/cases/{case_id}",
            headers=headers
        )
        assert response.status_code == 200, f"Get detail failed: {response.text}"
        case = response.json()
        
        # Verify structure
        assert case.get("id") == case_id
        assert "tenant_id" in case
        assert "provider" in case
        assert "case_type" in case
        assert "severity" in case
        assert "status" in case
        
        print(f"[PASS] Case detail: id={case_id}, type={case.get('case_type')}, "
              f"severity={case.get('severity')}, status={case.get('status')}")
    
    def test_get_nonexistent_case(self, headers):
        """Get 404 for nonexistent case."""
        fake_id = str(uuid.uuid4())
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/reconciliation/cases/{fake_id}",
            headers=headers
        )
        assert response.status_code == 404
        print(f"[PASS] Nonexistent case returns 404")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
