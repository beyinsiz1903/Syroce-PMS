#!/usr/bin/env python3
"""
Admin Authorization System Test
================================

Test Scenarios:
1. Super Admin (demo@hotel.com / demo123) - Should access all admin endpoints
2. Normal Hotel Admin (feith@test.com / feith123) - Should NOT access admin endpoints (HTTP 403)
3. Another Normal Hotel Admin (testhotel@example.com / test123456) - Should NOT access admin endpoints (HTTP 403)

Expected Results:
- ✅ Super admin: Full access to admin endpoints
- ❌ Normal admin: HTTP 403 with error message "Bu işlemi sadece platform yöneticileri yapabilir"
"""

import requests
import json
from datetime import datetime

# Base URL from frontend/.env
BASE_URL = "https://guest-unified.preview.emergentagent.com/api"

# Test credentials
SUPER_ADMIN = {
    "email": "demo@hotel.com",
    "password": "demo123",
    "expected_role": "super_admin"
}

NORMAL_ADMIN_1 = {
    "email": "feith@test.com",
    "password": "feith123",
    "expected_role": "admin"
}

NORMAL_ADMIN_2 = {
    "email": "testhotel@example.com",
    "password": "test123456",
    "expected_role": "admin"
}

def print_header(text):
    """Print formatted header"""
    print("\n" + "="*80)
    print(f"  {text}")
    print("="*80)

def print_test(text):
    """Print test description"""
    print(f"\n🧪 TEST: {text}")

def print_result(success, message):
    """Print test result"""
    icon = "✅" if success else "❌"
    print(f"{icon} {message}")

def login(credentials):
    """Login and return token and user info"""
    print(f"\n🔐 Logging in as: {credentials['email']}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={
                "email": credentials["email"],
                "password": credentials["password"]
            },
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            user = data.get("user", {})
            role = user.get("role")
            
            print(f"   ✅ Login successful")
            print(f"   📋 User: {user.get('name')} ({user.get('email')})")
            print(f"   🎭 Role: {role}")
            print(f"   🏨 Tenant ID: {user.get('tenant_id')}")
            
            # Verify role
            if role == credentials["expected_role"]:
                print(f"   ✅ Role verification: PASSED (expected: {credentials['expected_role']})")
            else:
                print(f"   ❌ Role verification: FAILED (expected: {credentials['expected_role']}, got: {role})")
            
            return token, user, role
        else:
            print(f"   ❌ Login failed: HTTP {response.status_code}")
            print(f"   Response: {response.text}")
            return None, None, None
            
    except Exception as e:
        print(f"   ❌ Login error: {str(e)}")
        return None, None, None

def test_get_tenants(token, user_email, expected_status):
    """Test GET /api/admin/tenants"""
    print_test(f"GET /api/admin/tenants (User: {user_email})")
    
    try:
        response = requests.get(
            f"{BASE_URL}/admin/tenants",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        print(f"   📊 HTTP Status: {response.status_code}")
        
        if response.status_code == expected_status:
            print_result(True, f"Status code matches expected: {expected_status}")
            
            if response.status_code == 200:
                data = response.json()
                tenants = data.get("tenants", [])
                print(f"   📋 Total tenants returned: {len(tenants)}")
                if tenants:
                    print(f"   🏨 Sample tenant: {tenants[0].get('property_name')} (ID: {tenants[0].get('id')})")
            elif response.status_code == 403:
                error_detail = response.json().get("detail", "")
                print(f"   🚫 Error message: {error_detail}")
                if "platform yöneticileri" in error_detail:
                    print_result(True, "Correct error message received")
                else:
                    print_result(False, f"Unexpected error message: {error_detail}")
            
            return True
        else:
            print_result(False, f"Status code mismatch: expected {expected_status}, got {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print_result(False, f"Request error: {str(e)}")
        return False

def test_get_module_report(token, user_email, expected_status):
    """Test GET /api/admin/module-report"""
    print_test(f"GET /api/admin/module-report (User: {user_email})")
    
    try:
        response = requests.get(
            f"{BASE_URL}/admin/module-report",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10
        )
        
        print(f"   📊 HTTP Status: {response.status_code}")
        
        if response.status_code == expected_status:
            print_result(True, f"Status code matches expected: {expected_status}")
            
            if response.status_code == 200:
                data = response.json()
                rows = data.get("rows", [])
                count = data.get("count", 0)
                print(f"   📋 Total rows in report: {count}")
                if rows:
                    print(f"   🏨 Sample row: {rows[0].get('property_name')} (Tenant ID: {rows[0].get('tenant_id')})")
            elif response.status_code == 403:
                error_detail = response.json().get("detail", "")
                print(f"   🚫 Error message: {error_detail}")
                if "platform yöneticileri" in error_detail:
                    print_result(True, "Correct error message received")
                else:
                    print_result(False, f"Unexpected error message: {error_detail}")
            
            return True
        else:
            print_result(False, f"Status code mismatch: expected {expected_status}, got {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print_result(False, f"Request error: {str(e)}")
        return False

def test_create_tenant(token, user_email, expected_status):
    """Test POST /api/admin/tenants"""
    print_test(f"POST /api/admin/tenants (User: {user_email})")
    
    # Generate unique test data
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    test_data = {
        "property_name": f"Test Hotel {timestamp}",
        "email": f"testhotel{timestamp}@example.com",
        "password": "testpass123",
        "name": "Test Admin",
        "phone": "+90 555 123 4567",
        "address": "Test Address, Istanbul",
        "location": "Istanbul",
        "description": "Test hotel created by authorization test"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/admin/tenants",
            headers={"Authorization": f"Bearer {token}"},
            json=test_data,
            timeout=10
        )
        
        print(f"   📊 HTTP Status: {response.status_code}")
        
        if response.status_code == expected_status:
            print_result(True, f"Status code matches expected: {expected_status}")
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ Tenant created successfully")
                print(f"   🏨 Tenant ID: {data.get('tenant_id')}")
                print(f"   👤 User ID: {data.get('user_id')}")
                print(f"   📧 Email: {test_data['email']}")
            elif response.status_code == 403:
                error_detail = response.json().get("detail", "")
                print(f"   🚫 Error message: {error_detail}")
                if "platform yöneticileri" in error_detail:
                    print_result(True, "Correct error message received")
                else:
                    print_result(False, f"Unexpected error message: {error_detail}")
            
            return True
        else:
            print_result(False, f"Status code mismatch: expected {expected_status}, got {response.status_code}")
            print(f"   Response: {response.text[:200]}")
            return False
            
    except Exception as e:
        print_result(False, f"Request error: {str(e)}")
        return False

def run_test_scenario(credentials, scenario_name, expected_results):
    """Run all tests for a specific user scenario"""
    print_header(f"SCENARIO: {scenario_name}")
    
    # Login
    token, user, role = login(credentials)
    if not token:
        print_result(False, "Login failed - cannot proceed with tests")
        return {
            "scenario": scenario_name,
            "login": False,
            "tests_passed": 0,
            "tests_total": 0
        }
    
    # Run tests
    results = []
    
    # Test 1: GET /api/admin/tenants
    result = test_get_tenants(token, credentials["email"], expected_results["get_tenants"])
    results.append(result)
    
    # Test 2: GET /api/admin/module-report
    result = test_get_module_report(token, credentials["email"], expected_results["get_module_report"])
    results.append(result)
    
    # Test 3: POST /api/admin/tenants
    result = test_create_tenant(token, credentials["email"], expected_results["create_tenant"])
    results.append(result)
    
    # Summary
    passed = sum(results)
    total = len(results)
    
    print(f"\n📊 Scenario Summary: {passed}/{total} tests passed")
    
    return {
        "scenario": scenario_name,
        "login": True,
        "role": role,
        "tests_passed": passed,
        "tests_total": total,
        "success": passed == total
    }

def main():
    """Main test execution"""
    print_header("ADMIN AUTHORIZATION SYSTEM TEST")
    print(f"Base URL: {BASE_URL}")
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    all_results = []
    
    # Scenario 1: Super Admin - Should have full access
    result1 = run_test_scenario(
        SUPER_ADMIN,
        "Super Admin (demo@hotel.com)",
        {
            "get_tenants": 200,
            "get_module_report": 200,
            "create_tenant": 200
        }
    )
    all_results.append(result1)
    
    # Scenario 2: Normal Admin 1 - Should be blocked (HTTP 403)
    result2 = run_test_scenario(
        NORMAL_ADMIN_1,
        "Normal Hotel Admin (feith@test.com)",
        {
            "get_tenants": 403,
            "get_module_report": 403,
            "create_tenant": 403
        }
    )
    all_results.append(result2)
    
    # Scenario 3: Normal Admin 2 - Should be blocked (HTTP 403)
    result3 = run_test_scenario(
        NORMAL_ADMIN_2,
        "Normal Hotel Admin (testhotel@example.com)",
        {
            "get_tenants": 403,
            "get_module_report": 403,
            "create_tenant": 403
        }
    )
    all_results.append(result3)
    
    # Final Summary
    print_header("FINAL TEST SUMMARY")
    
    total_scenarios = len(all_results)
    successful_scenarios = sum(1 for r in all_results if r.get("success", False))
    total_tests = sum(r.get("tests_total", 0) for r in all_results)
    passed_tests = sum(r.get("tests_passed", 0) for r in all_results)
    
    print(f"\n📊 Overall Results:")
    print(f"   Scenarios: {successful_scenarios}/{total_scenarios} passed")
    print(f"   Tests: {passed_tests}/{total_tests} passed")
    print(f"   Success Rate: {(passed_tests/total_tests*100):.1f}%")
    
    print(f"\n📋 Detailed Results:")
    for result in all_results:
        status = "✅ PASSED" if result.get("success") else "❌ FAILED"
        print(f"   {status} - {result['scenario']}")
        print(f"      Role: {result.get('role', 'N/A')}")
        print(f"      Tests: {result.get('tests_passed')}/{result.get('tests_total')}")
    
    # Verification
    print(f"\n🎯 Authorization Verification:")
    
    super_admin_success = all_results[0].get("success", False)
    normal_admin_1_blocked = all_results[1].get("success", False)
    normal_admin_2_blocked = all_results[2].get("success", False)
    
    if super_admin_success:
        print_result(True, "Super admin has full access to admin endpoints")
    else:
        print_result(False, "Super admin access verification FAILED")
    
    if normal_admin_1_blocked:
        print_result(True, "Normal admin 1 (feith@test.com) correctly blocked from admin endpoints")
    else:
        print_result(False, "Normal admin 1 blocking verification FAILED")
    
    if normal_admin_2_blocked:
        print_result(True, "Normal admin 2 (testhotel@example.com) correctly blocked from admin endpoints")
    else:
        print_result(False, "Normal admin 2 blocking verification FAILED")
    
    # Final verdict
    all_passed = super_admin_success and normal_admin_1_blocked and normal_admin_2_blocked
    
    print_header("FINAL VERDICT")
    if all_passed:
        print("✅ ADMIN AUTHORIZATION SYSTEM: WORKING CORRECTLY")
        print("   - Super admin can access all admin endpoints")
        print("   - Normal hotel admins are correctly blocked (HTTP 403)")
        print("   - Error message is correct: 'Bu işlemi sadece platform yöneticileri yapabilir'")
    else:
        print("❌ ADMIN AUTHORIZATION SYSTEM: ISSUES DETECTED")
        print("   Please review the detailed results above")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    exit(main())
