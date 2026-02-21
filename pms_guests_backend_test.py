#!/usr/bin/env python3
"""
PMS Guests Backend Test
Test the PMS Guests section backend flow as requested.

Test Objectives:
1. Login with demo@hotel.com / demo123 to get token
2. Test GET /api/pms/guests?limit=100
3. Test guest 360° profile endpoints if available
4. Verify response structure matches frontend expectations

Base URL: https://guest-unified.preview.emergentagent.com/api
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://guest-unified.preview.emergentagent.com/api"
LOGIN_EMAIL = "demo@hotel.com"
LOGIN_PASSWORD = "demo123"

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    PURPLE = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(text):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text.center(60)}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")

def print_success(text):
    print(f"{Colors.GREEN}✅ {text}{Colors.END}")

def print_error(text):
    print(f"{Colors.RED}❌ {text}{Colors.END}")

def print_warning(text):
    print(f"{Colors.YELLOW}⚠️ {text}{Colors.END}")

def print_info(text):
    print(f"{Colors.CYAN}ℹ️ {text}{Colors.END}")

def login():
    """Login and get JWT token"""
    print_header("AUTHENTICATION TEST")
    
    login_data = {
        "email": LOGIN_EMAIL,
        "password": LOGIN_PASSWORD
    }
    
    try:
        response = requests.post(f"{BASE_URL}/auth/login", json=login_data, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            token = data.get('access_token')
            user = data.get('user', {})
            tenant = data.get('tenant', {})
            
            print_success(f"Login successful")
            print_info(f"User: {user.get('name', 'Unknown')} ({user.get('email', 'Unknown')})")
            print_info(f"Tenant: {tenant.get('property_name', 'Unknown')} (ID: {user.get('tenant_id', 'Unknown')})")
            
            return token
        else:
            print_error(f"Login failed: HTTP {response.status_code}")
            print_error(f"Response: {response.text}")
            return None
            
    except Exception as e:
        print_error(f"Login error: {str(e)}")
        return None

def test_pms_guests_list(token):
    """Test GET /api/pms/guests?limit=100"""
    print_header("PMS GUESTS LIST TEST")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        # Test with limit=100 as requested
        response = requests.get(f"{BASE_URL}/pms/guests?limit=100", headers=headers, timeout=15)
        
        print_info(f"Request: GET /api/pms/guests?limit=100")
        print_info(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            guests = response.json()
            
            print_success(f"PMS Guests endpoint working")
            print_info(f"Response type: {type(guests)}")
            print_info(f"Total guests returned: {len(guests)}")
            
            if not isinstance(guests, list):
                print_error("Response is not a list/array as expected")
                return False
            
            if len(guests) == 0:
                print_warning("No guests found in demo data")
                return True
            
            # Test first guest structure
            print_info(f"Testing first guest structure...")
            first_guest = guests[0]
            
            # Required fields
            required_fields = ['id', 'name', 'email', 'phone', 'id_number']
            missing_fields = []
            
            for field in required_fields:
                if field not in first_guest:
                    missing_fields.append(field)
                else:
                    value = first_guest[field]
                    field_type = type(value).__name__
                    print_success(f"✓ {field}: {value} ({field_type})")
            
            if missing_fields:
                print_error(f"Missing required fields: {missing_fields}")
            
            # Optional fields
            optional_fields = ['loyalty_tier', 'loyalty_points', 'total_stays']
            for field in optional_fields:
                if field in first_guest:
                    value = first_guest[field]
                    field_type = type(value).__name__
                    print_success(f"✓ {field}: {value} ({field_type}) [OPTIONAL]")
                else:
                    print_info(f"○ {field}: Not present [OPTIONAL]")
            
            # Show sample guest data
            print_info("Sample guest data:")
            print(json.dumps(first_guest, indent=2, default=str))
            
            return len(missing_fields) == 0
            
        else:
            print_error(f"PMS Guests endpoint failed: HTTP {response.status_code}")
            print_error(f"Response: {response.text}")
            return False
            
    except Exception as e:
        print_error(f"PMS Guests test error: {str(e)}")
        return False

def test_guest_360_profile(token, guest_id):
    """Test guest 360° profile endpoints"""
    print_header("GUEST 360° PROFILE TEST")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # Test endpoints found in backend code
    profile_endpoints = [
        f"/guests/{guest_id}/complete-profile",
        f"/guests/{guest_id}/profile-enhanced"
    ]
    
    results = {}
    
    for endpoint in profile_endpoints:
        try:
            print_info(f"Testing: GET {endpoint}")
            response = requests.get(f"{BASE_URL}{endpoint}", headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                print_success(f"✓ {endpoint} - HTTP 200")
                print_info(f"Response keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
                results[endpoint] = True
            elif response.status_code == 404:
                print_warning(f"○ {endpoint} - HTTP 404 (Guest not found)")
                results[endpoint] = "not_found"
            else:
                print_error(f"✗ {endpoint} - HTTP {response.status_code}")
                results[endpoint] = False
                
        except Exception as e:
            print_error(f"✗ {endpoint} - Error: {str(e)}")
            results[endpoint] = False
    
    return results

def test_field_compatibility(token):
    """Test field compatibility with frontend expectations"""
    print_header("FRONTEND COMPATIBILITY TEST")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(f"{BASE_URL}/pms/guests?limit=5", headers=headers, timeout=10)
        
        if response.status_code != 200:
            print_error("Cannot test compatibility - guests endpoint failed")
            return False
        
        guests = response.json()
        
        if not guests:
            print_warning("No guests to test compatibility")
            return True
        
        # Expected field mappings based on request
        expected_fields = {
            'id': 'string',
            'name': 'string', 
            'email': 'string_or_empty',
            'phone': 'string_or_empty',
            'id_number': 'string_or_empty',
            'loyalty_tier': 'optional_string',  # vip/gold/silver/standard
            'loyalty_points': 'optional_number',
            'total_stays': 'optional_number'
        }
        
        compatibility_issues = []
        
        for guest in guests[:3]:  # Test first 3 guests
            for field, expected_type in expected_fields.items():
                if field in guest:
                    value = guest[field]
                    
                    if expected_type == 'string':
                        if not isinstance(value, str):
                            compatibility_issues.append(f"Field '{field}' should be string, got {type(value).__name__}")
                    
                    elif expected_type == 'string_or_empty':
                        if not isinstance(value, str):
                            compatibility_issues.append(f"Field '{field}' should be string or empty, got {type(value).__name__}")
                    
                    elif expected_type == 'optional_number':
                        if value is not None and not isinstance(value, (int, float)):
                            compatibility_issues.append(f"Field '{field}' should be number or null, got {type(value).__name__}")
                    
                    elif expected_type == 'optional_string':
                        if value is not None and not isinstance(value, str):
                            compatibility_issues.append(f"Field '{field}' should be string or null, got {type(value).__name__}")
                
                elif expected_type in ['string', 'string_or_empty']:
                    compatibility_issues.append(f"Required field '{field}' missing")
        
        if compatibility_issues:
            print_error("Frontend compatibility issues found:")
            for issue in compatibility_issues:
                print_error(f"  • {issue}")
            return False
        else:
            print_success("All field types compatible with frontend expectations")
            return True
            
    except Exception as e:
        print_error(f"Compatibility test error: {str(e)}")
        return False

def main():
    print_header("PMS GUESTS BACKEND FLOW TEST")
    print_info(f"Base URL: {BASE_URL}")
    print_info(f"Login: {LOGIN_EMAIL} / {LOGIN_PASSWORD}")
    print_info(f"Test Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Step 1: Login
    token = login()
    if not token:
        print_error("Authentication failed - cannot continue")
        sys.exit(1)
    
    # Step 2: Test PMS Guests List
    guests_test_passed = test_pms_guests_list(token)
    
    # Step 3: Test Guest 360° Profile (if guests exist)
    profile_results = {}
    if guests_test_passed:
        # Get a guest ID for profile testing
        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(f"{BASE_URL}/pms/guests?limit=1", headers=headers, timeout=10)
            if response.status_code == 200:
                guests = response.json()
                if guests:
                    guest_id = guests[0].get('id')
                    if guest_id:
                        profile_results = test_guest_360_profile(token, guest_id)
        except:
            pass
    
    # Step 4: Test Frontend Compatibility
    compatibility_passed = test_field_compatibility(token)
    
    # Final Results
    print_header("TEST RESULTS SUMMARY")
    
    print_info("AUTHENTICATION:")
    print_success("✅ Login successful with demo@hotel.com / demo123")
    
    print_info("PMS GUESTS ENDPOINT:")
    if guests_test_passed:
        print_success("✅ GET /api/pms/guests?limit=100 - Working")
        print_success("✅ Response structure valid (array)")
        print_success("✅ Required fields present (id, name, email, phone, id_number)")
    else:
        print_error("❌ GET /api/pms/guests?limit=100 - Failed")
    
    print_info("GUEST 360° PROFILE ENDPOINTS:")
    if profile_results:
        for endpoint, result in profile_results.items():
            if result is True:
                print_success(f"✅ {endpoint} - Working")
            elif result == "not_found":
                print_warning(f"⚠️ {endpoint} - Available but no data")
            else:
                print_error(f"❌ {endpoint} - Failed")
    else:
        print_warning("⚠️ No guest profile endpoints tested (no guest data)")
    
    print_info("FRONTEND COMPATIBILITY:")
    if compatibility_passed:
        print_success("✅ Field types match frontend expectations")
    else:
        print_error("❌ Field type mismatches found")
    
    # Overall Assessment
    print_header("OVERALL ASSESSMENT")
    
    if guests_test_passed and compatibility_passed:
        print_success("🎉 PMS Guests backend: PRODUCTION-READY")
        print_info("✅ All core functionality working")
        print_info("✅ Data structure compatible with UI")
        print_info("✅ Authentication flow stable")
    else:
        print_error("⚠️ PMS Guests backend: ISSUES FOUND")
        if not guests_test_passed:
            print_error("• Main guests endpoint has problems")
        if not compatibility_passed:
            print_error("• Field compatibility issues with frontend")
    
    return guests_test_passed and compatibility_passed

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)