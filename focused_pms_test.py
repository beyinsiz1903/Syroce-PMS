#!/usr/bin/env python3
"""
Focused Hotel PMS Enhancement Testing
Testing specific endpoints with accurate response validation
"""

import requests
import json
import sys

# Configuration
BACKEND_URL = "https://bug-fix-update.preview.emergentagent.com/api"
AUTH_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ1c2VyX2lkIjoiZGMwNjlmMzgtNmIwZi00NDc4LWI4N2UtNGUzN2YzM2UwODViIiwidGVuYW50X2lkIjoiZjExYTE5MTktYmZlOC00ODI1LTkyYzktYzNmZWUzNWE5MmZhIiwiZXhwIjoxNzYzNjcwNzIwfQ.xaDjzpkmG7UFVwfUzVa92Ngs9n9piy3W1yQBSj6we-E"

def test_endpoint(method, endpoint, data=None, expected_fields=None):
    """Test a single endpoint"""
    headers = {
        "Authorization": f"Bearer {AUTH_TOKEN}",
        "Content-Type": "application/json"
    }
    
    try:
        if method == "GET":
            response = requests.get(f"{BACKEND_URL}{endpoint}", headers=headers)
        elif method == "POST":
            response = requests.post(f"{BACKEND_URL}{endpoint}", headers=headers, json=data)
        else:
            return False, f"Unsupported method: {method}"
        
        if response.status_code not in [200, 201]:
            return False, f"Status: {response.status_code}, Response: {response.text[:200]}"
        
        try:
            json_response = response.json()
        except:
            return False, f"Invalid JSON response: {response.text[:200]}"
        
        # Check for expected fields if provided
        if expected_fields:
            missing_fields = []
            for field in expected_fields:
                if '.' in field:  # Nested field like 'summary.housekeeping'
                    parts = field.split('.')
                    current = json_response
                    for part in parts:
                        if isinstance(current, dict) and part in current:
                            current = current[part]
                        else:
                            missing_fields.append(field)
                            break
                else:
                    if field not in json_response:
                        missing_fields.append(field)
            
            if missing_fields:
                return False, f"Missing fields: {missing_fields}, Got: {list(json_response.keys())}"
        
        return True, f"Success - Response keys: {list(json_response.keys())}"
        
    except Exception as e:
        return False, f"Error: {str(e)}"

def main():
    """Test key Hotel PMS enhancement endpoints"""
    print("🚀 Focused Hotel PMS Enhancement Testing")
    print("="*60)
    
    tests = [
        # Dashboard Endpoints (3)
        ("GET", "/dashboard/employee-performance", None, ["summary.housekeeping", "summary.front_desk"]),
        ("GET", "/dashboard/guest-satisfaction-trends?days=7", None, ["nps_score", "avg_rating", "response_breakdown.promoters", "response_breakdown.detractors"]),
        ("GET", "/dashboard/ota-cancellation-rate", None, ["cancellation_rates", "channel_breakdown"]),
        
        # Check-in Enhancements (3)
        ("POST", "/frontdesk/passport-scan", {"image_base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="}, ["extracted_data", "confidence"]),
        ("POST", "/frontdesk/walk-in-booking", {
            "guest_name": "John Walker",
            "guest_email": "john.walker@email.com", 
            "guest_phone": "+1234567890",
            "guest_id_number": "ID123456789",
            "room_type": "standard",
            "nights": 2,
            "adults": 2,
            "children": 0,
            "rate": 120.0
        }, ["guest_id", "booking_id"]),
        
        # Housekeeping (3)
        ("GET", "/housekeeping/task-timing", None, ["summary"]),
        ("GET", "/housekeeping/staff-performance-table", None, ["staff_performance", "summary"]),
        ("GET", "/housekeeping/linen-inventory", None, ["inventory"]),
        
        # Business Operations (sample)
        ("GET", "/channel-manager/sync-history", None, ["sync_logs"]),
        ("GET", "/rms/market-compression", None, ["compression_score"]),
        ("POST", "/feedback/ai-sentiment-analysis", {
            "review_text": "Great hotel with excellent service!",
            "source": "booking_com"
        }, ["sentiment_score", "sentiment_label"]),
    ]
    
    passed = 0
    failed = 0
    
    for method, endpoint, data, expected_fields in tests:
        print(f"\n🔍 Testing {method} {endpoint}")
        success, details = test_endpoint(method, endpoint, data, expected_fields)
        
        if success:
            print(f"  ✅ PASS: {details}")
            passed += 1
        else:
            print(f"  ❌ FAIL: {details}")
            failed += 1
    
    print(f"\n{'='*60}")
    print(f"📊 RESULTS: {passed}/{passed + failed} ({(passed/(passed + failed)*100):.1f}%)")
    
    if passed >= (passed + failed) * 0.8:
        print("✅ Most Hotel PMS enhancements are working correctly!")
        return True
    else:
        print("⚠️ Several Hotel PMS enhancements need attention.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)