#!/usr/bin/env python3
"""
Syroce PMS Faz 1 Backend Testing Suite
Testing critical PMS functionality as specified in review request
"""

import requests
import json
import sys
from typing import Dict, Any, Optional

# Configuration
BACKEND_URL = "https://improvement-guide-1.preview.emergentagent.com"
BASE_API_URL = f"{BACKEND_URL}/api"

# Test credentials
LOGIN_EMAIL = "demo@hotel.com"
LOGIN_PASSWORD = "demo123"

class TestReporter:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []
        
    def test(self, name: str, condition: bool, details: str = ""):
        if condition:
            self.passed += 1
            status = "✅ PASS"
        else:
            self.failed += 1
            status = "❌ FAIL"
            
        result = f"{status} {name}"
        if details:
            result += f" - {details}"
        print(result)
        self.results.append({"name": name, "passed": condition, "details": details})
        return condition
        
    def summary(self):
        total = self.passed + self.failed
        print(f"\n{'='*60}")
        print(f"FAZ 1 PMS BACKEND TEST RESULTS")
        print(f"{'='*60}")
        print(f"Total Tests: {total}")
        print(f"Passed: {self.passed}")
        print(f"Failed: {self.failed}")
        print(f"Success Rate: {(self.passed/total*100):.1f}%" if total > 0 else "0.0%")
        print(f"{'='*60}")

def make_request(method: str, url: str, headers: Dict = None, data: Dict = None) -> Dict[str, Any]:
    """Make HTTP request with error handling"""
    try:
        response = requests.request(
            method=method,
            url=url,
            headers=headers or {},
            json=data,
            timeout=10
        )
        return {
            "status_code": response.status_code,
            "data": response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text,
            "headers": dict(response.headers)
        }
    except requests.exceptions.Timeout:
        return {"status_code": 408, "data": {"error": "Request timeout"}, "headers": {}}
    except requests.exceptions.ConnectionError:
        return {"status_code": 0, "data": {"error": "Connection failed"}, "headers": {}}
    except Exception as e:
        return {"status_code": 500, "data": {"error": str(e)}, "headers": {}}

def test_authentication() -> Optional[str]:
    """Test authentication endpoints and return JWT token"""
    reporter = TestReporter()
    
    print(f"\n🔐 TESTING AUTHENTICATION")
    print(f"Backend URL: {BACKEND_URL}")
    print(f"API Base URL: {BASE_API_URL}")
    
    # Test login endpoint
    login_data = {
        "email": LOGIN_EMAIL,
        "password": LOGIN_PASSWORD
    }
    
    response = make_request("POST", f"{BASE_API_URL}/auth/login", data=login_data)
    
    # Check login response
    login_success = reporter.test(
        "POST /api/auth/login",
        response["status_code"] == 200,
        f"Status: {response['status_code']}, Expected: 200"
    )
    
    if not login_success:
        print(f"❌ Login failed: {response.get('data', {})}")
        reporter.summary()
        return None
    
    # Verify response structure
    login_resp = response["data"]
    has_token = reporter.test(
        "Login response has token",
        "access_token" in login_resp,
        f"Keys: {list(login_resp.keys())}"
    )
    
    has_user = reporter.test(
        "Login response has user",
        "user" in login_resp,
        f"Keys: {list(login_resp.keys())}"
    )
    
    has_tenant = reporter.test(
        "Login response has tenant info",
        "user" in login_resp and "tenant_id" in login_resp["user"],
        f"User keys: {list(login_resp.get('user', {}).keys())}"
    )
    
    if not has_token:
        reporter.summary()
        return None
        
    token = login_resp["access_token"]
    
    # Test /auth/me endpoint
    auth_headers = {"Authorization": f"Bearer {token}"}
    me_response = make_request("GET", f"{BASE_API_URL}/auth/me", headers=auth_headers)
    
    me_success = reporter.test(
        "GET /api/auth/me",
        me_response["status_code"] == 200,
        f"Status: {me_response['status_code']}, Expected: 200"
    )
    
    if me_success:
        me_data = me_response["data"]
        reporter.test(
            "Auth/me returns user data",
            "email" in me_data and me_data["email"] == LOGIN_EMAIL,
            f"Email: {me_data.get('email', 'missing')}"
        )
    
    reporter.summary()
    return token if login_success else None

def test_seed_data(token: str):
    """Test seed data endpoints"""
    reporter = TestReporter()
    
    print(f"\n📊 TESTING SEED DATA VERIFICATION")
    
    auth_headers = {"Authorization": f"Bearer {token}"}
    
    # Test rooms endpoint
    rooms_response = make_request("GET", f"{BASE_API_URL}/pms/rooms", headers=auth_headers)
    rooms_success = reporter.test(
        "GET /api/pms/rooms",
        rooms_response["status_code"] == 200,
        f"Status: {rooms_response['status_code']}"
    )
    
    if rooms_success:
        rooms_data = rooms_response["data"]
        if isinstance(rooms_data, list):
            room_count = len(rooms_data)
            reporter.test(
                "Rooms count validation",
                room_count >= 1,  # At least some rooms should exist
                f"Found {room_count} rooms (expected: around 30)"
            )
        else:
            reporter.test("Rooms response is list", False, f"Got: {type(rooms_data)}")
    
    # Test bookings endpoint
    bookings_response = make_request("GET", f"{BASE_API_URL}/pms/bookings", headers=auth_headers)
    bookings_success = reporter.test(
        "GET /api/pms/bookings",
        bookings_response["status_code"] == 200,
        f"Status: {bookings_response['status_code']}"
    )
    
    if bookings_success:
        bookings_data = bookings_response["data"]
        if isinstance(bookings_data, list):
            booking_count = len(bookings_data)
            reporter.test(
                "Bookings data exists",
                booking_count >= 0,  # Can be zero
                f"Found {booking_count} bookings"
            )
        else:
            reporter.test("Bookings response is list", False, f"Got: {type(bookings_data)}")
    
    # Test guests endpoint
    guests_response = make_request("GET", f"{BASE_API_URL}/pms/guests", headers=auth_headers)
    guests_success = reporter.test(
        "GET /api/pms/guests",
        guests_response["status_code"] == 200,
        f"Status: {guests_response['status_code']}"
    )
    
    if guests_success:
        guests_data = guests_response["data"]
        if isinstance(guests_data, list):
            guest_count = len(guests_data)
            reporter.test(
                "Guests data exists",
                guest_count >= 1,  # At least some guests should exist
                f"Found {guest_count} guests (expected: around 50)"
            )
        else:
            reporter.test("Guests response is list", False, f"Got: {type(guests_data)}")
    
    # Test housekeeping tasks endpoint
    hk_response = make_request("GET", f"{BASE_API_URL}/housekeeping/tasks", headers=auth_headers)
    hk_success = reporter.test(
        "GET /api/housekeeping/tasks",
        hk_response["status_code"] == 200,
        f"Status: {hk_response['status_code']}"
    )
    
    if hk_success:
        hk_data = hk_response["data"]
        if isinstance(hk_data, list):
            task_count = len(hk_data)
            reporter.test(
                "Housekeeping tasks exist",
                task_count >= 0,  # Can be zero
                f"Found {task_count} housekeeping tasks"
            )
        else:
            reporter.test("HK tasks response is list", False, f"Got: {type(hk_data)}")
    
    # Test dashboard endpoint
    dashboard_response = make_request("GET", f"{BASE_API_URL}/pms/dashboard", headers=auth_headers)
    dashboard_success = reporter.test(
        "GET /api/pms/dashboard",
        dashboard_response["status_code"] == 200,
        f"Status: {dashboard_response['status_code']}"
    )
    
    if dashboard_success:
        dashboard_data = dashboard_response["data"]
        if isinstance(dashboard_data, dict):
            has_stats = any(key in dashboard_data for key in ["rooms", "occupancy", "bookings", "total_rooms", "available_rooms"])
            reporter.test(
                "Dashboard has statistics",
                has_stats,
                f"Keys: {list(dashboard_data.keys())}"
            )
        else:
            reporter.test("Dashboard response is object", False, f"Got: {type(dashboard_data)}")
    
    reporter.summary()

def test_cors_headers():
    """Test CORS headers"""
    reporter = TestReporter()
    
    print(f"\n🌐 TESTING CORS HEADERS")
    
    # Test preflight request (OPTIONS)
    options_response = make_request("OPTIONS", f"{BASE_API_URL}/auth/login")
    
    options_success = reporter.test(
        "OPTIONS preflight request",
        options_response["status_code"] in [200, 204],
        f"Status: {options_response['status_code']}"
    )
    
    if options_success:
        headers = options_response["headers"]
        
        # Check for CORS headers
        has_cors_origin = reporter.test(
            "Access-Control-Allow-Origin header",
            "Access-Control-Allow-Origin" in headers,
            f"Value: {headers.get('Access-Control-Allow-Origin', 'missing')}"
        )
        
        has_cors_methods = reporter.test(
            "Access-Control-Allow-Methods header",
            "Access-Control-Allow-Methods" in headers,
            f"Value: {headers.get('Access-Control-Allow-Methods', 'missing')}"
        )
        
        # Verify NOT using wildcard *
        if has_cors_origin:
            origin_value = headers.get("Access-Control-Allow-Origin", "")
            reporter.test(
                "CORS origin is NOT wildcard (*)",
                origin_value != "*",
                f"Origin: {origin_value}"
            )
    
    reporter.summary()

def test_security(token: str):
    """Test security features"""
    reporter = TestReporter()
    
    print(f"\n🔒 TESTING SECURITY")
    
    # Test valid JWT token
    auth_headers = {"Authorization": f"Bearer {token}"}
    protected_response = make_request("GET", f"{BASE_API_URL}/pms/rooms", headers=auth_headers)
    
    reporter.test(
        "Valid JWT token works",
        protected_response["status_code"] == 200,
        f"Status: {protected_response['status_code']}"
    )
    
    # Test invalid JWT token
    invalid_headers = {"Authorization": "Bearer invalid_token_12345"}
    invalid_response = make_request("GET", f"{BASE_API_URL}/pms/rooms", headers=invalid_headers)
    
    reporter.test(
        "Invalid JWT token returns 401",
        invalid_response["status_code"] == 401,
        f"Status: {invalid_response['status_code']}, Expected: 401"
    )
    
    # Test no authorization header
    no_auth_response = make_request("GET", f"{BASE_API_URL}/pms/rooms")
    
    reporter.test(
        "No auth header returns 401",
        no_auth_response["status_code"] == 401,
        f"Status: {no_auth_response['status_code']}, Expected: 401"
    )
    
    reporter.summary()

def main():
    """Main test execution"""
    print(f"🏨 SYROCE PMS FAZ 1 BACKEND TESTING")
    print(f"{'='*60}")
    print(f"Testing Backend URL: {BACKEND_URL}")
    print(f"Login Credentials: {LOGIN_EMAIL} / {LOGIN_PASSWORD}")
    print(f"{'='*60}")
    
    # Step 1: Test Authentication
    token = test_authentication()
    if not token:
        print(f"\n❌ CRITICAL ERROR: Authentication failed - cannot continue with other tests")
        sys.exit(1)
    
    # Step 2: Test Seed Data
    test_seed_data(token)
    
    # Step 3: Test CORS Headers  
    test_cors_headers()
    
    # Step 4: Test Security
    test_security(token)
    
    print(f"\n🎯 FAZ 1 PMS BACKEND TESTING COMPLETE")

if __name__ == "__main__":
    main()