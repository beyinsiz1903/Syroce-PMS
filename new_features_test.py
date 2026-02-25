#!/usr/bin/env python3
"""
New Features Backend Test: Billing History, Plan Downgrade, and Hotel Info Update

Tests the following new endpoints:
1. PATCH /api/hotel/info - Update hotel information with validation
2. POST /api/subscription/change-plan - Upgrade/Downgrade subscription plans
3. GET /api/billing/history - Get billing/plan change history
"""

import requests
import json
from datetime import datetime
import os

# Configuration
BASE_URL = "https://hotel-pms-demo.preview.emergentagent.com/api"

# Test credentials from review request
BASIC_HOTEL = {"email": "demo@butikotel.com", "password": "demo123"}
PROFESSIONAL_HOTEL = {"email": "demo@grandcity.com", "password": "demo123"}

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

def login_user(email, password, user_type=""):
    """Login and return token"""
    print(f"Logging in as {user_type}: {email}")
    
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
            tenant = data.get("tenant", {})
            
            print_result(f"Login {user_type}", True, 
                        f"User: {user.get('name')}, Hotel: {tenant.get('property_name')}, Tier: {tenant.get('subscription_tier')}")
            return token, user, tenant
        else:
            print_result(f"Login {user_type}", False, f"HTTP {response.status_code}: {response.text}")
            return None, None, None
            
    except Exception as e:
        print_result(f"Login {user_type}", False, f"Exception: {str(e)}")
        return None, None, None

def test_hotel_info_update(token, test_data, expected_success=True):
    """Test PATCH /api/hotel/info"""
    print_section("HOTEL INFO UPDATE TEST")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.patch(
            f"{BASE_URL}/hotel/info",
            json=test_data,
            headers=headers,
            timeout=30
        )
        
        print(f"Request: PATCH /api/hotel/info")
        print(f"Payload: {json.dumps(test_data, indent=2)}")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200 and expected_success:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            
            # Verify update was successful
            tenant = data.get('tenant', {})
            checks = {
                "HTTP 200": True,
                "Success field": data.get('success') == True,
                "Tenant data returned": 'tenant' in data,
            }
            
            # Check specific fields that were updated
            if 'property_name' in test_data:
                checks["Property name updated"] = tenant.get('property_name') == test_data['property_name']
            if 'phone' in test_data:
                checks["Phone updated"] = tenant.get('phone') == test_data['phone']
            if 'address' in test_data:
                checks["Address updated"] = tenant.get('address') == test_data['address']
            if 'location' in test_data:
                checks["Location updated"] = tenant.get('location') == test_data['location']
            if 'description' in test_data:
                checks["Description updated"] = tenant.get('description') == test_data['description']
            if 'total_rooms' in test_data:
                checks["Total rooms updated"] = tenant.get('total_rooms') == test_data['total_rooms']
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed
            
        elif not expected_success:
            # Expected to fail
            print(f"Response: {response.text}")
            
            checks = {
                "HTTP 400 (expected failure)": response.status_code == 400,
                "Has error message": len(response.text) > 0,
            }
            
            # Check for specific error messages
            if response.status_code == 400:
                response_text = response.text.lower()
                if 'room' in response_text and 'limit' in response_text:
                    checks["Room limit error message"] = True
                elif 'basic' in response_text and '15' in response_text:
                    checks["Basic tier limit mentioned"] = True
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed
        else:
            print_result("Hotel Info Update", False, f"HTTP {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        print_result("Hotel Info Update", False, f"Exception: {str(e)}")
        return False

def test_plan_change(token, new_tier, billing_cycle="monthly", expected_success=True, user_info=""):
    """Test POST /api/subscription/change-plan"""
    print_section(f"PLAN CHANGE TEST: {new_tier.upper()} ({billing_cycle}) - {user_info}")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        payload = {
            "new_tier": new_tier,
            "billing_cycle": billing_cycle
        }
        
        response = requests.post(
            f"{BASE_URL}/subscription/change-plan",
            json=payload,
            headers=headers,
            timeout=30
        )
        
        print(f"Request: POST /api/subscription/change-plan")
        print(f"Payload: {json.dumps(payload, indent=2)}")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200 and expected_success:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            
            checks = {
                "HTTP 200": True,
                "Success field": data.get('success') == True,
                "Has tier field": 'tier' in data,
                "Has is_downgrade field": 'is_downgrade' in data,
                "Has billing_cycle field": 'billing_cycle' in data,
            }
            
            # Verify tier change
            if 'tier' in data:
                checks[f"Tier changed to {new_tier}"] = data.get('tier') == new_tier
            if 'billing_cycle' in data:
                checks[f"Billing cycle set to {billing_cycle}"] = data.get('billing_cycle') == billing_cycle
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed, data.get('is_downgrade', False)
            
        elif not expected_success:
            # Expected to fail
            print(f"Response: {response.text}")
            response_text = response.text.lower() if response.text else ""
            
            checks = {
                "HTTP 400 (expected failure)": response.status_code == 400,
                "Has error message": len(response.text) > 0,
            }
            
            # Check for specific error messages
            if "zaten bu plandasınız" in response_text or "already on this plan" in response_text:
                checks["Same plan error message"] = True
            elif "limit" in response_text:
                checks["Limit exceeded error"] = True
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed, None
        else:
            print_result("Plan Change", False, f"HTTP {response.status_code}: {response.text}")
            return False, None
            
    except Exception as e:
        print_result("Plan Change", False, f"Exception: {str(e)}")
        return False, None

def test_billing_history(token, expected_min_records=0):
    """Test GET /api/billing/history"""
    print_section("BILLING HISTORY TEST")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(
            f"{BASE_URL}/billing/history",
            headers=headers,
            timeout=30
        )
        
        print(f"Request: GET /api/billing/history")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Response: {json.dumps(data, indent=2)}")
            
            records = data.get('records', [])
            
            checks = {
                "HTTP 200": True,
                "Has records field": 'records' in data,
                f"At least {expected_min_records} records": len(records) >= expected_min_records,
            }
            
            # Check record structure if records exist
            if records:
                sample_record = records[0]
                required_fields = ['id', 'tenant_id', 'action', 'from_tier', 'to_tier', 
                                 'amount', 'currency', 'status', 'created_at']
                
                for field in required_fields:
                    checks[f"Record has {field}"] = field in sample_record
                
                # Check for upgrade/downgrade actions
                actions = [r.get('action', '') for r in records]
                if 'upgrade' in actions:
                    checks["Has upgrade record"] = True
                if 'downgrade' in actions:
                    checks["Has downgrade record"] = True
                
                print(f"Found {len(records)} billing records")
                for i, record in enumerate(records[:3]):  # Show first 3
                    print(f"  Record {i+1}: {record.get('action')} from {record.get('from_tier')} to {record.get('to_tier')} - {record.get('amount')} {record.get('currency')}")
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed, records
        else:
            print_result("Billing History", False, f"HTTP {response.status_code}: {response.text}")
            return False, []
            
    except Exception as e:
        print_result("Billing History", False, f"Exception: {str(e)}")
        return False, []

def test_current_subscription(token):
    """Test GET /api/subscription/current to verify current state"""
    print_section("CURRENT SUBSCRIPTION CHECK")
    
    try:
        headers = {"Authorization": f"Bearer {token}"}
        
        response = requests.get(
            f"{BASE_URL}/subscription/current",
            headers=headers,
            timeout=30
        )
        
        print(f"Request: GET /api/subscription/current")
        print(f"Response Status: HTTP {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Current subscription: {json.dumps(data, indent=2)}")
            
            checks = {
                "HTTP 200": True,
                "Has tier/plan field": 'tier' in data or 'plan' in data,
            }
            
            current_tier = data.get('tier') or data.get('plan', {}).get('tier')
            if current_tier:
                print(f"Current tier: {current_tier}")
                checks["Has valid tier"] = current_tier in ['basic', 'professional', 'enterprise']
            
            all_passed = all(checks.values())
            for check, passed in checks.items():
                print_result(check, passed)
            
            return all_passed, current_tier
        else:
            print_result("Current Subscription Check", False, f"HTTP {response.status_code}: {response.text}")
            return False, None
            
    except Exception as e:
        print_result("Current Subscription Check", False, f"Exception: {str(e)}")
        return False, None

def main():
    """Main test execution following the test cases from review request"""
    print("\n" + "="*80)
    print("  NEW FEATURES BACKEND TEST")
    print("  Testing: Billing History, Plan Downgrade, and Hotel Info Update")
    print("="*80)
    
    results = {
        "basic_hotel_login": False,
        "professional_hotel_login": False,
        "hotel_info_update_success": False,
        "plan_upgrade": False,
        "plan_downgrade": False,
        "billing_history": False,
        "same_plan_check": False,
        "room_limit_check": False,
        "downgrade_limit_check": False,
    }
    
    # Test 1: Login as Basic hotel (demo@butikotel.com)
    print_section("1. BASIC HOTEL LOGIN")
    basic_token, basic_user, basic_tenant = login_user(
        BASIC_HOTEL["email"], BASIC_HOTEL["password"], "Basic Hotel"
    )
    if not basic_token:
        print("\n❌ CRITICAL: Basic hotel login failed. Cannot continue tests.")
        print_final_summary(results)
        return
    results["basic_hotel_login"] = True
    
    # Test 2: Hotel Info Update (success case)
    hotel_info_data = {
        "property_name": "Butik Otel Antalya Deluxe",
        "phone": "+905559999999", 
        "address": "Kaleiçi Mah. No:5, Antalya",
        "location": "Antalya",
        "description": "Akdeniz manzaralı butik otel"
    }
    
    hotel_info_success = test_hotel_info_update(basic_token, hotel_info_data, True)
    results["hotel_info_update_success"] = hotel_info_success
    
    # Test 3: Plan Change - Upgrade to Professional
    upgrade_success, is_downgrade = test_plan_change(
        basic_token, "professional", "monthly", True, "Basic → Professional"
    )
    results["plan_upgrade"] = upgrade_success
    
    # Test 4: Plan Change - Downgrade back to Basic
    downgrade_success, is_downgrade = test_plan_change(
        basic_token, "basic", "yearly", True, "Professional → Basic"
    )
    results["plan_downgrade"] = downgrade_success
    
    # Test 5: Billing History (should have at least 2 records from upgrade + downgrade)
    billing_success, billing_records = test_billing_history(basic_token, 2)
    results["billing_history"] = billing_success
    
    # Test 6: Same plan check (should fail)
    same_plan_success, _ = test_plan_change(
        basic_token, "basic", "monthly", False, "Same Plan Check"
    )
    results["same_plan_check"] = same_plan_success
    
    # Test 7: Room limit check (should fail for Basic tier)
    room_limit_data = {"total_rooms": 100}  # Basic max is 15
    room_limit_success = test_hotel_info_update(basic_token, room_limit_data, False)
    results["room_limit_check"] = room_limit_success
    
    # Test 8: Login as Professional hotel
    print_section("8. PROFESSIONAL HOTEL LOGIN")
    pro_token, pro_user, pro_tenant = login_user(
        PROFESSIONAL_HOTEL["email"], PROFESSIONAL_HOTEL["password"], "Professional Hotel"
    )
    if not pro_token:
        print("\n⚠️ Professional hotel login failed. Skipping downgrade limit test.")
    else:
        results["professional_hotel_login"] = True
        
        # Test 9: Check current subscription for Professional hotel
        current_success, current_tier = test_current_subscription(pro_token)
        
        # Test 10: Downgrade limit check (try downgrading Professional to Basic)
        downgrade_limit_success, _ = test_plan_change(
            pro_token, "basic", "monthly", True, "Professional → Basic (Limit Check)"
        )
        results["downgrade_limit_check"] = downgrade_limit_success
    
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
    login_tests = {k: v for k, v in results.items() if 'login' in k}
    feature_tests = {k: v for k, v in results.items() if 'login' not in k}
    
    print("🔐 LOGIN TESTS:")
    for test_name, passed in login_tests.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {test_name.replace('_', ' ').title()}")
    
    print("\n🚀 FEATURE TESTS:")
    for test_name, passed in feature_tests.items():
        status = "✅" if passed else "❌"
        print(f"  {status} {test_name.replace('_', ' ').title()}")
    
    if all(results.values()):
        print("\n🎉 ALL TESTS PASSED! New features are working correctly!")
    else:
        failed_tests = [name.replace('_', ' ').title() for name, passed in results.items() if not passed]
        print(f"\n⚠️  FAILED TESTS: {', '.join(failed_tests)}")
        print("Please review the details above for specific failures.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n⚠️  Test execution interrupted by user.")
    except Exception as e:
        print(f"\n❌ CRITICAL ERROR: {e}")
        import traceback
        traceback.print_exc()