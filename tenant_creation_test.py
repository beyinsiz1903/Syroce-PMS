#!/usr/bin/env python3
"""
Test: Hotel Creation and Login Flow
Turkish Request: Yeni otel oluşturma ve giriş yapma akışını test et

Test Scenario:
1. Admin login: demo@hotel.com / demo123
2. Create new hotel via POST /api/admin/tenants
3. Login with newly created hotel credentials
4. Verify all responses
"""

import requests
import json
import sys
from datetime import datetime

# Configuration
BASE_URL = "https://code-cleanup-135.preview.emergentagent.com/api"
ADMIN_EMAIL = "demo@hotel.com"
ADMIN_PASSWORD = "demo123"

# New hotel details
NEW_HOTEL = {
    "property_name": "Test Hotel Istanbul",
    "email": "testhotel@example.com",
    "password": "test123456",
    "name": "Test Hotel Manager",
    "phone": "+90 555 123 4567",
    "address": "İstiklal Caddesi No:123, Beyoğlu",
    "location": "İstanbul, Türkiye",
    "description": "Test amaçlı oluşturulmuş otel"
}

def print_section(title):
    print(f"\n{'='*80}")
    print(f"  {title}")
    print(f"{'='*80}\n")

def print_result(test_name, success, details=""):
    status = "✅ PASSED" if success else "❌ FAILED"
    print(f"{status} - {test_name}")
    if details:
        print(f"   {details}")

def test_admin_login():
    """Step 1: Login as admin"""
    print_section("STEP 1: Admin Login")
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            user = data.get("user", {})
            
            print(f"User: {user.get('name')} ({user.get('email')})")
            print(f"Role: {user.get('role')}")
            print(f"Token: {token[:50]}..." if token else "No token")
            
            if token and user.get("role") == "admin":
                print_result("Admin Login", True, f"Logged in as {user.get('name')}")
                return token
            else:
                print_result("Admin Login", False, "Not an admin user or no token")
                return None
        else:
            print(f"Response: {response.text}")
            print_result("Admin Login", False, f"HTTP {response.status_code}")
            return None
            
    except Exception as e:
        print(f"Error: {str(e)}")
        print_result("Admin Login", False, str(e))
        return None

def test_create_hotel(admin_token):
    """Step 2: Create new hotel"""
    print_section("STEP 2: Create New Hotel")
    
    if not admin_token:
        print_result("Create Hotel", False, "No admin token available")
        return None
    
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        
        print(f"Creating hotel: {NEW_HOTEL['property_name']}")
        print(f"Email: {NEW_HOTEL['email']}")
        print(f"Manager: {NEW_HOTEL['name']}")
        
        response = requests.post(
            f"{BASE_URL}/admin/tenants",
            json=NEW_HOTEL,
            headers=headers,
            timeout=10
        )
        
        print(f"\nStatus Code: {response.status_code}")
        print(f"Response: {response.text}")
        
        if response.status_code == 200:
            data = response.json()
            tenant_id = data.get("tenant_id")
            user_id = data.get("user_id")
            
            print(f"\nTenant ID: {tenant_id}")
            print(f"User ID: {user_id}")
            
            if tenant_id and user_id:
                print_result("Create Hotel", True, f"Hotel created with ID: {tenant_id}")
                return {"tenant_id": tenant_id, "user_id": user_id}
            else:
                print_result("Create Hotel", False, "Missing tenant_id or user_id in response")
                return None
        else:
            print_result("Create Hotel", False, f"HTTP {response.status_code}")
            return None
            
    except Exception as e:
        print(f"Error: {str(e)}")
        print_result("Create Hotel", False, str(e))
        return None

def test_new_hotel_login():
    """Step 3: Login with newly created hotel credentials"""
    print_section("STEP 3: Login with New Hotel Credentials")
    
    try:
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={
                "email": NEW_HOTEL["email"],
                "password": NEW_HOTEL["password"]
            },
            timeout=10
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            token = data.get("access_token")
            user = data.get("user", {})
            tenant = data.get("tenant", {})
            
            print(f"\n✅ LOGIN SUCCESSFUL!")
            print(f"\nUser Details:")
            print(f"  - Email: {user.get('email')}")
            print(f"  - Name: {user.get('name')}")
            print(f"  - Role: {user.get('role')}")
            print(f"  - Tenant ID: {user.get('tenant_id')}")
            
            print(f"\nTenant Details:")
            print(f"  - Property Name: {tenant.get('property_name')}")
            print(f"  - Location: {tenant.get('location')}")
            print(f"  - Address: {tenant.get('address')}")
            
            print(f"\nAccess Token: {token[:50]}..." if token else "No token")
            
            # Verify expected values
            checks = []
            checks.append(("Email matches", user.get('email') == NEW_HOTEL['email']))
            checks.append(("Property name matches", tenant.get('property_name') == NEW_HOTEL['property_name']))
            checks.append(("Access token present", bool(token)))
            checks.append(("User data present", bool(user)))
            checks.append(("Tenant data present", bool(tenant)))
            
            print(f"\n{'='*80}")
            print("VERIFICATION CHECKS:")
            print(f"{'='*80}")
            all_passed = True
            for check_name, passed in checks:
                status = "✅" if passed else "❌"
                print(f"{status} {check_name}")
                if not passed:
                    all_passed = False
            
            if all_passed:
                print_result("\nNew Hotel Login", True, "All verification checks passed")
                return True
            else:
                print_result("\nNew Hotel Login", False, "Some verification checks failed")
                return False
        else:
            print(f"Response: {response.text}")
            print_result("New Hotel Login", False, f"HTTP {response.status_code} - LOGIN FAILED!")
            return False
            
    except Exception as e:
        print(f"Error: {str(e)}")
        print_result("New Hotel Login", False, str(e))
        return False

def cleanup_test_hotel(admin_token):
    """Optional: Cleanup test hotel (if endpoint exists)"""
    print_section("CLEANUP: Removing Test Hotel")
    print("Note: Cleanup endpoint may not exist - this is optional")
    # This is optional and may not be implemented
    pass

def main():
    print_section("🏨 HOTEL CREATION AND LOGIN FLOW TEST")
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Base URL: {BASE_URL}")
    
    results = {
        "admin_login": False,
        "create_hotel": False,
        "new_hotel_login": False
    }
    
    # Step 1: Admin Login
    admin_token = test_admin_login()
    results["admin_login"] = bool(admin_token)
    
    if not admin_token:
        print("\n❌ CRITICAL: Cannot proceed without admin token")
        print_final_summary(results)
        sys.exit(1)
    
    # Step 2: Create Hotel
    hotel_data = test_create_hotel(admin_token)
    results["create_hotel"] = bool(hotel_data)
    
    if not hotel_data:
        print("\n❌ CRITICAL: Hotel creation failed")
        print_final_summary(results)
        sys.exit(1)
    
    # Step 3: Login with New Hotel
    login_success = test_new_hotel_login()
    results["new_hotel_login"] = login_success
    
    # Final Summary
    print_final_summary(results)
    
    # Exit with appropriate code
    if all(results.values()):
        sys.exit(0)
    else:
        sys.exit(1)

def print_final_summary(results):
    print_section("📊 FINAL TEST SUMMARY")
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    
    print(f"Total Tests: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    print(f"Success Rate: {(passed/total)*100:.1f}%\n")
    
    for test_name, passed in results.items():
        status = "✅ PASSED" if passed else "❌ FAILED"
        print(f"{status} - {test_name}")
    
    if all(results.values()):
        print("\n🎉 ALL TESTS PASSED! Hotel creation and login flow working correctly.")
    else:
        print("\n❌ SOME TESTS FAILED! Please review the errors above.")

if __name__ == "__main__":
    main()
