#!/usr/bin/env python3
"""
Subscription Management Backend Test
Tests subscription_days parameter for hotel creation and updates
"""

import requests
import json
from datetime import datetime, timedelta

# Configuration
BASE_URL = "https://locust-load-test.preview.emergentagent.com/api"
SUPER_ADMIN_EMAIL = "demo@hotel.com"
SUPER_ADMIN_PASSWORD = "demo123"

# Test data
TEST_HOTEL_EMAIL = f"subscription.test.{datetime.now().timestamp()}@test.com"
TEST_HOTEL_DATA = {
    "property_name": "Test Subscription Hotel",
    "email": TEST_HOTEL_EMAIL,
    "password": "sub123",
    "name": "Sub Manager",
    "phone": "+90 555 111 2222",
    "address": "Test Address",
    "location": "Ankara",
    "description": "Test",
    "subscription_days": 90
}

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

def login_super_admin():
    """Login as super admin and return token"""
    print_section("1. SUPER ADMIN GİRİŞ")
    
    response = requests.post(
        f"{BASE_URL}/auth/login",
        json={
            "email": SUPER_ADMIN_EMAIL,
            "password": SUPER_ADMIN_PASSWORD
        },
        timeout=10
    )
    
    if response.status_code == 200:
        data = response.json()
        token = data.get("access_token")
        user = data.get("user", {})
        print_result("Super Admin Login", True, f"User: {user.get('name')}, Role: {user.get('role')}")
        return token
    else:
        print_result("Super Admin Login", False, f"HTTP {response.status_code}: {response.text}")
        return None

def create_hotel_with_subscription(token):
    """Create a new hotel with subscription_days parameter"""
    print_section("2. YENİ OTEL OLUŞTUR (subscription_days=90)")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.post(
        f"{BASE_URL}/admin/tenants",
        json=TEST_HOTEL_DATA,
        headers=headers,
        timeout=10
    )
    
    print(f"Request: POST /api/admin/tenants")
    print(f"Body: {json.dumps(TEST_HOTEL_DATA, indent=2)}")
    print(f"Response Status: HTTP {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        
        # Verify response fields
        checks = {
            "HTTP 200": response.status_code == 200,
            "subscription_start exists": "subscription_start" in data,
            "subscription_end exists": "subscription_end" in data,
            "subscription_days = 90": data.get("subscription_days") == 90,
        }
        
        # Verify dates
        if "subscription_start" in data and "subscription_end" in data:
            try:
                start = datetime.fromisoformat(data["subscription_start"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(data["subscription_end"].replace("Z", "+00:00"))
                days_diff = (end - start).days
                checks["subscription_end is 90 days after start"] = abs(days_diff - 90) <= 1  # Allow 1 day tolerance
                print(f"   Start: {start.strftime('%Y-%m-%d')}")
                print(f"   End: {end.strftime('%Y-%m-%d')}")
                print(f"   Days difference: {days_diff}")
            except Exception as e:
                checks["subscription_end is 90 days after start"] = False
                print(f"   Date parsing error: {e}")
        
        all_passed = all(checks.values())
        for check, passed in checks.items():
            print_result(check, passed)
        
        return data.get("tenant_id"), all_passed
    else:
        print(f"Response: {response.text}")
        print_result("Create Hotel", False, f"HTTP {response.status_code}")
        return None, False

def update_subscription_180_days(token, tenant_id):
    """Update subscription to 180 days"""
    print_section("3. SUBSCRIPTION GÜNCELLEME (180 gün)")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.patch(
        f"{BASE_URL}/admin/tenants/{tenant_id}/subscription",
        json={"subscription_days": 180},
        headers=headers,
        timeout=10
    )
    
    print(f"Request: PATCH /api/admin/tenants/{tenant_id}/subscription")
    print(f"Body: {json.dumps({'subscription_days': 180}, indent=2)}")
    print(f"Response Status: HTTP {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        
        # Verify response fields
        checks = {
            "HTTP 200": response.status_code == 200,
            "subscription_end updated": "subscription_end" in data,
            "subscription_days = 180": data.get("subscription_days") == 180,
        }
        
        # Verify dates
        if "subscription_start" in data and "subscription_end" in data:
            try:
                start = datetime.fromisoformat(data["subscription_start"].replace("Z", "+00:00"))
                end = datetime.fromisoformat(data["subscription_end"].replace("Z", "+00:00"))
                days_diff = (end - start).days
                checks["subscription_end is 180 days after start"] = abs(days_diff - 180) <= 1
                print(f"   Start: {start.strftime('%Y-%m-%d')}")
                print(f"   End: {end.strftime('%Y-%m-%d')}")
                print(f"   Days difference: {days_diff}")
            except Exception as e:
                checks["subscription_end is 180 days after start"] = False
                print(f"   Date parsing error: {e}")
        
        all_passed = all(checks.values())
        for check, passed in checks.items():
            print_result(check, passed)
        
        return all_passed
    else:
        print(f"Response: {response.text}")
        print_result("Update Subscription", False, f"HTTP {response.status_code}")
        return False

def update_subscription_unlimited(token, tenant_id):
    """Update subscription to unlimited (null)"""
    print_section("4. SINIRSIZ SUBSCRIPTION (null)")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.patch(
        f"{BASE_URL}/admin/tenants/{tenant_id}/subscription",
        json={"subscription_days": None},
        headers=headers,
        timeout=10
    )
    
    print(f"Request: PATCH /api/admin/tenants/{tenant_id}/subscription")
    print(f"Body: {json.dumps({'subscription_days': None}, indent=2)}")
    print(f"Response Status: HTTP {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Response: {json.dumps(data, indent=2)}")
        
        # Verify response fields
        checks = {
            "HTTP 200": response.status_code == 200,
            "subscription_end is null or 'Sınırsız'": data.get("subscription_end") in [None, "Sınırsız"],
            "subscription_days is 'Sınırsız'": data.get("subscription_days") == "Sınırsız",
        }
        
        all_passed = all(checks.values())
        for check, passed in checks.items():
            print_result(check, passed)
        
        return all_passed
    else:
        print(f"Response: {response.text}")
        print_result("Update to Unlimited", False, f"HTTP {response.status_code}")
        return False

def verify_hotel_in_list(token, tenant_id):
    """Verify hotel appears in list with subscription fields"""
    print_section("5. OTEL LİSTESİNDE KONTROL")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    response = requests.get(
        f"{BASE_URL}/admin/tenants",
        headers=headers,
        timeout=10
    )
    
    print(f"Request: GET /api/admin/tenants")
    print(f"Response Status: HTTP {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        tenants = data.get("tenants", [])
        
        # Find our test hotel
        test_hotel = None
        for tenant in tenants:
            if tenant.get("id") == tenant_id:
                test_hotel = tenant
                break
        
        if test_hotel:
            print(f"Found test hotel: {test_hotel.get('property_name')}")
            print(f"Hotel data: {json.dumps(test_hotel, indent=2)}")
            
            checks = {
                "Hotel found in list": True,
                "subscription_start_date field exists": "subscription_start_date" in test_hotel,
                "subscription_end_date field exists": "subscription_end_date" in test_hotel,
                "subscription_status field exists": "subscription_status" in test_hotel,
            }
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed
        else:
            print_result("Hotel found in list", False, f"Tenant ID {tenant_id} not found")
            return False
    else:
        print(f"Response: {response.text}")
        print_result("Get Tenants List", False, f"HTTP {response.status_code}")
        return False

def main():
    """Main test execution"""
    print("\n" + "="*80)
    print("  SUBSCRIPTION MANAGEMENT BACKEND TEST")
    print("  Testing subscription_days parameter for hotel creation and updates")
    print("="*80)
    
    results = {
        "super_admin_login": False,
        "create_hotel_90_days": False,
        "update_to_180_days": False,
        "update_to_unlimited": False,
        "verify_in_list": False
    }
    
    # Step 1: Login as super admin
    token = login_super_admin()
    if not token:
        print("\n❌ CRITICAL: Super admin login failed. Cannot continue tests.")
        return
    results["super_admin_login"] = True
    
    # Step 2: Create hotel with 90 days subscription
    tenant_id, success = create_hotel_with_subscription(token)
    results["create_hotel_90_days"] = success
    if not tenant_id:
        print("\n❌ CRITICAL: Hotel creation failed. Cannot continue tests.")
        print_final_summary(results)
        return
    
    # Step 3: Update subscription to 180 days
    results["update_to_180_days"] = update_subscription_180_days(token, tenant_id)
    
    # Step 4: Update subscription to unlimited
    results["update_to_unlimited"] = update_subscription_unlimited(token, tenant_id)
    
    # Step 5: Verify hotel in list
    results["verify_in_list"] = verify_hotel_in_list(token, tenant_id)
    
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
    
    for test_name, passed in results.items():
        status = "✅" if passed else "❌"
        print(f"{status} {test_name.replace('_', ' ').title()}")
    
    if all(results.values()):
        print("\n🎉 ALL TESTS PASSED! Subscription management is working correctly!")
    else:
        print("\n⚠️ SOME TESTS FAILED. Please review the details above.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()
