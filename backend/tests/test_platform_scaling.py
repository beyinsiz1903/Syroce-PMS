"""
Test suite for Platform Scaling enterprise modules.
Tests: Event Architecture, Multi-Property, Revenue ML, Competitive Analysis.
"""
import pytest
import httpx
import os

API_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://hotel-refactor-2.preview.emergentagent.com")

@pytest.fixture(scope="module")
def auth_headers():
    """Get auth headers for test user."""
    resp = httpx.post(f"{API_URL}/api/auth/login", json={
        "email": "demo@hotel.com", "password": "demo123"
    })
    assert resp.status_code == 200
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ═══════════════════════════════════════
# 1. REAL-TIME EVENT ARCHITECTURE
# ═══════════════════════════════════════

class TestEventArchitecture:
    def test_publish_event(self, auth_headers):
        resp = httpx.post(f"{API_URL}/api/platform/events/publish", json={
            "event_type": "rate_alert",
            "payload": {"message": "Test rate alert", "room_type": "Standard"},
        }, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "event_id" in data

    def test_publish_invalid_event_type(self, auth_headers):
        resp = httpx.post(f"{API_URL}/api/platform/events/publish", json={
            "event_type": "invalid_type_xyz",
            "payload": {},
        }, headers=auth_headers)
        assert resp.status_code == 400

    def test_event_stream(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/events/stream?limit=10", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "events" in data
        assert "count" in data

    def test_notifications(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/events/notifications?unread_only=true", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "notifications" in data
        assert "unread_count" in data

    def test_event_analytics(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/events/analytics?hours=24", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_events" in data
        assert "by_priority" in data
        assert "gateway_stats" in data

    def test_escalation_queue(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/events/escalation-queue", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert "events" in data

    def test_gateway_stats(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/events/gateway-stats", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "total_connections" in data

    def test_acknowledge_event(self, auth_headers):
        # First publish
        pub = httpx.post(f"{API_URL}/api/platform/events/publish", json={
            "event_type": "demand_spike",
            "payload": {"message": "Test acknowledge"},
            "priority": "critical",
        }, headers=auth_headers)
        event_id = pub.json()["event_id"]
        # Acknowledge
        resp = httpx.post(f"{API_URL}/api/platform/events/acknowledge", json={
            "event_id": event_id, "note": "Handled",
        }, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is True


# ═══════════════════════════════════════
# 2. MULTI-PROPERTY PLATFORM
# ═══════════════════════════════════════

class TestMultiPropertyPlatform:
    def test_portfolio_overview(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/multi-property/portfolio", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "properties" in data
        assert "total_rooms" in data
        assert "portfolio_occupancy_pct" in data

    def test_cross_property_search(self, auth_headers):
        resp = httpx.post(f"{API_URL}/api/platform/multi-property/search-availability", json={
            "check_in": "2026-04-01", "check_out": "2026-04-03", "guests": 2,
        }, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "properties" in data
        assert "total_available" in data

    def test_portfolio_revenue(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/multi-property/revenue?days=30", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "properties" in data
        assert "total_portfolio_revenue" in data

    def test_global_alerts(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/multi-property/alerts", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        assert "count" in data

    def test_multi_property_dashboard(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/multi-property/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "portfolio" in data
        assert "revenue" in data
        assert "alerts" in data


# ═══════════════════════════════════════
# 3. REVENUE ML
# ═══════════════════════════════════════

class TestRevenueML:
    def test_demand_forecast(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/ml/demand-forecast?days=7", headers=auth_headers, timeout=30)
        assert resp.status_code == 200
        data = resp.json()
        assert "forecast" in data
        assert len(data["forecast"]) == 7
        assert "model" in data

    def test_rate_elasticity(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/ml/rate-elasticity", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "elasticity_coefficient" in data
        assert "interpretation" in data

    def test_optimal_prices(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/ml/optimal-prices", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "price_points" in data

    def test_booking_probability(self, auth_headers):
        resp = httpx.post(f"{API_URL}/api/platform/ml/booking-probability", json={
            "check_in": "2026-04-15", "check_out": "2026-04-17",
            "source": "direct", "room_type": "Standard",
        }, headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "conversion_probability" in data
        assert "cancellation_risk" in data

    def test_conversion_rates(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/ml/conversion-rates", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "by_source" in data

    def test_at_risk_bookings(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/ml/at-risk-bookings?min_risk=0.3", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "at_risk_count" in data
        assert "total_at_risk_revenue" in data

    def test_ml_dashboard(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/ml/dashboard", headers=auth_headers, timeout=60)
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert "demand_forecast" in data
        assert "price_optimization" in data
        assert "conversion_rates" in data
        assert "cancellation_risk" in data


# ═══════════════════════════════════════
# 4. COMPETITIVE SET ANALYSIS
# ═══════════════════════════════════════

class TestCompetitiveAnalysis:
    def test_add_competitor(self, auth_headers):
        resp = httpx.post(f"{API_URL}/api/platform/competitive/add-competitor", json={
            "name": "Test Rakip Hotel", "star_rating": 4,
        }, headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_get_competitors(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/competitive/competitors", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "competitors" in data
        assert "count" in data

    def test_record_competitor_rate(self, auth_headers):
        # First get a competitor
        comps = httpx.get(f"{API_URL}/api/platform/competitive/competitors", headers=auth_headers).json()
        if comps["count"] > 0:
            comp_id = comps["competitors"][0]["id"]
            resp = httpx.post(f"{API_URL}/api/platform/competitive/record-rate", json={
                "competitor_id": comp_id, "room_type": "Standard",
                "rate": 250.0, "date": "2026-04-01",
            }, headers=auth_headers)
            assert resp.status_code == 200
            assert resp.json()["success"] is True

    def test_get_competitor_rates(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/competitive/rates", headers=auth_headers)
        assert resp.status_code == 200
        assert "rates" in resp.json()

    def test_market_position(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/competitive/market-position?room_type=Standard", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "our_rate" in data

    def test_rate_parity(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/competitive/rate-parity", headers=auth_headers)
        assert resp.status_code == 200
        assert "room_types" in resp.json()

    def test_adr_suggestions(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/competitive/adr-suggestions", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "suggestions" in data

    def test_competitive_dashboard(self, auth_headers):
        resp = httpx.get(f"{API_URL}/api/platform/competitive/dashboard", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert "comp_set" in data
        assert "rate_parity" in data
        assert "adr_suggestions" in data
