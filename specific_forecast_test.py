#!/usr/bin/env python3
"""
Test the specific date ranges mentioned in the review request
"""

import requests
import json

# Configuration
BACKEND_URL = "https://guest-messaging-1.preview.emergentagent.com/api"
TEST_EMAIL = "test@hotel.com"
TEST_PASSWORD = "test123"

def authenticate():
    """Authenticate with the backend"""
    session = requests.Session()
    response = session.post(f"{BACKEND_URL}/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    
    if response.status_code == 200:
        data = response.json()
        session.headers.update({
            "Authorization": f"Bearer {data['access_token']}",
            "Content-Type": "application/json"
        })
        return session
    return None

def test_specific_ranges():
    """Test the exact date ranges from the review request"""
    session = authenticate()
    if not session:
        print("❌ Authentication failed")
        return
    
    print("🎯 Testing Specific Date Ranges from Review Request...")
    
    # Test cases from the review request
    test_cases = [
        {
            "name": "90-Day Forecast (89 days: Feb 1 - Apr 30)",
            "start_date": "2025-02-01",
            "end_date": "2025-04-30",
            "expected_days": 89
        },
        {
            "name": "30-Day Forecast (30 days: Feb 1 - Mar 2)",
            "start_date": "2025-02-01", 
            "end_date": "2025-03-02",
            "expected_days": 30
        },
        {
            "name": "60-Day Forecast (60 days: Feb 1 - Apr 1)",
            "start_date": "2025-02-01",
            "end_date": "2025-04-01", 
            "expected_days": 60
        }
    ]
    
    for test_case in test_cases:
        print(f"\n📈 Testing: {test_case['name']}")
        
        try:
            response = session.post(f"{BACKEND_URL}/rms/demand-forecast", json={
                "start_date": test_case["start_date"],
                "end_date": test_case["end_date"]
            })
            
            if response.status_code == 200:
                data = response.json()
                forecasts = data.get('forecasts', [])
                summary = data.get('summary', {})
                
                print(f"  ✅ Status: 200")
                print(f"  📊 Forecasts generated: {len(forecasts)}")
                print(f"  🎯 Expected days: {test_case['expected_days']}")
                print(f"  ✅ Match: {'Yes' if len(forecasts) == test_case['expected_days'] else 'No'}")
                
                if forecasts:
                    first_forecast = forecasts[0]
                    print(f"  🔮 Sample forecast:")
                    print(f"     - Date: {first_forecast.get('date', 'N/A')}")
                    print(f"     - Occupancy: {first_forecast.get('forecasted_occupancy', 'N/A')}%")
                    print(f"     - Confidence: {first_forecast.get('confidence', 'N/A')} ({first_forecast.get('confidence_level', 'N/A')})")
                    print(f"     - Trend: {first_forecast.get('trend', 'N/A')}")
                    print(f"     - Model Version: {first_forecast.get('model_version', 'N/A')}")
                
                print(f"  📈 Summary:")
                print(f"     - Total days: {summary.get('total_days', 'N/A')}")
                print(f"     - High demand days: {summary.get('high_demand_days', 'N/A')}")
                print(f"     - Moderate demand days: {summary.get('moderate_demand_days', 'N/A')}")
                print(f"     - Low demand days: {summary.get('low_demand_days', 'N/A')}")
                print(f"     - Avg occupancy: {summary.get('avg_forecasted_occupancy', 'N/A')}%")
                
            else:
                print(f"  ❌ Status: {response.status_code}")
                print(f"  ❌ Error: {response.text[:200]}")
                
        except Exception as e:
            print(f"  ❌ Exception: {str(e)}")
    
    print("\n🎉 All specific date range tests completed!")

if __name__ == "__main__":
    test_specific_ranges()