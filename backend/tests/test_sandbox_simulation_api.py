"""
API Tests for Sandbox Simulation Endpoints.

Tests the HTTP API layer for the sandbox simulation feature:
- POST /api/channel-manager/v2/sandbox/simulate
- GET /api/channel-manager/v2/sandbox/results
- GET /api/channel-manager/v2/sandbox/results/{run_id}
- GET /api/channel-manager/v2/sandbox/timeline/{run_id}
- DELETE /api/channel-manager/v2/sandbox/cleanup/{run_id}

Verifies:
- All 5 scenarios pass for hotelrunner and exely
- Per-provider result tables with pass_rate
- Timeline events are recorded
- Simulation results are persisted and retrievable
- Specific assertions for each scenario
"""
import pytest
import requests
import os
import time

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")
if not BASE_URL:
    BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "").rstrip("/")

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


class TestSandboxSimulationAPI:
    """Test sandbox simulation API endpoints."""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=30,
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        token = data.get("access_token") or data.get("token")
        assert token, f"No token in response: {data}"
        return token

    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get auth headers."""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        }

    # ════════════════════════════════════════════════════════════════════
    #  Test: Run Full Simulation (Both Providers)
    # ════════════════════════════════════════════════════════════════════

    def test_run_simulation_both_providers(self, auth_headers):
        """Run simulation for both hotelrunner and exely providers."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/sandbox/simulate",
            headers=auth_headers,
            timeout=60,
        )
        assert response.status_code == 200, f"Simulation failed: {response.text}"
        
        data = response.json()
        
        # Verify structure
        assert "run_id" in data, "Missing run_id"
        assert "summary" in data, "Missing summary"
        assert "provider_results" in data, "Missing provider_results"
        
        # Verify summary
        summary = data["summary"]
        assert summary["total_scenarios"] == 10, f"Expected 10 scenarios, got {summary['total_scenarios']}"
        assert "passed" in summary
        assert "failed" in summary
        assert "pass_rate" in summary
        
        # Verify both providers present
        assert "hotelrunner" in data["provider_results"], "Missing hotelrunner results"
        assert "exely" in data["provider_results"], "Missing exely results"
        
        # Store run_id for subsequent tests
        self.__class__.run_id = data["run_id"]
        self.__class__.simulation_result = data
        
        print(f"Simulation run_id: {data['run_id']}")
        print(f"Summary: {summary}")

    def test_hotelrunner_all_scenarios_pass(self, auth_headers):
        """Verify all 5 scenarios pass for hotelrunner."""
        data = getattr(self.__class__, "simulation_result", None)
        if not data:
            pytest.skip("No simulation result available")
        
        hr_results = data["provider_results"]["hotelrunner"]
        
        # Verify structure
        assert hr_results["display_name"] == "HotelRunner"
        assert hr_results["total"] == 5, f"Expected 5 scenarios, got {hr_results['total']}"
        assert "pass_rate" in hr_results
        
        # Verify all scenarios present
        scenarios = {s["scenario"] for s in hr_results["scenarios"]}
        expected_scenarios = {
            "duplicate_delivery",
            "delayed_ack",
            "retry_storm",
            "stale_provider_state",
            "modify_cancel_race",
        }
        assert scenarios == expected_scenarios, f"Missing scenarios: {expected_scenarios - scenarios}"
        
        # Verify all passed
        for scenario in hr_results["scenarios"]:
            assert scenario["passed"] is True, f"HotelRunner {scenario['scenario']} failed: {scenario}"
        
        assert hr_results["passed"] == 5, f"Expected 5 passed, got {hr_results['passed']}"
        assert hr_results["failed"] == 0, f"Expected 0 failed, got {hr_results['failed']}"
        
        print(f"HotelRunner pass_rate: {hr_results['pass_rate']}")

    def test_exely_all_scenarios_pass(self, auth_headers):
        """Verify all 5 scenarios pass for exely."""
        data = getattr(self.__class__, "simulation_result", None)
        if not data:
            pytest.skip("No simulation result available")
        
        ex_results = data["provider_results"]["exely"]
        
        # Verify structure
        assert ex_results["display_name"] == "Exely"
        assert ex_results["total"] == 5, f"Expected 5 scenarios, got {ex_results['total']}"
        assert "pass_rate" in ex_results
        
        # Verify all scenarios present
        scenarios = {s["scenario"] for s in ex_results["scenarios"]}
        expected_scenarios = {
            "duplicate_delivery",
            "delayed_ack",
            "retry_storm",
            "stale_provider_state",
            "modify_cancel_race",
        }
        assert scenarios == expected_scenarios, f"Missing scenarios: {expected_scenarios - scenarios}"
        
        # Verify all passed
        for scenario in ex_results["scenarios"]:
            assert scenario["passed"] is True, f"Exely {scenario['scenario']} failed: {scenario}"
        
        assert ex_results["passed"] == 5, f"Expected 5 passed, got {ex_results['passed']}"
        assert ex_results["failed"] == 0, f"Expected 0 failed, got {ex_results['failed']}"
        
        print(f"Exely pass_rate: {ex_results['pass_rate']}")

    # ════════════════════════════════════════════════════════════════════
    #  Test: Specific Scenario Assertions
    # ════════════════════════════════════════════════════════════════════

    def test_duplicate_delivery_assertions(self, auth_headers):
        """Verify duplicate delivery assertion: zero_double_consumption."""
        data = getattr(self.__class__, "simulation_result", None)
        if not data:
            pytest.skip("No simulation result available")
        
        for provider in ["hotelrunner", "exely"]:
            scenarios = data["provider_results"][provider]["scenarios"]
            dup_scenario = next((s for s in scenarios if s["scenario"] == "duplicate_delivery"), None)
            assert dup_scenario, f"Missing duplicate_delivery for {provider}"
            
            # Verify assertions
            assertions = dup_scenario.get("assertions", {})
            assert assertions.get("zero_double_consumption") is True, \
                f"{provider} duplicate_delivery: zero_double_consumption failed"
            assert assertions.get("single_booking_created") is True, \
                f"{provider} duplicate_delivery: single_booking_created failed"
            assert assertions.get("duplicates_identified") is True, \
                f"{provider} duplicate_delivery: duplicates_identified failed"
            
            # Verify metrics
            assert dup_scenario.get("double_inventory_consumption") == 0, \
                f"{provider} had double inventory consumption"
            assert dup_scenario.get("pms_bookings_created") == 1, \
                f"{provider} created more than 1 PMS booking"
            
            print(f"{provider} duplicate_delivery: {dup_scenario['new_created']} new, "
                  f"{dup_scenario['duplicates_detected']} duplicates")

    def test_retry_storm_assertions(self, auth_headers):
        """Verify retry storm assertion: zero_oversell, idempotent_import."""
        data = getattr(self.__class__, "simulation_result", None)
        if not data:
            pytest.skip("No simulation result available")
        
        for provider in ["hotelrunner", "exely"]:
            scenarios = data["provider_results"][provider]["scenarios"]
            storm_scenario = next((s for s in scenarios if s["scenario"] == "retry_storm"), None)
            assert storm_scenario, f"Missing retry_storm for {provider}"
            
            # Verify assertions
            assertions = storm_scenario.get("assertions", {})
            assert assertions.get("zero_oversell") is True, \
                f"{provider} retry_storm: zero_oversell failed"
            assert assertions.get("idempotent_import") is True, \
                f"{provider} retry_storm: idempotent_import failed"
            
            # Verify metrics
            assert storm_scenario.get("oversell_count") == 0, \
                f"{provider} had oversell"
            
            print(f"{provider} retry_storm: {storm_scenario['total_deliveries']} deliveries, "
                  f"{storm_scenario['new_created']} new, {storm_scenario['duplicates_detected']} duplicates")

    def test_modify_cancel_race_assertions(self, auth_headers):
        """Verify modify/cancel race assertion: deterministic_sequence, final_state_cancelled."""
        data = getattr(self.__class__, "simulation_result", None)
        if not data:
            pytest.skip("No simulation result available")
        
        for provider in ["hotelrunner", "exely"]:
            scenarios = data["provider_results"][provider]["scenarios"]
            race_scenario = next((s for s in scenarios if s["scenario"] == "modify_cancel_race"), None)
            assert race_scenario, f"Missing modify_cancel_race for {provider}"
            
            # Verify assertions
            assertions = race_scenario.get("assertions", {})
            assert assertions.get("deterministic_sequence") is True, \
                f"{provider} modify_cancel_race: deterministic_sequence failed"
            assert assertions.get("final_state_cancelled") is True, \
                f"{provider} modify_cancel_race: final_state_cancelled failed"
            
            # Verify sequence
            expected_sequence = ["new", "modified", "cancelled"]
            assert race_scenario.get("sequence_results") == expected_sequence, \
                f"{provider} sequence mismatch: {race_scenario.get('sequence_results')}"
            assert race_scenario.get("final_pms_status") == "cancelled", \
                f"{provider} final status not cancelled"
            
            print(f"{provider} modify_cancel_race: sequence={race_scenario['sequence_results']}, "
                  f"final_status={race_scenario['final_pms_status']}")

    def test_stale_provider_state_assertions(self, auth_headers):
        """Verify stale provider state: drift detected and reconciliation recovers."""
        data = getattr(self.__class__, "simulation_result", None)
        if not data:
            pytest.skip("No simulation result available")
        
        for provider in ["hotelrunner", "exely"]:
            scenarios = data["provider_results"][provider]["scenarios"]
            stale_scenario = next((s for s in scenarios if s["scenario"] == "stale_provider_state"), None)
            assert stale_scenario, f"Missing stale_provider_state for {provider}"
            
            # Verify assertions
            assertions = stale_scenario.get("assertions", {})
            assert assertions.get("drift_detected") is True, \
                f"{provider} stale_provider_state: drift_detected failed"
            assert assertions.get("reconciliation_recovery") is True, \
                f"{provider} stale_provider_state: reconciliation_recovery failed"
            
            # Verify drift records
            drift_records = stale_scenario.get("drift_records", [])
            assert len(drift_records) > 0, f"{provider} no drift records"
            
            print(f"{provider} stale_provider_state: {len(drift_records)} drift records, "
                  f"recovered={stale_scenario.get('reconciliation_recovered')}")

    def test_delayed_ack_assertions(self, auth_headers):
        """Verify delayed ack: booking created, ack recovered, consistent state."""
        data = getattr(self.__class__, "simulation_result", None)
        if not data:
            pytest.skip("No simulation result available")
        
        for provider in ["hotelrunner", "exely"]:
            scenarios = data["provider_results"][provider]["scenarios"]
            ack_scenario = next((s for s in scenarios if s["scenario"] == "delayed_ack"), None)
            assert ack_scenario, f"Missing delayed_ack for {provider}"
            
            # Verify assertions
            assertions = ack_scenario.get("assertions", {})
            assert assertions.get("booking_created") is True, \
                f"{provider} delayed_ack: booking_created failed"
            assert assertions.get("ack_recovered") is True, \
                f"{provider} delayed_ack: ack_recovered failed"
            assert assertions.get("consistent_state") is True, \
                f"{provider} delayed_ack: consistent_state failed"
            
            print(f"{provider} delayed_ack: ack_flow={ack_scenario.get('ack_flow')}")

    # ════════════════════════════════════════════════════════════════════
    #  Test: Results Retrieval
    # ════════════════════════════════════════════════════════════════════

    def test_get_simulation_results_list(self, auth_headers):
        """Get list of recent simulation results."""
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/sandbox/results",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Get results failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        assert len(data) >= 1, "No simulation results found"
        
        # Verify structure of first result
        first = data[0]
        assert "run_id" in first
        assert "summary" in first
        assert "provider_results" in first
        
        print(f"Found {len(data)} simulation results")

    def test_get_specific_simulation_result(self, auth_headers):
        """Get a specific simulation result by run_id."""
        run_id = getattr(self.__class__, "run_id", None)
        if not run_id:
            pytest.skip("No run_id available")
        
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/sandbox/results/{run_id}",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Get result failed: {response.text}"
        
        data = response.json()
        assert data.get("run_id") == run_id, f"run_id mismatch"
        assert "summary" in data
        assert "provider_results" in data
        
        print(f"Retrieved result for run_id: {run_id}")

    def test_get_simulation_timeline(self, auth_headers):
        """Get event timeline for a simulation run."""
        run_id = getattr(self.__class__, "run_id", None)
        if not run_id:
            pytest.skip("No run_id available")
        
        response = requests.get(
            f"{BASE_URL}/api/channel-manager/v2/sandbox/timeline/{run_id}",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Get timeline failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        assert len(data) > 0, "No timeline events found"
        
        # Verify event types
        event_types = {e.get("event") for e in data}
        assert "scenario_start" in event_types, "Missing scenario_start events"
        assert "scenario_complete" in event_types, "Missing scenario_complete events"
        
        # Verify reservation_processed events exist
        reservation_events = [e for e in data if e.get("event") == "reservation_processed"]
        assert len(reservation_events) > 0, "No reservation_processed events"
        
        print(f"Timeline has {len(data)} events, types: {event_types}")

    # ════════════════════════════════════════════════════════════════════
    #  Test: Single Provider Simulation
    # ════════════════════════════════════════════════════════════════════

    def test_run_simulation_hotelrunner_only(self, auth_headers):
        """Run simulation for hotelrunner only."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/sandbox/simulate?providers=hotelrunner",
            headers=auth_headers,
            timeout=60,
        )
        assert response.status_code == 200, f"Simulation failed: {response.text}"
        
        data = response.json()
        assert data["summary"]["total_scenarios"] == 5, "Expected 5 scenarios for single provider"
        assert "hotelrunner" in data["provider_results"]
        assert "exely" not in data["provider_results"]
        
        hr_results = data["provider_results"]["hotelrunner"]
        assert hr_results["passed"] == 5, f"HotelRunner: {hr_results['passed']}/5 passed"
        
        print(f"HotelRunner-only simulation: {hr_results['pass_rate']}")

    def test_run_simulation_exely_only(self, auth_headers):
        """Run simulation for exely only."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/sandbox/simulate?providers=exely",
            headers=auth_headers,
            timeout=60,
        )
        assert response.status_code == 200, f"Simulation failed: {response.text}"
        
        data = response.json()
        assert data["summary"]["total_scenarios"] == 5, "Expected 5 scenarios for single provider"
        assert "exely" in data["provider_results"]
        assert "hotelrunner" not in data["provider_results"]
        
        ex_results = data["provider_results"]["exely"]
        assert ex_results["passed"] == 5, f"Exely: {ex_results['passed']}/5 passed"
        
        print(f"Exely-only simulation: {ex_results['pass_rate']}")

    # ════════════════════════════════════════════════════════════════════
    #  Test: Cleanup
    # ════════════════════════════════════════════════════════════════════

    def test_cleanup_sandbox_data(self, auth_headers):
        """Clean up sandbox data for a simulation run."""
        run_id = getattr(self.__class__, "run_id", None)
        if not run_id:
            pytest.skip("No run_id available")
        
        response = requests.delete(
            f"{BASE_URL}/api/channel-manager/v2/sandbox/cleanup/{run_id}",
            headers=auth_headers,
            timeout=30,
        )
        assert response.status_code == 200, f"Cleanup failed: {response.text}"
        
        data = response.json()
        assert data.get("status") == "cleaned"
        assert data.get("run_id") == run_id
        
        print(f"Cleaned up sandbox data for run_id: {run_id}")


class TestSandboxSimulationPassRate:
    """Test pass rate calculations."""

    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token."""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
            timeout=30,
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        return data.get("access_token") or data.get("token")

    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get auth headers."""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json",
        }

    def test_overall_pass_rate_100_percent(self, auth_headers):
        """Verify overall pass rate is 100% when all scenarios pass."""
        response = requests.post(
            f"{BASE_URL}/api/channel-manager/v2/sandbox/simulate",
            headers=auth_headers,
            timeout=60,
        )
        assert response.status_code == 200
        
        data = response.json()
        summary = data["summary"]
        
        # All scenarios should pass
        assert summary["all_passed"] is True, f"Not all passed: {summary}"
        assert summary["pass_rate"] == "100%", f"Pass rate not 100%: {summary['pass_rate']}"
        assert summary["failed"] == 0, f"Some scenarios failed: {summary['failed']}"
        
        # Verify per-provider pass rates
        for provider in ["hotelrunner", "exely"]:
            pr = data["provider_results"][provider]
            assert pr["pass_rate"] == "100%", f"{provider} pass_rate: {pr['pass_rate']}"
        
        print(f"Overall pass rate: {summary['pass_rate']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
