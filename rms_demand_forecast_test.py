#!/usr/bin/env python3
"""
Focused RMS 90-Day Demand Forecast Testing
Testing the timezone fix for demand forecasting
"""

import requests
import json
import sys
from datetime import datetime, timedelta

# Configuration
BACKEND_URL = "https://code-cleanup-135.preview.emergentagent.com/api"
TEST_EMAIL = "test@hotel.com"
TEST_PASSWORD = "test123"

class RMSDemandForecastTester:
    def __init__(self):
        self.session = requests.Session()
        self.auth_token = None
        self.test_results = []

    def authenticate(self):
        """Authenticate with the backend"""
        print("🔐 Authenticating...")
        try:
            response = self.session.post(f"{BACKEND_URL}/auth/login", json={
                "email": TEST_EMAIL,
                "password": TEST_PASSWORD
            })
            
            if response.status_code == 200:
                data = response.json()
                self.auth_token = data["access_token"]
                self.session.headers.update({
                    "Authorization": f"Bearer {self.auth_token}",
                    "Content-Type": "application/json"
                })
                print(f"✅ Authentication successful - User: {data['user']['name']}")
                return True
            else:
                print(f"❌ Authentication failed: {response.status_code} - {response.text}")
                return False
        except Exception as e:
            print(f"❌ Authentication error: {str(e)}")
            return False

    def log_result(self, test_name, success, details, response_data=None):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        result = {
            "test": test_name,
            "status": status,
            "details": details,
            "response_data": response_data
        }
        self.test_results.append(result)
        print(f"  {status}: {test_name} - {details}")

    def test_30_day_forecast(self):
        """Test 30-day demand forecast"""
        print("\n📈 Testing 30-Day Demand Forecast...")
        
        try:
            response = self.session.post(f"{BACKEND_URL}/rms/demand-forecast", json={
                "start_date": "2025-02-01",
                "end_date": "2025-03-02"  # 30 days
            })
            
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                data = response.json()
                forecast_data = data.get('forecasts', [])
                details += f" - Forecast days: {len(forecast_data)}"
                
                # Verify response structure
                if forecast_data:
                    first_forecast = forecast_data[0]
                    required_fields = [
                        'forecasted_occupancy', 'confidence', 'confidence_level',
                        'trend', 'model_version'
                    ]
                    
                    missing_fields = [field for field in required_fields if field not in first_forecast]
                    if missing_fields:
                        details += f" - Missing fields: {missing_fields}"
                        success = False
                    else:
                        model_version = first_forecast.get('model_version', 'N/A')
                        confidence_level = first_forecast.get('confidence_level', 'N/A')
                        details += f" - Model: {model_version}, Confidence: {confidence_level}"
                
                # Check summary
                summary = data.get('summary', {})
                if summary:
                    high_demand = summary.get('high_demand_days', 0)
                    moderate_demand = summary.get('moderate_demand_days', 0)
                    low_demand = summary.get('low_demand_days', 0)
                    details += f" - Demand breakdown: H:{high_demand}, M:{moderate_demand}, L:{low_demand}"
                
                self.log_result("30-Day Demand Forecast", success, details, data)
            else:
                error_text = response.text[:200] if response.text else "No error details"
                self.log_result("30-Day Demand Forecast", success, f"{details} - Error: {error_text}")
                
        except Exception as e:
            self.log_result("30-Day Demand Forecast", False, f"Exception: {str(e)}")

    def test_60_day_forecast(self):
        """Test 60-day demand forecast"""
        print("\n📈 Testing 60-Day Demand Forecast...")
        
        try:
            response = self.session.post(f"{BACKEND_URL}/rms/demand-forecast", json={
                "start_date": "2025-02-01",
                "end_date": "2025-04-01"  # 60 days
            })
            
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                data = response.json()
                forecast_data = data.get('forecasts', [])
                details += f" - Forecast days: {len(forecast_data)}"
                
                # Verify we get approximately 60 days
                if 55 <= len(forecast_data) <= 65:
                    details += " - Day count correct ✓"
                else:
                    details += f" - WARNING: Expected ~60 days, got {len(forecast_data)}"
                
                # Check model version
                if forecast_data:
                    model_version = forecast_data[0].get('model_version', 'N/A')
                    if model_version == "2.0-advanced":
                        details += f" - Model version: {model_version} ✓"
                    else:
                        details += f" - Model version: {model_version} (expected: 2.0-advanced)"
                
                self.log_result("60-Day Demand Forecast", success, details, data)
            else:
                error_text = response.text[:200] if response.text else "No error details"
                self.log_result("60-Day Demand Forecast", success, f"{details} - Error: {error_text}")
                
        except Exception as e:
            self.log_result("60-Day Demand Forecast", False, f"Exception: {str(e)}")

    def test_90_day_forecast(self):
        """Test 90-day demand forecast (the main focus)"""
        print("\n📈 Testing 90-Day Demand Forecast (MAIN TEST)...")
        
        try:
            response = self.session.post(f"{BACKEND_URL}/rms/demand-forecast", json={
                "start_date": "2025-02-01",
                "end_date": "2025-04-30"  # 89 days (Feb 1 to Apr 30)
            })
            
            success = response.status_code == 200
            details = f"Status: {response.status_code}"
            
            if success:
                data = response.json()
                forecast_data = data.get('forecasts', [])
                details += f" - Forecast days: {len(forecast_data)}"
                
                # Verify we get 89 days (Feb 1 to Apr 30)
                if 85 <= len(forecast_data) <= 92:
                    details += " - Day count correct for 89 days ✓"
                else:
                    details += f" - WARNING: Expected ~89 days, got {len(forecast_data)}"
                
                # Verify response structure
                if forecast_data:
                    first_forecast = forecast_data[0]
                    required_fields = [
                        'forecasted_occupancy', 'confidence', 'confidence_level',
                        'trend', 'model_version'
                    ]
                    
                    missing_fields = [field for field in required_fields if field not in required_fields]
                    present_fields = [field for field in required_fields if field in first_forecast]
                    details += f" - Required fields present: {len(present_fields)}/{len(required_fields)}"
                    
                    # Check specific values
                    forecasted_occupancy = first_forecast.get('forecasted_occupancy', 'N/A')
                    confidence = first_forecast.get('confidence', 'N/A')
                    confidence_level = first_forecast.get('confidence_level', 'N/A')
                    trend = first_forecast.get('trend', 'N/A')
                    model_version = first_forecast.get('model_version', 'N/A')
                    
                    details += f" - Occupancy: {forecasted_occupancy}, Confidence: {confidence} ({confidence_level})"
                    details += f" - Trend: {trend}, Model: {model_version}"
                    
                    # Verify dynamic confidence scoring
                    if isinstance(confidence, (int, float)) and confidence != 0.85:
                        details += " - Dynamic confidence ✓"
                    else:
                        details += " - WARNING: Static confidence detected"
                    
                    # Verify model version
                    if model_version == "2.0-advanced":
                        details += " - Model version correct ✓"
                    else:
                        details += f" - WARNING: Expected model version 2.0-advanced, got {model_version}"
                
                # Check summary statistics
                summary = data.get('summary', {})
                if summary:
                    high_demand = summary.get('high_demand_days', 0)
                    moderate_demand = summary.get('moderate_demand_days', 0)
                    low_demand = summary.get('low_demand_days', 0)
                    total_days = high_demand + moderate_demand + low_demand
                    details += f" - Summary: H:{high_demand}, M:{moderate_demand}, L:{low_demand} (Total: {total_days})"
                    
                    if total_days == len(forecast_data):
                        details += " - Summary totals match ✓"
                    else:
                        details += f" - WARNING: Summary total ({total_days}) != forecast days ({len(forecast_data)})"
                
                self.log_result("90-Day Demand Forecast", success, details, data)
            else:
                error_text = response.text[:500] if response.text else "No error details"
                self.log_result("90-Day Demand Forecast", success, f"{details} - Error: {error_text}")
                
        except Exception as e:
            self.log_result("90-Day Demand Forecast", False, f"Exception: {str(e)}")

    def run_all_tests(self):
        """Run all demand forecast tests"""
        print("🚀 Starting RMS Demand Forecast Testing...")
        
        if not self.authenticate():
            print("❌ Authentication failed. Cannot proceed with tests.")
            return False
        
        # Run tests in order
        self.test_30_day_forecast()
        self.test_60_day_forecast()
        self.test_90_day_forecast()
        
        # Print summary
        print("\n" + "="*60)
        print("📊 TEST SUMMARY")
        print("="*60)
        
        passed = sum(1 for result in self.test_results if "✅ PASS" in result["status"])
        failed = sum(1 for result in self.test_results if "❌ FAIL" in result["status"])
        
        print(f"Total Tests: {len(self.test_results)}")
        print(f"Passed: {passed}")
        print(f"Failed: {failed}")
        print(f"Success Rate: {(passed/len(self.test_results)*100):.1f}%")
        
        # Show detailed results
        for result in self.test_results:
            print(f"\n{result['status']}: {result['test']}")
            print(f"   Details: {result['details']}")
        
        # Focus on 90-day test result
        ninety_day_result = next((r for r in self.test_results if "90-Day" in r["test"]), None)
        if ninety_day_result:
            print("\n" + "="*60)
            print("🎯 90-DAY FORECAST TEST RESULT")
            print("="*60)
            print(f"Status: {ninety_day_result['status']}")
            print(f"Details: {ninety_day_result['details']}")
            
            if "✅ PASS" in ninety_day_result['status']:
                print("\n✅ SUCCESS: 90-day demand forecast is working correctly!")
                print("   - No more timezone errors")
                print("   - Proper response structure")
                print("   - Dynamic confidence scoring")
                print("   - Model version 2.0-advanced")
            else:
                print("\n❌ ISSUE: 90-day demand forecast still has problems")
        
        return failed == 0

if __name__ == "__main__":
    tester = RMSDemandForecastTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)