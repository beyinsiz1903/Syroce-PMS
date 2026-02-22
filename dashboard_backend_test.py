#!/usr/bin/env python3
"""
Dashboard Backend API Test

Tests dashboard API endpoints to ensure they return proper data types for React rendering:
1. POST /api/auth/login - Login with gm@hotel.com / gm123 and admin@hotel.com / admin123
2. GET /api/pms/dashboard - Should return numbers for all stats
3. GET /api/invoices/stats - Should return numbers for all stats
4. GET /api/ai/dashboard/briefing - Should return proper structure with no nested objects in React-renderable fields
5. GET /api/analytics/occupancy-trend?days=30 - Should return trend data
6. GET /api/analytics/revenue-trend?days=30 - Should return trend data
7. GET /api/analytics/booking-trends?days=30 - Should return trend data

CRITICAL: Verify that NO response value that will be rendered as React text contains nested objects.
Every value in PMS dashboard and invoice stats response should be a number or string, never an object.
"""

import requests
import json
from datetime import datetime
import os

# Configuration
BASE_URL = "https://auth-endpoint-suite.preview.emergentagent.com/api"

def print_section(title):
    """Print a formatted section header"""
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")

def print_result(test_name, passed, details=""):
    """Print test result"""
    status = "✅ PASSED" if passed else "❌ FAILED"
    print(f"{status}: {test_name}")
    if details:
        print(f"   Details: {details}")

def check_for_nested_objects(data, path=""):
    """
    Recursively check if any value in the data structure is a nested object
    that would cause React rendering issues.
    Returns (is_safe, issues) where issues is a list of problematic paths
    """
    issues = []
    
    if isinstance(data, dict):
        for key, value in data.items():
            current_path = f"{path}.{key}" if path else key
            
            # Check if this value would be rendered as text in React
            if isinstance(value, dict) and key not in ['metrics', 'data', 'trend', 'insights']:
                # This is a nested object in a field that might be rendered directly
                issues.append(f"{current_path}: {type(value).__name__}")
            elif isinstance(value, list):
                # Check each item in the list
                for i, item in enumerate(value):
                    item_path = f"{current_path}[{i}]"
                    if isinstance(item, dict):
                        # Lists of objects are usually fine (like trends), but check contents
                        nested_issues = check_for_nested_objects(item, item_path)[1]
                        issues.extend(nested_issues)
            elif isinstance(value, dict):
                # Recurse into nested objects
                nested_issues = check_for_nested_objects(value, current_path)[1]
                issues.extend(nested_issues)
    
    return len(issues) == 0, issues

def login_user(email, password):
    """Login with provided credentials and return token"""
    print(f"Attempting login: {email}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={
                "email": email,
                "password": password
            },
            timeout=30
        )
        
        print(f"Request: POST /api/auth/login")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            user = data.get("user", {})
            print_result("Login", True, f"User: {user.get('name', 'Unknown')}, Role: {user.get('role', 'Unknown')}")
            if token:
                print(f"Token preview: {token[:20]}...")
            return token, user
        else:
            print_result("Login", False, f"HTTP {response.status_code}: {response.text}")
            return None, None
            
    except Exception as e:
        print_result("Login", False, f"Exception: {str(e)}")
        return None, None

def test_pms_dashboard(token):
    """Test GET /api/pms/dashboard"""
    print_section("PMS Dashboard Test")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/pms/dashboard", headers=headers, timeout=30)
        
        print(f"Request: GET /api/pms/dashboard")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response data: {json.dumps(data, indent=2)}")
            
            # Check for required fields
            required_fields = [
                "total_rooms", "occupied_rooms", "available_rooms", 
                "occupancy_rate", "today_checkins", "total_guests"
            ]
            
            checks = {"HTTP 200": response.status_code == 200}
            
            for field in required_fields:
                field_exists = field in data
                checks[f"Has {field}"] = field_exists
                
                if field_exists:
                    value = data[field]
                    is_number = isinstance(value, (int, float))
                    checks[f"{field} is number"] = is_number
                    if not is_number:
                        print(f"❌ {field} is {type(value).__name__}: {value}")
            
            # Check for nested objects that would break React rendering
            is_safe, issues = check_for_nested_objects(data)
            checks["No nested objects in React fields"] = is_safe
            if issues:
                print(f"❌ Nested object issues: {issues}")
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed, data
            
        else:
            print_result("PMS Dashboard", False, f"HTTP {response.status_code}: {response.text}")
            return False, {}
            
    except Exception as e:
        print_result("PMS Dashboard", False, f"Exception: {str(e)}")
        return False, {}

def test_invoices_stats(token):
    """Test GET /api/invoices/stats"""
    print_section("Invoices Stats Test")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/invoices/stats", headers=headers, timeout=30)
        
        print(f"Request: GET /api/invoices/stats")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response data: {json.dumps(data, indent=2)}")
            
            # Check for required fields
            required_fields = [
                "total_invoices", "total_revenue", "pending_amount", "overdue_amount"
            ]
            
            checks = {"HTTP 200": response.status_code == 200}
            
            for field in required_fields:
                field_exists = field in data
                checks[f"Has {field}"] = field_exists
                
                if field_exists:
                    value = data[field]
                    is_number = isinstance(value, (int, float))
                    checks[f"{field} is number"] = is_number
                    if not is_number:
                        print(f"❌ {field} is {type(value).__name__}: {value}")
            
            # Check for nested objects that would break React rendering
            is_safe, issues = check_for_nested_objects(data)
            checks["No nested objects in React fields"] = is_safe
            if issues:
                print(f"❌ Nested object issues: {issues}")
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed, data
            
        else:
            print_result("Invoices Stats", False, f"HTTP {response.status_code}: {response.text}")
            return False, {}
            
    except Exception as e:
        print_result("Invoices Stats", False, f"Exception: {str(e)}")
        return False, {}

def test_ai_dashboard_briefing(token):
    """Test GET /api/ai/dashboard/briefing"""
    print_section("AI Dashboard Briefing Test")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(f"{BASE_URL}/ai/dashboard/briefing", headers=headers, timeout=30)
        
        print(f"Request: GET /api/ai/dashboard/briefing")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response data: {json.dumps(data, indent=2)}")
            
            checks = {"HTTP 200": response.status_code == 200}
            
            # Check required fields
            required_fields = ["summary", "text", "briefing", "metrics", "generated_at", "insights"]
            for field in required_fields:
                checks[f"Has {field}"] = field in data
            
            # Check data types for React-safe rendering
            if "summary" in data:
                checks["summary is string"] = isinstance(data["summary"], str)
            if "text" in data:
                checks["text is string"] = isinstance(data["text"], str)
            if "briefing" in data:
                checks["briefing is string"] = isinstance(data["briefing"], str)
            if "generated_at" in data:
                checks["generated_at is string"] = isinstance(data["generated_at"], str)
            if "insights" in data:
                insights = data["insights"]
                checks["insights is array"] = isinstance(insights, list)
                if isinstance(insights, list) and insights:
                    checks["insights contains strings"] = all(isinstance(item, str) for item in insights)
            
            # Check metrics object has number values
            if "metrics" in data and isinstance(data["metrics"], dict):
                metrics = data["metrics"]
                checks["metrics is object"] = True
                for key, value in metrics.items():
                    checks[f"metrics.{key} is number"] = isinstance(value, (int, float))
            
            # Check for nested objects in string fields that would break React
            string_fields = ["summary", "text", "briefing", "generated_at"]
            for field in string_fields:
                if field in data and not isinstance(data[field], str):
                    checks[f"{field} React-safe"] = False
                    print(f"❌ {field} is {type(data[field]).__name__}, should be string")
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed, data
            
        else:
            print_result("AI Dashboard Briefing", False, f"HTTP {response.status_code}: {response.text}")
            return False, {}
            
    except Exception as e:
        print_result("AI Dashboard Briefing", False, f"Exception: {str(e)}")
        return False, {}

def test_analytics_endpoint(token, endpoint, days=30):
    """Test analytics endpoints"""
    endpoint_name = endpoint.replace("/api/analytics/", "").replace("?days=30", "")
    print_section(f"Analytics Test: {endpoint_name}")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        url = f"{BASE_URL}/analytics/{endpoint_name}?days={days}"
        response = requests.get(url, headers=headers, timeout=30)
        
        print(f"Request: GET {url}")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response data: {json.dumps(data, indent=2)}")
            
            checks = {"HTTP 200": response.status_code == 200}
            
            # Check for trend field
            checks["Has trend field"] = "trend" in data
            
            if "trend" in data:
                trend = data["trend"]
                checks["trend is array"] = isinstance(trend, list)
                
                if isinstance(trend, list) and trend:
                    # Check first item structure for occupancy-trend
                    first_item = trend[0]
                    if endpoint_name == "occupancy-trend":
                        required_fields = ["date", "occupancy_rate", "occupied_rooms", "total_rooms"]
                        for field in required_fields:
                            checks[f"trend item has {field}"] = field in first_item
                            if field in first_item:
                                value = first_item[field]
                                if field == "date":
                                    checks[f"{field} is string"] = isinstance(value, str)
                                else:
                                    checks[f"{field} is number"] = isinstance(value, (int, float))
                    else:
                        # For other analytics endpoints, just check they have data
                        checks["trend items are objects"] = isinstance(first_item, dict)
                        checks["trend items have data"] = len(first_item) > 0
                else:
                    checks["trend has data"] = len(trend) > 0
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed, data
            
        else:
            print_result(f"Analytics {endpoint_name}", False, f"HTTP {response.status_code}: {response.text}")
            return False, {}
            
    except Exception as e:
        print_result(f"Analytics {endpoint_name}", False, f"Exception: {str(e)}")
        return False, {}

def main():
    """Main test execution"""
    print("\n" + "="*80)
    print("  DASHBOARD BACKEND API TEST")
    print("  Testing dashboard endpoints for React rendering compatibility")
    print("="*80)
    
    results = {
        "gm_login": False,
        "admin_login": False,
        "pms_dashboard_gm": False,
        "invoices_stats_gm": False,
        "ai_briefing_gm": False,
        "occupancy_trend_gm": False,
        "revenue_trend_gm": False,
        "booking_trends_gm": False,
        "pms_dashboard_admin": False,
        "invoices_stats_admin": False,
        "ai_briefing_admin": False,
        "occupancy_trend_admin": False,
        "revenue_trend_admin": False,
        "booking_trends_admin": False,
    }
    
    # Test with GM credentials
    print_section("Testing with GM Account (gm@hotel.com)")
    gm_token, gm_user = login_user("gm@hotel.com", "gm123")
    
    if gm_token:
        results["gm_login"] = True
        
        # Test all endpoints with GM account
        pms_success, _ = test_pms_dashboard(gm_token)
        results["pms_dashboard_gm"] = pms_success
        
        invoices_success, _ = test_invoices_stats(gm_token)
        results["invoices_stats_gm"] = invoices_success
        
        ai_success, _ = test_ai_dashboard_briefing(gm_token)
        results["ai_briefing_gm"] = ai_success
        
        occupancy_success, _ = test_analytics_endpoint(gm_token, "occupancy-trend")
        results["occupancy_trend_gm"] = occupancy_success
        
        revenue_success, _ = test_analytics_endpoint(gm_token, "revenue-trend")
        results["revenue_trend_gm"] = revenue_success
        
        booking_success, _ = test_analytics_endpoint(gm_token, "booking-trends")
        results["booking_trends_gm"] = booking_success
    
    # Test with Admin credentials
    print_section("Testing with Admin Account (admin@hotel.com)")
    admin_token, admin_user = login_user("admin@hotel.com", "admin123")
    
    if admin_token:
        results["admin_login"] = True
        
        # Test all endpoints with Admin account
        pms_success, _ = test_pms_dashboard(admin_token)
        results["pms_dashboard_admin"] = pms_success
        
        invoices_success, _ = test_invoices_stats(admin_token)
        results["invoices_stats_admin"] = invoices_success
        
        ai_success, _ = test_ai_dashboard_briefing(admin_token)
        results["ai_briefing_admin"] = ai_success
        
        occupancy_success, _ = test_analytics_endpoint(admin_token, "occupancy-trend")
        results["occupancy_trend_admin"] = occupancy_success
        
        revenue_success, _ = test_analytics_endpoint(admin_token, "revenue-trend")
        results["revenue_trend_admin"] = revenue_success
        
        booking_success, _ = test_analytics_endpoint(admin_token, "booking-trends")
        results["booking_trends_admin"] = booking_success
    
    # Print final summary
    print_final_summary(results)

def print_final_summary(results):
    """Print final test summary"""
    print_section("FINAL TEST SUMMARY")
    
    total_tests = len(results)
    passed_tests = sum(1 for v in results.values() if v)
    success_rate = (passed_tests / total_tests * 100) if total_tests > 0 else 0
    
    print(f"Total Tests: {total_tests}")
    print(f"Passed: {passed_tests}")
    print(f"Failed: {total_tests - passed_tests}")
    print(f"Success Rate: {success_rate:.1f}%\n")
    
    # Group results by category
    gm_tests = {k: v for k, v in results.items() if k.endswith("_gm") or k == "gm_login"}
    admin_tests = {k: v for k, v in results.items() if k.endswith("_admin") or k == "admin_login"}
    
    print("GM Account Tests:")
    for test_name, passed in gm_tests.items():
        status = "✅" if passed else "❌"
        display_name = test_name.replace('_gm', '').replace('_', ' ').title()
        print(f"  {status} {display_name}")
    
    print("\nAdmin Account Tests:")
    for test_name, passed in admin_tests.items():
        status = "✅" if passed else "❌"
        display_name = test_name.replace('_admin', '').replace('_', ' ').title()
        print(f"  {status} {display_name}")
    
    if all(results.values()):
        print("\n🎉 ALL TESTS PASSED! Dashboard APIs are working correctly!")
        print("✅ All response values are React-safe (no nested objects in display fields)")
    else:
        failed_tests = [name for name, passed in results.items() if not passed]
        print(f"\n⚠️  FAILED TESTS: {', '.join(failed_tests)}")
        print("Please review the details above for specific failures.")
        
        # Check for critical React rendering issues
        critical_failures = []
        for test_name in failed_tests:
            if "nested objects" in test_name.lower() or "react" in test_name.lower():
                critical_failures.append(test_name)
        
        if critical_failures:
            print(f"\n🚨 CRITICAL: React rendering issues detected in: {', '.join(critical_failures)}")
            print("These must be fixed to prevent 'Objects are not valid as React child' errors!")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Test execution interrupted by user.")
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()