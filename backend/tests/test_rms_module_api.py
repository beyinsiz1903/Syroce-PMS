"""
RMS Module API Tests - New Internal-Data-Driven RMS Implementation
Tests: Dashboard KPIs, Yield Rules CRUD, Seasonal Calendar CRUD, Generate Pricing
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE_URL:
    BASE_URL = "https://pms-channel-ui-fix.preview.emergentagent.com"

# Test credentials
TEST_EMAIL = "demo@hotel.com"
TEST_PASSWORD = "demo123"


class TestRMSAuth:
    """Authentication for RMS tests"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "email": TEST_EMAIL,
            "password": TEST_PASSWORD
        })
        assert response.status_code == 200, f"Login failed: {response.text}"
        data = response.json()
        # Token field is 'access_token' not 'token'
        token = data.get("access_token") or data.get("token")
        assert token, f"No token in response: {data}"
        return token
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Headers with auth token"""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }


class TestRMSDashboardKPIs(TestRMSAuth):
    """Test /api/rms/dashboard-kpis endpoint"""
    
    def test_dashboard_kpis_default_period(self, auth_headers):
        """Test dashboard KPIs with default 30-day period"""
        response = requests.get(f"{BASE_URL}/api/rms/dashboard-kpis", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "kpis" in data, "Missing 'kpis' in response"
        
        kpis = data["kpis"]
        # Verify all required KPI fields
        required_fields = ["occupancy", "adr", "revpar", "cancel_rate", "pickup_rate", 
                          "total_revenue", "total_bookings", "pickup_count_7d"]
        for field in required_fields:
            assert field in kpis, f"Missing KPI field: {field}"
        
        # Verify data types
        assert isinstance(kpis["occupancy"], (int, float))
        assert isinstance(kpis["adr"], (int, float))
        assert isinstance(kpis["revpar"], (int, float))
        print(f"KPIs: Occupancy={kpis['occupancy']}%, ADR={kpis['adr']} TRY, RevPAR={kpis['revpar']} TRY")
    
    def test_dashboard_kpis_7_day_period(self, auth_headers):
        """Test dashboard KPIs with 7-day period"""
        response = requests.get(f"{BASE_URL}/api/rms/dashboard-kpis?period=7", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("period_days") == 7
        assert "daily_trend" in data
        print(f"7-day period: {len(data.get('daily_trend', []))} trend data points")
    
    def test_dashboard_kpis_90_day_period(self, auth_headers):
        """Test dashboard KPIs with 90-day period"""
        response = requests.get(f"{BASE_URL}/api/rms/dashboard-kpis?period=90", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("period_days") == 90
        print(f"90-day period: Total revenue={data['kpis'].get('total_revenue')} TRY")
    
    def test_dashboard_channels_data(self, auth_headers):
        """Test channel distribution data in dashboard"""
        response = requests.get(f"{BASE_URL}/api/rms/dashboard-kpis", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "channels" in data, "Missing 'channels' in response"
        
        channels = data["channels"]
        if len(channels) > 0:
            ch = channels[0]
            assert "channel" in ch
            assert "label" in ch
            assert "revenue" in ch
            assert "bookings" in ch
            print(f"Top channel: {ch['label']} with {ch['bookings']} bookings, {ch['revenue']} TRY revenue")
    
    def test_dashboard_room_type_performance(self, auth_headers):
        """Test room type performance data"""
        response = requests.get(f"{BASE_URL}/api/rms/dashboard-kpis", headers=auth_headers)
        assert response.status_code == 200
        
        data = response.json()
        assert "room_type_performance" in data
        
        rt_perf = data["room_type_performance"]
        if len(rt_perf) > 0:
            rt = rt_perf[0]
            assert "room_type" in rt
            assert "revenue" in rt
            assert "count" in rt
            print(f"Room type performance: {len(rt_perf)} room types")


class TestYieldRulesCRUD(TestRMSAuth):
    """Test /api/rms/yield-rules CRUD operations"""
    
    def test_get_yield_rules(self, auth_headers):
        """Test GET yield rules - should have 5 pre-seeded rules"""
        response = requests.get(f"{BASE_URL}/api/rms/yield-rules", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "rules" in data
        rules = data["rules"]
        assert len(rules) >= 5, f"Expected at least 5 pre-seeded rules, got {len(rules)}"
        
        # Verify rule structure
        if rules:
            rule = rules[0]
            assert "id" in rule
            assert "name" in rule
            assert "condition_type" in rule
            assert "action_type" in rule
            print(f"Found {len(rules)} yield rules")
    
    def test_create_yield_rule(self, auth_headers):
        """Test POST create new yield rule"""
        new_rule = {
            "name": "TEST_High_Demand_Premium",
            "description": "Test rule for high demand pricing",
            "condition_type": "occupancy_above",
            "condition_value": 85,
            "action_type": "increase_percent",
            "action_value": 20,
            "is_active": True,
            "priority": 99,
            "room_types": []
        }
        
        response = requests.post(f"{BASE_URL}/api/rms/yield-rules", 
                                json=new_rule, headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "id" in data
        assert data["name"] == new_rule["name"]
        assert data["condition_value"] == 85
        print(f"Created yield rule: {data['id']}")
        
        # Store for cleanup
        return data["id"]
    
    def test_update_yield_rule(self, auth_headers):
        """Test PUT update yield rule"""
        # First create a rule
        new_rule = {
            "name": "TEST_Update_Rule",
            "description": "Rule to be updated",
            "condition_type": "lead_time_below",
            "condition_value": 5,
            "action_type": "decrease_percent",
            "action_value": 8,
            "is_active": True,
            "priority": 98
        }
        
        create_resp = requests.post(f"{BASE_URL}/api/rms/yield-rules", 
                                   json=new_rule, headers=auth_headers)
        assert create_resp.status_code == 200
        rule_id = create_resp.json()["id"]
        
        # Update the rule
        updated_rule = {
            "name": "TEST_Update_Rule_Modified",
            "description": "Updated description",
            "condition_type": "lead_time_below",
            "condition_value": 7,
            "action_type": "decrease_percent",
            "action_value": 12,
            "is_active": False,
            "priority": 97
        }
        
        update_resp = requests.put(f"{BASE_URL}/api/rms/yield-rules/{rule_id}", 
                                  json=updated_rule, headers=auth_headers)
        assert update_resp.status_code == 200, f"Update failed: {update_resp.text}"
        
        # Verify update
        get_resp = requests.get(f"{BASE_URL}/api/rms/yield-rules", headers=auth_headers)
        rules = get_resp.json()["rules"]
        updated = next((r for r in rules if r["id"] == rule_id), None)
        assert updated is not None
        assert updated["name"] == "TEST_Update_Rule_Modified"
        assert updated["action_value"] == 12
        print(f"Updated yield rule: {rule_id}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/rms/yield-rules/{rule_id}", headers=auth_headers)
    
    def test_delete_yield_rule(self, auth_headers):
        """Test DELETE yield rule"""
        # Create a rule to delete
        new_rule = {
            "name": "TEST_Delete_Rule",
            "description": "Rule to be deleted",
            "condition_type": "day_of_week",
            "condition_value": "monday",
            "action_type": "decrease_percent",
            "action_value": 5,
            "is_active": True,
            "priority": 100
        }
        
        create_resp = requests.post(f"{BASE_URL}/api/rms/yield-rules", 
                                   json=new_rule, headers=auth_headers)
        assert create_resp.status_code == 200
        rule_id = create_resp.json()["id"]
        
        # Delete the rule
        delete_resp = requests.delete(f"{BASE_URL}/api/rms/yield-rules/{rule_id}", 
                                     headers=auth_headers)
        assert delete_resp.status_code == 200, f"Delete failed: {delete_resp.text}"
        
        # Verify deletion
        get_resp = requests.get(f"{BASE_URL}/api/rms/yield-rules", headers=auth_headers)
        rules = get_resp.json()["rules"]
        deleted = next((r for r in rules if r["id"] == rule_id), None)
        assert deleted is None, "Rule should be deleted"
        print(f"Deleted yield rule: {rule_id}")


class TestSeasonalCalendarCRUD(TestRMSAuth):
    """Test /api/rms/seasonal-calendar CRUD operations"""
    
    def test_get_seasonal_calendar(self, auth_headers):
        """Test GET seasonal calendar - should have 6 pre-seeded seasons"""
        response = requests.get(f"{BASE_URL}/api/rms/seasonal-calendar", headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "seasons" in data
        seasons = data["seasons"]
        assert len(seasons) >= 6, f"Expected at least 6 pre-seeded seasons, got {len(seasons)}"
        
        # Verify season structure
        if seasons:
            season = seasons[0]
            assert "id" in season
            assert "name" in season
            assert "season_type" in season
            assert "start_date" in season
            assert "end_date" in season
            assert "rate_multiplier" in season
            print(f"Found {len(seasons)} seasons")
    
    def test_create_season(self, auth_headers):
        """Test POST create new season"""
        new_season = {
            "name": "TEST_Special_Event",
            "season_type": "peak",
            "start_date": "2026-08-01",
            "end_date": "2026-08-15",
            "rate_multiplier": 1.40,
            "min_stay": 2,
            "color": "#dc2626",
            "is_active": True
        }
        
        response = requests.post(f"{BASE_URL}/api/rms/seasonal-calendar", 
                                json=new_season, headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "id" in data
        assert data["name"] == new_season["name"]
        assert data["rate_multiplier"] == 1.40
        print(f"Created season: {data['id']}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/rms/seasonal-calendar/{data['id']}", headers=auth_headers)
    
    def test_update_season(self, auth_headers):
        """Test PUT update season"""
        # First create a season
        new_season = {
            "name": "TEST_Update_Season",
            "season_type": "mid",
            "start_date": "2026-09-01",
            "end_date": "2026-09-30",
            "rate_multiplier": 1.05,
            "min_stay": 1,
            "color": "#22c55e",
            "is_active": True
        }
        
        create_resp = requests.post(f"{BASE_URL}/api/rms/seasonal-calendar", 
                                   json=new_season, headers=auth_headers)
        assert create_resp.status_code == 200
        season_id = create_resp.json()["id"]
        
        # Update the season
        updated_season = {
            "name": "TEST_Update_Season_Modified",
            "season_type": "high",
            "start_date": "2026-09-01",
            "end_date": "2026-10-15",
            "rate_multiplier": 1.25,
            "min_stay": 2,
            "color": "#ef4444",
            "is_active": True
        }
        
        update_resp = requests.put(f"{BASE_URL}/api/rms/seasonal-calendar/{season_id}", 
                                  json=updated_season, headers=auth_headers)
        assert update_resp.status_code == 200, f"Update failed: {update_resp.text}"
        
        # Verify update
        get_resp = requests.get(f"{BASE_URL}/api/rms/seasonal-calendar", headers=auth_headers)
        seasons = get_resp.json()["seasons"]
        updated = next((s for s in seasons if s["id"] == season_id), None)
        assert updated is not None
        assert updated["name"] == "TEST_Update_Season_Modified"
        assert updated["rate_multiplier"] == 1.25
        print(f"Updated season: {season_id}")
        
        # Cleanup
        requests.delete(f"{BASE_URL}/api/rms/seasonal-calendar/{season_id}", headers=auth_headers)
    
    def test_delete_season(self, auth_headers):
        """Test DELETE season"""
        # Create a season to delete
        new_season = {
            "name": "TEST_Delete_Season",
            "season_type": "low",
            "start_date": "2026-11-01",
            "end_date": "2026-11-30",
            "rate_multiplier": 0.80,
            "min_stay": 1,
            "color": "#3b82f6",
            "is_active": True
        }
        
        create_resp = requests.post(f"{BASE_URL}/api/rms/seasonal-calendar", 
                                   json=new_season, headers=auth_headers)
        assert create_resp.status_code == 200
        season_id = create_resp.json()["id"]
        
        # Delete the season
        delete_resp = requests.delete(f"{BASE_URL}/api/rms/seasonal-calendar/{season_id}", 
                                     headers=auth_headers)
        assert delete_resp.status_code == 200, f"Delete failed: {delete_resp.text}"
        
        # Verify deletion
        get_resp = requests.get(f"{BASE_URL}/api/rms/seasonal-calendar", headers=auth_headers)
        seasons = get_resp.json()["seasons"]
        deleted = next((s for s in seasons if s["id"] == season_id), None)
        assert deleted is None, "Season should be deleted"
        print(f"Deleted season: {season_id}")


class TestGeneratePricing(TestRMSAuth):
    """Test /api/rms/generate-pricing endpoint"""
    
    def test_generate_pricing_recommendations(self, auth_headers):
        """Test POST generate pricing recommendations"""
        from datetime import datetime, timedelta
        
        today = datetime.now()
        start_date = today.strftime("%Y-%m-%d")
        end_date = (today + timedelta(days=7)).strftime("%Y-%m-%d")
        
        payload = {
            "start_date": start_date,
            "end_date": end_date
        }
        
        response = requests.post(f"{BASE_URL}/api/rms/generate-pricing", 
                                json=payload, headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "recommendations" in data or "summary" in data
        
        if "summary" in data:
            summary = data["summary"]
            print(f"Generated {summary.get('total', 0)} pricing recommendations")
        
        if "recommendations" in data:
            recs = data["recommendations"]
            if len(recs) > 0:
                rec = recs[0]
                assert "date" in rec
                assert "room_type" in rec
                assert "current_rate" in rec or "base_rate" in rec
                assert "suggested_rate" in rec
                print(f"Sample recommendation: {rec.get('room_type')} on {rec.get('date')}: {rec.get('suggested_rate')} TRY")


class TestApplyRecommendations(TestRMSAuth):
    """Test /api/rms/apply-recommendations endpoint"""
    
    def test_apply_all_recommendations(self, auth_headers):
        """Test POST apply all pending recommendations"""
        response = requests.post(f"{BASE_URL}/api/rms/apply-recommendations", 
                                headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "message" in data
        assert "applied_count" in data
        print(f"Applied {data['applied_count']} recommendations: {data['message']}")


class TestPricingRecommendations(TestRMSAuth):
    """Test /api/rms/pricing-recommendations endpoint"""
    
    def test_get_pending_recommendations(self, auth_headers):
        """Test GET pending pricing recommendations"""
        response = requests.get(f"{BASE_URL}/api/rms/pricing-recommendations?status=pending", 
                               headers=auth_headers)
        assert response.status_code == 200, f"Failed: {response.text}"
        
        data = response.json()
        assert "recommendations" in data
        assert "count" in data
        print(f"Found {data['count']} pending recommendations")


# Cleanup test data after all tests
@pytest.fixture(scope="session", autouse=True)
def cleanup_test_data():
    """Cleanup TEST_ prefixed data after all tests"""
    yield
    
    # Login and cleanup
    login_resp = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if login_resp.status_code == 200:
        token = login_resp.json().get("access_token") or login_resp.json().get("token")
        headers = {"Authorization": f"Bearer {token}"}
        
        # Cleanup yield rules
        rules_resp = requests.get(f"{BASE_URL}/api/rms/yield-rules", headers=headers)
        if rules_resp.status_code == 200:
            for rule in rules_resp.json().get("rules", []):
                if rule.get("name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/rms/yield-rules/{rule['id']}", headers=headers)
        
        # Cleanup seasons
        seasons_resp = requests.get(f"{BASE_URL}/api/rms/seasonal-calendar", headers=headers)
        if seasons_resp.status_code == 200:
            for season in seasons_resp.json().get("seasons", []):
                if season.get("name", "").startswith("TEST_"):
                    requests.delete(f"{BASE_URL}/api/rms/seasonal-calendar/{season['id']}", headers=headers)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
