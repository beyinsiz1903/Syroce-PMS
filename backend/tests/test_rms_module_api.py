"""
Test RMS Module API Endpoints
Tests for the RMS (Revenue Management System) endpoints including:
- GET /api/rms/pricing-strategy
- PUT /api/rms/pricing-strategy
- GET /api/rms/price-adjustments
- GET /api/rms/demand-forecast?days=N
- POST /api/rms/apply-recommendations
- GET /api/rms/comp-set
"""
import os
import pytest
import requests

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestRMSModuleAPI:
    """RMS Module API Tests"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """Setup test session with authentication"""
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        
        # Login to get token
        login_response = self.session.post(f"{BASE_URL}/api/auth/login", json={
            "email": "demo@hotel.com",
            "password": "demo123"
        })
        
        if login_response.status_code == 200:
            data = login_response.json()
            token = data.get('access_token') or data.get('token')
            if token:
                self.session.headers.update({"Authorization": f"Bearer {token}"})
                self.token = token
            else:
                pytest.skip("No token in login response")
        else:
            pytest.skip(f"Authentication failed: {login_response.status_code}")
    
    # ========== GET /api/rms/pricing-strategy ==========
    def test_get_pricing_strategy_returns_200(self):
        """Test GET /api/rms/pricing-strategy returns 200"""
        response = self.session.get(f"{BASE_URL}/api/rms/pricing-strategy")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ GET /api/rms/pricing-strategy returned 200")
    
    def test_get_pricing_strategy_has_required_fields(self):
        """Test GET /api/rms/pricing-strategy returns required fields"""
        response = self.session.get(f"{BASE_URL}/api/rms/pricing-strategy")
        assert response.status_code == 200
        
        data = response.json()
        
        # Check required fields
        assert 'current_rate' in data, "Missing 'current_rate' field"
        assert 'recommended_rate' in data, "Missing 'recommended_rate' field"
        assert 'auto_pricing_enabled' in data, "Missing 'auto_pricing_enabled' field"
        assert 'market_position' in data, "Missing 'market_position' field"
        
        print(f"✓ Pricing strategy has all required fields:")
        print(f"  - current_rate: {data['current_rate']}")
        print(f"  - recommended_rate: {data['recommended_rate']}")
        print(f"  - auto_pricing_enabled: {data['auto_pricing_enabled']}")
        print(f"  - market_position: {data['market_position']}")
    
    # ========== PUT /api/rms/pricing-strategy ==========
    def test_put_pricing_strategy_enable_auto_pricing(self):
        """Test PUT /api/rms/pricing-strategy with auto_pricing_enabled=true"""
        response = self.session.put(f"{BASE_URL}/api/rms/pricing-strategy", json={
            "auto_pricing_enabled": True
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert 'auto_pricing_enabled' in data, "Response should contain auto_pricing_enabled"
        assert data['auto_pricing_enabled'] == True, "auto_pricing_enabled should be True"
        
        print(f"✓ PUT /api/rms/pricing-strategy with auto_pricing_enabled=true works")
    
    def test_put_pricing_strategy_disable_auto_pricing(self):
        """Test PUT /api/rms/pricing-strategy with auto_pricing_enabled=false"""
        response = self.session.put(f"{BASE_URL}/api/rms/pricing-strategy", json={
            "auto_pricing_enabled": False
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert 'auto_pricing_enabled' in data, "Response should contain auto_pricing_enabled"
        assert data['auto_pricing_enabled'] == False, "auto_pricing_enabled should be False"
        
        print(f"✓ PUT /api/rms/pricing-strategy with auto_pricing_enabled=false works")
    
    # ========== GET /api/rms/price-adjustments ==========
    def test_get_price_adjustments_returns_200(self):
        """Test GET /api/rms/price-adjustments returns 200"""
        response = self.session.get(f"{BASE_URL}/api/rms/price-adjustments")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ GET /api/rms/price-adjustments returned 200")
    
    def test_get_price_adjustments_has_required_structure(self):
        """Test GET /api/rms/price-adjustments returns {adjustments: [], count: N}"""
        response = self.session.get(f"{BASE_URL}/api/rms/price-adjustments")
        assert response.status_code == 200
        
        data = response.json()
        
        assert 'adjustments' in data, "Missing 'adjustments' field"
        assert 'count' in data, "Missing 'count' field"
        assert isinstance(data['adjustments'], list), "'adjustments' should be a list"
        assert isinstance(data['count'], int), "'count' should be an integer"
        
        print(f"✓ Price adjustments has correct structure: adjustments={len(data['adjustments'])}, count={data['count']}")
    
    # ========== GET /api/rms/demand-forecast?days=N ==========
    def test_get_demand_forecast_with_days_param_returns_200(self):
        """Test GET /api/rms/demand-forecast?days=7 returns 200"""
        response = self.session.get(f"{BASE_URL}/api/rms/demand-forecast?days=7")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ GET /api/rms/demand-forecast?days=7 returned 200")
    
    def test_get_demand_forecast_returns_correct_count(self):
        """Test GET /api/rms/demand-forecast?days=7 returns count=7"""
        response = self.session.get(f"{BASE_URL}/api/rms/demand-forecast?days=7")
        assert response.status_code == 200
        
        data = response.json()
        
        assert 'forecast' in data or 'forecasts' in data, "Missing 'forecast' or 'forecasts' field"
        assert 'count' in data, "Missing 'count' field"
        
        forecast_list = data.get('forecast') or data.get('forecasts', [])
        
        # Count should match days param (or be close to it)
        assert data['count'] == 7 or len(forecast_list) == 7, f"Expected count=7, got count={data['count']}, len={len(forecast_list)}"
        
        print(f"✓ Demand forecast returns correct count: {data['count']}")
    
    def test_get_demand_forecast_has_date_and_demand_index(self):
        """Test demand forecast items have date and demand_index fields"""
        response = self.session.get(f"{BASE_URL}/api/rms/demand-forecast?days=7")
        assert response.status_code == 200
        
        data = response.json()
        forecast_list = data.get('forecast') or data.get('forecasts', [])
        
        if len(forecast_list) > 0:
            first_item = forecast_list[0]
            assert 'date' in first_item, "Forecast item missing 'date' field"
            assert 'demand_index' in first_item, "Forecast item missing 'demand_index' field"
            print(f"✓ Forecast items have date and demand_index: date={first_item['date']}, demand_index={first_item['demand_index']}")
        else:
            print(f"✓ Forecast list is empty (no data yet) - structure is correct")
    
    def test_get_demand_forecast_30_days(self):
        """Test GET /api/rms/demand-forecast?days=30 returns 30 days"""
        response = self.session.get(f"{BASE_URL}/api/rms/demand-forecast?days=30")
        assert response.status_code == 200
        
        data = response.json()
        forecast_list = data.get('forecast') or data.get('forecasts', [])
        
        assert data['count'] == 30 or len(forecast_list) == 30, f"Expected 30 days, got count={data['count']}"
        print(f"✓ Demand forecast with days=30 returns {data['count']} items")
    
    # ========== POST /api/rms/apply-recommendations ==========
    def test_apply_recommendations_returns_200(self):
        """Test POST /api/rms/apply-recommendations returns 200"""
        response = self.session.post(f"{BASE_URL}/api/rms/apply-recommendations")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ POST /api/rms/apply-recommendations returned 200")
    
    def test_apply_recommendations_returns_applied_count(self):
        """Test POST /api/rms/apply-recommendations returns applied_count"""
        response = self.session.post(f"{BASE_URL}/api/rms/apply-recommendations")
        assert response.status_code == 200
        
        data = response.json()
        assert 'applied_count' in data, "Missing 'applied_count' field"
        assert isinstance(data['applied_count'], int), "'applied_count' should be an integer"
        
        print(f"✓ Apply recommendations returned applied_count: {data['applied_count']}")
    
    # ========== GET /api/rms/comp-set ==========
    def test_get_comp_set_returns_200(self):
        """Test GET /api/rms/comp-set returns 200"""
        response = self.session.get(f"{BASE_URL}/api/rms/comp-set")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        print(f"✓ GET /api/rms/comp-set returned 200")
    
    def test_get_comp_set_has_both_keys(self):
        """Test GET /api/rms/comp-set returns both 'competitors' and 'comp_set' keys"""
        response = self.session.get(f"{BASE_URL}/api/rms/comp-set")
        assert response.status_code == 200
        
        data = response.json()
        
        assert 'competitors' in data, "Missing 'competitors' key"
        assert 'comp_set' in data, "Missing 'comp_set' key"
        assert 'count' in data, "Missing 'count' key"
        
        print(f"✓ Comp-set has both 'competitors' and 'comp_set' keys, count={data['count']}")
    
    def test_get_comp_set_competitors_structure(self):
        """Test comp-set competitors have expected fields"""
        response = self.session.get(f"{BASE_URL}/api/rms/comp-set")
        assert response.status_code == 200
        
        data = response.json()
        competitors = data.get('competitors', [])
        
        if len(competitors) > 0:
            comp = competitors[0]
            # Check for enriched fields
            assert 'avg_rate' in comp, "Competitor missing 'avg_rate'"
            assert 'occupancy_rate' in comp, "Competitor missing 'occupancy_rate'"
            assert 'revpar' in comp, "Competitor missing 'revpar'"
            assert 'distance_km' in comp, "Competitor missing 'distance_km'"
            print(f"✓ Competitor has enriched fields: avg_rate={comp['avg_rate']}, occupancy_rate={comp['occupancy_rate']}")
        else:
            print(f"✓ No competitors in comp-set yet (empty list is valid)")


class TestRMSModuleWithoutAuth:
    """Test RMS endpoints require authentication"""
    
    def test_pricing_strategy_requires_auth(self):
        """Test GET /api/rms/pricing-strategy requires authentication"""
        response = requests.get(f"{BASE_URL}/api/rms/pricing-strategy")
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        print(f"✓ GET /api/rms/pricing-strategy requires authentication")
    
    def test_comp_set_requires_auth(self):
        """Test GET /api/rms/comp-set requires authentication"""
        response = requests.get(f"{BASE_URL}/api/rms/comp-set")
        assert response.status_code in [401, 403], f"Expected 401/403 without auth, got {response.status_code}"
        print(f"✓ GET /api/rms/comp-set requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
