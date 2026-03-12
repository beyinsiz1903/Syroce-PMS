"""
Test suite for Data Intelligence module.
Tests: Revenue ML Pipeline, Operational AI, Guest Intelligence.
"""
import pytest
import httpx
import os

API_URL = os.environ.get("API_URL", "https://hotel-hardening.preview.emergentagent.com")
EMAIL = "demo@hotel.com"
PASSWORD = "demo123"


@pytest.fixture(scope="module")
def auth_headers():
    """Get auth token for API calls."""
    resp = httpx.post(f"{API_URL}/api/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=30)
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════════════════════════
# REVENUE ML PIPELINE TESTS
# ═══════════════════════════════════════════════════════════

class TestRevenuePipeline:
    def test_forecast_dashboard(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/data-intelligence/revenue/forecast-dashboard",
                         headers=auth_headers, timeout=60)
        assert resp.status_code == 200
        data = resp.json()
        assert "demand_forecast" in data
        assert "price_optimization" in data
        assert "cancellation_risk" in data
        assert "autopricing" in data
        assert "ml_recommendations" in data

    def test_forecast_has_14_days(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/data-intelligence/revenue/forecast-dashboard",
                         headers=auth_headers, timeout=60)
        data = resp.json()
        forecast = data.get("demand_forecast", {}).get("forecast", [])
        assert len(forecast) == 14

    def test_run_pipeline(self, auth_headers):
        resp = httpx.post(f"{API_URL}/api/data-intelligence/revenue/run-pipeline",
                          headers=auth_headers, json={}, timeout=120)
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert "recommendations" in data
        assert "signals" in data
        assert data["pipeline"] == "revenue_ml"

    def test_pipeline_recommendation_fields(self, auth_headers):
        resp = httpx.post(f"{API_URL}/api/data-intelligence/revenue/run-pipeline",
                          headers=auth_headers, json={}, timeout=120)
        data = resp.json()
        recs = data.get("recommendations", [])
        if len(recs) > 0:
            rec = recs[0]
            assert "confidence_score" in rec
            assert "confidence_band" in rec
            assert rec["confidence_band"] in ("high", "medium", "low")
            assert "auto_eligible" in rec
            assert "requires_human_approval" in rec
            assert "recommendation_reasons" in rec
            assert "explainability" in rec

    def test_pipeline_explainability(self, auth_headers):
        resp = httpx.post(f"{API_URL}/api/data-intelligence/revenue/run-pipeline",
                          headers=auth_headers, json={}, timeout=120)
        data = resp.json()
        recs = data.get("recommendations", [])
        if len(recs) > 0:
            explain = recs[0]["explainability"]
            assert "demand_signal" in explain
            assert "pace_signal" in explain
            assert "cancellation_risk" in explain
            assert "price_sensitivity" in explain
            assert "recommendation_reason" in explain

    def test_pipeline_signals(self, auth_headers):
        resp = httpx.post(f"{API_URL}/api/data-intelligence/revenue/run-pipeline",
                          headers=auth_headers, json={}, timeout=120)
        signals = resp.json().get("signals", {})
        assert "demand_summary" in signals
        assert "elasticity_summary" in signals
        assert "cancellation_risk" in signals
        assert "conversion_rates" in signals

    def test_confidence_threshold_behavior(self, auth_headers):
        resp = httpx.post(f"{API_URL}/api/data-intelligence/revenue/run-pipeline",
                          headers=auth_headers, json={}, timeout=120)
        recs = resp.json().get("recommendations", [])
        for rec in recs:
            score = rec.get("confidence_score", 0)
            assert 0.1 <= score <= 0.95
            if score < 0.6:
                assert rec.get("requires_human_approval") is True

    def test_get_recommendations(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/data-intelligence/revenue/recommendations",
                         headers=auth_headers, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert "pending" in data
        assert "history" in data


# ═══════════════════════════════════════════════════════════
# OPERATIONAL AI TESTS
# ═══════════════════════════════════════════════════════════

class TestOperationalAI:
    def test_operations_dashboard(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/data-intelligence/operations/dashboard",
                         headers=auth_headers, timeout=60)
        assert resp.status_code == 200
        data = resp.json()
        assert "check_in_load" in data
        assert "housekeeping_workload" in data
        assert "room_readiness" in data
        assert "maintenance_risk" in data

    def test_checkin_load_structure(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/data-intelligence/operations/dashboard",
                         headers=auth_headers, timeout=60)
        checkin = resp.json().get("check_in_load", {})
        assert "total_expected_arrivals" in checkin
        assert "peak_hour" in checkin
        assert "arrival_pressure_score" in checkin
        assert "hourly_forecast" in checkin
        assert "staffing_recommendation" in checkin

    def test_housekeeping_workload_structure(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/data-intelligence/operations/dashboard",
                         headers=auth_headers, timeout=60)
        hk = resp.json().get("housekeeping_workload", {})
        assert "workload" in hk
        assert "staffing_recommendation" in hk
        wl = hk.get("workload", {})
        assert "departures" in wl
        assert "stayovers" in wl
        assert "arrivals" in wl
        assert "total_rooms_to_clean" in wl

    def test_room_readiness_structure(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/data-intelligence/operations/room-readiness",
                         headers=auth_headers, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_rooms_pending" in data
        assert "predictions" in data

    def test_maintenance_risk_structure(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/data-intelligence/operations/maintenance-risk",
                         headers=auth_headers, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_rooms_analyzed" in data
        assert "at_risk_rooms" in data
        assert "risk_items" in data

    def test_maintenance_risk_scoring_range(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/data-intelligence/operations/maintenance-risk",
                         headers=auth_headers, timeout=30)
        items = resp.json().get("risk_items", [])
        for item in items:
            assert 0 <= item["risk_score"] <= 1
            assert item["risk_level"] in ("high", "medium", "low")

    def test_staffing_recommendations(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/data-intelligence/operations/staffing",
                         headers=auth_headers, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert "front_desk" in data
        assert "housekeeping" in data
        assert "combined_pressure" in data

    def test_workload_heatmap(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/data-intelligence/operations/workload-heatmap",
                         headers=auth_headers, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert "housekeeping_floors" in data
        assert "checkin_hourly" in data


# ═══════════════════════════════════════════════════════════
# GUEST INTELLIGENCE TESTS
# ═══════════════════════════════════════════════════════════

class TestGuestIntelligence:
    def test_guest_dashboard(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/data-intelligence/guests/dashboard?limit=10",
                         headers=auth_headers, timeout=120)
        assert resp.status_code == 200
        data = resp.json()
        assert "guests_analyzed" in data
        assert "value_distribution" in data
        assert "segment_distribution" in data
        assert "churn_risk_summary" in data
        assert "top_value_guests" in data
        assert "high_churn_guests" in data
        assert "upsell_opportunities" in data

    def test_value_distribution_tiers(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/data-intelligence/guests/dashboard?limit=10",
                         headers=auth_headers, timeout=120)
        dist = resp.json().get("value_distribution", {})
        for tier in ("platinum", "gold", "silver", "bronze"):
            assert tier in dist

    def test_churn_risk_labels(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/data-intelligence/guests/dashboard?limit=10",
                         headers=auth_headers, timeout=120)
        summary = resp.json().get("churn_risk_summary", {})
        for label in ("high", "medium", "low"):
            assert label in summary

    def test_guest_segments(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/data-intelligence/guests/segments",
                         headers=auth_headers, timeout=60)
        assert resp.status_code == 200
        data = resp.json()
        assert "segment_distribution" in data
        assert "value_distribution" in data

    def test_churn_summary(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/data-intelligence/guests/churn-summary",
                         headers=auth_headers, timeout=60)
        assert resp.status_code == 200
        data = resp.json()
        assert "churn_risk_summary" in data
        assert "high_churn_guests" in data

    def test_upsell_opportunities(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/data-intelligence/guests/upsell-opportunities",
                         headers=auth_headers, timeout=60)
        assert resp.status_code == 200
        data = resp.json()
        assert "opportunities" in data
        assert "total_potential" in data


# ═══════════════════════════════════════════════════════════
# TENANT ISOLATION TESTS
# ═══════════════════════════════════════════════════════════

class TestTenantIsolation:
    def test_unauthorized_access(self):
        resp = httpx.get(f"{API_URL}/api/data-intelligence/revenue/forecast-dashboard", timeout=10)
        assert resp.status_code in (401, 403)

    def test_invalid_token(self):
        headers = {"Authorization": "Bearer invalid_token"}
        resp = httpx.get(f"{API_URL}/api/data-intelligence/operations/dashboard",
                         headers=headers, timeout=10)
        assert resp.status_code in (401, 403)


# ═══════════════════════════════════════════════════════════
# EMPTY DATASET FALLBACK TESTS
# ═══════════════════════════════════════════════════════════

class TestEmptyFallback:
    def test_pipeline_with_no_room_type(self, auth_headers):
        resp = httpx.post(f"{API_URL}/api/data-intelligence/revenue/run-pipeline",
                          headers=auth_headers, json={"room_type": "NonExistentType"},
                          timeout=60)
        assert resp.status_code == 200
        data = resp.json()
        # Should return empty recommendations for non-existent type
        assert "recommendations" in data


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
