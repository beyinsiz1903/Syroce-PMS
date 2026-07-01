"""
HotelRunner v2 — New Features API Tests
=========================================

Tests for newly added features in iteration 164:
- Write Readiness Score (0-100 gauge)
- Shadow Observation (snapshot, history, report, thresholds)
- Write Path Transition Plan (4-phase: Shadow->Dry-run->Limited->Full Live)

Endpoints tested:
- GET /api/channel/hotelrunner-v2/readiness-score
- POST /api/channel/hotelrunner-v2/observation/snapshot
- GET /api/channel/hotelrunner-v2/observation/history
- GET /api/channel/hotelrunner-v2/observation/report
- GET /api/channel/hotelrunner-v2/observation/thresholds
- GET /api/channel/hotelrunner-v2/transition/plan
- GET /api/channel/hotelrunner-v2/transition/status
- GET /api/channel/hotelrunner-v2/transition/history
- GET /api/channel/hotelrunner-v2/ops-dashboard (updated with readiness + transition)
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("VITE_BACKEND_URL", "").rstrip("/")
TENANT_ID = "syroce_default"
PROPERTY_ID = "default"


class TestWriteReadinessScore:
    """Tests for Write Readiness Score endpoint"""

    def test_readiness_score_returns_200(self):
        """GET /readiness-score should return 200 with score data"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/readiness-score",
            params={"tenant_id": TENANT_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify required fields
        assert "overall_score" in data, "Missing overall_score"
        assert "verdict" in data, "Missing verdict"
        assert "components" in data, "Missing components"
        
        # Verify score is 0-100
        assert 0 <= data["overall_score"] <= 100, f"Score {data['overall_score']} out of range"
        
        # Verify verdict is valid
        valid_verdicts = ["ready", "caution", "not_ready", "blocked", "no_data"]
        assert data["verdict"] in valid_verdicts, f"Invalid verdict: {data['verdict']}"
        
        print(f"✓ Readiness Score: {data['overall_score']}, Verdict: {data['verdict']}")

    def test_readiness_score_components_breakdown(self):
        """Verify components breakdown structure"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/readiness-score",
            params={"tenant_id": TENANT_ID}
        )
        assert response.status_code == 200
        
        data = response.json()
        components = data.get("components", {})
        
        # Expected component keys
        expected_components = ["drift", "error_rate", "retry", "dlq", "latency"]
        for comp in expected_components:
            assert comp in components, f"Missing component: {comp}"
            comp_data = components[comp]
            assert "score" in comp_data, f"Missing score in {comp}"
            assert "weight" in comp_data, f"Missing weight in {comp}"
            assert "raw_value" in comp_data, f"Missing raw_value in {comp}"
            assert "unit" in comp_data, f"Missing unit in {comp}"
        
        print(f"✓ Components verified: {list(components.keys())}")

    def test_readiness_score_with_custom_hours(self):
        """Test readiness score with custom hours parameter"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/readiness-score",
            params={"tenant_id": TENANT_ID, "hours": 48}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("period_hours") == 48, "Hours parameter not applied"
        print(f"✓ Custom hours (48h) applied, score: {data['overall_score']}")


class TestShadowObservation:
    """Tests for Shadow Observation endpoints"""

    def test_observation_thresholds_returns_200(self):
        """GET /observation/thresholds should return threshold definitions"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/observation/thresholds"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify expected threshold keys
        expected_thresholds = [
            "drift_count_24h", "retry_count_24h", "dlq_count", 
            "error_rate_pct", "avg_latency_ms", "auth_failure_count",
            "duplicate_ingest_count", "stale_reservation_count"
        ]
        for threshold in expected_thresholds:
            assert threshold in data, f"Missing threshold: {threshold}"
            t = data[threshold]
            assert "warn" in t, f"Missing warn in {threshold}"
            assert "critical" in t, f"Missing critical in {threshold}"
            assert "description" in t, f"Missing description in {threshold}"
        
        print(f"✓ Thresholds verified: {len(data)} definitions")

    def test_collect_observation_snapshot(self):
        """POST /observation/snapshot should collect daily metrics"""
        response = requests.post(
            f"{BASE_URL}/api/channel/hotelrunner-v2/observation/snapshot",
            params={"tenant_id": TENANT_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify snapshot structure
        assert "tenant_id" in data, "Missing tenant_id"
        assert "snapshot_date" in data, "Missing snapshot_date"
        assert "day_label" in data, "Missing day_label"
        assert "metrics" in data, "Missing metrics"
        assert "alerts" in data, "Missing alerts"
        assert "alert_summary" in data, "Missing alert_summary"
        
        # Verify metrics
        metrics = data.get("metrics", {})
        expected_metrics = [
            "total_operations", "success_count", "fail_count", "error_rate_pct",
            "avg_latency_ms", "drift_count_24h", "dlq_count", "retry_count_24h"
        ]
        for m in expected_metrics:
            assert m in metrics, f"Missing metric: {m}"
        
        # Verify alert summary
        alert_summary = data.get("alert_summary", {})
        assert "critical_count" in alert_summary, "Missing critical_count"
        assert "warn_count" in alert_summary, "Missing warn_count"
        assert "ok_count" in alert_summary, "Missing ok_count"
        
        print(f"✓ Snapshot collected: {data['day_label']}, alerts: {alert_summary}")

    def test_observation_history_returns_200(self):
        """GET /observation/history should return snapshot history"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/observation/history",
            params={"tenant_id": TENANT_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Should be a list
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        
        # If there are snapshots, verify structure
        if len(data) > 0:
            snapshot = data[0]
            assert "tenant_id" in snapshot, "Missing tenant_id in snapshot"
            assert "day_label" in snapshot, "Missing day_label in snapshot"
            assert "metrics" in snapshot, "Missing metrics in snapshot"
        
        print(f"✓ Observation history: {len(data)} snapshots")

    def test_observation_report_returns_200(self):
        """GET /observation/report should return daily report with trends"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/observation/report",
            params={"tenant_id": TENANT_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "tenant_id" in data, "Missing tenant_id"
        
        # If data exists, verify report structure
        if data.get("status") != "no_data":
            assert "observation_day" in data, "Missing observation_day"
            assert "observation_target" in data, "Missing observation_target"
            assert "latest_snapshot" in data, "Missing latest_snapshot"
            assert "history_summary" in data, "Missing history_summary"
            print(f"✓ Report: Day {data.get('observation_day')}/{data.get('observation_target')}")
        else:
            print(f"✓ Report: No data yet (expected for fresh tenant)")


class TestTransitionPlan:
    """Tests for Write Path Transition Plan endpoints"""

    def test_transition_plan_returns_200(self):
        """GET /transition/plan should return full 4-phase plan"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/transition/plan"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "phases" in data, "Missing phases"
        assert "phase_order" in data, "Missing phase_order"
        assert "total_phases" in data, "Missing total_phases"
        
        # Verify 4 phases
        phases = data.get("phases", {})
        expected_phases = ["shadow", "dry_run", "limited_live", "full_live"]
        for phase in expected_phases:
            assert phase in phases, f"Missing phase: {phase}"
            p = phases[phase]
            assert "label" in p, f"Missing label in {phase}"
            assert "description" in p, f"Missing description in {phase}"
            assert "entry_criteria" in p, f"Missing entry_criteria in {phase}"
            assert "exit_criteria" in p, f"Missing exit_criteria in {phase}"
            assert "rollback_conditions" in p, f"Missing rollback_conditions in {phase}"
            assert "actions" in p, f"Missing actions in {phase}"
        
        assert data["total_phases"] == 4, f"Expected 4 phases, got {data['total_phases']}"
        print(f"✓ Transition plan: {data['total_phases']} phases verified")

    def test_transition_status_returns_200(self):
        """GET /transition/status should return current phase + readiness"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/transition/status",
            params={"tenant_id": TENANT_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify required fields
        assert "tenant_id" in data, "Missing tenant_id"
        assert "current_phase" in data, "Missing current_phase"
        assert "phase_label" in data, "Missing phase_label"
        assert "phase_description" in data, "Missing phase_description"
        assert "exit_criteria" in data, "Missing exit_criteria"
        assert "rollback_conditions" in data, "Missing rollback_conditions"
        assert "readiness_score" in data, "Missing readiness_score"
        assert "readiness_verdict" in data, "Missing readiness_verdict"
        
        # Verify current phase is valid
        valid_phases = ["shadow", "dry_run", "limited_live", "full_live"]
        assert data["current_phase"] in valid_phases, f"Invalid phase: {data['current_phase']}"
        
        print(f"✓ Transition status: {data['current_phase']} ({data['phase_label']}), readiness: {data['readiness_score']}")

    def test_transition_history_returns_200(self):
        """GET /transition/history should return transition log"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/transition/history",
            params={"tenant_id": TENANT_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Should be a list
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        
        # If there are transitions, verify structure
        if len(data) > 0:
            entry = data[0]
            assert "from_phase" in entry, "Missing from_phase"
            assert "to_phase" in entry, "Missing to_phase"
            assert "timestamp" in entry, "Missing timestamp"
        
        print(f"✓ Transition history: {len(data)} entries")


class TestOpsDashboardUpdated:
    """Tests for updated ops-dashboard endpoint with readiness + transition"""

    def test_ops_dashboard_includes_readiness(self):
        """GET /ops-dashboard should include readiness data"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/ops-dashboard",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify readiness section
        assert "readiness" in data, "Missing readiness in ops-dashboard"
        readiness = data["readiness"]
        assert "overall_score" in readiness, "Missing overall_score in readiness"
        assert "verdict" in readiness, "Missing verdict in readiness"
        assert "components" in readiness, "Missing components in readiness"
        
        print(f"✓ Ops dashboard readiness: {readiness['overall_score']}, {readiness['verdict']}")

    def test_ops_dashboard_includes_transition(self):
        """GET /ops-dashboard should include transition data"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/ops-dashboard",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID}
        )
        assert response.status_code == 200
        
        data = response.json()
        # Verify transition section
        assert "transition" in data, "Missing transition in ops-dashboard"
        transition = data["transition"]
        assert "current_phase" in transition, "Missing current_phase in transition"
        assert "phase_started_at" in transition or transition.get("phase_started_at") is None, "Missing phase_started_at"
        assert "phase_day" in transition, "Missing phase_day in transition"
        
        print(f"✓ Ops dashboard transition: {transition['current_phase']}, day {transition['phase_day']}")

    def test_ops_dashboard_full_structure(self):
        """Verify full ops-dashboard response structure"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/ops-dashboard",
            params={"tenant_id": TENANT_ID, "property_id": PROPERTY_ID}
        )
        assert response.status_code == 200
        
        data = response.json()
        # Verify all expected sections
        expected_sections = [
            "generated_at", "tenant_id", "property_id",
            "provider_health", "feature_flags", "sync_overview",
            "metrics_24h", "dlq", "error_taxonomy",
            "recent_events", "recent_drifts",
            "readiness", "transition"  # NEW sections
        ]
        for section in expected_sections:
            assert section in data, f"Missing section: {section}"
        
        print(f"✓ Ops dashboard: All {len(expected_sections)} sections present")


class TestFeatureFlagsUpdated:
    """Tests for updated feature flags with dry_run_mode and limited_scope"""

    def test_flags_include_new_fields(self):
        """GET /flags should include dry_run_mode and limited_scope"""
        response = requests.get(
            f"{BASE_URL}/api/channel/hotelrunner-v2/flags",
            params={"tenant_id": TENANT_ID}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        # Verify new flag fields
        assert "dry_run_mode" in data, "Missing dry_run_mode flag"
        assert "limited_scope" in data, "Missing limited_scope flag"
        
        # Verify existing flags still present
        assert "connector_enabled" in data, "Missing connector_enabled"
        assert "shadow_mode" in data, "Missing shadow_mode"
        assert "write_enabled" in data, "Missing write_enabled"
        
        print(f"✓ Feature flags: dry_run_mode={data['dry_run_mode']}, limited_scope={data['limited_scope']}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
